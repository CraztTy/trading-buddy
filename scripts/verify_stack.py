#!/usr/bin/env python3
"""
验证当前 .env：数据库（MySQL 或 SQLite）/ Redis 是否按配置工作，并冒烟测试核心 API 路由
（含 ``/openapi.json``、``/api/data/trade-calendar/options``、``status``、``/api/strategies/catalog``、
``/api/backtest/catalog``、``/api/factors/catalog``）；有指数 overview 日期时再冒烟 **``GET /api/factors/cross-section``**。
契约通过后另做回测异步轻量校验：**``GET /api/backtest/jobs/{不存在}`` → 404**；
**``POST /api/backtest/jobs/{不存在}/cancel`` → 404**；
**``POST /api/backtest/run?async=true``** 且非法 ``strategy_id`` → **400**（不创建 job）。
在全部 GET 返回 200 后，额外校验：
（1）``/api/strategies/catalog`` 含 ``ma_cross`` / ``ma_cross_scan`` / ``buy_hold``；**``strategy_contract_version``** 为 ``1``；
**``id``** 与 **``backtest_run.strategy_id``** 一致；**``signal_params``** 为对象、**``backtest_archive_kinds``** 非空且与
条目约定一致；**``backtest_run.params_schema``** 为对象；
各条目 **``backtest_run.archive_kind``** 须出现在 **``backtest_archive_kinds``** 中；
各条目含 ``backtest_run``（**``strategy_version``** ``1``）；
（2）``/api/backtest/catalog``：**``engine_version``** 与内核 **``ENGINE_VERSION``** 一致；无重复
``strategy_id``；各条目含 ``strategy_version``（``1``）/ ``title`` / ``description`` / ``response_shape`` /
``get_equivalent_paths``（与 ``strategy_id`` 同义 GET 路径，顺序与内核一致）；``strategy_id`` 集合与 ``POST /api/backtest/run`` 支持的一致；**``post_run_path``** /
**``doc_ref``** 与 **``BacktestEngineCatalogResponse``** 默认值一致；**``async_run_query_param``** 为 ``async``、**``async_job_status_path_template``** 为 ``/api/backtest/jobs/{job_id}``、**``async_job_persistence``** 为 ``memory`` 或 ``redis`` 且与 **``catalog_async_job_persistence()``** 一致；
**``async_job_queue_key``** / **``async_job_queue_depth``** 在 ``memory`` 时须为 ``null``，在 ``redis`` 时须分别为 **``tb:backtest:job:queue``** 与 **非负整数**（与 **``LLEN``** 一致）；
且与策略 catalog 的 ``archive_kind`` 对齐；
（3）``/api/factors/catalog``：**``preview_path``** / **``doc_ref``** 与 **``FactorCatalogResponse``** 默认一致；
``ops`` 非空且每条含 ``id`` / ``window`` / ``column`` / ``series_keys``（``window``∈``required|optional|unused``，
``column``∈``ohlcv|ignored``），且 **``ops[].id`` 集合与 ``OpName``** 一致。
（4）若 **``GET /api/dashboard/overview``** 的 **``indices[0].date``** 存在：``GET /api/factors/cross-section``（同 **``as_of_date``**，**``period=20``**，**``max_codes=20``**）须 **200**，且体与 **``FactorCrossSectionResponse``** 字段一致；**503**（窗口查询失败）记 **FAIL**。无指数日期时打印 **[SKIP]** 跳过本条。

**设计约定**：栈探测需导入 ``src``（``app``、存储、``ENGINE_VERSION``、``OpName`` 等），属正常依赖。
**catalog 形态与跨 catalog 对齐的纯断言函数保留在本文件**（单测通过 ``importlib`` 加载本模块复用），
**不**迁入 ``src/``，以免应用包与运维脚本形成额外双向耦合。

用法（项目根目录）::

    python scripts/verify_stack.py
    python scripts/verify_stack.py --skip-db   # 跳过 DB 行数统计（缺表/未灌 trade_calendar 时仍可跑 API 与契约）

若 DB 阶段失败且未使用 ``--skip-db``，会额外打印 ``[HINT]`` 行提示上述重试命令。

"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


async def _db_table_counts() -> tuple[int, int, dict]:
    from sqlalchemy import func, select

    from src.data.quality.trade_calendar_table import trade_calendar_table_summary
    from src.data.storage import dispose_database, get_database
    from src.data.storage.models import DailyKlineModel, StockInfoModel

    db = get_database()
    try:
        async with db.session() as session:
            ns = await session.scalar(select(func.count()).select_from(StockInfoModel))
            nk = await session.scalar(select(func.count()).select_from(DailyKlineModel))
            tc = await trade_calendar_table_summary(session)
            return int(ns or 0), int(nk or 0), tc
    finally:
        await dispose_database()


def _redis_probe() -> dict:
    from src.common import get_settings
    import redis

    s = get_settings()
    if not s.redis.enabled:
        return {"enabled": False, "ok": None, "sample_keys": 0}
    r = redis.Redis(
        host=s.redis.host,
        port=s.redis.port,
        db=s.redis.db,
        password=s.redis.password or None,
        decode_responses=True,
        socket_connect_timeout=5,
    )
    try:
        r.ping()
        sample = 0
        for _ in r.scan_iter(match="tb:stkname:*", count=200):
            sample += 1
            if sample >= 500:
                break
        return {"enabled": True, "ok": True, "sample_keys": sample, "host": s.redis.host}
    except Exception as e:
        return {"enabled": True, "ok": False, "error": str(e)}
    finally:
        r.close()


def _api_routes() -> list[tuple[str, int]]:
    from fastapi.testclient import TestClient

    from src.api.main import app

    out: list[tuple[str, int]] = []
    with TestClient(app) as client:
        for path in (
            "/health",
            "/health/ready",
            "/openapi.json",
            "/api/dashboard/overview",
            "/api/dashboard/gainers?limit=3",
            "/api/dashboard/losers?limit=3",
            "/api/dashboard/turnover?limit=3",
            "/api/stocks/list",
            "/api/data/trade-calendar/options",
            "/api/data/trade-calendar/status?exchange=cn",
            "/api/strategies/catalog",
            "/api/backtest/catalog",
            "/api/factors/catalog",
        ):
            r = client.get(path)
            out.append((path, r.status_code))
    return out


def _backtest_catalog_archive_kind_errors(data: object) -> str | None:
    """校验 GET /api/backtest/catalog：engine_version、条目字段、archive_kind、strategy_id 集合与 POST /run 一致。"""
    from src.backtest.runner import (
        ENGINE_VERSION,
        STRATEGY_ID_BUY_HOLD,
        STRATEGY_ID_LIMIT_UP_PULLBACK,
        STRATEGY_ID_LIMIT_UP_PULLBACK_SCAN,
        STRATEGY_ID_MA_CROSS,
        STRATEGY_ID_MA_CROSS_SCAN,
    )

    _expected_shape_paths: dict[str, tuple[str, list[str]]] = {
        STRATEGY_ID_MA_CROSS: ("result", ["/api/backtest/ma-cross"]),
        STRATEGY_ID_MA_CROSS_SCAN: ("scan_result", ["/api/backtest/ma-cross/scan"]),
        STRATEGY_ID_BUY_HOLD: ("result", ["/api/backtest/buy-hold"]),
        STRATEGY_ID_LIMIT_UP_PULLBACK: ("result", ["/api/backtest/limit-up-pullback"]),
        STRATEGY_ID_LIMIT_UP_PULLBACK_SCAN: ("scan_result", ["/api/backtest/limit-up-pullback/scan"]),
    }

    if not isinstance(data, dict):
        return "backtest catalog: 响应体不是 JSON 对象"
    ev = data.get("engine_version")
    if ev != ENGINE_VERSION:
        return (
            "backtest catalog: engine_version 与内核不一致 "
            f"expected={ENGINE_VERSION!r} got={ev!r}"
        )
    post_run_path = data.get("post_run_path")
    if post_run_path != "/api/backtest/run":
        return (
            "backtest catalog: post_run_path 应为 '/api/backtest/run' "
            f"got={post_run_path!r}"
        )
    doc_ref = data.get("doc_ref")
    if doc_ref != "docs/GENERIC_BACKTEST_DRAFT.md":
        return (
            "backtest catalog: doc_ref 应为 'docs/GENERIC_BACKTEST_DRAFT.md' "
            f"got={doc_ref!r}"
        )
    arp = data.get("async_run_query_param")
    if arp != "async":
        return (
            "backtest catalog: async_run_query_param 应为 'async' "
            f"got={arp!r}"
        )
    ajt = data.get("async_job_status_path_template")
    want_tmpl = "/api/backtest/jobs/{job_id}"
    if ajt != want_tmpl:
        return (
            f"backtest catalog: async_job_status_path_template 应为 {want_tmpl!r} "
            f"got={ajt!r}"
        )
    ajp = data.get("async_job_persistence")
    if ajp not in ("memory", "redis"):
        return (
            "backtest catalog: async_job_persistence 须为 memory 或 redis "
            f"got={ajp!r}"
        )
    from src.backtest.async_job_backend import QUEUE_KEY, catalog_async_job_persistence

    if ajp != catalog_async_job_persistence():
        return (
            "backtest catalog: async_job_persistence 与当前 API 推断不一致 "
            f"got={ajp!r} expected={catalog_async_job_persistence()!r}"
        )
    qk = data.get("async_job_queue_key")
    qd = data.get("async_job_queue_depth")
    if ajp == "memory":
        if qk is not None:
            return (
                "backtest catalog: async_job_queue_key 在 memory 时须为 null "
                f"got={qk!r}"
            )
        if qd is not None:
            return (
                "backtest catalog: async_job_queue_depth 在 memory 时须为 null "
                f"got={qd!r}"
            )
    else:
        if qk != QUEUE_KEY:
            return (
                "backtest catalog: async_job_queue_key 在 redis 时须为 "
                f"{QUEUE_KEY!r} got={qk!r}"
            )
        if type(qd) is not int or qd < 0:
            return (
                "backtest catalog: async_job_queue_depth 在 redis 时须为非负 int "
                f"got={qd!r}"
            )
    strategies = data.get("strategies")
    if not isinstance(strategies, list) or not strategies:
        return "backtest catalog: strategies 缺失或为空"
    seen_sid: set[str] = set()
    by_sid: dict[str, str] = {}
    for i, row in enumerate(strategies):
        if not isinstance(row, dict):
            return f"backtest catalog: strategies[{i}] 不是对象"
        for key in ("strategy_version", "title", "description", "response_shape"):
            if key not in row:
                return f"backtest catalog: strategies[{i}] 缺字段 {key!r}"
        title = row.get("title")
        if not isinstance(title, str) or not title.strip():
            return f"backtest catalog: strategies[{i}].title 须为非空字符串"
        desc = row.get("description")
        if not isinstance(desc, str) or not desc.strip():
            return f"backtest catalog: strategies[{i}].description 须为非空字符串"
        rs = row.get("response_shape")
        if rs not in ("result", "scan_result"):
            return (
                f"backtest catalog: strategies[{i}].response_shape 须为 result|scan_result，"
                f"实际 {rs!r}"
            )
        paths = row.get("get_equivalent_paths")
        if not isinstance(paths, list):
            return f"backtest catalog: strategies[{i}].get_equivalent_paths 非列表"
        for pi, p in enumerate(paths):
            if not isinstance(p, str) or not p.strip().startswith("/"):
                return (
                    f"backtest catalog: strategies[{i}].get_equivalent_paths[{pi}] "
                    f"须为以 / 开头的非空字符串，实际 {p!r}"
                )
        sid = row.get("strategy_id")
        ak = row.get("archive_kind")
        if not isinstance(sid, str) or not sid.strip():
            return f"backtest catalog: strategies[{i}] 缺有效 strategy_id"
        if not isinstance(ak, str) or not ak.strip():
            return f"backtest catalog: strategies[{i}] 缺有效 archive_kind"
        sid_norm = sid.strip()
        sv = row.get("strategy_version")
        if sv != "1":
            return (
                f"backtest catalog: strategies[{i}].strategy_version 应为 '1' "
                f"实际 {sv!r}"
            )
        exp = _expected_shape_paths.get(sid_norm)
        if exp is not None:
            want_shape, want_paths = exp
            if rs != want_shape:
                return (
                    f"backtest catalog: strategy_id={sid_norm!r} 的 response_shape 应为 "
                    f"{want_shape!r} 实际 {rs!r}"
                )
            if paths != want_paths:
                return (
                    f"backtest catalog: strategy_id={sid_norm!r} 的 get_equivalent_paths 应为 "
                    f"{want_paths!r} 实际 {paths!r}"
                )
        if sid_norm in seen_sid:
            return f"backtest catalog: 重复的 strategy_id={sid_norm!r}"
        seen_sid.add(sid_norm)
        by_sid[sid_norm] = ak.strip()
    if by_sid.get("ma_cross") != "ma_cross_single":
        return (
            "backtest catalog: ma_cross 的 archive_kind 应为 ma_cross_single，"
            f"实际 {by_sid.get('ma_cross')!r}"
        )
    if by_sid.get("ma_cross_scan") != "ma_cross_scan":
        return (
            "backtest catalog: ma_cross_scan 的 archive_kind 应为 ma_cross_scan，"
            f"实际 {by_sid.get('ma_cross_scan')!r}"
        )
    if by_sid.get("buy_hold") != "buy_hold_single":
        return (
            "backtest catalog: buy_hold 的 archive_kind 应为 buy_hold_single，"
            f"实际 {by_sid.get('buy_hold')!r}"
        )
    if by_sid.get("limit_up_pullback") != "limit_up_pullback_single":
        return (
            "backtest catalog: limit_up_pullback 的 archive_kind 应为 limit_up_pullback_single，"
            f"实际 {by_sid.get('limit_up_pullback')!r}"
        )
    if by_sid.get("limit_up_pullback_scan") != "limit_up_pullback_scan":
        return (
            "backtest catalog: limit_up_pullback_scan 的 archive_kind 应为 limit_up_pullback_scan，"
            f"实际 {by_sid.get('limit_up_pullback_scan')!r}"
        )
    expected_ids = frozenset({
        STRATEGY_ID_MA_CROSS,
        STRATEGY_ID_MA_CROSS_SCAN,
        STRATEGY_ID_BUY_HOLD,
        STRATEGY_ID_LIMIT_UP_PULLBACK,
        STRATEGY_ID_LIMIT_UP_PULLBACK_SCAN,
    })
    got_ids = frozenset(by_sid.keys())
    if got_ids != expected_ids:
        return (
            "backtest catalog: strategy_id 集合须与 POST /api/backtest/run 支持的一致 "
            f"expected={sorted(expected_ids)!r} got={sorted(got_ids)!r}"
        )
    return None


def _factors_catalog_shape_errors(data: object) -> str | None:
    """校验 GET /api/factors/catalog 体：ops 非空，条目含 id / window / column / series_keys。"""
    _factor_window_policies = frozenset(("required", "optional", "unused"))
    _factor_column_policies = frozenset(("ohlcv", "ignored"))
    if not isinstance(data, dict):
        return "factors catalog: 响应体不是 JSON 对象"
    ops = data.get("ops")
    if not isinstance(ops, list) or not ops:
        return "factors catalog: ops 缺失或为空"
    for i, row in enumerate(ops):
        if not isinstance(row, dict):
            return f"factors catalog: ops[{i}] 不是对象"
        for key in ("id", "window", "column", "series_keys"):
            if key not in row:
                return f"factors catalog: ops[{i}] 缺字段 {key!r}"
        wpol = row.get("window")
        if wpol not in _factor_window_policies:
            return (
                f"factors catalog: ops[{i}].window 须为 required|optional|unused，实际 {wpol!r}"
            )
        cpol = row.get("column")
        if cpol not in _factor_column_policies:
            return (
                f"factors catalog: ops[{i}].column 须为 ohlcv|ignored，实际 {cpol!r}"
            )
        sk = row.get("series_keys")
        if not isinstance(sk, list):
            return f"factors catalog: ops[{i}].series_keys 非列表"
        for ki, keyn in enumerate(sk):
            if not isinstance(keyn, str) or not keyn.strip():
                return (
                    f"factors catalog: ops[{i}].series_keys[{ki}] 须为非空字符串，实际 {keyn!r}"
                )
        oid = row.get("id")
        if not isinstance(oid, str) or not oid.strip():
            return f"factors catalog: ops[{i}].id 无效"
    return None


def _factors_catalog_top_level_errors(data: object) -> str | None:
    """``preview_path`` / ``doc_ref`` 须与 ``FactorCatalogResponse`` 默认值一致。"""
    if not isinstance(data, dict):
        return "factors catalog (顶层): 响应体不是 JSON 对象"
    pp = data.get("preview_path")
    if pp != "/api/factors/preview":
        return (
            "factors catalog: preview_path 应为 '/api/factors/preview' "
            f"got={pp!r}"
        )
    dr = data.get("doc_ref")
    if dr != "docs/FACTORS.md":
        return f"factors catalog: doc_ref 应为 'docs/FACTORS.md' got={dr!r}"
    return None


def _factors_catalog_op_ids_match_opname(data: object) -> str | None:
    """``ops[].id`` 须与 ``src.api.routers.factors.OpName`` 成员完全一致（无漏无多）。"""
    from typing import get_args

    from src.api.routers.factors import OpName

    if not isinstance(data, dict):
        return "factors catalog (OpName): 响应体不是 JSON 对象"
    ops = data.get("ops")
    if not isinstance(ops, list):
        return "factors catalog (OpName): ops 非列表"
    expected = frozenset(get_args(OpName))
    got: set[str] = set()
    for i, row in enumerate(ops):
        if not isinstance(row, dict):
            return f"factors catalog (OpName): ops[{i}] 不是对象"
        oid = row.get("id")
        if not isinstance(oid, str) or not oid.strip():
            return f"factors catalog (OpName): ops[{i}].id 无效"
        got.add(oid.strip())
    if got != expected:
        miss = sorted(expected - got)
        extra = sorted(got - expected)
        return (
            "factors catalog: op id 集合与 OpName 不一致 "
            f"missing={miss!r} extra={extra!r}"
        )
    return None


_ROW_KEYS = frozenset(
    ("code", "close", "volume", "amount", "turnover_rate", "pct_change", "ret_pct", "meta_bars")
)


def _factors_cross_section_body_errors(
    data: object,
    *,
    expect_as_of: str,
    expect_period: int,
    expect_max_codes: int,
) -> str | None:
    """校验 ``GET /api/factors/cross-section`` 200 JSON 与请求参数、行字段一致。"""
    if not isinstance(data, dict):
        return "factors cross-section: 响应体不是 JSON 对象"
    for k in ("as_of_trade_date", "period", "max_codes_requested", "row_count", "rows", "doc_ref"):
        if k not in data:
            return f"factors cross-section: 缺字段 {k!r}"
    if data.get("doc_ref") != "docs/FACTORS.md":
        return f"factors cross-section: doc_ref 应为 'docs/FACTORS.md' got={data.get('doc_ref')!r}"
    asof = data.get("as_of_trade_date")
    asof_s = asof if isinstance(asof, str) else (str(asof) if asof is not None else "")
    if asof_s != expect_as_of:
        return (
            "factors cross-section: as_of_trade_date 与请求不一致 "
            f"got={asof_s!r} expect={expect_as_of!r}"
        )
    if data.get("period") != expect_period:
        return f"factors cross-section: period 期望 {expect_period} 实际 {data.get('period')!r}"
    if data.get("max_codes_requested") != expect_max_codes:
        return (
            "factors cross-section: max_codes_requested 期望 "
            f"{expect_max_codes} 实际 {data.get('max_codes_requested')!r}"
        )
    rows = data.get("rows")
    if not isinstance(rows, list):
        return "factors cross-section: rows 非列表"
    rc = data.get("row_count")
    if not isinstance(rc, int) or rc < 0 or rc > expect_max_codes:
        return f"factors cross-section: row_count 异常 {rc!r}"
    if len(rows) != rc:
        return "factors cross-section: len(rows) 与 row_count 不一致"
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            return f"factors cross-section: rows[{i}] 非对象"
        if frozenset(row.keys()) != _ROW_KEYS:
            return (
                f"factors cross-section: rows[{i}] 键集合异常 "
                f"got={sorted(row.keys())!r}"
            )
        if not isinstance(row.get("code"), str) or not str(row.get("code")).strip():
            return f"factors cross-section: rows[{i}].code 无效"
        if not isinstance(row.get("meta_bars"), int) or row["meta_bars"] < 1:
            return f"factors cross-section: rows[{i}].meta_bars 须为正整数"
    return None


def _verify_factors_cross_section_smoke() -> tuple[str | None, bool]:
    """依赖 overview 首条指数 ``date``。返回 ``(错误信息, 是否跳过)``；成功为 ``(None, False)``。"""
    from fastapi.testclient import TestClient

    from src.api.main import app

    period = 20
    max_codes = 20

    with TestClient(app) as client:
        ro = client.get("/api/dashboard/overview")
        if ro.status_code != 200:
            return (
                f"/api/dashboard/overview -> HTTP {ro.status_code}（截面冒烟依赖 overview）",
                False,
            )
        ob = ro.json()
        indices = ob.get("indices") if isinstance(ob, dict) else None
        first = indices[0] if isinstance(indices, list) and indices else None
        d_raw = first.get("date") if isinstance(first, dict) else None
        if not isinstance(d_raw, str) or not d_raw.strip():
            return (None, True)
        as_of = d_raw.strip()
        r = client.get(
            "/api/factors/cross-section",
            params={"as_of_date": as_of, "period": period, "max_codes": max_codes},
        )
        if r.status_code == 503:
            return (
                "factors cross-section: HTTP 503（批量日 K 失败；需 MySQL 8+ / SQLite 3.25+ "
                "或脚本 --legacy-per-code-fetch）",
                False,
            )
        if r.status_code != 200:
            return (
                f"/api/factors/cross-section?as_of_date={as_of!r} -> HTTP {r.status_code}",
                False,
            )
        err = _factors_cross_section_body_errors(
            r.json(),
            expect_as_of=as_of,
            expect_period=period,
            expect_max_codes=max_codes,
        )
        if err:
            return (err, False)
    return (None, False)


def _strategies_catalog_shape_errors(sc_body: object) -> str | None:
    """校验 GET /api/strategies/catalog：strategies 非空，须含 ma_cross / ma_cross_scan；含 buy_hold 时校验其 Kinds。"""
    if not isinstance(sc_body, dict):
        return "strategies catalog: 响应体不是 JSON 对象"
    strategies = sc_body.get("strategies")
    if not isinstance(strategies, list) or len(strategies) < 1:
        return "strategies catalog: strategies 缺失或为空"
    ids: list[str] = []
    for i, st in enumerate(strategies):
        if not isinstance(st, dict):
            return f"strategies catalog: strategies[{i}] 不是对象"
        sid = st.get("id")
        if not isinstance(sid, str) or not sid.strip():
            return f"strategies catalog: strategies[{i}].id 无效"
        ids.append(sid.strip())
        title = st.get("title")
        if not isinstance(title, str) or not title.strip():
            return f"strategies catalog: strategies[{i}].title 须为非空字符串"
        desc = st.get("description")
        if not isinstance(desc, str) or not desc.strip():
            return f"strategies catalog: strategies[{i}].description 须为非空字符串"
        ver = st.get("strategy_contract_version")
        if ver != "1":
            return (
                f"strategies catalog: strategies[{i}].strategy_contract_version 应为 '1' "
                f"实际 {ver!r}"
            )
        br = st.get("backtest_run")
        if not isinstance(br, dict):
            return f"strategies catalog: strategies[{i}] 缺 backtest_run 对象"
        if not isinstance(br.get("archive_kind"), str) or not str(br.get("archive_kind")).strip():
            return f"strategies catalog: strategies[{i}].backtest_run.archive_kind 无效"
        if not isinstance(br.get("strategy_id"), str) or not str(br.get("strategy_id")).strip():
            return f"strategies catalog: strategies[{i}].backtest_run.strategy_id 无效"
        br_ver = br.get("strategy_version")
        if br_ver != "1":
            return (
                f"strategies catalog: strategies[{i}].backtest_run.strategy_version 应为 '1' "
                f"实际 {br_ver!r}"
            )
        entry_id = sid.strip()
        br_sid = str(br.get("strategy_id")).strip()
        if entry_id != br_sid:
            return (
                f"strategies catalog: strategies[{i}].id={entry_id!r} 与 "
                f"backtest_run.strategy_id={br_sid!r} 不一致"
            )
        sp = st.get("signal_params")
        if not isinstance(sp, dict):
            return f"strategies catalog: strategies[{i}].signal_params 非对象"
        bak = st.get("backtest_archive_kinds")
        if not isinstance(bak, list):
            return (
                f"strategies catalog: strategies[{i}].backtest_archive_kinds "
                "须为列表"
            )
        if entry_id == "ma_cross":
            if bak != ["ma_cross_single", "ma_cross_scan"]:
                return (
                    f"strategies catalog: ma_cross 的 backtest_archive_kinds 应为 "
                    f"['ma_cross_single', 'ma_cross_scan'] 实际 {bak!r}"
                )
        elif entry_id == "ma_cross_scan":
            if bak != ["ma_cross_scan"]:
                return (
                    "strategies catalog: ma_cross_scan 的 backtest_archive_kinds 应为 "
                    f"['ma_cross_scan'] 实际 {bak!r}"
                )
        elif entry_id == "buy_hold":
            if bak != ["buy_hold_single"]:
                return (
                    "strategies catalog: buy_hold 的 backtest_archive_kinds 应为 "
                    f"['buy_hold_single'] 实际 {bak!r}"
                )
        elif entry_id == "limit_up_pullback":
            if bak != ["limit_up_pullback_single"]:
                return (
                    "strategies catalog: limit_up_pullback 的 backtest_archive_kinds 应为 "
                    f"['limit_up_pullback_single'] 实际 {bak!r}"
                )
        elif entry_id == "limit_up_pullback_scan":
            if bak != ["limit_up_pullback_scan"]:
                return (
                    "strategies catalog: limit_up_pullback_scan 的 backtest_archive_kinds 应为 "
                    f"['limit_up_pullback_scan'] 实际 {bak!r}"
                )
        if not all(isinstance(x, str) for x in bak):
            return (
                f"strategies catalog: strategies[{i}].backtest_archive_kinds "
                "须为字符串列表"
            )
        ak_str = str(br.get("archive_kind")).strip()
        if ak_str not in bak:
            return (
                f"strategies catalog: strategies[{i}].backtest_run.archive_kind={ak_str!r} "
                f"不在 backtest_archive_kinds={bak!r} 中"
            )
        pschema = br.get("params_schema")
        if not isinstance(pschema, dict):
            return (
                f"strategies catalog: strategies[{i}].backtest_run.params_schema 非对象"
            )
    if "ma_cross" not in ids:
        return "strategies catalog: 缺少 id=ma_cross"
    if "ma_cross_scan" not in ids:
        return "strategies catalog: 缺少 id=ma_cross_scan"
    return None


def _strategy_catalog_vs_backtest_archive_errors(client: Any) -> str | None:
    """策略 catalog 的 backtest_run.archive_kind 须与 backtest engine catalog 逐条一致。"""
    r_sc = client.get("/api/strategies/catalog")
    if r_sc.status_code != 200:
        return f"/api/strategies/catalog -> HTTP {r_sc.status_code}"
    r_bc = client.get("/api/backtest/catalog")
    if r_bc.status_code != 200:
        return f"/api/backtest/catalog -> HTTP {r_bc.status_code}"
    sc_body = r_sc.json()
    shape_err = _strategies_catalog_shape_errors(sc_body)
    if shape_err:
        return shape_err
    bc_body = r_bc.json()
    e = _backtest_catalog_archive_kind_errors(bc_body)
    if e:
        return e
    by_engine: dict[str, str] = {
        str(s["strategy_id"]): str(s["archive_kind"])
        for s in bc_body["strategies"]
        if isinstance(s, dict) and "strategy_id" in s and "archive_kind" in s
    }
    strategies = sc_body["strategies"]
    strat_sids: set[str] = set()
    for j, st in enumerate(strategies):
        if not isinstance(st, dict):
            continue
        br = st.get("backtest_run")
        if not isinstance(br, dict):
            continue
        sid = br.get("strategy_id")
        ak = br.get("archive_kind")
        if isinstance(sid, str) and sid.strip():
            strat_sids.add(sid.strip())
        if not isinstance(sid, str) or sid not in by_engine:
            continue
        if not isinstance(ak, str):
            return f"strategies catalog: 条目 {j} backtest_run.archive_kind 非字符串"
        if ak != by_engine[sid]:
            return (
                f"archive_kind 不一致: strategy_id={sid!r} "
                f"strategies.catalog={ak!r} backtest.catalog={by_engine[sid]!r}"
            )
    eng_keys = frozenset(by_engine.keys())
    # 仅要求有 backtest_archive_kinds 的策略出现在 backtest catalog 中
    strat_sids_with_backtest = frozenset(
        sid for sid in strat_sids
        if any(
            (st.get("backtest_run") or {}).get("strategy_id") == sid
            and (st.get("backtest_archive_kinds") or [])
            for st in strategies
            if isinstance(st, dict)
        )
    )
    if strat_sids_with_backtest != eng_keys:
        return (
            "strategies catalog 与 backtest catalog 的 strategy_id 集合须完全一致 "
            f"engine={sorted(eng_keys)!r} strategies={sorted(strat_sids_with_backtest)!r}"
        )
    return None


def _verify_api_catalog_contracts() -> str | None:
    from fastapi.testclient import TestClient

    from src.api.main import app

    with TestClient(app) as client:
        err = _strategy_catalog_vs_backtest_archive_errors(client)
        if err:
            return err
        r_fc = client.get("/api/factors/catalog")
        if r_fc.status_code != 200:
            return f"/api/factors/catalog -> HTTP {r_fc.status_code}"
        fc_body = r_fc.json()
        err = _factors_catalog_top_level_errors(fc_body)
        if err:
            return err
        err = _factors_catalog_shape_errors(fc_body)
        if err:
            return err
        return _factors_catalog_op_ids_match_opname(fc_body)


def _verify_backtest_async_job_smoke() -> str | None:
    """不依赖库内 K 线：未知 job → GET/POST cancel 均 404；非法策略 + async → 400。"""
    from fastapi.testclient import TestClient

    from src.api.main import app

    fake_job = "ffffffffffffffffffffffffffffffff"
    with TestClient(app) as client:
        r404 = client.get(f"/api/backtest/jobs/{fake_job}")
        if r404.status_code != 404:
            return (
                f"GET /api/backtest/jobs/{{unknown}} 期望 404，"
                f"实际 HTTP {r404.status_code}"
            )
        r404c = client.post(f"/api/backtest/jobs/{fake_job}/cancel")
        if r404c.status_code != 404:
            return (
                f"POST /api/backtest/jobs/{{unknown}}/cancel 期望 404，"
                f"实际 HTTP {r404c.status_code}"
            )
        r400 = client.post(
            "/api/backtest/run?async=true",
            json={
                "strategy_id": "not_registered_verify_stack",
                "strategy_version": "1",
                "params": {"code": "sh.600000", "fast": 5, "slow": 20, "limit": 100},
            },
        )
        if r400.status_code != 400:
            return (
                "POST /api/backtest/run?async=true（非法 strategy_id）期望 400，"
                f"实际 HTTP {r400.status_code}"
            )
    return None


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="验证 .env 数据库/Redis 与核心 API 契约")
    p.add_argument(
        "--skip-db",
        action="store_true",
        help=(
            "跳过 stock_info/daily_kline/trade_calendar 行数统计；"
            "库表未齐（如缺 trade_calendar）时仍可继续 Redis、API 冒烟、catalog 与回测异步 job 检查"
        ),
    )
    return p.parse_args(argv)


def _run_stack_verify(args: argparse.Namespace) -> int:
    from src.common import get_settings

    s = get_settings()
    mode = (s.database.mode or "sqlite").strip().lower()
    print("=== 配置 ===")
    print(f"  DATABASE_MODE: {mode}")
    if mode == "sqlite":
        print(f"  SQLite 文件: {s.database.db_path}")
    elif mode == "mysql":
        print(
            f"  MySQL 目标: {s.database.user}@{s.database.host}:{s.database.port}/{s.database.name}"
        )
    else:
        print(f"\n[FAIL] 不支持的数据库模式: {mode!r}（仅支持 mysql / sqlite）")
        return 1
    print(f"  REDIS_ENABLED: {s.redis.enabled}")
    if s.redis.enabled:
        print(f"  Redis 目标: {s.redis.host}:{s.redis.port} db={s.redis.db}")

    label = "SQLite" if mode == "sqlite" else "MySQL"
    print(f"\n=== {label} ===")
    if args.skip_db:
        print("  [SKIP] 已跳过 DB 行数统计（--skip-db）")
    else:
        try:
            ns, nk, tc = asyncio.run(_db_table_counts())
            print(f"  stock_info 行数: {ns}")
            print(f"  daily_kline 行数: {nk}")
            print(
                f"  trade_calendar: 总行数 {tc.get('total_row_count', 0)} "
                f"（distinct exchange: {tc.get('distinct_exchange_count', 0)}）"
            )
            for row in tc.get("by_exchange") or []:
                print(f"    {row.get('exchange', '?')}: {row.get('row_count', 0)} 行")
            print(f"  [OK] 已连上 {label} 并完成计数")
        except Exception as e:
            print(f"  [FAIL] {e}")
            if not args.skip_db:
                print(
                    "  [HINT] 若仅需验证 Redis、API 冒烟、catalog 契约与回测异步 job，可重试："
                    "python scripts/verify_stack.py --skip-db"
                )
            return 1

    print("\n=== Redis ===")
    rp = _redis_probe()
    if not rp["enabled"]:
        print("  [SKIP] REDIS_ENABLED=false，名称缓存仅走 DB 批量查询")
    elif rp.get("ok"):
        print(f"  PING 成功；tb:stkname:* 键数量约: {rp.get('sample_keys', 0)}")
        print("  [OK] Redis 可用")
    else:
        print(f"  [FAIL] {rp.get('error', rp)}")
        return 1

    print("\n=== API 冒烟 (TestClient) ===")
    try:
        for path, code in _api_routes():
            tag = "OK" if code == 200 else "FAIL"
            print(f"  [{tag}] {path} -> {code}")
            if code != 200:
                return 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        return 1

    print("\n=== 契约: API catalog（archive_kind + 因子 ops）===")
    try:
        contract_err = _verify_api_catalog_contracts()
        if contract_err:
            print(f"  [FAIL] {contract_err}")
            return 1
        print(
            "  [OK] strategies catalog 形态；backtest/strategies archive_kind 对齐；"
            "factors catalog 顶层与 ops 形态及 OpName 对齐"
        )
    except Exception as e:
        print(f"  [FAIL] {e}")
        return 1

    print("\n=== 因子截面 cross-section（overview 填日）===")
    try:
        xs_err, xs_skip = _verify_factors_cross_section_smoke()
        if xs_err:
            print(f"  [FAIL] {xs_err}")
            return 1
        if xs_skip:
            print(
                "  [SKIP] factors cross-section: overview 无 indices[0].date，跳过截面冒烟"
            )
        else:
            print("  [OK] GET /api/factors/cross-section（period=20, max_codes=20）")
    except Exception as e:
        print(f"  [FAIL] {e}")
        return 1

    print("\n=== 回测异步 job 冒烟 (TestClient) ===")
    try:
        async_err = _verify_backtest_async_job_smoke()
        if async_err:
            print(f"  [FAIL] {async_err}")
            return 1
        print("  [OK] 未知 job_id -> GET 404 & POST cancel 404；非法 strategy + async -> 400")
    except Exception as e:
        print(f"  [FAIL] {e}")
        return 1

    print("\n=== 汇总 ===")
    if mode == "sqlite":
        print("  SQLite: 使用中（本地/CI 仓储与看板数据）")
    else:
        print("  MySQL: 使用中（仓储与看板数据）")
    if s.redis.enabled:
        print("  Redis: 已启用（股票名称缓存等依赖 app.state.redis）")
    else:
        print("  Redis: 未启用")
    return 0


def main(argv: list[str] | None = None) -> int:
    t0 = time.perf_counter()
    try:
        return _run_stack_verify(_parse_args(argv))
    finally:
        print(f"[timing] verify_stack {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
