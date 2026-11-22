"""身份与单位核对：用公开学术元数据把“人—单位—院系—通讯作者”对上。

设计边界：
- 单位用 ROR（Research Organization Registry）规范化，返回 ROR ID、官方名称、别名；
- 院系没有全球统一库，只能从作者论文中的 raw affiliation 提取候选，保留原文；
- 通讯作者用 OpenAlex 的 `is_corresponding` 标记和作者作品列表给候选，
  最终仍由用户确认，不按姓名猜人；
- DOI 用 Crossref/OpenAlex 回查题录、作者位次与通讯标记；
- 不抓知网，不模拟登录，不把公开元数据里的联系方式另作他用。

这个模块只产出“候选 + 证据 + 置信度”，不替用户决定通讯作者，也不把检索排名
当成学术水平。负责人评价仍走 `team.py` 的 DORA 口径。
"""
from __future__ import annotations

import math
import re
import time
import urllib.parse
from typing import Any

from . import credentials
from .net import get_json

ROR_API = "https://api.ror.org/v2/organizations"
OPENALEX_API = "https://api.openalex.org"
CROSSREF_API = "https://api.crossref.org/works/"
CACHE_TTL = 3600
_CACHE: dict[str, tuple[float, Any]] = {}

_PUNCT = re.compile(r"[\s\-_,，。；;：:、/\\|（）()\[\]【】.·'\"“”]+")
_ZH_ORG = re.compile(
    r"([\u4e00-\u9fffA-Za-z0-9（）()·\-]{2,40}?"
    r"(?:大学|学院|研究院|研究所|中心|医院|学校|实验室))"
)
_EN_ORG = re.compile(
    r"([A-Z][A-Za-z&.\- ]{2,70}?"
    r"(?:University|Institute|College|Academy|Hospital|School|Center|Centre|Laboratory))",
    re.I,
)
_DEPT = re.compile(
    r"(学院|学系|系|研究所|研究院|研究中心|重点实验室|实验室|中心|"
    r"College|School|Department|Faculty|Institute|Laboratory|Lab|Center|Centre|Division)",
    re.I,
)
_COUNTRY = {
    "CN": "中国", "US": "美国", "GB": "英国", "DE": "德国", "FR": "法国",
    "JP": "日本", "KR": "韩国", "AU": "澳大利亚", "CA": "加拿大", "NL": "荷兰",
}


def _norm(text: str) -> str:
    return _PUNCT.sub("", str(text or "").lower())


def _cache_get(key: str) -> Any:
    item = _CACHE.get(key)
    if not item:
        return None
    at, value = item
    if time.time() - at > CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_put(key: str, value: Any) -> Any:
    _CACHE[key] = (time.time(), value)
    return value


def _json(url: str) -> Any:
    cached = _cache_get(url)
    if cached is not None:
        return cached
    value = get_json(url, timeout=30, retries=2)
    return _cache_put(url, value)


def _openalex_url(path: str, params: dict) -> str:
    params = {k: v for k, v in params.items() if v not in (None, "")}
    cred = credentials.active("openalex") or {}
    if cred.get("email"):
        params.setdefault("mailto", cred["email"])
    return f"{OPENALEX_API}{path}?" + urllib.parse.urlencode(params)


def _ror_display(item: dict) -> tuple[str, str, list[str]]:
    names = item.get("names") or []
    display, zh, aliases = "", "", []
    for row in names:
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
        display = next((str(r.get("value") or "") for r in names if r.get("value")), "")
    return display, zh, aliases


def _ror_country(item: dict) -> tuple[str, str]:
    for loc in item.get("locations") or []:
        geo = loc.get("geonames_details") or {}
        code = str(geo.get("country_code") or "").upper()
        name = str(geo.get("country_name") or "")
        if code or name:
            return code, name
    return "", ""


def _ror_queries(query: str) -> list[str]:
    query = re.sub(r"\s+", " ", str(query or "")).strip(" ,，;；")
    if not query:
        return []
    out = [query]
    for part in re.split(r"\s*[,，;；/]\s*", query):
        part = part.strip()
        if len(part) >= 3 and part not in out:
            out.append(part)
    zh = [m.group(1).strip() for m in _ZH_ORG.finditer(query)]
    en = [m.group(1).strip() for m in _EN_ORG.finditer(query)]
    for value in zh + en:
        if 3 <= len(value) <= 80 and value not in out:
            out.append(value)
    return out[:5]


