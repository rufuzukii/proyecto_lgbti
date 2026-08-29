from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.modules.didactics.page as didactica_page
import app.web.application as dash_app_module
from app.modules.account.users.schemas import UserRole, UserType
from app.modules.didactics.presentation_service import (
    DidacticPresentation,
    DidacticPresentationStorageError,
)
from app.modules.didactics.translations import tr


def _user(
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.COMMON,
    user_type: UserType | None = UserType.COMUN,
):
    return SimpleNamespace(
        is_authenticated=authenticated,
        role=role,
        user_type=user_type,
        get_id=lambda: "user-1" if authenticated else None,
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
        identifier
        for item in _walk(component)
        if isinstance((identifier := getattr(item, "id", None)), str)
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


@pytest.mark.parametrize(
    "user",
    [
        _user(authenticated=False, role=UserRole.ANONYMOUS, user_type=None),
        _user(user_type=UserType.COMUN),
        _user(user_type=UserType.DOCENTE),
        _user(role=UserRole.ADMIN, user_type=UserType.ADMIN),
        _user(user_type=UserType.RRHH),
        _user(user_type=UserType.ONG),
        _user(user_type=UserType.POLITICO),
        _user(user_type=UserType.SOCIOLOGO),
    ],
)
def test_presentations_route_is_public_for_every_profile(dash_app, monkeypatch, user) -> None:
    display_page = dash_app.callback_map["page-content.children"]["callback"].__wrapped__
    monkeypatch.setattr(dash_app_module, "current_user", user)
    monkeypatch.setattr(didactica_page, "current_user", user)
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")

    page = display_page("/es/didactica/presentaciones", "")

    assert "didactica-presentations-list" in _ids(page)
    assert not any(identifier and "login" in identifier for identifier in _ids(page))


def test_library_callback_renders_powerpoint_pdf_and_direct_downloads(
    dash_app, monkeypatch
) -> None:
    presentations = (
        DidacticPresentation(
            name="diversidad.pptx",
            display_name="Diversidad",
            storage_path="es/diversidad.pptx",
            extension=".pptx",
            file_type="PowerPoint",
            size=2_515_000,
            updated_at=datetime(2026, 8, 15, tzinfo=UTC).isoformat(),
            download_url="https://project.supabase.co/storage/diversidad.pptx?download=diversidad.pptx",
        ),
        DidacticPresentation(
            name="guia.pdf",
            display_name="Guia",
            storage_path="guia.pdf",
            extension=".pdf",
            file_type="PDF",
            size=860_000,
            updated_at=None,
            download_url="https://project.supabase.co/storage/guia.pdf?download=guia.pdf",
        ),
    )
    monkeypatch.setattr(
        didactica_page, "list_didactic_presentations", lambda: presentations
    )
    callback = _callback(dash_app, "load_didactic_presentations")

    children, list_class, retry_class, state = callback(1, 0)
    body = str(children)
    links = [item for item in _walk(children) if getattr(item, "href", None)]

    assert "PowerPoint" in body and "PDF" in body
    assert "2,4 MB" in body and "840 KB" in body
    assert list_class.endswith("is-ready")
    assert retry_class.endswith("is-hidden")
    assert state == {"status": "READY", "count": 2}
    assert {item.download for item in links} == {"diversidad.pptx", "guia.pdf"}
    assert all("supabase.co" in item.href for item in links)
    assert all(getattr(item, "aria-label", "").startswith("Descargar ") for item in links)


def test_library_distinguishes_empty_and_error_states(dash_app, monkeypatch) -> None:
    callback = _callback(dash_app, "load_didactic_presentations")
    monkeypatch.setattr(didactica_page, "list_didactic_presentations", lambda: ())

    empty = callback(1, 0)

    assert tr("presentations_empty", "es") in str(empty[0])
    assert empty[3] == {"status": "EMPTY", "count": 0}
    assert empty[2].endswith("is-hidden")

    def fail():
        raise DidacticPresentationStorageError("unavailable")

    monkeypatch.setattr(didactica_page, "list_didactic_presentations", fail)
    error = callback(1, 1)

    assert tr("presentations_error", "es") in str(error[0])
    assert error[3] == {"status": "ERROR", "count": 0}
    assert not error[2].endswith("is-hidden")


def test_presentations_texts_and_styles_are_bilingual_responsive_and_theme_aware(
    monkeypatch,
) -> None:
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    layout = didactica_page.build_presentations_layout()
    body = str(layout)
    css = Path("src/app/web/assets/didactica.css").read_text(encoding="utf-8")

    assert tr("presentations_desc", "es") in body
    assert tr("presentations_desc", "en") in body
    assert tr("presentations_loading", "es") in body
    assert ".didactica-presentation-card" in css
    assert "background: var(--panel-bg);" in css
    assert "border: 1px solid var(--panel-border);" in css
    assert "@media (max-width: 680px)" in css
    mobile = css.split("@media (max-width: 680px)", 1)[1]
    assert ".didactica-presentation-card" in mobile
    assert "grid-template-columns: 1fr;" in mobile
