import re

ACCESSORY_RE = re.compile(
    r"\b("
    r"hülle|huelle|schutzhülle|schutzhuelle|case|cover|tasche|etui|"
    r"ohrpolster|ohrmuschel|ohrmuscheln|earpads?|ersatz|replacement|"
    r"polster|kopfband|headband|cushion|cushions|aufkleber|"
    r"zubehör|zubehoer|sleeve|pouch"
    r")\b",
    re.IGNORECASE,
)
USED_RE = re.compile(
    r"\b("
    r"gebraucht|refurbished|erneuert|b-ware|bware|generalüberholt|"
    r"generalueberholt|vorführ|vorfuehr|used|second hand|retourware|"
    r"renewed|aufbereitet|ausverkauft"
    r")\b",
    re.IGNORECASE,
)
BUNDLE_RE = re.compile(
    r"\b(\d+\s*x|doppelpack|2er-pack|3er-pack|twin pack|doppelpackung)\b",
    re.IGNORECASE,
)
TOKEN_RE = re.compile(r"[a-z0-9äöüß]+", re.IGNORECASE)
STOPWORDS = {
    "der", "die", "das", "ein", "eine", "und", "mit", "für", "fuer", "von",
    "the", "and", "with", "for", "auf", "aus", "bei", "oder", "or", "to",
    "in", "of", "am", "im", "zum", "zur", "den", "dem",
}


def model_codes(text: str) -> list[str]:
    """Alphanumeric tokens that contain a digit, such as ``wh1000xm5``."""
    found: list[str] = []
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9+/-]{2,}", text):
        compact = re.sub(r"[^a-z0-9]", "", token.lower())
        if len(compact) >= 4 and any(character.isdigit() for character in compact):
            if compact not in found:
                found.append(compact)
    return found


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def tokens(text: str) -> list[str]:
    words = []
    for token in TOKEN_RE.findall(text.casefold()):
        if token in STOPWORDS or len(token) < 2:
            continue
        if token not in words:
            words.append(token)
    return words


def classify(query: str, title: str) -> tuple[bool, str]:
    """Decide whether a listing is the product the query asked for.

    Returns ``(keep, reason)``. Reasons for a drop: accessory, used, bundle,
    different-model, low-overlap.
    """
    if ACCESSORY_RE.search(title) and not ACCESSORY_RE.search(query):
        return False, "accessory"
    if USED_RE.search(title) and not USED_RE.search(query):
        return False, "used"
    if BUNDLE_RE.search(title) and not BUNDLE_RE.search(query):
        return False, "bundle"

    query_codes = [code for code in model_codes(query) if len(code) >= 5]
    title_compact = normalize(title)
    if query_codes:
        if any(code in title_compact for code in query_codes):
            return True, "model"
        return False, "different-model"

    query_tokens = tokens(query)
    if not query_tokens:
        return True, "empty-query"
    title_tokens = set(tokens(title))
    hits = sum(1 for token in query_tokens if token in title_tokens)
    if hits / len(query_tokens) < 0.5:
        return False, "low-overlap"
    return True, "overlap"


def cluster_key(query: str, title: str) -> str:
    """Group color variants of one model. Fall back to the title words."""
    title_compact = normalize(title)
    codes = sorted((code for code in model_codes(query) if len(code) >= 5), key=len, reverse=True)
    for code in codes:
        if code in title_compact:
            return code
    return " ".join(tokens(title)[:6]) or title.casefold()
