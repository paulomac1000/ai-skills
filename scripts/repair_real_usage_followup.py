#!/usr/bin/env python3
"""Apply reviewed fail-closed follow-ups; removed before the resulting commit."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, got {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Test identities are repository-relative and must never permit parent traversal.
for path, key_path in (
    ("contracts/atomic-claim-report.schema.json", ("properties", "results", "items", "properties", "test_case")),
    ("contracts/adoption-assessment.schema.json", ("$defs", "verification", "properties", "test_case")),
):
    target = ROOT / path
    document = json.loads(target.read_text(encoding="utf-8"))
    node = document
    for key in key_path:
        node = node[key]
    node["pattern"] = r"^(?!.*(?:^|/)[.][.](?:/|$))tests/[A-Za-z0-9_./-]+[.]py::test_[A-Za-z0-9_]+$"
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

# Canonicalize nested JSON schemas recursively and require a final (non-prerelease) version for a release gate.
replace_once(
    "contracts/mcp_public_contract.py",
    '''def normalize_contract(document: dict[str, Any]) -> dict[str, Any]:
    """Return a stable JSON representation without changing public semantics."""
''',
    '''def _normalize_schema(value: Any) -> Any:
    """Canonicalize order-insensitive JSON Schema collections recursively."""
    if isinstance(value, dict):
        normalized = {key: _normalize_schema(child) for key, child in value.items()}
        required = normalized.get("required")
        if isinstance(required, list):
            normalized["required"] = sorted(required)
        return normalized
    if isinstance(value, list):
        return [_normalize_schema(child) for child in value]
    return value


def normalize_contract(document: dict[str, Any]) -> dict[str, Any]:
    """Return a stable JSON representation without changing public semantics."""
''',
)
replace_once(
    "contracts/mcp_public_contract.py",
    '''        input_schema = tool.get("input_schema")
        if isinstance(input_schema, dict) and isinstance(input_schema.get("required"), list):
            input_schema["required"] = sorted(input_schema["required"])
        output_schema = tool.get("output_schema")
        if isinstance(output_schema, dict) and isinstance(output_schema.get("required"), list):
            output_schema["required"] = sorted(output_schema["required"])
''',
    '''        tool["input_schema"] = _normalize_schema(tool.get("input_schema", {}))
        tool["output_schema"] = _normalize_schema(tool.get("output_schema", {}))
''',
)
replace_once(
    "contracts/mcp_public_contract.py",
    '''    before_triplet = (before.major, before.minor, before.patch)
    after_triplet = (after.major, after.minor, after.patch)
''',
    '''    before_triplet = (before.major, before.minor, before.patch)
    after_triplet = (after.major, after.minor, after.patch)
    if after.prerelease:
        return False
''',
)

# Child control catalogs are JSON/YAML arrays, not arbitrary Sequences such as strings.
replace_once(
    "contracts/rule_applicability.py",
    "from collections.abc import Mapping, Sequence\n",
    "from collections.abc import Mapping\n",
)
replace_once(
    "contracts/rule_applicability.py",
    '''    raw_controls = child_catalog.get("controls", [])
    if not isinstance(raw_controls, Sequence):
        raise ValueError("atomic child-control catalog has no controls")
    children: list[Mapping[str, Any]] = []
    for raw in raw_controls:
        if not isinstance(raw, Mapping) or raw.get("skill") != skill_name:
            continue
''',
    '''    raw_controls = child_catalog.get("controls", [])
    if not isinstance(raw_controls, list):
        raise ValueError("atomic child-control catalog controls must be a list")
    children: list[Mapping[str, Any]] = []
    for raw in raw_controls:
        if not isinstance(raw, Mapping):
            raise ValueError("atomic child control must be an object")
        if raw.get("skill") != skill_name:
            continue
''',
)

# Temporal evidence must remain comparable and timezone aware even if schema-format support changes.
replace_once(
    "contracts/validate_deployment_observation.py",
    '''        if isinstance(started, str) and isinstance(completed, str):
            try:
                started_at = datetime.fromisoformat(started.replace("Z", "+00:00"))
                completed_at = datetime.fromisoformat(completed.replace("Z", "+00:00"))
            except ValueError:
                return findings
            if completed_at < started_at:
                findings.append("result.completed_at must not precede result.started_at")
''',
    '''        if isinstance(started, str) and isinstance(completed, str):
            try:
                started_text = started[:-1] + "+00:00" if started.endswith("Z") else started
                completed_text = completed[:-1] + "+00:00" if completed.endswith("Z") else completed
                started_at = datetime.fromisoformat(started_text)
                completed_at = datetime.fromisoformat(completed_text)
            except ValueError as exc:
                findings.append(f"result timestamps must be valid ISO 8601 date-times: {exc}")
            else:
                if started_at.tzinfo is None or completed_at.tzinfo is None:
                    findings.append("result timestamps must include a timezone offset")
                elif completed_at < started_at:
                    findings.append("result.completed_at must not precede result.started_at")
''',
)

# A percent-encoded colon is legal in a local path; only the raw target can declare an external URI scheme.
replace_once(
    "skills/afds-doc-writer/validate.py",
    '''        raw_path, separator, raw_fragment = destination.partition("#")
        decoded_path = unquote(raw_path)
        fragment = unquote(raw_fragment) if separator else ""
        if re.match(r"^[a-z][a-z0-9+.-]*:", decoded_path, re.I) or decoded_path.startswith("//"):
            continue
''',
    '''        raw_path, separator, raw_fragment = destination.partition("#")
        if re.match(r"^[a-z][a-z0-9+.-]*:", raw_path, re.I) or raw_path.startswith("//"):
            continue
        decoded_path = unquote(raw_path)
        fragment = unquote(raw_fragment) if separator else ""
''',
)

# Discovery must prune ignored directories before descending and bound candidates, not enumerate the whole tree first.
replace_once(
    "skills/mcp-server-architect/tools/inspect_existing_project.py",
    '''def _source_corpus(root: Path) -> tuple[str, int, int]:
    chunks: list[str] = []
    total = 0
    files = 0
    for path in sorted(root.rglob("*")):
        if files >= MAX_FILES or total >= MAX_TOTAL_BYTES:
            break
        if IGNORED_PARTS.intersection(path.parts) or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = _regular_text(path)
        if text is None:
            continue
        encoded_size = len(text.encode("utf-8"))
        if total + encoded_size > MAX_TOTAL_BYTES:
            break
        chunks.append(text)
        total += encoded_size
        files += 1
    return "\\n".join(chunks).casefold(), files, total
''',
    '''def _source_corpus(root: Path) -> tuple[str, int, int]:
    chunks: list[str] = []
    total = 0
    files = 0
    candidates = 0
    for directory, names, filenames in os.walk(root, topdown=True, followlinks=False):
        names[:] = sorted(name for name in names if name not in IGNORED_PARTS)
        base = Path(directory)
        for filename in sorted(filenames):
            candidates += 1
            if candidates > MAX_FILES * 20 or files >= MAX_FILES or total >= MAX_TOTAL_BYTES:
                return "\\n".join(chunks).casefold(), files, total
            path = base / filename
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = _regular_text(path)
            if text is None:
                continue
            encoded_size = len(text.encode("utf-8"))
            if total + encoded_size > MAX_TOTAL_BYTES:
                return "\\n".join(chunks).casefold(), files, total
            chunks.append(text)
            total += encoded_size
            files += 1
    return "\\n".join(chunks).casefold(), files, total
''',
)

# A network/materialization error is a canary finding, not an uncaught traceback that prevents report upload.
replace_once(
    "skills/mcp-server-architect/tools/check_consumer_canaries.py",
    '''        target = workspace / canary_id
        if not target.exists():
            if not materialize:
                findings.append(f"{canary_id}: workspace is missing")
                continue
            _materialize(repository, revision, target)
        discovery = inspect_repository(target)
''',
    '''        target = workspace / canary_id
        try:
            if not target.exists():
                if not materialize:
                    findings.append(f"{canary_id}: workspace is missing")
                    continue
                _materialize(repository, revision, target)
            discovery = inspect_repository(target)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            findings.append(f"{canary_id}: consumer materialization/inspection failed: {exc}")
            continue
''',
)

# Evidence text is free-form but must not embed obvious secret assignments.
replace_once(
    "contracts/validate_upstream_contract.py",
    "import json\n",
    "import json\nimport re\n",
)
replace_once(
    "contracts/validate_upstream_contract.py",
    '''SECRET_KEYS = {"token", "password", "secret", "api_key", "apikey", "credential"}
''',
    '''SECRET_KEYS = {"token", "password", "secret", "api_key", "apikey", "credential"}
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\\b(?:access[_-]?token|api[_-]?key|apikey|password|secret|credential|token)\\s*[:=]\\s*([^\\s,;&]+)"
)
SAFE_SECRET_REFERENCES = {"redacted", "<redacted>", "***", "env", "secret-ref"}
''',
)
replace_once(
    "contracts/validate_upstream_contract.py",
    '''    elif isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False
''',
    '''    elif isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    elif isinstance(value, str):
        for match in SECRET_ASSIGNMENT.finditer(value):
            secret_value = match.group(1).strip().casefold()
            if secret_value.startswith(("$", "env:", "secret-ref:")) or secret_value in SAFE_SECRET_REFERENCES:
                continue
            return True
    return False
''',
)

# Strengthen two real-use tests that previously accepted the wrong failure reason or moving revision spelling.
replace_once(
    "tests/test_practical_consumer_feedback.py",
    "import json\n",
    "import json\nimport re\n",
)
replace_once(
    "tests/test_practical_consumer_feedback.py",
    '''    contract["observations"][0]["api_key"] = "should-never-be-recorded"
    path.write_text(yaml.safe_dump(contract), encoding="utf-8")
    assert validator.validate_contract(path)
''',
    '''    contract["observations"][0]["api_key"] = "should-never-be-recorded"
    path.write_text(yaml.safe_dump(contract), encoding="utf-8")
    assert any("secret values" in finding for finding in validator.validate_contract(path))
    contract["observations"][0].pop("api_key")
    contract["observations"][0]["evidence"] = ["probe api_key=plaintext-secret"]
    path.write_text(yaml.safe_dump(contract), encoding="utf-8")
    assert any("secret values" in finding for finding in validator.validate_contract(path))
''',
)
replace_once(
    "tests/test_practical_consumer_feedback.py",
    '''    valid["mutations"]["independent_opt_ins"] = 1
    path.write_text(yaml.safe_dump(valid), encoding="utf-8")
    assert validator.validate_policy(path)
''',
    '''    valid["mutations"]["independent_opt_ins"] = 1
    path.write_text(yaml.safe_dump(valid), encoding="utf-8")
    assert any("independent_opt_ins" in finding for finding in validator.validate_policy(path))
''',
)
replace_once(
    "tests/test_practical_consumer_feedback.py",
    '''    for canary in catalog["canaries"]:
        assert len(canary["revision"]) == 40
        int(canary["revision"], 16)
        assert canary["expected"]["facts.external_upstream"] is True
''',
    '''    for canary in catalog["canaries"]:
        assert re.fullmatch(r"[0-9a-f]{40}", canary["revision"])
        assert canary["proof_level"] == "source-inspection"
        assert canary["expected"]["facts.external_upstream"] is True
''',
)

# Extra branch coverage for new field-feedback validators and the reviewed fail-closed edges.
(ROOT / "tests/test_real_usage_followup_contracts.py").write_text(
    r'''"""Fail-closed regressions for field feedback and its review follow-ups."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from contracts.mcp_public_contract import compare_contracts
