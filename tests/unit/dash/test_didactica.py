from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from dash import no_update
from werkzeug.exceptions import Forbidden

import app.modules.didactics.page as didactica_page
import app.web.application as dash_app_module
from app.core.auth.permissions import can_access_docente_material
from app.modules.account.users.schemas import UserRole, UserType
from app.modules.didactics.components import glossary_card
from app.modules.didactics.game_service import new_game_state
from app.modules.didactics.glossary_service import (
    FUNDEU_SOURCE_URL,
    PROHIBITED_TERM_KEYS,
    UNAM_SOURCE_URL,
    get_glossary_term,
    list_glossary_terms,
    normalized_term_key,
    search_glossary,
    validate_glossary_catalog,
)
from app.modules.didactics.models import GlossarySource, GlossaryTerm
from app.modules.didactics.teacher_service import (
    generate_teacher_resource_pdf,
    list_teacher_resources,
)


def _user(*, authenticated: bool = True, role=UserRole.COMMON, user_type=None):
    return SimpleNamespace(
        is_authenticated=authenticated,
        role=role,
        user_type=user_type,
        username="Teacher",
        email="teacher@example.test",
        get_id=lambda: "user-1",
    )


def _walk(component):
    if component is None:
        return
    if isinstance(component, (list, tuple)):
        for item in component:
            yield from _walk(item)
        return
    yield component
    children = getattr(component, "children", None)
    if children is not None:
        yield from _walk(children)


def _ids(component) -> set[str]:
    return {
        item_id
        for item in _walk(component)
        if isinstance((item_id := getattr(item, "id", None)), str)
    }


def _callback(app, name: str):
    return next(
        value["callback"].__wrapped__
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
        and value["callback"].__wrapped__.__name__ == name
    )


@pytest.fixture
def dash_app(monkeypatch):
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    return dash_app_module.create_dash_app()


def test_teacher_space_is_restricted_to_docente_and_admin() -> None:
    assert can_access_docente_material(_user(user_type=UserType.DOCENTE))
    assert can_access_docente_material(_user(role=UserRole.ADMIN))
    assert not can_access_docente_material(_user(user_type=UserType.RRHH))
    assert not can_access_docente_material(_user(user_type=UserType.ONG))
    assert not can_access_docente_material(_user(user_type=UserType.COMUN))
    assert not can_access_docente_material(_user(authenticated=False, user_type=UserType.DOCENTE))


def test_index_only_exposes_teacher_space_to_authorized_profiles(monkeypatch) -> None:
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica_page, "current_user", _user(user_type=UserType.RRHH))
    rrhh_hrefs = {
        getattr(item, "href", None) for item in _walk(didactica_page.build_didactica_layout())
    }
    assert "/es/didactica/docentes" not in rrhh_hrefs

    monkeypatch.setattr(didactica_page, "current_user", _user(user_type=UserType.DOCENTE))
    teacher_hrefs = {
        getattr(item, "href", None) for item in _walk(didactica_page.build_didactica_layout())
    }
    assert "/es/didactica/docentes" in teacher_hrefs

    monkeypatch.setattr(didactica_page, "current_user", _user(role=UserRole.ADMIN))
    admin_hrefs = {
        getattr(item, "href", None) for item in _walk(didactica_page.build_didactica_layout())
    }
    assert "/es/didactica/docentes" in admin_hrefs


def test_public_modules_have_stable_content_and_functional_controls(monkeypatch) -> None:
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica_page, "current_user", _user(authenticated=False))

    terms = list_glossary_terms()
    assert len(terms) == 63
    assert len({term.id for term in terms}) == len(terms)
    assert get_glossary_term("transsexual") is None
    assert {"trans", "trans_man", "trans_woman"} <= {term.id for term in terms}
    assert "gender_identity" in {term.id for term in search_glossary("identidad", language="es")}
    assert all(
        term.category == "rights_legal_protection"
        for term in search_glossary(category="rights_legal_protection")
    )

    assert len(set(new_game_state("guess_term")["order"])) == 5

    assert {"didactica-glossary-search", "didactica-glossary-category"} <= _ids(
        didactica_page.build_dictionary_layout()
    )
    presentations_layout = didactica_page.build_presentations_layout()
    assert {
        "didactica-presentations-list",
        "didactica-presentations-retry",
        "didactica-presentations-state",
    } <= _ids(presentations_layout)

    game_layout = didactica_page.build_games_layout("guess_term")
    assert {"didactica-game-submit", "didactica-game-hint", "didactica-game-next"} <= _ids(
        game_layout
    )
    game_progress = next(
        item
        for item in _walk(game_layout)
        if getattr(item, "id", None) == "didactica-game-progress"
    )
    assert game_progress.value == "1"


