from __future__ import annotations

from collections.abc import Iterable

from dash import dcc, html
from dash.development.base_component import Component
from flask_login import current_user

from app.dash.i18n import dash_attrs, text, text_attrs, ui_text_component
from app.dash.layouts.navigation import build_navbar
from app.dash.routes import route_path
from app.privacy.policy import (
    AEPD_COMPLAINT_URL,
    AEPD_RIGHTS_URL,
    PrivacyPolicyConfig,
    get_privacy_policy_config,
)


def build_privacy_layout() -> Component:
    config = get_privacy_policy_config()
    return html.Div(
        [
            build_navbar(active="privacy"),
            html.Main(
                [
                    html.Header(
                        [
                            html.P(
                                text("RGPD · Unión Europea", "GDPR · European Union"),
                                className="privacy-eyebrow",
                            ),
                            html.H1(ui_text_component("privacy_title")),
                            html.P(
                                text(
                                    "Esta página explica qué información usa realmente RainbowLens DataHub, por qué la necesita y cómo puedes ejercer tus derechos.",
                                    "This page explains what information RainbowLens DataHub actually uses, why it is needed and how you can exercise your rights.",
                                ),
                                className="privacy-lead",
                            ),
                            html.P(
                                text(
                                    f"Política vigente desde: {config.policy_effective_date}.",
                                    f"Policy effective from: {config.policy_effective_date}.",
                                ),
                                className="privacy-effective-date",
                            ),
                        ],
                        className="privacy-header",
                    ),
                    _controller_card(config),
                    _data_inventory_card(),
                    _purposes_card(),
                    _retention_card(config),
                    _recipients_card(config),
                    _security_card(),
                    _rights_card(config),
                    _backup_card(config),
                ],
                className="privacy-page app-page-container",
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
                        className="privacy-deleted-card",
                    )
                ],
                className="privacy-deleted-page app-page-container",
                **dash_attrs({"data-privacy-account-deleted": "true"}),
            ),
        ]
    )


