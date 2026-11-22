from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .config import DB_PATH, FULLTEXT_DIR, REQUEST_INTERVAL, ensure_dirs
from .europepmc import build_query, iter_papers
from .fulltext import FullText, fetch_fulltext
from .pipeline import run_pipeline
from .store import (all_papers, connect, count, figures_for, fulltext_stats,
                    get_fulltext, pending_fulltexts, save_fulltext, to_csv,
                    upsert)
from .web import serve


def cmd_search(args: argparse.Namespace) -> int:
    query = args.query
    if not query and not args.pico:
        print("需要 --query 或 --pico 至少一个", file=sys.stderr)
        return 2
    if args.pico:
        fields = dict(pair.split("=", 1) for pair in args.pico)
        query = build_query(fields, years=args.years, extra=query)
    elif args.years:
        query = build_query({}, years=args.years, extra=query)

    print(f"检索式：{query}")
    conn = connect(args.db)
    seen, added = set(), 0
    for paper in iter_papers(query, limit=args.limit):
        if paper.key in seen:
            continue
        seen.add(paper.key)
        upsert(conn, paper)
        added += 1
    conn.commit()
    print(f"本次写入 {added} 条，库内共 {count(conn)} 条 → {args.db}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    total = count(conn)
    oa = conn.execute("SELECT COUNT(*) FROM papers WHERE is_oa=1").fetchone()[0]
    years = conn.execute("SELECT MIN(year), MAX(year) FROM papers").fetchone()
    full, figs = fulltext_stats(conn)
    print(f"文献总数：{total}")
    print(f"开放获取：{oa}")
    print(f"年份范围：{years[0]} – {years[1]}")
    print(f"已抓全文：{full} 篇")
    print(f"图表条目：{figs} 个")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    ensure_dirs()
    conn = connect(args.db)
    targets = [(args.pmcid, "")] if args.pmcid else pending_fulltexts(conn, args.limit)
    if not targets:
        print("没有待抓取的 OA 全文")
        return 0

    ok = fail = skip = figs = 0
    for pmcid, title in targets:
        existing = get_fulltext(conn, pmcid)
        if existing and existing["status"] == "ok" and not args.force:
            skip += 1
            continue
        try:
            ft, raw = fetch_fulltext(pmcid)
            xml_path = FULLTEXT_DIR / f"{pmcid}.xml"
            xml_path.write_bytes(raw)
            save_fulltext(conn, ft, xml_path)
            conn.commit()
            ok += 1
            figs += len(ft.figures)
            print(f"[ok] {pmcid} 正文 {len(ft.text)} 字 / 图表 {len(ft.figures)} 个 | {ft.title[:50]}")
        except Exception as exc:  # noqa: BLE001 - 单篇失败不影响整批
            save_fulltext(conn, FullText(pmcid=pmcid, status="error"), None, error=str(exc))
            conn.commit()
            fail += 1
            print(f"[fail] {pmcid} {exc}")
        if args.rate:
            time.sleep(args.rate)

    print(f"完成：成功 {ok}，跳过 {skip}，失败 {fail}，新增图表 {figs} → {args.db}")
    return 0 if fail == 0 else 1


def cmd_list_figures(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    if args.pmcid:
        pmcids = [args.pmcid]
    else:
        pmcids = [row[0] for row in conn.execute(
            "SELECT DISTINCT pmcid FROM figures LIMIT ?", (int(args.limit),)).fetchall()]
    total = 0
    for pmcid in pmcids:
        info = get_fulltext(conn, pmcid)
        head = (info["title"][:60] if info else "")
        print(f"\n== {pmcid} {head} ==")
        for fig in figures_for(conn, pmcid):
            total += 1
            print(f"  {fig.label} [{fig.kind}] {fig.caption[:90]}")
            if fig.image_url:
                print(f"    图: {fig.image_url}")
            if fig.cited_sentences:
                print(f"    正文引用: {fig.cited_sentences[:120]}")
    print(f"\n共 {total} 个图表")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    def progress(step: str, detail: str, percent: int) -> None:
        print(f"[{percent:3d}%] {step} | {detail[:90]}")

    result = run_pipeline(
        args.direction,
        platform=args.platform,
        budget=args.budget,
        period=args.period,
        wet_lab=args.wet_lab,
        years=args.years,
        search_limit=args.search_limit,
        fetch_limit=args.fetch_limit,
        card_limit=args.card_limit,
        model_name=args.model,
        db_path=args.db,
        domain_key=args.domain,
        sources_list=args.sources.split(",") if args.sources else ["europepmc"],
        oecd_code=args.oecd,
        progress=progress,
    )
    print(f"\n简报：{result['report']}")
    print(f"开题报告：{result['proposal']}"
          + (f"（Word：{result['proposal_docx']}）" if result.get("proposal_docx") else ""))
    print(f"候选 {result['found']} 篇 / 同域 {result.get('kept', result['found'])} 篇"
          f" / 挡掉 {result.get('dropped', 0)} 篇"
          f" / 全文 {result['fetched']} 篇 / 卡片 {result['cards']} 张"
          f" / tokens {result['tokens']}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    serve(args.host, args.port)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    n = to_csv(conn, Path(args.out))
    print(f"导出 {n} 条 → {args.out}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    for paper in all_papers(conn, limit=args.limit):
        print(f"[{paper.year}] {paper.title[:70]} | {paper.doi}")
    return 0


def _add_db(parser: argparse.ArgumentParser) -> None:
    # 让 --db 既能写在子命令前，也能写在子命令后
    parser.add_argument("--db", default=argparse.SUPPRESS, help="SQLite 路径")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="litradar", description="文献雷达")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite 路径")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="检索并写入本地库")
    p_search.add_argument("--query", default="", help="检索词或布尔式")
    p_search.add_argument("--pico", nargs="*", help="population=... intervention=...")
    p_search.add_argument("--years", help="2012-2026")
    p_search.add_argument("--limit", type=int, default=60)
    p_search.set_defaults(func=cmd_search)
    _add_db(p_search)

    p_stats = sub.add_parser("stats", help="查看库内统计")
    p_stats.set_defaults(func=cmd_stats)
    _add_db(p_stats)

    p_export = sub.add_parser("export", help="导出 CSV")
    p_export.add_argument("--out", default="papers.csv")
    p_export.set_defaults(func=cmd_export)
    _add_db(p_export)

    p_list = sub.add_parser("list", help="列出库内文献")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list)
    _add_db(p_list)

    p_fetch = sub.add_parser("fetch", help="抓取 OA 全文、图注与原图链接")
    p_fetch.add_argument("--pmcid", help="只抓指定一篇")
    p_fetch.add_argument("--limit", type=int, default=20, help="本批抓多少篇")
    p_fetch.add_argument("--force", action="store_true", help="已抓过的也重抓")
    p_fetch.add_argument("--rate", type=float, default=1.0, help="每篇之间停几秒")
    p_fetch.set_defaults(func=cmd_fetch)
    _add_db(p_fetch)

    p_figs = sub.add_parser("list-figures", help="查看已抓到的图注与原图链接")
    p_figs.add_argument("--pmcid", help="只看这一篇")
    p_figs.add_argument("--limit", type=int, default=5, help="最多看几篇")
    p_figs.set_defaults(func=cmd_list_figures)
    _add_db(p_figs)

    p_run = sub.add_parser("run", help="一个方向跑完整流水线")
    p_run.add_argument("--direction", required=True, help="研究方向，一句话")
    p_run.add_argument("--platform", default="不限")
    p_run.add_argument("--budget", default="不限")
    p_run.add_argument("--period", default="不限")
    p_run.add_argument("--wet-lab", default="接受", choices=["接受", "只做干实验"])
    p_run.add_argument("--years", default="")
    p_run.add_argument("--search-limit", type=int, default=40)
    p_run.add_argument("--fetch-limit", type=int, default=8)
    p_run.add_argument("--card-limit", type=int, default=8)
    p_run.add_argument("--model", default="deepseek")
    p_run.add_argument("--domain", default="auto",
                       choices=["auto", "materials", "agri", "biomed", "general"],
                       help="学科判定：默认自动，可强制指定")
    p_run.add_argument("--sources", default="europepmc",
                       help="逗号分隔：europepmc,pubmed,openalex,wos,scopus")
    p_run.add_argument("--oecd", default="", help="OECD 子类代码，如 2.5")
    p_run.set_defaults(func=cmd_run)
    _add_db(p_run)

    p_serve = sub.add_parser("serve", help="打开本地界面")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8899)
    p_serve.set_defaults(func=cmd_serve)
    _add_db(p_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
