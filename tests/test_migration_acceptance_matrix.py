"""Migration acceptance regressions for exact legacy-state and migrator identity."""

from __future__ import annotations

import fnmatch
import importlib.util
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/qa-change-verifier"
TOOL = SKILL / "tools/migration_acceptance.py"
QUALITY_TARGETS = ROOT / "scripts/quality_targets.py"

CURRENT = "v2"
ENTRY = "app.Migrations.run"
ENTRY_REV = "sha256:entrypoint-v2"
CANDIDATE = "candidate-sha-42"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _covered(targets: tuple[str, ...], path: str) -> bool:
    return any(
        path == target or path.startswith(f"{target.rstrip('/')}/") or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


def _specs(module: ModuleType) -> tuple[tuple[object, ...], tuple[object, ...]]:
    supported = (
        module.MigrationInputSpec("fresh", module.MigrationInputKind.FRESH, None),
        module.MigrationInputSpec("v1", module.MigrationInputKind.LEGACY, "v1"),
        module.MigrationInputSpec("current", module.MigrationInputKind.CURRENT, CURRENT),
    )
    unsupported = (module.MigrationInputSpec("v0", module.MigrationInputKind.UNSUPPORTED, "v0"),)
    return supported, unsupported


def _case(
    module: ModuleType,
    ref: str,
    pre: str | None,
    result: object | None = None,
    post: str | None = CURRENT,
    *,
    legacy_refs: tuple[str, ...] = ("schema:legacy-column",),
    absent_refs: tuple[str, ...] = ("schema:no-current-column",),
    entry: str = ENTRY,
    entry_revision: str = ENTRY_REV,
    data_refs: tuple[str, ...] = ("data:representative-row",),
    recovery_refs: tuple[str, ...] = (),
) -> object:
    if result is None:
        result = module.MigrationCaseResult.PASS
    return module.MigrationCaseEvidence(
        input_ref=ref,
        fixture_identity=f"fixture:{ref}:sha256:abc",
        observed_pre_schema=pre,
        legacy_characteristic_refs=legacy_refs,
        absent_current_characteristic_refs=absent_refs,
        exercised_entrypoint=entry,
        exercised_entrypoint_revision=entry_revision,
        result=result,
        observed_post_schema=post,
        data_invariant_refs=data_refs,
        recovery_evidence_refs=recovery_refs,
    )


def _evaluate(module: ModuleType, cases: tuple[object, ...], **changes: object) -> object:
    supported, unsupported = _specs(module)
    values: dict[str, object] = {
        "candidate_revision": CANDIDATE,
        "current_schema": CURRENT,
        "production_entrypoint": ENTRY,
        "production_entrypoint_revision": ENTRY_REV,
        "supported_inputs": supported,
        "unsupported_inputs": unsupported,
        "cases": cases,
    }
    values.update(changes)
    return module.evaluate_migration_acceptance(**values)


def test_complete_matrix_passes_and_receipt_names_exercised_inputs() -> None:
    module = _load("migration_acceptance_complete", TOOL)
    cases = (
        _case(module, "fresh", None, legacy_refs=(), absent_refs=()),
        _case(module, "v1", "v1"),
        _case(module, "current", CURRENT, legacy_refs=(), absent_refs=()),
        _case(module, "v0", "v0", module.MigrationCaseResult.REJECT, "v0", data_refs=()),
        _case(
            module,
            "v1",
            "v1",
            module.MigrationCaseResult.INTERRUPTED,
            "v1",
            data_refs=(),
            recovery_refs=("recovery:transaction-rolled-back",),
        ),
    )
    assessment = _evaluate(module, cases, require_current_rerun=True)
    assert assessment.status == "pass"
    receipt = assessment.receipt()
    assert receipt["candidate_revision"] == CANDIDATE
    assert receipt["exercised_inputs"] == ["current", "fresh", "v0", "v1"]
    assert module.validate_migration_acceptance_receipt(receipt) == ()


def test_current_bootstrap_false_positive_is_rejected() -> None:
    module = _load("migration_acceptance_bootstrap", TOOL)
    db = sqlite3.connect(":memory:")
    db.execute("create table schema_meta(version text not null)")
    db.execute("insert into schema_meta values ('v1')")
    db.execute("create table items(id integer primary key, legacy_name text)")

    # Historical failure: the fixture runs current bootstrap before migration-under-test.
    db.execute("update schema_meta set version='v2'")
    db.execute("alter table items add column display_name text")
    observed = db.execute("select version from schema_meta").fetchone()[0]
    columns = {row[1] for row in db.execute("pragma table_info(items)")}
    legacy_refs = ("sqlite:legacy_name",) if "legacy_name" in columns else ()
    absent_refs = ("sqlite:display_name-absent",) if "display_name" not in columns else ()

    cases = (
        _case(module, "fresh", None, legacy_refs=(), absent_refs=()),
        _case(module, "v1", observed, legacy_refs=legacy_refs, absent_refs=absent_refs),
        _case(module, "v0", "v0", module.MigrationCaseResult.REJECT, "v0", data_refs=()),
        _case(
            module,
            "v1",
            "v1",
            module.MigrationCaseResult.INTERRUPTED,
            "v1",
            data_refs=(),
            recovery_refs=("recovery:transaction-rolled-back",),
        ),
    )
    assessment = _evaluate(module, cases)
    assert assessment.status == "fail"
    assert any("pre-state mismatch" in finding for finding in assessment.findings)
    assert any("current characteristics were absent" in finding for finding in assessment.findings)


def test_wrong_migrator_identity_or_revision_is_harness_failure() -> None:
    module = _load("migration_acceptance_entrypoint", TOOL)
    cases = (
        _case(module, "fresh", None, legacy_refs=(), absent_refs=()),
        _case(module, "v1", "v1", entry="test.Migrations.run", entry_revision="sha256:wrong"),
        _case(module, "v0", "v0", module.MigrationCaseResult.REJECT, "v0", data_refs=()),
        _case(
            module,
            "v1",
            "v1",
            module.MigrationCaseResult.INTERRUPTED,
            "v1",
            data_refs=(),
            recovery_refs=("recovery:transaction-rolled-back",),
        ),
    )
    assessment = _evaluate(module, cases)
    assert any("wrong entrypoint:" in finding for finding in assessment.findings)
    assert any("wrong entrypoint revision" in finding for finding in assessment.findings)


def test_missing_predecessor_and_silent_unsupported_normalization_fail() -> None:
    module = _load("migration_acceptance_matrix_gaps", TOOL)
    cases = (
        _case(module, "fresh", None, legacy_refs=(), absent_refs=()),
        _case(module, "v0", "v0", module.MigrationCaseResult.PASS, CURRENT),
        _case(
            module,
            "v1",
            "v1",
            module.MigrationCaseResult.INTERRUPTED,
            "v1",
            data_refs=(),
            recovery_refs=("recovery:transaction-rolled-back",),
        ),
    )
    assessment = _evaluate(module, cases)
    assert "supported migration input not exercised: v1" in assessment.findings
    assert "unsupported migration input v0 was not deliberately rejected" in assessment.findings
    assert "unsupported migration input v0 was silently normalized to current" in assessment.findings


def test_legacy_prestate_data_and_recovery_require_evidence_refs() -> None:
    module = _load("migration_acceptance_evidence_refs", TOOL)
    cases = (
        _case(module, "fresh", None, legacy_refs=(), absent_refs=()),
        _case(module, "v1", "v1", legacy_refs=(), absent_refs=(), data_refs=()),
        _case(module, "v0", "v0", module.MigrationCaseResult.REJECT, "v0", data_refs=()),
        _case(module, "v1", "v1", module.MigrationCaseResult.INTERRUPTED, "v1", data_refs=()),
    )
    assessment = _evaluate(module, cases)
    assert "migration input v1 lacks legacy pre-state proof" in assessment.findings
    assert "migration input v1 lacks proof current characteristics were absent" in assessment.findings
    assert "supported migration input v1 did not prove data invariants" in assessment.findings
    assert "interrupted migration case did not prove recovery invariants" in assessment.findings


def test_current_rerun_is_required_only_when_policy_requests_it() -> None:
    module = _load("migration_acceptance_current_rerun", TOOL)
    cases = (
        _case(module, "fresh", None, legacy_refs=(), absent_refs=()),
        _case(module, "v1", "v1"),
        _case(module, "v0", "v0", module.MigrationCaseResult.REJECT, "v0", data_refs=()),
        _case(
            module,
            "v1",
            "v1",
            module.MigrationCaseResult.INTERRUPTED,
            "v1",
            data_refs=(),
            recovery_refs=("recovery:transaction-rolled-back",),
        ),
    )
    assert _evaluate(module, cases).status == "pass"
    required = _evaluate(module, cases, require_current_rerun=True)
    assert "supported migration input not exercised: current" in required.findings


def test_receipt_validation_is_closed_and_fail_closed() -> None:
    module = _load("migration_acceptance_receipt", TOOL)
    valid = {
        "schema_version": 1,
        "verdict": "pass",
        "candidate_revision": CANDIDATE,
        "current_schema": CURRENT,
        "production_entrypoint": ENTRY,
        "production_entrypoint_revision": ENTRY_REV,
        "exercised_inputs": ["fresh", "v1"],
        "failures": [],
    }
    assert module.validate_migration_acceptance_receipt(valid) == ()

    malformed = dict(valid)
    malformed["schema_version"] = True
    malformed["extra"] = "candidate-controlled"
    malformed["failures"] = ["unexpected"]
    findings = module.validate_migration_acceptance_receipt(malformed)
    assert "migration acceptance receipt schema_version must be integer 1" in findings
    assert any("unknown fields" in finding for finding in findings)
    assert "passing migration acceptance receipt cannot contain failures" in findings


def test_tool_is_manifested_and_in_quality_inventories() -> None:
    manifest = yaml.safe_load((SKILL / "manifest.yaml").read_text(encoding="utf-8"))
    assert "tools/migration_acceptance.py" in manifest["required"]

    inventories = _load("migration_acceptance_quality_targets", QUALITY_TARGETS)
    path = "skills/qa-change-verifier/tools/migration_acceptance.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)


def test_unsupported_interruption_cannot_satisfy_supported_recovery_proof() -> None:
    module = _load("migration_acceptance_recovery_scope", TOOL)
    cases = (
        _case(module, "fresh", None, legacy_refs=(), absent_refs=()),
        _case(module, "v1", "v1"),
        _case(module, "v0", "v0", module.MigrationCaseResult.REJECT, "v0", data_refs=()),
        _case(
            module,
            "v0",
            "v0",
            module.MigrationCaseResult.INTERRUPTED,
            "v0",
            data_refs=(),
            recovery_refs=("recovery:unsupported-path",),
        ),
    )
    assessment = _evaluate(module, cases)
    assert "interrupted supported migration recovery case is required" in assessment.findings
