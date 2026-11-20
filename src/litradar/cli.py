from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DB_PATH
from .europepmc import build_query, iter_papers
from .store import all_papers, connect, count, to_csv, upsert


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
    print(f"文献总数：{total}")
    print(f"开放获取：{oa}")
    print(f"年份范围：{years[0]} – {years[1]}")
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

    p_stats = sub.add_parser("stats", help="查看库内统计")
    p_stats.set_defaults(func=cmd_stats)

    p_export = sub.add_parser("export", help="导出 CSV")
    p_export.add_argument("--out", default="papers.csv")
    p_export.set_defaults(func=cmd_export)

    p_list = sub.add_parser("list", help="列出库内文献")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
