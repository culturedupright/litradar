"""检索结果的相关性闸门。

检索源（Europe PMC）是生命科学库，跨学科方向检索时必然混进大量无关文献。
这一层在抓全文之前先做一次领域判定：命中干扰词、又没有任何方向术语的文献
直接挡在门外，不消耗全文抓取与 token；同时把判定过程汇总成"检索体检"，
让人一眼看出这批结果是不是跑偏了。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .domain import Domain, contains

STOP = {
    "and", "or", "not", "the", "of", "in", "on", "for", "with", "a", "an",
    "study", "studies", "effect", "effects", "analysis", "review", "using",
    "based", "from", "to", "by", "is", "are", "as", "at", "its",
}


def _norm(text: str) -> str:
    text = (text or "").lower()
    return re.sub(r"\s+", " ", text)


def topic_terms(query: str) -> list[str]:
    """从布尔检索式里抽出真正的主题词，丢掉括号、年份子句、NOT 子句与停用词。"""
    q = (query or "").lower()
    q = q.split(" not ")[0]
    q = re.sub(r"\((?:first_pdate|pub_year|first_[a-z_]+)[^)]*\)", " ", q)
    q = q.replace('"', " ")
    tokens = re.split(r"[^a-z0-9\-]+", q)
    terms: list[str] = []
    for raw in tokens:
        token = raw.strip("-")
        if len(token) < 3 or token in STOP:
            continue
        if token not in terms:
            terms.append(token)
    return terms[:24]


@dataclass
class Verdict:
    score: float
    keep: bool
    reason: str = ""
    topic_hits: tuple[str, ...] = ()
    domain_hits: tuple[str, ...] = ()
    anti_hits: tuple[str, ...] = ()


def judge(title: str, abstract: str, domain: Domain,
          terms: list[str]) -> Verdict:
    body = _norm(f"{title}\n{abstract}")
    topic = _norm(title)
    topic_hits = tuple(t for t in terms if contains(body, t))
    title_hits = tuple(t for t in terms if contains(topic, t))
    domain_hits = tuple(w for w in domain.lexicon if contains(body, w))
    anti_hits = tuple(w for w in domain.anti if contains(body, w))

    score = (2.0 * len(topic_hits) + 1.5 * len(title_hits)
             + 1.0 * len(domain_hits) - 2.5 * len(anti_hits))

    if not domain.gate:
        return Verdict(score=score, keep=True, reason="通用方向，不做领域闸门",
                       topic_hits=topic_hits, domain_hits=domain_hits, anti_hits=anti_hits)

    if not topic_hits and not domain_hits:
        reason = ("命中干扰词：" + "、".join(anti_hits[:4])) if anti_hits else "与该方向没有共同术语"
        return Verdict(score=score, keep=False, reason=reason,
                       topic_hits=topic_hits, domain_hits=domain_hits, anti_hits=anti_hits)

    if score < domain.min_score:
        reason = "相关度不足"
        if anti_hits:
            reason += "；命中干扰词：" + "、".join(anti_hits[:4])
        return Verdict(score=score, keep=False, reason=reason,
                       topic_hits=topic_hits, domain_hits=domain_hits, anti_hits=anti_hits)

    return Verdict(score=score, keep=True,
                   topic_hits=topic_hits, domain_hits=domain_hits, anti_hits=anti_hits)


def relax_query(query: str) -> str:
    """检索式为 0 命中时，从尾部去掉一个 AND 组再试。

    规划模型有时会把三个概念全用 AND 串起来（研究对象 AND 干预 AND 结局），
    最严的那一组常常把命中打到 0；宁可比预期宽，也不要不给结果。
    """
    q = (query or "").strip()
    index = q.rfind(" AND (")
    if index == -1:
        return q
    tail = q[index + len(" AND "):].strip()
    if tail.startswith("(") and tail.endswith(")"):
        return q[:index].strip()
    return q


def audit(domain: Domain, terms: list[str], decisions: list[dict]) -> dict:
    """把逐篇判定汇总成一张体检表，写进 report 与 summary.json。"""
    total = len(decisions)
    kept = [d for d in decisions if d["keep"]]
    dropped = [d for d in decisions if not d["keep"]]
    journals: dict[str, int] = {}
    years: list[int] = []
    for item in decisions:
        journal = (item.get("journal") or "").strip()
        if journal:
            journals[journal] = journals.get(journal, 0) + 1
        year = item.get("year")
        if isinstance(year, int) and 1900 < year < 2100:
            years.append(year)
    top = sorted(journals.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return {
        "domain": domain.key,
        "domain_label": domain.label,
        "framework": domain.framework,
        "gate_enabled": domain.gate,
        "threshold": domain.min_score,
        "topic_terms": terms,
        "candidates": total,
        "kept": len(kept),
        "dropped": len(dropped),
        "keep_ratio": round(len(kept) / total, 3) if total else 0.0,
        "top_journals": [{"journal": j, "count": c} for j, c in top],
        "year_range": [min(years), max(years)] if years else [],
        "dropped_samples": [
            {"title": (d.get("title") or "")[:90], "reason": d.get("reason", "")}
            for d in dropped[:8]
        ],
        "kept_samples": [{"title": (d.get("title") or "")[:90], "score": round(d["score"], 1)}
                         for d in kept[:8]],
    }
