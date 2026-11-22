from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import oecd, proposal, team
from .aggregate import summarize
from .cards import make_card
from .config import DB_PATH, FULLTEXT_DIR, RUNS_DIR, ensure_dirs
from .domain import Domain, by_key, classify
from .fulltext import FullText, fetch_fulltext
from .llm import chat, extract_json
from .relevance import audit as audit_retrieval
from .relevance import judge, relax_query, topic_terms
from .report import write_markdown
from .sources import search_all
from .store import (connect, figures_for, get_cards, get_fulltext, get_paper,
                    pending_abstracts, pending_cards, pending_fulltexts, save_card,
                    save_fulltext, save_report, set_gate, to_csv, upsert)

Progress = Callable[[str, str, int], None]
Note = Callable[[str], None]


def _n(note: Note | None, text: str) -> None:
    """往界面日志里补一条，不改变百分比。"""
    if note:
        try:
            note(text)
        except Exception:  # noqa: BLE001
            pass


def plan_prompt(domain: Domain, field_code: str = "") -> str:
    field = oecd.get(field_code)
    scope = ""
    if field:
        terms = "、".join(field.keywords[:12])
        scope = (f"\n学科口径：OECD/Frascati {oecd.label(field_code)}（{field.label_en}）。"
                 f"该子类的英文主题词包括：{terms}。检索式要落在这一口径的专业义上，"
                 f"至少覆盖其中 2 个词，不要扩展到其他学科的同形义。\n")
    return f"""把下面的中文研究方向翻成 Europe PMC 能用的英文布尔检索式。
要求：只用英文关键词与同义词，用 OR 连接同义词、用 AND 连接不同概念；不要加年份。
同义词扩展必须留在本学科内：不要把本领域词扩展到别的学科的常用义（例如材料学方向里的
"neural network" 不要扩展成神经科学词汇，也不要引入 plant、mouse、patient 这类实验词）。
{scope}同时按 {domain.framework} 把方向拆成四格，键名固定为 population / intervention /
comparison / outcome，中文含义按该范式解释：{domain.framework_hint}没有的留空。
另外给一个 keywords 数组：6–12 个英文核心词（含同义词），供 PubMed / Web of Science /
Scopus / OpenAlex 这些不支持同一套布尔语法的库使用。
只输出 JSON：{{"query": "...", "keywords": ["..."], "framework_name": "{domain.framework}",
"pico": {{"population": "", "intervention": "", "comparison": "", "outcome": ""}}}}"""


def _step(cb: Progress, name: str, detail: str, percent: int) -> None:
    if cb:
        cb(name, detail, max(0, min(100, percent)))


def plan_query(direction: str, model_name: str,
               domain: Domain | None = None, field_code: str = "") -> tuple[str, dict, int, str, list[str]]:
    domain = domain or classify(direction)
    reply, usage = chat(
        [{"role": "system", "content": "你是文献检索专家，只输出 JSON。"},
         {"role": "user", "content": f"{plan_prompt(domain, field_code)}\n\n研究方向：{direction}"}],
        model_name=model_name,
        temperature=0.1,
    )
    data = extract_json(reply)
    query = str(data.get("query") or "").strip()
    if not query:
        query = direction
    framework = str(data.get("framework_name") or domain.framework)
    keywords = [str(k).strip() for k in (data.get("keywords") or []) if str(k).strip()]
    return query, data.get("pico") or {}, usage.total_tokens, framework, keywords


