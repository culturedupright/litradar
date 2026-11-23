from __future__ import annotations

from pathlib import Path

from litradar import credentials, groups, identity, oecd, proposal, team
from litradar.models import Paper
from litradar import sources as source_module
from litradar.sources import _crossref_year, _inverted, _merge, _parse_pubmed, search_all, tokens

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
    removed = credentials.clear_expired()
    assert removed and removed[0]["source"] == "wos"
    assert credentials.active("wos") is None
    assert not credentials.status("wos")["configured"]
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
    assert "研究群学术水平" in weak["gaps"]


def test_oecd_full_taxonomy_and_classify() -> None:
    assert len(oecd.FIELDS) == 42
    assert oecd.get("2.5").label_en == "Materials engineering"
    assert oecd.label_full("2.5").startswith("2 工程与技术")
    assert oecd.validate("9.9") == "" and oecd.validate("2") == "2"
    tags = oecd.classify("HfO2 memristor thin film device")
    assert tags and tags[0]["code"] in ("2.5", "2.2")
    dist = oecd.distribution(["memristor thin film", "memristor device", "rice yield"],
                             "2.5")
    assert dist["total"] == 3 and dist["fit"] >= 0.5


def test_team_quick_derive_conditions_and_schema() -> None:
    profile = team.defaults()
    profile["identity"].update({"research_group": "草地微生物研究中心",
                                "group_id": "lzu-caoye-microbial-center",
                                "org": "全国重点实验室",
                                "group_size": "9 人以上", "project": "国家级项目"})
    profile = team.quick_derive(profile)
    assert profile["dims"]["pi"]["level"] == 3
    assert profile["dims"]["platform"]["level"] == 5
    assert profile["conditions"]["period"] == "1 年"
    assert team.evaluate(profile)["score"] >= 3.5
    schema = team.schema()
    assert schema["identity"] and schema["conditions"]
    keys = [row["key"] for row in schema["identity"]]
    assert "research_group" in keys and "author_title" not in keys
    assert schema["dimensions"][0]["options"][0]["criteria"]


def test_team_derive_uses_publication_evidence() -> None:
    profile = team.defaults()
    profile["identity"].update({"org": "普通高校院系",
                                "group_size": "1 人", "project": "无在研项目"})
    profile["conditions"].update({"budget": "5 万以内", "period": "3 个月"})
    evidence = {"works_count": 30, "recent_works": 10, "corresponding_count": 3,
                "platform_hint": "省部级重点实验室/平台"}
    profile = team.quick_derive(profile, evidence)
    assert profile["dims"]["pi"]["level"] >= 3
    assert profile["dims"]["foundation"]["level"] >= 3
    assert profile["dims"]["platform"]["level"] >= 3


def test_chinese_name_variants_for_openalex() -> None:
    import pytest

    pytest.importorskip("pypinyin")
    variants = identity._name_variants("石遵计")
    assert any("Shi" in v and "Zun" in v for v in variants)


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


def test_proposal_intl_structure_and_handoff_metadata(tmp_path: Path) -> None:
    md = proposal.build("忆阻器", SUMMARY, CARDS, AUDIT, mode="intl", field_code="2.5",
                        platform="湿+干", budget="5–20 万", period="1 年",
                        team_profile=None, owner="潘鹏旭")
    for title in ("Abstract", "1. Introduction and Problem Statement",
                  "2. Literature Review and Research Gap",
                  "3. Research Questions and Hypotheses",
                  "4. Theoretical / Conceptual Framework",
                  "5. Research Design and Methodology",
                  "6. Data, Materials, and Ethical Considerations",
                  "7. Timeline and Budget", "8. Expected Outcomes and Contribution",
                  "9. Risk, Limitations, and Mitigation", "10. References"):
        assert title in md
    assert "Appendix A" in md and "Appendix C" in md
    assert "待申请人补充" in md

    meta = proposal.metadata("忆阻器", SUMMARY, CARDS, AUDIT, mode="intl",
                             field_code="2.5", owner="潘鹏旭", markdown_text=md,
                             query="memristor", framework="PSPP")
    assert meta["mode"] == "intl"
    assert meta["sections"][1]["title"].startswith("1. Introduction")
    assert meta["evidence"]["cards"] == 1
    assert meta["content_sha256"]

    package = proposal.write_package(tmp_path, "忆阻器", SUMMARY, CARDS, AUDIT,
                                     mode="intl", field_code="2.5", owner="潘鹏旭",
                                     query="memristor", framework="PSPP")
    assert Path(package["markdown"]).exists()
    assert Path(package["metadata"]).exists()
    assert Path(package["sources"]).exists()
    assert (tmp_path / "assets" / "README.md").exists()
    assert "C1" in Path(package["sources"]).read_text(encoding="utf-8-sig")
    assert (tmp_path / "proposal.preview.docx").exists() is False

    cn_meta = proposal.metadata("忆阻器", SUMMARY, CARDS, AUDIT, mode="cn",
                                field_code="2.5", markdown_text="# 忆阻器：开题报告")
    assert cn_meta["doc_type"] == "cn_kaiti_report"
    assert cn_meta["sections"][0]["title"] == "一、立项依据"
    assert "[C1]" in md  # 参考文献使用 C 级引文编号


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


