#!/usr/bin/env python3
"""Close the shared-applicability and exact-test-identity review gap; deleted before commit."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Shared parent/child projection and exact test-case identity helper.
path = ROOT / "contracts/rule_applicability.py"
text = path.read_text(encoding="utf-8")
text = text.replace("from __future__ import annotations\n\n", "from __future__ import annotations\n\nimport ast\nimport re\n")
text = text.replace("from typing import Any\n", "from pathlib import Path, PurePosixPath\nfrom typing import Any\n")
text += r'''


TEST_CASE_IDENTITY = re.compile(
    r"^(tests/[A-Za-z0-9_./-]+[.]py)::(test_[A-Za-z0-9_]+)$"
)


@dataclass(frozen=True, slots=True)
class ApplicabilityProjection:
    """One context projection shared by parent rules and atomic child controls."""

    parent_rules: tuple[Mapping[str, Any], ...]
    child_controls: tuple[Mapping[str, Any], ...]


def project_applicability(
    parent_catalog: Mapping[str, Any],
    child_catalog: Mapping[str, Any],
    skill_name: str,
    context: RuleContext,
) -> ApplicabilityProjection:
    """Project parent and child applicability and reject child-without-parent states."""
    parents = tuple(expected_rules(parent_catalog, skill_name, context))
    parent_ids = {str(rule["id"]) for rule in parents}
    raw_controls = child_catalog.get("controls", [])
    if not isinstance(raw_controls, Sequence):
        raise ValueError("atomic child-control catalog has no controls")
    children: list[Mapping[str, Any]] = []
    for raw in raw_controls:
        if not isinstance(raw, Mapping) or raw.get("skill") != skill_name:
            continue
        parent_id = raw.get("parent_rule_id")
        control_id = raw.get("id")
        if not isinstance(parent_id, str) or not isinstance(control_id, str):
            raise ValueError("atomic child control has invalid parent or control identity")
        if not rule_applies(raw, context):
            continue
        if parent_id not in parent_ids:
            raise ValueError(
                f"child control {control_id} applies while parent rule {parent_id} does not"
            )
        children.append(raw)
    return ApplicabilityProjection(parents, tuple(children))


def test_case_identity_finding(value: object, repository_root: Path) -> str | None:
    """Validate one exact repository test identity without executing candidate code."""
    if not isinstance(value, str):
        return "must be an exact tests/file.py::test_name identity"
    match = TEST_CASE_IDENTITY.fullmatch(value)
    if match is None:
        return "must be an exact tests/file.py::test_name identity"
    raw_path, function_name = match.groups()
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return "test path must remain inside the repository"
    root = repository_root.resolve(strict=True)
    current = root
    for part in pure.parts:
        current /= part
        if current.is_symlink():
            return "test path must not contain symlinks"
    if not current.is_file():
        return "test file does not exist"
    try:
        tree = ast.parse(current.read_text(encoding="utf-8"), filename=raw_path)
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        return f"cannot inspect test file: {exc}"
    functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if function_name not in functions:
        return f"test function {function_name!r} does not exist"
    return None
'''
path.write_text(text, encoding="utf-8")

# Atomic controls consume the same projection as parent rules and bind each result to a catalog selector.
replace_once(
    "contracts/validate_atomic_claims.py",
    '''from contracts.rule_applicability import (  # noqa: E402
    RuleContext,
    rule_applies,
    validate_rule_metadata,
)
''',
    '''from contracts.rule_applicability import (  # noqa: E402
    RuleContext,
    project_applicability,
    test_case_identity_finding,
    validate_rule_metadata,
)
''',
)
replace_once(
    "contracts/validate_atomic_claims.py",
    '''def _controls(catalog: Mapping[str, Any], skill: str, context: RuleContext) -> dict[str, Mapping[str, Any]]:
    raw_controls = catalog.get("controls")
    if not isinstance(raw_controls, list):
        return {}
    return {
        str(control["id"]): control
        for control in raw_controls
        if isinstance(control, Mapping)
        and control.get("skill") == skill
        and rule_applies(control, context)
    }
''',
    '''def _controls(
    catalog: Mapping[str, Any],
    parent_catalog: Mapping[str, Any],
    skill: str,
    context: RuleContext,
) -> dict[str, Mapping[str, Any]]:
    projection = project_applicability(parent_catalog, catalog, skill, context)
    return {str(control["id"]): control for control in projection.child_controls}
''',
)
replace_once(
    "contracts/validate_atomic_claims.py",
    '''        report = _load_mapping(report_path)
        catalog = _load_mapping(catalog_path)
        schema = _load_mapping(schema_path)
        root = repository_root.resolve(strict=True)
''',
    '''        report = _load_mapping(report_path)
        catalog = _load_mapping(catalog_path)
        parent_catalog = _load_mapping(parent_catalog_path)
        schema = _load_mapping(schema_path)
        root = repository_root.resolve(strict=True)
''',
)
replace_once(
    "contracts/validate_atomic_claims.py",
    "    expected = _controls(catalog, skill, context)\n",
    '''    try:
        expected = _controls(catalog, parent_catalog, skill, context)
    except ValueError as exc:
        return [*findings, f"applicability: {exc}"]
''',
)
replace_once(
    "contracts/validate_atomic_claims.py",
    '''        control = expected.get(control_id)
        if control is None:
            findings.append(f"{location}.control_id: not applicable for the selected context")
            continue
        evidence_types = raw.get("evidence_types")
''',
    '''        control = expected.get(control_id)
        if control is None:
            findings.append(f"{location}.control_id: not applicable for the selected context")
            continue
        test_case = raw.get("test_case")
        test_case_finding = test_case_identity_finding(test_case, root)
        if test_case_finding:
            findings.append(f"{location}.test_case: {test_case_finding}")
        elif test_case not in control.get("test_selectors", []):
            findings.append(
                f"{location}.test_case: is not an approved selector for {control_id}"
            )
        evidence_types = raw.get("evidence_types")
''',
)

schema_path = ROOT / "contracts/atomic-claim-report.schema.json"
schema = json.loads(schema_path.read_text(encoding="utf-8"))
item = schema["properties"]["checks"]["items"]
if "test_case" not in item["required"]:
    item["required"].insert(item["required"].index("result"), "test_case")
item["properties"]["test_case"] = {
    "type": "string",
    "pattern": r"^tests/[A-Za-z0-9_./-]+[.]py::test_[A-Za-z0-9_]+$",
}
schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

# Parent conformance uses the same projection and exact test identity helper.
replace_once(
    "contracts/validate_conformance.py",
    "from contracts.rule_applicability import RuleContext, expected_rules  # noqa: E402\n",
    '''from contracts.rule_applicability import (  # noqa: E402
    RuleContext,
    project_applicability,
    test_case_identity_finding,
)
''',
)
replace_once(
    "contracts/validate_conformance.py",
    "MAX_IMPLEMENTATION_BYTES = 2 * 1024 * 1024\n",
    '''MAX_IMPLEMENTATION_BYTES = 2 * 1024 * 1024
DEFAULT_ATOMIC_CATALOG = Path(__file__).with_name("atomic-claim-catalog.yaml")
''',
)
replace_once(
    "contracts/validate_conformance.py",
    '''            "command",
            "result",
''',
    '''            "command",
            "test_case",
            "result",
''',
)
replace_once(
    "contracts/validate_conformance.py",
    '''    command = check.get("command")
    if not isinstance(command, str) or not command.strip():
        errors.append(f"{location}.command: must be executable text")

    evidence_types = set(_strings(check.get("evidence_types"), f"{location}.evidence_types", errors))
''',
    '''    command = check.get("command")
    if not isinstance(command, str) or not command.strip():
        errors.append(f"{location}.command: must be executable text")
    test_case_finding = test_case_identity_finding(
        check.get("test_case"), repository_root
    )
    if test_case_finding:
        errors.append(f"{location}.test_case: {test_case_finding}")

    evidence_types = set(_strings(check.get("evidence_types"), f"{location}.evidence_types", errors))
''',
)
replace_once(
    "contracts/validate_conformance.py",
    '''def validate(
    report_path: Path,
    repository_root: Path,
    catalog_path: Path,
) -> list[str]:
''',
    '''def validate(
    report_path: Path,
    repository_root: Path,
    catalog_path: Path,
    atomic_catalog_path: Path = DEFAULT_ATOMIC_CATALOG,
) -> list[str]:
''',
)
replace_once(
    "contracts/validate_conformance.py",
    '''    report = _load_yaml(report_path, "$", errors)
    catalog = _load_yaml(catalog_path, "catalog", errors)
''',
    '''    report = _load_yaml(report_path, "$", errors)
    catalog = _load_yaml(catalog_path, "catalog", errors)
    atomic_catalog = _load_yaml(atomic_catalog_path, "atomic catalog", errors)
''',
)
replace_once(
    "contracts/validate_conformance.py",
    '''        context = RuleContext(
            str(context_raw.get("target_level")),
            frozenset(profiles),
            frozenset(capabilities),
        )
        rules = expected_rules(catalog, skill_name, context)
''',
    '''        context = RuleContext(
            str(context_raw.get("target_level")),
            frozenset(profiles),
            frozenset(capabilities),
        )
        projection = project_applicability(
            catalog, atomic_catalog, skill_name, context
        )
        rules = projection.parent_rules
''',
)
replace_once(
    "contracts/conformance-report.yaml.template",
    "    command: REPLACE_WITH_EXACT_COMMAND\n    result: passed\n",
    "    command: REPLACE_WITH_EXACT_COMMAND\n    test_case: tests/REPLACE_WITH_TEST_FILE.py::test_REPLACE_WITH_EXACT_CASE\n    result: passed\n",
)

# Adoption: exact test-case identity is schema-required, validated, and included in provider claims.
schema_path = ROOT / "contracts/adoption-assessment.schema.json"
schema = json.loads(schema_path.read_text(encoding="utf-8"))
verification = schema["$defs"]["verification"]
verification["properties"]["test_case"] = {
    "type": "string",
    "pattern": r"^tests/[A-Za-z0-9_./-]+[.]py::test_[A-Za-z0-9_]+$",
}
if "test_case" not in verification["required"]:
    verification["required"].insert(verification["required"].index("result"), "test_case")
schema_path.write_text(json.dumps(schema, separators=(",", ":")) + "\n", encoding="utf-8")

replace_once(
    "contracts/validate_adoption.py",
    '''from contracts.rule_applicability import RuleContext, expected_rules  # noqa: E402
''',
    '''from contracts.rule_applicability import (  # noqa: E402
    RuleContext,
    expected_rules,
    project_applicability,
    test_case_identity_finding,
)
''',
)
replace_once(
    "contracts/validate_adoption.py",
    "DEFAULT_CATALOG = Path(__file__).with_name(\"rule-catalog.yaml\")\n",
    '''DEFAULT_CATALOG = Path(__file__).with_name("rule-catalog.yaml")
DEFAULT_ATOMIC_CATALOG = Path(__file__).with_name("atomic-claim-catalog.yaml")
''',
)
replace_once(
    "contracts/validate_adoption.py",
    '''def validate_document(
    assessment: Mapping[str, Any],
    catalog: Mapping[str, Any],
    skills_root: Path,
    *,
''',
    '''def validate_document(
    assessment: Mapping[str, Any],
    catalog: Mapping[str, Any],
    skills_root: Path,
    *,
    atomic_catalog: Mapping[str, Any] | None = None,
''',
)
replace_once(
    "contracts/validate_adoption.py",
    '''                    machine_applicable_rules = {
                        str(rule["id"])
                        for rule in expected_rules(catalog, skill_name, context)
                    }
''',
    '''                    if atomic_catalog is None:
                        parent_rules = expected_rules(catalog, skill_name, context)
                    else:
                        parent_rules = list(
                            project_applicability(
                                catalog, atomic_catalog, skill_name, context
                            ).parent_rules
                        )
                    machine_applicable_rules = {
                        str(rule["id"]) for rule in parent_rules
                    }
''',
)
replace_once(
    "contracts/validate_adoption.py",
    '''                command = _text(verification.get("command"), f"{verification_location}.command", findings)
                evidence = _evidence_reference(
''',
    '''                command = _text(verification.get("command"), f"{verification_location}.command", findings)
                test_case = _text(
                    verification.get("test_case"),
                    f"{verification_location}.test_case",
                    findings,
                )
                if test_case:
                    test_case_finding = test_case_identity_finding(
                        test_case, repository_root
                    )
                    if test_case_finding:
                        findings.append(
                            Finding(
                                f"{verification_location}.test_case",
                                test_case_finding,
                            )
                        )
                evidence = _evidence_reference(
''',
)
replace_once(
    "contracts/validate_adoption.py",
    '''                        "result": "passed",
                        "command_digest": _command_digest(command),
                    }
''',
    '''                        "result": "passed",
                        "command_digest": _command_digest(command),
                        "test_case": test_case,
                    }
''',
)
replace_once(
    "contracts/validate_adoption.py",
    '''        catalog = _load_yaml(args.catalog)
        schema = _load_json(args.schema)
''',
    '''        catalog = _load_yaml(args.catalog)
        atomic_catalog = _load_yaml(DEFAULT_ATOMIC_CATALOG)
        schema = _load_json(args.schema)
''',
)
replace_once(
    "contracts/validate_adoption.py",
    '''        args.skills_root,
        require_approval=args.require_approval,
''',
    '''        args.skills_root,
        atomic_catalog=atomic_catalog,
        require_approval=args.require_approval,
''',
)

# Test fixtures contain real exact test-case identities.
replace_once(
    "tests/test_adoption_contract.py",
    '''    artifact = tmp_path / "artifact.txt"
    artifact.write_text("immutable artifact\\n", encoding="utf-8")
''',
    '''    artifact = tmp_path / "artifact.txt"
    artifact.write_text("immutable artifact\\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_rule.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_rule():\\n    pass\\n", encoding="utf-8")
''',
)
replace_once(
    "tests/test_adoption_contract.py",
    '''                        "command": "python -m pytest tests/test_rule.py",
                        "evidence": evidence(1),
''',
    '''                        "command": "python -m pytest tests/test_rule.py",
                        "test_case": "tests/test_rule.py::test_rule",
                        "evidence": evidence(1),
''',
)
replace_once(
    "tests/test_conformance_report.py",
    '''    (root / "evidence.xml").write_text("<testsuite/>\\n", encoding="utf-8")
''',
    '''    (root / "evidence.xml").write_text("<testsuite/>\\n", encoding="utf-8")
    test_file = root / "tests" / "test_rule.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_rule():\\n    pass\\n", encoding="utf-8")
''',
)
replace_once(
    "tests/test_conformance_report.py",
    '''                "command": "python -m pytest",
                "result": "passed",
''',
    '''                "command": "python -m pytest",
                "test_case": "tests/test_rule.py::test_rule",
                "result": "passed",
''',
)

# Regression: a child may never apply when its parent is projected out.
path = ROOT / "tests/test_atomic_claim_contract.py"
text = path.read_text(encoding="utf-8")
text += r'''


def test_shared_projection_rejects_applicable_child_with_inapplicable_parent() -> None:
    from contracts.rule_applicability import RuleContext, project_applicability

    parents = {
        "skills": {
            "mcp-server-architect": {
                "rules": [
                    {
                        "id": "mcp.parent",
                        "applies_when": {"maturity_at_least": "L4"},
                        "severity": "blocking",
                        "waivable": False,
                        "required_evidence": ["unit"],
                    }
                ]
            }
        }
    }
    children = {
        "controls": [
            {
                "id": "mcp.child",
                "parent_rule_id": "mcp.parent",
                "skill": "mcp-server-architect",
                "applies_when": {"maturity_at_least": "L1"},
            }
        ]
    }
    try:
        project_applicability(
            parents,
            children,
            "mcp-server-architect",
            RuleContext("L1"),
        )
    except ValueError as exc:
        assert "applies while parent rule" in str(exc)
    else:
        raise AssertionError("child-without-parent applicability must fail closed")
'''
path.write_text(text, encoding="utf-8")

# Regression: exact selector is required and bound to the approved atomic selector.
path = ROOT / "tests/test_atomic_claim_contract.py"
text = path.read_text(encoding="utf-8")
text += r'''


def test_atomic_report_rejects_test_case_outside_control_selector(tmp_path: Path) -> None:
    controls = _controls()
    control = controls["mcp.runtime.isolation"]
    report = {
        "schema_version": 1,
        "report_id": "wrong-test-case",
        "repository": {"name": "example/server", "revision": "1" * 40},
        "skill": "mcp-server-architect",
        "context": {"target_level": "L1", "profiles": [], "capabilities": []},
        "checks": [
            {
                "control_id": control["id"],
                "status": "passed",
                "implementation": [
                    {"path": "contracts/rule_applicability.py", "symbol": "RuleContext"}
                ],
                "command": "python -m pytest tests/test_atomic_claim_contract.py",
                "test_case": "tests/test_atomic_claim_contract.py::test_atomic_claim_catalog_is_confined_and_executable",
                "result": "passed",
                "evidence_types": control["required_evidence"],
                "evidence_paths": ["tests/test_atomic_claim_contract.py"],
            }
        ],
        "residual_risks": [],
    }
    path = tmp_path / "atomic-report.yaml"
    path.write_text(yaml.safe_dump(report), encoding="utf-8")
    findings = validate_report(path, repository_root=ROOT)
    assert any("not an approved selector" in finding for finding in findings)
'''
path.write_text(text, encoding="utf-8")
