"""Regressions proving that the generated .NET baseline enforces its normative manifest."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "skills/mcp-server-architect/tools/dotnet-template"


def read(relative: str) -> str:
    return (TEMPLATE / relative).read_text(encoding="utf-8")


def test_dotnet_manifest_contains_every_normative_policy_axis() -> None:
    manifest = read("src/__NAMESPACE__.Mcp.Server/CapabilityManifest.cs.template")
    for token in (
        "string Version",
        "CapabilityRisk Risk",
        "SideEffectClass SideEffects",
        "ConfidentialityClass Confidentiality",
        "IdempotencyMechanism IdempotencyMechanism",
        "bool Retryable",
        "RetryConditions RetryConditions",
        "bool ConcurrentSafe",
        "string ConcurrencyScope",
        "int TimeoutMilliseconds",
        "bool RequiresConfirmation",
        "DeterminismClass Determinism",
        "LatencyClass Latency",
        "CostClass Cost",
        "ImpactClass Impact",
        "bool Reversible",
        "string TargetBinding",
        "CapabilityActiveState ActiveState",
        "IReadOnlyList<CapabilityEvidence> Evidence",
    ):
        assert token in manifest
    assert "manifest.Retryable != manifest.RetryConditions.Retryable" in manifest
    assert "RequireEvidence(manifest, \"idempotent\", manifest.Idempotent)" in manifest
    assert "RequireEvidence(manifest, \"concurrent-safe\", manifest.ConcurrentSafe)" in manifest
    assert "RequireEvidence(manifest, \"reversible\", manifest.Reversible)" in manifest
    assert "RequireEvidence(manifest, \"retryable\", manifest.Retryable)" in manifest


def test_dotnet_manifest_serializes_canonical_wire_vocabulary() -> None:
    manifest = read("src/__NAMESPACE__.Mcp.Server/CapabilityManifest.cs.template")
    for canonical in (
        "READ",
        "WRITE",
        "DESTRUCTIVE",
        "DANGEROUS",
        "SENSITIVE",
        "none",
        "idempotency_key",
        "env-dependent",
        "eventually-consistent",
        "long-running",
        "service_outage",
        "active",
        "deprecated",
    ):
        assert f'JsonStringEnumMemberName("{canonical}")' in manifest


def test_dotnet_write_defaults_remain_conservative() -> None:
    manifest = read("src/__NAMESPACE__.Mcp.Server/CapabilityManifest.cs.template")
    put_section = manifest.split("[CapabilityNames.PutItem] = new(", 1)[1].split("),\n        };", 1)[0]
    for token in (
        "CapabilityRisk.Write",
        "SideEffectClass.Write",
        "false,\n                IdempotencyMechanism.None",
        "IdempotencyMechanism.None,\n                false,\n                RetryConditions.Never",
        "false,\n                \"inventory:itemId\"",
        "ImpactClass.Persistent",
        "CapabilityActiveState.Active",
        "true,\n                Array.Empty<CapabilityEvidence>()",
    ):
        assert token in put_section


def test_dotnet_read_capabilities_do_not_claim_compensation() -> None:
    manifest = read("src/__NAMESPACE__.Mcp.Server/CapabilityManifest.cs.template")
    describe = manifest.split("[CapabilityNames.DescribeCapabilities] = new(", 1)[1].split(
        "[CapabilityNames.ListItems]", 1
    )[0]
    listed = manifest.split("[CapabilityNames.ListItems] = new(", 1)[1].split(
        "[CapabilityNames.PutItem]", 1
    )[0]
    for section in (describe, listed):
        assert "ImpactClass.None,\n                false," in section
        assert 'new("reversible"' not in section


def test_dotnet_kernel_enforces_timeout_active_state_concurrency_and_approval() -> None:
    kernel = read("src/__NAMESPACE__.Mcp.Server/InvocationKernel.cs.template")
    gate = read("src/__NAMESPACE__.Mcp.Server/OperationGate.cs.template")
    program = read("src/__NAMESPACE__.Mcp.Server/Program.cs.template")
    manifest = read("src/__NAMESPACE__.Mcp.Server/CapabilityManifest.cs.template")
    for token in (
        "RequireActive(CapabilityNames.ListItems)",
        "RequireActive(CapabilityNames.PutItem)",
        "manifest.TimeoutMilliseconds",
        "CancellationTokenSource.CreateLinkedTokenSource",
        "operationGate.EnterAsync",
        "manifest.ConcurrencyScope",
        "TIMEOUT:",
        "beforeExecution?.Invoke()",
        "if (manifest.RequiresApproval)",
        "beforeExecution: approvalGate",
    ):
        assert token in kernel
    assert "SemaphoreSlim" in gate
    assert "References" in gate
    assert "maximumKeys" in gate
    assert "AddSingleton<KeyedOperationGate>()" in program
    assert "static CapabilityRegistry()" in manifest
    assert "manifest.RequiresConfirmation && !manifest.RequiresApproval" in manifest
    assert kernel.index("if (manifest.RequiresApproval)") < kernel.index("approvals.Consume")
    assert kernel.index("Action? approvalGate = null") < kernel.index("beforeExecution: approvalGate")
    execute = kernel.split("private async ValueTask<T> ExecuteAsync", 1)[1]
    assert execute.index("operationGate.EnterAsync") < execute.index("beforeExecution?.Invoke()")


def test_dotnet_manifest_contract_matches_normative_reference() -> None:
    reference = read("../../references/capability-manifests-and-versioning.md")
    manifest = read("src/__NAMESPACE__.Mcp.Server/CapabilityManifest.cs.template")
    field_map = {
        "version": "string Version",
        "risk": "CapabilityRisk Risk",
        "side_effects": "SideEffectClass SideEffects",
        "confidentiality": "ConfidentialityClass Confidentiality",
        "idempotency_mechanism": "IdempotencyMechanism IdempotencyMechanism",
        "retryable": "bool Retryable",
        "retry_conditions": "RetryConditions RetryConditions",
        "concurrent_safe": "bool ConcurrentSafe",
        "concurrency_scope": "string ConcurrencyScope",
        "timeout_ms": "int TimeoutMilliseconds",
        "requires_confirmation": "bool RequiresConfirmation",
        "determinism": "DeterminismClass Determinism",
        "latency": "LatencyClass Latency",
        "cost": "CostClass Cost",
        "impact": "ImpactClass Impact",
        "reversible": "bool Reversible",
        "target_binding": "string TargetBinding",
        "active_state": "CapabilityActiveState ActiveState",
    }
    for normative_name, implementation_token in field_map.items():
        assert f"`{normative_name}`" in reference
        assert implementation_token in manifest
