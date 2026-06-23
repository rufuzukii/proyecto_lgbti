from __future__ import annotations

import base64
import binascii
import logging
from pathlib import Path
from typing import Any

from app.dash.compat import Dash, Input, Output, State, dcc, html
from app.dash.layouts.navigation import build_navbar
from flask_login import current_user

from app.analytics import invalidate_analytics_cache
from ...import_to_db.error_handler import ImportErrorHandler

logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_FILES = 3

DATA_SOURCE_OPTIONS = [
    {"label": "FRA - EU LGBTIQ Survey", "value": "FRA"},
    {"label": "ILGA - Rainbow Map", "value": "ILGA"},
    {"label": "FELGTB - Informes estatales", "value": "FELGTB"},
]


def _decode_upload_contents(contents: str) -> tuple[str, int]:
    data = contents.split(",", 1)[1] if "," in contents else contents
    try:
        payload = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raw_text = data
        return raw_text, len(raw_text.encode("utf-8"))
    return payload.decode("utf-8", errors="replace"), len(payload)


def build_upload_layout() -> html.Div:
    return html.Div(
        [
            build_navbar(active="upload"),
            html.Main(
                [
                    html.Header(
                        [
                            html.P("Reviewable import", className="upload-eyebrow"),
                            html.H1("Upload data for review"),
                            html.P(
                                "Convert CSV or ILGA JSON files into temporary JSON and leave the import pending for administrative validation."
                            ),
                        ],
                        className="page-header upload-header",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Label(
                                        "CSV source",
                                        htmlFor="data-source",
                                        className="upload-label",
                                    ),
                                    dcc.Dropdown(
                                        id="data-source",
                                        options=DATA_SOURCE_OPTIONS,
                                        value="FRA",
                                        clearable=False,
                                        className="upload-dropdown",
                                    ),
                                    html.P(
                                        "Select the source to apply the correct parser before saving JSON in import_logs.",
                                        className="upload-help",
                                    ),
                                ],
                                className="upload-field",
                            ),
                            dcc.Upload(
                                id="upload-csv",
                                children=html.Div(
                                    [
                                        html.Strong("Drag CSV files here"),
                                        html.Span(" or click to select files"),
                                        html.Small(
                                            f"Maximum {MAX_UPLOAD_FILES} files, {MAX_UPLOAD_BYTES // (1024 * 1024)} MB per file."
                                        ),
                                    ],
                                    className="upload-area-content",
                                ),
                                multiple=True,
                                className="upload-area",
                            ),
                            html.Div(
                                [
                                    html.H2("Review flow"),
                                    html.Ol(
                                        [
                                            html.Li("The file is validated and transformed into JSON."),
                                            html.Li(
                                                "The JSON is recorded in PostgreSQL with pending status."
                                            ),
                                            html.Li(
                                                "An administrator reviews and approves it before inserting into MongoDB."
                                            ),
                                        ]
                                    ),
                                ],
                                className="upload-info-card",
                            ),
                            html.Div(
                                id="upload-output",
                                className="upload-output",
                                role="status",
                            ),
                        ],
                        className="page-container upload-container",
                    ),
                ]
            ),
        ]
    )