def test_teacher_resources_have_metadata_and_generate_in_memory_pdf() -> None:
    resources = list_teacher_resources()
    assert len(resources) >= 3
    assert all(
        resource.level.es
        and resource.duration_minutes
        and resource.objectives
        and resource.instructions.es
        and resource.materials
        and resource.teacher_guide.es
        and resource.formats
        for resource in resources
    )
    payload, filename = generate_teacher_resource_pdf(resources[0].id, "es")
    assert payload.startswith(b"%PDF")
    assert filename.startswith("rainbowlens-datahub-")
    assert filename.endswith("-es.pdf")
    assert "/" not in filename and "\\" not in filename


def test_direct_teacher_resource_download_requires_teacher_permission(
    dash_app, monkeypatch
) -> None:
    view = dash_app.server.view_functions["download_docente_resource_direct"]
    with dash_app.server.test_request_context(
        "/didactica/docentes/descargar/rights_country_comparison"
    ):
        monkeypatch.setattr(
            dash_app_module,
            "current_user",
            _user(authenticated=False, user_type=UserType.DOCENTE),
        )
        with pytest.raises(Forbidden):
            view("rights_country_comparison")

        monkeypatch.setattr(dash_app_module, "current_user", _user(user_type=UserType.RRHH))
        with pytest.raises(Forbidden):
            view("rights_country_comparison")

        monkeypatch.setattr(dash_app_module, "current_user", _user(user_type=UserType.DOCENTE))
        response = view("rights_country_comparison")
        assert response.status_code == 200
        assert response.mimetype == "application/pdf"

        monkeypatch.setattr(dash_app_module, "current_user", _user(role=UserRole.ADMIN))
        admin_response = view("rights_country_comparison")
        assert admin_response.status_code == 200
        assert admin_response.mimetype == "application/pdf"

        monkeypatch.setattr(dash_app_module, "current_user", _user(user_type=UserType.COMUN))
        with pytest.raises(Forbidden):
            view("rights_country_comparison")


def test_teacher_resource_callback_requires_teacher_permission(dash_app, monkeypatch) -> None:
    callback = _callback(dash_app, "download_docente_resource")
    monkeypatch.setattr(didactica_page, "current_user", _user(user_type=UserType.ONG))
    result = callback(1, "rights_country_comparison", "en")
    assert result[0] is no_update
    assert result[1]

    monkeypatch.setattr(didactica_page, "current_user", _user(user_type=UserType.DOCENTE))
    allowed = callback(1, "rights_country_comparison", "en")
    assert allowed[0]["type"] == "application/pdf"
    assert allowed[1] == ""


def test_dictionary_and_guess_game_callbacks_work_in_english(dash_app, monkeypatch) -> None:
    monkeypatch.setattr(didactica_page, "current_user", _user())

    glossary = _callback(dash_app, "filter_glossary")
    cards, count = glossary("genero", "all", "en")
    assert cards and "results" in count

    game = _callback(dash_app, "play_game")
    state = new_game_state("guess_term")
    identifier = state["order"][0]
    monkeypatch.setattr(
        didactica_page, "ctx", SimpleNamespace(triggered_id="didactica-game-submit")
    )
    game_result = game(1, None, None, "en", identifier, state)
    assert game_result[6]["score"] == 1
    assert "Correct answer" in game_result[3]
    assert game_result[9] == "1"


