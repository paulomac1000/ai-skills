from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

from build_skill_bundle import BundleError, build_bundle  # noqa: E402

RELEASE_1_4_0 = "435061ad67ee36d77e01a993bc4f9e4379a29666"


def _write_consumer_repository(root: Path) -> None:
    (root / "docs").mkdir(parents=True)
    (root / "docs/architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts/ci.py").write_text("print('gate')\n", encoding="utf-8")
    (root / "AGENTS.md").write_text(
        """# AGENTS.md

These instructions apply to the repository.

## Scope and precedence

These instructions apply to the repository. Nested AGENTS.md files define inherited subtree differences.

## Commands and verification

- Focused check: `python -m pytest tests/test_service.py`
- Full gate: `python scripts/ci.py`

## Architecture boundaries

- Generated files must not be edited directly.
- When changing boundaries, read [the architecture guide](docs/architecture.md) for ownership.

## Safety boundaries

Secrets must not be committed. Destructive writes require explicit authorization and rollback.

## Definition of done

Report focused and full checks, the exact revision, skipped checks, and residual risk.
""",
        encoding="utf-8",
    )


def test_agents_manifest_declares_shared_confined_io_owner() -> None:
    manifest = yaml.safe_load(
        (ROOT / "skills/agents-md-architect/manifest.yaml").read_text(encoding="utf-8")
    )
    shared = manifest["dependencies"]["shared_resources"]
    assert shared == ["contracts/confined_io.py"]
    assert (ROOT / shared[0]).is_file()


def test_agents_bundle_contains_shared_dependency_and_runs_clean_entrypoint(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    state = build_bundle(
        repository_root=ROOT,
        skill_id="agents-md-architect",
        output=bundle,
        source_revision="test-current-revision",
    )
    paths = {item["path"] for item in state["files"]}
    assert "contracts/confined_io.py" in paths
    assert "skills/agents-md-architect/tools/audit_agents_md.py" in paths
    assert "skills/agents-md-architect/tools/audit_agents_md_impl.py" in paths

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _write_consumer_repository(consumer)
    audit = bundle / "skills/agents-md-architect/tools/audit_agents_md.py"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(audit),
            "--strict",
            "--layout",
            "monorepo",
            "--profile",
            "application",
            "--language",
            "en",
            str(consumer),
        ],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "AGENTS.md audit passed." in result.stdout


def test_bundle_fails_actionably_when_declared_shared_resource_is_missing(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    skill = repository / "skills/example-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    (skill / "STANDARD.md").write_text("# Standard\n", encoding="utf-8")
    (skill / "manifest.yaml").write_text(
        """schema_version: 1
name: example-skill
dependencies:
  shared_resources:
  - contracts/missing.py
""",
        encoding="utf-8",
    )

    with pytest.raises(BundleError, match=r"contracts/missing\.py"):
        build_bundle(
            repository_root=repository,
            skill_id="example-skill",
            output=tmp_path / "bundle",
            source_revision="deadbeef",
        )


def test_v1_4_0_investigation_is_bound_to_exact_tag_revision() -> None:
    text = (ROOT / "contracts/agents-md-confined-io-investigation.md").read_text(encoding="utf-8")
    assert RELEASE_1_4_0 in text
    assert "WRONG_CONSUMER_LAYOUT" in text
    assert "contracts/confined_io.py" in text
