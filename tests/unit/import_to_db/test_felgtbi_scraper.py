from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.import_to_db.felgtbi.scraper import parse_felgtbi_pdf_links


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
        "Estado socioeconomico",
    ]
    assert links[0].url == "https://felgtbi.org/wp-content/uploads/2026/estado-del-odio-2026.pdf"
    assert links[0].year == 2026
    assert links[1].url == "https://example.test/estado-socioeconomico-2025.pdf"
    assert links[1].year == 2025
