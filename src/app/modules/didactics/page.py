from __future__ import annotations

from datetime import datetime
from typing import Any

from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.development.base_component import Component
from flask import has_request_context, request
from flask_login import current_user
from pymongo.errors import PyMongoError

from app.core.auth.permissions import (
    Permission,
    can_access_docente_material,
    can_manage_own_edu_games,
    user_has_permission,
)
from app.modules.didactics.components import (
    access_denied,
    glossary_card,
    resource_card,
    teacher_resource_details,
    translated,
)
from app.modules.didactics.custom_game_service import (
    GAME_TYPE_DEFINITIONS,
    CustomGameAuthorizationError,
    CustomGameValidationError,
    build_activity_game_state,
    delete_owned_game,
    duplicate_owned_game,
    get_owned_game,
    get_public_game,
    list_owned_games,
    save_owned_game,
    validate_activity,
)
from app.modules.didactics.game_service import guess_options, new_game_state
from app.modules.didactics.glossary_service import (
    FUNDEU_SOURCE_URL,
    UNAM_SOURCE_URL,
    get_glossary_term,
    glossary_categories,
    list_glossary_terms,
    search_glossary,
)
from app.modules.didactics.presentation_service import (
    DidacticPresentationStorageError,
    list_didactic_presentations,
)
from app.modules.didactics.ranking_component import ranking_game_result, ranking_game_rows
from app.modules.didactics.ranking_game_service import (
    check_ranking_game,
    move_ranking_country,
    new_ranking_game,
)
from app.modules.didactics.teacher_service import (
    generate_teacher_resource_pdf,
    get_teacher_resource,
)
from app.modules.didactics.translations import CATEGORIES, pair, tr
from app.modules.didactics.word_search_component import (
    word_search_board,
    word_search_progress,
    word_search_words,
)
from app.modules.didactics.word_search_service import (
    apply_word_search_selection,
    create_word_search_game,
    is_word_search_complete,
)
from app.modules.home.legal_service import HOME_LEGAL_YEAR
from app.shared.components.loading import contextual_loading
from app.shared.components.page_structure import build_page_header
from app.shared.components.source_attribution import build_source_attribution
from app.shared.data.legal_ranking import build_legal_ranking
from app.shared.data.repository import get_ilga_document_by_year, get_ilga_years
from app.web.i18n import attribute_attrs, country_labels, dash_attrs, text, text_attrs
from app.web.navigation import build_navbar
from app.web.routes import current_route_language, route_path


def build_didactica_layout(notice: str | None = None) -> Component:
    rows = [
        _didactica_mode_row(
            "dictionary",
            "dictionary_desc",
            resource_card(
                "dictionary",
                "dictionary_card_desc",
                "dictionary",
                "Aa",
                class_name="is-compact",
            ),
        ),
        _didactica_mode_row(
            "presentations",
            "presentations_desc",
            resource_card(
                "presentations",
                "presentations_card_desc",
                "presentations",
                "▤",
                class_name="is-compact",
            ),
        ),
    ]
    if user_has_permission(current_user, Permission.PLAY_EDU_GAMES):
        rows.append(
            _didactica_mode_row(
                "games",
                "games_desc",
                html.Div(
                    [
                        resource_card(
                            "guess_term",
                            "guess_desc",
                            "games",
                            "?",
                            query="?game=guess_term",
                            class_name="is-game-card",
                        ),
                        resource_card(
                            "word_search",
                            "word_search_card_desc",
                            "word_search",
                            "ABC",
                            class_name="is-game-card",
                        ),
                        resource_card(
                            "rank_countries",
                            "rank_countries_card_desc",
                            "games",
                            "↕",
                            query="?game=rank_countries",
                            class_name="is-game-card",
                        ),
                    ],
                    className="didactica-game-access-grid",
                ),
                games=True,
            )
        )
    if can_access_docente_material(current_user):
        rows.append(
            _didactica_mode_row(
                "docente",
                "docente_desc",
                resource_card(
                    "docente",
                    "docente_card_desc",
                    "educators",
                    "▣",
                    class_name="is-compact",
                ),
            )
        )
    return _page(
        html.Main(
            [
                build_page_header(
                    eyebrow=text("Recursos educativos", "Educational resources"),
                    title=translated("learning"),
                    description=translated("intro"),
                    class_name="didactica-hero",
                ),
                translated(
                    "docente_required_notice",
                    tag=html.P,
                    class_name="didactica-feedback is-error didactica-route-notice",
                )
                if notice == "docente_required"
                else None,
                html.Section(
                    rows,
                    className="didactica-mode-list",
                    **dash_attrs({"aria-label": pair("learning")[0]}),
                ),
            ],
            className="didactica-shell app-page app-page-container",
        )
    )


def _didactica_mode_row(
    title_key: str,
    description_key: str,
    access: Component,
    *,
    games: bool = False,
) -> Component:
    modifier = " didactica-mode-row--games" if games else ""
    return html.Article(
        [
            html.Div(
                [translated(title_key, tag=html.H2), translated(description_key, tag=html.P)],
                className="didactica-mode-copy",
            ),
            html.Div(access, className="didactica-mode-access"),
        ],
        className=f"didactica-mode-row{modifier}",
    )


def build_dictionary_layout() -> Component:
    category_options = [{"label": text(*pair("all_categories")), "value": "all"}]
    category_options.extend(
        {"label": text(*CATEGORIES[category]), "value": category}
        for category in glossary_categories()
    )
    return _page(
        html.Main(
            [
                _subpage_header("dictionary", "dictionary_desc"),
                html.Aside(
                    [
                        html.P(
                            [
                                text(
                                    "Definiciones educativas redactadas por RainbowLens y acreditadas "
                                    "en cada tarjeta. El catálogo conserva también términos adaptados "
                                    "de los glosarios de ",
                                    "Educational definitions written by RainbowLens and credited on "
                                    "each card. The catalogue also retains terms adapted from the "
                                    "glossaries of ",
                                ),
                                html.A(
                                    "UNAM ↗",
                                    href=UNAM_SOURCE_URL,
                                    target="_blank",
                                    rel="noopener noreferrer",
                                ),
                                " · ",
                                html.A(
                                    "FundéuRAE ↗",
                                    href=FUNDEU_SOURCE_URL,
                                    target="_blank",
                                    rel="noopener noreferrer",
                                ),
                            ]
                        ),
                        translated("glossary_original_language", tag=html.P),
                    ],
                    className="didactica-glossary-note",
                ),
                html.Section(
                    [
                        html.Div(
                            [
                                html.Label(
                                    translated("search_term"),
                                    htmlFor="didactica-glossary-search",
                                ),
                                dcc.Input(
                                    id="didactica-glossary-search",
                                    type="search",
                                    debounce=True,
                                    placeholder=pair("search_placeholder")[0],
                                ),
                            ],
                            className="didactica-field",
                        ),
                        html.Div(
                            [
                                html.Span(
                                    translated("category"),
                                    id="didactica-glossary-category-label",
                                    className="didactica-field-label",
                                ),
                                dcc.Dropdown(
                                    id="didactica-glossary-category",
                                    options=category_options,
                                    value="all",
                                    clearable=False,
                                    className="didactica-dropdown",
                                ),
                            ],
                            className="didactica-field",
                            role="group",
                            **dash_attrs(
                                {"aria-labelledby": "didactica-glossary-category-label"}
                            ),
                        ),
                    ],
                    className="didactica-filters",
                ),
                html.P(
                    id="didactica-glossary-count",
                    className="didactica-result-count",
                    **dash_attrs({"aria-live": "polite"}),
                ),
                html.Section(
                    id="didactica-glossary-results",
                    className="didactica-glossary-grid",
                    **dash_attrs({"aria-live": "polite"}),
                ),
            ],
            className="didactica-shell app-page app-page-container",
        )
    )


