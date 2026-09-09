from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

from skill_consumer import resolve_skill  # noqa: E402
from skill_distribution import DistributionError, STATE_FILENAME, install, uninstall  # noqa: E402


def _source(root: Path, text: str = "# Skill\n") -> Path:
    source = root / "source-skill"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(text, encoding="utf-8")
    (source / "STANDARD.md").write_text("# Standard\n", encoding="utf-8")
    return source


def _install_kwargs(source: Path, target: Path, project: Path, mode: str) -> dict:
    return {
        "source": source,
        "target": target,
        "project_root": project,
        "mode": mode,
        "skill_id": "example-skill",
        "canonical_source": "github:example/skills/example-skill",
        "source_revision": "a" * 40,
        "managed_by": "ai-skills",
        "update_policy": "explicit",
        "cleanup_policy": "owner-digest-verified",
        "installed_at": "2026-09-10T00:00:00+00:00",
    }


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if ".git" in path.parts or not path.is_file():
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_contract_schemas_and_catalog_validate() -> None:
    catalog = yaml.safe_load((CONTRACTS / "skill-catalog.yaml").read_text(encoding="utf-8"))
    schema = json.loads((CONTRACTS / "skill-catalog.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(catalog)
    assert all("body" not in entry and "instructions" not in entry for entry in catalog["skills"])
    assert len(catalog["skills"]) >= 7


def test_global_install_leaves_project_tree_unchanged(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "tracked.txt").write_text("unchanged\n", encoding="utf-8")
    source = _source(tmp_path / "trusted")
    target = tmp_path / "global" / "example-skill"
    before = _tree_digest(project)

    state = install(**_install_kwargs(source, target, project, "GLOBAL"))

    assert state.distribution_mode == "GLOBAL"
    assert state.source_revision == "a" * 40
    assert _tree_digest(project) == before
    assert (target / STATE_FILENAME).is_file()


def test_global_target_inside_project_fails_closed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _source(tmp_path / "trusted")
    with pytest.raises(DistributionError, match="outside the project"):
        install(**_install_kwargs(source, project / ".agents/skills/example-skill", project, "GLOBAL"))


def test_vendored_install_is_idempotent_and_modified_copy_blocks_update(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _source(tmp_path / "trusted")
    target = project / ".agents" / "skills" / "example-skill"

    first = install(**_install_kwargs(source, target, project, "VENDORED"))
    second = install(**_install_kwargs(source, target, project, "VENDORED"))
    assert first == second
    state = json.loads((target / STATE_FILENAME).read_text(encoding="utf-8"))
    assert state["canonical_source"] == "github:example/skills/example-skill"
    assert state["distribution_mode"] == "VENDORED"

    (target / "SKILL.md").write_text("user modification\n", encoding="utf-8")
    (source / "SKILL.md").write_text("upstream update\n", encoding="utf-8")
    with pytest.raises(DistributionError, match="modified outside installer ownership"):
        install(**{**_install_kwargs(source, target, project, "VENDORED"), "source_revision": "b" * 40})


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required for broad-staging regression")
def test_ephemeral_install_is_ignored_and_broad_staging_cannot_ingest_it(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / ".gitignore").write_text(".ai-skills/ephemeral/\n", encoding="utf-8")
    (project / "README.md").write_text("# Project\n", encoding="utf-8")
    source = _source(tmp_path / "trusted")
    target = project / ".ai-skills" / "ephemeral" / "example-skill"

    install(**_install_kwargs(source, target, project, "EPHEMERAL"))
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project,
        check=True,
        text=True,
        capture_output=True,
    ).stdout

    assert ".ai-skills/ephemeral" not in status
    uninstall(target=target, project_root=project, mode="EPHEMERAL")
    assert not target.exists()


def test_ephemeral_requires_designated_ignore_boundary(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / ".gitignore").write_text("dist/\n", encoding="utf-8")
    source = _source(tmp_path / "trusted")
    target = project / ".ai-skills" / "ephemeral" / "example-skill"
    with pytest.raises(DistributionError, match="must be ignored"):
        install(**_install_kwargs(source, target, project, "EPHEMERAL"))


def test_uninstall_refuses_user_owned_or_modified_files_before_deleting(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _source(tmp_path / "trusted")
    target = project / ".agents" / "skills" / "example-skill"
    install(**_install_kwargs(source, target, project, "VENDORED"))
    (target / "notes.txt").write_text("project owned\n", encoding="utf-8")

    with pytest.raises(DistributionError, match="user/project-owned"):
        uninstall(target=target, project_root=project, mode="VENDORED")
    assert (target / "SKILL.md").is_file()
    assert (target / "notes.txt").is_file()


def _catalog(*entries: dict) -> dict:
    return {"schema_version": 1, "catalog_revision": "test-catalog", "skills": list(entries)}


def _entry(skill_id: str, capability: str) -> dict:
    return {
        "skill_id": skill_id,
        "version": "1.0.0",
        "capabilities": [capability],
        "use_when": ["declared use"],
        "do_not_use_when": ["declared exclusion"],
        "loading": {"modes": ["runtime_tool", "vendored"]},
    }


def _state(skill_id: str, **overrides: object) -> dict:
    item = {
        "skill_id": skill_id,
        "installed": True,
        "installed_revision": "abc123",
        "installed_artifact_digest": "1" * 64,
        "runtime_visible": True,
        "compatible": True,
        "supported_load_modes": ["runtime_tool"],
        "loaded_revision": None,
        "loaded_artifact_digest": None,
    }
    item.update(overrides)
    return {"schema_version": 1, "runtime_id": "test", "observed_at": "2026-09-10T00:00:00Z", "skills": [item]}


def test_catalogued_but_not_installed_is_not_a_name_guess_loop() -> None:
    result = resolve_skill(
        catalog=_catalog(_entry("exact-skill", "release-verification")),
        runtime={"skills": []},
        capability="release-verification",
    )
    assert result.status == "NOT_INSTALLED"
    assert result.skill_id == "exact-skill"


def test_installed_visibility_loadability_and_compatibility_are_distinct() -> None:
    catalog = _catalog(_entry("exact-skill", "analysis"))
    assert resolve_skill(catalog=catalog, runtime=_state("exact-skill", runtime_visible=False), capability="analysis").status == "NOT_VISIBLE"
    assert resolve_skill(catalog=catalog, runtime=_state("exact-skill", compatible=False), capability="analysis").status == "INCOMPATIBLE"
    assert resolve_skill(
        catalog=catalog,
        runtime=_state("exact-skill", supported_load_modes=["preload"]),
        capability="analysis",
        allowed_load_modes=("runtime_tool",),
    ).status == "UNSUPPORTED_LOAD_MODE"


def test_exact_capability_beats_overlapping_names_and_keywords() -> None:
    catalog = _catalog(
        _entry("release-auditor", "release-documentation"),
        _entry("release-workflow-helper", "protected-release-workflow"),
    )
    runtime = _state("release-workflow-helper")
    result = resolve_skill(catalog=catalog, runtime=runtime, capability="protected-release-workflow")
    assert result.status == "READY"
    assert result.skill_id == "release-workflow-helper"


def test_large_catalog_does_not_require_skill_bodies() -> None:
    entries = [_entry(f"skill-{index}", f"capability-{index}") for index in range(100)]
    result = resolve_skill(
        catalog=_catalog(*entries),
        runtime=_state("skill-73"),
        capability="capability-73",
    )
    assert result.status == "READY"
    assert result.skill_id == "skill-73"
    assert all("body" not in entry for entry in entries)


def test_loaded_revision_is_invalidated_when_installed_artifact_changes() -> None:
    catalog = _catalog(_entry("exact-skill", "analysis"))
    runtime = _state(
        "exact-skill",
        loaded_revision="old",
        loaded_artifact_digest="2" * 64,
    )
    result = resolve_skill(catalog=catalog, runtime=runtime, capability="analysis")
    assert result.status == "STALE_LOADED_REVISION"


def test_explicit_required_skill_unavailable_is_blocked_deviation() -> None:
    result = resolve_skill(
        catalog=_catalog(_entry("other-skill", "analysis")),
        runtime={"skills": []},
        capability="analysis",
        required_skill="required-skill",
    )
    assert result.status == "BLOCKED_REQUIRED_SKILL"
    assert result.deviation_required is True
    assert result.skill_id == "required-skill"
