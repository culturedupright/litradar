from __future__ import annotations

from pathlib import Path


def _bullets(items: list[dict], title_key: str, extra_key: str = "") -> list[str]:
    lines = []
    for item in items:
        text = str(item.get(title_key) or "").strip()
        papers = ", ".join(item.get("papers") or [])
        extra = str(item.get(extra_key) or "").strip() if extra_key else ""
        suffix = f"（{papers}）" if papers else ""
        if extra:
            lines.append(f"- {text}：{extra}{suffix}")
        else:
            lines.append(f"- {text}{suffix}")
    return lines or ["- 证据不足"]


def build_markdown(direction: str, papers: list[dict], cards: list[dict],
                   summary: dict, figures: dict[str, list[dict]]) -> str:
    out: list[str] = [f"# 题眼 LitRadar · 证据简报", "", f"**研究方向**：{direction}", ""]

    out += ["## 一、领域全景", "", "### 共识"]
    out += _bullets(summary.get("consensus", []), "point")
    out += ["", "### 争议"]
    out += _bullets(summary.get("controversies", []), "point", "sides")
    out += ["", "### 空白"]
    out += _bullets(summary.get("gaps", []), "gap", "why")
    out += [""]

    out += ["## 二、证据矩阵", "",
            "| PMCID | 设计 | 系统 | 处理 | n | 组学/检测 | 核心结论 |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for card in cards:
        cells = [card.get("pmcid", ""), card.get("design", ""), card.get("system", ""),
                 card.get("factors", ""), card.get("sample_size", ""),
                 card.get("omics", ""), card.get("conclusion", "")]
        row = " | ".join(str(c).replace("|", "/").replace("\n", " ")[:80] for c in cells)
        out.append(f"| {row} |")
    out += [""]

    out += ["## 三、单篇卡片", ""]
    for card in cards:
        out += [f"### {card.get('pmcid', '')} · {card.get('title', '')}", ""]
        labels = {
            "design": "设计", "system": "系统", "factors": "处理因素",
            "controls": "对照", "sample_size": "样本量", "omics": "组学/检测",
            "outcomes": "结局", "conclusion": "结论", "limitations": "局限",
        }
        for key, label in labels.items():
            out.append(f"- **{label}**：{card.get(key, '')}")
        evidence = card.get("evidence") or []
        if evidence:
            out += ["", "证据定位："]
            for item in evidence:
                mark = "已核" if item.get("verified") else "待核"
                out.append(f"- [{mark}] {item.get('location', '')}：{item.get('quote', '')[:160]}")
        out += [""]

    out += ["## 四、图表复刻清单", ""]
    for pattern in summary.get("figure_patterns", []):
        out.append(f"- **{pattern.get('type', '')}**：{pattern.get('purpose', '')}")
        out.append(f"  - 复刻要点：{pattern.get('how_to_replicate', '')}")
    out += ["", "### 已抓到的原图（可直接对照）", ""]
    for pmcid, figs in figures.items():
        images = [f for f in figs if f.get("image_url")]
        if not images:
            continue
        out.append(f"**{pmcid}**")
        for fig in images[:12]:
            out.append(f"- {fig.get('label', '')}：{fig.get('caption', '')[:100]}")
            out.append(f"  - 原图：{fig.get('image_url', '')}")
        out += [""]

    out += ["## 五、方向候选", ""]
    for index, item in enumerate(summary.get("directions", []), start=1):
        out += [f"### 方向 {index}：{item.get('title', '')}", ""]
        out.append(f"- 理由：{item.get('rationale', '')}")
        out.append(f"- 可检验假说：{item.get('hypothesis', '')}")
        out.append(f"- 最小实验设计：{item.get('design', '')}")
        out.append(f"- 读出指标：{item.get('readout', '')}")
        out.append(f"- 适合：{item.get('fit', '')}；难度：{item.get('difficulty', '')}；预算：{item.get('budget', '')}")
        out.append(f"- 主要风险：{item.get('risk', '')}")
        out.append("")

    out += ["## 六、开题卡（以方向 1 为例）", ""]
    if summary.get("directions"):
        first = summary["directions"][0]
        out += [
            f"- **题目**：{first.get('title', '')}",
            f"- **科学问题**：{first.get('hypothesis', '')}",
            f"- **研究系统**：见证据矩阵中的系统列，优先选与你条件匹配的材料",
            f"- **处理与对照**：{first.get('design', '')}",
            f"- **读出指标**：{first.get('readout', '')}",
            f"- **工作量与预算**：{first.get('budget', '')}",
            f"- **风险与退路**：{first.get('risk', '')}",
            "",
        ]
    else:
        out += ["- 证据不足，暂不生成开题卡", ""]

    out += ["---", "",
            "本简报由 LitRadar 自动生成；卡片结论均要求原文引句定位，标“待核”的字段表示未找到可核对证据。"]
    return "\n".join(out)


def write_markdown(path: Path, direction: str, papers: list[dict], cards: list[dict],
                   summary: dict, figures: dict[str, list[dict]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown(direction, papers, cards, summary, figures), encoding="utf-8")
    return path
