from __future__ import annotations

import os
from typing import Any

from app.import_to_db.felgtbi.models import PdfExtractionError


def extract_pdf_pages(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """Extract ordered text, style hints and visual regions without image payloads."""
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("missing_pdf_dependency") from exc
    pages: list[dict[str, Any]] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        if document.needs_pass:
            raise PdfExtractionError("encrypted_pdf_not_supported")
        maximum_pages = max(1, int(os.getenv("PDF_MAX_PAGES", "500")))
        if document.page_count > maximum_pages:
            raise PdfExtractionError("pdf_page_limit_exceeded")
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            text_dict_flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES
            text_page = page.get_textpage(flags=text_dict_flags)
            text_blocks = page.get_text("blocks", textpage=text_page)
            page_dict = page.get_text("dict", textpage=text_page)
            dict_blocks = page_dict.get("blocks", []) if isinstance(page_dict, dict) else []
            image_blocks = [
                {"type": 1, "bbox": image.get("bbox")}
                for image in page.get_image_info(hashes=False, xrefs=False)
                if isinstance(image, dict)
            ]
            page_width = float(page.rect.width)
            page_height = float(page.rect.height)
            visual_regions = [
                *extract_page_figures(image_blocks, kind="figure"),
                *extract_page_vector_regions(page, page_width, page_height),
            ]
            pages.append(
                {
                    "page": page_index + 1,
                    "text": page.get_text("text", textpage=text_page),
                    "blocks": [
                        {
                            "x0": block[0], "y0": block[1], "x1": block[2], "y1": block[3],
                            "text": block[4], **text_block_style(dict_blocks, block),
                        }
                        for block in text_blocks if len(block) >= 5
                    ],
                    "figures": deduplicate_visual_regions(visual_regions),
                    "width": page_width,
                    "height": page_height,
                }
            )
            del text_page, page_dict, dict_blocks, image_blocks, text_blocks, visual_regions, page
    return pages


def text_block_style(dict_blocks: list[dict[str, Any]], text_block: Any) -> dict[str, Any]:
    if len(text_block) < 4:
        return {}
    block_bbox = [float(text_block[index]) for index in range(4)]
    best: dict[str, Any] | None = None
    best_overlap = 0.0
    for candidate in dict_blocks:
        if candidate.get("type") != 0:
            continue
        bbox = safe_bbox(candidate.get("bbox"))
        if bbox is None:
            continue
        overlap = bbox_overlap_area(block_bbox, bbox)
        if overlap > best_overlap:
            best, best_overlap = candidate, overlap
    if best is None:
        return {}
    spans = [
        span for line in best.get("lines", []) if isinstance(line, dict)
        for span in line.get("spans", []) if isinstance(span, dict)
    ]
    if not spans:
        return {}
    fonts = [str(span.get("font") or "") for span in spans]
    return {
        "font_size": round(max(float(span.get("size") or 0) for span in spans), 2),
        "is_bold": any("bold" in font.casefold() for font in fonts),
        "is_italic": any("italic" in font.casefold() for font in fonts),
    }


def extract_page_figures(
    blocks: list[dict[str, Any]], *, kind: str = "figure"
) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("type") != 1:
            continue
        bbox = block.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        x0, y0, x1, y1 = [float(value) for value in bbox]
        width, height = x1 - x0, y1 - y0
        if width < 80 or height < 60:
            continue
        if x0 < 5 and y0 < 5 and width > 550 and height > 780:
            continue
        if y0 < 90 and height < 100:
            continue
        figures.append(
            {"kind": kind, "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]}
        )
    return figures


def extract_page_vector_regions(
    page: Any, page_width: float, page_height: float
) -> list[dict[str, Any]]:
    try:
        regions = page.cluster_drawings()
    except (AttributeError, RuntimeError, ValueError):
        return []
    page_area = max(page_width * page_height, 1.0)
    figures: list[dict[str, Any]] = []
    for region in regions:
        try:
            x0, y0, x1, y1 = map(float, (region.x0, region.y0, region.x1, region.y1))
        except (AttributeError, TypeError, ValueError):
            continue
        width, height = x1 - x0, y1 - y0
        if width < 80 or height < 60 or (width * height) / page_area >= 0.8:
            continue
        if y0 < 70 and height < 100:
            continue
        figures.append(
            {"kind": "vector", "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]}
        )
    return figures


def deduplicate_visual_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for region in regions:
        bbox = safe_bbox(region.get("bbox"))
        if bbox is None:
            continue
        duplicate = False
        for existing in result:
            existing_bbox = safe_bbox(existing.get("bbox"))
            if existing_bbox is None:
                continue
            smaller_area = min(bbox_area(bbox), bbox_area(existing_bbox))
            if smaller_area > 0 and bbox_overlap_area(bbox, existing_bbox) / smaller_area >= 0.94:
                duplicate = True
                break
        if not duplicate:
            result.append({"kind": str(region.get("kind") or "visual"), "bbox": bbox})
    return result


def safe_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        bbox = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return [round(item, 2) for item in bbox]


def bbox_overlap_area(first: list[float], second: list[float]) -> float:
    width = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
    height = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
    return width * height


def bbox_area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
