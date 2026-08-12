"""Regressions for the final exact-head bot follow-up."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENTS_TOOLS = ROOT / "skills/agents-md-architect/tools"
CI_TOOLS = ROOT / "skills/ci-cd-architect/tools"
sys.path.insert(0, str(AGENTS_TOOLS))
sys.path.insert(0, str(CI_TOOLS))

import agents_md_python_evidence as python_evidence  # noqa: E402
import agents_md_shell_evidence as shell_evidence  # noqa: E402
import check_github_actions_policy as workflow_policy  # noqa: E402


@pytest.mark.parametrize(
    "source",
    (
        """import subprocess
if False:
    subprocess.run(["python", "scripts/ghost.py"], check=True)
""",
        """import subprocess
while 0:
    subprocess.run(["python", "scripts/ghost.py"], check=True)
""",
        """import subprocess
result = (
    subprocess.run(["python", "scripts/ghost.py"], check=True)
    if ()
    else None
)
""",
    ),
)
def test_literal_dead_python_branch_cannot_establish_evidence(source: str) -> None:
    commands = python_evidence._extract_python_invocations(source)

    assert "python scripts/ghost.py" not in commands


def test_literal_live_python_branch_remains_evidence() -> None:
    commands = python_evidence._extract_python_invocations(
        """import subprocess
if True:
    subprocess.run(["python", "scripts/ci.py"], check=True)
else:
    subprocess.run(["python", "scripts/ghost.py"], check=True)
"""
    )

    assert "python scripts/ci.py" in commands
    assert "python scripts/ghost.py" not in commands


def test_invalid_python_never_establishes_evidence() -> None:
    assert python_evidence._extract_python_invocations("if:") == set()


def test_make_recipe_continuation_establishes_complete_gate() -> None:
    commands = shell_evidence._extract_gate_invocations(
        "Makefile",
        """quality:
	python scripts/ci.py \\
	  --strict \\
	  --profile safety-critical
