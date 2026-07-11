from __future__ import annotations

from collections import defaultdict
import json
from typing import Any

from app.auth.csrf import get_csrf_token
from app.dash.compat import dcc, html
from app.dash.layouts.navigation import build_navbar
from app.import_to_db.import_log import PendingImportLog


STATUS_MESSAGES = {
    "import_inserted": "JSON inserted into MongoDB and removed from the review queue.",
    "import_rejected": "JSON rejected and removed from the review queue.",
}

ERROR_MESSAGES = {
    "access_denied": "You do not have permission to access this page.",
    "csrf": "The session expired. Refresh the page and try again.",
    "import_not_found": "The selected import is no longer pending.",
    "invalid_json_payload": "The JSON must be an object or a non-empty array of objects.",
    "invalid_ilga_payload": "The ILGA JSON does not have the expected annual structure.",
    "invalid_felgtbi_payload": "The FELGTBI+ JSON does not have the expected indicator structure.",
    "unsupported_import_dataset": "The JSON source is not supported.",
    "mongo": "MongoDB insertion failed. The JSON remains pending.",
    "storage": "Pending imports are not available right now.",
}


def build_admin_imports_layout(
    logs: list[PendingImportLog],
    *,
    status_code: str | None = None,
    error_code: str | None = None,
) -> html.Div:
    status = STATUS_MESSAGES.get(status_code)
    error = ERROR_MESSAGES.get(error_code)

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
                                        "Back to admin",
                                        href="/admin",
                                        className="profile-back-link admin-imports-back",
                                    ),
                                    html.P("Administration", className="auth-eyebrow"),
                                    html.H1("Inspect JSON imports"),
                                    html.P(
                                        "Review pending JSON files grouped by user before inserting them into MongoDB.",
                                        className="auth-copy",
                                    ),
                                    _message(status, is_error=False),
                                    _message(error, is_error=True),
                                    _build_grouped_imports(logs),
                                ],
                                className="admin-card admin-imports-card",
                            ),
                            *_build_import_modals(logs),
                        ],
                        className="admin-shell",
                    )
                ],
                className="page-shell",
            ),
        ]
    )


def _build_grouped_imports(logs: list[PendingImportLog]) -> html.Div:
    if not logs:
        return html.Div(
            [
                html.H2("No pending JSON files"),
                html.P("There are no files waiting for administrator review."),
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


def _build_user_group(user_label: str, logs: list[PendingImportLog]) -> html.Section:
    return html.Section(
        [
            html.Div(
                [
                    html.H2(user_label),
                    html.Span(f"{len(logs)} pending file{'s' if len(logs) != 1 else ''}"),
                ],
                className="admin-import-user-header",
            ),
            html.Div([_build_file_link(log) for log in logs], className="admin-import-file-list"),
        ],
        className="admin-import-user-group",
    )


def _build_file_link(log: PendingImportLog) -> html.A:
    return html.A(
        [
            html.Strong(log.file_name),
            html.Span(log.created_at or "No date"),
        ],
        href=f"#{_modal_id(log.id)}",
        className="admin-import-file",
    )


def _build_import_modals(logs: list[PendingImportLog]) -> list[html.Div]:
    return [_build_import_modal(log) for log in logs]


def _build_import_modal(log: PendingImportLog) -> html.Div:
    return html.Div(
        [
            html.A("", href="/admin/imports", className="admin-import-modal-backdrop"),
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
                            html.A("Close", href="/admin/imports", className="profile-back-link"),
                        ],
                        className="admin-import-modal-header",
                    ),
                    html.Pre(
                        json.dumps(log.file_json, ensure_ascii=False, indent=2),
                        className="admin-json-preview",
                    ),
                    html.Form(
                        [
                            dcc.Input(type="hidden", name="csrf_token", value=get_csrf_token()),
                            dcc.Input(type="hidden", name="import_id", value=log.id),
                            html.Button(
                                "Reject",
                                type="submit",
                                name="action",
                                value="reject",
                                className="admin-action-button admin-delete-button",
                            ),
                            html.Button(
                                "Insert",
                                type="submit",
                                name="action",
                                value="insert",
                                className="admin-action-button admin-save-button",
                            ),
                        ],
                        action="/admin/imports",
                        method="post",
                        className="admin-import-modal-actions",
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


def _message(message: str | None, *, is_error: bool) -> html.Div | str:
    if not message:
        return ""
    class_name = "auth-message auth-message-error" if is_error else "auth-message auth-message-success"
    return html.Div(message, className=class_name, role="alert")
