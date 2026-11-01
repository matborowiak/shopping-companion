import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from shop.models import Response

# A browser Accept profile, because the stores return their public search HTML
# to browsers. This does not solve challenges, rotate proxies, or hide the client.
# A challenge page is recorded and left for Claude Code's own fetch.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

BLOCK_MARKERS = (
    "sichere verbindung wird überprüft",
    "enter the characters you see",
    "api-services-support@amazon.com",
    "to discuss automated access to amazon data",
    "px-captcha",
    "cf-browser-verification",
    "just a moment...",
    "attention required",
    "access denied",
)
CACHE_TTL_SECONDS = 6 * 60 * 60
MAX_BYTES = 3_000_000


def looks_like_block(status: int, text: str) -> bool:
    if status >= 400 or status == 0:
        return True
    if len(text) >= 80_000:
        return False
    head = text[:12_000].casefold()
    return any(marker in head for marker in BLOCK_MARKERS)


class UrllibClient:
    def get(self, url: str) -> Response:
        request = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = response.read(MAX_BYTES)
                charset = response.headers.get_content_charset() or "utf-8"
                return Response(response.status, response.geturl(), raw.decode(charset, "replace"))
        except urllib.error.HTTPError as exc:
            raw = exc.read(MAX_BYTES) if exc.fp else b""
            return Response(exc.code, url, raw.decode("utf-8", "replace"))
        except urllib.error.URLError as exc:
            return Response(0, url, "", error=str(exc.reason))


class CachedClient:
    """Read recent responses from disk and wait between calls to one host."""

    def __init__(self, inner, cache_dir: Path, refresh: bool = False, delay: float = 1.0):
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.refresh = refresh
        self.delay = delay
        self._last_by_host: dict[str, float] = {}

    def get(self, url: str) -> Response:
        path = self.cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
        if path.exists() and not self.refresh:
            age = time.time() - path.stat().st_mtime
            if age < CACHE_TTL_SECONDS:
                payload = json.loads(path.read_text(encoding="utf-8"))
                return Response(payload["status"], url, payload["text"], payload.get("error"))

        host = _host(url)
        elapsed = time.time() - self._last_by_host.get(host, 0.0)
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        response = self.inner.get(url)
        self._last_by_host[host] = time.time()
        if response.status != 0:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {"status": response.status, "text": response.text, "error": response.error},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        return response


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc
