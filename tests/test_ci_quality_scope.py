"""Local and hosted quality gates share one canonical Python target inventory."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGETS_PATH = ROOT / "scripts/quality_targets.py"


def load_targets() -> Any:
    spec = importlib.util.spec_from_file_location("quality_targets", TARGETS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_agents_tools_are_in_every_policy_critical_target_set() -> None:
    targets = load_targets()
    tools = "skills/agents-md-architect/tools"
    assert tools in targets.QUALITY_PATHS
    assert tools in targets.BANDIT_PATHS
    assert f"{tools}/*.py" in targets.POLICY_COVERAGE_PATHS

    entrypoints = {
        f"{tools}/audit_agents_md.py",
        f"{tools}/discover_repository.py",
        f"{tools}/validate_agents_md.py",
    }
    assert entrypoints <= set(targets.TYPE_PATHS)
    assert tools not in targets.TYPE_PATHS

    for name in (
        "agents_md_parse.py",
        "agents_md_types.py",
        "audit_agents_md.py",
        "discover_repository.py",
        "validate_agents_md.py",
    ):
        assert (ROOT / tools / name).is_file()
    assert not (ROOT / tools / "__init__.py").exists()

    mypy = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'mypy_path = "skills/agents-md-architect/tools"' in mypy


def test_hosted_workflow_consumes_canonical_target_inventory() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "$(python scripts/quality_targets.py quality)" in workflow
    assert "$(python scripts/quality_targets.py typing)" in workflow
    assert "$(python scripts/quality_targets.py bandit)" in workflow
    assert "$(python scripts/quality_targets.py policy-coverage)" in workflow


def test_local_gate_imports_canonical_target_inventory() -> None:
    source = (ROOT / "scripts/ci.py").read_text(encoding="utf-8")
    assert "from quality_targets import" in source
    for token in ("QUALITY_PATHS", "TYPE_PATHS", "BANDIT_PATHS", "POLICY_COVERAGE_PATHS"):
        assert token in source


def test_target_cli_is_deterministic(capsys) -> None:
    targets = load_targets()
    assert targets.main(["quality"]) == 0
    assert capsys.readouterr().out.strip() == " ".join(targets.QUALITY_PATHS)
