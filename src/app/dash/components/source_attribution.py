from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from dash import html
from dash.development.base_component import Component

from app.dash.i18n import dash_attrs, text_attrs, ui_text, ui_text_component
from app.source_attribution import (
    FELGTBI_URL,
    FRA_ORGANIZATION_URL,
    ILGA_URL,
    SourceAttributionMetadata,
    SourceLink,
    source_metadata,
)


def build_source_attribution(
    source: str,
    *,
    source_name: str | None = None,
    year: int | None = None,
    source_url: str | None = None,
    custom_text: tuple[str, str] | None = None,
    compact: bool = False,
    language: str | None = None,
    document_id: str | None = None,
    figure: str | None = None,
    accessed_at: str | None = None,
    class_name: str = "",
    element_id: str | None = None,
) -> Component:
    metadata = source_metadata(
        source,
        year=year,
        source_name=source_name,
        source_url=source_url,
        source_document=document_id,
        source_figure=figure,
        accessed_at=accessed_at,
    )
    attribution = custom_text or (
        metadata.attribution("es", compact=compact),
        metadata.attribution("en", compact=compact),
    )
    classes = ["source-attribution", f"source-attribution--{metadata.key}"]
    classes.append("source-attribution--compact" if compact else "source-attribution--full")
    if class_name:
        classes.append(class_name)
    props: dict[str, Any] = {
        "className": " ".join(classes),
        "role": "note",
        **dash_attrs(
            {
                "data-source-attribution": metadata.key,
                "aria-label": "Fuente y atribución / Source and attribution",
            }
        ),
    }
    if element_id:
        props["id"] = element_id
    if compact:
        children: list[Component] = [
            html.Span(
                attribution[1] if language == "en" else attribution[0],
                **text_attrs(*attribution),
            ),
            _external_link(
                SourceLink(
                    "Consultar fuente original",
                    "View original source",
                    metadata.source_url,
                ),
                language=language,
                compact=True,
            ),
        ]
        return html.Aside(children, **props)

    metadata_items = _metadata_items(metadata, language=language)
    return html.Aside(
        [
            html.H3(
                "Fuente y atribución" if language != "en" else "Source and attribution",
                **text_attrs("Fuente y atribución", "Source and attribution"),
            ),
            html.P(
                metadata.source_organization,
                className="source-attribution-organization",
            ),
            html.P(
                metadata.description_en if language == "en" else metadata.description_es,
                className="source-attribution-description",
                **text_attrs(metadata.description_es, metadata.description_en),
            ),
            html.P(
                attribution[1] if language == "en" else attribution[0],
                className="source-attribution-text",
                **text_attrs(*attribution),
            ),
            html.Dl(metadata_items, className="source-attribution-metadata"),
            html.Div(
                [
                    _external_link(link, language=language)
                    for link in _unique_links(metadata.official_links)
                ],
                className="source-attribution-links",
            ),
        ],
        **props,
    )


def build_footer_attributions(*, language: str | None = None) -> Component:
    sources = (
        (
            "fra",
            "source_fra_label",
            "footer_attribution_fra_text",
            FRA_ORGANIZATION_URL,
        ),
        (
            "ilga",
            "source_ilga_label",
            "footer_attribution_ilga_text",
            ILGA_URL,
        ),
        (
            "felgtbi",
            "source_felgtbi_label",
            "footer_attribution_felgtbi_text",
            FELGTBI_URL,
        ),
    )
    return html.Section(
        [
            html.H2(
                ui_text_component("footer_attributions_title", language=language),
                id="footer-attributions-heading",
                className="footer-attributions-title",
            ),
            html.Div(
                [
                    _footer_attribution_card(
                        source_key,
                        label_key,
                        description_key,
                        url,
                        language=language,
                    )
                    for source_key, label_key, description_key, url in sources
                ],
                className="footer-attributions-grid",
            ),
        ],
        className="footer-attributions",
        **dash_attrs({"aria-labelledby": "footer-attributions-heading"}),
    )


def _footer_attribution_card(
    source_key: str,
    label_key: str,
    description_key: str,
    url: str,
    *,
    language: str | None,
) -> Component:
    label_es = ui_text(label_key, "es")
    label_en = ui_text(label_key, "en")
    return html.Article(
        [
            html.H3(ui_text_component(label_key, language=language)),
            html.P(ui_text_component(description_key, language=language)),
            _external_link(
                SourceLink(label_es, label_en, url),
                language=language,
                class_name="footer-attribution-link",
            ),
        ],
        className="footer-attribution-block",
        **dash_attrs({"data-footer-attribution": source_key}),
    )


def _metadata_items(
    metadata: SourceAttributionMetadata,
    *,
    language: str | None,
) -> list[Component]:
    rows: list[tuple[str, str, str, str]] = [
        (
            "Fuente utilizada",
            "Source used",
            metadata.source_name,
            metadata.source_name,
        ),
        (
            "Última actualización",
            "Last update",
            metadata.last_updated_es,
            metadata.last_updated_en,
        ),
        (
            "Reutilización",
            "Reuse",
            metadata.source_license,
            "Consult the reuse terms of the original source",
        ),
    ]
    if metadata.source_document:
        rows.insert(
            1,
            (
                "Documento",
                "Document",
                metadata.source_document,
                metadata.source_document,
            ),
        )
    if metadata.source_figure:
        rows.insert(
            2,
            (
                "Figura",
                "Figure",
                metadata.source_figure,
                metadata.source_figure,
            ),
        )
    if metadata.source_accessed_at:
        rows.append(
            (
                "Fecha de acceso",
                "Accessed on",
                metadata.source_accessed_at,
                metadata.source_accessed_at,
            )
        )
    items: list[Component] = []
    for label_es, label_en, value_es, value_en in rows:
        items.extend(
            [
                html.Dt(
                    label_en if language == "en" else label_es,
                    **text_attrs(label_es, label_en),
                ),
                html.Dd(
                    value_en if language == "en" else value_es,
                    **text_attrs(value_es, value_en),
                ),
            ]
        )
    return items


def _external_link(
    link: SourceLink,
    *,
    language: str | None,
    compact: bool = False,
    class_name: str = "",
) -> Component:
    label = link.label_en if language == "en" else link.label_es
    accessible_es = f"{link.label_es} (se abre en una pestaña nueva)"
    accessible_en = f"{link.label_en} (opens in a new tab)"
    return html.A(
        [
            html.Span(label, **text_attrs(link.label_es, link.label_en)),
            html.Span(
                "↗",
                className="source-attribution-external-icon",
                **dash_attrs({"aria-hidden": "true"}),
            ),
        ],
        href=link.url,
        target="_blank",
        rel="noopener noreferrer",
        className=" ".join(
            filter(
                None,
                (
                    "source-attribution-link",
                    "source-attribution-link--compact" if compact else "",
                    class_name,
                ),
            )
        ),
        **dash_attrs(
            {
                "aria-label": accessible_en if language == "en" else accessible_es,
                "data-i18n-aria-label-es": accessible_es,
                "data-i18n-aria-label-en": accessible_en,
            }
        ),
    )


def _unique_links(links: Iterable[SourceLink]) -> list[SourceLink]:
    unique: list[SourceLink] = []
    seen: set[str] = set()
    for link in links:
        if link.url in seen:
            continue
        seen.add(link.url)
        unique.append(link)
    return unique
