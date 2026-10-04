"""Deterministic migration-matrix acceptance helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class MigrationInputKind(StrEnum):
    FRESH = "fresh"
    LEGACY = "legacy"
    CURRENT = "current"
    UNSUPPORTED = "unsupported"


class MigrationCaseResult(StrEnum):
    PASS = "pass"
    REJECT = "reject"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class MigrationInputSpec:
    input_ref: str
    kind: MigrationInputKind
    schema_identity: str | None


@dataclass(frozen=True)
class MigrationCaseEvidence:
    input_ref: str
    fixture_identity: str
    observed_pre_schema: str | None
    legacy_characteristic_refs: tuple[str, ...]
    absent_current_characteristic_refs: tuple[str, ...]
    exercised_entrypoint: str
    exercised_entrypoint_revision: str
    result: MigrationCaseResult
    observed_post_schema: str | None
    data_invariant_refs: tuple[str, ...]
    recovery_evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class MigrationAcceptanceAssessment:
    status: str
    findings: tuple[str, ...]
    exercised_inputs: tuple[MigrationInputSpec, ...]
    candidate_revision: str
    current_schema: str
    production_entrypoint: str
    production_entrypoint_revision: str

    def receipt(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "verdict": self.status,
            "candidate_revision": self.candidate_revision,
            "current_schema": self.current_schema,
            "production_entrypoint": self.production_entrypoint,
            "production_entrypoint_revision": self.production_entrypoint_revision,
            "exercised_inputs": [
                {
                    "input_ref": item.input_ref,
                    "kind": item.kind.value,
                    "schema_identity": item.schema_identity,
                }
                for item in self.exercised_inputs
            ],
            "failures": list(self.findings),
        }


def evaluate_migration_acceptance(
    *,
    candidate_revision: object,
    current_schema: object,
    production_entrypoint: object,
    production_entrypoint_revision: object,
    supported_inputs: object,
    unsupported_inputs: object,
    cases: object,
    require_current_rerun: object = False,
    require_interrupted_recovery: object = True,
) -> MigrationAcceptanceAssessment:
    """Evaluate migration-matrix evidence without executing a product migrator."""
    findings: list[str] = []
    candidate_value = (
        candidate_revision if isinstance(candidate_revision, str) and candidate_revision.strip() else ""
    )
    current_schema_value = (
        current_schema if isinstance(current_schema, str) and current_schema.strip() else ""
    )
    entrypoint_value = (
        production_entrypoint
        if isinstance(production_entrypoint, str) and production_entrypoint.strip()
        else ""
    )
    entrypoint_revision_value = (
        production_entrypoint_revision
        if isinstance(production_entrypoint_revision, str) and production_entrypoint_revision.strip()
        else ""
    )
    if not candidate_value:
        findings.append("candidate_revision must be a non-empty string")
    if not current_schema_value:
        findings.append("current_schema must be a non-empty string")
    if not entrypoint_value:
        findings.append("production_entrypoint must be a non-empty string")
    if not entrypoint_revision_value:
        findings.append("production_entrypoint_revision must be a non-empty string")
    if isinstance(require_current_rerun, bool):
        require_current_rerun_value = require_current_rerun
    else:
        findings.append("require_current_rerun must be boolean")
        require_current_rerun_value = False
    if isinstance(require_interrupted_recovery, bool):
        require_interrupted_recovery_value = require_interrupted_recovery
    else:
        findings.append("require_interrupted_recovery must be boolean")
        require_interrupted_recovery_value = True

    supported = _migration_input_specs(supported_inputs, "supported_inputs", findings)
    unsupported = _migration_input_specs(unsupported_inputs, "unsupported_inputs", findings)
    evidence_cases = _migration_cases(cases, "cases", findings)

    spec_by_ref: dict[str, MigrationInputSpec] = {}
    supported_refs: set[str] = set()
    matrix_items = tuple((item, False) for item in supported) + tuple((item, True) for item in unsupported)
    for spec, expected_unsupported in matrix_items:
        ref = spec.input_ref
        if not _non_empty_string(ref):
            findings.append("migration input_ref must be a non-empty string")
            continue
        if ref in spec_by_ref:
            findings.append(f"duplicate migration input_ref: {ref}")
            continue
        raw_kind: object = spec.kind
        if not isinstance(raw_kind, MigrationInputKind):
            findings.append(f"migration input {ref} has invalid kind")
            continue
        if expected_unsupported and raw_kind is not MigrationInputKind.UNSUPPORTED:
            findings.append(f"unsupported input {ref} must use kind=unsupported")
        if not expected_unsupported and raw_kind is MigrationInputKind.UNSUPPORTED:
            findings.append(f"supported input {ref} cannot use kind=unsupported")
        if raw_kind in {MigrationInputKind.LEGACY, MigrationInputKind.CURRENT}:
            if not _non_empty_string(spec.schema_identity):
                findings.append(f"input {ref} requires schema_identity")
        elif raw_kind is MigrationInputKind.UNSUPPORTED:
            if spec.schema_identity is not None and not _non_empty_string(spec.schema_identity):
                findings.append(f"unsupported input {ref} schema_identity must be a non-empty string or null")
        elif spec.schema_identity is not None:
            findings.append(f"fresh input {ref} must use schema_identity=None")
        if (
            raw_kind is MigrationInputKind.CURRENT
            and current_schema_value
            and spec.schema_identity != current_schema_value
        ):
            findings.append(f"current input {ref} does not match current_schema")
        spec_by_ref[ref] = spec
        if not expected_unsupported:
            supported_refs.add(ref)

    if not any(
        spec.kind is MigrationInputKind.FRESH for spec in supported if isinstance(spec.kind, MigrationInputKind)
    ):
        findings.append("supported migration matrix must include a fresh/empty input")

    case_by_ref: dict[str, list[MigrationCaseEvidence]] = {}
    for case in evidence_cases:
        ref = case.input_ref
        if not _non_empty_string(ref):
            findings.append("migration case input_ref must be a non-empty string")
            continue
        if not _non_empty_string(case.fixture_identity):
            findings.append(f"migration case {ref} requires immutable fixture_identity")
        raw_pre_schema: object = case.observed_pre_schema
        raw_post_schema: object = case.observed_post_schema
        if raw_pre_schema is not None and not isinstance(raw_pre_schema, str):
            findings.append(f"migration case {ref} observed_pre_schema must be string or null")
        if raw_post_schema is not None and not isinstance(raw_post_schema, str):
            findings.append(f"migration case {ref} observed_post_schema must be string or null")
        _validate_string_refs(
            case.legacy_characteristic_refs,
            f"migration case {ref} legacy_characteristic_refs",
            findings,
        )
        _validate_string_refs(
            case.absent_current_characteristic_refs,
            f"migration case {ref} absent_current_characteristic_refs",
            findings,
        )
        _validate_string_refs(case.data_invariant_refs, f"migration case {ref} data_invariant_refs", findings)
        _validate_string_refs(case.recovery_evidence_refs, f"migration case {ref} recovery_evidence_refs", findings)
        if not _non_empty_string(case.exercised_entrypoint):
            findings.append(f"migration case {ref} requires exercised_entrypoint")
        elif entrypoint_value and case.exercised_entrypoint != entrypoint_value:
            findings.append(f"migration case {ref} exercised wrong entrypoint: {case.exercised_entrypoint}")
        if not _non_empty_string(case.exercised_entrypoint_revision):
            findings.append(f"migration case {ref} requires exercised_entrypoint_revision")
        elif entrypoint_revision_value and case.exercised_entrypoint_revision != entrypoint_revision_value:
            findings.append(
                f"migration case {ref} exercised wrong entrypoint revision: {case.exercised_entrypoint_revision}"
            )
        raw_result: object = case.result
        if not isinstance(raw_result, MigrationCaseResult):
            findings.append(f"migration case {ref} has invalid result")
            continue
        if ref not in spec_by_ref:
            findings.append(f"migration case references undeclared input: {ref}")
            continue
        case_by_ref.setdefault(ref, []).append(case)

    for ref, values in case_by_ref.items():
        terminal = [case for case in values if case.result in {MigrationCaseResult.PASS, MigrationCaseResult.REJECT}]
        if len(terminal) > 1:
            findings.append(f"migration input {ref} has multiple terminal cases")

    for spec in supported:
        if spec.input_ref not in supported_refs:
            continue
        values = case_by_ref.get(spec.input_ref, [])
        terminal = next(
            (case for case in values if case.result in {MigrationCaseResult.PASS, MigrationCaseResult.REJECT}),
            None,
        )
        if terminal is None:
            if spec.kind is MigrationInputKind.CURRENT and not require_current_rerun_value:
                continue
            findings.append(f"supported migration input not exercised: {spec.input_ref}")
            continue
        _validate_pre_state(spec, terminal, current_schema_value, findings)
        if terminal.result is not MigrationCaseResult.PASS:
            findings.append(f"supported migration input {spec.input_ref} did not pass")
        if current_schema_value and terminal.observed_post_schema != current_schema_value:
            findings.append(f"supported migration input {spec.input_ref} did not reach current schema")
        if spec.kind in {MigrationInputKind.LEGACY, MigrationInputKind.CURRENT} and not _non_empty_string_sequence(
            terminal.data_invariant_refs
        ):
            findings.append(f"supported migration input {spec.input_ref} did not prove data invariants")

    for spec in unsupported:
        if spec.input_ref not in spec_by_ref:
            continue
        values = case_by_ref.get(spec.input_ref, [])
        terminal = next(
            (case for case in values if case.result in {MigrationCaseResult.PASS, MigrationCaseResult.REJECT}),
            None,
        )
        if terminal is None:
            findings.append(f"unsupported migration input not exercised: {spec.input_ref}")
            continue
        _validate_pre_state(spec, terminal, current_schema_value, findings)
        if terminal.result is not MigrationCaseResult.REJECT:
            findings.append(f"unsupported migration input {spec.input_ref} was not deliberately rejected")
        if current_schema_value and terminal.observed_post_schema == current_schema_value:
            findings.append(f"unsupported migration input {spec.input_ref} was silently normalized to current")

    if require_interrupted_recovery_value:
        legacy_recovery_refs = {
            spec.input_ref
            for spec in supported
            if spec.input_ref in supported_refs and spec.kind is MigrationInputKind.LEGACY
        }
        recovery_input_refs = legacy_recovery_refs or {
            spec.input_ref
            for spec in supported
            if spec.input_ref in supported_refs and spec.kind is MigrationInputKind.FRESH
        }
        recovery_cases = [
            case
            for case in evidence_cases
            if case.result is MigrationCaseResult.INTERRUPTED and case.input_ref in recovery_input_refs
        ]
        for case in recovery_cases:
            spec = spec_by_ref.get(case.input_ref)
            if spec is not None:
                _validate_pre_state(spec, case, current_schema_value, findings)
        if not recovery_cases:
            findings.append("interrupted mutating supported migration recovery case is required")
        elif not any(_non_empty_string_sequence(case.recovery_evidence_refs) for case in recovery_cases):
            findings.append("interrupted migration case did not prove recovery invariants")

    exercised = tuple(spec_by_ref[ref] for ref in sorted(case_by_ref))
    unique_findings = tuple(sorted(set(findings)))
    return MigrationAcceptanceAssessment(
        status="pass" if not unique_findings else "fail",
        findings=unique_findings,
        exercised_inputs=exercised,
        candidate_revision=candidate_value,
        current_schema=current_schema_value,
        production_entrypoint=entrypoint_value,
        production_entrypoint_revision=entrypoint_revision_value,
    )


def validate_migration_acceptance_receipt(receipt: object) -> tuple[str, ...]:
    """Validate the bounded receipt consumed by candidate/release gates."""
    if not isinstance(receipt, dict):
        return ("migration acceptance receipt must be an object",)
    allowed = {
        "schema_version",
        "verdict",
        "candidate_revision",
        "current_schema",
        "production_entrypoint",
        "production_entrypoint_revision",
        "exercised_inputs",
        "failures",
    }
    findings: list[str] = []
    raw_keys = list(receipt)
    if not all(isinstance(key, str) for key in raw_keys):
        findings.append("migration acceptance receipt field names must be strings")
    extra = sorted(key for key in raw_keys if isinstance(key, str) and key not in allowed)
    if extra:
        findings.append("migration acceptance receipt has unknown fields: " + ", ".join(extra))
    version = receipt.get("schema_version")
    if isinstance(version, bool) or version != 1:
        findings.append("migration acceptance receipt schema_version must be integer 1")
    verdict = receipt.get("verdict")
    if not isinstance(verdict, str) or verdict not in {"pass", "fail"}:
        findings.append("migration acceptance receipt verdict must be pass or fail")
    for field in (
        "candidate_revision",
        "current_schema",
        "production_entrypoint",
        "production_entrypoint_revision",
    ):
        value = receipt.get(field)
        if not _non_empty_string(value):
            findings.append(f"migration acceptance receipt {field} must be a non-empty string")
    exercised = receipt.get("exercised_inputs")
    allow_empty_exercised = verdict == "fail"
    if not _exercised_input_array(exercised, allow_empty=allow_empty_exercised):
        findings.append(
            "migration acceptance receipt exercised_inputs must be a unique array of input identity objects"
        )
    failures = receipt.get("failures")
    if not _string_array(failures, allow_empty=True):
        findings.append("migration acceptance receipt failures must be a unique string array")
    elif verdict == "pass" and failures:
        findings.append("passing migration acceptance receipt cannot contain failures")
    elif verdict == "fail" and not failures:
        findings.append("failing migration acceptance receipt must contain failures")
    return tuple(sorted(set(findings)))


def _migration_input_specs(
    value: object,
    field: str,
    findings: list[str],
) -> tuple[MigrationInputSpec, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        findings.append(f"{field} must be an array")
        return ()
    result: list[MigrationInputSpec] = []
    for item in value:
        if not isinstance(item, MigrationInputSpec):
            findings.append(f"{field} entries must be MigrationInputSpec records")
            continue
        result.append(item)
    return tuple(result)


def _migration_cases(
    value: object,
    field: str,
    findings: list[str],
) -> tuple[MigrationCaseEvidence, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        findings.append(f"{field} must be an array")
        return ()
    result: list[MigrationCaseEvidence] = []
    for item in value:
        if not isinstance(item, MigrationCaseEvidence):
            findings.append(f"{field} entries must be MigrationCaseEvidence records")
            continue
        result.append(item)
    return tuple(result)


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_empty_string_sequence(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and bool(value)
        and all(_non_empty_string(item) for item in value)
        and len(set(value)) == len(value)
    )


def _validate_string_refs(value: object, field: str, findings: list[str]) -> None:
    if (
        not isinstance(value, tuple)
        or not all(_non_empty_string(item) for item in value)
        or len(set(value)) != len(value)
    ):
        findings.append(f"{field} must be a unique tuple of non-empty strings")


def _exercised_input_array(value: object, *, allow_empty: bool) -> bool:
    if not isinstance(value, list):
        return False
    if not value:
        return allow_empty
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"input_ref", "kind", "schema_identity"}:
            return False
        input_ref = item.get("input_ref")
        kind = item.get("kind")
        schema_identity = item.get("schema_identity")
        if not isinstance(input_ref, str) or not input_ref.strip() or input_ref in seen:
            return False
        seen.add(input_ref)
        if not isinstance(kind, str) or kind not in {member.value for member in MigrationInputKind}:
            return False
        if kind in {MigrationInputKind.LEGACY.value, MigrationInputKind.CURRENT.value}:
            if not _non_empty_string(schema_identity):
                return False
        elif kind == MigrationInputKind.FRESH.value:
            if schema_identity is not None:
                return False
        elif schema_identity is not None and not _non_empty_string(schema_identity):
            return False
    return True


def _string_array(value: object, *, allow_empty: bool) -> bool:
    if not isinstance(value, list):
        return False
    if not allow_empty and not value:
        return False
    return all(_non_empty_string(item) for item in value) and len(set(value)) == len(value)


def _validate_pre_state(
    spec: MigrationInputSpec,
    case: MigrationCaseEvidence,
    current_schema: str,
    findings: list[str],
) -> None:
    if spec.kind is MigrationInputKind.FRESH:
        if case.observed_pre_schema is not None:
            findings.append(f"fresh migration input {spec.input_ref} was not empty before migration")
        return
    if case.observed_pre_schema != spec.schema_identity:
        findings.append(
            f"migration input {spec.input_ref} pre-state mismatch: expected {spec.schema_identity}, "
            f"observed {case.observed_pre_schema}"
        )
    if spec.kind is MigrationInputKind.LEGACY:
        if not _non_empty_string_sequence(case.legacy_characteristic_refs):
            findings.append(f"migration input {spec.input_ref} lacks legacy pre-state proof")
        if not _non_empty_string_sequence(case.absent_current_characteristic_refs):
            findings.append(f"migration input {spec.input_ref} lacks proof current characteristics were absent")
    elif spec.kind is MigrationInputKind.UNSUPPORTED:
        if not _non_empty_string_sequence(case.absent_current_characteristic_refs):
            findings.append(f"migration input {spec.input_ref} lacks proof current characteristics were absent")
    if (
        spec.kind in {MigrationInputKind.LEGACY, MigrationInputKind.UNSUPPORTED}
        and current_schema
        and case.observed_pre_schema == current_schema
    ):
        findings.append(f"migration input {spec.input_ref} was already current before migration")