def test_source_catalog_is_ordered_by_authority() -> None:
    rows = credentials.all_status()
    keys = [row["source"] for row in rows]
    assert keys[:3] == ["wos", "scopus", "cnki"]
    assert keys.index("wanfang") < keys.index("pubmed")
    assert keys.index("pubmed") < keys.index("openalex") < keys.index("arxiv")
    assert credentials.status("cnki")["direct"] is False
    assert credentials.status("cnki")["access"] == "subscription"
    assert "校园网" in credentials.status("cnki")["help"]


def test_crossref_year_falls_back() -> None:
    assert _crossref_year({"published-print": {"date-parts": [[2021, 5]]}}) == 2021
    assert _crossref_year({"issued": {"date-parts": [[2023]]}}) == 2023
    assert _crossref_year({}) is None


def test_search_all_keeps_source_tier(monkeypatch) -> None:
    monkeypatch.setitem(source_module.BACKENDS, "crossref",
                        lambda q, k, y, n: [Paper(id="10/x", source="crossref", title="T")])
    papers, stats = search_all("test", [], "2020-2024", 5, ["crossref"])
    assert papers and stats[0]["ok"] and stats[0]["tier"] == "开放元数据"


def test_team_has_dora_and_reporting_standards() -> None:
    profile = team.defaults()
    assert profile["conditions"]["assessment"].startswith("DORA")
    assert profile["conditions"]["reporting"] == "不适用"
    schema = team.schema()
    keys = [c["key"] for c in schema["conditions"]]
    assert "ethics" in keys and "data_policy" in keys and "reporting" in keys
    md = "\n".join(team.markdown_block(profile))
    assert "DORA" in md and "ARRIVE" in md and "FAIR" in md


def test_team_full_unit_combines_institution_and_department() -> None:
    profile = team.defaults()
    profile["identity"].update({"unit": "兰州大学", "department": "草地农业科技学院",
                                "unit_ror": "https://ror.org/01mkqqe32",
                                "research_group": "草地微生物研究中心",
                                "group_id": "lzu-caoye-microbial-center"})
    md = "\n".join(team.markdown_block(profile))
    assert "兰州大学草地农业科技学院" in md
    assert "ROR" in md and "研究群目录 ID" in md
    assert "通讯作者" not in md


def test_local_directory_has_formal_units_and_aliases() -> None:
    center = groups.get("lzu-caoye-microbial-center")
    assert center and center["name"] == "草地微生物研究中心"
    assert center["leader"] == "南志标"
    assert "草地土壤微生物" in center["directions"]
    assert groups.search_local("草微")[0]["id"] == "lzu-caoye-microbial-center"
    assert groups.search_local("草保")[0]["id"] == "lzu-caoye-grassland-protection"


def test_local_directory_contains_management_institutes() -> None:
    rows = groups.search_local("数智供应链管理研究所")
    assert rows and rows[0]["id"] == "lzu-management-digital-supply-chain"
    assert rows[0]["unit"] == "兰州大学"
    assert rows[0]["department"] == "管理学院"
    assert rows[0]["line"] == "local"


