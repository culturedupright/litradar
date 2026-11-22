from __future__ import annotations

from litradar.cards import schema_hint, system_prompt
from litradar.domain import AGRI, GENERAL, MATERIALS, classify
from litradar.relevance import audit, judge, relax_query, topic_terms
from litradar.report import build_markdown


def test_classify_materials() -> None:
    assert classify("忆阻器类脑神经网络").key == "materials"
    assert classify("钙钛矿太阳能电池的稳定性").key == "materials"


def test_classify_agri() -> None:
    assert classify("黄花棘豆内生真菌抗锈病").key == "agri"
    assert classify("根际微生物组与连作障碍").key == "agri"


def test_classify_biomed() -> None:
    assert classify("肿瘤患者队列的免疫治疗响应").key == "biomed"


def test_classify_falls_back_to_general() -> None:
    assert classify("某个我还没想清楚的方向") is GENERAL


def test_topic_terms_drops_not_clause_and_dates() -> None:
    query = ('(memristor OR RRAM) AND (neuromorphic) '
             'NOT (plant OR mouse) AND (FIRST_PDATE:[2015-01-01 TO 2026-12-31])')
    terms = topic_terms(query)
    assert "memristor" in terms and "neuromorphic" in terms
    assert "plant" not in terms and "mouse" not in terms
    assert "first_pdate" not in terms


def test_gate_drops_off_domain_paper() -> None:
    verdict = judge(
        "Integrated microbiome and metabolome analysis of banana rhizosphere soil",
        "Fusarium wilt resistance in banana; rhizosphere soil; 16S rRNA; field trial",
        MATERIALS, ["memristor", "neuromorphic", "rram"],
    )
    assert not verdict.keep
    assert "plant" in verdict.reason or "rhizosphere" in verdict.reason or "香蕉" in verdict.reason


def test_gate_keeps_on_domain_paper() -> None:
    verdict = judge(
        "Dual bipolar resistive switching in wafer-scalable 2D perovskite oxide memristor",
        "memristor based on 2D Sr2Nb3O10 nanosheets; I-V; retention; neuromorphic",
        MATERIALS, ["memristor", "neuromorphic", "rram"],
    )
    assert verdict.keep
    assert verdict.score > 0


def test_gate_passes_everything_for_general() -> None:
    verdict = judge("Whatever paper", "no keyword at all", GENERAL, ["x"])
    assert verdict.keep


def test_cards_prompt_is_domain_specific() -> None:
    assert "盆栽" not in schema_hint(MATERIALS)
    assert "制备" in schema_hint(MATERIALS)
    assert "盆栽" in schema_hint(AGRI)
    assert "材料" in system_prompt(MATERIALS) or "器件" in system_prompt(MATERIALS)


def test_relax_query_drops_last_and_group() -> None:
    q = '("A" OR "B") AND ("C" OR "D") AND ("E" OR "rust")'
    assert relax_query(q) == '("A" OR "B") AND ("C" OR "D")'
    assert relax_query('"single"') == '"single"'
    # 不在结尾的 AND 组不动，避免把主干削掉
    assert relax_query('"A" AND ("B") AND "C"') == '"A" AND ("B") AND "C"'


def test_audit_counts_and_samples() -> None:
    decisions = [
        {"title": "A", "keep": True, "score": 9.0, "reason": "", "journal": "Nature", "year": 2024},
        {"title": "B", "keep": False, "score": -5.0, "reason": "命中干扰词：plant", "journal": "Plant Soil", "year": 2020},
    ]
    result = audit(MATERIALS, ["memristor"], decisions)
    assert result["candidates"] == 2
    assert result["kept"] == 1 and result["dropped"] == 1
    assert result["keep_ratio"] == 0.5
    assert result["dropped_samples"][0]["title"] == "B"


def test_report_renders_audit_block() -> None:
    md = build_markdown("忆阻器类脑神经网络", [], [], {
        "consensus": [], "controversies": [], "gaps": [],
        "figure_patterns": [], "directions": [],
    }, {}, audit={
        "domain_label": "材料与器件", "framework": "PSPP",
        "candidates": 13, "kept": 5, "dropped": 8, "keep_ratio": 0.385,
        "threshold": 1.5, "gate_enabled": True, "topic_terms": ["memristor"],
        "top_journals": [{"journal": "Nature Communications", "count": 3}],
        "year_range": [2019, 2026],
        "dropped_samples": [{"title": "Banana rhizosphere", "reason": "命中干扰词：plant"}],
    }, domain=MATERIALS)
    assert "## 检索体检" in md
    assert "同域保留 5 篇" in md
    assert "Banana rhizosphere" in md
