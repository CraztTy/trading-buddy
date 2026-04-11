"""pytest 入口：须在首次 import src.* 之前生效。"""

from __future__ import annotations

import os

os.environ["TRADING_BUDDY_SKIP_DOTENV"] = "1"