def test_local_directory_covers_lzu_colleges_and_marxism() -> None:
    rows = groups.search_local("马克思主义学院", limit=20)
    assert len(rows) >= 5
    names = {row["name"] for row in rows}
    assert "马克思主义基本原理研究所" in names
    assert "思想政治教育研究所" in names
    exact = groups.search_local("马克思主义基本原理研究所")
    assert exact and exact[0]["name"] == "马克思主义基本原理研究所"
    assert exact[0]["department"] == "马克思主义学院"
    lit = groups.search_local("文学院", limit=20)
    assert any(row["name"] == "中国古代文学与古典文献学研究所" for row in lit)
    stats = groups.local_store.stats()
    assert stats["lzu_units"] >= 300
    assert stats["lzu_departments"] >= 30
    assert "其他高校" in stats["coverage_note"]


def test_local_directory_contains_moe_university_base() -> None:
    rows = groups.search_local("兰州大学", limit=5)
    assert rows and rows[0]["type"] == "university"
    assert rows[0]["name"] == "兰州大学"
    stats = groups.local_store.stats()
    assert stats["total"] >= 3196
    assert stats["by_source"]["教育部名单"] == 3196


def test_group_identity_patch_and_evidence() -> None:
    group = groups.get("lzu-caoye-microbial-center")
    assert group
    patch = groups.identity_patch(group)
    assert patch["unit"] == "兰州大学"
    assert patch["department"] == "草地农业科技学院"
    assert patch["unit_ror"] == "https://ror.org/01mkqqe32"
    assert patch["group_id"] == "lzu-caoye-microbial-center"
    assert patch["org"] == "全国重点实验室"
    assert "南志标" in patch["group_leader"]
    evidence = groups.evidence(group)
    assert evidence["has_leader"] and evidence["direction_count"] == 4
    assert evidence["verified"] == "2026-11-22"


def test_group_global_ror_normalizes_parent_and_child() -> None:
    item = {
        "id": "https://ror.org/036xfaa94",
        "names": [
            {"value": "State Key Lab of Grassland Agroecosystem", "lang": "en", "types": ["ror_display"]},
            {"value": "草地农业生态系统国家重点实验室", "lang": "zh", "types": ["label"]},
        ],
        "types": ["facility"],
        "locations": [{"geonames_details": {"country_code": "CN", "country_name": "China"}}],
        "links": [{"type": "website", "value": "https://skl.example.edu.cn"}],
        "relationships": [{"type": "parent", "id": "https://ror.org/01mkqqe32", "label": "Lanzhou University"}],
    }
    group = groups._normalize_ror(item)
    assert group
    assert group["id"] == "ror:036xfaa94"
    assert group["name_zh"].startswith("草地农业生态系统")
    assert group["unit"] == "Lanzhou University"
    assert group["department"].startswith("State Key Lab")
    assert group["unit_ror"] == "https://ror.org/01mkqqe32"
    assert group["source_label"] == "ROR"


def test_group_global_openalex_uses_parent_and_no_duplicate_department() -> None:
    item = {
        "id": "https://openalex.org/I4210154168",
        "display_name": "Max Planck Institute for Biogeochemistry",
        "type": "facility",
        "ror": "https://ror.org/051yxp643",
        "country_code": "DE",
        "lineage": ["https://openalex.org/I149899117", "https://openalex.org/I4210154168"],
        "homepage_url": "https://www.bgc-jena.mpg.de",
        "associated_institutions": [{
            "id": "https://openalex.org/I149899117",
            "ror": "https://ror.org/01hhn8329",
            "display_name": "Max Planck Society",
            "country_code": "DE",
            "type": "nonprofit",
            "relationship": "parent",
        }],
    }
    group = groups._normalize_openalex(item)
    assert group
    assert group["unit"] == "Max Planck Society"
    assert group["department"] == ""
    assert group["parent_name"] == "Max Planck Society"
    assert group["unit_ror"] == "https://ror.org/01hhn8329"
    patch = groups.identity_patch(group)
    assert patch["unit"] == "Max Planck Society"
    assert patch["department"] == ""
    assert patch["research_group"] == "Max Planck Institute for Biogeochemistry"


