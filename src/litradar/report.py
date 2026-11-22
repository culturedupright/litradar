from __future__ import annotations

from pathlib import Path

from .domain import GENERAL, Domain


def _audit_block(audit: dict | None, domain: Domain | None) -> list[str]:
    if not audit:
        return []
    label = audit.get("domain_label") or (domain.label if domain else "")
    pct = f"{audit.get('keep_ratio', 0) * 100:.0f}%"
    lines = ["## 检索体检", ""]
    lines.append(f"- 学科判定：{label}；归纳口径：{audit.get('framework', '')}")
    if audit.get("oecd"):
        lines.append(f"- OECD 学科口径：{audit['oecd']}")
    dist = audit.get("oecd_distribution") or {}
    if dist.get("total"):
        tags = "；".join(f"{r['label']}（{r['count']}）" for r in (dist.get("counts") or [])[:5])
        line = f"- 同域文献的学科分布（按标题词表打标）：{tags or '无'}"
        if dist.get("untagged"):
            line += f"；未打标 {dist['untagged']} 篇"
        lines.append(line)
        if dist.get("selected") and dist.get("fit") is not None and dist["fit"] < 0.5:
            lines.append(f"- 提示：仅 {dist['fit'] * 100:.0f}% 的文献落在所选 OECD 子类，"
                         "口径可能选窄了，或方向本身跨子类。")
    lines.append(f"- 候选 {audit.get('candidates', 0)} 篇，同域保留 {audit.get('kept', 0)} 篇（{pct}），"
                 f"挡掉 {audit.get('dropped', 0)} 篇（阈值 {audit.get('threshold', 0)}）")
    if not audit.get("gate_enabled", True):
        lines.append("- 本次为通用方向，未启用领域闸门")
    journals = audit.get("top_journals") or []
    if journals:
        lines.append("- 期刊分布：" + "；".join(
            f"{item['journal']}（{item['count']}）" for item in journals))
    years = audit.get("year_range") or []
    if years:
        lines.append(f"- 年份跨度：{years[0]}–{years[1]}")
    terms = audit.get("topic_terms") or []
    if terms:
        lines.append("- 主题词：" + "、".join(terms[:10]))
    dropped = audit.get("dropped_samples") or []
    if dropped:
        lines += ["", "被挡掉的样例（不进全文抓取、不进卡片）："]
        for item in dropped[:5]:
            lines.append(f"- {item.get('title', '')} —— {item.get('reason', '')}")
    if audit.get("kept") == 0:
        lines += ["", "> 本次没有同域文献。后面的归纳不可用，请改写方向或检索式后重跑。"]
    lines.append("")
    return lines


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
                   summary: dict, figures: dict[str, list[dict]],
                   audit: dict | None = None,
                   domain: Domain | None = None) -> str:
    domain = domain or GENERAL
    out: list[str] = [f"# 题眼 LitRadar · 证据简报", "", f"**研究方向**：{direction}", ""]
    out += _audit_block(audit, domain)

    out += ["## 一、领域全景", "", "### 共识"]
    out += _bullets(summary.get("consensus", []), "point")
    out += ["", "### 争议"]
    out += _bullets(summary.get("controversies", []), "point", "sides")
    out += ["", "### 空白"]
    out += _bullets(summary.get("gaps", []), "gap", "why")
    out += [""]

    labels = dict(domain.card_labels or {})
    out += ["## 二、证据矩阵", "",
            f"| 文献 ID | {labels.get('design', '设计')} | {labels.get('system', '系统')} | "
            f"{labels.get('factors', '处理')} | {labels.get('sample_size', 'n')} | "
            f"{labels.get('omics', '检测')} | {labels.get('conclusion', '结论')} |",
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
        scope = "（摘要级，未核字段以“待核”为准）" if card.get("evidence_scope") == "摘要级" else ""
        out += [f"### {card.get('pmcid', '')} · {card.get('title', '')}{scope}", ""]
        labels = domain.card_labels or {}
        for key in ("design", "system", "factors", "controls", "sample_size",
                    "omics", "outcomes", "conclusion", "limitations"):
            out.append(f"- **{labels.get(key, key)}**：{card.get(key, '')}")
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
                   summary: dict, figures: dict[str, list[dict]],
                   audit: dict | None = None,
                   domain: Domain | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown(direction, papers, cards, summary, figures,
                                   audit=audit, domain=domain), encoding="utf-8")
    return path
