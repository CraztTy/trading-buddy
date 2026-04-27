"""新浪财经实时行情数据源 — HTTP 轮询，免费、稳定、无需认证。

接口: https://hq.sinajs.cn/list=sh600000,sz000001
返回: JS 变量赋值格式，解析为 RealtimeQuote

特点:
- 无需 API Key
- 支持批量查询（最多约 300 只）
- 延迟约 3-5 秒（非 tick 级，但比 baostock 实时性好）
- A 股、B 股、指数均支持
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from src.common import get_logger
from src.data.models import RealtimeQuote
from src.market_data.base import BaseMarketDataSource, MarketQuote

logger = get_logger("sina_source")

# 新浪行情 API 基址
_SINA_HQ_URL = "https://hq.sinajs.cn/list={codes}"

# 单次请求最多股票数（避免 URL 过长）
_MAX_CODES_PER_REQ = 200

# 请求间隔（秒），避免过于频繁
_REQUEST_INTERVAL = 1.0


def _to_sina_code(code: str) -> str:
    """内部格式 → 新浪格式。"""
    c = code.strip().lower()
    if c.startswith("sh."):
        return c.replace("sh.", "sh")
    if c.startswith("sz."):
        return c.replace("sz.", "sz")
    if c.startswith("bj."):
        return c.replace("bj.", "bj")
    return c


def _from_sina_code(sina_code: str) -> str:
    """新浪格式 → 内部格式。"""
    sc = sina_code.strip().lower()
    if sc.startswith("sh"):
        return f"sh.{sc[2:]}"
    if sc.startswith("sz"):
        return f"sz.{sc[2:]}"
    if sc.startswith("bj"):
        return f"bj.{sc[2:]}"
    return sc


def _parse_sina_js(js_text: str) -> list[RealtimeQuote]:
    """解析新浪返回的 JS 变量格式。

    格式示例:
        var hq_str_sh600000="浦发银行,10.50,10.60,10.55,10.65,10.45,...

    字段顺序:
        0=name, 1=open, 2=pre_close, 3=price, 4=high, 5=low,
        6=bid1, 7=ask1, 8=volume, 9=amount,
        10=bid1_vol, 11=bid1_price, 12=bid2_vol, 13=bid2_price, ... (买1-买5)
        20=ask1_vol, 21=ask1_price, 22=ask2_vol, ... (卖1-卖5)
        30=date, 31=time
    """
    quotes: list[RealtimeQuote] = []

    for line in js_text.split(";"):
        line = line.strip()
        if not line.startswith("var hq_str_"):
            continue

        # 提取变量名和数据
        try:
            var_part, data_part = line.split('="', 1)
            sina_code = var_part.replace("var hq_str_", "").strip()
            raw = data_part.rstrip('"').strip()

            if not raw or raw == "":
                # 停牌或无效代码
                continue

            parts = raw.split(",")
            if len(parts) < 32:
                logger.warning("sina quote parse: insufficient fields for %s", sina_code)
                continue

            # 指数字段数不同（无买卖盘）
            is_index = sina_code.startswith("sh0") or sina_code.startswith("sz3") or sina_code.startswith("sh9")

            name = parts[0]
            open_price = float(parts[1]) if parts[1] else 0.0
            pre_close = float(parts[2]) if parts[2] else 0.0
            price = float(parts[3]) if parts[3] else 0.0
            high = float(parts[4]) if parts[4] else 0.0
            low = float(parts[5]) if parts[5] else 0.0

            # 买卖盘（股票）
            if not is_index and len(parts) >= 32:
                bid1_price = float(parts[11]) if parts[11] else 0.0
                bid1_vol = int(float(parts[10])) if parts[10] else 0
                ask1_price = float(parts[21]) if parts[21] else 0.0
                ask1_vol = int(float(parts[20])) if parts[20] else 0
                volume = int(float(parts[8])) if parts[8] else 0
                amount = float(parts[9]) if parts[9] else 0.0
            else:
                # 指数
                bid1_price = price
                bid1_vol = 0
                ask1_price = price
                ask1_vol = 0
                volume = int(float(parts[8])) if len(parts) > 8 and parts[8] else 0
                amount = float(parts[9]) if len(parts) > 9 and parts[9] else 0.0

            change = round(price - pre_close, 2) if pre_close > 0 else 0.0
            pct_change = round(change / pre_close * 100, 2) if pre_close > 0 else 0.0

            # 时间解析
            time_str = f"{parts[30]} {parts[31]}" if len(parts) > 31 else ""
            try:
                update_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                update_time = datetime.now()

            quote = RealtimeQuote(
                code=_from_sina_code(sina_code),
                name=name,
                open=open_price,
                close=pre_close,
                price=price,
                high=high,
                low=low,
                volume=volume,
                amount=amount,
                bid1_price=bid1_price,
                bid1_volume=bid1_vol,
                ask1_price=ask1_price,
                ask1_volume=ask1_vol,
                update_time=update_time,
            )
            quote.change = change
            quote.pct_change = pct_change

            quotes.append(quote)

        except (ValueError, IndexError) as e:
            logger.warning("sina parse error: %s", e)
            continue

    return quotes


class SinaMarketDataSource(BaseMarketDataSource):
    """新浪财经实时行情数据源。"""

    name = "sina"
    supports_websocket = False
    supports_snapshot = True
    max_subscriptions = 300

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._subscribed: set[str] = set()

    async def connect(self) -> None:
        """创建 HTTP 客户端。"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                headers={
                    "Referer": "https://finance.sina.com.cn",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0",
                },
            )
        logger.info("sina source connected")

    async def disconnect(self) -> None:
        """关闭 HTTP 客户端。"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        logger.info("sina source disconnected")

    async def subscribe(self, code: str) -> bool:
        """订阅标的（仅记录，不建立实际连接）。"""
        self._subscribed.add(code.strip().lower())
        return True

    async def unsubscribe(self, code: str) -> bool:
        """取消订阅。"""
        self._subscribed.discard(code.strip().lower())
        return True

    async def get_snapshot(self, code: str) -> MarketQuote | None:
        """获取单标的一次性快照。"""
        quotes = await self.get_snapshots([code])
        return quotes.get(code)

    async def get_snapshots(self, codes: list[str]) -> dict[str, MarketQuote]:
        """批量获取行情快照。"""
        if not self._client or self._client.is_closed:
            await self.connect()

        quotes: dict[str, MarketQuote] = {}

        # 分批请求
        for i in range(0, len(codes), _MAX_CODES_PER_REQ):
            batch = codes[i : i + _MAX_CODES_PER_REQ]
            sina_codes = [_to_sina_code(c) for c in batch]
            url = _SINA_HQ_URL.format(codes=",".join(sina_codes))

            try:
                resp = await self._client.get(url)
                resp.raise_for_status()
                # 新浪返回 GBK 编码
                text = resp.content.decode("gbk", errors="replace")
                realtime_quotes = _parse_sina_js(text)

                for q in realtime_quotes:
                    quotes[q.code] = MarketQuote(
                        code=q.code,
                        name=q.name,
                        price=q.price,
                        open=q.open,
                        high=q.high,
                        low=q.low,
                        pre_close=q.close,
                        change=q.change or 0.0,
                        change_pct=q.pct_change or 0.0,
                        volume=q.volume,
                        amount=q.amount,
                        bid1=q.bid1_price,
                        ask1=q.ask1_price,
                        bid1_vol=q.bid1_volume,
                        ask1_vol=q.ask1_volume,
                        timestamp=q.update_time,
                        source="sina",
                    )

                if i + _MAX_CODES_PER_REQ < len(codes):
                    await asyncio.sleep(_REQUEST_INTERVAL)

            except httpx.HTTPError as e:
                logger.warning("sina request error: %s", e)
                continue

        return quotes

    async def health_check(self) -> dict:
        """健康检查。"""
        healthy = self._client is not None and not self._client.is_closed
        return {
            "source": self.name,
            "status": "ok" if healthy else "disconnected",
            "subscribed": len(self._subscribed),
        }
