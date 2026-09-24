from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/skill-architect"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_skill_architect_audits_its_own_runtime_package() -> None:
    module = load_module(
        "skill_architect_audit",
        SKILL / "tools/audit_skill.py",
    )
    findings = module.audit_skill(SKILL, ROOT, strict=True)
    assert findings == []


def test_scaffold_creates_only_the_minimal_runtime_core(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_scaffold",
        SKILL / "tools/scaffold_skill.py",
    )
    (tmp_path / "skills").mkdir()

    target = module.scaffold(
        tmp_path,
        "example-skill",
        (
            "Create and review a reusable example workflow when the task "
            "matches its bounded scope."
        ),
    )

    assert {path.name for path in target.iterdir()} == {
        "SKILL.md",
        "STANDARD.md",
        "manifest.yaml",
    }
    manifest = (target / "manifest.yaml").read_text(encoding="utf-8")
    assert "name: example-skill" in manifest
    assert "version: REPLACE_WITH_RELEASE_VERSION" in manifest
    assert "maturity: experimental" in manifest
    assert "operating_systems: []" in manifest
    assert "evidence_lanes: []" in manifest
    assert "tested_combinations: []" in manifest
    assert "tools: []" in manifest


def test_audit_rejects_developer_artifacts_inside_runtime_package(
    tmp_path: Path,
) -> None:
    module = load_module(
        "skill_architect_audit_pollution",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(
        (
            "---\n"
            "name: example-skill\n"
            "description: Use for one bounded example workflow.\n"
            "---\n\n"
            "# Example\n\n"
            "Read STANDARD.md before normative decisions.\n"
        ),
        encoding="utf-8",
    )
    (target / "STANDARD.md").write_text(
        "# Example standard\n",
        encoding="utf-8",
    )
    (target / "manifest.yaml").write_text(
        (
            "name: example-skill\n"
            "normative_entrypoint: STANDARD.md\n"
            "required: [SKILL.md, STANDARD.md]\n"
            "categories: [core]\n"
            "dependencies:\n"
            "  skills: []\n"
            "  tools: []\n"
        ),
        encoding="utf-8",
    )
    (target / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (target / "README.md").write_text("# Auxiliary docs\n", encoding="utf-8")
    (target / "reports").mkdir()

    findings = module.audit_skill(target, tmp_path)
    pollution = {
        finding.path
        for finding in findings
        if finding.code == "skill.package.pollution"
    }
    assert (target / "VERSION").resolve().as_posix() in pollution
    assert (target / "README.md").resolve().as_posix() in pollution
    assert (target / "reports").resolve().as_posix() in pollution


def test_auditor_accepts_existing_skill_packages_without_errors() -> None:
    module = load_module(
        "skill_architect_audit_repository",
        SKILL / "tools/audit_skill.py",
    )
    errors: dict[str, list[str]] = {}
    for directory in sorted((ROOT / "skills").iterdir()):
        if not directory.is_dir():
            continue
        findings = module.audit_skill(directory, ROOT)
        current = [finding.code for finding in findings if finding.severity == "error"]
        if current:
            errors[directory.name] = current
    assert errors == {}



def test_route_parser_ignores_protocol_and_operation_names() -> None:
    module = load_module(
        "skill_architect_route_parser",
        SKILL / "tools/audit_skill.py",
    )
    routes = module._routed_paths(
        "Call tools/list and tools/listChanged while holding locks/transactions; "
        "then read references/routing.md and run tools/audit_skill.py."
    )
    assert routes == {"references/routing.md", "tools/audit_skill.py"}

def test_skill_architect_eval_corpus_is_well_formed() -> None:
    module = load_module(
        "skill_architect_evals",
        SKILL / "tools/validate_skill_evals.py",
    )
    findings = module.validate_path(ROOT / "evals/skills/skill-architect")
    assert findings == []
    assert (SKILL / "schemas/skill-eval.schema.json").is_file()


def test_audit_fails_closed_on_malformed_manifest(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_malformed",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(
        (
            "---\n"
            "name: example-skill\n"
            "description: Use for one bounded example workflow.\n"
            "---\n\n"
            "# Example\n\n"
            "Read STANDARD.md before normative decisions.\n"
        ),
        encoding="utf-8",
    )
    (target / "STANDARD.md").write_text("# Example standard\n", encoding="utf-8")
    (target / "manifest.yaml").write_text("required: [\n", encoding="utf-8")

    findings = module.audit_skill(target, tmp_path)
    assert "skill.manifest.invalid" in {finding.code for finding in findings}


def test_strict_audit_accepts_references_routed_from_standard(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_reference_graph",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    references = target / "references"
    references.mkdir(parents=True)
    (target / "SKILL.md").write_text(
        (
            "---\n"
            "name: example-skill\n"
            "description: Use for one bounded example workflow.\n"
            "---\n\n"
            "# Example\n\n"
            "Read STANDARD.md before normative decisions.\n"
        ),
        encoding="utf-8",
    )
    (target / "STANDARD.md").write_text(
        (
            "# Example standard\n\n"
            "For conditional detail read references/conditional.md.\n"
        ),
        encoding="utf-8",
    )
    (references / "conditional.md").write_text(
        "# Conditional detail\n",
        encoding="utf-8",
    )
    (target / "manifest.yaml").write_text(
        (
            "name: example-skill\n"
            "normative_entrypoint: STANDARD.md\n"
            "required: [SKILL.md, STANDARD.md]\n"
            "categories: [core, references]\n"
            "dependencies:\n"
            "  skills: []\n"
            "  tools: []\n"
        ),
        encoding="utf-8",
    )

    findings = module.audit_skill(target, tmp_path, strict=True)
    assert findings == []


def test_strict_audit_rejects_unreachable_reference(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_orphan_reference",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    references = target / "references"
    references.mkdir(parents=True)
    (target / "SKILL.md").write_text(
        (
            "---\n"
            "name: example-skill\n"
            "description: Use for one bounded example workflow.\n"
            "---\n\n"
            "# Example\n\n"
            "Read STANDARD.md before normative decisions.\n"
        ),
        encoding="utf-8",
    )
    (target / "STANDARD.md").write_text("# Example standard\n", encoding="utf-8")
    (references / "orphan.md").write_text("# Orphan\n", encoding="utf-8")
    (target / "manifest.yaml").write_text(
        (
            "name: example-skill\n"
            "normative_entrypoint: STANDARD.md\n"
            "required: [SKILL.md, STANDARD.md]\n"
            "categories: [core, references]\n"
            "dependencies:\n"
            "  skills: []\n"
            "  tools: []\n"
        ),
        encoding="utf-8",
    )

    findings = module.audit_skill(target, tmp_path, strict=True)
    assert "skill.routing.orphan-reference" in {finding.code for finding in findings}


def test_audit_rejects_missing_resource_routed_from_reference(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_nested_missing",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    references = target / "references"
    references.mkdir(parents=True)
    (target / "SKILL.md").write_text(
        (
            "---\n"
            "name: example-skill\n"
            "description: Use for one bounded example workflow.\n"
            "---\n\n"
            "# Example\n\n"
            "Read STANDARD.md before normative decisions.\n"
        ),
        encoding="utf-8",
    )
    (target / "STANDARD.md").write_text(
        "Read references/parent.md for conditional policy.\n",
        encoding="utf-8",
    )
    (references / "parent.md").write_text(
        "Then read references/missing.md.\n",
        encoding="utf-8",
    )
    (target / "manifest.yaml").write_text(
        (
            "name: example-skill\n"
            "normative_entrypoint: STANDARD.md\n"
            "required: [SKILL.md, STANDARD.md]\n"
            "categories: [core, references]\n"
            "dependencies:\n"
            "  skills: []\n"
            "  tools: []\n"
        ),
        encoding="utf-8",
    )

    findings = module.audit_skill(target, tmp_path, strict=True)
    assert "skill.routing.missing" in {finding.code for finding in findings}


def test_eval_validator_fails_closed_on_malformed_yaml(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_evals_malformed",
        SKILL / "tools/validate_skill_evals.py",
    )
    source = tmp_path / "routing.yaml"
    source.write_text("cases: [\n", encoding="utf-8")

    findings = module.validate_suite(source)
    assert [finding.code for finding in findings] == ["skill.eval.invalid"]


def test_eval_schema_rejects_unknown_case_fields(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_evals_schema",
        SKILL / "tools/validate_skill_evals.py",
    )
    source = tmp_path / "routing.yaml"
    source.write_text(
        (
            "schema_version: 1\n"
            "skill: example-skill\n"
            "suite: routing\n"
            "cases:\n"
            "- id: positive\n"
            "  kind: positive\n"
            "  prompt: Use the example skill.\n"
            "  selected_skills: [example-skill]\n"
            "  rejected_skills: []\n"
            "  unexpected: true\n"
        ),
        encoding="utf-8",
    )

    findings = module.validate_suite(source)
    assert "skill.eval.schema" in {finding.code for finding in findings}


def test_eval_validator_rejects_selected_rejected_overlap(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_evals_overlap",
        SKILL / "tools/validate_skill_evals.py",
    )
    source = tmp_path / "routing.yaml"
    source.write_text(
        (
            "schema_version: 1\n"
            "skill: example-skill\n"
            "suite: routing\n"
            "cases:\n"
            "- id: contradictory\n"
            "  kind: positive\n"
            "  prompt: Use the example skill.\n"
            "  selected_skills: [example-skill]\n"
            "  rejected_skills: [example-skill]\n"
        ),
        encoding="utf-8",
    )

    findings = module.validate_suite(source)
    assert "skill.eval.routing-overlap" in {finding.code for finding in findings}


def test_scaffold_normalizes_multiline_description(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_scaffold_description",
        SKILL / "tools/scaffold_skill.py",
    )
    (tmp_path / "skills").mkdir()
    target = module.scaffold(
        tmp_path,
        "example-skill",
        "Create reusable workflows.\nUse when a bounded task needs them.",
    )

    text = (target / "SKILL.md").read_text(encoding="utf-8")
    assert "Create reusable workflows. Use when a bounded task needs them." in text
