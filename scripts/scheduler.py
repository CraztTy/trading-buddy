#!/usr/bin/env python3
"""
定时任务：建议每日收盘后跑一次「日常增量」拉数。

实现方式：到点用子进程执行 fetch_data --mode daily，避免阻塞与 baostock 会话纠缠。
更推荐在生产环境用系统计划任务直接调用同一命令，而不用常驻本脚本。

PowerShell 计划任务示例（每天 16:05）:
  cd C:\\path\\to\\trading-buddy
  python scripts\\fetch_data.py --mode daily --overlap-days 7
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

import schedule

project_root = Path(__file__).resolve().parent.parent
fetch_script = Path(__file__).resolve().parent / "fetch_data.py"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("scheduler")


def run_daily_fetch() -> None:
    cmd = [
        sys.executable,
        str(fetch_script),
        "--mode",
        "daily",
        "--overlap-days",
        "7",
    ]
    logger.info("执行: %s", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(project_root))
    if r.returncode != 0:
        logger.error("日常拉数失败，退出码 %s", r.returncode)
    else:
        logger.info("日常拉数完成")


def main() -> None:
    # A 股收盘后约 15:00，留缓冲到 16:05
    schedule.every().day.at("16:05").do(run_daily_fetch)
    logger.info("调度器已启动：每日 16:05 执行增量拉数（Ctrl+C 退出）")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
