from __future__ import annotations

import logging
import unicodedata
from collections.abc import Sequence
from typing import Any, cast

from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.development.base_component import Component
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app.core.auth.permissions import is_admin_user
from app.core.dates import utc_today, utc_today_iso
from app.modules.home.country_status_admin_service import (
    CountryStatusAuthorizationError,
    CountryStatusValidationError,
    delete_country_lgbti_status,
    load_country_lgbti_status_for_edit,
    save_country_lgbti_status,
)
from app.modules.home.country_status_service import get_country_lgbti_status
from app.modules.home.criteria_component import (
    build_ilga_country_criteria_panel,
)
from app.modules.home.figures import build_ilga_choropleth
from app.modules.home.legal_service import HOME_LEGAL_YEAR, get_home_legal_country_detail
from app.shared.components.loading import contextual_loading
from app.shared.components.page_structure import build_page_header
from app.shared.components.source_attribution import build_source_attribution
from app.shared.data.legal_ranking import (
    LEGAL_MAP_EXPORT_HEIGHT,
    LEGAL_MAP_EXPORT_SCALE,
    LEGAL_MAP_EXPORT_WIDTH,
    LegalRankingEntry,
    build_legal_ranking,
    legal_ranking_payload,
)
from app.shared.data.normalization import normalize_country_code
from app.shared.data.repository import (
    get_ilga_document_by_year,
    get_ilga_years,
    get_latest_ilga_document,
)
from app.shared.data.source_attribution import ILGA_ANNUAL_REVIEW_2026_PDF_URL
from app.web.graph_config import fixed_europe_map_config
from app.web.i18n import (
    COUNTRY_NAMES,
    attribute_attrs,
    country_labels,
    dash_attrs,
    text,
    text_attrs,
    ui_text,
    ui_text_component,
)
from app.web.navigation import build_navbar
from app.web.routes import current_route_language, route_path
from app.web.section_navigation import build_home_section_navigation

logger = logging.getLogger(__name__)

EDITOR_LABELS_EN = {
    "Identificación": "Identification",
    "País": "Country",
    "Código de país": "Country code",
    "Año": "Year",
    "Estado": "Status",
    "Estado general": "Overall status",
    "Descripción": "Description",
    "Contexto": "Context",
    "Contexto legal": "Legal context",
    "Contexto social": "Social context",
    "Avances destacados": "Key progress",
    "Retos principales": "Main challenges",
    "Fuente": "Source",
    "Organización o informe": "Organization or report",
    "Enlace de la fuente": "Source link",
    "Fecha de actualización": "Review date",
    "Información adicional": "Additional information",
    "Observaciones": "Notes",
}


def build_home_layout() -> Component:
    language = current_route_language()
    ilga_document = get_latest_ilga_document()
    ilga_years = get_ilga_years()
    current_year = ilga_document.get("year") if isinstance(ilga_document, dict) else None
    initial_ranking = _localized_legal_ranking(ilga_document, language)
    if current_year and current_year not in ilga_years:
        ilga_years = [int(current_year), *ilga_years]

    return html.Div(
        [
            build_navbar(active="home"),
            html.Main(
                [
                    build_page_header(
                        eyebrow=text("RainbowLens DataHub", "RainbowLens DataHub"),
                        title=text("Inicio", "Home"),
                        description=text(
                            "Explora datos legales y sociales sobre la realidad LGBTIQ+ en Europa.",
                            "Explore legal and social data on LGBTIQ+ realities across Europe.",
                        ),
                        class_name="home-page-header",
                        title_id="home-page-title",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H2(
                                                text(
                                                    "Mapa europeo LGBTIQ+", "European LGBTIQ+ map"
                                                ),
                                                id="home-map-title",
                                                className="home-map-heading",
                                            ),
                                            html.P(
                                                ui_text("home_legal_map_helper", "es"),
                                                id="home-map-helper-text",
                                                className="home-map-helper-text",
                                                **text_attrs(
                                                    ui_text("home_legal_map_helper", "es"),
                                                    ui_text("home_legal_map_helper", "en"),
                                                ),
                                            ),
                                            ui_text_component(
                                                "home_legal_map_explanation",
                                                class_name="home-map-explanation",
                                            ),
                                        ],
                                        className="home-map-intro",
                                    ),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Span(
                                                        _ilga_copy(ilga_document),
                                                        id="home-map-copy",
                                                        className="home-map-copy",
                                                    ),
                                                    html.A(
                                                        text(
                                                            "Abrir estadísticas",
                                                            "Open statistics",
                                                        ),
                                                        href=route_path("statistics"),
                                                        className="home-map-link",
                                                    ),
                                                ],
                                                className="home-map-summary-header",
                                            ),
                                            html.Div(
                                                _ilga_metrics(ilga_document),
                                                id="home-map-metrics",
                                                className="home-map-metrics",
                                            ),
                                        ],
                                        className="home-map-summary",
                                    ),
                                ],
                                className="home-map-header",
                            ),
                            html.Div(
                                [
                                    _control_field(
                                        ("Año del mapa legal", "Legal map year"),
                                        dcc.Dropdown(
                                            id="home-map-year-select",
                                            options=[
                                                {"label": str(year), "value": year}
                                                for year in ilga_years
                                            ],
                                            value=current_year,
                                            clearable=False,
                                            disabled=not bool(ilga_years),
                                            className="home-dropdown",
                                        ),
                                        "home-map-year-control",
                                        "home-map-year-control",
                                    ),
                                    html.Div(
                                        [
                                            html.Button(
                                                text("Descargar imagen", "Download image"),
                                                id="home-map-export-button",
                                                type="button",
                                                className="home-map-export-button",
                                                title="Descargar imagen",
                                                **dash_attrs(
                                                    {
                                                        "aria-label": "Descargar imagen del mapa y ranking legal",
                                                        "aria-controls": "home-map-graph",
                                                        "data-chart-export": "true",
                                                        "data-chart-export-target": "home-map-graph",
                                                        "data-export-format": "png",
                                                        "data-export-width": "1600",
                                                        "data-export-height": "900",
                                                        "data-export-scale": "2",
                                                        **attribute_attrs(
                                                            "title",
                                                            "Descargar imagen",
                                                            "Download image",
                                                        ),
                                                        **attribute_attrs(
                                                            "aria-label",
                                                            "Descargar imagen del mapa y ranking legal",
                                                            "Download legal map and ranking image",
                                                        ),
                                                    }
                                                ),
                                            ),
                                            html.Span(
                                                ui_text_component("home_legal_export_error"),
                                                id="home-map-export-status",
                                                className="home-map-export-status",
                                                hidden=True,
                                                role="alert",
                                                **dash_attrs(
                                                    {
                                                        "data-chart-export-error": "home-map-graph"
                                                    }
                                                ),
                                            ),
                                        ],
                                        className="home-map-export-control",
                                    ),
                                ],
                                className="home-map-controls",
                            ),
                            html.Div(
                                [
                                    dcc.Graph(
                                        id="home-map-graph",
                                        figure=_home_map_figure(
                                            build_ilga_choropleth(ilga_document, language=language),
                                            current_year,
                                            ranking=initial_ranking,
                                            language=language,
                                        ),
                                        className="home-europe-map europe-map-container",
                                        config=cast(
                                            dcc.Graph.Config,
                                            {
                                                "displayModeBar": True,
                                                **fixed_europe_map_config(
                                                    extra_mode_bar_buttons_to_remove=("toImage",)
                                                ),
                                            },
                                        ),
                                    ),
                                    html.Aside(
                                        _legal_ranking_content(
                                            initial_ranking,
                                            current_year,
                                            language,
                                        ),
                                        id="home-legal-ranking",
                                        className="home-legal-ranking",
                                        **dash_attrs(
                                            {
                                                "aria-label": "Ranking legal de países",
                                                **attribute_attrs(
                                                    "aria-label",
                                                    "Ranking legal de países",
                                                    "Country legal ranking",
                                                ),
                                            }
                                        ),
                                    ),
                                ],
                                className="home-map-visual-grid",
                            ),
                            dcc.Store(
                                id="home-legal-ranking-store",
                                data=legal_ranking_payload(initial_ranking),
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                _ilga_source(ilga_document),
                                                id="home-map-source",
                                                className="home-map-source",
                                            ),
                                        ],
                                        className="home-map-footer-meta",
                                    ),
                                ],
                                className="home-map-footer",
                            ),
                        ],
                        className="home-map-stage app-surface app-chart-card",
                    ),
                    _home_legal_country_section(),
                    build_home_section_navigation(
                        authenticated=bool(getattr(current_user, "is_authenticated", False))
                    ),
                ],
                className="home-data-shell app-page app-page-container",
            ),
        ]
    )


