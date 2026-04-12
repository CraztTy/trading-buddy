"""
通用回测异步任务：进程内 dict（默认）或 Redis 列表队列 + JSON 任务记录。

环境变量：
- ``BACKTEST_ASYNC_JOB_STORE``：``auto``（``REDIS_ENABLED`` 且已连接客户端时用 Redis）、
  ``memory``、``redis``（强制 Redis；未连接时 POST 异步回测返回 503）。
- ``BACKTEST_ASYNC_JOB_TTL_SEC``：Redis 中任务 JSON 的过期秒数（默认 604800，7 天）。
- ``BACKTEST_ASYNC_JOB_STUCK_SEC``：**running** 超过该秒数未结束时，**GET /api/backtest/jobs/{id}** 可将任务置为 **failed** 并写 ``finished_at``（默认 1800；``0`` 关闭）。与执行器并发时存在极小竞态，宜保守设大。

队列键 ``tb:backtest:job:queue``；任务键 ``tb:backtest:job:{job_id}``。
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import HTTPException
from redis.asyncio import Redis

from src.common.config import get_settings
from src.common.redis_client import get_redis_client

QUEUE_KEY = "tb:backtest:job:queue"


def utc_now_iso_z() -> str:
    """UTC ISO-8601，秒精度，``Z`` 后缀（便于日志与客户端展示）。"""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def job_record_key(job_id: str) -> str:
    return f"tb:backtest:job:{job_id}"


def _store_raw() -> str:
    return (os.environ.get("BACKTEST_ASYNC_JOB_STORE") or "auto").strip().lower()


def configured_prefers_redis_jobs() -> bool:
    raw = _store_raw()
    if raw == "memory":
        return False
    if raw == "redis":
        return True
    return bool(get_settings().redis.enabled)


def effective_redis_async_jobs() -> bool:
    """是否实际走 Redis（配置希望 Redis 且全局客户端已创建）。"""
    return configured_prefers_redis_jobs() and get_redis_client() is not None


def catalog_async_job_persistence() -> Literal["memory", "redis"]:
    return "redis" if effective_redis_async_jobs() else "memory"


def job_ttl_sec() -> int:
    try:
        return max(60, int(os.environ.get("BACKTEST_ASYNC_JOB_TTL_SEC", "604800")))
    except ValueError:
        return 604800


def stuck_running_cutoff_utc() -> datetime | None:
    """``running`` 早于该时刻则视为卡住，可回收；``BACKTEST_ASYNC_JOB_STUCK_SEC<=0`` 时关闭。"""
    try:
        sec = int(os.environ.get("BACKTEST_ASYNC_JOB_STUCK_SEC", "1800"))
    except ValueError:
        sec = 1800
    if sec <= 0:
        return None
    return datetime.now(timezone.utc) - timedelta(seconds=sec)


def parse_iso_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    t = value.strip()
    if not t:
        return None
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


STALE_RUNNING_RECLAIM_MSG = (
    "执行一直处于 running 且超过 BACKTEST_ASYNC_JOB_STUCK_SEC，已置为 failed（GET 回收）"
)
JOB_CANCELLED_MSG = "cancelled"


def is_running_stale(rec: dict[str, Any]) -> bool:
    if rec.get("status") != "running":
        return False
    cutoff = stuck_running_cutoff_utc()
    if cutoff is None:
        return False
    started = parse_iso_utc(rec.get("started_at"))
    if started is None:
        return False
    return started < cutoff


async def reclaim_stale_running_redis(r: Redis, job_id: str, rec: dict[str, Any]) -> dict[str, Any]:
    if not is_running_stale(rec):
        return rec
    out = {
        **rec,
        "status": "failed",
        "error": STALE_RUNNING_RECLAIM_MSG,
        "result": None,
        "finished_at": utc_now_iso_z(),
    }
    await _redis_set_record(r, job_id, out)
    return out


def enforce_redis_job_store_or_503() -> None:
    """``BACKTEST_ASYNC_JOB_STORE=redis`` 时若 Redis 不可用则拒绝受理。"""
    if _store_raw() != "redis":
        return
    s = get_settings()
    if not s.redis.enabled or get_redis_client() is None:
        raise HTTPException(
            status_code=503,
            detail="BACKTEST_ASYNC_JOB_STORE=redis 需要 REDIS_ENABLED 且 API 已连接 Redis",
        )


async def run_mvp_job_execution(body: Any) -> tuple[Literal["completed", "failed"], dict | None, str | None]:
    """
    执行已校验的 ``BacktestRunMvpRequest``；返回 (completed|failed, result dict 或 None, error 或 None)。
    """
    from src.api.routers import backtest as bt
    from src.data.storage import get_database

    try:
        async with get_database().session() as session:
            out = await bt._execute_run_mvp(session, body)
        return ("completed", out.model_dump(mode="json"), None)
    except HTTPException as he:
        detail = he.detail
        msg = detail if isinstance(detail, str) else str(detail)
        return ("failed", None, msg)
    except Exception as e:
        return ("failed", None, str(e))


async def _redis_get_record(r: Redis, job_id: str) -> dict[str, Any] | None:
    raw = await r.get(job_record_key(job_id))
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode()
    data = json.loads(raw)
    return data if isinstance(data, dict) else None


async def _redis_set_record(r: Redis, job_id: str, record: dict[str, Any]) -> None:
    ttl = job_ttl_sec()
    await r.set(
        job_record_key(job_id),
        json.dumps(record, ensure_ascii=False),
        ex=ttl,
    )


async def enqueue_redis_async_job(r: Redis, job_id: str, body: Any) -> None:
    """写入 pending 记录并入队（须先 ``SET`` 再 ``LPUSH``，与 worker 顺序一致）。"""
    body_dict = body.model_dump(mode="json")
    record: dict[str, Any] = {
        "status": "pending",
        "request": body_dict,
        "result": None,
        "error": None,
        "queued_at": utc_now_iso_z(),
        "started_at": None,
        "finished_at": None,
    }
    ttl = job_ttl_sec()
    pipe = r.pipeline(transaction=True)
    pipe.set(
        job_record_key(job_id),
        json.dumps(record, ensure_ascii=False),
        ex=ttl,
    )
    pipe.lpush(QUEUE_KEY, job_id)
    await pipe.execute()


async def redis_job_status_snapshot(r: Redis, job_id: str) -> dict[str, Any] | None:
    """供 HTTP GET：与进程内 ``_mvp_jobs`` 条目形状对齐。"""
    return await _redis_get_record(r, job_id)


async def cancel_redis_pending_job(r: Redis, job_id: str) -> Literal["absent", "ok", "bad_state"]:
    """仅 ``pending`` 可取消；写入 ``cancelled`` 终态。"""
    rec = await _redis_get_record(r, job_id)
    if rec is None:
        return "absent"
    if rec.get("status") != "pending":
        return "bad_state"
    rec["status"] = "cancelled"
    rec["error"] = JOB_CANCELLED_MSG
    rec["result"] = None
    rec["finished_at"] = utc_now_iso_z()
    await _redis_set_record(r, job_id, rec)
    return "ok"


async def _process_one_queued_job(r: Redis, job_id: str) -> None:
    from src.api.routers.backtest import BacktestRunMvpRequest

    rec = await _redis_get_record(r, job_id)
    if rec is None:
        return
    if rec.get("status") == "cancelled":
        return
    if rec.get("status") != "pending":
        return
    try:
        body = BacktestRunMvpRequest.model_validate(rec.get("request") or {})
    except Exception as e:
        rec["status"] = "failed"
        rec["error"] = f"invalid job request: {e}"
        rec["finished_at"] = utc_now_iso_z()
        await _redis_set_record(r, job_id, rec)
        return

    rec = await _redis_get_record(r, job_id)
    if rec is None or rec.get("status") != "pending":
        return

    rec["status"] = "running"
    rec["error"] = None
    rec["started_at"] = utc_now_iso_z()
    await _redis_set_record(r, job_id, rec)

    status, payload, err = await run_mvp_job_execution(body)
    rec = await _redis_get_record(r, job_id)
    if rec is None:
        return
    if rec.get("status") != "running":
        return
    if status == "completed":
        rec["status"] = "completed"
        rec["result"] = payload
        rec["error"] = None
    else:
        rec["status"] = "failed"
        rec["result"] = None
        rec["error"] = err or "failed"
    rec["finished_at"] = utc_now_iso_z()
    await _redis_set_record(r, job_id, rec)


async def redis_job_consumer_loop(stop: asyncio.Event) -> None:
    """BRPOP 队列并执行；在 lifespan 中 ``create_task`` 启动。"""
    r = get_redis_client()
    if r is None:
        return
    while not stop.is_set():
        try:
            out = await r.brpop(QUEUE_KEY, timeout=5)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(1)
            continue
        if out is None:
            continue
        try:
            _, job_id_raw = out
        except (TypeError, ValueError):
            continue
        job_id = (
            job_id_raw.decode()
            if isinstance(job_id_raw, (bytes, bytearray))
            else str(job_id_raw)
        )
        if not job_id.strip():
            continue
        try:
            await _process_one_queued_job(r, job_id.strip())
        except Exception:
            await asyncio.sleep(0)


async def start_backtest_async_job_consumer(app: Any) -> None:
    if not configured_prefers_redis_jobs():
        return
    r = get_redis_client()
    if r is None:
        return
    stop = asyncio.Event()
    app.state._backtest_async_job_consumer_stop = stop
    app.state._backtest_async_job_consumer_task = asyncio.create_task(
        redis_job_consumer_loop(stop),
        name="tb-backtest-async-jobs",
    )


async def stop_backtest_async_job_consumer(app: Any) -> None:
    stop = getattr(app.state, "_backtest_async_job_consumer_stop", None)
    task = getattr(app.state, "_backtest_async_job_consumer_task", None)
    if stop is not None:
        stop.set()
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
