from __future__ import annotations

import base64
import json
import logging
from types import SimpleNamespace

import pytest
from dash import Dash, dcc, html

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
    monkeypatch.setattr(
        upload_page,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            role="admin",
            get_id=lambda: "user-1",
        ),
    )
    monkeypatch.setattr(upload_page, "rate_limit_key", lambda **_kwargs: "upload-key")
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

    result, reset_upload = main_callback(_data_uri(b"%PDF-1.4\n%%EOF"), "report.pdf", "FELGTB")

    assert result.to_plotly_json()["props"]["children"] == "ok"
    assert reset_upload.id == "upload-csv"


def test_upload_callback_rejects_anonymous_users(monkeypatch) -> None:
    monkeypatch.setattr(
        upload_page,
        "current_user",
        SimpleNamespace(is_authenticated=False, role="anonymous"),
    )
    app = Dash("upload-auth-test", suppress_callback_exceptions=True)
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

    result, _reset_upload = main_callback(
        _data_uri(b"%PDF-1.4\n%%EOF"),
        "report.pdf",
        "FELGTB",
    )

    assert process_calls == []
    assert result.to_plotly_json()["props"]["className"] == "upload-message upload-message-error"


def test_upload_callback_accepts_authorized_professional_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        upload_page,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            role="common",
            user_type="rrhh",
            get_id=lambda: "rrhh-1",
        ),
    )
    monkeypatch.setattr(upload_page, "rate_limit_key", lambda **_kwargs: "upload-key")
    app = Dash("upload-profile-auth-test", suppress_callback_exceptions=True)
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
    callback = next(
        metadata["callback"].__wrapped__
        for metadata in app.callback_map.values()
        if metadata["inputs"] == [{"id": "upload-csv", "property": "contents"}]
    )

    monkeypatch.setattr(upload_page, "_process_upload", lambda *_args, **_kwargs: html.Div("ok"))

    result, _reset = callback(_data_uri(b"%PDF-1.4\n%%EOF"), "report.pdf", "FELGTB")

    assert result.to_plotly_json()["props"]["children"] == "ok"


def test_upload_callback_allows_non_admin_validated_professional_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        upload_page,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            admin_validated=False,
            role="common",
            user_type="rrhh",
            get_id=lambda: "rrhh-pending-validation",
        ),
    )
    app = Dash("upload-unverified-test", suppress_callback_exceptions=True)
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
    callback = next(
        metadata["callback"].__wrapped__
        for metadata in app.callback_map.values()
        if metadata["inputs"] == [{"id": "upload-csv", "property": "contents"}]
    )
    monkeypatch.setattr(
        upload_page,
        "_process_upload",
        lambda *_args, **_kwargs: html.Div("ok"),
    )
    monkeypatch.setattr(upload_page, "rate_limit_key", lambda **_kwargs: "upload-key")

    result, _reset = callback(
        _data_uri(b"%PDF-1.4\n%%EOF"), "report.pdf", "FELGTB"
    )

    assert result.to_plotly_json()["props"]["children"] == "ok"


