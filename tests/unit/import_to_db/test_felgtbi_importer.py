import pytest

from app.infrastructure.storage import supabase_public_image_url
from app.modules.imports.felgtbi.importer import (
    StorageUploadError,
    _clean_figure_caption_title,
    _extract_figure_segments,
    _layout_visual_bbox,
    _resolve_report_title,
    _upload_figure_with_retries,
    extract_pdf_pages,
    parse_felgtbi_text_pages,
)
from app.modules.imports.felgtbi.mongo import _prepare_indicator_document
from app.modules.imports.felgtbi.pdf_reader import repair_block_text_spacing
from app.modules.imports.felgtbi.pipeline import parse_felgtbi_pdf_bytes
from app.modules.imports.felgtbi.storage import supabase_s3_client


def test_spacing_repair_preserves_percentage_and_sentence_boundaries() -> None:
    source = "Una amplia mayoría percibe una amenaza por los discursos de odio (78%).\n"
    broken = source.replace(" ", "")
    assert repair_block_text_spacing(broken, source) == source
    assert repair_block_text_spacing(source, source) == source


def test_spacing_repair_preserves_opening_punctuation_without_adjacent_text() -> None:
    source = "Título anterior.\n¿Percibe una amenaza a sus derechos?\nOtra sección."
    assert repair_block_text_spacing("¿Percibeunaamenazaasusderechos?", source) == (
        "¿Percibe una amenaza a sus derechos?"
    )


def test_felgtbi_text_pages_extract_percentages_as_indicator_documents() -> None:
    pages = [
        {
            "page": 3,
            "text": """
Estado LGTBI+ 2026
Estado del odio
Trabajo de campo: del 29 de enero al 11 de febrero de 2026
Muestra de 800 personas LGTBI+
Dimension del odio
El 54% de las personas LGTBI+ declara haber sufrido algun hecho de odio.
""",
        }
    ]

    payload = parse_felgtbi_text_pages(pages, file_name="estado-del-odio-2026.pdf")

    assert len(payload) == 1
    document = payload[0]
    assert document["source"] == "felgtbi_estado_lgtbi"
    assert "dataset" not in document
    assert document["year"] == 2026
    assert document["report_type"] == "odio"
    assert document["category"] == "Hate crime & hate speech"
    assert document["topic"] == "Hate crime & hate speech"
    assert document["sample_size"] == 800
    assert document["fieldwork"] == "del 29 de enero al 11 de febrero de 2026"
    assert document["answers"][0]["country_code"] == "ES"
    assert document["answers"][0]["percentage"] == 54.0
    assert document["answers"][0]["unit"] == "percent"
    assert document["answers"][0]["page"] == 3
    assert "54%" in document["question"]
    assert "54%" in document["description"]
    assert document["visual_context"]["page"] == 3