from contracts.rule_applicability import RuleContext, project_applicability
from contracts.validate_consumer_feedback import validate_registry
from contracts.validate_deployment_observation import validate_observation
from contracts.validate_operational_claims import validate_claims

ROOT = Path(__file__).resolve().parents[1]


def _contract(version: str) -> dict:
    return {
        "format": "ai-skills-mcp-public-contract",
        "schema_version": 1,
        "source_revision": "a" * 40,
        "artifact_digest": "sha256:" + "b" * 64,
        "server": {"name": "sample", "version": version},
        "sdk": {"profile": "python-official-mcp", "version": "2.0.0"},
        "transports": ["stdio"],
        "authentication": {"required": False, "mechanism": "none", "target_selection": "fixed"},
        "tools": [
            {
                "name": "read",
                "input_schema": {
                    "type": "object",
                    "properties": {"nested": {"type": "object", "required": ["b", "a"], "properties": {"a": {"type": "string"}, "b": {"type": "string"}}}},
                    "required": [],
                },
                "output_schema": {"type": "object", "properties": {}, "required": []},
                "error_contract": ["INTERNAL_ERROR"],
                "pagination": "none",
                "retry_semantics": "none",
                "target_selection": "fixed",
            }
        ],
    }


def test_nested_required_order_is_not_a_breaking_change_and_prerelease_cannot_close_release_gate() -> None:
    baseline = _contract("1.0.0")
    candidate = _contract("1.0.1")
    candidate["tools"][0]["input_schema"]["properties"]["nested"]["required"] = ["a", "b"]
    result = compare_contracts(baseline, candidate)
    assert result.required_bump == "none"
    assert result.version_satisfies is True
    candidate["server"]["version"] = "1.0.1-rc.1"
    assert compare_contracts(baseline, candidate).version_satisfies is False


