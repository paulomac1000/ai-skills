from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

from secret_taint import TaintGuard, TaintViolation, exposure_json, safe_json  # noqa: E402


def _credential() -> str:
    return "ghp_" + "A7b9" * 9


def _guard() -> tuple[TaintGuard, str]:
    raw = _credential()
    guard = TaintGuard()
    guard.observe(
        raw,
        sensitivity="credential",
        source_boundary="existing-config",
        opaque_ref="secret://github/release-token",
        exposure_state="model_visible",
    )
    return guard, raw


@pytest.mark.parametrize(
    "sink",
    ["delegated_prompt", "external_model_prompt", "tool_argument", "argv", "github_output", "durable_evidence", "log", "memory", "screenshot"],
)
def test_observed_credential_is_redacted_from_model_and_durable_sinks(sink: str) -> None:
    guard, raw = _guard()
    payload = f"token={raw}"
    sanitized = guard.sanitize_text(payload, sink=sink)
    assert raw not in sanitized
    assert "secret://github/release-token" in sanitized


def test_nested_tool_arguments_and_argv_do_not_replay_raw_value() -> None:
    guard, raw = _guard()
    tool_args = {"headers": {"Authorization": f"Bearer {raw}"}, "items": [raw]}
    argv = ["deploy", "--token", raw]
    sanitized_tool = guard.sanitize_value(tool_args, sink="tool_argument")
    sanitized_argv = guard.sanitize_value(argv, sink="argv")
    assert raw not in json.dumps(sanitized_tool)
    assert raw not in json.dumps(sanitized_argv)


def test_tainted_mapping_key_is_redacted_before_external_egress() -> None:
    guard, raw = _guard()
    sanitized = guard.sanitize_value({raw: "value"}, sink="tool_argument")
    serialized = json.dumps(sanitized, sort_keys=True)
    assert raw not in serialized
    assert "secret://github/release-token" in serialized


def test_tainted_mapping_key_collision_fails_closed() -> None:
    guard, raw = _guard()
    replacement = "[REDACTED:secret://github/release-token]"
    with pytest.raises(TaintViolation, match="collapse distinct mapping keys"):
        guard.sanitize_value({raw: "secret-key", replacement: "existing-key"}, sink="durable_evidence")


def test_protected_runtime_callback_can_use_secret_without_returning_it() -> None:
    guard, raw = _guard()
    observed: list[str] = []

    def operation(value: str) -> str:
        observed.append(value)
        return "ok"

    result, binding = guard.use_protected(
        "secret://github/release-token",
        channel="protected-env",
        purpose="release-authentication",
        operation=operation,
    )

    assert result == "ok"
    assert observed == [raw]
    receipt = json.dumps(binding.__dict__, sort_keys=True)
    assert raw not in receipt
    assert binding.opaque_ref == "secret://github/release-token"


def test_protected_channel_cannot_be_faked_by_putting_raw_secret_in_text() -> None:
    guard, raw = _guard()
    with pytest.raises(TaintViolation, match="use_protected"):
        guard.sanitize_text(raw, sink="protected_runtime_channel")


def test_unknown_sensitive_external_egress_fails_conservatively() -> None:
    guard = TaintGuard()
    with pytest.raises(TaintViolation, match="unknown-sensitive"):
        guard.guard_unknown(
            sensitivity="unknown",
            sink="external_model_prompt",
            opaque_ref="candidate://unclassified-auth",
        )


def test_prior_model_visibility_does_not_clear_taint_for_later_github_output() -> None:
    guard, raw = _guard()
    first = guard.sanitize_text(f"observed {raw}", sink="delegated_prompt")
    second = guard.sanitize_text(f"post incident value {raw}", sink="github_output")
    assert raw not in first
    assert raw not in second


def test_exposure_record_is_redacted_and_schema_valid() -> None:
    guard, raw = _guard()
    record = guard.exposure_record(
        "secret://github/release-token",
        affected_sinks=("external_model_prompt", "github_output"),
    )
    serialized = exposure_json(record)
    assert raw not in serialized
    assert "sha256" not in serialized.casefold()
    payload = json.loads(serialized)
    schema = json.loads((CONTRACTS / "secret-taint.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(payload)
    assert payload["exposure_state"] == "externally_exposed"


def test_safe_json_redacts_before_durable_serialization() -> None:
    guard, raw = _guard()
    serialized = safe_json(
        {"message": f"credential={raw}", "opaque": "secret://github/release-token"},
        guard,
        sink="durable_evidence",
    )
    assert raw not in serialized
    assert "secret://github/release-token" in serialized
