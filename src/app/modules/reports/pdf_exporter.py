from __future__ import annotations

import html as html_std
import re
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.dates import utc_today_iso
from app.modules.reports.models import ReportChart, ReportContent

BRAND_BLUE = colors.HexColor("#2F6BDE")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#5F6B7A")
PALE_BLUE = colors.HexColor("#EEF4FF")
PALE_GREY = colors.HexColor("#F5F7FA")
REPORT_MARGIN = 17 * mm
PRINTABLE_WIDTH = A4[0] - (2 * REPORT_MARGIN)


class _MultilineTextField(Flowable):
    """Printable AcroForm textarea with a visible default value."""

    def __init__(self, name: str, value: str, tooltip: str) -> None:
        super().__init__()
        self.field_name = name
        self.value = value
        self.tooltip = tooltip
        self.width = 170 * mm
        self.height = 14 * mm

    def wrap(self, available_width: float, _available_height: float) -> tuple[float, float]:
        self.width = min(self.width, available_width)
        characters_per_line = max(36, int(self.width / 4.7))
        wrapped_lines = sum(
            max(1, (len(line) + characters_per_line - 1) // characters_per_line)
            for line in (self.value.splitlines() or [""])
        )
        self.height = min(34 * mm, max(14 * mm, (wrapped_lines + 1) * 4.2 * mm))
        return self.width, self.height

    def draw(self) -> None:
        self.canv.acroForm.textfieldRelative(
            name=self.field_name,
            tooltip=self.tooltip,
            value=self.value,
            width=int(self.width),
            height=int(self.height),
            borderStyle="solid",
            borderWidth=1,
            borderColor=colors.HexColor("#AAB6C5"),
            fillColor=colors.white,
            textColor=INK,
            fontName="Helvetica",
            fontSize=8.5,
            fieldFlags="multiline",
            annotationFlags="print",
            forceBorder=True,
            maxlen=2_000,
        )


class PDFExporter:
    """Render a ReportContent model to a self-contained PDF byte stream."""

    def __init__(self) -> None:
        self.page_count = 0

    def export(
        self,
        report: ReportContent,
        chart_images: Mapping[str, Path | Sequence[Path]],
    ) -> bytes:
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=REPORT_MARGIN,
            leftMargin=REPORT_MARGIN,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=report.configuration.title,
            author=report.configuration.author or "RainbowLens Datahub",
            subject="LGBTIQ+ diversity and inclusion",
        )
        styles = _styles()
        story = self._story(report, chart_images, styles)
        document.build(
            story,
            onFirstPage=lambda canvas, doc: _page_decorations(canvas, doc, cover=True),
            onLaterPages=lambda canvas, doc: _page_decorations(canvas, doc, cover=False),
        )
        self.page_count = document.page
        return buffer.getvalue()

    def _story(
        self,
        report: ReportContent,
        chart_images: Mapping[str, Path | Sequence[Path]],
        styles: dict[str, ParagraphStyle],
    ) -> list[Flowable]:
        language = report.configuration.language
        story: list[Flowable] = [
            Spacer(1, 25 * mm),
            Paragraph(_escape(report.configuration.title), styles["cover_title"]),
            Spacer(1, 7 * mm),
            Paragraph(
                _escape(
                    report.configuration.organization
                    or report.focus_label
                    or _t(language, "Informe RainbowLens", "RainbowLens report")
                ),
                styles["cover_subtitle"],
            ),
            Spacer(1, 19 * mm),
            _cover_metadata(report, styles),
            Spacer(1, 28 * mm),
            Paragraph(
                _escape(
                    _t(
                        language,
                        "Informe orientado a RRHH y diversidad e inclusión. Preparado con RainbowLens DataHub.",
                        "Report focused on HR, diversity and inclusion. Prepared with RainbowLens DataHub.",
                    )
                ),
                styles["cover_note"],
            ),
            PageBreak(),
        ]

        section_number = 0
        if _enabled(report, "executive"):
            section_number += 1
            story.extend(
                _text_section(
                    f"{section_number}. {_t(language, 'Resumen ejecutivo', 'Executive summary')}",
                    _edited_section_paragraphs(
                        report,
                        "executive",
                        report.executive_summary,
                    ),
                    styles,
                )
            )

        map_charts = [chart for chart in report.charts if chart.key.startswith("map_")]
        other_charts = [chart for chart in report.charts if not chart.key.startswith("map_")]
        if map_charts:
            section_number += 1
            story.extend(
                _chart_section(
                    report,
                    chart_images,
                    styles,
                    section_number=section_number,
                    charts=map_charts,
                    section_title=_t(language, "Estadísticas", "Statistics"),
                )
            )

        if _enabled(report, "metrics") and report.metrics:
            section_number += 1
            story.extend(
                [
                    Paragraph(
                        _escape(
                            f"{section_number}. "
                            f"{_t(language, 'Métricas principales', 'Key metrics')}"
                        ),
                        styles["h1"],
                    ),
                    Spacer(1, 3 * mm),
                    _metric_table(report, styles),
                    Spacer(1, 7 * mm),
                ]
            )

        if other_charts:
            section_number += 1
            story.extend(
                _chart_section(
                    report,
                    chart_images,
                    styles,
                    section_number=section_number,
                    charts=other_charts,
                )
            )

        if _enabled(report, "context"):
            section_number += 1
            default_context = [
                _t(
                    language,
                    f'Se analiza "{report.indicator}" para {report.configuration.year or "el periodo disponible"} como contexto externo para apoyar políticas de diversidad e inclusión.',
                    f'The report analyses "{report.indicator}" for {report.configuration.year or "the available period"} as external context supporting diversity and inclusion policies.',
                )
            ]
            story.extend(
                _text_section(
                    f"{section_number}. {_t(language, 'Contexto y alcance', 'Context and scope')}",
                    _edited_section_paragraphs(report, "context", default_context),
                    styles,
                )
            )

        if _enabled(report, "workplace") and report.workplace_analysis:
            section_number += 1
            story.extend(
                _text_section(
                    f"{section_number}. "
                    f"{_t(language, 'Diversidad e inclusión en el entorno laboral', 'Workplace diversity and inclusion')}",
                    report.workplace_analysis,
                    styles,
                )
            )
        if _enabled(report, "demographics") and report.demographic_analysis:
            section_number += 1
            story.extend(
                _text_section(
                    f"{section_number}. "
                    f"{_t(language, 'Diferencias sociodemográficas', 'Sociodemographic differences')}",
                    report.demographic_analysis,
                    styles,
                )
            )

        if _enabled(report, "comparison") and report.table_rows:
            section_number += 1
            story.extend(
                [
                    Paragraph(
                        _escape(
                            f"{section_number}. "
                            f"{_t(language, 'Comparación de respuestas', 'Response comparison')}"
                        ),
                        styles["h1"],
                    ),
                    Spacer(1, 3 * mm),
                    _comparison_table(report, styles),
                    Spacer(1, 6 * mm),
                ]
            )
        if _enabled(report, "interpretation") and report.conclusions:
            section_number += 1
            story.extend(
                _text_section(
                    f"{section_number}. "
                    f"{_t(language, 'Interpretación y conclusiones', 'Interpretation and conclusions')}",
                    report.conclusions,
                    styles,
                )
            )
        if _enabled(report, "recommendations") and report.recommendations:
            section_number += 1
            edited_recommendations = report.section_narratives.get("recommendations")
            derived = [
                recommendation.text
                for recommendation in report.recommendations
                if recommendation.derived_from_metrics
            ]
            general = [
                recommendation.text
                for recommendation in report.recommendations
                if not recommendation.derived_from_metrics
            ]
            story.append(
                Paragraph(
                    _escape(
                        f"{section_number}. "
                        f"{_t(language, 'Posibles líneas de actuación', 'Possible courses of action')}"
                    ),
                    styles["h1"],
                )
            )
            if edited_recommendations is not None:
                story.extend(
                    _bullet_list(
                        _nonempty_lines(edited_recommendations),
                        styles,
                    )
                )
            elif derived:
                story.append(
                    Paragraph(
                        _escape(
                            _t(
                                language,
                                "Relacionadas con los resultados observados",
                                "Related to the observed results",
                            )
                        ),
                        styles["h2"],
                    )
                )
                story.extend(_bullet_list(derived, styles))
            if edited_recommendations is None and general:
                story.append(
                    Paragraph(
                        _escape(
                            _t(
                                language,
                                "Orientaciones generales",
                                "General guidance",
                            )
                        ),
                        styles["h2"],
                    )
                )
                story.extend(_bullet_list(general, styles))
            story.append(Spacer(1, 5 * mm))
        if _enabled(report, "methodology") and report.methodology:
            section_number += 1
            story.extend(
                _text_section(
                    f"{section_number}. {_t(language, 'Metodología', 'Methodology')}",
                    report.methodology,
                    styles,
                )
            )
        if _enabled(report, "limitations") and report.limitations:
            section_number += 1
            story.extend(
                _text_section(
                    f"{section_number}. {_t(language, 'Limitaciones', 'Limitations')}",
                    report.limitations,
                    styles,
                    bullets=True,
                )
            )
        # Attribution is mandatory whenever the report contains external data,
        # even if the optional narrative sections were customised by the user.
        if report.sources:
            section_number += 1
            story.extend(
                _text_section(
                    f"{section_number}. {_t(language, 'Fuentes, metodología y atribuciones', 'Sources, methodology and attributions')}",
                    report.sources,
                    styles,
                    bullets=True,
                )
            )
        return story


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=34,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=base["Heading2"],
            fontName="Helvetica",
            fontSize=16,
            leading=22,
            textColor=BRAND_BLUE,
        ),
        "cover_note": ParagraphStyle(
            "CoverNote",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=11,
            leading=16,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "h1": ParagraphStyle(
            "ReportH1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=22,
            textColor=INK,
            keepWithNext=True,
            spaceBefore=8,
            spaceAfter=7,
        ),
        "h2": ParagraphStyle(
            "ReportH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=BRAND_BLUE,
            spaceBefore=5,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=INK,
            spaceAfter=5,
        ),
        "bullet": ParagraphStyle(
            "ReportBullet",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=INK,
            leftIndent=6 * mm,
            firstLineIndent=-4 * mm,
            spaceAfter=3,
        ),
        "table": ParagraphStyle(
            "ReportTable",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=INK,
        ),
    }


