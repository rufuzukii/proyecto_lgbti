from __future__ import annotations

from types import SimpleNamespace

import pytest
from dash import no_update
from werkzeug.exceptions import Forbidden

import app.dash.pages.didactica as didactica_page
import app.dash_app as dash_app_module
from app.auth.permissions import can_access_docente_material
from app.edu import progress_service
from app.edu.game_service import new_game_state
from app.edu.glossary_service import list_glossary_terms, search_glossary
from app.edu.lesson_service import list_lessons
from app.edu.teacher_service import generate_teacher_resource_pdf, list_teacher_resources
from app.users.schemas import UserRole, UserType


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


def test_teacher_permission_is_explicit_and_admin_inherits_all_roles() -> None:
    assert can_access_docente_material(_user(user_type=UserType.DOCENTE))
    assert not can_access_docente_material(_user(user_type=UserType.RRHH))
    assert not can_access_docente_material(_user(user_type=UserType.ONG))
    assert not can_access_docente_material(_user(user_type=UserType.COMUN))
    assert can_access_docente_material(_user(role=UserRole.ADMIN))
    assert not can_access_docente_material(_user(authenticated=False, user_type=UserType.DOCENTE))


def test_index_only_exposes_teacher_card_to_teachers_and_admin(monkeypatch) -> None:
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica_page, "current_user", _user(user_type=UserType.RRHH))
    denied_hrefs = {
        getattr(item, "href", None) for item in _walk(didactica_page.build_didactica_layout())
    }
    assert "/didactica/docentes" not in denied_hrefs

    monkeypatch.setattr(didactica_page, "current_user", _user(user_type=UserType.DOCENTE))
    teacher_hrefs = {
        getattr(item, "href", None) for item in _walk(didactica_page.build_didactica_layout())
    }
    assert "/didactica/docentes" in teacher_hrefs

    monkeypatch.setattr(didactica_page, "current_user", _user(role=UserRole.ADMIN))
    admin_hrefs = {
        getattr(item, "href", None) for item in _walk(didactica_page.build_didactica_layout())
    }
    assert "/didactica/docentes" in admin_hrefs


def test_public_modules_have_stable_content_and_functional_controls(monkeypatch) -> None:
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica_page, "current_user", _user(authenticated=False))

    terms = list_glossary_terms()
    assert len(terms) >= 10
    assert len({term.id for term in terms}) == len(terms)
    assert "gender_identity" in {term.id for term in search_glossary("identidad", language="es")}
    assert all(term.category == "rights" for term in search_glossary(category="rights"))

    lessons = list_lessons()
    assert {lesson.id for lesson in lessons} >= {
        "lgbtiq_basics",
        "european_rights",
        "reading_statistics",
        "law_vs_experience",
    }
    assert all(lesson.slides and lesson.activity and lesson.sources for lesson in lessons)
    assert len(set(new_game_state("guess_term")["order"])) == 5
    assert len(set(new_game_state("true_false")["order"])) == 5

    assert {"didactica-glossary-search", "didactica-glossary-category"} <= _ids(
        didactica_page.build_dictionary_layout()
    )
    lesson_layout = didactica_page.build_presentations_layout("lgbtiq_basics")
    assert {"didactica-lesson-next", "didactica-lesson-finish"} <= _ids(lesson_layout)
    lesson_progress = next(
        item
        for item in _walk(lesson_layout)
        if getattr(item, "id", None) == "didactica-lesson-progress"
    )
    assert lesson_progress.value == "1"

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
    assert len(resources) >= 4
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
    assert filename.startswith("rainbowlens-")
    assert filename.endswith("-es.pdf")
    assert "/" not in filename and "\\" not in filename


def test_direct_download_requires_teacher_and_rechecks_changed_type(dash_app, monkeypatch) -> None:
    view = dash_app.server.view_functions["download_docente_resource_direct"]
    with dash_app.server.test_request_context(
        "/didactica/docentes/descargar/rights_country_comparison"
    ):
        monkeypatch.setattr(
            dash_app_module,
            "current_user",
            _user(authenticated=False, user_type=UserType.DOCENTE),
        )
        response = view("rights_country_comparison")
        assert response.status_code == 302
        assert "/login?next=%2Fdidactica%2Fdocentes" in response.location

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