def test_felgtbi_text_pages_builds_html_subsections_from_figure_captions() -> None:
    pages = [
        {
            "page": 3,
            "text": """
Estado LGTBI+ 2026
Agresiones fisicas y sexuales
La Figura 3.1 muestra que el 6% de la poblacion LGTBI+ sufrio empujones.
Figura 3.1. Agresiones fisicas y sexuales
El 4% sufrio agresiones fisicas graves.
El 4% sufrio agresiones sexuales con violencia y el 5% sufrio agresiones sexuales mediante intimidacion.
Texto introductorio sin resultados relevantes.
""",
            "blocks": [
                {
                    "x0": 85,
                    "y0": 100,
                    "x1": 460,
                    "y1": 122,
                    "text": "Agresiones fisicas y sexuales",
                },
                {
                    "x0": 85,
                    "y0": 132,
                    "x1": 510,
                    "y1": 150,
                    "text": "La Figura 3.1 muestra que el 6% de la poblacion LGTBI+ sufrio empujones.",
                },
                {
                    "x0": 85,
                    "y0": 170,
                    "x1": 510,
                    "y1": 188,
                    "text": "Figura 3.1. Agresiones fisicas y sexuales",
                },
                {
                    "x0": 85,
                    "y0": 360,
                    "x1": 510,
                    "y1": 410,
                    "text": (
                        "El 4% sufrio agresiones fisicas graves. "
                        "El 4% sufrio agresiones sexuales con violencia y el 5% "
                        "sufrio agresiones sexuales mediante intimidacion. "
                        "Texto introductorio sin resultados relevantes."
                    ),
                },
            ],
            "figures": [
                {"bbox": [80, 200, 520, 340]},
            ],
        }
    ]

    payload = parse_felgtbi_text_pages(pages, file_name="estado-del-odio-2026.pdf")

    assert len(payload) == 1
    document = payload[0]
    assert document["question"] == "Agresiones fisicas y sexuales"
    assert document["visual_context"]["bbox"] == [80.0, 200.0, 520.0, 340.0]
    assert [answer["percentage"] for answer in document["answers"]] == [6.0, 4.0, 4.0, 5.0]
    assert document["data_points"][0]["text"].startswith("La Figura 3.1 muestra que el 6%")
    assert document["paragraphs_before_figure"]
    assert document["paragraphs_after_figure"]
    assert "<h3>Agresiones fisicas y sexuales</h3>" in document["content_html"]
    assert '<figure class="report-figure">' in document["content_html"]
    assert '<img src=""' not in document["content_html"]
    assert "<code>" not in document["content_html"]
    assert "<pre>" not in document["content_html"]
    assert "&lt;h2&gt;" not in document["content_html"]
    assert document["content_html"].count("<p>") >= 2
    assert "Dato 1" not in document["content_html"]
    assert "Dato 2" not in document["content_html"]
    assert "<strong>6%</strong>" in document["content_html"]
    assert "Texto introductorio" not in document["content_html"]


def test_felgtbi_pdf_bytes_does_not_create_local_figure_asset(monkeypatch) -> None:
    import fitz

    monkeypatch.delenv("SUPABASE_S3_ENDPOINT", raising=False)
    monkeypatch.delenv("SUPABASE_S3_ACCESS_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_S3_SECRET_KEY", raising=False)

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00"
        b"\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    pdf = fitz.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((85, 90), "Estado LGTBI+ 2026", fontsize=14)
    page.insert_text((85, 120), "Agresiones fisicas y sexuales", fontsize=13)
    page.insert_text(
        (85, 150),
        "La Figura 1.1 muestra que el 17% de las personas LGTBI+ sufrio insultos.",
        fontsize=10,
    )
    page.insert_text((85, 190), "Figura 1.1. Agresiones fisicas y sexuales", fontsize=10)
    page.insert_image(fitz.Rect(85, 220, 510, 430), stream=png_bytes)
    page.insert_text((85, 470), "El 6% sufrio agresiones fisicas leves.", fontsize=10)
    page.insert_text((85, 490), "El 4% sufrio agresiones fisicas graves.", fontsize=10)
    pdf_bytes = pdf.tobytes()
    pdf.close()

    payload = parse_felgtbi_pdf_bytes(pdf_bytes, file_name="estado-del-odio-2026.pdf")

    with pytest.raises(StorageUploadError, match="supabase_storage_not_configured"):
        parse_felgtbi_pdf_bytes(
            pdf_bytes,
            file_name="estado-del-odio-2026.pdf",
            require_storage=True,
            upload_id="strict-storage-test",
        )

    assert payload
    document = payload[0]
    forbidden = {kind + "_url" for kind in ("asset", "signed", "public")}
    assert forbidden.isdisjoint(document["visual_context"])
    assert "image_storage" not in document["visual_context"]
    assert "<img " not in document["content_html"]
    assert 'loading="lazy"' not in document["content_html"]
    assert forbidden.isdisjoint(document["figure"])
    assert "image_path" not in document["figure"]
    assert "storage_path" not in document["figure"]
    assert "Dato" not in document["content_html"]
    assert "<strong>17%</strong>" in document["content_html"]
    assert "<code>" not in document["content_html"]
    assert "<pre>" not in document["content_html"]
    assert "&lt;section" not in document["content_html"]