def build_presentations_layout() -> Component:
    return _page(
        html.Main(
            [
                _subpage_header("presentations", "presentations_desc"),
                dcc.Store(
                    id="didactica-presentations-state",
                    data={"status": "LOADING", "count": 0},
                    storage_type="memory",
                ),
                dcc.Interval(
                    id="didactica-presentations-load",
                    interval=1,
                    max_intervals=1,
                ),
                html.Section(
                    [
                        contextual_loading(
                            html.Div(
                                translated("presentations_loading", tag=html.P),
                                id="didactica-presentations-list",
                                className="didactica-presentations-list is-loading",
                                **dash_attrs({"aria-live": "polite"}),
                            ),
                            "presentations_loading",
                            element_id="didactica-presentations-loading",
                        ),
                        html.Button(
                            translated("retry"),
                            id="didactica-presentations-retry",
                            type="button",
                            className="didactica-button didactica-button-secondary is-hidden",
                            n_clicks=0,
                        ),
                    ],
                    className="didactica-presentations-library",
                ),
                translated("presentations_material_note", tag=html.P, class_name="didactica-presentations-note"),
            ],
            className="didactica-shell didactica-presentations-page app-page app-page-container",
        )
    )


def build_games_layout(game_id: str | None = None) -> Component:
    if game_id == "rank_countries":
        return _build_ranking_game_layout()
    if game_id != "guess_term":
        return html.Div(
            dcc.Location(
                id="didactica-games-catalog-redirect",
                href=route_path("didactica"),
                refresh=False,
            )
        )
    state = new_game_state(game_id)
    question, options = _game_round(state, "es")
    return _page(
        html.Main(
            [
                dcc.Store(id="didactica-game-state", data=state),
                dcc.Link(
                    text("← Didáctica", "← Learning"),
                    href=route_path("didactica"),
                    className="didactica-back-link",
                ),
                html.Header(
                    [
                        translated("guess_term", tag=html.H1),
                        translated("guess_desc", tag=html.P),
                    ],
                    className="didactica-subpage-header app-page-header",
                ),
                html.Div(
                    [
                        html.Strong(id="didactica-game-round"),
                        html.Strong(id="didactica-game-score"),
                    ],
                    className="didactica-game-stats",
                ),
                html.Progress(
                    id="didactica-game-progress",
                    value="1",
                    max=len(state["order"]),
                    className="didactica-progress",
                ),
                html.Article(
                    [
                        html.P(
                            id="didactica-game-prompt",
                            children=question,
                            className="didactica-game-prompt",
                        ),
                        dcc.RadioItems(
                            id="didactica-game-answer",
                            options=options,
                            className="didactica-radio-group",
                        ),
                        html.P(
                            id="didactica-game-hint-text",
                            className="didactica-hint",
                            **dash_attrs({"aria-live": "polite"}),
                        ),
                        html.P(
                            id="didactica-game-feedback",
                            className="didactica-feedback",
                            **dash_attrs({"aria-live": "assertive"}),
                        ),
                        html.Div(
                            [
                                html.Button(
                                    translated("hint"),
                                    id="didactica-game-hint",
                                    type="button",
                                    className="didactica-button didactica-button-secondary",
                                ),
                                html.Button(
                                    translated("answer"),
                                    id="didactica-game-submit",
                                    type="button",
                                    className="didactica-button",
                                ),
                                html.Button(
                                    translated("next"),
                                    id="didactica-game-next",
                                    type="button",
                                    className="didactica-button",
                                    disabled=True,
                                ),
                            ],
                            className="didactica-actions",
                        ),
                    ],
                    className="didactica-game-card",
                ),
                html.Div(
                    [
                        build_source_attribution("fra", compact=True),
                        build_source_attribution("ilga", compact=True),
                    ],
                    className="didactica-game-attributions",
                ),
            ],
            className="didactica-shell didactica-viewer app-page app-page-container",
        )
    )


def _build_ranking_game_layout() -> Component:
    state = new_ranking_game()
    return _page(
        html.Main(
            [
                dcc.Store(
                    id="didactica-ranking-state",
                    data=state,
                    storage_type="memory",
                ),
                dcc.Link(
                    text("← Didáctica", "← Learning"),
                    href=route_path("didactica"),
                    className="didactica-back-link",
                ),
                html.Header(
                    [
                        translated("rank_countries", tag=html.H1),
                        translated("rank_countries_desc", tag=html.P),
                    ],
                    className="didactica-subpage-header app-page-header",
                ),
                html.P(
                    translated("rank_countries_instructions"),
                    className="ranking-game-instructions",
                ),
                html.Article(
                    [
                        html.Div(
                            ranking_game_rows(state, "es"),
                            id="didactica-ranking-list",
                            className="ranking-game-list",
                            **dash_attrs({"aria-live": "polite"}),
                        ),
                        html.Div(
                            [
                                html.Button(
                                    translated("check"),
                                    id="didactica-ranking-check",
                                    n_clicks=0,
                                    type="button",
                                    disabled=len(state.get("items", [])) < 2,
                                    className="didactica-button",
                                ),
                                html.Button(
                                    translated("new_round"),
                                    id="didactica-ranking-new",
                                    n_clicks=0,
                                    type="button",
                                    className="didactica-button didactica-button-secondary",
                                ),
                            ],
                            className="didactica-actions ranking-game-actions",
                        ),
                        html.Div(
                            id="didactica-ranking-result",
                            className="ranking-game-result",
                            **dash_attrs({"aria-live": "assertive"}),
                        ),
                    ],
                    className="didactica-game-card ranking-game-card",
                ),
                translated(
                    "rank_countries_methodology", tag=html.P, class_name="ranking-game-note"
                ),
                build_source_attribution("ilga", year=HOME_LEGAL_YEAR, compact=True),
            ],
            className="didactica-shell didactica-viewer app-page app-page-container",
        )
    )


def build_word_search_layout(*, seed: int | None = None) -> Component:
    state = create_word_search_game(seed=seed)
    return _page(
        html.Main(
            [
                dcc.Store(id="didactica-word-search-state", data=state, storage_type="memory"),
                dcc.Link(
                    text("← Didáctica", "← Learning"),
                    href=route_path("didactica"),
                    className="didactica-back-link",
                ),
                html.Header(
                    [
                        translated("word_search", tag=html.H1),
                        translated("word_search_desc", tag=html.P),
                    ],
                    className="didactica-subpage-header app-page-header",
                ),
                html.P(
                    translated("word_search_instructions"),
                    className="word-search-instructions",
                    id="didactica-word-search-instructions",
                ),
                html.Div(
                    [
                        html.Section(
                            [
                                html.Div(
                                    word_search_progress(state, "es"),
                                    id="didactica-word-search-progress",
                                    className="word-search-progress",
                                    **dash_attrs({"aria-live": "polite"}),
                                ),
                                html.Div(
                                    word_search_board(state, "es"),
                                    id="didactica-word-search-grid",
                                ),
                            ],
                            className="word-search-board-panel",
                            **dash_attrs({"aria-labelledby": "didactica-word-search-instructions"}),
                        ),
                        html.Aside(
                            [
                                translated("words", tag=html.H2),
                                html.Div(
                                    word_search_words(state, "es"),
                                    id="didactica-word-search-words",
                                ),
                                html.P(
                                    id="didactica-word-search-feedback",
                                    className="didactica-feedback word-search-feedback",
                                    **dash_attrs({"aria-live": "assertive"}),
                                ),
                                _word_search_confetti(),
                                html.Button(
                                    translated("new_word_search"),
                                    id="didactica-word-search-new",
                                    n_clicks=0,
                                    type="button",
                                    className="didactica-button word-search-new-game",
                                ),
                            ],
                            className="word-search-sidebar",
                        ),
                    ],
                    className="word-search-layout",
                ),
            ],
            className="didactica-shell word-search-page app-page app-page-container",
        )
    )


