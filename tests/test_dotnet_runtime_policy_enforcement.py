"""Generated .NET runtime enforces the safety claims exported by its canonical manifest."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "skills/mcp-server-architect/tools/dotnet-template/src/__NAMESPACE__.Mcp.Server"


def test_dotnet_approval_record_binds_all_put_mutation_arguments() -> None:
    registry = (TEMPLATE / "ApprovalRegistry.cs.template").read_text(encoding="utf-8")
    kernel = (TEMPLATE / "InvocationKernel.cs.template").read_text(encoding="utf-8")

    assert "string ArgumentsDigest" in registry
    assert "PutItemDigest(string itemId, string name, int expectedVersion)" in registry
    for field in ('"itemId"', '"name"', '"expectedVersion"'):
        assert field in registry
    assert "var argumentsDigest = ApprovalArguments.PutItemDigest(itemId, name, expectedVersion);" in kernel
    assert "argumentsDigest))" in kernel


def test_dotnet_approval_binding_mismatch_does_not_consume_the_token() -> None:
    registry = (TEMPLATE / "ApprovalRegistry.cs.template").read_text(encoding="utf-8")
    consume = registry.split("public bool Consume(", 1)[1].split("private static bool FixedTimeEquals", 1)[0]

    assert "_records.TryGetValue(token, out var record)" in consume
    assert "_records.Remove(token, out record)" not in consume
    binding_check = consume.index("if (!FixedTimeEquals(record.Principal, principal)")
    successful_remove = consume.index("return _records.Remove(token);")
    assert binding_check < successful_remove
    assert "if (record.ExpiresAt <= clock.GetUtcNow())" in consume
    assert "_records.Remove(token);\n                return false;" in consume


def test_dotnet_runtime_enforces_exported_concurrency_and_queue_limits() -> None:
    canonical = (TEMPLATE / "CanonicalCapabilityManifest.cs.template").read_text(encoding="utf-8")
    gate = (TEMPLATE / "OperationGate.cs.template").read_text(encoding="utf-8")
    kernel = (TEMPLATE / "InvocationKernel.cs.template").read_text(encoding="utf-8")

    assert "manifest.ConcurrentSafe ? 32 : 1" in canonical
    assert "manifest.ConcurrentSafe ? 64 : 0" in canonical
    assert "SemaphoreSlim Semaphore { get; } = new(limit, limit)" in gate
    assert "entry.Waiting >= entry.QueueLimit" in gate
    assert '"CONCURRENCY_QUEUE_FULL"' in gate
    assert "operationGate.EnterAsync(" in kernel
    assert "concurrency.Limit" in kernel
    assert "concurrency.QueueLimit" in kernel
    assert "if (!manifest.ConcurrentSafe)" not in kernel
    assert "var limit = manifest.ConcurrentSafe ? 32 : 1;" in kernel
    assert "var queueLimit = manifest.ConcurrentSafe ? 64 : 0;" in kernel
    assert '"global" => $"{manifest.Name}:global",' in kernel
    assert '"global" => "global",' not in kernel
