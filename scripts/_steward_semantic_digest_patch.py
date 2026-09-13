#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def replace_regex_once(path: str, pattern: str, replacement: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{label}: expected one regex match, found {count}")
    target.write_text(updated, encoding="utf-8")


# Generator: bind the digest to the complete reviewed semantic capability document.
generator = "skills/mcp-steward-architect/tools/generate_steward.py"
replace_once(
    generator,
    '''def _sha256(value: object) -> str:\n    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()\n\n\n''',
    '''def _sha256(value: object) -> str:\n    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()\n\n\ndef _capability_semantic_projection(capability: dict[str, Any]) -> dict[str, Any]:\n    projected = json.loads(json.dumps(capability))\n    contract = projected.get("contract")\n    if not isinstance(contract, dict):\n        raise ValueError("capability contract is required")\n    contract.pop("digest", None)\n    return projected\n\n\ndef _capability_semantic_digest(capability: dict[str, Any]) -> str:\n    return _sha256(_capability_semantic_projection(capability))\n\n\n''',
    "generator semantic digest helper",
)
replace_regex_once(
    generator,
    r'''def _upstream_document\(steward_id: str\) -> dict\[str, Any\]:\n.*?\n\n\ndef _profile_document''',
    '''def _upstream_document(steward_id: str) -> dict[str, Any]:\n    capability_id = f"{steward_id}:seed-provider-result"\n    identity = {"source": "pinned-trusted", "id": capability_id, "revision": "1"}\n    document: dict[str, Any] = {\n        "schema_version": 2,\n        "capability_id": capability_id,\n        "contract": {**identity, "digest": "sha256:" + "0" * 64},\n        "subject_types": ["target"],\n        "target_types": ["target"],\n        "identity_dimensions_observed": ["target"],\n        "evidence_classes_produced": ["provider-observation"],\n        "interaction": "stateful",\n        "delivery": "durable-async",\n        "idempotency": "provider-key",\n        "recovery": "status-by-handle",\n        "cancellation": {\n            "mode": "confirmed",\n            "delivery_model": "stateful",\n            "idempotency": "provider-key",\n            "reconciliation": "lookup-by-idempotency-key",\n            "handle_affinity": "operation",\n            "local_terminal_requires_remote_resolution": True,\n        },\n        "progress": {\n            "kind": "state-revision",\n            "stable_revision": True,\n            "wait_hint": "retry-after",\n            "worker_wait_policy": "external-maintenance",\n        },\n        "reconciliation": {"ambiguous_delivery": "lookup-by-idempotency-key"},\n        "deadline": {"application_owned": True, "transport_may_shorten": False},\n        "credential_affinity": "operation",\n        "bounds": {\n            "max_request_bytes": 65536,\n            "max_result_bytes": 65536,\n            "concurrency_scope": "target",\n            "rate_limit_scope": "provider",\n        },\n        "confidentiality": {"egress_class": "local"},\n    }\n    document["contract"]["digest"] = _capability_semantic_digest(document)\n    return document\n\n\ndef _profile_document''',
    "generator upstream document",
)
replace_once(
    generator,
    '''    local_identity = {"source": "local", "id": "local:handoff@1", "revision": "1"}\n    local_contract = {**local_identity, "digest": _sha256(local_identity)}\n''',
    '''    local_identity = {"source": "local", "id": "local:handoff@1", "revision": "1"}\n    local_capability: dict[str, Any] = {\n        "capability_id": "local:handoff@1",\n        "contract": {**local_identity, "digest": "sha256:" + "0" * 64},\n    }\n    local_capability["contract"]["digest"] = _capability_semantic_digest(local_capability)\n    local_contract = dict(local_capability["contract"])\n''',
    "generator local capability",
)