def build_docente_layout() -> Component:
    if not can_access_docente_material(current_user):
        return _page(access_denied())
    try:
        activities = list_owned_games(current_user)
    except PyMongoError, RuntimeError:
        activities = []
    return _page(
        html.Main(
            [
                dcc.Link(
                    translated("back_learning"),
                    href=route_path("didactica"),
                    className="didactica-back-link",
                ),
                html.Header(
                    [
                        translated("docente", tag=html.H1),
                        translated("docente_desc", tag=html.P),
                    ],
                    className="didactica-hero teacher-space-hero app-page-header",
                ),
                html.Section(
                    [
                        translated("my_games", tag=html.H2),
                        html.Div(
                            [_activity_card(item) for item in activities]
                            if activities
                            else [translated("no_custom_activities", tag=html.P)],
                            id="teacher-activity-list",
                            className="teacher-activity-list",
                        ),
                        html.P(
                            id="teacher-activity-list-status",
                            className="didactica-feedback",
                            **dash_attrs({"aria-live": "polite"}),
                        ),
                    ],
                    className="didactica-docente-section teacher-activities-section",
                ),
                html.Section(
                    [
                        translated("create_new_activity", tag=html.H2),
                        translated("create_new_activity_desc", tag=html.P),
                        html.Div(
                            [_activity_type_card(game_type) for game_type in GAME_TYPE_DEFINITIONS],
                            className="teacher-game-type-grid",
                        ),
                    ],
                    className="didactica-docente-section",
                ),
            ],
            className="didactica-shell teacher-space app-page app-page-container",
        )
    )


def build_activity_editor_layout(
    activity_id: str | None = None, initial_game_type: str | None = None
) -> Component:
    if not can_manage_own_edu_games(current_user):
        return _page(access_denied())
    activity = get_owned_game(current_user, activity_id) if activity_id else None
    if activity_id and activity is None:
        return _page(access_denied())
    values = _activity_editor_values(activity)
    if activity is None and initial_game_type in GAME_TYPE_DEFINITIONS:
        values["game_type"] = initial_game_type
    terms = list_glossary_terms()
    years = sorted((int(year) for year in get_ilga_years()), reverse=True)
    year = int(values["year"] or (years[0] if years else HOME_LEGAL_YEAR))
    country_options = _legal_country_options(year)
    return _page(
        html.Main(
            [
                dcc.Store(id="teacher-editor-activity-id", data=activity_id),
                dcc.Link(
                    translated("back_teacher_space"),
                    href=route_path("educators"),
                    className="didactica-back-link",
                ),
                html.Header(
                    [translated("game_creator", tag=html.H1), translated("create_activity_lead", tag=html.P)],
                    className="didactica-subpage-header app-page-header",
                ),
                html.Section(
                    [
                        translated("step_type", tag=html.H2),
                        dcc.RadioItems(
                            id="teacher-editor-game-type",
                            options=[
                                {
                                    "label": text(*pair(definition["label_key"])),
                                    "value": game_type,
                                }
                                for game_type, definition in GAME_TYPE_DEFINITIONS.items()
                            ],
                            value=values["game_type"],
                            className="teacher-game-type-selector",
                        ),
                    ],
                    className="teacher-editor-step",
                ),
                html.Section(
                    [
                        translated("step_content", tag=html.H2),
                        html.Div(
                            [
                                html.Span(
                                    translated("select_terms"),
                                    id="teacher-editor-term-ids-label",
                                    className="didactica-field-label",
                                ),
                                dcc.Dropdown(
                                    id="teacher-editor-term-ids",
                                    options=[{"label": term.term, "value": term.id} for term in terms],
                                    value=values["term_ids"],
                                    multi=True,
                                    className="didactica-dropdown",
                                ),
                            ],
                            id="teacher-editor-glossary-content",
                            className="didactica-field",
                            role="group",
                            **dash_attrs(
                                {"aria-labelledby": "teacher-editor-term-ids-label"}
                            ),
                        ),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Span(
                                            translated("legal_year"),
                                            id="teacher-editor-year-label",
                                            className="didactica-field-label",
                                        ),
                                        dcc.Dropdown(
                                            id="teacher-editor-year",
                                            options=[
                                                {"label": str(item), "value": item}
                                                for item in years
                                            ],
                                            value=year,
                                            clearable=False,
                                            className="didactica-dropdown",
                                        ),
                                    ],
                                    className="didactica-field-group",
                                    role="group",
                                    **dash_attrs(
                                        {"aria-labelledby": "teacher-editor-year-label"}
                                    ),
                                ),
                                html.Div(
                                    [
                                        html.Span(
                                            translated("select_countries"),
                                            id="teacher-editor-country-codes-label",
                                            className="didactica-field-label",
                                        ),
                                        dcc.Dropdown(
                                            id="teacher-editor-country-codes",
                                            options=country_options,
                                            value=values["country_codes"],
                                            multi=True,
                                            className="didactica-dropdown",
                                        ),
                                    ],
                                    className="didactica-field-group",
                                    role="group",
                                    **dash_attrs(
                                        {
                                            "aria-labelledby": (
                                                "teacher-editor-country-codes-label"
                                            )
                                        }
                                    ),
                                ),
                                translated("ranking_required_note", tag=html.P, class_name="ranking-game-note"),
                            ],
                            id="teacher-editor-ranking-content",
                            className="didactica-field is-hidden",
                        ),
                    ],
                    className="teacher-editor-step",
                ),
                html.Section(
                    [
                        translated("step_configuration", tag=html.H2),
                        _editor_field("title", "teacher-editor-title", values["title"], required=True),
                        _editor_field("description", "teacher-editor-description", values["description"], multiline=True),
                        _editor_field("custom_instructions", "teacher-editor-instructions", values["instructions"], multiline=True),
                        _editor_field("teacher_note", "teacher-editor-teacher-note", values["teacher_note"], multiline=True, help_key="teacher_note_help"),
                        html.Div(
                            [
                                html.Span(
                                    translated("language"),
                                    id="teacher-editor-language-label",
                                    className="didactica-field-label",
                                ),
                                dcc.RadioItems(
                                    id="teacher-editor-language",
                                    options=[{"label": "Español", "value": "es"}, {"label": "English", "value": "en"}],
                                    value=values["language"],
                                    inline=True,
                                ),
                            ],
                            className="didactica-field",
                            role="group",
                            **dash_attrs(
                                {"aria-labelledby": "teacher-editor-language-label"}
                            ),
                        ),
                        _number_field("question_count", "teacher-editor-question-count", values["question_count"], 5, 20),
                        dcc.Checklist(
                            id="teacher-editor-options",
                            options=[
                                {"label": translated("shuffle_order"), "value": "shuffle"},
                            ],
                            value=values["options"],
                            className="teacher-editor-options",
                        ),
                        html.Div(
                            [
                                html.Span(
                                    translated("activity_status"),
                                    id="teacher-editor-status-label",
                                    className="didactica-field-label",
                                ),
                                dcc.Dropdown(
                                    id="teacher-editor-status",
                                    options=[
                                        {"label": translated("draft"), "value": "DRAFT"},
                                        {"label": translated("active"), "value": "ACTIVE"},
                                        {"label": translated("archived"), "value": "ARCHIVED"},
                                    ],
                                    value=values["status"],
                                    clearable=False,
                                    className="didactica-dropdown",
                                ),
                            ],
                            className="didactica-field",
                            role="group",
                            **dash_attrs(
                                {"aria-labelledby": "teacher-editor-status-label"}
                            ),
                        ),
                    ],
                    className="teacher-editor-step",
                ),
                html.Section(
                    [
                        translated("step_preview", tag=html.H2),
                        html.Button(translated("generate_preview"), id="teacher-editor-preview", type="button", className="didactica-button didactica-button-secondary"),
                        html.Div(id="teacher-editor-preview-content", className="teacher-activity-preview"),
                    ],
                    className="teacher-editor-step",
                ),
                html.Section(
                    [
                        translated("step_save", tag=html.H2),
                        html.Button(translated("save_game"), id="teacher-editor-save", type="button", className="didactica-button"),
                        html.P(id="teacher-editor-status-message", className="didactica-feedback", **dash_attrs({"aria-live": "assertive"})),
                        html.Div(
                            id="teacher-editor-share-link",
                            className="teacher-editor-share-link is-hidden",
                            **dash_attrs({"aria-live": "polite"}),
                        ),
                    ],
                    className="teacher-editor-step",
                ),
            ],
            className="didactica-shell teacher-activity-editor app-page app-page-container",
        )
    )


