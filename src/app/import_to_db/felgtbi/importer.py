from __future__ import annotations

import hashlib
import html
import io
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from bson import ObjectId

from app.import_to_db.utils import normalize_header, parse_float

FELGTBI_SOURCE_CODE = "felgtbi_estado_lgtbi"
FELGTBI_SOURCE_NAME = "FELGTBI+ Estado LGBTIQ+"
SPAIN_COUNTRY = "Spain"
SPAIN_COUNTRY_CODE = "ES"
FELGTBI_ASSET_ROOT = (
    Path(__file__).resolve().parents[2] / "dash" / "assets" / "generated" / "felgtbi"
)
FELGTBI_ASSET_URL_PREFIX = "/assets/generated/felgtbi"
DEFAULT_SUPABASE_STORAGE_BUCKET = "felgtbi-reports"
FIGURE_IMAGE_MIME_TYPE = "image/webp"
FIGURE_IMAGE_EXTENSION = "webp"

YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
PERCENT_PATTERN = re.compile(r"(?<!\d)(\d{1,3}(?:[,.]\d{1,2})?)\s*%")
NUMBER_PATTERN = re.compile(r"(?<![\w])\d{1,4}(?:[,.]\d{1,2})?(?![\w])")
TOC_ENTRY_PATTERN = re.compile(r"^(?P<title>.+?)\s+\.{3,}\s*(?P<page>\d{1,3})$")
TOC_DOTS_PAGE_PATTERN = re.compile(r"^\.{3,}\s*(?P<page>\d{1,3})$")
FIGURE_CAPTION_PATTERN = re.compile(
    r"^\s*(?P<label>Figura|Gr[aá]fico)\s+(?P<number>\d+(?:\.\d+)?)[.:]?\s*(?P<title>.+)?$",
    re.IGNORECASE,
)
FIGURE_NUMBER_REFERENCE_PATTERN = re.compile(
    r"\b(?:Figura|Gr[aá]fico)\s+(?P<number>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
SECTION_NUMBER_PATTERN = re.compile(r"^\d{1,2}(?:\.\d+)*\.?\s+.+")
SENTENCE_BREAK_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜÑ¿¡])")
FIGURE_REFERENCE_PATTERN = re.compile(r"\bFigura\s+\d+(?:\.\d+)?[.:]?\s*", re.IGNORECASE)
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


def parse_felgtbi_pdf(file_path: Path | str, *, year: int | None = None) -> list[dict]:
    path = Path(file_path)
    return parse_felgtbi_pdf_bytes(path.read_bytes(), file_name=path.name, year=year)


def parse_felgtbi_pdf_bytes(
    pdf_bytes: bytes,
    *,
    file_name: str = "felgtbi.pdf",
    year: int | None = None,
) -> list[dict]:
    pages = extract_pdf_pages(pdf_bytes)
    documents = parse_felgtbi_text_pages(pages, file_name=file_name, year=year)
    _attach_source_document_metadata(
        documents,
        file_name=file_name,
        source_document_id=_build_pdf_source_document_id(pdf_bytes, file_name),
        overwrite_document_id=True,
    )
    _attach_page_assets(pdf_bytes, file_name, documents)
    _refresh_content_html(documents)
    return documents


def extract_pdf_pages(pdf_bytes: bytes) -> list[dict[str, Any]]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("missing_pdf_dependency") from exc

    pages: list[dict[str, Any]] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for index, page in enumerate(document, start=1):
            text_blocks = page.get_text("blocks")
            dict_blocks = page.get_text("dict").get("blocks", [])
            pages.append(
                {
                    "page": index,
                    "text": page.get_text("text"),
                    "blocks": [
                        {
                            "x0": block[0],
                            "y0": block[1],
                            "x1": block[2],
                            "y1": block[3],
                            "text": block[4],
                        }
                        for block in text_blocks
                        if len(block) >= 5
                    ],
                    "figures": _extract_page_figures(dict_blocks),
                }
            )
    return pages


