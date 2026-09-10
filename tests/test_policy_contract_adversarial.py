"""Adversarial coverage for policy-critical governance contracts."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from contracts import build_skill_bundle as bundle
from contracts import skill_consumer as consumer
from contracts import skill_distribution as distribution
from contracts import validate_verification_receipt as receipt

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


STATE_ISOLATION = _load_module(
    "policy_contract_state_isolation",
    ROOT / "skills/ci-cd-architect/tools/verify_state_isolation.py",
)


def _skill_repo(tmp_path: Path, *, shared: object | None = None) -> Path:
    root = tmp_path / "repo"
    skill = root / "skills" / "example-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    manifest = "name: example-skill\n"
    if shared is not None:
        if isinstance(shared, str):
            manifest += f"dependencies:\n  shared_resources:\n    - {shared}\n"
        else:
            manifest += "dependencies:\n  shared_resources: invalid\n"
    (skill / "manifest.yaml").write_text(manifest, encoding="utf-8")
    return root


def test_bundle_copies_declared_shared_resource_and_is_deterministic(tmp_path: Path) -> None:
    root = _skill_repo(tmp_path, shared="contracts/shared.txt")
    (root / "contracts").mkdir()
    (root / "contracts/shared.txt").write_text("shared\n", encoding="utf-8")

    first = bundle.build_bundle(
        repository_root=root,
        skill_id="example-skill",
        output=tmp_path / "out-a",
        source_revision="a" * 40,
    )
    second = bundle.build_bundle(
        repository_root=root,
        skill_id="example-skill",
        output=tmp_path / "out-b",
        source_revision="a" * 40,
    )

    assert first["bundle_digest"] == second["bundle_digest"]
    assert (tmp_path / "out-a/contracts/shared.txt").read_text(encoding="utf-8") == "shared\n"
    assert json.loads((tmp_path / "out-a" / bundle.BUNDLE_STATE).read_text(encoding="utf-8"))["skill_id"] == "example-skill"


@pytest.mark.parametrize("skill_id", ["", "Upper", "bad/name", "-leading"])
def test_bundle_rejects_invalid_skill_identity(tmp_path: Path, skill_id: str) -> None:
    root = _skill_repo(tmp_path)
    with pytest.raises(bundle.BundleError, match="invalid skill_id"):
        bundle.build_bundle(
            repository_root=root,
            skill_id=skill_id,
            output=tmp_path / "out",
            source_revision="a" * 40,
        )


def test_bundle_rejects_invalid_source_manifest_and_output_boundaries(tmp_path: Path) -> None:
    root = _skill_repo(tmp_path)
    with pytest.raises(bundle.BundleError, match="source_revision"):
        bundle.build_bundle(repository_root=root, skill_id="example-skill", output=tmp_path / "out", source_revision=" ")

    (root / "skills/example-skill/manifest.yaml").write_text("name: other-skill\n", encoding="utf-8")
    with pytest.raises(bundle.BundleError, match="identity"):
        bundle.build_bundle(
            repository_root=root,
            skill_id="example-skill",
            output=tmp_path / "out",
            source_revision="a" * 40,
        )

    (root / "skills/example-skill/manifest.yaml").write_text("name: example-skill\n", encoding="utf-8")
    with pytest.raises(bundle.BundleError, match="outside"):
        bundle.build_bundle(
            repository_root=root,
            skill_id="example-skill",
            output=root / "bundle",
            source_revision="a" * 40,
        )
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(bundle.BundleError, match="absent or empty"):
        bundle.build_bundle(
            repository_root=root,
            skill_id="example-skill",
            output=occupied,
            source_revision="a" * 40,
        )


def test_bundle_rejects_unsafe_shared_resource_shapes(tmp_path: Path) -> None:
    root = _skill_repo(tmp_path, shared=object())
    with pytest.raises(bundle.BundleError, match="shared_resources must be a list"):
        bundle.build_bundle(
            repository_root=root,
            skill_id="example-skill",
            output=tmp_path / "out",
            source_revision="a" * 40,
        )

    root = tmp_path / "repo2"
    skill = root / "skills/example-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    (skill / "manifest.yaml").write_text(
        "name: example-skill\ndependencies:\n  shared_resources:\n    - ../escape\n",
        encoding="utf-8",
    )
    with pytest.raises(bundle.BundleError, match="unsafe repository-relative"):
        bundle.build_bundle(
            repository_root=root,
            skill_id="example-skill",
            output=tmp_path / "out2",
            source_revision="a" * 40,
        )


def _entry(skill_id: str = "exact-skill", capability: str = "analysis") -> dict[str, object]:
    return {
        "skill_id": skill_id,
        "version": "2.0.0",
        "capabilities": [capability],
        "loading": {"modes": ["runtime_tool", "vendored"]},
    }


def _catalog(*entries: dict[str, object]) -> dict[str, object]:
    return {"schema_version": 1, "catalog_revision": "catalog-1", "skills": list(entries)}


def _runtime_item(skill_id: str = "exact-skill", **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "skill_id": skill_id,
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
    value.update(overrides)
    return value


def _runtime(*items: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "runtime_id": "runtime-1",
        "observed_at": "2026-09-10T20:00:00Z",
        "skills": list(items),
    }


@pytest.mark.parametrize(
    "skills,match",
    [
        (None, "skills list"),
        (["bad"], "must be an object"),
        ([_entry("", "analysis")], "skill_id is required"),
        ([_entry(), _entry()], "duplicate skill_id"),
        ([{**_entry(), "capabilities": "analysis"}], "capabilities"),
        ([{**_entry(), "capabilities": ["analysis", "analysis"]}], "capabilities"),
        ([{**_entry(), "loading": None}], "loading must be an object"),
        ([{**_entry(), "loading": {"modes": ["unknown"]}}], "loading.modes"),
    ],
)
def test_catalog_entry_validation_fails_closed(skills: object, match: str) -> None:
    with pytest.raises(consumer.SkillConsumerError, match=match):
        consumer._validate_catalog_entries(skills)


@pytest.mark.parametrize(
    "items,match",
    [
        (None, "skills list"),
        (["bad"], "must be an object"),
        ([{**_runtime_item(), "skill_id": ""}], "skill_id is required"),
        ([_runtime_item(), _runtime_item()], "duplicate skill_id"),
        ([{**_runtime_item(), "installed": 1}], "installed must be boolean"),
        ([{**_runtime_item(), "supported_load_modes": ["bad"]}], "supported_load_modes"),
        ([{**_runtime_item(), "installed_revision": ""}], "installed_revision"),
        ([{**_runtime_item(), "installed_artifact_digest": "A" * 64}], "installed_artifact_digest"),
        ([{**_runtime_item(), "distribution_mode": "LOCAL"}], "distribution_mode"),
    ],
)
def test_runtime_entry_validation_fails_closed(items: object, match: str) -> None:
    with pytest.raises(consumer.SkillConsumerError, match=match):
        consumer._validate_runtime_entries(items)


@pytest.mark.parametrize(
    "runtime,match",
    [
        ({"schema_version": 2, "runtime_id": "r", "observed_at": "2026-09-10T00:00:00Z", "skills": []}, "schema_version"),
        ({"schema_version": 1, "runtime_id": "", "observed_at": "2026-09-10T00:00:00Z", "skills": []}, "runtime_id"),
        ({"schema_version": 1, "runtime_id": "r", "observed_at": "2026-09-10T00:00:00", "skills": []}, "timezone-aware"),
    ],
)
def test_runtime_state_validation_rejects_unattributed_observations(runtime: dict[str, object], match: str) -> None:
    with pytest.raises(consumer.SkillConsumerError, match=match):
        consumer._validate_runtime_state(runtime)


def test_catalog_and_runtime_loaders_reject_non_object_or_invalid_inputs(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("- list\n", encoding="utf-8")
    with pytest.raises(consumer.SkillConsumerError, match="object"):
        consumer.load_catalog(catalog)
    runtime = tmp_path / "runtime.json"
    runtime.write_text("[]", encoding="utf-8")
    with pytest.raises(consumer.SkillConsumerError, match="root must be an object"):
        consumer.load_runtime_state(runtime)
    runtime.write_text("{not-json", encoding="utf-8")
    with pytest.raises(consumer.SkillConsumerError, match="cannot be loaded"):
        consumer.load_runtime_state(runtime)


def test_consumer_resolves_every_material_runtime_state() -> None:
    catalog = _catalog(_entry())
    cases = [
        (_runtime(), {}, "NOT_INSTALLED"),
        (_runtime(_runtime_item(installed_revision=None)), {}, "UNKNOWN"),
        (_runtime(_runtime_item(installed_artifact_digest=None)), {}, "UNKNOWN"),
        (_runtime(_runtime_item(runtime_visible=False)), {}, "NOT_VISIBLE"),
        (_runtime(_runtime_item(compatible=False)), {}, "INCOMPATIBLE"),
        (_runtime(_runtime_item(supported_load_modes=["preload"])), {"allowed_load_modes": ("runtime_tool",)}, "UNSUPPORTED_LOAD_MODE"),
        (_runtime(_runtime_item(loaded_revision="a" * 40, loaded_artifact_digest=None)), {}, "STALE_LOADED_REVISION"),
        (_runtime(_runtime_item(loaded_revision="b" * 40, loaded_artifact_digest="1" * 64)), {}, "STALE_LOADED_REVISION"),
        (_runtime(_runtime_item(loaded_revision="a" * 40, loaded_artifact_digest="2" * 64)), {}, "STALE_LOADED_REVISION"),
        (_runtime(_runtime_item(loaded_revision="a" * 40, loaded_artifact_digest="1" * 64)), {}, "LOADED"),
        (_runtime(_runtime_item()), {}, "READY"),
    ]
    for runtime, kwargs, expected in cases:
        assert consumer.resolve_skill(catalog=catalog, runtime=runtime, capability="analysis", **kwargs).status == expected


def test_consumer_catalogue_routing_is_exact_and_required_skill_is_fail_closed() -> None:
    first = _entry("one", "analysis")
    second = _entry("two", "analysis")
    assert consumer.resolve_skill(catalog=_catalog(), runtime=_runtime(), capability="missing").status == "NOT_CATALOGUED"
    assert consumer.resolve_skill(catalog=_catalog(first, second), runtime=_runtime(), capability="analysis").status == "AMBIGUOUS"
    assert consumer.resolve_skill(
        catalog=_catalog(first), runtime=_runtime(), capability="analysis", required_skill="missing"
    ).status == "BLOCKED_REQUIRED_SKILL"
    assert consumer.resolve_skill(
        catalog=_catalog(_entry("one", "other")), runtime=_runtime(), capability="analysis", required_skill="one"
    ).status == "BLOCKED_REQUIRED_SKILL"
    blocked = consumer.resolve_skill(
        catalog=_catalog(first), runtime=_runtime(_runtime_item("one", installed=False)), capability="analysis", required_skill="one"
    )
    assert blocked.status == "BLOCKED_REQUIRED_SKILL"
    assert blocked.deviation_required is True


def test_consumer_digest_and_duplicate_runtime_helpers() -> None:
    catalog = _catalog(_entry())
    assert consumer.catalog_digest(catalog) == consumer.catalog_digest(dict(catalog))
    with pytest.raises(consumer.SkillConsumerError, match="duplicate skill_id"):
        consumer._runtime_entry(_runtime(_runtime_item(), _runtime_item()), "exact-skill")


@pytest.mark.parametrize(
    "value",
    ["", "../escape", "/absolute", "a\\b", "./a", "a//b", distribution.STATE_FILENAME],
)
def test_distribution_rejects_unsafe_owned_paths(value: str) -> None:
    with pytest.raises(distribution.DistributionError):
        distribution._owned_relative_path(value)


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    (source / "nested").mkdir()
    (source / "nested/STANDARD.md").write_text("# Standard\n", encoding="utf-8")
    return source


def _install_kwargs(source: Path, target: Path, project: Path, mode: str = "VENDORED") -> dict[str, object]:
    return {
        "source": source,
        "target": target,
        "project_root": project,
        "mode": mode,
        "skill_id": "example-skill",
        "canonical_source": "github:example/skill",
        "source_revision": "a" * 40,
        "managed_by": "ai-skills",
        "update_policy": "explicit",
        "cleanup_policy": "owner-digest-verified",
        "installed_at": "2026-09-10T20:00:00+00:00",
    }


def test_distribution_scope_rules_reject_wrong_ownership_boundaries(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(distribution.DistributionError, match="outside"):
        distribution._validate_scope("GLOBAL", project, project / "skill")
    with pytest.raises(distribution.DistributionError, match="project-owned subdirectory"):
        distribution._validate_scope("VENDORED", project, tmp_path / "elsewhere")
    with pytest.raises(distribution.DistributionError, match="project-owned subdirectory"):
        distribution._validate_scope("VENDORED", project, project)
    with pytest.raises(distribution.DistributionError, match="EPHEMERAL installation target"):
        distribution._validate_scope("EPHEMERAL", project, project / "elsewhere")
    with pytest.raises(distribution.DistributionError, match="unsupported"):
        distribution._validate_scope("INVALID", project, tmp_path / "elsewhere")


def test_distribution_inventory_bounds_and_empty_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(distribution.DistributionError, match="contains no files"):
        distribution._source_inventory(empty)

    source = _source(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(distribution, "MAX_FILES", 1)
        with pytest.raises(distribution.DistributionError, match="file limit"):
            distribution._source_inventory(source)
    with monkeypatch.context() as patch:
        patch.setattr(distribution, "MAX_TOTAL_BYTES", 1)
        with pytest.raises(distribution.DistributionError, match="byte limit"):
            distribution._source_inventory(source)


def test_distribution_update_and_uninstall_preserve_owner_contract(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _source(tmp_path)
    target = project / "vendor/example-skill"
    kwargs = _install_kwargs(source, target, project)
    first = distribution.install(**kwargs)
    assert distribution.install(**kwargs) == first

    (source / "SKILL.md").write_text("# Updated\n", encoding="utf-8")
    updated = distribution.install(**{**kwargs, "source_revision": "b" * 40})
    assert updated.source_revision == "b" * 40
    removed = distribution.uninstall(target=target, project_root=project, mode="VENDORED")
    assert removed.source_revision == "b" * 40
    assert not target.exists()


def test_distribution_rejects_unowned_or_wrongly_owned_targets(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _source(tmp_path)
    target = project / "vendor/example-skill"
    target.mkdir(parents=True)
    (target / "user.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(distribution.DistributionError, match="non-empty unowned"):
        distribution.install(**_install_kwargs(source, target, project))

    target = project / "vendor/managed"
    distribution.install(**_install_kwargs(source, target, project))
    state_path = target / distribution.STATE_FILENAME
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["skill_id"] = "other"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(distribution.DistributionError, match="different skill"):
        distribution.install(**_install_kwargs(source, target, project))


def test_distribution_load_state_rejects_corrupt_ownership_records(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_path = target / distribution.STATE_FILENAME
    state_path.write_text("not-json", encoding="utf-8")
    with pytest.raises(distribution.DistributionError, match="invalid installation state"):
        distribution._load_state(target)

    state_path.write_text(json.dumps({"owned_files": []}), encoding="utf-8")
    with pytest.raises(distribution.DistributionError, match="non-empty list"):
        distribution._load_state(target)


def test_distribution_uninstall_requires_managed_state_and_matching_mode(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    unmanaged = project / "vendor/unmanaged"
    unmanaged.mkdir(parents=True)
    with pytest.raises(distribution.DistributionError, match="no managed installation state"):
        distribution.uninstall(target=unmanaged, project_root=project, mode="VENDORED")

    source = _source(tmp_path)
    target = project / "vendor/managed"
    distribution.install(**_install_kwargs(source, target, project))
    state_path = target / distribution.STATE_FILENAME
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["distribution_mode"] = "GLOBAL"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(distribution.DistributionError, match="mode does not match"):
        distribution.uninstall(target=target, project_root=project, mode="VENDORED")


@pytest.mark.parametrize("value", [-1, True, 1.5, "1", None])
def test_receipt_non_negative_integer_validation(value: object) -> None:
    with pytest.raises(receipt.VerificationReceiptError, match="non-negative integer"):
        receipt._non_negative_int(value, "field")


def _corpus(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "discovered_files": 2,
        "executed_files": 1,
        "excluded_files": [{"path": "tests/excluded.py", "reason": "hosted only"}],
        "accounted_files": 2,
        "execution_evidence": "observed",
        "completeness": "complete",
        "discovery_drift": 0,
    }
    value.update(overrides)
    return value


def test_receipt_semantics_cover_arithmetic_exclusions_and_pass_invariants() -> None:
    assert receipt.validate_receipt_semantics({}) == ["test_corpus must be an object"]
    assert "excluded_files must be an array" in receipt.validate_receipt_semantics(
        {"test_corpus": _corpus(excluded_files="bad")}
    )[0]

    findings = receipt.validate_receipt_semantics(
        {
            "verdict": "pass",
            "test_corpus": _corpus(
                discovered_files=1,
                executed_files=1,
                accounted_files=3,
                excluded_files=[
                    {"path": "tests/x.py"},
                    {"path": "tests/x.py"},
                    {},
                    "bad",
                ],
                execution_evidence="declared",
                completeness="partial",
                discovery_drift=1,
            ),
        }
    )
    assert any("duplicate test-corpus exclusion" in item for item in findings)
    assert any("entries must be objects" in item for item in findings)
    assert any("path must be non-empty" in item for item in findings)
    assert any("accounted_files must equal" in item for item in findings)
    assert any("more files" in item for item in findings)
    assert any("observed execution" in item for item in findings)
    assert any("complete test-corpus" in item for item in findings)
    assert any("zero test discovery" in item for item in findings)


def test_receipt_loader_and_validator_fail_closed_on_malformed_inputs(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    path.write_bytes(b"\xff")
    with pytest.raises(receipt.VerificationReceiptError, match="invalid UTF-8 JSON"):
        receipt._load_mapping(path)
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(receipt.VerificationReceiptError, match="root must be an object"):
        receipt._load_mapping(path)
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(receipt.VerificationReceiptError, match="exceeds"):
        receipt._read_file_bounded(path, max_bytes=1)


def test_receipt_validator_combines_schema_and_semantic_findings() -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["test_corpus"],
    }
    assert receipt.validate_receipt({"test_corpus": _corpus()}, schema=schema) == []
    findings = receipt.validate_receipt({"verdict": "pass", "test_corpus": _corpus(accounted_files=1)}, schema=schema)
    assert any("accounted_files must equal" in item for item in findings)
    assert any("every discovered file" in item for item in findings)


def test_receipt_main_reports_input_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not-json", encoding="utf-8")
    assert receipt.main([str(path)]) == 2
    assert "ERROR:" in capsys.readouterr().out


def test_state_isolation_snapshots_files_and_detects_overlap(tmp_path: Path) -> None:
    protected = tmp_path / "protected"
    protected.mkdir()
    (protected / "state.db").write_bytes(b"state")
    nested = protected / "nested"
    nested.mkdir()
    (nested / "value.txt").write_text("value", encoding="utf-8")
    snap = STATE_ISOLATION.snapshot([protected])
    assert len(snap) == 2
    STATE_ISOLATION.prove_disjoint([tmp_path / "scratch"], [protected])
    with pytest.raises(ValueError, match="overlap"):
        STATE_ISOLATION.prove_disjoint([protected / "scratch"], [protected])


def test_state_isolation_file_and_count_bounds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    protected = tmp_path / "protected"
    protected.mkdir()
    file = protected / "state.db"
    file.write_bytes(b"12")
    with monkeypatch.context() as patch:
        patch.setattr(STATE_ISOLATION, "MAX_FILE_BYTES", 1)
        with pytest.raises(ValueError, match="size bound"):
            STATE_ISOLATION.snapshot([file])
    with monkeypatch.context() as patch:
        patch.setattr(STATE_ISOLATION, "MAX_FILES", 0)
        with pytest.raises(ValueError, match="maximum file count"):
            STATE_ISOLATION.snapshot([protected])


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support required")
def test_state_isolation_rejects_symlinked_protected_state(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("state", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ValueError, match="must not be a symlink"):
        STATE_ISOLATION.snapshot([link])


def test_state_isolation_cli_snapshot_and_change_detection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    protected = tmp_path / "protected"
    protected.mkdir()
    state = protected / "state.txt"
    state.write_text("before", encoding="utf-8")
    snapshot_path = tmp_path / "snapshot.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_state_isolation.py", "snapshot", "--protected", str(protected), "--output", str(snapshot_path)],
    )
    assert STATE_ISOLATION.main() == 0
    assert '"verdict": "pass"' in capsys.readouterr().out

    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_state_isolation.py", "assert-unchanged", "--protected", str(protected), "--snapshot", str(snapshot_path)],
    )
    assert STATE_ISOLATION.main() == 0
    capsys.readouterr()

    state.write_text("after", encoding="utf-8")
    assert STATE_ISOLATION.main() == 1
    assert '"verdict": "fail"' in capsys.readouterr().out
