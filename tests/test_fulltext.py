from __future__ import annotations

from pathlib import Path

from litradar.fulltext import parse_jats
from litradar.store import connect, figures_for, fulltext_stats, save_fulltext

SAMPLE = """
<article>
  <front>
    <journal-title>Journal of Tests</journal-title>
    <article-title>A test article</article-title>
    <pub-date><year>2026</year></pub-date>
  </front>
  <body>
    <sec><title>Results</title>
      <p>Growth increased under treatment (Fig. 1A).</p>
      <p>Both traits responded (Figs. 2, 3 and 4).</p>
      <fig id="Fig1"><label>Fig. 1</label>
        <caption><p>Growth curve</p></caption>
        <graphic xlink:href="fig1.webp"><?image-cloudpmc-urn urn:cdn:blobs/4316/1/abc/fig1.webp?></graphic>
      </fig>
      <fig id="Fig2"><label>Fig. 2</label><caption><p>Root length</p></caption>
        <graphic xlink:href="fig2.webp"><?image-cloudpmc-urn urn:cdn:blobs/4316/1/def/fig2.webp?></graphic>
      </fig>
      <table-wrap id="Tab1"><label>Table 1</label><caption><p>Design</p></caption></table-wrap>
    </sec>
  </body>
</article>
"""


def test_parse_jats_extracts_meta_and_body() -> None:
    ft = parse_jats(SAMPLE, "PMC1")
    assert ft.title == "A test article"
    assert ft.journal == "Journal of Tests"
    assert ft.year == 2026
    assert "Growth increased" in ft.text
    assert "Growth curve" not in ft.text  # 图注不能混进正文


def test_parse_jats_builds_figure_and_table_records() -> None:
    ft = parse_jats(SAMPLE, "PMC1")
    kinds = {f.kind for f in ft.figures}
    assert kinds == {"figure", "table"}
    fig1 = next(f for f in ft.figures if f.label == "Fig. 1")
    assert fig1.image_url.endswith("/pmc/blobs/4316/1/abc/fig1.webp")
    assert "Fig. 1A" in fig1.cited_sentences
    assert fig1.pmcid == "PMC1"


def test_parse_jats_handles_grouped_citation() -> None:
    ft = parse_jats(SAMPLE, "PMC1")
    fig2 = next(f for f in ft.figures if f.label == "Fig. 2")
    assert "Figs. 2, 3 and 4" in fig2.cited_sentences
    table = next(f for f in ft.figures if f.label == "Table 1")
    assert table.cited_sentences == ""


def test_save_fulltext_roundtrip(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    ft = parse_jats(SAMPLE, "PMC1")
    save_fulltext(conn, ft, tmp_path / "PMC1.xml")
    conn.commit()
    figs = figures_for(conn, "PMC1")
    assert len(figs) == 3
    full, count = fulltext_stats(conn)
    assert full == 1
    assert count == 3
