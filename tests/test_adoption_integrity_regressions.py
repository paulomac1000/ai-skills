"""Integrity regressions for adoption planning, canaries, and promoted field feedback."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from contracts.validate_consumer_feedback import validate_registry
from contracts.validate_operational_claims import _is_non_exact_version

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/mcp-server-architect/tools"


def _load(name: str, path: Path):
    tools = str(path.parent)
    inserted = tools not in sys.path
    if inserted:
        sys.path.insert(0, tools)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(tools)


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def _checkout(path: Path, repository: str = "owner/consumer") -> str:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, timeout=30)
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "remote", "add", "origin", f"https://github.com/{repository}.git")
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "fixture")
    return _git(path, "rev-parse", "HEAD")


def _canary_catalog(path: Path, *, revision: str, repository: str = "owner/consumer") -> Path:
    catalog = {
        "schema_version": 1,
        "canaries": [
            {
                "id": "consumer-fixture",
                "repository": repository,
                "revision": revision,
                "target_level": "L2",
                "proof_level": "source-inspection",
                "expected": {"facts.external_upstream": False},
            }
        ],
    }
    path.write_text(yaml.safe_dump(catalog), encoding="utf-8")
    return path


def test_pre_materialized_canary_must_match_pinned_repository_and_revision(tmp_path: Path) -> None:
    checker = _load("consumer_canary_integrity", TOOLS / "check_consumer_canaries.py")
    workspace = tmp_path / "workspace"
    checkout = workspace / "consumer-fixture"
    revision = _checkout(checkout)
    catalog = _canary_catalog(tmp_path / "canaries.yaml", revision="f" * 40)

    findings = checker.check_catalog(catalog, workspace, materialize=False)
    assert any("revision does not match the canary pin" in finding for finding in findings)

    catalog = _canary_catalog(tmp_path / "canaries.yaml", revision=revision, repository="other/consumer")
    findings = checker.check_catalog(catalog, workspace, materialize=False)
    assert any("repository does not match the canary pin" in finding for finding in findings)


def test_pre_materialized_canary_rejects_dirty_and_ignored_inputs(tmp_path: Path) -> None:
    checker = _load("consumer_canary_dirty_worktree", TOOLS / "check_consumer_canaries.py")
    workspace = tmp_path / "workspace"
    checkout = workspace / "consumer-fixture"
    revision = _checkout(checkout)
    catalog = _canary_catalog(tmp_path / "canaries.yaml", revision=revision)

    (checkout / "README.md").write_text("modified\n", encoding="utf-8")
    findings = checker.check_catalog(catalog, workspace, materialize=False)
    assert any("must be pristine" in finding for finding in findings)

    _git(checkout, "reset", "--hard", "HEAD")
    (checkout / ".git/info/exclude").write_text("ignored.py\n", encoding="utf-8")
    (checkout / "ignored.py").write_text("# inspection input\n", encoding="utf-8")
    findings = checker.check_catalog(catalog, workspace, materialize=False)
    assert any("must be pristine" in finding for finding in findings)


def test_canary_planner_failure_is_reported_per_consumer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checker = _load("consumer_canary_planner_failure", TOOLS / "check_consumer_canaries.py")
    workspace = tmp_path / "workspace"
    checkout = workspace / "consumer-fixture"
    revision = _checkout(checkout)
    catalog = _canary_catalog(tmp_path / "canaries.yaml", revision=revision)
    monkeypatch.setattr(checker, "inspect_repository", lambda _path: {"facts": {"external_upstream": False}})

    def fail_plan(_path: Path, *, target_level: str) -> dict:
        assert target_level == "L2"
        raise ValueError("planner fixture failed")

    monkeypatch.setattr(checker, "build_plan", fail_plan)
    findings = checker.check_catalog(catalog, workspace, materialize=False)
    assert any("planning failed: planner fixture failed" in finding for finding in findings)


def test_sdk_claim_does_not_confuse_package_prefix_or_wildcard_pin(tmp_path: Path) -> None:
    planner = _load("adoption_planner_integrity", TOOLS / "plan_existing_project.py")
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='sample'\nversion='1.0.0'\ndependencies=['mcpfoo==9.0.0','mcp==2.*']\n",
        encoding="utf-8",
    )
    (tmp_path / "server.py").write_text("# stdio\n", encoding="utf-8")
    plan = planner.build_plan(tmp_path, target_level="L2")
    assert plan["sdk_compatibility_claim"] == {
        "package": "mcp",
        "requirement": "==2.*",
        "status": "requires-compatibility-evidence",
    }

    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='sample'\nversion='1.0.0'\ndependencies=['mcpfoo==9.0.0','mcp==2.0.0']\n",
        encoding="utf-8",
    )
    assert planner.build_plan(tmp_path, target_level="L2")["sdk_compatibility_claim"]["status"] == "exact-pin"


def test_sdk_claim_uses_requirements_files_seen_by_discovery(tmp_path: Path) -> None:
    planner = _load("adoption_planner_requirements", TOOLS / "plan_existing_project.py")
    (tmp_path / "requirements.txt").write_text("mcpfoo==9.0.0\nmcp==2.*\n", encoding="utf-8")
    (tmp_path / "server.py").write_text("# stdio\n", encoding="utf-8")

    plan = planner.build_plan(tmp_path, target_level="L2")
    assert plan["discovery"]["facts"]["sdk_profile"] == "python-official-mcp"
    assert plan["sdk_compatibility_claim"] == {
        "package": "mcp",
        "requirement": "==2.*",
        "status": "requires-compatibility-evidence",
    }

    (tmp_path / "requirements.txt").write_text("mcpfoo==9.0.0\nmcp==2.0.0\n", encoding="utf-8")
    assert planner.build_plan(tmp_path, target_level="L2")["sdk_compatibility_claim"]["status"] == "exact-pin"


def test_feedback_selector_must_name_top_level_test_and_owner_heading_must_not_be_fenced(tmp_path: Path) -> None:
    (tmp_path / "contracts").mkdir()
    (tmp_path / "skills/example").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "contracts/consumer-canaries.yaml").write_text(
        "schema_version: 1\ncanaries: []\n",
        encoding="utf-8",
    )
    (tmp_path / "skills/example/guide.md").write_text(
        "# Guide\n\n```md\n## Fake owner\n```not-a-close\n## Still fenced\n```\n\n## Real owner\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_example.py").write_text(
        "def helper():\n    def test_nested():\n        assert True\n    return test_nested\n",
        encoding="utf-8",
    )
    registry = {
        "schema_version": 1,
        "incidents": [
            {
                "id": "field.selector-integrity",
                "source_kind": "field-report",
                "failure_mode": "A claimed regression selector existed in source but could not be selected by pytest.",
                "generalized_invariant": "Promoted regressions and canonical owners must resolve to executable tests and real document headings.",
                "canonical_owner": "skills/example/guide.md#still-fenced",
                "regression_selectors": ["tests/test_example.py::test_nested"],
                "status": "implemented",
            }
        ],
    }
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    findings = validate_registry(path, repository_root=tmp_path)
    assert any("canonical owner anchor #still-fenced does not exist" in finding for finding in findings)
    assert any("must be a top-level test" in finding for finding in findings)


def test_feedback_selector_must_be_collectable_by_pytest(tmp_path: Path) -> None:
    (tmp_path / "contracts").mkdir()
    (tmp_path / "skills/example").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "contracts/consumer-canaries.yaml").write_text("schema_version: 1\ncanaries: []\n", encoding="utf-8")
    (tmp_path / "skills/example/guide.md").write_text("# Guide\n\n## Owner\n", encoding="utf-8")
    (tmp_path / "tests/test_hidden.py").write_text(
        "__test__ = False\n\ndef test_hidden():\n    assert True\n",
        encoding="utf-8",
    )
    registry = {
        "schema_version": 1,
        "incidents": [
            {
                "id": "field.collection-integrity",
                "source_kind": "field-report",
                "failure_mode": "A selector existed in source but pytest collection disabled the module.",
                "generalized_invariant": "Promoted regressions must be addressable by the repository test runner.",
                "canonical_owner": "skills/example/guide.md#owner",
                "regression_selectors": ["tests/test_hidden.py::test_hidden"],
                "status": "implemented",
            }
        ],
    }
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    findings = validate_registry(path, repository_root=tmp_path)
    assert any("not collectable by pytest" in finding for finding in findings)


def test_runtime_version_exactness_rejects_moving_tokens_without_substring_false_positives() -> None:
    for version in ("latest", "stable", "release", "edge", "1.x", "2.*", ">=1.2,<2", "nightly-20260813"):
        assert _is_non_exact_version(version) is True, version
    assert _is_non_exact_version("concurrent-1.0.0") is False
    assert _is_non_exact_version("maint-2026.08.13") is False
    assert _is_non_exact_version("1.2.3-rc.1") is False


def test_atomic_report_context_may_have_empty_profiles_and_capabilities() -> None:
    schema = json.loads((ROOT / "contracts/atomic-claim-report.schema.json").read_text(encoding="utf-8"))
    report = {
        "schema_version": 1,
        "report_id": "empty-context-is-valid",
        "repository": {"name": "example/server", "revision": "1" * 40},
        "skill": "mcp-server-architect",
        "context": {"target_level": "L1", "profiles": [], "capabilities": []},
        "checks": [
            {
                "control_id": "mcp.example",
                "status": "passed",
                "implementation": [{"path": "server.py", "symbol": "main"}],
                "command": "pytest tests/test_server.py::test_server",
                "test_case": "tests/test_server.py::test_server",
                "result": "passed",
                "evidence_types": ["unit"],
                "evidence_paths": ["evidence/test.json"],
            }
        ],
        "residual_risks": [],
    }
    assert list(Draft202012Validator(schema).iter_errors(report)) == []
