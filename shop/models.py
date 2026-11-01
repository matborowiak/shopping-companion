from dataclasses import dataclass, field


@dataclass
class Offer:
    source: str
    query: str
    page: int
    rank: int
    title: str
    url: str
    price_eur: float | None = None
    rating: float | None = None
    rating_scale: str | None = None  # "stars5" (higher is better) or "grade6" (1.0 is best)
    votes: int | None = None
    sponsored: bool = False
    expired: bool = False
    external_id: str | None = None
    extra: dict = field(default_factory=dict)

    def identity(self) -> str:
        if self.external_id:
            return f"{self.source}:{self.external_id}"
        price = "" if self.price_eur is None else f"{self.price_eur:.2f}"
        return f"{self.source}:{self.title.casefold()}:{price}"


@dataclass
class Response:
    status: int
    url: str
    text: str
    error: str | None = None
