from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .aggregate import summarize
from .cards import make_card
from .config import DB_PATH, FULLTEXT_DIR, RUNS_DIR, ensure_dirs
from .europepmc import iter_papers
from .fulltext import FullText, fetch_fulltext
from .llm import chat, extract_json
from .report import write_markdown
from .store import (connect, figures_for, get_cards, get_fulltext,
                    pending_cards, pending_fulltexts, save_card,
                    save_fulltext, save_report, to_csv, upsert)

Progress = Callable[[str, str, int], None]

PLAN_PROMPT = """把下面的中文研究方向翻成 Europe PMC 能用的英文布尔检索式。
要求：只用英文关键词与同义词，用 OR 连接同义词、用 AND 连接不同概念；不要加年份。
同时给出 PICO 四格（population/intervention/comparison/outcome），没有的留空。
只输出 JSON：{"query": "...", "pico": {"population": "", "intervention": "", "comparison": "", "outcome": ""}}"""


def _step(cb: Progress, name: str, detail: str, percent: int) -> None:
    if cb:
        cb(name, detail, max(0, min(100, percent)))


def plan_query(direction: str, model_name: str) -> tuple[str, dict, int]:
    reply, usage = chat(
        [{"role": "system", "content": "你是文献检索专家，只输出 JSON。"},
         {"role": "user", "content": f"{PLAN_PROMPT}\n\n研究方向：{direction}"}],
        model_name=model_name,
        temperature=0.1,
    )
    data = extract_json(reply)
    query = str(data.get("query") or "").strip()
    if not query:
        query = direction
    return query, data.get("pico") or {}, usage.total_tokens


def run_pipeline(direction: str, *, platform: str = "不限", budget: str = "不限",
                 period: str = "不限", wet_lab: str = "接受",
                 years: str = "", search_limit: int = 40,
                 fetch_limit: int = 8, card_limit: int = 8,
                 model_name: str = "deepseek",
                 db_path: Path | str = DB_PATH,
                 progress: Progress | None = None) -> dict:
    ensure_dirs()
    conn = connect(db_path)
    started = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(RUNS_DIR) / started
    run_dir.mkdir(parents=True, exist_ok=True)
    tokens = 0

    _step(progress, "规划检索式", "正在把研究方向翻成英文检索式", 3)
    query, pico, used = plan_query(direction, model_name)
    tokens += used
    _step(progress, "规划检索式", f"检索式：{query[:120]}", 8)

    added = 0
    for paper in iter_papers(query, limit=search_limit):
        upsert(conn, paper)
        added += 1
    conn.commit()
    _step(progress, "检索", f"写入 {added} 条候选文献", 20)

    targets = pending_fulltexts(conn, fetch_limit)
    fetched = 0
    for index, (pmcid, _title) in enumerate(targets, start=1):
        _step(progress, "抓全文", f"{pmcid}（{index}/{len(targets)}）", 20 + int(18 * index / max(1, len(targets))))
        try:
            ft, raw = fetch_fulltext(pmcid)
            xml_path = Path(FULLTEXT_DIR) / f"{pmcid}.xml"
            xml_path.parent.mkdir(parents=True, exist_ok=True)
            xml_path.write_bytes(raw)
            save_fulltext(conn, ft, xml_path)
            conn.commit()
            fetched += 1
        except Exception as exc:  # noqa: BLE001
            save_fulltext(conn, FullText(pmcid=pmcid, status="error"), None, error=str(exc))
            conn.commit()
        time.sleep(1.0)
    _step(progress, "抓全文", f"成功 {fetched}/{len(targets)} 篇", 40)

    cards = get_cards(conn)
    carded_ids = {c["pmcid"] for c in cards}
    todo = [pmcid for pmcid in pending_cards(conn, card_limit) if pmcid not in carded_ids]
    new_cards = 0
    for index, pmcid in enumerate(todo, start=1):
        info = get_fulltext(conn, pmcid)
        if not info:
            continue
        _step(progress, "抽卡片", f"{pmcid}（{index}/{len(todo)}）", 40 + int(30 * index / max(1, len(todo))))
        figs = [f.__dict__ for f in figures_for(conn, pmcid)]
        try:
            card = make_card(info["title"], info["journal"], info["year"], figs,
                             info["text"], model_name=model_name)
            data = {**card.data, "title": info["title"]}
            save_card(conn, pmcid, data, model_name,
                      card.usage.prompt_tokens, card.usage.completion_tokens)
            conn.commit()
            tokens += card.usage.total_tokens
            new_cards += 1
        except Exception as exc:  # noqa: BLE001
            save_card(conn, pmcid, {"error": str(exc)}, model_name, status="error", error=str(exc))
            conn.commit()
    _step(progress, "抽卡片", f"新增 {new_cards} 张卡片", 70)

    all_cards = get_cards(conn)
    _step(progress, "跨文献聚合", f"正在归纳 {len(all_cards)} 张卡片", 78)
    constraints = (f"平台约束：{platform}；预算量级：{budget}；可投入周期：{period}；"
                   f"湿实验：{wet_lab}")
    summary, usage = summarize(f"{direction}\n{constraints}", all_cards, model_name=model_name)
    tokens += usage.total_tokens

    figs_map = {}
    for card in all_cards:
        figs_map[card["pmcid"]] = [f.__dict__ for f in figures_for(conn, card["pmcid"])]

    _step(progress, "生成简报", "正在写六件套 Markdown", 92)
    report_path = write_markdown(run_dir / "report.md", direction, all_cards, all_cards,
                                 summary, figs_map)
    to_csv(conn, run_dir / "papers.csv")
    (run_dir / "summary.json").write_text(
        json.dumps({"direction": direction, "platform": platform, "budget": budget,
                    "period": period, "wet_lab": wet_lab, "query": query, "pico": pico,
                    "search_limit": search_limit, "fetch_limit": fetch_limit,
                    "card_limit": card_limit, "tokens": tokens,
                    "summary": summary}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    save_report(conn, direction, summary, model_name, tokens)
    conn.commit()
    _step(progress, "完成", f"简报：{report_path}", 100)

    return {
        "run_dir": str(run_dir),
        "report": str(report_path),
        "query": query,
        "found": added,
        "fetched": fetched,
        "cards": len(all_cards),
        "summary": summary,
        "cards_data": all_cards,
        "figures": {k: v for k, v in figs_map.items()},
        "tokens": tokens,
    }
