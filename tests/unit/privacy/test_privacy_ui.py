from __future__ import annotations

from pathlib import Path
from typing import Any

from app.modules.account import privacy_page as privacy
from app.modules.account import profile_page as user_page
from app.modules.account import register_page as register
from app.modules.account.privacy.models import PersonalDataInventory
from app.modules.account.users.schemas import UserRole, UserType
from app.web.i18n import UI_TEXT

ASSETS = Path(__file__).parents[3] / "src" / "app" / "web" / "assets"


def test_registration_contains_bilingual_privacy_information(monkeypatch) -> None:
    monkeypatch.setattr(register, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(register, "get_csrf_token", lambda: "csrf")

    layout = register.build_register_layout()
    rendered = str(layout)

    assert "registration-privacy-information" in rendered
    assert (
        "RainbowLens DataHub utiliza los datos necesarios para gestionar tu cuenta y "
        "ofrecer las funcionalidades solicitadas."
    ) in rendered
    assert (
        "RainbowLens DataHub uses the data required to manage your account"
        in UI_TEXT["registration_privacy_notice"]["en"]
    )
    assert "/es/privacidad" in rendered


class _User:
    is_authenticated = True
    username = "Alex"
    email = "alex@example.test"
    organization = "Rainbow Org"
    role = UserRole.COMMON
    user_type = UserType.DOCENTE

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
    assert (
        "Los informes se construyen en memoria y archivos temporales, no existe un "
        "historial de informes guardado."
    ) in body
    assert "Las contraseñas se almacenan de forma segura mediante hash" in body
    assert "texto plano" in body
    assert privacy.AEPD_RIGHTS_URL in hrefs
    assert "Submit a complaint" not in body
    assert "Presentar una reclamación" not in body
    assert "Copias de seguridad" not in body
    assert "Backups" not in body
    assert "No se utiliza consentimiento" not in body
    assert "Logs de acceso de Render y proveedores" not in body
    assert "pendiente de documentar por el responsable" not in body
    assert "Logs de acceso de Render:" in body
    assert "Política vigente desde:" not in body
    assert "Policy effective from:" not in body


def test_recipients_card_omits_transfer_paragraph_without_configured_location() -> None:
    # Arrange
    config = privacy.PrivacyPolicyConfig(
        controller_name="RainbowLens DataHub",
        contact_email="privacy@example.test",
        policy_effective_date="2026-08-06",
        audit_retention_days=90,
        deletion_job_retention_days=30,
        backup_retention=None,
        access_log_retention=None,
        hosting_location=None,
        postgres_provider=None,
        mongo_provider=None,
        transfer_safeguards=None,
    )

    # Act
    card = privacy._recipients_card(config)
    paragraphs = [item for item in _walk(card) if item.__class__.__name__ == "P"]

    # Assert
    assert paragraphs == []


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
    assert "NIF:" in body
    assert (
        "Disponible para el usuario que acredite su identidad y desee ejercer sus derechos ARCO"
        in body
    )
    assert "NIF/Pasaporte:" not in body
    assert "NIF/Passport:" not in body
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
        "privacy-recipients",
        "privacy-security",
        "privacy-rights",
    } <= ids
    assert "privacy-backups" not in ids


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
            teacher_games=2,
        ),
    )

    # Act
    layout = user_page.build_user_page_layout()
    rendered = str(layout)
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
    assert "Gestiona tu perfil" in rendered
    assert "Manage your profile" in rendered
    assert "Consulta y actualiza los datos de tu cuenta" in rendered
    assert "Review and update your account details" in rendered
    assert "Gestiona tu perfil, utiliza tus herramientas" not in rendered
    assert "Gestiona tu privacidad y tus datos personales." in rendered
    assert "Manage your privacy and personal data." in rendered
    assert "Esta acción no se puede deshacer." in rendered


def test_privacy_assets_cover_persistence_accessibility_themes_and_mobile() -> None:
    javascript = (ASSETS / "js" / "50_privacy.js").read_text(encoding="utf-8")
    css = (ASSETS / "privacy.css").read_text(encoding="utf-8")
    global_css = (ASSETS / "styles.css").read_text(encoding="utf-8")

    assert "rainbowlens-privacy-notice" not in javascript
    assert ".privacy-notice" not in css
    assert "dialog.showModal()" in javascript
    assert "dialog.close()" in javascript
    assert "lastDialogTrigger.focus()" in javascript
    assert "rainbowlens-" in javascript
    assert 'body[data-theme="dark"]' in global_css
    assert "var(--panel-bg)" in css
    assert ":focus-visible" in css
    assert ".privacy-content-grid" in css
    assert ".privacy-controller-details" in css
    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 680px)" in css
    assert ".privacy-dialog::backdrop" in css
    assert ".privacy-config-warning" not in css
    full_width_rule = css.split("#privacy-data,", 1)[1].split("{", 1)[0]
    assert "#privacy-security" in full_width_rule
