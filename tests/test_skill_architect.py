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
    (target / "manifest.yaml").write_text(_valid_manifest_text(), encoding="utf-8")
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
        _valid_manifest_text("[core, references]"),
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


def _valid_manifest_text(categories: str = "[core]") -> str:
    return (
        "schema_version: 1\n"
        "name: example-skill\n"
        "version: 1.0.0\n"
        "maturity: experimental\n"
        "skill_format: ai-skills/v1\n"
        "normative_entrypoint: STANDARD.md\n"
        "compatibility:\n"
        "  agent_contract: tool-capable-instruction-agent\n"
        "  operating_systems: [linux]\n"
        "  evidence_lanes: [test]\n"
        "  tested_combinations:\n"
        "  - operating_system: linux\n"
        "    architecture: x64\n"
        "    runtime: python\n"
        "    version: '3.12'\n"
        "    lane: test\n"
        "dependencies:\n"
        "  skills: []\n"
        "  tools: []\n"
        "deprecation:\n"
        "  policy: semantic-versioning\n"
        "  minimum_notice: one-minor-release\n"
        "required: [SKILL.md, STANDARD.md]\n"
        f"categories: {categories}\n"
        "adoption:\n"
        "  template: contracts/adoption-assessment.yaml.template\n"
        "  validator: contracts/validate_adoption.py\n"
        "  rule_catalog: contracts/rule-catalog.yaml\n"
        "  extension: generic\n"
        "  rule_map: contracts/standard-rule-map.yaml\n"
    )


def _write_minimal_skill(target: Path) -> None:
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
    (target / "manifest.yaml").write_text(_valid_manifest_text(), encoding="utf-8")


def _symlink_or_skip(source: Path, target: Path, *, directory: bool = False) -> None:
    try:
        target.symlink_to(source, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f"symlink fixture unavailable: {exc}")


def _write_eval_corpus(root: Path, routing_cases: str, behavior_suite: str | None = None) -> None:
    root.mkdir(parents=True)
    (root / "routing.yaml").write_text(
        (
            "schema_version: 1\n"
            "skill: example-skill\n"
            "suite: routing\n"
            "cases:\n"
            f"{routing_cases}"
        ),
        encoding="utf-8",
    )
    (root / "behavior.yaml").write_text(
        behavior_suite
        or (
            "schema_version: 1\n"
            "skill: example-skill\n"
            "suite: behavior\n"
            "cases:\n"
            "- id: representative\n"
            "  kind: representative\n"
            "  prompt: Produce the bounded result.\n"
            "  baseline: optional\n"
            "  assertions: [Preserves the requested scope.]\n"
        ),
        encoding="utf-8",
    )