def register_upload_callbacks(app: Dash) -> None:
    @app.callback(
        Output("upload-output", "children"),
        Input("upload-csv", "contents"),
        State("upload-csv", "filename"),
        State("data-source", "value"),
    )
    def handle_upload(contents, filenames, data_source):
        if not contents:
            return ""
        if not filenames:
            return build_error_message("No file was received.")
        if not data_source:
            return build_error_message("Select the CSV source before uploading.")

        contents_list, filenames_list = normalize_upload_values(contents, filenames)
        if len(contents_list) > MAX_UPLOAD_FILES:
            return build_error_message(f"Maximum {MAX_UPLOAD_FILES} files per upload.")

        imported_files = []
        total_documents = 0

        for data, name in zip(contents_list, filenames_list):
            safe_name = Path(name).name if name else "upload.csv"
            if not is_supported_upload_file(data_source, safe_name):
                return build_error_message(
                    f"Unsupported file: {safe_name}. FRA accepts CSV; ILGA accepts CSV or JSON."
                )

            file_text, payload_size = _decode_upload_contents(data)
            if payload_size > MAX_UPLOAD_BYTES:
                return build_error_message(f"{safe_name} exceeds the allowed size.")

            try:
                payload = parse_file_by_source(
                    source=data_source,
                    file_text=file_text,
                    file_name=safe_name,
                )
            except NotImplementedError as exc:
                return build_error_message(str(exc))
            except Exception:
                logger.exception(
                    "csv_parse_failed",
                    extra={"file": safe_name, "data_source": data_source},
                )
                return build_error_message(f"No se pudo procesar el CSV ({safe_name}).")

            if not payload:
                return build_error_message(
                    f"No data was generated for {safe_name}. Check that the selected source matches the CSV format."
                )

            if data_source == "FRA":
                try:
                    from ...import_to_db.fra import upsert_indicators_from_json

                    upsert_indicators_from_json(payload)
                    invalidate_analytics_cache()
                except Exception:
                    logger.exception(
                        "indicator_upsert_failed",
                        extra={"file": safe_name, "data_source": data_source},
                    )
                    return build_error_message(
                        "No se pudieron guardar los indicadores en PostgreSQL."
                    )

            try:
                from ...import_to_db import register_pending_import

                user_id = current_user.get_id() if current_user.is_authenticated else None
                register_pending_import(file_name=safe_name, file_json=payload, user_id=user_id)
            except Exception as exc:
                logger.exception(
                    "import_log_failed",
                    extra={"file": safe_name, "data_source": data_source},
                )
                error_info = ImportErrorHandler.describe_import_log_error(exc)
                return build_error_message(error_info.title, error_info.details)

            document_count = count_payload_documents(payload)
            total_documents += document_count
            imported_files.append(
                {
                    "name": safe_name,
                    "documents": document_count,
                }
            )

        return build_success_message(
            source=data_source,
            imported_files=imported_files,
            total_documents=total_documents,
        )


def normalize_upload_values(contents: Any, filenames: Any) -> tuple[list[str], list[str]]:
    contents_list = [contents] if isinstance(contents, str) else list(contents)
    filenames_list = [filenames] if isinstance(filenames, str) else list(filenames)
    return contents_list, filenames_list


def is_supported_upload_file(source: str, file_name: str) -> bool:
    suffix = Path(file_name).suffix.lower()
    if source == "ILGA":
        return suffix in {".csv", ".json"}
    return suffix == ".csv"


def parse_file_by_source(source: str, file_text: str, file_name: str) -> dict | list[dict]:
    if source == "FRA":
        from ...import_to_db import parse_fra_csv_text

        return parse_fra_csv_text(file_text, file_name=file_name)
    if source == "ILGA":
        if Path(file_name).suffix.lower() == ".json":
            from ...import_to_db import parse_ilga_json_text

            return parse_ilga_json_text(file_text)
        from ...import_to_db import parse_ilga_csv_text

        return parse_ilga_csv_text(file_text, file_name=file_name)
    if source == "FELGTB":
        raise NotImplementedError(
            "The FELGTB importer is not implemented yet. Select FRA or ILGA for this CSV."
        )
    raise ValueError(f"Unsupported source: {source}")


def count_payload_documents(payload: Any) -> int:
    if isinstance(payload, dict) and isinstance(payload.get("questions"), list):
        from ...import_to_db import count_fra_questions

        return count_fra_questions(payload)
    return len(payload) if isinstance(payload, list) else 1


def build_error_message(message: str, details: list[str] | None = None) -> html.Div:
    children: list[Any] = [
        html.Strong("The import was not completed"),
        html.P(message),
    ]
    if details:
        children.append(
            html.Ul(
                [html.Li(detail) for detail in details],
                className="upload-message-details",
            )
        )

    return html.Div(
        children,
        className="upload-message upload-message-error",
    )


def build_success_message(
    *, source: str, imported_files: list[dict], total_documents: int
) -> html.Div:
    return html.Div(
        [
            html.Strong("Import registered as pending"),
            html.P(
                f"Source: {source}. Generated JSON documents: {total_documents}. An administrator must review the content before inserting it into MongoDB."
            ),
            html.Ul(
                [
                    html.Li(
                        [
                            html.Span(file_info["name"]),
                            html.Em(f"{file_info['documents']} documents"),
                        ]
                    )
                    for file_info in imported_files
                ]
            ),
        ],
        className="upload-message upload-message-success",
    )