def _attach_page_assets(pdf_bytes: bytes, file_name: str, documents: list[dict]) -> None:
    asset_documents = [
        document
        for document in documents
        if isinstance(document.get("visual_context"), dict)
        and (document.get("visual_context") or {}).get("bbox")
    ]
    if not asset_documents:
        return

    try:
        import fitz
    except ImportError:
        return

    FELGTBI_ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    rendered_assets: dict[str, dict[str, Any]] = {}

    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf_document:
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
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(2.0, 2.0),
                clip=rect,
                alpha=False,
            )
            image_bytes, width, height, mime_type, extension = _pixmap_image_bytes(pixmap)
            checksum = hashlib.sha256(image_bytes).hexdigest()
            upload = _upload_figure_to_supabase(
                image_bytes=image_bytes,
                storage_path=storage_path,
                mime_type=mime_type,
                checksum=checksum,
            )
            uploaded_asset_url = str(upload.get("public_url") or upload.get("signed_url") or "")
            if uploaded_asset_url:
                rendered_assets[asset_id] = {
                    **upload,
                    "asset_url": uploaded_asset_url,
                    "width": width,
                    "height": height,
                    "size": len(image_bytes),
                    "checksum": checksum,
                }
                continue

            asset_name = _local_asset_name(storage_path, checksum, extension)
            asset_path = FELGTBI_ASSET_ROOT / asset_name
            if not asset_path.exists():
                asset_path.write_bytes(image_bytes)
            rendered_assets[asset_id] = {
                **upload,
                "status": "failed",
                "bucket": upload.get("bucket") or _supabase_storage_bucket(),
                "storage_path": storage_path,
                "public_url": "",
                "asset_url": f"{FELGTBI_ASSET_URL_PREFIX}/{asset_name}",
                "mime_type": mime_type,
                "width": width,
                "height": height,
                "size": len(image_bytes),
                "checksum": checksum,
                "fallback_storage": "dash_asset",
            }

    for document in documents:
        context = document.get("visual_context")
        if not isinstance(context, dict):
            continue
        page_number = int(context.get("page") or 0)
        bbox = _safe_bbox(context.get("bbox"))
        storage_path = _figure_storage_path(document, file_name)
        asset_id = f"{page_number}:{','.join(str(value) for value in bbox)}:{storage_path}" if bbox else ""
        asset = rendered_assets.get(asset_id)
        if not asset:
            continue
        asset_url = str(asset.get("public_url") or asset.get("asset_url") or "")
        context["asset_url"] = asset_url
        context["image_storage"] = "supabase" if asset.get("public_url") or asset.get("signed_url") else "dash_asset"
        context["image_upload"] = {
            "status": asset.get("status") or "failed",
            "error": asset.get("error"),
            "bucket": asset.get("bucket"),
            "storage_path": asset.get("storage_path"),
            "public_url": asset.get("public_url"),
            "signed_url": asset.get("signed_url"),
            "url_type": asset.get("url_type"),
            "signed_url_expires_in": asset.get("signed_url_expires_in"),
            "mime_type": asset.get("mime_type"),
            "size": asset.get("size"),
            "checksum": asset.get("checksum"),
            "width": asset.get("width"),
            "height": asset.get("height"),
        }
        figure = document.get("figure")
        if isinstance(figure, dict):
            figure.update(
                {
                    "bucket": asset.get("bucket"),
                    "storage_path": asset.get("storage_path"),
                    "public_url": asset.get("public_url") or "",
                    "signed_url": asset.get("signed_url") or "",
                    "url_type": asset.get("url_type"),
                    "signed_url_expires_in": asset.get("signed_url_expires_in"),
                    "image_path": asset_url,
                    "asset_url": asset_url,
                    "mime_type": asset.get("mime_type"),
                    "size": asset.get("size"),
                    "checksum": asset.get("checksum"),
                    "width": asset.get("width"),
                    "height": asset.get("height"),
                    "upload": {
                        "status": asset.get("status") or "failed",
                        "error": asset.get("error"),
                    },
                }
            )


def _safe_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        bbox = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return [round(item, 2) for item in bbox]