def _name_variants(name: str) -> list[str]:
    """中文姓名转常见英文署名顺序，补 OpenAlex 对中文名的召回。

    OpenAlex 的 display_name 多数是英文/拼音；中文姓名直接搜经常为空。
    这里只在本地做拼音转换，不把姓名发给第三方翻译服务。
    """
    name = str(name or "").strip()
    if not name or not re.search(r"[\u4e00-\u9fff]", name):
        return []
    try:
        from pypinyin import Style, lazy_pinyin  # type: ignore
        parts = [p for p in lazy_pinyin(name, style=Style.NORMAL) if p]
    except Exception:  # noqa: BLE001 - 未装拼音库时保持原检索
        return []
    if len(parts) < 2:
        return []
    surname, given = parts[0], parts[1:]
    rows = [" ".join([*given, surname]), " ".join([surname, *given])]
    out = []
    for row in rows:
        row = " ".join(word.capitalize() for word in row.split())
        if row.lower() != name.lower() and row not in out:
            out.append(row)
    return out


def _score_name(query: str, names: list[str]) -> int:
    q = _norm(query)
    best = 0
    for name in names:
        n = _norm(name)
        if not q or not n:
            continue
        if q == n:
            return 100
        if q in n or n in q:
            best = max(best, 72)
            continue
        q_tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", q))
        n_tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", n))
        if q_tokens and n_tokens:
            best = max(best, int(20 + 40 * len(q_tokens & n_tokens) / len(q_tokens | n_tokens)))
    return best


def ror_search(query: str, limit: int = 8) -> list[dict]:
    """按机构名/别名查 ROR；返回候选，不替用户选定。"""
    queries = _ror_queries(query)
    rows: dict[str, dict] = {}
    for q in queries:
        params = {"query": f'"{q}"'}
        url = ROR_API + "?" + urllib.parse.urlencode(params)
        try:
            data = _json(url)
        except Exception:  # noqa: BLE001 - 单个查询失败不阻断后续候选
            continue
        for item in (data.get("items") or [])[:20]:
            ror = str(item.get("id") or "")
            if not ror:
                continue
            display, zh, aliases = _ror_display(item)
            if not display and not zh:
                continue
            names = [x for x in [display, zh, *aliases] if x]
            country_code, country_name = _ror_country(item)
            score = _score_name(q, names)
            if _norm(q) and _norm(q) == _norm(display):
                score = max(score, 100)
            if score <= 0:
                continue
            if country_code == "CN" and re.search(r"[\u4e00-\u9fff]", q):
                score += 4
            old = rows.get(ror)
            if old and old["score"] >= score:
                continue
            links = item.get("links") or []
            website = next((x.get("value") for x in links if x.get("type") == "website"), "")
            parents = [x.get("label") for x in (item.get("relationships") or [])
                       if x.get("type") == "parent" and x.get("label")]
            children = [x.get("label") for x in (item.get("relationships") or [])
                        if x.get("type") == "child" and x.get("label")]
            rows[ror] = {
                "id": ror, "ror": ror.rsplit("/", 1)[-1],
                "name": display or zh, "name_zh": zh, "aliases": aliases[:8],
                "country": country_code, "country_name": _COUNTRY.get(country_code, country_name),
                "type": (item.get("types") or [""])[0], "website": website,
                "domains": (item.get("domains") or [])[:5],
                "parent": parents[:3], "children": children[:6],
                "score": min(100, score), "matched": q,
            }
    out = sorted(rows.values(), key=lambda x: (-x["score"], x["name"]))
    return out[:limit]


def _institutions(item: dict, limit: int = 6, prefer_ror: str = "") -> list[dict]:
    rows = []
    for aff in item.get("affiliations") or []:
        inst = aff.get("institution") or {}
        name = str(inst.get("display_name") or "")
        if not name:
            continue
        rows.append({"name": name, "ror": str(inst.get("ror") or ""),
                     "country": str(inst.get("country_code") or ""),
                     "years": [int(y) for y in (aff.get("years") or []) if str(y).isdigit()]})
    for inst in item.get("last_known_institutions") or []:
        name = str(inst.get("display_name") or "")
        if name and not any(r["name"] == name for r in rows):
            rows.append({"name": name, "ror": str(inst.get("ror") or ""),
                         "country": str(inst.get("country_code") or ""), "years": []})
    if prefer_ror:
        rows.sort(key=lambda r: 0 if r.get("ror") == prefer_ror else 1)
    return rows[:limit]


