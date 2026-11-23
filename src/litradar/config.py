from __future__ import annotations

import os
from pathlib import Path

VERSION = "0.13.0"

HOME = Path(os.environ.get("LITRADAR_HOME", Path.home() / ".litradar"))
DATA_DIR = HOME / "data"
DB_PATH = DATA_DIR / "litradar.db"
RUNS_DIR = HOME / "runs"
FULLTEXT_DIR = HOME / "fulltext"

USER_AGENT = os.environ.get(
    "LITRADAR_UA", "litradar/0.1 (https://github.com/; mailto:pan@example.com)"
)
REQUEST_INTERVAL = float(os.environ.get("LITRADAR_RATE", "0.35"))


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)


def detect_proxy() -> str | None:
    """按 环境变量 → Windows 系统代理 的顺序探测代理。

    Python 不会读注册表里的系统代理，Clash 这类工具开的开关需要手动接过来。
    """
    for name in ("LITRADAR_PROXY", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        value = os.environ.get(name)
        if value:
            return value
    if os.name != "nt":
        return None
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
        if not enabled:
            return None
        server, _ = winreg.QueryValueEx(key, "ProxyServer")
        if not server:
            return None
        # ProxyServer 可能是 "http=127.0.0.1:7897;https=127.0.0.1:7897"
        for part in str(server).split(";"):
            if "=" in part:
                proto, value = part.split("=", 1)
                if proto.strip().lower() in ("http", "https"):
                    server = value.strip()
        return server if "://" in server else f"http://{server}"
    except OSError:
        return None