def _cover_metadata(
    report: ReportContent,
    styles: dict[str, ParagraphStyle],
) -> Table:
    language = report.configuration.language
    rows = [
        [
            _paragraph(_t(language, "Fecha", "Date"), styles["table"], bold=True),
            _paragraph(utc_today_iso(), styles["table"]),
        ],
        [
            _paragraph(
                _t(language, "Tipo de información", "Information type"), styles["table"], bold=True
            ),
            _paragraph(
                {
                    "fra": _t(language, "Datos sociales", "Social data"),
                    "ilga": _t(language, "Datos legales", "Legal data"),
                    "combined": _t(language, "Análisis combinado", "Combined analysis"),
                }.get(report.configuration.source, report.configuration.source),
                styles["table"],
            ),
        ],
        [
            _paragraph(_t(language, "Enfoque", "Focus"), styles["table"], bold=True),
            _paragraph(report.focus_label or "N/A", styles["table"]),
        ],
        [
            _paragraph(_t(language, "Año de datos", "Data year"), styles["table"], bold=True),
            _paragraph(str(report.configuration.year or "N/A"), styles["table"]),
        ],
        [
            _paragraph(_t(language, "Indicador", "Indicator"), styles["table"], bold=True),
            _paragraph(report.indicator or "N/A", styles["table"]),
        ],
        [
            _paragraph(_t(language, "Ámbito", "Scope"), styles["table"], bold=True),
            _paragraph(
                ", ".join(report.country_names) or _t(language, "Europa", "Europe"),
                styles["table"],
            ),
        ],
    ]
    if report.configuration.author:
        rows.append(
            [
                _paragraph(
                    _t(language, "Autor o departamento", "Author or department"),
                    styles["table"],
                    bold=True,
                ),
                _paragraph(report.configuration.author, styles["table"]),
            ]
        )
    table = Table(
        rows,
        colWidths=[PRINTABLE_WIDTH * 0.28, PRINTABLE_WIDTH * 0.72],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), PALE_BLUE),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CDD6E3")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDE3EC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _metric_table(
    report: ReportContent,
    styles: dict[str, ParagraphStyle],
) -> Table:
    cells: list[list[Flowable]] = [
        [
            _paragraph(metric.label, styles["table"]),
            Spacer(1, 2 * mm),
            Paragraph(
                f"<b>{_escape(metric.display_value)}</b>",
                ParagraphStyle(
                    f"Metric{index}",
                    parent=styles["table"],
                    fontSize=12,
                    leading=15,
                    textColor=BRAND_BLUE,
                ),
            ),
        ]
        for index, metric in enumerate(report.metrics[:6])
    ]
    rows = [cells[index : index + 3] for index in range(0, len(cells), 3)]
    while rows and len(rows[-1]) < 3:
        rows[-1].append([Paragraph("", styles["table"])])
    table = Table(rows, colWidths=[PRINTABLE_WIDTH / 3] * 3)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE_GREY),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDE3EC")),
                ("INNERGRID", (0, 0), (-1, -1), 4, colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _comparison_table(
    report: ReportContent,
    styles: dict[str, ParagraphStyle],
) -> Table:
    language = report.configuration.language
    headings = (
        ["Country", "Value", "Rank", "EU difference", "Year"]
        if language == "en"
        else ["País", "Valor", "Posición", "Diferencia UE", "Año"]
    )
    rows = [[_paragraph(value, styles["table"], bold=True) for value in headings]]
    for row in report.table_rows:
        rows.append(
            [
                _paragraph(row.get("country"), styles["table"]),
                _paragraph(f"{row.get('value')} %", styles["table"]),
                _paragraph(row.get("position"), styles["table"]),
                _paragraph(f"{float(row.get('difference') or 0):+.2f} pp", styles["table"]),
                _paragraph(row.get("year") or "N/A", styles["table"]),
            ]
        )
    table = Table(
        rows,
        colWidths=[
            PRINTABLE_WIDTH * 0.33,
            PRINTABLE_WIDTH * 0.15,
            PRINTABLE_WIDTH * 0.14,
            PRINTABLE_WIDTH * 0.23,
            PRINTABLE_WIDTH * 0.15,
        ],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_GREY]),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CDD6E3")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E1E6ED")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _chart_image(path: Path) -> Image:
    image = Image(str(path))
    max_width = PRINTABLE_WIDTH
    max_height = 150 * mm
    width = float(image.imageWidth or 1)
    height = float(image.imageHeight or 1)
    scale = min(max_width / width, max_height / height)
    image.drawWidth = width * scale
    image.drawHeight = height * scale
    return image


