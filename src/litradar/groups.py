"""研究单元解析：全球公开库 + 本地核验补充档。

设计口径：
- 主路径不绑定任何学校：ROR 查全球注册机构/实验室，OpenAlex 补机构与下属设施，Wikidata 补中文/英文实体；
- 本地核验档只用于全球库没有收录的院系内部研究所/中心，保留 source 与 verified，不冒充全球全集；
- 组织单元按 CERIF OrgUnit 的父子层级、负责人、成员、来源与有效期建模；
- 不按姓名、论文数猜职称或负责人；找不到就留空，让申请人回官网核对；
- 搜索只负责“找到哪个研究单元”，不替用户判断某个人是谁。
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlencode

INSTITUTION = {
    "id": "lzu",
    "name": "兰州大学",
    "name_en": "Lanzhou University",
    "type": "university",
    "ror": "https://ror.org/01mkqqe32",
    "country": "中国",
}

COLLEGE = {
    "id": "lzu-caoye",
    "name": "草地农业科技学院",
    "name_en": "College of Pastoral Agriculture Science and Technology",
    "type": "college",
    "parent_id": "lzu",
    "source": "https://caoye.lzu.edu.cn/xueyuangaikuang/jigoushezhi/index.html",
}

COLLEGE_SOURCE = "https://caoye.lzu.edu.cn/xueyuangaikuang/jigoushezhi/index.html"
CENTER_SOURCE = "http://cgm.lzu.edu.cn/index.htm"
VERIFIED = "2026-11-22"
PLATFORM = "草种创新与草地农业生态系统全国重点实验室"

_COMMON = {
    "institution": "兰州大学",
    "department": "草地农业科技学院",
    "unit_ror": INSTITUTION["ror"],
    "parent_id": COLLEGE["id"],
    "platform": f"{PLATFORM}（学院共享，按课题组实际使用核对）",
    "source": COLLEGE_SOURCE,
    "source_kind": "local",
    "source_label": "本地核验档",
    "verified": VERIFIED,
}

LOCAL_GROUPS: tuple[dict[str, Any], ...] = (
    {
        **_COMMON, "id": "lzu-caoye-grassland-protection",
        "name": "草地保护研究所", "short": "草保所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草地保护所", "草地保护", "草保"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-breeding-seed",
        "name": "草类植物育种与种子研究所", "short": "育种与种子所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草类植物育种与种子所", "育种与种子所", "育种所", "草种所", "种子所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-grassland-ecology",
        "name": "草地生态研究所", "short": "生态所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草地生态所", "生态所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-rural-grassland",
        "name": "农区草业研究所", "short": "农区草业所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["农区草业所", "农区所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-element-management",
        "name": "草业系统元素利用与管理研究所", "short": "元素利用所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草业系统元素利用与管理所", "元素利用所", "元素所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-livestock-system",
        "name": "草畜生产系统调控研究所", "short": "草畜调控所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草畜生产系统调控所", "草畜调控所", "草畜所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-ruminant",
        "name": "反刍动物研究所", "short": "反刍所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["反刍动物所", "反刍所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-stress-physiology",
        "name": "草类植物逆境生理与遗传改良研究所", "short": "逆境生理所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草类植物逆境生理与遗传改良所", "逆境生理所", "逆境所", "遗传改良所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-remote-sensing-gis",
        "name": "草地遥感与地理信息系统研究所", "short": "遥感与GIS所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草地遥感与地理信息系统所", "遥感与GIS所", "遥感所", "GIS所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON, "id": "lzu-caoye-system-analysis",
        "name": "草业系统分析和社会发展研究所", "short": "系统分析所", "type": "institute",
        "type_label": "研究所",
        "aliases": ["草业系统分析和社会发展所", "草业系统分析所", "系统分析所", "社会发展所"],
        "directions": [], "leader": "", "members": [],
        "note": "学院机构设置页只列名称；方向、负责人和成员需按研究所页面或公开师资补齐。",
    },
    {
        **_COMMON,
        "id": "lzu-caoye-microbial-center",
        "name": "草地微生物研究中心", "short": "草微中心", "type": "center",
        "type_label": "研究中心",
        "aliases": ["草微中心", "草地微生物中心", "微生物中心", "草微"],
        "leader": "南志标",
        "deputy_leaders": ["苟小军", "杨云锋"],
        "chief_scientist": "周集中",
        "members": ["邓建明", "李祥锴", "张金林"],
        "directions": ["草地土壤微生物", "植物微生物", "动物微生物", "系统微生物学理论与技术"],
        "platform": f"{PLATFORM}（中心依托）",
        "platform_level": "全国重点实验室",
        "source": CENTER_SOURCE,
        "verified": VERIFIED,
        "note": "中心 2019 年成立；官网教师风采只列部分成员，完整名单需向中心确认。",
    },
)

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


def _local_score(query: str, group: dict[str, Any]) -> int:
    q = _norm(query)
    best = 0
    for term in [group.get("name", ""), group.get("short", ""), *(group.get("aliases") or [])]:
        t = _norm(term)
        if not t:
            continue
        if t == q:
            best = max(best, 100)
        elif t.startswith(q):
            best = max(best, 80)
        elif q in t:
            best = max(best, 60)
    return best


def _search_local(query: str, limit: int) -> list[dict[str, Any]]:
    q = _norm(query)
    if not q:
        return [dict(group) for group in LOCAL_GROUPS[:limit]]
    rows: list[tuple[int, dict[str, Any]]] = []
    for group in LOCAL_GROUPS:
        score = _local_score(query, group)
        if score:
            rows.append((score, group))
    rows.sort(key=lambda item: (-item[0], item[1].get("name", "")))
    out = []
    for score, group in rows[:limit]:
        row = dict(group)
        row["score"] = score
        out.append(row)
    return out


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


def search(query: str = "", limit: int = 20, remote: bool = True) -> list[dict[str, Any]]:
    """先查本地核验档，再查 ROR / OpenAlex / Wikidata 全球公开记录。

    空查询只返回本地补充档，避免把“本地 11 个”误当成全球全集；输入名称后并发查三个来源。
    """
    q = str(query or "").strip()
    if not q:
        return [dict(group) for group in LOCAL_GROUPS[:limit]]
    local = _search_local(q, limit)
    remote_rows: list[dict[str, Any]] = []
    if remote and len(_norm(q)) >= 2:
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
    rows = local + remote_rows
    rows.sort(key=lambda row: (
        -int(row.get("score") or 0),
        0 if row.get("source_kind") == "local" else 1,
        -_richness(row),
        row.get("name", ""),
    ))
    for row in rows:
        _BY_ID[row["id"]] = (time.time(), row)
    return rows[:limit]


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
    for group in LOCAL_GROUPS:
        if group["id"] == gid:
            return dict(group)
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
    """从 group_id 或 research_group 名称找到唯一研究群；找不到/不唯一都返回 None。"""
    row = identity or {}
    group = get(row.get("group_id") or "")
    if group:
        return group
    name = str(row.get("research_group") or "").strip()
    if not name:
        return None
    rows = search(name, limit=10)
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
    return [as_json(group) for group in LOCAL_GROUPS]
