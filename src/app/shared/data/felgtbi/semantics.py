from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

TOKEN_PATTERN = re.compile(r"\d{1,4}(?:[.,]\d+)?\s*%?|[^\W\d_]+", re.UNICODE)
NUMERIC_TOKEN_PATTERN = re.compile(r"^\d{1,4}(?:[.,]\d+)?\s*%?$", re.UNICODE)
YEAR_TOKEN_PATTERN = re.compile(r"^(?:19|20)\d{2}$")
CAPTION_PREFIX_PATTERN = re.compile(
    r"^\s*(?:figura|gr[aá]fico|tabla)\s*\d+(?:\.\d+)?\s*[:.\-]?\s*",
    re.IGNORECASE,
)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
HTML_PARAGRAPH_PATTERN = re.compile(r"<p(?:\s[^>]*)?>(?P<body>.*?)</p>", re.IGNORECASE | re.DOTALL)
SENTENCE_END_PATTERN = re.compile(r"[.!?](?:[\s\"'»)]|$)")
URL_PATTERN = re.compile(r"(?:https?://|www\.|chrome-extension://)\S+", re.IGNORECASE)
FOOTER_PATTERN = re.compile(
    r"^\s*(?:p[aá]gina\s+)?\d{1,3}\s*$|"
    r"(?:©|copyright|todos\s+los\s+derechos\s+reservados)|"
    r"^\s*(?:m[aá]s\s+informaci[oó]n|isbn|dep[oó]sito\s+legal)\b",
    re.IGNORECASE,
)
CONTACT_PATTERN = re.compile(
    r"(?:\binfo@|\+34\s*\d|\bcalle\s+[A-ZÁÉÍÓÚÜÑ]|\bcontacto\b)",
    re.IGNORECASE,
)

FUNCTION_WORDS = {
    "a",
    "al",
    "ante",
    "como",
    "con",
    "de",
    "del",
    "desde",
    "durante",
    "el",
    "ella",
    "ellas",
    "ellos",
    "en",
    "entre",
    "es",
    "esta",
    "este",
    "la",
    "las",
    "lo",
    "los",
    "más",
    "menos",
    "para",
    "pero",
    "por",
    "que",
    "se",
    "según",
    "sin",
    "sobre",
    "su",
    "sus",
    "un",
    "una",
    "y",
    "ya",
    "the",
    "of",
    "and",
    "in",
    "to",
    "with",
    "from",
    "for",
}
VERB_WORDS = {
    "alcanza",
    "aumenta",
    "considera",
    "conserva",
    "constituye",
    "declara",
    "define",
    "destaca",
    "disminuye",
    "encuentra",
    "es",
    "está",
    "están",
    "fue",
    "han",
    "hay",
    "incluye",
    "indica",
    "muestra",
    "percibe",
    "perciben",
    "presenta",
    "representa",
    "señala",
    "son",
    "supone",
    "tiene",
}
CHART_LABEL_WORDS = {
    "año",
    "años",
    "categoría",
    "categorías",
    "edad",
    "eje",
    "grupo",
    "media",
    "minoría",
    "mujer",
    "mujeres",
    "hombre",
    "hombres",
    "ns",
    "nc",
    "total",
}


@dataclass(frozen=True)
class ExtractionContext:
    near_figure: bool = False
    inside_figure: bool = False
    overlaps_figure: bool = False
    position: str = "unknown"
    caption: str = ""
    figure_source: str = ""
    detected_image_texts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResidualTextAnalysis:
    is_residual: bool
    score: int
    confidence: float
    reasons: tuple[str, ...]
    numeric_token_ratio: float
    percentage_count: int
    has_semantic_sentence: bool


@dataclass(frozen=True)
class CleanedParagraphs:
    before: list[str]
    after: list[str]
    removed: list[tuple[str, ResidualTextAnalysis]]


