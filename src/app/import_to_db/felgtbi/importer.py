from __future__ import annotations

import hashlib
import html
import importlib
import io
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, cast

from bson import ObjectId

from app.import_to_db.felgtbi import pipeline as _pipeline
from app.import_to_db.felgtbi.document_identity import (
    attach_source_document_metadata as _attach_source_document_metadata,
)
from app.import_to_db.felgtbi.document_identity import (
    build_metadata_source_document_id as _build_metadata_source_document_id,
)
from app.import_to_db.felgtbi.document_identity import (
    build_pdf_source_document_id as _build_pdf_source_document_id,
)
from app.import_to_db.felgtbi.models import PdfExtractionError, StorageUploadError
from app.import_to_db.felgtbi.pdf_reader import bbox_area as _bbox_area
from app.import_to_db.felgtbi.pdf_reader import bbox_overlap_area as _bbox_overlap_area
from app.import_to_db.felgtbi.pdf_reader import extract_pdf_pages
from app.import_to_db.felgtbi.pdf_reader import safe_bbox as _safe_bbox
from app.import_to_db.felgtbi.semantics import (
    ExtractionContext,
    analyze_chart_residual_text,
    clean_figure_paragraphs,
    clean_semantic_text,
    is_semantically_useful_text,
    semantic_noise_reason,
)
from app.import_to_db.felgtbi.storage import (
    figure_storage_path as _figure_storage_path,
)
from app.import_to_db.felgtbi.storage import (
    supabase_storage_bucket as _supabase_storage_bucket,
)
from app.import_to_db.felgtbi.storage import (
    upload_figure_to_supabase as _upload_figure_to_supabase,
)
from app.import_to_db.utils import normalize_header, parse_float

FELGTBI_SOURCE_CODE = "felgtbi_estado_lgtbi"
FELGTBI_SOURCE_NAME = "FELGTBI+ Estado LGBTIQ+"
SPAIN_COUNTRY = "Spain"
SPAIN_COUNTRY_CODE = "ES"
FIGURE_IMAGE_MIME_TYPE = "image/webp"
FIGURE_IMAGE_EXTENSION = "webp"
logger = logging.getLogger(__name__)

# Compatibility exports: orchestration now lives in pipeline.py while the
# extraction implementation remains here during the gradual refactor.
parse_felgtbi_pdf = _pipeline.parse_felgtbi_pdf
parse_felgtbi_pdf_bytes = _pipeline.parse_felgtbi_pdf_bytes


def _peak_memory_mb() -> float | None:
    try:
        resource_module = importlib.import_module("resource")
        peak = float(resource_module.getrusage(resource_module.RUSAGE_SELF).ru_maxrss)
        return round(peak / 1024, 2)
    except AttributeError, ImportError, OSError, ValueError:
        return None


def _pdf_import_log(
    level: int,
    event: str,
    *,
    upload_id: str,
    file_name: str,
    phase: str,
    started_at: float,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    safe_file_name = Path(file_name).name
    payload = {
        "event": event,
        "upload_id": upload_id or None,
        "file_extension": Path(safe_file_name).suffix.casefold(),
        "file_name_digest": hashlib.sha256(
            safe_file_name.encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()[:16],
        "phase": phase,
        "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
        "peak_memory_mb": _peak_memory_mb(),
        "worker_pid": os.getpid(),
        **fields,
    }
    logger.log(
        level,
        "pdf_import_event %s",
        json.dumps(payload, ensure_ascii=True, default=str),
        exc_info=exc_info,
    )


YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
PERCENT_PATTERN = re.compile(r"(?<!\d)(\d{1,3}(?:[,.]\d{1,2})?)\s*%")
NUMBER_PATTERN = re.compile(r"(?<![\w])\d{1,4}(?:[,.]\d{1,2})?(?![\w])")
CHART_NUMBER_PATTERN = re.compile(
    r"(?<![\w])(?P<value>\d{1,4}(?:[,.]\d{1,2})?)(?P<percent>\s*%)?(?![\w])"
)
TOC_ENTRY_PATTERN = re.compile(r"^(?P<title>.+?)\s+\.{3,}\s*(?P<page>\d{1,3})$")
TOC_DOTS_PAGE_PATTERN = re.compile(r"^\.{3,}\s*(?P<page>\d{1,3})$")
SIMPLE_TOC_ENTRY_PATTERN = re.compile(r"^(?P<title>.+?\D)\s+(?P<page>\d{1,3})$")
FIGURE_CAPTION_PATTERN = re.compile(
    r"^\s*(?P<label>Figura|Gr[aá]fico|Tabla|Ilustraci[oó]n)\s+"
    r"(?P<number>\d+(?:\.\d+)?)[.:]?\s*(?P<title>.+)?$",
    re.IGNORECASE,
)
FIGURE_NUMBER_REFERENCE_PATTERN = re.compile(
    r"\b(?:Figura|Gr[aá]fico|Tabla|Ilustraci[oó]n)\s+(?P<number>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
SECTION_NUMBER_PATTERN = re.compile(r"^\d{1,2}(?:\.\d+)*\.?\s+.+")
SENTENCE_BREAK_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜÑ¿¡])")
FIGURE_REFERENCE_PATTERN = re.compile(
    r"\b(?:Figura|Gr[aá]fico|Tabla|Ilustraci[oó]n)\s+\d+(?:\.\d+)?[.:]?\s*",
    re.IGNORECASE,
)
COLLECTION_REFERENCE_PATTERN = re.compile(
    r"\s*(?::|[,;\-\u2013\u2014])?\s*Estado\s+LGTBI\+?\s+(?:20\d{2})\s*$",
    re.IGNORECASE,
)
CAPTION_SOURCE_PATTERN = re.compile(r"\s+Fuente\s*:\s*", re.IGNORECASE)
MAX_DATA_POINTS_PER_FIGURE = 8
KNOWN_SECTION_PREFIXES = (
    "Resumen Ejecutivo",
    "Resumen ejecutivo",
    "Dimensión del odio",
    "Dimension del odio",
    "Los tipos de odio",
    "Los espacios de riesgo de odio",
    "Contexto y lugar del odio",
    "Agresiones físicas y sexuales",
    "Agresiones fisicas y sexuales",
    "Situaciones de acoso",
    "Situaciones de discriminación",
    "Situaciones de discriminacion",
    "Redes sociales: espacios de proliferación del odio",
    "Redes sociales: espacios de proliferacion del odio",
    "La LGTBIfobia según los datos oficiales",
    "La LGTBIfobia segun los datos oficiales",
    "Conclusiones",
)
EXCLUDED_SECTION_KEYWORDS = {
    "ficha tecnica",
    "ficha t\u00e9cnica",
    "metodologia",
    "metodolog\u00eda",
    "muestra",
    "cuestionario",
    "trabajo de campo",
    "datos tecnicos",
    "datos t\u00e9cnicos",
    "bibliografia",
    "bibliograf\u00eda",
    "referencias",
    "anexos",
}
SHORT_TOC_TITLES = {
    "resumen ejecutivo",
    "presentacion",
    "presentaci\u00f3n",
    "conclusiones",
}
SAMPLE_PATTERNS = (
    re.compile(
        r"tama[ñn]o\s+de\s+la\s+muestra\s+obtenida\s*:?\s*(\d{3,6})",
        re.IGNORECASE,
    ),
    re.compile(r"\bmuestra\s+de\s+(\d{3,6})\b", re.IGNORECASE),
    re.compile(r"\bmuestra\s+(?:obtenida|final)?\s*:?\s*(\d{3,6})", re.IGNORECASE),
    re.compile(r"\b[nN]\s*=\s*(\d{3,6})\b"),
    re.compile(r"(\d{3,6})\s+(?:entrevistas completas|encuestas completas)", re.IGNORECASE),
)
FIELDWORK_PATTERNS = (
    re.compile(
        r"fechas\s+de\s+realizaci[oó]n\s*:?\s*([^\n.]+?20\d{2})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:trabajo de campo|fieldwork)[^:]*:\s*(.+?20\d{2})(?=\s+(?:muestra|tama(?:ño|no|\u00c3\u00b1o)|dimensi(?:ón|on|\u00c3\u00b3n)|el|la|un|una)\b|$)",
        re.IGNORECASE,
    ),
)
EXCLUDED_SENTENCE_KEYWORDS = {
    "fuente:",
    "figura ",
    "tabla ",
    "error muestral",
    "nivel de confianza",
    "tama\u00f1o de la muestra",
    "tamano de la muestra",
    "seleccion aleatoria",
    "selecci\u00f3n aleatoria",
    "telefonos",
    "tel\u00e9fonos",
    "cawi",
    "cati",
    "ponderacion",
    "ponderaci\u00f3n",
    "ficha tecnica",
    "ficha t\u00e9cnica",
    "portal estadistico",
    "portal estad\u00edstico",
    "datos ponderados",
    "recodificacion",
    "recodificaci\u00f3n",
    "margen de error",
    "margenes de error",
    "m\u00e1rgenes de error",
}
RELEVANT_SENTENCE_KEYWORDS = {
    "lgtbi",
    "odio",
    "victima",
    "v\u00edctima",
    "agresion",
    "agresi\u00f3n",
    "acoso",
    "discrimin",
    "denuncia",
    "redes",
    "calle",
    "trabajo",
    "laboral",
    "violencia",
    "aislamiento",
    "insult",
    "trans",
    "lesbian",
    "gay",
    "bisexual",
    "intersex",
}
NUMERIC_RELEVANCE_KEYWORDS = {
    "acuerdo",
    "aument",
    "cae",
    "compar",
    "decrec",
    "descens",
    "desacuerdo",
    "diferenc",
    "disminu",
    "duplica",
    "edad",
    "escala",
    "inferior",
    "ingres",
    "increment",
    "mayor",
    "media",
    "menor",
    "menos",
    "oscila",
    "poco",
    "por_debajo",
    "por_encima",
    "puntos",
    "reduce",
    "riesgo",
    "situa",
    "superior",
    "tendencia",
    "valor",
    "valoracion",
}
HEADING_KEYWORDS = {
    "resumen",
    "dimension",
    "dimensi\u00f3n",
    "tipos",
    "agresiones",
    "situaciones",
    "denuncia",
    "infradenuncia",
    "redes sociales",
    "conclusiones",
    "estimacion",
    "estimaci\u00f3n",
    "poblacion",
    "poblaci\u00f3n",
    "contexto",
    "perfil",
    "opinion",
    "opini\u00f3n",
    "odio",
    "salud",
    "acoso",
    "discriminacion",
    "discriminaci\u00f3n",
}

CATEGORY_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("odio", "Hate crime & hate speech"),
    ("agresion", "Hate crime & hate speech"),
    ("delito", "Hate crime & hate speech"),
    ("discrimin", "Discrimination"),
    ("educacion", "Education"),
    ("escuela", "Education"),
    ("instituto", "Education"),
    ("universidad", "Education"),
    ("empleo", "Employment"),
    ("trabajo", "Employment"),
    ("laboral", "Employment"),
    ("salud", "Health"),
    ("sanitari", "Health"),
    ("vivienda", "Housing"),
    ("familia", "Family"),
    ("politic", "Political participation"),
    ("voto", "Political participation"),
    ("rural", "Territory"),
    ("trans", "Trans and gender identity"),
    ("intersex", "Intersex"),
)

TOPIC_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("discrimin", "Discrimination"),
    ("laboral", "Employment"),
    ("trabajo", "Employment"),
    ("empleo", "Employment"),
    ("salud", "Health"),
    ("sanitari", "Health"),
    ("educacion", "Education"),
    ("escuela", "Education"),
    ("vivienda", "Housing"),
    ("familia", "Family"),
    ("trans", "Trans and gender identity"),
    ("intersex", "Intersex"),
    ("redes", "Hate crime & hate speech"),
    ("denuncia", "Hate crime & hate speech"),
    ("agresion", "Hate crime & hate speech"),
    ("acoso", "Hate crime & hate speech"),
    ("odio", "Hate crime & hate speech"),
)

CONTROLLED_TOPIC_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("agresion sexual", "Sexual violence"),
    ("violencia sexual", "Sexual violence"),
    ("agresion fisica", "Physical violence"),
    ("violencia fisica", "Physical violence"),
    ("acoso", "Harassment"),
    ("discrimin", "Discrimination"),
    ("odio", "Hate crime"),
    ("delito", "Hate crime"),
    ("insult", "Harassment"),
    ("amenaza", "Hate crime"),
    ("educacion", "Education"),
    ("escuela", "Education"),
    ("instituto", "Education"),
    ("universidad", "Education"),
    ("empleo", "Employment"),
    ("trabajo", "Employment"),
    ("laboral", "Employment"),
    ("salud mental", "Mental health"),
    ("salud", "Healthcare"),
    ("sanitari", "Healthcare"),
    ("vivienda", "Housing"),
    ("familia", "Family"),
    ("juventud", "LGBTIQ+ youth"),
    ("joven", "LGBTIQ+ youth"),
    ("trans", "Trans rights"),
    ("aceptacion", "Social acceptance"),
    ("aceptaci\u00f3n", "Social acceptance"),
    ("derechos", "Social acceptance"),
)

REPORT_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("odio", "odio"),
    ("activismo", "activismo_derechos"),
    ("derechos", "activismo_derechos"),
    ("socioeconom", "socioeconomico"),
    ("voto", "voto"),
    ("salud", "salud"),
    ("educacion", "educacion"),
    ("rural", "rural"),
)

BROAD_REPORT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("odio", "Hate crime & hate speech"),
    ("activismo", "Political participation"),
    ("derechos", "Spanish LGBTIQ+ indicators"),
    ("socioeconomico", "Spanish LGBTIQ+ indicators"),
    ("salud", "Health"),
    ("educacion", "Education"),
    ("rural", "Territory"),
    ("voto", "Political participation"),
)