# Validator: use the same semantic projection for upstream documents and runtime admission.
validator = "skills/mcp-steward-architect/tools/validate_steward.py"
replace_once(
    validator,
    '''def compute_handoff_digest(value: dict[str, Any]) -> str:\n    unsigned = {key: item for key, item in value.items() if key != "digest"}\n    canonical = json.dumps(unsigned, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")\n    return "sha256:" + hashlib.sha256(canonical).hexdigest()\n\n\n''',
    '''def compute_handoff_digest(value: dict[str, Any]) -> str:\n    unsigned = {key: item for key, item in value.items() if key != "digest"}\n    canonical = json.dumps(unsigned, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")\n    return "sha256:" + hashlib.sha256(canonical).hexdigest()\n\n\ndef _capability_semantic_projection(value: dict[str, Any]) -> dict[str, Any]:\n    projected = json.loads(json.dumps(value))\n    contract = projected.get("contract")\n    if not isinstance(contract, dict):\n        raise ValueError("capability contract is required")\n    contract.pop("digest", None)\n    return projected\n\n\ndef compute_capability_contract_digest(value: dict[str, Any]) -> str:\n    canonical = json.dumps(\n        _capability_semantic_projection(value),\n        ensure_ascii=False,\n        separators=(",", ":"),\n        sort_keys=True,\n    ).encode("utf-8")\n    return "sha256:" + hashlib.sha256(canonical).hexdigest()\n\n\n''',
    "validator semantic digest helper",
)
replace_regex_once(
    validator,
    r'''def _upstream_findings\(value: dict\[str, Any\]\) -> list\[str\]:\n    findings: list\[str\] = \[\]\n    contract = value\["contract"\]\n    identity = \{"source": contract\["source"\], "id": contract\["id"\], "revision": contract\["revision"\]\}\n    expected_digest = \(\n        "sha256:"\n        \+ hashlib\.sha256\(\n            json\.dumps\(identity, ensure_ascii=False, separators=\(",", ":"\), sort_keys=True\)\.encode\("utf-8"\)\n        \)\.hexdigest\(\)\n    \)\n    if contract\["digest"\] != expected_digest:\n        findings\.append\("upstream: capability contract digest does not bind source/id/revision"\)''',
    '''def _upstream_findings(value: dict[str, Any]) -> list[str]:\n    findings: list[str] = []\n    contract = value["contract"]\n    expected_digest = compute_capability_contract_digest(value)\n    if contract["digest"] != expected_digest:\n        findings.append("upstream: capability contract digest does not bind complete reviewed semantic definition")''',
    "validator upstream digest",
)
replace_regex_once(
    validator,
    r'''        contract = effect\["capability_contract"\]\n        identity = \{"source": contract\["source"\], "id": contract\["id"\], "revision": contract\["revision"\]\}\n        expected = \(\n            "sha256:"\n            \+ hashlib\.sha256\(\n                json\.dumps\(identity, ensure_ascii=False, separators=\(",", ":"\), sort_keys=True\)\.encode\("utf-8"\)\n            \)\.hexdigest\(\)\n        \)\n        if contract\["id"\] != effect\["capability_ref"\] or contract\["digest"\] != expected:\n            findings\.append\(f"\{location\} capability contract must exactly bind source/id/revision/digest"\)''',
    '''        contract = effect["capability_contract"]\n        if contract["id"] != effect["capability_ref"]:\n            findings.append(f"{location} capability contract id must equal capability_ref")''',
    "validator mutation contract standalone check",
)
replace_regex_once(
    validator,
    r'''def _capability_contract_digest\(capability: dict\[str, Any\]\) -> str \| None:\n    contract = capability\.get\("contract"\)\n    if not isinstance\(contract, dict\):\n        return None\n    try:\n        identity = \{"source": contract\["source"\], "id": contract\["id"\], "revision": contract\["revision"\]\}\n    except KeyError:\n        return None\n    canonical = json\.dumps\(identity, ensure_ascii=False, separators=\(",", ":"\), sort_keys=True\)\.encode\("utf-8"\)\n    return "sha256:" \+ hashlib\.sha256\(canonical\)\.hexdigest\(\)''',
    '''def _capability_contract_digest(capability: dict[str, Any]) -> str | None:\n    contract = capability.get("contract")\n    if not isinstance(contract, dict):\n        return None\n    try:\n        return compute_capability_contract_digest(capability)\n    except (TypeError, ValueError):\n        return None''',
    "validator admission digest helper",
)