def build_custom_activity_layout(activity_id: str | None) -> Component:
    if not activity_id or not can_manage_own_edu_games(current_user):
        return _page(access_denied())
    activity = get_owned_game(current_user, activity_id)
    if activity is None:
        return _page(access_denied())
    state = build_activity_game_state(activity)
    return _page(
        html.Main(
            [
                dcc.Link(translated("back_teacher_space"), href=route_path("educators"), className="didactica-back-link"),
                html.Header(
                    [html.H1(activity["title"]), html.P(activity.get("description") or "")],
                    className="didactica-subpage-header app-page-header",
                ),
                html.P(activity.get("instructions") or "", className="teacher-activity-instructions"),
                _activity_engine(activity, state),
                html.Aside(
                    [translated("teacher_note", tag=html.H2), html.P(activity.get("teacher_note") or "")],
                    className="teacher-note-panel",
                )
                if activity.get("teacher_note")
                else None,
            ],
            className="didactica-shell teacher-activity-player app-page app-page-container",
        )
    )


def build_public_activity_layout(public_id: str | None) -> Component:
    try:
        activity = get_public_game(public_id or "")
    except CustomGameValidationError:
        activity = None
    if activity is None:
        return _page(
            html.Main(
                [
                    _subpage_header("activity_unavailable", "activity_unavailable_desc"),
                    dcc.Link(
                        translated("back_learning"),
                        href=route_path("didactica"),
                        className="didactica-button didactica-button-secondary",
                    ),
                ],
                className="didactica-shell app-page app-page-container",
            )
        )
    state = build_activity_game_state(activity)
    return _page(
        html.Main(
            [
                dcc.Link(
                    translated("back_learning"),
                    href=route_path("didactica"),
                    className="didactica-back-link",
                ),
                html.Header(
                    [html.H1(activity["title"]), html.P(activity.get("description") or "")],
                    className="didactica-subpage-header app-page-header",
                ),
                html.P(
                    activity.get("instructions") or "",
                    className="teacher-activity-instructions",
                ),
                _activity_engine(activity, state),
                html.Aside(
                    [
                        translated("teacher_note", tag=html.H2),
                        html.P(activity.get("teacher_note") or ""),
                    ],
                    className="teacher-note-panel",
                )
                if activity.get("teacher_note")
                else None,
            ],
            className="didactica-shell teacher-activity-player app-page app-page-container",
        )
    )


def build_access_denied_layout() -> Component:
    return _page(access_denied())