def _pixmap_image_bytes(pixmap: Any) -> tuple[bytes, int, int, str, str]:
    try:
        from PIL import Image
    except ImportError:
        return pixmap.tobytes("png"), int(pixmap.width), int(pixmap.height), "image/png", "png"

    mode = "RGBA" if getattr(pixmap, "alpha", 0) else "RGB"
    image = Image.frombytes(mode, (int(pixmap.width), int(pixmap.height)), pixmap.samples)
    if image.mode != "RGB":
        image = image.convert("RGB")
    output = io.BytesIO()
    image.save(output, format="WEBP", quality=90, method=6)
    return output.getvalue(), image.width, image.height, FIGURE_IMAGE_MIME_TYPE, FIGURE_IMAGE_EXTENSION


def _upload_figure_to_supabase(
    *,
    image_bytes: bytes,
    storage_path: str,
    mime_type: str,
    checksum: str,
) -> dict[str, Any]:
    config = _supabase_storage_config()
    if not config:
        return {
            "status": "failed",
            "error": "supabase_storage_not_configured",
            "bucket": _supabase_storage_bucket(),
            "storage_path": storage_path,
        }
    try:
        import boto3
    except ImportError:
        return {
            "status": "failed",
            "error": "boto3_not_installed",
            "bucket": config["bucket"],
            "storage_path": storage_path,
        }

    client = boto3.client(
        "s3",
        endpoint_url=config["endpoint"],
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        region_name=config["region"],
    )
    status = "uploaded"
    try:
        existing = client.head_object(Bucket=config["bucket"], Key=storage_path)
        metadata = existing.get("Metadata") or {}
        if metadata.get("checksum") == checksum:
            status = "reused"
        else:
            client.put_object(
                Bucket=config["bucket"],
                Key=storage_path,
                Body=image_bytes,
                ContentType=mime_type,
                CacheControl="public, max-age=31536000, immutable",
                Metadata={"checksum": checksum},
            )
    except Exception:
        try:
            client.put_object(
                Bucket=config["bucket"],
                Key=storage_path,
                Body=image_bytes,
                ContentType=mime_type,
                CacheControl="public, max-age=31536000, immutable",
                Metadata={"checksum": checksum},
            )
        except Exception as exc:
            return {
                "status": "failed",
                "error": exc.__class__.__name__,
                "bucket": config["bucket"],
                "storage_path": storage_path,
            }

    bucket_is_public = _supabase_bucket_is_public(config["bucket"])
    public_url = _supabase_public_url(config["bucket"], storage_path) if bucket_is_public is True else ""
    signed_url = ""
    signed_url_expires_in = None
    url_type = "public" if public_url else ""
    if bucket_is_public is False:
        signed_url_expires_in = int(os.getenv("SUPABASE_SIGNED_URL_EXPIRES_IN", "3600") or 3600)
        try:
            signed_url = _supabase_signed_url(
                config["bucket"],
                storage_path,
                expires_in=signed_url_expires_in,
            )
            url_type = "signed"
        except Exception:
            signed_url = ""
    return {
        "status": status,
        "error": None,
        "bucket": config["bucket"],
        "storage_path": storage_path,
        "public_url": public_url,
        "signed_url": signed_url,
        "url_type": url_type,
        "signed_url_expires_in": signed_url_expires_in,
        "mime_type": mime_type,
    }


def _supabase_storage_config() -> dict[str, str] | None:
    endpoint = os.getenv("SUPABASE_S3_ENDPOINT", "").strip()
    access_key = os.getenv("SUPABASE_S3_ACCESS_KEY", "").strip()
    secret_key = os.getenv("SUPABASE_S3_SECRET_KEY", "").strip()
    if not endpoint or not access_key or not secret_key:
        return None
    return {
        "bucket": _supabase_storage_bucket(),
        "endpoint": endpoint,
        "access_key": access_key,
        "secret_key": secret_key,
        "region": os.getenv("SUPABASE_S3_REGION", "us-east-1").strip() or "us-east-1",
    }


def _supabase_storage_bucket() -> str:
    return os.getenv("SUPABASE_STORAGE_BUCKET", DEFAULT_SUPABASE_STORAGE_BUCKET).strip() or DEFAULT_SUPABASE_STORAGE_BUCKET