def _ror_match(insts: list[dict], ror: str) -> bool:
    if not ror:
        return True
    recent = time.gmtime().tm_year - 5
    for row in insts:
        if str(row.get("ror") or "") != ror:
            continue
        years = row.get("years") or []
        if not years or max(years) >= recent:
            return True
    return False


def _author_score(name: str, item: dict, institutions: list[dict], ror: str, orcid: str) -> int:
    raw_names = [str(x) for x in (item.get("raw_author_names") or [])]
    display = str(item.get("display_name") or "")
    score = _score_name(name, [display, *raw_names])
    if score >= 100:
        score = 55
    if ror and any(str(x.get("ror") or "") == ror for x in institutions):
        score += 30
    if orcid and str(item.get("orcid") or "").rstrip("/").endswith(orcid):
        score += 20
    works = int(item.get("works_count") or 0)
    if works:
        score += min(8, int(math.log10(max(works, 1)) * 3))
    return score


def author_search(name: str, ror: str = "", orcid: str = "", limit: int = 8) -> list[dict]:
    """按姓名（可加 ROR/ORCID）查 OpenAlex 作者候选。"""
    name = str(name or "").strip()
    if not name and not orcid:
        return []
    params = {"search": name, "per-page": 25}
    filters = []
    if ror:
        filters.append(f"last_known_institutions.ror:{ror}")
    if orcid:
        filters.append(f"orcid:{orcid if orcid.startswith('http') else 'https://orcid.org/' + orcid}")
    if filters:
        params["filter"] = ",".join(filters)
    try:
        data = _json(_openalex_url("/authors", params))
        results = data.get("results") or []
    except Exception:  # noqa: BLE001
        results = []
    if ror and len(results) < 2:
        params.pop("filter", None)
        try:
            fallback = _json(_openalex_url("/authors", params))
            results = fallback.get("results") or []
        except Exception:  # noqa: BLE001
            pass
    rows = []
    for item in results:
        display = str(item.get("display_name") or "")
        if not display:
            continue
        insts = _institutions(item, prefer_ror=ror)
        if ror and not _ror_match(insts, ror):
            continue
        score = _author_score(name or orcid, item, insts, ror, orcid)
        if score < 25:
            continue
        rows.append({
            "id": str(item.get("id") or "").rsplit("/", 1)[-1],
            "openalex": str(item.get("id") or ""),
            "name": display,
            "orcid": str(item.get("orcid") or "").rsplit("/", 1)[-1],
            "works_count": int(item.get("works_count") or 0),
            "institutions": insts,
            "score": min(100, score),
            "confidence": "高" if score >= 88 else ("中" if score >= 60 else "低"),
        })
    rows.sort(key=lambda x: (-x["score"], -x["works_count"]))
    return rows[:limit]


def _affiliation_parts(raw: list[str]) -> list[str]:
    parts = []
    for text in raw:
        for part in re.split(r"\s*[,，;；]\s*", str(text or "")):
            part = re.sub(r"\s+", " ", part).strip(" .;；,，")
            if 3 <= len(part) <= 80:
                parts.append(part)
    return parts


def _department_candidates(rows: list[dict], institution_names: list[str]) -> list[dict]:
    counts: dict[str, dict] = {}
    for row in rows:
        for part in _affiliation_parts(row.get("affiliations") or []):
            for inst_name in institution_names:
                if inst_name:
                    part = re.sub(re.escape(inst_name), "", part, flags=re.I).strip(" ,，;；")
            if not _DEPT.search(part):
                continue
            key = _norm(part)
            item = counts.setdefault(key, {"value": part, "count": 0, "last_year": 0})
            item["count"] += 1
            item["last_year"] = max(item["last_year"], int(row.get("year") or 0))
    return sorted(counts.values(), key=lambda x: (-x["count"], -x["last_year"]))[:6]


def _research_work(row: dict) -> bool:
    """判断一条 OpenAlex 记录是不是可当代表作的 research item。"""
    kind = str(row.get("type") or "").lower()
    title = str(row.get("title") or "").strip().lower()
    if kind in {"erratum", "editorial", "paratext", "letter", "dataset", "peer-review"}:
        return False
    if title.startswith(("erratum", "correction", "retraction", "editorial")):
        return False
    return True