def register_didactica_callbacks(app: Dash) -> None:
    @app.callback(
        Output("didactica-glossary-search", "placeholder"),
        Input("app-language-store", "data"),
    )
    def translate_glossary_placeholder(language: str | None):
        return tr("search_placeholder", _language(language))

    @app.callback(
        Output("didactica-glossary-results", "children"),
        Output("didactica-glossary-count", "children"),
        Input("didactica-glossary-search", "value"),
        Input("didactica-glossary-category", "value"),
        Input("app-language-store", "data"),
    )
    def filter_glossary(query: str | None, category: str | None, language: str | None):
        language = _language(language)
        results = search_glossary(query, category, language)
        return [
            glossary_card(item, language) for item in results
        ], f"{len(results)} {tr('results', language)}"

    @app.callback(
        Output("didactica-presentations-list", "children"),
        Output("didactica-presentations-list", "className"),
        Output("didactica-presentations-retry", "className"),
        Output("didactica-presentations-state", "data"),
        Input("didactica-presentations-load", "n_intervals"),
        Input("didactica-presentations-retry", "n_clicks"),
    )
    def load_didactic_presentations(_load: int | None, _retry: int | None):
        try:
            presentations = list_didactic_presentations()
        except DidacticPresentationStorageError:
            return (
                translated("presentations_error", tag=html.P),
                "didactica-presentations-list is-error",
                "didactica-button didactica-button-secondary",
                {"status": "ERROR", "count": 0},
            )
        if not presentations:
            return (
                translated("presentations_empty", tag=html.P),
                "didactica-presentations-list is-empty",
                "didactica-button didactica-button-secondary is-hidden",
                {"status": "EMPTY", "count": 0},
            )
        return (
            [_presentation_card(item.to_dict()) for item in presentations],
            "didactica-presentations-list is-ready",
            "didactica-button didactica-button-secondary is-hidden",
            {"status": "READY", "count": len(presentations)},
        )

    @app.callback(
        Output("didactica-word-search-grid", "children"),
        Output("didactica-word-search-words", "children"),
        Output("didactica-word-search-progress", "children"),
        Output("didactica-word-search-feedback", "children"),
        Output("didactica-word-search-feedback", "className"),
        Output("didactica-word-search-state", "data"),
        Output("didactica-word-search-confetti", "className"),
        Input("didactica-word-search-new", "n_clicks"),
        Input({"type": "didactica-word-search-cell", "index": ALL}, "n_clicks"),
        Input("app-language-store", "data"),
        State("didactica-word-search-state", "data"),
    )
    def play_word_search(_new_game, _cell_clicks, language, state):
        language = _language(language)
        triggered = ctx.triggered_id
        status = ""
        if triggered == "didactica-word-search-new" or not isinstance(state, dict):
            configuration = dict(state.get("_activity_configuration") or {}) if isinstance(state, dict) else {}
            state = (
                create_word_search_game(
                    language=language,
                    word_count=int(configuration.get("word_count") or 8),
                    term_ids=configuration.get("term_ids"),
                    board_size=(
                        int(configuration["board_size"])
                        if configuration.get("board_size")
                        else None
                    ),
                )
                if configuration
                else create_word_search_game(language=language)
            )
            if configuration:
                state["_activity_configuration"] = configuration
        elif (
            isinstance(triggered, dict)
            and triggered.get("type") == "didactica-word-search-cell"
            and any(_cell_clicks or [])
        ):
            state, status = apply_word_search_selection(state, int(triggered["index"]))

        feedback = {
            "start": tr("select_word_end", language),
            "found": tr("word_search_found", language),
            "duplicate": tr("word_search_duplicate", language),
            "incorrect": tr("word_search_incorrect", language),
            "complete": tr("word_search_complete", language),
        }.get(status, "")
        if not feedback and is_word_search_complete(state):
            feedback = tr("word_search_complete", language)
            status = "complete"
        feedback_class = "didactica-feedback word-search-feedback"
        if status in {"found", "complete"}:
            feedback_class += " is-success"
        elif status in {"incorrect", "duplicate"}:
            feedback_class += " is-error"
        return (
            word_search_board(state, language),
            word_search_words(state, language),
            word_search_progress(state, language),
            feedback,
            feedback_class,
            state,
            "word-search-confetti is-active" if status == "complete" else "word-search-confetti",
        )

    @app.callback(
        Output("didactica-ranking-list", "children"),
        Output("didactica-ranking-result", "children"),
        Output("didactica-ranking-state", "data"),
        Output("didactica-ranking-check", "disabled"),
        Input("didactica-ranking-new", "n_clicks"),
        Input("didactica-ranking-check", "n_clicks"),
        Input({"type": "didactica-ranking-up", "index": ALL}, "n_clicks"),
        Input({"type": "didactica-ranking-down", "index": ALL}, "n_clicks"),
        Input("app-language-store", "data"),
        State("didactica-ranking-state", "data"),
    )
    def play_ranking_game(_new, _check, _up, _down, language, state):
        language = _language(language)
        current = dict(state or {})
        triggered = ctx.triggered_id
        if triggered == "didactica-ranking-new" or not current:
            previous_codes = [
                str(item.get("country_code") or "")
                for item in current.get("items", [])
                if isinstance(item, dict)
            ]
            configuration = dict(current.get("_activity_configuration") or {})
            current = new_ranking_game(
                previous_codes=previous_codes,
                year=int(configuration.get("year") or HOME_LEGAL_YEAR),
                country_count=int(configuration.get("country_count") or 4),
                country_codes=configuration.get("country_codes"),
            )
            if configuration:
                current["_activity_configuration"] = configuration
        elif triggered == "didactica-ranking-check" and not current.get("checked"):
            current = check_ranking_game(current)
        elif isinstance(triggered, dict):
            control_type = triggered.get("type")
            if control_type in {"didactica-ranking-up", "didactica-ranking-down"}:
                direction = -1 if control_type == "didactica-ranking-up" else 1
                current = move_ranking_country(
                    current,
                    int(triggered.get("index", 0)),
                    direction,
                )
        raw_items = current.get("items")
        items: list[Any] = raw_items if isinstance(raw_items, list) else []
        return (
            ranking_game_rows(current, language),
            ranking_game_result(current, language),
            current,
            bool(current.get("checked")) or len(items) < 2,
        )

    @app.callback(
        Output("didactica-game-prompt", "children"),
        Output("didactica-game-answer", "options"),
        Output("didactica-game-answer", "value"),
        Output("didactica-game-feedback", "children"),
        Output("didactica-game-feedback", "className"),
        Output("didactica-game-hint-text", "children"),
        Output("didactica-game-state", "data"),
        Output("didactica-game-round", "children"),
        Output("didactica-game-score", "children"),
        Output("didactica-game-progress", "value"),
        Output("didactica-game-submit", "disabled"),
        Output("didactica-game-next", "disabled"),
        Output("didactica-game-next", "children"),
        Output("didactica-game-answer", "className"),
        Output("didactica-game-hint", "disabled"),
        Input("didactica-game-submit", "n_clicks"),
        Input("didactica-game-next", "n_clicks"),
        Input("didactica-game-hint", "n_clicks"),
        Input("app-language-store", "data"),
        State("didactica-game-answer", "value"),
        State("didactica-game-state", "data"),
    )
    def play_game(_submit, _next, _hint, language, selected, state):
        language = _language(language)
        if not user_has_permission(current_user, Permission.PLAY_EDU_GAMES):
            return (no_update,) * 15
        state = dict(state or {})
        order = state.get("order", [])
        index = min(int(state.get("index", 0)), max(0, len(order) - 1))
        feedback, feedback_class, hint = "", "didactica-feedback", ""
        if ctx.triggered_id == "didactica-game-next":
            if state.get("completed"):
                configuration = dict(state.get("_activity_configuration") or {})
                previous_order = list(order)
                state = new_game_state(
                    "guess_term",
                    rounds=int(configuration.get("question_count") or 5),
                    term_ids=configuration.get("term_ids"),
                    shuffle=bool(configuration.get("shuffle", True)),
                    previous_term_ids=previous_order,
                )
                if configuration:
                    state["_activity_configuration"] = configuration
                order = state["order"]
                index = 0
                selected = None
            elif state.get("answered") and index < len(order) - 1:
                index += 1
                state.update(index=index, answered=False, selected=None)
                selected = None
        elif ctx.triggered_id == "didactica-game-submit":
            if selected is None:
                feedback, feedback_class = (
                    tr("choose_answer", language),
                    "didactica-feedback is-error",
                )
            elif not state.get("answered"):
                correct, correct_term = _check_game_answer(
                    state["game_id"], order[index], selected, language
                )
                state["answered"] = True
                state["selected"] = selected
                if correct:
                    state["score"] = int(state.get("score", 0)) + 1
                    feedback = f"{tr('correct', language)}."
                else:
                    feedback = (
                        f'{tr("incorrect", language)}. '
                        f'{tr("correct_answer_was", language)}: «{correct_term}».'
                    )
                feedback_class = (
                    "didactica-feedback is-success" if correct else "didactica-feedback is-error"
                )
                if index == len(order) - 1:
                    state["completed"] = True
        elif ctx.triggered_id == "didactica-game-hint":
            hint = _game_hint(state["game_id"], order[index], language)
        completed = bool(state.get("completed"))
        if completed:
            score = int(state.get("score", 0))
            question = html.Div(
                [
                    html.H2(f"{tr('final_score', language)} {score}/{len(order)}"),
                    translated("final_encouragement", tag=html.P),
                ],
                className="guess-game-finish",
            )
            options = []
        else:
            question, options = _game_round(state, language)
        answered = bool(state.get("answered"))
        return (
            question,
            options,
            state.get("selected") if answered else selected,
            feedback,
            feedback_class,
            hint,
            state,
            (
                tr("game_finished", language)
                if completed
                else f"{tr('round', language)} {index + 1}/{len(order)}"
            ),
            f"{tr('score', language)}: {state.get('score', 0)}",
            str(index + 1),
            answered or completed,
            not completed and (not answered or index == len(order) - 1),
            tr("play_again", language) if completed else tr("next", language),
            "didactica-radio-group is-hidden" if completed else "didactica-radio-group",
            completed,
        )

    @app.callback(
        Output("didactica-docente-detail", "children"),
        Input("didactica-docente-select", "value"),
        Input("app-language-store", "data"),
    )
    def show_docente_resource(resource_id: str | None, language: str | None):
        if not can_access_docente_material(current_user):
            return access_denied()
        resource = get_teacher_resource(str(resource_id or ""))
        return (
            teacher_resource_details(resource, _language(language))
            if resource
            else tr("not_found", _language(language))
        )

    @app.callback(
        Output("didactica-docente-download", "data"),
        Output("didactica-docente-status", "children"),
        Input("didactica-docente-download-button", "n_clicks"),
        State("didactica-docente-select", "value"),
        State("app-language-store", "data"),
        prevent_initial_call=True,
    )
    def download_docente_resource(clicks, resource_id, language):
        language = _language(language)
        if not clicks:
            return no_update, no_update
        if not can_access_docente_material(current_user):
            return no_update, tr("download_denied", language)
        try:
            payload, filename = generate_teacher_resource_pdf(str(resource_id or ""), language)
        except ValueError:
            return no_update, tr("download_error", language)
        return dcc.send_bytes(payload, filename, type="application/pdf"), ""

    _register_teacher_activity_callbacks(app)


