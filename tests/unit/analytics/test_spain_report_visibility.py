from pathlib import Path
import sys
from types import SimpleNamespace

from flask import Flask

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app.analytics.repository as repository
from app.analytics.repository import (
    FelgtbiDocument,
    _has_valid_spain_section,
    _spain_navigation_projection,
)
from app.cache import init_cache
from app.dash.pages.spain import (
    SPAIN_SLOT_CLASS,
    _figure_component,
    _spain_document_view_state,
    _spain_visualization_shell,
)
from app.import_to_db.felgtbi.importer import _attach_page_assets, parse_felgtbi_text_pages
from app.import_to_db.felgtbi.mongo import _prepare_indicator_document
from app.import_to_db.felgtbi.semantics import (
    ExtractionContext,
    analyze_chart_residual_text,
    clean_figure_paragraphs,
    sanitize_report_document,
)


def test_textual_report_section_is_visible_without_a_numeric_chart() -> None:
    document = {
        "question": "Conclusiones",
        "section_title": "Conclusiones",
        "paragraphs": [
            "El informe incluye conclusiones cualitativas relevantes para interpretar los resultados."
        ],
    }

    assert _has_valid_spain_section(document) is True


def test_empty_report_section_is_not_visible() -> None:
    assert _has_valid_spain_section({"question": "", "description": ""}) is False


def test_structured_section_activates_the_visible_dash_report_slot() -> None:
    document = {
        "report_title": "Informe de participación 2026",
        "section_title": "Participación política",
        "subsection_title": "Estimación de voto",
        "paragraphs_before_figure": ["Resultados sobre la población encuestada."],
        "figure": {"caption": "Estimación de voto", "number": "4"},
        "data_points": [
            {"text": "PSOE: 44,5%", "value": 44.5, "percentage": 44.5}
        ],
        "answers": [{"answer": "PSOE", "value": 44.5, "percentage": 44.5}],
    }

    state = _spain_document_view_state(document)

    assert state[1] != SPAIN_SLOT_CLASS
    assert state[3] == SPAIN_SLOT_CLASS
    assert state[2] != []


def test_spain_visualization_keeps_content_without_duplicate_detail_panel() -> None:
    panels = _spain_visualization_shell()

    assert len(panels) == 1
    assert panels[0].children[0].children == "Contenido"
    assert len(_spain_document_view_state(None)) == 9


def test_layout_pdf_page_extracts_vector_chart_without_figure_caption() -> None:
    pages = [
        {
            "page": 4,
            "width": 960,
            "height": 540,
            "drawing_count": 12,
            "text": """
Informe Estado LGTBI 2026
Estimación de voto
¿A qué opción votarías? (% sobre la población encuestada)
44,5
PSOE
31,2
PP
""",
            "blocks": [
                {
                    "x0": 48,
                    "y0": 36,
                    "x1": 430,
                    "y1": 65,
                    "text": "Estimación de voto",
                    "font_size": 24,
                    "is_bold": True,
                },
                {
                    "x0": 48,
                    "y0": 88,
                    "x1": 650,
                    "y1": 112,
                    "text": "¿A qué opción votarías? (% sobre la población encuestada)",
                    "font_size": 12,
                    "is_italic": True,
                },
                {"x0": 120, "y0": 180, "x1": 165, "y1": 198, "text": "PSOE"},
                {"x0": 450, "y0": 180, "x1": 490, "y1": 198, "text": "44,5"},
                {"x0": 130, "y0": 230, "x1": 160, "y1": 248, "text": "PP"},
                {"x0": 360, "y0": 230, "x1": 400, "y1": 248, "text": "31,2"},
            ],
            "figures": [],
        }
    ]

    payload = parse_felgtbi_text_pages(
        pages,
        file_name="informe-participacion-2026.pdf",
    )

    assert len(payload) == 1
    document = payload[0]
    assert document["schema_version"] == 2
    assert document["page"] == 4
    assert document["extraction"]["method"] == "pdf_text_layout"
    assert document["visual_context"]["bbox"]
    assert [answer["percentage"] for answer in document["answers"]] == [44.5, 31.2]
    assert [point["label"] for point in document["data_points"]] == ["PSOE", "PP"]


