from __future__ import annotations

import os
from pathlib import Path

VERSION = "0.1.0"

HOME = Path(os.environ.get("LITRADAR_HOME", Path.home() / ".litradar"))
DATA_DIR = HOME / "data"
DB_PATH = DATA_DIR / "litradar.db"
RUNS_DIR = HOME / "runs"

USER_AGENT = os.environ.get(
    "LITRADAR_UA", "litradar/0.1 (https://github.com/; mailto:pan@example.com)"
)
REQUEST_INTERVAL = float(os.environ.get("LITRADAR_RATE", "0.35"))


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
