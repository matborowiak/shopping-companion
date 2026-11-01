import argparse
import sys
from pathlib import Path

from shop.engine import execute, ingest, new_run_directory
from shop.fetch import CachedClient, UrllibClient
from shop.parsers import SOURCES
from shop.queries import expand_queries
from shop.score import rank_offers


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "ingest":
        return _ingest(args[1:])
    return _run(args)


def _run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="shop",
        description="Search German stores and rank the best-value listing.",
    )
    parser.add_argument("item", help="Product to look for, in your own words")
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Extra wording of the same product. Repeat for each wording.",
    )
    parser.add_argument("--pages", type=int, default=3, help="Pages to read per query (default: 3)")
    parser.add_argument("--max-queries", type=int, default=6)
    parser.add_argument(
        "--sources",
        default="amazon,geizhals,idealo,mydealz",
        help="Comma-separated subset of amazon,geizhals,idealo,mydealz",
    )
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds to wait between requests to one site")
    parser.add_argument("--refresh", action="store_true", help="Ignore cached pages")
    parser.add_argument("--out", help="Directory for this run. Default: runs/<timestamp>")
    args = parser.parse_args(argv)

    sources = [part.strip() for part in args.sources.split(",") if part.strip()]
    unknown = [source for source in sources if source not in SOURCES]
    if unknown:
        parser.error(f"unknown source: {', '.join(unknown)}")
    if args.pages < 1:
        parser.error("--pages must be at least 1")

    queries = expand_queries(args.item, args.query, limit=args.max_queries)
    root = Path.cwd()
    directory = Path(args.out) if args.out else new_run_directory(root / "runs")
    client = CachedClient(
        UrllibClient(),
        cache_dir=root / ".cache" / "http",
        refresh=args.refresh,
        delay=args.delay,
    )
    run = execute(args.item, queries, args.pages, sources, client, directory)
    ranking = rank_offers(run.item, run.offers)
    print(f"Queries: {', '.join(queries)}")
    if ranking.winner:
        winner = ranking.winner.offer
        print(f"Best value: {winner.title}")
        print(f"Price: {winner.price_eur:.2f} EUR at {winner.source}")
        print(f"Link: {winner.url}")
    else:
        print("No comparable listing yet.")
    if run.pending:
        print(f"Blocked pages to fetch another way: {len(run.pending)}")
    print(f"RUN_DIR={directory}")
    return 0


def _ingest(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="shop ingest", description="Add one fetched page to a run and rescore.")
    parser.add_argument("--run", required=True, help="Run directory that contains offers.json")
    parser.add_argument("--source", required=True, choices=SOURCES)
    parser.add_argument("--query", required=True)
    parser.add_argument("--page", required=True, type=int)
    parser.add_argument("--url", required=True)
    parser.add_argument("--file", required=True, help="Saved page text, HTML or the readable fetch")
    args = parser.parse_args(argv)
    text = Path(args.file).read_text(encoding="utf-8")
    run = ingest(Path(args.run), args.source, args.query, args.page, args.url, text)
    ranking = rank_offers(run.item, run.offers)
    if ranking.winner:
        winner = ranking.winner.offer
        print(f"Best value: {winner.title}")
        print(f"Price: {winner.price_eur:.2f} EUR at {winner.source}")
    else:
        print("No comparable listing yet.")
    print(f"RUN_DIR={args.run}")
    return 0
