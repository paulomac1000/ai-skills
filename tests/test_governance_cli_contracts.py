"""CLI and boundary regressions for the governance contracts introduced in 2.0.0."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from contracts import build_skill_bundle as bundle
from contracts import skill_consumer as consumer
from contracts import skill_distribution as distribution


def _bundle_repository(root: Path) -> Path:
    repository = root / "repository"
    skill = repository / "skills/example-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    (skill / "manifest.yaml").write_text("name: example-skill\n", encoding="utf-8")
    return repository


def test_bundle_cli_reports_success_and_contract_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = _bundle_repository(tmp_path)
    output = tmp_path / "bundle"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_skill_bundle.py",
            "--repository-root",
            str(repository),
            "--skill-id",
            "example-skill",
            "--output",
            str(output),
            "--source-revision",
            "a" * 40,
        ],
    )
    assert bundle.main() == 0
    success = json.loads(capsys.readouterr().out)
    assert success["verdict"] == "pass"
    assert success["bundle"]["skill_id"] == "example-skill"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_skill_bundle.py",
            "--repository-root",
            str(repository),
            "--skill-id",
            "INVALID",
            "--output",
            str(tmp_path / "invalid"),
            "--source-revision",
            "a" * 40,
        ],
    )
    assert bundle.main() == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["verdict"] == "fail"
    assert "invalid skill_id" in failure["error"]


def test_bundle_rejects_malformed_manifest_shared_resource_and_output_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _bundle_repository(tmp_path)
    manifest = repository / "skills/example-skill/manifest.yaml"
    manifest.write_text("- not-an-object\n", encoding="utf-8")
    with pytest.raises(bundle.BundleError, match="root must be an object"):
        bundle.build_bundle(
            repository_root=repository,
            skill_id="example-skill",
            output=tmp_path / "out-a",
            source_revision="a" * 40,
        )

    manifest.write_text("name: example-skill\ndependencies:\n  shared_resources:\n    - 7\n", encoding="utf-8")
    with pytest.raises(bundle.BundleError, match="shared resource path must be a string"):
        bundle.build_bundle(
            repository_root=repository,
            skill_id="example-skill",
            output=tmp_path / "out-b",
            source_revision="a" * 40,
        )

    manifest.write_text("name: example-skill\n", encoding="utf-8")
    output_file = tmp_path / "occupied-file"
    output_file.write_text("occupied\n", encoding="utf-8")
    with pytest.raises(bundle.BundleError, match="must be a directory"):
        bundle.build_bundle(
            repository_root=repository,
            skill_id="example-skill",
            output=output_file,
            source_revision="a" * 40,
        )

    with monkeypatch.context() as patch:
        patch.setattr(bundle, "MAX_FILES", 1)
        with pytest.raises(bundle.BundleError, match="file limit"):
            bundle.build_bundle(
                repository_root=repository,
                skill_id="example-skill",
                output=tmp_path / "out-c",
                source_revision="a" * 40,
            )


def _catalog() -> dict[str, object]:
    return {
        "schema_version": 1,
        "catalog_revision": "catalog-1",
        "skills": [
            {
                "skill_id": "example-skill",
                "version": "2.0.0",
                "capabilities": ["analysis"],
                "loading": {"modes": ["runtime_tool"]},
            }
        ],
    }


def _runtime() -> dict[str, object]:
    return {
        "schema_version": 1,
        "runtime_id": "runtime-1",
        "observed_at": "2026-09-10T20:00:00Z",
        "skills": [
            {
                "skill_id": "example-skill",
                "installed": True,
                "installed_revision": "a" * 40,
                "installed_artifact_digest": "1" * 64,
                "runtime_visible": True,
                "compatible": True,
                "supported_load_modes": ["runtime_tool"],
                "loaded_revision": None,
                "loaded_artifact_digest": None,
                "distribution_mode": "VENDORED",
            }
        ],
    }


def test_skill_consumer_cli_distinguishes_ready_unavailable_and_invalid_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    catalog_path = tmp_path / "catalog.yaml"
    runtime_path = tmp_path / "runtime.json"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")
    runtime_path.write_text(json.dumps(_runtime()), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "skill_consumer.py",
            "--catalog",
            str(catalog_path),
            "--runtime-state",
            str(runtime_path),
            "--capability",
            "analysis",
        ],
    )
    assert consumer.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "READY"

    monkeypatch.setattr(sys, "argv", [*sys.argv[:-1], "missing"])
    assert consumer.main() == 1
    assert json.loads(capsys.readouterr().out)["status"] == "NOT_CATALOGUED"

    runtime_path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [*sys.argv[:-1], "analysis"])
    assert consumer.main() == 2
    assert json.loads(capsys.readouterr().out)["status"] == "UNKNOWN"


def test_skill_consumer_catalog_loader_rejects_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "catalog.yaml"
    path.write_text("skills: [", encoding="utf-8")
    with pytest.raises(consumer.SkillConsumerError, match="catalog cannot be loaded"):
        consumer.load_catalog(path)


def _source(root: Path) -> Path:
    source = root / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    return source


def _install_argv(source: Path, target: Path, project: Path) -> list[str]:
    return [
        "skill_distribution.py",
        "install",
        "--source",
        str(source),
        "--target",
        str(target),
        "--project-root",
        str(project),
        "--mode",
        "VENDORED",
        "--skill-id",
        "example-skill",
        "--canonical-source",
        "github:example/skill",
        "--source-revision",
        "a" * 40,
        "--managed-by",
        "ai-skills",
        "--update-policy",
        "explicit",
        "--cleanup-policy",
        "owner-digest-verified",
    ]


def test_skill_distribution_cli_install_uninstall_and_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _source(tmp_path)
    target = project / "vendor/example-skill"

    monkeypatch.setattr(sys, "argv", _install_argv(source, target, project))
    assert distribution.main() == 0
    installed = json.loads(capsys.readouterr().out)
    assert installed["verdict"] == "pass"
    assert installed["state"]["distribution_mode"] == "VENDORED"

    uninstall_argv = [
        "skill_distribution.py",
        "uninstall",
        "--target",
        str(target),
        "--project-root",
        str(project),
        "--mode",
        "VENDORED",
    ]
    monkeypatch.setattr(sys, "argv", uninstall_argv)
    assert distribution.main() == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "pass"
    assert not target.exists()

    monkeypatch.setattr(sys, "argv", uninstall_argv)
    assert distribution.main() == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["verdict"] == "fail"
    assert "no managed installation state" in failure["error"]


def test_distribution_rejects_source_target_overlap_and_non_directory_roots(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _source(tmp_path)
    with pytest.raises(distribution.DistributionError, match="must not contain each other"):
        distribution.install(
            source=source,
            target=source / "nested-target",
            project_root=project,
            mode="GLOBAL",
            skill_id="example-skill",
            canonical_source="github:example/skill",
            source_revision="a" * 40,
            managed_by="ai-skills",
            update_policy="explicit",
            cleanup_policy="owner-digest-verified",
        )

    file_root = tmp_path / "not-a-directory"
    file_root.write_text("file\n", encoding="utf-8")
    with pytest.raises(distribution.DistributionError, match="not a directory"):
        distribution._resolved_directory(file_root)