def test_pdf_page_extraction_keeps_image_bbox_without_extracting_image_bytes(monkeypatch) -> None:
    import fitz

    pdf = fitz.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((85, 90), "Estado LGTBI+ 2026", fontsize=14)
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 90), False)
    pixmap.clear_with(0x336699)
    page.insert_image(fitz.Rect(85, 180, 505, 495), pixmap=pixmap)
    pdf_bytes = pdf.tobytes()
    pdf.close()

    text_page_flags: list[int | None] = []
    original_get_textpage = fitz.Page.get_textpage

    def recording_get_textpage(page, *args, **kwargs):
        text_page_flags.append(kwargs.get("flags"))
        return original_get_textpage(page, *args, **kwargs)

    monkeypatch.setattr(fitz.Page, "get_textpage", recording_get_textpage)

    pages = extract_pdf_pages(pdf_bytes)

    assert text_page_flags
    extraction_flags = text_page_flags[0]
    assert extraction_flags is not None
    assert not extraction_flags & fitz.TEXT_PRESERVE_IMAGES
    assert pages[0]["figures"] == [{"kind": "figure", "bbox": [85.0, 180.0, 505.0, 495.0]}]


def test_block_spacing_is_restored_from_the_same_page_text_layer() -> None:
    broken = "La distribución dela población LGTBI+en función desu identidad"
    page_text = "La distribución\nde\nla población\nLGTBI+\nen función\nde\nsu identidad."

    restored = repair_block_text_spacing(broken, page_text)

    assert " ".join(restored.split()) == (
        "La distribución de la población LGTBI+ en función de su identidad"
    )


def test_pdf_page_extraction_detects_vector_chart_regions() -> None:
    import fitz

    pdf = fitz.open()
    page = pdf.new_page(width=595, height=842)
    page.draw_rect(fitz.Rect(110, 210, 490, 520), color=(0.8, 0.2, 0.4))
    page.draw_rect(fitz.Rect(150, 350, 210, 500), fill=(0.8, 0.2, 0.4))
    pdf_bytes = pdf.tobytes()
    pdf.close()

    pages = extract_pdf_pages(pdf_bytes)

    assert any(figure["kind"] == "vector" for figure in pages[0]["figures"])


def test_figure_extraction_ignores_toc_references_and_keeps_real_tables() -> None:
    pages = [
        {
            "page": 3,
            "width": 595,
            "height": 842,
            "text": "Indice de figuras\nGrafico 1: Resultado principal .......... 12",
            "blocks": [
                {
                    "x0": 85,
                    "y0": 120,
                    "x1": 510,
                    "y1": 140,
                    "text": "Grafico 1: Resultado principal .......... 12",
                }
            ],
            "figures": [],
        },
        {
            "page": 12,
            "width": 595,
            "height": 842,
            "text": "Tabla 1: Resultado principal\nTotal 42%",
            "blocks": [
                {
                    "x0": 85,
                    "y0": 120,
                    "x1": 510,
                    "y1": 140,
                    "text": "Tabla 1: Resultado principal",
                },
                {"x0": 120, "y0": 180, "x1": 460, "y1": 300, "text": "Total 42%"},
            ],
            "figures": [{"kind": "vector", "bbox": [110, 165, 480, 315]}],
        },
    ]

    segments = _extract_figure_segments(pages)

    assert len(segments) == 1
    assert segments[0]["page"] == 12
    assert segments[0]["caption"] == "Tabla 1: Resultado principal"


def test_vector_chart_crop_stops_before_the_first_narrative_paragraph() -> None:
    pages = [
        {
            "page": 14,
            "width": 595,
            "height": 842,
            "text": "Grafico 1: Distribucion\n55% 45%\nEl resultado muestra una diferencia clara entre ambos grupos.",
            "blocks": [
                {"x0": 85, "y0": 100, "x1": 510, "y1": 120, "text": "Grafico 1: Distribucion"},
                {"x0": 120, "y0": 175, "x1": 460, "y1": 280, "text": "55% 45% Grupo A Grupo B"},
                {
                    "x0": 85,
                    "y0": 330,
                    "x1": 510,
                    "y1": 380,
                    "text": "El resultado muestra una diferencia clara entre ambos grupos y debe conservarse como parrafo.",
                },
            ],
            "figures": [{"kind": "vector", "bbox": [120, 170, 460, 285]}],
        }
    ]

    segment = _extract_figure_segments(pages)[0]

    assert segment["bbox"][3] < 330
    assert segment["after_description"].startswith("El resultado muestra")


