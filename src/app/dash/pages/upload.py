from __future__ import annotations

import base64
import binascii
import hashlib
import importlib
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from dash import Dash, Input, Output, State, dcc, html
from dash.development.base_component import Component
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app.auth.permissions import Permission, user_has_permission
from app.auth.rate_limit import create_rate_limiter
from app.dash.i18n import dash_attrs, text, text_attrs
from app.dash.layouts.loading_modal import build_loading_modal
from app.dash.layouts.navigation import build_navbar
from app.http_security import rate_limit_key
from app.taxonomy import taxonomy_pair

logger = logging.getLogger(__name__)
MEBIBYTE = 1024 * 1024


def _upload_limit_bytes(environment_name: str, default_mebibytes: int) -> int:
    try:
        configured = int(os.getenv(environment_name, str(default_mebibytes)))
    except ValueError:
        configured = default_mebibytes
    return max(1, configured) * MEBIBYTE


MAX_UPLOAD_BYTES = _upload_limit_bytes("UPLOAD_MAX_FILE_MB", 20)
MAX_UPLOAD_TOTAL_BYTES = _upload_limit_bytes("UPLOAD_MAX_TOTAL_MB", 30)
MAX_UPLOAD_REQUEST_BYTES = _upload_limit_bytes("UPLOAD_MAX_REQUEST_MB", 90)
MAX_UPLOAD_FILES = 3
MAX_UPLOAD_FILENAME_LENGTH = 180
_UPLOAD_PROCESSING_LOCK = threading.Lock()


class UploadValidationError(ValueError):
    pass


DATA_SOURCE_OPTIONS = [
    {
        "label": text(*taxonomy_pair("data_source", "fra")),
        "value": "FRA",
    },
    {
        "label": text(*taxonomy_pair("data_source", "ilga")),
        "value": "ILGA",
    },
    {
        "label": text(*taxonomy_pair("data_source", "felgtbi")),
        "value": "FELGTB",
    },
]


def _decode_upload_payload(contents: str) -> tuple[bytes, int]:
    _mime_type, data = _upload_data_parts(contents)
    estimated_size = _estimated_decoded_size(data)
    if estimated_size > MAX_UPLOAD_BYTES:
        raise UploadValidationError("file_too_large")
    try:
        payload = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise UploadValidationError("invalid_base64") from exc
    return payload, len(payload)


def _upload_data_parts(contents: str) -> tuple[str, str]:
    if not isinstance(contents, str) or not contents:
        raise UploadValidationError("empty_contents")
    header, separator, data = contents.partition(",")
    if not separator or not header.startswith("data:") or ";base64" not in header.casefold():
        raise UploadValidationError("invalid_data_uri")
    mime_type = header[5:].split(";", 1)[0].strip().casefold()
    return mime_type, data


