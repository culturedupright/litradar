from __future__ import annotations

from pathlib import Path

from litradar.fulltext import FullText
from litradar.models import Paper
from litradar.store import (connect, pending_cards, pending_fulltexts,
                            save_card, save_fulltext, to_csv, upsert)


def _seed(conn) -> None:
    for pmcid, title in [("PMC1", "Memristor array"), ("PMC2", "Banana rhizosphere")]:
        upsert(conn, Paper(id=pmcid, pmcid=pmcid, title=title, is_oa=True))
    # 只给 PMC1 存全文：PMC2 还缺全文，用来区分“本次运行”和“库里其它方向”
    save_fulltext(conn, FullText(pmcid="PMC1", text="body"), b"<xml/>")
    conn.commit()


def test_pending_fulltexts_respects_run_ids(tmp_path: Path) -> None:
    conn = connect(tmp_path / "db.sqlite")
    _seed(conn)
    assert {p for p, _ in pending_fulltexts(conn, 10, {"PMC2"})} == {"PMC2"}
    assert pending_fulltexts(conn, 10, {"PMC1"}) == []
    assert pending_fulltexts(conn, 10, set()) == []
    assert {p for p, _ in pending_fulltexts(conn, 10)} == {"PMC2"}


def test_pending_cards_respects_run_ids(tmp_path: Path) -> None:
    conn = connect(tmp_path / "db.sqlite")
    _seed(conn)
    assert pending_cards(conn, 10, {"PMC1"}) == ["PMC1"]
    assert pending_cards(conn, 10, {"PMC2"}) == []
    save_card(conn, "PMC1", {"conclusion": "x"}, "test")
    conn.commit()
    assert pending_cards(conn, 10, {"PMC1"}) == []


def test_to_csv_filters_by_ids(tmp_path: Path) -> None:
    conn = connect(tmp_path / "db.sqlite")
    _seed(conn)
    out = tmp_path / "papers.csv"
    assert to_csv(conn, out, {"PMC1"}) == 1
    assert "Memristor" in out.read_text(encoding="utf-8")
    assert to_csv(conn, tmp_path / "empty.csv", set()) == 0
