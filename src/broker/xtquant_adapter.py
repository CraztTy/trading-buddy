"""迅投 QMT (xtquant) 实盘 Broker Adapter。

依赖:
    pip install xtquant          # 或从 QMT 安装目录复制
    # QMT/miniQMT 客户端须已安装并运行（Windows）

环境变量（示例 .env）:
    XTQUANT_QMT_PATH=C:\\国金QMT交易端\\userdata_mini
    XTQUANT_ACCOUNT_ID=12345678
    XTQUANT_SESSION_ID=123456

使用流程:
    1. 确保 QMT/miniQMT 客户端已启动并登录
    2. 创建 adapter: XtquantBrokerAdapter(account_id, qmt_path, session_id)
    3. await adapter.connect()
    4. await adapter.place_order(...)
    5. await adapter.disconnect()

注意:
    - xtquant API 是同步的，所有调用都通过 asyncio.to_thread() 包装
    - 本实现采用"下单后返回 SUBMITTED，通过 get_order 轮询查状态"的 MVP 策略
    - 代码格式转换：内部统一用 "sh.600000"，与 xtquant 交互时转 "600000.SH"
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any

from src.broker.base import (
    BaseBrokerAdapter,
    BrokerBalance,
    BrokerOrderRequest,
    BrokerOrderResponse,
    BrokerPosition,
    BrokerTrade,
    OrderSide,
    OrderStatus,
    OrderType,
)
from src.common import get_logger

logger = get_logger("xtquant_adapter")

# ---------------------------------------------------------------------------
# 代码格式转换
# ---------------------------------------------------------------------------


def _to_xt_code(code: str) -> str:
    """内部格式 → xtquant 格式。

    sh.600000 → 600000.SH
    sz.000001 → 000001.SZ
    """
    c = code.strip().lower()
    parts = c.split(".")
    if len(parts) == 2:
        return f"{parts[1]}.{parts[0].upper()}"
    return c


def _from_xt_code(xt_code: str) -> str:
    """xtquant 格式 → 内部格式。

    600000.SH → sh.600000
    """
    parts = xt_code.split(".")
    if len(parts) == 2:
        return f"{parts[1].lower()}.{parts[0]}"
    return xt_code


# ---------------------------------------------------------------------------
# 订单状态映射
# ---------------------------------------------------------------------------

# xtquant 订单状态码 → OrderStatus
# 参考: http://dict.thinktrader.net/nativeApi/xttrader.html
_XT_ORDER_STATUS_MAP: dict[int, OrderStatus] = {
    48: OrderStatus.PENDING,        # 未报
    49: OrderStatus.PENDING,        # 待报
    50: OrderStatus.SUBMITTED,      # 已报
    51: OrderStatus.FILLED,         # 已成交（旧）
    52: OrderStatus.REJECTED,       # 已失败
    53: OrderStatus.CANCELLED,      # 部撤
    54: OrderStatus.CANCELLED,      # 已撤
    55: OrderStatus.PARTIAL_FILLED, # 部分成交
    56: OrderStatus.FILLED,         # 全部成交
}


def _map_xt_order_status(xt_status: int) -> OrderStatus:
    """将 xtquant 订单状态码映射为统一 OrderStatus。"""
    return _XT_ORDER_STATUS_MAP.get(xt_status, OrderStatus.PENDING)


# ---------------------------------------------------------------------------
# XtquantBrokerAdapter
# ---------------------------------------------------------------------------


class XtquantBrokerAdapter(BaseBrokerAdapter):
    """迅投 QMT 实盘适配器。"""

    name = "xtquant"
    supports_market_order = True
    supports_limit_order = True
    supports_stop_order = False
    supports_cancel = True
    t_plus_n = 1

    def __init__(
        self,
        account_id: str,
        qmt_path: str,
        session_id: int = 123456,
    ):
        """
        Args:
            account_id: QMT 资金账号，如 "12345678"
            qmt_path: miniQMT userdata 路径，如 r"C:\\国金QMT交易端\\userdata_mini"
            session_id: 会话 ID，须唯一（每个策略实例不同）
        """
        if not account_id or not str(account_id).strip():
            raise ValueError("xtquant account_id 不能为空")
        if not qmt_path or not str(qmt_path).strip():
            raise ValueError("xtquant qmt_path 不能为空")

        self._account_id = str(account_id).strip()
        self._qmt_path = str(qmt_path).strip()
        self._session_id = int(session_id)

        self._trader: Any | None = None
        self._account: Any | None = None
        self._connected: bool = False

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """连接 QMT 客户端并订阅账号。"""
        try:
            from xtquant.xttrader import XtQuantTrader
            from xtquant.xttype import StockAccount
        except ImportError as e:
            raise ImportError(
                "xtquant 未安装。请执行: pip install xtquant "
                "或从 QMT 安装目录复制 xtquant 包到当前 Python 环境。"
            ) from e

        logger.info(
            "xtquant connecting: path=%s session_id=%s account=%s",
            self._qmt_path,
            self._session_id,
            self._account_id,
        )

        self._trader = XtQuantTrader(self._qmt_path, self._session_id)
        self._trader.start()

        connect_result = await asyncio.to_thread(self._trader.connect)
        if connect_result != 0:
            raise ConnectionError(
                f"xtquant 连接失败，返回码: {connect_result}。"
                f"请确认 QMT/miniQMT 客户端已启动并登录。"
            )

        self._account = StockAccount(self._account_id)
        sub_result = await asyncio.to_thread(self._trader.subscribe, self._account)
        if sub_result != 0:
            raise ConnectionError(
                f"xtquant 订阅账号失败，返回码: {sub_result}。"
                f"请确认账号 {self._account_id} 正确且已登录。"
            )

        self._connected = True
        logger.info("xtquant connected and subscribed: account=%s", self._account_id)

    async def disconnect(self) -> None:
        """断开 QMT 连接。"""
        if self._trader is not None:
            try:
                await asyncio.to_thread(self._trader.stop)
                logger.info("xtquant disconnected")
            except Exception as e:
                logger.warning("xtquant disconnect error: %s", e)
        self._connected = False
        self._trader = None
        self._account = None

    def _ensure_connected(self) -> None:
        """检查是否已连接，未连接时抛出 RuntimeError。"""
        if not self._connected or self._trader is None or self._account is None:
            raise RuntimeError("xtquant 未连接，请先调用 connect()")

    # ------------------------------------------------------------------
    # 下单
    # ------------------------------------------------------------------

    async def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResponse:
        """提交订单，返回 SUBMITTED 状态。

        xtquant 的 order_stock 是同步阻塞调用，立即返回 order_id（>0）或 -1（失败）。
        实际成交状态需要通过 get_order 轮询查询。
        """
        self._ensure_connected()

        try:
            from xtquant import xtconstant
        except ImportError as e:
            raise ImportError("xtquant 未安装") from e

        xt_code = _to_xt_code(request.code)

        # side 映射
        if request.side == OrderSide.BUY:
            xt_order_type = xtconstant.STOCK_BUY
        else:
            xt_order_type = xtconstant.STOCK_SELL

        # order_type 映射
        if request.order_type == OrderType.MARKET:
            xt_price_type = xtconstant.LATEST_PRICE
            xt_price = 0.0
        elif request.order_type == OrderType.LIMIT:
            xt_price_type = xtconstant.FIX_PRICE
            xt_price = request.limit_price or 0.0
        else:
            return BrokerOrderResponse(
                order_id="",
                code=request.code,
                side=request.side,
                quantity=request.quantity,
                status=OrderStatus.REJECTED,
                rejected_reason=f"xtquant 不支持订单类型: {request.order_type.value}",
                created_at=datetime.now(),
            )

        # 调用 xtquant 下单（同步 → 异步包装）
        try:
            order_id = await asyncio.to_thread(
                self._trader.order_stock,
                account=self._account,
                stock_code=xt_code,
                order_type=xt_order_type,
                order_volume=request.quantity,
                price_type=xt_price_type,
                price=xt_price,
                strategy_name=request.strategy_id or "trading_buddy",
                order_remark=request.tag or "",
            )
        except Exception as e:
            logger.error("xtquant place_order error: %s", e)
            return BrokerOrderResponse(
                order_id="",
                code=request.code,
                side=request.side,
                quantity=request.quantity,
                status=OrderStatus.REJECTED,
                rejected_reason=f"下单异常: {e}",
                created_at=datetime.now(),
            )

        if order_id is None or order_id <= 0:
            return BrokerOrderResponse(
                order_id="",
                code=request.code,
                side=request.side,
                quantity=request.quantity,
                status=OrderStatus.REJECTED,
                rejected_reason=f"xtquant 拒单 (order_id={order_id})",
                created_at=datetime.now(),
            )

        logger.info(
            "xtquant order placed: id=%s code=%s side=%s qty=%s type=%s price=%s",
            order_id,
            xt_code,
            request.side.value,
            request.quantity,
            request.order_type.value,
            xt_price,
        )

        return BrokerOrderResponse(
            order_id=str(order_id),
            code=request.code,
            side=request.side,
            quantity=request.quantity,
            status=OrderStatus.SUBMITTED,
            order_type=request.order_type,
            limit_price=request.limit_price,
            created_at=datetime.now(),
        )

    # ------------------------------------------------------------------
    # 撤单
    # ------------------------------------------------------------------

    async def cancel_order(self, order_id: str) -> BrokerOrderResponse:
        """撤销指定订单。"""
        self._ensure_connected()

        try:
            oid = int(order_id)
        except ValueError:
            return BrokerOrderResponse(
                order_id=order_id,
                code="",
                side=OrderSide.BUY,
                quantity=0,
                status=OrderStatus.REJECTED,
                rejected_reason="order_id 格式错误，须为整数",
                created_at=datetime.now(),
            )

        try:
            result = await asyncio.to_thread(
                self._trader.cancel_order_stock,
                self._account,
                oid,
            )
        except Exception as e:
            logger.error("xtquant cancel_order error: %s", e)
            return BrokerOrderResponse(
                order_id=order_id,
                code="",
                side=OrderSide.BUY,
                quantity=0,
                status=OrderStatus.REJECTED,
                rejected_reason=f"撤单异常: {e}",
                created_at=datetime.now(),
            )

        # xtquant cancel 返回: 0=成功, -1=已完成, -2=找不到, -3=未登录
        if result == 0:
            logger.info("xtquant order cancelled: id=%s", oid)
            return BrokerOrderResponse(
                order_id=order_id,
                code="",
                side=OrderSide.BUY,
                quantity=0,
                status=OrderStatus.CANCELLED,
                created_at=datetime.now(),
            )
        else:
            reason_map = {
                -1: "订单已成交或已撤，无法撤销",
                -2: "找不到该订单",
                -3: "未登录",
            }
            reason = reason_map.get(result, f"撤单失败，返回码: {result}")
            logger.warning("xtquant cancel failed: id=%s result=%s", oid, result)
            return BrokerOrderResponse(
                order_id=order_id,
                code="",
                side=OrderSide.BUY,
                quantity=0,
                status=OrderStatus.REJECTED,
                rejected_reason=reason,
                created_at=datetime.now(),
            )

    # ------------------------------------------------------------------
    # 查询订单
    # ------------------------------------------------------------------

    async def get_order(self, order_id: str) -> BrokerOrderResponse | None:
        """查询指定订单的最新状态。"""
        self._ensure_connected()

        try:
            oid = int(order_id)
        except ValueError:
            return None

        try:
            xt_order = await asyncio.to_thread(
                self._trader.query_stock_order,
                self._account,
                oid,
            )
        except Exception as e:
            logger.error("xtquant get_order error: %s", e)
            return None

        if xt_order is None:
            return None

        return self._xt_order_to_response(xt_order)

    def _xt_order_to_response(self, xt_order: Any) -> BrokerOrderResponse:
        """将 xtquant 订单对象转换为 BrokerOrderResponse。"""
        code = _from_xt_code(getattr(xt_order, "stock_code", ""))
        side = (
            OrderSide.BUY
            if getattr(xt_order, "order_type", 0) == 23
            else OrderSide.SELL
        )
        status = _map_xt_order_status(getattr(xt_order, "order_status", 48))
        qty = getattr(xt_order, "order_volume", 0)
        traded_qty = getattr(xt_order, "traded_volume", 0)
        traded_price = getattr(xt_order, "traded_price", 0.0)
        order_price = getattr(xt_order, "price", 0.0)
        oid = getattr(xt_order, "order_id", "")

        return BrokerOrderResponse(
            order_id=str(oid),
            code=code,
            side=side,
            quantity=qty,
            filled_quantity=traded_qty,
            avg_fill_price=traded_price if traded_price > 0 else None,
            status=status,
            order_type=OrderType.LIMIT if order_price > 0 else OrderType.MARKET,
            limit_price=order_price if order_price > 0 else None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    # ------------------------------------------------------------------
    # 查询持仓
    # ------------------------------------------------------------------

    async def get_positions(self) -> list[BrokerPosition]:
        """查询当前持仓列表。"""
        self._ensure_connected()

        try:
            xt_positions = await asyncio.to_thread(
                self._trader.query_stock_positions,
                self._account,
            )
        except Exception as e:
            logger.error("xtquant get_positions error: %s", e)
            return []

        if xt_positions is None:
            return []

        positions: list[BrokerPosition] = []
        for pos in xt_positions:
            code = _from_xt_code(getattr(pos, "stock_code", ""))
            if not code:
                continue
            qty = getattr(pos, "volume", 0)
            can_use = getattr(pos, "can_use_volume", 0)
            avg_cost = getattr(pos, "open_price", 0.0)
            mv = getattr(pos, "market_value", 0.0)

            positions.append(
                BrokerPosition(
                    code=code,
                    quantity=qty,
                    available_quantity=can_use,
                    avg_cost=round(avg_cost, 4),
                    market_value=round(mv, 4),
                    updated_at=datetime.now(),
                )
            )

        return positions

    # ------------------------------------------------------------------
    # 查询资金
    # ------------------------------------------------------------------

    async def get_balance(self) -> BrokerBalance:
        """查询资金账户。"""
        self._ensure_connected()

        try:
            asset = await asyncio.to_thread(
                self._trader.query_stock_asset,
                self._account,
            )
        except Exception as e:
            logger.error("xtquant get_balance error: %s", e)
            return BrokerBalance(
                cash=0.0,
                available_cash=0.0,
                frozen_cash=0.0,
                market_value=0.0,
                total_equity=0.0,
                updated_at=datetime.now(),
            )

        if asset is None:
            return BrokerBalance(
                cash=0.0,
                available_cash=0.0,
                frozen_cash=0.0,
                market_value=0.0,
                total_equity=0.0,
                updated_at=datetime.now(),
            )

        cash = getattr(asset, "cash", 0.0)
        frozen = getattr(asset, "frozen_cash", 0.0)
        mv = getattr(asset, "market_value", 0.0)
        total = getattr(asset, "total_asset", 0.0)

        return BrokerBalance(
            cash=round(cash, 4),
            available_cash=round(cash - frozen, 4),
            frozen_cash=round(frozen, 4),
            market_value=round(mv, 4),
            total_equity=round(total, 4),
            updated_at=datetime.now(),
        )

    # ------------------------------------------------------------------
    # 查询成交
    # ------------------------------------------------------------------

    async def get_trades(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[BrokerTrade]:
        """查询当日成交记录。

        xtquant 的 query_stock_trades 只返回当日成交，不支持日期范围。
        start_date/end_date 参数在此实现中被忽略（留待未来扩展）。
        """
        self._ensure_connected()

        try:
            xt_trades = await asyncio.to_thread(
                self._trader.query_stock_trades,
                self._account,
            )
        except Exception as e:
            logger.error("xtquant get_trades error: %s", e)
            return []

        if xt_trades is None:
            return []

        trades: list[BrokerTrade] = []
        for t in xt_trades:
            code = _from_xt_code(getattr(t, "stock_code", ""))
            if not code:
                continue
            side = (
                OrderSide.BUY
                if getattr(t, "order_type", 0) == 23
                else OrderSide.SELL
            )
            qty = getattr(t, "traded_volume", 0)
            price = getattr(t, "traded_price", 0.0)
            amount = getattr(t, "traded_amount", 0.0)
            tid = getattr(t, "traded_id", "")
            oid = getattr(t, "order_id", "")

            trades.append(
                BrokerTrade(
                    trade_id=str(tid),
                    order_id=str(oid),
                    code=code,
                    side=side,
                    quantity=qty,
                    price=round(price, 4),
                    amount=round(amount, 4),
                    trade_date=date.today(),
                    trade_time=datetime.now(),
                )
            )

        return trades

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """检查适配器健康状态。"""
        status = "ok" if self._connected else "disconnected"
        detail: dict[str, Any] = {
            "adapter": self.name,
            "status": status,
            "account_id": self._account_id,
            "qmt_path": self._qmt_path,
            "session_id": self._session_id,
        }

        if self._connected:
            try:
                balance = await self.get_balance()
                detail["balance"] = {
                    "cash": balance.cash,
                    "total_equity": balance.total_equity,
                }
            except Exception as e:
                detail["balance_error"] = str(e)

        return detail
