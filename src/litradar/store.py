from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import DB_PATH
from .fulltext import Figure, FullText
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
  relevance REAL DEFAULT 0,
  gate TEXT DEFAULT 'pass',
  gate_reason TEXT,
  payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE TABLE IF NOT EXISTS fulltext (
  pmcid TEXT PRIMARY KEY,
  title TEXT,
  journal TEXT,
  year INTEGER,
  text TEXT,
  char_count INTEGER,
  xml_path TEXT,
  status TEXT,
  error TEXT,
  fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS figures (
  pmcid TEXT,
  fig_id TEXT,
  kind TEXT,
  label TEXT,
  caption TEXT,
  image_url TEXT,
  cited_sentences TEXT,
  PRIMARY KEY (pmcid, fig_id)
);
CREATE INDEX IF NOT EXISTS idx_figures_pmcid ON figures(pmcid);
CREATE TABLE IF NOT EXISTS cards (
  pmcid TEXT PRIMARY KEY,
  data TEXT,
  model TEXT,
  tokens_in INTEGER,
  tokens_out INTEGER,
  status TEXT,
  error TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  direction TEXT,
  data TEXT,
  model TEXT,
  tokens INTEGER,
  created_at TEXT
);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """老库补列：相关性闸门是后加的，旧数据默认放行。"""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(papers)").fetchall()}
    for name, ddl in (("relevance", "REAL DEFAULT 0"),
                      ("gate", "TEXT DEFAULT 'pass'"),
                      ("gate_reason", "TEXT")):
        if name not in columns:
            conn.execute(f"ALTER TABLE papers ADD COLUMN {name} {ddl}")
    conn.commit()


def set_gate(conn: sqlite3.Connection, paper_id: str, score: float,
             keep: bool, reason: str = "") -> None:
    conn.execute(
        "UPDATE papers SET relevance=?, gate=?, gate_reason=? WHERE id=?",
        (float(score), "pass" if keep else "drop", reason or "", paper_id),
    )


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


def to_csv(conn: sqlite3.Connection, out: Path, ids: set[str] | None = None) -> int:
    sql = "SELECT doi, pmid, pmcid, year, journal, title, is_oa FROM papers"
    args: list[str] = []
    if ids is not None:
        if not ids:
            return 0
        marks = ",".join("?" for _ in ids)
        sql += f" WHERE id IN ({marks})"
        args = list(ids)
    rows = conn.execute(sql, args).fetchall()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig") as fh:
        fh.write("doi,pmid,pmcid,year,journal,title,is_oa\n")
        for r in rows:
            cells = ["" if v is None else str(v) for v in r]
            fh.write(",".join('"' + c.replace('"', '""') + '"' for c in cells) + "\n")
    return len(rows)


def _in_clause(ids: set[str] | None) -> tuple[str, list[str]]:
    """把本次运行的 PMCID 收窄成 IN 子句；None 表示不限制（老调用方兼容）。"""
    if ids is None:
        return "", []
    if not ids:
        return " AND 1=0", []
    marks = ",".join("?" for _ in ids)
    return f" AND p.pmcid IN ({marks})", list(ids)


def pending_fulltexts(conn: sqlite3.Connection, limit: int = 20,
                      allowed: set[str] | None = None) -> list[tuple[str, str]]:
    """挑出还没成功抓过全文的 OA 文献，按引用数降序。

    allowed 给出本次运行通过闸门的 PMCID 时，只在这些文献里挑，
    避免把历史库里别的方向的文献抓进来。
    """
    clause, params = _in_clause(allowed)
    sql = """
        SELECT p.pmcid, p.title
        FROM papers p
        LEFT JOIN fulltext f ON f.pmcid = p.pmcid
        WHERE p.pmcid IS NOT NULL AND p.pmcid <> ''
          AND p.is_oa = 1
          AND COALESCE(p.gate, 'pass') <> 'drop'
          AND (f.pmcid IS NULL OR f.status <> 'ok')
    """ + clause + """
        ORDER BY p.cited_by DESC
        LIMIT ?
    """
    args = [*params, int(limit)]
    return [(row[0], row[1] or "") for row in conn.execute(sql, args).fetchall()]


def save_fulltext(conn: sqlite3.Connection, ft: FullText,
                  xml_path: Path | str | None = None, error: str = "") -> None:
    conn.execute(
        """INSERT OR REPLACE INTO fulltext
           (pmcid, title, journal, year, text, char_count, xml_path, status, error, fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            ft.pmcid, ft.title, ft.journal, ft.year, ft.text, len(ft.text),
            str(xml_path) if xml_path else "", ft.status, error,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )
    conn.execute("DELETE FROM figures WHERE pmcid=?", (ft.pmcid,))
    for fig in ft.figures:
        conn.execute(
            """INSERT OR REPLACE INTO figures
               (pmcid, fig_id, kind, label, caption, image_url, cited_sentences)
               VALUES (?,?,?,?,?,?,?)""",
            (ft.pmcid, fig.fig_id, fig.kind, fig.label, fig.caption,
             fig.image_url, fig.cited_sentences),
        )


def fulltext_stats(conn: sqlite3.Connection) -> tuple[int, int]:
    full = int(conn.execute("SELECT COUNT(*) FROM fulltext WHERE status='ok'").fetchone()[0])
    figs = int(conn.execute("SELECT COUNT(*) FROM figures").fetchone()[0])
    return full, figs


def figures_for(conn: sqlite3.Connection, pmcid: str) -> list[Figure]:
    rows = conn.execute(
        """SELECT pmcid, fig_id, kind, label, caption, image_url, cited_sentences
           FROM figures WHERE pmcid=? ORDER BY kind, fig_id""",
        (pmcid,),
    ).fetchall()
    return [Figure(*row) for row in rows]


def get_fulltext(conn: sqlite3.Connection, pmcid: str) -> dict | None:
    row = conn.execute(
        """SELECT pmcid, title, journal, year, text, char_count, xml_path, status, error
           FROM fulltext WHERE pmcid=?""",
        (pmcid,),
    ).fetchone()
    if not row:
        return None
    keys = ("pmcid", "title", "journal", "year", "text", "char_count",
            "xml_path", "status", "error")
    return dict(zip(keys, row))


def get_paper(conn: sqlite3.Connection, paper_id: str) -> dict | None:
    row = conn.execute(
        """SELECT id, source, pmid, pmcid, doi, title, abstract, year, journal,
                  authors, is_oa, cited_by
           FROM papers WHERE id=?""",
        (paper_id,),
    ).fetchone()
    if not row:
        return None
    keys = ("id", "source", "pmid", "pmcid", "doi", "title", "abstract", "year",
            "journal", "authors", "is_oa", "cited_by")
    return dict(zip(keys, row))


def pending_abstracts(conn: sqlite3.Connection, limit: int = 20,
                      allowed: set[str] | None = None) -> list[str]:
    """挑出没有可用全文、但有摘要的同域文献，做摘要级卡片。

    非生医库（Crossref / OpenAlex / Scopus / 中文库）多数没有 PMC 全文，
    不能让整轮停在“0 张卡片”；摘要级卡片的每个字段都按“待核”约束。
    """
    if allowed is None:
        clause, params = "", []
    elif not allowed:
        return []
    else:
        marks = ",".join("?" for _ in allowed)
        clause, params = f" AND p.id IN ({marks})", list(allowed)
    sql = """
        SELECT p.id
        FROM papers p
        LEFT JOIN cards c ON c.pmcid = p.id
        LEFT JOIN fulltext f ON f.pmcid = p.pmcid AND f.status = 'ok'
        WHERE COALESCE(p.gate, 'pass') <> 'drop'
          AND COALESCE(p.abstract, '') <> ''
          AND c.pmcid IS NULL
          AND f.pmcid IS NULL
    """ + clause + """
        ORDER BY p.relevance DESC, p.cited_by DESC
        LIMIT ?
    """
    return [row[0] for row in conn.execute(sql, [*params, int(limit)]).fetchall()]


def save_card(conn: sqlite3.Connection, pmcid: str, data: dict, model: str,
              tokens_in: int = 0, tokens_out: int = 0,
              status: str = "ok", error: str = "") -> None:
    conn.execute(
        """INSERT OR REPLACE INTO cards
           (pmcid, data, model, tokens_in, tokens_out, status, error, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (pmcid, json.dumps(data, ensure_ascii=False), model, tokens_in,
         tokens_out, status, error, datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )


def get_cards(conn: sqlite3.Connection, limit: int | None = None) -> list[dict]:
    sql = "SELECT pmcid, data FROM cards WHERE status='ok' ORDER BY created_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    result = []
    for pmcid, payload in rows:
        item = json.loads(payload)
        item["pmcid"] = pmcid
        result.append(item)
    return result


def pending_cards(conn: sqlite3.Connection, limit: int = 20,
                  allowed: set[str] | None = None) -> list[str]:
    clause, params = _in_clause(allowed)
    rows = conn.execute(
        """SELECT f.pmcid FROM fulltext f
           LEFT JOIN cards c ON c.pmcid = f.pmcid
           LEFT JOIN papers p ON p.pmcid = f.pmcid
           WHERE f.status='ok' AND (c.pmcid IS NULL OR c.status <> 'ok')
    """ + clause + """
           ORDER BY f.pmcid LIMIT ?""",
        [*params, int(limit)],
    ).fetchall()
    return [row[0] for row in rows]


def save_report(conn: sqlite3.Connection, direction: str, data: dict,
                model: str, tokens: int) -> int:
    cursor = conn.execute(
        """INSERT INTO reports (direction, data, model, tokens, created_at)
           VALUES (?,?,?,?,?)""",
        (direction, json.dumps(data, ensure_ascii=False), model, tokens,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    return int(cursor.lastrowid)
