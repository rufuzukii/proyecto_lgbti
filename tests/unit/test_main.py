from __future__ import annotations

from types import SimpleNamespace

from app import main


def test_main_run_uses_configured_server_without_reloader(monkeypatch) -> None:
    config = SimpleNamespace(dash_host="127.0.0.1", dash_port=8050, debug=True)
    calls: list[dict] = []
    app = SimpleNamespace(run=lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(main, "get_app_config", lambda: config)
    monkeypatch.setattr(main, "create_dash_app", lambda: app)

    main.run()

    assert calls == [
        {"host": "127.0.0.1", "port": 8050, "debug": True, "use_reloader": False}
    ]