@pytest.mark.parametrize(
    ("query", "language", "expected_term"),
    [
        ("LGTBIfobia", "es", "LGTBIfobia"),
        ("Prácticas de conversión", "es", "Prácticas de conversión"),
        ("Recognition of trans parenthood", "en", "Recognition of trans parenthood"),
    ],
)
def test_dictionary_callback_finds_priority_terms_with_sources(
    dash_app, query: str, language: str, expected_term: str
) -> None:
    glossary = _callback(dash_app, "filter_glossary")

    cards, count = glossary(query, "all", language)
    nodes = list(_walk(cards))

    assert cards
    assert count.startswith("1 ")
    assert any(getattr(node, "children", None) == expected_term for node in nodes)
    assert any(getattr(node, "className", "") == "didactica-glossary-sources" for node in nodes)


def test_guess_game_finishes_after_five_questions_and_restarts(dash_app, monkeypatch) -> None:
    callback = _callback(dash_app, "play_game")
    monkeypatch.setattr(didactica_page, "current_user", _user())
    state = new_game_state("guess_term")
    original_order = list(state["order"])

    for index in range(5):
        monkeypatch.setattr(
            didactica_page,
            "ctx",
            SimpleNamespace(triggered_id="didactica-game-submit"),
        )
        result = callback(1, None, None, "es", state["order"][index], state)
        state = result[6]
        assert result[3] == "Respuesta correcta."
        if index < 4:
            monkeypatch.setattr(
                didactica_page,
                "ctx",
                SimpleNamespace(triggered_id="didactica-game-next"),
            )
            result = callback(None, 1, None, "es", None, state)
            state = result[6]

    assert state["completed"] is True
    assert state["score"] == 5
    assert result[12] == "Jugar de nuevo"
    assert result[13].endswith("is-hidden")

    monkeypatch.setattr(
        didactica_page,
        "ctx",
        SimpleNamespace(triggered_id="didactica-game-next"),
    )
    restarted = callback(None, 1, None, "es", None, state)
    assert restarted[6]["score"] == 0
    assert restarted[6]["index"] == 0
    assert set(restarted[6]["order"]).isdisjoint(original_order)


def test_guess_game_incorrect_feedback_names_only_the_correct_term(dash_app, monkeypatch) -> None:
    callback = _callback(dash_app, "play_game")
    monkeypatch.setattr(didactica_page, "current_user", _user())
    state = new_game_state("guess_term")
    correct_id = state["order"][0]
    wrong_id = next(term.id for term in list_glossary_terms() if term.id != correct_id)
    correct_term = get_glossary_term(correct_id)
    assert correct_term is not None
    monkeypatch.setattr(
        didactica_page,
        "ctx",
        SimpleNamespace(triggered_id="didactica-game-submit"),
    )

    result = callback(1, None, None, "es", wrong_id, state)

    assert result[3] == (f'Respuesta incorrecta. La respuesta correcta era: "{correct_term.term}".')