""",
    )

    assert "python scripts/ci.py --strict --profile safety-critical" in commands
    assert "python scripts/ci.py" not in commands


def test_workflow_reader_rejects_intermediate_symlink(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside"
    workflows = outside / "workflows"
    workflows.mkdir(parents=True)
    workflow = workflows / "ci.yml"
    workflow.write_text("name: outside\n", encoding="utf-8")
    try:
        (repository / ".github").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    text, error = workflow_policy._read_workflow(
        repository / ".github" / "workflows" / "ci.yml",
        repository,
    )

    assert text is None
    assert error is not None
    assert "cannot read workflow safely" in error


def test_component_snapshot_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    with pytest.raises(OSError, match="reparse or symlink"):
        workflow_policy._component_snapshot(link / "workflow.yml")


def test_component_snapshot_detects_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = tmp_path / "workflow.yml"
    replacement = tmp_path / "replacement.yml"
    workflow.write_text("name: first\n", encoding="utf-8")
    replacement.write_text("name: second\n", encoding="utf-8")
    snapshot = workflow_policy._component_snapshot(workflow)
    real_lstat = workflow_policy.os.lstat
    replacement_stat = real_lstat(replacement)

    def replaced_lstat(
        path: os.PathLike[str] | str,
        *,
        dir_fd: int | None = None,
    ) -> os.stat_result:
        if dir_fd is not None:
            return real_lstat(path, dir_fd=dir_fd)
        return replacement_stat if Path(path) == workflow else real_lstat(path)

    monkeypatch.setattr(workflow_policy.os, "lstat", replaced_lstat)

    assert not workflow_policy._snapshot_is_current(snapshot)


def test_fallback_open_binds_every_component(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = tmp_path / "workflow.yml"
    workflow.write_text("name: stable\n", encoding="utf-8")
    monkeypatch.setattr(workflow_policy, "_supports_component_nofollow", lambda: False)

    descriptor, snapshot = workflow_policy._open_stable(workflow, os.O_RDONLY)
    try:
        assert snapshot is not None
        assert os.read(descriptor, 4) == b"name"
    finally:
        os.close(descriptor)


def test_workflow_reader_rejects_invalid_utf8(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    workflow = repository / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_bytes(b"\xff")

    text, error = workflow_policy._read_workflow(workflow, repository)

    assert text is None
    assert error is not None
    assert "cannot read workflow safely" in error


def test_workflow_reader_enforces_size_while_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    workflow = repository / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: oversized\n", encoding="utf-8")
    monkeypatch.setattr(workflow_policy, "MAX_WORKFLOW_BYTES", 4)

    text, error = workflow_policy._read_workflow(workflow, repository)

    assert text is None
    assert error == "workflow exceeds 4 byte limit"


def test_missing_workflow_directory_reports_stable_finding(tmp_path: Path) -> None:
    paths, findings = workflow_policy.workflow_paths(tmp_path)

    assert paths == []
    assert any("no GitHub Actions workflows found" in finding.message for finding in findings)


def test_workflow_directory_must_fail_closed(tmp_path: Path) -> None:
    workflow_path = tmp_path / ".github" / "workflows"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text("not a directory", encoding="utf-8")

    paths, findings = workflow_policy.workflow_paths(tmp_path)

    assert paths == []
    assert any(
        "must be a regular directory" in finding.message or "cannot enumerate workflows" in finding.message
        for finding in findings
    )


def test_workflow_enumeration_charges_non_yaml_entries_to_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    workflow_dir = repository / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    for index in range(5):
        (workflow_dir / f"noise-{index}.txt").write_text("noise", encoding="utf-8")
    monkeypatch.setattr(workflow_policy, "MAX_DISCOVERY_ENTRIES", 3)

    paths, findings = workflow_policy.workflow_paths(repository)

    assert paths == []
    assert any("entry count exceeds 3" in finding.message for finding in findings)


def test_capability_manifest_schema_error_stops_unhashable_semantics(tmp_path: Path) -> None:
    import json

    from contracts.validate_capability_manifest import validate_manifest

    manifest = {
        "schema_version": 1,
        "id": "dangerous.write",
        "name": "Dangerous write",
        "description": "Malformed approval binds produce findings, not a traceback.",
        "operation_kind": "write",
        "risk": "high",
        "determinism": "deterministic",
        "latency": "interactive",
        "impact": "external",
        "active_state": "active",
        "retryable": False,
        "idempotent": False,
        "reversible": False,
        "requires_confirmation": True,
        "idempotency_key_required": False,
        "authorization_scopes": ["write"],
        "concurrency": {"scope": "principal", "limit": 1, "queue_limit": 1},
        "max_response_bytes": 1024,
        "protocol_revisions": ["2026-07-28"],
        "approval": {"binds": [{}]},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert validate_manifest(path)


def test_atomic_claim_schema_error_stops_semantics(tmp_path: Path) -> None:
    import json

    from contracts.validate_atomic_claims import validate_report

    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "skill": "mcp-server-architect",
                "context": {
                    "target_level": "L1",
                    "profiles": [],
                    "capabilities": [],
                },
                "checks": [
                    {
                        "control_id": "mcp.architecture.separation.domain-adapter",
                        "status": "passed",
                        "evidence_types": [{}],
                        "implementation": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert validate_report(report)


def test_afds_percent_encoded_hash_remains_part_of_local_path(tmp_path: Path) -> None:
    import importlib.util
    import sys

    module_path = ROOT / "skills/afds-doc-writer/validate.py"
    spec = importlib.util.spec_from_file_location("afds_encoded_hash", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    target = tmp_path / "guide#part.md"
    target.write_text("# Guide\n", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text("[guide](guide%23part.md)\n", encoding="utf-8")
    assert (
        module._validate_links(
            source,
            source.read_text(encoding="utf-8"),
            tmp_path,
            check_anchors=True,
        )
        == []
    )


def test_explicit_missing_afds_governance_fails_closed(tmp_path: Path) -> None:
    import importlib.util
    import sys

    module_path = ROOT / "skills/afds-doc-writer/validate.py"
    spec = importlib.util.spec_from_file_location("afds_missing_governance", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    readme = tmp_path / "README.md"
    readme.write_text("# Example\n", encoding="utf-8")
    assert (
        module.main(
            [
                "--repository-root",
                str(tmp_path),
                "--governance",
                str(tmp_path / "missing.yaml"),
                str(readme),
            ]
        )
        == 1
    )


def test_hyphenated_write_permission_is_privileged() -> None:
    assert workflow_policy._permissions_write({"contents": "read-write"}) is True


def test_generated_python_image_uses_exact_checked_out_sha() -> None:
    template = (ROOT / "skills/mcp-server-architect/tools/python-template/.github/workflows/ci.yml.template").read_text(
        encoding="utf-8"
    )
    expression = "${" + "{ github.event.pull_request.head.sha || github.sha }}"
    assert f"EXPECTED_SHA: {expression}" in template
    assert 'test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"' in template
    assert "sha-${EXPECTED_SHA}" in template
    assert "sha-${GITHUB_SHA}" not in template
