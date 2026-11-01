from shop.models import Offer
from shop.numbers import format_count, format_eur
from shop.score import Ranking, Row

SOURCE_LABELS = {
    "amazon": "Amazon.de",
    "geizhals": "Geizhals",
    "idealo": "Idealo",
    "mydealz": "MyDealz",
}


def render_report(item: str, queries: list[str], ranking: Ranking, fetches: list[dict]) -> str:
    lines: list[str] = [f"# Best value for {item}", ""]
    if ranking.winner is None:
        lines.append("No comparable in-stock listing survived the filters.")
        lines.append("Check the coverage section before deciding the search missed the product.")
    else:
        winner = ranking.winner
        lines.extend(_winner_block(winner))
        lines.extend(["", "## Why this one", ""])
        lines.append(_why(winner, ranking.alternatives))
        lines.extend(["", "## Other offers worth a look", ""])
        lines.extend(_table([winner, *ranking.alternatives]))
    lines.extend(["", "## Set aside", ""])
    if ranking.dropped:
        for reason, count in sorted(ranking.dropped.items()):
            lines.append(f"- {count} {reason.replace('-', ' ')}")
    else:
        lines.append("- Nothing was filtered out.")
    lines.extend(["", "## Coverage", ""])
    lines.append("Queries: " + "; ".join(queries))
    lines.append("")
    lines.extend(_coverage(fetches))
    lines.extend(
        [
            "",
            "## How the score works",
            "",
            "Each listing is judged on price, rating, and number of votes. "
            "Star ratings (Amazon, Geizhals) and Idealo's school grade are put on one 0–1 scale. "
            "A rating with few votes is pulled toward 4.0/5 until more reviews back it up. "
            "The score is that adjusted quality, squared, times a vote-confidence term, divided by the price in euro. "
            "Vote count stops adding confidence after a few hundred reviews, so two well-reviewed listings are then separated by stars and price. "
            "The best offer is scaled to 100. Search position is shown in the table and does not change the score.",
            "",
            "MyDealz temperature is deal heat, not a product review. A deal uses the rating of the same model from the store with the most reviews. "
            "Prices are what the page showed: Amazon's displayed price, Geizhals and Idealo \"from\" prices, and the MyDealz deal price. "
            "Shipping can still change the total, and a marketplace seller is not the same as the manufacturer. "
            "Open the link and confirm the current price, seller, and return terms before paying.",
            "",
        ]
    )
    return "\n".join(lines)


def _winner_block(row: Row) -> list[str]:
    offer = row.offer
    where = SOURCE_LABELS.get(offer.source, offer.source)
    merchant = offer.extra.get("merchant")
    place = f"{where}, {merchant}" if merchant else where
    lines = [
        f"**Buy:** {offer.title}",
        "",
        f"**Price:** {format_eur(offer.price_eur or 0)} at {place}",
        "",
        f"**Link:** {offer.url}",
        "",
        f"**Value index:** {row.index:.0f}" if row.index is not None else "**Value index:** n/a",
        "",
        _rating_line(row),
    ]
    heat = offer.extra.get("heat")
    if isinstance(heat, (int, float)):
        lines.append("")
        lines.append(f"**MyDealz heat:** {heat:.0f} (community votes on this deal)")
    usual = offer.extra.get("next_best_price")
    if isinstance(usual, (int, float)) and usual > 0:
        lines.append("")
        lines.append(f"**Usual price cited on the deal:** {format_eur(usual)}")
    return lines