def test_chart_percentage_sequence_is_removed_with_high_confidence() -> None:
    analysis = analyze_chart_residual_text(
        "42,40% 43,20% 39,30% 38,50% 35,20% 26,50% 26,90% 29,40%",
        ExtractionContext(near_figure=True, position="after"),
    )

    assert analysis.is_residual is True
    assert analysis.confidence >= 0.8
    assert "many_percentages" in analysis.reasons


def test_chart_labels_and_years_are_removed_but_real_percentage_sentences_remain() -> None:
    residual = (
        "10,80% 10,60% 8,90% 7,70% 6,50% Minoría religiosa Minoría étnica "
        "Diversidad funcional Migrante Año 2025 Año 2024"
    )
    narrative = (
        "El 8,9 % de las personas LGTBI+ se autoperciben como pertenecientes a una minoría "
        "étnica, un 7,7 % se categorizan como personas con alguna discapacidad y un 6,5 % "
        "se define como personas migrantes."
    )
    short_narrative = (
        "Destaca el 10,8 % que se define como perteneciente a una minoría religiosa."
    )
    extracted_without_final_period = (
        "Aunque algunas personas no denuncian porque no le dieron importancia (25%), por "
        "vergüenza (19%), porque no se les ocurrió (13%), por miedo (12%) o por desconfianza "
        "(11%), la mayoría explica su decisión mediante razones relacionadas con el trato recibido"
    )

    cleaned = clean_figure_paragraphs(
        [],
        [residual, narrative, short_narrative, extracted_without_final_period],
    )

    assert residual not in cleaned.after
    assert narrative in cleaned.after
    assert short_narrative in cleaned.after
    assert extracted_without_final_period in cleaned.after
    assert len(cleaned.removed) == 1


def test_caption_duplicate_is_kept_only_as_figure_caption() -> None:
    caption = "Gráfico 10: Otras interseccionalidades de las personas LGTBI+."
    duplicate = "Otras interseccionalidades de las personas LGTBI+."

    cleaned = clean_figure_paragraphs([duplicate], [], caption=caption)

    assert cleaned.before == []
    assert "duplicate_figure_caption" in cleaned.removed[0][1].reasons


def test_defensive_read_filter_preserves_order_and_removes_only_residual_blocks() -> None:
    narrative = "La encuesta incluye un indicador para medir la pertenencia a una minoría."
    residual = "42,40% 43,20% 39,30% 38,50% 35,20% 26,50%"
    document = {
        "figure": {"caption": "Gráfico 10: Resultado", "storage_path": "reports/chart.webp"},
        "paragraphs_before_figure": [narrative],
        "paragraphs_after_figure": [residual, "Destaca el 10,8 % de las respuestas."],
    }

    cleaned = sanitize_report_document(document)

    assert cleaned["paragraphs"] == [narrative, "Destaca el 10,8 % de las respuestas."]
    assert cleaned["figure"]["storage_path"] == "reports/chart.webp"


def test_persistence_cleanup_never_stores_residual_text_or_derived_image_urls() -> None:
    residual = "42,40% 43,20% 39,30% 38,50% 35,20% 26,50%"
    document = {
        "source": "felgtbi_estado_lgtbi",
        "year": 2026,
        "code": "section-1",
        "question": "Resultados",
        "paragraphs_after_figure": [residual],
        "figure": {
            "caption": "Gráfico 1: Resultados",
            "storage_path": "reports/chart.webp",
            "public_url": "https://example.invalid/chart.webp",
            "width": 1200,
            "height": 800,
        },
    }

    prepared = _prepare_indicator_document(document, original_filename="report.pdf")

    assert prepared["paragraphs_after_figure"] == []
    assert prepared["figure"]["storage_path"] == "reports/chart.webp"
    assert prepared["figure"]["width"] == 1200
    assert prepared["figure"]["height"] == 800
    assert "public_url" not in prepared["figure"]


