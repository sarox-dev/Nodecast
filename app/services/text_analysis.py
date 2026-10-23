"""Deterministic Unicode analysis for Nodecast's rebuildable lexical index."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass


ANALYZER_ID = "nodecast-unicode"
ANALYZER_VERSION = "2"
MAX_INDEX_TERMS = 512
MAX_QUERY_TERMS = 48

_NGRAM_SCRIPTS = {"Han", "Hiragana", "Katakana", "Thai", "Lao", "Khmer"}
_TECHNICAL_RE = re.compile(
    r"https?://[^\s]+|(?:[A-Za-z0-9]+[._:/-])+(?:[A-Za-z0-9._:/-]+)|"
    r"\b[A-Z][A-Za-z0-9]+Error\b|\b[A-Z]{1,8}-?\d{3,}\b"
)


@dataclass(frozen=True)
class ScriptSpan:
    script: str
    start: int
    end: int


@dataclass(frozen=True)
class TextAnalysis:
    normalized_text: str
    scripts: tuple[ScriptSpan, ...]
    lexical_terms: tuple[str, ...]
    protected_terms: tuple[str, ...]
    analyzer_id: str = ANALYZER_ID
    analyzer_version: str = ANALYZER_VERSION

    @property
    def search_terms(self) -> tuple[str, ...]:
        return _unique((*self.protected_terms, *self.lexical_terms))

    @property
    def script_names(self) -> tuple[str, ...]:
        return _unique(span.script for span in self.scripts)


def _script_for(character: str) -> str:
    codepoint = ord(character)
    if 0x0041 <= codepoint <= 0x024F or 0x1E00 <= codepoint <= 0x1EFF:
        return "Latin"
    if 0x0400 <= codepoint <= 0x052F:
        return "Cyrillic"
    if 0x0590 <= codepoint <= 0x05FF:
        return "Hebrew"
    if 0x0600 <= codepoint <= 0x06FF or 0x0750 <= codepoint <= 0x077F or 0x08A0 <= codepoint <= 0x08FF:
        return "Arabic"
    if 0x0900 <= codepoint <= 0x097F:
        return "Devanagari"
    if 0x0E00 <= codepoint <= 0x0E7F:
        return "Thai"
    if 0x0E80 <= codepoint <= 0x0EFF:
        return "Lao"
    if 0x1780 <= codepoint <= 0x17FF:
        return "Khmer"
    if 0x3040 <= codepoint <= 0x309F:
        return "Hiragana"
    if 0x30A0 <= codepoint <= 0x30FF:
        return "Katakana"
    if 0x3400 <= codepoint <= 0x4DBF or 0x4E00 <= codepoint <= 0x9FFF or 0xF900 <= codepoint <= 0xFAFF:
        return "Han"
    if 0xAC00 <= codepoint <= 0xD7AF:
        return "Hangul"
    category = unicodedata.category(character)
    return "Common" if category[0] in {"N", "P", "S", "Z"} else "Unknown"


def _script_spans(text: str) -> tuple[ScriptSpan, ...]:
    spans = []
    active_script = None
    start = 0
    for index, character in enumerate(text):
        script = _script_for(character)
        if script == "Common":
            continue
        if active_script is None:
            active_script, start = script, index
        elif script != active_script:
            spans.append(ScriptSpan(active_script, start, index))
            active_script, start = script, index
    if active_script is not None:
        spans.append(ScriptSpan(active_script, start, len(text)))
    return tuple(spans)


def _technical_token(value: str) -> str:
    digest = hashlib.blake2s(value.casefold().encode("utf-8"), digest_size=8).hexdigest()
    return f"ztech{digest}"


def _word_terms(text: str) -> list[str]:
    terms, current = [], []
    for character in text:
        if character.isalnum() or character == "_":
            current.append(character)
        elif current:
            terms.append("".join(current))
            current = []
    if current:
        terms.append("".join(current))
    return [term for term in terms if term]


def _ngram_terms(text: str, spans: tuple[ScriptSpan, ...]) -> list[str]:
    terms = []
    for span in spans:
        if span.script not in _NGRAM_SCRIPTS:
            continue
        run = "".join(character for character in text[span.start:span.end] if character.isalnum())
        for size in (2, 3):
            if len(run) < size:
                continue
            terms.extend(f"z{span.script.lower()}{size}{run[index:index + size]}" for index in range(len(run) - size + 1))
    return terms


def _unique(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def analyze_text(text: str, *, mode: str = "index") -> TextAnalysis:
    if mode not in {"index", "query"}:
        raise ValueError("mode must be index or query")
    original = str(text or "")
    normalized = unicodedata.normalize("NFC", original).casefold()
    spans = _script_spans(normalized)
    protected = _unique(_technical_token(match.group(0)) for match in _TECHNICAL_RE.finditer(original))
    lexical = _unique((*_word_terms(normalized), *_ngram_terms(normalized, spans)))
    limit = MAX_QUERY_TERMS if mode == "query" else MAX_INDEX_TERMS
    return TextAnalysis(
        normalized_text=normalized,
        scripts=spans,
        lexical_terms=lexical[:limit],
        protected_terms=protected[:limit],
    )


def language_hint(analysis: TextAnalysis) -> tuple[str, float]:
    scripts = set(analysis.script_names)
    text = analysis.normalized_text
    if "Hiragana" in scripts or "Katakana" in scripts:
        return "ja", 0.95
    if "Hangul" in scripts:
        return "ko", 0.95
    if "Han" in scripts and len(scripts - {"Han", "Latin"}) == 0:
        return "zh-Hans", 0.8
    if "Thai" in scripts:
        return "th", 0.9
    if "Arabic" in scripts:
        return "ar", 0.65
    if "Cyrillic" in scripts:
        return "und-Cyrl", 0.4
    words = set(_word_terms(text))
    signatures = {
        "lv": {"un", "vai", "kā", "kas", "par", "salīdzini", "atšķirība"},
        "en": {"and", "or", "how", "what", "which", "the", "compare"},
        "tr": {"ve", "veya", "nasıl", "nedir", "için"},
    }
    scores = {tag: len(words & markers) for tag, markers in signatures.items()}
    tag, score = max(scores.items(), key=lambda item: item[1])
    if score:
        return tag, min(0.9, 0.45 + score * 0.15)
    return "und", 0.0


def index_terms(*parts: str) -> tuple[str, ...]:
    values = []
    for part in parts:
        values.extend(analyze_text(part, mode="index").search_terms)
    return _unique(values)[:MAX_INDEX_TERMS]