def _register_teacher_activity_callbacks(app: Dash) -> None:
    @app.callback(
        Output("teacher-editor-glossary-content", "className"),
        Output("teacher-editor-ranking-content", "className"),
        Output("teacher-editor-question-count-field", "className"),
        Output("teacher-editor-options", "className"),
        Input("teacher-editor-game-type", "value"),
    )
    def show_activity_configuration(game_type: str | None):
        selected = game_type if game_type in GAME_TYPE_DEFINITIONS else "guess_term"
        return (
            "didactica-field" if selected != "legal_ranking" else "didactica-field is-hidden",
            "didactica-field" if selected == "legal_ranking" else "didactica-field is-hidden",
            "didactica-field" if selected == "guess_term" else "didactica-field is-hidden",
            "teacher-editor-options" if selected == "guess_term" else "teacher-editor-options is-hidden",
        )

    @app.callback(
        Output("teacher-editor-country-codes", "options"),
        Output("teacher-editor-country-codes", "value"),
        Input("teacher-editor-year", "value"),
        State("teacher-editor-country-codes", "value"),
    )
    def update_activity_country_options(year: int | None, selected: list[str] | None):
        options = _legal_country_options(int(year or HOME_LEGAL_YEAR))
        allowed = {str(item["value"]) for item in options}
        return options, [code for code in selected or [] if code in allowed]

    editor_states = _teacher_editor_states()

    @app.callback(
        Output("teacher-editor-preview-content", "children"),
        Input("teacher-editor-preview", "n_clicks"),
        *editor_states,
        State("app-language-store", "data"),
        prevent_initial_call=True,
    )
    def preview_teacher_activity(_clicks: int | None, *values: Any):
        language = _language(values[-1])
        if not can_manage_own_edu_games(current_user):
            return html.P(tr("docente_required_notice", language), className="is-error")
        try:
            activity = validate_activity(_teacher_activity_payload(values[:-1]))
            state = build_activity_game_state(activity)
            return _activity_engine(activity, state)
        except CustomGameValidationError as exc:
            return html.P(_activity_validation_message(str(exc), language), className="is-error")
        except (PyMongoError, RuntimeError, ValueError):
            return html.P(tr("game_storage_error", language), className="is-error")

    @app.callback(
        Output("teacher-editor-status-message", "children"),
        Output("teacher-editor-activity-id", "data"),
        Output("teacher-editor-share-link", "children"),
        Output("teacher-editor-share-link", "className"),
        Input("teacher-editor-save", "n_clicks"),
        State("teacher-editor-activity-id", "data"),
        *editor_states,
        State("app-language-store", "data"),
        prevent_initial_call=True,
    )
    def save_teacher_activity(
        _clicks: int | None, activity_id: str | None, *values: Any
    ):
        language = _language(values[-1])
        if not can_manage_own_edu_games(current_user):
            return tr("docente_required_notice", language), no_update, no_update, no_update
        try:
            saved = save_owned_game(
                current_user, activity_id, _teacher_activity_payload(values[:-1])
            )
            public_path = (
                f"{route_path('educator_public_activity')}/{saved['public_id']}"
            )
            public_url = (
                f"{request.host_url.rstrip('/')}{public_path}"
                if has_request_context()
                else public_path
            )
            share = html.Div(
                [
                    html.Strong(translated("share_link")),
                    html.Code(public_url, id="teacher-editor-share-url"),
                    dcc.Clipboard(
                        target_id="teacher-editor-share-url",
                        title=tr("copy_link", language),
                        className="didactica-button didactica-button-secondary",
                    ),
                    translated("copy_link", tag=html.Span),
                ],
                className="teacher-share-row",
            )
            return tr("game_saved", language), saved["id"], share, "teacher-editor-share-link"
        except CustomGameAuthorizationError:
            return tr("docente_required_notice", language), no_update, no_update, no_update
        except CustomGameValidationError as exc:
            return _activity_validation_message(str(exc), language), no_update, no_update, no_update
        except PyMongoError, RuntimeError:
            return tr("game_storage_error", language), no_update, no_update, no_update

    @app.callback(
        Output("teacher-activity-list", "children"),
        Output("teacher-activity-list-status", "children"),
        Input({"type": "teacher-activity-duplicate", "index": ALL}, "n_clicks"),
        Input({"type": "teacher-activity-delete", "index": ALL}, "submit_n_clicks"),
        State("app-language-store", "data"),
        prevent_initial_call=True,
    )
    def manage_teacher_activities(_duplicate: list[int], _delete: list[int], language):
        clean_language = _language(language)
        triggered = ctx.triggered_id
        if not can_manage_own_edu_games(current_user) or not isinstance(triggered, dict):
            return no_update, tr("docente_required_notice", clean_language)
        activity_id = str(triggered.get("index") or "")
        try:
            if triggered.get("type") == "teacher-activity-delete":
                deleted = delete_owned_game(current_user, activity_id)
                if not deleted:
                    return no_update, tr("activity_delete_failed", clean_language)
                message = tr("game_deleted", clean_language)
            else:
                duplicate_owned_game(current_user, activity_id)
                message = tr("game_duplicated", clean_language)
            activities = list_owned_games(current_user)
            children = [_activity_card(item) for item in activities]
            return children or [translated("no_custom_activities", tag=html.P)], message
        except CustomGameAuthorizationError:
            return no_update, tr("docente_required_notice", clean_language)
        except CustomGameValidationError:
            return no_update, tr("game_validation_error", clean_language)
        except PyMongoError, RuntimeError:
            return no_update, tr("game_storage_error", clean_language)