def _run_felgtbi_pdf_pipeline(
    pdf_bytes: bytes,
    *,
    file_name: str = "felgtbi.pdf",
    year: int | None = None,
    require_storage: bool = False,
    upload_id: str = "",
) -> list[dict]:
    started_at = time.perf_counter()
    phase = "pdf_open_and_extract"
    _pdf_import_log(
        logging.INFO,
        "felgtbi_pdf_started",
        upload_id=upload_id,
        file_name=file_name,
        phase=phase,
        started_at=started_at,
        size_bytes=len(pdf_bytes),
    )
    try:
        phase_started = time.perf_counter()
        pages = extract_pdf_pages(pdf_bytes)
        page_count = len(pages)
        _pdf_import_log(
            logging.INFO,
            "phase_completed",
            upload_id=upload_id,
            file_name=file_name,
            phase=phase,
            started_at=started_at,
            phase_elapsed_ms=round((time.perf_counter() - phase_started) * 1000, 2),
            page_count=page_count,
        )

        phase = "text_and_figure_classification"
        phase_started = time.perf_counter()
        _pdf_import_log(
            logging.INFO,
            "phase_started",
            upload_id=upload_id,
            file_name=file_name,
            phase=phase,
            started_at=started_at,
        )
        documents = parse_felgtbi_text_pages(pages, file_name=file_name, year=year)
        detected_sections = len(
            {
                str(document.get("section_title") or "").strip()
                for document in documents
                if str(document.get("section_title") or "").strip()
            }
        )
        detected_figures = sum(
            isinstance(document.get("figure"), dict) for document in documents
        )
        discarded = _discarded_block_summary(documents)
        _pdf_import_log(
            logging.INFO,
            "felgtbi_pdf_structure_detected",
            upload_id=upload_id,
            file_name=file_name,
            phase=phase,
            started_at=started_at,
            year=year or _extract_year(file_name),
            sections=detected_sections,
            figures=detected_figures,
        )
        _pdf_import_log(
            logging.INFO,
            "felgtbi_text_blocks_discarded",
            upload_id=upload_id,
            file_name=file_name,
            phase=phase,
            started_at=started_at,
            **cast(dict[str, Any], discarded),
        )
        del pages
        _attach_source_document_metadata(
            documents,
            file_name=file_name,
            source_document_id=_build_pdf_source_document_id(pdf_bytes, file_name),
            overwrite_document_id=True,
        )
        _pdf_import_log(
            logging.INFO,
            "phase_completed",
            upload_id=upload_id,
            file_name=file_name,
            phase=phase,
            started_at=started_at,
            phase_elapsed_ms=round((time.perf_counter() - phase_started) * 1000, 2),
            document_count=len(documents),
        )

        phase = "supabase_figure_upload"
        phase_started = time.perf_counter()
        _pdf_import_log(
            logging.INFO,
            "phase_started",
            upload_id=upload_id,
            file_name=file_name,
            phase=phase,
            started_at=started_at,
        )
        asset_summary = _attach_page_assets(
            pdf_bytes,
            file_name,
            documents,
            require_storage=require_storage,
            upload_id=upload_id,
        )
        _pdf_import_log(
            logging.INFO,
            "phase_completed",
            upload_id=upload_id,
            file_name=file_name,
            phase=phase,
            started_at=started_at,
            phase_elapsed_ms=round((time.perf_counter() - phase_started) * 1000, 2),
            supabase_elapsed_ms=round((time.perf_counter() - phase_started) * 1000, 2),
            asset_summary=asset_summary,
        )

        phase = "semantic_cleanup"
        phase_started = time.perf_counter()
        _pdf_import_log(
            logging.INFO,
            "phase_started",
            upload_id=upload_id,
            file_name=file_name,
            phase=phase,
            started_at=started_at,
        )
        _refresh_content_html(documents)
        _pdf_import_log(
            logging.INFO,
            "phase_completed",
            upload_id=upload_id,
            file_name=file_name,
            phase=phase,
            started_at=started_at,
            phase_elapsed_ms=round((time.perf_counter() - phase_started) * 1000, 2),
        )
        _pdf_import_log(
            logging.INFO,
            "felgtbi_pdf_completed",
            upload_id=upload_id,
            file_name=file_name,
            phase=phase,
            started_at=started_at,
            page_count=page_count,
            indicators=len(documents),
            figures_uploaded=asset_summary["uploaded"] + asset_summary["reused"],
        )
        return documents
    except Exception as exc:
        _pdf_import_log(
            logging.ERROR,
            "failed",
            upload_id=upload_id,
            file_name=file_name,
            phase=phase,
            started_at=started_at,
            exc_info=True,
            exception_type=type(exc).__name__,
            exception_message=str(exc)[:500],
        )
        raise


def _discarded_block_summary(documents: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"numeric_noise": 0, "footer": 0, "duplicate": 0, "chart_noise": 0, "short": 0}
    for document in documents:
        extraction = document.get("extraction")
        if not isinstance(extraction, dict):
            continue
        reasons = extraction.get("semantic_cleanup_reasons")
        if not isinstance(reasons, dict):
            continue
        for reason, count in reasons.items():
            clean_reason = str(reason or "")
            if clean_reason not in summary:
                clean_reason = "chart_noise"
            summary[clean_reason] += int(count or 0)
    return summary


def _attach_page_assets(
    pdf_bytes: bytes,
    file_name: str,
    documents: list[dict],
    *,
    require_storage: bool = False,
    upload_id: str = "",
) -> dict[str, int]:
    asset_documents = [
        document
        for document in documents
        if isinstance(document.get("visual_context"), dict)
        and (document.get("visual_context") or {}).get("bbox")
    ]
    if not asset_documents:
        return {"page_count": 0, "figure_count": 0, "uploaded": 0, "reused": 0, "failed": 0}

    try:
        import fitz
    except ImportError as exc:
        if require_storage:
            raise PdfExtractionError("missing_pdf_dependency") from exc
        return {"page_count": 0, "figure_count": 0, "uploaded": 0, "reused": 0, "failed": 0}

    rendered_assets: dict[str, dict[str, Any]] = {}
    counters = {"page_count": 0, "figure_count": 0, "uploaded": 0, "reused": 0, "failed": 0}

    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf_document:
        counters["page_count"] = int(pdf_document.page_count)
        for source_document in asset_documents:
            context = source_document.get("visual_context")
            if not isinstance(context, dict):
                continue
            page_number = int(context.get("page") or 0)
            if page_number < 1 or page_number > pdf_document.page_count:
                continue
            bbox = _safe_bbox(context.get("bbox"))
            if bbox is None:
                continue

            storage_path = _figure_storage_path(source_document, file_name)
            asset_id = f"{page_number}:{','.join(str(value) for value in bbox)}:{storage_path}"
            if asset_id in rendered_assets:
                continue
            page = pdf_document[page_number - 1]
            rect = fitz.Rect(*bbox)
            scale = _figure_render_scale(bbox[2] - bbox[0], bbox[3] - bbox[1])
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(scale, scale),
                clip=rect,
                alpha=False,
            )
            image_bytes, width, height, mime_type = _pixmap_image_bytes(pixmap)
            checksum = hashlib.sha256(image_bytes).hexdigest()
            upload_started = time.perf_counter()
            upload = _upload_figure_with_retries(
                image_bytes=image_bytes,
                storage_path=storage_path,
                mime_type=mime_type,
                checksum=checksum,
            )
            counters["figure_count"] += 1
            status = str(upload.get("status") or "failed")
            if status not in {"uploaded", "reused"}:
                status = "failed"
            counters[status] += 1
            _pdf_import_log(
                logging.INFO if status != "failed" else logging.ERROR,
                "figure_upload_completed",
                upload_id=upload_id,
                file_name=file_name,
                phase="supabase_figure_upload",
                started_at=upload_started,
                storage_path=storage_path,
                image_size_bytes=len(image_bytes),
                width=width,
                height=height,
                status=status,
                error=upload.get("error"),
            )
            if upload.get("status") in {"uploaded", "reused"}:
                rendered_assets[asset_id] = {
                    **upload,
                    "width": width,
                    "height": height,
                    "size": len(image_bytes),
                    "checksum": checksum,
                }
                del pixmap, image_bytes
                continue

            rendered_assets[asset_id] = {
                **upload,
                "status": "failed",
                "bucket": upload.get("bucket") or _supabase_storage_bucket(),
                "storage_path": storage_path,
                "mime_type": mime_type,
                "width": width,
                "height": height,
                "size": len(image_bytes),
                "checksum": checksum,
            }
            del pixmap, image_bytes
            if require_storage:
                raise StorageUploadError(
                    f"figure_upload_failed:{upload.get('error') or 'unknown'}:{storage_path}"
                )

    for document in documents:
        context = document.get("visual_context")
        if not isinstance(context, dict):
            continue
        page_number = int(context.get("page") or 0)
        bbox = _safe_bbox(context.get("bbox"))
        storage_path = _figure_storage_path(document, file_name)
        asset_id = (
            f"{page_number}:{','.join(str(value) for value in bbox)}:{storage_path}" if bbox else ""
        )
        asset = rendered_assets.get(asset_id)
        if not asset:
            continue
        figure = document.get("figure")
        if isinstance(figure, dict) and asset.get("status") in {"uploaded", "reused"}:
            figure["storage_path"] = str(asset.get("storage_path") or storage_path)
            figure["width"] = int(asset.get("width") or 0)
            figure["height"] = int(asset.get("height") or 0)
            figure["mime_type"] = str(asset.get("mime_type") or FIGURE_IMAGE_MIME_TYPE)
            figure["size"] = int(asset.get("size") or 0)
            figure["checksum"] = str(asset.get("checksum") or "")
    return counters


def _upload_figure_with_retries(**kwargs: Any) -> dict[str, Any]:
    try:
        attempts = max(1, min(5, int(os.getenv("FELGTBI_STORAGE_ATTEMPTS", "4"))))
    except ValueError:
        attempts = 4
    result: dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        result = _upload_figure_to_supabase(**kwargs)
        if result.get("status") in {"uploaded", "reused"}:
            return result
        error = str(result.get("error") or "")
        if not _is_transient_storage_error(error) or attempt >= attempts:
            return result
        logger.warning(
            "felgtbi_figure_upload_retry attempt=%d max_attempts=%d error=%s",
            attempt,
            attempts,
            error[:160],
        )
        time.sleep(min(2.0, 0.35 * (2 ** (attempt - 1))))
    return result


def _is_transient_storage_error(error: str) -> bool:
    normalized = str(error or "").casefold()
    return any(
        marker in normalized
        for marker in (
            "timeout",
            "endpointconnectionerror",
            "connectionclosederror",
            "connectionerror",
            "temporarilyunavailable",
        )
    )


def _figure_render_scale(width: float, height: float) -> float:
    try:
        configured_max_pixels = int(os.getenv("PDF_FIGURE_MAX_PIXELS", "2500000"))
    except ValueError:
        configured_max_pixels = 2_500_000
    max_pixels = max(250_000, configured_max_pixels)
    source_pixels = max(1.0, float(width) * float(height))
    return round(max(1.0, min(2.0, (max_pixels / source_pixels) ** 0.5)), 3)


def _pixmap_image_bytes(pixmap: Any) -> tuple[bytes, int, int, str]:
    try:
        from PIL import Image
    except ImportError:
        return pixmap.tobytes("png"), int(pixmap.width), int(pixmap.height), "image/png"

    mode = "RGBA" if getattr(pixmap, "alpha", 0) else "RGB"
    source_image = Image.frombytes(
        mode,
        (int(pixmap.width), int(pixmap.height)),
        pixmap.samples,
    )
    rgb_image = source_image if source_image.mode == "RGB" else source_image.convert("RGB")
    try:
        with io.BytesIO() as output:
            rgb_image.save(output, format="WEBP", quality=88, method=4)
            encoded = output.getvalue()
        return encoded, rgb_image.width, rgb_image.height, FIGURE_IMAGE_MIME_TYPE
    finally:
        if rgb_image is not source_image:
            rgb_image.close()
        source_image.close()


def parse_felgtbi_text_pages(
    pages: list[dict[str, Any]],
    *,
    file_name: str = "felgtbi.pdf",
    year: int | None = None,
) -> list[dict]:
    full_text = "\n".join(str(page.get("text") or "") for page in pages)
    resolved_year = year or _extract_year(file_name) or _extract_year(full_text)
    if resolved_year is None:
        raise ValueError("invalid_felgtbi_year")

    report_title = _resolve_report_title(full_text, file_name)
    report_type = _resolve_report_type(report_title, file_name)
    report_category = _resolve_report_category(report_type, report_title, file_name)
    sample_size = _extract_sample_size(full_text)
    fieldwork = _extract_fieldwork(full_text)
    toc_sections = _extract_toc_sections(pages)
    figure_segments = _extract_figure_segments(pages, toc_sections=toc_sections)
    if figure_segments:
        occupied_pages = {int(segment.get("page") or 0) for segment in figure_segments}
        documents = _build_figure_segment_documents(
            pages=pages,
            figure_segments=figure_segments,
            toc_sections=toc_sections,
            year=resolved_year,
            report_title=report_title,
            report_type=report_type,
            report_category=report_category,
            sample_size=sample_size,
            fieldwork=fieldwork,
        )
        if documents:
            supplemental_layout = _build_layout_page_documents(
                pages=pages,
                toc_sections=toc_sections,
                year=resolved_year,
                report_title=report_title,
                report_type=report_type,
                report_category=report_category,
                sample_size=sample_size,
                fieldwork=fieldwork,
            )
            documents.extend(
                document
                for document in supplemental_layout
                if int(document.get("page") or 0) not in occupied_pages
            )
            occupied_pages.update(int(document.get("page") or 0) for document in documents)
            documents.extend(
                _build_narrative_section_documents(
                    pages=pages,
                    toc_sections=toc_sections,
                    occupied_pages=occupied_pages,
                    year=resolved_year,
                    report_title=report_title,
                    report_type=report_type,
                    report_category=report_category,
                    sample_size=sample_size,
                    fieldwork=fieldwork,
                )
            )
            documents.sort(key=lambda item: (int(item.get("page") or 0), str(item.get("code"))))
            _attach_source_document_metadata(
                documents,
                file_name=file_name,
                source_document_id=_build_metadata_source_document_id(
                    file_name, resolved_year, report_title
                ),
            )
            _refresh_content_html(documents)
            return documents

    layout_documents = _build_layout_page_documents(
        pages=pages,
        toc_sections=toc_sections,
        year=resolved_year,
        report_title=report_title,
        report_type=report_type,
        report_category=report_category,
        sample_size=sample_size,
        fieldwork=fieldwork,
    )
    if layout_documents:
        layout_documents.extend(
            _build_narrative_section_documents(
                pages=pages,
                toc_sections=toc_sections,
                occupied_pages={int(document.get("page") or 0) for document in layout_documents},
                year=resolved_year,
                report_title=report_title,
                report_type=report_type,
                report_category=report_category,
                sample_size=sample_size,
                fieldwork=fieldwork,
            )
        )
        layout_documents.sort(
            key=lambda item: (int(item.get("page") or 0), str(item.get("code")))
        )
        _attach_source_document_metadata(
            layout_documents,
            file_name=file_name,
            source_document_id=_build_metadata_source_document_id(
                file_name,
                resolved_year,
                report_title,
            ),
        )
        _refresh_content_html(layout_documents)
        return layout_documents

    documents: list[dict] = []
    seen_codes: set[str] = set()

    for page in pages:
        page_number = int(page.get("page") or 0)
        current_section = _section_for_page(toc_sections, page_number)
        for block in _page_text_block_entries(page):
            block_text = block["text"]
            if _is_excluded_text(block_text):
                continue
            if _looks_like_heading(block_text) or _looks_like_side_heading_block(block):
                current_section = _clean_section_title(block_text)
                continue
            if _is_excluded_section(current_section):
                continue

            for sentence in _split_sentences(block_text):
                matches = list(PERCENT_PATTERN.finditer(sentence))
                if not matches:
                    continue
                if _is_excluded_text(sentence) or not _is_relevant_sentence(sentence):
                    continue

                section = current_section or _infer_section_from_sentence(sentence)
                if _is_excluded_section(section):
                    continue
                for match in matches:
                    percentage = parse_float(match.group(1))
                    if percentage is None or percentage < 0 or percentage > 100:
                        continue
                    question = _build_question(sentence, match)
                    if not _is_meaningful_question(question):
                        continue
                    figure_segment = _figure_segment_for_position(
                        figure_segments,
                        page_number,
                        float(block.get("y0") or 0),
                    )
                    description = (
                        str(figure_segment.get("description") or "")
                        if figure_segment
                        else _build_description(block_text, sentence)
                    )
                    topic = _infer_topic(question, sentence, description, section, report_category)

                    document = _build_document(
                        year=resolved_year,
                        report_title=report_title,
                        report_type=report_type,
                        category=report_category,
                        topic=topic,
                        section=section,
                        question=question,
                        description=description,
                        percentage=percentage,
                        sample_size=sample_size,
                        fieldwork=fieldwork,
                        page=page_number,
                        visual_context=(
                            _visual_context_from_segment(figure_segment)
                            if figure_segment
                            else _build_visual_context(page_number, None, "")
                        ),
                    )
                    if document["code"] in seen_codes:
                        continue
                    seen_codes.add(document["code"])
                    documents.append(document)

    if not documents:
        raise ValueError("invalid_felgtbi_pdf")
    _attach_source_document_metadata(
        documents,
        file_name=file_name,
        source_document_id=_build_metadata_source_document_id(
            file_name, resolved_year, report_title
        ),
    )
    return documents