def _home_legal_country_section() -> Component:
    language = current_route_language()
    return html.Section(
        [
            html.Div(
                [
                    ui_text_component(
                        "home_ilga_country_eyebrow",
                        class_name="home-ilga-detail-eyebrow",
                        language=language,
                    ),
                    html.H2(
                        ui_text_component("home_ilga_country_title", language=language),
                        className="home-ilga-detail-title",
                    ),
                    ui_text_component(
                        "home_ilga_country_intro",
                        class_name="home-ilga-detail-intro",
                        language=language,
                    ),
                ],
                className="home-ilga-detail-header",
            ),
            _control_field(
                (
                    ui_text("home_legal_country_label", "es"),
                    ui_text("home_legal_country_label", "en"),
                ),
                dcc.Dropdown(
                    id="home-legal-country-select",
                    options=_home_legal_country_options(),
                    value=None,
                    clearable=True,
                    multi=False,
                    searchable=True,
                    placeholder=ui_text("home_legal_country_placeholder", "es"),
                    className="home-dropdown home-legal-country-dropdown",
                ),
                "home-legal-country-control",
                "home-legal-country-control",
            ),
            dcc.Store(
                id="home-legal-country-state",
                data={"status": "INITIAL", "country_code": None, "year": HOME_LEGAL_YEAR},
            ),
            dcc.Store(id="home-legal-status-refresh", data=0),
            dcc.Store(id="home-legal-status-editor-state", data={}),
            contextual_loading(
                html.Div(
                    [
                        html.Div(
                            _home_legal_initial_state(language),
                            id="home-legal-details",
                            className="home-legal-details-panel",
                        ),
                        html.Div(
                            id="home-legal-country-status",
                            className="country-status-anchor home-legal-context-divider",
                        ),
                    ],
                    className="home-legal-results",
                ),
                "loading_indicators",
                element_id="home-legal-details-loading",
                target_components={
                    "home-legal-details": "children",
                    "home-legal-country-status": "children",
                },
                hide_content_while_loading=True,
                show_message=False,
            ),
            html.Div(
                id="home-legal-status-admin-feedback",
                className="country-status-admin-feedback",
                role="status",
            ),
            html.Div(
                id="home-legal-status-editor",
                className="country-status-editor-shell",
            ),
        ],
        id="home-legal-section",
        className="home-legal-section",
    )


def _home_legal_initial_state(language: str | None = None) -> Component:
    return html.P(
        ui_text_component("home_ilga_country_empty", language=language),
        className="home-legal-message home-legal-message--initial",
    )