def _activity_card(activity: dict[str, Any]) -> Component:
    activity_id = str(activity["id"])
    game_type = str(activity.get("game_type") or "")
    definition = GAME_TYPE_DEFINITIONS.get(game_type, GAME_TYPE_DEFINITIONS["guess_term"])
    updated = activity.get("updated_at")
    date_label = str(updated)[:10] if updated else ""
    public_id = str(activity.get("public_id") or "")
    return html.Article(
        [
            html.Div(
                [
                    html.Span(str(definition["icon"]), className="teacher-activity-card__icon"),
                    html.Div(
                        [
                            html.H3(str(activity.get("title") or "")),
                            html.P(translated(str(definition["label_key"]))),
                        ]
                    ),
                    html.Span(
                        translated(str(activity.get("status") or "draft").lower()),
                        className="teacher-activity-status",
                    ),
                ],
                className="teacher-activity-card__header",
            ),
            html.Time(date_label, dateTime=date_label),
            html.Div(
                [
                    dcc.Link(
                        translated("play"),
                        href=(
                            f"{route_path('educator_public_activity')}/{public_id}"
                            if public_id
                            else f"{route_path('educator_activity')}?id={activity_id}"
                        ),
                        className="didactica-button",
                    ),
                    dcc.Link(
                        translated("edit"),
                        href=f"{route_path('educator_create')}?id={activity_id}",
                        className="didactica-button didactica-button-secondary",
                    ),
                    html.Button(
                        translated("duplicate"),
                        id={"type": "teacher-activity-duplicate", "index": activity_id},
                        type="button",
                        className="didactica-button didactica-button-secondary",
                    ),
                    dcc.ConfirmDialogProvider(
                        html.Button(
                            translated("delete"),
                            type="button",
                            className="didactica-button teacher-activity-delete",
                        ),
                        id={"type": "teacher-activity-delete", "index": activity_id},
                        message=tr("delete_confirmation", current_route_language()),
                    ),
                ],
                className="didactica-actions teacher-activity-actions",
            ),
        ],
        className="teacher-activity-card",
        **dash_attrs({"data-activity-id": activity_id}),
    )


def _activity_type_card(game_type: str) -> Component:
    definition = GAME_TYPE_DEFINITIONS[game_type]
    return dcc.Link(
        [
            html.Span(str(definition["icon"]), className="teacher-game-type-card__icon"),
            translated(str(definition["label_key"]), tag=html.H3),
            translated(
                {
                    "guess_term": "guess_desc",
                    "word_search": "word_search_desc",
                    "legal_ranking": "rank_countries_desc",
                }[game_type],
                tag=html.P,
            ),
        ],
        href=f"{route_path('educator_create')}?type={game_type}",
        className="teacher-game-type-card",
    )


def _activity_editor_values(activity: dict[str, Any] | None) -> dict[str, Any]:
    configuration = dict((activity or {}).get("configuration") or {})
    return {
        "game_type": (activity or {}).get("game_type") or "guess_term",
        "title": (activity or {}).get("title") or "",
        "description": (activity or {}).get("description") or "",
        "instructions": (activity or {}).get("instructions") or "",
        "teacher_note": (activity or {}).get("teacher_note") or "",
        "language": (activity or {}).get("language") or "es",
        "status": (activity or {}).get("status") or "DRAFT",
        "term_ids": configuration.get("term_ids") or [],
        "question_count": configuration.get("question_count") or 5,
        "country_codes": configuration.get("country_codes") or [],
        "year": configuration.get("year") or HOME_LEGAL_YEAR,
        "options": [
            key
            for key in ("shuffle",)
            if configuration.get(key, True)
        ],
    }


def _editor_field(
    label_key: str,
    component_id: str,
    value: Any,
    *,
    multiline: bool = False,
    required: bool = False,
    help_key: str | None = None,
) -> Component:
    control: Component = (
        dcc.Textarea(
            id=component_id,
            value=value,
            maxLength=800,
            className="didactica-textarea",
        )
        if multiline
        else dcc.Input(
            id=component_id,
            value=value,
            type="text",
            required=required,
            maxLength=120,
            className="didactica-input",
        )
    )
    children: list[Component] = [html.Label(translated(label_key), htmlFor=component_id), control]
    if help_key:
        children.append(translated(help_key, tag=html.Small))
    return html.Div(children, className="didactica-field")


def _number_field(
    label_key: str,
    component_id: str,
    value: int,
    minimum: int,
    maximum: int,
    *,
    hidden: bool = False,
) -> Component:
    return html.Div(
        [
            html.Label(translated(label_key), htmlFor=component_id),
            dcc.Input(
                id=component_id,
                value=value,
                type="number",
                min=minimum,
                max=maximum,
                step=1,
                className="didactica-input",
            ),
        ],
        id=f"{component_id}-field",
        className="didactica-field is-hidden" if hidden else "didactica-field",
    )


def _legal_country_options(year: int) -> list[dict[str, Any]]:
    ranking = build_legal_ranking(get_ilga_document_by_year(year))
    return [
        {
            "label": text(*country_labels(entry.country_code, entry.country_name)),
            "value": entry.country_code,
        }
        for entry in ranking
    ]


def _teacher_editor_states() -> list[State]:
    return [
        State("teacher-editor-game-type", "value"),
        State("teacher-editor-title", "value"),
        State("teacher-editor-description", "value"),
        State("teacher-editor-instructions", "value"),
        State("teacher-editor-teacher-note", "value"),
        State("teacher-editor-language", "value"),
        State("teacher-editor-term-ids", "value"),
        State("teacher-editor-question-count", "value"),
        State("teacher-editor-year", "value"),
        State("teacher-editor-country-codes", "value"),
        State("teacher-editor-options", "value"),
        State("teacher-editor-status", "value"),
    ]


def _teacher_activity_payload(values: tuple[Any, ...]) -> dict[str, Any]:
    (
        game_type,
        title,
        description,
        instructions,
        teacher_note,
        language,
        term_ids,
        question_count,
        year,
        country_codes,
        options,
        status,
    ) = values
    selected_options = set(options or [])
    return {
        "game_type": game_type,
        "title": title,
        "description": description,
        "instructions": instructions,
        "teacher_note": teacher_note,
        "language": language,
        "status": status,
        "configuration": {
            "term_ids": term_ids or [],
            "question_count": question_count,
            "word_count": len(term_ids or []),
            "year": year,
            "country_codes": country_codes or [],
            "country_count": len(country_codes or []),
            "shuffle": "shuffle" in selected_options,
        },
    }


def _activity_validation_message(code: str, language: str) -> str:
    messages = {
        "missing_title": ("Introduce un título para la actividad.", "Enter an activity title."),
        "not_enough_terms": ("Selecciona suficientes términos.", "Select enough terms."),
        "word_does_not_fit": (
            "Algunas palabras son demasiado largas para generar esta actividad. Reduce el número de términos o selecciona términos más cortos.",
            "Some words are too long to generate this activity. Select fewer or shorter terms.",
        ),
        "not_enough_countries": (
            "Selecciona suficientes países para la ronda.",
            "Select enough countries for the round.",
        ),
        "not_enough_distinct_scores": (
            "No hay suficientes países con puntuaciones diferentes para crear esta ronda.",
            "There are not enough countries with different scores to create this round.",
        ),
    }
    pair_value = messages.get(code, pair("game_validation_error"))
    return pair_value[1] if language == "en" else pair_value[0]


