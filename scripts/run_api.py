"""
从项目根启动 FastAPI：读取 `.env` 中的 API_HOST / API_PORT / API_DEBUG（与 FIRST_STEPS 一致）。

用法（仓库根目录）::

    python scripts/run_api.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> None:
    import uvicorn

    from src.common.config import get_settings

    api = get_settings().api
    uvicorn.run(
        "src.api.main:app",
        host=api.host,
        port=api.port,
        reload=api.debug,
    )


if __name__ == "__main__":
    main()
