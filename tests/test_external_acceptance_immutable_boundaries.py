"""Regressions for immutable provider and Git-object boundaries in final external acceptance."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.error import HTTPError

import pytest
import yaml

from contracts import rule_applicability
from contracts import validate_trusted_executable_sources as trusted_sources

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


def _external_adoption() -> ModuleType:
    if str(CONTRACTS) not in sys.path:
        sys.path.insert(0, str(CONTRACTS))
    path = CONTRACTS / "validate_external_adoption.py"
    spec = importlib.util.spec_from_file_location("external_acceptance_immutable_boundaries", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _external_trust_lock() -> ModuleType:
    if str(CONTRACTS) not in sys.path:
        sys.path.insert(0, str(CONTRACTS))
    path = CONTRACTS / "validate_external_trust_lock.py"
    spec = importlib.util.spec_from_file_location("external_trust_lock_immutable_boundaries", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_final_evidence_metadata_rejects_provider_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = _external_adoption()

    class RedirectingOpener:
        def open(self, request, *, timeout: int):
            raise HTTPError(
                request.full_url,
                301,
                "Moved Permanently",
                {"Location": "https://api.github.com/repositories/123/actions/runs/1"},
                io.BytesIO(b""),
            )

    monkeypatch.setattr(validator, "build_opener", lambda *_handlers: RedirectingOpener())
    verifier = validator._ExternalGitHubEvidenceVerifier("token")

    with pytest.raises(ValueError, match="provider metadata redirect is not accepted"):
        verifier._get_json("/repos/old/name/actions/runs/1")


def test_external_test_identity_loader_ignores_mutable_worktree_bytes(tmp_path: Path) -> None:
    repository = tmp_path / "candidate"
    tests = repository / "tests"
    tests.mkdir(parents=True)
    (tests / "contract.py").write_text("def test_mutable_only():\n    pass\n", encoding="utf-8")

    with rule_applicability.test_case_source_loader(lambda _path: "def test_locked():\n    pass\n"):
        assert rule_applicability.test_case_identity_finding(
            "tests/contract.py::test_locked",
            repository,
        ) is None
        finding = rule_applicability.test_case_identity_finding(
            "tests/contract.py::test_mutable_only",
            repository,
        )

    assert finding == "test function 'test_mutable_only' does not exist"


def test_git_object_reader_rejects_same_size_substituted_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = b"trusted"
    substituted = b"evil!!!"
    object_id = trusted_sources._git_object_digest("blob", expected)

    monkeypatch.setattr(trusted_sources, "_git", lambda *_args: str(len(substituted)))
    monkeypatch.setattr(trusted_sources, "_git_argv", lambda *_args: ["git"])
    monkeypatch.setattr(
        trusted_sources.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=substituted, stderr=b""),
    )

    with pytest.raises(ValueError, match="object bytes do not match requested object id"):
        trusted_sources._read_verified_git_object(Path("."), object_id, "blob", max_bytes=64)


def test_lock_vendored_digest_can_be_bound_to_candidate_git_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "candidate"
    repository.mkdir()
    (repository / "validator.py").write_bytes(b"mutable worktree bytes\n")
    immutable = b"locked candidate bytes\n"
    revision = "b" * 40
    document = {
        "schema_version": 1,
        "sources": [
            {
                "id": "validator",
                "role": "vendored-validator",
                "repository": "owner/trusted",
                "revision": "a" * 40,
                "credential_access": "none",
                "files": [
                    {
                        "authority_path": "validator.py",
                        "local_path": "validator.py",
                        "sha256": "sha256:" + hashlib.sha256(immutable).hexdigest(),
                    }
                ],
            }
        ],
    }

    def immutable_blob(root: Path, observed_revision: str, raw: str, *, max_bytes: int) -> bytes:
        assert root == repository.resolve()
        assert observed_revision == revision
        assert raw == "validator.py"
        assert max_bytes == trusted_sources.MAX_SOURCE_BYTES
        return immutable

    monkeypatch.setattr(trusted_sources, "_git_blob", immutable_blob)

    findings = trusted_sources.validate_document(
        document,
        repository_root=repository,
        repository_revision=revision,
    )

    assert findings == []


def test_external_trust_lock_uses_candidate_git_object_for_lock_and_vendored_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = _external_trust_lock()
    candidate = tmp_path / "candidate"
    authority = tmp_path / "authority"
    candidate.mkdir()
    authority.mkdir()
    (candidate / "trusted-executable-sources.lock.yaml").write_text("schema_version: 999\n", encoding="utf-8")
    candidate_revision = "b" * 40
    authority_revision = "a" * 40
    immutable_document = {
        "schema_version": 1,
        "sources": [
            {
                "id": "ai-skills",
                "role": "auditor",
                "repository": "trusted/ai-skills",
                "revision": authority_revision,
                "credential_access": "none",
                "files": [
                    {
                        "authority_path": "contracts/validate_external_adoption.py",
                        "local_path": "vendor/validator.py",
                        "sha256": "sha256:" + "0" * 64,
                    }
                ],
            }
        ],
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(validator.trusted_sources, "_verify_candidate_identity", lambda *_args, **_kwargs: None)

    def candidate_text(root: Path, revision: str, raw: str, *, max_bytes: int) -> str:
        assert root == candidate
        assert revision == candidate_revision
        assert raw == "trusted-executable-sources.lock.yaml"
        assert max_bytes == validator.trusted_sources.MAX_LOCK_BYTES
        return yaml.safe_dump(immutable_document, sort_keys=False)

    def capture_validation(document, **kwargs):
        captured["document"] = document
        captured.update(kwargs)
        return []

    monkeypatch.setattr(validator.trusted_sources, "_authority_text", candidate_text)
    monkeypatch.setattr(validator.trusted_lock_snapshot, "validate_document", capture_validation)

    findings = validator.validate_external_lock(
        "trusted-executable-sources.lock.yaml",
        candidate_root=candidate,
        candidate_repository="consumer/project",
        candidate_revision=candidate_revision,
        authority_root=authority,
        source_id="ai-skills",
        expected_repository="trusted/ai-skills",
        expected_revision=authority_revision,
        required_authority_paths=("contracts/validate_external_adoption.py",),
    )

    assert findings == []
    assert captured["document"] == immutable_document
    assert captured["repository_root"] == candidate
    assert captured["repository_revision"] == candidate_revision


def _provider_controls() -> ModuleType:
    tools = ROOT / "skills" / "ci-cd-architect" / "tools"
    for value in (str(tools), str(CONTRACTS)):
        if value not in sys.path:
            sys.path.insert(0, value)
    path = tools / "check_github_provider_controls.py"
    spec = importlib.util.spec_from_file_location("external_provider_controls_immutable_boundaries", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_provider_release_scope_comes_from_immutable_candidate_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider_controls()
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / ".github" / "workflows").mkdir(parents=True)
    (candidate / ".github" / "workflow-policy.yaml").write_text(
        "schema_version: 1\nworkflows: {}\n",
        encoding="utf-8",
    )
    revision = "a" * 40
    immutable = {
        ".github/workflow-policy.yaml": (
            "schema_version: 1\n"
            "workflows:\n"
            "  .github/workflows/release.yml: protected-release\n"
        ),
        ".github/workflows/release.yml": (
            "name: release\n"
            "on: workflow_dispatch\n"
            "jobs:\n"
            "  publish:\n"
            "    runs-on: ubuntu-latest\n"
            "    environment: production\n"
            "    steps: []\n"
        ),
    }

    def immutable_text(root: Path, observed_revision: str, relative: str, *, max_bytes: int) -> str:
        assert root == candidate.resolve()
        assert observed_revision == revision
        assert max_bytes > 0
        return immutable[relative]

    monkeypatch.setattr(provider.trusted_sources, "_authority_text", immutable_text)

    environments, findings = provider._release_environments(candidate, revision)

    assert findings == []
    assert environments == {"production"}


def test_provider_control_scope_binds_candidate_identity_before_api_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider_controls()
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    revision = "a" * 40
    captured: list[tuple[Path, str, str]] = []

    def verify_identity(root: Path, repository: str, observed_revision: str) -> None:
        captured.append((root, repository, observed_revision))

    class Client:
        def get(self, path: str):
            if path == "/repos/consumer/project":
                return 200, {"default_branch": "main"}, ""
            if path == "/repos/consumer/project/branches/main":
                return 200, {"protected": True}, ""
            raise AssertionError(path)

    monkeypatch.setattr(provider.trusted_sources, "_verify_candidate_identity", verify_identity)
    monkeypatch.setattr(provider, "_release_environments", lambda _root, _revision=None: (set(), []))

    findings = provider.check_provider_controls(
        candidate,
        "consumer/project",
        Client(),
        repository_revision=revision,
    )

    assert findings == []
    assert captured == [(candidate, "consumer/project", revision)]
