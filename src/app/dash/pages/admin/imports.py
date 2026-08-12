from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from dash import dcc, html
from dash.development.base_component import Component

from app.auth.csrf import get_csrf_token
from app.dash.i18n import dash_attrs, text, text_attrs
from app.dash.layouts.loading_modal import build_loading_modal
from app.dash.layouts.navigation import build_navbar
from app.dash.routes import route_path
from app.import_to_db.import_log import PendingImportLog

STATUS_MESSAGES = {
    "import_inserted": (
        "El contenido se ha aprobado correctamente.",
        "The content was approved successfully.",
    ),
    "import_rejected": (
        "El contenido se ha descartado correctamente.",
        "The content was rejected successfully.",
    ),
}

ERROR_MESSAGES = {
    "access_denied": (
        "No tienes permisos para acceder a esta página.",
        "You do not have permission to access this page.",
    ),
    "csrf": (
        "La sesión ha caducado. Actualiza la página e inténtalo de nuevo.",
        "The session expired. Refresh the page and try again.",
    ),
    "import_not_found": (
        "El contenido seleccionado ya no está pendiente.",
        "The selected content is no longer pending.",
    ),
    "invalid_json_payload": (
        "El contenido no tiene una estructura válida.",
        "The content structure is not valid.",
    ),
    "invalid_ilga_payload": (
        "El contenido legal no tiene la estructura esperada.",
        "The legal content does not have the expected structure.",
    ),
    "invalid_felgtbi_payload": (
        "El contenido estatal no tiene la estructura esperada.",
        "The national content does not have the expected structure.",
    ),
    "unsupported_import_dataset": (
        "La fuente seleccionada no está admitida.",
        "The selected source is not supported.",
    ),
    "mongo": (
        "No ha sido posible aprobar el contenido en este momento. Inténtalo de nuevo más tarde.",
        "The content could not be approved right now. Please try again later.",
    ),
    "storage": (
        "La revisión de archivos no está disponible en este momento.",
        "File review is not available right now.",
    ),
}


def build_admin_imports_layout(
    logs: list[PendingImportLog],
    *,
    status_code: str | None = None,
    error_code: str | None = None,
) -> Component:
    status = STATUS_MESSAGES.get(status_code) if status_code is not None else None
    error = ERROR_MESSAGES.get(error_code) if error_code is not None else None

    return html.Div(
        [
            build_navbar(active="admin"),
            html.Main(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.A(
                                        text("Volver a administración", "Back to administration"),
                                        href=route_path("admin"),
                                        className="profile-back-link admin-imports-back",
                                    ),
                                    html.P(
                                        "Administración",
                                        className="auth-eyebrow",
                                        **text_attrs("Administración", "Administration"),
                                    ),
                                    html.H1(
                                        text("Revisar archivos pendientes", "Review pending files")
                                    ),
                                    html.P(
                                        text(
                                            "Revisa el contenido pendiente agrupado por usuario antes de aprobarlo.",
                                            "Review pending content grouped by user before approving it.",
                                        ),
                                        className="auth-copy",
                                    ),
                                    _message(status, is_error=False),
                                    _message(error, is_error=True),
                                    _build_grouped_imports(logs),
                                ],
                                className="admin-card admin-imports-card",
                            ),
                            *_build_import_modals(logs),
                            build_loading_modal(
                                element_id="admin-import-loading-modal",
                                title=("Cargando datos...", "Loading data..."),
                                description=(
                                    "Estamos importando la información a la base de datos. Este proceso puede tardar unos segundos.",
                                    "We are importing the data into the database. This may take a few seconds.",
                                ),
                            ),
                        ],
                        className="admin-shell",
                    )
                ],
                className="page-shell app-page-container",
            ),
        ]
    )