def test_audit_rejects_symlinked_core_file(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_core_symlink",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    _write_minimal_skill(target)
    external = tmp_path / "external-manifest.yaml"
    external.write_text((target / "manifest.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (target / "manifest.yaml").unlink()
    _symlink_or_skip(external, target / "manifest.yaml")

    findings = module.audit_skill(target, tmp_path, strict=True)
    assert "skill.core.unconfined" in {finding.code for finding in findings}


def test_audit_rejects_symlinked_resource_directory(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_directory_symlink",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    _write_minimal_skill(target)
    outside = tmp_path / "outside"
    outside.mkdir()
    _symlink_or_skip(outside, target / "templates", directory=True)
    (target / "manifest.yaml").write_text(
        (
            "name: example-skill\n"
            "normative_entrypoint: STANDARD.md\n"
            "required: [SKILL.md, STANDARD.md]\n"
            "categories: [core, templates]\n"
            "dependencies:\n"
            "  skills: []\n"
            "  tools: []\n"
        ),
        encoding="utf-8",
    )

    findings = module.audit_skill(target, tmp_path, strict=True)
    assert "skill.package.symlink" in {finding.code for finding in findings}


def test_strict_audit_rejects_unexpected_top_level_file(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_unexpected_file",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    _write_minimal_skill(target)
    (target / "notes.txt").write_text("development note\n", encoding="utf-8")

    findings = module.audit_skill(target, tmp_path, strict=True)
    assert "skill.package.unexpected-file" in {finding.code for finding in findings}


def test_audit_rejects_nested_development_artifact(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_nested_pollution",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    _write_minimal_skill(target)
    templates = target / "templates"
    templates.mkdir()
    (templates / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (target / "manifest.yaml").write_text(
        (
            "name: example-skill\n"
            "normative_entrypoint: STANDARD.md\n"
            "required: [SKILL.md, STANDARD.md]\n"
            "categories: [core, templates]\n"
            "dependencies:\n"
            "  skills: []\n"
            "  tools: []\n"
        ),
        encoding="utf-8",
    )

    findings = module.audit_skill(target, tmp_path)
    assert "skill.package.pollution" in {finding.code for finding in findings}


def test_route_parser_ignores_fenced_markdown_examples(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_fenced_route",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    _write_minimal_skill(target)
    (target / "STANDARD.md").write_text(
        (
            "# Example standard\n\n"
            "Illustration only:\n\n"
            "```text\n"
            "Read references/example.md.\n"
            "```\n"
        ),
        encoding="utf-8",
    )

    findings = module.audit_skill(target, tmp_path, strict=True)
    assert findings == []


def test_scaffold_rejects_symlinked_skills_root(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_scaffold_symlink",
        SKILL / "tools/scaffold_skill.py",
    )
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _symlink_or_skip(outside, repository / "skills", directory=True)

    with pytest.raises(ValueError, match="must not be a symlink"):
        module.scaffold(repository, "example-skill", "Use for one bounded workflow.")
    assert not (outside / "example-skill").exists()


def test_failed_scaffold_cleans_destination_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module(
        "skill_architect_scaffold_cleanup",
        SKILL / "tools/scaffold_skill.py",
    )
    (tmp_path / "skills").mkdir()
    original = Path.write_text

    def fail_standard(path: Path, data: str, *args: object, **kwargs: object) -> int:
        if path.name == "STANDARD.md":
            raise OSError("injected write failure")
        return original(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_standard)
    with pytest.raises(OSError, match="injected write failure"):
        module.scaffold(tmp_path, "example-skill", "Use for one bounded workflow.")
    assert not (tmp_path / "skills/example-skill").exists()


def test_eval_validator_returns_schema_findings_for_malformed_collections(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_evals_invalid_collection",
        SKILL / "tools/validate_skill_evals.py",
    )
    source = tmp_path / "routing.yaml"
    source.write_text(
        (
            "schema_version: 1\n"
            "skill: example-skill\n"
            "suite: routing\n"
            "cases:\n"
            "- id: malformed\n"
            "  kind: positive\n"
            "  prompt: Use the skill.\n"
            "  selected_skills: [{name: example-skill}]\n"
            "  rejected_skills: []\n"
        ),
        encoding="utf-8",
    )

    findings = module.validate_suite(source)
    assert "skill.eval.schema" in {finding.code for finding in findings}


def test_eval_corpus_requires_canonical_routing_and_behavior_suites(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_evals_required_suites",
        SKILL / "tools/validate_skill_evals.py",
    )
    corpus = tmp_path / "skills/example-skill"
    corpus.mkdir(parents=True)
    (corpus / "routing.yaml").write_text(
        (
            "schema_version: 1\n"
            "skill: example-skill\n"
            "suite: routing\n"
            "cases:\n"
            "- id: positive\n"
            "  kind: positive\n"
            "  prompt: Use the skill.\n"
            "  selected_skills: [example-skill]\n"
            "  rejected_skills: []\n"
            "- id: negative\n"
            "  kind: negative\n"
            "  prompt: Do something outside the skill.\n"
            "  selected_skills: []\n"
            "  rejected_skills: [example-skill]\n"
        ),
        encoding="utf-8",
    )

    findings = module.validate_path(corpus)
    assert "skill.eval.suite-missing" in {finding.code for finding in findings}


def test_eval_corpus_rejects_suite_filename_mismatch(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_evals_filename",
        SKILL / "tools/validate_skill_evals.py",
    )
    corpus = tmp_path / "skills/example-skill"
    _write_eval_corpus(
        corpus,
        (
            "- id: positive\n"
            "  kind: positive\n"
            "  prompt: Use the skill.\n"
            "  selected_skills: [example-skill]\n"
            "  rejected_skills: []\n"
            "- id: negative\n"
            "  kind: negative\n"
            "  prompt: Do something else.\n"
            "  selected_skills: []\n"
            "  rejected_skills: [example-skill]\n"
        ),
        behavior_suite=(
            "schema_version: 1\n"
            "skill: example-skill\n"
            "suite: routing\n"
            "cases:\n"
            "- id: second-routing\n"
            "  kind: negative\n"
            "  prompt: Use something else.\n"
            "  selected_skills: []\n"
            "  rejected_skills: [example-skill]\n"
        ),
    )

    findings = module.validate_path(corpus)
    assert "skill.eval.suite-filename" in {finding.code for finding in findings}


def test_eval_corpus_requires_positive_and_boundary_routing_cases(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_evals_routing_coverage",
        SKILL / "tools/validate_skill_evals.py",
    )
    corpus = tmp_path / "skills/example-skill"
    _write_eval_corpus(
        corpus,
        (
            "- id: positive\n"
            "  kind: positive\n"
            "  prompt: Use the skill.\n"
            "  selected_skills: [example-skill]\n"
            "  rejected_skills: []\n"
        ),
    )

    findings = module.validate_path(corpus)
    assert "skill.eval.routing-boundary-missing" in {finding.code for finding in findings}


def test_skill_admission_contract_is_present() -> None:
    standard = (SKILL / "STANDARD.md").read_text(encoding="utf-8")
    assert "not already owned more clearly by an existing skill" in standard
    assert "Start from" in standard and "representative real tasks" in standard


def test_skill_ownership_contract_is_present() -> None:
    standard = (SKILL / "STANDARD.md").read_text(encoding="utf-8")
    assert "Every durable rule has one canonical owner." in standard
    assert "authority-restatement test" in standard


def test_skill_routing_contract_has_positive_and_boundary_corpus() -> None:
    module = load_module(
        "skill_architect_evals_routing_contract",
        SKILL / "tools/validate_skill_evals.py",
    )
    assert module.validate_path(ROOT / "evals/skills/skill-architect") == []


def test_skill_progressive_context_contract_routes_references() -> None:
    module = load_module(
        "skill_architect_context_contract",
        SKILL / "tools/audit_skill.py",
    )
    findings = module.audit_skill(SKILL, ROOT, strict=True)
    assert "skill.routing.orphan-reference" not in {finding.code for finding in findings}


def test_skill_representation_contract_keeps_scaffold_minimal(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_representation_contract",
        SKILL / "tools/scaffold_skill.py",
    )
    (tmp_path / "skills").mkdir()
    target = module.scaffold(tmp_path, "example-skill", "Use for one bounded workflow.")
    assert {path.name for path in target.iterdir()} == {"SKILL.md", "STANDARD.md", "manifest.yaml"}


def test_skill_package_contract_rejects_pollution(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_package_contract",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    _write_minimal_skill(target)
    (target / "README.md").write_text("# Not runtime knowledge\n", encoding="utf-8")
    findings = module.audit_skill(target, tmp_path, strict=True)
    assert "skill.package.pollution" in {finding.code for finding in findings}


def test_skill_tools_contract_is_quality_gated() -> None:
    quality = (ROOT / "scripts/quality_targets.py").read_text(encoding="utf-8")
    assert '"skills/skill-architect/tools"' in quality
    assert '"skills/skill-architect/tools/*.py"' in quality


def test_skill_trust_contract_rejects_unconfined_resources(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_trust_contract",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    _write_minimal_skill(target)
    external = tmp_path / "external"
    external.mkdir()
    _symlink_or_skip(external, target / "references", directory=True)
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
    assert "skill.package.symlink" in {finding.code for finding in findings}


def test_skill_evaluation_contract_separates_model_evidence() -> None:
    reference = (SKILL / "references/behavioral-evaluation.md").read_text(encoding="utf-8")
    normalized = " ".join(reference.split())
    assert "does not ship a provider-specific model runner" in normalized
    assert "never report the local corpus validator" in normalized


def test_skill_lifecycle_contract_requires_representative_reruns() -> None:
    standard = (SKILL / "STANDARD.md").read_text(encoding="utf-8")
    assert "Re-run representative routing and behavior suites after material skill changes" in standard


def test_skill_migration_contract_preserves_compliant_behavior() -> None:
    standard = (SKILL / "STANDARD.md").read_text(encoding="utf-8")
    assert "Preserve compliant consumer-specific behavior" in standard


def test_skill_completion_contract_self_audits() -> None:
    module = load_module(
        "skill_architect_completion_contract",
        SKILL / "tools/audit_skill.py",
    )
    assert module.audit_skill(SKILL, ROOT, strict=True) == []

def test_audit_returns_finding_for_unreadable_skill_text(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_unreadable_skill",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    _write_minimal_skill(target)
    (target / "SKILL.md").write_bytes(b"\xff\xfe\x00")

    findings = module.audit_skill(target, tmp_path, strict=True)
    assert "skill.file.unreadable" in {finding.code for finding in findings}


def test_route_parser_ignores_external_urls(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_external_url",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    _write_minimal_skill(target)
    (target / "STANDARD.md").write_text(
        "External evidence: https://example.invalid/repo/tools/setup.py\n",
        encoding="utf-8",
    )

    findings = module.audit_skill(target, tmp_path, strict=True)
    assert "skill.routing.missing" not in {finding.code for finding in findings}
    assert "skill.routing.not-file" not in {finding.code for finding in findings}


def test_strict_audit_rejects_missing_and_empty_declared_categories(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_declared_categories",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    _write_minimal_skill(target)
    manifest = (
        "name: example-skill\n"
        "normative_entrypoint: STANDARD.md\n"
        "required: [SKILL.md, STANDARD.md]\n"
        "categories: [core, references]\n"
        "dependencies:\n"
        "  skills: []\n"
        "  tools: []\n"
    )
    (target / "manifest.yaml").write_text(manifest, encoding="utf-8")

    missing = module.audit_skill(target, tmp_path, strict=True)
    assert "skill.categories.missing" in {finding.code for finding in missing}

    (target / "references").mkdir()
    empty = module.audit_skill(target, tmp_path, strict=True)
    assert "skill.categories.empty" in {finding.code for finding in empty}


def test_audit_rejects_routed_directory_as_resource(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_routed_directory",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    _write_minimal_skill(target)
    references = target / "references"
    references.mkdir()
    (references / "guide.md").mkdir()
    (target / "STANDARD.md").write_text(
        "Read references/guide.md for conditional policy.\n",
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
    assert "skill.routing.not-file" in {finding.code for finding in findings}

def test_scaffold_cli_returns_stable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_module(
        "skill_architect_scaffold_cli_error",
        SKILL / "tools/scaffold_skill.py",
    )

    class Args:
        repository_root = tmp_path
        name = "Bad Name"
        description = "Use for one bounded workflow."

    monkeypatch.setattr(module, "_parse_args", lambda: Args())
    assert module.main() == 2
    assert capsys.readouterr().err.startswith("ERROR skill.scaffold.failed:")


def test_eval_validator_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_evals_duplicate_keys",
        SKILL / "tools/validate_skill_evals.py",
    )
    source = tmp_path / "routing.yaml"
    source.write_text(
        (
            "schema_version: 1\n"
            "skill: example-skill\n"
            "suite: routing\n"
            "cases:\n"
            "- id: first\n"
            "  kind: positive\n"
            "  prompt: Use the skill.\n"
            "  selected_skills: [example-skill]\n"
            "  rejected_skills: []\n"
            "cases:\n"
            "- id: second\n"
            "  kind: positive\n"
            "  prompt: Use the skill again.\n"
            "  selected_skills: [example-skill]\n"
            "  rejected_skills: []\n"
        ),
        encoding="utf-8",
    )

    findings = module.validate_suite(source)
    assert [finding.code for finding in findings] == ["skill.eval.invalid"]


def test_eval_schema_rejects_whitespace_only_prompt(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_evals_whitespace_prompt",
        SKILL / "tools/validate_skill_evals.py",
    )
    source = tmp_path / "routing.yaml"
    source.write_text(
        (
            "schema_version: 1\n"
            "skill: example-skill\n"
            "suite: routing\n"
            "cases:\n"
            "- id: empty-task\n"
            "  kind: positive\n"
            "  prompt: '   '\n"
            "  selected_skills: [example-skill]\n"
            "  rejected_skills: []\n"
        ),
        encoding="utf-8",
    )

    findings = module.validate_suite(source)
    assert "skill.eval.schema" in {finding.code for finding in findings}


def test_strict_audit_rejects_parent_relative_route(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_parent_route",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    _write_minimal_skill(target)
    (target / "STANDARD.md").write_text(
        "Read ../references/shared.md for policy.\n",
        encoding="utf-8",
    )

    findings = module.audit_skill(target, tmp_path, strict=True)
    assert "skill.routing.unconfined" in {finding.code for finding in findings}


def test_strict_audit_recognizes_arbitrary_resource_extensions(tmp_path: Path) -> None:
    module = load_module(
        "skill_architect_audit_generic_extension",
        SKILL / "tools/audit_skill.py",
    )
    target = tmp_path / "skills/example-skill"
    _write_minimal_skill(target)
    tools_dir = target / "tools"
    tools_dir.mkdir()
    (tools_dir / "keep.py").write_text("pass\n", encoding="utf-8")
    (target / "manifest.yaml").write_text(
        _valid_manifest_text("[core, tools]"),
        encoding="utf-8",
    )
    (target / "STANDARD.md").write_text(
        "Run tools/check.ts before publishing.\n",
        encoding="utf-8",
    )

    findings = module.audit_skill(target, tmp_path, strict=True)
    assert "skill.routing.missing" in {finding.code for finding in findings}


def test_strict_audit_rejects_scaffold_placeholder_manifest(tmp_path: Path) -> None:
    scaffold_module = load_module(
        "skill_architect_scaffold_manifest",
        SKILL / "tools/scaffold_skill.py",
    )
    audit_module = load_module(
        "skill_architect_audit_scaffold_manifest",
        SKILL / "tools/audit_skill.py",
    )
    (tmp_path / "skills").mkdir()
    target = scaffold_module.scaffold(
        tmp_path,
        "example-skill",
        "Use for one bounded workflow.",
    )

    findings = audit_module.audit_skill(target, tmp_path, strict=True)
    assert "skill.manifest.contract" in {finding.code for finding in findings}