def _controller_card(config: PrivacyPolicyConfig) -> Component:
    identity_note: Component | None = None
    if not config.controller_identity_configured:
        identity_note = html.P(
            text(
                "La identidad jurídica del responsable debe completarse en la configuración del despliegue antes de publicar esta política.",
                "The controller's legal identity must be completed in the deployment configuration before this policy is published.",
            ),
            className="privacy-config-warning",
            role="status",
        )
    details: list[Component] = [
        html.P(
            [
                html.Strong(text("Responsable: ", "Controller: ")),
                config.controller_name,
            ]
        ),
        html.P(
            [
                html.Strong(text("Contacto de privacidad: ", "Privacy contact: ")),
                html.A(config.contact_email, href=f"mailto:{config.contact_email}"),
            ]
        ),
    ]
    if config.controller_address:
        details.append(
            html.P(
                [html.Strong(text("Dirección: ", "Address: ")), config.controller_address]
            )
        )
    if identity_note is not None:
        details.append(identity_note)
    return _card("privacy_controller", details)


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
                    "estado de la cuenta, verificación del correo y versión de sesión",
                    "account status, email verification and session version",
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
                    "mensajes, perfil solicitado y adjuntos enviados voluntariamente por correo",
                    "messages, requested profile and attachments voluntarily sent by email",
                ],
            ),
            _subsection(
                "Contenido creado y actividad",
                "Created content and activity",
                [
                    "progreso didáctico, lecciones completadas y mejores puntuaciones",
                    "learning progress, completed lessons and best scores",
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
                    "cookie técnica de sesión, tokens almacenados solo como hash y registros de seguridad",
                    "technical session cookie, tokens stored only as hashes and security records",
                    "claves de limitación de intentos derivadas mediante hash y datos de caché",
                    "hashed rate-limit keys and cached data",
                    "logs de acceso del alojamiento, que pueden incluir IP, fecha, ruta, estado, referente y agente de usuario",
                    "hosting access logs, which may include IP, date, route, status, referrer and user agent",
                    "idioma, tema y versión del aviso aceptado guardados solo en este navegador",
                    "language, theme and accepted notice version stored only in this browser",
                ],
            ),
            html.P(
                text(
                    "Los informes se construyen en memoria y archivos temporales; no existe un historial de informes guardado. Los adjuntos de contacto se envían por SMTP y no se guardan en PostgreSQL, MongoDB ni Supabase. Supabase contiene figuras de informes públicos, no archivos personales de usuarios.",
                    "Reports are built in memory and temporary files; no saved report history exists. Contact attachments are sent by SMTP and are not stored in PostgreSQL, MongoDB or Supabase. Supabase contains figures from public reports, not users' personal files.",
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
                "Guardar progreso didáctico, juegos propios y cargas pendientes.",
                "Save learning progress, owned games and pending uploads.",
                "Ejecución del servicio solicitado.",
                "Performance of the requested service.",
            ),
            _policy_row(
                "Prevenir abuso, limitar intentos y conservar trazabilidad de seguridad.",
                "Prevent abuse, limit attempts and retain security traceability.",
                "Interés legítimo en proteger cuentas, datos y servicio, limitado y documentado.",
                "Legitimate interest in protecting accounts, data and the service, limited and documented.",
            ),
            _policy_row(
                "Enviar una solicitud de rol, mensaje o adjunto opcional al equipo responsable.",
                "Send an optional role request, message or attachment to the responsible team.",
                "Consentimiento mediante el envío voluntario; puede retirarse contactando con el responsable.",
                "Consent through voluntary submission; it can be withdrawn by contacting the controller.",
            ),
            html.P(
                text(
                    "No se utiliza consentimiento para tratamientos necesarios para mantener la cuenta. Si una obligación legal exigiera conservar un dato concreto, se documentaría y limitaría a ese dato y plazo.",
                    "Consent is not used for processing required to maintain the account. If a legal obligation required a specific record to be retained, it would be documented and limited to that data and period.",
                )
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
                        "Cuenta, perfil, progreso y juegos: mientras la cuenta exista; se eliminan al completar la solicitud.",
                        "Account, profile, progress and games: while the account exists; deleted when the request completes.",
                    ),
                    (
                        "Tokens: hasta 24 horas para verificación y 1 hora para recuperación; MongoDB los elimina por caducidad.",
                        "Tokens: up to 24 hours for verification and 1 hour for recovery; MongoDB removes them on expiry.",
                    ),
                    (
                        "Sesión: 12 horas por defecto; se invalida al cambiar credenciales o eliminar la cuenta.",
                        "Session: 12 hours by default; invalidated after credential changes or account deletion.",
                    ),
                    (
                        "Caché: 5 minutos por defecto. Los límites de intentos caducan entre 5 minutos y 1 hora según el flujo.",
                        "Cache: 5 minutes by default. Attempt limits expire between 5 minutes and 1 hour depending on the flow.",
                    ),
                    (
                        f"Auditoría de seguridad: {config.audit_retention_days} días; al eliminar la cuenta se retira la identidad y queda una referencia irreversible.",
                        f"Security audit: {config.audit_retention_days} days; account deletion removes identity and leaves an irreversible reference.",
                    ),
                    (
                        f"Informes: solo durante la generación. Mensajes y adjuntos recibidos: {config.email_retention or 'según la retención del buzón, que el responsable debe configurar'}.",
                        f"Reports: only during generation. Received messages and attachments: {config.email_retention or 'according to mailbox retention, which the controller must configure'}.",
                    ),
                    (
                        f"Logs de acceso de Render y proveedores: {config.access_log_retention or 'durante el plazo del servicio contratado, pendiente de documentar por el responsable'}.",
                        f"Render and provider access logs: {config.access_log_retention or 'for the contracted service period, to be documented by the controller'}.",
                    ),
                ]
            )
        ],
    )


