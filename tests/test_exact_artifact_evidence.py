"""Exact artifact evidence construction regressions."""

from __future__ import annotations

import importlib.util
import json
import sys
import unicodedata
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "contracts" / "artifact_evidence.py"
SCHEMA_PATH = ROOT / "contracts" / "artifact-evidence.schema.json"
RECEIPT_SCHEMA_PATH = ROOT / "contracts" / "verification-receipt.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _load():
    spec = importlib.util.spec_from_file_location("artifact_evidence_test", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _profile(module, **kwargs):
    return module.ConstructionProfile(
        "artifact-tree/v1",
        "policy:artifact-evidence/v1",
        module.ArtifactBounds(**kwargs),
    )


def _evidence(module, entries, **kwargs):
    return module.construct_artifact_evidence(
        entries,
        subject_ref="artifact:candidate",
        profile=kwargs.pop("profile", _profile(module)),
        requested_kind=kwargs.pop("requested_kind", "package_spec"),
        requested_value=kwargs.pop("requested_value", "pkg>=1"),
        enumeration_complete=kwargs.pop("enumeration_complete", True),
        **kwargs,
    )


def _schema_errors(value):
    return list(Draft202012Validator(SCHEMA).iter_errors(value))


def test_collision_safe_framing_breaks_historical_delimiter_collision() -> None:
    module = _load()
    single = [module.ArtifactEntry("a", b"b\x00c\x00d")]
    split = [
        module.ArtifactEntry("a", b"b"),
        module.ArtifactEntry("c", b"d"),
    ]

    def naive(entries):
        return b"".join(
            entry.path.encode() + b"\x00" + entry.content + b"\x00"
            for entry in entries
        )

    assert naive(single) == naive(split)
    one = _evidence(module, single)
    two = _evidence(module, split)
    assert one["observed_identity"]["artifact_digest"] != two["observed_identity"]["artifact_digest"]
    assert _schema_errors(one) == []
    assert _schema_errors(two) == []


def test_order_is_deterministic_and_paths_are_nfc_normalized() -> None:
    module = _load()
    composed = "caf\u00e9.txt"
    decomposed = unicodedata.normalize("NFD", composed)

    one = _evidence(
        module,
        [
            module.ArtifactEntry("z.txt", b"z"),
            module.ArtifactEntry(decomposed, b"cafe"),
        ],
    )
    two = _evidence(
        module,
        [
            module.ArtifactEntry(composed, b"cafe"),
            module.ArtifactEntry("z.txt", b"z"),
        ],
    )

    assert one["observed_identity"]["artifact_digest"] == two["observed_identity"]["artifact_digest"]
    with pytest.raises(module.ArtifactEvidenceError, match="duplicate normalized artifact path"):
        _evidence(
            module,
            [
                module.ArtifactEntry(composed, b"a"),
                module.ArtifactEntry(decomposed, b"b"),
            ],
        )


def test_representative_large_artifact_fits_reviewed_profile() -> None:
    module = _load()
    blob = b"x" * 8192
    entries = [
        module.ArtifactEntry(f"pkg/{index:04d}.bin", blob)
        for index in range(2600)
    ]

    result = _evidence(
        module,
        entries,
        profile=_profile(
            module,
            max_files=3000,
            max_bytes=32 * 1024 * 1024,
            max_depth=8,
            max_duration_ms=30_000,
        ),
    )

    assert result["coverage"]["state"] == "exact"
    assert result["coverage"]["file_count"] == 2600
    expected_bytes = 2500 * (8192 + len("pkg/0000.bin".encode("utf-8")))
    assert result["coverage"]["byte_count"] == expected_bytes
    assert result["coverage"]["max_depth_observed"] == 2
    assert result["coverage"]["limit_hit"] is False
    assert result["coverage"]["omitted_reason"] is None
    assert result["coverage"]["enumeration_complete"] is True
    assert result["claims"]["artifact_exact"] == "true"
    assert _schema_errors(result) == []


def test_file_byte_and_depth_limits_never_return_exact() -> None:
    module = _load()
    cases = (
        (
            _profile(
                module,
                max_files=1,
                max_bytes=100,
                max_depth=8,
                max_duration_ms=1000,
            ),
            [
                module.ArtifactEntry("a", b"a"),
                module.ArtifactEntry("b", b"b"),
            ],
            "file_limit",
        ),
        (
            _profile(
                module,
                max_files=10,
                max_bytes=1,
                max_depth=8,
                max_duration_ms=1000,
            ),
            [module.ArtifactEntry("a", b"ab")],
            "byte_limit",
        ),
        (
            _profile(
                module,
                max_files=10,
                max_bytes=100,
                max_depth=1,
                max_duration_ms=1000,
            ),
            [module.ArtifactEntry("a/b", b"x")],
            "depth_limit",
        ),
    )

    for profile, entries, reason in cases:
        result = _evidence(module, entries, profile=profile)
        assert result["coverage"]["state"] == "partial"
        assert result["coverage"]["limit_hit"] is True
        assert result["coverage"]["omitted_reason"] == reason
        assert result["observed_identity"]["artifact_digest"] is None
        assert result["claims"]["artifact_exact"] == "false"
        assert _schema_errors(result) == []


def test_byte_bound_includes_normalized_path_bytes() -> None:
    module = _load()
    result = _evidence(
        module,
        [module.ArtifactEntry("path", b"")],
        profile=_profile(
            module,
            max_files=10,
            max_bytes=3,
            max_depth=8,
            max_duration_ms=1000,
        ),
    )
    assert result["coverage"]["state"] == "partial"
    assert result["coverage"]["omitted_reason"] == "byte_limit"


def test_time_limit_after_final_hash_cannot_return_exact() -> None:
    module = _load()
    ticks = iter([0, 0, 0, 2_000_000])

    result = _evidence(
        module,
        [module.ArtifactEntry("a", b"x")],
        profile=_profile(
            module,
            max_files=10,
            max_bytes=100,
            max_depth=8,
            max_duration_ms=1,
        ),
        clock_ns=lambda: next(ticks),
    )

    assert result["coverage"]["state"] == "partial"
    assert result["coverage"]["limit_hit"] is True
    assert result["coverage"]["omitted_reason"] == "time_limit"
    assert result["coverage"]["enumeration_complete"] is True
    assert result["observed_identity"]["artifact_digest"] is None
    assert _schema_errors(result) == []


def test_incomplete_inventory_and_unsupported_type_are_non_exact() -> None:
    module = _load()

    incomplete = _evidence(
        module,
        [module.ArtifactEntry("a", b"a")],
        enumeration_complete=False,
    )
    assert incomplete["coverage"]["state"] == "partial"
    assert incomplete["coverage"]["omitted_reason"] == "enumeration_incomplete"

    unsupported = _evidence(
        module,
        [module.ArtifactEntry("link", b"", file_type="symlink")],
    )
    assert unsupported["coverage"]["state"] == "unknown"
    assert unsupported["coverage"]["omitted_reason"] == "unsupported_file_type"
    assert unsupported["observed_identity"]["artifact_digest"] is None


def test_requested_identity_survives_fallback_observation() -> None:
    module = _load()
    result = _evidence(
        module,
        [module.ArtifactEntry("a", b"a")],
        requested_kind="version",
        requested_value="1.0.0",
        package_version="2.0.0",
        source_revision=None,
        observation_refs=("provider:fallback",),
    )

    assert result["requested_identity"] == {
        "kind": "version",
        "value": "1.0.0",
        "preserved_from_admission": True,
    }
    assert result["observed_identity"]["package_version"] == "2.0.0"
    assert result["claims"]["requested_identity_matched"] == "false"
    assert result["claims"]["source_compatibility_established"] == "unknown"
    assert result["claims"]["runtime_compatibility_established"] == "unknown"
    assert module.validate_artifact_evidence_semantics(result) == ()


def test_exact_digest_does_not_establish_source_or_runtime_compatibility() -> None:
    module = _load()
    result = _evidence(module, [module.ArtifactEntry("a", b"a")])
    assert result["claims"]["artifact_exact"] == "true"
    assert result["claims"]["source_compatibility_established"] == "unknown"
    assert result["claims"]["runtime_compatibility_established"] == "unknown"

    tampered = json.loads(json.dumps(result))
    tampered["claims"]["source_compatibility_established"] = "true"
    assert (
        "artifact construction cannot establish source compatibility"
        in module.validate_artifact_evidence_semantics(tampered)
    )
    assert _schema_errors(tampered)


def test_fail_closed_digest_accessor_is_reusable_by_lineage_consumers() -> None:
    module = _load()
    exact = _evidence(module, [module.ArtifactEntry("a", b"a")])
    assert module.require_exact_artifact_digest(exact) == exact["observed_identity"]["artifact_digest"]

    partial = _evidence(
        module,
        [module.ArtifactEntry("a", b"a")],
        enumeration_complete=False,
    )
    with pytest.raises(module.ArtifactEvidenceError, match="not exact"):
        module.require_exact_artifact_digest(partial)

    excluded = json.loads(json.dumps(exact))
    excluded["construction_profile"]["exclusions"] = ["a"]
    with pytest.raises(module.ArtifactEvidenceError, match="unknown construction_profile fields"):
        module.require_exact_artifact_digest(excluded)


def test_runtime_constructor_inputs_fail_closed_before_emitting_invalid_evidence() -> None:
    module = _load()
    with pytest.raises(module.ArtifactEvidenceError, match="requested_kind"):
        module.construct_artifact_evidence(
            [module.ArtifactEntry("a", b"a")],
            subject_ref="artifact:candidate",
            profile=_profile(module),
            requested_kind="not-supported",
            requested_value="x",
            enumeration_complete=True,
        )
    with pytest.raises(module.ArtifactEvidenceError, match="ConstructionProfile"):
        module.construct_artifact_evidence(
            [module.ArtifactEntry("a", b"a")],
            subject_ref="artifact:candidate",
            profile={},
            requested_kind="other",
            requested_value="x",
            enumeration_complete=True,
        )


def test_profile_digest_detects_material_change_and_manual_tampering() -> None:
    module = _load()
    one = _evidence(
        module,
        [module.ArtifactEntry("a", b"a")],
        profile=module.ConstructionProfile("v1", "policy:a"),
    )
    two = _evidence(
        module,
        [module.ArtifactEntry("a", b"a")],
        profile=module.ConstructionProfile("v2", "policy:a"),
    )

    assert not module.construction_profiles_comparable(
        one["construction_profile"],
        two["construction_profile"],
    )

    tampered = json.loads(json.dumps(one))
    tampered["construction_profile"]["revision"] = "v2"
    assert any(
        "profile_digest" in finding
        for finding in module.validate_artifact_evidence_semantics(tampered)
    )


def test_candidate_defined_exclusion_field_is_rejected() -> None:
    module = _load()
    result = _evidence(module, [module.ArtifactEntry("a", b"a")])
    result["construction_profile"]["exclusions"] = ["a"]
    assert any(
        "Additional properties are not allowed" in error.message
        for error in _schema_errors(result)
    )


def test_malformed_paths_and_non_bytes_fail_closed() -> None:
    module = _load()
    for path in ("/abs", "../escape", "a//b", "a\\b", "a\x00b"):
        with pytest.raises(module.ArtifactEvidenceError):
            _evidence(module, [module.ArtifactEntry(path, b"x")])

    with pytest.raises(module.ArtifactEvidenceError, match="content must be bytes"):
        _evidence(module, [module.ArtifactEntry("a", "text")])


def test_verification_receipt_schema_consumes_artifact_evidence_contract() -> None:
    receipt_schema = json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
    candidate = receipt_schema["properties"]["candidate"]["properties"]
    assert candidate["artifact_evidence"] == {
        "$ref": "artifact-evidence.schema.json"
    }
