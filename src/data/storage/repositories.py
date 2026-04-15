"""
Trading Buddy - 数据仓库
封装数据库操作，提供简洁的增删改查接口
"""

from datetime import date, datetime
from typing import Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common import get_logger
from ..models import StockInfo, KLine, Market, StockType
from .models import StockInfoModel, DailyKlineModel, SectorInfoModel


logger = get_logger("repository")

# SQLite 默认 SQLITE_MAX_VARIABLE_NUMBER≈999；IN 占位 + WHERE 留余量
_KLINE_IN_CHUNK = 400


def _stock_type_to_int(st: StockType) -> int:
    return {
        StockType.COMMON: 1,
        StockType.ST: 2,
        StockType.STAR: 3,
        StockType.GROWTH: 4,
        StockType.BEIJING: 5,
    }.get(st, 1)


def _int_to_stock_type(i: int) -> StockType:
    return {
        1: StockType.COMMON,
        2: StockType.ST,
        3: StockType.STAR,
        4: StockType.GROWTH,
        5: StockType.BEIJING,
    }.get(i, StockType.COMMON)


def _sql_like_prefix_pattern(raw: str) -> str:
    """LIKE 前缀匹配用字面量：`%` / `_` / `\\` 转义，末尾追加 `%`。"""
    esc = (
        raw.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"{esc}%"


def _stock_type_filter_int(raw: str | None) -> int | None:
    """Query 参数 `stock_type` → 与 stock_info.stock_type 一致的整型；未知值返回 None（不过滤）。"""
    if raw is None or not str(raw).strip():
        return None
    key = str(raw).strip().lower()
    return {
        "common": 1,
        "st": 2,
        "star": 3,
        "growth": 4,
        "beijing": 5,
    }.get(key)


class StockRepository:
    """股票数据仓库"""
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def bulk_upsert(self, stocks: list[StockInfo]) -> int:
        """批量插入或更新股票（按 code 主键合并）"""
        count = 0
        for stock in stocks:
            model = StockInfoModel(
                code=stock.code,
                name=stock.name,
                industry=stock.industry,
                sector=stock.sector_code,
                list_date=stock.ipo_date,
                out_date=stock.out_date,
                stock_type=_stock_type_to_int(stock.stock_type),
                status=1,
                market=stock.market.value,
                is_trading=stock.is_trading,
            )
            await self._session.merge(model)
            count += 1

        await self._session.flush()
        logger.info(f"Bulk upserted {count} stocks")
        return count
    
    async def get_by_code(self, code: str) -> StockInfo | None:
        """根据代码查询股票"""
        stmt = select(StockInfoModel).where(StockInfoModel.code == code)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        
        if model:
            try:
                mkt = Market(model.market)
            except ValueError:
                mkt = Market.SH
            return StockInfo(
                code=model.code,
                name=model.name or "",
                ipo_date=model.list_date,
                out_date=model.out_date,
                stock_type=_int_to_stock_type(model.stock_type),
                market=mkt,
                industry=model.industry,
                sector_code=model.sector,
                is_trading=model.is_trading,
            )
        return None

    @staticmethod
    def _stock_list_filter_clauses(
        market: str | None,
        is_trading: bool | None,
        industry: str | None,
        stock_type: str | None,
    ) -> list:
        clauses: list = []
        if market:
            clauses.append(StockInfoModel.market == market)
        if is_trading is not None:
            clauses.append(StockInfoModel.is_trading.is_(is_trading))
        ind_key = (industry or "").strip()
        if ind_key:
            clauses.append(
                StockInfoModel.industry.like(
                    _sql_like_prefix_pattern(ind_key), escape="\\"
                )
            )
        st_i = _stock_type_filter_int(stock_type)
        if st_i is not None:
            clauses.append(StockInfoModel.stock_type == st_i)
        return clauses

    async def get_name_map(self, codes: Sequence[str]) -> dict[str, str]:
        """批量查询 code -> 显示名（单次 IN 查询，供看板等聚合接口使用）。"""
        uniq = list(dict.fromkeys(c for c in codes if c))
        if not uniq:
            return {}
        stmt = select(StockInfoModel.code, StockInfoModel.name).where(
            StockInfoModel.code.in_(uniq)
        )
        result = await self._session.execute(stmt)
        return {
            row[0]: (row[1] if row[1] else row[0])
            for row in result.all()
        }
    
    async def count_stock_codes(
        self,
        market: str | None = None,
        is_trading: bool = True,
        *,
        industry: str | None = None,
        stock_type: str | None = None,
    ) -> int:
        """与 `get_all_codes` / `list_stock_codes_page` 相同过滤条件下的总行数。"""
        clauses = self._stock_list_filter_clauses(
            market, is_trading, industry, stock_type
        )
        stmt = select(func.count(StockInfoModel.code))
        if clauses:
            stmt = stmt.where(and_(*clauses))
        n = (await self._session.execute(stmt)).scalar_one()
        return int(n or 0)

    async def list_stock_codes_page(
        self,
        limit: int,
        offset: int,
        market: str | None = None,
        is_trading: bool = True,
        *,
        industry: str | None = None,
        stock_type: str | None = None,
    ) -> list[str]:
        """按 `code` 排序后 `LIMIT`/`OFFSET` 取一页（`limit`/`offset` 由调用方保证合法）。"""
        clauses = self._stock_list_filter_clauses(
            market, is_trading, industry, stock_type
        )
        stmt = select(StockInfoModel.code)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        stmt = stmt.order_by(StockInfoModel.code).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_all_codes(
        self,
        market: str | None = None,
        is_trading: bool = True,
        *,
        industry: str | None = None,
        stock_type: str | None = None,
    ) -> list[str]:
        """获取股票代码列表；可选市场、行业**前缀**（与 `get_by_industry` 同口径）、`stock_type`（common/st/star/growth/beijing）。"""
        clauses = self._stock_list_filter_clauses(
            market, is_trading, industry, stock_type
        )
        stmt = select(StockInfoModel.code)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        stmt = stmt.order_by(StockInfoModel.code)
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]
    
    async def get_by_industry(self, industry: str) -> list[StockInfo]:
        """根据行业查询股票（**前缀匹配**：`industry` 字段以参数字符串开头；空串返回空列表）。"""
        key = (industry or "").strip()
        if not key:
            return []
        pat = _sql_like_prefix_pattern(key)
        stmt = select(StockInfoModel).where(
            StockInfoModel.industry.like(pat, escape="\\")
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        
        return [
            StockInfo(
                code=m.code,
                name=m.name or "",
                ipo_date=m.list_date,
                out_date=m.out_date,
                stock_type=_int_to_stock_type(m.stock_type),
                market=Market(m.market) if m.market in (e.value for e in Market) else Market.SH,
                industry=m.industry,
                sector_code=m.sector,
                is_trading=m.is_trading,
            )
            for m in models
        ]


class KlineRepository:
    """K线数据仓库"""
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    def _kline_row_dict(self, kline: KLine) -> dict:
        return {
            "code": kline.code,
            "trade_date": kline.trade_date,
            "open": kline.open,
            "high": kline.high,
            "low": kline.low,
            "close": kline.close,
            "volume": kline.volume,
            "amount": kline.amount,
            "turnover_rate": kline.turnover_rate,
            "change_pct": kline.pct_change,
            "adjust_flag": kline.adjust_flag,
        }

    async def bulk_insert(self, klines: list[KLine]) -> int:
        """批量写入日K线（同一 code+trade_date 已存在则更新，可安全重复执行拉数）"""
        if not klines:
            return 0
        dialect = self._session.bind.dialect.name
        rows = [self._kline_row_dict(k) for k in klines]

        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert

            ins = dialect_insert(DailyKlineModel).values(rows)
            stmt = ins.on_conflict_do_update(
                index_elements=["code", "trade_date", "adjust_flag"],
                set_={
                    "open": ins.excluded.open,
                    "high": ins.excluded.high,
                    "low": ins.excluded.low,
                    "close": ins.excluded.close,
                    "volume": ins.excluded.volume,
                    "amount": ins.excluded.amount,
                    "turnover_rate": ins.excluded.turnover_rate,
                    "change_pct": ins.excluded.change_pct,
                    "adjust_flag": ins.excluded.adjust_flag,
                },
            )
            await self._session.execute(stmt)
        elif dialect == "mysql":
            from sqlalchemy.dialects.mysql import insert as dialect_insert

            ins = dialect_insert(DailyKlineModel).values(rows)
            stmt = ins.on_duplicate_key_update(
                open=ins.inserted.open,
                high=ins.inserted.high,
                low=ins.inserted.low,
                close=ins.inserted.close,
                volume=ins.inserted.volume,
                amount=ins.inserted.amount,
                turnover_rate=ins.inserted.turnover_rate,
                change_pct=ins.inserted.change_pct,
                adjust_flag=ins.inserted.adjust_flag,
            )
            await self._session.execute(stmt)
        else:
            count = 0
            for kline in klines:
                self._session.add(
                    DailyKlineModel(
                        code=kline.code,
                        trade_date=kline.trade_date,
                        open=kline.open,
                        high=kline.high,
                        low=kline.low,
                        close=kline.close,
                        volume=kline.volume,
                        amount=kline.amount,
                        turnover_rate=kline.turnover_rate,
                        change_pct=kline.pct_change,
                        adjust_flag=kline.adjust_flag,
                    )
                )
                count += 1
            await self._session.flush()
            logger.info(f"Bulk inserted {count} klines (fallback add)")
            return count

        await self._session.flush()
        logger.info(f"Bulk upserted {len(klines)} klines")
        return len(klines)
    
    async def get_daily(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
        adjust_flag: str = "3",
    ) -> list[KLine]:
        """查询日K线数据"""
        stmt = select(DailyKlineModel).where(
            DailyKlineModel.code == code,
            DailyKlineModel.adjust_flag == adjust_flag,
        )

        if start_date:
            stmt = stmt.where(DailyKlineModel.trade_date >= start_date)
        if end_date:
            stmt = stmt.where(DailyKlineModel.trade_date <= end_date)

        stmt = stmt.order_by(DailyKlineModel.trade_date.desc()).limit(limit)

        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [
            KLine(
                code=m.code,
                trade_date=m.trade_date,
                open=float(m.open),
                high=float(m.high),
                low=float(m.low),
                close=float(m.close),
                volume=m.volume or 0,
                amount=float(m.amount) if m.amount else 0.0,
                turnover_rate=float(m.turnover_rate) if m.turnover_rate else None,
                pct_change=float(m.change_pct) if m.change_pct else None,
                adjust_flag=m.adjust_flag,
            )
            for m in reversed(models)  # 正序返回
        ]
    
    async def get_latest_date(self, code: str, adjust_flag: str = "3") -> date | None:
        """获取最新K线日期"""
        stmt = select(func.max(DailyKlineModel.trade_date)).where(
            DailyKlineModel.code == code,
            DailyKlineModel.adjust_flag == adjust_flag,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_trade_dates_for_codes(
        self, codes: Sequence[str], adjust_flag: str = "3"
    ) -> dict[str, date]:
        """批量查询各 code 在 daily_kline 中的最新 trade_date（一次 GROUP BY）。"""
        uniq = list(dict.fromkeys(c for c in codes if c))
        if not uniq:
            return {}
        stmt = (
            select(DailyKlineModel.code, func.max(DailyKlineModel.trade_date))
            .where(
                DailyKlineModel.code.in_(uniq),
                DailyKlineModel.adjust_flag == adjust_flag,
            )
            .group_by(DailyKlineModel.code)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_latest_global_trade_date(self, adjust_flag: str = "3") -> date | None:
        """全表最新交易日（用于涨跌榜默认日期，避免非交易日无数据）"""
        stmt = select(func.max(DailyKlineModel.trade_date)).where(
            DailyKlineModel.adjust_flag == adjust_flag,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_codes_on_trade_date(
        self, trade_date: date, *, max_codes: int | None = None, adjust_flag: str = "3"
    ) -> list[str]:
        """在指定 ``trade_date`` 有日 K 的 ``code`` 列表（按 ``code`` 升序）。

        ``max_codes`` 为 ``None`` 或 **≤0** 时不限制条数；**>0** 时等价 **LIMIT**。
        """
        stmt = (
            select(DailyKlineModel.code)
            .where(
                DailyKlineModel.trade_date == trade_date,
                DailyKlineModel.adjust_flag == adjust_flag,
            )
            .order_by(DailyKlineModel.code)
        )
        if max_codes is not None and max_codes > 0:
            stmt = stmt.limit(max_codes)
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_daily_last_n_bars_per_code(
        self,
        codes: Sequence[str],
        end_date: date,
        *,
        max_bars: int,
        adjust_flag: str = "3",
    ) -> dict[str, list[KLine]]:
        """一次（或多次分块 **IN**）查询：各 ``code`` 在 ``trade_date <= end_date`` 下最近 ``max_bars`` 根日 K（**时间升序**）。

        依赖 **ROW_NUMBER** 窗口（MySQL **8+**、SQLite **3.25+**）。无数据的 ``code`` 不出现在 dict。
        """
        uniq = list(dict.fromkeys(c for c in codes if c))
        if not uniq or max_bars < 1:
            return {}

        out: dict[str, list[KLine]] = {}
        for i in range(0, len(uniq), _KLINE_IN_CHUNK):
            chunk = uniq[i : i + _KLINE_IN_CHUNK]
            part = await self._get_daily_last_n_bars_per_code_chunk(
                chunk, end_date, max_bars=max_bars, adjust_flag=adjust_flag
            )
            out.update(part)
        return out

    async def _get_daily_last_n_bars_per_code_chunk(
        self,
        codes: list[str],
        end_date: date,
        *,
        max_bars: int,
        adjust_flag: str = "3",
    ) -> dict[str, list[KLine]]:
        _rn = (
            func.row_number()
            .over(
                partition_by=DailyKlineModel.code,
                order_by=DailyKlineModel.trade_date.desc(),
            )
            .label("_rn")
        )
        inner = (
            select(
                DailyKlineModel.code,
                DailyKlineModel.trade_date,
                DailyKlineModel.open,
                DailyKlineModel.high,
                DailyKlineModel.low,
                DailyKlineModel.close,
                DailyKlineModel.volume,
                DailyKlineModel.amount,
                DailyKlineModel.turnover_rate,
                DailyKlineModel.change_pct,
                DailyKlineModel.adjust_flag,
                _rn,
            )
            .where(
                DailyKlineModel.code.in_(codes),
                DailyKlineModel.trade_date <= end_date,
                DailyKlineModel.adjust_flag == adjust_flag,
            )
        ).subquery()
        stmt = (
            select(inner)
            .where(inner.c._rn <= max_bars)
            .order_by(inner.c.code, inner.c.trade_date)
        )
        result = await self._session.execute(stmt)
        out: dict[str, list[KLine]] = {}
        for row in result.mappings():
            kline = KLine(
                code=row["code"],
                trade_date=row["trade_date"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=row["volume"] or 0,
                amount=float(row["amount"]) if row["amount"] else 0.0,
                turnover_rate=float(row["turnover_rate"])
                if row["turnover_rate"] is not None
                else None,
                pct_change=float(row["change_pct"])
                if row["change_pct"] is not None
                else None,
                adjust_flag=row["adjust_flag"],
            )
            out.setdefault(kline.code, []).append(kline)
        return out

    async def get_top_gainers(
        self, trade_date: date | None, limit: int = 10, adjust_flag: str = "3"
    ) -> list[KLine]:
        """获取涨幅最大的股票。trade_date 为 None 时用单次查询绑定全表最新交易日（少一次往返）。"""
        if trade_date is None:
            latest = (
                select(func.max(DailyKlineModel.trade_date))
                .where(DailyKlineModel.adjust_flag == adjust_flag)
                .scalar_subquery()
            )
            date_clause = DailyKlineModel.trade_date == latest
        else:
            date_clause = DailyKlineModel.trade_date == trade_date
        stmt = (
            select(DailyKlineModel)
            .where(date_clause)
            .where(DailyKlineModel.adjust_flag == adjust_flag)
            .where(DailyKlineModel.change_pct.isnot(None))
            .order_by(DailyKlineModel.change_pct.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [
            KLine(
                code=m.code,
                trade_date=m.trade_date,
                open=float(m.open),
                high=float(m.high),
                low=float(m.low),
                close=float(m.close),
                volume=m.volume or 0,
                amount=float(m.amount) if m.amount else 0.0,
                pct_change=float(m.change_pct) if m.change_pct else None,
                adjust_flag=m.adjust_flag,
            )
            for m in models
        ]

    async def get_top_losers(
        self, trade_date: date | None, limit: int = 10, adjust_flag: str = "3"
    ) -> list[KLine]:
        """获取跌幅最大的股票。trade_date 为 None 时同上，单次查询。"""
        if trade_date is None:
            latest = (
                select(func.max(DailyKlineModel.trade_date))
                .where(DailyKlineModel.adjust_flag == adjust_flag)
                .scalar_subquery()
            )
            date_clause = DailyKlineModel.trade_date == latest
        else:
            date_clause = DailyKlineModel.trade_date == trade_date
        stmt = (
            select(DailyKlineModel)
            .where(date_clause)
            .where(DailyKlineModel.adjust_flag == adjust_flag)
            .where(DailyKlineModel.change_pct.isnot(None))
            .order_by(DailyKlineModel.change_pct.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [
            KLine(
                code=m.code,
                trade_date=m.trade_date,
                open=float(m.open),
                high=float(m.high),
                low=float(m.low),
                close=float(m.close),
                volume=m.volume or 0,
                amount=float(m.amount) if m.amount else 0.0,
                pct_change=float(m.change_pct) if m.change_pct else None,
                adjust_flag=m.adjust_flag,
            )
            for m in models
        ]

    async def get_top_by_amount(
        self,
        trade_date: date | None,
        limit: int = 10,
        *,
        trading_stocks_only: bool = True,
        adjust_flag: str = "3",
    ) -> list[KLine]:
        """指定交易日成交额 Top；`trade_date` 为 None 时用全表最新交易日。

        默认 **INNER JOIN** ``stock_info`` 且 ``is_trading``，排除无基础信息的代码（如仅存在于 K 表的指数）。
        """
        if trade_date is None:
            latest = (
                select(func.max(DailyKlineModel.trade_date))
                .where(DailyKlineModel.adjust_flag == adjust_flag)
                .scalar_subquery()
            )
            date_clause = DailyKlineModel.trade_date == latest
        else:
            date_clause = DailyKlineModel.trade_date == trade_date
        stmt = select(DailyKlineModel).where(
            date_clause,
            DailyKlineModel.adjust_flag == adjust_flag,
        )
        if trading_stocks_only:
            stmt = stmt.join(
                StockInfoModel, StockInfoModel.code == DailyKlineModel.code
            ).where(StockInfoModel.is_trading.is_(True))
        stmt = (
            stmt.where(DailyKlineModel.amount.isnot(None))
            .order_by(DailyKlineModel.amount.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [
            KLine(
                code=m.code,
                trade_date=m.trade_date,
                open=float(m.open),
                high=float(m.high),
                low=float(m.low),
                close=float(m.close),
                volume=m.volume or 0,
                amount=float(m.amount) if m.amount else 0.0,
                turnover_rate=float(m.turnover_rate) if m.turnover_rate else None,
                pct_change=float(m.change_pct) if m.change_pct else None,
                adjust_flag=m.adjust_flag,
            )
            for m in models
        ]