def author_works(author_id: str, name: str = "", unit: str = "", ror: str = "",
                 limit: int = 10) -> dict:
    """取作者近作，返回通讯标记、作者位次、院系写法与代表作候选。"""
    aid = re.sub(r"[^A-Za-z0-9]", "", str(author_id or "").rsplit("/", 1)[-1])
    if not aid:
        return {"works": [], "total": 0, "departments": [], "platform_hint": "",
                "representative_suggestion": ""}
    params = {
        "filter": f"author.id:{aid}", "per-page": min(limit, 25),
        "sort": "publication_year:desc",
        "select": "id,doi,title,publication_year,type,primary_location,authorships",
    }
    try:
        data = _json(_openalex_url("/works", params))
    except Exception:  # noqa: BLE001
        data = {}
    total = int((data.get("meta") or {}).get("count") or 0)
    rows = []
    for item in (data.get("results") or [])[:limit]:
        authorships = item.get("authorships") or []
        mine = next((a for a in authorships
                     if str((a.get("author") or {}).get("id") or "").endswith(aid)), None)
        if not mine:
            continue
        venue = (((item.get("primary_location") or {}).get("source") or {})
                 .get("display_name") or "")
        rows.append({
            "id": str(item.get("id") or "").rsplit("/", 1)[-1],
            "doi": str(item.get("doi") or "").replace("https://doi.org/", ""),
            "title": str(item.get("title") or ""),
            "year": int(item.get("publication_year") or 0),
            "type": str(item.get("type") or ""),
            "journal": str(venue),
            "position": str(mine.get("author_position") or ""),
            "is_corresponding": bool(mine.get("is_corresponding")),
            "affiliations": [str(x) for x in (mine.get("raw_affiliation_strings") or [])],
        })
    names = [unit] if unit else []
    departments = _department_candidates(rows, [name, *names])
    research = [row for row in rows if _research_work(row)]
    corresponding = [row for row in research if row["is_corresponding"]]
    base = corresponding[0] if corresponding else (research[0] if research else None)
    representative = ""
    if base:
        pos = {"first": "第一作者", "last": "末位作者", "middle": "中间作者"}.get(base["position"], "")
        rep = "通讯作者" if base["is_corresponding"] else pos
        representative = f"{base['year']} 年《{base['title'][:80]}》" if base["title"] else ""
        if base["doi"]:
            representative += f"，DOI: {base['doi']}"
        representative += f"；作者位次：{rep or '待核'}；个人贡献待申请人补充"
    return {"works": rows, "total": total, "departments": departments,
            "platform_hint": _platform_hint(rows, name),
            "representative_suggestion": representative}


def _platform_hint(rows: list[dict], unit: str) -> str:
    text = " ".join([unit, *[x for r in rows for x in (r.get("affiliations") or [])]])
    if re.search(r"全国重点实验室|National Key Laboratory", text, re.I):
        return "全国重点实验室"
    if re.search(r"State Key Laboratory|国家重点实验室|国家级重点实验室", text, re.I):
        return "国家级平台/重点实验室"
    if re.search(r"省部级重点实验室|省重点实验室|Provincial Key Laboratory", text, re.I):
        return "省部级重点实验室/平台"
    return ""


def _crossref_authors(item: dict) -> list[dict]:
    rows = []
    for a in item.get("author") or []:
        name = " ".join(x for x in [a.get("given"), a.get("family")] if x).strip()
        if not name:
            name = str(a.get("name") or "")
        rows.append({
            "name": name,
            "orcid": str(a.get("ORCID") or "").rsplit("/", 1)[-1],
            "sequence": str(a.get("sequence") or ""),
            "affiliation": [str(x.get("name") or "") for x in (a.get("affiliation") or [])
                            if x.get("name")],
        })
    return rows


def _crossref_year(item: dict) -> int:
    for key in ("published-print", "published-online", "issued"):
        parts = ((item.get(key) or {}).get("date-parts") or [[None]])[0]
        if parts and str(parts[0]).isdigit():
            return int(parts[0])
    return 0


def _doi_work(doi: str) -> dict:
    bare = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    url = OPENALEX_API + "/works/https://doi.org/" + urllib.parse.quote(bare, safe="/")
    try:
        return _json(url)
    except Exception:  # noqa: BLE001
        return {}


