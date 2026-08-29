from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.modules.imports.felgtbi.importer import YEAR_PATTERN
from app.shared.data.source_attribution import FELGTBI_REPORTS_URL

DEFAULT_FELGTBI_STATE_URL = FELGTBI_REPORTS_URL
DEFAULT_ALLOWED_HOSTS = {"felgtbi.org", "www.felgtbi.org"}
MEBIBYTE = 1024 * 1024
DEFAULT_MAX_RESPONSE_MEBIBYTES = 20
MIN_MAX_RESPONSE_MEBIBYTES = 1
MAX_MAX_RESPONSE_MEBIBYTES = 100


def _response_limit_bytes() -> int:
    configured_value = os.getenv(
        "FELGTBI_SCRAPER_MAX_RESPONSE_MB",
        str(DEFAULT_MAX_RESPONSE_MEBIBYTES),
    )
    try:
        configured_mebibytes = int(configured_value)
    except ValueError:
        configured_mebibytes = DEFAULT_MAX_RESPONSE_MEBIBYTES
    bounded_mebibytes = max(
        MIN_MAX_RESPONSE_MEBIBYTES,
        min(configured_mebibytes, MAX_MAX_RESPONSE_MEBIBYTES),
    )
    return bounded_mebibytes * MEBIBYTE


MAX_RESPONSE_BYTES = _response_limit_bytes()


@dataclass(frozen=True)
class FelgtbiPdfLink:
    title: str
    url: str
    year: int | None

    def to_dict(self) -> dict:
        return asdict(self)


def discover_felgtbi_pdfs(
    page_url: str = DEFAULT_FELGTBI_STATE_URL,
    *,
    timeout_seconds: int = 10,
) -> list[dict]:
    _validate_felgtbi_url(page_url)
    request = Request(page_url, headers={"User-Agent": "RainbowLens-Datahub/1.0"})
    opener = build_opener(_SafeRedirectHandler())
    with opener.open(request, timeout=max(1, min(timeout_seconds, 30))) as response:
        content_type = str(response.headers.get("Content-Type") or "").casefold()
        if content_type and "text/html" not in content_type:
            raise ValueError("page_url did not return HTML")
        response_bytes = response.read(MAX_RESPONSE_BYTES + 1)
        if len(response_bytes) > MAX_RESPONSE_BYTES:
            raise ValueError("page_url response is too large")
        html_text = response_bytes.decode("utf-8", errors="replace")
    return [link.to_dict() for link in parse_felgtbi_pdf_links(html_text, base_url=page_url)]


def parse_felgtbi_pdf_links(html_text: str, *, base_url: str) -> list[FelgtbiPdfLink]:
    parser = _PdfAnchorParser(base_url)
    parser.feed(html_text)
    return parser.links


class _PdfAnchorParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[FelgtbiPdfLink] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attributes = {key.lower(): value for key, value in attrs if value}
        href = attributes.get("href")
        if href and ".pdf" in href.lower():
            self._current_href = href
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._current_href:
            return
        url = urljoin(self.base_url, self._current_href)
        title = " ".join(" ".join(self._current_text).split()) or url.rsplit("/", 1)[-1]
        if _is_allowed_felgtbi_url(url):
            self.links.append(FelgtbiPdfLink(title=title, url=url, year=_extract_year(title, url)))
        self._current_href = None
        self._current_text = []


def _extract_year(*values: str) -> int | None:
    for value in values:
        match = YEAR_PATTERN.search(value)
        if match:
            return int(match.group(1))
    return None


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_felgtbi_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _validate_felgtbi_url(value: str) -> None:
    if not _is_allowed_felgtbi_url(value):
        raise ValueError("page_url must use HTTPS on an approved FELGTBI host")


def _is_allowed_felgtbi_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme == "https" and (parsed.hostname or "").casefold() in _allowed_hosts()


def _allowed_hosts() -> set[str]:
    configured = {
        item.strip().casefold()
        for item in os.getenv("FELGTBI_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }
    return configured or DEFAULT_ALLOWED_HOSTS
