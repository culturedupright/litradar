from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from collections.abc import Iterator

from .config import REQUEST_INTERVAL, USER_AGENT
from .models import Paper

BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def build_query(pico: dict[str, str] | None = None,
                years: str | None = None,
                extra: str | None = None) -> str:
    """把 PICO 四格翻成 Europe PMC 布尔检索式。

    同一个格子内的同义词用 | 分隔，格子之间用 AND。
    """
    parts: list[str] = []
    for key in ("population", "intervention", "comparison", "outcome"):
        value = (pico or {}).get(key, "")
        terms = [t.strip() for t in value.split("|") if t.strip()]
        if terms:
            parts.append("(" + " OR ".join(terms) + ")")
    if extra and extra.strip():
        parts.append("(" + extra.strip() + ")")
    query = " AND ".join(parts)
    if years:
        start, end = [x.strip() for x in years.split("-")]
        query += f" AND (FIRST_PDATE:[{start}-01-01 TO {end}-12-31])"
    return query


def _request(query: str, cursor: str, page_size: int, timeout: int) -> dict:
    params = urllib.parse.urlencode({
        "query": query,
        "format": "json",
        "pageSize": page_size,
        "resultType": "core",
        "cursorMark": cursor,
    })
    req = urllib.request.Request(f"{BASE_URL}?{params}",
                                 headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def fetch_page(query: str, cursor: str = "*", page_size: int = 100,
               timeout: int = 30, retries: int = 3) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return _request(query, cursor, page_size, timeout)
        except Exception as exc:  # noqa: BLE001 - 网络抖动统一重试
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Europe PMC 请求失败：{last}")


def iter_papers(query: str, limit: int = 200,
                rate: float = REQUEST_INTERVAL) -> Iterator[Paper]:
    cursor, seen, yielded = "*", 0, 0
    while yielded < limit:
        data = fetch_page(query, cursor)
        items = (data.get("resultList") or {}).get("result") or []
        if not items:
            return
        for item in items:
            paper = Paper.from_europepmc(item)
            if not paper.id:
                continue
            yield paper
            yielded += 1
            if yielded >= limit:
                return
        cursor = data.get("nextCursorMark")
        if not cursor or cursor == "*":
            return
        time.sleep(rate)
