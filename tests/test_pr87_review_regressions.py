"""Fail-closed regressions for PR #87 review findings."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

from skill_consumer import resolve_skill  # noqa: E402
from skill_distribution import DistributionError, STATE_FILENAME, install, uninstall  # noqa: E402


def _source(root: Path) -> Path:
    source = root / "source"
    (source / "nested").mkdir(parents=True)
    (source / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    (source / "nested/payload.txt").write_text("owned\n", encoding="utf-8")
    return source


def _install(source: Path, target: Path, project: Path) -> None:
    install(
        source=source,
        target=target,
        project_root=project,
        mode="VENDORED",
        skill_id="example-skill",
        canonical_source="github:example/skills/example-skill",
        source_revision="a" * 40,
        managed_by="ai-skills",
        update_policy="explicit",
        cleanup_policy="owner-digest-verified",
        installed_at="2026-09-10T00:00:00+00:00",
    )


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.txt",
        "nested/../../outside.txt",
        "/tmp/outside.txt",
        "C:/outside.txt",
        "nested\\outside.txt",
        ".ai-skill-installation.json",
    ],
)
def test_installation_schema_rejects_unsafe_owned_paths(unsafe_path: str) -> None:
    schema = json.loads((CONTRACTS / "skill-installation.schema.json").read_text(encoding="utf-8"))
    state = {
        "schema_version": 1,
        "skill_id": "example-skill",
        "canonical_source": "github:example/skills/example-skill",
        "source_revision": "a" * 40,
        "source_digest": "b" * 64,
        "distribution_mode": "VENDORED",
        "install_scope": "project",
        "install_path": "/tmp/project/.agents/skills/example-skill",
        "installed_at": "2026-09-10T00:00:00Z",
        "managed_by": "ai-skills",
        "update_policy": "explicit",
        "cleanup_policy": "owner-digest-verified",
        "owned_files": [{"path": unsafe_path, "sha256": "c" * 64, "size": 1}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(state)


def test_uninstall_rejects_tampered_parent_traversal_before_deleting(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _source(tmp_path / "trusted")
    target = project / ".agents/skills/example-skill"
    _install(source, target, project)
    outside = project / "outside.txt"
    outside.write_text("preserve\n", encoding="utf-8")

    state_path = target / STATE_FILENAME
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["owned_files"][0]["path"] = "../../../outside.txt"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(DistributionError, match="unsafe segment"):
        uninstall(target=target, project_root=project, mode="VENDORED")
    assert outside.read_text(encoding="utf-8") == "preserve\n"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support is unavailable")
def test_uninstall_rejects_intermediate_symlink_before_touching_external_file(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _source(tmp_path / "trusted")
    target = project / ".agents/skills/example-skill"
    _install(source, target, project)

    external = tmp_path / "external"
    external.mkdir()
    external_payload = external / "payload.txt"
    external_payload.write_text("external\n", encoding="utf-8")
    (target / "nested/payload.txt").unlink()
    (target / "nested").rmdir()
    try:
        (target / "nested").symlink_to(external, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(DistributionError, match="symlink component"):
        uninstall(target=target, project_root=project, mode="VENDORED")
    assert external_payload.read_text(encoding="utf-8") == "external\n"


def _catalog() -> dict:
    return {
        "schema_version": 1,
        "catalog_revision": "test-catalog",
        "skills": [
            {
                "skill_id": "exact-skill",
                "version": "2.0.0",
                "capabilities": ["analysis"],
                "use_when": ["declared use"],
                "do_not_use_when": ["declared exclusion"],
                "loading": {"modes": ["runtime_tool"]},
            }
        ],
    }


def _runtime(**overrides: object) -> dict:
    skill = {
        "skill_id": "exact-skill",
        "installed": True,
        "installed_revision": "abc123",
        "installed_artifact_digest": "1" * 64,
        "runtime_visible": True,
        "compatible": True,
        "supported_load_modes": ["runtime_tool"],
        "loaded_revision": "abc123",
        "loaded_artifact_digest": "1" * 64,
    }
    skill.update(overrides)
    return {
        "schema_version": 1,
        "runtime_id": "test-runtime",
        "observed_at": "2026-09-10T00:00:00Z",
        "skills": [skill],
    }


def test_loaded_state_requires_installed_and_loaded_artifact_digests() -> None:
    assert resolve_skill(catalog=_catalog(), runtime=_runtime(), capability="analysis").status == "LOADED"
    assert (
        resolve_skill(
            catalog=_catalog(),
            runtime=_runtime(installed_artifact_digest=None),
            capability="analysis",
        ).status
        == "UNKNOWN"
    )
    assert (
        resolve_skill(
            catalog=_catalog(),
            runtime=_runtime(loaded_artifact_digest=None),
            capability="analysis",
        ).status
        == "STALE_LOADED_REVISION"
    )
