from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from dash import dcc, html
from dash.development.base_component import Component
from flask_login import current_user

from app.modules.account.privacy.policy import (
    AEPD_RIGHTS_URL,
    PrivacyPolicyConfig,
    get_privacy_policy_config,
)
from app.shared.components.page_structure import build_page_header
from app.web.i18n import (
    attribute_attrs,
    dash_attrs,
    text,
    text_attrs,
    ui_text,
    ui_text_component,
)
from app.web.navigation import build_navbar
from app.web.routes import route_path

_PRIVACY_SECTION_IDS = {
    "privacy_data_collected": "privacy-data",
    "privacy_purposes": "privacy-purposes",
    "privacy_retention": "privacy-retention",
    "privacy_recipients": "privacy-recipients",
    "privacy_security": "privacy-security",
    "privacy_rights": "privacy-rights",
}


def build_privacy_layout() -> Component:
    config = get_privacy_policy_config()
    return html.Div(
        [
            build_navbar(active="privacy"),
            html.Main(
                [
                    build_page_header(
                        eyebrow=text("RGPD · Unión Europea", "GDPR · European Union"),
                        title=ui_text_component("privacy_title"),
                        description=text(
                            "Esta página explica qué información usa realmente RainbowLens DataHub, por qué la necesita y cómo puedes ejercer tus derechos.",
                            "This page explains what information RainbowLens DataHub actually uses, why it is needed and how you can exercise your rights.",
                        ),
                        class_name="privacy-header",
                    ),
                    _privacy_navigation(),
                    _controller_card(config),
                    html.Div(
                        [
                            _data_inventory_card(),
                            _purposes_card(),
                            _retention_card(config),
                            _recipients_card(config),
                            _security_card(),
                            _rights_card(config),
                        ],
                        className="privacy-content-grid",
                    ),
                ],
                className="privacy-page app-page app-page-container",
            ),
        ]
    )


def build_account_deleted_layout() -> Component:
    return html.Div(
        [
            build_navbar(),
            html.Main(
                [
                    html.Section(
                        [
                            html.P(
                                text("Privacidad", "Privacy"),
                                className="privacy-eyebrow",
                            ),
                            html.H1(ui_text_component("privacy_deleted_heading")),
                            html.P(
                                ui_text_component("privacy_account_deleted"),
                                role="status",
                                **dash_attrs({"aria-live": "polite"}),
                            ),
                            dcc.Link(
                                text("Volver al inicio", "Return home"),
                                href=route_path("home"),
                                refresh=False,
                                className="auth-button privacy-home-link",
                            ),
                        ],
                        className="privacy-deleted-card app-surface",
                    )
                ],
                className="privacy-deleted-page app-page app-page-container",
                **dash_attrs({"data-privacy-account-deleted": "true"}),
            ),
        ]
    )


def _privacy_navigation() -> Component:
    links = (
        ("privacy_controller", "#privacy-controller"),
        ("privacy_purposes", "#privacy-purposes"),
        ("privacy_data_collected", "#privacy-data"),
        ("privacy_retention", "#privacy-retention"),
        ("privacy_recipients", "#privacy-recipients"),
        ("privacy_security", "#privacy-security"),
        ("privacy_rights", "#privacy-rights"),
        ("privacy_contact", "#privacy-contact"),
    )
    return html.Nav(
        [
            ui_text_component("privacy_on_this_page", class_name="privacy-toc-title"),
            html.Ul(
                [
                    html.Li(html.A(ui_text_component(label_key), href=href))
                    for label_key, href in links
                ]
            ),
        ],
        className="privacy-toc",
        **dash_attrs(
            {
                "aria-label": ui_text("privacy_on_this_page", "es"),
                **attribute_attrs(
                    "aria-label",
                    ui_text("privacy_on_this_page", "es"),
                    ui_text("privacy_on_this_page", "en"),
                ),
            }
        ),
    )


def _controller_card(config: PrivacyPolicyConfig) -> Component:
    heading_id = "privacy-controller-title"
    return html.Section(
        [
            html.Div(
                [
                    html.P(
                        text("Información identificativa", "Identification details"),
                        className="privacy-card-eyebrow",
                    ),
                    html.H2(ui_text_component("privacy_controller"), id=heading_id),
                ],
                className="privacy-card-heading",
            ),
            html.Dl(
                [
                    _controller_detail(
                        "privacy_controller_name_label",
                        config.controller_name,
                    ),
                    _controller_detail(
                        "privacy_location_label",
                        ui_text_component("privacy_controller_location"),
                    ),
                    _controller_detail(
                        "privacy_identity_document_label",
                        ui_text_component("privacy_identity_document_value"),
                        class_name="privacy-controller-detail--wide",
                    ),
                    _controller_detail(
                        "privacy_contact_email_label",
                        html.A(
                            config.contact_email,
                            href=f"mailto:{config.contact_email}",
                        ),
                        detail_id="privacy-contact",
                    ),
                ],
                className="privacy-controller-details",
            ),
        ],
        id="privacy-controller",
        className="privacy-card privacy-card--controller",
        **dash_attrs({"aria-labelledby": heading_id}),
    )


