"""XtquantBrokerAdapter 单元测试 — 使用 mock 模拟 xtquant SDK。"""

from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.broker.base import (
    BrokerOrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
)
from src.broker.factory import BrokerAdapterFactory
from src.broker.xtquant_adapter import (
    XtquantBrokerAdapter,
    _from_xt_code,
    _map_xt_order_status,
    _to_xt_code,
)


# ===========================================================================
# 代码转换测试
# ===========================================================================


def test_to_xt_code():
    assert _to_xt_code("sh.600000") == "600000.SH"
    assert _to_xt_code("sz.000001") == "000001.SZ"
    assert _to_xt_code("bj.430047") == "430047.BJ"
    assert _to_xt_code("  SH.600000  ") == "600000.SH"


def test_from_xt_code():
    assert _from_xt_code("600000.SH") == "sh.600000"
    assert _from_xt_code("000001.SZ") == "sz.000001"
    assert _from_xt_code("430047.BJ") == "bj.430047"


# ===========================================================================
# 订单状态映射测试
# ===========================================================================


def test_map_xt_order_status():
    assert _map_xt_order_status(48) == OrderStatus.PENDING      # 未报
    assert _map_xt_order_status(49) == OrderStatus.PENDING      # 待报
    assert _map_xt_order_status(50) == OrderStatus.SUBMITTED    # 已报
    assert _map_xt_order_status(55) == OrderStatus.PARTIAL_FILLED  # 部分成交
    assert _map_xt_order_status(56) == OrderStatus.FILLED       # 全部成交
    assert _map_xt_order_status(54) == OrderStatus.CANCELLED    # 已撤
    assert _map_xt_order_status(53) == OrderStatus.CANCELLED    # 部撤
    assert _map_xt_order_status(52) == OrderStatus.REJECTED     # 已失败
    # 未知状态默认 PENDING
    assert _map_xt_order_status(999) == OrderStatus.PENDING


# ===========================================================================
# BrokerAdapterFactory 测试
# ===========================================================================


def test_factory_create_paper(empty_sqlite_db):
    adapter = BrokerAdapterFactory.create(
        "paper",
        session=MagicMock(),
        user_id=1,
        account_label="default",
    )
    assert adapter.name == "paper"


def test_factory_create_xtquant():
    adapter = BrokerAdapterFactory.create(
        "xtquant",
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )
    assert adapter.name == "xtquant"
    assert isinstance(adapter, XtquantBrokerAdapter)


def test_factory_create_unknown():
    with pytest.raises(ValueError, match="未知的 broker adapter"):
        BrokerAdapterFactory.create("unknown")


def test_factory_available_types():
    types = BrokerAdapterFactory.available_types()
    assert "paper" in types


# ===========================================================================
# XtquantBrokerAdapter 初始化测试
# ===========================================================================


def test_init_valid():
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )
    assert adapter._account_id == "12345678"
    assert adapter._qmt_path == r"C:\\QMT\\userdata_mini"
    assert adapter._session_id == 123456
    assert not adapter._connected


def test_init_empty_account_id():
    with pytest.raises(ValueError, match="account_id 不能为空"):
        XtquantBrokerAdapter(account_id="", qmt_path="C:\\QMT")


def test_init_empty_qmt_path():
    with pytest.raises(ValueError, match="qmt_path 不能为空"):
        XtquantBrokerAdapter(account_id="123", qmt_path="")


# ===========================================================================
# XtquantBrokerAdapter 连接测试
# ===========================================================================


@pytest.fixture
def mock_xtquant_modules():
    """Mock xtquant 全部模块。"""
    mock_xtconstant = MagicMock()
    mock_xtconstant.STOCK_BUY = 23
    mock_xtconstant.STOCK_SELL = 24
    mock_xtconstant.LATEST_PRICE = 5
    mock_xtconstant.FIX_PRICE = 11

    mock_trader_class = MagicMock()
    mock_account_class = MagicMock()

    modules = {
        "xtquant": MagicMock(),
        "xtquant.xtconstant": mock_xtconstant,
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_trader_class),
        "xtquant.xttype": MagicMock(StockAccount=mock_account_class),
    }

    with patch.dict(sys.modules, modules):
        yield {
            "xtconstant": mock_xtconstant,
            "trader_class": mock_trader_class,
            "account_class": mock_account_class,
        }


