import pytest

from app.modules.imports.felgtbi import scraper
from app.modules.imports.felgtbi.scraper import (
    discover_felgtbi_pdfs,
    parse_felgtbi_pdf_links,
)


def test_response_limit_defaults_to_previous_20_mebibyte_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FELGTBI_SCRAPER_MAX_RESPONSE_MB", raising=False)

    assert scraper._response_limit_bytes() == 20 * scraper.MEBIBYTE


def test_response_limit_is_configurable_and_safely_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FELGTBI_SCRAPER_MAX_RESPONSE_MB", "35")
    assert scraper._response_limit_bytes() == 35 * scraper.MEBIBYTE

    monkeypatch.setenv("FELGTBI_SCRAPER_MAX_RESPONSE_MB", "invalid")
    assert scraper._response_limit_bytes() == 20 * scraper.MEBIBYTE

    monkeypatch.setenv("FELGTBI_SCRAPER_MAX_RESPONSE_MB", "1000")
    assert scraper._response_limit_bytes() == 100 * scraper.MEBIBYTE


def test_discover_felgtbi_pdfs_rejects_non_http_urls() -> None:
    with pytest.raises(ValueError, match="approved FELGTBI host"):
        discover_felgtbi_pdfs("file:///tmp/report.html")
    with pytest.raises(ValueError, match="approved FELGTBI host"):
        discover_felgtbi_pdfs("https://example.test/report.html")


def test_parse_felgtbi_pdf_links_discovers_absolute_pdf_urls() -> None:
    html_text = """
<html>
  <body>
    <a href="/wp-content/uploads/2026/estado-del-odio-2026.pdf">Estado del odio 2026</a>
    <a href="https://example.test/estado-socioeconomico-2025.pdf">Estado socioeconomico</a>
    <a href="/not-a-pdf">HTML page</a>
  </body>
</html>
"""

    links = parse_felgtbi_pdf_links(
        html_text,
        base_url="https://felgtbi.org/que-hacemos/investigacion/estado-lgtbi/",
    )

    assert [link.title for link in links] == [
        "Estado del odio 2026",
    ]
    assert links[0].url == "https://felgtbi.org/wp-content/uploads/2026/estado-del-odio-2026.pdf"
    assert links[0].year == 2026