# Python generated runtime: bind the exact semantic capability, not only its identity tuple.
python_runtime = "skills/mcp-steward-architect/tools/steward-templates/python/steward_runtime.py.template"
replace_regex_once(
    python_runtime,
    r'''def _capability_digest\(capability: dict\[str, Any\]\) -> str \| None:\n    contract = capability\.get\("contract"\)\n    if not isinstance\(contract, dict\):\n        return None\n    try:\n        identity = \{"source": contract\["source"\], "id": contract\["id"\], "revision": contract\["revision"\]\}\n    except KeyError:\n        return None\n    return _digest\(identity\)''',
    '''def _capability_digest(capability: dict[str, Any]) -> str | None:\n    contract = capability.get("contract")\n    if not isinstance(contract, dict):\n        return None\n    projected = json.loads(json.dumps(capability))\n    projected_contract = projected.get("contract")\n    if not isinstance(projected_contract, dict):\n        return None\n    projected_contract.pop("digest", None)\n    return _digest(projected)''',
    "python runtime semantic digest",
)
replace_regex_once(
    python_runtime,
    r'''def _local_handoff_capability\(self\) -> dict\[str, Any\]:\n.*?\n\n    def _authority''',
    '''def _local_handoff_capability(self) -> dict[str, Any]:\n        identity = {"source": "local", "id": "local:handoff@1", "revision": "1"}\n        capability: dict[str, Any] = {\n            "capability_id": "local:handoff@1",\n            "contract": {**identity, "digest": "sha256:" + "0" * 64},\n        }\n        capability["contract"]["digest"] = _capability_digest(capability)\n        return capability\n\n    def _authority''',
    "python runtime local capability",
)

# .NET generated runtime: canonical JSON writer mirrors Python sort-key semantics and omits only contract.digest.
dotnet_runtime = "skills/mcp-steward-architect/tools/steward-templates/dotnet/StewardSeedRuntime.cs.template"
replace_regex_once(
    dotnet_runtime,
    r'''    private static string CapabilityDigest\(string source, string id, string revision\)\n    \{\n        var identity = new SortedDictionary<string, string>\(StringComparer\.Ordinal\) \{ \["id"\] = id, \["revision"\] = revision, \["source"\] = source \};\n        return "sha256:" \+ Convert\.ToHexStringLower\(SHA256\.HashData\(JsonSerializer\.SerializeToUtf8Bytes\(identity\)\)\);\n    \}''',
    '''    private static string CapabilityDigest(JsonElement capability)\n    {\n        using var stream = new MemoryStream();\n        using (var writer = new Utf8JsonWriter(stream))\n        {\n            WriteCapabilityCanonical(writer, capability, insideContract: false);\n        }\n        return "sha256:" + Convert.ToHexStringLower(SHA256.HashData(stream.ToArray()));\n    }\n\n    private static void WriteCapabilityCanonical(Utf8JsonWriter writer, JsonElement value, bool insideContract)\n    {\n        switch (value.ValueKind)\n        {\n            case JsonValueKind.Object:\n                writer.WriteStartObject();\n                foreach (var property in value.EnumerateObject().OrderBy(item => item.Name, StringComparer.Ordinal))\n                {\n                    if (insideContract && property.NameEquals("digest")) continue;\n                    writer.WritePropertyName(property.Name);\n                    WriteCapabilityCanonical(writer, property.Value, property.NameEquals("contract"));\n                }\n                writer.WriteEndObject();\n                break;\n            case JsonValueKind.Array:\n                writer.WriteStartArray();\n                foreach (var item in value.EnumerateArray()) WriteCapabilityCanonical(writer, item, insideContract: false);\n                writer.WriteEndArray();\n                break;\n            default:\n                value.WriteTo(writer);\n                break;\n        }\n    }''',
    ".NET semantic digest helper",
)
replace_once(
    dotnet_runtime,
    '''                if (!string.Equals(CapabilityDigest(pinned.Source, pinned.Id, pinned.Revision), pinned.Digest, StringComparison.Ordinal))\n                    throw new InvalidOperationException("mutation effect capability contract identity/digest is invalid");\n''',
    '''                if (!string.Equals(pinned.Id, item.GetProperty("capability_ref").GetString(), StringComparison.Ordinal))\n                    throw new InvalidOperationException("mutation effect capability contract id does not match capability_ref");\n''',
    ".NET effect contract check",
)
replace_once(
    dotnet_runtime,
    '''        if (!string.Equals(contract.GetProperty("id").GetString(), capability.Id, StringComparison.Ordinal)\n            || !string.Equals(CapabilityDigest(capability.Source, capability.Id, capability.Revision), capability.Digest, StringComparison.Ordinal))\n            throw new InvalidOperationException("reviewed upstream capability contract identity/digest is invalid");\n        var revision = proof.RootElement.GetProperty("revision").GetInt32();\n''',
    '''        if (!string.Equals(contract.GetProperty("id").GetString(), capability.Id, StringComparison.Ordinal)\n            || !string.Equals(CapabilityDigest(upstream.RootElement), capability.Digest, StringComparison.Ordinal))\n            throw new InvalidOperationException("reviewed upstream capability semantic digest is invalid");\n        foreach (var effect in effects.Values.Where(item => string.Equals(item.CapabilityRef, capability.Id, StringComparison.Ordinal)))\n            if (effect.CapabilityContract != capability)\n                throw new InvalidOperationException("mutation effect capability contract does not match reviewed semantic capability");\n        var revision = proof.RootElement.GetProperty("revision").GetInt32();\n''',
    ".NET upstream semantic validation",
)