def test_group_identity_patch_drops_department_equal_to_group_name() -> None:
    item = {
        "id": "https://ror.org/036xfaa94",
        "names": [{"value": "State Key Lab of Grassland Agroecosystem", "lang": "en", "types": ["ror_display"]}],
        "types": ["facility"],
        "relationships": [{"type": "parent", "id": "https://ror.org/01mkqqe32", "label": "Lanzhou University"}],
    }
    group = groups._normalize_ror(item)
    patch = groups.identity_patch(group)
    assert patch["unit"] == "Lanzhou University"
    assert patch["department"] == ""
    assert patch["research_group"].startswith("State Key Lab")


def test_group_search_merges_global_sources_without_lzu(monkeypatch) -> None:
    ror = {"id": "ror:051yxp643", "source_kind": "ror", "source_label": "ROR",
           "name": "Max Planck Institute for Biogeochemistry", "name_zh": "",
           "short": "", "type": "facility", "type_label": "实验室/设施",
           "unit": "Max Planck Society", "department": "Max Planck Institute for Biogeochemistry",
           "unit_ror": "https://ror.org/04z8jv273", "leader": "", "members": [],
           "directions": [], "platform": "", "platform_level": "", "source": "https://www.bgc-jena.mpg.de",
           "verified": "", "score": 100, "ids": {"ror": "https://ror.org/051yxp643"}}
    openalex = {"id": "openalex:I4210109156", "source_kind": "openalex", "source_label": "OpenAlex",
                "name": "Max Planck Institute for Astronomy", "name_zh": "",
                "short": "MPIA", "type": "facility", "type_label": "实验室/设施",
                "unit": "Max Planck Society", "department": "Max Planck Institute for Astronomy",
                "unit_ror": "", "leader": "", "members": [], "directions": [],
                "platform": "", "platform_level": "", "source": "https://www.mpia.de",
                "verified": "", "score": 80, "ids": {"openalex": "https://openalex.org/I4210109156"}}
    monkeypatch.setattr(groups, "_search_ror", lambda q, limit=8: [ror])
    monkeypatch.setattr(groups, "_search_openalex", lambda q, limit=8: [openalex])
    monkeypatch.setattr(groups, "_search_wikidata", lambda q, limit=5: [])
    rows = groups.search("Max Planck Institute", limit=5)
    assert rows and rows[0]["source_kind"] == "ror"
    assert any(row["source_kind"] == "openalex" for row in rows)


def test_two_lines_never_mix_and_empty_query_is_empty() -> None:
    assert groups.search("") == []
    assert groups.search_local("") == []
    assert groups.search_global("") == []
    assert groups.search("草微中心", line="local")[0]["id"] == "lzu-caoye-microbial-center"
    assert all(row["line"] == "local" for row in groups.search("草微中心", line="local"))


def test_import_local_units_csv(tmp_path) -> None:
    store = groups.local_store
    old_path, old_cache = store.STORE_PATH, store._CACHE
    try:
        store.STORE_PATH = tmp_path / "local_units.json"
        store._CACHE = None
        text = "名称,简称,单位,院系,负责人,来源\n测试研究中心,测中,兰州大学,测试学院,张三,https://example.org\n"
        result = store.import_text(text)
        assert result["added"] == 1
        rows = store.search("测中")
        assert rows and rows[0]["name"] == "测试研究中心"
        assert rows[0]["leader"] == "张三"
    finally:
        store.STORE_PATH, store._CACHE = old_path, old_cache


def test_team_schema_has_no_corresponding_author_fields() -> None:
    keys = [row["key"] for row in team.schema()["identity"]]
    assert "research_group" in keys and "group_leader" in keys
    assert "author" not in keys and "author_title" not in keys
    labels = [row["label"] for row in team.schema()["identity"]]
    assert any("研究群" in label for label in labels)