def _build_grouped_imports(logs: list[PendingImportLog]) -> Component:
    if not logs:
        return html.Div(
            [
                html.H2(text("No hay archivos pendientes", "No pending files")),
                html.P(
                    text(
                        "No hay archivos en espera de revisión.",
                        "There are no files waiting for review.",
                    )
                ),
            ],
            className="admin-empty-state",
        )

    groups: dict[str, list[PendingImportLog]] = defaultdict(list)
    for log in logs:
        groups[log.user_label].append(log)

    return html.Div(
        [_build_user_group(user_label, user_logs) for user_label, user_logs in groups.items()],
        className="admin-import-groups",
    )


def _build_user_group(user_label: str, logs: list[PendingImportLog]) -> Component:
    return html.Section(
        [
            html.Div(
                [
                    html.H2(user_label),
                    html.Span(
                        f"{len(logs)} archivo{'s' if len(logs) != 1 else ''} pendiente{'s' if len(logs) != 1 else ''}",
                        **text_attrs(
                            f"{len(logs)} archivo{'s' if len(logs) != 1 else ''} pendiente{'s' if len(logs) != 1 else ''}",
                            f"{len(logs)} pending file{'s' if len(logs) != 1 else ''}",
                        ),
                    ),
                ],
                className="admin-import-user-header",
            ),
            html.Div([_build_file_link(log) for log in logs], className="admin-import-file-list"),
        ],
        className="admin-import-user-group",
    )


def _build_file_link(log: PendingImportLog) -> Component:
    return html.A(
        [
            html.Strong(log.file_name),
            html.Span(
                log.created_at or "Sin fecha",
                **text_attrs(log.created_at or "Sin fecha", log.created_at or "No date"),
            ),
        ],
        href=f"#{_modal_id(log.id)}",
        className="admin-import-file",
    )


def _build_import_modals(logs: list[PendingImportLog]) -> list[Component]:
    return [_build_import_modal(log) for log in logs]


def _build_import_modal(log: PendingImportLog) -> Component:
    return html.Div(
        [
            html.A(
                "",
                href=route_path("admin_imports"),
                className="admin-import-modal-backdrop",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.P(log.user_label, className="auth-eyebrow"),
                                    html.H2(log.file_name),
                                ],
                                className="admin-import-modal-title",
                            ),
                            html.A(
                                text("Cerrar", "Close"),
                                href=route_path("admin_imports"),
                                className="profile-back-link",
                            ),
                        ],
                        className="admin-import-modal-header",
                    ),
                    _content_preview(log.file_json),
                    html.Form(
                        [
                            dcc.Input(type="hidden", name="csrf_token", value=get_csrf_token()),
                            dcc.Input(type="hidden", name="import_id", value=log.id),
                            html.Button(
                                "Descartar",
                                type="submit",
                                name="action",
                                value="reject",
                                className="admin-action-button admin-delete-button",
                                **text_attrs("Descartar", "Reject"),
                            ),
                            html.Button(
                                "Aprobar",
                                type="submit",
                                name="action",
                                value="insert",
                                className="admin-action-button admin-save-button",
                                **text_attrs("Aprobar", "Approve"),
                            ),
                        ],
                        action="/admin/imports",
                        method="post",
                        className="admin-import-modal-actions",
                        **dash_attrs(
                            {
                                "data-admin-import-form": "true",
                                "data-loading-modal": "admin-import-loading-modal",
                            }
                        ),
                    ),
                ],
                className="admin-import-modal-panel",
            ),
        ],
        id=_modal_id(log.id),
        className="admin-import-modal",
    )


def _modal_id(import_id: str) -> str:
    return f"import-{import_id}"


def _content_preview(content: Any) -> Component:
    return html.Pre(
        json.dumps(content, ensure_ascii=False, indent=2),
        className="admin-json-preview",
    )


def _message(message: tuple[str, str] | None, *, is_error: bool) -> Component | str:
    if not message:
        return ""
    es, en = message
    class_name = (
        "auth-message auth-message-error" if is_error else "auth-message auth-message-success"
    )
    return html.Div(es, className=class_name, role="alert", **text_attrs(es, en))