def _recipients_card(config: PrivacyPolicyConfig) -> Component:
    providers = [
        ("Render para alojar la aplicación y Redis.", "Render for application hosting and Redis."),
        (
            f"PostgreSQL{_provider_suffix(config.postgres_provider)} para cuentas y cargas pendientes.",
            f"PostgreSQL{_provider_suffix(config.postgres_provider)} for accounts and pending uploads.",
        ),
        (
            f"MongoDB{_provider_suffix(config.mongo_provider)} para seguridad, progreso, juegos y auditoría.",
            f"MongoDB{_provider_suffix(config.mongo_provider)} for security, progress, games and auditing.",
        ),
        (
            "Supabase Storage para figuras de fuentes públicas; actualmente no recibe archivos personales de cuenta.",
            "Supabase Storage for public-source figures; it currently receives no personal account files.",
        ),
        (
            f"El proveedor SMTP{_provider_suffix(config.email_provider)} para verificación, recuperación y mensajes de contacto.",
            f"The SMTP provider{_provider_suffix(config.email_provider)} for verification, recovery and contact messages.",
        ),
    ]
    transfer = (
        text(
            f"Ubicación configurada: {config.hosting_location}. Garantías: {config.transfer_safeguards or 'deben verificarse en el contrato del proveedor'}.",
            f"Configured location: {config.hosting_location}. Safeguards: {config.transfer_safeguards or 'must be verified in the provider agreement'}.",
        )
        if config.hosting_location
        else text(
            "El código no permite determinar la región contratada ni afirmar una transferencia internacional. El responsable debe documentar la ubicación y las garantías de cada proveedor antes del despliegue.",
            "The code cannot determine the contracted region or establish that an international transfer occurs. The controller must document each provider's location and safeguards before deployment.",
        )
    )
    return _card("privacy_recipients", [_bullet_list(providers), html.P(transfer)])


def _security_card() -> Component:
    return _card(
        "privacy_security",
        [
            html.P(
                text(
                    "Las contraseñas se guardan como hash; los tokens también se almacenan como hash. Las cookies son HttpOnly, SameSite y Secure en producción. Hay CSRF, reautenticación, limitación de intentos, validación en servidor, TLS obligatorio para PostgreSQL y MongoDB en producción, y registros sin contraseñas ni secretos.",
                    "Passwords are stored as hashes and tokens are also hashed. Cookies are HttpOnly, SameSite and Secure in production. The service uses CSRF protection, reauthentication, rate limiting, server-side validation, mandatory TLS for PostgreSQL and MongoDB in production, and logs without passwords or secrets.",
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
                    href=(
                        f"{route_path('login')}?"
                        f"next={route_path('profile')}"
                    ),
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
        html.P(
            [
                text(
                    "Si no recibes una respuesta adecuada, puedes reclamar ante la Agencia Española de Protección de Datos. Antes debes dirigirte al responsable cuando así lo exija el procedimiento.",
                    "If you do not receive an adequate response, you may complain to the Spanish Data Protection Agency. You must first contact the controller where the procedure requires it.",
                ),
                " ",
                html.A(
                    text("Presentar una reclamación", "Submit a complaint"),
                    href=AEPD_COMPLAINT_URL,
                    target="_blank",
                    rel="noopener noreferrer",
                ),
            ]
        ),
    ]
    return _card("privacy_rights", actions)


def _backup_card(config: PrivacyPolicyConfig) -> Component:
    retention = config.backup_retention or "la rotación normal configurada por el operador"
    retention_en = config.backup_retention or "the normal rotation configured by the operator"
    return _card(
        "privacy_backups",
        [
            html.P(
                text(
                    f"Los datos pueden permanecer temporalmente en copias inmutables hasta {retention}. No se modifican copias individuales. Una restauración debe volver a ejecutar las eliminaciones pendientes y nunca reactivar una cuenta eliminada.",
                    f"Data may remain temporarily in immutable backups until {retention_en}. Individual backups are not modified. A restore must re-run pending deletions and must never reactivate a deleted account.",
                )
            )
        ],
    )


def _card(
    title_key: str,
    children: Iterable[Component],
    *,
    secondary_key: str | None = None,
) -> Component:
    headings: list[Component] = [html.H2(ui_text_component(title_key))]
    if secondary_key:
        headings.append(html.H3(ui_text_component(secondary_key)))
    return html.Section([*headings, *children], className="privacy-card")


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
