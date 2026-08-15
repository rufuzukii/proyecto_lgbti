import os
import re
import unicodedata
from functools import cache
from pathlib import Path

import pytest

from app.import_to_db.felgtbi.importer import (
    extract_pdf_pages,
    parse_felgtbi_text_pages,
)

_REFERENCE_ROOT_VALUE = os.getenv("FELGTBI_REFERENCE_PDF_DIR")
REFERENCE_ROOT = Path(_REFERENCE_ROOT_VALUE) if _REFERENCE_ROOT_VALUE else None
COLLECTION_SUFFIX = re.compile(r"estado\s+lgtbi\+?\s+20\d{2}\s*$", re.IGNORECASE)
REFERENCE_CASES = (
    (
        "2024",
        "estado-de-la-educacion-lgtbi-2024_final.pdf",
        37,
        "Estado de la educación LGTBI+",
    ),
    ("2024", "estado-politico-2024.pdf", 35, "Estado político"),
    ("2024", "informe-ddoo_24.pdf", 60, "Estado del odio"),
    ("2024", "informe-estado-socioeconomico_24.pdf", 29, "Estado socioeconómico"),
    ("2024", "informe-felgtbi-2024.pdf", 20, "El voto en la comunidad LGTBI+"),
    ("2023", "ano-tematico23_familias_felgtbi.pdf", 10, "Estado de la diversidad familiar"),
    ("2023", "estadopolitico.pdf", 15, "Estado político LGTBI+"),
    ("2023", "i-informe-estado-socioeconomico_felgtbi.pdf", 30, "ESTADO SOCIOECÓMICO LGTBI+"),
    ("2023", "informe_ddoo23_felgtbi.pdf", 25, "Estado del odio"),
    ("2023", "informediversidadempresa_felgtbi.pdf", 25, "Diversidad en la empresa"),
    ("2025", "estado-lgtbi-estado-odio-2025.pdf", 50, "Estado del odio"),
    ("2025", "estado-politico-2025.pdf", 35, "Estado Político"),
    (
        "2025",
        "informe-estado-lgtbi-2025.pdf",
        20,
        "El voto en la comunidad LGTBI+",
    ),
    ("2025", "informe-matrimonio_25.pdf", 35, "20 años de matrimonio igualitario"),
    ("2025", "informe-sexilio-2025.pdf", 20, "Sexilio"),
    (
        "2025",
        "informe-socio-economico_estado-lgrbi-2025_.pdf",
        45,
        "Estado socioeconómico",
    ),
    (
        "2026",
        "activismo y derechos.pdf",
        25,
        "Derechos LGTBI+. El papel del activismo y del apoyo institucional",
    ),
    ("2026", "el voto en la comunidad lgtbi+.pdf", 15, "El voto en la comunidad LGTBI+"),
    ("2026", "estado del odio.pdf", 50, "Estado del odio"),
)


def _ascii_name(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()


def _reference_pdf(year: str, normalized_name: str) -> Path:
    if REFERENCE_ROOT is None:
        pytest.skip("FELGTBI_REFERENCE_PDF_DIR no configurado")
    directory = REFERENCE_ROOT / year
    if directory.is_dir():
        for candidate in directory.glob("*.pdf"):
            if _ascii_name(candidate.name) == normalized_name:
                return candidate
    pytest.skip(f"PDF de referencia no disponible: {year}/{normalized_name}")


@cache
def _parse_reference(year: str, normalized_name: str):
    path = _reference_pdf(year, normalized_name)
    pages = extract_pdf_pages(path.read_bytes())
    documents = parse_felgtbi_text_pages(pages, file_name=path.name)
    return pages, documents


@pytest.mark.parametrize(
    ("year", "normalized_name", "minimum_documents", "expected_title"),
    REFERENCE_CASES,
)
def test_reference_pdf_figures_have_bounded_crops_and_clean_titles(
    year: str,
    normalized_name: str,
    minimum_documents: int,
    expected_title: str,
) -> None:
    pages, documents = _parse_reference(year, normalized_name)
    page_by_number = {int(page["page"]): page for page in pages}

    assert len(documents) >= minimum_documents
    assert {document["report_title"] for document in documents} == {expected_title}
    assert all(
        not COLLECTION_SUFFIX.search(str(document.get("figure_caption") or ""))
        for document in documents
    )

    figure_documents = [
        document
        for document in documents
        if isinstance(document.get("figure"), dict)
    ]
    assert figure_documents
    for document in figure_documents:
        bbox = (document.get("visual_context") or {}).get("bbox")
        assert isinstance(bbox, list) and len(bbox) == 4
        page = page_by_number[int(document["page"])]
        assert 0 <= bbox[0] < bbox[2] <= float(page["width"])
        assert 0 <= bbox[1] < bbox[3] <= float(page["height"])

    for document in documents:
        if (document.get("extraction") or {}).get("method") != "narrative_section":
            continue
        assert document.get("figure") is None
        assert document["paragraphs"]


def test_ddoo_2024_reference_crops_exclude_known_following_paragraphs() -> None:
    _pages, documents = _parse_reference("2024", "informe-ddoo_24.pdf")
    graph_1 = next(
        document
        for document in documents
        if document["page"] == 14 and document["figure_number"] == "1"
    )
    graph_8 = next(
        document
        for document in documents
        if document["page"] == 23 and document["figure_number"] == "8"
    )

    assert graph_1["visual_context"]["bbox"][3] < 344.6
    assert graph_8["visual_context"]["bbox"][3] < 396.5


def test_family_and_political_reference_layouts_use_distinct_visual_regions() -> None:
    _family_pages, family_documents = _parse_reference(
        "2023",
        "ano-tematico23_familias_felgtbi.pdf",
    )
    _political_pages, political_documents = _parse_reference("2023", "estadopolitico.pdf")
    family_page_21 = next(document for document in family_documents if document["page"] == 21)
    political_page_7 = [document for document in political_documents if document["page"] == 7]

    assert family_page_21["visual_context"]["bbox"][1] >= 490
    assert len(political_page_7) == 2
    assert (
        political_page_7[0]["visual_context"]["bbox"]
        != political_page_7[1]["visual_context"]["bbox"]
    )


def test_2025_political_legend_is_not_mistaken_for_narrative() -> None:
    _pages, documents = _parse_reference("2025", "estado-politico-2025.pdf")
    graph_27 = next(
        document
        for document in documents
        if document["page"] == 36 and document["figure_number"] == "27"
    )

    assert graph_27["visual_context"]["page"] == 36
    bbox = graph_27["visual_context"]["bbox"]
    assert bbox[1] < 200
    assert bbox[3] < 510.9


def test_2025_sexilio_bottom_captions_use_next_page_visuals() -> None:
    _pages, documents = _parse_reference("2025", "informe-sexilio-2025.pdf")
    expected_visual_pages = {
        (28, "11"): 29,
        (32, "3"): 33,
        (37, "5"): 38,
        (40, "6"): 41,
    }

    for (caption_page, figure_number), visual_page in expected_visual_pages.items():
        document = next(
            item
            for item in documents
            if item["page"] == caption_page and item["figure_number"] == figure_number
        )
        assert document["visual_context"]["page"] == visual_page
        assert document["visual_context"]["bbox"]
