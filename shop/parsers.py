import json
import re
from urllib.parse import quote_plus

from shop.models import Offer
from shop.numbers import parse_count, parse_de_number, parse_eur

SOURCES = ("amazon", "geizhals", "idealo", "mydealz")

_PRICE_RE = re.compile(
    r"(?:ab|um)\s*(?:€\s*(\d[\d.]*,\d{2})|(\d[\d.]*,\d{2})\s*€)",
    re.IGNORECASE,
)
_GEIZHALS_RATING_RE = re.compile(
    r"Bewertung:\s*([\d.,]+)\s*von\s*5",
    re.IGNORECASE,
)
_COUNT_WORD_RE = re.compile(r"(\d[\d.]*)\s+(Bewertungen|Angebot(?:e)?)", re.IGNORECASE)
_IDEALO_ROW_RE = re.compile(
    r"(\d[\d.]*)\s+Angebot(?:e)?\s+ab\s+(\d[\d.]*,\d{2})\s*€",
    re.IGNORECASE,
)
_IDEALO_GRADE_RE = re.compile(r"Note\s*[∅Øø]?\s*([\d.,]+)", re.IGNORECASE)
_ONLY_NUMBER_RE = re.compile(r"\d{1,3}(?:\.\d{3})+|\d+")


def search_url(source: str, query: str, page: int) -> str:
    encoded = quote_plus(query)
    if source == "amazon":
        return f"https://www.amazon.de/s?k={encoded}&page={page}&language=de_DE"
    if source == "geizhals":
        base = f"https://geizhals.de/?fs={encoded}&hloc=de"
        return base if page == 1 else f"{base}&pg={page}"
    if source == "idealo":
        base = (
            "https://www.idealo.de/preisvergleich/MainSearchProductCategory.html"
            f"?q={encoded}"
        )
        return base if page == 1 else f"{base}&page={page}"
    if source == "mydealz":
        return f"https://www.mydealz.de/search?q={encoded}&page={page}"
    raise ValueError(f"unknown source: {source}")


def parse_source(source: str, text: str, query: str, page: int, url: str) -> list[Offer]:
    if source == "amazon":
        return parse_amazon(text, query, page)
    if source == "geizhals":
        return parse_geizhals(text, query, page, url)
    if source == "idealo":
        return parse_idealo(text, query, page, url)
    if source == "mydealz":
        return parse_mydealz(text, query, page)
    raise ValueError(f"unknown source: {source}")


def parse_amazon(html: str, query: str, page: int) -> list[Offer]:
    offers: list[Offer] = []
    seen: set[str] = set()
    for rank, card in enumerate(_amazon_cards(html), start=1):
        asin = _amazon_asin(card)
        if not asin or asin in seen:
            continue
        title = _amazon_title(card)
        price = _first_price(re.findall(r'class="a-offscreen">\s*([^<]+?)\s*<', card))
        if not title or price is None:
            continue
        rating = _first_number(
            re.search(r'class="a-icon-alt">\s*([\d.,]+)\s*von\s*5', card)
        )
        votes = _amazon_votes(card)
        sponsored = bool(
            re.search(r"s-sponsored-label-text|>\s*Gesponsert\s*<|Sponsored", card)
        )
        position = re.search(r'data-csa-c-pos="(\d+)"', card)
        seen.add(asin)
        offers.append(
            Offer(
                source="amazon",
                query=query,
                page=page,
                rank=int(position.group(1)) if position else rank,
                title=_clean_title(title),
                url=f"https://www.amazon.de/dp/{asin}",
                price_eur=price,
                rating=rating,
                rating_scale="stars5" if rating is not None else None,
                votes=votes,
                sponsored=sponsored,
                external_id=asin,
            )
        )
    return offers


def parse_geizhals(text: str, query: str, page: int, url: str) -> list[Offer]:
    body = _clip(text, ("Alle Angaben ohne Gewähr",))
    offers: list[Offer] = []
    matches = list(_PRICE_RE.finditer(body))
    for rank, match in enumerate(matches, start=1):
        start = matches[rank - 2].end() if rank > 1 else 0
        block = body[start:match.end()]
        title = _title_from_block(block)
        amount = match.group(1) or match.group(2)
        price = parse_eur(amount)
        if not title or price is None:
            continue
        rating_match = _GEIZHALS_RATING_RE.search(block)
        rating = parse_de_number(rating_match.group(1)) if rating_match else None
        votes = _labeled_count(block, "Bewertungen")
        offer_count = _labeled_count(block, "Angebot")
        offers.append(
            Offer(
                source="geizhals",
                query=query,
                page=page,
                rank=rank,
                title=title,
                url=url,
                price_eur=price,
                rating=rating,
                rating_scale="stars5" if rating is not None else None,
                votes=votes,
                external_id=_slug(title),
                extra={"offer_count": offer_count} if offer_count is not None else {},
            )
        )
    return offers


