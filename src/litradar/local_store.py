"""国内本地科研单元库。

B 线只读用户目录里的本地库，不碰 ROR / OpenAlex / Wikidata。
种子分两层：
1. 教育部全国普通/成人高校名单（学校层，截至 2026-06-17）；
2. 兰州大学草业学院与管理学院的院内研究所/中心/团队（人工核验档）。
用户导入的 CSV/JSON 与种子同库，用 ``cn:`` 前缀 ID，便于与全球线分开。
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import threading
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from . import config

STORE_PATH = config.DATA_DIR / "local_units.json"
SEED_DIR = Path(__file__).resolve().parent / "data"
SEED_FILES = ("cn_universities_seed.json", "lzu_units_seed.json")
STORE_VERSION = "0.12.0"

_LOCK = threading.RLock()
_CACHE: list[dict[str, Any]] | None = None


def _norm(text: str) -> str:
    return re.sub(r"[\s\-_,，。；;：:、/\\|（）()\[\]【】.·'\"“”]+", "", str(text or "").lower())


def _seed_units() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in SEED_FILES:
        path = SEED_DIR / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, list):
            rows.extend(x for x in data if isinstance(x, dict) and x.get("id") and x.get("name"))
    return _normalize_many(rows)


def _normalize_unit(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["id"] = str(item.get("id") or "").strip()
    item["name"] = str(item.get("name") or "").strip()
    item["short"] = str(item.get("short") or "").strip()
    aliases = item.get("aliases") or []
    if isinstance(aliases, str):
        aliases = re.split(r"[;；,，、|]", aliases)
    item["aliases"] = [str(x).strip() for x in aliases if str(x).strip()][:12]
    item["type"] = str(item.get("type") or "research_unit").strip()
    item["type_label"] = str(item.get("type_label") or "研究单元").strip()
    item["unit"] = str(item.get("unit") or item.get("institution") or "").strip()
    item["institution"] = str(item.get("institution") or item["unit"]).strip()
    item["department"] = str(item.get("department") or "").strip()
    item["country"] = str(item.get("country") or "CN").strip()
    item["country_name"] = str(item.get("country_name") or "中国").strip()
    item["region"] = str(item.get("region") or item.get("province") or "").strip()
    item["source"] = str(item.get("source") or "").strip()
    item["source_kind"] = "cn_local"
    item["source_label"] = str(item.get("source_label") or "本地核验档").strip()
    item["verified"] = str(item.get("verified") or "").strip()
    item["leader"] = str(item.get("leader") or "").strip()
    for key in ("deputy_leaders", "chief_scientist", "members", "directions"):
        value = item.get(key)
        if isinstance(value, str):
            value = [x.strip() for x in re.split(r"[;；,，、]", value) if x.strip()]
        item[key] = [str(x) for x in (value or []) if str(x).strip()]
    item["note"] = str(item.get("note") or "").strip()
    item["line"] = "local"
    return item


def _normalize_many(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        item = _normalize_unit(row)
        if not item["id"] or not item["name"] or item["id"] in seen:
            continue
        seen.add(item["id"])
        out.append(item)
    return out


def _write(rows: list[dict[str, Any]]) -> None:
    config.ensure_dirs()
    payload = {
        "version": STORE_VERSION,
        "seed_version": "2026-06-17",
        "updated": date.today().isoformat(),
        "units": rows,
    }
    tmp = STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(STORE_PATH)


def _load() -> list[dict[str, Any]]:
    global _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        seeds = _seed_units()
        if not STORE_PATH.exists():
            _CACHE = seeds
            _write(_CACHE)
            return _CACHE
        try:
            data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _CACHE = seeds
            _write(_CACHE)
            return _CACHE
        rows = data.get("units") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            rows = []
        existing = _normalize_many(rows)
        by_id = {x["id"]: x for x in existing}
        changed = False
        for seed in seeds:
            # 只补缺失种子，用户改过的同名记录保留，避免覆盖本地维护。
            if seed["id"] not in by_id:
                existing.append(seed)
                by_id[seed["id"]] = seed
                changed = True
        _CACHE = existing
        if changed or not STORE_PATH.exists():
            _write(_CACHE)
        return _CACHE


def reload() -> None:
    global _CACHE
    with _LOCK:
        _CACHE = None


def _values(item: dict[str, Any]) -> list[str]:
    values = [item.get("name", ""), item.get("short", "")]
    values.extend(item.get("aliases") or [])
    return [str(x) for x in values if str(x or "").strip()]


def _context_values(item: dict[str, Any]) -> list[str]:
    values = [item.get("unit", ""), item.get("institution", ""), item.get("department", "")]
    values.extend(item.get("unit_aliases") or [])
    values.extend(item.get("department_aliases") or [])
    return [str(x) for x in values if str(x or "").strip()]


_PINYIN: dict[str, tuple[str, str]] | None = None


def _pinyin_index() -> dict[str, tuple[str, str]]:
    global _PINYIN
    if _PINYIN is not None:
        return _PINYIN
    try:
        from pypinyin import Style, lazy_pinyin
    except Exception:  # noqa: BLE001
        _PINYIN = {}
        return _PINYIN
    out: dict[str, tuple[str, str]] = {}
    for item in _load():
        names = [item.get("name", ""), item.get("short", "")] + list(item.get("aliases") or [])
        fulls, initials = [], []
        for name in names:
            if not name:
                continue
            py = lazy_pinyin(str(name), errors="ignore")
            fulls.append("".join(py).lower())
            initials.append("".join(lazy_pinyin(str(name), style=Style.FIRST_LETTER, errors="ignore")).lower())
        out[item["id"]] = (" ".join(fulls), " ".join(initials))
    _PINYIN = out
    return out


def _score(query: str, item: dict[str, Any]) -> int:
    q = _norm(query)
    if not q:
        return 0
    best = 0
    for value in _values(item):
        n = _norm(value)
        if not n:
            continue
        if q == n:
            return 100
        if n.startswith(q) or q.startswith(n):
            best = max(best, 88 if min(len(q), len(n)) >= 2 else 60)
            continue
        if q in n:
            best = max(best, 72 if len(q) >= 2 else 50)
            continue
        q_tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", q))
        n_tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", n))
        common = q_tokens & n_tokens
        if common:
            best = max(best, int(25 + 35 * len(common) / len(q_tokens | n_tokens)))
    # 单位/院系是上下文，不是单元名：全等也只给中低分，避免搜“兰州大学”时
    # 把校内所有研究所排到学校本身前面。
    for value in _context_values(item):
        n = _norm(value)
        if not n:
            continue
        if q == n:
            best = max(best, 78)
        elif q in n or n in q:
            best = max(best, 50)
    if re.fullmatch(r"[a-z0-9 ]+", q):
        py = _pinyin_index().get(item["id"], ("", ""))
        if py[0] and (q in py[0] or q in py[1]):
            best = max(best, 65)
    return best


def search(query: str, limit: int = 20) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    scored = []
    for item in _load():
        score = _score(q, item)
        if score >= 40:
            scored.append((score, len(item.get("name", "")), item))
    scored.sort(key=lambda x: (-x[0], x[1], x[2].get("name", "")))
    out = []
    for score, _, item in scored[:max(1, min(int(limit or 20), 50))]:
        row = dict(item)
        row["score"] = score
        out.append(row)
    return out


def get(group_id: str) -> dict[str, Any] | None:
    gid = str(group_id or "").strip()
    if not gid:
        return None
    for item in _load():
        if item["id"] == gid:
            return dict(item)
    return None


def all_units() -> list[dict[str, Any]]:
    return [dict(item) for item in _load()]


def resolve(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None
    hit = get(text)
    if hit:
        return hit
    rows = search(text, limit=5)
    if rows and _score(text, rows[0]) >= 80:
        return rows[0]
    return None


def stats() -> dict[str, Any]:
    rows = _load()
    by_label: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for item in rows:
        by_label[item.get("source_label", "")] = by_label.get(item.get("source_label", ""), 0) + 1
        by_type[item.get("type_label", "")] = by_type.get(item.get("type_label", ""), 0) + 1
    return {"total": len(rows), "by_source": by_label, "by_type": by_type,
            "store": str(STORE_PATH)}


_FIELD_MAP = {
    "id": "id", "编号": "id", "名称": "name", "研究群": "name", "研究单元": "name",
    "name": "name", "简称": "short", "short": "short", "别名": "aliases", "aliases": "aliases",
    "类型": "type_label", "type": "type", "type_label": "type_label",
    "单位": "unit", "学校": "unit", "机构": "unit", "unit": "unit",
    "院系": "department", "学院": "department", "department": "department",
    "负责人": "leader", "leader": "leader", "副主任": "deputy_leaders",
    "成员": "members", "members": "members", "方向": "directions", "directions": "directions",
    "平台": "platform", "platform": "platform", "平台层级": "platform_level",
    "来源": "source", "source": "source", "核验日期": "verified", "verified": "verified",
    "备注": "note", "note": "note", "省份": "region", "region": "region",
}


def _rows_from_csv(text: str) -> list[dict[str, Any]]:
    # 兼容 UTF-8 BOM 与制表符分隔。
    sample = text[:2000]
    delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = []
    for raw in reader:
        row: dict[str, Any] = {}
        for key, value in raw.items():
            if not key:
                continue
            field = _FIELD_MAP.get(str(key).strip(), str(key).strip())
            row[field] = value
        rows.append(row)
    return rows


def _make_id(row: dict[str, Any]) -> str:
    parts = [row.get("unit", ""), row.get("department", ""), row.get("name", ""), row.get("source", "")]
    digest = hashlib.sha1("|".join(str(x) for x in parts).encode("utf-8")).hexdigest()[:12]
    return f"cn:local:{digest}"


def import_rows(rows: Iterable[dict[str, Any]], source_label: str = "用户导入") -> dict[str, Any]:
    """把 CSV/JSON 行写进本地库；同 ID 覆盖，同单位+院系+名称视为同一条。"""
    incoming = []
    for raw in rows:
        row = dict(raw)
        # 中文表头先映射
        mapped: dict[str, Any] = {}
        for key, value in row.items():
            mapped[_FIELD_MAP.get(str(key).strip(), str(key).strip())] = value
        name = str(mapped.get("name") or mapped.get("研究群") or "").strip()
        if not name:
            name = str(mapped.get("unit") or mapped.get("学校") or "").strip()
        if not name:
            continue
        mapped["name"] = name
        if not mapped.get("unit"):
            mapped["unit"] = mapped.get("institution") or mapped.get("学校") or ""
        if not mapped.get("institution"):
            mapped["institution"] = mapped.get("unit") or ""
        mapped["source_label"] = mapped.get("source_label") or source_label
        mapped["id"] = str(mapped.get("id") or "").strip() or _make_id(mapped)
        incoming.append(_normalize_unit(mapped))
    if not incoming:
        return {"added": 0, "updated": 0, "total": len(_load())}

    with _LOCK:
        rows_now = _load()
        by_id = {x["id"]: x for x in rows_now}
        by_key = {(x.get("unit", ""), x.get("department", ""), x.get("name", "")): x for x in rows_now}
        added = updated = 0
        for item in incoming:
            key = (item.get("unit", ""), item.get("department", ""), item.get("name", ""))
            old = by_id.get(item["id"]) or by_key.get(key)
            if old:
                old.update(item)
                updated += 1
            else:
                rows_now.append(item)
                by_id[item["id"]] = item
                by_key[key] = item
                added += 1
        _write(rows_now)
        global _CACHE
        _CACHE = rows_now
    return {"added": added, "updated": updated, "total": len(_load())}


def import_text(text: str, source_label: str = "用户导入") -> dict[str, Any]:
    stripped = text.lstrip("\ufeff").strip()
    if not stripped:
        return {"added": 0, "updated": 0, "total": len(_load())}
    if stripped[0] in "[{":
        data = json.loads(stripped)
        rows = data.get("units") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError("JSON 必须是数组，或带 units 数组的对象")
        return import_rows(rows, source_label=source_label)
    return import_rows(_rows_from_csv(stripped), source_label=source_label)
