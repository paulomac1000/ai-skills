"""Regressions for canonical retry conditions and MCP content annotations."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_engine():
    path = ROOT / "skills/mcp-server-consumer/tools/decision_engine.py"
    spec = importlib.util.spec_from_file_location("mcp_consumer_retry_annotations", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical_retry_manifest(**condition_overrides: Any) -> dict[str, Any]:
    conditions = {
        "retryable": True,
        "eligibleErrors": ["TIMEOUT", "UNAVAILABLE"],
        "maxAttempts": 3,
        "backoffMilliseconds": 100,
        "requiresReconciliation": False,
    }
    conditions.update(condition_overrides)
    return {"retryable": True, "retryConditions": conditions}


def test_nested_retry_veto_and_conflicts_win() -> None:
    engine = load_engine()
    for manifest in (
        canonical_retry_manifest(retryable=False),
        {"retryable": False, "retryConditions": canonical_retry_manifest()["retryConditions"]},
        {"retryable": True, "retryConditions": {"retryable": "yes"}},
        {"retryable": True, "retryConditions": []},
    ):
        assert not engine.should_retry(
            error_code="TIMEOUT",
            attempt=0,
            operation_idempotent=True,
            manifest=manifest,
        )


def test_retry_conditions_restrict_error_attempt_and_reconciliation() -> None:
    engine = load_engine()
    manifest = canonical_retry_manifest()
    assert engine.should_retry(
        error_code="TIMEOUT", attempt=0, operation_idempotent=True, manifest=manifest
    )
    assert engine.should_retry(
        error_code="TIMEOUT", attempt=1, operation_idempotent=True, manifest=manifest
    )
    assert not engine.should_retry(
        error_code="TIMEOUT", attempt=2, operation_idempotent=True, manifest=manifest
    )
    assert not engine.should_retry(
        error_code="RATE_LIMITED", attempt=0, operation_idempotent=True, manifest=manifest
    )

    reconciliation = canonical_retry_manifest(requiresReconciliation=True)
    assert not engine.should_retry(
        error_code="TIMEOUT",
        attempt=0,
        operation_idempotent=True,
        manifest=reconciliation,
    )
    assert not engine.should_retry(
        error_code="TIMEOUT",
        attempt=0,
        operation_idempotent=True,
        manifest=reconciliation,
        precondition_refreshed=True,
    )
    assert engine.should_retry(
        error_code="TIMEOUT",
        attempt=0,
        operation_idempotent=True,
        manifest=reconciliation,
        reconciliation_completed=True,
    )


def test_conflict_refresh_and_reconciliation_are_independent_proofs() -> None:
    engine = load_engine()
    manifest = canonical_retry_manifest(
        eligibleErrors=["CONFLICT"],
        requiresReconciliation=True,
    )
    assert not engine.should_retry(
        error_code="CONFLICT",
        attempt=0,
        operation_idempotent=True,
        manifest=manifest,
        precondition_refreshed=True,
    )
    assert not engine.should_retry(
        error_code="CONFLICT",
        attempt=0,
        operation_idempotent=True,
        manifest=manifest,
        reconciliation_completed=True,
    )
    assert engine.should_retry(
        error_code="CONFLICT",
        attempt=0,
        operation_idempotent=True,
        manifest=manifest,
        precondition_refreshed=True,
        reconciliation_completed=True,
    )


def test_retry_conditions_accept_consistent_snake_case_compatibility_shape() -> None:
    engine = load_engine()
    manifest = {
        "retryable": True,
        "retry_conditions": {
            "retryable": True,
            "eligible_errors": ["TIMEOUT"],
            "max_attempts": 2,
            "backoff_milliseconds": 50,
            "requires_reconciliation": False,
        },
    }
    assert engine.should_retry(
        error_code="timeout", attempt=0, operation_idempotent=True, manifest=manifest
    )
    assert not engine.should_retry(
        error_code="timeout", attempt=1, operation_idempotent=True, manifest=manifest
    )


def annotated_text(annotations: Any):
    return {"content": [{"type": "text", "text": "ok", "annotations": annotations}]}


def test_valid_content_annotations_and_future_fields_are_preserved() -> None:
    engine = load_engine()
    for annotations in (
        None,
        {},
        {"audience": None, "priority": None, "lastModified": None},
        {"audience": []},
        {"audience": ["user"]},
        {"audience": ["user", "assistant"], "priority": 0.5},
        {"priority": 0},
        {"priority": 1.0, "lastModified": "2025-01-12T15:00:58Z"},
        {"futureExtension": {"version": 1}},
    ):
        assert engine.handle_response(annotated_text(annotations)).success is True


def test_official_model_dump_nullable_fields_are_accepted() -> None:
    engine = load_engine()
    result = engine.handle_response(
        {
            "content": [
                {
                    "type": "text",
                    "text": "ok",
                    "annotations": None,
                    "_meta": None,
                },
                {
                    "type": "resource_link",
                    "uri": "https://example.invalid/item",
                    "name": "item",
                    "title": None,
                    "description": None,
                    "mimeType": None,
                    "size": None,
                    "annotations": None,
                    "_meta": None,
                },
                {
                    "type": "resource",
                    "resource": {
                        "uri": "file:///tmp/item.txt",
                        "mimeType": None,
                        "_meta": None,
                        "text": "payload",
                    },
                    "annotations": None,
                    "_meta": None,
                },
            ],
            "structuredContent": None,
            "isError": False,
            "_meta": None,
        }
    )
    assert result.success is True
    assert isinstance(result.data, list)


def test_malformed_content_annotation_fields_fail_closed() -> None:
    engine = load_engine()
    malformed = (
        [],
        {"audience": "user"},
        {"audience": ["system"]},
        {"audience": [1]},
        {"priority": True},
        {"priority": "0.5"},
        {"priority": -0.1},
        {"priority": 1.1},
        {"priority": math.nan},
        {"priority": math.inf},
        {"priority": 10**10000},
        {"lastModified": 7},
        {"lastModified": ""},
        {"lastModified": "   "},
    )
    for annotations in malformed:
        result = engine.handle_response(annotated_text(annotations))
        assert result.success is False, annotations
        assert result.error_code == "MALFORMED_RESPONSE", annotations


def test_nullable_fields_do_not_weaken_non_null_validation() -> None:
    engine = load_engine()
    malformed_blocks = (
        {"type": "text", "text": "ok", "_meta": []},
        {
            "type": "resource_link",
            "uri": "https://example.invalid/item",
            "name": "item",
            "size": True,
        },
        {
            "type": "resource",
            "resource": {"uri": "file:///tmp/item", "text": "ok", "mimeType": []},
        },
    )
    for block in malformed_blocks:
        result = engine.handle_response({"content": [block]})
        assert result.success is False, block
        assert result.error_code == "MALFORMED_RESPONSE", block


def test_malformed_annotations_on_error_blocks_are_reported_as_malformed() -> None:
    engine = load_engine()
    result = engine.handle_response(
        {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": "upstream failed",
                    "annotations": {"priority": "high"},
                }
            ],
        }
    )
    assert result.success is False
    assert result.error_code == "MALFORMED_RESPONSE"