def parse_idealo(text: str, query: str, page: int, url: str) -> list[Offer]:
    body = _clip(text, ("### Black Friday", "### Neu in", "Fachredakteur"))
    offers: list[Offer] = []
    matches = list(_IDEALO_ROW_RE.finditer(body))
    for rank, match in enumerate(matches, start=1):
        start = matches[rank - 2].end() if rank > 1 else 0
        block = body[start:match.start()]
        title = _title_from_block(block)
        price = parse_eur(match.group(2))
        if not title or price is None:
            continue
        grade_match = _IDEALO_GRADE_RE.search(block)
        grade = parse_de_number(grade_match.group(1)) if grade_match else None
        votes = _standalone_count(block)
        offer_count = parse_count(match.group(1))
        offers.append(
            Offer(
                source="idealo",
                query=query,
                page=page,
                rank=rank,
                title=title,
                url=url,
                price_eur=price,
                rating=grade,
                rating_scale="grade6" if grade is not None else None,
                votes=votes,
                external_id=_slug(title),
                extra={"offer_count": offer_count} if offer_count is not None else {},
            )
        )
    return offers


def parse_mydealz(html: str, query: str, page: int) -> list[Offer]:
    offers: list[Offer] = []
    seen: set[str] = set()
    for match in re.finditer(r'\{"thread":\{', html):
        try:
            payload, _ = json.JSONDecoder().raw_decode(html[match.start():])
        except json.JSONDecodeError:
            continue
        thread = payload.get("thread") if isinstance(payload, dict) else None
        if not isinstance(thread, dict):
            continue
        thread_id = str(thread.get("threadId") or "")
        title = _clean_title(str(thread.get("title") or ""))
        price = _as_float(thread.get("price"))
        if not thread_id or thread_id in seen or not title or price is None or price <= 0:
            continue
        if thread.get("deletedAt"):
            continue
        seen.add(thread_id)
        slug = thread.get("titleSlug") or _slug(title)
        merchant = thread.get("merchant") if isinstance(thread.get("merchant"), dict) else {}
        heat = _as_float(thread.get("temperature"))
        offers.append(
            Offer(
                source="mydealz",
                query=query,
                page=page,
                rank=len(offers) + 1,
                title=title,
                url=f"https://www.mydealz.de/deals/{slug}-{thread_id}",
                price_eur=price,
                expired=bool(thread.get("isExpired")),
                external_id=thread_id,
                extra={
                    "heat": heat,
                    "merchant": merchant.get("merchantName"),
                    "next_best_price": _as_float(thread.get("nextBestPrice")),
                    "host": thread.get("linkHost"),
                },
            )
        )
    return offers


def _amazon_cards(html: str) -> list[str]:
    marker = 'data-component-type="s-search-result"'
    cards: list[str] = []
    cursor = 0
    while True:
        found = html.find(marker, cursor)
        if found < 0:
            break
        tag_start = html.rfind("<", 0, found)
        nxt = html.find(marker, found + len(marker))
        tag_end = html.rfind("<", 0, nxt) if nxt > 0 else len(html)
        cards.append(html[tag_start:tag_end])
        cursor = found + len(marker)
    return cards


def _amazon_asin(card: str) -> str | None:
    for pattern in (
        r'data-asin="([A-Z0-9]{10})"',
        r'data-csa-c-asin="([A-Z0-9]{10})"',
        r"/dp/([A-Z0-9]{10})",
    ):
        match = re.search(pattern, card)
        if match:
            return match.group(1)
    return None


def _amazon_title(card: str) -> str | None:
    titles = re.findall(r"<h2\b[^>]*>[\s\S]*?<span[^>]*>([^<]+)</span>", card)
    for title in titles:
        cleaned = _clean_title(title)
        if 8 <= len(cleaned) <= 180 and "Carbon Trust" not in cleaned:
            return cleaned
    return None


def _amazon_votes(card: str) -> int | None:
    labeled = re.search(r'aria-label="([\d.,]+)\s+Bewertungen"', card)
    if labeled:
        return parse_count(labeled.group(1))
    paren = re.search(r"s-underline-text[^>]*>\s*\(([\d.,]+)\)", card)
    if paren:
        return parse_count(paren.group(1))
    return None


def _first_price(candidates: list[str]) -> float | None:
    for candidate in candidates:
        if "€" not in candidate and "EUR" not in candidate:
            continue
        price = parse_eur(candidate)
        if price is not None:
            return price
    return None


def _first_number(match: re.Match[str] | None) -> float | None:
    if not match:
        return None
    return parse_de_number(match.group(1))


def _labeled_count(block: str, label: str) -> int | None:
    for match in _COUNT_WORD_RE.finditer(block):
        if match.group(2).casefold().startswith(label.casefold()):
            return parse_count(match.group(1))
    return None


def _standalone_count(block: str) -> int | None:
    for line in reversed([line.strip() for line in block.splitlines() if line.strip()]):
        if _ONLY_NUMBER_RE.fullmatch(line):
            return parse_count(line)
    return None


def _title_from_block(block: str) -> str | None:
    for raw_line in block.splitlines():
        line = raw_line.strip(" #\t")
        if not line or len(line) < 6 or len(line) > 160:
            continue
        if line.count(",") >= 3:
            continue
        if re.match(r"(Bewertung:|Note\b|\d)", line, re.IGNORECASE):
            continue
        if re.search(r"Angebot(?:e)?", line, re.IGNORECASE):
            continue
        if re.fullmatch(r"[A-Z0-9][A-Z0-9./+-]{4,}", line):
            continue
        return _clean_title(line)
    return None


def _clip(text: str, markers: tuple[str, ...]) -> str:
    end = len(text)
    for marker in markers:
        found = text.find(marker)
        if found != -1:
            end = min(end, found)
    return text[:end]


def _clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:80]


def _as_float(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return parse_de_number(value)
    return None