def is_semantically_useful_text(
    text: str,
    context: ExtractionContext | None = None,
    *,
    seen_texts: Iterable[str] = (),
) -> bool:
    """Descarta residuos de gráficas y elementos de página, conservando la prosa con cifras."""
    clean = _plain_text(text)
    if not clean or FOOTER_PATTERN.search(clean):
        return False
    words = re.findall(r"[^\W\d_]+", clean, re.UNICODE)
    if URL_PATTERN.fullmatch(clean) or (CONTACT_PATTERN.search(clean) and len(words) < 12):
        return False
    if len(clean) < 18 and len(words) < 3:
        return False
    if any(_similarity(clean, previous) >= 0.94 for previous in seen_texts if previous):
        return False
    return not analyze_chart_residual_text(
        clean,
        context or ExtractionContext(),
    ).is_residual


def semantic_noise_reason(text: str, context: ExtractionContext | None = None) -> str:
    clean = _plain_text(text)
    if not clean:
        return "empty"
    if FOOTER_PATTERN.search(clean):
        return "footer"
    if URL_PATTERN.fullmatch(clean) or (CONTACT_PATTERN.search(clean) and len(clean.split()) < 12):
        return "footer"
    if len(clean) < 18 and len(re.findall(r"[^\W\d_]+", clean, re.UNICODE)) < 3:
        return "short"
    analysis = analyze_chart_residual_text(clean, context or ExtractionContext())
    if analysis.is_residual:
        if any(
            reason in analysis.reasons
            for reason in ("many_percentages", "numeric_token_ratio_high", "many_numeric_tokens")
        ):
            return "numeric_noise"
        return "chart_noise"
    return "useful"


def clean_semantic_text(text: str) -> str:
    """Elimina referencias de transporte sin alterar las frases con significado."""
    clean = _plain_text(text)
    clean = URL_PATTERN.sub("", clean)
    clean = re.sub(r"\bchrome-extension:\S+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s+([,.;:!?])", r"\1", clean)
    clean = re.sub(r"\s{2,}", " ", clean).strip().strip(":-")
    return clean


def is_chart_residual_text(text: str, context: ExtractionContext) -> bool:
    return analyze_chart_residual_text(text, context).is_residual