def _supabase_bucket_is_public(bucket: str) -> bool | None:
    configured = os.getenv("SUPABASE_STORAGE_PUBLIC", "").strip().lower()
    if configured in {"1", "true", "yes", "public"}:
        return True
    if configured in {"0", "false", "no", "private"}:
        return False

    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url or not service_key:
        return None
    request = Request(
        f"{supabase_url}/storage/v1/bucket/{quote(bucket, safe='')}",
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    is_public = payload.get("public")
    return bool(is_public) if isinstance(is_public, bool) else None


def _supabase_public_url(bucket: str, storage_path: str) -> str:
    configured_base = os.getenv("SUPABASE_STORAGE_PUBLIC_BASE_URL", "").strip()
    if configured_base:
        base = configured_base.rstrip("/")
        return f"{base}/{quote(storage_path, safe='/')}"
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    if not supabase_url:
        return ""
    return f"{supabase_url}/storage/v1/object/public/{quote(bucket, safe='')}/{quote(storage_path, safe='/')}"


def _supabase_signed_url(bucket: str, storage_path: str, *, expires_in: int) -> str:
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url or not service_key:
        return ""
    body = json.dumps({"expiresIn": int(expires_in)}).encode("utf-8")
    request = Request(
        f"{supabase_url}/storage/v1/object/sign/{quote(bucket, safe='')}/{quote(storage_path, safe='/')}",
        data=body,
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    signed_url = str(payload.get("signedURL") or payload.get("signedUrl") or "").strip()
    if not signed_url:
        return ""
    if signed_url.startswith("http://") or signed_url.startswith("https://"):
        return signed_url
    return f"{supabase_url}/storage/v1{signed_url if signed_url.startswith('/') else '/' + signed_url}"


def _figure_storage_path(document: dict[str, Any], file_name: str) -> str:
    year = str(document.get("year") or _extract_year(file_name) or "unknown")
    report_slug = _slugify(str(document.get("report_title") or Path(file_name).stem or "felgtbi"))
    section_slug = _slugify(
        str(document.get("section_title") or document.get("specific_category") or "seccion")
    )
    figure_number = str(document.get("figure_number") or (document.get("figure") or {}).get("number") or "")
    figure_slug = _figure_file_stem(figure_number)
    return f"{year}/{report_slug}/{section_slug}/{figure_slug}.{FIGURE_IMAGE_EXTENSION}"


def _figure_file_stem(figure_number: str) -> str:
    number = re.sub(r"[^0-9]+", "-", figure_number).strip("-")
    return f"figura-{number}" if number else "figura"


def _local_asset_name(storage_path: str, checksum: str, extension: str) -> str:
    base = storage_path.replace("/", "_").replace("\\", "_")
    base = re.sub(rf"\.{re.escape(extension)}$", "", base, flags=re.IGNORECASE)
    return f"{base}_{checksum[:10]}.{extension}"


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug) or "felgtbi"


def _asset_key(pdf_bytes: bytes, file_name: str) -> str:
    digest = hashlib.sha1()
    digest.update(str(file_name or "felgtbi.pdf").encode("utf-8", errors="ignore"))
    digest.update(pdf_bytes)
    return digest.hexdigest()[:16]


def _build_pdf_source_document_id(pdf_bytes: bytes, file_name: str) -> str:
    digest = hashlib.sha1()
    digest.update(_safe_original_filename(file_name).encode("utf-8", errors="ignore"))
    digest.update(pdf_bytes)
    return f"felgtbi_pdf_{digest.hexdigest()[:16]}"


def _build_metadata_source_document_id(file_name: str, year: int, report_title: str) -> str:
    seed = f"{_safe_original_filename(file_name)}|{year}|{report_title}"
    digest = hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"felgtbi_pdf_{digest}"


def _safe_original_filename(file_name: str) -> str:
    clean_name = str(file_name or "felgtbi.pdf").replace("\\", "/").rstrip("/")
    clean_name = clean_name.rsplit("/", 1)[-1].strip()
    return clean_name or "felgtbi.pdf"


def _attach_source_document_metadata(
    documents: list[dict],
    *,
    file_name: str,
    source_document_id: str,
    overwrite_document_id: bool = False,
) -> None:
    original_filename = _safe_original_filename(file_name)
    for document in documents:
        if not isinstance(document, dict):
            continue
        document["original_filename"] = str(document.get("original_filename") or original_filename)
        if overwrite_document_id or not document.get("source_document_id"):
            document["source_document_id"] = source_document_id
        document["import_status"] = str(document.get("import_status") or "processed")


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
            _attach_source_document_metadata(
                documents,
                file_name=file_name,
                source_document_id=_build_metadata_source_document_id(file_name, resolved_year, report_title),
            )
            _refresh_content_html(documents)
            return documents

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
        source_document_id=_build_metadata_source_document_id(file_name, resolved_year, report_title),
    )
    return documents


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
        if document["code"] in seen_codes:
            continue
        seen_codes.add(document["code"])
        documents.append(document)
    return documents


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
    description = _paragraphs_plain_summary(paragraphs) or _data_points_plain_summary(data_points) or subsection
    document = {
        "id": str(ObjectId()),
        "source": FELGTBI_SOURCE_CODE,
        "year": year,
        "report_title": report_title,
        "report_type": report_type,
        "category": category,
        "specific_category": section or category,
        "section_title": section or category,
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
            "image_path": "",
            "source": figure_source,
        },
        "content_html": "",
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
        context = document.get("visual_context")
        figure = document.get("figure")
        if isinstance(figure, dict) and isinstance(context, dict):
            asset_url = str(context.get("asset_url") or "")
            if asset_url:
                figure["image_path"] = asset_url
                figure["asset_url"] = asset_url
        document["content_html"] = _build_content_html(
            section=str(document.get("section_title") or document.get("specific_category") or ""),
            subsection=str(document.get("subsection_title") or document.get("question") or ""),
            visual_context=document.get("visual_context"),
            figure=document.get("figure"),
            paragraphs_before=(
                document.get("paragraphs_before_figure")
                if isinstance(document.get("paragraphs_before_figure"), list)
                else []
            ),
            paragraphs_after=(
                document.get("paragraphs_after_figure")
                if isinstance(document.get("paragraphs_after_figure"), list)
                else []
            ),
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
    asset_url = str(context.get("asset_url") or "")
    if asset_url:
        parts.append(
            '<figure class="report-figure">\n'
            '<img src="{src}" alt="{alt}" loading="lazy">\n'
            '<figcaption>{caption}</figcaption>\n'
            "</figure>".format(
                src=html.escape(asset_url, quote=True),
                alt=html.escape(_figure_alt_text(caption, subsection), quote=True),
                caption=html.escape(caption or subsection or "Figura"),
            )
        )
    elif caption:
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
    paragraph = " ".join(str(text or "").split()).strip(" .:-")
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


def _extract_year(text: str) -> int | None:
    match = YEAR_PATTERN.search(text or "")
    return int(match.group(1)) if match else None


def _resolve_report_title(full_text: str, file_name: str) -> str:
    lines = _clean_lines(full_text)
    for line in lines[:60]:
        normalized = normalize_header(line)
        if "estado_lgtbi" in normalized or "estado_lgbti" in normalized:
            return line[:160]
    stem = Path(file_name).stem.replace("-", " ").replace("_", " ").strip()
    return stem[:160] or FELGTBI_SOURCE_NAME


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
    return [
        " ".join(line.strip().split())
        for line in text.splitlines()
        if line and line.strip()
    ]


def _extract_page_figures(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("type") != 1:
            continue
        bbox = block.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        x0, y0, x1, y1 = [float(value) for value in bbox]
        width = x1 - x0
        height = y1 - y0
        if width < 80 or height < 60:
            continue
        if x0 < 5 and y0 < 5 and width > 550 and height > 780:
            continue
        if y0 < 90 and height < 100:
            continue
        figures.append(
            {
                "kind": "figure",
                "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
            }
        )
    return figures


def _build_visual_context(
    page: int,
    bbox: list[float] | None,
    caption: str,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "page": page,
        "kind": "pdf_figure" if bbox else "pdf_text",
        "image_storage": "reference_only",
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
        int(segment.get("page") or 0),
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
            match = FIGURE_CAPTION_PATTERN.match(block["text"])
            if match:
                captions.append(
                    {
                        "page": page_number,
                        "x0": block["x0"],
                        "y0": block["y0"],
                        "x1": block["x1"],
                        "y1": block["y1"],
                        "figure_number": match.group("number"),
                        "caption_title": _clean_figure_caption_title(block["text"]),
                        "caption": block["text"],
                    }
                )

    segments: list[dict[str, Any]] = []
    for index, caption in enumerate(captions):
        previous_caption = captions[index - 1] if index > 0 else None
        next_caption = captions[index + 1] if index + 1 < len(captions) else None
        bbox = _figure_bbox_for_caption(pages, caption, next_caption)
        before_description, after_description = _figure_text_parts(
            pages,
            caption,
            next_caption,
            previous_caption,
            toc_sections or [],
        )
        description = _format_description(
            " ".join([before_description, after_description]),
            max_length=6000,
        )
        if not bbox and not description:
            continue
        segments.append(
            {
                "page": caption["page"],
                "y0": caption["y0"],
                "figure_number": caption["figure_number"],
                "caption_title": caption["caption_title"],
                "caption": caption["caption"],
                "bbox": bbox,
                "source": _figure_source(pages, caption, next_caption),
                "before_description": before_description,
                "after_description": after_description,
                "description": description or caption["caption"],
                "next_page": next_caption["page"] if next_caption else None,
                "next_y0": next_caption["y0"] if next_caption else None,
            }
        )
    return segments


def _figure_bbox_for_caption(
    pages: list[dict[str, Any]],
    caption: dict[str, Any],
    next_caption: dict[str, Any] | None,
) -> list[float] | None:
    page = _page_by_number(pages, int(caption["page"]))
    if not page:
        return None
    page_number = int(caption["page"])
    caption_y1 = float(caption["y1"])
    next_y0 = (
        float(next_caption["y0"])
        if next_caption and int(next_caption["page"]) == page_number
        else 760.0
    )
    image_bbox = _nearest_image_bbox(page, caption_y1, next_y0)
    if image_bbox:
        return image_bbox

    source_y0 = _next_source_y0(page, caption_y1, next_y0)
    bottom = source_y0 - 6 if source_y0 else next_y0 - 6
    top = caption_y1 + 4
    if bottom - top < 80:
        return None
    return [70.0, round(top, 2), 525.0, round(bottom, 2)]


def _nearest_image_bbox(page: dict[str, Any], caption_y1: float, next_y0: float) -> list[float] | None:
    figures = page.get("figures")
    if not isinstance(figures, list):
        return None
    candidates: list[list[float]] = []
    for figure in figures:
        if not isinstance(figure, dict):
            continue
        bbox = _safe_bbox(figure.get("bbox"))
        if not bbox:
            continue
        if bbox[1] >= caption_y1 - 8 and bbox[3] <= next_y0 + 8:
            candidates.append(bbox)
            continue
        if bbox[3] <= caption_y1 + 8 and caption_y1 - bbox[3] <= 520:
            candidates.append(bbox)
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda bbox: (abs(bbox[1] - caption_y1), -(bbox[2] - bbox[0]) * (bbox[3] - bbox[1])),
    )[0]


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
                elif not before_caption_context_seen:
                    continue
                elif _mentions_other_figure_number(block["text"], figure_number):
                    continue
                elif _section_changed(toc_sections, caption_section, page_number):
                    continue
            if next_caption and page_number == end_page and block["y0"] >= next_caption["y0"]:
                continue
            text = block["text"]
            normalized = normalize_header(text)
            if normalized.isdigit():
                continue
            if _is_figure_caption_text(text):
                continue
            if position > caption_position and _section_changed(toc_sections, caption_section, page_number):
                if not _mentions_figure_number(text, figure_number):
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
            if position < caption_position:
                before_fragments.append(text)
            else:
                after_fragments.append(text)
    return (
        _format_description(" ".join(before_fragments), max_length=3000),
        _format_description(" ".join(after_fragments), max_length=3000),
    )


def _figure_description(
    pages: list[dict[str, Any]],
    caption: dict[str, Any],
    next_caption: dict[str, Any] | None,
    previous_caption: dict[str, Any] | None,
    toc_sections: list[dict[str, Any]],
) -> str:
    before_text, after_text = _figure_text_parts(
        pages,
        caption,
        next_caption,
        previous_caption,
        toc_sections,
    )
    return _format_description(f"{before_text} {after_text}", max_length=6000)


def _clean_figure_caption_title(text: str) -> str:
    match = FIGURE_CAPTION_PATTERN.match(text)
    if not match:
        return _clean_section_title(text)
    title = str(match.group("title") or "").strip(" .:-")
    return _truncate_at_word_boundary(title, 180) if title else ""


def _is_figure_caption_text(text: str) -> bool:
    return bool(FIGURE_CAPTION_PATTERN.match(str(text or "").strip()))


def _mentions_figure_number(text: str, figure_number: str) -> bool:
    if not figure_number:
        return False
    return figure_number in _mentioned_figure_numbers(text)


def _mentions_other_figure_number(text: str, figure_number: str) -> bool:
    numbers = _mentioned_figure_numbers(text)
    return bool(numbers and any(number != figure_number for number in numbers))


def _mentioned_figure_numbers(text: str) -> set[str]:
    return {
        match.group("number")
        for match in FIGURE_NUMBER_REFERENCE_PATTERN.finditer(str(text or ""))
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
    for page in pages[:6]:
        lines = _clean_lines(str(page.get("text") or ""))
        if not any(normalize_header(line) == "contenido" for line in lines[:5]):
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
            match = TOC_ENTRY_PATTERN.match(line)
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
    return sorted(sections, key=lambda item: int(item["start_page"]))


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
    if len(value.split()) < 3 and not SECTION_NUMBER_PATTERN.match(value):
        return True
    return False


def _clean_section_title(value: str) -> str:
    title = " ".join((value or "").split()).strip(" .:-")
    if not title:
        return ""
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
        if start_page > page + 1:
            break
        if start_page <= page + 1:
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
        }
        for index, line in enumerate(_clean_lines(str(page.get("text") or "")))
    ]


def _page_text_block_entries(page: dict[str, Any]) -> list[dict[str, Any]]:
    cleaned_blocks = _merge_left_heading_fragments(_raw_text_block_entries(page))
    if cleaned_blocks:
        merged_blocks: list[dict[str, Any]] = []
        for block in cleaned_blocks:
            text = block["text"]
            if merged_blocks and _should_merge_spatial_heading_blocks(merged_blocks[-1], block):
                merged_blocks[-1]["text"] = f"{merged_blocks[-1]['text']} {text}"
                merged_blocks[-1]["x1"] = max(float(merged_blocks[-1]["x1"]), float(block["x1"]))
                merged_blocks[-1]["y1"] = max(float(merged_blocks[-1]["y1"]), float(block["y1"]))
            elif (
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


def _page_text_blocks(page: dict[str, Any]) -> list[str]:
    return [block["text"] for block in _page_text_block_entries(page)]


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
    if gap > 14:
        return False
    return True


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
    if gap < -2 or gap > 8:
        return False
    return True


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
    y_match = list(re.finditer(r"\s+y\s+(?:un|el|la)?\s*\d{1,3}(?:[,.]\d{1,2})?\s*%", sentence[match.end() :], re.IGNORECASE))
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


def _section_from_previous_lines(lines: list[str], index: int) -> str:
    for position in range(index - 1, max(index - 8, -1), -1):
        candidate = lines[position].strip()
        if _looks_like_heading(candidate):
            return _clean_section_title(candidate)[:120]
    return ""


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
    if normalized.isdigit() or _is_excluded_section(value):
        return False
    return True


def _infer_category(text: str) -> str:
    normalized = normalize_header(text)
    for keyword, category in CATEGORY_KEYWORDS:
        if keyword in normalized:
            return category
    return "Spanish LGBTIQ+ indicators"


def _build_code(year: int, report_title: str, question: str, percentage: float, page: int) -> str:
    seed = f"{FELGTBI_SOURCE_CODE}|{year}|{report_title}|{page}|{question}|{percentage}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"felgtbi_{digest}"


def _build_subsection_code(
    year: int,
    report_title: str,
    subsection: str,
    caption: str,
    page: int,
) -> str:
    seed = f"{FELGTBI_SOURCE_CODE}|html|{year}|{report_title}|{page}|{subsection}|{caption}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"felgtbi_{digest}"