def test_chart_crop_preserves_labels_outside_the_report_text_margins() -> None:
    # El gráfico 4 del informe socioeconómico 2023 coloca etiquetas a 6 pt
    # del borde. Los márgenes del texto del informe no delimitan el gráfico.
    blocks = [
        {"x0": 85, "y0": 426, "x1": 438, "y1": 436, "text": "Gráfico 4: Identidad"},
        {"x0": 9, "y0": 485, "x1": 75, "y1": 495, "text": "Población LGTBI+"},
        {"x0": 6, "y0": 705, "x1": 75, "y1": 715, "text": "Persona No binaria"},
        {"x0": 87, "y0": 705, "x1": 590, "y1": 715, "text": "6,30% 25,00% 62,50% 12,50%"},
    ]
    page = {
        "page": 9,
        "width": 595,
        "height": 842,
        "text": "\n".join(block["text"] for block in blocks),
        "blocks": blocks,
        "figures": [],
    }

    segment = _extract_figure_segments([page])[0]
    x0, y0, x1, y1 = segment["bbox"]

    assert 0 <= x0 < 6
    assert 590 < x1 <= 595
    assert y0 >= 436
    assert 715 < y1 < 790


def test_side_by_side_captions_are_associated_by_horizontal_geometry() -> None:
    pages = [
        {
            "page": 24,
            "width": 595,
            "height": 842,
            "text": "Grafico 16: Izquierda\nGrafico 17: Derecha",
            "blocks": [
                {"x0": 85, "y0": 120, "x1": 290, "y1": 145, "text": "Grafico 16: Izquierda"},
                {"x0": 305, "y0": 120, "x1": 510, "y1": 145, "text": "Grafico 17: Derecha"},
            ],
            "figures": [
                {"kind": "figure", "bbox": [90, 170, 290, 340]},
                {"kind": "figure", "bbox": [305, 170, 510, 340]},
            ],
        }
    ]

    segments = _extract_figure_segments(pages)

    assert [segment["bbox"] for segment in segments] == [
        [90.0, 170.0, 290.0, 340.0],
        [305.0, 170.0, 510.0, 340.0],
    ]


def test_layout_crop_prefers_visual_geometry_over_introductory_text() -> None:
    page = {
        "width": 595,
        "height": 842,
        "figures": [{"kind": "vector", "bbox": [117.5, 501.3, 477.5, 717.3]}],
    }

    bbox = _layout_visual_bbox(page, [], {"y1": 130}, [])

    assert bbox == [111.5, 495.3, 483.5, 723.3]


def test_report_and_figure_titles_remove_repeated_collection_reference() -> None:
    full_text = """
    Han participado en la elaboracion de este informe.
    Titulo: Estado del odio: Estado LGTBI+ 2024
    Coleccion: Estado LGTBI+ 2024
    """

    assert _resolve_report_title(full_text, "Informe-DDOO_24.pdf") == "Estado del odio"
    assert (
        _clean_figure_caption_title("Grafico 8: Donde sufriste la agresion, Estado LGTBI+ 2024")
        == "Donde sufriste la agresion"
    )


