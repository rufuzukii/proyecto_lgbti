from __future__ import annotations

import html as html_std
from collections.abc import Mapping
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

from app.reports.models import ReportContent

BRAND_BLUE = colors.HexColor("#2F6BDE")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#5F6B7A")
PALE_BLUE = colors.HexColor("#EEF4FF")
PALE_GREY = colors.HexColor("#F5F7FA")


class PDFExporter:
    """Render a ReportContent model to a self-contained PDF byte stream."""

    def export(
        self,
        report: ReportContent,
        chart_images: Mapping[str, Path],
    ) -> bytes:
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=17 * mm,
            leftMargin=17 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=report.configuration.title,
            author=report.configuration.author or "RainbowLens",
            subject="LGBTIQ+ diversity and inclusion",
        )
        styles = _styles()
        story = self._story(report, chart_images, styles)
        document.build(
            story,
            onFirstPage=lambda canvas, doc: _page_decorations(canvas, doc, cover=True),
            onLaterPages=lambda canvas, doc: _page_decorations(canvas, doc, cover=False),
        )
        return buffer.getvalue()

    def _story(
        self,
        report: ReportContent,
        chart_images: Mapping[str, Path],
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
                    or _t(language, "Informe para Recursos Humanos", "Human Resources report")
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
                        "Análisis agregado para apoyar decisiones de diversidad e inclusión.",
                        "Aggregated analysis to support diversity and inclusion decisions.",
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
                    report.executive_summary,
                    styles,
                )
            )
        if _enabled(report, "methodology"):
            section_number += 1
            story.extend(
                _text_section(
                    f"{section_number}. {_t(language, 'Objetivo, alcance y metodología', 'Objective, scope and methodology')}",
                    report.methodology,
                    styles,
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

        if report.charts:
            section_number += 1
            chart_section = section_number
            for index, chart in enumerate(report.charts, start=1):
                image_path = chart_images.get(chart.key)
                if image_path is None or not image_path.exists():
                    continue
                elements: list[Flowable] = []
                if index == 1:
                    elements.extend(
                        [
                            Paragraph(
                                _escape(
                                    f"{chart_section}. "
                                    f"{_t(language, 'Evidencia gráfica', 'Visual evidence')}"
                                ),
                                styles["h1"],
                            ),
                            Spacer(1, 2 * mm),
                        ]
                    )
                elements.extend(
                    [
                        Paragraph(
                            _escape(f"{chart_section}.{index}. {chart.title}"),
                            styles["h2"],
                        ),
                        Spacer(1, 2 * mm),
                        Image(
                            str(image_path),
                            width=176 * mm,
                            height=98 * mm,
                            kind="proportional",
                        ),
                        Spacer(1, 5 * mm),
                    ]
                )
                story.append(KeepTogether(elements))

        if _enabled(report, "comparison") and report.table_rows:
            section_number += 1
            story.extend(
                [
                    PageBreak(),
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
        if _enabled(report, "risks") and report.conclusions:
            section_number += 1
            story.extend(
                _text_section(
                    f"{section_number}. "
                    f"{_t(language, 'Conclusiones y áreas de riesgo', 'Conclusions and risk areas')}",
                    report.conclusions,
                    styles,
                )
            )
        if _enabled(report, "recommendations") and report.recommendations:
            section_number += 1
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
                        f"{_t(language, 'Recomendaciones para RRHH', 'HR recommendations')}"
                    ),
                    styles["h1"],
                )
            )
            if derived:
                story.append(
                    Paragraph(
                        _escape(
                            _t(
                                language,
                                "Derivadas de las métricas seleccionadas",
                                "Derived from selected metrics",
                            )
                        ),
                        styles["h2"],
                    )
                )
                story.extend(_bullet_list(derived, styles))
            if general:
                story.append(
                    Paragraph(
                        _escape(
                            _t(
                                language,
                                "Buenas prácticas generales",
                                "General good practices",
                            )
                        ),
                        styles["h2"],
                    )
                )
                story.extend(_bullet_list(general, styles))
            story.append(Spacer(1, 5 * mm))
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
        if _enabled(report, "sources") and report.sources:
            section_number += 1
            story.extend(
                _text_section(
                    f"{section_number}. {_t(language, 'Fuentes', 'Sources')}",
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
            _paragraph(report.configuration.generated_on, styles["table"]),
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
        [
            _paragraph(
                _t(language, "Autor o departamento", "Author or department"),
                styles["table"],
                bold=True,
            ),
            _paragraph(report.configuration.author or "N/A", styles["table"]),
        ],
    ]
    table = Table(rows, colWidths=[48 * mm, 122 * mm])
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
    cells: list[Flowable] = [
        Table(
            [
                [_paragraph(metric.label, styles["table"])],
                [
                    Paragraph(
                        f"<b>{_escape(metric.display_value)}</b>",
                        ParagraphStyle(
                            f"Metric{index}",
                            parent=styles["table"],
                            fontSize=12,
                            leading=15,
                            textColor=BRAND_BLUE,
                        ),
                    )
                ],
            ],
            colWidths=[54 * mm],
        )
        for index, metric in enumerate(report.metrics[:6])
    ]
    rows = [cells[index : index + 3] for index in range(0, len(cells), 3)]
    while rows and len(rows[-1]) < 3:
        rows[-1].append(Paragraph("", styles["table"]))
    table = Table(rows, colWidths=[58 * mm] * 3)
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
    for row in report.table_rows[:30]:
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
        colWidths=[56 * mm, 26 * mm, 24 * mm, 38 * mm, 25 * mm],
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
    canvas.setCreator("RainbowLens")
    canvas.setProducer("RainbowLens")
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(BRAND_BLUE)
    canvas.rect(0, height - 6 * mm, width, 6 * mm, fill=1, stroke=0)
    if not cover:
        canvas.setStrokeColor(colors.HexColor("#DDE3EC"))
        canvas.line(17 * mm, 14 * mm, width - 17 * mm, 14 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(17 * mm, 9 * mm, "RainbowLens")
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
