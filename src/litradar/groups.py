"""研究单元检索：全球公开库（A 线）+ 国内本地库（B 线）。

两条线彼此独立：
- A 线只查 ROR v2 / OpenAlex institutions / Wikidata，空查询不返回任何本地项；
- B 线只查 ``local_store`` 里的国内本地库，不联网；
- 两边 ID 空间分开：全球 ``ror:`` / ``openalex:`` / ``wikidata:``，本地 ``cn:`` 或 ``lzu-``；
- 同名不自动合并，只有全球记录明确带 ROR 映射时才在 A 线内部合并；
- 不按姓名、论文数猜职称或负责人；负责人字段只来自官网核验档。
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlencode

from . import local_store

ROR_API = "https://api.ror.org/v2/organizations"
OPENALEX_API = "https://api.openalex.org/institutions"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
CACHE_TTL = 600
REMOTE_LIMIT = 8

_TYPE_LABEL = {
    "education": "高校/大学",
    "facility": "实验室/设施",
    "healthcare": "医院",
    "company": "企业",
    "government": "政府机构",
    "nonprofit": "非营利机构",
    "funder": "资助机构",
}

_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_BY_ID: dict[str, tuple[float, dict[str, Any]]] = {}


def _json(url: str) -> Any:
    from .net import get_json

    return get_json(url, timeout=8, retries=1)


def _norm(text: str) -> str:
    return re.sub(r"[\s\-_,，。；;：:、/\\|（）()\[\]【】.·'\"“”]+", "", str(text or "").lower())


def _score_name(query: str, names: list[str]) -> int:
    q = _norm(query)
    best = 0
    for name in names:
        n = _norm(name)
        if not q or not n:
            continue
        if q == n:
            return 100
        if (q in n or n in q) and min(len(q), len(n)) >= 4:
            best = max(best, 72)
            continue
        q_tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", q))
        n_tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", n))
        common = q_tokens & n_tokens
        if common:
            best = max(best, int(20 + 40 * len(common) / len(q_tokens | n_tokens)))
    return best


def _parents(item: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for rel in item.get("relationships") or []:
        if str(rel.get("type") or "") == "parent" and rel.get("label"):
            rows.append({"label": str(rel.get("label") or ""), "id": str(rel.get("id") or "")})
    return rows


def _ror_names(item: dict[str, Any]) -> tuple[str, str, list[str]]:
    display, zh, aliases = "", "", []
    for row in item.get("names") or []:
        value = str(row.get("value") or "").strip()
        types = row.get("types") or []
        if not value:
            continue
        if "ror_display" in types:
            display = value
        if row.get("lang") == "zh" and not zh:
            zh = value
        if "alias" in types and value not in aliases:
            aliases.append(value)
    if not display:
        display = next((str(r.get("value") or "") for r in (item.get("names") or []) if r.get("value")), "")
    return display, zh, aliases


def _country(item: dict[str, Any]) -> tuple[str, str]:
    for loc in item.get("locations") or []:
        geo = loc.get("geonames_details") or {}
        code = str(geo.get("country_code") or "").upper()
        name = str(geo.get("country_name") or "")
        if code or name:
            return code, name
    return "", ""


def _website(item: dict[str, Any]) -> str:
    for link in item.get("links") or []:
        if str(link.get("type") or "") == "website" and link.get("value"):
            return str(link["value"])
    return ""


def _normalize_ror(item: dict[str, Any]) -> dict[str, Any] | None:
    ror_url = str(item.get("id") or "").strip()
    if not ror_url:
        return None
    display, zh, aliases = _ror_names(item)
    if not display and not zh:
        return None
    parents = _parents(item)
    parent = parents[0] if parents else {}
    type_code = str((item.get("types") or [""])[0] or "")
    type_label = _TYPE_LABEL.get(type_code, type_code or "研究单元")
    country_code, country_name = _country(item)
    source = _website(item) or ror_url
    note = "ROR 公开机构记录；ROR 只收独立注册的机构/实验室，大学内部院系、研究组可能未收录。"
    if parent.get("label"):
        note = f"ROR 公开机构记录，上级单位：{parent['label']}；ROR 不保证收录该上级单位内部的全部研究组。"
    return {
        "id": "ror:" + ror_url.rsplit("/", 1)[-1],
        "line": "global",
        "source_kind": "ror",
        "source_label": "ROR",
        "source": source,
        "verified": "",
        "name": display or zh,
        "name_zh": zh,
        "short": ((item.get("acronyms") or [""])[0] or ""),
        "aliases": aliases[:8],
        "type": type_code or "research_unit",
        "type_label": type_label,
        "unit": parent.get("label") or display or zh,
        "institution": parent.get("label") or display or zh,
        "department": (display or zh) if parent.get("label") else "",
        "unit_ror": parent.get("id") or ror_url,
        "parent_id": parent.get("id") or "",
        "parent_name": parent.get("label") or "",
        "leader": "",
        "deputy_leaders": [],
        "chief_scientist": "",
        "members": [],
        "directions": [],
        "platform": "",
        "platform_level": "",
        "country": country_code,
        "country_name": country_name,
        "note": note,
        "ids": {"ror": ror_url},
    }


def _normalize_openalex(item: dict[str, Any]) -> dict[str, Any] | None:
    url = str(item.get("id") or "").strip()
    name = str(item.get("display_name") or "").strip()
    if not url or not name:
        return None
    lineage = [str(x) for x in (item.get("lineage") or []) if x]
    parent_id = lineage[-2] if len(lineage) > 1 else ""
    parents = [
        p for p in (item.get("associated_institutions") or [])
        if str(p.get("relationship") or "").lower() == "parent" and p.get("display_name")
    ]
    parent = parents[0] if parents else {}
    type_code = str(item.get("type") or "")
    country_code = str(item.get("country_code") or "").upper()
    aliases = [str(x) for x in (item.get("display_name_alternatives") or []) if x]
    aliases += [str(x) for x in (item.get("display_name_acronyms") or []) if x]
    unit = str(parent.get("display_name") or "")
    return {
        "id": "openalex:" + url.rsplit("/", 1)[-1],
        "line": "global",
        "source_kind": "openalex",
        "source_label": "OpenAlex",
        "source": str(item.get("homepage_url") or url),
        "verified": "",
        "name": name,
        "name_zh": "",
        "short": ((item.get("display_name_acronyms") or [""])[0] or ""),
        "aliases": aliases[:8],
        "type": type_code or "research_unit",
        "type_label": _TYPE_LABEL.get(type_code, type_code or "研究单元"),
        "unit": unit or (name if not parent_id else ""),
        "institution": unit or (name if not parent_id else ""),
        "department": "",
        "unit_ror": str(parent.get("ror") or (item.get("ror") if not parent_id else "") or ""),
        "parent_id": str(parent.get("id") or parent_id or ""),
        "parent_name": unit,
        "leader": "",
        "deputy_leaders": [],
        "chief_scientist": "",
        "members": [],
        "directions": [],
        "platform": "",
        "platform_level": "",
        "country": country_code,
        "country_name": "",
        "note": "OpenAlex 公开机构记录；院系、内部研究组是否收录取决于数据源。",
        "image": str(item.get("image_thumbnail_url") or item.get("image_url") or ""),
        "ids": {"openalex": url, "ror": str(item.get("ror") or "")},
    }


def _normalize_wikidata(item: dict[str, Any], language: str = "") -> dict[str, Any] | None:
    qid = str(item.get("id") or "").strip()
    name = str(item.get("label") or "").strip()
    if not qid or not name:
        return None
    desc = str(item.get("description") or "").strip()
    return {
        "id": "wikidata:" + qid,
        "line": "global",
        "source_kind": "wikidata",
        "source_label": "Wikidata",
        "source": str(item.get("concepturi") or item.get("url") or f"https://www.wikidata.org/wiki/{qid}"),
        "verified": "",
        "name": name,
        "name_zh": name if language == "zh" else "",
        "short": "",
        "aliases": [],
        "type": "research_unit",
        "type_label": desc or "研究单元",
        "unit": "",
        "institution": "",
        "department": "",
        "unit_ror": "",
        "parent_id": "",
        "parent_name": "",
        "leader": "",
        "deputy_leaders": [],
        "chief_scientist": "",
        "members": [],
        "directions": [],
        "platform": "",
        "platform_level": "",
        "country": "",
        "country_name": "",
        "note": "Wikidata 公开实体；完整性与字段取决于社区标注，需回官网核对。",
        "ids": {"wikidata": f"https://www.wikidata.org/entity/{qid}"},
    }


def _search_ror(query: str, limit: int = REMOTE_LIMIT) -> list[dict[str, Any]]:
    data = _json(f"{ROR_API}?{urlencode({'query': query})}")
    rows = []
    for item in (data.get("items") or [])[:20]:
        group = _normalize_ror(item)
        if not group:
            continue
        names = [group.get("name", ""), group.get("name_zh", ""), *(group.get("aliases") or [])]
        score = _score_name(query, names)
        if score <= 0:
            continue
        group["score"] = score
        rows.append(group)
    rows.sort(key=lambda row: (-row["score"], row["name"]))
    return rows[:limit]


def _search_openalex(query: str, limit: int = REMOTE_LIMIT) -> list[dict[str, Any]]:
    params = {"search": query, "per-page": 10, "mailto": "litradar@example.com"}
    data = _json(f"{OPENALEX_API}?{urlencode(params)}")
    rows = []
    for item in (data.get("results") or [])[:10]:
        group = _normalize_openalex(item)
        if not group:
            continue
        names = [group.get("name", ""), *(group.get("aliases") or [])]
        score = _score_name(query, names)
        if score <= 0:
            continue
        group["score"] = score
        rows.append(group)
    rows.sort(key=lambda row: (-row["score"], row["name"]))
    return rows[:limit]


def _search_wikidata(query: str, limit: int = 5) -> list[dict[str, Any]]:
    language = "zh" if re.search(r"[\u4e00-\u9fff]", query) else "en"
    params = {
        "action": "wbsearchentities", "search": query, "language": language,
        "uselang": language, "format": "json", "limit": 10,
    }
    data = _json(f"{WIKIDATA_API}?{urlencode(params)}")
    rows = []
    for item in (data.get("search") or []):
        text = f"{item.get('label', '')} {item.get('description', '')}"
        if language == "zh":
            if not any(k in text for k in ("研究所", "研究院", "实验室", "中心", "大学", "学院", "系", "科研", "研究")):
                continue
        else:
            if not re.search(r"institut|laborator|research|centre|center|universit|college|department|faculty|school", text, re.I):
                continue
            if re.search(r"high school|primary school|middle school|kindergarten", text, re.I):
                continue
        group = _normalize_wikidata(item, language)
        if not group:
            continue
        score = _score_name(query, [group["name"], item.get("match", "")])
        if score <= 0:
            continue
        group["score"] = score
        rows.append(group)
    rows.sort(key=lambda row: (-row["score"], row["name"]))
    return rows[:limit]


def _remember(rows: list[dict[str, Any]]) -> None:
    now = time.time()
    for row in rows:
        _BY_ID[row["id"]] = (now, row)


def _merge_global(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda x: -int(x.get("score") or 0)):
        ror = (row.get("ids") or {}).get("ror") or ""
        key = "ror:" + ror if ror else "name:" + _norm(row.get("name", "")) + "|" + str(row.get("country") or "")
        old = out.get(key)
        if not old:
            out[key] = row
            continue
        for field in ("name_zh", "short", "leader", "platform", "platform_level", "image",
                      "unit", "institution", "department", "unit_ror", "parent_name",
                      "country", "country_name"):
            if not old.get(field) and row.get(field):
                old[field] = row[field]
        for field in ("aliases", "members", "directions"):
            if not old.get(field) and row.get(field):
                old[field] = row[field]
        ids = old.setdefault("ids", {})
        for k, v in (row.get("ids") or {}).items():
            if not ids.get(k) and v:
                ids[k] = v
        if row.get("source_kind") and row["source_kind"] != old.get("source_kind"):
            labels = set()
            for label in (old.get("source_label", ""), row.get("source_label", "")):
                labels.update(x.strip() for x in str(label).split(" + ") if x.strip())
            ordered = [x for x in ("ROR", "OpenAlex", "Wikidata") if x in labels]
            ordered += sorted(x for x in labels if x and x not in ordered)
            old["source_label"] = " + ".join(ordered)
    return list(out.values())


def _cache_get(key: str) -> list[dict[str, Any]] | None:
    row = _CACHE.get(key)
    if not row:
        return None
    stamp, value = row
    if time.time() - stamp > CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return [dict(x) for x in value]


def _cache_put(key: str, rows: list[dict[str, Any]]) -> None:
    _CACHE[key] = (time.time(), [dict(x) for x in rows])


def _richness(row: dict[str, Any]) -> int:
    """同等匹配下，优先展示带上级单位、国家和官网的记录，减少空壳档案。"""
    name = _norm(row.get("name", ""))
    unit = str(row.get("unit") or row.get("institution") or "")
    return sum((
        bool(unit and _norm(unit) != name),
        bool(row.get("parent_name")),
        bool(row.get("country")),
        bool(row.get("source")),
        bool(row.get("image")),
    ))


def search_global(query: str = "", limit: int = 20, remote: bool = True) -> list[dict[str, Any]]:
    """A 线：只查 ROR / OpenAlex / Wikidata；空查询返回空列表。"""
    q = str(query or "").strip()
    if not q or len(_norm(q)) < 2:
        return []
    remote_rows: list[dict[str, Any]] = []
    if remote:
        key = "q:" + _norm(q)
        cached = _cache_get(key)
        if cached is None:
            tasks = (("ror", _search_ror), ("openalex", _search_openalex), ("wikidata", _search_wikidata))
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(func, q): name for name, func in tasks}
                for future in as_completed(futures):
                    try:
                        remote_rows.extend(future.result() or [])
                    except Exception:  # noqa: BLE001 - 单个全球源失败不阻断其它来源
                        continue
            remote_rows = _merge_global(remote_rows)
            _remember(remote_rows)
            _cache_put(key, remote_rows)
        else:
            remote_rows = cached
    rows = remote_rows
    rows.sort(key=lambda row: (-int(row.get("score") or 0), -_richness(row), row.get("name", "")))
    for row in rows:
        _BY_ID[row["id"]] = (time.time(), row)
    return rows[:limit]


def search_local(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """B 线：只查国内本地库；空查询返回空列表，不硬塞任何学校目录。"""
    return local_store.search(query, limit=limit)


def search(query: str = "", limit: int = 20, remote: bool = True, line: str = "global") -> list[dict[str, Any]]:
    """兼容入口：``line="local"`` 走 B 线，其余走 A 线。绝不把两条线混成一个列表。"""
    if str(line).lower() == "local":
        return search_local(query, limit=limit)
    return search_global(query, limit=limit, remote=remote)


def _get_ror(slug: str) -> dict[str, Any] | None:
    data = _json(f"{ROR_API}/{slug}")
    return _normalize_ror(data)


def _get_openalex(slug: str) -> dict[str, Any] | None:
    data = _json(f"{OPENALEX_API}/{slug}")
    return _normalize_openalex(data)


def _get_wikidata(qid: str) -> dict[str, Any] | None:
    params = {
        "action": "wbgetentities", "ids": qid, "props": "labels|descriptions|sitelinks",
        "languages": "zh|en", "format": "json",
    }
    data = _json(f"{WIKIDATA_API}?{urlencode(params)}")
    item = (data.get("entities") or {}).get(qid)
    if not item:
        return None
    labels = item.get("labels") or {}
    descriptions = item.get("descriptions") or {}
    label = str((labels.get("zh") or {}).get("value") or (labels.get("en") or {}).get("value") or "")
    desc = str((descriptions.get("zh") or {}).get("value") or (descriptions.get("en") or {}).get("value") or "")
    return _normalize_wikidata({"id": qid, "label": label, "description": desc,
                                "concepturi": f"https://www.wikidata.org/entity/{qid}"}, "zh" if labels.get("zh") else "en")


def get(group_id: str) -> dict[str, Any] | None:
    gid = str(group_id or "").strip()
    if not gid:
        return None
    local = local_store.get(gid)
    if local:
        return local
    cached = _BY_ID.get(gid)
    if cached and time.time() - cached[0] <= CACHE_TTL:
        return dict(cached[1])
    try:
        if gid.startswith("ror:"):
            group = _get_ror(gid[4:])
        elif gid.startswith("openalex:"):
            group = _get_openalex(gid[9:])
        elif gid.startswith("wikidata:"):
            group = _get_wikidata(gid[9:])
        else:
            group = None
    except Exception:  # noqa: BLE001 - 详情失败时返回 None，由界面保留已填字段
        group = None
    if group:
        _BY_ID[gid] = (time.time(), group)
    return group


def resolve(identity: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """从 group_id 或 research_group 名称找到唯一研究群；找不到/不唯一都返回 None。

    先本地精确解析，避免为了一个校内研究所去打三个全球接口；本地没有才查 A 线。
    """
    row = identity or {}
    group = get(row.get("group_id") or "")
    if group:
        return group
    name = str(row.get("research_group") or "").strip()
    if not name:
        return None
    local = local_store.resolve(name)
    if local:
        return local
    rows = search_global(name, limit=10)
    exact = [g for g in rows if g.get("name") == name or g.get("short") == name or g.get("name_zh") == name]
    return exact[0] if len(exact) == 1 else None


def _leader_text(group: dict[str, Any]) -> str:
    parts: list[str] = []
    if group.get("leader"):
        parts.append(f"{group['leader']}（主任）" if group.get("type") == "center" else group["leader"])
    if group.get("deputy_leaders"):
        parts.append("、".join(group["deputy_leaders"]) + "（副主任）")
    if group.get("chief_scientist"):
        parts.append(f"{group['chief_scientist']}（首席科学家）")
    return "；".join(parts)


def _department_field(group: dict[str, Any]) -> str:
    """院系字段不能和研究单元同名，否则全球机构会出现两行重复。"""
    dept = str(group.get("department") or "").strip()
    if not dept:
        return ""
    names = {_norm(group.get("name", "")), _norm(group.get("name_zh", ""))}
    return "" if _norm(dept) in names else dept


def identity_patch(group: dict[str, Any]) -> dict[str, str]:
    """把研究群档案映射到课题组表单；只放可核对字段，不猜负责人或职称。"""
    patch = {
        "unit": group.get("unit") or group.get("institution") or group["name"],
        "department": _department_field(group),
        "unit_ror": group.get("unit_ror") or "",
        "unit_official": group.get("unit") or group.get("institution") or group["name"],
        "research_group": group["name"],
        "group_id": group["id"],
        "group_short": group.get("short", ""),
        "group_type": group.get("type_label", ""),
        "group_leader": _leader_text(group),
        "group_directions": "；".join(group.get("directions") or []),
        "group_platform": group.get("platform", ""),
        "group_source": group.get("source", ""),
        "group_verified": group.get("verified", ""),
    }
    if group.get("platform_level"):
        patch["org"] = group["platform_level"]
    return patch


def evidence(group: dict[str, Any]) -> dict[str, Any]:
    """只给结构化证据：档案来自哪里、有什么，不用论文数反推职称。"""
    dirs = group.get("directions") or []
    members = group.get("members") or []
    source_label = group.get("source_label") or group.get("source_kind") or ""
    verified = group.get("verified") or ""
    note = f"研究群档案已带入：{group['name']}；来源 {source_label or '未标注'} {group.get('source', '')}"
    note += f"；核验 {verified}" if verified else "；公开记录未做本地核验"
    return {
        "group_id": group["id"],
        "group_name": group["name"],
        "group_type": group.get("type_label", ""),
        "source_kind": group.get("source_kind", ""),
        "source_label": source_label,
        "has_leader": bool(group.get("leader")),
        "direction_count": len(dirs),
        "known_member_count": len(members),
        "platform_level": group.get("platform_level", ""),
        "source": group.get("source", ""),
        "verified": verified,
        "note": note,
    }


def as_json(group: dict[str, Any]) -> dict[str, Any]:
    """给前端的紧凑记录，保留来源与目录字段，不塞推断值。"""
    return {
        "id": group["id"],
        "line": group.get("line", "global"),
        "source_kind": group.get("source_kind", "local"),
        "source_label": group.get("source_label", "本地核验档"),
        "name": group["name"],
        "name_zh": group.get("name_zh", ""),
        "short": group.get("short", ""),
        "type": group.get("type", ""),
        "type_label": group.get("type_label", ""),
        "unit": group.get("unit") or group.get("institution", ""),
        "department": _department_field(group),
        "unit_ror": group.get("unit_ror", ""),
        "country": group.get("country", ""),
        "country_name": group.get("country_name", ""),
        "region": group.get("region", ""),
        "province": group.get("province", "") or group.get("region", ""),
        "school_code": group.get("school_code", ""),
        "authority": group.get("authority", ""),
        "level": group.get("level", ""),
        "leader": _leader_text(group),
        "members": group.get("members") or [],
        "directions": group.get("directions") or [],
        "platform": group.get("platform", ""),
        "platform_level": group.get("platform_level", ""),
        "source": group.get("source", ""),
        "verified": group.get("verified", ""),
        "note": group.get("note", ""),
        "parent_id": group.get("parent_id", ""),
        "parent_name": group.get("parent_name", ""),
        "image": group.get("image", ""),
    }


def all_groups() -> list[dict[str, Any]]:
    """兼容旧调用：只返回本地库，不再假装是全球全集。"""
    return [as_json(group) for group in local_store.all_units()]
