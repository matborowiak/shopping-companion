import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from shop.fetch import looks_like_block
from shop.models import Offer, Response
from shop.parsers import parse_source, search_url
from shop.report import offer_from_dict, offer_to_dict, render_report
from shop.score import rank_offers

DUPLICATE = "duplicate-page"
BLOCKED = "blocked"
EMPTY = "empty"
OK = "ok"
NOT_FETCHED = "not-fetched"


@dataclass
class Run:
    item: str
    queries: list[str]
    pages: int
    offers: list[Offer] = field(default_factory=list)
    fetches: list[dict] = field(default_factory=list)
    pending: list[dict] = field(default_factory=list)
    directory: Path | None = None


def execute(item: str, queries: list[str], pages: int, sources: list[str], client, directory: Path) -> Run:
    run = Run(item=item, queries=queries, pages=pages, directory=directory)
    seen: set[str] = set()
    for source in sources:
        for query in queries:
            blocked = False
            previous_ids: list[str] | None = None
            for page in range(1, pages + 1):
                url = search_url(source, query, page)
                if blocked:
                    _record(run, source, query, page, url, NOT_FETCHED, 0, pending=True, reason="earlier page was blocked")
                    continue
                response = client.get(url)
                if _http_blocked(response):
                    blocked = True
                    _record(run, source, query, page, url, BLOCKED, 0, pending=True, reason=_block_reason(response))
                    continue
                parsed = parse_source(source, response.text, query, page, response.url or url)
                if not parsed and looks_like_block(response.status, response.text):
                    blocked = True
                    _record(run, source, query, page, url, BLOCKED, 0, pending=True, reason="challenge page")
                    continue
                identities = [offer.identity() for offer in parsed]
                if not identities:
                    _record(run, source, query, page, url, EMPTY, 0)
                    break
                if previous_ids is not None and set(identities) <= set(previous_ids):
                    _record(run, source, query, page, url, DUPLICATE, len(parsed))
                    break
                fresh = [offer for offer in parsed if offer.identity() not in seen]
                for offer in fresh:
                    seen.add(offer.identity())
                run.offers.extend(fresh)
                previous_ids = identities
                _record(run, source, query, page, url, OK, len(fresh))
    write_run(run)
    return run


def ingest(directory: Path, source: str, query: str, page: int, url: str, text: str) -> Run:
    run = read_run(directory)
    parsed = parse_source(source, text, query, page, url)
    if not parsed and looks_like_block(200, text):
        status = BLOCKED
    elif not parsed:
        status = EMPTY
    else:
        status = OK
    seen = {offer.identity() for offer in run.offers}
    fresh = [offer for offer in parsed if offer.identity() not in seen]
    run.offers.extend(fresh)
    run.fetches.append(
        {
            "source": source,
            "query": query,
            "page": page,
            "url": url,
            "status": status,
            "count": len(fresh),
        }
    )
    run.pending = [
        item
        for item in run.pending
        if not (item["source"] == source and item["query"] == query and item["page"] == page)
    ]
    write_run(run)
    return run


def write_run(run: Run) -> None:
    if run.directory is None:
        raise ValueError("run has no directory")
    run.directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "item": run.item,
        "queries": run.queries,
        "pages": run.pages,
        "offers": [offer_to_dict(offer) for offer in run.offers],
        "fetches": run.fetches,
        "pending": run.pending,
    }
    (run.directory / "offers.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run.directory / "blocked.json").write_text(
        json.dumps({"pending": run.pending}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ranking = rank_offers(run.item, run.offers)
    report = render_report(run.item, run.queries, ranking, run.fetches)
    (run.directory / "report.md").write_text(report, encoding="utf-8")


def read_run(directory: Path) -> Run:
    payload = json.loads((directory / "offers.json").read_text(encoding="utf-8"))
    return Run(
        item=payload["item"],
        queries=payload["queries"],
        pages=payload["pages"],
        offers=[offer_from_dict(offer) for offer in payload["offers"]],
        fetches=payload.get("fetches") or [],
        pending=payload.get("pending") or [],
        directory=directory,
    )


def new_run_directory(root: Path, when: datetime | None = None) -> Path:
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
    directory = root / stamp
    suffix = 2
    while directory.exists():
        directory = root / f"{stamp}-{suffix}"
        suffix += 1
    return directory


def _http_blocked(response: Response) -> bool:
    return response.status == 0 or response.status >= 400


def _block_reason(response: Response) -> str:
    if response.error:
        return response.error
    return f"http-{response.status}"


def _record(
    run: Run,
    source: str,
    query: str,
    page: int,
    url: str,
    status: str,
    count: int,
    pending: bool = False,
    reason: str | None = None,
) -> None:
    fetch = {
        "source": source,
        "query": query,
        "page": page,
        "url": url,
        "status": status,
        "count": count,
    }
    if reason:
        fetch["reason"] = reason
    run.fetches.append(fetch)
    if pending:
        run.pending.append(
            {"source": source, "query": query, "page": page, "url": url, "reason": reason or status}
        )