def test_teacher_callback_rejects_direct_invocation_without_permission(
    dash_app, monkeypatch
) -> None:
    callback = _callback(dash_app, "download_docente_resource")
    monkeypatch.setattr(didactica_page, "current_user", _user(user_type=UserType.ONG))
    result = callback(1, "rights_country_comparison", "en")
    assert result[0] is no_update
    assert "not allowed" in result[1]


def test_dictionary_lesson_and_both_games_callbacks_work_in_english(dash_app, monkeypatch) -> None:
    monkeypatch.setattr(didactica_page, "current_user", _user())

    glossary = _callback(dash_app, "filter_glossary")
    cards, count = glossary("gender", "all", "en")
    assert cards and "results" in count

    lesson = _callback(dash_app, "navigate_lesson")
    monkeypatch.setattr(
        didactica_page, "ctx", SimpleNamespace(triggered_id="didactica-lesson-next")
    )
    lesson_result = lesson(None, 1, None, "en", None, "lgbtiq_basics", 0)
    assert lesson_result[1] == 1
    assert lesson_result[4] == "2"

    game = _callback(dash_app, "play_game")
    for game_id in ("guess_term", "true_false"):
        state = new_game_state(game_id)
        identifier = state["order"][0]
        if game_id == "guess_term":
            selected = identifier
        else:
            from app.edu.game_service import true_false_question

            selected = str(true_false_question(identifier)["answer"]).lower()
        monkeypatch.setattr(
            didactica_page, "ctx", SimpleNamespace(triggered_id="didactica-game-submit")
        )
        game_result = game(1, None, None, "en", selected, state)
        assert game_result[6]["score"] == 1
        assert "Correct answer" in game_result[3]
        assert game_result[9] == "1"


def test_progress_is_stored_as_summary_not_individual_answers(monkeypatch) -> None:
    class Collection:
        def __init__(self):
            self.updates = []

        def update_one(self, query, update, *, upsert):
            self.updates.append((query, update, upsert))

    collection = Collection()
    monkeypatch.setattr(progress_service, "get_mongo_collection", lambda _name: collection)
    progress_service.complete_lesson("user-1", "lgbtiq_basics")
    progress_service.save_game_score("user-1", "guess_term", 4)

    assert collection.updates[0][1]["$addToSet"] == {"completed_lessons": "lgbtiq_basics"}
    assert collection.updates[1][1]["$max"] == {"game_scores.guess_term": 4}
    assert all("answers" not in str(update) for _, update, _ in collection.updates)


def test_direct_teacher_page_is_denied_after_role_change(dash_app, monkeypatch) -> None:
    display_page = dash_app.callback_map["page-content.children"]["callback"].__wrapped__
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")

    teacher = _user(user_type=UserType.DOCENTE)
    monkeypatch.setattr(dash_app_module, "current_user", teacher)
    monkeypatch.setattr(didactica_page, "current_user", teacher)
    assert "didactica-docente-select" in _ids(display_page("/didactica/docentes", ""))

    changed = _user(user_type=UserType.RRHH)
    monkeypatch.setattr(dash_app_module, "current_user", changed)
    monkeypatch.setattr(didactica_page, "current_user", changed)
    denied = display_page("/didactica/docentes", "")
    assert "didactica-docente-select" not in _ids(denied)


def test_games_route_and_callback_require_authenticated_general_access(dash_app, monkeypatch) -> None:
    display_page = dash_app.callback_map["page-content.children"]["callback"].__wrapped__
    monkeypatch.setattr("app.dash.pages.session.login.build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr("app.dash.pages.session.login.get_csrf_token", lambda: "csrf")
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    anonymous = _user(authenticated=False)
    monkeypatch.setattr(dash_app_module, "current_user", anonymous)
    monkeypatch.setattr(didactica_page, "current_user", anonymous)

    assert "login-email" in _ids(display_page("/didactica/juegos", "?game=guess_term"))
    state = new_game_state("guess_term")
    result = _callback(dash_app, "play_game")(1, None, None, "es", None, state)
    assert all(value is no_update for value in result)

    registered = _user(user_type=UserType.COMUN)
    monkeypatch.setattr(dash_app_module, "current_user", registered)
    monkeypatch.setattr(didactica_page, "current_user", registered)
    assert "didactica-game-state" in _ids(
        display_page("/didactica/juegos", "?game=guess_term")
    )


def test_didactica_callbacks_are_registered_without_duplicate_outputs(dash_app) -> None:
    keys = [key for key in dash_app.callback_map if "didactica" in key]
    assert len(keys) == len(set(keys))
    assert len(keys) >= 6