def test_teacher_routes_redirect_unauthorized_profiles_and_keep_login_destination(
    dash_app, monkeypatch
) -> None:
    display_page = dash_app.callback_map["page-content.children"]["callback"].__wrapped__
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr("app.modules.account.login_page.build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr("app.modules.account.login_page.get_csrf_token", lambda: "csrf")

    teacher = _user(user_type=UserType.DOCENTE)
    monkeypatch.setattr(dash_app_module, "current_user", teacher)
    monkeypatch.setattr(didactica_page, "current_user", teacher)
    monkeypatch.setattr(didactica_page, "list_owned_games", lambda _user: [])
    assert "teacher-activity-list" in _ids(display_page("/es/didactica/docentes", ""))

    changed = _user(user_type=UserType.RRHH)
    monkeypatch.setattr(dash_app_module, "current_user", changed)
    monkeypatch.setattr(didactica_page, "current_user", changed)
    denied = display_page("/es/didactica/docentes", "")
    assert "educator-access-denied-redirect" in _ids(denied)
    assert getattr(denied, "href", "").endswith("?notice=docente_required")

    anonymous = _user(authenticated=False)
    monkeypatch.setattr(dash_app_module, "current_user", anonymous)
    monkeypatch.setattr(didactica_page, "current_user", anonymous)
    login = display_page("/es/didactica/docentes/crear", "?type=guess_term")
    next_input = next(item for item in _walk(login) if getattr(item, "name", None) == "next")
    assert next_input.value == "/es/didactica/docentes/crear?type=guess_term"


def test_games_route_is_public(dash_app, monkeypatch) -> None:
    display_page = dash_app.callback_map["page-content.children"]["callback"].__wrapped__
    monkeypatch.setattr("app.modules.account.login_page.build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr("app.modules.account.login_page.get_csrf_token", lambda: "csrf")
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    anonymous = _user(authenticated=False)
    monkeypatch.setattr(dash_app_module, "current_user", anonymous)
    monkeypatch.setattr(didactica_page, "current_user", anonymous)

    assert "didactica-game-state" in _ids(display_page("/es/didactica/juegos", "?game=guess_term"))

    registered = _user(user_type=UserType.COMUN)
    monkeypatch.setattr(dash_app_module, "current_user", registered)
    monkeypatch.setattr(didactica_page, "current_user", registered)
    assert "didactica-game-state" in _ids(display_page("/es/didactica/juegos", "?game=guess_term"))


def test_teacher_activity_editor_is_vertical_and_offers_exactly_three_engines(
    monkeypatch,
) -> None:
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica_page, "current_user", _user(user_type=UserType.DOCENTE))
    monkeypatch.setattr(didactica_page, "get_ilga_years", lambda: [2026])
    monkeypatch.setattr(didactica_page, "_legal_country_options", lambda _year: [])

    layout = didactica_page.build_activity_editor_layout(initial_game_type="word_search")
    selector = next(
        item for item in _walk(layout) if getattr(item, "id", None) == "teacher-editor-game-type"
    )
    assert selector.value == "word_search"
    assert {option["value"] for option in selector.options} == {
        "guess_term",
        "word_search",
        "legal_ranking",
    }
    ordered_ids = [getattr(item, "id", None) for item in _walk(layout)]
    assert "teacher-editor-selection-mode" not in ordered_ids
    assert "teacher-editor-board-size" not in ordered_ids
    assert ordered_ids.index("teacher-editor-game-type") < ordered_ids.index(
        "teacher-editor-term-ids"
    )
    assert ordered_ids.index("teacher-editor-term-ids") < ordered_ids.index("teacher-editor-title")
    assert ordered_ids.index("teacher-editor-preview") < ordered_ids.index("teacher-editor-save")


def test_teacher_activity_delete_confirmation_drives_the_persistent_callback(
    dash_app, monkeypatch
) -> None:
    monkeypatch.setattr(didactica_page, "current_route_language", lambda: "es")
    card = didactica_page._activity_card(
        {
            "id": "activity-1",
            "public_id": "public-1",
            "game_type": "guess_term",
            "title": "Actividad",
            "status": "draft",
        }
    )
    provider = next(
        item
        for item in _walk(card)
        if getattr(item, "id", None) == {"type": "teacher-activity-delete", "index": "activity-1"}
    )
    child_button = provider.children
    callback = next(
        value
        for value in dash_app.callback_map.values()
        if any(
            input_item["id"] == '{"index":["ALL"],"type":"teacher-activity-delete"}'
            for input_item in value["inputs"]
        )
    )

    assert provider.__class__.__name__ == "ConfirmDialogProvider"
    assert getattr(child_button, "id", None) is None
    assert any(
        input_item["property"] == "submit_n_clicks"
        for input_item in callback["inputs"]
        if "teacher-activity-delete" in input_item["id"]
    )


@pytest.mark.parametrize(
    ("game_type", "expected_store"),
    [
        ("guess_term", "didactica-game-state"),
        ("word_search", "didactica-word-search-state"),
        ("legal_ranking", "didactica-ranking-state"),
    ],
)
def test_custom_activity_preview_mounts_the_existing_game_component_ids(
    monkeypatch, game_type, expected_store
) -> None:
    activity = {
        "id": "activity1",
        "game_type": game_type,
        "title": "Actividad",
        "description": "",
        "instructions": "",
        "teacher_note": "",
        "language": "es",
        "configuration": {},
    }
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica_page, "current_user", _user(user_type=UserType.DOCENTE))
    monkeypatch.setattr(didactica_page, "get_owned_game", lambda _user, _id: activity)
    states = {
        "guess_term": new_game_state("guess_term", rounds=5),
        "word_search": didactica_page.create_word_search_game(seed=4, word_count=6),
        "legal_ranking": {"year": 2026, "items": [], "checked": False},
    }
    monkeypatch.setattr(
        didactica_page, "build_activity_game_state", lambda _activity: states[game_type]
    )

    layout = didactica_page.build_custom_activity_layout("activity1")
    assert expected_store in _ids(layout)


