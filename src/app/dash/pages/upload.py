from __future__ import annotations

import base64
import binascii
import logging
from pathlib import Path
from typing import Any

from app.dash.compat import Dash, Input, Output, PreventUpdate, State, dcc, html
from app.dash.i18n import text, text_attrs
from app.dash.layouts.loading_modal import build_loading_modal
from app.dash.layouts.navigation import build_navbar
from flask_login import current_user

from app.analytics import invalidate_analytics_cache
from ...import_to_db.error_handler import ImportErrorHandler

logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_UPLOAD_FILES = 3

DATA_SOURCE_OPTIONS = [
    {"label": "Encuesta europea LGBTIQ+", "value": "FRA"},
    {"label": "Mapa legal europeo", "value": "ILGA"},
    {"label": "Estado LGTBI+ en España", "value": "FELGTB"},
]


def _decode_upload_payload(contents: str) -> tuple[bytes, int]:
    data = contents.split(",", 1)[1] if "," in contents else contents
    try:
        payload = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        payload = data.encode("utf-8")
    return payload, len(payload)


def build_upload_layout() -> html.Div:
    return html.Div(
        [
            build_navbar(active="upload"),
            html.Main(
                [
                    html.Header(
                        [
                            html.P("Revisión de datos", className="upload-eyebrow", **text_attrs("Revisión de datos", "Data review")),
                            html.H1(text("Subir archivo para revisión", "Upload file for review")),
                            html.P(
                                text(
                                    "Sube archivos de fuentes oficiales para que una persona administradora revise el contenido antes de incorporarlo a la aplicación.",
                                    "Upload files from official sources so an administrator can review the content before adding it to the application.",
                                )
                            ),
                        ],
                        className="page-header upload-header",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Label(
                                        "Fuente de datos",
                                        htmlFor="data-source",
                                        className="upload-label",
                                        **text_attrs("Fuente de datos", "Data source"),
                                    ),
                                    dcc.Dropdown(
                                        id="data-source",
                                        options=DATA_SOURCE_OPTIONS,
                                        value="FRA",
                                        clearable=False,
                                        className="upload-dropdown",
                                    ),
                                    html.P(
                                        text(
                                            "Selecciona la fuente correspondiente al archivo que vas a subir.",
                                            "Select the source that matches the file you are uploading.",
                                        ),
                                        className="upload-help",
                                    ),
                                ],
                                className="upload-field",
                            ),
                            dcc.Upload(
                                id="upload-csv",
                                children=html.Div(
                                    [
                                        html.Strong("Arrastra archivos aquí", **text_attrs("Arrastra archivos aquí", "Drag files here")),
                                        html.Span(" o haz clic para seleccionarlos", **text_attrs(" o haz clic para seleccionarlos", " or click to select files")),
                                        html.Small(
                                            f"Máximo {MAX_UPLOAD_FILES} archivos, {MAX_UPLOAD_BYTES // (1024 * 1024)} MB por archivo.",
                                            **text_attrs(
                                                f"Máximo {MAX_UPLOAD_FILES} archivos, {MAX_UPLOAD_BYTES // (1024 * 1024)} MB por archivo.",
                                                f"Maximum {MAX_UPLOAD_FILES} files, {MAX_UPLOAD_BYTES // (1024 * 1024)} MB per file.",
                                            ),
                                        ),
                                    ],
                                    className="upload-area-content",
                                ),
                                multiple=True,
                                className="upload-area",
                                className_disabled="upload-area upload-area-disabled",
                            ),
                            html.Div(
                                [
                                    html.H2(text("Proceso de revisión", "Review process")),
                                    html.Ol(
                                        [
                                            html.Li("El archivo se valida y prepara para su revisión.", **text_attrs("El archivo se valida y prepara para su revisión.", "The file is validated and prepared for review.")),
                                            html.Li(
                                                "El contenido queda pendiente de aprobación.",
                                                **text_attrs("El contenido queda pendiente de aprobación.", "The content remains pending approval."),
                                            ),
                                            html.Li(
                                                "Una persona administradora lo revisa antes de incorporarlo a la aplicación.",
                                                **text_attrs(
                                                    "Una persona administradora lo revisa antes de incorporarlo a la aplicación.",
                                                    "An administrator reviews it before adding it to the application.",
                                                ),
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
                            build_loading_modal(
                                element_id="upload-loading-modal",
                                title=("Subiendo archivos...", "Uploading files..."),
                                description=(
                                    "Estamos procesando los archivos. Este proceso puede tardar unos segundos.",
                                    "We are processing your files. This may take a few seconds.",
                                ),
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
        Output("upload-csv", "contents"),
        Output("upload-csv", "filename"),
        Output("upload-csv", "last_modified"),
        Input("upload-csv", "contents"),
        State("upload-csv", "filename"),
        State("data-source", "value"),
        prevent_initial_call=True,
        running=[
            (
                Output("upload-loading-modal", "className"),
                "upload-loading-overlay",
                "upload-loading-overlay is-hidden",
            ),
            (Output("upload-csv", "disabled"), True, False),
        ],
    )
    def handle_upload(contents, filenames, data_source):
        if not contents:
            raise PreventUpdate
        try:
            result = _process_upload(contents, filenames, data_source)
        except Exception:
            logger.exception("upload_unexpected_failed", extra={"data_source": data_source})
            result = build_error_message(
                (
                    "No ha sido posible completar la subida. Inténtalo de nuevo más tarde.",
                    "The upload could not be completed. Please try again later.",
                )
            )
        return result, None, None, None

    @app.callback(
        Output("upload-output", "children", allow_duplicate=True),
        Output("upload-csv", "contents", allow_duplicate=True),
        Output("upload-csv", "filename", allow_duplicate=True),
        Output("upload-csv", "last_modified", allow_duplicate=True),
        Input("upload-error-close", "n_clicks"),
        Input("upload-error-retry", "n_clicks"),
        prevent_initial_call=True,
    )
    def dismiss_upload_error(close_clicks: int | None, retry_clicks: int | None):
        if not close_clicks and not retry_clicks:
            raise PreventUpdate
        return "", None, None, None


def _process_upload(contents, filenames, data_source):
        if not filenames:
            return build_error_message(("No se ha recibido ningún archivo.", "No file was received."))
        if not data_source:
            return build_error_message(("Selecciona una fuente antes de subir el archivo.", "Select the data source before uploading."))

        contents_list, filenames_list = normalize_upload_values(contents, filenames)
        if len(contents_list) > MAX_UPLOAD_FILES:
            return build_error_message((f"Puedes subir un máximo de {MAX_UPLOAD_FILES} archivos cada vez.", f"Maximum {MAX_UPLOAD_FILES} files per upload."))

        imported_files = []
        total_documents = 0

        for data, name in zip(contents_list, filenames_list):
            safe_name = Path(name).name if name else "upload.csv"
            if not is_supported_upload_file(data_source, safe_name):
                return build_error_message(
                    (
                        "El archivo seleccionado no corresponde con la fuente de datos elegida. Comprueba el archivo o selecciona otra fuente e inténtalo de nuevo.",
                        "The selected file does not match the chosen data source. Check the file or select another source and try again.",
                    )
                )

            payload_bytes, payload_size = _decode_upload_payload(data)
            if payload_size > MAX_UPLOAD_BYTES:
                return build_error_message((f"El archivo {safe_name} supera el tamaño permitido.", f"{safe_name} exceeds the allowed size."))

            try:
                payload = parse_file_by_source(
                    source=data_source,
                    file_bytes=payload_bytes,
                    file_name=safe_name,
                )
            except NotImplementedError:
                return build_error_message(
                    (
                        "El formato seleccionado no está disponible en este momento.",
                        "The selected format is not available right now.",
                    )
                )
            except RuntimeError as exc:
                if str(exc) == "missing_pdf_dependency":
                    return build_error_message(
                        (
                            "No ha sido posible procesar este archivo en este momento. Inténtalo de nuevo más tarde.",
                            "This file could not be processed right now. Please try again later.",
                        )
                    )
                raise
            except Exception:
                logger.exception(
                    "file_parse_failed",
                    extra={"file": safe_name, "data_source": data_source},
                )
                return build_error_message((f"No se ha podido procesar el archivo {safe_name}.", f"The file {safe_name} could not be processed."))

            if not payload:
                return build_error_message(
                    (
                        f"No se ha encontrado información válida en {safe_name}. Comprueba que la fuente seleccionada corresponde al archivo.",
                        f"No valid information was found in {safe_name}. Check that the selected source matches the file.",
                    )
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
                        (
                            "No ha sido posible guardar la información en este momento. Inténtalo de nuevo más tarde.",
                            "The information could not be saved right now. Please try again later.",
                        )
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
                return build_error_message(
                    (
                        error_info.title,
                        "The file could not be saved for review. Please try again later.",
                    )
                )

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
    if source == "FELGTB":
        return suffix == ".pdf"
    return suffix == ".csv"


def parse_file_by_source(source: str, file_bytes: bytes, file_name: str) -> dict | list[dict]:
    if source == "FRA":
        from ...import_to_db import parse_fra_csv_text

        file_text = file_bytes.decode("utf-8", errors="replace")
        return parse_fra_csv_text(file_text, file_name=file_name)
    if source == "ILGA":
        file_text = file_bytes.decode("utf-8", errors="replace")
        if Path(file_name).suffix.lower() == ".json":
            from ...import_to_db import parse_ilga_json_text

            return parse_ilga_json_text(file_text)
        from ...import_to_db import parse_ilga_csv_text

        return parse_ilga_csv_text(file_text, file_name=file_name)
    if source == "FELGTB":
        from ...import_to_db import parse_felgtbi_pdf_bytes

        return parse_felgtbi_pdf_bytes(file_bytes, file_name=file_name)
    raise ValueError(f"Unsupported source: {source}")


def count_payload_documents(payload: Any) -> int:
    if isinstance(payload, dict) and isinstance(payload.get("questions"), list):
        from ...import_to_db import count_fra_questions

        return count_fra_questions(payload)
    return len(payload) if isinstance(payload, list) else 1


def build_error_message(message: tuple[str, str], details: list[str] | None = None) -> html.Div:
    es, en = message
    children: list[Any] = [
        html.Div(
            [
                html.Strong(
                    "La subida no se ha completado",
                    **text_attrs("La subida no se ha completado", "The upload was not completed"),
                ),
                html.Button(
                    "Cerrar",
                    id="upload-error-close",
                    type="button",
                    className="upload-message-close",
                    **{
                        **text_attrs("Cerrar", "Close"),
                        "data-upload-dismiss": "true",
                    },
                ),
            ],
            className="upload-message-header",
        ),
        html.P(es, **text_attrs(es, en)),
    ]
    if details:
        children.append(
            html.Ul(
                [html.Li(detail) for detail in details],
                className="upload-message-details",
            )
        )
    children.append(
        html.Div(
            html.Button(
                "Volver a intentar",
                id="upload-error-retry",
                type="button",
                className="upload-message-retry",
                **{
                    **text_attrs("Volver a intentar", "Try again"),
                    "data-upload-dismiss": "true",
                },
            ),
            className="upload-message-actions",
        )
    )

    return html.Div(
        children,
        className="upload-message upload-message-error",
    )


def build_success_message(
    *, source: str, imported_files: list[dict], total_documents: int
) -> html.Div:
    records_es = f"{total_documents} registro{'s' if total_documents != 1 else ''} preparado{'s' if total_documents != 1 else ''}"
    records_en = f"{total_documents} prepared record{'s' if total_documents != 1 else ''}"
    return html.Div(
        [
            html.Strong("Archivo enviado a revisión", **text_attrs("Archivo enviado a revisión", "File sent for review")),
            html.P(
                records_es,
                **text_attrs(records_es, records_en),
            ),
            html.Ul(
                [
                    html.Li(
                        [
                            html.Span(file_info["name"]),
                            html.Em(
                                f"{file_info['documents']} registro{'s' if file_info['documents'] != 1 else ''}",
                                **text_attrs(
                                    f"{file_info['documents']} registro{'s' if file_info['documents'] != 1 else ''}",
                                    f"{file_info['documents']} record{'s' if file_info['documents'] != 1 else ''}",
                                ),
                            ),
                        ]
                    )
                    for file_info in imported_files
                ]
            ),
        ],
        className="upload-message upload-message-success",
    )
