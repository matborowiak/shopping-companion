"""Best-value ranking.

Price, rating, and the number of votes all count. Search position is reported
and is not part of the score: a clearly better offer on page 2 still wins.

Stars are Amazon and Geizhals (1 to 5, higher is better). Idealo's Note is a
German school grade (1.0 is best, 6 is worst). Both are converted to a 0–1
quality before they are compared. MyDealz heat is community interest in a
deal, not a product review, so a deal borrows the rating of the same model
from the store with the most reviews.

A Bayesian prior pulls thin ratings toward a middling 4.0/5 (quality 0.75)
until there are enough votes to trust them. Quality is squared so a real gap
in the rating matters, then divided by price. Extra votes stop increasing
confidence after a few hundred reviews.
"""

from dataclasses import dataclass, field
import math
import statistics

from shop.models import Offer
from shop.relevance import classify, cluster_key

PRIOR_QUALITY = 0.75
PRIOR_VOTES = 40
MIN_PRICE_RATIO = 0.40
HOT_DEAL_HEAT = 100
# Past a few hundred reviews, more votes do not mean a better product.
# 2,000 and 20,000 reviews are both enough, so the stars decide.
CONFIDENCE_VOTE_CAP = 500


@dataclass
class Row:
    offer: Offer
    kept: bool
    reason: str
    cluster: str = ""
    value: float | None = None
    index: float | None = None
    quality: float | None = None
    votes_used: int | None = None
    rating_used: float | None = None
    rating_scale_used: str | None = None
    evidence_source: str | None = None


@dataclass
class Ranking:
    rows: list[Row] = field(default_factory=list)
    winner: Row | None = None
    alternatives: list[Row] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)

    @property
    def kept(self) -> list[Row]:
        return [row for row in self.rows if row.kept and row.value is not None]


def rank_offers(query: str, offers: list[Offer]) -> Ranking:
    ranking = Ranking()
    preliminary: list[Row] = []
    for offer in offers:
        keep, reason = classify(query, offer.title)
        if offer.sponsored:
            keep, reason = False, "sponsored"
        elif offer.expired:
            keep, reason = False, "expired"
        elif offer.price_eur is None or offer.price_eur <= 0:
            keep, reason = False, "no-price"
        preliminary.append(
            Row(
                offer=offer,
                kept=keep,
                reason=reason if keep else reason,
                cluster=cluster_key(query, offer.title) if keep else "",
            )
        )

    medians = _cluster_medians(preliminary)
    for row in preliminary:
        if not row.kept:
            continue
        median = medians.get(row.cluster)
        price = row.offer.price_eur or 0
        if median and price < MIN_PRICE_RATIO * median and not _trusted_hot_deal(row.offer):
            row.kept = False
            row.reason = "price-outlier"

    evidence = _cluster_evidence(preliminary)
    for row in preliminary:
        if not row.kept:
            ranking.dropped[row.reason] = ranking.dropped.get(row.reason, 0) + 1
            ranking.rows.append(row)
            continue
        quality, votes, rating, scale, source = _evidence_for(row, evidence)
        if quality is None:
            row.reason = "unrated"
            row.value = 1.0 / (row.offer.price_eur or 1.0)
        else:
            row.quality = quality
            row.votes_used = votes
            row.rating_used = rating
            row.rating_scale_used = scale
            row.evidence_source = source
            row.reason = "kept"
            row.value = _value(row.offer.price_eur or 1.0, quality, votes or 0)
        ranking.rows.append(row)

    ranked = sorted(
        ranking.kept,
        key=lambda row: (row.quality is not None, row.value or 0),
        reverse=True,
    )
    rated = [row for row in ranked if row.quality is not None]
    scale_group = rated or ranked
    best = scale_group[0].value if scale_group else None
    for row in ranked:
        comparable = row.quality is not None or not rated
        row.index = (100.0 * (row.value or 0) / best) if best and comparable else None
    ranking.winner = ranked[0] if ranked else None
    ranking.alternatives = ranked[1:8]
    return ranking


def _value(price: float, quality: float, votes: int) -> float:
    bayes = (votes * quality + PRIOR_VOTES * PRIOR_QUALITY) / (votes + PRIOR_VOTES)
    confidence = math.log10(min(votes, CONFIDENCE_VOTE_CAP) + 10)
    return (bayes ** 2) * confidence / price


def quality_unit(rating: float, scale: str) -> float:
    if scale == "stars5":
        raw = (rating - 1.0) / 4.0
    elif scale == "grade6":
        raw = (6.0 - rating) / 5.0
    else:
        raise ValueError(scale)
    return max(0.0, min(1.0, raw))


def _cluster_medians(rows: list[Row]) -> dict[str, float]:
    prices: dict[str, list[float]] = {}
    for row in rows:
        if row.kept and row.offer.price_eur:
            prices.setdefault(row.cluster, []).append(row.offer.price_eur)
    return {
        key: statistics.median(values)
        for key, values in prices.items()
        if values
    }


def _trusted_hot_deal(offer: Offer) -> bool:
    heat = offer.extra.get("heat")
    return offer.source == "mydealz" and isinstance(heat, (int, float)) and heat >= HOT_DEAL_HEAT


def _cluster_evidence(rows: list[Row]) -> dict[str, tuple]:
    best: dict[str, tuple] = {}
    for row in rows:
        offer = row.offer
        if not row.kept or offer.rating is None or not offer.rating_scale:
            continue
        votes = offer.votes or 0
        current = best.get(row.cluster)
        if current is None or votes > current[0]:
            best[row.cluster] = (
                votes,
                quality_unit(offer.rating, offer.rating_scale),
                offer.rating,
                offer.rating_scale,
                offer.source,
            )
    return best


def _evidence_for(row: Row, evidence: dict[str, tuple]):
    offer = row.offer
    # A listing that published its own rating is judged on that rating.
    # Borrowing is only for listings with no product rating, such as a MyDealz deal.
    if offer.rating is not None and offer.rating_scale:
        return (
            quality_unit(offer.rating, offer.rating_scale),
            offer.votes or 0,
            offer.rating,
            offer.rating_scale,
            offer.source,
        )
    family = evidence.get(row.cluster)
    if family is not None:
        _votes, quality, rating, scale, source = family
        return quality, family[0], rating, scale, source
    if offer.rating is not None and offer.rating_scale:
        return (
            quality_unit(offer.rating, offer.rating_scale),
            own_votes,
            offer.rating,
            offer.rating_scale,
            offer.source,
        )
    return None, None, None, None, None
