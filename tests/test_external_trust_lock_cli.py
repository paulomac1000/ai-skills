"""Exercise the exact external trust-lock CLI entrypoint."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


def _load() -> ModuleType:
    if str(CONTRACTS) not in sys.path:
        sys.path.insert(0, str(CONTRACTS))
    path = CONTRACTS / "validate_external_trust_lock.py"
    spec = importlib.util.spec_from_file_location("external_trust_lock_cli", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load()
REPOSITORY = "trusted/ai-skills"
REVISION = "b" * 40


def _lock(root: Path) -> Path:
    path = root / "trusted-executable-sources.lock.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "ai-skills",
                        "role": "auditor",
                        "repository": REPOSITORY,
                        "revision": REVISION,
                        "credential_access": "read-only-provider",
                        "files": [
                            {
                                "authority_path": "contracts/validate_external_adoption.py",
                                "sha256": "sha256:" + "0" * 64,
                            }
                        ],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_external_trust_lock_cli_reports_authority_identity_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lock = _lock(tmp_path)
    authority = tmp_path / "authority"
    authority.mkdir()

    result = VALIDATOR.main(
        [
            lock.name,
            "--candidate-root",
            str(tmp_path),
            "--authority-root",
            str(authority),
            "--expected-repository",
            REPOSITORY,
            "--expected-revision",
            REVISION,
            "--require-authority-path",
            "contracts/validate_external_adoption.py",
        ]
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "authority checkout is not a verifiable git checkout" in output
    assert "external trust-lock findings: 1" in output


def test_external_trust_lock_cli_fails_closed_when_root_cannot_be_resolved(tmp_path: Path) -> None:
    lock = _lock(tmp_path)
    missing = tmp_path / "missing-authority"

    with pytest.raises(SystemExit) as exc_info:
        VALIDATOR.main(
            [
                lock.name,
                "--candidate-root",
                str(tmp_path),
                "--authority-root",
                str(missing),
                "--expected-repository",
                REPOSITORY,
                "--expected-revision",
                REVISION,
            ]
        )

    assert exc_info.value.code == 2
