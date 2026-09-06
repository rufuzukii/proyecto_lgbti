from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from urllib.parse import urlsplit

import pytest
from dash import html

from app.web import application
from app.web.routes import (
    ROUTES,
    client_route_config,
    current_route_language,
    equivalent_path,
    route_path,
)


@pytest.fixture(scope="module")
def language_callback():
    registrations = []
    application._register_client_preferences_callbacks(
        cast(Any, SimpleNamespace(clientside_callback=lambda *args: registrations.append(args)))
    )
    assert len(registrations) == 1
    return registrations[0][0]


@pytest.fixture(scope="module")
def run_switch(language_callback):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the actual Dash clientside callback")
    state_source = (Path(application.__file__).parent / "assets" / "js" / "00_state.js").read_text(
        encoding="utf-8"
    )

    def run(path, search, fragment):
        # Execute the registered callback and real language-state helper, not a
        # Python reimplementation of the client navigation logic.
        payload = {
            "callback": language_callback,
            "state": state_source,
            "routes": client_route_config(),
            "path": path,
            "search": search,
            "fragment": fragment,
        }
        result = subprocess.run(
            [node, "-e", _SWITCH_RUNNER],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return json.loads(result.stdout)

    return run


_SWITCH_RUNNER = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const values = new Map([
    ['rainbowlens-language', payload.path.startsWith('/en') ? 'es' : 'en'],
    ['rainbowlens-theme', 'dark'],
    ['unrelated-preference', 'keep-me'],
]);
let appliedLanguage;
const window = {
    localStorage: {
        getItem: key => values.get(key) || null,
        setItem: (key, value) => values.set(key, value),
    },
    dash_clientside: {no_update: 'NO_UPDATE', callback_context: {}},
};
const context = vm.createContext({window});
vm.runInContext(payload.state, context);
window.RainbowLens.i18n = {applyLanguage: value => { appliedLanguage = value; }};
const callback = vm.runInContext('(' + payload.callback + ')', context);
function invoke(trigger, clicks, path) {
    window.dash_clientside.callback_context.triggered = [{prop_id: trigger}];
    const result = callback(1, clicks, path, payload.search, payload.fragment, payload.routes);
    return {result, appliedLanguage, persisted: values.get('rainbowlens-language')};
}
const initial = invoke('app-language-init.n_intervals', 0, payload.path);
const first = invoke('app-language-toggle.n_clicks', 1, payload.path);
const destination = new URL(first.result[1], 'https://example.test').pathname;
const settled = invoke('url.pathname', 1, destination);
const second = invoke('app-language-toggle.n_clicks', 2, destination);
console.log(JSON.stringify({initial, first, settled, second, values: Object.fromEntries(values)}));
"""


@pytest.mark.parametrize("route", ROUTES.values(), ids=ROUTES.keys())
@pytest.mark.parametrize("language", ["es", "en"])
@pytest.mark.parametrize("trailing_slash", ["", "/"])
def test_language_switch_round_trip(run_switch, route, language, trailing_slash):
    _assert_round_trip(run_switch, route.path(language) + trailing_slash, language)


@pytest.mark.parametrize("language", ["es", "en"])
@pytest.mark.parametrize("trailing_slash", ["", "/", "///"])
def test_public_activity_switch_keeps_public_id(run_switch, language, trailing_slash):
    path = ROUTES["educator_public_activity"].path(language) + "/share_ABC-123" + trailing_slash
    _assert_round_trip(run_switch, path, language)


def _assert_round_trip(run_switch, path, language):
    other = "en" if language == "es" else "es"
    search = "?source=fra&year=2024&countries=ES&countries=PT&answer=Yes%20%26%20No"
    fragment = "#page-content"
    result = run_switch(path, search, fragment)
    assert result["initial"]["result"] == [language, "NO_UPDATE"]
    for phase, selected, expected_path in (
        ("first", other, equivalent_path(path, other)),
        ("second", language, equivalent_path(path, language)),
    ):
        step = result[phase]
        assert expected_path is not None
        assert step["result"] == [selected, expected_path + search + fragment]
        assert step["appliedLanguage"] == step["persisted"] == selected
        assert urlsplit(step["result"][1]).netloc == ""
    # Location's follow-up must synchronize the page without another redirect.
    assert result["settled"]["result"] == [other, "NO_UPDATE"]
    assert result["values"]["rainbowlens-theme"] == "dark"
    assert result["values"]["unrelated-preference"] == "keep-me"


@pytest.fixture(scope="module", params=[False, True], ids=["local", "production-proxy"])
def navigation_client(request):
    production = request.param
    config = replace(application.get_app_config(), local_mode=not production)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(application, "get_app_config", lambda: config)
        patch.setattr(application, "initialize_mongo_indexes", lambda: None)
        patch.setattr(application, "migrate_account_security_schema", lambda: None)
        patch.setattr(application, "assert_analytics_databases_available", lambda: None)
        # Isolate data access while exercising Dash's real HTTP callback dispatch
        # and the language context passed to each page builder.
        patch.setattr(
            application,
            "_build_page_for_route",
            lambda route_id, language, params, search: html.Div(
                id="localized-page",
                children=json.dumps(
                    {
                        "route": route_id,
                        "language": language,
                        "context_language": current_route_language(),
                        "path": route_path(route_id),
                        "search": search,
                        "params": params,
                    }
                ),
            ),
        )
        app = application.create_dash_app()
        yield app.server.test_client(), production


@pytest.mark.parametrize("route_id", ["home", "statistics", "trends", "reports"])
@pytest.mark.parametrize("language", ["es", "en"])
def test_switch_destinations_render_without_redirects(navigation_client, route_id, language):
    client, production = navigation_client
    base_url = "https://example.test" if production else "http://localhost"
    headers = {"X-Forwarded-Proto": "https"} if production else {}
    search = "?year=2024&countries=ES&countries=PT"
    path = route_path(route_id, language) + "/"
    with client.session_transaction(base_url=base_url) as session:
        session["navigation-regression"] = "keep-me"
    for selected in (language, "en" if language == "es" else "es", language):
        assert path is not None
        response = client.get(path + search, base_url=base_url, headers=headers)
        assert response.status_code == 200
        assert "Location" not in response.headers
        rendered = client.post(
            "/_dash-update-component",
            base_url=base_url,
            headers={**headers, "Origin": base_url},
            json={
                "output": "page-content.children",
                "outputs": {"id": "page-content", "property": "children"},
                "inputs": [
                    {"id": "url", "property": "pathname", "value": path},
                    {"id": "url", "property": "search", "value": search},
                ],
                "state": [{"id": "statistics-selection", "property": "data", "value": None}],
                "changedPropIds": ["url.pathname"],
            },
        )
        assert rendered.status_code == 200
        content = rendered.get_json()["response"]["page-content"]["children"]
        page = json.loads(content["props"]["children"])
        assert page["route"] == route_id
        assert page["language"] == page["context_language"] == selected
        assert page["path"] == route_path(route_id, selected)
        assert page["search"] == search
        assert page["params"] == {"year": ["2024"], "countries": ["ES", "PT"]}
        path = equivalent_path(path, "en" if selected == "es" else "es")
    with client.session_transaction(base_url=base_url) as session:
        assert session["navigation-regression"] == "keep-me"
