from __future__ import annotations

from .domain import GENERAL, Domain
from .llm import Usage, chat, extract_json


def system_prompt(domain: Domain | None = None) -> str:
    domain = domain or GENERAL
    return f"""{domain.analyst_role}
只依据给出的卡片做归纳，不引入卡片之外的事实，不编造文献。
指出共识、争议、空白时，尽量标注来自哪些 PMCID；证据不足就写“证据不足”。
按 {domain.framework} 的口径组织结论：卡片缺哪一格，就说明哪一格是空白，不要替作者补。
输出严格 JSON。"""

SCHEMA = """{
  "consensus": [{"point": "...", "papers": ["PMC..."]}],
  "controversies": [{"point": "...", "sides": "...", "papers": ["PMC..."]}],
  "gaps": [{"gap": "...", "why": "...", "papers": ["PMC..."]}],
  "figure_patterns": [{"type": "...", "purpose": "...", "how_to_replicate": "...", "papers": ["PMC..."]}],
  "directions": [{
     "title": "...", "rationale": "...", "hypothesis": "...",
     "design": "...", "readout": "...", "fit": "干实验/湿实验",
     "difficulty": "低/中/高", "budget": "...", "risk": "..."
  }]
}"""


def _compact(card: dict) -> str:
    fields = ("design", "system", "factors", "controls", "sample_size",
              "omics", "outcomes", "conclusion", "limitations")
    lines = [f"PMCID: {card.get('pmcid')}", f"标题: {card.get('title', '')[:120]}"]
    for key in fields:
        lines.append(f"{key}: {str(card.get(key, ''))[:220]}")
    return "\n".join(lines)


def summarize(direction: str, cards: list[dict], model_name: str = "deepseek",
              max_cards: int = 12, domain: Domain | None = None) -> tuple[dict, Usage]:
    domain = domain or GENERAL
    blocks = "\n\n".join(_compact(c) for c in cards[:max_cards])
    prompt = f"""研究方向：{direction}
学科：{domain.label}；归纳口径：{domain.framework}

已抽取的文献卡片：
{blocks}

请输出：
1. 这个领域已经形成的共识（每条注明 PMCID）
2. 仍存在争议的点
3. 没人做或做得不够的空白
4. 图表套路：这些论文常用哪几类图，分别解决什么问题，复刻需要什么数据与工具
5. 3–5 个值得做的方向，每个给出理由、可检验假说、最小可行实验设计、读出指标、
   适合干实验还是湿实验、难度、预算量级、主要风险

按此 JSON 输出：
{SCHEMA}"""
    reply, usage = chat(
        [{"role": "system", "content": system_prompt(domain)},
         {"role": "user", "content": prompt}],
        model_name=model_name,
        temperature=0.3,
    )
    data = extract_json(reply)
    for key in ("consensus", "controversies", "gaps", "figure_patterns", "directions"):
        if not isinstance(data.get(key), list):
            data[key] = []
    return data, usage
