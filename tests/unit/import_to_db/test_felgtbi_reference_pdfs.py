from __future__ import annotations

import fitz
import pytest

from app.modules.imports.felgtbi.importer import (
    _clean_block_paragraph,
    _clean_data_sentence,
    extract_pdf_pages,
    parse_felgtbi_text_pages,
)


@pytest.mark.parametrize("cleaner", [_clean_block_paragraph, _clean_data_sentence])
@pytest.mark.parametrize(
    "text",
    [
        "Como se puede observar en la Figura 3.1, el 18% declara discriminación.",
        "Los resultados se muestran en la Figura 1. El estudio analiza la orientación sexual.",
    ],
)
def test_narrative_keeps_figure_references_and_sentence_separators(cleaner, text):
    assert cleaner(text) == text.rstrip(".")


@pytest.fixture
def controlled_report_pdf() -> bytes:
    """Informe pequeño reproducible con texto, pies, vectores y metadatos para probar la
    extracción.
    """
    pdf = fitz.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((85, 90), "Estado del odio", fontsize=18)
    page.insert_text((85, 130), "Agresiones fisicas", fontsize=14)
    page.insert_text((85, 170), "Figura 1. Agresiones fisicas", fontsize=10)
    page.draw_rect(fitz.Rect(100, 210, 490, 430), fill=(0.7, 0.2, 0.4))
    page.insert_text(
        (85, 470),
        "El 18,5% de las personas encuestadas declara discriminacion.",
        fontsize=9,
    )
    content = pdf.tobytes()
    pdf.close()
    return content


def test_controlled_pdf_extracts_page_geometry_and_visual_regions(
    controlled_report_pdf: bytes,
) -> None:
    pages = extract_pdf_pages(controlled_report_pdf)

    assert len(pages) == 1
    page = pages[0]
    assert page["page"] == 1
    assert page["width"] == 595
    assert page["height"] == 842
    assert "Figura 1. Agresiones fisicas" in page["text"]
    assert page["figures"] == [{"bbox": [100.0, 210.0, 490.0, 430.0], "kind": "vector"}]


def test_controlled_pdf_parses_caption_text_answers_and_metadata(
    controlled_report_pdf: bytes,
) -> None:
    pages = extract_pdf_pages(controlled_report_pdf)
    documents = parse_felgtbi_text_pages(pages, file_name="estado-del-odio-2026.pdf")

    assert len(documents) == 1
    document = documents[0]
    assert document["report_title"] == "Estado del odio"
    assert document["year"] == 2026
    assert document["figure_number"] == "1"
    assert document["figure_caption"] == "Figura 1: Agresiones fisicas"
    assert document["extraction"]["method"] == "figure_caption"
    assert document["paragraphs"] == ["El 18,5% de las personas encuestadas declara discriminacion"]
    assert document["answers"][0]["percentage"] == 18.5
    bbox = document["visual_context"]["bbox"]
    assert 0 <= bbox[0] < bbox[2] <= pages[0]["width"]
    assert 0 <= bbox[1] < bbox[3] <= pages[0]["height"]


def test_controlled_pdf_produces_stable_source_identity(
    controlled_report_pdf: bytes,
) -> None:
    pages = extract_pdf_pages(controlled_report_pdf)

    first = parse_felgtbi_text_pages(pages, file_name="estado-del-odio-2026.pdf")
    second = parse_felgtbi_text_pages(pages, file_name="estado-del-odio-2026.pdf")

    assert first[0]["code"] == second[0]["code"]
    assert first[0]["source_document_id"] == second[0]["source_document_id"]