@pytest.mark.parametrize("user_type", ["comun", "docente"])
def test_upload_callback_rejects_profiles_without_import_permission(
    monkeypatch, user_type: str
) -> None:
    monkeypatch.setattr(
        upload_page,
        "current_user",
        SimpleNamespace(is_authenticated=True, role="common", user_type=user_type),
    )
    app = Dash(f"upload-{user_type}-auth-test", suppress_callback_exceptions=True)
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
    callback = next(
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

    result, _reset = callback(_data_uri(b"%PDF-1.4\n%%EOF"), "report.pdf", "FELGTB")

    assert process_calls == []
    assert result.to_plotly_json()["props"]["className"] == "upload-message upload-message-error"


def test_decode_upload_rejects_invalid_base64_and_oversized_payload(monkeypatch) -> None:
    with pytest.raises(upload_page.UploadValidationError, match="invalid_base64"):
        upload_page._decode_upload_payload("data:application/pdf;base64,not-base64!")

    monkeypatch.setattr(upload_page, "MAX_UPLOAD_BYTES", 3)
    with pytest.raises(upload_page.UploadValidationError, match="file_too_large"):
        upload_page._decode_upload_payload(_data_uri(b"%PDF"))


def test_upload_filename_is_bounded_and_cannot_preserve_paths() -> None:
    assert upload_page._safe_upload_filename("../../private/report.csv") == "report.csv"
    assert upload_page._safe_upload_filename("..\\..\\private\\report.csv") == "report.csv"
    bounded = upload_page._safe_upload_filename(f"{'a' * 300}.pdf")
    assert len(bounded) <= upload_page.MAX_UPLOAD_FILENAME_LENGTH
    assert bounded.endswith(".pdf")


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

    first = upload_page._process_upload(
        contents, "Informe con tildes 2026.pdf", "FELGTB", trace=trace
    )
    second = upload_page._process_upload(
        contents, "Informe con tildes 2026.pdf", "FELGTB", trace=trace
    )

    assert first.to_plotly_json()["props"]["className"] == "upload-message upload-message-success"
    assert second.to_plotly_json()["props"]["className"] == "upload-message upload-message-success"
    assert len(parsed) == 2
    assert all(item["upload_id"] == "upload-test" for item in parsed)
    assert len(persisted) == 2


def test_fra_upload_stays_pending_until_admin_approval(monkeypatch) -> None:
    pending: list[dict[str, object]] = []
    mongo_writes: list[object] = []
    monkeypatch.setattr(
        upload_page,
        "parse_file_by_source",
        lambda *_args, **_kwargs: [
            {
                "dataset": "eu_lgbtiq_survey_iii",
                "code": "D1_1",
                "question": "Question",
            }
        ],
    )
    monkeypatch.setattr(
        "app.import_to_db.register_pending_import",
        lambda **kwargs: pending.append(kwargs),
    )
    monkeypatch.setattr(
        "app.import_to_db.fra.upsert_indicators_from_json",
        lambda *_args, **_kwargs: mongo_writes.append(object()),
    )
    monkeypatch.setattr(
        upload_page,
        "current_user",
        SimpleNamespace(is_authenticated=True, get_id=lambda: "user-1"),
    )

    upload_page._process_upload(
        _data_uri(b"question,answer\nD1_1,Yes\n", "text/csv"),
        "fra.csv",
        "FRA",
    )

    assert len(pending) == 1
    assert mongo_writes == []


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

    message = next(
        record.getMessage() for record in caplog.records if "upload_event" in record.getMessage()
    )
    payload = json.loads(message.split("upload_event ", 1)[1])
    assert payload["upload_id"] == "abc123"
    assert payload["phase"] == "validation"
    assert payload["file_extension"] == ".pdf"
    assert payload["file_name_digest"]
    assert "filename" not in payload
    assert "contents" not in payload


def test_fra_upload_rejects_html_renamed_as_csv_with_validation_code() -> None:
    with pytest.raises(upload_page.UploadValidationError, match="html_instead_of_fra_csv"):
        upload_page.parse_file_by_source(
            "FRA",
            b"<html><body>FRA error</body></html>",
            "fra.csv",
        )


def test_fra_schema_error_message_is_clear_and_closable() -> None:
    # Arrange / Act
    message = upload_page._upload_validation_message(
        "unsupported_fra_csv_schema:foo,bar",
        "fra.csv",
    )

    # Assert
    props = message.to_plotly_json()["props"]
    assert props["className"] == "upload-message upload-message-error"
    serialized = str(props["children"])
    assert "esquema del CSV de FRA" in serialized
    assert "upload-error-close" in serialized
    assert "upload-error-retry" not in serialized


def test_concurrent_upload_is_rejected_without_starting_a_second_import(monkeypatch) -> None:
    monkeypatch.setattr(
        upload_page,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            role="admin",
            get_id=lambda: "user-1",
        ),
    )
    monkeypatch.setattr(upload_page, "rate_limit_key", lambda **_kwargs: "upload-key")
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
        result, reset_upload = main_callback(_data_uri(b"%PDF-1.4\n%%EOF"), "report.pdf", "FELGTB")
    finally:
        upload_page._UPLOAD_PROCESSING_LOCK.release()

    assert process_calls == []
    assert result.to_plotly_json()["props"]["className"] == "upload-message upload-message-error"
    assert reset_upload.id == "upload-csv"
