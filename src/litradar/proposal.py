"""开题报告：双模式 Markdown 生成 + 排版交接包。

- cn：国内通行九节骨架（立项依据→目标→内容→方案→创新→可行性→成果→进度→文献）。
- intl：国际 research proposal 结构（问题陈述→文献缺口→研究问题→理论框架→方法→伦理→进度预算→预期贡献→风险→文献）。

正文只写能从证据里推出来的话；推不出的地方明确写“待申请人补充”，不编实验参数、不编团队数据。
Word 只保留“预览版”，正式排版交给下游排版 agent。
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from . import oecd, team

MODE_CN = "cn"
MODE_INTL = "intl"
MODE_LABELS = {
    MODE_CN: "国内开题报告（九节骨架）",
    MODE_INTL: "国际 Research Proposal",
}
MODE_ALIASES = {
    "cn": MODE_CN,
    "china": MODE_CN,
    "domestic": MODE_CN,
    "国内": MODE_CN,
    "开题": MODE_CN,
    "intl": MODE_INTL,
    "international": MODE_INTL,
    "research_proposal": MODE_INTL,
    "research proposal": MODE_INTL,
    "research-proposal": MODE_INTL,
    "国际": MODE_INTL,
}


def normalize_mode(mode: str | None) -> str:
    value = str(mode or MODE_CN).strip().lower()
    return MODE_ALIASES.get(value, MODE_CN)


def _bullets(items: list[dict], key: str, extra: str = "") -> list[str]:
    out = []
    for item in items:
        text = ""
        for candidate in (key, "point", "gap", "title"):
            value = str(item.get(candidate) or "").strip()
            if value:
                text = value
                break
        if not text:
            continue
        suffix = ""
        papers = [p for p in (item.get("papers") or []) if p]
        if papers:
            suffix = "（" + "、".join(papers[:4]) + "）"
        tail = str(item.get(extra) or "").strip()
        if tail:
            text = text.rstrip("。；;，, ")
        out.append(f"- {text}" + (f"：{tail}" if tail else "") + suffix)
    return out or ["- 现有证据不足以支撑这一条，需补充文献。"]


def _gap_text(item: dict) -> str:
    for key in ("gap", "point", "title"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _period(text: str) -> str:
    text = str(text or "").strip().rstrip("。；;，, ")
    if not text:
        return ""
    return text + ("." if not text.endswith((".", "!", "?")) else "")


def _refs(cards: list[dict]) -> list[str]:
    refs = []
    for index, card in enumerate(cards, start=1):
        title = str(card.get("title") or "").rstrip(".")
        journal = str(card.get("journal") or "")
        year = card.get("year") or ""
        doi = card.get("doi") or ""
        pmcid = card.get("pmcid") or ""
        tail = " ".join(x for x in (journal, str(year)) if x)
        ident = f"DOI: {doi}" if doi else (pmcid if pmcid else "")
        refs.append(f"[C{index}] {title}. {tail}. {ident}".strip())
    return refs


def _timeline(period: str) -> list[str]:
    if period in ("3 个月",):
        stages = [("第 1 月", "文献与方案定稿、材料/数据准备"),
                  ("第 2 月", "主体实验/计算与中期核对"),
                  ("第 3 月", "补充验证、成文")]
    elif period in ("6 个月",):
        stages = [("第 1–2 月", "方案定稿、预实验/数据准备"),
                  ("第 3–4 月", "主体实验/计算"),
                  ("第 5 月", "补充验证与复现"),
                  ("第 6 月", "成文与答辩材料")]
    elif period in ("2 年以上",):
        stages = [("第 1–3 月", "文献综述、方案与预实验"),
                  ("第 4–9 月", "主体实验/计算与阶段核对"),
                  ("第 10–15 月", "补充验证、复现与扩展场景"),
                  ("第 16–24 月", "成文、投稿与结题材料")]
    else:
        stages = [("第 1–3 月", "文献综述、方案与预实验"),
                  ("第 4–7 月", "主体实验/计算与阶段核对"),
                  ("第 8–10 月", "补充验证、复现与数据分析"),
                  ("第 11–12 月", "成文、投稿/答辩")]
    return [f"- {when}：{what}" for when, what in stages]


def _route_rows() -> list[tuple[str, str, str, str]]:
    return [
        ("问题锚定", "把 1.3 的空白转成 1–2 个可检验假说", "假说可被数据否定", "1.3 与方向候选"),
        ("体系与对照", "确定研究系统、处理组与对照组", "对照与处理只差一个变量", "证据矩阵“设计/对照”列"),
        ("制备/干预", "按已发表方案执行，参数逐项落表", "关键参数可复现", "卡片“工艺参数/处理”字段"),
        ("表征/读出", "选与假说直接相关的指标，先做预实验", "指标有基线、有重复", "卡片“表征检测/读出”字段"),
        ("复现与统计", "独立重复，报告效应量与区间", "重复间变异可解释", "开放获取原文的方法节"),
    ]


def _stats_line(audit: dict) -> str:
    bits = [f"本次检索覆盖 {audit.get('candidates', 0)} 篇候选，同域保留 {audit.get('kept', 0)} 篇"]
    span = audit.get("year_range") or []
    if span:
        bits.append(f"年份 {span[0]}–{span[1]}")
    journals = audit.get("top_journals") or []
    if journals:
        bits.append("主要期刊：" + "、".join(f"{j['journal']}（{j['count']}）" for j in journals[:4]))
    return "；".join(bits) + "。"


def _appendices(cards: list[dict], audit: dict, stats: list[dict] | None,
                mode: str = MODE_CN) -> list[str]:
    intl = normalize_mode(mode) == MODE_INTL
    title_a = "Appendix A: Evidence Matrix" if intl else "附录 A　证据矩阵"
    title_b = "Appendix B: Search Audit" if intl else "附录 B　检索体检"
    title_c = "Appendix C: Cards and Evidence Locations" if intl else "附录 C　单篇卡片与证据定位"
    table_head = (["Paper ID", "Design", "System", "Treatment/Process", "n", "Readout", "Conclusion"]
                  if intl else ["文献 ID", "设计", "体系", "处理/工艺", "n", "检测", "结论"])
    lines: list[str] = ["", "---", "", f"# {title_a}", ""]
    lines += ["| " + " | ".join(table_head) + " |",
              "| " + " | ".join(["---"] * len(table_head)) + " |"]
    for card in cards:
        cells = [card.get("pmcid", ""), card.get("design", ""), card.get("system", ""),
                 card.get("factors", ""), card.get("sample_size", ""),
                 card.get("omics", ""), card.get("conclusion", "")]
        lines.append("| " + " | ".join(re.sub(r"\s+", " ", str(c)).replace("|", "/")[:80]
                                       for c in cells) + " |")

    lines += ["", f"# {title_b}", ""]
    if stats:
        lines.append("- 检索源：" + "；".join(
            f"{s['label']} {s['count']} 篇" + (f"（失败：{s['error']}）" if not s["ok"] else "")
            for s in stats))
    lines.append(f"- 候选 {audit.get('candidates', 0)} 篇，同域 {audit.get('kept', 0)} 篇，"
                 f"挡掉 {audit.get('dropped', 0)} 篇，阈值 {audit.get('threshold', 0)}")
    if audit.get("dropped_samples"):
        lines.append("- 被挡样例：" + "；".join(
            f"{s.get('title', '')}（{s.get('reason', '')}）" for s in audit["dropped_samples"][:3]))

    lines += ["", f"# {title_c}", ""]
    for card in cards:
        lines += [f"## {card.get('pmcid', '')} · {card.get('title', '')}", ""]
        for key, label in (("design", "设计"), ("system", "体系/结构"), ("factors", "处理/工艺"),
                           ("controls", "对照"), ("sample_size", "样本量"), ("omics", "表征/检测"),
                           ("outcomes", "结果"), ("conclusion", "结论"), ("limitations", "局限")):
            lines.append(f"- **{label}**：{card.get(key, '')}")
        evidence = card.get("evidence") or []
        if evidence:
            lines += ["", "证据定位："]
            for item in evidence:
                mark = "已核" if item.get("verified") else "待核"
                lines.append(f"- [{mark}] {item.get('location', '')}：{item.get('quote', '')[:160]}")
        lines.append("")
    return lines


def _cn_header(direction: str, field: str, audit: dict, owner: str,
               platform: str, budget: str, period: str) -> list[str]:
    return [
        f"# {direction}：开题报告", "",
        f"**学科分类（OECD）**：{field or '未指定'}　　"
        f"**归纳口径**：{audit.get('framework', '') or '未判定'}", "",
        f"**申请人**：{owner or '（待填）'}　　**研究类型**：{platform}　　"
        f"**经费量级**：{budget}　　**周期**：{period}", "",
        "**引文编号**：C1 起，对应 `sources.csv`；正式参考文献格式由下游按 `citation_style` 重排。", "",
        "---", "",
    ]


def _build_cn(direction: str, summary: dict, cards: list[dict], audit: dict | None,
              *, field_code: str = "", platform: str = "不限", budget: str = "不限",
              period: str = "不限", wet_lab: str = "接受",
              team_profile: dict | None = None, owner: str = "",
              stats: list[dict] | None = None) -> str:
    audit = audit or {}
    summary = summary or {}
    field = oecd.label_full(field_code) or oecd.label(field_code)
    first = (summary.get("directions") or [{}])[0]
    gaps = summary.get("gaps") or []
    consensus = summary.get("consensus") or []
    controversies = summary.get("controversies") or []

    lines: list[str] = []
    lines += _cn_header(direction, field, audit, owner, platform, budget, period)

    # 一、立项依据
    lines += ["## 一、立项依据", "", "### 1.1 研究背景与意义", ""]
    if consensus:
        lines.append("本方向已有工作集中在以下几点：")
        lines += _bullets(consensus, "point")
    else:
        lines.append("本方向尚未形成可归纳的共识，需申请人补充综述。")
    if audit.get("candidates"):
        lines += ["", _stats_line(audit)]
    lines += ["", "### 1.2 国内外研究现状", ""]
    if controversies:
        lines.append("现有研究在以下问题上尚未对齐：")
        lines += _bullets(controversies, "point", "sides")
    else:
        lines.append("现有研究之间没有形成明确争议，多以单点报道为主。")
    lines += ["", "逐篇设计与结论见附录 A 证据矩阵；这里只保留可支撑论证的要点。"]
    lines += ["", "### 1.3 现有研究的不足（本课题的切入点）", ""]
    lines += _bullets(gaps, "gap", "why")

    # 二、研究目标
    lines += ["", "## 二、研究目标", ""]
    if first.get("hypothesis"):
        lines.append(f"- **总目标**：围绕「{direction}」，检验“{first.get('hypothesis')}”这一核心假说，"
                     f"给出可复现的设计与读出指标。")
    else:
        lines.append(f"- **总目标**：围绕「{direction}」建立可复现的研究设计，并给出可检验的核心假说（待申请人补充）。")
    for index, item in enumerate(summary.get("directions", [])[:3], start=1):
        if item.get("title"):
            lines.append(f"- **分目标 {index}**：{item['title']}——{item.get('rationale', '')}")
    if not summary.get("directions"):
        lines += ["- 分目标：需在完成文献综述后确定（现有证据不足，不代拟）。"]

    # 三、研究内容
    lines += ["", "## 三、研究内容", ""]
    directions = summary.get("directions") or []
    if directions:
        for index, item in enumerate(directions[:3], start=1):
            lines += [f"### 内容 {index}：{item.get('title', '')}", ""]
            lines.append(str(item.get("rationale") or ""))
            if item.get("design"):
                lines.append(f"- 最小实验设计：{item['design']}")
            if item.get("readout"):
                lines.append(f"- 读出指标：{item['readout']}")
            lines.append("")
    else:
        lines += ["证据不足，暂不划分研究内容；建议先补 5–8 篇同域核心文献再定。", ""]

    # 四、研究方案与技术路线
    lines += ["## 四、研究方案与技术路线", "", "### 4.1 总体路线", ""]
    lines.append("文献锚定问题 → 选定体系与对照 → 制备/干预 → 表征与读出 → 复现与统计 → 结论与边界。"
                 "每一步的输入、方法与判据对应下表，未定参数以“待定”标注，不做假填写。")
    lines += ["", "| 阶段 | 做什么 | 判据/读出 | 依据 |", "| --- | --- | --- | --- |"]
    for row in _route_rows():
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "### 4.2 关键技术与复刻要点", ""]
    patterns = summary.get("figure_patterns") or []
    if patterns:
        for pattern in patterns[:5]:
            lines.append(f"- **{pattern.get('type', '')}**：{pattern.get('purpose', '')}；"
                         f"复刻要点：{pattern.get('how_to_replicate', '')}")
    else:
        lines.append("- 暂无可复刻的图表套路，需补充方法学文献。")
    lines += ["", f"平台与条件约束：研究类型 {platform}，经费 {budget}，周期 {period}，"
                 f"湿实验 {wet_lab}。超出条件的步骤在 4.3 写替代方案。"]

    # 五、创新点
    lines += ["", "## 五、创新点", ""]
    if gaps:
        for index, item in enumerate(gaps[:3], start=1):
            text = _gap_text(item)
            lines.append(f"{index}. 针对“{text}”，本课题给出可复现的设计与判据。")
    else:
        lines.append("现有证据不足，创新点需在补文献后提炼（不代拟）。")

    # 六、可行性
    lines += ["", "## 六、可行性分析", ""]
    lines += team.markdown_block(team_profile)
    lines += ["", "### 理论与技术可行性", "",
              "- 理论与技术依据来自附录 A 中已核引文的原文，未核部分标“待核”，不作为可行性论据。",
              "- 关键步骤若依赖本单位不具备的设备，需在方案中写外协或合作单位（待申请人补充）。"]

    # 七、预期成果
    lines += ["", "## 七、预期成果", "",
              "- 一份可复现的研究方案与参数表（含对照、样本量与判据）。",
              "- 一套原始数据与可追溯的分析脚本（按数据管理规范归档）。",
              "- 一篇研究论文或阶段性报告；如形成方法改进，另报专利/软件著作权（按单位要求）。"]

    # 八、进度
    lines += ["", "## 八、进度安排", ""]
    lines += _timeline(period)
    lines += ["", "> 上述节点按可投入周期倒排；具体月份以入学/立项时间为准，由申请人落日历。"]

    # 九、参考文献
    lines += ["", "## 九、参考文献", ""]
    refs = _refs(cards)
    lines += refs or ["[1] 待补：本次没有生成卡片，参考文献需申请人补充。"]

    lines += _appendices(cards, audit, stats)
    lines += ["", "---", "",
              "本报告的研究目标、内容与创新点来自本次检索到的同域文献；"
              "未能从证据中确定的参数与条件标为“待定/待申请人补充”，不代填。"]
    return "\n".join(lines)


def _intl_abstract(direction: str, summary: dict, audit: dict) -> str:
    consensus = summary.get("consensus") or []
    gaps = summary.get("gaps") or []
    first = (summary.get("directions") or [{}])[0]
    parts = [f"This proposal addresses the research direction: {direction}."]
    if consensus:
        parts.append("Existing evidence indicates that " + _period(consensus[0].get("point", "")))
    else:
        parts.append("The current evidence base is insufficient to establish a consensus.")
    if gaps:
        parts.append("The principal gap identified in this run is: " + _period(_gap_text(gaps[0])))
    else:
        parts.append("A concrete research gap still needs to be specified by the applicant.")
    if first.get("hypothesis"):
        parts.append("The core hypothesis to be tested is: " + _period(first.get("hypothesis", "")))
    else:
        parts.append("The core hypothesis is to be completed by the applicant.")
    parts.append("The study will use an evidence-anchored design; specific materials, sample size, "
                 "statistical power and ethical approvals are marked as pending applicant input.")
    return " ".join(parts)


def _intl_header(direction: str, field: str, audit: dict, owner: str,
                 platform: str, budget: str, period: str) -> list[str]:
    return [
        f"# Research Proposal: {direction}", "",
        "**Structure**：International research proposal（中文稿；英文标题，正文可由下游翻译/排版）", "",
        f"**OECD field**：{field or '未指定'}　　**Evidence framework**：{audit.get('framework', '') or '未判定'}", "",
        f"**Applicant**：{owner or '（待填）'}　　**Study type**：{platform}　　"
        f"**Budget level**：{budget}　　**Duration**：{period}", "",
        "**Citation IDs**：C1… map to `sources.csv`; the formal reference style is applied downstream according to `citation_style`.", "",
        "---", "",
    ]


def _build_intl(direction: str, summary: dict, cards: list[dict], audit: dict | None,
                *, field_code: str = "", platform: str = "不限", budget: str = "不限",
                period: str = "不限", wet_lab: str = "接受",
                team_profile: dict | None = None, owner: str = "",
                stats: list[dict] | None = None) -> str:
    audit = audit or {}
    summary = summary or {}
    field = oecd.label_full(field_code) or oecd.label(field_code)
    first = (summary.get("directions") or [{}])[0]
    gaps = summary.get("gaps") or []
    consensus = summary.get("consensus") or []
    controversies = summary.get("controversies") or []
    patterns = summary.get("figure_patterns") or []

    lines: list[str] = []
    lines += _intl_header(direction, field, audit, owner, platform, budget, period)

    lines += ["## Abstract", "", _intl_abstract(direction, summary, audit), ""]

    lines += ["## 1. Introduction and Problem Statement", ""]
    lines.append(f"This proposal investigates **{direction}**. The purpose is to convert the identified "
                 "evidence into a testable research question, a reproducible design, and a clear statement "
                 "of expected contribution.")
    if consensus:
        lines += ["", "The current evidence base includes the following accepted points:"]
        lines += _bullets(consensus, "point")
    else:
        lines += ["", "No stable consensus was found in this run; the applicant must supplement the literature review."]
    if audit.get("candidates"):
        lines += ["", _stats_line(audit)]

    lines += ["", "## 2. Literature Review and Research Gap", ""]
    if controversies:
        lines.append("The literature is not aligned on the following issues:")
        lines += _bullets(controversies, "point", "sides")
    else:
        lines.append("The retrieved literature does not show a clear controversy; most reports are single-case observations.")
    lines += ["", "The gap that this proposal intends to address is:"]
    lines += _bullets(gaps, "gap", "why")
    lines += ["", "A full evidence matrix is provided in Appendix A; only claims supported by retrieved cards are used in the main text."]

    lines += ["", "## 3. Research Questions and Hypotheses", ""]
    if first.get("hypothesis"):
        lines.append(f"- **RQ1 / core hypothesis**：{first.get('hypothesis')}")
    else:
        lines.append("- **RQ1 / core hypothesis**：待申请人补充（现有证据不足以形成可检验假说）。")
    for index, item in enumerate(summary.get("directions", [])[:3], start=1):
        if item.get("title"):
            lines.append(f"- **RQ{index + 1}**：{item.get('title')}——{item.get('rationale', '')}")
            if item.get("design"):
                lines.append(f"  - Minimal design：{item['design']}")
            if item.get("readout"):
                lines.append(f"  - Readout：{item['readout']}")
    if not summary.get("directions"):
        lines.append("- **RQ2–3**：待申请人补充；建议先补 5–8 篇同域核心文献。")

    lines += ["", "## 4. Theoretical / Conceptual Framework", ""]
    framework = audit.get("framework") or "未判定"
    lines.append(f"本稿暂以 {framework} 作为证据组织框架；正式的理论框架、概念模型与变量关系"
                 "需由申请人结合学科理论补充。现有卡片不足以自动生成理论框架，系统不代拟。")

    lines += ["", "## 5. Research Design and Methodology", ""]
    lines.append("The proposed route is: problem anchoring → system and controls → preparation/intervention → "
                 "characterisation/readout → replication and statistics → conclusion and boundary conditions.")
    lines += ["", "| Stage | What to do | Criterion / readout | Evidence basis |", "| --- | --- | --- | --- |"]
    for row in _route_rows():
        lines.append("| " + " | ".join(row) + " |")
    if patterns:
        lines += ["", "### Replicable figure and assay patterns", ""]
        for pattern in patterns[:5]:
            lines.append(f"- **{pattern.get('type', '')}**：{pattern.get('purpose', '')}；"
                         f"replication notes：{pattern.get('how_to_replicate', '')}")
    lines += ["", "**Sample size, statistical power, randomisation, blinding, and statistical models**："
                 "待申请人补充；本稿不伪造这些参数。"]

    lines += ["", "## 6. Data, Materials, and Ethical Considerations", ""]
    lines += [f"- Study type：{platform}；budget level：{budget}；duration：{period}；wet-lab：{wet_lab}。",
              "- Data sources and inclusion/exclusion criteria：见附录 B 检索体检；正式方案需补充数据管理计划（DMP）。",
              "- Ethics / biosafety / privacy approvals：待申请人按所在单位要求补充；未获批前不开展相关实验。",
              "- Open-science practice：只使用开放获取全文；无法获取全文的条目只做题录级证据，并标注“待核”。"]
    if team_profile:
        lines += ["", "### Team and feasibility", ""]
        lines += team.markdown_block(team_profile)

    lines += ["", "## 7. Timeline and Budget", ""]
    lines += _timeline(period)
    lines += ["", f"Budget level：{budget}。Detailed budget lines, co-funding and procurement are to be completed by the applicant."]

    lines += ["", "## 8. Expected Outcomes and Contribution", ""]
    lines += ["- **Theoretical contribution**：针对本文识别出的证据缺口，给出可检验的解释或机制假设（待申请人细化）。",
              "- **Methodological contribution**：形成一套可复现的对照、读出与统计方案，并保留证据定位。",
              "- **Practical / policy contribution**：形成可交付的阶段报告、数据与代码；应用场景待申请人确认。"]
    if gaps:
        lines += ["", "The expected contribution is tied to the following gaps:"]
        lines += _bullets(gaps[:3], "gap")

    lines += ["", "## 9. Risk, Limitations, and Mitigation", ""]
    lines += ["- **Data access risk**：开放全文不足时，退到题录级证据，不绕付费墙；关键文献由申请人通过机构权限补全。",
              "- **Feasibility risk**：设备、样本或周期不匹配时，缩小目标、增加合作单位或改为干实验验证。",
              "- **Ethics / compliance risk**：未取得伦理、生物安全或数据授权前，不启动相关实验。",
              "- **Negative-result risk**：预注册判据；结果不支持假说时，如实报告边界，不修改判据。",
              "- **Evidence risk**：所有引文需人工复核；“待核”字段不得进入最终结论。"]

    lines += ["", "## 10. References", ""]
    refs = _refs(cards)
    lines += refs or ["[1] 待补：本次没有生成卡片，参考文献需申请人补充。"]

    lines += _appendices(cards, audit, stats, mode=MODE_INTL)
    lines += ["", "---", "",
              "本稿由 LitRadar 按国际 research proposal 结构生成（中文稿）；"
              "理论框架、样本量、统计功效、伦理审批等未能从证据中确定的字段，均标为待申请人补充。"]

    return "\n".join(lines)


def build(direction: str, summary: dict, cards: list[dict], audit: dict | None,
          *, mode: str = MODE_CN, field_code: str = "", platform: str = "不限",
          budget: str = "不限", period: str = "不限", wet_lab: str = "接受",
          team_profile: dict | None = None, owner: str = "",
          stats: list[dict] | None = None) -> str:
    mode = normalize_mode(mode)
    if mode == MODE_INTL:
        return _build_intl(direction, summary, cards, audit, field_code=field_code,
                           platform=platform, budget=budget, period=period,
                           wet_lab=wet_lab, team_profile=team_profile, owner=owner,
                           stats=stats)
    return _build_cn(direction, summary, cards, audit, field_code=field_code,
                     platform=platform, budget=budget, period=period,
                     wet_lab=wet_lab, team_profile=team_profile, owner=owner,
                     stats=stats)


def _section_titles(mode: str) -> list[dict]:
    if normalize_mode(mode) == MODE_INTL:
        titles = [
            ("abstract", "Abstract"),
            ("introduction", "1. Introduction and Problem Statement"),
            ("literature", "2. Literature Review and Research Gap"),
            ("questions", "3. Research Questions and Hypotheses"),
            ("framework", "4. Theoretical / Conceptual Framework"),
            ("methodology", "5. Research Design and Methodology"),
            ("data_ethics", "6. Data, Materials, and Ethical Considerations"),
            ("timeline_budget", "7. Timeline and Budget"),
            ("outcomes", "8. Expected Outcomes and Contribution"),
            ("risk", "9. Risk, Limitations, and Mitigation"),
            ("references", "10. References"),
            ("appendix_a", "Appendix A: Evidence Matrix"),
            ("appendix_b", "Appendix B: Search Audit"),
            ("appendix_c", "Appendix C: Cards and Evidence Locations"),
        ]
    else:
        titles = [
            ("basis", "一、立项依据"),
            ("objectives", "二、研究目标"),
            ("contents", "三、研究内容"),
            ("methodology", "四、研究方案与技术路线"),
            ("innovation", "五、创新点"),
            ("feasibility", "六、可行性分析"),
            ("outcomes", "七、预期成果"),
            ("timeline", "八、进度安排"),
            ("references", "九、参考文献"),
            ("appendix_a", "附录 A　证据矩阵"),
            ("appendix_b", "附录 B　检索体检"),
            ("appendix_c", "附录 C　单篇卡片与证据定位"),
        ]
    return [{"id": key, "title": title, "level": 1} for key, title in titles]


def metadata(direction: str, summary: dict, cards: list[dict], audit: dict | None,
             *, mode: str = MODE_CN, field_code: str = "", platform: str = "不限",
             budget: str = "不限", period: str = "不限", wet_lab: str = "接受",
             owner: str = "", stats: list[dict] | None = None,
             markdown_text: str = "", query: str = "", pico: dict | None = None,
             framework: str = "") -> dict:
    mode = normalize_mode(mode)
    summary = summary or {}
    audit = audit or {}
    verified = total = 0
    for card in cards:
        for item in (card.get("evidence") or []):
            total += 1
            if item.get("verified"):
                verified += 1
    template_id = "intl_general_v1" if mode == MODE_INTL else "cn_general_v1"
    return {
        "schema": "litradar.proposal/1",
        "doc_type": "research_proposal" if mode == MODE_INTL else "cn_kaiti_report",
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "language": "zh",
        "heading_language": "en" if mode == MODE_INTL else "zh",
        "title": direction,
        "author": owner or "",
        "template": {
            "id": template_id,
            "label": MODE_LABELS[mode],
            "source": "LitRadar 通用骨架，不是官方模板",
            "school": "",
            "notes": "学校/资助方模板请通过 template 覆盖层替换；不要直接删改章节。",
        },
        "sections": _section_titles(mode),
        "citation_style": "APA 7（待按学校/资助方确认）" if mode == MODE_INTL else "GB/T 7714（待按学校模板确认）",
        "word_limit": None,
        "word_limit_note": "按学校/资助方模板填写；本稿不写死字数。",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "content_sha256": hashlib.sha256(markdown_text.encode("utf-8")).hexdigest() if markdown_text else "",
        "query": query,
        "pico": pico or {},
        "framework": framework or audit.get("framework", ""),
        "oecd": oecd.label_full(field_code) or oecd.label(field_code),
        "constraints": {"platform": platform, "budget": budget, "period": period, "wet_lab": wet_lab},
        "evidence": {
            "cards": len(cards),
            "consensus": len(summary.get("consensus") or []),
            "controversies": len(summary.get("controversies") or []),
            "gaps": len(summary.get("gaps") or []),
            "figure_patterns": len(summary.get("figure_patterns") or []),
            "directions": len(summary.get("directions") or []),
            "evidence_verified": verified,
            "evidence_total": total,
            "candidates": audit.get("candidates", 0),
            "kept": audit.get("kept", 0),
            "dropped": audit.get("dropped", 0),
        },
        "sources": stats or [],
        "assets": [],
        "handoff": {
            "markdown": "proposal.md",
            "metadata": "proposal.meta.json",
            "sources_csv": "sources.csv",
            "assets_dir": "assets",
            "preview_docx": "proposal.preview.docx",
            "note": "正式 Word/PDF 由下游排版 agent 读取 Markdown + metadata 后生成；插件不负责正式版式。",
        },
    }


def _source_rows(cards: list[dict]) -> list[dict]:
    rows = []
    for index, card in enumerate(cards, start=1):
        evidence = card.get("evidence") or []
        rows.append({
            "ref_id": f"C{index}",
            "pmcid": card.get("pmcid", ""),
            "title": card.get("title", ""),
            "journal": card.get("journal", ""),
            "year": card.get("year", ""),
            "doi": card.get("doi", ""),
            "evidence_verified": sum(1 for item in evidence if item.get("verified")),
            "evidence_total": len(evidence),
            "evidence_scope": card.get("evidence_scope", "全文"),
        })
    return rows


def write_sources_csv(path: Path, cards: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = _source_rows(cards)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "ref_id", "pmcid", "title", "journal", "year", "doi",
            "evidence_verified", "evidence_total", "evidence_scope",
        ])
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_package(run_dir: Path, direction: str, summary: dict, cards: list[dict],
                  audit: dict | None, *, mode: str = MODE_CN, field_code: str = "",
                  platform: str = "不限", budget: str = "不限", period: str = "不限",
                  wet_lab: str = "接受", team_profile: dict | None = None,
                  owner: str = "", stats: list[dict] | None = None,
                  query: str = "", pico: dict | None = None, framework: str = "") -> dict:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    md = build(direction, summary, cards, audit, mode=mode, field_code=field_code,
               platform=platform, budget=budget, period=period, wet_lab=wet_lab,
               team_profile=team_profile, owner=owner, stats=stats)
    md_path = run_dir / "proposal.md"
    md_path.write_text(md, encoding="utf-8")
    meta = metadata(direction, summary, cards, audit, mode=mode, field_code=field_code,
                    platform=platform, budget=budget, period=period, wet_lab=wet_lab,
                    owner=owner, stats=stats, markdown_text=md, query=query,
                    pico=pico, framework=framework)
    meta_path = run_dir / "proposal.meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    sources_path = write_sources_csv(run_dir / "sources.csv", cards)
    assets_dir = run_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    asset_readme = assets_dir / "README.md"
    if not asset_readme.exists():
        asset_readme.write_text(
            "# 交接素材\n\n"
            "把论文原图、复刻图、流程图放在这个目录；在 `proposal.md` 中用相对路径引用，"
            "例如 `![图1](assets/fig1.png)`。正式版式由下游排版 agent 生成。\n",
            encoding="utf-8",
        )
    return {
        "markdown": str(md_path),
        "metadata": str(meta_path),
        "sources": str(sources_path),
        "assets": str(assets_dir),
        "mode": normalize_mode(mode),
    }


def write_markdown(path: Path, *args, **kwargs) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build(*args, **kwargs), encoding="utf-8")
    return path


def write_docx(md_path: Path, docx_path: Path, title: str) -> Path | None:
    """生成“预览版”Word；正式版式交给下游排版 agent，不追求排版质量。"""
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt
    except ImportError:
        return None
    text = md_path.read_text(encoding="utf-8")
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(12)
    style.paragraph_format.line_spacing = 1.5

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line == "---":
            continue
        if line.startswith("# "):
            paragraph = doc.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = paragraph.add_run(line[2:].strip())
            run.bold = True
            run.font.size = Pt(18)
            continue
        if line.startswith("## "):
            paragraph = doc.add_paragraph()
            run = paragraph.add_run(line[3:].strip())
            run.bold = True
            run.font.size = Pt(15)
            continue
        if line.startswith("### "):
            paragraph = doc.add_paragraph()
            run = paragraph.add_run(line[4:].strip())
            run.bold = True
            run.font.size = Pt(13)
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r"[-: ]*", c or "") for c in cells):
                continue
            table = getattr(doc, "_last_table", None)
            if table is None:
                table = doc.add_table(rows=0, cols=len(cells))
                table.style = "Table Grid"
                doc._last_table = table  # type: ignore[attr-defined]
            row = table.add_row().cells
            for idx, cell in enumerate(cells[:len(row)]):
                row[idx].text = cell
            continue
        doc._last_table = None  # type: ignore[attr-defined]
        if line.startswith("- ") or re.match(r"^\d+\.\s", line):
            paragraph = doc.add_paragraph(line.lstrip("- ").strip(), style="List Bullet")
            paragraph.paragraph_format.line_spacing = 1.5
            continue
        clean = line.replace("**", "")
        doc.add_paragraph(clean)
    doc.save(docx_path)
    return docx_path