def test_applicability_rejects_non_list_and_non_object_child_catalogs() -> None:
    parents = {"skills": {"demo": {"rules": []}}}
    context = RuleContext("L1")
    with pytest.raises(ValueError, match="must be a list"):
        project_applicability(parents, {"controls": "not-a-list"}, "demo", context)
    with pytest.raises(ValueError, match="must be an object"):
        project_applicability(parents, {"controls": ["not-an-object"]}, "demo", context)


def test_deployment_observation_rejects_naive_and_reversed_times(tmp_path: Path) -> None:
    base = {
        "format": "ai-skills-deployment-observation",
        "schema_version": 1,
        "source_revision": "a" * 40,
        "artifact": {"identity": "sample.whl", "digest": "sha256:" + "b" * 64},
        "deployment_identity": "local-test",
        "environment_class": "live-test",
        "command": {"argv": ["probe"], "working_directory": "."},
        "result": {"status": "passed", "result_digest": "sha256:" + "c" * 64, "started_at": "2026-08-13T01:00:00Z", "completed_at": "2026-08-13T01:01:00Z"},
        "actor": {"kind": "runner", "identity": "ci"},
    }
    path = tmp_path / "observation.yaml"
    path.write_text(yaml.safe_dump(base), encoding="utf-8")
    assert validate_observation(path) == []
    base["result"]["completed_at"] = "2026-08-13T00:59:00Z"
    path.write_text(yaml.safe_dump(base), encoding="utf-8")
    assert any("must not precede" in finding for finding in validate_observation(path))


def test_field_feedback_validators_cover_schema_and_load_failures(tmp_path: Path) -> None:
    bad_registry = tmp_path / "registry.yaml"
    bad_registry.write_text("schema_version: 1\nincidents: []\n", encoding="utf-8")
    assert any("schema:" in finding for finding in validate_registry(bad_registry, repository_root=ROOT))
    missing_claims = tmp_path / "missing-claims.yaml"
    missing_claims.write_text("schema_version: 1\nclaims: []\n", encoding="utf-8")
    assert any("schema:" in finding for finding in validate_claims(missing_claims, repository_root=tmp_path))


def test_test_case_schemas_reject_parent_traversal() -> None:
    for name, node_path in (
        ("atomic-claim-report.schema.json", ("properties", "results", "items", "properties", "test_case")),
        ("adoption-assessment.schema.json", ("$defs", "verification", "properties", "test_case")),
    ):
        schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
        node = schema
        for key in node_path:
            node = node[key]
        import re
        assert re.fullmatch(node["pattern"], "tests/unit/test_ok.py::test_case")
        assert not re.fullmatch(node["pattern"], "tests/../secrets/x.py::test_case")
''',
    encoding="utf-8",
)