def analyze_chart_residual_text(
    text: str,
    context: ExtractionContext,
) -> ResidualTextAnalysis:
    clean = _plain_text(text)
    tokens = TOKEN_PATTERN.findall(clean)
    numeric_tokens = [token for token in tokens if NUMERIC_TOKEN_PATTERN.fullmatch(token.strip())]
    word_tokens = [
        token.casefold() for token in tokens if not NUMERIC_TOKEN_PATTERN.fullmatch(token.strip())
    ]
    numeric_ratio = len(numeric_tokens) / max(len(tokens), 1)
    percentage_count = sum("%" in token for token in numeric_tokens)
    year_count = sum(bool(YEAR_TOKEN_PATTERN.fullmatch(token.strip())) for token in numeric_tokens)
    functional_count = sum(word in FUNCTION_WORDS for word in word_tokens)
    functional_ratio = functional_count / max(len(word_tokens), 1)
    verb_count = sum(_looks_like_verb(word) for word in word_tokens)
    has_sentence_end = bool(SENTENCE_END_PATTERN.search(clean))
    has_semantic_sentence = (
        len(word_tokens) >= 7
        and verb_count >= 1
        and functional_ratio >= 0.1
        and (has_sentence_end or len(word_tokens) >= 10)
    ) or (len(word_tokens) >= 18 and functional_ratio >= 0.15)

    score = 0
    reasons: list[str] = []
    if numeric_ratio >= 0.65:
        score += 3
        reasons.append("numeric_token_ratio_high")
    elif numeric_ratio >= 0.35:
        score += 2
        reasons.append("numeric_token_ratio_medium")
    elif numeric_ratio >= 0.2 and len(numeric_tokens) >= 4:
        score += 1
        reasons.append("many_numeric_tokens")

    if percentage_count >= 5:
        score += 3
        reasons.append("many_percentages")
    elif percentage_count >= 3:
        score += 2
        reasons.append("several_percentages")

    if year_count >= 3:
        score += 2
        reasons.append("many_years")
    elif year_count >= 2:
        score += 1
        reasons.append("repeated_years")

    if not has_sentence_end and len(tokens) >= 5:
        score += 1
        reasons.append("no_sentence_punctuation")
    if verb_count == 0 and len(word_tokens) >= 3:
        score += 1
        reasons.append("no_verbs")
    if functional_ratio < 0.08 and len(word_tokens) >= 5:
        score += 1
        reasons.append("few_function_words")

    capitalized_labels = sum(
        token[:1].isupper() for token in re.findall(r"[^\W\d_]+", clean, re.UNICODE)
    )
    chart_label_count = sum(word in CHART_LABEL_WORDS for word in word_tokens)
    looks_like_legend = bool(re.match(r"^\s*leyenda\s*:", clean, re.IGNORECASE))
    if chart_label_count >= 3 or capitalized_labels >= 5:
        score += 2
        reasons.append("fragmented_chart_labels")
    elif chart_label_count >= 2 or capitalized_labels >= 3:
        score += 1
        reasons.append("possible_chart_labels")
    if looks_like_legend:
        score += 2
        reasons.append("fragmented_legend")

    if context.inside_figure or context.overlaps_figure:
        score += 3
        reasons.append("inside_or_overlapping_figure")
    elif context.near_figure:
        score += 2
        reasons.append("near_figure")

    matches_caption = _matches_reference(clean, context.caption)
    matches_source = _matches_reference(clean, context.figure_source)
    matches_image_text = any(
        _partial_text_match(clean, image_text) for image_text in context.detected_image_texts
    )
    if matches_caption:
        score += 5
        reasons.append("duplicate_figure_caption")
    if matches_source:
        score += 4
        reasons.append("duplicate_figure_source")
    if matches_image_text:
        score += 2
        reasons.append("matches_text_inside_figure")

    if has_semantic_sentence:
        score -= 5
        reasons.append("coherent_sentence_preserved")

    threshold = 5
    fragmented_label_sequence = (
        not has_sentence_end
        and len(word_tokens) <= 20
        and functional_ratio < 0.12
        and (chart_label_count >= 3 or capitalized_labels >= 5 or looks_like_legend)
    )
    spatial_chart_signal = (context.inside_figure or context.overlaps_figure) and (
        numeric_ratio >= 0.15 or percentage_count >= 2 or fragmented_label_sequence
    )
    strong_residual_signal = (
        numeric_ratio >= 0.35
        or percentage_count >= 5
        or year_count >= 3
        or fragmented_label_sequence
        or spatial_chart_signal
        or matches_caption
        or matches_source
        or matches_image_text
    )
    is_residual = bool(clean) and score >= threshold and strong_residual_signal
    confidence = min(1.0, max(0.0, score / 9.0))
    return ResidualTextAnalysis(
        is_residual=is_residual,
        score=score,
        confidence=round(confidence, 3),
        reasons=tuple(reasons),
        numeric_token_ratio=round(numeric_ratio, 3),
        percentage_count=percentage_count,
        has_semantic_sentence=has_semantic_sentence,
    )


def clean_figure_paragraphs(
    before: Iterable[Any],
    after: Iterable[Any],
    *,
    caption: str = "",
    figure_source: str = "",
    detected_image_texts: Iterable[str] = (),
) -> CleanedParagraphs:
    removed: list[tuple[str, ResidualTextAnalysis]] = []
    entries: list[tuple[str, str]] = []
    image_texts = tuple(
        str(value or "") for value in detected_image_texts if str(value or "").strip()
    )
    for position, values in (("before", before), ("after", after)):
        for value in values:
            text = _plain_text(value)
            if not text:
                continue
            context = ExtractionContext(
                near_figure=True,
                position=position,
                caption=caption,
                figure_source=figure_source,
                detected_image_texts=image_texts,
            )
            reason = semantic_noise_reason(text, context)
            if reason in {"footer", "short", "empty"}:
                removed.append((text, _noise_analysis(reason)))
                continue
            analysis = analyze_chart_residual_text(text, context)
            if analysis.is_residual:
                removed.append((text, analysis))
                continue
            if not _append_best_duplicate(entries, position, text):
                removed.append((text, _noise_analysis("duplicate")))

    return CleanedParagraphs(
        before=[text for position, text in entries if position == "before"],
        after=[text for position, text in entries if position == "after"],
        removed=removed,
    )