def _build_narrative_section_documents(
    *,
    pages: list[dict[str, Any]],
    toc_sections: list[dict[str, Any]],
    occupied_pages: set[int],
    year: int,
    report_title: str,
    report_type: str,
    report_category: str,
    sample_size: int | None,
    fieldwork: str,
) -> list[dict[str, Any]]:
    """Keep high-value prose sections that contain no chart or extracted figure."""
    documents: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for section in toc_sections:
        title = _clean_section_title(str(section.get("title") or ""))
        normalized = normalize_header(title)
        if not any(marker in normalized for marker in ("resumen_ejecutivo", "conclusiones")):
            continue
        if normalized in seen_titles or _is_excluded_section(title):
            continue
        start_page = _find_body_heading_page(
            pages,
            title,
            approximate_page=int(section.get("start_page") or 0),
        )
        if start_page is None:
            continue
        paragraphs: list[str] = []
        seen_paragraphs: list[str] = []
        used_pages: list[int] = []
        for page_number in range(start_page, min(len(pages), start_page + 4) + 1):
            if page_number in occupied_pages:
                continue
            page = _page_by_number(pages, page_number)
            if page is None:
                continue
            for block in _raw_text_block_entries(page):
                block_text = str(block.get("text") or "").strip()
                if normalize_header(block_text) == normalized:
                    continue
                if _looks_like_heading(block_text) or _looks_like_side_heading_block(block):
                    continue
                paragraph = _clean_block_paragraph(block_text)
                if not paragraph or len(paragraph) < 55:
                    continue
                if not is_semantically_useful_text(paragraph, seen_texts=seen_paragraphs):
                    continue
                paragraphs.append(paragraph)
                seen_paragraphs.append(paragraph)
                used_pages.append(page_number)
                if len(paragraphs) >= 8:
                    break
            if len(paragraphs) >= 8:
                break
        if not paragraphs:
            continue
        seen_titles.add(normalized)
        page_number = min(used_pages) if used_pages else start_page
        parent_section = _narrative_parent_section(toc_sections, title, page_number)
        topic = _infer_topic(title, " ".join(paragraphs[:2]), "", parent_section, report_category)
        code = _build_subsection_code(year, report_title, title, "narrative", page_number)
        document: dict[str, Any] = {
            "id": str(ObjectId()),
            "schema_version": 2,
            "source": FELGTBI_SOURCE_CODE,
            "year": year,
            "page": page_number,
            "report_title": report_title,
            "report_type": report_type,
            "category": report_category,
            "specific_category": parent_section,
            "section_title": parent_section,
            "section_number": _section_number(parent_section),
            "subsection_title": title,
            "topic": topic,
            "topics": _infer_controlled_topics(
                section=parent_section,
                subsection=title,
                caption="",
                paragraphs=paragraphs,
            ),
            "question": title,
            "description": _paragraphs_plain_summary(paragraphs),
            "paragraphs": paragraphs,
            "paragraphs_before_figure": paragraphs,
            "paragraphs_after_figure": [],
            "data_points": [],
            "content_html": "",
            "content_order": ["paragraphs_before_figure"],
            "visual_context": {"page": page_number},
            "code": code,
            "extraction": {"method": "narrative_section", "semantic_cleanup_removed": 0},
        }
        if sample_size is not None:
            document["sample_size"] = sample_size
        if fieldwork:
            document["fieldwork"] = fieldwork
        documents.append(document)
    return documents


def _find_body_heading_page(
    pages: list[dict[str, Any]],
    title: str,
    *,
    approximate_page: int,
) -> int | None:
    normalized_title = normalize_header(title)
    preferred = [
        page
        for page in pages
        if abs(int(page.get("page") or 0) - max(1, approximate_page - 1)) <= 4
    ]
    for page in [*preferred, *pages]:
        page_number = int(page.get("page") or 0)
        if page_number <= 3:
            continue
        for block in _raw_text_block_entries(page):
            block_title = normalize_header(str(block.get("text") or ""))
            if block_title != normalized_title:
                continue
            if float(block.get("font_size") or 0) >= 14 or bool(block.get("is_bold")):
                return page_number
    return None


def _narrative_parent_section(
    toc_sections: list[dict[str, Any]],
    title: str,
    page_number: int,
) -> str:
    normalized_title = normalize_header(title)
    parent = ""
    for section in toc_sections:
        candidate = _clean_section_title(str(section.get("title") or ""))
        if normalize_header(candidate) == normalized_title:
            continue
        if int(section.get("start_page") or 0) > page_number + 1:
            break
        if SECTION_NUMBER_PATTERN.match(candidate) and not _is_excluded_section(candidate):
            parent = candidate
    return parent or "Contenido del informe"


def _build_layout_page_documents(
    *,
    pages: list[dict[str, Any]],
    toc_sections: list[dict[str, Any]],
    year: int,
    report_title: str,
    report_type: str,
    report_category: str,
    sample_size: int | None,
    fieldwork: str,
) -> list[dict[str, Any]]:
    """Build one structured section per visual data page when captions are absent.

    Many reports use vector charts and page headings instead of explicit ``Figura``
    captions.  The previous percentage-only fallback lost those pages completely.
    Font and position hints let us recognize the page structure without relying on
    a report filename or a fixed list of section titles.
    """
    documents: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    current_layout_heading = ""
    for page in pages:
        blocks = _raw_text_block_entries(page)
        detected_heading = _layout_page_heading(page, blocks)
        heading_block = detected_heading or _layout_fallback_heading(
            page,
            toc_sections,
            inherited_heading=current_layout_heading,
        )
        if heading_block is None or not _is_layout_content_page(page, blocks, heading_block):
            continue
        if detected_heading is not None:
            candidate_heading = _clean_section_title(str(detected_heading.get("text") or ""))
            if candidate_heading and not _is_excluded_section(candidate_heading):
                current_layout_heading = candidate_heading

        page_number = int(page.get("page") or 0)
        heading = _clean_section_title(str(heading_block.get("text") or ""))
        if heading_block.get("synthetic") and heading:
            heading = f"{heading} · p. {page_number}"
        if not heading or _is_excluded_section(heading):
            continue
        section = _section_for_page(toc_sections, page_number) or report_category
        section = _clean_section_title(section) or report_category
        data_points = _extract_layout_data_points(page, blocks, heading_block)
        visual_bbox = _layout_visual_bbox(page, blocks, heading_block, data_points)
        if visual_bbox is None and not data_points:
            continue

        paragraphs_before, paragraphs_after = _layout_context_paragraphs(
            page,
            blocks,
            heading_block,
            visual_bbox,
        )
        semantic_cleanup = clean_figure_paragraphs(
            paragraphs_before,
            paragraphs_after,
            caption=heading,
        )
        paragraphs_before = semantic_cleanup.before
        paragraphs_after = semantic_cleanup.after
        topic = _infer_topic(
            heading,
            str(page.get("text") or ""),
            " ".join([*paragraphs_before, *paragraphs_after]),
            section,
            report_category,
        )
        topics = _infer_controlled_topics(
            section=section,
            subsection=heading,
            caption=heading,
            paragraphs=[*paragraphs_before, *paragraphs_after],
        )
        document = _build_figure_document(
            year=year,
            report_title=report_title,
            report_type=report_type,
            category=report_category,
            topic=topic,
            topics=topics,
            section=section,
            subsection=heading,
            figure_caption=heading,
            figure_source="",
            figure_number=str(page_number),
            paragraphs_before=paragraphs_before,
            paragraphs_after=paragraphs_after,
            data_points=data_points,
            sample_size=sample_size,
            fieldwork=fieldwork,
            page=page_number,
            visual_context=_build_visual_context(page_number, visual_bbox, heading),
        )
        document.update(
            {
                "schema_version": 2,
                "page": page_number,
                "content_order": [
                    "paragraphs_before_figure",
                    "figure",
                    "paragraphs_after_figure",
                    "data_points",
                ],
                "extraction": {
                    "method": "pdf_text_layout",
                    "text_characters": len(str(page.get("text") or "")),
                    "block_count": len(blocks),
                    "data_point_count": len(data_points),
                    "semantic_cleanup_removed": len(semantic_cleanup.removed),
                    "semantic_cleanup_reasons": _semantic_cleanup_reasons(
                        semantic_cleanup.removed
                    ),
                },
            }
        )
        if document["code"] in seen_codes:
            continue
        seen_codes.add(document["code"])
        documents.append(document)
    return documents


def _layout_page_heading(
    page: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    page_height = float(page.get("height") or 842)
    candidates = []
    for block in blocks:
        text = str(block.get("text") or "").strip()
        font_size = float(block.get("font_size") or 0)
        if not text or text.isdigit() or len(text) > 220:
            continue
        if float(block.get("y0") or 0) > page_height * 0.3:
            continue
        if font_size < 16 and not (bool(block.get("is_bold")) and font_size >= 14):
            continue
        candidates.append(block)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda block: (
            -float(block.get("font_size") or 0),
            float(block.get("y0") or 0),
            float(block.get("x0") or 0),
        ),
    )


def _layout_fallback_heading(
    page: dict[str, Any],
    toc_sections: list[dict[str, Any]],
    *,
    inherited_heading: str = "",
) -> dict[str, Any] | None:
    page_number = int(page.get("page") or 0)
    section = _clean_section_title(
        _section_for_page(toc_sections, page_number) or inherited_heading
    )
    if not section or _is_excluded_section(section):
        return None
    return {
        "x0": 70.0,
        "y0": 40.0,
        "x1": float(page.get("width") or 595) - 70.0,
        "y1": 70.0,
        "text": section,
        "font_size": 16.0,
        "is_bold": True,
        "is_italic": False,
        "synthetic": True,
    }


def _is_layout_content_page(
    page: dict[str, Any],
    blocks: list[dict[str, Any]],
    heading: dict[str, Any],
) -> bool:
    page_number = int(page.get("page") or 0)
    visual_regions = _page_visual_regions(page)
    if page_number <= 2:
        return False
    if len(blocks) < 3 and not visual_regions:
        return False
    normalized_text = normalize_header(str(page.get("text") or ""))
    heading_text = normalize_header(str(heading.get("text") or ""))
    if heading_text in {"indice", "contenido", "pagina", "40db", "felgtbi"}:
        return False
    if "indice" in normalized_text[:120] or "tabla_de_contenidos" in normalized_text[:160]:
        return False
    if _is_excluded_section(heading_text):
        return False
    contact_signals = sum(
        marker in normalized_text
        for marker in ("info_40db", "contacto", "calle_", "telefono", "www_40db", "data_insights")
    )
    if contact_signals >= 2:
        return False
    if visual_regions:
        return True
    values = _layout_numeric_matches(page, blocks, heading)
    narrative_blocks = [
        block
        for block in blocks
        if len(str(block.get("text") or "").strip()) >= 40
        and _block_has_letters(str(block.get("text") or ""))
    ]
    return len(values) >= 2 or (bool(values) and (bool(visual_regions) or len(narrative_blocks) >= 2))


def _extract_layout_data_points(
    page: dict[str, Any],
    blocks: list[dict[str, Any]],
    heading: dict[str, Any],
) -> list[dict[str, Any]]:
    matches = _layout_numeric_matches(page, blocks, heading)
    points: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    for index, item in enumerate(matches, start=1):
        value = float(item["value"])
        unit = str(item["unit"])
        label = _nearest_layout_label(blocks, item, heading)
        normalized_label = normalize_header(label)
        if (
            not bool(item.get("explicit_percent"))
            and value <= 10
            and any(token in normalized_label for token in ("media", "promedio", "escala"))
        ):
            unit = "number"
        text = (
            f"{label}: {_format_layout_value(value, unit)}"
            if label
            else f"Resultado {index}: {_format_layout_value(value, unit)}"
        )
        key = (normalize_header(text), value)
        if key in seen:
            continue
        seen.add(key)
        point: dict[str, Any] = {
            "text": text,
            "label": label or f"Resultado {index}",
            "value": value,
            "unit": unit,
            "page": int(page.get("page") or 0),
            "bbox": [
                round(float(item["block"].get("x0") or 0), 2),
                round(float(item["block"].get("y0") or 0), 2),
                round(float(item["block"].get("x1") or 0), 2),
                round(float(item["block"].get("y1") or 0), 2),
            ],
        }
        if unit == "percent":
            point["percentage"] = value
        point["html"] = f"<p>{_data_point_inner_html(text)}</p>"
        points.append(point)
        if len(points) >= 40:
            break
    return points


def _layout_numeric_matches(
    page: dict[str, Any],
    blocks: list[dict[str, Any]],
    heading: dict[str, Any],
) -> list[dict[str, Any]]:
    page_number = int(page.get("page") or 0)
    page_height = float(page.get("height") or 842)
    normalized_page = normalize_header(str(page.get("text") or ""))
    count_unit = "escano" in normalized_page or "escaño" in str(page.get("text") or "").casefold()
    page_uses_percent = (
        "%" in str(page.get("text") or "")
        or "porcentaje" in normalized_page
        or "porcentajes" in normalized_page
    )
    results: list[dict[str, Any]] = []
    for block in blocks:
        text = str(block.get("text") or "").strip()
        if not text or float(block.get("y0") or 0) <= float(heading.get("y1") or 0):
            continue
        if float(block.get("y0") or 0) >= page_height - 35:
            continue
        if text.isdigit() and int(text) == page_number:
            continue
        if text.startswith("*") or _is_figure_note_text(text):
            continue
        block_has_percentages = bool(PERCENT_PATTERN.search(text))
        block_is_narrative = (
            len(text) > 80
            and _block_has_letters(text)
            and is_semantically_useful_text(text)
        )
        if block_is_narrative:
            continue
        for match in CHART_NUMBER_PATTERN.finditer(text):
            if block_has_percentages and not match.group("percent"):
                continue
            value = parse_float(match.group("value"))
            if value is None:
                continue
            if 1900 <= value <= 2100 and not match.group("percent"):
                continue
            unit = (
                "count"
                if count_unit
                else "percent"
                if (match.group("percent") or page_uses_percent)
                else "number"
            )
            maximum = 400 if unit == "count" else 100
            if value < 0 or value > maximum:
                continue
            results.append(
                {
                    "value": float(value),
                    "unit": unit,
                    "block": block,
                    "explicit_percent": bool(match.group("percent")),
                    "match_start": match.start(),
                    "match_end": match.end(),
                }
            )
    return results


