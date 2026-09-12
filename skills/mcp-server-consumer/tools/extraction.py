"""Typed extraction workflow separating transport bytes from semantic evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class ExtractionState(StrEnum):
    EXTRACTED = "EXTRACTED"
    PARTIAL = "PARTIAL"
    UNEXTRACTED = "UNEXTRACTED"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"


@dataclass(frozen=True)
class ExtractionProvenance:
    source_locator: str
    content_type: str
    content_sha256: str
    transport_truncated: bool
    semantic_truncated: bool
    extractor: str


@dataclass(frozen=True)
class ExtractionResult:
    state: ExtractionState
    text: str | None
    provenance: ExtractionProvenance


Extractor = Callable[[bytes], str]


def extract_semantic_content(
    body: bytes,
    *,
    content_type: str,
    source_locator: str,
    transport_truncated: bool = False,
    max_semantic_bytes: int = 16_384,
    extractor: Extractor | None = None,
    extractor_name: str | None = None,
) -> ExtractionResult:
    """Validate type, extract, bound semantic text, then attach evidence provenance."""
    if not source_locator.strip() or not content_type.strip():
        raise ValueError("source_locator and content_type must be non-empty")
    if max_semantic_bytes <= 0:
        raise ValueError("max_semantic_bytes must be positive")

    normalized = content_type.split(";", 1)[0].strip().lower()
    digest = hashlib.sha256(body).hexdigest()
    binary = normalized.startswith(("image/", "audio/", "video/")) or normalized in {
        "application/octet-stream",
        "application/pdf",
        "application/zip",
    }
    if binary:
        return _result(
            ExtractionState.UNSUPPORTED_FORMAT,
            None,
            source_locator,
            content_type,
            digest,
            transport_truncated,
            False,
            "none",
        )

    if normalized == "text/plain" and extractor is None:
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return _result(
                ExtractionState.UNEXTRACTED,
                None,
                source_locator,
                content_type,
                digest,
                transport_truncated,
                False,
                "plain-text/1",
            )
        return _bounded_result(
            text,
            source_locator=source_locator,
            content_type=content_type,
            digest=digest,
            transport_truncated=transport_truncated,
            max_semantic_bytes=max_semantic_bytes,
            extractor_name="plain-text/1",
        )

    if extractor is None:
        return _result(
            ExtractionState.UNEXTRACTED,
            None,
            source_locator,
            content_type,
            digest,
            transport_truncated,
            False,
            "none",
        )

    name = extractor_name.strip() if isinstance(extractor_name, str) else ""
    if not name:
        raise ValueError("extractor_name is required when extractor is provided")
    try:
        text = extractor(body)
    except Exception:  # extractor adapters are untrusted boundaries; normalize to typed state
        return _result(
            ExtractionState.UNEXTRACTED,
            None,
            source_locator,
            content_type,
            digest,
            transport_truncated,
            False,
            name,
        )
    if not isinstance(text, str) or not text.strip():
        return _result(
            ExtractionState.UNEXTRACTED,
            None,
            source_locator,
            content_type,
            digest,
            transport_truncated,
            False,
            name,
        )
    return _bounded_result(
        text,
        source_locator=source_locator,
        content_type=content_type,
        digest=digest,
        transport_truncated=transport_truncated,
        max_semantic_bytes=max_semantic_bytes,
        extractor_name=name,
    )


def require_extracted_text(result: ExtractionResult) -> str:
    """Fail closed for downstream claims unless semantic extraction produced text."""
    if result.state not in {ExtractionState.EXTRACTED, ExtractionState.PARTIAL} or result.text is None:
        raise ValueError("semantic content is not extracted")
    return result.text


def _bounded_result(
    text: str,
    *,
    source_locator: str,
    content_type: str,
    digest: str,
    transport_truncated: bool,
    max_semantic_bytes: int,
    extractor_name: str,
) -> ExtractionResult:
    encoded = text.encode("utf-8")
    semantic_truncated = len(encoded) > max_semantic_bytes
    if semantic_truncated:
        encoded = encoded[:max_semantic_bytes]
        while True:
            try:
                text = encoded.decode("utf-8")
                break
            except UnicodeDecodeError:
                encoded = encoded[:-1]
    state = ExtractionState.PARTIAL if transport_truncated or semantic_truncated else ExtractionState.EXTRACTED
    return _result(
        state,
        text,
        source_locator,
        content_type,
        digest,
        transport_truncated,
        semantic_truncated,
        extractor_name,
    )


def _result(
    state: ExtractionState,
    text: str | None,
    source_locator: str,
    content_type: str,
    digest: str,
    transport_truncated: bool,
    semantic_truncated: bool,
    extractor: str,
) -> ExtractionResult:
    return ExtractionResult(
        state,
        text,
        ExtractionProvenance(
            source_locator=source_locator,
            content_type=content_type,
            content_sha256=digest,
            transport_truncated=transport_truncated,
            semantic_truncated=semantic_truncated,
            extractor=extractor,
        ),
    )