def _estimated_decoded_size(encoded_data: str) -> int:
    padding = len(encoded_data) - len(encoded_data.rstrip("="))
    return max(0, (len(encoded_data) * 3) // 4 - padding)


def _memory_usage_mb() -> float | None:
    try:
        resource_module = importlib.import_module("resource")
        peak = float(resource_module.getrusage(resource_module.RUSAGE_SELF).ru_maxrss)
        return round(peak / 1024, 2)
    except AttributeError, ImportError, OSError, ValueError:
        return None


def _upload_log(
    level: int,
    event: str,
    trace: dict[str, Any],
    *,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    started_at = float(trace.get("started_at") or time.perf_counter())
    filenames = _safe_upload_names(trace.get("filename"))
    filename = filenames[0] if filenames else "upload"
    payload = {
        "event": event,
        "upload_id": trace.get("upload_id"),
        "phase": trace.get("phase"),
        "file_extension": Path(filename).suffix.casefold(),
        "file_name_digest": hashlib.sha256(
            filename.encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()[:16],
        "data_source": trace.get("data_source"),
        "mime_type": trace.get("mime_type"),
        "size_bytes": trace.get("size_bytes"),
        "decoded_size_bytes": trace.get("decoded_size_bytes"),
        "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
        "peak_memory_mb": _memory_usage_mb(),
        "worker_pid": os.getpid(),
        **fields,
    }
    logger.log(
        level,
        "upload_event %s",
        json.dumps(payload, ensure_ascii=True, default=str),
        exc_info=exc_info,
    )


def _build_upload_component() -> Component:
    return dcc.Upload(
        id="upload-csv",
        children=html.Div(
            [
                html.Strong(
                    "Arrastra archivos aqu\u00ed",
                    **text_attrs("Arrastra archivos aqu\u00ed", "Drag files here"),
                ),
                html.Span(
                    " o haz clic para seleccionarlos",
                    **text_attrs(" o haz clic para seleccionarlos", " or click to select files"),
                ),
                html.Small(
                    f"M\u00e1ximo {MAX_UPLOAD_FILES} archivos, {MAX_UPLOAD_BYTES // MEBIBYTE} MB por archivo y {MAX_UPLOAD_TOTAL_BYTES // MEBIBYTE} MB en total.",
                    **text_attrs(
                        f"M\u00e1ximo {MAX_UPLOAD_FILES} archivos, {MAX_UPLOAD_BYTES // MEBIBYTE} MB por archivo y {MAX_UPLOAD_TOTAL_BYTES // MEBIBYTE} MB en total.",
                        f"Maximum {MAX_UPLOAD_FILES} files, {MAX_UPLOAD_BYTES // MEBIBYTE} MB per file and {MAX_UPLOAD_TOTAL_BYTES // MEBIBYTE} MB total.",
                    ),
                ),
            ],
            className="upload-area-content",
        ),
        multiple=True,
        className="upload-area",
        className_disabled="upload-area upload-area-disabled",
    )


def build_upload_layout() -> Component:
    return html.Div(
        [
            build_navbar(active="upload"),
            html.Main(
                [
                    html.Header(
                        [
                            html.P(
                                "Revisión de datos",
                                className="upload-eyebrow",
                                **text_attrs("Revisión de datos", "Data review"),
                            ),
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
                            html.Div(_build_upload_component(), id="upload-control-container"),
                            html.Div(
                                [
                                    html.H2(text("Proceso de revisión", "Review process")),
                                    html.Ol(
                                        [
                                            html.Li(
                                                "El archivo se valida y prepara para su revisión.",
                                                **text_attrs(
                                                    "El archivo se valida y prepara para su revisión.",
                                                    "The file is validated and prepared for review.",
                                                ),
                                            ),
                                            html.Li(
                                                "El contenido queda pendiente de aprobación.",
                                                **text_attrs(
                                                    "El contenido queda pendiente de aprobación.",
                                                    "The content remains pending approval.",
                                                ),
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
    upload_rate_limiter = create_rate_limiter(
        max_attempts=max(1, int(os.getenv("UPLOAD_MAX_ATTEMPTS", "10"))),
        window_seconds=max(60, int(os.getenv("UPLOAD_WINDOW_SECONDS", "3600"))),
        namespace="uploads",
    )

    @app.callback(
        Output("upload-output", "children"),
        Output("upload-control-container", "children"),
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
        if not user_has_permission(current_user, Permission.UPLOAD_DATA):
            return (
                build_error_message(
                    (
                        "Debes iniciar sesión para importar datos.",
                        "You must sign in to import data.",
                    )
                ),
                _build_upload_component(),
            )
        limiter_key = rate_limit_key(subject=current_user.get_id() or "", scope="upload")
        if upload_rate_limiter.is_blocked(limiter_key):
            return (
                build_error_message(
                    (
                        "Has alcanzado el límite temporal de importaciones. Inténtalo más tarde.",
                        "You have reached the temporary import limit. Try again later.",
                    )
                ),
                _build_upload_component(),
            )
        upload_rate_limiter.record_failure(limiter_key)
        trace: dict[str, Any] = {
            "upload_id": uuid4().hex,
            "started_at": time.perf_counter(),
            "phase": "callback_received",
            "data_source": data_source,
            "filename": _safe_upload_names(filenames),
        }
        _upload_log(logging.INFO, "started", trace)
        if not _UPLOAD_PROCESSING_LOCK.acquire(blocking=False):
            _upload_log(logging.WARNING, "rejected_busy", trace)
            return (
                build_error_message(
                    (
                        "Ya hay otro PDF proces\u00e1ndose. Espera a que termine antes de iniciar otra subida.",
                        "Another PDF is already being processed. Wait for it to finish before uploading another file.",
                    )
                ),
                _build_upload_component(),
            )
        try:
            result = _process_upload(contents, filenames, data_source, trace=trace)
            trace["phase"] = "completed"
            _upload_log(logging.INFO, "completed", trace)
        except UploadValidationError as exc:
            _upload_log(
                logging.WARNING,
                "validation_failed",
                trace,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            result = _upload_validation_message(str(exc), trace.get("filename"))
        # This callback is the application boundary for PDF, storage and database failures.
        except Exception as exc:  # noqa: BLE001
            _upload_log(
                logging.ERROR,
                "failed",
                trace,
                exc_info=True,
                exception_type=type(exc).__name__,
                exception_message=str(exc)[:500],
            )
            result = build_error_message(
                (
                    "No ha sido posible completar la subida. Inténtalo de nuevo más tarde.",
                    "The upload could not be completed. Please try again later.",
                )
            )
        finally:
            _UPLOAD_PROCESSING_LOCK.release()
        return result, _build_upload_component()

    @app.callback(
        Output("upload-output", "children", allow_duplicate=True),
        Input("upload-error-close", "n_clicks"),
        prevent_initial_call=True,
    )
    def dismiss_upload_error(close_clicks: int | None):
        if not close_clicks:
            raise PreventUpdate
        return ""


def _process_upload(
    contents: Any,
    filenames: Any,
    data_source: str | None,
    *,
    trace: dict[str, Any] | None = None,
) -> Component:
    trace = (
        trace
        if trace is not None
        else {
            "upload_id": uuid4().hex,
            "started_at": time.perf_counter(),
            "data_source": data_source,
        }
    )
    trace["phase"] = "validation"
    if not filenames:
        raise UploadValidationError("missing_filename")
    if not data_source:
        raise UploadValidationError("missing_data_source")

    contents_list, filenames_list = normalize_upload_values(contents, filenames)
    if len(contents_list) != len(filenames_list):
        raise UploadValidationError("upload_metadata_mismatch")
    if len(contents_list) > MAX_UPLOAD_FILES:
        raise UploadValidationError("too_many_files")
    if data_source == "FELGTB" and len(contents_list) != 1:
        raise UploadValidationError("single_pdf_required")

    imported_files: list[dict[str, Any]] = []
    total_documents = 0
    total_decoded_bytes = 0
    for index, (data, name) in enumerate(zip(contents_list, filenames_list, strict=True)):
        phase_started = time.perf_counter()
        trace["phase"] = "validation"
        safe_name = _safe_upload_filename(name)
        trace["filename"] = safe_name
        _upload_log(logging.INFO, "phase_started", trace)
        if not is_supported_upload_file(data_source, safe_name):
            raise UploadValidationError("unsupported_file_type")

        mime_type, encoded_data = _upload_data_parts(data)
        estimated_size = _estimated_decoded_size(encoded_data)
        trace["mime_type"] = mime_type or "unknown"
        trace["size_bytes"] = estimated_size
        _validate_upload_metadata(data_source, safe_name, mime_type, estimated_size)
        if total_decoded_bytes + estimated_size > MAX_UPLOAD_TOTAL_BYTES:
            raise UploadValidationError("total_too_large")
        _upload_log(
            logging.INFO,
            "phase_completed",
            trace,
            phase_elapsed_ms=round((time.perf_counter() - phase_started) * 1000, 2),
        )

        phase_started = time.perf_counter()
        trace["phase"] = "base64_decode"
        _upload_log(logging.INFO, "phase_started", trace)
        payload_bytes, payload_size = _decode_upload_payload(data)
        contents_list[index] = ""
        total_decoded_bytes += payload_size
        trace["decoded_size_bytes"] = payload_size
        _validate_decoded_payload(data_source, safe_name, payload_bytes)
        _upload_log(
            logging.INFO,
            "phase_completed",
            trace,
            phase_elapsed_ms=round((time.perf_counter() - phase_started) * 1000, 2),
        )

        phase_started = time.perf_counter()
        trace["phase"] = "pdf_processing" if data_source == "FELGTB" else "file_parsing"
        _upload_log(logging.INFO, "phase_started", trace)
        payload = parse_file_by_source(
            source=data_source,
            file_bytes=payload_bytes,
            file_name=safe_name,
            upload_id=str(trace.get("upload_id") or ""),
        )
        del payload_bytes
        document_count = count_payload_documents(payload) if payload else 0
        _upload_log(
            logging.INFO,
            "phase_completed",
            trace,
            phase_elapsed_ms=round((time.perf_counter() - phase_started) * 1000, 2),
            document_count=document_count,
        )
        if not payload:
            raise UploadValidationError("empty_payload")

        phase_started = time.perf_counter()
        trace["phase"] = "pending_import_persistence"
        _upload_log(logging.INFO, "phase_started", trace)
        from app.import_to_db import register_pending_import

        user_id = current_user.get_id() if current_user.is_authenticated else None
        register_pending_import(file_name=safe_name, file_json=payload, user_id=user_id)
        _upload_log(
            logging.INFO,
            "phase_completed",
            trace,
            postgres_elapsed_ms=round((time.perf_counter() - phase_started) * 1000, 2),
        )

        total_documents += document_count
        imported_files.append({"name": safe_name, "documents": document_count})

    return build_success_message(
        source=data_source,
        imported_files=imported_files,
        total_documents=total_documents,
    )


def normalize_upload_values(contents: Any, filenames: Any) -> tuple[list[str], list[str]]:
    # Dash supplies a mutable list when ``dcc.Upload(multiple=True)`` is used.
    # Keep ownership of that list so replacing each processed entry releases
    # the large base64 string from the callback frame before PDF extraction.
    contents_list = (
        [contents]
        if isinstance(contents, str)
        else contents
        if isinstance(contents, list)
        else list(contents or [])
    )
    filenames_list = [filenames] if isinstance(filenames, str) else list(filenames or [])
    return contents_list, filenames_list


def _safe_upload_names(filenames: Any) -> list[str]:
    if isinstance(filenames, str):
        values = [filenames]
    elif isinstance(filenames, (list, tuple)):
        values = list(filenames)
    else:
        values = []
    return [_safe_upload_filename(value) for value in values]


def _safe_upload_filename(value: Any) -> str:
    filename = Path(str(value or "upload")).name
    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename).strip().strip(".")
    if not filename:
        return "upload"
    if len(filename) <= MAX_UPLOAD_FILENAME_LENGTH:
        return filename
    suffix = Path(filename).suffix[:20]
    stem_length = MAX_UPLOAD_FILENAME_LENGTH - len(suffix)
    return f"{filename[:stem_length].rstrip()}{suffix}"


def _validate_upload_metadata(
    source: str,
    file_name: str,
    mime_type: str,
    estimated_size: int,
) -> None:
    if estimated_size <= 0:
        raise UploadValidationError("empty_file")
    if estimated_size > MAX_UPLOAD_BYTES:
        raise UploadValidationError("file_too_large")

    suffix = Path(file_name).suffix.casefold()
    allowed_mime_types = {
        ".pdf": {"application/pdf", "application/octet-stream", ""},
        ".csv": {
            "text/csv",
            "text/plain",
            "application/vnd.ms-excel",
            "application/octet-stream",
            "",
        },
        ".json": {"application/json", "text/json", "text/plain", "application/octet-stream", ""},
    }
    if mime_type not in allowed_mime_types.get(suffix, set()):
        raise UploadValidationError("invalid_mime_type")
    if not is_supported_upload_file(source, file_name):
        raise UploadValidationError("unsupported_file_type")


def _validate_decoded_payload(source: str, file_name: str, payload: bytes) -> None:
    if len(payload) > MAX_UPLOAD_BYTES:
        raise UploadValidationError("file_too_large")
    if source == "FELGTB":
        from app.import_to_db.felgtbi.validation import PdfValidationError, validate_felgtbi_pdf

        try:
            validate_felgtbi_pdf(payload, file_name)
        except PdfValidationError as exc:
            raise UploadValidationError(str(exc)) from exc
    if not Path(file_name).name:
        raise UploadValidationError("missing_filename")


def _upload_validation_message(reason: str, filenames: Any) -> Component:
    name = _safe_upload_names(filenames)
    display_name = name[0] if name else "archivo"
    if reason in {"file_too_large", "total_too_large"}:
        return build_error_message(
            (
                f"El archivo {display_name} supera el tama\u00f1o permitido.",
                f"{display_name} exceeds the allowed size.",
            )
        )
    if reason == "too_many_files":
        return build_error_message(
            (
                f"Puedes subir un m\u00e1ximo de {MAX_UPLOAD_FILES} archivos cada vez.",
                f"Maximum {MAX_UPLOAD_FILES} files per upload.",
            )
        )
    if reason == "single_pdf_required":
        return build_error_message(
            ("Sube un \u00fanico PDF cada vez.", "Upload one PDF at a time.")
        )
    if reason == "missing_data_source":
        return build_error_message(
            (
                "Selecciona una fuente antes de subir el archivo.",
                "Select the data source before uploading.",
            )
        )
    if reason in {"unsupported_file_type", "invalid_mime_type"}:
        return build_error_message(
            (
                "El tipo de archivo no corresponde con la fuente seleccionada.",
                "The file type does not match the selected source.",
            )
        )
    if reason in {"empty_fra_csv", "fra_csv_without_data_rows", "empty_payload"}:
        return build_error_message(
            (
                "El CSV de FRA está vacío o no contiene filas de datos válidas.",
                "The FRA CSV is empty or contains no valid data rows.",
            )
        )
    if reason == "html_instead_of_fra_csv":
        return build_error_message(
            (
                "El archivo recibido es HTML, no un CSV de FRA. Descárgalo de nuevo.",
                "The received file is HTML, not a FRA CSV. Download it again.",
            )
        )
    if reason.startswith(("unsupported_fra_csv_schema", "fra_current_schema_without_answer_columns")):
        return build_error_message(
            (
                "No se reconoce el esquema del CSV de FRA ni sus columnas de respuesta.",
                "The FRA CSV schema or its answer columns are not recognized.",
            )
        )
    if reason.startswith(("fra_metadata_mismatch", "fra_answer_metadata_mismatch")):
        return build_error_message(
            (
                "Los filtros o la respuesta indicados por el CSV de FRA no coinciden con el archivo.",
                "The filters or answer declared by the FRA CSV do not match the file.",
            )
        )
    if reason.startswith(("invalid_fra_percentage", "fra_percentage_out_of_range", "fra_proportion_out_of_range")):
        return build_error_message(
            (
                "El CSV de FRA contiene un porcentaje no válido.",
                "The FRA CSV contains an invalid percentage.",
            )
        )
    if reason == "fra_conflicting_duplicate_rows":
        return build_error_message(
            (
                "El CSV de FRA contiene duplicados incompatibles para la misma respuesta.",
                "The FRA CSV contains conflicting duplicates for the same answer.",
            )
        )
    return build_error_message(
        (
            f"No se ha podido validar el archivo {display_name}.",
            f"The file {display_name} could not be validated.",
        )
    )


def is_supported_upload_file(source: str, file_name: str) -> bool:
    suffix = Path(file_name).suffix.lower()
    if source == "ILGA":
        return suffix in {".csv", ".json"}
    if source == "FELGTB":
        return suffix == ".pdf"
    return suffix == ".csv"


def parse_file_by_source(
    source: str,
    file_bytes: bytes,
    file_name: str,
    *,
    upload_id: str = "",
) -> dict | list[dict]:
    if source == "FRA":
        from app.import_to_db import parse_fra_csv_text
        from app.import_to_db.fra.schema import FraCsvError, decode_fra_csv_bytes

        try:
            file_text = decode_fra_csv_bytes(file_bytes)
            return parse_fra_csv_text(file_text, file_name=file_name)
        except FraCsvError as exc:
            raise UploadValidationError(str(exc)) from exc
    if source == "ILGA":
        file_text = file_bytes.decode("utf-8", errors="replace")
        if Path(file_name).suffix.lower() == ".json":
            from app.import_to_db import parse_ilga_json_text

            return parse_ilga_json_text(file_text)
        from app.import_to_db import parse_ilga_csv_text

        return parse_ilga_csv_text(file_text, file_name=file_name)
    if source == "FELGTB":
        from app.import_to_db import parse_felgtbi_pdf_bytes

        return parse_felgtbi_pdf_bytes(
            file_bytes,
            file_name=file_name,
            require_storage=True,
            upload_id=upload_id,
        )
    raise ValueError(f"Unsupported source: {source}")


def count_payload_documents(payload: Any) -> int:
    if isinstance(payload, dict) and isinstance(payload.get("questions"), list):
        from app.import_to_db import count_fra_questions

        return count_fra_questions(payload)
    return len(payload) if isinstance(payload, list) else 1


def build_error_message(message: tuple[str, str], details: list[str] | None = None) -> Component:
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
                    **dash_attrs(
                        {
                            **text_attrs("Cerrar", "Close"),
                            "data-upload-dismiss": "true",
                        }
                    ),
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
    return html.Div(
        children,
        className="upload-message upload-message-error",
    )


def build_success_message(
    *, source: str, imported_files: list[dict], total_documents: int
) -> Component:
    records_es = f"{total_documents} registro{'s' if total_documents != 1 else ''} preparado{'s' if total_documents != 1 else ''}"
    records_en = f"{total_documents} prepared record{'s' if total_documents != 1 else ''}"
    return html.Div(
        [
            html.Strong(
                "Archivo enviado a revisión",
                **text_attrs("Archivo enviado a revisión", "File sent for review"),
            ),
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
