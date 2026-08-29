from __future__ import annotations

from types import SimpleNamespace

import app.modules.didactics.page as didactica_page
import app.web.application as dash_app_module
from app.modules.account.users.schemas import UserRole
from app.modules.didactics.glossary_service import get_glossary_term
from app.web.routes import route_path


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


def _callback(app, name: str):
    return next(
        value["callback"].__wrapped__
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
        and value["callback"].__wrapped__.__name__ == name
    )


def test_anonymous_bilingual_word_search_full_game_and_restart(monkeypatch) -> None:
    # Arrange
    anonymous = SimpleNamespace(
        is_authenticated=False,
        role=UserRole.ANONYMOUS,
        user_type=None,
        get_id=lambda: None,
    )
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    monkeypatch.setattr(dash_app_module, "current_user", anonymous)
    monkeypatch.setattr(didactica_page, "current_user", anonymous)
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    app = dash_app_module.create_dash_app()
    display_page = app.callback_map["page-content.children"]["callback"].__wrapped__
    play = _callback(app, "play_word_search")

    # Act: open the public Spanish route and obtain the generated glossary-backed game.
    page = display_page(route_path("word_search", "es"), "")
    store = next(
        item for item in _walk(page) if getattr(item, "id", None) == "didactica-word-search-state"
    )
    state = store.data
    original_game_id = state["game_id"]

    # Assert the visible terms all come from the canonical dictionary.
    assert state["words"]
    assert all(get_glossary_term(word["id"]) is not None for word in state["words"])

    # Act: select every correct word using the same two-tap flow as mouse and touch users.
    for word in state["words"]:
        start = word["start"][0] * state["columns"] + word["start"][1]
        end = word["end"][0] * state["columns"] + word["end"][1]
        monkeypatch.setattr(
            didactica_page,
            "ctx",
            SimpleNamespace(triggered_id={"type": "didactica-word-search-cell", "index": start}),
        )
        state = play(None, [1], "es", state)[5]
        monkeypatch.setattr(
            didactica_page,
            "ctx",
            SimpleNamespace(triggered_id={"type": "didactica-word-search-cell", "index": end}),
        )
        result = play(None, [1], "es", state)
        state = result[5]

    # Assert completion, English translation, and a genuinely new game.
    assert result[3] == "¡Has encontrado todas las palabras!"
    assert len(state["found"]) == len(state["words"])
    monkeypatch.setattr(
        didactica_page,
        "ctx",
        SimpleNamespace(triggered_id="app-language-store"),
    )
    english = play(None, [], "en", state)
    assert english[3] == "You found all the words!"

    monkeypatch.setattr(
        didactica_page,
        "ctx",
        SimpleNamespace(triggered_id="didactica-word-search-new"),
    )
    restarted = play(1, [], "en", state)[5]
    assert restarted["game_id"] != original_game_id
    assert restarted["found"] == []
    assert restarted["grid"] != state["grid"]

    # The English canonical route is public too.
    english_page = display_page(route_path("word_search", "en"), "")
    assert any(
        getattr(item, "id", None) == "didactica-word-search-state" for item in _walk(english_page)
    )
