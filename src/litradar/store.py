from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import DB_PATH
from .models import Paper

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
  id TEXT PRIMARY KEY,
  source TEXT,
  pmid TEXT,
  pmcid TEXT,
  doi TEXT,
  title TEXT,
  abstract TEXT,
  year INTEGER,
  journal TEXT,
  authors TEXT,
  is_oa INTEGER,
  cited_by INTEGER,
  payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def upsert(conn: sqlite3.Connection, paper: Paper) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO papers
           (id, source, pmid, pmcid, doi, title, abstract, year, journal,
            authors, is_oa, cited_by, payload)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            paper.id, paper.source, paper.pmid, paper.pmcid, paper.doi,
            paper.title, paper.abstract, paper.year, paper.journal,
            paper.authors, int(paper.is_oa), paper.cited_by,
            json.dumps(paper.to_dict(), ensure_ascii=False),
        ),
    )


def count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0])


def all_papers(conn: sqlite3.Connection, limit: int | None = None) -> list[Paper]:
    sql = "SELECT payload FROM papers ORDER BY year DESC, cited_by DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    return [Paper.from_dict(json.loads(r[0])) for r in rows]


def to_csv(conn: sqlite3.Connection, out: Path) -> int:
    rows = conn.execute(
        "SELECT doi, pmid, pmcid, year, journal, title, is_oa FROM papers"
    ).fetchall()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig") as fh:
        fh.write("doi,pmid,pmcid,year,journal,title,is_oa\n")
        for r in rows:
            cells = ["" if v is None else str(v) for v in r]
            fh.write(",".join('"' + c.replace('"', '""') + '"' for c in cells) + "\n")
    return len(rows)
