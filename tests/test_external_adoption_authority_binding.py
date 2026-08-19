"""Regressions for immutable candidate and authority identity in provider-backed adoption."""

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
CANDIDATE_REPOSITORY = "consumer/project"
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


def _init_git_checkout(root: Path, repository: str, message: str) -> str:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=30)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True, timeout=30)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True, timeout=30)
    subprocess.run(
        ["git", "-C", str(root), "remote", "add", "origin", f"https://github.com/{repository}.git"],
        check=True,
        timeout=30,
    )
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, timeout=30)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", message],
        check=True,
        timeout=30,
    )
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def _git_authority(root: Path) -> str:
    (root / "contracts").mkdir(parents=True)
    (root / "skills/example-skill").mkdir(parents=True)
    (root / "contracts/rule-catalog.yaml").write_text("schema_version: 1\nskills: {}\n", encoding="utf-8")
    (root / "contracts/atomic-claim-catalog.yaml").write_text("schema_version: 1\nclaims: {}\n", encoding="utf-8")
    (root / "contracts/adoption-assessment.schema.json").write_text("{}\n", encoding="utf-8")
    (root / "skills/example-skill/manifest.yaml").write_text("name: example-skill\n", encoding="utf-8")
    return _init_git_checkout(root, REPOSITORY, "authority")


def _git_candidate(root: Path) -> str:
    return _init_git_checkout(root, CANDIDATE_REPOSITORY, "candidate")


def _assessment(authority_revision: str, candidate_revision: str) -> dict[str, object]:
    return {
        "acceptance_authority": _authority(authority_revision),
        "repository": {"name": CANDIDATE_REPOSITORY, "revision": candidate_revision},
        "skill": {"name": "example-skill"},
    }


def _validate(candidate: Path, candidate_revision: str, authority: Path, authority_revision: str) -> list[object]:
    return VALIDATOR.validate_external_adoption(
        _assessment(authority_revision, candidate_revision),
        candidate_root=candidate,
        candidate_repository=CANDIDATE_REPOSITORY,
        candidate_revision=candidate_revision,
        authority_root=authority,
        authority_repository=REPOSITORY,
        authority_revision=authority_revision,
        authority_workflow_path=WORKFLOW,
        token="test-token",
        as_of=date(2026, 8, 16),
    )