def _why(winner: Row, alternatives: list[Row]) -> str:
    offer = winner.offer
    if winner.quality is None:
        return (
            "None of the matching listings had a usable rating, so this is simply the lowest price "
            "that still looked like the requested product. Treat it as a lead, not a verdict."
        )
    rating = _format_rating(winner.rating_used, winner.rating_scale_used)
    votes = format_count(winner.votes_used or 0)
    source = SOURCE_LABELS.get(winner.evidence_source or "", winner.evidence_source or "a store")
    sentence = (
        f"The rating used is {rating} from {votes} votes on {source}. "
        f"Thinner ratings were discounted, and this price is {format_eur(offer.price_eur or 0)}."
    )
    if alternatives:
        nxt = alternatives[0]
        if nxt.offer.price_eur and offer.price_eur:
            gap = nxt.offer.price_eur - offer.price_eur
            if gap > 0.5:
                sentence += f" The next listing is {format_eur(gap)} more."
            elif gap < -0.5:
                sentence += (
                    f" A listing at {format_eur(nxt.offer.price_eur)} is cheaper, "
                    "and its rating or vote count does not make up the difference."
                )
    if offer.source == "mydealz":
        sentence += " Confirm the seller on the deal page; heat is not a warranty."
    return sentence


def _table(rows: list[Row]) -> list[str]:
    header = (
        "| Value | Price | Rating used | Votes | Where | Page / slot | Title |",
        "| ---: | ---: | --- | ---: | --- | --- | --- |",
    )
    body = []
    for row in rows:
        offer = row.offer
        index = f"{row.index:.0f}" if row.index is not None else "—"
        rating = _format_rating(row.rating_used, row.rating_scale_used)
        votes = format_count(row.votes_used) if row.votes_used else "—"
        where = SOURCE_LABELS.get(offer.source, offer.source)
        if offer.extra.get("merchant"):
            where += f" / {offer.extra['merchant']}"
        title = offer.title.replace("|", "/")
        body.append(
            f"| {index} | {format_eur(offer.price_eur or 0)} | {rating} | {votes} | {where} | "
            f"{offer.page} / {offer.rank} | [{title}]({offer.url}) |"
        )
    return [*header, *body]


def _coverage(fetches: list[dict]) -> list[str]:
    lines = ["| Source | Query | Page | Status | Listings |", "| --- | --- | ---: | --- | ---: |"]
    for fetch in fetches:
        lines.append(
            f"| {fetch['source']} | {fetch['query']} | {fetch['page']} | {fetch['status']} | {fetch.get('count', 0)} |"
        )
    return lines


def _rating_line(row: Row) -> str:
    if row.rating_used is None:
        return "**Rating:** none on the matching listings"
    source = SOURCE_LABELS.get(row.evidence_source or "", row.evidence_source or "")
    votes = format_count(row.votes_used or 0)
    rating = _format_rating(row.rating_used, row.rating_scale_used)
    if row.evidence_source and row.evidence_source != row.offer.source:
        listing = SOURCE_LABELS.get(row.offer.source, row.offer.source)
        return f"**Rating:** {rating} from {votes} votes on {source}, applied to this {listing} listing"
    return f"**Rating:** {rating} from {votes} votes on {source}"


def _format_rating(rating: float | None, scale: str | None) -> str:
    if rating is None:
        return "—"
    shown = f"{rating:.1f}".replace(".", ",")
    if scale == "grade6":
        return f"Note {shown} (1 is best)"
    return f"{shown}/5"


def offer_to_dict(offer: Offer) -> dict:
    return {
        "source": offer.source,
        "query": offer.query,
        "page": offer.page,
        "rank": offer.rank,
        "title": offer.title,
        "url": offer.url,
        "price_eur": offer.price_eur,
        "rating": offer.rating,
        "rating_scale": offer.rating_scale,
        "votes": offer.votes,
        "sponsored": offer.sponsored,
        "expired": offer.expired,
        "external_id": offer.external_id,
        "extra": offer.extra,
    }


def offer_from_dict(payload: dict) -> Offer:
    return Offer(
        source=payload["source"],
        query=payload["query"],
        page=payload["page"],
        rank=payload["rank"],
        title=payload["title"],
        url=payload["url"],
        price_eur=payload.get("price_eur"),
        rating=payload.get("rating"),
        rating_scale=payload.get("rating_scale"),
        votes=payload.get("votes"),
        sponsored=payload.get("sponsored", False),
        expired=payload.get("expired", False),
        external_id=payload.get("external_id"),
        extra=payload.get("extra") or {},
    )
