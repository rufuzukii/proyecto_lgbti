from __future__ import annotations

from pathlib import Path
from typing import Any

from app.dash.i18n import UI_TEXT
from app.dash.layouts import user_page
from app.dash.pages import privacy
from app.privacy.models import PersonalDataInventory
from app.users.schemas import UserRole, UserType

ASSETS = Path(__file__).parents[3] / "src" / "app" / "dash" / "assets"


class _User:
    is_authenticated = True
    username = "Alex"
    email = "alex@example.test"
    organization = "Rainbow Org"
    role = UserRole.COMMON
    user_type = UserType.DOCENTE
    email_verified = True

    @staticmethod
    def get_id() -> str:
        return "7bf1c278-4ad4-4cf3-a70d-9769590c5099"


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None:
        yield from _walk(children)


def test_required_privacy_translations_exist_in_both_languages() -> None:
    required = {
        "privacy_title",
        "privacy_data_collected",
        "privacy_purposes",
        "privacy_legal_basis",
        "privacy_retention",
        "privacy_recipients",
        "privacy_rights",
        "privacy_account_deleted",
        "privacy_manage_data",
        "privacy_on_this_page",
        "privacy_contact",
        "privacy_controller_name_label",
        "privacy_location_label",
        "privacy_controller_location",
        "privacy_identity_document_label",
        "privacy_identity_document_value",
        "privacy_contact_email_label",
    }
    assert required <= UI_TEXT.keys()
    assert all(set(UI_TEXT[key]) == {"es", "en"} for key in required)


def test_privacy_page_describes_only_real_stores_and_links_rights(monkeypatch) -> None:
    # Arrange
    monkeypatch.setattr(privacy, "current_user", _User())
    monkeypatch.setattr(privacy, "build_navbar", lambda **_kwargs: "navbar")

    # Act
    layout = privacy.build_privacy_layout()
    body = str(layout.to_plotly_json())
    hrefs = {getattr(item, "href", None) for item in _walk(layout)}

    # Assert
    assert "PostgreSQL" in body
    assert "MongoDB" in body
    assert "Supabase" in body
    assert "no existe un historial de informes guardado" in body
    assert privacy.AEPD_RIGHTS_URL in hrefs
    assert privacy.AEPD_COMPLAINT_URL in hrefs


def test_privacy_controller_is_production_ready_and_bilingual(monkeypatch) -> None:
    # Arrange
    monkeypatch.setattr(privacy, "current_user", _User())
    monkeypatch.setattr(privacy, "build_navbar", lambda **_kwargs: "navbar")

    # Act
    layout = privacy.build_privacy_layout()
    body = str(layout.to_plotly_json())
    ids = {getattr(item, "id", None) for item in _walk(layout)}
    classes = {getattr(item, "className", None) for item in _walk(layout)}

    # Assert
    assert "Málaga, España" in body
    assert "Málaga, Spain" in body
    assert "NIF/Pasaporte:" in body
    assert (
        "Disponible para el usuario que acredite su identidad y desee ejercer sus derechos ARCO"
        in body
    )
    assert "NIF/Passport:" in body
    assert (
        "Available to users who verify their identity and wish to exercise their data protection rights."
        in body
    )
    assert "privacy-config-warning" not in classes
    assert {
        "privacy-controller",
        "privacy-contact",
        "privacy-data",
        "privacy-purposes",
        "privacy-retention",
        "privacy-rights",
    } <= ids


def test_personal_panel_has_export_and_reinforced_deletion_controls(monkeypatch) -> None:
    # Arrange
    monkeypatch.setattr(user_page, "current_user", _User())
    monkeypatch.setattr(user_page, "build_navbar", lambda **_kwargs: "navbar")
    monkeypatch.setattr(user_page, "get_csrf_token", lambda: "csrf-token")
    monkeypatch.setattr(
        user_page,
        "get_personal_data_inventory",
        lambda _user_id: PersonalDataInventory(
            profile=True,
            learning_progress=1,
            teacher_games=2,
        ),
    )

    # Act
    layout = user_page.build_user_page_layout()
    ids = {getattr(item, "id", None) for item in _walk(layout)}
    actions = {getattr(item, "action", None) for item in _walk(layout)}

    # Assert
    assert {
        "privacy-delete-dialog",
        "privacy-delete-email",
        "privacy-delete-password",
        "privacy-delete-phrase",
        "privacy-confirm-checklist",
    } <= ids
    assert {"/privacy/delete-account", "/privacy/export"} <= actions


def test_privacy_assets_cover_persistence_accessibility_themes_and_mobile() -> None:
    javascript = (ASSETS / "js" / "50_privacy.js").read_text(encoding="utf-8")
    css = (ASSETS / "privacy.css").read_text(encoding="utf-8")

    assert 'NOTICE_KEY = "rainbowlens-privacy-notice"' in javascript
    assert "notice.dataset.noticeVersion" in javascript
    assert "dialog.showModal()" in javascript
    assert "dialog.close()" in javascript
    assert "lastDialogTrigger.focus()" in javascript
    assert "rainbowlens-" in javascript
    assert 'body[data-theme="dark"]' in css
    assert ":focus-visible" in css
    assert ".privacy-content-grid" in css
    assert ".privacy-controller-details" in css
    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 680px)" in css
    assert ".privacy-dialog::backdrop" in css
    assert ".privacy-config-warning" not in css