def _activity_engine(activity: dict[str, Any], state: dict[str, Any]) -> Component:
    game_type = str(activity["game_type"])
    language = str(activity.get("language") or "es")
    state = dict(state)
    state["_activity_configuration"] = dict(activity.get("configuration") or {})
    if game_type == "guess_term":
        question, options = _game_round(state, language)
        return html.Div(
            [
                dcc.Store(id="didactica-game-state", data=state),
                html.Div(
                    [html.Strong(id="didactica-game-round"), html.Strong(id="didactica-game-score")],
                    className="didactica-game-stats",
                ),
                html.Progress(id="didactica-game-progress", value="1", max=len(state["order"]), className="didactica-progress"),
                html.Article(
                    [
                        html.P(question, id="didactica-game-prompt", className="didactica-game-prompt"),
                        dcc.RadioItems(id="didactica-game-answer", options=options, className="didactica-radio-group"),
                        html.P(id="didactica-game-hint-text", className="didactica-hint", **dash_attrs({"aria-live": "polite"})),
                        html.P(id="didactica-game-feedback", className="didactica-feedback", **dash_attrs({"aria-live": "assertive"})),
                        html.Div(
                            [
                                html.Button(translated("hint"), id="didactica-game-hint", type="button", className="didactica-button didactica-button-secondary"),
                                html.Button(translated("answer"), id="didactica-game-submit", type="button", className="didactica-button"),
                                html.Button(translated("next"), id="didactica-game-next", type="button", className="didactica-button", disabled=True),
                            ],
                            className="didactica-actions",
                        ),
                    ],
                    className="didactica-game-card",
                ),
            ],
            className="teacher-engine teacher-engine--guess",
        )
    if game_type == "word_search":
        return html.Div(
            [
                dcc.Store(id="didactica-word-search-state", data=state, storage_type="memory"),
                html.Div(
                    [
                        html.Section(
                            [
                                html.Div(word_search_progress(state, language), id="didactica-word-search-progress", className="word-search-progress"),
                                html.Div(word_search_board(state, language), id="didactica-word-search-grid"),
                            ],
                            className="word-search-board-panel",
                        ),
                        html.Aside(
                            [
                                translated("words", tag=html.H2),
                                html.Div(word_search_words(state, language), id="didactica-word-search-words"),
                                html.P(id="didactica-word-search-feedback", className="didactica-feedback word-search-feedback"),
                                _word_search_confetti(),
                                html.Button(translated("new_word_search"), id="didactica-word-search-new", type="button", className="didactica-button"),
                            ],
                            className="word-search-sidebar",
                        ),
                    ],
                    className="word-search-layout",
                ),
            ],
            className="teacher-engine teacher-engine--word-search",
        )
    return html.Div(
        [
            dcc.Store(id="didactica-ranking-state", data=state, storage_type="memory"),
            translated("ranking_order_instruction", tag=html.P, class_name="ranking-game-instructions"),
            html.Article(
                [
                    html.Div(ranking_game_rows(state, language), id="didactica-ranking-list", className="ranking-game-list"),
                    html.Div(
                        [
                            html.Button(translated("check"), id="didactica-ranking-check", type="button", className="didactica-button"),
                            html.Button(translated("new_round"), id="didactica-ranking-new", type="button", className="didactica-button didactica-button-secondary"),
                        ],
                        className="didactica-actions ranking-game-actions",
                    ),
                    html.Div(id="didactica-ranking-result", className="ranking-game-result"),
                ],
                className="didactica-game-card ranking-game-card",
            ),
            translated("ranking_required_note", tag=html.P, class_name="ranking-game-note"),
            build_source_attribution("ilga", year=int(state.get("year") or HOME_LEGAL_YEAR), compact=True),
        ],
        className="teacher-engine teacher-engine--ranking",
    )


def _page(content: Component) -> Component:
    return html.Div([build_navbar(active="didactica"), content])


def _subpage_header(title_key: str, description_key: str) -> Component:
    return html.Header(
        [
            dcc.Link(
                text("← Didáctica", "← Learning"),
                href=route_path("didactica"),
                className="didactica-back-link",
            ),
            translated(title_key, tag=html.H1),
            translated(description_key, tag=html.P),
        ],
        className="didactica-subpage-header app-page-header",
    )


def _word_search_confetti() -> Component:
    return html.Div(
        [
            html.Span(
                className=f"word-search-confetti__piece piece-{index + 1}",
                **dash_attrs({"aria-hidden": "true"}),
            )
            for index in range(16)
        ],
        id="didactica-word-search-confetti",
        className="word-search-confetti",
        **dash_attrs({"aria-hidden": "true"}),
    )


def _presentation_card(item: dict[str, Any]) -> Component:
    display_name = str(item.get("display_name") or item.get("name") or "")
    filename = str(item.get("name") or "")
    file_type = str(item.get("file_type") or "")
    size_es, size_en = _file_size_labels(item.get("size"))
    metadata: list[Component | str] = [html.Span(file_type)]
    if size_es:
        metadata.extend([" · ", html.Span(size_es, **text_attrs(size_es, size_en))])
    updated_es, updated_en = _updated_labels(item.get("updated_at"))
    if updated_es:
        metadata.append(
            html.Span(
                updated_es,
                className="didactica-presentation-updated",
                **text_attrs(updated_es, updated_en),
            )
        )
    download_es = f"Descargar {display_name}"
    download_en = f"Download {display_name}"
    return html.Article(
        [
            html.Div(
                [
                    html.Span(
                        "PPT" if file_type == "PowerPoint" else "PDF",
                        className="didactica-presentation-icon",
                        **dash_attrs({"aria-hidden": "true"}),
                    ),
                    html.Div(
                        [
                            html.H2(display_name),
                            html.P(metadata, className="didactica-presentation-metadata"),
                        ],
                    ),
                ],
                className="didactica-presentation-info",
            ),
            html.A(
                [translated("download"), html.Span("↓", **dash_attrs({"aria-hidden": "true"}))],
                href=str(item.get("download_url") or ""),
                download=filename,
                className="didactica-button didactica-presentation-download",
                **dash_attrs(
                    {
                        "aria-label": download_es,
                        **attribute_attrs("aria-label", download_es, download_en),
                    }
                ),
            ),
        ],
        className="didactica-presentation-card",
    )


def _file_size_labels(value: object) -> tuple[str, str]:
    if not isinstance(value, int | float) or value < 0:
        return "", ""
    size = float(value)
    units = ("B", "KB", "MB", "GB")
    unit = units[0]
    for candidate in units:
        unit = candidate
        if size < 1024 or candidate == units[-1]:
            break
        size /= 1024
    number = f"{size:.0f}" if unit == "B" or size >= 100 else f"{size:.1f}"
    return f"{number.replace('.', ',')} {unit}", f"{number} {unit}"


def _updated_labels(value: object) -> tuple[str, str]:
    try:
        updated = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return "", ""
    date_label = updated.strftime("%d/%m/%Y")
    return f"Actualizado: {date_label}", f"Updated: {date_label}"


def _language(value: str | None) -> str:
    return "en" if value == "en" else "es"


def _game_round(state: dict[str, Any], language: str) -> tuple[str, list[dict[str, str]]]:
    identifier = state["order"][int(state.get("index", 0))]
    if state.get("game_id") != "guess_term":
        raise ValueError("unknown_game")
    term = get_glossary_term(identifier)
    if term is None:
        raise ValueError("unknown_glossary_term")
    return term.definition, guess_options(identifier, language)


def _check_game_answer(
    game_id: str, identifier: str, selected: str, language: str
) -> tuple[bool, str]:
    del language
    if game_id != "guess_term":
        raise ValueError("unknown_game")
    term = get_glossary_term(identifier)
    if term is None:
        raise ValueError("unknown_glossary_term")
    return selected == identifier, term.term


def _game_hint(game_id: str, identifier: str, language: str) -> str:
    if game_id != "guess_term":
        raise ValueError("unknown_game")
    term = get_glossary_term(identifier)
    if term is None:
        raise ValueError("unknown_glossary_term")
    return f'{tr("hint_text", language)} «{term.term[0].upper()}».'
