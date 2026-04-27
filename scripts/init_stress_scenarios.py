#!/usr/bin/env python3
"""
初始化内置压力测试场景。
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select

from src.data.storage.database import Database
from src.data.storage.models import StressScenarioModel


BUILTIN_SCENARIOS = [
    {
        "name": "2008 全球金融危机",
        "description": "雷曼兄弟破产引发的全球股灾，A股上证指数从6124点暴跌至1664点",
        "start_date": date(2008, 1, 1),
        "end_date": date(2008, 12, 31),
        "benchmark_drop_pct": -65.0,
        "tags": "global_crisis,2008",
        "is_builtin": True,
    },
    {
        "name": "2015 A股股灾",
        "description": "杠杆牛市破裂，上证指数从5178点跌至2850点，多次熔断",
        "start_date": date(2015, 6, 1),
        "end_date": date(2015, 9, 30),
        "benchmark_drop_pct": -45.0,
        "tags": "a_share_crash,2015",
        "is_builtin": True,
    },
    {
        "name": "2020 COVID-19 疫情冲击",
        "description": "新冠疫情全球爆发，春节后A股首日千股跌停，随后快速反弹",
        "start_date": date(2020, 1, 1),
        "end_date": date(2020, 3, 31),
        "benchmark_drop_pct": -15.0,
        "tags": "covid19,pandemic,2020",
        "is_builtin": True,
    },
    {
        "name": "2018 贸易摩擦",
        "description": "中美贸易摩擦升级，全年震荡下行",
        "start_date": date(2018, 1, 1),
        "end_date": date(2018, 12, 31),
        "benchmark_drop_pct": -25.0,
        "tags": "trade_war,2018",
        "is_builtin": True,
    },
    {
        "name": "2022 俄乌冲突+美联储加息",
        "description": "地缘政治冲突叠加全球紧缩，A股全年低迷",
        "start_date": date(2022, 1, 1),
        "end_date": date(2022, 10, 31),
        "benchmark_drop_pct": -30.0,
        "tags": "geopolitical,rate_hike,2022",
        "is_builtin": True,
    },
]


async def main() -> None:
    db = Database()
    async with db.session() as session:
        for scenario in BUILTIN_SCENARIOS:
            # 检查是否已存在
            stmt = select(StressScenarioModel).where(
                StressScenarioModel.name == scenario["name"],
                StressScenarioModel.is_builtin == True,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                print(f"  [SKIP] {scenario['name']} 已存在")
                continue

            row = StressScenarioModel(**scenario)
            session.add(row)
            print(f"  [OK] {scenario['name']} 添加成功")

        await session.commit()

    print("内置压力测试场景初始化完成。")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
