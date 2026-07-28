from __future__ import annotations

import base64
import json
import logging
from types import SimpleNamespace

from dash import Dash, dcc, html
import pytest

import app.dash.pages.upload as upload_page


def _data_uri(payload: bytes, mime_type: str = "application/pdf") -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def test_normalize_upload_values_reuses_mutable_contents_list() -> None:
    contents = [_data_uri(b"%PDF-test")]

    normalized_contents, normalized_names = upload_page.normalize_upload_values(
        contents,
        ["report.pdf"],
    )

    assert normalized_contents is contents
    assert normalized_names == ["report.pdf"]


def test_upload_callback_does_not_write_to_its_own_input_properties(monkeypatch) -> None:
    app = Dash("upload-callback-test", suppress_callback_exceptions=True)
    app.layout = html.Div(
        [
            dcc.Upload(id="upload-csv"),
            html.Div(id="upload-control-container"),
            dcc.Dropdown(id="data-source"),
            html.Div(id="upload-output"),
            html.Div(id="upload-loading-modal"),
        ]
    )
    upload_page.register_upload_callbacks(app)

    callback_keys = list(app.callback_map)
    assert all("upload-csv.contents" not in key for key in callback_keys)
    assert all("upload-csv.filename" not in key for key in callback_keys)
    assert all("upload-csv.last_modified" not in key for key in callback_keys)

    main_callback = next(
        metadata["callback"].__wrapped__
        for metadata in app.callback_map.values()
        if metadata["inputs"] == [{"id": "upload-csv", "property": "contents"}]
    )
    monkeypatch.setattr(upload_page, "_process_upload", lambda *_args, **_kwargs: html.Div("ok"))

    result, reset_upload = main_callback(
        _data_uri(b"%PDF-1.4\n%%EOF"), "report.pdf", "FELGTB"
    )

    assert result.to_plotly_json()["props"]["children"] == "ok"
    assert reset_upload.id == "upload-csv"


def test_decode_upload_rejects_invalid_base64_and_oversized_payload(monkeypatch) -> None:
    with pytest.raises(upload_page.UploadValidationError, match="invalid_base64"):
        upload_page._decode_upload_payload("data:application/pdf;base64,not-base64!")

    monkeypatch.setattr(upload_page, "MAX_UPLOAD_BYTES", 3)
    with pytest.raises(upload_page.UploadValidationError, match="file_too_large"):
        upload_page._decode_upload_payload(_data_uri(b"%PDF"))


def test_pdf_validation_checks_mime_type_and_signature() -> None:
    with pytest.raises(upload_page.UploadValidationError, match="invalid_mime_type"):
        upload_page._validate_upload_metadata("FELGTB", "report.pdf", "image/png", 100)
    with pytest.raises(upload_page.UploadValidationError, match="invalid_pdf_signature"):
        upload_page._validate_decoded_payload("FELGTB", "report.pdf", b"not a pdf")


def test_pdf_upload_is_processed_once_and_persisted_for_review(monkeypatch) -> None:
    parsed: list[dict[str, object]] = []
    persisted: list[dict[str, object]] = []

    def fake_parse(source, file_bytes, file_name, *, upload_id=""):
        parsed.append(
            {
                "source": source,
                "bytes": file_bytes,
                "filename": file_name,
                "upload_id": upload_id,
            }
        )
        return [{"code": "report-1", "question": "Report"}]

    def fake_register_pending_import(**kwargs):
        persisted.append(kwargs)

    monkeypatch.setattr(upload_page, "parse_file_by_source", fake_parse)
    monkeypatch.setattr("app.import_to_db.register_pending_import", fake_register_pending_import)
    monkeypatch.setattr(upload_page, "current_user", SimpleNamespace(is_authenticated=False))
    trace = {
        "upload_id": "upload-test",
        "started_at": 1.0,
        "data_source": "FELGTB",
    }
    contents = _data_uri(b"%PDF-1.4\n%%EOF")

    first = upload_page._process_upload(contents, "Informe con tildes 2026.pdf", "FELGTB", trace=trace)
    second = upload_page._process_upload(contents, "Informe con tildes 2026.pdf", "FELGTB", trace=trace)

    assert first.to_plotly_json()["props"]["className"] == "upload-message upload-message-success"
    assert second.to_plotly_json()["props"]["className"] == "upload-message upload-message-success"
    assert len(parsed) == 2
    assert all(item["upload_id"] == "upload-test" for item in parsed)
    assert len(persisted) == 2


def test_structured_upload_log_contains_phase_and_safe_metadata(caplog) -> None:
    trace = {
        "upload_id": "abc123",
        "started_at": 1.0,
        "phase": "validation",
        "filename": "report.pdf",
        "data_source": "FELGTB",
        "mime_type": "application/pdf",
        "size_bytes": 1234,
    }

    with caplog.at_level(logging.INFO, logger=upload_page.__name__):
        upload_page._upload_log(logging.INFO, "started", trace)

    message = next(record.getMessage() for record in caplog.records if "upload_event" in record.getMessage())
    payload = json.loads(message.split("upload_event ", 1)[1])
    assert payload["upload_id"] == "abc123"
    assert payload["phase"] == "validation"
    assert payload["filename"] == "report.pdf"
    assert "contents" not in payload


def test_concurrent_upload_is_rejected_without_starting_a_second_import(monkeypatch) -> None:
    app = Dash("upload-lock-test", suppress_callback_exceptions=True)
    app.layout = html.Div(
        [
            dcc.Upload(id="upload-csv"),
            html.Div(id="upload-control-container"),
            dcc.Dropdown(id="data-source"),
            html.Div(id="upload-output"),
            html.Div(id="upload-loading-modal"),
        ]
    )
    upload_page.register_upload_callbacks(app)
    main_callback = next(
        metadata["callback"].__wrapped__
        for metadata in app.callback_map.values()
        if metadata["inputs"] == [{"id": "upload-csv", "property": "contents"}]
    )
    process_calls: list[object] = []
    monkeypatch.setattr(
        upload_page,
        "_process_upload",
        lambda *_args, **_kwargs: process_calls.append(object()),
    )

    assert upload_page._UPLOAD_PROCESSING_LOCK.acquire(blocking=False)
    try:
        result, reset_upload = main_callback(
            _data_uri(b"%PDF-1.4\n%%EOF"), "report.pdf", "FELGTB"
        )
    finally:
        upload_page._UPLOAD_PROCESSING_LOCK.release()

    assert process_calls == []
    assert result.to_plotly_json()["props"]["className"] == "upload-message upload-message-error"
    assert reset_upload.id == "upload-csv"
