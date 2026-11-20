from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

from .config import USER_AGENT, detect_proxy

TIMEOUT = 40
RETRIES = 3


def make_opener() -> urllib.request.OpenerDirector:
    proxy = detect_proxy()
    if proxy:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    else:
        handler = urllib.request.ProxyHandler({})
    return urllib.request.build_opener(handler)


def get_bytes(url: str, timeout: int = TIMEOUT, retries: int = RETRIES) -> bytes:
    last: Exception | None = None
    opener = make_opener()
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with opener.open(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001 - 网络抖动统一重试
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"请求失败：{url} → {last}")


def get_json(url: str, timeout: int = TIMEOUT, retries: int = RETRIES) -> Any:
    return json.loads(get_bytes(url, timeout=timeout, retries=retries))