def _nearest_layout_label(
    blocks: list[dict[str, Any]],
    item: dict[str, Any],
    heading: dict[str, Any],
) -> str:
    value_block = item["block"]
    own_text = str(value_block.get("text") or "")
    own_label = CHART_NUMBER_PATTERN.sub(" ", own_text)
    own_label = " ".join(own_label.replace("%", " ").split()).strip(" .:-")
    if (
        float(value_block.get("y1") or 0) - float(value_block.get("y0") or 0) > 45
        and len(CHART_NUMBER_PATTERN.findall(own_text)) > 3
    ):
        return ""
    if _is_layout_label(own_label):
        return _truncate_at_word_boundary(own_label, 120)

    value_center = (float(value_block.get("y0") or 0) + float(value_block.get("y1") or 0)) / 2
    candidates: list[tuple[float, float, str]] = []
    for block in blocks:
        if block is value_block or float(block.get("y0") or 0) <= float(heading.get("y1") or 0):
            continue
        text = str(block.get("text") or "").strip()
        if CHART_NUMBER_PATTERN.search(text) or not _is_layout_label(text):
            continue
        if float(block.get("x0") or 0) > float(value_block.get("x0") or 0) + 20:
            continue
        center = (float(block.get("y0") or 0) + float(block.get("y1") or 0)) / 2
        vertical_distance = abs(center - value_center)
        if vertical_distance > 18:
            continue
        horizontal_distance = abs(float(block.get("x1") or 0) - float(value_block.get("x0") or 0))
        candidates.append((vertical_distance, horizontal_distance, text))
    if not candidates:
        return ""
    return _truncate_at_word_boundary(min(candidates)[2], 120)


def _is_layout_label(text: str) -> bool:
    clean = " ".join(str(text or "").split()).strip(" .:-")
    if not clean or len(clean) > 140 or not _block_has_letters(clean):
        return False
    if clean.endswith("?") or len(clean.split()) > 18:
        return False
    normalized = normalize_header(clean)
    return normalized not in {"si", "no", "ns", "nc"} or len(clean) <= 4


def _block_has_letters(text: str) -> bool:
    return any(character.isalpha() for character in str(text or ""))


def _format_layout_value(value: float, unit: str) -> str:
    rendered = f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{rendered}%" if unit == "percent" else rendered


def _layout_visual_bbox(
    page: dict[str, Any],
    blocks: list[dict[str, Any]],
    heading: dict[str, Any],
    data_points: list[dict[str, Any]],
) -> list[float] | None:
    visual_regions = _page_visual_regions(page)
    if visual_regions:
        relevant_regions = _regions_for_data_points(visual_regions, data_points)
        return _union_visual_regions(
            relevant_regions or visual_regions,
            float(page.get("width") or 595),
            float(page.get("height") or 842),
        )
    if not data_points:
        return None
    page_width = float(page.get("width") or 595)
    page_height = float(page.get("height") or 842)
    heading_bottom = float(heading.get("y1") or 0)
    numeric_top = min(float(point["bbox"][1]) for point in data_points)
    introductory = [
        block
        for block in blocks
        if heading_bottom < float(block.get("y0") or 0) < numeric_top - 2
        and len(str(block.get("text") or "")) >= 45
        and _block_has_letters(str(block.get("text") or ""))
    ]
    top = max([heading_bottom + 10, *[float(block.get("y1") or 0) + 8 for block in introductory]])
    numeric_bottom = max(float(point["bbox"][3]) for point in data_points)
    bottom = min(page_height - 45, numeric_bottom + 28)
    if bottom - top < 70:
        bottom = min(page_height - 45, top + 120)
    if bottom <= top:
        return None
    return [24.0, round(top, 2), round(page_width - 24, 2), round(bottom, 2)]


def _page_visual_regions(page: dict[str, Any]) -> list[list[float]]:
    figures = page.get("figures")
    if not isinstance(figures, list):
        return []
    regions: list[list[float]] = []
    for figure in figures:
        if not isinstance(figure, dict):
            continue
        bbox = _safe_bbox(figure.get("bbox"))
        if bbox is not None:
            regions.append(bbox)
    return regions


def _regions_for_data_points(
    regions: list[list[float]],
    data_points: list[dict[str, Any]],
) -> list[list[float]]:
    if not data_points:
        return []
    matched: list[list[float]] = []
    for region in regions:
        for point in data_points:
            bbox = _safe_bbox(point.get("bbox"))
            if bbox is None:
                continue
            center_x = (bbox[0] + bbox[2]) / 2
            center_y = (bbox[1] + bbox[3]) / 2
            if (
                region[0] - 18 <= center_x <= region[2] + 18
                and region[1] - 18 <= center_y <= region[3] + 18
            ):
                matched.append(region)
                break
    return matched


def _union_visual_regions(
    regions: list[list[float]],
    page_width: float,
    page_height: float,
) -> list[float] | None:
    if not regions:
        return None
    padding = 6.0
    return [
        round(max(0.0, min(region[0] for region in regions) - padding), 2),
        round(max(0.0, min(region[1] for region in regions) - padding), 2),
        round(min(page_width, max(region[2] for region in regions) + padding), 2),
        round(min(page_height, max(region[3] for region in regions) + padding), 2),
    ]


def _layout_context_paragraphs(
    page: dict[str, Any],
    blocks: list[dict[str, Any]],
    heading: dict[str, Any],
    bbox: list[float] | None,
) -> tuple[list[str], list[str]]:
    if bbox is None:
        return [], []
    before: list[str] = []
    after: list[str] = []
    for block in blocks:
        text = " ".join(str(block.get("text") or "").split()).strip()
        if block is heading or len(text) < 35 or not _block_has_letters(text):
            continue
        if _is_excluded_data_sentence(text) or _is_figure_caption_text(text):
            continue
        if float(block.get("y1") or 0) <= bbox[1]:
            before.append(_truncate_at_word_boundary(text, 700))
        elif float(block.get("y0") or 0) >= bbox[3]:
            after.append(_truncate_at_word_boundary(text, 700))
    return _deduplicate_text(before)[:5], _deduplicate_text(after)[:5]


