"""开题报告：按国内通行骨架（立项依据→目标→内容→方案→创新→可行性→成果→进度→文献）。

报告是交付物，卡片与证据矩阵退到附录；正文只写能从证据里推出来的话，
推不出的地方明确写“需申请人补充”，不编实验参数、不编团队数据。
"""
from __future__ import annotations

import re
from pathlib import Path

from . import oecd, team


def _bullets(items: list[dict], key: str, extra: str = "") -> list[str]:
    out = []
    for item in items:
        text = str(item.get(key) or "").strip()
        if not text:
            continue
        suffix = ""
        papers = [p for p in (item.get("papers") or []) if p]
        if papers:
            suffix = "（" + "、".join(papers[:4]) + "）"
        tail = str(item.get(extra) or "").strip()
        out.append(f"- {text}" + (f"：{tail}" if tail else "") + suffix)
    return out or ["- 现有证据不足以支撑这一条，需补充文献。"]


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
        refs.append(f"[{index}] {title}. {tail}. {ident}".strip())
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
    else:
        stages = [("第 1–3 月", "文献综述、方案与预实验"),
                  ("第 4–7 月", "主体实验/计算与阶段核对"),
                  ("第 8–10 月", "补充验证、复现与数据分析"),
                  ("第 11–12 月", "成文、投稿/答辩")]
    return [f"- {when}：{what}" for when, what in stages]


def build(direction: str, summary: dict, cards: list[dict], audit: dict | None,
          *, field_code: str = "", platform: str = "不限", budget: str = "不限",
          period: str = "不限", wet_lab: str = "接受",
          team_profile: dict | None = None, owner: str = "",
          stats: list[dict] | None = None) -> str:
    audit = audit or {}
    summary = summary or {}
    field = oecd.label(field_code)
    first = (summary.get("directions") or [{}])[0]
    gaps = summary.get("gaps") or []
    consensus = summary.get("consensus") or []
    controversies = summary.get("controversies") or []

    lines: list[str] = []
    lines += [f"# {direction}：开题报告", ""]
    lines += [f"**学科分类（OECD）**：{field or '未指定'}　　"
              f"**归纳口径**：{audit.get('framework', '') or '未判定'}", ""]
    lines += [f"**申请人**：{owner or '（待填）'}　　**实验类型**：{platform}　　"
              f"**经费量级**：{budget}　　**周期**：{period}", ""]
    lines += ["---", ""]

    # 一、立项依据
    lines += ["## 一、立项依据", "", "### 1.1 研究背景与意义", ""]
    if consensus:
        lines.append("本方向已有工作集中在以下几点：")
        lines += _bullets(consensus, "point")
    else:
        lines.append("本方向尚未形成可归纳的共识，需申请人补充综述。")
    if audit.get("candidates"):
        journals = audit.get("top_journals") or []
        span = audit.get("year_range") or []
        bits = [f"本次检索覆盖 {audit.get('candidates')} 篇候选，同域保留 {audit.get('kept', 0)} 篇"]
        if span:
            bits.append(f"年份 {span[0]}–{span[1]}")
        if journals:
            bits.append("主要期刊：" + "、".join(f"{j['journal']}（{j['count']}）" for j in journals[:4]))
        lines += ["", "；".join(bits) + "。"]
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
    route = [
        ("问题锚定", "把 1.3 的空白转成 1–2 个可检验假说", "假说可被数据否定", "1.3 与方向候选"),
        ("体系与对照", "确定研究系统、处理组与对照组", "对照与处理只差一个变量", "证据矩阵“设计/对照”列"),
        ("制备/干预", "按已发表方案执行，参数逐项落表", "关键参数可复现", "卡片“工艺参数/处理”字段"),
        ("表征/读出", "选与假说直接相关的指标，先做预实验", "指标有基线、有重复", "卡片“表征检测/读出”字段"),
        ("复现与统计", "独立重复，报告效应量与区间", "重复间变异可解释", "开放获取原文的方法节"),
    ]
    for row in route:
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "### 4.2 关键技术与复刻要点", ""]
    patterns = summary.get("figure_patterns") or []
    if patterns:
        for pattern in patterns[:5]:
            lines.append(f"- **{pattern.get('type', '')}**：{pattern.get('purpose', '')}；"
                         f"复刻要点：{pattern.get('how_to_replicate', '')}")
    else:
        lines.append("- 暂无可复刻的图表套路，需补充方法学文献。")
    lines += ["", f"平台与条件约束：实验类型 {platform}，经费 {budget}，周期 {period}，"
                 f"湿实验 {wet_lab}。超出条件的步骤在 4.3 写替代方案。"]

    # 五、创新点
    lines += ["", "## 五、创新点", ""]
    if gaps:
        for index, item in enumerate(gaps[:3], start=1):
            text = str(item.get("gap") or "").strip()
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

    # 附录
    lines += ["", "---", "", "# 附录 A　证据矩阵", ""]
    lines += ["| PMCID | 设计 | 体系 | 处理/工艺 | n | 检测 | 结论 |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for card in cards:
        cells = [card.get("pmcid", ""), card.get("design", ""), card.get("system", ""),
                 card.get("factors", ""), card.get("sample_size", ""),
                 card.get("omics", ""), card.get("conclusion", "")]
        lines.append("| " + " | ".join(re.sub(r"\s+", " ", str(c)).replace("|", "/")[:80]
                                       for c in cells) + " |")

    lines += ["", "# 附录 B　检索体检", ""]
    if stats:
        lines.append("- 检索源：" + "；".join(
            f"{s['label']} {s['count']} 篇" + (f"（失败：{s['error']}）" if not s["ok"] else "")
            for s in stats))
    lines.append(f"- 候选 {audit.get('candidates', 0)} 篇，同域 {audit.get('kept', 0)} 篇，"
                 f"挡掉 {audit.get('dropped', 0)} 篇，阈值 {audit.get('threshold', 0)}")
    if audit.get("dropped_samples"):
        lines.append("- 被挡样例：" + "；".join(
            f"{s.get('title', '')}（{s.get('reason', '')}）" for s in audit["dropped_samples"][:3]))

    lines += ["", "# 附录 C　单篇卡片与证据定位", ""]
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

    lines += ["---", "",
              "本报告的研究目标、内容与创新点来自本次检索到的同域文献；"
              "未能从证据中确定的参数与条件标为“待定/待申请人补充”，不代填。"]
    return "\n".join(lines)


def write_markdown(path: Path, *args, **kwargs) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build(*args, **kwargs), encoding="utf-8")
    return path


def write_docx(md_path: Path, docx_path: Path, title: str) -> Path | None:
    """把同一份内容排成 Word；没装 python-docx 时跳过，不阻塞主流程。"""
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
