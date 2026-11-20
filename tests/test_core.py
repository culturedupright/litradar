from __future__ import annotations

from pathlib import Path

from litradar.europepmc import build_query
from litradar.models import Paper
from litradar.store import connect, count, upsert


def test_build_query_joins_synonyms_with_or() -> None:
    q = build_query({
        "population": "Oxytropis ochrocephala|黄花棘豆",
        "intervention": "endophyte|内生真菌",
    })
    assert q == "(Oxytropis ochrocephala OR 黄花棘豆) AND (endophyte OR 内生真菌)"


def test_build_query_adds_year_window() -> None:
    q = build_query({"outcome": "rust"}, years="2012-2026")
    assert "FIRST_PDATE:[2012-01-01 TO 2026-12-31]" in q


def test_build_query_empty_pico_returns_empty() -> None:
    assert build_query({}) == ""


def test_paper_from_europepmc_reads_journal_title() -> None:
    item = {
        "id": "40572460",
        "doi": "10.3390/molecules30122489",
        "title": "Chemical Constituents of <i>Oxytropis ochrocephala</i>.",
        "pubYear": "2025",
        "isOpenAccess": "Y",
        "journalInfo": {"journal": {"title": "Molecules"}},
    }
    paper = Paper.from_europepmc(item)
    assert paper.journal == "Molecules"
    assert paper.title == "Chemical Constituents of Oxytropis ochrocephala."
    assert paper.is_oa is True
    assert paper.year == 2025


def test_store_upsert_deduplicates(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    paper = Paper(id="1", doi="10.1/x", title="A")
    upsert(conn, paper)
    upsert(conn, paper)
    conn.commit()
    assert count(conn) == 1
