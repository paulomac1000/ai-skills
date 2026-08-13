#!/usr/bin/env python3
"""Apply the final verified real-usage and review hardening bundle."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{relative}: expected one match, got {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


# Semantic helpers remain fail-closed even when called independently of schema validation.
replace_once(
    "contracts/validate_capability_manifest.py",
    '''            raw_binds = approval.get("binds", [])\n            binds = set(raw_binds) if isinstance(raw_binds, list) else set()\n            missing = sorted(_REQUIRED_APPROVAL_BINDINGS - binds)\n            if missing:\n                findings.append(f"approval.binds is missing {missing}")\n''',
    '''            raw_binds = approval.get("binds", [])\n            if isinstance(raw_binds, list) and all(isinstance(binding, str) for binding in raw_binds):\n                binds = set(raw_binds)\n                missing = sorted(_REQUIRED_APPROVAL_BINDINGS - binds)\n                if missing:\n                    findings.append(f"approval.binds is missing {missing}")\n''',
)

# An atomic evidence report must contain evidence checks. Profiles/capabilities remain
# allowed to be empty because non-MCP skills and capability-free contexts are valid.
schema_path = ROOT / "contracts/atomic-claim-report.schema.json"
schema = json.loads(schema_path.read_text(encoding="utf-8"))
schema["properties"]["checks"]["minItems"] = 1
schema["properties"]["residual_risks"]["items"] = {
    "additionalProperties": False,
    "properties": {
        "blocking": {"type": "boolean"},
        "mitigation": {"minLength": 1, "type": "string"},
        "owner": {"minLength": 1, "type": "string"},
        "risk": {"minLength": 1, "type": "string"},
    },
    "required": ["risk", "owner", "mitigation", "blocking"],
    "type": "object",
}
schema_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

# Contract probes receive a minimal non-secret process environment instead of an
# ever-stale credential denylist.
replace_once(
    "skills/mcp-server-architect/tools/capture_mcp_contract.py",
    '''MAX_STDOUT_BYTES = 2 * 1024 * 1024\nPROVIDER_CREDENTIALS = {\n    "GITHUB_TOKEN",\n    "GH_TOKEN",\n    "CI_JOB_TOKEN",\n    "SYSTEM_ACCESSTOKEN",\n}\n''',
    '''MAX_STDOUT_BYTES = 2 * 1024 * 1024\nALLOWED_ENVIRONMENT = {\n    "COMSPEC",\n    "LANG",\n    "LC_ALL",\n    "LC_CTYPE",\n    "PATH",\n    "PATHEXT",\n    "PYTHONHASHSEED",\n    "SYSTEMROOT",\n    "TEMP",\n    "TMP",\n    "TMPDIR",\n    "WINDIR",\n}\n''',
)
replace_once(
    "skills/mcp-server-architect/tools/capture_mcp_contract.py",
    '''    environment = dict(os.environ)\n    for name in PROVIDER_CREDENTIALS:\n        environment.pop(name, None)\n''',
    '''    environment = {name: value for name, value in os.environ.items() if name in ALLOWED_ENVIRONMENT}\n''',
)

# Public typing and legacy diagnostics describe the actual contracts they expose.
replace_once(
    "skills/mcp-server-consumer/tools/decision_engine.py",
    ''') -> Any:\n    """Infer a fail-closed profile using exact, identity-bound trusted values.\n''',
    ''') -> CapabilityProfile:\n    """Infer a fail-closed profile using exact, identity-bound trusted values.\n''',
)
replace_once(
    "skills/mcp-server-consumer/tools/decision_engine_legacy.py",
    '''        raise TypeError("trusted_policy must be TrustedCapabilityPolicy or None")\n''',
    '''        raise TypeError("trusted_policy must be _LegacyTrustedCapabilityPolicy or None")\n''',
)
replace_once(
    "skills/mcp-server-consumer/tools/decision_engine_legacy.py",
    '''        raise TypeError("trusted_contract must be TrustedCapabilityContract or None")\n''',
    '''        raise TypeError("trusted_contract must be _LegacyTrustedCapabilityContract or None")\n''',
)

# Missing platform capability is visible as a skip, never a false pass.
replace_once(
    "tests/test_real_usage_hardening.py",
    '''    try:\n        link.symlink_to(outside, target_is_directory=True)\n    except OSError:\n        return\n    with pytest.raises(ValueError, match="symlink components"):\n''',
    '''    try:\n        link.symlink_to(outside, target_is_directory=True)\n    except OSError:\n        pytest.skip("symlink creation is unavailable on this platform")\n    with pytest.raises(ValueError, match="symlink components"):\n''',
)

# The practical upstream regression now proves the specific rejected secret field.
replace_once(
    "tests/test_practical_consumer_feedback.py",
    '''    contract["observations"][0]["api_key"] = "should-never-be-recorded"\n    path.write_text(yaml.safe_dump(contract), encoding="utf-8")\n    assert validator.validate_contract(path)\n''',
    '''    contract["observations"][0]["api_key"] = "should-never-be-recorded"\n    path.write_text(yaml.safe_dump(contract), encoding="utf-8")\n    assert any("api_key" in finding for finding in validator.validate_contract(path))\n''',
)

# Environment allowlisting is tested with both provider and unrelated cloud credentials.
replace_once(
    "tests/test_consumer_driven_contract_tools.py",
    '''        "if os.environ.get('GITHUB_TOKEN'): doc['server']['name']='credential-leaked'\\n"\n        "print(json.dumps(doc))\\n",\n''',
    '''        "if os.environ.get('GITHUB_TOKEN') or os.environ.get('AWS_SECRET_ACCESS_KEY'): doc['server']['name']='credential-leaked'\\n"\n        "print(json.dumps(doc))\\n",\n''',
)
replace_once(
    "tests/test_consumer_driven_contract_tools.py",
    '''    monkeypatch.setenv("GITHUB_TOKEN", "must-not-reach-probe")\n\n    assert (\n''',
    '''    monkeypatch.setenv("GITHUB_TOKEN", "must-not-reach-probe")\n    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-reach-probe-either")\n\n    assert (\n''',
)

# Mixed timezone awareness must be a deterministic finding, never a TypeError.
replace_once(
    "tests/test_real_usage_followup_contracts.py",
    '''    base["result"]["completed_at"] = "2026-08-13T00:59:00Z"\n    path.write_text(yaml.safe_dump(base), encoding="utf-8")\n    assert any("must not precede" in finding for finding in validate_observation(path))\n''',
    '''    base["result"]["completed_at"] = "2026-08-13T00:59:00Z"\n    path.write_text(yaml.safe_dump(base), encoding="utf-8")\n    assert any("must not precede" in finding for finding in validate_observation(path))\n    base["result"]["started_at"] = "2026-08-13T01:00:00"\n    base["result"]["completed_at"] = "2026-08-13T01:01:00Z"\n    path.write_text(yaml.safe_dump(base), encoding="utf-8")\n    assert any("timezone offset" in finding for finding in validate_observation(path))\n''',
)

# Empty atomic checks are rejected at the schema boundary; the test should assert
# that boundary rather than a later semantic symptom.
replace_once(
    "tests/test_atomic_claim_contract.py",
    '''    findings = validate_report(path, repository_root=ROOT)\n    assert any("missing applicable child controls" in finding for finding in findings)\n''',
    '''    findings = validate_report(path, repository_root=ROOT)\n    assert any(finding.startswith("checks:") for finding in findings)\n''',
)

# Cover malformed approval bindings and structured residual risks directly at the
# schema/helper boundary without weakening public validation.
replace_once(
    "tests/test_atomic_claim_contract.py",
    '''from contracts.validate_capability_manifest import validate_manifest\n''',
    '''from contracts.validate_capability_manifest import _semantic_findings, validate_manifest\n''',
)
replace_once(
    "tests/test_atomic_claim_contract.py",
    '''def test_shell_boundary_adversarial_matrix_is_normative() -> None:\n''',
    '''def test_malformed_approval_bindings_do_not_crash_semantic_validation() -> None:\n    manifest = {\n        "operation_kind": "destructive",\n        "active_state": "active",\n        "requires_confirmation": True,\n        "approval": {"binds": [{}]},\n    }\n    assert _semantic_findings(manifest) == []\n\n\ndef test_atomic_report_schema_requires_checks_and_structured_residual_risks() -> None:\n    from jsonschema import Draft202012Validator\n\n    schema = json.loads((ROOT / "contracts/atomic-claim-report.schema.json").read_text(encoding="utf-8"))\n    validator = Draft202012Validator(schema)\n    report = {\n        "schema_version": 1,\n        "report_id": "schema-boundary",\n        "repository": {"name": "example/server", "revision": "1" * 40},\n        "skill": "mcp-server-architect",\n        "context": {"target_level": "L1", "profiles": [], "capabilities": []},\n        "checks": [],\n        "residual_risks": ["unowned risk"],\n    }\n    messages = [error.message for error in validator.iter_errors(report)]\n    assert any("non-empty" in message for message in messages)\n    assert any("not of type 'object'" in message for message in messages)\n\n\ndef test_shell_boundary_adversarial_matrix_is_normative() -> None:\n''',
)

# Avoid reconstructing the public-contract schema validator on every compare.
replace_once(
    "contracts/mcp_public_contract.py",
    '''import json\nfrom dataclasses import dataclass\n''',
    '''import json\nfrom dataclasses import dataclass\nfrom functools import lru_cache\n''',
)
replace_once(
    "contracts/mcp_public_contract.py",
    '''def _schema() -> dict[str, Any]:\n    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))\n\n\ndef validate_contract(document: object) -> list[str]:\n    """Return schema and cross-field findings for one public-contract snapshot."""\n    validator = Draft202012Validator(_schema())\n''',
    '''@lru_cache(maxsize=1)\ndef _validator() -> Draft202012Validator:\n    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))\n\n\ndef validate_contract(document: object) -> list[str]:\n    """Return schema and cross-field findings for one public-contract snapshot."""\n    validator = _validator()\n''',
)
