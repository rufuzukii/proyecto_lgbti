from __future__ import annotations

from dataclasses import dataclass

from dash import dcc, html
from dash.development.base_component import Component

from app.dash.i18n import attribute_attrs, dash_attrs, ui_text, ui_text_component


@dataclass(frozen=True, slots=True)
class PrimarySection:
    key: str
    href: str
    label_key: str
    description_key: str | None = None
    action_key: str | None = None
    aria_key: str | None = None


PRIMARY_SECTIONS = (
    PrimarySection("home", "/", "navigation_home"),
    PrimarySection(
        "statistics",
        "/statistics",
        "navigation_statistics",
        "home_statistics_description",
        "home_statistics_action",
        "home_statistics_aria",
    ),
    PrimarySection(
        "trends",
        "/tendencias",
        "navigation_trends",
        "home_trends_description",
        "home_trends_action",
        "home_trends_aria",
    ),
    PrimarySection(
        "spain",
        "/spain",
        "navigation_spain",
        "home_spain_description",
        "home_spain_action",
        "home_spain_aria",
    ),
    PrimarySection(
        "didactica",
        "/didactica",
        "navigation_didactics",
        "home_didactics_description",
        "home_didactics_action",
        "home_didactics_aria",
    ),
    PrimarySection(
        "about",
        "/about",
        "navigation_about",
        "home_about_description",
        "home_about_action",
        "home_about_aria",
    ),
)


def build_home_section_navigation() -> Component:
    return html.Section(
        [
            html.Header(
                [
                    ui_text_component("home_sections_eyebrow", class_name="home-sections-eyebrow"),
                    html.H2(
                        ui_text_component("home_sections_title"),
                        id="home-sections-title",
                    ),
                    ui_text_component("home_sections_lead", class_name="home-sections-lead"),
                ],
                className="home-sections-header",
            ),
            html.Div(
                [
                    _build_section_card(section)
                    for section in PRIMARY_SECTIONS
                    if section.key != "home"
                ],
                className="home-sections-grid",
            ),
        ],
        className="home-sections",
        **dash_attrs({"aria-labelledby": "home-sections-title"}),
    )


def _build_section_card(section: PrimarySection) -> Component:
    if not section.description_key or not section.action_key or not section.aria_key:
        raise ValueError(f"Section {section.key!r} is missing its home card translations")

    aria_es = ui_text(section.aria_key, "es")
    aria_en = ui_text(section.aria_key, "en")
    return html.Article(
        dcc.Link(
            [
                html.Span(
                    className=f"home-section-card__icon home-section-card__icon--{section.key}",
                    **dash_attrs({"aria-hidden": "true"}),
                ),
                html.Div(
                    [
                        html.H3(ui_text_component(section.label_key)),
                        ui_text_component(
                            section.description_key,
                            class_name="home-section-card__description",
                        ),
                    ],
                    className="home-section-card__body",
                ),
                html.Span(
                    [
                        ui_text_component(section.action_key),
                        html.Span(
                            className="home-section-card__arrow",
                            **dash_attrs({"aria-hidden": "true"}),
                        ),
                    ],
                    className="home-section-card__action",
                ),
            ],
            href=section.href,
            refresh=False,
            className="home-section-card__link",
        ),
        className=f"home-section-card home-section-card--{section.key}",
        **dash_attrs(
            {
                "aria-label": aria_es,
                **attribute_attrs("aria-label", aria_es, aria_en),
            }
        ),
    )