def _ror_fixture() -> dict:
    return {"items": [
        {"id": "https://ror.org/01mkqqe32", "names": [
            {"value": "Lanzhou University", "lang": "en", "types": ["ror_display", "label"]},
            {"value": "兰州大学", "lang": "zh", "types": ["label"]}],
         "locations": [{"geonames_details": {"country_code": "CN", "country_name": "China"}}],
         "types": ["education"], "domains": ["lzu.edu.cn"],
         "links": [{"type": "website", "value": "https://www.lzu.edu.cn"}],
         "relationships": [{"type": "child", "label": "State Key Laboratory of Herbage Improvement"}]},
        {"id": "https://ror.org/05d2xpa49", "names": [
            {"value": "First Hospital of Lanzhou University", "lang": "en", "types": ["ror_display"]}],
         "locations": [{"geonames_details": {"country_code": "CN", "country_name": "China"}}],
         "types": ["healthcare"], "relationships": []},
    ]}


def test_identity_ror_prefers_parent_university(monkeypatch) -> None:
    monkeypatch.setattr(identity, "_json", lambda url: _ror_fixture())
    rows = identity.ror_search("兰州大学草地农业科技学院")
    assert rows and rows[0]["ror"] == "01mkqqe32"
    assert rows[0]["name_zh"] == "兰州大学"
    assert rows[0]["children"]


def test_identity_author_filter_recent_ror(monkeypatch) -> None:
    data = {"results": [
        {"id": "https://openalex.org/A1", "display_name": "Wei Zhang",
         "raw_author_names": ["Wei Zhang", "张伟"], "orcid": "https://orcid.org/0000-0001-0000-0001",
         "works_count": 40,
         "affiliations": [{"institution": {"display_name": "Lanzhou University",
                                            "ror": "https://ror.org/01mkqqe32",
                                            "country_code": "CN"}, "years": [2025]}],
         "last_known_institutions": []},
        {"id": "https://openalex.org/A2", "display_name": "Wei Zhang",
         "raw_author_names": ["Wei Zhang"], "works_count": 200,
         "affiliations": [{"institution": {"display_name": "Oklahoma State University",
                                            "ror": "https://ror.org/01g9vbr38",
                                            "country_code": "US"}, "years": [2026]}],
         "last_known_institutions": []},
    ]}
    monkeypatch.setattr(identity, "_json", lambda url: data)
    rows = identity.author_search("Wei Zhang", "https://ror.org/01mkqqe32")
    assert len(rows) == 1 and rows[0]["id"] == "A1"
    assert rows[0]["confidence"] == "高"
    assert rows[0]["institutions"][0]["name"] == "Lanzhou University"


def test_identity_works_corresponding_and_departments(monkeypatch) -> None:
    data = {"results": [{
        "id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/x",
        "title": "Grassland carbon", "publication_year": 2025, "type": "article",
        "primary_location": {"source": {"display_name": "Journal"}},
        "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Wei Zhang"},
                         "author_position": "last", "is_corresponding": True,
                         "raw_affiliation_strings": [
                             "College of Pastoral Agriculture Science and Technology, Lanzhou University"]}],
    }]}
    monkeypatch.setattr(identity, "_json", lambda url: data)
    out = identity.author_works("A1", "Wei Zhang", "Lanzhou University")
    assert out["works"][0]["is_corresponding"]
    assert any("Pastoral" in x["value"] for x in out["departments"])
    assert "通讯作者" in out["representative_suggestion"]


def test_identity_doi_check(monkeypatch) -> None:
    def fake(url: str) -> dict:
        if "crossref" in url:
            return {"message": {"title": ["A paper"], "container-title": ["J"],
                                "issued": {"date-parts": [[2025]]},
                                "author": [{"given": "Wei", "family": "Zhang",
                                            "ORCID": "https://orcid.org/0000-0001-0000-0001",
                                            "affiliation": [{"name": "Lanzhou University"}]}]}}
        return {"authorships": [{"author": {"display_name": "Wei Zhang"},
                                  "raw_author_name": "Wei Zhang", "is_corresponding": True,
                                  "institutions": [{"ror": "https://ror.org/01mkqqe32"}]}]}
    monkeypatch.setattr(identity, "_json", fake)
    out = identity.doi_check("10.1/x", "Wei Zhang", "Lanzhou University",
                             "https://ror.org/01mkqqe32")
    assert out["ok"] and out["confidence"] == "高"
    assert out["corresponding"] == ["Wei Zhang"]
    assert all(x["ok"] for x in out["checks"])