def run_pipeline(direction: str, *, platform: str = "不限", budget: str = "不限",
                 period: str = "不限", wet_lab: str = "接受",
                 years: str = "", search_limit: int = 40,
                 fetch_limit: int = 8, card_limit: int = 8,
                 model_name: str = "deepseek",
                 db_path: Path | str = DB_PATH,
                 domain_key: str = "auto",
                 sources_list: list[str] | None = None,
                 oecd_code: str = "",
                 team_profile: dict | None = None,
                 owner: str = "",
                 progress: Progress | None = None,
                 note: Note | None = None) -> dict:
    ensure_dirs()
    field_code = oecd.validate(oecd_code)
    if team_profile:
        cond = team.conditions(team_profile)
        platform = platform if platform and platform != "不限" else cond.get("experiment", platform)
        budget = budget if budget and budget != "不限" else cond.get("budget", budget)
        period = period if period and period != "不限" else cond.get("period", period)
        wet_lab = wet_lab if wet_lab and wet_lab != "接受" else cond.get("wet", wet_lab)
    conn = connect(db_path)
    started = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(RUNS_DIR) / started
    run_dir.mkdir(parents=True, exist_ok=True)
    tokens = 0
    source_stats: list[dict] = []

    if field_code:
        domain = by_key(oecd.domain_hint(field_code))
    elif domain_key and domain_key != "auto":
        domain = by_key(domain_key)
    else:
        domain = classify(direction)
    _step(progress, "判定学科", f"{domain.label}；归纳口径 {domain.framework}", 2)
    _n(note, f"学科判定：{domain.label}（闸门 {'开' if domain.gate else '关'}）"
             + (f"；OECD 分类：{oecd.label(field_code)}" if field_code else ""))

    _step(progress, "规划检索式", "正在把研究方向翻成英文检索式", 4)
    _n(note, f"方向：{direction[:60]}；模型：{model_name}")
    query, pico, used, framework, keywords = plan_query(direction, model_name, domain, field_code)
    tokens += used
    _step(progress, "规划检索式", f"检索式：{query[:120]}", 8)
    _n(note, f"检索式定稿：{query[:160]}")
    if keywords:
        _n(note, "核心词：" + "、".join(keywords[:10]))

    added, dropped = 0, 0
    decisions: list[dict] = []
    used_query = query
    papers = []
    for _attempt in range(3):
        papers, source_stats = search_all(used_query, keywords, years, search_limit,
                                          sources_list or ["europepmc"],
                                          oecd_code=oecd_code)
        _n(note, "检索源：" + "；".join(
            f"{s['label']} {s['count']} 篇" + ("" if s["ok"] else f"（失败：{s['error']}）")
            for s in source_stats))
        if papers:
            break
        relaxed = relax_query(used_query)
        if relaxed == used_query:
            break
        _n(note, f"检索 0 命中，去掉一个限制条件重试：{relaxed[:120]}")
        _step(progress, "检索", "0 命中，正在放宽检索式重试", 12)
        used_query = relaxed
    if papers:
        query = used_query
    terms = topic_terms(query)
    for paper in papers:
        upsert(conn, paper)
        added += 1
        verdict = judge(paper.title, paper.abstract, domain, terms)
        set_gate(conn, paper.id, verdict.score, verdict.keep, verdict.reason)
        decisions.append({
            "id": paper.id, "pmcid": paper.pmcid or "", "title": paper.title, "journal": paper.journal,
            "year": paper.year, "keep": verdict.keep, "score": verdict.score,
            "reason": verdict.reason,
        })
        if not verdict.keep:
            dropped += 1
        if added % 5 == 0:
            _n(note, f"检索：已收 {added} 条（同域 {added - dropped}，挡掉 {dropped}）")
    conn.commit()

    kept_ids = {d["id"] for d in decisions if d["keep"]}
    pmc_ids = {d["pmcid"] for d in decisions if d["keep"] and d["pmcid"].startswith("PMC")}
    run_ids = kept_ids | pmc_ids

    audit = audit_retrieval(domain, terms, decisions)
    audit["sources"] = source_stats
    audit["oecd"] = oecd.label(field_code) if field_code else ""
    audit["oecd_distribution"] = oecd.distribution(
        [f"{d.get('title', '')} {d.get('journal', '')}" for d in decisions if d.get("keep")],
        field_code)
    kept = audit["kept"]
    _step(progress, "相关性闸门",
          f"候选 {added} 篇，同域 {kept} 篇，挡掉 {dropped} 篇", 20)
    _n(note, f"闸门：候选 {added}，同域 {kept}，挡掉 {dropped}"
             + (f"（{audit['dropped_samples'][0]['reason']}）" if dropped else ""))

    if kept == 0:
        empty = {"consensus": [], "controversies": [], "gaps": [],
                 "figure_patterns": [], "directions": []}
        report_path = write_markdown(run_dir / "report.md", direction, [], [],
                                     empty, {}, audit=audit, domain=domain)
        proposal_path = proposal.write_markdown(
            run_dir / "开题报告.md", direction, empty, [], audit,
            field_code=field_code, platform=platform, budget=budget, period=period,
            wet_lab=wet_lab, team_profile=team_profile, owner=owner, stats=source_stats)
        docx_path = proposal.write_docx(proposal_path, run_dir / "开题报告.docx", direction)
        to_csv(conn, run_dir / "papers.csv", {d["id"] for d in decisions})
        (run_dir / "summary.json").write_text(
            json.dumps({"direction": direction, "query": query, "pico": pico,
                        "framework": framework, "domain": domain.key,
                        "audit": audit, "tokens": tokens, "summary": empty,
                        "sources": source_stats, "oecd": oecd.label(field_code)},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        save_report(conn, direction, empty, model_name, tokens)
        conn.commit()
        _step(progress, "完成", f"没有同域文献，已写体检报告：{report_path}", 100)
        return {"run_dir": str(run_dir), "report": str(report_path), "query": query,
                "proposal": str(proposal_path),
                "proposal_docx": str(docx_path) if docx_path else "",
                "found": added, "kept": 0, "dropped": dropped, "fetched": 0,
                "cards": 0, "summary": empty, "cards_data": [], "figures": {},
                "tokens": tokens, "domain": domain.key, "audit": audit,
                "sources": source_stats}

    targets = pending_fulltexts(conn, fetch_limit, pmc_ids)
    fetched = 0
    for index, (pmcid, _title) in enumerate(targets, start=1):
        _step(progress, "抓全文", f"{pmcid}（{index}/{len(targets)}）", 20 + int(18 * index / max(1, len(targets))))
        _n(note, f"抓全文 {pmcid}（{index}/{len(targets)}）：请求 Europe PMC")
        try:
            ft, raw = fetch_fulltext(pmcid)
            xml_path = Path(FULLTEXT_DIR) / f"{pmcid}.xml"
            xml_path.parent.mkdir(parents=True, exist_ok=True)
            xml_path.write_bytes(raw)
            save_fulltext(conn, ft, xml_path)
            conn.commit()
            fetched += 1
            _n(note, f"✓ {pmcid} 全文 {len(ft.text)} 字、图表 {len(ft.figures)} 个")
        except Exception as exc:  # noqa: BLE001
            save_fulltext(conn, FullText(pmcid=pmcid, status="error"), None, error=str(exc))
            conn.commit()
            _n(note, f"× {pmcid} 抓全文失败：{str(exc)[:80]}")
        time.sleep(1.0)
    _step(progress, "抓全文", f"成功 {fetched}/{len(targets)} 篇", 40)

    cards = [c for c in get_cards(conn) if c["pmcid"] in run_ids]
    carded_ids = {c["pmcid"] for c in cards}
    todo = [pmcid for pmcid in pending_cards(conn, card_limit, run_ids)
            if pmcid not in carded_ids]
    new_cards = 0
    for index, pmcid in enumerate(todo, start=1):
        info = get_fulltext(conn, pmcid)
        if not info:
            continue
        _step(progress, "抽卡片", f"{pmcid}（{index}/{len(todo)}）", 40 + int(30 * index / max(1, len(todo))))
        figs = [f.__dict__ for f in figures_for(conn, pmcid)]
        _n(note, f"抽卡片 {pmcid}（{index}/{len(todo)}）：{info['title'][:48]}｜全文 {len(info['text'])} 字")
        try:
            card = make_card(info["title"], info["journal"], info["year"], figs,
                             info["text"], model_name=model_name, domain=domain)
            data = {**card.data, "title": info["title"]}
            save_card(conn, pmcid, data, model_name,
                      card.usage.prompt_tokens, card.usage.completion_tokens)
            conn.commit()
            tokens += card.usage.total_tokens
            new_cards += 1
            _n(note, f"✓ {pmcid} 卡片完成（累计 {new_cards} 张，{tokens} tokens）")
        except Exception as exc:  # noqa: BLE001
            save_card(conn, pmcid, {"error": str(exc)}, model_name, status="error", error=str(exc))
            conn.commit()
            _n(note, f"× {pmcid} 卡片失败：{str(exc)[:80]}")
    _step(progress, "抽卡片", f"新增 {new_cards} 张卡片", 70)

    # 没有 PMC 全文的方向（社科、人文、工程、中文库）用摘要做卡片，字段一律按“待核”约束。
    current_cards = [c for c in get_cards(conn) if c["pmcid"] in run_ids]
    remaining = max(0, card_limit - len(current_cards))
    abstract_todo = pending_abstracts(conn, remaining, kept_ids)
    abstract_cards = 0
    for index, paper_id in enumerate(abstract_todo, start=1):
        info = get_paper(conn, paper_id)
        if not info or not info.get("abstract"):
            continue
        _step(progress, "抽卡片", f"摘要级 {index}/{len(abstract_todo)}", 70 + int(8 * index / max(1, len(abstract_todo))))
        _n(note, f"摘要卡片 {paper_id}：{info['title'][:48]}｜无 PMC 全文，按摘要抽取")
        try:
            card = make_card(info["title"], info["journal"], info["year"], [],
                             info["abstract"], model_name=model_name, domain=domain)
            data = {**card.data, "title": info["title"], "evidence_scope": "摘要级"}
            save_card(conn, paper_id, data, model_name,
                      card.usage.prompt_tokens, card.usage.completion_tokens)
            conn.commit()
            tokens += card.usage.total_tokens
            abstract_cards += 1
            _n(note, f"✓ {paper_id} 摘要级卡片完成（累计 {new_cards + abstract_cards} 张）")
        except Exception as exc:  # noqa: BLE001
            save_card(conn, paper_id, {"error": str(exc)}, model_name, status="error", error=str(exc))
            conn.commit()
            _n(note, f"× {paper_id} 摘要级卡片失败：{str(exc)[:80]}")
    if abstract_cards:
        _step(progress, "抽卡片", f"全文 {new_cards} 张 / 摘要级 {abstract_cards} 张", 78)

    all_cards = [c for c in get_cards(conn) if c["pmcid"] in run_ids]
    if not all_cards:
        summary = {"consensus": [], "controversies": [], "gaps": [],
                   "figure_patterns": [], "directions": []}
        _step(progress, "跨文献聚合", "没有卡片，跳过聚合，避免凭空编结论", 78)
        _n(note, "聚合：0 张卡片，跳过模型调用（防止无证据归纳）")
    else:
        _step(progress, "跨文献聚合", f"正在归纳 {len(all_cards)} 张卡片", 78)
        _n(note, f"聚合：把 {len(all_cards)} 张卡片放在一起比共识/争议/空白")
        constraints = (f"平台约束：{platform}；预算量级：{budget}；可投入周期：{period}；"
                       f"湿实验：{wet_lab}")
        summary, usage = summarize(f"{direction}\n{constraints}", all_cards,
                                   model_name=model_name, domain=domain)
        tokens += usage.total_tokens
        _n(note, f"✓ 聚合完成（{usage.total_tokens} tokens）")

    figs_map = {}
    for card in all_cards:
        figs_map[card["pmcid"]] = [f.__dict__ for f in figures_for(conn, card["pmcid"])]

    _step(progress, "生成简报", "正在写六件套 Markdown", 92)
    _n(note, "写简报：组装页签并落盘 report.md / papers.csv / summary.json")
    report_path = write_markdown(run_dir / "report.md", direction, all_cards, all_cards,
                                 summary, figs_map, audit=audit, domain=domain)
    _step(progress, "生成开题报告", "按通行九节骨架排版，附表进附录", 96)
    proposal_path = proposal.write_markdown(
        run_dir / "开题报告.md", direction, summary, all_cards, audit,
        field_code=field_code, platform=platform, budget=budget, period=period,
        wet_lab=wet_lab, team_profile=team_profile, owner=owner, stats=source_stats)
    docx_path = proposal.write_docx(proposal_path, run_dir / "开题报告.docx", direction)
    to_csv(conn, run_dir / "papers.csv", {d["id"] for d in decisions})
    (run_dir / "summary.json").write_text(
        json.dumps({"direction": direction, "platform": platform, "budget": budget,
                    "period": period, "wet_lab": wet_lab, "query": query,
                    "pico": pico, "framework": framework, "domain": domain.key,
                    "audit": audit, "search_limit": search_limit,
                    "fetch_limit": fetch_limit, "card_limit": card_limit,
                    "tokens": tokens, "summary": summary,
                    "sources": source_stats, "oecd": oecd.label(field_code)},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    save_report(conn, direction, summary, model_name, tokens)
    conn.commit()
    _step(progress, "完成", f"简报：{report_path}", 100)

    return {
        "run_dir": str(run_dir),
        "report": str(report_path),
        "proposal": str(proposal_path),
        "proposal_docx": str(docx_path) if docx_path else "",
        "query": query,
        "found": added,
        "kept": kept,
        "dropped": dropped,
        "fetched": fetched,
        "cards": len(all_cards),
        "summary": summary,
        "cards_data": all_cards,
        "figures": {k: v for k, v in figs_map.items()},
        "tokens": tokens,
        "domain": domain.key,
        "audit": audit,
        "sources": source_stats,
    }

