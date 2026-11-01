import re


def parse_de_number(raw: str | None) -> float | None:
    """Parse a German or plain number. '1.639' is 1639, '4,2' is 4.2, '207,04' is 207.04."""
    if raw is None:
        return None
    cleaned = raw.replace("\xa0", "").replace(" ", "")
    match = re.search(r"\d[\d.,]*", cleaned)
    if not match:
        return None
    token = match.group(0)
    if "," in token and "." in token:
        token = token.replace(".", "").replace(",", ".")
    elif "," in token:
        token = token.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", token):
        token = token.replace(".", "")
    try:
        return float(token)
    except ValueError:
        return None


def parse_count(raw: str | None) -> int | None:
    number = parse_de_number(raw)
    if number is None:
        return None
    return int(round(number))


def parse_eur(raw: str | None) -> float | None:
    if raw is None:
        return None
    cleaned = raw.replace("\xa0", " ").replace("€", " ").replace("EUR", " ")
    match = re.search(r"\d[\d.]*,\d{2}|\d[\d.]*", cleaned)
    if not match:
        return None
    return parse_de_number(match.group(0))


def format_eur(value: float) -> str:
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"


def format_count(value: int) -> str:
    return f"{value:,}".replace(",", ".")