def _deduplicate_text(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = normalize_header(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _build_figure_segment_documents(
    *,
    pages: list[dict[str, Any]],
    figure_segments: list[dict[str, Any]],
    toc_sections: list[dict[str, Any]],
    year: int,
    report_title: str,
    report_type: str,
    report_category: str,
    sample_size: int | None,
    fieldwork: str,
) -> list[dict]:
    documents: list[dict] = []
    seen_codes: set[str] = set()
    for segment in figure_segments:
        page = int(segment.get("page") or 0)
        section = _section_for_page(toc_sections, page) or report_category
        section = _clean_section_title(section) or report_category
        if _is_excluded_section(section):
            continue

        subsection = _figure_subsection_title(segment)
        source_text = str(segment.get("description") or "")
        paragraphs_before = _extract_block_paragraphs(str(segment.get("before_description") or ""))
        paragraphs_after = _extract_block_paragraphs(str(segment.get("after_description") or ""))
        semantic_cleanup = clean_figure_paragraphs(
            paragraphs_before,
            paragraphs_after,
            caption=str(segment.get("caption") or ""),
            figure_source=str(segment.get("source") or ""),
        )
        paragraphs_before = semantic_cleanup.before
        paragraphs_after = semantic_cleanup.after
        paragraphs = [*paragraphs_before, *paragraphs_after]
        data_points = _extract_relevant_data_points(source_text, page=page)
        visual_context = _visual_context_from_segment(segment)
        if not paragraphs and not data_points and not visual_context.get("bbox"):
            continue

        topic = _infer_topic(
            subsection,
            source_text,
            str(segment.get("caption") or ""),
            section,
            report_category,
        )
        topics = _infer_controlled_topics(
            section=section,
            subsection=subsection,
            caption=str(segment.get("caption") or ""),
            paragraphs=paragraphs,
        )
        document = _build_figure_document(
            year=year,
            report_title=report_title,
            report_type=report_type,
            category=report_category,
            topic=topic,
            topics=topics,
            section=section,
            subsection=subsection,
            figure_caption=str(segment.get("caption") or ""),
            figure_source=str(segment.get("source") or ""),
            figure_number=str(segment.get("figure_number") or ""),
            paragraphs_before=paragraphs_before,
            paragraphs_after=paragraphs_after,
            data_points=data_points,
            sample_size=sample_size,
            fieldwork=fieldwork,
            page=page,
            visual_context=visual_context,
        )
        document["extraction"] = {
            "method": "figure_caption",
            "semantic_cleanup_removed": len(semantic_cleanup.removed),
            "semantic_cleanup_reasons": _semantic_cleanup_reasons(semantic_cleanup.removed),
        }
        if document["code"] in seen_codes:
            continue
        seen_codes.add(document["code"])
        documents.append(document)
    return documents


def _semantic_cleanup_reasons(removed: list[tuple[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for text_value, analysis in removed:
        reason = semantic_noise_reason(
            text_value,
            ExtractionContext(near_figure=True),
        )
        if reason == "useful":
            reasons = getattr(analysis, "reasons", ())
            reason = str(reasons[0]) if reasons else "chart_noise"
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _build_figure_document(
    *,
    year: int,
    report_title: str,
    report_type: str,
    category: str,
    topic: str,
    topics: list[str],
    section: str,
    subsection: str,
    figure_caption: str,
    figure_source: str,
    figure_number: str,
    paragraphs_before: list[str],
    paragraphs_after: list[str],
    data_points: list[dict[str, Any]],
    sample_size: int | None,
    fieldwork: str,
    page: int,
    visual_context: dict[str, Any],
) -> dict:
    code = _build_subsection_code(year, report_title, subsection, figure_caption, page)
    paragraphs = [*paragraphs_before, *paragraphs_after]
    answers = [
        answer
        for index, point in enumerate(data_points, start=1)
        if (answer := _answer_from_data_point(index, point, sample_size, fieldwork)) is not None
    ]
    description = (
        _paragraphs_plain_summary(paragraphs)
        or _data_points_plain_summary(data_points)
        or subsection
    )
    document = {
        "id": str(ObjectId()),
        "schema_version": 2,
        "source": FELGTBI_SOURCE_CODE,
        "year": year,
        "page": page,
        "report_title": report_title,
        "report_type": report_type,
        "category": category,
        "specific_category": section or category,
        "section_title": section or category,
        "section_number": _section_number(section),
        "subsection_title": subsection,
        "topic": topic,
        "topics": topics or [topic],
        "question": subsection,
        "description": description,
        "figure_caption": figure_caption,
        "figure_number": figure_number,
        "paragraphs": paragraphs,
        "paragraphs_before_figure": paragraphs_before,
        "paragraphs_after_figure": paragraphs_after,
        "data_points": data_points,
        "figure": {
            "number": figure_number,
            "title": _clean_figure_caption_title(figure_caption),
            "caption": figure_caption,
            "source": figure_source,
        },
        "content_html": "",
        "content_order": [
            "paragraphs_before_figure",
            "figure",
            "paragraphs_after_figure",
            "data_points",
        ],
        "visual_context": visual_context,
        "code": code,
    }
    if answers:
        document["answers"] = answers
    if sample_size is not None:
        document["sample_size"] = sample_size
    if fieldwork:
        document["fieldwork"] = fieldwork
    return document


def _answer_from_data_point(
    index: int,
    point: dict[str, Any],
    sample_size: int | None,
    fieldwork: str,
) -> dict[str, Any] | None:
    percentage = point.get("percentage")
    if not isinstance(percentage, (int, float)):
        return None
    answer = {
        "country": SPAIN_COUNTRY,
        "country_code": SPAIN_COUNTRY_CODE,
        "answer": _truncate_at_word_boundary(str(point.get("text") or "Resultado"), 120),
        "value": float(percentage),
        "percentage": float(percentage),
        "unit": "percent",
        "filters": [{"type": "All", "value": "All"}],
        "page": point.get("page"),
    }
    if sample_size is not None:
        answer["sample_size"] = sample_size
    if fieldwork:
        answer["fieldwork"] = fieldwork
    return answer


def _refresh_content_html(documents: list[dict]) -> None:
    for document in documents:
        data_points = document.get("data_points")
        if not isinstance(data_points, list):
            continue
        paragraphs_before = document.get("paragraphs_before_figure")
        paragraphs_after = document.get("paragraphs_after_figure")
        document["content_html"] = _build_content_html(
            section=str(document.get("section_title") or document.get("specific_category") or ""),
            subsection=str(document.get("subsection_title") or document.get("question") or ""),
            visual_context=document.get("visual_context"),
            figure=document.get("figure"),
            paragraphs_before=paragraphs_before if isinstance(paragraphs_before, list) else [],
            paragraphs_after=paragraphs_after if isinstance(paragraphs_after, list) else [],
            data_points=data_points,
        )


def _build_content_html(
    *,
    section: str,
    subsection: str,
    visual_context: Any,
    figure: Any,
    paragraphs_before: list[Any],
    paragraphs_after: list[Any],
    data_points: list[Any],
) -> str:
    parts: list[str] = []
    parts.append('<section class="report-section">')
    if section:
        parts.append(f"<h2>{html.escape(section)}</h2>")
    parts.append('<article class="report-subsection">')
    if subsection:
        parts.append(f"<h3>{html.escape(subsection)}</h3>")

    for paragraph in paragraphs_before:
        text = str(paragraph or "").strip()
        if text:
            parts.append(f"<p>{_emphasize_percentages(text)}</p>")

    context = visual_context if isinstance(visual_context, dict) else {}
    figure_data = figure if isinstance(figure, dict) else {}
    caption = str(figure_data.get("caption") or context.get("caption") or "")
    if caption:
        parts.append(
            '<figure class="report-figure">'
            f"<figcaption>{html.escape(caption)}</figcaption>"
            "</figure>"
        )

    for paragraph in paragraphs_after:
        text = str(paragraph or "").strip()
        if not text:
            continue
        parts.append(f"<p>{_emphasize_percentages(text)}</p>")

    if not paragraphs_before and not paragraphs_after:
        for point in data_points:
            if not isinstance(point, dict):
                continue
            text = str(point.get("text") or "").strip()
            if not text:
                continue
            point_html = f"<p>{_data_point_inner_html(text)}</p>"
            point["html"] = point_html
            parts.append(point_html)
    parts.append("</article>")
    parts.append("</section>")
    return "\n\n".join(parts)


def _data_point_inner_html(text: str) -> str:
    return _emphasize_percentages(text)


def _figure_alt_text(caption: str, fallback: str) -> str:
    clean_caption = FIGURE_REFERENCE_PATTERN.sub("", caption or "").strip(" .:-")
    return _truncate_at_word_boundary(clean_caption or fallback or "Figura del informe", 160)


def _emphasize_percentages(text: str) -> str:
    parts: list[str] = []
    position = 0
    for match in PERCENT_PATTERN.finditer(text):
        parts.append(html.escape(text[position : match.start()]))
        parts.append(f"<strong>{html.escape(match.group(0))}</strong>")
        position = match.end()
    parts.append(html.escape(text[position:]))
    return "".join(parts)


def _extract_block_paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    seen: set[str] = set()
    raw_parts = re.split(r"\n{1,}|\s{2,}", str(text or ""))
    if len(raw_parts) <= 1:
        raw_parts = _split_sentences(str(text or ""))
    for part in raw_parts:
        paragraph = _clean_block_paragraph(part)
        if not paragraph:
            continue
        normalized = normalize_header(paragraph)
        if normalized in seen:
            continue
        seen.add(normalized)
        paragraphs.append(paragraph)
    return _merge_short_context_paragraphs(paragraphs)


def _clean_block_paragraph(text: str) -> str:
    paragraph = clean_semantic_text(text)
    if not paragraph:
        return ""
    paragraph = re.sub(
        r"\s*\(?\s*(?:Figura|Gr[aá]fico)\s+\d+(?:\.\d+)?\s*\)?",
        "",
        paragraph,
        flags=re.IGNORECASE,
    )
    paragraph = re.sub(r"\s+([,.;:!?])", r"\1", paragraph).strip(" .:-")
    if len(paragraph) < 35 and not PERCENT_PATTERN.search(paragraph):
        return ""
    if _is_excluded_data_sentence(paragraph):
        return ""
    normalized = normalize_header(paragraph)
    if "sin_resultados_relevantes" in normalized or normalized.startswith("texto_introductorio"):
        return ""
    if normalized in {"caso", "total"}:
        return ""
    if not is_semantically_useful_text(
        paragraph,
        ExtractionContext(near_figure=True),
    ):
        return ""
    return _truncate_at_word_boundary(paragraph, 900)


def _merge_short_context_paragraphs(paragraphs: list[str]) -> list[str]:
    merged: list[str] = []
    for paragraph in paragraphs:
        if merged and len(paragraph) < 80 and not PERCENT_PATTERN.search(paragraph):
            merged[-1] = f"{merged[-1]} {paragraph}".strip()
            continue
        merged.append(paragraph)
    return merged[:8]


def _extract_relevant_data_points(text: str, *, page: int) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sentence in _split_sentences(text):
        clean_sentence = _clean_data_sentence(sentence)
        if not clean_sentence or _is_excluded_data_sentence(clean_sentence):
            continue

        percent_matches = list(PERCENT_PATTERN.finditer(clean_sentence))
        if percent_matches:
            for match in percent_matches:
                percentage = parse_float(match.group(1))
                if percentage is None or percentage < 0 or percentage > 100:
                    continue
                point_text = _build_data_point_text(clean_sentence, match)
                if not _is_meaningful_question(point_text):
                    continue
                _add_data_point(
                    points,
                    seen,
                    point_text,
                    page=page,
                    percentage=percentage,
                )
                if len(points) >= MAX_DATA_POINTS_PER_FIGURE:
                    break
        elif _is_relevant_numeric_sentence(clean_sentence):
            _add_data_point(points, seen, clean_sentence, page=page)

        if len(points) >= MAX_DATA_POINTS_PER_FIGURE:
            break

    for point in points:
        point.pop("label", None)
        point["html"] = f"<p>{_data_point_inner_html(str(point['text']))}</p>"
    return points


def _add_data_point(
    points: list[dict[str, Any]],
    seen: set[str],
    text: str,
    *,
    page: int,
    percentage: float | None = None,
) -> None:
    clean_text = _clean_data_sentence(text)
    key = normalize_header(clean_text)
    if not clean_text or key in seen:
        return
    seen.add(key)
    point: dict[str, Any] = {
        "text": clean_text,
        "page": page,
    }
    if percentage is not None:
        point["value"] = percentage
        point["percentage"] = percentage
        point["unit"] = "percent"
    points.append(point)


def _clean_data_sentence(text: str) -> str:
    clean_text = " ".join(str(text or "").split()).strip(" .:-")
    clean_text = re.sub(
        r"^(?:la\s+)?Figura\s+\d+(?:\.\d+)?[.:]?\s+"
        r"(?:muestra|indica|presenta|refleja)\s+(?:que\s+)?",
        "",
        clean_text,
        flags=re.IGNORECASE,
    )
    clean_text = re.sub(
        r"\s*\(?\s*Figura\s+\d+(?:\.\d+)?\s*\)?",
        "",
        clean_text,
        flags=re.IGNORECASE,
    )
    clean_text = re.sub(r"\s+([,.;:!?])", r"\1", clean_text)
    clean_text = re.sub(r"^(?:y|e|o|,)\s+", "", clean_text, flags=re.IGNORECASE)
    return _truncate_at_word_boundary(clean_text, 700).strip(" .:-")


def _build_data_point_text(sentence: str, match: re.Match[str]) -> str:
    if len(PERCENT_PATTERN.findall(sentence)) <= 1:
        text = sentence
    else:
        text = _clause_for_percentage(sentence, match)
    text = re.sub(r"\s{2,}", " ", text).strip(" .:-")
    text = re.sub(r"^(?:y|e|o|,)\s+", "", text, flags=re.IGNORECASE)
    return _clean_data_sentence(text)


def _is_excluded_data_sentence(text: str) -> bool:
    if _is_figure_caption_text(text) or _is_figure_note_text(text):
        return True
    normalized = normalize_header(text)
    if normalized.isdigit():
        return True
    if "\u00c2\u00b1" in text or "\u00b1" in text:
        return True
    for keyword in EXCLUDED_SENTENCE_KEYWORDS:
        marker = normalize_header(keyword)
        if marker == "figura":
            continue
        if marker and marker in normalized:
            return True
    return False


def _is_relevant_numeric_sentence(text: str) -> bool:
    text_without_figure_refs = re.sub(
        r"\bFigura\s+\d+(?:\.\d+)?\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    if not NUMBER_PATTERN.search(text_without_figure_refs):
        return False
    numbers = NUMBER_PATTERN.findall(text_without_figure_refs)
    if numbers and all(re.fullmatch(r"20\d{2}", number) for number in numbers):
        return False
    normalized = normalize_header(text)
    if any(keyword in normalized for keyword in NUMERIC_RELEVANCE_KEYWORDS):
        return True
    return _is_relevant_sentence(text)


def _data_points_plain_summary(data_points: list[dict[str, Any]]) -> str:
    summary = " ".join(str(point.get("text") or "") for point in data_points[:3])
    return _truncate_at_word_boundary(summary, 520)


def _paragraphs_plain_summary(paragraphs: list[str]) -> str:
    summary = " ".join(paragraphs[:2])
    return _truncate_at_word_boundary(summary, 620)


def _infer_controlled_topics(
    *,
    section: str,
    subsection: str,
    caption: str,
    paragraphs: list[str],
) -> list[str]:
    text = " ".join([section, subsection, caption, *paragraphs[:4]])
    normalized = normalize_header(text)
    topics: list[str] = []
    for keyword, topic in CONTROLLED_TOPIC_KEYWORDS:
        if normalize_header(keyword) in normalized and topic not in topics:
            topics.append(topic)
    if "agresion" in normalized and "sexual" in normalized:
        for topic in ("Hate crime", "Physical violence", "Sexual violence"):
            if topic not in topics:
                topics.append(topic)
    if "acoso" in normalized and "discrimin" in normalized:
        for topic in ("Harassment", "Discrimination"):
            if topic not in topics:
                topics.append(topic)
    return topics or ["Spanish LGBTIQ+ indicators"]


def _figure_subsection_title(segment: dict[str, Any]) -> str:
    title = str(segment.get("caption_title") or "").strip()
    if not title:
        title = str(segment.get("caption") or "").strip()
    title = FIGURE_REFERENCE_PATTERN.sub("", title).strip(" .:-")
    return _truncate_at_word_boundary(title or "Figura FELGTBI+", 180)


def _build_document(
    *,
    year: int,
    report_title: str,
    report_type: str,
    category: str,
    topic: str,
    section: str,
    question: str,
    description: str,
    percentage: float,
    sample_size: int | None,
    fieldwork: str,
    page: int,
    visual_context: dict[str, Any],
) -> dict:
    code = _build_code(year, report_title, description or question, percentage, page)
    answer = {
        "country": SPAIN_COUNTRY,
        "country_code": SPAIN_COUNTRY_CODE,
        "answer": "Total",
        "value": percentage,
        "percentage": percentage,
        "unit": "percent",
        "filters": [{"type": "All", "value": "All"}],
        "page": page,
    }
    if sample_size is not None:
        answer["sample_size"] = sample_size
    if fieldwork:
        answer["fieldwork"] = fieldwork

    document = {
        "id": str(ObjectId()),
        "source": FELGTBI_SOURCE_CODE,
        "year": year,
        "report_title": report_title,
        "report_type": report_type,
        "category": category,
        "specific_category": section or category,
        "section_title": section or category,
        "section_number": _section_number(section),
        "topic": topic,
        "question": question,
        "description": description or question,
        "visual_context": visual_context,
        "code": code,
        "answers": [answer],
    }
    if sample_size is not None:
        document["sample_size"] = sample_size
    if fieldwork:
        document["fieldwork"] = fieldwork
    return document


def _section_number(section: str) -> str:
    match = re.match(r"^\s*(\d{1,2}(?:\.\d+)*)\.?\s+", str(section or ""))
    return match.group(1) if match else ""


def _extract_year(text: str) -> int | None:
    match = YEAR_PATTERN.search(text or "")
    return int(match.group(1)) if match else None


def _resolve_report_title(full_text: str, file_name: str) -> str:
    lines = _clean_lines(full_text)
    filename_title = _report_title_from_filename(file_name)
    cover_title = _cover_report_title(lines)
    if cover_title:
        return cover_title

    metadata_match = re.search(
        r"\bT[ií]tulo\s*:\s*(?P<title>.+?)\s+(?=Editado\s+por\s*:|Colecci[oó]n\s*:|Madrid\s*,|ISBN\s*:)",
        full_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if metadata_match:
        metadata_title = _clean_report_title(metadata_match.group("title"))
        if _filename_title_conflicts(filename_title, metadata_title):
            return filename_title
        if metadata_title:
            return metadata_title

    for index, line in enumerate(lines[:80]):
        if normalize_header(line).startswith("titulo_"):
            title_line = line
            if index + 1 < len(lines) and re.fullmatch(
                r"LGTBI\+?\s+20\d{2}",
                lines[index + 1],
                flags=re.IGNORECASE,
            ):
                title_line = f"{line} {lines[index + 1]}"
            title = _clean_report_title(title_line)
            if title:
                return title
    for index, line in enumerate(lines[:80]):
        normalized = normalize_header(line)
        if not _is_collection_reference(normalized):
            continue
        for candidate_index in (index - 1, index + 1):
            if candidate_index < 0 or candidate_index >= len(lines):
                continue
            candidate = _clean_report_title(lines[candidate_index])
            if _is_report_title_candidate(candidate):
                return candidate
    stem_title = filename_title
    if normalize_header(stem_title) in {"informe", "informe_estado"}:
        for line in lines[:120]:
            if not SECTION_NUMBER_PATTERN.match(line):
                continue
            content_title = re.sub(r"^\d{1,2}(?:\.\d+)*\.?\s+", "", line).strip()
            if 4 <= len(content_title.split()) <= 16:
                return _clean_report_title(content_title)
    normalized_full_text = normalize_header(full_text)
    if _is_generic_report_title(stem_title) and sum(
        token in normalized_full_text
        for token in ("estimacion_de_voto", "transferencias_de_voto", "movilizacion", "ideologia")
    ) >= 2:
        return "El voto en la comunidad LGTBI+"
    return stem_title or FELGTBI_SOURCE_NAME


def _cover_report_title(lines: list[str]) -> str:
    for index, line in enumerate(lines[:12]):
        candidate = _clean_report_title(line)
        normalized = normalize_header(candidate)
        if not _is_report_title_candidate(candidate) or _is_collection_reference(normalized):
            continue
        if normalized.startswith(("han_participado", "analisis_sobre", "indice")):
            continue
        if 2 <= len(candidate.split()) <= 16 and any(
            token in normalized
            for token in (
                "estado_",
                "diversidad_",
                "matrimonio_",
                "sexilio",
                "derechos_",
                "voto_",
            )
        ):
            if index + 1 < len(lines) and _is_collection_reference(
                normalize_header(lines[index + 1])
            ):
                return candidate
            if index == 0:
                return candidate
    return ""


def _report_title_from_filename(file_name: str) -> str:
    stem = Path(file_name).stem.replace("-", " ").replace("_", " ")
    stem = re.sub(r"\b(?:final|revisado|v\d+)\b", " ", stem, flags=re.IGNORECASE)
    stem = re.sub(r"^\s*(?:i\s+)?informe\s+", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\s+(?:felgtbi?)\s*$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\s+(?:20)?\d{2}\s*$", "", stem)
    stem = re.sub(r"\bLGTBIQ?\+?", "LGTBI+", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\beducacion\b", "educación", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\bpolitico\b", "político", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\bsocioeconomico\b", "socioeconómico", stem, flags=re.IGNORECASE)
    return _clean_report_title(" ".join(stem.split()))[:160]


def _is_generic_report_title(value: str) -> bool:
    normalized = normalize_header(value)
    return normalized in {
        "",
        "informe",
        "informe_felgtbi",
        "estado_lgtbi",
        "felgtbi",
    }


def _filename_title_conflicts(filename_title: str, metadata_title: str) -> bool:
    filename_normalized = normalize_header(filename_title)
    metadata_normalized = normalize_header(metadata_title)
    topic_tokens = ("educacion", "politico", "socioeconomico", "matrimonio", "sexilio", "odio")
    return any(
        token in filename_normalized and token not in metadata_normalized for token in topic_tokens
    )


def _clean_report_title(value: str) -> str:
    title = re.sub(r"^\s*T[ií]tulo\s*:\s*", "", str(value or ""), flags=re.IGNORECASE)
    title = _strip_collection_reference(title)
    return title.strip(" .:-")[:160]


def _is_collection_reference(normalized: str) -> bool:
    return bool(re.fullmatch(r"(?:coleccion_)?estado_lgtbi_?20\d{2}", normalized))


def _is_report_title_candidate(value: str) -> bool:
    clean = str(value or "").strip()
    if not clean or clean.isdigit() or len(clean) > 160:
        return False
    normalized = normalize_header(clean)
    if _is_collection_reference(normalized):
        return False
    excluded_prefixes = (
        "editado_por",
        "coleccion",
        "isbn",
        "madrid",
        "han_participado",
        "diseno_de_portada",
    )
    return not normalized.startswith(excluded_prefixes)


def _resolve_report_type(report_title: str, file_name: str) -> str:
    normalized = normalize_header(f"{report_title} {file_name}")
    for keyword, report_type in REPORT_TYPE_KEYWORDS:
        if keyword in normalized:
            return report_type
    return "estado_lgtbi"


def _resolve_report_category(report_type: str, report_title: str, file_name: str) -> str:
    normalized = normalize_header(f"{report_type} {report_title} {file_name}")
    for keyword, category in BROAD_REPORT_CATEGORIES:
        if keyword in normalized:
            return category
    return _infer_category(normalized)


def _extract_sample_size(text: str) -> int | None:
    normalized_text = text.replace(".", "").replace("\n", " ")
    for pattern in SAMPLE_PATTERNS:
        match = pattern.search(normalized_text)
        if match:
            try:
                sample_size = int(match.group(1))
            except ValueError:
                return None
            if 1900 <= sample_size <= 2100:
                continue
            return sample_size
    return None


def _extract_fieldwork(text: str) -> str:
    normalized_text = " ".join((text or "").split())
    for pattern in FIELDWORK_PATTERNS:
        match = pattern.search(normalized_text)
        if match:
            return " ".join(match.group(1).split())[:180]
    return ""


def _clean_lines(text: str) -> list[str]:
    return [" ".join(line.strip().split()) for line in text.splitlines() if line and line.strip()]


def _build_visual_context(
    page: int,
    bbox: list[float] | None,
    caption: str,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "page": page,
        "kind": "pdf_figure" if bbox else "pdf_text",
    }
    if bbox:
        context["bbox"] = bbox
    if caption:
        context["caption"] = caption[:240]
    return context


def _visual_context_from_segment(segment: dict[str, Any] | None) -> dict[str, Any]:
    if not segment:
        return _build_visual_context(0, None, "")
    return _build_visual_context(
        int(segment.get("visual_page") or segment.get("page") or 0),
        _safe_bbox(segment.get("bbox")),
        str(segment.get("caption") or ""),
    )


def _extract_figure_segments(
    pages: list[dict[str, Any]],
    *,
    toc_sections: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    captions: list[dict[str, Any]] = []
    for page in pages:
        page_number = int(page.get("page") or 0)
        for block in _raw_text_block_entries(page):
            raw_caption = str(block.get("text") or "").strip()
            match = FIGURE_CAPTION_PATTERN.match(raw_caption)
            if match:
                if _is_toc_figure_reference(page, raw_caption):
                    continue
                captions.append(
                    {
                        "page": page_number,
                        "x0": block["x0"],
                        "y0": block["y0"],
                        "x1": block["x1"],
                        "y1": block["y1"],
                        "figure_number": match.group("number"),
                        "caption_title": _clean_figure_caption_title(raw_caption),
                        "caption": _clean_figure_caption(raw_caption),
                        "raw_caption": raw_caption,
                    }
                )

    segments: list[dict[str, Any]] = []
    for index, caption in enumerate(captions):
        previous_caption = captions[index - 1] if index > 0 else None
        next_caption = _next_vertical_caption(captions, index)
        visual_page, bbox = _figure_location_for_caption(
            pages,
            caption,
            next_caption,
            previous_caption,
        )
        before_description, after_description = _figure_text_parts(
            pages,
            caption,
            next_caption,
            previous_caption,
            toc_sections or [],
            figure_bbox=bbox if visual_page == int(caption["page"]) else None,
        )
        description = _format_description(
            f"{before_description} {after_description}",
            max_length=6000,
        )
        if not bbox and not description:
            continue
        segments.append(
            {
                "page": caption["page"],
                "visual_page": visual_page,
                "y0": caption["y0"],
                "figure_number": caption["figure_number"],
                "caption_title": caption["caption_title"],
                "caption": caption["caption"],
                "bbox": bbox,
                "source": _caption_source(str(caption.get("raw_caption") or ""))
                or _figure_source(pages, caption, next_caption),
                "before_description": before_description,
                "after_description": after_description,
                "description": description or caption["caption"],
                "next_page": next_caption["page"] if next_caption else None,
                "next_y0": next_caption["y0"] if next_caption else None,
            }
        )
    return segments


def _figure_location_for_caption(
    pages: list[dict[str, Any]],
    caption: dict[str, Any],
    next_caption: dict[str, Any] | None,
    previous_caption: dict[str, Any] | None,
) -> tuple[int, list[float] | None]:
    caption_page = int(caption.get("page") or 0)
    bbox = _figure_bbox_for_caption(
        pages,
        caption,
        next_caption,
        previous_caption,
    )
    if bbox is not None:
        return caption_page, bbox

    next_page_bbox = _next_page_leading_visual_bbox(pages, caption)
    if next_page_bbox is not None:
        return caption_page + 1, next_page_bbox
    return caption_page, None


def _next_page_leading_visual_bbox(
    pages: list[dict[str, Any]],
    caption: dict[str, Any],
) -> list[float] | None:
    """Find a visual continued on the page after a bottom-of-page caption."""
    caption_page = _page_by_number(pages, int(caption.get("page") or 0))
    if not caption_page:
        return None
    page_height = float(caption_page.get("height") or 842)
    if float(caption.get("y0") or 0) < page_height * 0.72:
        return None

    next_page = _page_by_number(pages, int(caption.get("page") or 0) + 1)
    if not next_page:
        return None
    next_height = float(next_page.get("height") or 842)
    next_width = float(next_page.get("width") or 595)
    blocks = [
        block
        for block in _raw_text_block_entries(next_page)
        if float(block.get("y0") or 0) >= 45
        and float(block.get("y1") or 0) <= next_height - 45
        and str(block.get("text") or "").strip()
    ]
    narrative_starts = [
        float(block.get("y0") or 0)
        for block in blocks
        if _is_semantic_narrative_block(str(block.get("text") or ""))
    ]
    narrative_y0 = min(narrative_starts) if narrative_starts else next_height - 45

    leading_regions = [
        region
        for region in _page_visual_regions(next_page)
        if region[1] < narrative_y0 and region[3] <= narrative_y0 + 8
    ]
    if leading_regions:
        return _union_visual_regions(leading_regions, next_width, next_height)

    leading_blocks = [block for block in blocks if float(block.get("y1") or 0) < narrative_y0]
    value_count = sum(
        len(CHART_NUMBER_PATTERN.findall(str(block.get("text") or ""))) for block in leading_blocks
    )
    if value_count < 2 or not leading_blocks:
        return None

    x0 = max(24.0, min(float(block.get("x0") or 0) for block in leading_blocks) - 12)
    y0 = max(45.0, min(float(block.get("y0") or 0) for block in leading_blocks) - 12)
    x1 = min(next_width - 24.0, max(float(block.get("x1") or 0) for block in leading_blocks) + 12)
    y1 = min(
        narrative_y0 - 8,
        max(float(block.get("y1") or 0) for block in leading_blocks) + 12,
    )
    if x1 - x0 < 120 or y1 - y0 < 60:
        return None
    return _clamp_bbox([x0, y0, x1, y1], next_width, next_height)


def _next_vertical_caption(
    captions: list[dict[str, Any]],
    index: int,
) -> dict[str, Any] | None:
    current = captions[index]
    current_page = int(current.get("page") or 0)
    current_bottom = float(current.get("y1") or 0)
    for candidate in captions[index + 1 :]:
        candidate_page = int(candidate.get("page") or 0)
        if candidate_page > current_page:
            return candidate
        if candidate_page == current_page and float(candidate.get("y0") or 0) > current_bottom + 3:
            return candidate
    return None


def _figure_bbox_for_caption(
    pages: list[dict[str, Any]],
    caption: dict[str, Any],
    next_caption: dict[str, Any] | None,
    previous_caption: dict[str, Any] | None,
) -> list[float] | None:
    page = _page_by_number(pages, int(caption["page"]))
    if not page:
        return None
    page_number = int(caption["page"])
    page_width = float(page.get("width") or 595)
    page_height = float(page.get("height") or 842)
    caption_y1 = float(caption["y1"])
    next_y0 = (
        float(next_caption["y0"])
        if next_caption and int(next_caption["page"]) == page_number
        else page_height - 42.0
    )
    source_y0 = _next_source_y0(page, caption_y1, next_y0)
    top = caption_y1 + 4
    hard_bottom = next_y0 - 6
    visual_region = _nearest_visual_region(
        page,
        caption,
        top,
        hard_bottom,
        previous_caption,
    )
    source_precedes_visual = bool(
        source_y0 and visual_region and source_y0 < float(visual_region["bbox"][1])
    )
    if source_y0 and not source_precedes_visual and source_y0 - caption_y1 > 60:
        hard_bottom = min(hard_bottom, source_y0 - 6)
    if visual_region and (
        visual_region["kind"] != "vector"
        or normalize_header(
            str(caption.get("raw_caption") or caption.get("caption") or "")
        ).startswith("tabla_")
    ):
        return _clamp_bbox(visual_region["bbox"], page_width, page_height)

    narrative_search_y = top + 45
    if visual_region:
        narrative_search_y = max(narrative_search_y, visual_region["bbox"][3] + 3)
    narrative_y0 = _next_narrative_y0(
        page,
        narrative_search_y,
        hard_bottom,
    )
    bottom = min(hard_bottom, narrative_y0 - 6 if narrative_y0 else hard_bottom)
    if visual_region and not narrative_y0:
        bottom = min(bottom, visual_region["bbox"][3] + 60)
    elif not visual_region and not narrative_y0:
        content_bottom = _last_chart_content_y(page, top, hard_bottom)
        if content_bottom is not None:
            bottom = min(bottom, content_bottom + 18)
    if bottom - top < 80:
        return _text_chart_bbox(page, top, hard_bottom)
    return _clamp_bbox(
        [24.0, round(top, 2), page_width - 24.0, round(bottom, 2)],
        page_width,
        page_height,
    )


def _text_chart_bbox(
    page: dict[str, Any],
    top: float,
    bottom: float,
) -> list[float] | None:
    blocks = [
        block
        for block in _raw_text_block_entries(page)
        if float(block.get("y0") or 0) >= top
        and float(block.get("y1") or 0) <= bottom
        and str(block.get("text") or "").strip()
    ]
    numeric_count = sum(
        len(CHART_NUMBER_PATTERN.findall(str(block.get("text") or ""))) for block in blocks
    )
    if numeric_count < 2 or not blocks:
        return None
    page_width = float(page.get("width") or 595)
    page_height = float(page.get("height") or 842)
    x0 = max(24.0, min(float(block.get("x0") or 0) for block in blocks) - 12)
    y0 = max(top, min(float(block.get("y0") or 0) for block in blocks) - 8)
    x1 = min(page_width - 24.0, max(float(block.get("x1") or 0) for block in blocks) + 12)
    y1 = min(bottom, max(float(block.get("y1") or 0) for block in blocks) + 12)
    if x1 - x0 < 120 or y1 - y0 < 60:
        return None
    return _clamp_bbox([x0, y0, x1, y1], page_width, page_height)


def _nearest_visual_region(
    page: dict[str, Any],
    caption: dict[str, Any],
    top: float,
    bottom: float,
    previous_caption: dict[str, Any] | None,
) -> dict[str, Any] | None:
    figures = page.get("figures")
    if not isinstance(figures, list):
        return None
    candidates: list[dict[str, Any]] = []
    is_table = normalize_header(
        str(caption.get("raw_caption") or caption.get("caption") or "")
    ).startswith("tabla_")
    for figure in figures:
        if not isinstance(figure, dict):
            continue
        bbox = _safe_bbox(figure.get("bbox"))
        if not bbox:
            continue
        kind = str(figure.get("kind") or "visual")
        if kind == "vector" and not is_table and _visual_region_contains_narrative(page, bbox):
            continue
        if bbox[1] >= top - 8 and bbox[3] <= bottom + 8:
            candidates.append({"kind": kind, "bbox": bbox})
    if not candidates:
        for figure in figures:
            if not isinstance(figure, dict):
                continue
            bbox = _safe_bbox(figure.get("bbox"))
            kind = str(figure.get("kind") or "visual")
            if bbox and kind != "vector" and bbox[1] < top < bbox[3] - 80 and bbox[3] <= bottom + 8:
                candidates.append({"kind": kind, "bbox": [bbox[0], top, bbox[2], bbox[3]]})
    if not candidates:
        previous_on_page = bool(
            previous_caption
            and int(previous_caption.get("page") or 0) == int(caption.get("page") or 0)
        )
        if previous_on_page:
            return None
        caption_y0 = float(caption.get("y0") or top)
        for figure in figures:
            if not isinstance(figure, dict):
                continue
            bbox = _safe_bbox(figure.get("bbox"))
            kind = str(figure.get("kind") or "visual")
            if (
                kind == "vector"
                and not is_table
                and bbox
                and _visual_region_contains_narrative(page, bbox)
            ):
                continue
            if bbox and bbox[3] <= caption_y0 + 8 and caption_y0 - bbox[3] <= 48:
                candidates.append({"kind": kind, "bbox": bbox})
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda candidate: (
            -_horizontal_overlap_ratio(
                candidate["bbox"],
                [
                    float(caption.get("x0") or 0),
                    float(caption.get("y0") or 0),
                    float(caption.get("x1") or 0),
                    float(caption.get("y1") or 0),
                ],
            ),
            abs(
                (candidate["bbox"][0] + candidate["bbox"][2]) / 2
                - (float(caption.get("x0") or 0) + float(caption.get("x1") or 0)) / 2
            ),
            abs(candidate["bbox"][1] - top),
            -_bbox_area(candidate["bbox"]),
        ),
    )


def _horizontal_overlap_ratio(first: list[float], second: list[float]) -> float:
    overlap = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
    minimum_width = min(first[2] - first[0], second[2] - second[0])
    return overlap / minimum_width if minimum_width > 0 else 0.0


def _next_narrative_y0(
    page: dict[str, Any],
    start_y: float,
    end_y: float,
) -> float | None:
    candidates: list[float] = []
    for block in _raw_text_block_entries(page):
        y0 = float(block.get("y0") or 0)
        if y0 < start_y or y0 >= end_y:
            continue
        text = " ".join(str(block.get("text") or "").split()).strip()
        if _is_semantic_narrative_block(text):
            candidates.append(y0)
    return min(candidates) if candidates else None


def _last_chart_content_y(
    page: dict[str, Any],
    start_y: float,
    end_y: float,
) -> float | None:
    page_number = int(page.get("page") or 0)
    candidates: list[float] = []
    for block in _raw_text_block_entries(page):
        y0 = float(block.get("y0") or 0)
        y1 = float(block.get("y1") or 0)
        text = " ".join(str(block.get("text") or "").split()).strip()
        if y0 < start_y or y1 > end_y or not text:
            continue
        if text.isdigit() and int(text) == page_number:
            continue
        if _is_figure_caption_text(text) or normalize_header(text).startswith("fuente_"):
            continue
        candidates.append(y1)
    return max(candidates) if candidates else None


def _visual_region_contains_narrative(
    page: dict[str, Any],
    region: list[float],
) -> bool:
    for block in _raw_text_block_entries(page):
        block_bbox = _safe_bbox(
            [block.get("x0"), block.get("y0"), block.get("x1"), block.get("y1")]
        )
        if block_bbox is None or _bbox_overlap_area(region, block_bbox) <= 0:
            continue
        text = " ".join(str(block.get("text") or "").split()).strip()
        has_sentence_shape = bool(re.search(r"[.!?](?:\s|$)", text)) or len(text.split()) >= 14
        if has_sentence_shape and _is_semantic_narrative_block(text):
            return True
    return False


def _is_semantic_narrative_block(text: str) -> bool:
    clean = " ".join(str(text or "").split()).strip()
    if len(clean) < 55 or _is_figure_caption_text(clean) or _is_figure_note_text(clean):
        return False
    letters = "".join(character for character in clean if character.isalpha())
    if letters and letters == letters.upper():
        return False
    return analyze_chart_residual_text(clean, ExtractionContext()).has_semantic_sentence


def _clamp_bbox(
    bbox: list[float],
    page_width: float,
    page_height: float,
) -> list[float] | None:
    clamped = [
        max(0.0, min(page_width, float(bbox[0]))),
        max(0.0, min(page_height, float(bbox[1]))),
        max(0.0, min(page_width, float(bbox[2]))),
        max(0.0, min(page_height, float(bbox[3]))),
    ]
    if clamped[2] <= clamped[0] or clamped[3] <= clamped[1]:
        return None
    return [round(value, 2) for value in clamped]


def _next_source_y0(page: dict[str, Any], start_y: float, end_y: float) -> float | None:
    for block in _raw_text_block_entries(page):
        text = normalize_header(block["text"])
        if block["y0"] <= start_y or block["y0"] >= end_y:
            continue
        if text.startswith("fuente"):
            return float(block["y0"])
    return None


def _figure_source(
    pages: list[dict[str, Any]],
    caption: dict[str, Any],
    next_caption: dict[str, Any] | None,
) -> str:
    page = _page_by_number(pages, int(caption["page"]))
    if not page:
        return ""
    start_y = float(caption["y1"])
    end_y = (
        float(next_caption["y0"])
        if next_caption and int(next_caption["page"]) == int(caption["page"])
        else 760.0
    )
    for block in _raw_text_block_entries(page):
        text = str(block.get("text") or "").strip()
        normalized = normalize_header(text)
        if block["y0"] <= start_y or block["y0"] >= end_y:
            continue
        if normalized.startswith("fuente"):
            return _truncate_at_word_boundary(text, 240)
    return ""


def _figure_text_parts(
    pages: list[dict[str, Any]],
    caption: dict[str, Any],
    next_caption: dict[str, Any] | None,
    previous_caption: dict[str, Any] | None,
    toc_sections: list[dict[str, Any]],
    *,
    figure_bbox: list[float] | None = None,
) -> tuple[str, str]:
    before_fragments: list[str] = []
    after_fragments: list[str] = []
    figure_number = str(caption.get("figure_number") or "")
    start_page = max(1, int(caption["page"]) - 1)
    end_page = int(next_caption["page"]) if next_caption else int(caption["page"])
    caption_section = _section_for_page(toc_sections, int(caption["page"]))
    before_caption_context_seen = False
    heading_after_caption_seen = False
    for page_number in range(start_page, end_page + 1):
        page = _page_by_number(pages, page_number)
        if not page:
            continue
        for block in _raw_text_block_entries(page):
            position = (page_number, float(block["y0"]))
            caption_position = (int(caption["page"]), float(caption["y0"]))
            previous_position = (
                (int(previous_caption["page"]), float(previous_caption["y0"]))
                if previous_caption
                else None
            )
            if position < caption_position:
                if previous_position and position <= previous_position:
                    continue
                if _mentions_figure_number(block["text"], figure_number):
                    before_caption_context_seen = True
                elif (
                    not before_caption_context_seen
                    or _mentions_other_figure_number(block["text"], figure_number)
                    or _section_changed(toc_sections, caption_section, page_number)
                ):
                    continue
            if next_caption and page_number == end_page and block["y0"] >= next_caption["y0"]:
                continue
            text = clean_semantic_text(block["text"])
            normalized = normalize_header(text)
            if normalized.isdigit():
                continue
            if _is_figure_caption_text(text):
                continue
            if (
                position > caption_position
                and _section_changed(toc_sections, caption_section, page_number)
                and not _mentions_figure_number(text, figure_number)
            ):
                continue
            if position > caption_position and _looks_like_heading(text):
                heading_after_caption_seen = True
                continue
            if heading_after_caption_seen and not _mentions_figure_number(text, figure_number):
                continue
            if _mentions_other_figure_number(text, figure_number):
                continue
            if _is_figure_note_text(text):
                continue
            if not text.strip():
                continue
            context = _figure_block_extraction_context(
                block,
                figure_bbox,
                position="before" if position < caption_position else "after",
                caption=str(caption.get("caption") or ""),
            )
            if not is_semantically_useful_text(text, context):
                continue
            if position < caption_position:
                before_fragments.append(text)
            else:
                after_fragments.append(text)
    return (
        _format_description(" ".join(before_fragments), max_length=3000),
        _format_description(" ".join(after_fragments), max_length=3000),
    )


def _figure_block_extraction_context(
    block: dict[str, Any],
    figure_bbox: list[float] | None,
    *,
    position: str,
    caption: str,
) -> ExtractionContext:
    block_bbox = _safe_bbox([block.get("x0"), block.get("y0"), block.get("x1"), block.get("y1")])
    if not block_bbox or not figure_bbox:
        return ExtractionContext(
            near_figure=True,
            position=position,
            caption=caption,
        )

    left = max(block_bbox[0], figure_bbox[0])
    top = max(block_bbox[1], figure_bbox[1])
    right = min(block_bbox[2], figure_bbox[2])
    bottom = min(block_bbox[3], figure_bbox[3])
    overlaps = right > left and bottom > top
    inside = (
        block_bbox[0] >= figure_bbox[0]
        and block_bbox[1] >= figure_bbox[1]
        and block_bbox[2] <= figure_bbox[2]
        and block_bbox[3] <= figure_bbox[3]
    )
    vertical_gap = min(
        abs(block_bbox[1] - figure_bbox[3]),
        abs(figure_bbox[1] - block_bbox[3]),
    )
    horizontally_aligned = (
        block_bbox[2] >= figure_bbox[0] - 12 and block_bbox[0] <= figure_bbox[2] + 12
    )
    return ExtractionContext(
        near_figure=overlaps or (horizontally_aligned and vertical_gap <= 48),
        inside_figure=inside,
        overlaps_figure=overlaps,
        position=position,
        caption=caption,
    )



def _clean_figure_caption_title(text: str) -> str:
    match = FIGURE_CAPTION_PATTERN.match(text)
    if not match:
        return _strip_collection_reference(_clean_section_title(text))
    title = str(match.group("title") or "")
    title = CAPTION_SOURCE_PATTERN.split(title, maxsplit=1)[0]
    title = _strip_collection_reference(title).strip(" .:-")
    return _truncate_at_word_boundary(title, 180) if title else ""


def _clean_figure_caption(text: str) -> str:
    match = FIGURE_CAPTION_PATTERN.match(str(text or "").strip())
    if not match:
        return _strip_collection_reference(str(text or "")).strip()
    title = _clean_figure_caption_title(text)
    label = str(match.group("label") or "Figura").strip()
    number = str(match.group("number") or "").strip()
    prefix = f"{label} {number}".strip()
    return f"{prefix}: {title}" if title else prefix


def _caption_source(text: str) -> str:
    parts = CAPTION_SOURCE_PATTERN.split(str(text or ""), maxsplit=1)
    if len(parts) != 2:
        return ""
    return _truncate_at_word_boundary(parts[1].strip(), 240)


def _strip_collection_reference(text: str) -> str:
    clean = " ".join(str(text or "").split()).strip()
    previous = None
    while clean and clean != previous:
        previous = clean
        clean = COLLECTION_REFERENCE_PATTERN.sub("", clean).strip(" .,:;-\u2013\u2014")
    return clean


def _is_figure_caption_text(text: str) -> bool:
    return bool(FIGURE_CAPTION_PATTERN.match(str(text or "").strip()))


def _is_toc_figure_reference(page: dict[str, Any], text: str) -> bool:
    clean = " ".join(str(text or "").split()).strip()
    if (
        TOC_ENTRY_PATTERN.match(clean)
        or re.search(r"\.{3,}\s*\d{1,3}\s*$", clean)
        or re.search(r"\s\d{1,3}\s*$", clean)
    ):
        return True
    normalized_page = normalize_header(str(page.get("text") or ""))
    references = sum(
        1
        for block in _raw_text_block_entries(page)
        if FIGURE_CAPTION_PATTERN.match(str(block.get("text") or "").strip())
    )
    return references >= 3 and (
        any(marker in normalized_page[:500] for marker in ("indice", "contenido"))
        or sum("..." in str(block.get("text") or "") for block in _raw_text_block_entries(page))
        >= 2
    )


def _mentions_figure_number(text: str, figure_number: str) -> bool:
    if not figure_number:
        return False
    return figure_number in _mentioned_figure_numbers(text)


def _mentions_other_figure_number(text: str, figure_number: str) -> bool:
    numbers = _mentioned_figure_numbers(text)
    return bool(numbers and any(number != figure_number for number in numbers))


def _mentioned_figure_numbers(text: str) -> set[str]:
    return {
        match.group("number") for match in FIGURE_NUMBER_REFERENCE_PATTERN.finditer(str(text or ""))
    }


def _section_changed(
    toc_sections: list[dict[str, Any]],
    caption_section: str,
    page_number: int,
) -> bool:
    if not toc_sections or not caption_section:
        return False
    block_section = _section_for_page(toc_sections, page_number)
    return bool(block_section and block_section != caption_section)


def _is_figure_note_text(text: str) -> bool:
    normalized = normalize_header(text)
    return normalized.startswith(("fuente", "nota", "base")) or any(
        marker in normalized
        for marker in (
            "datos ponderados",
            "datos de la encuesta",
            "basado en la pregunta",
            "basados en las preguntas",
            "por favor, indica",
            "indica todas las que correspondan",
        )
    )


def _figure_segment_for_position(
    segments: list[dict[str, Any]],
    page: int,
    y0: float,
) -> dict[str, Any] | None:
    current: dict[str, Any] | None = None
    for segment in segments:
        segment_page = int(segment.get("page") or 0)
        segment_y0 = float(segment.get("y0") or 0)
        if (segment_page, segment_y0) <= (page, y0):
            current = segment
            continue
        break
    if not current:
        return None
    next_page = current.get("next_page")
    next_y0 = current.get("next_y0")
    if next_page is not None and (int(next_page), float(next_y0 or 0)) <= (page, y0):
        return None
    return current


def _page_by_number(pages: list[dict[str, Any]], page_number: int) -> dict[str, Any] | None:
    for page in pages:
        if int(page.get("page") or 0) == page_number:
            return page
    return None


def _extract_toc_sections(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    toc_active = False
    for page in pages[:6]:
        lines = _clean_lines(str(page.get("text") or ""))
        has_toc_heading = any(
            normalize_header(line) in {"contenido", "indice", "indice_general"}
            for line in lines[:8]
        )
        if has_toc_heading:
            toc_active = True
        elif not toc_active:
            continue
        visual_index_entries = sum(
            bool(re.match(r"^(?:gr[aá]fico|figura|tabla)\b", line, re.IGNORECASE))
            for line in lines
        )
        if visual_index_entries >= 3:
            toc_active = False
            continue
        pending_title = ""
        for line in lines:
            dots_page_match = TOC_DOTS_PAGE_PATTERN.match(line.strip())
            if dots_page_match and pending_title:
                title = _clean_toc_title(pending_title)
                pending_title = ""
                try:
                    start_page = int(dots_page_match.group("page"))
                except ValueError:
                    continue
                if not title or title[0].islower() or normalize_header(title) == "contenido":
                    continue
                if _is_toc_continuation_title(title):
                    continue
                key = (normalize_header(title), start_page)
                if key in seen:
                    continue
                seen.add(key)
                sections.append({"title": title[:220], "start_page": start_page})
                continue
            match = TOC_ENTRY_PATTERN.match(line) or SIMPLE_TOC_ENTRY_PATTERN.match(line)
            if not match:
                if _looks_like_toc_title_fragment(line):
                    pending_title = f"{pending_title} {line}".strip()
                    pending_title = pending_title[:320]
                continue
            title = _clean_toc_title(f"{pending_title} {match.group('title')}".strip())
            pending_title = ""
            try:
                start_page = int(match.group("page"))
            except ValueError:
                continue
            if not title or title[0].islower() or normalize_header(title) == "contenido":
                continue
            if _is_toc_continuation_title(title):
                continue
            key = (normalize_header(title), start_page)
            if key in seen:
                continue
            seen.add(key)
            sections.append({"title": title[:220], "start_page": start_page})
        for entry in _spatial_toc_entries(page):
            if _is_toc_continuation_title(entry["title"]):
                continue
            key = (normalize_header(entry["title"]), int(entry["start_page"]))
            if key in seen:
                continue
            seen.add(key)
            sections.append(entry)
        for entry in _linear_toc_entries(lines):
            key = (normalize_header(entry["title"]), int(entry["start_page"]))
            if key in seen:
                continue
            seen.add(key)
            sections.append(entry)

    body_sections = _extract_body_outline_sections(pages)
    body_by_title = {normalize_header(item["title"]): item for item in body_sections}
    combined = [
        body_by_title.get(normalize_header(item["title"]), item)
        for item in sections
    ]
    existing_titles = {normalize_header(item["title"]) for item in combined}
    combined.extend(
        item for item in body_sections if normalize_header(item["title"]) not in existing_titles
    )
    return sorted(combined, key=lambda item: (int(item["start_page"]), item["title"]))


def _linear_toc_entries(lines: list[str]) -> list[dict[str, Any]]:
    """Parse TOCs whose words, dot leaders and page number occupy separate lines."""
    entries: list[dict[str, Any]] = []
    pending: list[str] = []
    saw_dot_leader = False
    for raw_line in lines:
        line = " ".join(str(raw_line or "").split()).strip()
        if not line:
            continue
        if re.fullmatch(r"[.\s]{4,}", line):
            saw_dot_leader = True
            continue
        if line.isdigit() and pending and saw_dot_leader:
            title = _clean_toc_title(" ".join(pending))
            pending = []
            saw_dot_leader = False
            normalized = normalize_header(title)
            if (
                title
                and normalized not in {"indice", "contenido"}
                and not normalized.startswith("indice_")
                and not _is_excluded_section(title)
                and not normalized.startswith(("grafico_", "figura_", "tabla_"))
            ):
                entries.append({"title": title[:220], "start_page": int(line)})
            continue
        if saw_dot_leader and not line.isdigit():
            pending = []
            saw_dot_leader = False
        if not PERCENT_PATTERN.search(line) and len(line) <= 180:
            pending.append(line.strip(" ."))
            pending = pending[-8:]
    return entries


def _spatial_toc_entries(page: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = _raw_text_block_entries(page)
    page_width = float(page.get("width") or 595)
    page_number = int(page.get("page") or 0)
    number_blocks = [
        block
        for block in blocks
        if str(block.get("text") or "").strip().isdigit()
        and int(str(block.get("text") or "").strip()) != page_number
        and float(block.get("x0") or 0) >= page_width * 0.6
    ]
    entries: list[dict[str, Any]] = []
    for block in blocks:
        title = _clean_toc_title(str(block.get("text") or ""))
        if not SECTION_NUMBER_PATTERN.match(title) or _is_figure_caption_text(title):
            continue
        center_y = (float(block.get("y0") or 0) + float(block.get("y1") or 0)) / 2
        matching_numbers = [
            number
            for number in number_blocks
            if abs(
                (float(number.get("y0") or 0) + float(number.get("y1") or 0)) / 2
                - center_y
            )
            <= 8
        ]
        if not matching_numbers:
            continue
        start_page = int(str(min(matching_numbers, key=lambda item: item["x0"])["text"]).strip())
        entries.append({"title": title[:220], "start_page": start_page})
    return entries


def _extract_body_outline_sections(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in pages:
        page_number = int(page.get("page") or 0)
        if page_number <= 2:
            continue
        page_height = float(page.get("height") or 842)
        for block in _raw_text_block_entries(page):
            title = _clean_section_title(str(block.get("text") or ""))
            if not SECTION_NUMBER_PATTERN.match(title):
                continue
            if len(title.split()) > 24 or float(block.get("y0") or 0) > page_height * 0.7:
                continue
            font_size = float(block.get("font_size") or 0)
            if font_size < 18 and not bool(block.get("is_bold")):
                continue
            normalized = normalize_header(title)
            if (
                normalized in seen
                or _is_excluded_section(title)
                or _is_toc_continuation_title(title)
                or _looks_like_reference_entry(title)
            ):
                continue
            seen.add(normalized)
            sections.append({"title": title[:220], "start_page": page_number})
    return sections


def _looks_like_reference_entry(value: str) -> bool:
    text = " ".join(str(value or "").split())
    return bool(
        re.match(r"^\d+\s+(?:https?://|www\.|\S+.*,.*\(20\d{2}\))", text, re.IGNORECASE)
    )


def _looks_like_toc_title_fragment(value: str) -> bool:
    text = " ".join((value or "").split()).strip()
    if not text or normalize_header(text) == "contenido":
        return False
    if text.isdigit() or PERCENT_PATTERN.search(text):
        return False
    if len(text) < 8 or len(text) > 220:
        return False
    if text.endswith((".", ",", ";", ":")):
        return True
    return bool(re.match(r"^(?:\d+(?:\.\d+)*\.?\s+|[A-ZÁÉÍÓÚÜÑ¿])", text))


def _clean_toc_title(value: str) -> str:
    title = " ".join(value.split()).strip(" .")
    return _clean_section_title(re.sub(r"\s{2,}", " ", title))


def _is_toc_continuation_title(value: str) -> bool:
    normalized = normalize_header(value)
    if normalized in {normalize_header(title) for title in SHORT_TOC_TITLES}:
        return False
    if normalized in {"lgtbi", "lgbti", "personas lgtbi", "personas lgbti"}:
        return True
    if normalized.startswith(("indice_", "grafico_", "figura_", "tabla_")):
        return True
    if re.fullmatch(r"\d+(?:_\d+)+", normalized):
        return True
    return bool(len(value.split()) < 3 and not SECTION_NUMBER_PATTERN.match(value))


def _clean_section_title(value: str) -> str:
    title = " ".join((value or "").split()).strip(" .:-")
    if not title:
        return ""
    title = re.sub(r"^Contenido\s+(?=\S)", "", title, flags=re.IGNORECASE)
    if len(title.split()) >= 3 and re.search(r"\bL$", title):
        title = re.sub(r"\bL$", "LGTBI+", title)
    for prefix in KNOWN_SECTION_PREFIXES:
        if normalize_header(title).startswith(normalize_header(prefix)):
            return prefix[:220]
    title = FIGURE_REFERENCE_PATTERN.sub("", title).strip(" .:-")
    title = re.sub(r"\s{2,}", " ", title)
    if len(title) > 120:
        title = _truncate_title_at_sentence_boundary(title)
    return title[:220].strip(" .:-")


def _truncate_title_at_sentence_boundary(value: str) -> str:
    first_sentence = re.split(r"(?<=[.!?])\s+", value, maxsplit=1)[0]
    if 10 <= len(first_sentence) <= 180:
        return first_sentence
    for separator in (
        " Segun ",
        " Según ",
        " La encuesta ",
        " Los datos ",
        " Las personas ",
        " El conjunto ",
        " Una amplia ",
    ):
        index = value.find(separator, 12)
        if 10 <= index <= 180:
            return value[:index]
    return _truncate_at_word_boundary(value, 180)


def _truncate_at_word_boundary(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    truncated = value[:max_length].rsplit(" ", 1)[0]
    return truncated or value[:max_length]


def _section_for_page(sections: list[dict[str, Any]], page: int) -> str:
    current = ""
    for section in sections:
        start_page = int(section.get("start_page") or 0)
        if start_page > page:
            break
        if start_page <= page:
            current = str(section.get("title") or "")
    return current


def _raw_text_block_entries(page: dict[str, Any]) -> list[dict[str, Any]]:
    raw_blocks = page.get("blocks")
    if isinstance(raw_blocks, list) and raw_blocks:
        entries = [
            {
                "x0": float(block.get("x0") or 0),
                "y0": float(block.get("y0") or 0),
                "x1": float(block.get("x1") or 0),
                "y1": float(block.get("y1") or block.get("y0") or 0),
                "text": " ".join(str(block.get("text") or "").split()),
                "font_size": float(block.get("font_size") or 0),
                "is_bold": bool(block.get("is_bold")),
                "is_italic": bool(block.get("is_italic")),
            }
            for block in raw_blocks
            if isinstance(block, dict) and str(block.get("text") or "").strip()
        ]
        return sorted(entries, key=_reading_order_key)
    return [
        {
            "x0": 0.0,
            "y0": float(index),
            "x1": 0.0,
            "y1": float(index),
            "text": line,
            "font_size": 0.0,
            "is_bold": False,
            "is_italic": False,
        }
        for index, line in enumerate(_clean_lines(str(page.get("text") or "")))
    ]


def _page_text_block_entries(page: dict[str, Any]) -> list[dict[str, Any]]:
    cleaned_blocks = _merge_left_heading_fragments(_raw_text_block_entries(page))
    if cleaned_blocks:
        merged_blocks: list[dict[str, Any]] = []
        for block in cleaned_blocks:
            text = block["text"]
            if (
                merged_blocks and _should_merge_spatial_heading_blocks(merged_blocks[-1], block)
            ) or (
                merged_blocks
                and _blocks_can_text_merge(merged_blocks[-1], block)
                and _should_merge_blocks(merged_blocks[-1]["text"], text)
            ):
                merged_blocks[-1]["text"] = f"{merged_blocks[-1]['text']} {text}"
                merged_blocks[-1]["x1"] = max(float(merged_blocks[-1]["x1"]), float(block["x1"]))
                merged_blocks[-1]["y1"] = max(float(merged_blocks[-1]["y1"]), float(block["y1"]))
            else:
                merged_blocks.append(dict(block))
        return merged_blocks
    return []



def _reading_order_key(block: dict[str, Any]) -> tuple[int, float, float]:
    y0 = float(block.get("y0") or 0)
    return (round(y0 / 10), float(block.get("x0") or 0), y0)


def _merge_left_heading_fragments(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    left_blocks = [dict(block) for block in blocks if _is_left_heading_fragment(block)]
    other_blocks = [dict(block) for block in blocks if not _is_left_heading_fragment(block)]
    merged_left: list[dict[str, Any]] = []
    for block in sorted(left_blocks, key=lambda item: (float(item["y0"]), float(item["x0"]))):
        if merged_left and _left_heading_fragments_are_adjacent(merged_left[-1], block):
            merged_left[-1]["text"] = f"{merged_left[-1]['text']} {block['text']}"
            merged_left[-1]["x0"] = min(float(merged_left[-1]["x0"]), float(block["x0"]))
            merged_left[-1]["x1"] = max(float(merged_left[-1]["x1"]), float(block["x1"]))
            merged_left[-1]["y1"] = max(float(merged_left[-1]["y1"]), float(block["y1"]))
        else:
            merged_left.append(block)
    return sorted([*merged_left, *other_blocks], key=_reading_order_key)


def _is_left_heading_fragment(block: dict[str, Any]) -> bool:
    text = str(block.get("text") or "").strip()
    if not text or text.isdigit() or PERCENT_PATTERN.search(text):
        return False
    if len(text) > 140:
        return False
    return float(block.get("x1") or 0) <= 225


def _left_heading_fragments_are_adjacent(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    gap = float(current.get("y0") or 0) - float(previous.get("y1") or 0)
    return -2 <= gap <= 12


def _blocks_can_text_merge(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    previous_left = float(previous.get("x1") or 0) <= 225
    current_left = float(current.get("x1") or 0) <= 225
    if previous_left != current_left:
        return False
    gap = float(current.get("y0") or 0) - float(previous.get("y1") or 0)
    return not gap > 14


def _should_merge_spatial_heading_blocks(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    previous_text = str(previous.get("text") or "")
    current_text = str(current.get("text") or "")
    if not previous_text or not current_text:
        return False
    if PERCENT_PATTERN.search(previous_text) or PERCENT_PATTERN.search(current_text):
        return False
    if _is_excluded_text(previous_text) or _is_excluded_text(current_text):
        return False
    if float(previous.get("x1") or 0) > 225 or float(current.get("x1") or 0) > 225:
        return False
    gap = float(current.get("y0") or 0) - float(previous.get("y1") or 0)
    return not (gap < -2 or gap > 8)


def _should_merge_blocks(previous: str, current: str) -> bool:
    if not previous or not current:
        return False
    if _is_excluded_text(previous) or _is_excluded_text(current):
        return False
    if previous.rstrip().endswith((".", "!", "?", ":", ";", ")")):
        return False
    if _looks_like_heading(previous):
        return False
    current_first = current[:1]
    continuation_start = re.match(
        r"^(?:(?:y|e|o|que|de|del|la|las|los|un|una)\b|LGTBI\+|LGBTI\+)",
        current,
        re.IGNORECASE,
    )
    if current_first.islower() or continuation_start:
        return True
    return len(previous) < 70 and len(current) < 70


def _split_sentences(text: str) -> list[str]:
    clean_text = " ".join(text.split())
    if not clean_text:
        return []
    candidates = re.split(r"(?<=[.!?])\s+", clean_text)
    sentences: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        if len(candidate) > 360 and PERCENT_PATTERN.search(candidate):
            sentences.extend(_split_long_sentence(candidate))
        else:
            sentences.append(candidate)
    return sentences


def _split_long_sentence(sentence: str) -> list[str]:
    parts = re.split(r";\s+", sentence)
    return [part.strip() for part in parts if part.strip()]


def _build_question(sentence: str, match: re.Match[str]) -> str:
    if len(PERCENT_PATTERN.findall(sentence)) <= 1:
        text = sentence
    else:
        text = _clause_for_percentage(sentence, match)
    text = re.sub(r"\s{2,}", " ", text).strip(" .:-")
    text = re.sub(r"^(?:y|e|o|,)\s+", "", text, flags=re.IGNORECASE)
    return text[:260]


def _build_description(block_text: str, sentence: str) -> str:
    text = block_text if len(block_text) >= len(sentence) else sentence
    return _format_description(text, max_length=1400)


def _format_description(text: str, *, max_length: int) -> str:
    clean_text = " ".join((text or "").split())
    if not clean_text:
        return ""
    clean_text = re.sub(r"\s+([,.;:!?])", r"\1", clean_text)
    clean_text = re.sub(r"([¿¡])\s+", r"\1", clean_text)
    clean_text = SENTENCE_BREAK_PATTERN.sub("\n", clean_text)
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
    return clean_text[:max_length].strip()


def _clause_for_percentage(sentence: str, match: re.Match[str]) -> str:
    prefix = sentence[: match.start()]
    conjunction_match = re.search(
        r"\s+(?:y|e|o)\s+(?:un|una|el|la|los|las)?\s*$",
        prefix,
        re.IGNORECASE,
    )
    topic_boundary_matches = list(
        re.finditer(
            r"\s+y\s+(?:el|la)\s+(?:porcentaje|proporcion|proporci[oó]n|cifra|respuesta)\b",
            prefix,
            re.IGNORECASE,
        )
    )
    start = max(
        sentence.rfind(".", 0, match.start()),
        sentence.rfind(";", 0, match.start()),
        sentence.rfind(",", 0, match.start()),
    )
    start = 0 if start < 0 else start + 1
    if topic_boundary_matches and topic_boundary_matches[-1].start() >= start:
        start = topic_boundary_matches[-1].start() + 1
    elif conjunction_match and conjunction_match.start() >= start:
        start = conjunction_match.start()
    y_match = list(
        re.finditer(
            r"\s+y\s+(?:un|el|la)?\s*\d{1,3}(?:[,.]\d{1,2})?\s*%",
            sentence[match.end() :],
            re.IGNORECASE,
        )
    )
    comma = sentence.find(",", match.end())
    semicolon = sentence.find(";", match.end())
    period = sentence.find(".", match.end())
    ends = [value for value in [comma, semicolon, period] if value >= 0]
    next_topic_boundary = re.search(
        r"\s+y\s+(?:el|la)\s+(?:porcentaje|proporcion|proporci[oó]n|cifra|respuesta)\b",
        sentence[match.end() :],
        re.IGNORECASE,
    )
    if next_topic_boundary:
        ends.append(match.end() + next_topic_boundary.start())
    if y_match:
        ends.append(match.end() + y_match[0].start())
    end = min(ends) if ends else len(sentence)
    clause = sentence[start:end].strip()
    if len(clause) < 10:
        return sentence
    return clause


def _is_meaningful_question(question: str) -> bool:
    if len(question) < 12:
        return False
    normalized = normalize_header(question)
    ignored = {
        "base",
        "total",
        "porcentaje",
        "grafico",
        "pagina",
        "indice",
    }
    return normalized not in ignored


def _is_excluded_text(text: str) -> bool:
    normalized = normalize_header(text)
    if normalized.isdigit():
        return True
    if "±" in text:
        return True
    return any(normalize_header(keyword) in normalized for keyword in EXCLUDED_SENTENCE_KEYWORDS)


def _is_excluded_section(section: str) -> bool:
    normalized = normalize_header(section or "")
    return any(normalize_header(keyword) in normalized for keyword in EXCLUDED_SECTION_KEYWORDS)


def _is_relevant_sentence(text: str) -> bool:
    normalized = normalize_header(text)
    return any(normalize_header(keyword) in normalized for keyword in RELEVANT_SENTENCE_KEYWORDS)


def _infer_section_from_sentence(sentence: str) -> str:
    category = _infer_category(sentence)
    return category if category != "Spanish LGBTIQ+ indicators" else ""


def _infer_topic(
    question: str,
    sentence: str,
    description: str,
    section: str,
    fallback: str,
) -> str:
    for text in (question, sentence, description, section):
        normalized = normalize_header(text)
        for keyword, topic in TOPIC_KEYWORDS:
            if keyword in normalized:
                return topic
    return fallback or "Spanish LGBTIQ+ indicators"



def _looks_like_heading(value: str) -> bool:
    if not value or len(value) > 180:
        return False
    if "?" in value or value.startswith(("(", "¿")):
        return False
    if value[0].islower():
        return False
    if PERCENT_PATTERN.search(value):
        return False
    words = value.split()
    if len(words) > 22:
        return False
    normalized = normalize_header(value)
    if not normalized or normalized.isdigit():
        return False
    if SECTION_NUMBER_PATTERN.match(value):
        return True
    if any(normalized.startswith(normalize_header(prefix)) for prefix in KNOWN_SECTION_PREFIXES):
        return True
    if value.rstrip().endswith((".", "!", "?")) and len(value) > 80:
        return False
    if len(words) > 12:
        return False
    return any(normalize_header(keyword) in normalized for keyword in HEADING_KEYWORDS)


def _looks_like_side_heading_block(block: dict[str, Any]) -> bool:
    value = str(block.get("text") or "").strip()
    if not value or value[0].islower() or PERCENT_PATTERN.search(value):
        return False
    if float(block.get("x1") or 0) > 225:
        return False
    if value.rstrip().endswith((".", "!", "?")):
        return False
    words = value.split()
    if not 2 <= len(words) <= 24:
        return False
    normalized = normalize_header(value)
    return not (normalized.isdigit() or _is_excluded_section(value))


def _infer_category(text: str) -> str:
    normalized = normalize_header(text)
    for keyword, category in CATEGORY_KEYWORDS:
        if keyword in normalized:
            return category
    return "Spanish LGBTIQ+ indicators"


def _build_code(year: int, report_title: str, question: str, percentage: float, page: int) -> str:
    seed = f"{FELGTBI_SOURCE_CODE}|{year}|{report_title}|{page}|{question}|{percentage}"
    digest = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"felgtbi_{digest}"


def _build_subsection_code(
    year: int,
    report_title: str,
    subsection: str,
    caption: str,
    page: int,
) -> str:
    seed = f"{FELGTBI_SOURCE_CODE}|html|{year}|{report_title}|{page}|{subsection}|{caption}"
    digest = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"felgtbi_{digest}"