def test_public_activity_route_is_playable_without_authentication(dash_app, monkeypatch) -> None:
    display_page = dash_app.callback_map["page-content.children"]["callback"].__wrapped__
    activity = {
        "id": "internal-id",
        "public_id": "public-share-id",
        "game_type": "guess_term",
        "title": "Actividad compartida",
        "description": "",
        "instructions": "",
        "teacher_note": "",
        "language": "es",
        "configuration": {},
    }
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica_page, "get_public_game", lambda _public_id: activity)
    monkeypatch.setattr(
        didactica_page,
        "build_activity_game_state",
        lambda _activity: new_game_state("guess_term"),
    )
    anonymous = _user(authenticated=False)
    monkeypatch.setattr(dash_app_module, "current_user", anonymous)
    monkeypatch.setattr(didactica_page, "current_user", anonymous)

    layout = display_page("/es/didactica/juegos/actividad/public-share-id", "")

    assert "didactica-game-state" in _ids(layout)
    assert "teacher-editor-save" not in _ids(layout)


def test_teacher_space_css_uses_theme_tokens_and_one_mobile_column() -> None:
    stylesheet = Path("src/app/web/assets/didactica.css").read_text(encoding="utf-8")
    assert ".teacher-activity-editor" in stylesheet
    assert ".teacher-game-type-grid" in stylesheet
    assert "var(--panel-bg)" in stylesheet
    assert "var(--color-text)" in stylesheet
    assert "@media (max-width: 900px)" in stylesheet
    assert "grid-template-columns: 1fr" in stylesheet


def test_ranking_game_callback_checks_and_starts_a_new_round_without_reload(
    dash_app, monkeypatch
) -> None:
    callback = _callback(dash_app, "play_ranking_game")
    monkeypatch.setattr(didactica_page, "current_user", _user())
    state = {
        "game_id": "rank_countries",
        "year": 2026,
        "items": [
            {"country_code": "MT", "country_name": "Malta", "score": 89},
            {"country_code": "ES", "country_name": "Spain", "score": 78},
            {"country_code": "DE", "country_name": "Germany", "score": 69},
            {"country_code": "IT", "country_name": "Italy", "score": 24},
        ],
        "checked": False,
    }
    monkeypatch.setattr(
        didactica_page, "ctx", SimpleNamespace(triggered_id="didactica-ranking-check")
    )

    checked = callback(None, 1, [0, 0, 0, 0], [0, 0, 0, 0], "en", state)

    assert checked[2]["checked"] is True
    assert checked[2]["positions_correct"] == 4
    assert checked[3] is True

    # El servicio entrega una nueva ronda sin recargar la página.
    replacement = {**state, "items": list(reversed(state["items"]))}
    monkeypatch.setattr(
        didactica_page,
        "new_ranking_game",
        lambda **_kwargs: replacement,
    )
    monkeypatch.setattr(
        didactica_page, "ctx", SimpleNamespace(triggered_id="didactica-ranking-new")
    )
    renewed = callback(1, None, [0, 0, 0, 0], [0, 0, 0, 0], "es", checked[2])
    assert renewed[2] == replacement
    assert renewed[3] is False