def test_supabase_image_source_is_derived_only_from_storage_path(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co/")
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", "report figures")

    result = supabase_public_image_url("2026/report/section/figura 1.webp")

    assert result == (
        "https://example.supabase.co/storage/v1/object/public/"
        "report%20figures/2026/report/section/figura%201.webp"
    )


def test_supabase_s3_client_is_reused_with_bounded_timeouts(monkeypatch) -> None:
    import boto3

    clients = []

    def fake_client(service_name, **kwargs):
        clients.append((service_name, kwargs))
        return object()

    supabase_s3_client.cache_clear()
    monkeypatch.setattr(boto3, "client", fake_client)

    first = supabase_s3_client("https://storage.test", "access", "secret", "eu-west-1")
    second = supabase_s3_client("https://storage.test", "access", "secret", "eu-west-1")
    supabase_s3_client.cache_clear()

    assert first is second
    assert len(clients) == 1
    config = clients[0][1]["config"]
    assert config.connect_timeout == 3
    assert config.read_timeout == 10
    assert config.retries["total_max_attempts"] == 2


def test_transient_figure_upload_is_retried_without_changing_storage_identity(monkeypatch) -> None:
    calls: list[str] = []

    def fake_upload(**kwargs):
        calls.append(kwargs["storage_path"])
        if len(calls) < 3:
            return {"status": "failed", "error": "head_object:ConnectTimeoutError"}
        return {"status": "reused", "storage_path": kwargs["storage_path"]}

    monkeypatch.setattr(
        "app.modules.imports.felgtbi.importer._upload_figure_to_supabase",
        fake_upload,
    )
    monkeypatch.setattr("app.modules.imports.felgtbi.importer.time.sleep", lambda _value: None)

    result = _upload_figure_with_retries(
        image_bytes=b"image",
        storage_path="2026/report/figure.webp",
        mime_type="image/webp",
        checksum="abc",
    )

    assert result["status"] == "reused"
    assert calls == ["2026/report/figure.webp"] * 3


def test_felgtbi_persistence_keeps_only_storage_key_for_image_location() -> None:
    forbidden = [kind + "_url" for kind in ("asset", "signed", "public")]
    figure = {
        "storage_path": "2026/report/section/figure.webp",
        "caption": "Figure 1",
        **{key: "https://legacy.test/image.webp" for key in forbidden},
        "image_path": "/assets/" + "generated/image.webp",
    }
    document = {
        "source": "felgtbi_estado_lgtbi",
        "code": "section-1",
        "year": 2026,
        "question": "Question",
        "figure": figure,
    }

    prepared = _prepare_indicator_document(document)

    assert prepared["figure"] == {
        "storage_path": "2026/report/section/figure.webp",
        "caption": "Figure 1",
    }


def test_felgtbi_text_pages_infers_fra_compatible_topic_names() -> None:
    pages = [
        {
            "page": 7,
            "text": """
Estado LGTBI+ 2025
Ambito laboral
El 32,5% de las personas encuestadas evita visibilizarse en el trabajo.
""",
        }
    ]

    payload = parse_felgtbi_text_pages(pages, file_name="estado-socioeconomico-2025.pdf")

    assert payload[0]["category"] == "Spanish LGBTIQ+ indicators"
    assert payload[0]["topic"] == "Employment"
    assert payload[0]["answers"][0]["percentage"] == 32.5


def test_felgtbi_text_pages_splits_multiple_percentages_into_indicators() -> None:
    pages = [
        {
            "page": 5,
            "text": """
Estado LGTBI+ 2026
Dimension del odio
Un 22% de agresion, un 36% de acoso y un 29% de discriminacion.
""",
        }
    ]

    payload = parse_felgtbi_text_pages(pages, file_name="estado-del-odio-2026.pdf")

    assert [item["answers"][0]["percentage"] for item in payload] == [22.0, 36.0, 29.0]
    assert [item["question"] for item in payload] == [
        "Un 22% de agresion",
        "un 36% de acoso",
        "un 29% de discriminacion",
    ]
    assert all("Un 22% de agresion" in item["description"] for item in payload)


def test_felgtbi_text_pages_does_not_treat_year_as_sample_size() -> None:
    pages = [
        {
            "page": 1,
            "text": """
Estado LGTBI+ 2026
Dimension del odio
El 44% de las personas LGTBI+ declara haber sido victima de odio.
""",
        }
    ]

    payload = parse_felgtbi_text_pages(pages, file_name="estado-del-odio-2026.pdf")

    assert "sample_size" not in payload[0]
    assert "sample_size" not in payload[0]["answers"][0]
