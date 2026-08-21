from __future__ import annotations

from dataclasses import dataclass

from dash import dcc, html
from dash.development.base_component import Component

from app.dash.i18n import attribute_attrs, dash_attrs, ui_text, ui_text_component
from app.dash.routes import route_path


@dataclass(frozen=True, slots=True)
class PrimarySection:
    key: str
    label_key: str
    description_key: str | None = None
    action_key: str | None = None
    aria_key: str | None = None
    route_id: str | None = None


PRIMARY_SECTIONS = (
    PrimarySection("home", "navigation_home"),
    PrimarySection(
        "statistics",
        "navigation_statistics",
        "home_statistics_description",
        "home_statistics_action",
        "home_statistics_aria",
    ),
    PrimarySection(
        "trends",
        "navigation_trends",
        "home_trends_description",
        "home_trends_action",
        "home_trends_aria",
    ),
    PrimarySection(
        "spain",
        "navigation_spain",
        "home_spain_description",
        "home_spain_action",
        "home_spain_aria",
    ),
    PrimarySection(
        "didactica",
        "navigation_didactics",
        "home_didactics_description",
        "home_didactics_action",
        "home_didactics_aria",
    ),
    PrimarySection(
        "about",
        "navigation_about",
        "home_about_description",
        "home_about_action",
        "home_about_aria",
    ),
)

PRIMARY_NAVIGATION_SECTIONS = (
    *PRIMARY_SECTIONS[:-1],
    PrimarySection("reports", "report_module_name"),
    PRIMARY_SECTIONS[-1],
)

ANONYMOUS_ACCOUNT_SECTION = PrimarySection(
    "login",
    "home_login_title",
    "home_login_description",
    "home_login_action",
    "home_login_aria",
    "login",
)

AUTHENTICATED_ACCOUNT_SECTION = PrimarySection(
    "profile",
    "home_profile_title",
    "home_profile_description",
    "home_profile_action",
    "home_profile_aria",
    "profile",
)


def build_home_section_navigation(*, authenticated: bool = False) -> Component:
    account_section = (
        AUTHENTICATED_ACCOUNT_SECTION if authenticated else ANONYMOUS_ACCOUNT_SECTION
    )
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
                    for section in (*PRIMARY_SECTIONS, account_section)
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
            href=route_path(section.route_id or section.key),
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