def test_navigation_projection_does_not_fetch_heavy_section_content() -> None:
    projection = _spain_navigation_projection()

    assert projection["code"] == 1
    assert projection["page"] == 1
    for field in ("content_html", "paragraphs", "data_points", "figure", "visual_context"):
        assert field not in projection


def test_report_image_is_lazy_and_uses_only_storage_path(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.dash.pages.spain.supabase_public_image_url",
        lambda storage_path: f"https://storage.example/{storage_path}",
    )
    component = _figure_component(
        {
            "figure": {
                "caption": "Gráfico 1",
                "storage_path": "reports/chart.webp",
                "public_url": "https://wrong.example/chart.webp",
                "width": 1200,
                "height": 800,
            }
        }
    )

    assert component is not None
    image = component.children[0]
    assert image.src is None
    assert image.to_plotly_json()["props"]["data-lazy-src"] == (
        "https://storage.example/reports/chart.webp"
    )
    assert image.width == 1200
    assert image.height == 800
    fallback = component.children[1]
    assert "report-figure-load-error" in fallback.className
    assert fallback.hidden is True


def test_successful_figure_upload_attaches_storage_path_and_dimensions(monkeypatch) -> None:
    class FakePage:
        def get_pixmap(self, **_kwargs):
            return object()

    class FakeDocument:
        page_count = 1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def __getitem__(self, _index):
            return FakePage()

    fake_fitz = SimpleNamespace(
        open=lambda **_kwargs: FakeDocument(),
        Rect=lambda *values: values,
        Matrix=lambda *values: values,
    )
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)
    monkeypatch.setattr(
        "app.import_to_db.felgtbi.importer._pixmap_image_bytes",
        lambda _pixmap: (b"image", 1200, 800, "image/webp"),
    )
    monkeypatch.setattr(
        "app.import_to_db.felgtbi.importer._upload_figure_to_supabase",
        lambda **kwargs: {
            "status": "uploaded",
            "storage_path": kwargs["storage_path"],
        },
    )
    document = {
        "code": "section-1",
        "page": 1,
        "visual_context": {"page": 1, "bbox": [10, 20, 300, 220]},
        "figure": {"caption": "Gráfico 1"},
    }

    _attach_page_assets(b"%PDF", "report.pdf", [document])

    assert document["figure"]["storage_path"].endswith(".webp")
    assert document["figure"]["width"] == 1200
    assert document["figure"]["height"] == 800


def test_section_cache_avoids_duplicate_mongo_queries(monkeypatch) -> None:
    class FakeCollection:
        calls = 0

        def find_one(self, _query, _projection):
            self.calls += 1
            return {
                "source": "felgtbi_estado_lgtbi",
                "source_document_id": "doc-1",
                "code": "section-1",
                "year": 2026,
                "question": "Resultados",
                "paragraphs": ["Contenido narrativo válido."],
            }

    collection = FakeCollection()
    selected_document = FelgtbiDocument(
        id="doc-1",
        label="Informe",
        original_filename="report.pdf",
        year=2026,
        report_title="Informe",
        report_type="report",
        section_count=1,
        filter_fields=(("source_document_id", "doc-1"),),
    )
    monkeypatch.setattr(repository, "_resolve_spain_collection_name", lambda _value: "Indicator_felgtbi")
    monkeypatch.setattr(repository, "_resolve_felgtbi_document", lambda *_args: selected_document)
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    app = Flask(__name__)
    init_cache(app)
    with app.app_context():
        repository.invalidate_analytics_cache()
        first = repository.get_felgtbi_indicator_answers(
            "section-1",
            "Indicator_felgtbi",
            document_id="doc-1",
        )
        second = repository.get_felgtbi_indicator_answers(
            "section-1",
            "Indicator_felgtbi",
            document_id="doc-1",
        )

    assert first == second
    assert collection.calls == 1