def _controller_detail(
    label_key: str,
    value: Component | str,
    *,
    class_name: str | None = None,
    detail_id: str | None = None,
) -> Component:
    classes = "privacy-controller-detail"
    if class_name:
        classes = f"{classes} {class_name}"
    attributes: dict[str, Any] = {"className": classes}
    if detail_id:
        attributes["id"] = detail_id
    return html.Div(
        [
            html.Dt(ui_text_component(label_key)),
            html.Dd(children=value),
        ],
        **attributes,
    )


def _data_inventory_card() -> Component:
    return _card(
        "privacy_data_collected",
        [
            _subsection(
                "Datos necesarios para la cuenta",
                "Data required for the account",
                [
                    "nombre visible, correo electrónico, rol y hash de contraseña",
                    "display name, email address, role and password hash",
                    "versión de sesión para invalidar accesos anteriores cuando sea necesario",
                    "session version used to invalidate previous access when necessary",
                    "identificador técnico de usuario y fecha de creación",
                    "technical user identifier and creation date",
                ],
            ),
            _subsection(
                "Datos opcionales",
                "Optional data",
                [
                    "organización indicada en el registro o actualizada por administración",
                    "organisation supplied during registration or updated by an administrator",
                ],
            ),
            _subsection(
                "Contenido creado y actividad",
                "Created content and activity",
                [
                    "juegos docentes privados creados por el usuario",
                    "private educator games created by the user",
                    "cargas pendientes y sus archivos JSON cuando un administrador importa datos",
                    "pending uploads and their JSON payloads when an administrator imports data",
                ],
            ),
            _subsection(
                "Datos técnicos y temporales",
                "Technical and temporary data",
                [
                    "cookie técnica de sesión y registros de seguridad",
                    "technical session cookie and security records",
                    "claves de limitación de intentos derivadas mediante hash y datos de caché",
                    "hashed rate-limit keys and cached data",
                    "logs de acceso del alojamiento, que pueden incluir IP, fecha, ruta, estado, referente y agente de usuario",
                    "hosting access logs, which may include IP, date, route, status, referrer and user agent",
                    "idioma y tema guardados solo en este navegador",
                    "language and theme stored only in this browser",
                ],
            ),
            html.P(
                text(
                    "Los informes se construyen en memoria y archivos temporales, no existe un historial de informes guardado.",
                    "Reports are built in memory and temporary files. No saved report history exists.",
                ),
                className="privacy-fact-note",
            ),
        ],
    )


def _purposes_card() -> Component:
    return _card(
        "privacy_purposes",
        [
            _policy_row(
                "Crear y proteger la cuenta, autenticar al usuario y prestar las funciones solicitadas.",
                "Create and protect the account, authenticate the user and provide requested features.",
                "Ejecución del servicio solicitado.",
                "Performance of the requested service.",
            ),
            _policy_row(
                "Guardar juegos docentes propios y cargas pendientes.",
                "Save owned educator games and pending uploads.",
                "Ejecución del servicio solicitado.",
                "Performance of the requested service.",
            ),
            _policy_row(
                "Prevenir abuso, limitar intentos y conservar trazabilidad de seguridad.",
                "Prevent abuse, limit attempts and retain security traceability.",
                "Interés legítimo en proteger cuentas, datos y servicio, limitado y documentado.",
                "Legitimate interest in protecting accounts, data and the service, limited and documented.",
            ),
        ],
        secondary_key="privacy_legal_basis",
    )


def _retention_card(config: PrivacyPolicyConfig) -> Component:
    return _card(
        "privacy_retention",
        [
            _bullet_list(
                [
                    (
                        "Cuenta, perfil y juegos docentes: mientras la cuenta exista. Se eliminan al completar la solicitud.",
                        "Account, profile and educator games: while the account exists. They are deleted when the request completes.",
                    ),
                    (
                        "Sesión: 12 horas por defecto. Se invalida al cambiar credenciales o eliminar la cuenta.",
                        "Session: 12 hours by default. It is invalidated after credential changes or account deletion.",
                    ),
                    (
                        "Caché: 5 minutos por defecto. Los límites de intentos caducan entre 5 minutos y 1 hora según el flujo.",
                        "Cache: 5 minutes by default. Attempt limits expire between 5 minutes and 1 hour depending on the flow.",
                    ),
                    (
                        f"Auditoría de seguridad: {config.audit_retention_days} días. Al eliminar la cuenta se retira la identidad y queda una referencia irreversible.",
                        f"Security audit: {config.audit_retention_days} days. Account deletion removes identity and leaves an irreversible reference.",
                    ),
                    (
                        "Informes: solo durante la generación. El enlace de contacto abre el cliente de correo del usuario y la aplicación no almacena el mensaje.",
                        "Reports: only during generation. The contact link opens the user's email client and the application does not store the message.",
                    ),
                    (
                        f"Logs de acceso de Render: {config.access_log_retention or 'durante el periodo en que puedan ser conservados por el servicio conforme a su funcionamiento y configuración'}.",
                        f"Render access logs: {config.access_log_retention or 'for the period in which the service may retain them according to its operation and configuration'}.",
                    ),
                ]
            )
        ],
    )


