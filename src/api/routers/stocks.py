"""
Trading Buddy - 股票相关API
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage import get_session, StockRepository
from src.data.models import StockInfo


router = APIRouter()


def _clamp_list_offset(total: int, limit: int, offset: int) -> int:
    """`offset` 超界时钳到最后一页起始；`total==0` 时返回 0。`limit` 须 >= 1。"""
    if total <= 0:
        return 0
    max_start = max(0, (total - 1) // limit * limit)
    off = max(0, offset)
    return min(off, max_start)


class StockListItem(BaseModel):
    code: str
    name: str
    status: str = "ok"


class StockListResponse(BaseModel):
    """分页列表体；`/docs` 中展示示例 JSON。"""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {"code": "sh.600000", "name": "浦发银行", "status": "ok"},
                        {"code": "sz.000001", "name": "平安银行", "status": "ok"},
                    ],
                    "total": 4281,
                    "limit": 100,
                    "offset": 0,
                }
            ]
        }
    )

    items: list[StockListItem] = Field(description="本页行（按 code 排序后切片）")
    total: int = Field(ge=0, description="过滤后的总条数（分页前）")
    limit: int = Field(ge=1, le=500, description="本页条数上限")
    offset: int = Field(
        ge=0,
        description="本页实际起始跳过条数（请求 `offset` 超界时钳到最后一页起点）",
    )


@router.get("/list", response_model=StockListResponse)
async def get_stock_list(
    market: str | None = Query(None, description="市场: sh/sz/bj"),
    industry: str | None = Query(
        None,
        description="行业前缀（与 GET /stocks/industry/{industry} 同口径）；未传或空则不过滤",
    ),
    stock_type: str | None = Query(
        None,
        description="类型: common | st | star | growth | beijing；未知值忽略（不过滤）",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="本页条数（结果按 code 排序后切片）",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="跳过前 offset 条；超过结果集时服务端钳制，响应 `offset` 为实际起点",
    ),
    session: AsyncSession = Depends(get_session),
) -> StockListResponse:
    """获取股票代码列表（分页），含 `name` 展示名与过滤后总数 `total`。"""
    repo = StockRepository(session)
    total = await repo.count_stock_codes(
        market=market,
        industry=industry,
        stock_type=stock_type,
    )
    eff_offset = _clamp_list_offset(total, limit, offset)
    page = await repo.list_stock_codes_page(
        limit,
        eff_offset,
        market=market,
        industry=industry,
        stock_type=stock_type,
    )
    names = await repo.get_name_map(page)
    items = [
        StockListItem(code=c, name=names.get(c, c), status="ok") for c in page
    ]
    return StockListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=eff_offset,
    )


@router.get("/{code}")
async def get_stock(
    code: str,
    session: AsyncSession = Depends(get_session),
) -> StockInfo | dict:
    """获取股票详情"""
    repo = StockRepository(session)
    stock = await repo.get_by_code(code)
    
    if stock is None:
        return {"error": "Stock not found", "code": code}
    
    return stock


@router.get("/industry/{industry}")
async def get_stocks_by_industry(
    industry: str,
    session: AsyncSession = Depends(get_session),
) -> list[StockInfo]:
    """根据行业获取股票（行业字段**前缀匹配**，如「新能源」可命中「新能源 整车」）。"""
    repo = StockRepository(session)
    return await repo.get_by_industry(industry)
