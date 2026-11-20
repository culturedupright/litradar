from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass
from typing import Any

_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub("", value))).strip()


@dataclass
class Paper:
    id: str
    source: str = ""
    pmid: str = ""
    pmcid: str = ""
    doi: str = ""
    title: str = ""
    abstract: str = ""
    year: int | None = None
    journal: str = ""
    authors: str = ""
    is_oa: bool = False
    cited_by: int = 0

    @property
    def key(self) -> str:
        return self.doi or self.id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Paper":
        return cls(
            id=str(data.get("id") or ""),
            source=str(data.get("source") or ""),
            pmid=str(data.get("pmid") or ""),
            pmcid=str(data.get("pmcid") or ""),
            doi=str(data.get("doi") or ""),
            title=str(data.get("title") or ""),
            abstract=str(data.get("abstract") or ""),
            year=data.get("year"),
            journal=str(data.get("journal") or ""),
            authors=str(data.get("authors") or ""),
            is_oa=bool(data.get("is_oa")),
            cited_by=int(data.get("cited_by") or 0),
        )

    @classmethod
    def from_europepmc(cls, item: dict[str, Any]) -> "Paper":
        journal_info = item.get("journalInfo") or {}
        journal = journal_info.get("journal") or {}
        year = item.get("pubYear")
        return cls(
            id=str(item.get("id") or ""),
            source=str(item.get("source") or ""),
            pmid=str(item.get("pmid") or ""),
            pmcid=str(item.get("pmcid") or ""),
            doi=str(item.get("doi") or ""),
            title=clean_text(item.get("title")),
            abstract=clean_text(item.get("abstractText")),
            year=int(year) if year and str(year).isdigit() else None,
            journal=journal.get("title") or journal.get("medlineAbbreviation") or "",
            authors=str(item.get("authorString") or ""),
            is_oa=item.get("isOpenAccess") == "Y",
            cited_by=int(item.get("citedByCount") or 0),
        )