def _chart_section(
    report: ReportContent,
    chart_images: Mapping[str, Path | Sequence[Path]],
    styles: dict[str, ParagraphStyle],
    *,
    section_number: int,
    charts: Sequence[ReportChart] | None = None,
    section_title: str | None = None,
) -> list[Flowable]:
    language = report.configuration.language
    story: list[Flowable] = []
    selected_charts = list(charts) if charts is not None else report.charts
    for index, chart in enumerate(selected_charts, start=1):
        image_paths = _chart_image_paths(chart_images.get(chart.key))
        if not image_paths:
            continue
        chart_header: list[Flowable] = []
        if index == 1:
            chart_header.extend(
                [
                    Paragraph(
                        _escape(
                            f"{section_number}. "
                            f"{section_title or _t(language, 'Evidencia gráfica', 'Visual evidence')}"
                        ),
                        styles["h1"],
                    ),
                    Spacer(1, 2 * mm),
                ]
            )
        for page_index, image_path in enumerate(image_paths, start=1):
            page_suffix = f" ({page_index}/{len(image_paths)})" if len(image_paths) > 1 else ""
            page_header = [
                Paragraph(
                    _escape(f"{section_number}.{index}. {chart.title}{page_suffix}"),
                    styles["h2"],
                ),
                Spacer(1, 2 * mm),
                _chart_image(image_path),
            ]
            story.append(KeepTogether([*chart_header, *page_header]))
            chart_header = []
        safe_chart_key = re.sub(r"[^a-zA-Z0-9_-]+", "_", chart.key).strip("_")
        fields = (
            (
                "what_shows",
                _t(language, "Qué muestra", "What it shows"),
                chart.what_shows,
            ),
            (
                "how_to_read",
                _t(language, "Cómo se interpreta", "How to read it"),
                chart.how_to_read,
            ),
            (
                "observation",
                _t(language, "Qué observamos", "What we observe"),
                chart.observation,
            ),
        )
        for field, label, value in fields:
            story.append(
                KeepTogether(
                    [
                        Paragraph(f"<b>{_escape(label)}:</b>", styles["body"]),
                        _MultilineTextField(
                            f"chart_{safe_chart_key}_{field}",
                            value,
                            f"{chart.title}: {label}",
                        ),
                        Spacer(1, 2 * mm),
                    ]
                )
            )
        story.append(Spacer(1, 5 * mm))
    return story


