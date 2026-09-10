#!/usr/bin/env python3
"""Semantic validation for verification receipts beyond JSON Schema arithmetic."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class VerificationReceiptError(ValueError):
    """Raised when a verification receipt overstates its evidence."""


def _non_negative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise VerificationReceiptError(f"{field} must be a non-negative integer")
    return value


def validate_receipt_semantics(receipt: Mapping[str, Any]) -> None:
    """Reject internally inconsistent corpus accounting and false pass dispositions."""
    corpus = receipt.get("test_corpus")
    if not isinstance(corpus, Mapping):
        raise VerificationReceiptError("test_corpus must be an object")

    discovered = _non_negative_int(corpus.get("discovered_files"), "test_corpus.discovered_files")
    executed = _non_negative_int(corpus.get("executed_files"), "test_corpus.executed_files")
    accounted = _non_negative_int(corpus.get("accounted_files"), "test_corpus.accounted_files")
    excluded = corpus.get("excluded_files")
    if not isinstance(excluded, Sequence) or isinstance(excluded, (str, bytes, bytearray)):
        raise VerificationReceiptError("test_corpus.excluded_files must be an array")

    paths: set[str] = set()
    for item in excluded:
        if not isinstance(item, Mapping):
            raise VerificationReceiptError("test_corpus.excluded_files entries must be objects")
        path = item.get("path")
        if not isinstance(path, str) or not path:
            raise VerificationReceiptError("test_corpus exclusion path must be non-empty")
        if path in paths:
            raise VerificationReceiptError(f"duplicate test-corpus exclusion: {path}")
        paths.add(path)

    computed = executed + len(paths)
    if accounted != computed:
        raise VerificationReceiptError(
            "test_corpus.accounted_files must equal executed_files plus unique excluded_files"
        )
    if accounted > discovered:
        raise VerificationReceiptError("test_corpus accounts for more files than were discovered")

    if receipt.get("verdict") == "pass":
        if accounted != discovered:
            raise VerificationReceiptError("pass requires every discovered file to be executed or explicitly excluded")
        if corpus.get("execution_evidence") != "observed":
            raise VerificationReceiptError("pass requires observed execution evidence")
        if corpus.get("completeness") != "complete":
            raise VerificationReceiptError("pass requires complete test-corpus evidence")
        if corpus.get("discovery_drift") != 0:
            raise VerificationReceiptError("pass requires zero test discovery/execution drift")


def validated_receipt(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the input only after semantic verification succeeds."""
    validate_receipt_semantics(receipt)
    return receipt
