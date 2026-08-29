from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.web import application as dash_app_module
from app.web import navigation
from app.web.routes import (
    LEGACY_REDIRECTS,
    ROUTES,
    canonical_safe_next,
    equivalent_path,
    is_safe_next,
    localized_route_context,
    match_route,
    route_path,
)
from app.web.section_navigation import PRIMARY_SECTIONS

EXPECTED_ROUTES = {
    "home": ("/es", "/en"),
    "statistics": ("/es/estadisticas", "/en/statistics"),
    "trends": ("/es/tendencias", "/en/trends"),
    "spain": ("/es/espana", "/en/spain"),
    "didactica": ("/es/didactica", "/en/learning"),
    "about": ("/es/acerca-de", "/en/about"),
    "reports": ("/es/informe", "/en/report"),
    "privacy": ("/es/privacidad", "/en/privacy"),
    "profile": ("/es/perfil", "/en/profile"),
}


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


def test_route_table_uses_stable_ids_and_unique_localized_paths() -> None:
    paths: list[str] = []
    for route_id, (spanish, english) in EXPECTED_ROUTES.items():
        assert route_path(route_id, "es") == spanish
        assert route_path(route_id, "en") == english
        assert match_route(spanish).route_id == route_id  # type: ignore[union-attr]
        assert match_route(english).route_id == route_id  # type: ignore[union-attr]
        assert equivalent_path(spanish, "en") == english
        assert equivalent_path(english, "es") == spanish
    for route in ROUTES.values():
        paths.extend((route.es, route.en))
    assert len(paths) == len(set(paths))
    assert [section.key for section in PRIMARY_SECTIONS] == [
        "home",
        "statistics",
        "trends",
        "spain",
        "didactica",
        "about",
    ]


def test_mixed_and_historical_paths_have_one_canonical_destination() -> None:
    assert LEGACY_REDIRECTS["/statistics"] == "/en/statistics"
    assert LEGACY_REDIRECTS["/estadisticas"] == "/es/estadisticas"
    assert LEGACY_REDIRECTS["/es/statistics"] == "/es/estadisticas"
    assert LEGACY_REDIRECTS["/en/estadisticas"] == "/en/statistics"
    assert LEGACY_REDIRECTS["/es/about"] == "/es/acerca-de"
    assert LEGACY_REDIRECTS["/en/acerca-de"] == "/en/about"
    assert LEGACY_REDIRECTS["/es/login"] == "/es/iniciar-sesion"
    assert LEGACY_REDIRECTS["/en/user"] == "/en/profile"
    public_es = match_route("/es/didactica/juegos/actividad/share_ABC-123")
    assert public_es is not None
    assert public_es.route_id == "educator_public_activity"
    assert public_es.public_id == "share_ABC-123"
    assert equivalent_path(public_es.path, "en") == (
        "/en/learning/games/activity/share_ABC-123"
    )


def test_safe_next_only_accepts_registered_local_pages() -> None:
    assert is_safe_next("/es/informe?source=fra")
    assert is_safe_next("/en/report?source=fra")
    assert not is_safe_next("https://attacker.example/es/informe")
    assert not is_safe_next("//attacker.example/path")
    assert not is_safe_next("/api/users")
    assert is_safe_next("/statistics")
    assert canonical_safe_next("/statistics") == "/en/statistics"


def test_navbar_paths_follow_the_active_route_context(monkeypatch) -> None:
    monkeypatch.setattr(
        navigation,
        "current_user",
        SimpleNamespace(is_authenticated=False, role="anonymous"),
    )
    with localized_route_context("en"):
        navbar = navigation.build_navbar(active="about")
    hrefs = [item.href for item in _walk(navbar) if getattr(item, "href", None)]
    assert "/en/statistics" in hrefs
    assert "/en/trends" in hrefs
    assert "/en/spain" in hrefs
    assert "/en/learning" in hrefs
    assert "/en/about" in hrefs
    assert "/en/sign-in" in hrefs


def test_http_redirects_preserve_query_and_404_infers_language(monkeypatch) -> None:
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    app = dash_app_module.create_dash_app()
    client = app.server.test_client()

    redirect_response = client.get("/es/statistics?year=2024", follow_redirects=False)
    assert redirect_response.status_code == 302
    assert redirect_response.headers["Location"].endswith("/es/estadisticas?year=2024")

    for path in ("/es/estadisticas", "/en/statistics", "/es/acerca-de", "/en/about"):
        assert client.get(path).status_code == 200

    not_found_es = client.get("/es/no-existe")
    not_found_en = client.get("/en/not-found-example")
    assert not_found_es.status_code == not_found_en.status_code == 404
    assert 'lang="es"' in not_found_es.get_data(as_text=True)
    assert "Página no encontrada" in not_found_es.get_data(as_text=True)
    assert 'lang="en"' in not_found_en.get_data(as_text=True)
    assert "Page not found" in not_found_en.get_data(as_text=True)


def test_language_switch_client_preserves_query_and_hash() -> None:
    source = dash_app_module._register_client_preferences_callbacks.__code__
    assert source is not None
    module_source = Path(dash_app_module.__file__).read_text(encoding="utf-8")
    assert 'route[selected] + dynamicSuffix + (search || "") + (hash || "")' in module_source
    assert 'Output("url", "href")' in module_source
    assert "document.title" in (
        Path(dash_app_module.__file__).parent / "assets" / "js" / "10_i18n.js"
    ).read_text(encoding="utf-8")
