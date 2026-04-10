#!/usr/bin/env python3
"""
兼容入口：等价于在项目根目录执行
  python scripts/fetch_data.py --source baostock [参数...]
请优先使用 fetch_data.py，数据源由 DATA_SOURCE 或 --source 指定。
"""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    script = root / "scripts" / "fetch_data.py"
    argv = [sys.executable, str(script), "--source", "baostock", *sys.argv[1:]]
    raise SystemExit(subprocess.call(argv))
