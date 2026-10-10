import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

import spacy

EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?<!\w)\+?\d[\d ().-]{6,}\d(?!\w)")
IDENTIFIER_PATTERN = re.compile(r"\b(?:[A-Z]{2,8}-SCESI-\d{4}-\d{3,}|\d{8,})\b")
PLACEHOLDER_PATTERN = re.compile(r"\[(?:PERSON|ENTITY|EMAIL|PHONE|IDENTIFIER)_\d+\]")


@dataclass(frozen=True)
class RedactedSpan:
    redacted_start: int
    redacted_end: int
    source_start: int
    source_end: int
    protected: bool


@dataclass(frozen=True)
class RedactedText:
    source: str
    text: str
    source_indices: tuple[int | None, ...]
    spans: tuple[RedactedSpan, ...]

    def map_range(self, start: int, end: int) -> tuple[int, int] | None:
        if start < 0 or end <= start or end > len(self.source_indices):
            return None
        indices = self.source_indices[start:end]
        if not indices or any(index is None for index in indices):
            return None
        concrete = [int(index) for index in indices]
        source_start = concrete[0]
        source_end = concrete[-1] + 1
        if concrete != list(range(source_start, source_end)):
            return None
        return source_start, source_end


class LocalPrivacyFilter:
    def __init__(self) -> None:
        try:
            self._nlp = _load_nlp()
        except Exception as error:
            raise PrivacyReviewRequired("LOCAL_ENTITY_DETECTION_UNAVAILABLE") from error

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())

    def redact(self, body: str, private_names: list[str]) -> RedactedText:
        if not body.strip():
            raise PrivacyReviewRequired("EMPTY_BODY")
        candidates: list[tuple[int, int, str]] = []
        for name in private_names:
            normalized_name = self._normalize(name)
            if not normalized_name:
                continue
            variants = {normalized_name}
            variants.update(
                token for token in normalized_name.split() if len(token) >= 3
            )
            for variant in sorted(variants, key=len, reverse=True):
                pattern = re.compile(rf"(?<!\w){re.escape(variant)}(?!\w)", re.I)
                candidates.extend(
                    (m.start(), m.end(), "PERSON") for m in pattern.finditer(body)
                )

        try:
            doc = self._nlp(body)
        except Exception as error:
            raise PrivacyReviewRequired("LOCAL_ENTITY_DETECTION_UNAVAILABLE") from error
        for entity in doc.ents:
            if entity.label_ in {"PER", "PERSON"}:
                candidates.append((entity.start_char, entity.end_char, "PERSON"))
            elif entity.label_ == "ORG":
                candidates.append((entity.start_char, entity.end_char, "ENTITY"))
        for token in doc:
            if token.pos_ == "PROPN" and not token.ent_type_:
                candidates.append((token.idx, token.idx + len(token), "PERSON"))
        candidates.extend(
            (m.start(), m.end(), "EMAIL") for m in EMAIL_PATTERN.finditer(body)
        )
        candidates.extend(
            (m.start(), m.end(), "PHONE") for m in PHONE_PATTERN.finditer(body)
        )
        candidates.extend(
            (m.start(), m.end(), "IDENTIFIER")
            for m in IDENTIFIER_PATTERN.finditer(body)
        )

        priority = {"EMAIL": 0, "PHONE": 1, "IDENTIFIER": 2, "PERSON": 3, "ENTITY": 4}
        candidates.sort(
            key=lambda item: (item[0], priority.get(item[2], 9), -(item[1] - item[0]))
        )
        merged: list[tuple[int, int, str]] = []
        for start, end, kind in candidates:
            if merged and start < merged[-1][1]:
                old_start, old_end, old_kind = merged[-1]
                merged_kind = old_kind if priority[old_kind] <= priority[kind] else kind
                merged[-1] = (old_start, max(old_end, end), merged_kind)
            else:
                merged.append((start, end, kind))

        redacted_parts: list[str] = []
        source_indices: list[int | None] = []
        spans: list[RedactedSpan] = []
        source_cursor = 0
        redacted_cursor = 0
        counts: dict[str, int] = {}
        for start, end, kind in merged:
            if end <= source_cursor:
                continue
            visible = body[source_cursor:start]
            redacted_parts.append(visible)
            source_indices.extend(range(source_cursor, start))
            redacted_cursor += len(visible)
            counts[kind] = counts.get(kind, 0) + 1
            token = f"[{kind}_{counts[kind]}]"
            redacted_parts.append(token)
            spans.append(
                RedactedSpan(
                    redacted_cursor, redacted_cursor + len(token), start, end, True
                )
            )
            source_indices.extend([None] * len(token))
            redacted_cursor += len(token)
            source_cursor = end
        tail = body[source_cursor:]
        redacted_parts.append(tail)
        source_indices.extend(range(source_cursor, len(body)))
        redacted = "".join(redacted_parts)
        if not redacted or len(redacted) > 20_000:
            raise PrivacyReviewRequired("INPUT_TOO_LARGE_OR_EMPTY")
        return RedactedText(body, redacted, tuple(source_indices), tuple(spans))

    def validate_public_text(
        self, value: str, private_names: list[str] | None = None
    ) -> bool:
        if (
            PLACEHOLDER_PATTERN.search(value)
            or EMAIL_PATTERN.search(value)
            or PHONE_PATTERN.search(value)
        ):
            return False
        normalized = self._normalize(value)
        for name in private_names or []:
            for variant in {
                self._normalize(name),
                *(token for token in self._normalize(name).split() if len(token) >= 3),
            }:
                if variant and re.search(
                    rf"(?<!\w){re.escape(variant)}(?!\w)", normalized, re.I
                ):
                    return False
        try:
            document = self._nlp(value)
            if any(
                entity.label_ in {"PER", "PERSON", "ORG"} for entity in document.ents
            ):
                return False
            return not any(
                token.pos_ == "PROPN" and not token.ent_type_ for token in document
            )
        except Exception:
            return False


class PrivacyReviewRequired(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@lru_cache(maxsize=1)
def _load_nlp():
    return spacy.load("es_core_news_sm", disable=["parser", "lemmatizer"])
