from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

ROUTING_KINDS = {"positive", "negative", "collision"}
BEHAVIOR_KINDS = {"representative", "regression"}
BASELINE_MODES = {"required", "optional", "not-applicable"}
REQUIRED_SUITES = {"routing.yaml": "routing", "behavior.yaml": "behavior"}


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str


def _finding(code: str, path: Path, message: str) -> Finding:
    return Finding(code=code, path=path.as_posix(), message=message)


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas/skill-eval.schema.json"


def _schema() -> dict[str, object]:
    value = json.loads(_schema_path().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("skill eval schema must contain an object")
    Draft202012Validator.check_schema(value)
    return cast(dict[str, object], value)


def _load_mapping(path: Path) -> tuple[dict[str, Any] | None, Finding | None]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        return None, _finding("skill.eval.invalid", path, f"eval suite could not be parsed: {exc}")
    if not isinstance(value, dict):
        return None, _finding("skill.eval.invalid", path, "eval suite must contain a mapping")
    return cast(dict[str, Any], value), None


def validate_suite(
    path: Path,
    expected_skill: str | None = None,
) -> list[Finding]:
    value, load_finding = _load_mapping(path)
    if load_finding is not None:
        return [load_finding]
    assert value is not None

    try:
        schema = _schema()
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, SchemaError) as exc:
        return [
            _finding(
                "skill.eval.schema-unavailable",
                _schema_path(),
                f"skill eval schema could not be loaded: {exc}",
            )
        ]

    findings: list[Finding] = []
    validator = Draft202012Validator(schema)
    for error in sorted(
        validator.iter_errors(value),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    ):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        findings.append(
            _finding(
                "skill.eval.schema",
                path,
                f"{location}: {error.message}",
            )
        )

    # Schema-invalid data is already fully enumerated by jsonschema. Stop here so
    # malformed collection members cannot crash semantic checks below.
    if findings:
        return findings

    skill = cast(str, value["skill"])
    suite = cast(str, value["suite"])
    cases = cast(list[dict[str, Any]], value["cases"])

    if expected_skill is not None and skill != expected_skill:
        findings.append(
            _finding(
                "skill.eval.skill-mismatch",
                path,
                f"expected skill {expected_skill!r}, got {skill!r}",
            )
        )

    seen: set[str] = set()
    for index, case in enumerate(cases):
        case_path = Path(f"{path.as_posix()}#cases[{index}]")
        case_id = cast(str, case["id"])
        if case_id in seen:
            findings.append(
                _finding(
                    "skill.eval.case-id-duplicate",
                    case_path,
                    f"duplicate case id: {case_id}",
                )
            )
        else:
            seen.add(case_id)

        kind = cast(str, case["kind"])
        if suite == "routing":
            if kind not in ROUTING_KINDS:
                findings.append(
                    _finding(
                        "skill.eval.routing-kind",
                        case_path,
                        f"routing kind must be one of {sorted(ROUTING_KINDS)}",
                    )
                )
                continue

            selected = cast(list[str] | None, case.get("selected_skills"))
            rejected = cast(list[str] | None, case.get("rejected_skills"))
            if selected is None or rejected is None:
                findings.append(
                    _finding(
                        "skill.eval.routing-result",
                        case_path,
                        "routing case needs selected_skills and rejected_skills lists",
                    )
                )
                continue

            overlap = set(selected) & set(rejected)
            if overlap:
                findings.append(
                    _finding(
                        "skill.eval.routing-overlap",
                        case_path,
                        f"skills cannot be both selected and rejected: {sorted(overlap)}",
                    )
                )

            if kind == "positive" and (skill not in selected or skill in rejected):
                findings.append(
                    _finding(
                        "skill.eval.positive",
                        case_path,
                        "positive case must select the suite skill",
                    )
                )
            if kind == "negative" and (skill not in rejected or skill in selected):
                findings.append(
                    _finding(
                        "skill.eval.negative",
                        case_path,
                        "negative case must reject the suite skill",
                    )
                )
            if kind == "collision" and (skill not in selected or skill in rejected or not rejected):
                findings.append(
                    _finding(
                        "skill.eval.collision",
                        case_path,
                        "collision must select the suite skill and reject at least one neighbor",
                    )
                )
        else:
            if kind not in BEHAVIOR_KINDS:
                findings.append(
                    _finding(
                        "skill.eval.behavior-kind",
                        case_path,
                        f"behavior kind must be one of {sorted(BEHAVIOR_KINDS)}",
                    )
                )

            assertions = cast(list[str] | None, case.get("assertions"))
            if assertions is None or not assertions or not all(item.strip() for item in assertions):
                findings.append(
                    _finding(
                        "skill.eval.assertions",
                        case_path,
                        "behavior case needs non-empty semantic assertions",
                    )
                )

            baseline = cast(str | None, case.get("baseline"))
            if baseline not in BASELINE_MODES:
                findings.append(
                    _finding(
                        "skill.eval.baseline",
                        case_path,
                        f"baseline must be one of {sorted(BASELINE_MODES)}",
                    )
                )

    return findings


def _suite_kind_counts(path: Path) -> tuple[str | None, set[str]]:
    value, finding = _load_mapping(path)
    if finding is not None or value is None:
        return None, set()
    suite = value.get("suite")
    cases = value.get("cases")
    if not isinstance(suite, str) or not isinstance(cases, list):
        return None, set()
    kinds = {case.get("kind") for case in cases if isinstance(case, dict) and isinstance(case.get("kind"), str)}
    return suite, cast(set[str], kinds)


def validate_path(path: Path) -> list[Finding]:
    if path.is_file():
        return validate_suite(path)

    findings: list[Finding] = []
    if not path.is_dir():
        return [_finding("skill.eval.path", path, "eval path does not exist")]

    expected_skill = path.name if path.parent.name == "skills" else None
    sources = sorted(path.glob("*.yaml"))
    if not sources:
        return [_finding("skill.eval.empty", path, "eval directory contains no YAML suites")]

    by_name = {source.name: source for source in sources}
    for filename, expected_suite in REQUIRED_SUITES.items():
        source = by_name.get(filename)
        if source is None:
            findings.append(
                _finding(
                    "skill.eval.suite-missing",
                    path / filename,
                    f"required {expected_suite} suite is missing",
                )
            )
            continue
        suite, _ = _suite_kind_counts(source)
        if suite is not None and suite != expected_suite:
            findings.append(
                _finding(
                    "skill.eval.suite-filename",
                    source,
                    f"{filename} must declare suite: {expected_suite}",
                )
            )

    routing_kinds: set[str] = set()
    for source in sources:
        suite_findings = validate_suite(source, expected_skill)
        findings.extend(suite_findings)
        if suite_findings:
            continue
        suite, kinds = _suite_kind_counts(source)
        if suite == "routing":
            routing_kinds.update(kinds)

    if sources and "positive" not in routing_kinds:
        findings.append(
            _finding(
                "skill.eval.routing-positive-missing",
                path,
                "routing corpus needs at least one positive case",
            )
        )
    if sources and not (routing_kinds & {"negative", "collision"}):
        findings.append(
            _finding(
                "skill.eval.routing-boundary-missing",
                path,
                "routing corpus needs at least one negative or collision boundary case",
            )
        )

    return findings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate repository-level skill eval corpus files.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    findings = validate_path(args.path)
    if args.as_json:
        print(json.dumps([asdict(f) for f in findings], indent=2, sort_keys=True))
    else:
        for finding in findings:
            print(f"ERROR {finding.code} {finding.path}: {finding.message}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
