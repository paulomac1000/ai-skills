"""Negative and boundary coverage for repository adoption contracts."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
from test_adoption_contract import FakeVerifier, assessment_for, findings
from test_evidence_verifier import (
    CLAIM,
    REPORT_PATH,
    SHA,
    StubVerifier,
    make_report,
    make_zip,
    successful_fixture,
)

import contracts.evidence as evidence_module
from contracts.evidence import GitHubEvidenceVerifier
from contracts.validate_adoption import (
    Finding,
    _catalog_rules,
    _date,
    _evidence_reference,
    _identity,
    _iso_datetime,
    _load_json,
    _load_yaml,
    _mapping,
    _path_digest,
    _safe_repository_path,
    _schema_findings,
    _sequence,
    _text,
    _text_list,
)


def test_evidence_constructor_and_scalar_validators() -> None:
    with pytest.raises(ValueError, match="non-empty token"):
        GitHubEvidenceVerifier(" ")
    with pytest.raises(ValueError, match="positive"):
        GitHubEvidenceVerifier("x", timeout_seconds=0)
    verifier = GitHubEvidenceVerifier("x")
    for reference in ({}, {"repository": "owner"}, {"repository": "owner/repo/extra"}):
        with pytest.raises(ValueError, match="owner/name"):
            verifier._repository_path(reference)
    assert verifier._repository_path({"repository": "owner/repo"}) == "owner/repo"
    for value in (None, True, 0, -1, "1"):
        with pytest.raises(ValueError, match="positive integer"):
            verifier._positive_int({"id": value}, "id")
    for value in (None, " ", 1):
        with pytest.raises(ValueError, match="non-empty string"):
            verifier._required_text({"name": value}, "name")
    assert verifier._required_text({"name": " value "}, "name") == "value"
    assert "HTTP 404" in verifier._api_error(HTTPError("u", 404, "x", {}, None))
    assert "offline" in verifier._api_error(URLError("offline"))
    assert "boom" in verifier._api_error(RuntimeError("boom"))


@pytest.mark.parametrize(
    "path",
    ["", "/abs.json", "\\abs.json", "a\\b.json", "a/../b.json", "a//b.json"],
)
def test_report_path_rejects_unsafe_values(path: str) -> None:
    with pytest.raises(ValueError, match="relative POSIX"):
        GitHubEvidenceVerifier._safe_report_path(path)
    assert GitHubEvidenceVerifier._safe_report_path("evidence/report.json") == "evidence/report.json"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.blob.core.windows.net/x",
        "https://user@example.blob.core.windows.net/x",
        "https://example.invalid/x",
        "not-a-url",
    ],
)
def test_download_url_rejects_untrusted_targets(url: str) -> None:
    with pytest.raises(ValueError, match="safe HTTPS|not trusted"):
        GitHubEvidenceVerifier._validate_download_url(url)
    assert "blob.core.windows.net" in GitHubEvidenceVerifier._validate_download_url(
        "https://example.blob.core.windows.net/x?sig=y"
    )


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False

    def read(self, limit: int | None = None) -> bytes:
        return self.payload if limit is None else self.payload[:limit]

    def close(self) -> None:
        self.closed = True


class _RedirectOpener:
    def __init__(self, location: str, code: int = 302) -> None:
        self.location = location
        self.code = code

    def open(self, request, timeout):
        raise HTTPError(request.full_url, self.code, "redirect", {"Location": self.location}, None)


def test_artifact_download_uses_signed_redirect_without_api_header(monkeypatch) -> None:
    verifier = GitHubEvidenceVerifier("secret")
    archive = b"zip-bytes"
    monkeypatch.setattr(
        evidence_module,
        "build_opener",
        lambda *_: _RedirectOpener("https://x.blob.core.windows.net/a"),
    )
    captured = {}

    def fake_urlopen(request, timeout):
        captured["authorization"] = request.headers.get("Authorization")
        return _Response(archive)

    monkeypatch.setattr(evidence_module, "urlopen", fake_urlopen)
    assert verifier._download_artifact_bytes("owner/repo", 1) == archive
    assert captured["authorization"] is None
    assert verifier._download_artifact_bytes("owner/repo", 1) == archive


def test_artifact_download_rejects_nonredirect_and_oversize(monkeypatch) -> None:
    verifier = GitHubEvidenceVerifier("secret")

    class NoRedirect:
        def open(self, request, timeout):
            return _Response(b"unexpected")

    monkeypatch.setattr(evidence_module, "build_opener", lambda *_: NoRedirect())
    with pytest.raises(ValueError, match="did not return"):
        verifier._download_artifact_bytes("owner/repo", 2)

    monkeypatch.setattr(
        evidence_module,
        "build_opener",
        lambda *_: _RedirectOpener("https://x.blob.core.windows.net/a"),
    )
    monkeypatch.setattr(evidence_module, "MAX_ARCHIVE_BYTES", 3)
    monkeypatch.setattr(evidence_module, "urlopen", lambda *args, **kwargs: _Response(b"1234"))
    with pytest.raises(ValueError, match="size limit"):
        verifier._download_artifact_bytes("owner/repo", 3)


def _zip_with_entries(entries: list[tuple[zipfile.ZipInfo | str, bytes]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    return output.getvalue()


def test_report_archive_rejects_bad_missing_duplicate_symlink_and_limits(monkeypatch) -> None:
    with pytest.raises(ValueError, match="valid ZIP"):
        GitHubEvidenceVerifier._read_report(b"bad", REPORT_PATH)
    with pytest.raises(ValueError, match="does not contain"):
        GitHubEvidenceVerifier._read_report(make_zip(None), REPORT_PATH)
    with pytest.warns(UserWarning, match="Duplicate name"):
        duplicate = _zip_with_entries([(REPORT_PATH, b"{}"), (REPORT_PATH, b"{}")])
    with pytest.raises(ValueError, match="duplicate"):
        GitHubEvidenceVerifier._read_report(duplicate, REPORT_PATH)
    unsafe_entries = ["../escape", "a/../b", "a//b"]
    if os.name != "nt":
        # zipfile normalizes these names while constructing archives on Windows.
        unsafe_entries.extend(["/absolute", "a\\b"])
    for unsafe in unsafe_entries:
        with pytest.raises(ValueError, match="non-POSIX|unsafe"):
            GitHubEvidenceVerifier._read_report(
                _zip_with_entries([(unsafe, b"x"), (REPORT_PATH, b"{}")]),
                REPORT_PATH,
            )
    symlink = zipfile.ZipInfo("link")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError, match="symlink"):
        GitHubEvidenceVerifier._read_report(
            _zip_with_entries([(symlink, b"target"), (REPORT_PATH, b"{}")]),
            REPORT_PATH,
        )
    monkeypatch.setattr(evidence_module, "MAX_ARCHIVE_MEMBERS", 1)
    with pytest.raises(ValueError, match="too many"):
        GitHubEvidenceVerifier._read_report(
            _zip_with_entries([("a", b"x"), (REPORT_PATH, b"{}")]),
            REPORT_PATH,
        )
    monkeypatch.setattr(evidence_module, "MAX_ARCHIVE_MEMBERS", 1000)
    monkeypatch.setattr(evidence_module, "MAX_UNCOMPRESSED_BYTES", 1)
    with pytest.raises(ValueError, match="uncompressed"):
        GitHubEvidenceVerifier._read_report(
            _zip_with_entries([(REPORT_PATH, b"{}")]),
            REPORT_PATH,
        )


def test_claim_matching_requires_exact_mapping() -> None:
    assert not GitHubEvidenceVerifier._claim_matches({}, None)
    assert not GitHubEvidenceVerifier._claim_matches({"claims": "x"}, CLAIM)
    assert GitHubEvidenceVerifier._claim_matches({"claims": [CLAIM]}, CLAIM)


def test_action_reports_all_execution_identity_mismatches() -> None:
    reference, responses, archive = successful_fixture()
    reference = dict(reference, workflow_id=999, check_run_id=9999)
    responses = dict(responses)
    responses["/repos/owner/repository/actions/runs/100"] = {
        "head_sha": "b" * 40,
        "status": "queued",
        "conclusion": None,
        "workflow_id": 300,
        "path": ".github/workflows/other.yml",
        "name": "Other",
        "event": "push",
    }
    responses["/repos/owner/repository/actions/jobs/200"] = {
        "run_id": 999,
        "status": "completed",
        "conclusion": "failure",
        "name": "wrong",
        "check_run_url": "https://api.github.com/check-runs/2200",
    }
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    expected = (
        "head_sha",
        "not completed",
        "workflow id",
        "workflow path",
        "workflow name",
        "workflow event",
        "not part",
        "job is not",
        "job name",
        "check run",
    )
    assert all(any(fragment in error for error in errors) for fragment in expected)


def test_report_and_artifact_mismatch_paths_fail_closed() -> None:
    reference, responses, archive = successful_fixture()
    responses = dict(responses)
    responses["/repos/owner/repository/actions/artifacts/400"] = {
        "name": reference["artifact_name"],
        "expired": True,
        "digest": "sha256:" + "0" * 64,
    }
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert "artifact has no workflow_run identity" in errors
    assert "artifact is expired" in errors
    assert any("provider digest" in error for error in errors)

    bad_report = make_report(
        repository="wrong",
        revision="b" * 40,
        run_id=9,
        check_run_id=8,
        workflow_path="x",
        workflow_name="x",
        event="push",
        job_name="x",
        lane="x",
    )
    bad_archive = make_zip(bad_report)
    digest = "sha256:" + hashlib.sha256(bad_archive).hexdigest()
    reference2 = dict(
        reference,
        provider_digest=digest,
        report_digest="sha256:" + "0" * 64,
    )
    responses2 = dict(responses)
    responses2["/repos/owner/repository/actions/artifacts/400"] = {
        "name": reference2["artifact_name"],
        "expired": False,
        "digest": digest,
        "workflow_run": {"id": 100, "head_sha": SHA},
    }
    errors = StubVerifier(responses2, bad_archive).verify_action(reference2, SHA)
    assert any("report bytes" in error for error in errors)
    assert sum("evidence report" in error for error in errors) >= 6


def test_invalid_report_json_and_provider_reference_are_findings() -> None:
    reference, responses, _ = successful_fixture()
    archive = make_zip(b"not-json")
    digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    reference = dict(
        reference,
        provider_digest=digest,
        report_digest="sha256:" + hashlib.sha256(b"not-json").hexdigest(),
    )
    responses = dict(responses)
    responses["/repos/owner/repository/actions/artifacts/400"] = {
        "name": reference["artifact_name"],
        "expired": False,
        "digest": digest,
        "workflow_run": {"id": 100, "head_sha": SHA},
    }
    assert any("UTF-8 JSON" in error for error in StubVerifier(responses, archive).verify_action(reference, SHA))
    bad_reference = dict(reference, run_id="bad")
    assert any(
        "positive integer" in error for error in StubVerifier(responses, archive).verify_action(bad_reference, SHA)
    )


def test_review_rejects_missing_wrong_and_stale_identity() -> None:
    reference = {
        "repository": "owner/repository",
        "pull_request": 12,
        "review_id": 500,
        "login": "reviewer",
        "id": 600,
    }
    _, responses, archive = successful_fixture()
    cases = [
        ({"state": "APPROVED", "commit_id": SHA}, "invalid numeric identity"),
        (
            {
                "state": "CHANGES_REQUESTED",
                "commit_id": "b" * 40,
                "user": {"id": 601, "login": "other"},
            },
            "numeric identity",
        ),
    ]
    for review, fragment in cases:
        altered = dict(responses)
        altered["/repos/owner/repository/pulls/12/reviews/500"] = review
        errors = StubVerifier(altered, archive).verify_review(reference, SHA)
        assert any(fragment in error for error in errors)
    errors = StubVerifier(
        {**responses, "/repos/owner/repository/pulls/12/reviews/500": cases[1][0]},
        archive,
    ).verify_review(reference, SHA)
    assert any("login" in error for error in errors)
    assert any("APPROVED" in error for error in errors)
    assert any("revision" in error for error in errors)


def test_validation_scalar_helpers_collect_findings(tmp_path: Path) -> None:
    result: list[Finding] = []
    assert _mapping([], "x", result) == {}
    assert _sequence({}, "x", result) == []
    assert _text("", "x", result) == ""
    assert _text("REPLACE_WITH_X", "x", result) == "REPLACE_WITH_X"
    assert _text_list("x", "x", result, nonempty=True) == []
    assert _iso_datetime("bad", "x", result) is None
    assert _iso_datetime("2026-01-01T00:00:00", "x", result) is None
    assert _date("bad", "x", result) is None
    assert result
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        _load_yaml(bad_yaml)
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        _load_json(bad_json)
    assert _schema_findings({}, {"type": "object", "required": ["x"]})


def test_catalog_identity_and_evidence_helpers_reject_bad_values() -> None:
    result: list[Finding] = []
    catalog = {
        "skills": {
            "x": {
                "rules": [
                    {"id": "r", "source": "s", "description": "d"},
                    {"id": "r", "source": "s", "description": "d"},
                ]
            }
        }
    }
    assert _catalog_rules(catalog, "x", result) == {"r"}
    assert _identity({"provider": "github", "login": "u", "id": True}, "i", result)[1] == 0
    bad = {
        "provider": "other",
        "repository": "wrong/repo",
        "run_id": 0,
        "job_id": "x",
        "check_run_id": -1,
        "artifact_id": None,
        "revision": "b" * 40,
        "workflow_path": "bad",
        "workflow_name": "",
        "event": "bad",
        "job_name": "",
        "lane": "",
        "artifact_name": "",
        "provider_digest": "bad",
        "report_path": "../x",
        "report_digest": "bad",
    }
    _evidence_reference(bad, "e", result, repository="owner/repo", revision=SHA)
    assert len(result) > 10


def test_safe_repository_path_rejects_absolute_parent_and_symlink(tmp_path: Path) -> None:
    assert _safe_repository_path(tmp_path, "/abs") is None
    assert _safe_repository_path(tmp_path, "../x") is None
    assert _safe_repository_path(tmp_path, "") is None
    assert _safe_repository_path(tmp_path, "new/path") == tmp_path / "new/path"
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    assert _safe_repository_path(tmp_path, "link/x") is None


def test_directory_digest_rejects_wrong_root_and_special_entry(tmp_path: Path) -> None:
    file = tmp_path / "file"
    file.write_text("x", encoding="utf-8")
    assert _path_digest(file).startswith("sha256:")
    if hasattr(os, "mkfifo"):
        tree = tmp_path / "tree"
        tree.mkdir()
        fifo = tree / "fifo"
        os.mkfifo(fifo)
        with pytest.raises(ValueError, match="non-regular"):
            _path_digest(tree)
    link = tmp_path / "link"
    try:
        link.symlink_to(file)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    with pytest.raises(ValueError, match="symlink"):
        _path_digest(link)


def test_semantic_mutations_cover_waivers_scope_risks_and_review(tmp_path: Path) -> None:
    document, catalog, skills = assessment_for(tmp_path)
    mutations = []
    changed = json.loads(json.dumps(document))
    changed["scope"]["included"] = []
    mutations.append((changed, "at least one"))
    changed = json.loads(json.dumps(document))
    changed["compatibility_claims"]["combinations"][0]["version"] = "9"
    mutations.append((changed, "unsupported combinations"))
    changed = json.loads(json.dumps(document))
    changed["compatibility_results"] = []
    mutations.append((changed, "missing passed evidence"))
    changed = json.loads(json.dumps(document))
    changed["applicability"][0]["rule_id"] = "unknown"
    mutations.append((changed, "stable rule catalog"))
    changed = json.loads(json.dumps(document))
    changed["applicability"][0]["status"] = "deferred"
    changed["applicability"][0]["waiver_id"] = "w"
    changed["waivers"] = [
        {
            "waiver_id": "w",
            "rule_id": changed["applicability"][0]["rule_id"],
            "owner": "o",
            "rationale": "r",
            "compensating_controls": ["c"],
            "expires_at": "2020-01-01",
        }
    ]
    mutations.append((changed, "expired"))
    changed = json.loads(json.dumps(document))
    changed["residual_risks"] = [{"risk": "r", "owner": "o", "mitigation": "m", "blocking": True}]
    mutations.append((changed, "blocking residual risk"))
    changed = json.loads(json.dumps(document))
    changed["decision"]["reviewer"]["id"] = 1001
    changed["decision"]["reviewer"]["login"] = "migration-author"
    mutations.append((changed, "independent"))
    changed = json.loads(json.dumps(document))
    changed["artifact_verification"]["artifacts"][0]["digest"] = "sha256:" + "0" * 64
    mutations.append((changed, "does not match"))
    for changed, fragment in mutations:
        output = "\n".join(findings(changed, catalog, skills, tmp_path, FakeVerifier()))
        assert fragment in output


def test_mcp_extension_rejects_unknown_transport_and_missing_checks(tmp_path: Path) -> None:
    document, catalog, skills = assessment_for(
        tmp_path,
        skill_name="mcp-server-architect",
        mcp=True,
    )
    document["extensions"]["mcp"]["target_level"] = "L9"
    document["extensions"]["mcp"]["advertised_transports"].append("sse")
    document["extensions"]["mcp"]["transport_results"]["stdio"]["capability_listing"]["result"] = "failed"
    output = "\n".join(findings(document, catalog, skills, tmp_path))
    assert "must be L1" in output
    assert "unsupported transports" in output
    assert "must be passed" in output
