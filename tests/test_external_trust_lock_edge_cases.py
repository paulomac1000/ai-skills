"""Fail-closed external authority binding regressions."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


def _load() -> ModuleType:
    if str(CONTRACTS) not in sys.path:
        sys.path.insert(0, str(CONTRACTS))
    path = CONTRACTS / "validate_external_trust_lock.py"
    spec = importlib.util.spec_from_file_location("external_trust_lock_edge_cases", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load()
REPOSITORY = "trusted/ai-skills"
REVISION = "a" * 40
AUTHORITY_PATH = "contracts/validate_external_adoption.py"


def _write_lock(root: Path, sources: object) -> str:
    path = root / "trusted-executable-sources.lock.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "sources": sources}, sort_keys=False), encoding="utf-8")
    return path.name


def _source(*, source_id: str = "ai-skills", files: object | None = None) -> dict[str, object]:
    return {
        "id": source_id,
        "role": "auditor",
        "repository": REPOSITORY,
        "revision": REVISION,
        "credential_access": "read-only-provider",
        "files": (
            [
                {
                    "authority_path": AUTHORITY_PATH,
                    "sha256": "sha256:" + "0" * 64,
                }
            ]
            if files is None
            else files
        ),
    }


def _validate(lock: str, root: Path, authority: Path, **kwargs: object) -> list[str]:
    return VALIDATOR.validate_external_lock(
        lock,
        candidate_root=root,
        authority_root=authority,
        source_id=str(kwargs.get("source_id", "ai-skills")),
        expected_repository=str(kwargs.get("expected_repository", REPOSITORY)),
        expected_revision=str(kwargs.get("expected_revision", REVISION)),
        required_authority_paths=tuple(kwargs.get("required_authority_paths", ())),
    )


def test_external_binding_rejects_invalid_external_coordinates(tmp_path: Path) -> None:
    lock = _write_lock(tmp_path, [_source()])
    authority = tmp_path / "authority"
    authority.mkdir()

    assert _validate(lock, tmp_path, authority, expected_repository="invalid") == [
        "expected authority repository must use GitHub owner/name syntax"
    ]
    assert _validate(lock, tmp_path, authority, expected_revision="short") == [
        "expected authority revision must be a full lowercase 40-character commit SHA"
    ]


def test_external_binding_rejects_missing_or_malformed_lock(tmp_path: Path) -> None:
    authority = tmp_path / "authority"
    authority.mkdir()

    missing = _validate("missing.yaml", tmp_path, authority)
    assert missing and "missing.yaml" in missing[0]

    malformed = tmp_path / "bad.yaml"
    malformed.write_text("- not\n- an\n- object\n", encoding="utf-8")
    assert _validate(malformed.name, tmp_path, authority) == ["trusted source lock root must be an object"]

    scalar = tmp_path / "scalar.yaml"
    scalar.write_text("plain-scalar\n", encoding="utf-8")
    assert _validate(scalar.name, tmp_path, authority) == ["trusted source lock root must be an object"]


def test_external_binding_requires_sources_list_and_unique_source(tmp_path: Path) -> None:
    authority = tmp_path / "authority"
    authority.mkdir()

    no_sources = tmp_path / "no-sources.yaml"
    no_sources.write_text("schema_version: 1\nsources: null\n", encoding="utf-8")
    assert _validate(no_sources.name, tmp_path, authority) == ["candidate trust lock has no sources list"]

    none = _write_lock(tmp_path, [_source(source_id="other")])
    assert "exactly one source id 'ai-skills'" in _validate(none, tmp_path, authority)[0]

    duplicate = _write_lock(tmp_path, [_source(), _source()])
    assert "exactly one source id 'ai-skills'" in _validate(duplicate, tmp_path, authority)[0]


def test_external_binding_requires_declared_trusted_entrypoints(tmp_path: Path) -> None:
    authority = tmp_path / "authority"
    authority.mkdir()
    lock = _write_lock(tmp_path, [_source(files="not-a-list")])

    findings = _validate(
        lock,
        tmp_path,
        authority,
        required_authority_paths=(AUTHORITY_PATH, "skills/ci-cd-architect/tools/check_github_provider_controls.py"),
    )

    assert len(findings) == 2
    assert all("missing required trusted executable" in finding for finding in findings)


def test_external_binding_collects_paths_only_from_valid_file_entries(tmp_path: Path) -> None:
    authority = tmp_path / "authority"
    authority.mkdir()
    lock = _write_lock(
        tmp_path,
        [
            _source(
                files=[
                    {"authority_path": AUTHORITY_PATH, "sha256": "sha256:" + "0" * 64},
                    "ignored",
                    {"authority_path": 123, "sha256": "sha256:" + "0" * 64},
                ]
            )
        ],
    )

    findings = _validate(lock, tmp_path, authority, required_authority_paths=(AUTHORITY_PATH, "missing.py"))

    assert findings == ["source 'ai-skills' is missing required trusted executable 'missing.py'"]


def test_external_binding_delegates_matching_lock_to_authority_identity_validation(tmp_path: Path) -> None:
    authority = tmp_path / "authority"
    authority.mkdir()
    lock = _write_lock(tmp_path, [_source()])

    findings = _validate(lock, tmp_path, authority, required_authority_paths=(AUTHORITY_PATH,))

    assert any("authority checkout is not a verifiable git checkout" in finding for finding in findings)
