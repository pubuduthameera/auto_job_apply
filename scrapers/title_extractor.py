"""
scrapers/title_extractor.py — Job title extraction and normalization pipeline

Deterministic, configurable pipeline that converts noisy job-listing text into
canonical titles with confidence scores. Operates on raw HTML, JSON dicts, or
plain text. All mapping rules are loaded from config/title_mappings.json.
"""

from __future__ import annotations

import html
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


# ── Configuration ────────────────────────────────────────────────────────────

_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), os.pardir, "config", "title_mappings.json"
)


@dataclass
class ExtractorConfig:
    abbreviations: dict[str, str] = field(default_factory=dict)
    synonyms: dict[str, str] = field(default_factory=dict)
    locale_tokens: dict[str, dict[str, str]] = field(default_factory=dict)
    ambiguity_margin: float = 0.10
    unknown_cutoff: float = 0.40

    @classmethod
    def load(cls, path: str | None = None) -> ExtractorConfig:
        path = path or _CONFIG_PATH
        path = os.path.normpath(path)
        if not os.path.exists(path):
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        thresholds = raw.get("confidence_thresholds", {})
        return cls(
            abbreviations=raw.get("abbreviations", {}),
            synonyms={k.lower(): v for k, v in raw.get("synonyms", {}).items()},
            locale_tokens=raw.get("locale_tokens", {}),
            ambiguity_margin=thresholds.get("ambiguity_margin", 0.10),
            unknown_cutoff=thresholds.get("unknown_cutoff", 0.40),
        )


# ── Output dataclass ────────────────────────────────────────────────────────


@dataclass
class ExtractedTitle:
    raw_text: str
    normalized_text: str
    canonical_title: str
    confidence: float
    ambiguous: bool = False
    alternatives: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)


# ── Internal helpers ─────────────────────────────────────────────────────────

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_PAREN_NOISE_RE = re.compile(r"\s*\([^)]*\)\s*$")
_TRAILING_META_RE = re.compile(
    r"\s*[\u2014\u2013|—–\-]+\s*.{0,60}$"
)
_MULTI_SPACE_RE = re.compile(r"\s+")
_SALARY_RE = re.compile(
    r"[\$€£₹]\s*[\d,.]+[kKmM]?"
    r"|[\d,.]+\s*[\$€£₹]"
    r"|\d{2,3}[kK]\s*[-–—]\s*\d{2,3}[kK]",
)


def _strip_html(text: str) -> tuple[str, bool]:
    """Remove HTML tags and decode entities. Returns (cleaned, was_html)."""
    had_tags = bool(_HTML_TAG_RE.search(text))
    text = _HTML_TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return text, had_tags


