from __future__ import annotations

from pathlib import Path

from litradar import credentials, oecd, proposal, team
from litradar.models import Paper
from litradar.sources import _inverted, _merge, _parse_pubmed, tokens

AUDIT = {"framework": "PSPP", "candidates": 20, "kept": 12, "dropped": 8,
         "threshold": 1.5, "top_journals": [{"journal": "Nature", "count": 3}],
         "year_range": [2020, 2026], "dropped_samples": [{"title": "Banana", "reason": "plant"}]}
SUMMARY = {
    "consensus": [{"point": "器件靠离子输运开关", "papers": ["PMC1"]}],
    "controversies": [{"point": "能耗瓶颈在哪一层", "sides": "器件 vs 架构", "papers": ["PMC1"]}],
    "gaps": [{"gap": "缺少工艺参数", "why": "三篇均未给温度与退火"}],
    "figure_patterns": [{"type": "I–V 曲线", "purpose": "证明开关", "how_to_replicate": "扫描电压"}],
    "directions": [{"title": "低功耗器件", "rationale": "能耗是瓶颈",
                    "hypothesis": "降低漏电流可降功耗", "design": "两组器件对照",
                    "readout": "开关能量", "risk": "工艺窗口窄"}],
}
CARDS = [{"pmcid": "PMC1", "title": "Memristor", "journal": "Nature",
          "year": 2025, "doi": "10.1/x", "design": "实验", "system": "HfO2",
          "factors": "退火 300 度", "controls": "未退火", "sample_size": "12",
          "omics": "TEM", "outcomes": "开关比 10", "conclusion": "可行",
          "limitations": "样本少", "evidence": [{"location": "Results", "quote": "q", "verified": True}]}]


def test_oecd_has_six_majors_and_subfields() -> None:
    assert len(oecd.MAJOR) == 6
    assert oecd.get("2.5").label == "材料工程"
    assert oecd.domain_hint("4.1") == "agri"
    assert oecd.as_json()[0]["children"]


def test_credentials_expiry(tmp_path: Path) -> None:
    credentials.PATH = tmp_path / "credentials.json"
    status = credentials.save("wos", {"api_key": "abc", "expires": "2000-01-01"})
    assert status["expired"] and not status["configured"]
    assert credentials.active("wos") is None
    status = credentials.save("wos", {"api_key": "abc", "expires": "2099-01-01"})
    assert status["configured"]
    assert credentials.active("wos")["api_key"] == "abc"
    credentials.clear("wos")
    assert not credentials.status("wos")["configured"]


def test_team_scores_and_gaps() -> None:
    strong = team.evaluate({k: {"level": 5, "note": ""} for k in
                            ("pi", "platform", "foundation", "team", "funding")})
    assert strong["score"] == 5.0 and strong["band"] == "强"
    weak = team.evaluate({"pi": {"level": 1, "note": ""}})
    assert "PI 学术资本" in weak["gaps"]


def test_proposal_has_nine_sections_and_appendix() -> None:
    md = proposal.build("忆阻器", SUMMARY, CARDS, AUDIT, field_code="2.5",
                        platform="湿+干", budget="5–20 万", period="1 年",
                        team_profile=None, owner="潘鹏旭")
    for title in ("一、立项依据", "二、研究目标", "三、研究内容", "四、研究方案与技术路线",
                  "五、创新点", "六、可行性分析", "七、预期成果", "八、进度安排", "九、参考文献"):
        assert title in md
    assert "附录 A" in md and "附录 C" in md
    assert "2.5 材料工程" in md
    assert "待申请人补充" in md


def test_source_helpers() -> None:
    assert tokens("(memristor OR RRAM) AND neuromorphic")[:2] == ["memristor", "rram"]
    assert _inverted({"a": [0], "b": [1]}) == "a b"

    xml = """<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID>
    <Article><ArticleTitle>A <i>device</i> paper</ArticleTitle>
    <Abstract><AbstractText>Body</AbstractText></Abstract>
    <Journal><Title>J</Title></Journal></Article></MedlineCitation>
    <PubDate><Year>2021</Year></PubDate></PubmedArticle></PubmedArticleSet>"""
    papers = _parse_pubmed(xml)
    assert papers and papers[0].title.startswith("A device")


def test_merge_prefers_richer_record() -> None:
    a = Paper(id="1", source="pubmed", title="T")
    b = Paper(id="2", source="openalex", title="T", pmcid="PMC1", abstract="long", is_oa=True)
    _merge(a, b)
    assert a.pmcid == "PMC1" and a.abstract == "long" and a.is_oa
    assert a.source == "openalex+pubmed"
