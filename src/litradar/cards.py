from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .domain import GENERAL, Domain
from .llm import Usage, chat, extract_json

FIELDS = (
    "design", "system", "factors", "controls", "sample_size",
    "omics", "outcomes", "conclusion", "limitations",
)


def system_prompt(domain: Domain | None = None) -> str:
    domain = domain or GENERAL
    return f"""你是{domain.analyst_role}
只依据用户给出的论文文本做抽取，不得引入外部知识，不得编造数字。
每条结论必须给出一条原文引句（英文原句，逐字复制），并注明位置（如 "Results, 2nd paragraph"、"Fig. 3 caption"）。
各字段用中文填写（材料名、方法名、指标名等专有名词可保留英文原文）；引句一律保留英文原样，不要翻译。
找不到证据的字段填 "待核"。只输出 JSON，不要解释。"""


def schema_hint(domain: Domain | None = None) -> str:
    domain = domain or GENERAL
    fields = domain.card_fields or GENERAL.card_fields
    body = ",\n".join(f'  "{key}": "{fields[key]}"' for key in FIELDS if key in fields)
    return (
        "{\n" + body + ',\n'
        '  "evidence": [\n'
        '    {"field": "conclusion", "quote": "原文英文句子", '
        '"location": "Results / Fig. 3 caption"}\n'
        "  ]\n}"
    )


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
                 figures: list[dict], text: str, max_chars: int = 12000,
                 domain: Domain | None = None) -> str:
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
{schema_hint(domain)}
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
              model_name: str = "deepseek",
              domain: Domain | None = None) -> Card:
    domain = domain or GENERAL
    prompt = build_prompt(title, journal, year, figures, text, domain=domain)
    reply, usage = chat(
        [{"role": "system", "content": system_prompt(domain)},
         {"role": "user", "content": prompt}],
        model_name=model_name,
        temperature=0.1,
    )
    card = validate(extract_json(reply), text + "\n" + "\n".join(
        f.get("caption", "") for f in figures))
    card.usage = usage
    return card