def _normalize_text(text: str) -> str:
    """Unicode-normalize, collapse whitespace, strip edges."""
    text = unicodedata.normalize("NFC", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    return text.strip()


def _remove_trailing_noise(text: str) -> tuple[str, list[str]]:
    """Strip parenthesized tags, salary figures, and trailing metadata segments."""
    reasons: list[str] = []
    if _SALARY_RE.search(text):
        text = _SALARY_RE.sub("", text).strip()
        reasons.append("salary_removed")
    if _PAREN_NOISE_RE.search(text):
        text = _PAREN_NOISE_RE.sub("", text).strip()
        reasons.append("noise_removed")
    prev = text
    text = _TRAILING_META_RE.sub("", text).strip()
    if text != prev and len(text) > 2:
        reasons.append("trailing_meta_removed")
    elif text != prev:
        text = prev
    return text, reasons


def _expand_abbreviations(
    text: str, abbrevs: dict[str, str]
) -> tuple[str, bool]:
    """Expand known abbreviations in-place. Returns (expanded, did_expand)."""
    if not abbrevs:
        return text, False
    tokens = text.split()
    expanded = False
    result = []
    for tok in tokens:
        key = tok.lower().rstrip(".")
        key_dot = tok.lower()
        if key_dot in abbrevs:
            result.append(abbrevs[key_dot])
            expanded = True
        elif key in abbrevs:
            result.append(abbrevs[key])
            expanded = True
        else:
            result.append(tok)
    return " ".join(result), expanded


def _try_comma_inversion(text: str) -> str | None:
    """If text has exactly one comma, try swapping the two parts."""
    parts = text.split(",")
    if len(parts) == 2:
        swapped = f"{parts[1].strip()} {parts[0].strip()}"
        return _normalize_text(swapped)
    return None


def _try_slash_split(text: str) -> list[str]:
    """Split on slash/pipe if it looks like multiple titles."""
    if "/" in text or "|" in text:
        parts = re.split(r"\s*[/|]\s*", text)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 2 and all(len(p) >= 2 for p in parts):
            return parts
    return []


def _to_title_case(text: str) -> str:
    """Smart title-case that keeps acronyms and small words sensible."""
    small_words = {"a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "is"}
    tokens = text.split()
    result = []
    for i, tok in enumerate(tokens):
        if tok.upper() == tok and len(tok) >= 2 and tok.isalpha():
            result.append(tok)
        elif i == 0 or tok.lower() not in small_words:
            result.append(tok.capitalize())
        else:
            result.append(tok.lower())
    return " ".join(result)


def _match_locale(text: str, locale_tokens: dict[str, dict[str, str]]) -> str | None:
    """Check if any locale-specific token appears in the text."""
    for _lang, mapping in locale_tokens.items():
        for token, canonical in mapping.items():
            if token in text:
                return canonical
    return None


def _match_canonical(
    text: str, config: ExtractorConfig
) -> tuple[str | None, str]:
    """Try to find a canonical title via exact synonym match. Returns (canonical, match_type)."""
    key = text.lower().strip()
    if key in config.synonyms:
        return config.synonyms[key], "synonym_match"
    for syn, canon in config.synonyms.items():
        if canon.lower() == key:
            return canon, "exact_match"
    return None, ""


# ── Scoring ──────────────────────────────────────────────────────────────────

_SCORE_WEIGHTS = {
    "title_field":           +0.40,
    "exact_match":           +0.30,
    "synonym_match":         +0.20,
    "locale_match":          +0.15,
    "abbreviation_expanded": -0.05,
    "comma_inversion":       -0.05,
    "html_stripped":         -0.05,
    "fallback_source":       -0.20,
}


def _compute_confidence(reason_codes: list[str]) -> float:
    base = 0.50
    score = base + sum(_SCORE_WEIGHTS.get(r, 0.0) for r in reason_codes)
    return max(0.0, min(1.0, round(score, 2)))


# ── Core extraction logic ───────────────────────────────────────────────────


def _extract_single(
    text: str,
    config: ExtractorConfig,
    from_title_field: bool = False,
) -> list[ExtractedTitle]:
    """Extract title candidates from a single string."""
    if not text or not text.strip():
        return [
            ExtractedTitle(
                raw_text=text or "",
                normalized_text="",
                canonical_title="Unknown",
                confidence=0.0,
                ambiguous=True,
                reason_codes=["empty_input"],
            )
        ]

    raw_text = text
    reasons: list[str] = []

    if from_title_field:
        reasons.append("title_field")

    cleaned, had_html = _strip_html(text)
    if had_html:
        reasons.append("html_stripped")
    text = _normalize_text(cleaned)

    text, noise_reasons = _remove_trailing_noise(text)
    reasons.extend(noise_reasons)

    locale_match = _match_locale(text, config.locale_tokens)
    if locale_match:
        return [
            ExtractedTitle(
                raw_text=raw_text,
                normalized_text=text,
                canonical_title=locale_match,
                confidence=_compute_confidence(reasons + ["locale_match"]),
                reason_codes=reasons + ["locale_match"],
            )
        ]

    text_expanded, did_expand = _expand_abbreviations(text, config.abbreviations)
    if did_expand:
        reasons.append("abbreviation_expanded")
        text = text_expanded

    slash_parts = _try_slash_split(text)
    if slash_parts:
        results = []
        for part in slash_parts:
            sub_results = _extract_single(part, config, from_title_field=from_title_field)
            results.extend(sub_results)
        for r in results:
            r.raw_text = raw_text
        return results

    candidates: list[tuple[str, list[str]]] = [(text, list(reasons))]

    inverted = _try_comma_inversion(text)
    if inverted:
        candidates.append((inverted, reasons + ["comma_inversion"]))

    results: list[ExtractedTitle] = []
    for candidate_text, cand_reasons in candidates:
        canonical, match_type = _match_canonical(candidate_text, config)
        final_reasons = list(cand_reasons)
        if match_type:
            final_reasons.append(match_type)

        if canonical:
            display = canonical
        else:
            display = _to_title_case(candidate_text)

        conf = _compute_confidence(final_reasons)
        results.append(
            ExtractedTitle(
                raw_text=raw_text,
                normalized_text=candidate_text,
                canonical_title=display,
                confidence=conf,
                reason_codes=final_reasons,
            )
        )

    return results


# ── Public API ───────────────────────────────────────────────────────────────


def extract_titles(
    payload: str | dict | list,
    config: ExtractorConfig | None = None,
) -> list[ExtractedTitle]:
    """
    Extract and normalize job titles from mixed input.

    Accepts a raw HTML string, a job dict (with 'title' / 'description' keys),
    or a list of such dicts. Returns deduplicated ExtractedTitle objects sorted
    by confidence descending.
    """
    if config is None:
        config = ExtractorConfig.load()

    raw_candidates: list[tuple[str, bool]] = []

    if isinstance(payload, dict):
        if payload.get("title"):
            raw_candidates.append((payload["title"], True))
        if payload.get("description"):
            raw_candidates.append((payload["description"].split("\n")[0], False))
    elif isinstance(payload, list):
        all_results: list[ExtractedTitle] = []
        for item in payload:
            all_results.extend(extract_titles(item, config))
        return _postprocess(all_results, config)
    elif isinstance(payload, str):
        is_title_field = not _HTML_TAG_RE.search(payload) and len(payload) < 120
        raw_candidates.append((payload, is_title_field))
    else:
        return [
            ExtractedTitle(
                raw_text=str(payload),
                normalized_text="",
                canonical_title="Unknown",
                confidence=0.0,
                ambiguous=True,
                reason_codes=["unsupported_input_type"],
            )
        ]

    results: list[ExtractedTitle] = []
    for text, from_title in raw_candidates:
        results.extend(_extract_single(text, config, from_title_field=from_title))

    return _postprocess(results, config)


def _postprocess(
    results: list[ExtractedTitle], config: ExtractorConfig
) -> list[ExtractedTitle]:
    """Deduplicate, resolve ambiguity, apply unknown cutoff, and sort."""
    if not results:
        return results

    seen: dict[str, ExtractedTitle] = {}
    for r in results:
        key = r.canonical_title.lower()
        if key not in seen or r.confidence > seen[key].confidence:
            seen[key] = r

    deduped = list(seen.values())

    for r in deduped:
        if r.confidence < config.unknown_cutoff and "exact_match" not in r.reason_codes and "synonym_match" not in r.reason_codes:
            r.canonical_title = "Unknown"
            if "low_confidence" not in r.reason_codes:
                r.reason_codes.append("low_confidence")
            r.ambiguous = True

    if len(deduped) >= 2:
        sorted_by_conf = sorted(deduped, key=lambda x: x.confidence, reverse=True)
        top = sorted_by_conf[0].confidence
        second = sorted_by_conf[1].confidence
        if (top - second) <= config.ambiguity_margin:
            sorted_by_conf[0].ambiguous = True
            sorted_by_conf[0].alternatives = [
                r.canonical_title
                for r in sorted_by_conf[1:]
                if (top - r.confidence) <= config.ambiguity_margin
            ]

    deduped.sort(key=lambda r: (-r.confidence, r.canonical_title))
    return deduped


# ── Convenience helper for the main pipeline ─────────────────────────────────


_default_config: ExtractorConfig | None = None


def _get_default_config() -> ExtractorConfig:
    global _default_config
    if _default_config is None:
        _default_config = ExtractorConfig.load()
    return _default_config


def normalize_job(job: dict, config: ExtractorConfig | None = None) -> dict:
    """
    Enrich a job dict in-place with canonical title metadata.

    Adds: canonical_title, title_confidence, title_ambiguous.
    Preserves the original 'title' field.
    """
    cfg = config or _get_default_config()
    results = extract_titles(job, cfg)
    if results:
        best = results[0]
        job["canonical_title"] = best.canonical_title
        job["title_confidence"] = best.confidence
        job["title_ambiguous"] = best.ambiguous
    else:
        job["canonical_title"] = job.get("title", "Unknown")
        job["title_confidence"] = 0.0
        job["title_ambiguous"] = True
    return job