@pytest.fixture
def adapter(mock_xtquant_modules):
    """创建已连接的 adapter（mock 连接）。"""
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    # 重新导入并连接
    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        import asyncio
        asyncio.run(adapter.connect())

    return adapter


@pytest.mark.asyncio
async def test_connect_success(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()

    assert adapter._connected
    mock_trader.start.assert_called_once()
    mock_trader.connect.assert_called_once()


@pytest.mark.asyncio
async def test_connect_failure(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = -1  # 连接失败
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        with pytest.raises(ConnectionError, match="xtquant 连接失败"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_disconnect(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()
        await adapter.disconnect()

    assert not adapter._connected
    mock_trader.stop.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_connected_not_connected():
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )
    with pytest.raises(RuntimeError, match="未连接"):
        adapter._ensure_connected()


# ===========================================================================
# 下单测试
# ===========================================================================


@pytest.mark.asyncio
async def test_place_order_success(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_trader.order_stock.return_value = 12345
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xtconstant": mock_xtquant_modules["xtconstant"],
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()

        req = BrokerOrderRequest(
            code="sh.600000",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        resp = await adapter.place_order(req)

    assert resp.order_id == "12345"
    assert resp.status == OrderStatus.SUBMITTED
    assert resp.code == "sh.600000"
    assert resp.side == OrderSide.BUY


@pytest.mark.asyncio
async def test_place_order_rejected(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_trader.order_stock.return_value = -1  # 拒单
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xtconstant": mock_xtquant_modules["xtconstant"],
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()

        req = BrokerOrderRequest(
            code="sh.600000",
            side=OrderSide.SELL,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=10.5,
        )
        resp = await adapter.place_order(req)

    assert resp.status == OrderStatus.REJECTED
    assert "拒单" in resp.rejected_reason


@pytest.mark.asyncio
async def test_place_order_limit(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_trader.order_stock.return_value = 99999
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xtconstant": mock_xtquant_modules["xtconstant"],
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()

        req = BrokerOrderRequest(
            code="sz.000001",
            side=OrderSide.BUY,
            quantity=200,
            order_type=OrderType.LIMIT,
            limit_price=15.88,
        )
        resp = await adapter.place_order(req)

    assert resp.order_id == "99999"
    assert resp.status == OrderStatus.SUBMITTED
    assert resp.limit_price == 15.88


# ===========================================================================
# 撤单测试
# ===========================================================================


@pytest.mark.asyncio
async def test_cancel_order_success(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_trader.cancel_order_stock.return_value = 0
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()
        resp = await adapter.cancel_order("12345")

    assert resp.status == OrderStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_order_already_filled(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_trader.cancel_order_stock.return_value = -1  # 已成交
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()
        resp = await adapter.cancel_order("12345")

    assert resp.status == OrderStatus.REJECTED
    assert "已成交" in resp.rejected_reason


# ===========================================================================
# 查询订单测试
# ===========================================================================


@pytest.mark.asyncio
async def test_get_order_found(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_order = SimpleNamespace(
        stock_code="600000.SH",
        order_type=23,
        order_status=56,
        order_volume=100,
        traded_volume=100,
        traded_price=10.5,
        price=10.5,
        order_id=12345,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_trader.query_stock_order.return_value = mock_order
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()
        resp = await adapter.get_order("12345")

    assert resp is not None
    assert resp.order_id == "12345"
    assert resp.code == "sh.600000"
    assert resp.status == OrderStatus.FILLED
    assert resp.filled_quantity == 100


@pytest.mark.asyncio
async def test_get_order_not_found(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_trader.query_stock_order.return_value = None
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()
        resp = await adapter.get_order("99999")

    assert resp is None


# ===========================================================================
# 查询持仓测试
# ===========================================================================


@pytest.mark.asyncio
async def test_get_positions(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_pos1 = SimpleNamespace(
        stock_code="600000.SH",
        volume=1000,
        can_use_volume=800,
        open_price=10.0,
        market_value=10500.0,
    )
    mock_pos2 = SimpleNamespace(
        stock_code="000001.SZ",
        volume=500,
        can_use_volume=500,
        open_price=15.0,
        market_value=7800.0,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_trader.query_stock_positions.return_value = [mock_pos1, mock_pos2]
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()
        positions = await adapter.get_positions()

    assert len(positions) == 2
    assert positions[0].code == "sh.600000"
    assert positions[0].quantity == 1000
    assert positions[0].available_quantity == 800  # T+1
    assert positions[0].avg_cost == 10.0
    assert positions[1].code == "sz.000001"


@pytest.mark.asyncio
async def test_get_positions_empty(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_trader.query_stock_positions.return_value = []
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()
        positions = await adapter.get_positions()

    assert positions == []


# ===========================================================================
# 查询资金测试
# ===========================================================================


@pytest.mark.asyncio
async def test_get_balance(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_asset = SimpleNamespace(
        cash=500000.0,
        frozen_cash=10000.0,
        market_value=450000.0,
        total_asset=960000.0,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_trader.query_stock_asset.return_value = mock_asset
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()
        balance = await adapter.get_balance()

    assert balance.cash == 500000.0
    assert balance.available_cash == 490000.0  # cash - frozen
    assert balance.frozen_cash == 10000.0
    assert balance.market_value == 450000.0
    assert balance.total_equity == 960000.0


# ===========================================================================
# 查询成交测试
# ===========================================================================


@pytest.mark.asyncio
async def test_get_trades(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_trade = SimpleNamespace(
        stock_code="600000.SH",
        order_type=23,
        traded_volume=100,
        traded_price=10.5,
        traded_amount=1050.0,
        traded_id="T001",
        order_id=12345,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_trader.query_stock_trades.return_value = [mock_trade]
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()
        trades = await adapter.get_trades()

    assert len(trades) == 1
    assert trades[0].trade_id == "T001"
    assert trades[0].code == "sh.600000"
    assert trades[0].side == OrderSide.BUY
    assert trades[0].quantity == 100
    assert trades[0].price == 10.5
    assert trades[0].amount == 1050.0


# ===========================================================================
# 健康检查测试
# ===========================================================================


@pytest.mark.asyncio
async def test_health_check_connected(mock_xtquant_modules):
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )

    mock_asset = SimpleNamespace(
        cash=100000.0,
        frozen_cash=0.0,
        market_value=50000.0,
        total_asset=150000.0,
    )

    mock_trader = MagicMock()
    mock_trader.connect.return_value = 0
    mock_trader.subscribe.return_value = 0
    mock_trader.query_stock_asset.return_value = mock_asset
    mock_xtquant_modules["trader_class"].return_value = mock_trader

    with patch.dict(sys.modules, {
        "xtquant": MagicMock(),
        "xtquant.xttrader": MagicMock(XtQuantTrader=mock_xtquant_modules["trader_class"]),
        "xtquant.xttype": MagicMock(StockAccount=mock_xtquant_modules["account_class"]),
    }):
        await adapter.connect()
        health = await adapter.health_check()

    assert health["adapter"] == "xtquant"
    assert health["status"] == "ok"
    assert health["account_id"] == "12345678"
    assert health["balance"]["cash"] == 100000.0


@pytest.mark.asyncio
async def test_health_check_disconnected():
    adapter = XtquantBrokerAdapter(
        account_id="12345678",
        qmt_path=r"C:\\QMT\\userdata_mini",
        session_id=123456,
    )
    health = await adapter.health_check()

    assert health["adapter"] == "xtquant"
    assert health["status"] == "disconnected"
    assert "balance" not in health
