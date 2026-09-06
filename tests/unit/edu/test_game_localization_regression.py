from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.modules.didactics import page
from app.modules.didactics.glossary_service import list_glossary_terms
from app.web import application
from app.web.routes import localized_route_context, route_path


@pytest.mark.parametrize("language", ["es", "en"])
def test_every_guess_round_answer_and_hint_use_the_dictionary_language(language):
    for term in list_glossary_terms():
        if not term.guess_game:
            continue
        state = {"game_id": "guess_term", "order": [term.id], "index": 0}
        definition, options = page._game_round(state, language)
        assert definition == term.localized_definition(language)
        assert {item["value"] for item in options} >= {term.id}
        assert page._check_game_answer("guess_term", term.id, term.id, language) == (
            True,
            term.localized_term(language),
        )
        assert page._check_game_answer("guess_term", term.id, "wrong", language) == (
            False,
            term.localized_term(language),
        )
        assert f'"{term.localized_term(language)[0].upper()}"' in page._game_hint(
            "guess_term", term.id, language
        )


@pytest.mark.parametrize("language", ["es", "en"])
def test_word_search_initial_board_uses_route_language(monkeypatch, language):
    monkeypatch.setattr(page, "build_navbar", lambda **_: "")
    with localized_route_context(language):
        layout = page.build_word_search_layout(seed=42)

    def walk(node):
        yield node
        children = getattr(node, "children", [])
        for child in children if isinstance(children, list) else [children]:
            if hasattr(child, "to_plotly_json"):
                yield from walk(child)

    store = cast(
        Any, next(n for n in walk(layout) if getattr(n, "id", "") == "didactica-word-search-state")
    )
    catalog = {term.id: term for term in list_glossary_terms()}
    assert len(store.data["words"]) == 8
    for word in store.data["words"]:
        assert word["display"] == catalog[word["id"]].localized_term(language)


@pytest.mark.parametrize("language", ["es", "en"])
@pytest.mark.parametrize("route", ["educators", "educator_create", "educator_activity"])
def test_denied_educator_routes_perform_a_real_navigation(monkeypatch, language, route):
    monkeypatch.setattr(application, "current_user", SimpleNamespace(is_authenticated=True))
    monkeypatch.setattr(application, "can_access_docente_material", lambda _: False)
    with localized_route_context(language):
        result = cast(Any, application._build_page_for_route(route, language, {}, ""))
    assert result.href == route_path("didactica", language) + "?notice=docente_required"
    assert result.refresh is True


@pytest.mark.parametrize("language", ["es", "en"])
def test_games_catalog_alias_navigates_to_learning(language):
    with localized_route_context(language):
        layout = page.build_games_layout()
    redirect = cast(Any, layout).children
    assert redirect.href == route_path("didactica", language)
    assert redirect.refresh is True
