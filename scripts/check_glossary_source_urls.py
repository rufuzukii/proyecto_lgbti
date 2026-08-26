"""Check glossary source redirects and HTTP reachability outside application runtime."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

CATALOG_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "app" / "edu" / "data" / "glossary.json"
)
TIMEOUT_SECONDS = 12


def _catalog_urls() -> tuple[str, ...]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return tuple(
        sorted({source["url"] for term in payload for source in term.get("sources", [])})
    )


def _request(url: str, method: str):
    request = Request(
        url,
        method=method,
        headers={"User-Agent": "RainbowLens-source-check/1.0"},
    )
    return urlopen(request, timeout=TIMEOUT_SECONDS)


def _check(url: str) -> tuple[bool, str]:
    try:
        try:
            response = _request(url, "HEAD")
        except HTTPError as error:
            if error.code == 405:
                response = _request(url, "GET")
            elif error.code in {401, 403}:
                final_url = error.geturl()
                secure = urlsplit(final_url).scheme == "https"
                return secure, f"{error.code} protected, final={final_url}"
            else:
                raise
        with response:
            final_url = response.geturl()
            status = response.status
        secure = urlsplit(final_url).scheme == "https"
        return secure and status < 400, f"{status}, final={final_url}"
    except (HTTPError, URLError, TimeoutError) as error:
        return False, f"{type(error).__name__}: {error}"


def main() -> int:
    urls = _catalog_urls()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = tuple(zip(urls, executor.map(_check, urls), strict=True))
    for url, (ok, detail) in results:
        print(f"{'PASS' if ok else 'FAIL'} {url} -> {detail}")
    return 0 if all(ok for _url, (ok, _detail) in results) else 1


if __name__ == "__main__":
    sys.exit(main())