# Standard: make digest semantics normative rather than implicit.
standard = "skills/mcp-steward-architect/STANDARD.md"
replace_once(
    standard,
    '''Every external adapter MUST expose a reviewed capability contract with explicit provenance: contract source, id, revision and digest; exact subject/target dimensions; evidence classes; stateless/stateful model; sync/durable-async delivery; idempotency; recovery/resume; submit and cancel semantics; stable progress semantics; credential affinity; bounds; rate/concurrency scope; deadline policy; and confidentiality/egress constraints.\n\nCapability truth and health are distinct.''',
    '''Every external adapter MUST expose a reviewed capability contract with explicit provenance: contract source, id, revision and digest; exact subject/target dimensions; evidence classes; stateless/stateful model; sync/durable-async delivery; idempotency; recovery/resume; submit and cancel semantics; stable progress semantics; credential affinity; bounds; rate/concurrency scope; deadline policy; and confidentiality/egress constraints.\n\nThe capability digest MUST cryptographically bind the complete reviewed semantic capability definition, not only its source/id/revision tuple. Unless a schema defines an explicit versioned semantic projection, the projection is the entire machine-readable capability document with only `contract.digest` removed; object keys are canonicalized, array order is preserved, and schema/revision fields remain included. Any behavior-significant capability change without a matching reviewed digest MUST fail closed as capability unavailable.\n\nCapability truth and health are distinct.''',
    "standard semantic digest rule",
)

# Tests: semantic drift with unchanged identity/revision must be rejected.
architect_tests = "tests/test_mcp_steward_architect.py"
replace_regex_once(
    architect_tests,
    r'''    drift = json\.loads\(json\.dumps\(docs\["steward_upstream_capability"\]\)\)\n    drift\["contract"\]\["revision"\] = "2"\n    identity = \{key: drift\["contract"\]\[key\] for key in \("source", "id", "revision"\)\}\n    import hashlib\n\n    drift\["contract"\]\["digest"\] = \(\n        "sha256:" \+ hashlib\.sha256\(json\.dumps\(identity, separators=\(",", ":"\), sort_keys=True\)\.encode\(\)\)\.hexdigest\(\)\n    \)\n    assert \(\n        validator\.evaluate_mutation_admission\(\*\*\{\*\*base, "capability": drift\}\)\["disposition"\] == "CapabilityUnavailable"\n    \)''',
    '''    drift = json.loads(json.dumps(docs["steward_upstream_capability"]))\n    drift["bounds"]["max_request_bytes"] += 1\n    assert any("semantic definition" in finding for finding in validator.validate_document("upstream", drift))\n    assert (\n        validator.evaluate_mutation_admission(**{**base, "capability": drift})["disposition"] == "CapabilityUnavailable"\n    )''',
    "semantic drift regression",
)