def doi_check(doi: str, name: str = "", unit: str = "", ror: str = "") -> dict:
    """DOI 回查：题录、作者位次、通讯标记、姓名/单位一致性。"""
    bare = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    if not bare:
        return {"ok": False, "error": "缺少 DOI"}
    try:
        data = _json(CROSSREF_API + urllib.parse.quote(bare, safe="/"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Crossref 查不到该 DOI：{exc}"}
    item = data.get("message") or {}
    if not item:
        return {"ok": False, "error": "Crossref 返回为空"}
    title = " ".join(item.get("title") or [])
    authors = _crossref_authors(item)
    oa = _doi_work(bare)
    corresponding = [str(a.get("raw_author_name") or (a.get("author") or {}).get("display_name") or "")
                     for a in (oa.get("authorships") or []) if a.get("is_corresponding")]
    ror_match = bool(ror) and any(
        str((inst or {}).get("ror") or "") == ror
        for a in (oa.get("authorships") or [])
        for inst in (a.get("institutions") or [])
    )
    name_match = bool(name) and any(
        _norm(name) == _norm(a["name"]) or _norm(name) in _norm(a["name"])
        or _norm(a["name"]) and _norm(a["name"]) in _norm(name)
        for a in authors
    )
    raw_aff = " ".join(x for a in authors for x in a["affiliation"])
    unit_match = ror_match or (bool(unit) and _norm(unit) and _norm(unit) in _norm(raw_aff))
    checks = [
        {"key": "doi", "label": "DOI 可解析", "ok": True},
        {"key": "name", "label": "姓名出现在作者列表", "ok": name_match},
        {"key": "affiliation", "label": "单位与论文署名一致", "ok": unit_match},
        {"key": "corresponding", "label": "OpenAlex 标为通讯作者", "ok": bool(corresponding)},
    ]
    score = sum(1 for c in checks if c["ok"])
    return {
        "ok": True, "doi": bare, "title": title,
        "year": _crossref_year(item), "journal": " ".join(item.get("container-title") or []),
        "authors": authors[:12], "corresponding": corresponding[:6],
        "checks": checks, "confidence": "高" if score >= 4 else ("中" if score >= 2 else "低"),
        "source": "Crossref + OpenAlex",
    }


def lookup(action: str, payload: dict) -> dict:
    """统一入口：search 返回单位/作者候选，works 返回近作，doi 做 DOI 回查。"""
    action = str(action or "search")
    name = str(payload.get("name") or "").strip()[:80]
    unit = str(payload.get("unit") or "").strip()[:120]
    ror = str(payload.get("ror") or "").strip()
    if ror and not ror.startswith("http"):
        ror = "https://ror.org/" + ror.rsplit("/", 1)[-1]
    orcid = str(payload.get("orcid") or "").strip()
    doi = str(payload.get("doi") or "").strip()
    if action == "works":
        return author_works(str(payload.get("author_id") or ""), name, unit, ror)
    if action == "doi":
        return doi_check(doi, name, unit, ror)
    if not name and not unit and not orcid:
        return {"error": "至少填姓名、单位或 ORCID 之一"}
    institutions = ror_search(unit) if unit else []
    authors = author_search(name, ror, orcid) if (name or orcid) else []
    if not ror and institutions and institutions[0]["score"] >= 90:
        ror = institutions[0]["id"]
        authors = author_search(name, ror, orcid) if (name or orcid) else []
    name_note = ""
    if (name or orcid) and not authors:
        for variant in _name_variants(name):
            rows = author_search(variant, ror, orcid)
            if rows:
                authors = rows
                name_note = f"中文姓名按英文署名“{variant}”补搜到候选"
                break
    note = "先选单位，再选作者；候选人按姓名、ROR、ORCID 匹配排序，不按影响因子、h-index 或论文数量评价质量。"
    if name_note:
        note = name_note + "；仍需确认作者身份。" + note
    elif ror and (name or orcid) and not authors:
        note = "没有找到近 5 年在该机构发文的同名作者。可只填姓名重搜，或补 ORCID/代表论文 DOI。"
    return {"institutions": institutions, "authors": authors,
            "query": {"name": name, "unit": unit, "orcid": orcid, "doi": doi},
            "note": note}
