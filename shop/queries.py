import re

# Word-level swaps so one product is searched the way both German and English
# shoppers name it. Short ambiguous words (case, bag, tv as a substring) stay out.
GLOSSARY = (
    ("headphones", "kopfhörer"),
    ("headphone", "kopfhörer"),
    ("earbuds", "ohrhörer"),
    ("earphones", "ohrhörer"),
    ("wireless", "kabellos"),
    ("keyboard", "tastatur"),
    ("mouse", "maus"),
    ("laptop", "notebook"),
    ("television", "fernseher"),
    ("vacuum cleaner", "staubsauger"),
    ("washing machine", "waschmaschine"),
    ("refrigerator", "kühlschrank"),
    ("fridge", "kühlschrank"),
    ("coffee machine", "kaffeemaschine"),
    ("air fryer", "heißluftfritteuse"),
    ("smartphone", "handy"),
    ("graphics card", "grafikkarte"),
    ("office chair", "bürostuhl"),
    ("backpack", "rucksack"),
    ("speaker", "lautsprecher"),
    ("printer", "drucker"),
    ("camera", "kamera"),
    ("lens", "objektiv"),
    ("charger", "ladegerät"),
    ("power bank", "powerbank"),
    ("hard drive", "festplatte"),
    ("motherboard", "mainboard"),
    ("dishwasher", "geschirrspüler"),
    ("microphone", "mikrofon"),
    ("sneakers", "sneaker"),
    ("shoes", "schuhe"),
)

FILLER = re.compile(
    r"\b(kaufen|billig|günstig|guenstig|angebot|angebote|sale|cheap|buy|bestens)\b",
    re.IGNORECASE,
)
HYPHENATED_MODEL = re.compile(r"\b[A-Za-z]{1,8}-\d[A-Za-z0-9-]*\b")


def expand_queries(item: str, extra: list[str] | None = None, limit: int = 6) -> list[str]:
    """Build a short list of search strings for the same product.

    The caller can pass further wordings. Those are kept ahead of generated
    variants. The list never grows past ``limit``.
    """
    seeds = [item, *(extra or [])]
    queries: list[str] = []

    def add(candidate: str) -> None:
        cleaned = re.sub(r"\s+", " ", candidate).strip(" ,")
        if len(cleaned) < 2:
            return
        if any(cleaned.casefold() == existing.casefold() for existing in queries):
            return
        if len(queries) >= limit:
            return
        queries.append(cleaned)

    for seed in seeds:
        add(seed)

    variants: list[str] = []
    for seed in seeds:
        without_filler = re.sub(r"\s+", " ", FILLER.sub(" ", seed)).strip()
        variants.append(without_filler)
        for model in HYPHENATED_MODEL.findall(seed):
            compact = model.replace("-", "")
            variants.append(seed.replace(model, compact))
            variants.append(model)
            variants.append(compact)
        for english, german in GLOSSARY:
            variants.append(_swap_word(seed, english, german))
            variants.append(_swap_word(seed, german, english))

    for candidate in variants:
        add(candidate)
        if len(queries) >= limit:
            break
    return queries


def _swap_word(text: str, source: str, target: str) -> str:
    return re.sub(rf"\b{re.escape(source)}\b", target, text, flags=re.IGNORECASE)
