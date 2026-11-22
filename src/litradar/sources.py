"""多检索源：Europe PMC / PubMed / OpenAlex / Web of Science / Scopus。

每个源都返回统一的 Paper；能拿到全文的只有 PMC 系，其余源负责把“同领域的文献”
先召回，再交给相关性闸门筛。WOS / Scopus 需要使用者自己的 API Key（机构订阅，
不共享账号密码），凭据由 credentials 管理。
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterable

from . import credentials
from .config import REQUEST_INTERVAL, USER_AGENT
from .europepmc import iter_papers
from .models import Paper, clean_text
from .net import make_opener

LABELS = {
    "europepmc": "Europe PMC",
    "pubmed": "PubMed",
    "openalex": "OpenAlex",
    "wos": "Web of Science",
    "scopus": "Scopus",
}

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")


def tokens(query: str) -> list[str]:
    """从布尔检索式里抠出关键词，给不支持同一套语法的源用。"""
    words = _TOKEN_RE.findall(query or "")
    stop = {"and", "or", "not", "the", "for", "with", "from", "into"}
    out: list[str] = []
    for word in words:
        low = word.lower()
        if low in stop or low in out:
            continue
        out.append(low)
    return out[:12]


def _year_clause(years: str) -> tuple[int | None, int | None]:
    if not years or "-" not in years:
        return None, None
    try:
        start, end = [int(x.strip()) for x in years.split("-")[:2]]
        return start, end
    except ValueError:
        return None, None


def _request(url: str, headers: dict | None = None, retries: int = 3,
             timeout: int = 40) -> bytes:
    opener = make_opener()
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    merged.update(headers or {})
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=merged)
            with opener.open(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(str(last))


def _get_json(url: str, headers: dict | None = None) -> dict:
    return json.loads(_request(url, headers))


def _auth_hint(exc: Exception) -> str:
    text = str(exc)
    if "401" in text or "403" in text or "Unauthorized" in text:
        return "凭据无效或已过期，请重新配置"
    return text[:120]


# ---------------------------------------------------------------- Europe PMC
def _europepmc(query: str, keywords: list[str], years: str, limit: int) -> list[Paper]:
    q = query
    start, end = _year_clause(years)
    if start and end:
        q = f"({q}) AND (FIRST_PDATE:[{start}-01-01 TO {end}-12-31])"
    return list(iter_papers(q, limit=limit))


# ------------------------------------------------------------------- PubMed
def _pubmed(query: str, keywords: list[str], years: str, limit: int) -> list[Paper]:
    terms = keywords or tokens(query)
    term = " OR ".join(f'"{t}"' for t in terms) if terms else query
    start, end = _year_clause(years)
    params = {"db": "pubmed", "term": term, "retmax": min(limit, 100),
              "retmode": "json", "sort": "relevance"}
    if start and end:
        params["datetype"] = "pdat"
        params["mindate"] = start
        params["maxdate"] = end
    cred = credentials.active("pubmed") or {}
    if cred.get("email"):
        params["email"] = cred["email"]
        params["tool"] = "litradar"
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(params)
    data = _get_json(url)
    ids = ((data.get("esearchresult") or {}).get("idlist") or [])[:limit]
    if not ids:
        return []
    fetch = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
             + urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids),
                                       "retmode": "xml"}))
    xml = _request(fetch).decode("utf-8", errors="replace")
    return _parse_pubmed(xml)


def _parse_pubmed(xml: str) -> list[Paper]:
    papers: list[Paper] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return papers
    for node in root.iter("PubmedArticle"):
        pmid = node.findtext(".//PMID") or ""
        title = "".join(node.find(".//ArticleTitle").itertext()) if node.find(".//ArticleTitle") is not None else ""
        abstract = " ".join("".join(x.itertext()) for x in node.findall(".//AbstractText"))
        journal = node.findtext(".//Journal/Title") or ""
        year_text = node.findtext(".//PubDate/Year") or node.findtext(".//PubDate/MedlineDate") or ""
        year = int(re.search(r"\d{4}", year_text).group()) if re.search(r"\d{4}", year_text) else None
        doi, pmcid = "", ""
        for ident in node.findall(".//ArticleId"):
            kind = (ident.get("IdType") or "").lower()
            if kind == "doi":
                doi = (ident.text or "").strip()
            if kind == "pmc":
                pmcid = (ident.text or "").strip()
        authors = ", ".join(
            "".join(a.itertext()) for a in node.findall(".//AuthorList/Author")[:6]
            if a.find("LastName") is not None)
        papers.append(Paper(id=pmid or doi, source="pubmed", pmid=pmid, pmcid=pmcid,
                            doi=doi, title=clean_text(title), abstract=abstract, year=year,
                            journal=journal, authors=authors,
                            is_oa=bool(pmcid)))
    return papers


# ------------------------------------------------------------------ OpenAlex
def _openalex(query: str, keywords: list[str], years: str, limit: int) -> list[Paper]:
    terms = keywords or tokens(query)
    search = " OR ".join(terms)
    start, end = _year_clause(years)
    params = {"search": search, "per-page": min(limit, 50), "sort": "relevance_score:desc"}
    filters = []
    if start:
        filters.append(f"from_publication_date:{start}-01-01")
    if end:
        filters.append(f"to_publication_date:{end}-12-31")
    if filters:
        params["filter"] = ",".join(filters)
    cred = credentials.active("openalex") or {}
    if cred.get("email"):
        params["mailto"] = cred["email"]
    data = _get_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
    out: list[Paper] = []
    for item in (data.get("results") or [])[:limit]:
        abstract = _inverted(item.get("abstract_inverted_index"))
        venue = ((item.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        doi = str(item.get("doi") or "").replace("https://doi.org/", "")
        ids = item.get("ids") or {}
        pmid = str(ids.get("pmid") or "").rstrip("/").split("/")[-1]
        out.append(Paper(
            id=str(item.get("id") or doi or pmid).split("/")[-1],
            source="openalex", pmid=pmid, doi=doi,
            title=clean_text(str(item.get("title") or "")), abstract=abstract,
            year=item.get("publication_year"), journal=venue,
            is_oa=bool((item.get("open_access") or {}).get("is_oa")),
            cited_by=int(item.get("cited_by_count") or 0),
        ))
    return out


def _inverted(index: dict | None) -> str:
    if not index:
        return ""
    slots: dict[int, str] = {}
    for word, positions in index.items():
        for pos in positions:
            slots[int(pos)] = word
    return " ".join(slots[k] for k in sorted(slots))


# ---------------------------------------------------------------------- WOS
def _wos(query: str, keywords: list[str], years: str, limit: int) -> list[Paper]:
    cred = credentials.active("wos")
    if not cred:
        raise RuntimeError("未配置 Web of Science API Key（或已过期）")
    terms = keywords or tokens(query)
    start, end = _year_clause(years)
    q = "TS=(" + " OR ".join(f'"{t}"' for t in terms) + ")"
    if start and end:
        q += f" AND PY=({start}-{end})"
    params = {"q": q, "limit": min(limit, 50), "page": 1, "db": "WOS"}
    data = _get_json("https://api.clarivate.com/apis/wos-starter/v1/documents?"
                     + urllib.parse.urlencode(params),
                     headers={"X-ApiKey": cred["api_key"]})
    out: list[Paper] = []
    for hit in (data.get("hits") or [])[:limit]:
        source = hit.get("source") or {}
        names = hit.get("names") or {}
        authors = ", ".join((a.get("displayName") or a.get("wosStandard") or "")
                            for a in (names.get("authors") or [])[:6] if a)
        ids = hit.get("identifiers") or {}
        out.append(Paper(
            id=str(hit.get("uid") or ids.get("doi") or ""), source="wos",
            doi=str(ids.get("doi") or ""), pmid=str(ids.get("pmid") or ""),
            title=clean_text(str(hit.get("title") or "")), abstract=clean_text(str(hit.get("abstract") or "")),
            year=source.get("publishYear"), journal=str(source.get("sourceTitle") or ""),
            authors=authors, is_oa=bool(hit.get("openAccess")),
        ))
    return out


# ------------------------------------------------------------------- Scopus
def _scopus(query: str, keywords: list[str], years: str, limit: int) -> list[Paper]:
    cred = credentials.active("scopus")
    if not cred:
        raise RuntimeError("未配置 Scopus API Key（或已过期）")
    terms = keywords or tokens(query)
    start, end = _year_clause(years)
    q = "TITLE-ABS-KEY(" + " OR ".join(f'"{t}"' for t in terms) + ")"
    if start and end:
        q += f" AND PUBYEAR > {start - 1} AND PUBYEAR < {end + 1}"
    params = {"query": q, "count": min(limit, 25), "sort": "-cited"}
    headers = {"X-ELS-APIKey": cred["api_key"], "Accept": "application/json"}
    if cred.get("inst_token"):
        headers["X-ELS-Insttoken"] = cred["inst_token"]
    data = _get_json("https://api.elsevier.com/content/search/scopus?"
                     + urllib.parse.urlencode(params), headers=headers)
    entries = ((data.get("search-results") or {}).get("entry") or [])
    out: list[Paper] = []
    for entry in entries[:limit]:
        if not isinstance(entry, dict) or "error" in entry:
            continue
        cover = str(entry.get("prism:coverDate") or "")
        year = int(cover[:4]) if cover[:4].isdigit() else None
        out.append(Paper(
            id=str(entry.get("dc:identifier") or entry.get("prism:doi") or ""),
            source="scopus", doi=str(entry.get("prism:doi") or ""),
            pmid=str(entry.get("pubmed-id") or ""),
            title=clean_text(str(entry.get("dc:title") or "")), abstract="",
            year=year, journal=str(entry.get("prism:publicationName") or ""),
            authors=str(entry.get("dc:creator") or ""),
            cited_by=int(entry.get("citedby-count") or 0),
        ))
    return out


BACKENDS = {
    "europepmc": _europepmc,
    "pubmed": _pubmed,
    "openalex": _openalex,
    "wos": _wos,
    "scopus": _scopus,
}


def search_all(query: str, keywords: list[str], years: str, limit: int,
               sources: Iterable[str], oecd_code: str = "",
               rate: float = REQUEST_INTERVAL) -> tuple[list[Paper], list[dict]]:
    """逐源检索、合并去重；返回文献与逐源体检（供界面与简报展示）。"""
    chosen = [s for s in sources if s in BACKENDS] or ["europepmc"]
    quota = max(5, int(limit / max(1, len(chosen))) + 1)
    stats: list[dict] = []
    merged: dict[str, Paper] = {}

    for source in chosen:
        label = LABELS[source]
        try:
            found = BACKENDS[source](query, keywords, years, quota)
        except Exception as exc:  # noqa: BLE001 - 单源失败不影响其它源
            stats.append({"source": source, "label": label, "ok": False,
                          "count": 0, "error": _auth_hint(exc)})
            continue
        stats.append({"source": source, "label": label, "ok": True,
                      "count": len(found), "error": ""})
        for paper in found:
            key = (paper.doi or "").lower() or (paper.pmid and f"pmid:{paper.pmid}") or \
                  re.sub(r"\W+", "", (paper.title or "").lower())[:80] or paper.id
            if key in merged:
                _merge(merged[key], paper)
            else:
                merged[key] = paper
        time.sleep(rate)

    if stats and not any(s["ok"] for s in stats):
        detail = "；".join(f"{s['label']}：{s['error']}" for s in stats)
        raise RuntimeError(f"所有检索源都失败（{detail}）")

    papers = list(merged.values())[:limit]
    return papers, stats


def _merge(keep: Paper, extra: Paper) -> None:
    """同一条文献被多个库命中时合并字段：优先保留有 PMCID / 摘要的那一份。"""
    if extra.pmcid and not keep.pmcid:
        keep.pmcid = extra.pmcid
    if extra.pmid and not keep.pmid:
        keep.pmid = extra.pmid
    if extra.doi and not keep.doi:
        keep.doi = extra.doi
    if len(extra.abstract or "") > len(keep.abstract or ""):
        keep.abstract = extra.abstract
    if extra.journal and not keep.journal:
        keep.journal = extra.journal
    if extra.year and not keep.year:
        keep.year = extra.year
    if extra.cited_by > keep.cited_by:
        keep.cited_by = extra.cited_by
    if extra.is_oa:
        keep.is_oa = True
    names = {n for n in (keep.source or "").split("+") if n}
    names.add(extra.source)
    keep.source = "+".join(sorted(names))