def register_home_callbacks(app: Dash) -> None:
    @app.callback(
        Output("home-legal-country-select", "placeholder"),
        Input("app-language-store", "data"),
    )
    def translate_home_legal_country_control(language: str | None) -> str:
        return ui_text("home_legal_country_placeholder", language or "es")

    @app.callback(
        Output("home-legal-country-select", "value"),
        Input("home-map-graph", "clickData"),
        State("home-legal-country-select", "options"),
        prevent_initial_call=True,
    )
    def select_home_legal_country_from_map(
        click_data: dict[str, Any] | None,
        legal_country_options: list[dict[str, Any]] | None,
    ) -> str:
        country_code = _country_code_from_map_click(click_data)
        available_codes = {
            normalize_country_code(option.get("value"))
            for option in legal_country_options or []
            if isinstance(option, dict)
        }
        if not country_code or country_code not in available_codes:
            raise PreventUpdate
        return country_code

    @app.callback(
        Output("home-legal-details", "children"),
        Output("home-legal-country-state", "data"),
        Input("home-legal-country-select", "value"),
        Input("app-language-store", "data"),
    )
    def update_home_legal_country_details(
        selected_country: str | None,
        language: str | None,
    ) -> tuple[Component, dict[str, Any]]:
        country_code = normalize_country_code(selected_country)
        if not country_code:
            return _home_legal_initial_state(language), {
                "status": "INITIAL",
                "country_code": None,
                "year": HOME_LEGAL_YEAR,
            }
        try:
            country = get_home_legal_country_detail(country_code)
        except Exception:
            logger.exception(
                "home_legal_country_detail_failed",
                extra={"country_code": country_code, "year": HOME_LEGAL_YEAR},
            )
            return (
                html.P(
                    ui_text_component("home_legal_country_error", language=language),
                    className="home-legal-message home-legal-message--error",
                    role="alert",
                ),
                {
                    "status": "ERROR",
                    "country_code": country_code,
                    "year": HOME_LEGAL_YEAR,
                },
            )
        if country is None:
            return (
                html.P(
                    ui_text_component("home_legal_country_no_data", language=language),
                    className="home-legal-message home-legal-message--no-data",
                ),
                {
                    "status": "NO_DATA",
                    "country_code": country_code,
                    "year": HOME_LEGAL_YEAR,
                },
            )
        return build_ilga_country_criteria_panel(country), {
            "status": "READY",
            "country_code": country_code,
            "year": HOME_LEGAL_YEAR,
        }

    @app.callback(
        Output("home-map-graph", "figure"),
        Output("home-map-title", "children"),
        Output("home-map-copy", "children"),
        Output("home-map-source", "children"),
        Output("home-map-metrics", "children"),
        Output("home-legal-ranking", "children"),
        Output("home-legal-ranking-store", "data"),
        Input("home-map-year-select", "value"),
        Input("app-language-store", "data"),
    )
    def update_home_map(
        ilga_year: int | None,
        language: str | None,
    ):
        document = get_ilga_document_by_year(ilga_year)
        ranking = _localized_legal_ranking(document, language or "es")
        return (
            _home_map_figure(
                build_ilga_choropleth(document, language=language or "es"),
                ilga_year,
                ranking=ranking,
                language=language or "es",
            ),
            text("Mapa europeo LGBTIQ+", "European LGBTIQ+ map", language=language),
            _ilga_copy(document, language),
            _ilga_source(document, language),
            _ilga_metrics(document, language),
            _legal_ranking_content(ranking, ilga_year, language or "es"),
            legal_ranking_payload(ranking),
        )

    @app.callback(
        Output("home-legal-country-status", "children"),
        Input("home-legal-country-select", "value"),
        Input("home-legal-status-refresh", "data"),
        State("home-legal-country-select", "options"),
    )
    def update_home_legal_country_status(
        selected_country: str | None,
        _refresh: int | None,
        country_options: list[dict[str, Any]] | None,
    ):
        country_code = normalize_country_code(selected_country)
        if not country_code:
            return []
        label_by_code = _country_label_map(country_options or [])
        statuses = get_country_lgbti_status([country_code], HOME_LEGAL_YEAR)
        statuses = [
            status
            for status in statuses
            if not status.get("available") or status.get("year") == HOME_LEGAL_YEAR
        ]
        if not statuses:
            return []
        return _country_status_section(
            statuses,
            label_by_code,
            HOME_LEGAL_YEAR,
            can_manage=is_admin_user(current_user),
        )

    @app.callback(
        Output("home-legal-status-editor", "children"),
        Output("home-legal-status-editor-state", "data"),
        Output("home-legal-status-admin-feedback", "children"),
        Input(
            {
                "type": "country-status-open-editor",
                "action": ALL,
                "country_code": ALL,
                "year": ALL,
            },
            "n_clicks",
        ),
        State("home-legal-country-select", "options"),
        prevent_initial_call=True,
    )
    def open_country_status_editor(
        open_clicks: list[int] | None,
        country_options: list[dict[str, Any]] | None,
    ):
        if not _any_clicks(open_clicks):
            raise PreventUpdate
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return no_update, no_update, no_update
        if not is_admin_user(current_user):
            return [], {}, "No tienes permisos para modificar estos datos."

        country_code = normalize_country_code(trigger.get("country_code"))
        year = _safe_year(trigger.get("year"))
        mode = "edit" if trigger.get("action") == "edit" else "create"
        record = load_country_lgbti_status_for_edit(country_code, year) if mode == "edit" else None
        label_by_code = _country_label_map(country_options or [])
        initial = _editor_initial_record(country_code, year, record, label_by_code)
        state = {
            "mode": mode,
            "country_code": country_code,
            "year": year,
            "exists": bool(record),
        }
        return _country_status_editor(initial, state, country_options or [], {}), state, ""

    @app.callback(
        Output("home-legal-status-editor", "children", allow_duplicate=True),
        Output("home-legal-status-editor-state", "data", allow_duplicate=True),
        Output("home-legal-status-admin-feedback", "children", allow_duplicate=True),
        Input({"type": "country-status-editor-cancel", "slot": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_country_status_editor(cancel_clicks: list[int] | None):
        if not _any_clicks(cancel_clicks):
            raise PreventUpdate
        return [], {}, ""

    @app.callback(
        Output("home-legal-status-editor", "children", allow_duplicate=True),
        Output("home-legal-status-editor-state", "data", allow_duplicate=True),
        Output("home-legal-status-admin-feedback", "children", allow_duplicate=True),
        Output("home-legal-status-refresh", "data"),
        Input({"type": "country-status-editor-save", "slot": ALL}, "n_clicks"),
        Input({"type": "country-status-editor-delete", "slot": ALL}, "n_clicks"),
        State("home-legal-status-editor-state", "data"),
        State("home-legal-country-select", "options"),
        State("home-legal-status-refresh", "data"),
        State({"type": "country-status-form-country", "slot": ALL}, "value"),
        State({"type": "country-status-form-country-code", "slot": ALL}, "value"),
        State({"type": "country-status-form-year", "slot": ALL}, "value"),
        State({"type": "country-status-form-title", "slot": ALL}, "value"),
        State({"type": "country-status-form-summary", "slot": ALL}, "value"),
        State({"type": "country-status-form-legal-context", "slot": ALL}, "value"),
        State({"type": "country-status-form-social-context", "slot": ALL}, "value"),
        State({"type": "country-status-form-positive", "slot": ALL}, "value"),
        State({"type": "country-status-form-challenges", "slot": ALL}, "value"),
        State({"type": "country-status-form-source-name", "slot": ALL}, "value"),
        State({"type": "country-status-form-source-url", "slot": ALL}, "value"),
        State({"type": "country-status-form-reviewed-at", "slot": ALL}, "value"),
        State({"type": "country-status-form-observations", "slot": ALL}, "value"),
        State({"type": "country-status-form-active", "slot": ALL}, "value"),
        State({"type": "country-status-delete-confirm", "slot": ALL}, "value"),
        prevent_initial_call=True,
    )
    def persist_country_status_editor(
        _save_clicks: int | None,
        _delete_clicks: int | None,
        editor_state: dict[str, Any] | None,
        country_options: list[dict[str, Any]] | None,
        refresh: int | None,
        country_values: list[str] | None,
        country_code_values: list[str] | None,
        year_values: list[int | str] | None,
        title_values: list[str] | None,
        summary_values: list[str] | None,
        legal_context_values: list[str] | None,
        social_context_values: list[str] | None,
        positive_developments_values: list[str] | None,
        main_challenges_values: list[str] | None,
        source_name_values: list[str] | None,
        source_url_values: list[str] | None,
        reviewed_at_values: list[str] | None,
        observations_values: list[str] | None,
        active_value_lists: list[list[str]] | None,
        delete_confirm_value_lists: list[list[str]] | None,
    ):
        if not _any_clicks([_save_clicks], [_delete_clicks]):
            raise PreventUpdate
        trigger = ctx.triggered_id
        trigger_type = trigger.get("type") if isinstance(trigger, dict) else trigger
        if trigger_type not in {"country-status-editor-save", "country-status-editor-delete"}:
            return no_update, no_update, no_update, no_update
        if not is_admin_user(current_user):
            return [], {}, "No tienes permisos para modificar estos datos.", refresh or 0

        state = editor_state or {}
        label_by_code = _country_label_map(country_options or [])
        country = _first_value(country_values)
        country_code = _first_value(country_code_values)
        year = _first_value(year_values)
        title = _first_value(title_values)
        summary = _first_value(summary_values)
        legal_context = _first_value(legal_context_values)
        social_context = _first_value(social_context_values)
        positive_developments = _first_value(positive_developments_values)
        main_challenges = _first_value(main_challenges_values)
        source_name = _first_value(source_name_values)
        source_url = _first_value(source_url_values)
        reviewed_at = _first_value(reviewed_at_values)
        observations = _first_value(observations_values)
        active_values = _first_value(active_value_lists, [])
        delete_confirm_values = _first_value(delete_confirm_value_lists, [])
        selected_country_code = normalize_country_code(country or country_code)
        selected_country_name = (
            label_by_code.get(selected_country_code) or str(country or "").strip()
        )
        payload = {
            "country": selected_country_name,
            "country_code": selected_country_code,
            "year": year,
            "title": title,
            "summary": summary,
            "legal_context": legal_context,
            "social_context": social_context,
            "positive_developments": positive_developments,
            "main_challenges": main_challenges,
            "source_name": source_name,
            "source_url": source_url,
            "reviewed_at": reviewed_at,
            "observations": observations,
            "active": "active" in (active_values or []),
        }

        if trigger_type == "country-status-editor-delete":
            try:
                delete_country_lgbti_status(
                    selected_country_code,
                    int(year or 0),
                    user=current_user,
                    confirmed="confirm" in (delete_confirm_values or []),
                )
            except CountryStatusValidationError as exc:
                return (
                    _country_status_editor(payload, state, country_options or [], exc.field_errors),
                    state,
                    "No se pudieron eliminar los datos. Revisa el país y el año.",
                    refresh or 0,
                )
            except CountryStatusAuthorizationError, RuntimeError:
                return [], {}, "No se pudieron eliminar los datos.", refresh or 0
            empty_state = {"mode": "create", "country_code": "", "year": None, "exists": False}
            return (
                _country_status_editor(
                    _empty_country_status_editor_record(),
                    empty_state,
                    country_options or [],
                    {},
                ),
                empty_state,
                "Los datos se han eliminado correctamente.",
                (refresh or 0) + 1,
            )

        try:
            saved = save_country_lgbti_status(
                payload,
                user=current_user,
                mode=str(state.get("mode") or "edit"),
            )
        except CountryStatusValidationError as exc:
            return (
                _country_status_editor(payload, state, country_options or [], exc.field_errors),
                state,
                "No se pudieron guardar los cambios. Revisa los campos e intentalo de nuevo.",
                refresh or 0,
            )
        except CountryStatusAuthorizationError, RuntimeError:
            return [], {}, "No se pudieron guardar los cambios.", refresh or 0

        message = (
            "Los datos se han creado correctamente."
            if state.get("mode") == "create"
            else "Los datos se han actualizado correctamente."
        )
        return (
            [],
            {"country_code": saved["country_code"], "year": saved["year"]},
            message,
            (refresh or 0) + 1,
        )

    @app.callback(
        Output({"type": "country-status-form-country-code", "slot": ALL}, "value"),
        Input({"type": "country-status-form-country", "slot": ALL}, "value"),
        prevent_initial_call=True,
    )
    def sync_country_status_iso(country_values: list[str] | None):
        return [normalize_country_code(value) for value in country_values or []]


def _home_map_figure(
    figure: Any,
    year: int | str | None = None,
    *,
    ranking: Sequence[LegalRankingEntry] = (),
    language: str = "es",
) -> Any:
    export_filename = "rainbowlens_mapa_legal_europa"
    if year is not None and str(year).strip():
        export_filename = f"{export_filename}_{year}"
    figure.update_layout(
        autosize=True,
        dragmode=False,
        geo={
            "center": {"lon": 20, "lat": 54},
            "projection": {"scale": 1.18},
        },
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        meta={
            "export_filename": export_filename,
            "export_format": "png",
            "export_width": LEGAL_MAP_EXPORT_WIDTH,
            "export_height": LEGAL_MAP_EXPORT_HEIGHT,
            "export_scale": LEGAL_MAP_EXPORT_SCALE,
            "export_map_ranking": legal_ranking_payload(ranking),
            "export_map_title": (
                "European LGBTIQ+ map" if language == "en" else "Mapa europeo LGBTIQ+"
            ),
            "export_ranking_title": _legal_ranking_title(year, language),
            "export_country_label": "Country" if language == "en" else "País",
            "export_score_label": "Legal score" if language == "en" else "Puntuación legal",
            "export_source": f"ILGA-Europe · Rainbow Map {year or ''}".strip(),
        },
    )
    return figure


def _home_legal_country_options() -> list[dict[str, Any]]:
    options = []
    for country_code, (name_es, name_en) in COUNTRY_NAMES.items():
        options.append(
            {
                "label": text(
                    f"{name_es} ({country_code})",
                    f"{name_en} ({country_code})",
                ),
                "value": country_code,
                "title": name_es,
                "search": _country_search_terms(country_code, name_es, name_en),
                "sort_label": name_es.casefold(),
            }
        )
    return [
        {key: value for key, value in option.items() if key != "sort_label"}
        for option in sorted(options, key=lambda item: str(item["sort_label"]))
    ]


def _country_code_from_map_click(click_data: dict[str, Any] | None) -> str:
    points = click_data.get("points") if isinstance(click_data, dict) else None
    if not isinstance(points, list) or not points or not isinstance(points[0], dict):
        return ""
    customdata = points[0].get("customdata")
    raw_code = customdata[0] if isinstance(customdata, (list, tuple)) and customdata else customdata
    return normalize_country_code(raw_code)


def _country_search_terms(country_code: str, *names: str) -> str:
    values = [country_code, *names]
    accentless = [
        "".join(
            character
            for character in unicodedata.normalize("NFKD", value)
            if not unicodedata.combining(character)
        )
        for value in values
    ]
    return " ".join([*values, *accentless]).casefold()


def _country_label_map(options: list[dict[str, Any]]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for option in options:
        code = normalize_country_code(option.get("value"))
        label = str(option.get("title") or code).strip()
        if "(" in label:
            label = label.rsplit("(", 1)[0].strip()
        if code:
            labels[code] = country_labels(code, label)[0]
    return labels


def _country_status_section(
    statuses: list[dict[str, Any]],
    label_by_code: dict[str, str],
    requested_year: int | None = None,
    *,
    can_manage: bool = False,
) -> Component:
    first_country_code = str(statuses[0].get("country_code") or "").strip().upper()
    first_country_fallback = _status_country_name(statuses[0], label_by_code)
    first_country_es, first_country_en = country_labels(
        first_country_code,
        first_country_fallback,
    )
    title_es = (
        f"Información LGBTIQ+ de {first_country_es}"
        if len(statuses) == 1
        else "Información LGBTIQ+ de los países seleccionados"
    )
    title_en = (
        f"LGBTIQ+ information for {first_country_en}"
        if len(statuses) == 1
        else "LGBTIQ+ information for the selected countries"
    )
    return html.Section(
        [
            html.Header(
                [
                    html.P(
                        "Contexto del país",
                        className="country-status-eyebrow",
                        **text_attrs("Contexto del país", "Country context"),
                    ),
                    html.H2(title_es, **text_attrs(title_es, title_en)),
                ],
                className="country-status-section__header",
            ),
            html.Div(
                [
                    _country_status_card(status, label_by_code, requested_year, can_manage)
                    for status in statuses
                ],
                className="country-status-grid",
            ),
        ],
        className="country-status-section",
    )


def _country_status_card(
    status: dict[str, Any],
    label_by_code: dict[str, str],
    requested_year: int | None,
    can_manage: bool = False,
) -> Component:
    country_name = _status_country_name(status, label_by_code)
    country_code = str(status.get("country_code") or "").strip()
    country_name_es, country_name_en = country_labels(country_code, country_name)
    year = status.get("year")
    if not status.get("available"):
        summary_es, summary_en = _status_translated_text(status, "summary")
        children: list[Any] = [
            html.Header(
                [
                    html.H3(
                        country_name_es,
                        **text_attrs(country_name_es, country_name_en),
                    ),
                    html.Span(country_code, className="country-status-card__year"),
                ],
                className="country-status-card__header",
            ),
            html.P(
                summary_es,
                className="country-status-card__empty",
                **text_attrs(summary_es, summary_en),
            ),
        ]
        if can_manage:
            children.append(
                _country_status_admin_button(
                    "add", country_code, requested_year, "Añadir información"
                )
            )
        return html.Article(children, className="country-status-card country-status-card--empty")

    title_es, title_en = _status_translated_text(status, "title")
    summary_es, summary_en = _status_translated_text(status, "summary")
    legal_es, legal_en = _status_translated_text(status, "legal_context")
    social_es, social_en = _status_translated_text(status, "social_context")
    progress_es, progress_en = _status_translated_list(status, "positive_developments")
    challenges_es, challenges_en = _status_translated_list(status, "main_challenges")
    observations_es, observations_en = _status_translated_text(status, "observations")

    details_children = []
    details_children.extend(
        _status_text_block("Contexto legal", legal_es, "Legal context", legal_en)
    )
    details_children.extend(
        _status_text_block("Contexto social", social_es, "Social context", social_en)
    )
    details_children.extend(
        _status_list_block(
            "Avances destacados", progress_es, "Key progress", progress_en
        )
    )
    details_children.extend(
        _status_list_block(
            "Retos principales", challenges_es, "Main challenges", challenges_en
        )
    )

    children: list[Any] = [
        html.Header(
            [
                html.Div(
                    [
                        html.H3(
                            country_name_es,
                            **text_attrs(country_name_es, country_name_en),
                        ),
                        html.Span(country_code, className="country-status-card__code"),
                    ],
                    className="country-status-card__title",
                ),
                html.Span(
                    f"Año {year or '-'}",
                    className="country-status-card__year",
                    **text_attrs(f"Año {year or '-'}", f"Year {year or '-'}"),
                ),
            ],
            className="country-status-card__header",
        ),
    ]
    if title_es:
        children.append(
            html.H4(
                "Estado general",
                className="country-status-card__subtitle",
                **text_attrs("Estado general", "Overall status"),
            )
        )
        children.append(
            html.P(
                title_es,
                className="country-status-card__status",
                **text_attrs(title_es, title_en),
            )
        )
    if requested_year and year and int(year) != int(requested_year):
        notice_es = f"Información disponible para {year}."
        notice_en = f"Information available for {year}."
        children.append(
            html.P(
                notice_es,
                className="country-status-card__notice",
                **text_attrs(notice_es, notice_en),
            )
        )
    children.append(
        html.P(
            summary_es,
            className="country-status-card__summary",
            **text_attrs(summary_es, summary_en),
        )
    )
    if details_children:
        children.append(
            html.Details(
                [
                    html.Summary(
                        "Ver contexto completo",
                        **text_attrs("Ver contexto completo", "View full context"),
                    ),
                    *details_children,
                ],
                className="country-status-card__details",
                open=True,
            )
        )
    observations_es = _clean_status_observations(observations_es)
    observations_en = _clean_status_observations(observations_en)
    if observations_es:
        children.append(
            html.P(
                observations_es,
                className="country-status-card__observations",
                **text_attrs(observations_es, observations_en),
            )
        )
    children.append(_status_source(status))
    if can_manage:
        children.append(_country_status_admin_button("edit", country_code, year, "Editar"))
    return html.Article(children, className="country-status-card")


def _country_status_admin_button(
    action: str,
    country_code: str,
    year: int | str | None,
    label: str,
) -> Component:
    label_en = {
        "Añadir información": "Add information",
        "Editar": "Edit",
    }.get(label, label)
    return html.Button(
        label,
        id={
            "type": "country-status-open-editor",
            "action": action,
            "country_code": country_code,
            "year": str(year or ""),
        },
        type="button",
        className="country-status-admin-button",
        **text_attrs(label, label_en),
    )


def _country_status_editor(
    record: dict[str, Any],
    state: dict[str, Any],
    country_options: list[dict[str, Any]],
    errors: dict[str, str],
) -> Component:
    mode = str(state.get("mode") or "edit")
    exists = bool(state.get("exists")) or mode == "edit"
    title = "Editar información del país" if exists else "Añadir información del país"
    country_code = normalize_country_code(record.get("country_code"))
    country_options = _ensure_country_option(country_options, record)
    return html.Div(
        [
            html.Div(className="country-status-editor-backdrop"),
            html.Section(
                [
                    html.Header(
                        [
                            html.Div(
                                [
                                    html.P(
                                        "Administración",
                                        className="country-status-eyebrow",
                                        **text_attrs("Administración", "Administration"),
                                    ),
                                    html.H2(
                                        title,
                                        **text_attrs(
                                            title,
                                            "Edit country information"
                                            if exists
                                            else "Add country information",
                                        ),
                                    ),
                                    html.P(
                                        "Los cambios se aplicarán a la información visible en la aplicación.",
                                        className="country-status-editor-copy",
                                        **text_attrs(
                                            "Los cambios se aplicarán a la información visible en la aplicación.",
                                            "Changes will be applied to the information shown in the application.",
                                        ),
                                    ),
                                ],
                                className="country-status-editor-title",
                            ),
                            html.Button(
                                "Cancelar",
                                id=_editor_id("country-status-editor-cancel"),
                                type="button",
                                className="country-status-editor-cancel",
                                **text_attrs("Cancelar", "Cancel"),
                            ),
                        ],
                        className="country-status-editor-header",
                    ),
                    html.Div(
                        [
                            _editor_group(
                                "Identificación",
                                [
                                    _editor_field(
                                        "País",
                                        dcc.Dropdown(
                                            id=_editor_id("country-status-form-country"),
                                            options=country_options,
                                            value=country_code,
                                            clearable=False,
                                            className="home-dropdown",
                                        ),
                                        errors.get("country"),
                                    ),
                                    _editor_field(
                                        "Código de país",
                                        dcc.Input(
                                            id=_editor_id("country-status-form-country-code"),
                                            type="text",
                                            value=country_code,
                                            maxLength=3,
                                        ),
                                        errors.get("country_code"),
                                    ),
                                    _editor_field(
                                        "Año",
                                        dcc.Input(
                                            id=_editor_id("country-status-form-year"),
                                            type="number",
                                            min=2000,
                                            max=2100,
                                            step=1,
                                            value=_record_value(record, "year", utc_today().year),
                                        ),
                                        errors.get("year"),
                                    ),
                                    dcc.Checklist(
                                        id=_editor_id("country-status-form-active"),
                                        options=[
                                            {
                                                "label": text(
                                                    "Información visible",
                                                    "Visible information",
                                                ),
                                                "value": "active",
                                            }
                                        ],
                                        value=["active"] if record.get("active", True) else [],
                                        className="country-status-editor-checklist",
                                    ),
                                ],
                            ),
                            _editor_group(
                                "Estado",
                                [
                                    _editor_field(
                                        "Estado general",
                                        dcc.Input(
                                            id=_editor_id("country-status-form-title"),
                                            type="text",
                                            value=record.get("title") or "",
                                            maxLength=240,
                                        ),
                                        errors.get("title"),
                                    ),
                                    _editor_field(
                                        "Descripción",
                                        dcc.Textarea(
                                            id=_editor_id("country-status-form-summary"),
                                            value=record.get("summary") or "",
                                            maxLength=6000,
                                        ),
                                        errors.get("summary"),
                                    ),
                                ],
                            ),
                            _editor_group(
                                "Contexto",
                                [
                                    _editor_field(
                                        "Contexto legal",
                                        dcc.Textarea(
                                            id=_editor_id("country-status-form-legal-context"),
                                            value=record.get("legal_context") or "",
                                            maxLength=6000,
                                        ),
                                        errors.get("legal_context"),
                                    ),
                                    _editor_field(
                                        "Contexto social",
                                        dcc.Textarea(
                                            id=_editor_id("country-status-form-social-context"),
                                            value=record.get("social_context") or "",
                                            maxLength=6000,
                                        ),
                                        errors.get("social_context"),
                                    ),
                                    _editor_field(
                                        "Avances destacados",
                                        dcc.Textarea(
                                            id=_editor_id("country-status-form-positive"),
                                            value=_lines_value(record.get("positive_developments")),
                                            maxLength=6000,
                                        ),
                                        errors.get("positive_developments"),
                                    ),
                                    _editor_field(
                                        "Retos principales",
                                        dcc.Textarea(
                                            id=_editor_id("country-status-form-challenges"),
                                            value=_lines_value(record.get("main_challenges")),
                                            maxLength=6000,
                                        ),
                                        errors.get("main_challenges"),
                                    ),
                                ],
                            ),
                            _editor_group(
                                "Fuente",
                                [
                                    _editor_field(
                                        "Organización o informe",
                                        dcc.Input(
                                            id=_editor_id("country-status-form-source-name"),
                                            type="text",
                                            value=record.get("source_name") or "",
                                            maxLength=240,
                                        ),
                                        errors.get("source_name"),
                                    ),
                                    _editor_field(
                                        "Enlace de la fuente",
                                        dcc.Input(
                                            id=_editor_id("country-status-form-source-url"),
                                            type="url",
                                            value=record.get("source_url") or "",
                                        ),
                                        errors.get("source_url"),
                                    ),
                                    _editor_field(
                                        "Fecha de actualización",
                                        dcc.Input(
                                            id=_editor_id("country-status-form-reviewed-at"),
                                            type="text",
                                            placeholder="AAAA-MM-DD",
                                            value=_record_value(
                                                record, "reviewed_at", utc_today_iso()
                                            ),
                                        ),
                                        errors.get("reviewed_at"),
                                    ),
                                ],
                            ),
                            _editor_group(
                                "Información adicional",
                                [
                                    _editor_field(
                                        "Observaciones",
                                        dcc.Textarea(
                                            id=_editor_id("country-status-form-observations"),
                                            value=record.get("observations") or "",
                                            maxLength=6000,
                                        ),
                                        errors.get("observations"),
                                    )
                                ],
                            ),
                            html.Div(
                                [
                                    dcc.Checklist(
                                        id=_editor_id("country-status-delete-confirm"),
                                        options=[
                                            {
                                                "label": text(
                                                    "Confirmo que quiero eliminar esta información",
                                                    "I confirm that I want to delete this information",
                                                ),
                                                "value": "confirm",
                                            }
                                        ],
                                        value=[],
                                        className="country-status-editor-checklist",
                                    ),
                                    _editor_error(errors.get("delete_confirm")),
                                ],
                                className=(
                                    "country-status-editor-delete-confirm"
                                    if exists
                                    else "country-status-editor-delete-confirm is-hidden"
                                ),
                            ),
                        ],
                        className="country-status-editor-body",
                    ),
                    html.Footer(
                        [
                            html.Button(
                                "Guardar cambios",
                                id=_editor_id("country-status-editor-save"),
                                type="button",
                                className="country-status-editor-save",
                                **text_attrs("Guardar cambios", "Save changes"),
                            ),
                            (
                                html.Button(
                                    "Eliminar",
                                    id=_editor_id("country-status-editor-delete"),
                                    type="button",
                                    className="country-status-editor-delete",
                                    **text_attrs("Eliminar", "Delete"),
                                )
                                if exists
                                else html.Button(
                                    "Eliminar",
                                    id=_editor_id("country-status-editor-delete"),
                                    type="button",
                                    className="country-status-editor-delete is-hidden",
                                    **text_attrs("Eliminar", "Delete"),
                                )
                            ),
                        ],
                        className="country-status-editor-actions",
                    ),
                ],
                className="country-status-editor-panel",
                role="dialog",
                **dash_attrs({"aria-modal": "true"}),
            ),
        ],
        className="country-status-editor-modal",
    )


def _editor_group(title: str, children: list[Any]) -> Component:
    return html.Fieldset(
        [html.Legend(title, **text_attrs(title, EDITOR_LABELS_EN.get(title, title))), *children],
        className="country-status-editor-group",
    )


def _editor_id(component_type: str) -> dict[str, str]:
    return {"type": component_type, "slot": "main"}


def _first_value(values: list[Any] | None, default: Any = None) -> Any:
    if not values:
        return default
    return values[0]


def _any_clicks(*groups: Sequence[int | None] | None) -> bool:
    for group in groups:
        for value in group or []:
            try:
                if int(value or 0) > 0:
                    return True
            except TypeError, ValueError:
                continue
    return False


def _editor_field(label: str, control: Any, error: str | None = None) -> Component:
    control_id = getattr(control, "id", None)
    if control_id and control.__class__.__name__ not in {"Input", "Textarea"}:
        label_id = f"{control_id}-label"
        return html.Div(
            [
                html.Span(
                    label,
                    id=label_id,
                    **text_attrs(label, EDITOR_LABELS_EN.get(label, label)),
                ),
                control,
                _editor_error(error),
            ],
            className="country-status-editor-field",
            role="group",
            **dash_attrs({"aria-labelledby": label_id}),
        )
    return html.Label(
        [
            html.Span(label, **text_attrs(label, EDITOR_LABELS_EN.get(label, label))),
            control,
            _editor_error(error),
        ],
        className="country-status-editor-field",
    )


def _editor_error(error: str | None) -> Component | str:
    if not error:
        return ""
    return html.P(error, className="country-status-editor-error")


def _editor_initial_record(
    country_code: str,
    year: int | None,
    record: dict[str, Any] | None,
    label_by_code: dict[str, str],
) -> dict[str, Any]:
    if record:
        return record
    return {
        "country_code": country_code,
        "country": label_by_code.get(country_code, country_code),
        "year": year or utc_today().year,
        "title": "",
        "summary": "",
        "legal_context": "",
        "social_context": "",
        "observations": "",
        "positive_developments": [],
        "main_challenges": [],
        "source_name": "ILGA-Europe Annual Review 2026",
        "source_url": ILGA_ANNUAL_REVIEW_2026_PDF_URL,
        "reviewed_at": utc_today_iso(),
        "active": True,
    }


def _empty_country_status_editor_record() -> dict[str, Any]:
    return {
        "country_code": "",
        "country": "",
        "year": "",
        "title": "",
        "summary": "",
        "legal_context": "",
        "social_context": "",
        "observations": "",
        "positive_developments": [],
        "main_challenges": [],
        "source_name": "",
        "source_url": "",
        "reviewed_at": "",
        "active": False,
    }


def _record_value(record: dict[str, Any], key: str, default: Any) -> Any:
    return record.get(key, default)


def _ensure_country_option(
    options: list[dict[str, Any]],
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    country_code = normalize_country_code(record.get("country_code"))
    values = {normalize_country_code(option.get("value")) for option in options}
    if country_code and country_code not in values:
        return [
            *options,
            {
                "label": f"{record.get('country') or country_code} ({country_code})",
                "value": country_code,
            },
        ]
    return options


def _lines_value(value: Any) -> str:
    if not isinstance(value, list):
        return str(value or "")
    return "\n".join(str(item) for item in value if str(item).strip())


def _safe_year(value: Any) -> int | None:
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _status_country_name(status: dict[str, Any], label_by_code: dict[str, str]) -> str:
    country_code = str(status.get("country_code") or "").strip()
    return str(status.get("country") or label_by_code.get(country_code) or country_code).strip()


def _status_translated_text(status: dict[str, Any], key: str) -> tuple[str, str]:
    translations = status.get(f"{key}_i18n")
    fallback = str(status.get(key) or "")
    if not isinstance(translations, dict):
        return fallback, fallback
    es = str(translations.get("es") or fallback)
    en = str(translations.get("en") or es)
    return es, en


def _status_translated_list(status: dict[str, Any], key: str) -> tuple[list[str], list[str]]:
    fallback_value = status.get(key)
    fallback = [str(item) for item in fallback_value] if isinstance(fallback_value, list) else []
    translations = status.get(f"{key}_i18n")
    if not isinstance(translations, dict):
        return fallback, fallback
    es_value = translations.get("es")
    en_value = translations.get("en")
    es = [str(item) for item in es_value] if isinstance(es_value, list) else fallback
    en = [str(item) for item in en_value] if isinstance(en_value, list) else es
    return es, en


def _clean_status_observations(value: Any) -> str:
    text_value = str(value or "").strip()
    caveats = (
        "; el 'estado general' es una síntesis editorial y no una categoría oficial de ILGA-Europe.",
        "; the 'overall status' is an editorial synthesis and not an official ILGA-Europe category.",
    )
    folded_value = text_value.casefold()
    for caveat in caveats:
        marker_index = folded_value.find(caveat.casefold())
        if marker_index >= 0:
            return text_value[:marker_index].rstrip()
    return text_value


def _status_text_block(
    title: str, value: Any, title_en: str, value_en: Any | None = None
) -> list[Any]:
    text_value = str(value or "").strip()
    if not text_value:
        return []
    english_value = str(value_en or text_value).strip()
    return [
        html.H4(title, **text_attrs(title, title_en)),
        html.P(text_value, **text_attrs(text_value, english_value)),
    ]


def _status_list_block(
    title: str, values: Any, title_en: str, values_en: Any | None = None
) -> list[Any]:
    if not isinstance(values, list) or not values:
        return []
    english_values = values_en if isinstance(values_en, list) else values
    items = []
    for index, value in enumerate(values):
        clean_value = str(value).strip()
        if not clean_value:
            continue
        english_value = (
            str(english_values[index]).strip()
            if index < len(english_values) and str(english_values[index]).strip()
            else clean_value
        )
        items.append(html.Li(clean_value, **text_attrs(clean_value, english_value)))
    return [
        html.H4(title, **text_attrs(title, title_en)),
        html.Ul(items),
    ]


def _status_source(status: dict[str, Any]) -> Component:
    source_name = str(status.get("source_name") or "").strip()
    source_url = str(status.get("source_url") or "").strip()
    reviewed_at = str(status.get("reviewed_at") or "").strip()
    children: list[Any] = []
    if reviewed_at:
        children.append(
            html.Span(
                f"Última revisión: {reviewed_at}",
                **text_attrs(f"Última revisión: {reviewed_at}", f"Last review: {reviewed_at}"),
            )
        )
    if "ilga" in source_name.casefold():
        year_value = status.get("year")
        if year_value is None:
            source_year = None
        else:
            try:
                source_year = int(year_value)
            except TypeError, ValueError:
                source_year = None
        annual_review_name = "ILGA-EUROPE-ANNUAL-REVIEW"
        if source_year is not None:
            annual_review_name = f"{annual_review_name} {source_year}"
        children.append(
            build_source_attribution(
                "ilga",
                year=source_year,
                source_url=source_url or None,
                custom_text=(
                    (
                        f"Fuente: {annual_review_name}. Datos adaptados y visualizados por "
                        "RainbowLens DataHub."
                    ),
                    (
                        f"Source: {annual_review_name}. Data adapted and visualised by "
                        "RainbowLens DataHub."
                    ),
                ),
                compact=True,
                class_name="country-status-card__attribution",
            )
        )
    return html.Footer(children, className="country-status-card__source")


def _localized_legal_ranking(
    document: dict[str, Any] | None,
    language: str,
) -> list[LegalRankingEntry]:
    name_index = 1 if language == "en" else 0
    return build_legal_ranking(
        document,
        country_name_resolver=lambda country_code, fallback: country_labels(
            country_code,
            fallback,
        )[name_index],
    )


def _legal_ranking_content(
    ranking: Sequence[LegalRankingEntry],
    year: int | str | None,
    language: str,
) -> list[Component]:
    english = language == "en"
    title = _legal_ranking_title(year, language)
    if not ranking:
        return [
            html.H3(title, className="home-legal-ranking-title"),
            html.P(
                ui_text("home_legal_ranking_empty", language),
                className="home-legal-ranking-empty",
            ),
        ]

    rows = [
        html.Li(
            [
                html.Span(str(position), className="home-legal-ranking-position"),
                html.Span(entry.country_name, className="home-legal-ranking-country"),
                html.Span(
                    entry.score_text,
                    className="home-legal-ranking-score",
                ),
            ],
            className="home-legal-ranking-row",
            **dash_attrs(
                {
                    "aria-label": (
                        f"{position}. {entry.country_name} — {entry.score_text}"
                    )
                }
            ),
        )
        for position, entry in enumerate(ranking, start=1)
    ]
    return [
        html.Div(
            [
                html.H3(title, className="home-legal-ranking-title"),
                html.Span(
                    str(len(ranking)),
                    className="home-legal-ranking-count",
                    **dash_attrs(
                        {
                            "aria-label": (
                                f"{len(ranking)} countries"
                                if english
                                else f"{len(ranking)} países"
                            )
                        }
                    ),
                ),
            ],
            className="home-legal-ranking-header",
        ),
        html.Ol(rows, className="home-legal-ranking-list"),
    ]


def _legal_ranking_title(year: int | str | None, language: str) -> str:
    title = "Legal ranking" if language == "en" else "Ranking legal"
    return f"{title} · {year}" if year is not None and str(year).strip() else title


def _control_field(
    label: tuple[str, str],
    control: Any,
    class_name: str = "",
    field_id: str | None = None,
) -> Component:
    classes = ["home-control-field"]
    if class_name:
        classes.append(class_name)
    props: dict[str, Any] = {"className": " ".join(classes)}
    if field_id:
        props["id"] = field_id
    control_id = getattr(control, "id", None)
    if control_id and control.__class__.__name__ not in {"Input", "Textarea"}:
        label_id = f"{control_id}-label"
        return html.Div(
            [
                html.Span(
                    text(label[0], label[1]),
                    id=label_id,
                    className="home-control-label",
                ),
                control,
            ],
            role="group",
            **dash_attrs({**props, "aria-labelledby": label_id}),
        )
    return html.Div(
        [
            html.Label(text(label[0], label[1]), htmlFor=control_id),
            control,
        ],
        **props,
    )


def _metric(
    value: str,
    label_es: str,
    label_en: str,
    language: str | None = None,
) -> Component:
    return html.Div(
        [
            html.Strong(value),
            html.Span(_localized(label_es, label_en, language), **text_attrs(label_es, label_en)),
        ],
        className="home-map-metric",
    )


def _ilga_copy(document: dict[str, Any] | None, language: str | None = None):
    if not isinstance(document, dict):
        return text(
            "No hay un Rainbow Map disponible.", "No Rainbow Map is available.", language=language
        )
    year = document.get("year")
    if year:
        return text(
            f"Información legal de {year}",
            f"Legal information for {year}",
            language=language,
        )
    return text(
        "Información legal LGBTIQ+",
        "LGBTIQ+ legal ranking",
        language=language,
    )


def _ilga_source(document: dict[str, Any] | None, language: str | None = None):
    year = document.get("year") if isinstance(document, dict) else None
    return build_source_attribution(
        "ilga",
        year=int(year) if isinstance(year, int | float) else None,
        compact=True,
        language=language,
        class_name="home-map-source-attribution",
    )


def _ilga_metrics(document: dict[str, Any] | None, language: str | None = None) -> list[Component]:
    countries = (
        document.get("countries", [])
        if isinstance(document, dict) and isinstance(document.get("countries"), list)
        else []
    )
    rankings = [
        float(country["ranking"])
        for country in countries
        if isinstance(country, dict) and isinstance(country.get("ranking"), (int, float))
    ]
    average = f"{sum(rankings) / len(rankings):.1f}%" if rankings else "-"
    year = document.get("year") if isinstance(document, dict) else None
    return [
        _metric(str(year or "-"), "Año", "Year", language),
        _metric(str(len(countries)), "Países", "Countries", language),
        _metric(average, "Media legal", "Legal average", language),
    ]


def _localized(es: str, en: str, language: str | None) -> str:
    return en if language == "en" else es
