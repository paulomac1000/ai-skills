"""Regressions for authority identity before provider-backed adoption policy loads."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
REPOSITORY = "trusted/ai-skills"
WORKFLOW = ".github/workflows/consumer-acceptance.yml"


def _load() -> ModuleType:
    if str(CONTRACTS) not in sys.path:
        sys.path.insert(0, str(CONTRACTS))
    path = CONTRACTS / "validate_external_adoption.py"
    spec = importlib.util.spec_from_file_location("external_adoption_authority_binding", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load()


def _authority(revision: str) -> dict[str, str]:
    return {
        "verifier_repository": REPOSITORY,
        "verifier_revision": revision,
        "claim_catalog_repository": REPOSITORY,
        "claim_catalog_revision": revision,
        "workflow_path": WORKFLOW,
    }


def _git_authority(root: Path) -> str:
    (root / "contracts").mkdir(parents=True)
    (root / "skills/example-skill").mkdir(parents=True)
    (root / "contracts/rule-catalog.yaml").write_text("schema_version: 1\nskills: {}\n", encoding="utf-8")
    (root / "contracts/atomic-claim-catalog.yaml").write_text("schema_version: 1\nclaims: {}\n", encoding="utf-8")
    (root / "contracts/adoption-assessment.schema.json").write_text("{}\n", encoding="utf-8")
    (root / "skills/example-skill/manifest.yaml").write_text("name: example-skill\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=30)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True, timeout=30)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True, timeout=30)
    subprocess.run(
        ["git", "-C", str(root), "remote", "add", "origin", f"https://github.com/{REPOSITORY}.git"],
        check=True,
        timeout=30,
    )
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, timeout=30)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "authority"], check=True, timeout=30)
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def _validate(candidate: Path, authority: Path, revision: str) -> list[object]:
    return VALIDATOR.validate_external_adoption(
        {"acceptance_authority": _authority(revision), "skill": {"name": "example-skill"}},
        candidate_root=candidate,
        authority_root=authority,
        authority_repository=REPOSITORY,
        authority_revision=revision,
        authority_workflow_path=WORKFLOW,
        token="test-token",
        as_of=date(2026, 8, 16),
    )


def test_external_adoption_verifies_checkout_before_loading_policy(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    authority = tmp_path / "authority"
    candidate.mkdir()
    authority.mkdir()

    with pytest.raises(ValueError, match="authority checkout is not a verifiable git checkout"):
        _validate(candidate, authority, "a" * 40)


def test_external_adoption_rejects_dirty_authority_catalog(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    authority = tmp_path / "authority"
    candidate.mkdir()
    revision = _git_authority(authority)
    (authority / "contracts/rule-catalog.yaml").write_text("schema_version: 1\nskills: changed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="authority checkout must be pristine at the locked revision"):
        _validate(candidate, authority, revision)


def test_external_adoption_rejects_dirty_selected_skill_manifest(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    authority = tmp_path / "authority"
    candidate.mkdir()
    revision = _git_authority(authority)
    (authority / "skills/example-skill/manifest.yaml").write_text("name: changed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="authority checkout must be pristine at the locked revision"):
        _validate(candidate, authority, revision)
