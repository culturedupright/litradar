from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .llm import Usage, chat, extract_json

FIELDS = (
    "design", "system", "factors", "controls", "sample_size",
    "omics", "outcomes", "conclusion", "limitations",
)

SYSTEM_PROMPT = """你是植物-微生物互作与多组学领域的文献信息抽取助手。
只依据用户给出的论文文本做抽取，不得引入外部知识，不得编造数字。
每条结论必须给出一条原文引句（英文原句，逐字复制），并注明位置（如 "Results, 2nd paragraph"、"Fig. 3 caption"）。
找不到证据的字段填 "待核"。只输出 JSON，不要解释。"""

SCHEMA_HINT = """{
  "design": "实验设计（盆栽/温室/田间/小鼠/体外/纯干分析）",
  "system": "研究系统与材料（物种、品种、根际/叶片等）",
  "factors": "处理因素与剂量",
  "controls": "对照组设置",
  "sample_size": "样本量/重复数（n=...），没有就写 待核",
  "omics": "组学与检测层（16S/ITS/代谢组/转录组/生理指标等）",
  "outcomes": "主要结局指标",
  "conclusion": "作者的核心结论（一句话）",
  "limitations": "作者承认的局限或设计上的明显短板",
  "evidence": [
    {"field": "conclusion", "quote": "原文英文句子", "location": "Results / Fig. 3 caption"}
  ]
}"""


def _normal(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Card:
    data: dict
    usage: Usage = field(default_factory=Usage)
    verified: int = 0
    total_evidence: int = 0


def build_prompt(title: str, journal: str, year: int | None,
                 figures: list[dict], text: str, max_chars: int = 12000) -> str:
    fig_lines = []
    for fig in figures[:15]:
        fig_lines.append(f"- {fig.get('label', '')} ({fig.get('kind', 'figure')}): {fig.get('caption', '')[:400]}")
    body = text[:max_chars]
    return f"""论文：{title}
期刊/年份：{journal} / {year}

图表清单：
{chr(10).join(fig_lines) or "（无图表信息）"}

正文（可能被截断）：
{body}

请按以下 JSON 结构输出：
{SCHEMA_HINT}
"""


def validate(card: dict, source_text: str) -> Card:
    data = {key: str(card.get(key) or "待核").strip() for key in FIELDS}
    evidence = card.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = []
    source = _normal(source_text)
    kept, total = [], len(evidence)
    for item in evidence[:20]:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        if not quote:
            continue
        hit = _normal(quote) in source
        kept.append({
            "field": str(item.get("field") or ""),
            "quote": quote,
            "location": str(item.get("location") or "待核"),
            "verified": hit,
        })
    # 某字段只有未核实的证据时，降级为待核，避免把幻觉当结论
    for item in kept:
        if not item["verified"] and item["field"] in data:
            data[item["field"]] = "待核"
    return Card(
        data={**data, "evidence": kept},
        verified=sum(1 for item in kept if item["verified"]),
        total_evidence=total,
    )


def make_card(title: str, journal: str, year: int | None,
              figures: list[dict], text: str,
              model_name: str = "deepseek") -> Card:
    prompt = build_prompt(title, journal, year, figures, text)
    reply, usage = chat(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": prompt}],
        model_name=model_name,
        temperature=0.1,
    )
    card = validate(extract_json(reply), text + "\n" + "\n".join(
        f.get("caption", "") for f in figures))
    card.usage = usage
    return card
