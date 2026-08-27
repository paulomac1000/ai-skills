"""Boundary coverage for policy-critical contract readers and renderers."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

from contracts import (
    render_rule_catalog,
    validate_capability_manifest,
    validate_evidence_provider,
    validate_live_backend_test_policy,
    validate_skills_lock,
    validate_upstream_contract,
)


def test_render_rule_catalog_rejects_unsafe_source_shapes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "skills/demo/STANDARD.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Demo\n\n## Safe heading\n", encoding="utf-8")
    catalog = root / "catalog.yaml"

    def render(source_value: object) -> None:
        catalog.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "catalog_version": "1.0.0",
                    "skills": {"demo": {"rules": [{"id": "demo.rule", "source": source_value}]}},
                }
            ),
            encoding="utf-8",
        )
        render_rule_catalog.render_catalog(catalog, root)

    with pytest.raises(ValueError, match="one path and one anchor"):
        render("STANDARD.md")
    with pytest.raises(ValueError, match="belong to demo"):
        render("skills/other/STANDARD.md#safe-heading")
    with pytest.raises(ValueError, match="missing source anchor"):
        render("STANDARD.md#missing")
    render("STANDARD.md#safe-heading")


def test_render_rule_catalog_file_guards(tmp_path: Path) -> None:
    root = tmp_path
    regular = root / "a.md"
    regular.write_text("x", encoding="utf-8")
    assert render_rule_catalog._safe_regular_file(root, "a.md", 10) == regular
    with pytest.raises(ValueError, match="POSIX"):
        render_rule_catalog._safe_regular_file(root, "a\\b", 10)
    with pytest.raises(ValueError, match="inside"):
        render_rule_catalog._safe_regular_file(root, "../a.md", 10)
    with pytest.raises(ValueError, match="does not exist"):
        render_rule_catalog._safe_regular_file(root, "missing.md", 10)
    directory = root / "dir"
    directory.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        render_rule_catalog._safe_regular_file(root, "dir", 10)
    with pytest.raises(ValueError, match="exceeds"):
        render_rule_catalog._safe_regular_file(root, "a.md", 0)
    link = root / "link.md"
    try:
        link.symlink_to(regular)
    except OSError:
        return
    with pytest.raises(ValueError, match="symlink"):
        render_rule_catalog._safe_regular_file(root, "link.md", 10)


def test_capability_manifest_loader_and_semantics(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    assert validate_capability_manifest.validate_manifest(missing)
    sequence = tmp_path / "sequence.yaml"
    sequence.write_text("- not-an-object\n", encoding="utf-8")
    assert any("root must be an object" in item for item in validate_capability_manifest.validate_manifest(sequence))

    write = {
        "operation_kind": "write",
        "active_state": "inactive",
        "retryable": True,
        "idempotent": True,
        "reversible": True,
        "requires_confirmation": True,
    }
    findings = validate_capability_manifest._semantic_findings(write, require_active=True)
    assert any("only active" in item for item in findings)
    assert sum("rationale" in item for item in findings) == 3
    assert any("approval record" in item for item in findings)
    write["approval"] = {"binds": ["principal"]}
    findings = validate_capability_manifest._semantic_findings(write)
    assert any("approval.binds" in item for item in findings)


def test_new_contract_loaders_reject_invalid_shapes(tmp_path: Path) -> None:
    for module, filename in (
        (validate_upstream_contract, "upstream.yaml"),
        (validate_live_backend_test_policy, "live.yaml"),
    ):
        path = tmp_path / filename
        path.write_text("- bad\n", encoding="utf-8")
        function = module.validate_contract if hasattr(module, "validate_contract") else module.validate_policy
        assert function(path)


def test_contract_validator_mains_report_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("{}\n", encoding="utf-8")
    assert validate_upstream_contract.main([str(path)]) == 1
    assert "findings" in capsys.readouterr().out
    assert validate_live_backend_test_policy.main([str(path)]) == 1
    assert "findings" in capsys.readouterr().out


def test_render_main_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "out.json"
    output.write_text("existing", encoding="utf-8")
    with pytest.raises(SystemExit):
        render_rule_catalog.main(["--output", str(output)])


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
    assert any(
        "cannot approve L2" in item for item in validate_evidence_provider.validate_record(path, target_level="L2")
    )
    assert any(
        "unknown target maturity" in item
        for item in validate_evidence_provider.validate_record(path, target_level="L9")
    )
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


def test_rule_applicability_metadata_and_context_edges() -> None:
    from contracts import rule_applicability

    with pytest.raises(ValueError, match="unknown maturity level"):
        rule_applicability.RuleContext("L9")

    invalid = {
        "id": "demo.rule",
        "applies_when": {
            "maturity_at_least": "L9",
            "profiles_any": ["remote-http", "remote-http"],
            "profiles_all": "not-a-list",
            "capabilities_any": [""],
            "capabilities_all": [1],
            "unknown": True,
        },
        "severity": "critical",
        "waivable": "no",
        "required_evidence": ["unknown"],
    }
    findings = rule_applicability.validate_rule_metadata(invalid)
    assert any("unsupported applicability" in item for item in findings)
    assert any("invalid maturity" in item for item in findings)
    assert any("profiles_any" in item for item in findings)
    assert any("profiles_all" in item for item in findings)
    assert any("capabilities_any" in item for item in findings)
    assert any("capabilities_all" in item for item in findings)
    assert any("severity" in item for item in findings)
    assert any("waivable" in item for item in findings)
    assert any("required_evidence" in item for item in findings)
    assert rule_applicability.validate_rule_metadata({"id": "x", "applies_when": []})

    rule = {
        "id": "demo.rule",
        "applies_when": {
            "maturity_at_least": "L2",
            "profiles_any": ["remote-http"],
            "profiles_all": ["remote-http"],
            "capabilities_any": ["write"],
            "capabilities_all": ["write"],
        },
        "severity": "blocking",
        "waivable": False,
        "required_evidence": ["integration"],
    }
    assert not rule_applicability.rule_applies(rule, rule_applicability.RuleContext("L1"))
    assert not rule_applicability.rule_applies(
        rule,
        rule_applicability.RuleContext("L2", profiles=frozenset({"local-stdio"}), capabilities=frozenset({"write"})),
    )
    assert rule_applicability.rule_applies(
        rule,
        rule_applicability.RuleContext("L2", profiles=frozenset({"remote-http"}), capabilities=frozenset({"write"})),
    )


def test_expected_rules_rejects_bad_catalog_shapes_and_applies_defaults() -> None:
    from contracts import rule_applicability

    context = rule_applicability.RuleContext("L1")
    with pytest.raises(ValueError, match="unknown skill"):
        rule_applicability.expected_rules({}, "demo", context)
    with pytest.raises(ValueError, match="has no rules"):
        rule_applicability.expected_rules({"skills": {"demo": {"rules": None}}}, "demo", context)
    with pytest.raises(ValueError, match="non-mapping rule"):
        rule_applicability.expected_rules({"skills": {"demo": {"rules": ["bad"]}}}, "demo", context)

    result = rule_applicability.expected_rules(
        {"skills": {"demo": {"rules": [{"id": "demo.default"}]}}},
        "demo",
        context,
    )
    assert len(result) == 1
    assert result[0]["severity"] == "blocking"
    assert result[0]["required_evidence"] == ["unit"]


def _python_generator_impl():
    name = "boundary_generate_python_server_impl"
    module_path = (
        Path(__file__).resolve().parents[1] / "skills/mcp-server-architect/tools/generate_python_server_impl.py"
    )
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_python_generator_input_path_and_file_guards(tmp_path: Path) -> None:
    impl = _python_generator_impl()
    impl._validate_inputs("sample_server", "Sample server")
    for package in ("A", "a", "a-b", "_bad"):
        with pytest.raises(ValueError, match="package name"):
            impl._validate_inputs(package, "server")
    for server in ("", "x" * 129, "bad\x01name"):
        with pytest.raises(ValueError, match="server name"):
            impl._validate_inputs("sample_server", server)

    assert impl._safe_relative_path("src/sample.py").as_posix() == "src/sample.py"
    for raw in ("", "src\\sample.py", "/absolute.py", "../escape.py", "src/../escape.py"):
        with pytest.raises(ValueError):
            impl._safe_relative_path(raw)

    regular = tmp_path / "regular.txt"
    regular.write_text("hello", encoding="utf-8")
    assert impl._read_regular_utf8(regular) == "hello"
    with pytest.raises(ValueError, match="exceeds"):
        impl._read_regular_utf8(regular, maximum=1)
    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        impl._read_regular_utf8(directory)
    invalid = tmp_path / "invalid.txt"
    invalid.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        impl._read_regular_utf8(invalid)
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(regular)
    except OSError:
        return
    with pytest.raises(ValueError, match="symlink"):
        impl._read_regular_utf8(link)


def test_python_generator_project_validation_rejects_contract_and_artifact_drift() -> None:
    impl = _python_generator_impl()
    files = impl.project_files("sample_server", "Sample server")
    impl.validate_generated_project(files, "sample_server")

    missing = dict(files)
    missing.pop("README.md")
    with pytest.raises(ValueError, match="incomplete"):
        impl.validate_generated_project(missing, "sample_server")

    wrong_identity = dict(files)
    wrong_identity["pyproject.toml"] = files["pyproject.toml"].replace(
        'name = "sample-server"', 'name = "wrong-name"', 1
    )
    with pytest.raises(ValueError, match="package identity"):
        impl.validate_generated_project(wrong_identity, "sample_server")

    bad_python = dict(files)
    bad_python["src/sample_server/server.py"] = "def broken(:\n"
    with pytest.raises(SyntaxError):
        impl.validate_generated_project(bad_python, "sample_server")

    forbidden_ci = dict(files)
    forbidden_ci[".github/workflows/ci.yml"] += "\ncontents: write\n"
    with pytest.raises(ValueError, match="trusted-CI baseline"):
        impl.validate_generated_project(forbidden_ci, "sample_server")

    weak_ci = dict(files)
    weak_ci[".github/workflows/ci.yml"] = files[".github/workflows/ci.yml"].replace("concurrency:", "parallel-policy:")
    with pytest.raises(ValueError, match="lacks concurrency"):
        impl.validate_generated_project(weak_ci, "sample_server")

    unpinned = dict(files)
    unpinned["Dockerfile"] = files["Dockerfile"].replace("@sha256:", "# sha256:", 1)
    with pytest.raises(ValueError, match="pin its base"):
        impl.validate_generated_project(unpinned, "sample_server")

    source_rebuild = dict(files)
    source_rebuild["Dockerfile"] += "\nCOPY src /app/src\n"
    with pytest.raises(ValueError, match="must not rebuild"):
        impl.validate_generated_project(source_rebuild, "sample_server")


def test_python_generator_capability_validation_rejects_stale_invalid_duplicate_and_missing() -> None:
    impl = _python_generator_impl()
    files = impl.project_files("sample_server", "Sample server")
    prefix = "src/sample_server/capabilities/"
    manifests = sorted(path for path in files if path.startswith(prefix) and path.endswith(".json"))
    assert len(manifests) >= 2

    stale = dict(files)
    document = json.loads(stale[manifests[0]])
    document["active"] = True
    stale[manifests[0]] = json.dumps(document)
    with pytest.raises(ValueError, match="legacy field"):
        impl._validate_capabilities(stale, "sample_server")

    invalid = dict(files)
    document = json.loads(invalid[manifests[0]])
    document.pop("id")
    invalid[manifests[0]] = json.dumps(document)
    with pytest.raises(ValueError):
        impl._validate_capabilities(invalid, "sample_server")

    duplicate = dict(files)
    first = json.loads(duplicate[manifests[0]])
    second = json.loads(duplicate[manifests[1]])
    second["id"] = first["id"]
    duplicate[manifests[1]] = json.dumps(second)
    with pytest.raises(ValueError, match="duplicate generated capability id"):
        impl._validate_capabilities(duplicate, "sample_server")

    without_manifests = {path: value for path, value in files.items() if not path.startswith(prefix)}
    with pytest.raises(ValueError, match="no capability manifests"):
        impl._validate_capabilities(without_manifests, "sample_server")
