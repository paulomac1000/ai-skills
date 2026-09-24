from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts/rule-catalog.yaml").write_text(
        "schema_version: 1\ncatalog_version: 3.0.0\nskills: {}\n",
        encoding="utf-8",
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
    assert "version: 3.0.0" in manifest
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
    (target / "reports").mkdir()

    findings = module.audit_skill(target, tmp_path)
    pollution = {
        finding.path
        for finding in findings
        if finding.code == "skill.package.pollution"
    }
    assert (target / "VERSION").resolve().as_posix() in pollution
    assert (target / "reports").resolve().as_posix() in pollution


def test_skill_architect_eval_corpus_is_well_formed() -> None:
    module = load_module(
        "skill_architect_evals",
        SKILL / "tools/validate_skill_evals.py",
    )
    findings = module.validate_path(
        ROOT / "evals/skills/skill-architect"
    )
    assert findings == []
    assert (ROOT / "contracts/skill-eval.schema.json").is_file()

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

