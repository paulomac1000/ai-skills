#!/usr/bin/env python3
"""Reference helpers for provenance-preserving tool-result envelopes."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping
from typing import Any


class ToolResultEnvelopeError(ValueError):
    """Raised when a runtime annotation would overwrite source provenance."""


def source_sha256(payload: bytes) -> str:
    """Hash the exact unmodified source bytes, before runtime annotation."""
    return hashlib.sha256(payload).hexdigest()


def add_runtime_annotation(
    envelope: Mapping[str, Any],
    *,
    kind: str,
    text: str,
    part_index: int | None = None,
) -> dict[str, Any]:
    """Add runtime guidance structurally without mutating provider/tool source material."""
    if not text:
        raise ToolResultEnvelopeError("runtime annotation text must be non-empty")
    result = copy.deepcopy(dict(envelope))
    annotation = {"source": "runtime", "kind": kind, "text": text}
    if part_index is None:
        annotations = result.setdefault("annotations", [])
    else:
        parts = result.get("parts")
        if not isinstance(parts, list) or not 0 <= part_index < len(parts):
            raise ToolResultEnvelopeError("part_index does not identify a multipart source part")
        annotations = parts[part_index].setdefault("annotations", [])
    if not isinstance(annotations, list):
        raise ToolResultEnvelopeError("annotations must be a list")
    annotations.append(annotation)
    return result