def _chart_image_paths(value: Path | Sequence[Path] | None) -> list[Path]:
    if value is None:
        return []
    candidates = [value] if isinstance(value, Path) else list(value)
    return [Path(path) for path in candidates if Path(path).exists()]


def _text_section(
    title: str,
    paragraphs: list[str],
    styles: dict[str, ParagraphStyle],
    *,
    bullets: bool = False,
) -> list[Flowable]:
    elements: list[Flowable] = [Paragraph(_escape(title), styles["h1"])]
    if bullets:
        elements.extend(_bullet_list(paragraphs, styles))
    else:
        elements.extend(Paragraph(_escape(paragraph), styles["body"]) for paragraph in paragraphs)
    elements.append(Spacer(1, 4 * mm))
    return elements


def _edited_section_paragraphs(
    report: ReportContent,
    section: str,
    default: list[str],
) -> list[str]:
    if section not in report.section_narratives:
        return default
    value = report.section_narratives[section]
    return [paragraph.strip() for paragraph in re.split(r"\n\s*\n", value) if paragraph.strip()]


def _nonempty_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def _bullet_list(
    values: list[str],
    styles: dict[str, ParagraphStyle],
) -> list[Paragraph]:
    return [Paragraph(f"- {_escape(value)}", styles["bullet"]) for value in values]


def _paragraph(
    value: object,
    style: ParagraphStyle,
    *,
    bold: bool = False,
) -> Paragraph:
    content = _escape(str(value or ""))
    return Paragraph(f"<b>{content}</b>" if bold else content, style)


def _enabled(report: ReportContent, section: str) -> bool:
    return section in report.configuration.sections


def _page_decorations(canvas, document, *, cover: bool) -> None:
    canvas.setCreator("RainbowLens Datahub")
    canvas.setProducer("RainbowLens Datahub")
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(BRAND_BLUE)
    canvas.rect(0, height - 6 * mm, width, 6 * mm, fill=1, stroke=0)
    if not cover:
        canvas.setStrokeColor(colors.HexColor("#DDE3EC"))
        canvas.line(17 * mm, 14 * mm, width - 17 * mm, 14 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(17 * mm, 9 * mm, "RainbowLens Datahub")
        canvas.drawRightString(
            width - 17 * mm,
            9 * mm,
            f"{document.page}",
        )
    canvas.restoreState()


def _escape(value: str) -> str:
    return html_std.escape(str(value or ""), quote=True)


def _t(language: str, es: str, en: str) -> str:
    return en if language == "en" else es