def _recipients_card(config: PrivacyPolicyConfig) -> Component:
    providers = [
        ("Render para alojar la aplicación.", "Render for application hosting."),
        (
            f"PostgreSQL{_provider_suffix(config.postgres_provider)} para cuentas y cargas pendientes.",
            f"PostgreSQL{_provider_suffix(config.postgres_provider)} for accounts and pending uploads.",
        ),
        (
            f"MongoDB{_provider_suffix(config.mongo_provider)} para seguridad, juegos docentes y auditoría.",
            f"MongoDB{_provider_suffix(config.mongo_provider)} for security, educator games and auditing.",
        ),
        (
            "Supabase Storage para figuras de fuentes públicas. Actualmente no recibe archivos personales de cuenta.",
            "Supabase Storage for public-source figures. It currently receives no personal account files.",
        ),
    ]
    children: list[Component] = [_bullet_list(providers)]
    if config.hosting_location:
        children.append(
            html.P(
                text(
                    f"Ubicación configurada: {config.hosting_location}. Garantías: {config.transfer_safeguards or 'deben verificarse en el contrato del proveedor'}.",
                    f"Configured location: {config.hosting_location}. Safeguards: {config.transfer_safeguards or 'must be verified in the provider agreement'}.",
                )
            )
        )
    return _card("privacy_recipients", children)


def _security_card() -> Component:
    return _card(
        "privacy_security",
        [
            html.P(
                text(
                    "Las contraseñas se almacenan de forma segura mediante hash y nunca se guardan en texto plano.",
                    "Passwords are stored securely using password hashing and are never stored in plain text.",
                )
            )
        ],
    )


def _rights_card(config: PrivacyPolicyConfig) -> Component:
    actions: list[Component] = [
        html.P(
            text(
                "Puedes solicitar información, acceso, rectificación, supresión, limitación, portabilidad u oposición, y retirar un consentimiento concreto sin afectar a tratamientos anteriores ni a funciones que no dependan de él.",
                "You can request information, access, rectification, erasure, restriction, portability or objection, and withdraw a specific consent without affecting earlier processing or features that do not depend on it.",
            )
        ),
        html.P(
            [
                text("Escribe a ", "Write to "),
                html.A(config.contact_email, href=f"mailto:{config.contact_email}"),
                text(
                    ". La edición del perfil, la copia de datos y la eliminación son acciones distintas.",
                    ". Profile editing, data export and account deletion are separate actions.",
                ),
            ]
        ),
        html.Div(
            [
                dcc.Link(
                    ui_text_component("privacy_manage_data"),
                    href=route_path("profile"),
                    refresh=False,
                    className="auth-button",
                )
                if current_user.is_authenticated
                else dcc.Link(
                    text("Iniciar sesión", "Sign in"),
                    href=(f"{route_path('login')}?next={route_path('profile')}"),
                    refresh=False,
                    className="auth-button",
                ),
                html.A(
                    text("Conocer tus derechos en la AEPD", "Learn about your rights at the AEPD"),
                    href=AEPD_RIGHTS_URL,
                    target="_blank",
                    rel="noopener noreferrer",
                    className="auth-button auth-button-secondary",
                ),
            ],
            className="privacy-actions",
        ),
    ]
    return _card("privacy_rights", actions)


def _card(
    title_key: str,
    children: Iterable[Component],
    *,
    secondary_key: str | None = None,
) -> Component:
    section_id = _PRIVACY_SECTION_IDS[title_key]
    heading_id = f"{section_id}-title"
    headings: list[Component] = [html.H2(ui_text_component(title_key), id=heading_id)]
    if secondary_key:
        headings.append(html.H3(ui_text_component(secondary_key)))
    return html.Section(
        [*headings, *children],
        id=section_id,
        className="privacy-card",
        **dash_attrs({"aria-labelledby": heading_id}),
    )


def _subsection(title_es: str, title_en: str, items: list[str]) -> Component:
    pairs = list(zip(items[::2], items[1::2], strict=True))
    return html.Div(
        [
            html.H3(title_es, **text_attrs(title_es, title_en)),
            _bullet_list(pairs),
        ],
        className="privacy-subsection",
    )


def _policy_row(purpose_es: str, purpose_en: str, basis_es: str, basis_en: str) -> Component:
    return html.Div(
        [
            html.P(purpose_es, **text_attrs(purpose_es, purpose_en)),
            html.P(
                [html.Strong(text("Base: ", "Basis: ")), text(basis_es, basis_en)],
                className="privacy-basis",
            ),
        ],
        className="privacy-policy-row",
    )


def _bullet_list(items: Iterable[tuple[str, str]]) -> Component:
    return html.Ul([html.Li(es, **text_attrs(es, en)) for es, en in items])


def _provider_suffix(provider: str | None) -> str:
    return f" ({provider})" if provider else ""