# Atomic conformance axes: split independent failure modes instead of hiding them in broad parent rules.
atomic = ROOT / "contracts/atomic-claim-catalog.yaml"
text = atomic.read_text(encoding="utf-8")
if "catalog_version: 1.3.0" not in text or "steward.evidence.no-overclaim" in text:
    raise SystemExit("atomic catalog version/contents are not at expected baseline")
text = text.replace("catalog_version: 1.3.0", "catalog_version: 1.4.0", 1)
text += '''  - id: steward.evidence.no-overclaim\n    parent_rule_id: steward.claim.bound\n    skill: mcp-steward-architect\n    source: skills/mcp-steward-architect/STANDARD.md#claim-binding-and-epistemic-promotion\n    description: Missing, unobserved, contradictory, or partial coverage cannot be promoted to a complete negative claim or stronger evidence authority.\n    applies_when: {maturity_at_least: L2}\n    severity: blocking\n    waivable: false\n    required_evidence: [unit, integration]\n    test_selectors: [tests/test_atomic_claim_contract.py::test_steward_v3_atomic_failure_axes_are_independent]\n  - id: steward.external.bulkheaded\n    parent_rule_id: steward.cancellation.reconciled\n    skill: mcp-steward-architect\n    source: skills/mcp-steward-architect/STANDARD.md#cancellation-and-external-wait-isolation\n    description: Reconstructable durable external waits release the primary worker and execute through bounded maintenance or reconciliation capacity that remains available for safe closure.\n    applies_when: {maturity_at_least: L2}\n    severity: blocking\n    waivable: false\n    required_evidence: [unit, integration]\n    test_selectors: [tests/test_atomic_claim_contract.py::test_steward_v3_atomic_failure_axes_are_independent]\n  - id: steward.recovery.equivalent\n    parent_rule_id: steward.persistence.authoritative\n    skill: mcp-steward-architect\n    source: skills/mcp-steward-architect/STANDARD.md#persistence-recovery-and-shutdown\n    description: Restarted and uninterrupted execution over the same durable input and external reality converge on the same canonical observations, evidence, and decisions without bypassing gates.\n    applies_when: {maturity_at_least: L2}\n    severity: blocking\n    waivable: false\n    required_evidence: [unit, integration]\n    test_selectors: [tests/test_atomic_claim_contract.py::test_steward_v3_atomic_failure_axes_are_independent]\n  - id: steward.data.canonical-sanitized\n    parent_rule_id: steward.observability.reconstructable\n    skill: mcp-steward-architect\n    source: skills/mcp-steward-architect/STANDARD.md#observability-and-diagnostics\n    description: Canonical evidence, summaries, logs, and public projections remain disclosure-bounded and cannot reintroduce protected data removed at an earlier boundary.\n    applies_when: {maturity_at_least: L2}\n    severity: blocking\n    waivable: false\n    required_evidence: [unit, security]\n    test_selectors: [tests/test_atomic_claim_contract.py::test_steward_v3_atomic_failure_axes_are_independent]\n'''
atomic.write_text(text, encoding="utf-8")

atomic_test = ROOT / "tests/test_atomic_claim_contract.py"
text = atomic_test.read_text(encoding="utf-8")
if "def test_steward_v3_atomic_failure_axes_are_independent" in text:
    raise SystemExit("atomic steward regression already exists")
text += '''\n\ndef test_steward_v3_atomic_failure_axes_are_independent() -> None:\n    controls = _controls()\n    expected_parents = {\n        "steward.evidence.no-overclaim": "steward.claim.bound",\n        "steward.external.bulkheaded": "steward.cancellation.reconciled",\n        "steward.recovery.equivalent": "steward.persistence.authoritative",\n        "steward.data.canonical-sanitized": "steward.observability.reconstructable",\n    }\n    for control_id, parent_id in expected_parents.items():\n        assert controls[control_id]["parent_rule_id"] == parent_id\n        assert controls[control_id]["severity"] == "blocking"\n        assert controls[control_id]["waivable"] is False\n    assert len({str(controls[control_id]["description"]) for control_id in expected_parents}) == len(expected_parents)\n'''
atomic_test.write_text(text, encoding="utf-8")

print("semantic capability digest + atomic Steward conformance hardening applied")
