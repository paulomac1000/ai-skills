#!/usr/bin/env python3
"""Add policy-boundary coverage discovered by the full repository gate; deleted before commit."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "tests/test_contract_boundary_coverage.py"
text = path.read_text(encoding="utf-8")
old = '''from contracts import validate_live_backend_test_policy
from contracts import validate_upstream_contract
'''
new = '''from contracts import validate_evidence_provider
from contracts import validate_live_backend_test_policy
from contracts import validate_skills_lock
from contracts import validate_upstream_contract
'''
if text.count(old) != 1:
    raise RuntimeError(f"coverage import anchor count: {text.count(old)}")
text = text.replace(old, new, 1)
text += r'''


def _provider_record(profile: str = "local-structural") -> dict[str, object]:
    quality = "executed-local" if profile == "local-structural" else "provider-backed-exact-sha"
    provider_kind = "local-structural" if profile == "local-structural" else "github-actions"
    return {
        "schema_version": 1,
        "profile": profile,
        "quality_level": quality,
        "provider": {"kind": provider_kind, "name": "test-provider"},
        "repository": "owner/repository",
        "revision": "a" * 40,
        "execution": {
            "id": "run-1",
            "lane": "policy-test",
            "command": "python -m pytest",
            "started_at": "2026-08-12T20:00:00Z",
        },
        "result": "passed",
        "evidence": [
            {
                "kind": "report",
                "identity": "report-1",
                "digest": "sha256:" + "b" * 64,
            }
        ],
    }


def test_evidence_provider_enforces_ceiling_escalation_and_input_guards(tmp_path: Path) -> None:
    path = tmp_path / "record.yaml"
    path.write_text(yaml.safe_dump(_provider_record()), encoding="utf-8")
    assert validate_evidence_provider.validate_record(path, target_level="L1") == []
    assert any("cannot approve L2" in item for item in validate_evidence_provider.validate_record(path, target_level="L2"))
    assert any("unknown target maturity" in item for item in validate_evidence_provider.validate_record(path, target_level="L9"))
    escalated = validate_evidence_provider.validate_record(
        path,
        target_level="L1",
        deployment_profiles=frozenset({"public-distribution"}),
    )
    assert any("requires evidence profile" in item for item in escalated)

    unknown = _provider_record()
    unknown["profile"] = "unknown-profile"
    path.write_text(yaml.safe_dump(unknown), encoding="utf-8")
    findings = validate_evidence_provider.validate_record(path, target_level="L1")
    assert any("unknown evidence profile" in item for item in findings)

    path.write_text("- not-an-object\n", encoding="utf-8")
    assert validate_evidence_provider.validate_record(path, target_level="L1")
    directory = tmp_path / "directory.yaml"
    directory.mkdir()
    assert validate_evidence_provider.validate_record(directory, target_level="L1")


def test_evidence_provider_cli_reports_findings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "record.yaml"
    path.write_text(yaml.safe_dump(_provider_record()), encoding="utf-8")
    assert validate_evidence_provider.main([str(path), "--target-level", "L2"]) == 1
    assert "evidence provider findings" in capsys.readouterr().out


def _skills_root(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "consumer"
    skill = root / "skills/demo-skill"
    skill.mkdir(parents=True)
    standard = skill / "STANDARD.md"
    standard.write_text("# Demo\n", encoding="utf-8")
    digest = validate_skills_lock._digest(standard)
    (skill / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "version": "1.3.0",
                "normative_entrypoint": "STANDARD.md",
            }
        ),
        encoding="utf-8",
    )
    return root, digest


def _skills_lock(digest: str) -> dict[str, object]:
    revision = "c" * 40
    return {
        "schema_version": 1,
        "repository": "paulomac1000/ai-skills",
        "revision": revision,
        "skills": {
            "demo-skill": {
                "version": "1.3.0",
                "revision": revision,
                "normative_entrypoint": "skills/demo-skill/STANDARD.md",
                "content_digest": digest,
            }
        },
    }


def test_skills_lock_validates_local_source_identity_and_drift(tmp_path: Path) -> None:
    root, digest = _skills_root(tmp_path)
    lock = _skills_lock(digest)
    path = tmp_path / "ai-skills.lock.yaml"
    path.write_text(yaml.safe_dump(lock), encoding="utf-8")
    assert validate_skills_lock.validate_lock(path, skills_root=root) == []

    entry = lock["skills"]["demo-skill"]
    assert isinstance(entry, dict)
    entry["version"] = "9.9.9"
    entry["revision"] = "d" * 40
    entry["content_digest"] = "sha256:" + "0" * 64
    path.write_text(yaml.safe_dump(lock), encoding="utf-8")
    findings = validate_skills_lock.validate_lock(path, skills_root=root)
    assert any("repository revision" in item for item in findings)
    assert any("local manifest" in item for item in findings)
    assert any("normative source" in item for item in findings)


def test_skills_lock_rejects_moving_refs_deprecated_names_and_bad_sources(tmp_path: Path) -> None:
    root, digest = _skills_root(tmp_path)
    lock = _skills_lock(digest)
    lock["revision"] = "main"
    lock["skills"] = {
        "mcp-architect": {
            "version": "",
            "revision": "e" * 40,
            "normative_entrypoint": "skills/other/STANDARD.md",
        }
    }
    path = tmp_path / "ai-skills.lock.yaml"
    path.write_text(yaml.safe_dump(lock), encoding="utf-8")
    findings = validate_skills_lock.validate_lock(path, skills_root=root)
    assert any("moving ref" in item for item in findings)
    assert any("deprecated or ambiguous" in item for item in findings)
    assert any("non-empty string" in item for item in findings)
    assert any("locked skill" in item for item in findings)

    for raw in ("", "../STANDARD.md", "skills\\demo-skill\\STANDARD.md", "/absolute.md"):
        with pytest.raises(ValueError):
            validate_skills_lock._safe_source(root, raw)
    with pytest.raises(ValueError, match="does not exist"):
        validate_skills_lock._safe_source(root, "skills/demo-skill/missing.md")


def test_skills_lock_cli_and_regular_file_guards(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "missing.yaml"
    assert validate_skills_lock.main([str(missing)]) == 1
    assert "skills lock findings" in capsys.readouterr().out
    directory = tmp_path / "dir"
    directory.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        validate_skills_lock._read_regular_utf8(directory, 100)
    oversized = tmp_path / "large.txt"
    oversized.write_text("abc", encoding="utf-8")
    with pytest.raises(ValueError, match="exceeds"):
        validate_skills_lock._read_regular_utf8(oversized, 1)


def test_capability_manifest_cli_exercises_multiple_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("{}\n", encoding="utf-8")
    second = tmp_path / "second.yaml"
    second.write_text("- invalid\n", encoding="utf-8")
    assert validate_capability_manifest.main([str(invalid), str(second), "--require-active"]) == 1
    output = capsys.readouterr().out
    assert "capability manifest findings" in output
    assert str(invalid) in output
'''
path.write_text(text, encoding="utf-8")