def sanitize_report_document(document: dict[str, Any]) -> dict[str, Any]:
    """Filtra defensivamente en lectura; las importaciones nuevas ya se limpian al guardar."""
    cleaned = deepcopy(document)
    figure_value = cleaned.get("figure")
    figure: dict[str, Any] = figure_value if isinstance(figure_value, dict) else {}
    caption = str(figure.get("caption") or cleaned.get("figure_caption") or "")
    source = str(figure.get("source") or "")
    before_value = cleaned.get("paragraphs_before_figure")
    after_value = cleaned.get("paragraphs_after_figure")
    before = before_value if isinstance(before_value, list) else []
    after = after_value if isinstance(after_value, list) else []
    if before or after:
        result = clean_figure_paragraphs(before, after, caption=caption, figure_source=source)
        cleaned["paragraphs_before_figure"] = result.before
        cleaned["paragraphs_after_figure"] = result.after
        cleaned["paragraphs"] = [*result.before, *result.after]
    elif isinstance(cleaned.get("paragraphs"), list):
        result = clean_figure_paragraphs(
            cleaned["paragraphs"],
            [],
            caption=caption,
            figure_source=source,
        )
        cleaned["paragraphs"] = result.before
    content_html = cleaned.get("content_html")
    if isinstance(content_html, str) and content_html.strip():
        cleaned["content_html"] = clean_report_content_html(
            content_html,
            caption=caption,
            figure_source=source,
        )
    return cleaned


def clean_report_content_html(
    content_html: str,
    *,
    caption: str = "",
    figure_source: str = "",
) -> str:
    seen: list[str] = []

    def replace_paragraph(match: re.Match[str]) -> str:
        body = match.group("body")
        text = _plain_text(body)
        analysis = analyze_chart_residual_text(
            text,
            ExtractionContext(
                near_figure=True,
                caption=caption,
                figure_source=figure_source,
            ),
        )
        if analysis.is_residual:
            return ""
        if any(_similarity(existing, text) >= 0.9 for existing in seen):
            return ""
        seen.append(text)
        return match.group(0)

    cleaned = HTML_PARAGRAPH_PATTERN.sub(replace_paragraph, str(content_html or ""))
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _append_best_duplicate(entries: list[tuple[str, str]], position: str, text: str) -> bool:
    for index, (existing_position, existing) in enumerate(entries):
        if _similarity(existing, text) < 0.9:
            continue
        if len(text) > len(existing):
            entries[index] = (existing_position, text)
        return False
    entries.append((position, text))
    return True


def _noise_analysis(reason: str) -> ResidualTextAnalysis:
    return ResidualTextAnalysis(
        is_residual=True,
        score=9,
        confidence=1.0,
        reasons=(reason,),
        numeric_token_ratio=0.0,
        percentage_count=0,
        has_semantic_sentence=False,
    )


def _plain_text(value: Any) -> str:
    text = html.unescape(HTML_TAG_PATTERN.sub(" ", str(value or "")))
    return " ".join(text.split()).strip()


def _looks_like_verb(word: str) -> bool:
    if word in VERB_WORDS:
        return True
    return len(word) >= 6 and word.endswith(
        (
            "aron",
            "ieron",
            "aban",
            "ían",
            "ando",
            "iendo",
            "ados",
            "idas",
            "amos",
            "emos",
            "imos",
            "izan",
            "perciben",
        )
    )


def _matches_reference(text: str, reference: str) -> bool:
    if not reference:
        return False
    return _similarity(_caption_core(text), _caption_core(reference)) >= 0.84


def _partial_text_match(text: str, reference: str) -> bool:
    left = _normalized(text)
    right = _normalized(reference)
    if len(left) < 12 or len(right) < 12:
        return False
    return left in right or right in left or SequenceMatcher(None, left, right).ratio() >= 0.82


def _caption_core(value: str) -> str:
    text = CAPTION_PREFIX_PATTERN.sub("", _plain_text(value))
    return re.sub(r"^fuente\s*[:.\-]?\s*", "", text, flags=re.IGNORECASE)


def _similarity(left: str, right: str) -> float:
    normalized_left = _normalized(left)
    normalized_right = _normalized(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _normalized(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", _plain_text(value))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()
