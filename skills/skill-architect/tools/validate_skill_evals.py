from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

ROUTING_KINDS = {"positive", "negative", "collision"}
BEHAVIOR_KINDS = {"representative", "regression"}
BASELINE_MODES = {"required", "optional", "not-applicable"}


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str


def _finding(code: str, path: Path, message: str) -> Finding:
    return Finding(code=code, path=path.as_posix(), message=message)


def validate_suite(
    path: Path,
    expected_skill: str | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        return [_finding("skill.eval.invalid", path, "eval suite must contain a mapping")]

    if value.get("schema_version") != 1:
        findings.append(
            _finding(
                "skill.eval.schema-version",
                path,
                "schema_version must be 1",
            )
        )

    skill = value.get("skill")
    if not isinstance(skill, str) or not skill:
        findings.append(
            _finding(
                "skill.eval.skill",
                path,
                "skill must be a non-empty string",
            )
        )
    elif expected_skill is not None and skill != expected_skill:
        findings.append(
            _finding(
                "skill.eval.skill-mismatch",
                path,
                f"expected skill {expected_skill!r}, got {skill!r}",
            )
        )

    suite = value.get("suite")
    if suite not in {"routing", "behavior"}:
        findings.append(
            _finding(
                "skill.eval.suite",
                path,
                "suite must be routing or behavior",
            )
        )
        return findings

    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        findings.append(
            _finding(
                "skill.eval.cases",
                path,
                "cases must be a non-empty list",
            )
        )
        return findings

    seen: set[str] = set()
    for index, case in enumerate(cases):
        case_path = Path(f"{path.as_posix()}#cases[{index}]")
        if not isinstance(case, dict):
            findings.append(
                _finding(
                    "skill.eval.case",
                    case_path,
                    "case must be a mapping",
                )
            )
            continue

        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            findings.append(
                _finding(
                    "skill.eval.case-id",
                    case_path,
                    "case id must be a non-empty string",
                )
            )
        elif case_id in seen:
            findings.append(
                _finding(
                    "skill.eval.case-id-duplicate",
                    case_path,
                    f"duplicate case id: {case_id}",
                )
            )
        else:
            seen.add(case_id)

        prompt = case.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            findings.append(
                _finding(
                    "skill.eval.prompt",
                    case_path,
                    "prompt must be non-empty",
                )
            )

        kind = case.get("kind")
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

            selected = case.get("selected_skills")
            rejected = case.get("rejected_skills")
            if not isinstance(selected, list) or not isinstance(rejected, list):
                findings.append(
                    _finding(
                        "skill.eval.routing-result",
                        case_path,
                        "routing case needs selected_skills and rejected_skills lists",
                    )
                )
                continue

            if kind == "positive" and skill not in selected:
                findings.append(
                    _finding(
                        "skill.eval.positive",
                        case_path,
                        "positive case must select the suite skill",
                    )
                )
            if kind == "negative" and skill not in rejected:
                findings.append(
                    _finding(
                        "skill.eval.negative",
                        case_path,
                        "negative case must reject the suite skill",
                    )
                )
            if kind == "collision" and (skill not in selected or not rejected):
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

            assertions = case.get("assertions")
            if (
                not isinstance(assertions, list)
                or not assertions
                or not all(isinstance(item, str) and item.strip() for item in assertions)
            ):
                findings.append(
                    _finding(
                        "skill.eval.assertions",
                        case_path,
                        "behavior case needs non-empty semantic assertions",
                    )
                )

            if case.get("baseline") not in BASELINE_MODES:
                findings.append(
                    _finding(
                        "skill.eval.baseline",
                        case_path,
                        f"baseline must be one of {sorted(BASELINE_MODES)}",
                    )
                )

    return findings


def validate_path(path: Path) -> list[Finding]:
    if path.is_file():
        return validate_suite(path)

    findings: list[Finding] = []
    if not path.is_dir():
        return [_finding("skill.eval.path", path, "eval path does not exist")]

    expected_skill = path.name if path.parent.name == "skills" else None
    sources = sorted(path.glob("*.yaml"))
    for source in sources:
        findings.extend(validate_suite(source, expected_skill))

    if not sources:
        findings.append(
            _finding(
                "skill.eval.empty",
                path,
                "eval directory contains no YAML suites",
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