def test_didactica_callbacks_are_registered_without_duplicate_outputs(dash_app) -> None:
    keys = [key for key in dash_app.callback_map if "didactica" in key]
    assert len(keys) == len(set(keys))
    assert len(keys) >= 6


def test_glossary_catalog_preserves_legacy_sources_and_institutional_provenance() -> None:
    terms = list_glossary_terms()
    unam = [term for term in terms if any(source.name == "UNAM" for source in term.sources)]
    fundeu = [term for term in terms if any(source.name == "FundéuRAE" for source in term.sources)]
    assert len(unam) == 17
    assert len(fundeu) == 3
    assert {
        UNAM_SOURCE_URL,
        FUNDEU_SOURCE_URL,
    } <= {source.url for term in terms for source in term.sources}
    assert all(source.url.startswith("https://") for term in terms for source in term.sources)
    intersex = get_glossary_term("intersex")
    biphobia = get_glossary_term("biphobia")
    bisexual = get_glossary_term("bisexual")
    assert intersex is not None
    assert biphobia is not None
    assert bisexual is not None
    assert {source.name for source in intersex.sources} == {"Council of Europe"}
    assert {source.name for source in biphobia.sources} == {"Boletín Oficial del Estado (BOE)"}
    assert {source.name for source in bisexual.sources} == {"UNAM"}


def test_glossary_is_complete_unique_sorted_and_searches_definitions_without_accents() -> None:
    terms = list_glossary_terms()
    keys = [normalized_term_key(term.term) for term in terms]

    assert list(terms) == search_glossary(language="es")
    assert len(keys) == len(set(keys))
    assert all(term.term and term.definition and term.sources for term in terms)
    assert {term.id for term in search_glossary("orientacion", language="es")} >= {
        "sexual_orientation"
    }
    assert {term.id for term in search_glossary("hate speech", language="en")} == {"hate_speech"}
    assert all(key not in PROHIBITED_TERM_KEYS for key in keys)


@pytest.mark.parametrize("prohibited", ["trasvestido", "TRASVESTIDA", "Travestido/a"])
def test_prohibited_term_cannot_enter_catalog(prohibited: str) -> None:
    invalid = GlossaryTerm(
        id="blocked",
        term=prohibited,
        definition="Definición no permitida.",
        category="gender_expression",
        sources=(GlossarySource("UNAM", UNAM_SOURCE_URL),),
    )

    with pytest.raises(ValueError, match="prohibited_glossary_term"):
        validate_glossary_catalog((invalid,))


def test_dictionary_renders_general_and_per_term_source_links(monkeypatch) -> None:
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    layout = didactica_page.build_dictionary_layout()
    hrefs = {getattr(item, "href", None) for item in _walk(layout)}
    note = next(
        item
        for item in _walk(layout)
        if getattr(item, "className", "") == "didactica-glossary-note"
    )

    assert {UNAM_SOURCE_URL, FUNDEU_SOURCE_URL} <= hrefs
    assert note is not None

    bisexual = get_glossary_term("bisexual")
    assert bisexual is not None
    card = glossary_card(bisexual, "en")
    card_hrefs = {href for item in _walk(card) if (href := getattr(item, "href", None)) is not None}
    assert card_hrefs == {UNAM_SOURCE_URL}
    assert any(
        getattr(item, "children", None) == bisexual.localized_definition("en")
        for item in _walk(card)
    )


def test_guess_game_uses_only_the_glossary_catalog() -> None:
    guess_state = new_game_state("guess_term", rounds=12)
    assert all(get_glossary_term(identifier) for identifier in guess_state["order"])


def test_dictionary_css_keeps_responsive_layout_and_theme_tokens() -> None:
    stylesheet = Path("src/app/web/assets/didactica.css").read_text(encoding="utf-8")
    assert "@media (max-width: 680px)" in stylesheet
    assert ".didactica-glossary-grid" in stylesheet
    assert ".didactica-glossary-sources" in stylesheet
    assert "overflow-wrap: anywhere" in stylesheet
    assert "var(--panel-bg)" in stylesheet
    assert "var(--color-text)" in stylesheet