def test_external_adoption_verifies_checkout_before_loading_policy(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    authority = tmp_path / "authority"
    candidate_revision = _git_candidate(candidate)
    authority.mkdir()

    with pytest.raises(ValueError, match="authority checkout is not a verifiable git checkout"):
        _validate(candidate, candidate_revision, authority, "a" * 40)


def test_external_adoption_rejects_dirty_authority_catalog(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    authority = tmp_path / "authority"
    candidate_revision = _git_candidate(candidate)
    revision = _git_authority(authority)
    (authority / "contracts/rule-catalog.yaml").write_text("schema_version: 1\nskills: changed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="authority checkout must be pristine at the locked revision"):
        _validate(candidate, candidate_revision, authority, revision)


def test_external_adoption_rejects_dirty_selected_skill_manifest(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    authority = tmp_path / "authority"
    candidate_revision = _git_candidate(candidate)
    revision = _git_authority(authority)
    (authority / "skills/example-skill/manifest.yaml").write_text("name: changed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="authority checkout must be pristine at the locked revision"):
        _validate(candidate, candidate_revision, authority, revision)


def test_external_adoption_rejects_candidate_coordinate_mismatch(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    authority = tmp_path / "authority"
    candidate_revision = _git_candidate(candidate)
    authority_revision = _git_authority(authority)
    assessment = _assessment(authority_revision, "b" * 40)

    findings = VALIDATOR.validate_external_adoption(
        assessment,
        candidate_root=candidate,
        candidate_repository=CANDIDATE_REPOSITORY,
        candidate_revision=candidate_revision,
        authority_root=authority,
        authority_repository=REPOSITORY,
        authority_revision=authority_revision,
        authority_workflow_path=WORKFLOW,
        token="test-token",
        as_of=date(2026, 8, 16),
    )

    assert any(finding.location == "repository.revision" for finding in findings)


def test_external_adoption_preflights_oversized_candidate_implementation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "implementation.py").write_text("x" * 64, encoding="utf-8")
    candidate_revision = _git_candidate(candidate)
    monkeypatch.setattr(VALIDATOR, "MAX_IMPLEMENTATION_BYTES", 32)
    assessment = {
        "applicability": [
            {
                "status": "applicable",
                "implementation": [{"path": "implementation.py", "symbol": "x"}],
            }
        ]
    }

    findings = VALIDATOR._preflight_candidate_implementation_files(assessment, candidate, candidate_revision)

    assert len(findings) == 1
    assert findings[0].location == "applicability[0].implementation[0].path"
    assert findings[0].message == "implementation file exceeds 32 bytes"


def test_external_adoption_preflight_rejects_unreadable_candidate_implementation(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate_revision = _git_candidate(candidate)
    assessment = {
        "applicability": [
            {
                "status": "applicable",
                "implementation": [{"path": "missing.py", "symbol": "x"}],
            }
        ]
    }

    findings = VALIDATOR._preflight_candidate_implementation_files(assessment, candidate, candidate_revision)

    assert len(findings) == 1
    assert findings[0].location == "applicability[0].implementation[0].path"
    assert findings[0].message.startswith("implementation file cannot be read from immutable candidate Git object:")


def test_external_adoption_semantics_use_candidate_revision_not_mutable_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate"
    authority = tmp_path / "authority"
    candidate.mkdir()
    implementation = candidate / "implementation.py"
    implementation.write_bytes(b"ORIGINAL_SYMBOL = True\n")
    candidate_revision = _git_candidate(candidate)
    revision = _git_authority(authority)
    assessment = _assessment(revision, candidate_revision)
    assessment["applicability"] = [
        {
            "status": "applicable",
            "implementation": [
                {"path": "implementation.py", "symbol": "ORIGINAL_SYMBOL"},
            ],
        }
    ]
    original_preflight = VALIDATOR._preflight_candidate_implementation_files

    def preflight_then_replace(
        document: object,
        candidate_root: Path,
        observed_revision: str,
        implementation_payloads: dict[str, str] | None = None,
    ) -> list[object]:
        implementation.write_bytes(b"REPLACEMENT_ONLY = True\n")
        return original_preflight(document, candidate_root, observed_revision, implementation_payloads)

    observed: dict[str, object] = {}

    def validate_from_snapshot(*args: object, **kwargs: object) -> list[object]:
        observed.update(kwargs)
        payloads = kwargs.get("implementation_payloads")
        assert isinstance(payloads, dict)
        semantic_findings: list[object] = []
        VALIDATOR.adoption._validate_implementation(
            {"path": "implementation.py", "symbol": "ORIGINAL_SYMBOL"},
            "implementation",
            semantic_findings,
            repository_root=candidate,
            implementation_payloads=payloads,
        )
        assert semantic_findings == []
        return []

    monkeypatch.setattr(VALIDATOR, "_preflight_candidate_implementation_files", preflight_then_replace)
    monkeypatch.setattr(VALIDATOR.adoption, "validate_document", validate_from_snapshot)

    findings = VALIDATOR.validate_external_adoption(
        assessment,
        candidate_root=candidate,
        candidate_repository=CANDIDATE_REPOSITORY,
        candidate_revision=candidate_revision,
        authority_root=authority,
        authority_repository=REPOSITORY,
        authority_revision=revision,
        authority_workflow_path=WORKFLOW,
        token="test-token",
        as_of=date(2026, 8, 16),
    )

    assert findings == []
    assert observed["implementation_payloads"] == {"implementation.py": "ORIGINAL_SYMBOL = True\n"}
    assert implementation.read_bytes() == b"REPLACEMENT_ONLY = True\n"
