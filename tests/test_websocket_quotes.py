"""WebSocket 实时行情测试。"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket

from src.market_data.manager import MarketDataManager
from src.market_data.sina_source import SinaMarketDataSource, _parse_sina_js, _to_sina_code, _from_sina_code


# ===========================================================================
# 新浪代码转换测试
# ===========================================================================

def test_to_sina_code():
    assert _to_sina_code("sh.600000") == "sh600000"
    assert _to_sina_code("sz.000001") == "sz000001"
    assert _to_sina_code("bj.430047") == "bj430047"


def test_from_sina_code():
    assert _from_sina_code("sh600000") == "sh.600000"
    assert _from_sina_code("sz000001") == "sz.000001"
    assert _from_sina_code("bj430047") == "bj.430047"


# ===========================================================================
# 新浪 JS 解析测试
# ===========================================================================

def test_parse_sina_js_stock():
    js_text = 'var hq_str_sh600000="浦发银行,10.50,10.60,10.55,10.65,10.45,10.54,10.55,1234567,13050000.00,100,10.54,200,10.53,300,10.52,400,10.51,500,10.50,50,10.56,60,10.57,70,10.58,80,10.59,90,10.60,2024-01-15,14:30:00"'
    quotes = _parse_sina_js(js_text)
    assert len(quotes) == 1
    q = quotes[0]
    assert q.code == "sh.600000"
    assert q.name == "浦发银行"
    assert q.price == 10.55
    assert q.open == 10.50
    assert q.close == 10.60
    assert q.high == 10.65
    assert q.low == 10.45
    assert q.volume == 1234567
    assert q.bid1_price == 10.54
    assert q.ask1_price == 10.56


def test_parse_sina_js_empty():
    quotes = _parse_sina_js("")
    assert quotes == []


def test_parse_sina_js_multiple():
    js_text = (
        'var hq_str_sh600000="浦发银行,10.50,10.60,10.55,10.65,10.45,10.54,10.55,100,1000.00,10,10.54,20,10.53,30,10.52,40,10.51,50,10.50,5,10.56,6,10.57,7,10.58,8,10.59,9,10.60,2024-01-15,14:30:00";'
        'var hq_str_sz000001="平安银行,15.00,15.10,15.05,15.15,14.95,15.04,15.05,200,2000.00,20,15.04,30,15.03,40,15.02,50,15.01,60,15.00,6,15.06,7,15.07,8,15.08,9,15.09,10,15.10,2024-01-15,14:30:00"'
    )
    quotes = _parse_sina_js(js_text)
    assert len(quotes) == 2
    assert quotes[0].code == "sh.600000"
    assert quotes[1].code == "sz.000001"


# ===========================================================================
# SinaMarketDataSource 测试
# ===========================================================================

@pytest.mark.asyncio
async def test_sina_source_connect_disconnect():
    source = SinaMarketDataSource()
    await source.connect()
    assert source._client is not None
    health = await source.health_check()
    assert health["source"] == "sina"
    assert health["status"] == "ok"
    await source.disconnect()


@pytest.mark.asyncio
async def test_sina_source_subscribe_unsubscribe():
    source = SinaMarketDataSource()
    assert await source.subscribe("sh.600000")
    assert "sh.600000" in source._subscribed
    assert await source.unsubscribe("sh.600000")
    assert "sh.600000" not in source._subscribed


# ===========================================================================
# MarketDataManager 测试
# ===========================================================================

@pytest.mark.asyncio
async def test_manager_lifecycle():
    mgr = MarketDataManager()
    assert not mgr._running
    await mgr.start()
    assert mgr._running
    health = await mgr.health_check()
    assert health["running"] is True
    await mgr.stop()
    assert not mgr._running


@pytest.mark.asyncio
async def test_manager_subscribe_unsubscribe():
    mgr = MarketDataManager()
    await mgr.start()

    mock_ws = MagicMock()
    mock_ws.send_json = AsyncMock()

    await mgr.subscribe("sh.600000", mock_ws)
    assert "sh.600000" in mgr.subscribed_codes()

    await mgr.unsubscribe("sh.600000", mock_ws)
    assert "sh.600000" not in mgr.subscribed_codes()

    await mgr.stop()


@pytest.mark.asyncio
async def test_manager_unsubscribe_all():
    mgr = MarketDataManager()
    await mgr.start()

    mock_ws = MagicMock()
    mock_ws.send_json = AsyncMock()

    await mgr.subscribe("sh.600000", mock_ws)
    await mgr.subscribe("sz.000001", mock_ws)
    assert len(mgr.subscribed_codes(mock_ws)) == 2

    await mgr.unsubscribe_all(mock_ws)
    assert len(mgr.subscribed_codes(mock_ws)) == 0

    await mgr.stop()


@pytest.mark.asyncio
async def test_manager_quote_changed():
    from src.market_data.base import MarketQuote

    old = MarketQuote(code="sh.600000", price=10.0, volume=100)
    new_same = MarketQuote(code="sh.600000", price=10.0, volume=100)
    new_diff = MarketQuote(code="sh.600000", price=10.5, volume=100)

    assert not MarketDataManager._quote_changed(old, new_same)
    assert MarketDataManager._quote_changed(old, new_diff)
    assert MarketDataManager._quote_changed(None, new_diff)


@pytest.mark.asyncio
async def test_manager_broadcast():
    mgr = MarketDataManager()
    await mgr.start()

    mock_ws1 = MagicMock()
    mock_ws1.send_json = AsyncMock()
    mock_ws2 = MagicMock()
    mock_ws2.send_json = AsyncMock()

    await mgr.subscribe("sh.600000", mock_ws1)
    await mgr.subscribe("sh.600000", mock_ws2)

    from src.market_data.base import MarketQuote
    quote = MarketQuote(
        code="sh.600000",
        name="浦发银行",
        price=10.55,
        open=10.50,
        high=10.60,
        low=10.45,
        pre_close=10.50,
        change=0.05,
        change_pct=0.48,
        volume=1000,
        amount=10000.0,
        bid1=10.54,
        ask1=10.56,
        bid1_vol=100,
        ask1_vol=50,
        source="sina",
    )

    await mgr._broadcast("sh.600000", quote)

    # 等待异步发送完成
    await asyncio.sleep(0.1)

    assert mock_ws1.send_json.called
    assert mock_ws2.send_json.called

    await mgr.stop()
