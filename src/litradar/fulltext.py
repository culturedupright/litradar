from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from .net import get_bytes

FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
IMAGE_BASE = "https://cdn.ncbi.nlm.nih.gov/pmc/"

_TAG_RE = re.compile(r"<[^>]+>")
_FIG_RE = re.compile(r"<fig\b[^>]*>(.*?)</fig>", re.S)
_TABLE_RE = re.compile(r"<table-wrap\b[^>]*>(.*?)</table-wrap>", re.S)
_LABEL_RE = re.compile(r"<label>(.*?)</label>", re.S)
_CAPTION_RE = re.compile(r"<caption>(.*?)</caption>", re.S)
_URN_RE = re.compile(r"<\?image-cloudpmc-urn\s+urn:cdn:(.*?)\?>", re.S)
_BODY_RE = re.compile(r"<body\b[^>]*>(.*?)</body>", re.S)
_TITLE_RE = re.compile(r"<article-title>(.*?)</article-title>", re.S)
_JOURNAL_RE = re.compile(r"<journal-title>(.*?)</journal-title>", re.S)
_YEAR_RE = re.compile(r"<pub-date[^>]*>.*?<year>(\d{4})</year>", re.S)
_DIGITS_RE = re.compile(r"(\d+)")


def plain(fragment: str) -> str:
    """去掉 JATS 标签，保留可读文本。"""
    if not fragment:
        return ""
    fragment = re.sub(r"</title>", ". ", fragment)
    fragment = re.sub(r"</(p|td|th|li|tr|caption|label|sec)>", " ", fragment)
    fragment = re.sub(r"<br\s*/?>", " ", fragment)
    text = html.unescape(_TAG_RE.sub(" ", fragment))
    return re.sub(r"\s+", " ", text).strip()


_ABBREV_RE = re.compile(r"\b(Fig|Figs|et al|vs|i\.e|e\.g|approx|ca)\.", re.I)


def sentences(text: str) -> list[str]:
    """按句号切句，但保护 Fig. / et al. 这类缩写，避免把 “Fig. 1” 切成两句。"""
    guarded = _ABBREV_RE.sub(r"\1<DOT>", text)
    parts = re.split(r"(?<=[.!?])\s+", guarded)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


@dataclass
class Figure:
    pmcid: str
    fig_id: str
    kind: str = "figure"
    label: str = ""
    caption: str = ""
    image_url: str = ""
    cited_sentences: str = ""


@dataclass
class FullText:
    pmcid: str
    title: str = ""
    journal: str = ""
    year: int | None = None
    text: str = ""
    status: str = "ok"
    n_refs: int = 0
    figures: list[Figure] = field(default_factory=list)


def _number(label: str) -> int | None:
    match = _DIGITS_RE.search(label or "")
    return int(match.group(1)) if match else None


def _mentions(number: int, kind: str, sentence: str) -> bool:
    if kind == "table":
        return bool(re.search(rf"\bTable\s*{number}(?![0-9])", sentence, re.I))
    if re.search(rf"\bFig(?:ure)?\.?\s*{number}(?![0-9])", sentence, re.I):
        return True
    # 处理 “Figs. 2, 3 and 4”“Figs. 1–3” 这类合并引用
    match = re.search(r"\bFigs?\.?\s*([0-9][^)\]]{0,40})", sentence, re.I)
    if not match:
        return False
    tail = match.group(1)
    numbers = {int(x) for x in re.findall(r"\d+", tail)}
    if number in numbers:
        return True
    for low, high in re.findall(r"(\d+)\s*[–-]\s*(\d+)", tail):
        if int(low) <= number <= int(high):
            return True
    return False


def _cite(n: int, kind: str, sents: list[str]) -> str:
    hits = [s for s in sents if _mentions(n, kind, s)]
    return " || ".join(hits[:3])


def _block_items(xml: str, block_re: re.Pattern[str], kind: str, sents: list[str]) -> list[Figure]:
    items: list[Figure] = []
    for index, match in enumerate(block_re.finditer(xml), start=1):
        block = match.group(1)
        label = plain(_LABEL_RE.search(block).group(1)) if _LABEL_RE.search(block) else ""
        caption = plain(_CAPTION_RE.search(block).group(1)) if _CAPTION_RE.search(block) else ""
        number = _number(label) or index
        name = "Table" if kind == "table" else "Figure"
        if not label or label.strip().isdigit():
            label = f"{name} {number}"
        item = Figure(
            pmcid="",
            fig_id=f"{kind}-{number}",
            kind=kind,
            label=label or f"{kind} {number}",
            caption=caption,
        )
        urn = _URN_RE.search(block)
        if urn and kind == "figure":
            item.image_url = IMAGE_BASE + urn.group(1).strip()
        item.cited_sentences = _cite(number, kind, sents)
        items.append(item)
    return items


def parse_jats(xml: str, pmcid: str) -> FullText:
    """把 PMC 的 JATS XML 拆成正文 + 图/表 + 引用句。"""
    title_match = _TITLE_RE.search(xml)
    journal_match = _JOURNAL_RE.search(xml)
    year_match = _YEAR_RE.search(xml)
    body_match = _BODY_RE.search(xml)
    body_raw = body_match.group(1) if body_match else ""
    # 图注属于图表条目，不能混进正文，否则引用句会自己和图注对上
    body_raw = _FIG_RE.sub(" ", body_raw)
    body_raw = _TABLE_RE.sub(" ", body_raw)
    body = plain(body_raw)
    sents = sentences(body)
    figures = _block_items(xml, _FIG_RE, "figure", sents)
    figures += _block_items(xml, _TABLE_RE, "table", sents)
    for item in figures:
        item.pmcid = pmcid
    status = "ok" if body and figures else "partial"
    return FullText(
        pmcid=pmcid,
        title=plain(title_match.group(1)) if title_match else "",
        journal=plain(journal_match.group(1)) if journal_match else "",
        year=int(year_match.group(1)) if year_match else None,
        text=body[:200_000],
        status=status,
        n_refs=len(re.findall(r"<ref\b", xml)),
        figures=figures,
    )


def fetch_fulltext(pmcid: str) -> tuple[FullText, bytes]:
    """抓一篇 OA 全文，返回解析结果与原始 XML。"""
    url = FULLTEXT_URL.format(pmcid=pmcid)
    data = get_bytes(url)
    text = data.decode("utf-8", errors="replace")
    return parse_jats(text, pmcid), data
