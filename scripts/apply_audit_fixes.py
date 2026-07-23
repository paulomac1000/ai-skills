#!/usr/bin/env python3
"""Apply the independently reviewed MCP fixes once and materialize lock files."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_or_verify(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if old in text:
        if text.count(old) != 1:
            raise RuntimeError(f"{relative}: expected one old fragment")
        path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        return
    if new not in text:
        raise RuntimeError(f"{relative}: neither reviewed old nor new fragment is present")


def append_once(relative: str, marker: str, content: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def apply_source_fixes() -> None:
    replace_or_verify(
        "skills/mcp-server-consumer/tools/decision_engine.py",
        """    conditions = _retry_conditions(manifest)\n    if conditions is _INVALID:\n        return True\n    if isinstance(conditions, Mapping):\n""",
        """    conditions = _retry_conditions(manifest)\n    if conditions is _INVALID:\n        return True\n    if top is True and conditions is None:\n        return True\n    if isinstance(conditions, Mapping):\n""",
    )
    replace_or_verify(
        "skills/mcp-server-consumer/tools/decision_engine.py",
        """    conditions = _retry_conditions(manifest)\n    if conditions is _INVALID:\n        return False\n    if isinstance(conditions, Mapping):\n""",
        """    conditions = _retry_conditions(manifest)\n    if conditions is _INVALID:\n        return False\n    if manifest_retryable is True and conditions is None:\n        return False\n    if isinstance(conditions, Mapping):\n""",
    )
    replace_or_verify(
        "tests/test_consumer_retry_and_annotations.py",
        """def test_retry_conditions_restrict_error_attempt_and_reconciliation() -> None:\n""",
        """def test_positive_retry_claim_requires_named_conditions() -> None:\n    engine = load_engine()\n    manifest = {\"retryable\": True}\n    assert engine.get_error_strategy(\"TIMEOUT\", manifest).retryable is False\n    assert not engine.should_retry(\n        error_code=\"TIMEOUT\",\n        attempt=0,\n        operation_idempotent=True,\n        manifest=manifest,\n    )\n\n\ndef test_retry_conditions_restrict_error_attempt_and_reconciliation() -> None:\n""",
    )

    manifest_path = (
        "skills/mcp-server-architect/tools/dotnet-template/src/"
        "__NAMESPACE__.Mcp.Server/CapabilityManifest.cs.template"
    )
    replace_or_verify(
        manifest_path,
        """                ImpactClass.None,\n                true,\n                \"process\",\n                CapabilityActiveState.Active,\n                \"inventory.read\",\n                false,\n                [\n                    new(\"idempotent\", \"generated-baseline\", \"CapabilityDiscoveryRepeated\"),\n                    new(\"concurrent-safe\", \"generated-baseline\", \"CapabilityDiscoveryConcurrent\"),\n                    new(\"reversible\", \"generated-baseline\", \"CapabilityDiscoveryHasNoSideEffect\"),\n                ]),\n""",
        """                ImpactClass.None,\n                false,\n                \"process\",\n                CapabilityActiveState.Active,\n                \"inventory.read\",\n                false,\n                [\n                    new(\"idempotent\", \"generated-baseline\", \"CapabilityDiscoveryRepeated\"),\n                    new(\"concurrent-safe\", \"generated-baseline\", \"CapabilityDiscoveryConcurrent\"),\n                ]),\n""",
    )
    replace_or_verify(
        manifest_path,
        """                ImpactClass.None,\n                true,\n                \"inventory\",\n                CapabilityActiveState.Active,\n                \"inventory.read\",\n                false,\n                [\n                    new(\"idempotent\", \"generated-baseline\", \"ListItemsRepeatedRead\"),\n                    new(\"concurrent-safe\", \"generated-baseline\", \"ListItemsConcurrentRead\"),\n                    new(\"reversible\", \"generated-baseline\", \"ListItemsHasNoMutation\"),\n                ]),\n""",
        """                ImpactClass.None,\n                false,\n                \"inventory\",\n                CapabilityActiveState.Active,\n                \"inventory.read\",\n                false,\n                [\n                    new(\"idempotent\", \"generated-baseline\", \"ListItemsRepeatedRead\"),\n                    new(\"concurrent-safe\", \"generated-baseline\", \"ListItemsConcurrentRead\"),\n                ]),\n""",
    )
    replace_or_verify(
        "tests/test_mcp_dotnet_runtime_contracts.py",
        """def test_dotnet_kernel_enforces_timeout_active_state_concurrency_and_approval() -> None:\n""",
        """def test_dotnet_read_capabilities_do_not_claim_compensation() -> None:\n    manifest = read(\"src/__NAMESPACE__.Mcp.Server/CapabilityManifest.cs.template\")\n    describe = manifest.split(\"[CapabilityNames.DescribeCapabilities] = new(\", 1)[1].split(\n        \"[CapabilityNames.ListItems]\", 1\n    )[0]\n    listed = manifest.split(\"[CapabilityNames.ListItems] = new(\", 1)[1].split(\n        \"[CapabilityNames.PutItem]\", 1\n    )[0]\n    for section in (describe, listed):\n        assert \"ImpactClass.None,\\n                false,\" in section\n        assert 'new(\"reversible\"' not in section\n\n\ndef test_dotnet_kernel_enforces_timeout_active_state_concurrency_and_approval() -> None:\n""",
    )

    replace_or_verify(
        "skills/mcp-server-architect/tools/dotnet-template/Directory.Build.props.template",
        """    <Deterministic>true</Deterministic>\n""",
        """    <Deterministic>true</Deterministic>\n    <RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>\n""",
    )
    replace_or_verify(
        "skills/mcp-server-architect/tools/dotnet-template/.github/workflows/ci.yml.template",
        """      - run: dotnet restore tests/__NAMESPACE__.Mcp.Smoke/__NAMESPACE__.Mcp.Smoke.csproj\n""",
        """      - run: dotnet restore tests/__NAMESPACE__.Mcp.Smoke/__NAMESPACE__.Mcp.Smoke.csproj --locked-mode\n""",
    )
    replace_or_verify(
        "skills/mcp-server-architect/tools/dotnet-template/README.md.template",
        """dotnet restore tests/__NAMESPACE__.Mcp.Smoke/__NAMESPACE__.Mcp.Smoke.csproj\n""",
        """dotnet restore tests/__NAMESPACE__.Mcp.Smoke/__NAMESPACE__.Mcp.Smoke.csproj --locked-mode\n""",
    )
    replace_or_verify(
        "tests/test_mcp_dotnet_generator.py",
        """        Path(\"src/Acme.Mcp.Server/Acme.Mcp.Server.csproj\"),\n""",
        """        Path(\"src/Acme.Mcp.Server/Acme.Mcp.Server.csproj\"),\n        Path(\"src/Acme.Mcp.Server/packages.lock.json\"),\n""",
    )
    replace_or_verify(
        "tests/test_mcp_dotnet_generator.py",
        """        Path(\"tests/Acme.Mcp.Smoke/Acme.Mcp.Smoke.csproj\"),\n""",
        """        Path(\"tests/Acme.Mcp.Smoke/Acme.Mcp.Smoke.csproj\"),\n        Path(\"tests/Acme.Mcp.Smoke/packages.lock.json\"),\n""",
    )
    replace_or_verify(
        "tests/test_mcp_dotnet_generator.py",
        """    packages = (target / \"Directory.Packages.props\").read_text(encoding=\"utf-8\")\n""",
        """    build_props = (target / \"Directory.Build.props\").read_text(encoding=\"utf-8\")\n    assert \"<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>\" in build_props\n\n    packages = (target / \"Directory.Packages.props\").read_text(encoding=\"utf-8\")\n""",
    )
    replace_or_verify(
        "tests/test_mcp_dotnet_generator.py",
        """    assert \"Official-client stdio smoke\" in workflow\n""",
        """    assert \"--locked-mode\" in workflow\n    assert \"Official-client stdio smoke\" in workflow\n""",
    )
    replace_or_verify(
        "tests/test_mcp_dotnet_generator.py",
        """        [\"dotnet\", \"restore\", project],\n""",
        """        [\"dotnet\", \"restore\", project, \"--locked-mode\"],\n""",
    )

    replace_or_verify(
        "skills/mcp-server-architect/tools/dotnet-template/tests/"
        "__NAMESPACE__.Mcp.Smoke/__NAMESPACE__.Mcp.Smoke.csproj.template",
        """    <ProjectReference Include=\"../../src/__NAMESPACE__.Mcp.Server/__NAMESPACE__.Mcp.Server.csproj\" ReferenceOutputAssembly=\"false\" />\n""",
        """    <ProjectReference Include=\"../../src/__NAMESPACE__.Mcp.Server/__NAMESPACE__.Mcp.Server.csproj\" />\n""",
    )
    smoke_path = (
        "skills/mcp-server-architect/tools/dotnet-template/tests/"
        "__NAMESPACE__.Mcp.Smoke/Program.cs.template"
    )
    replace_or_verify(
        smoke_path,
        """using ModelContextProtocol.Client;\n""",
        """using ModelContextProtocol;\nusing ModelContextProtocol.Client;\nusing System.Security.Claims;\nusing __NAMESPACE__.Mcp.Domain;\nusing __NAMESPACE__.Mcp.Server;\n""",
    )
    replace_or_verify(
        smoke_path,
        """if (!File.Exists(dll)) throw new FileNotFoundException(\"Server DLL not found.\", dll);\n\nif (args.Length == 2)\n""",
        """if (!File.Exists(dll)) throw new FileNotFoundException(\"Server DLL not found.\", dll);\n\nawait VerifyApprovalContractAsync();\n\nif (args.Length == 2)\n""",
    )
    append_once(
        smoke_path,
        "static async Task VerifyApprovalContractAsync()",
        """

static async Task VerifyApprovalContractAsync()
{
    var approvals = new ApprovalRegistry(TimeProvider.System);
    var kernel = new InvocationKernel(
        new InMemoryInventoryService(),
        new CapabilityRegistry(),
        approvals,
        new KeyedOperationGate(),
        new ServerSettings(false, 8000, 1_048_576, true));
    var approved = Principal("approved-principal");

    var token = approvals.Issue(
        "approved-principal", CapabilityNames.PutItem, "inventory", "gamma");
    var item = await kernel.PutAsync(
        approved, "gamma", "Gamma", 0, token, CancellationToken.None);
    if (item.Version != 1 || item.ItemId != "gamma")
        throw new InvalidOperationException("Trusted approval did not execute the intended write.");

    await ExpectApprovalFailureAsync(() => kernel.PutAsync(
        approved, "gamma", "Gamma replay", 1, token, CancellationToken.None).AsTask());

    var principalBound = approvals.Issue(
        "approved-principal", CapabilityNames.PutItem, "inventory", "delta");
    await ExpectApprovalFailureAsync(() => kernel.PutAsync(
        Principal("other-principal"), "delta", "Delta", 0, principalBound, CancellationToken.None).AsTask());

    var resourceBound = approvals.Issue(
        "approved-principal", CapabilityNames.PutItem, "inventory", "epsilon");
    await ExpectApprovalFailureAsync(() => kernel.PutAsync(
        approved, "zeta", "Zeta", 0, resourceBound, CancellationToken.None).AsTask());
}

static ClaimsPrincipal Principal(string id) => new(new ClaimsIdentity(
    [
        new Claim(ClaimTypes.NameIdentifier, id),
        new Claim(ClaimTypes.Name, id),
        new Claim("scope", "inventory.write"),
    ],
    "SmokeApproval"));

static async Task ExpectApprovalFailureAsync(Func<Task> operation)
{
    try
    {
        await operation();
    }
    catch (McpException exception) when (exception.Message.Contains("APPROVAL_INVALID", StringComparison.Ordinal))
    {
        return;
    }
    throw new InvalidOperationException("Approval binding or one-time replay was not rejected.");
}
""",
    )
    replace_or_verify(
        "tests/test_mcp_dotnet_generator.py",
        """    assert \"writesEnabled: true\" in smoke\n""",
        """    assert \"writesEnabled: true\" in smoke\n    assert \"VerifyApprovalContractAsync\" in smoke\n    assert \"approvals.Issue\" in smoke\n    assert \"other-principal\" in smoke\n""",
    )


def materialize_lock_files() -> None:
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "Locked"
        subprocess.run(
            [
                "python",
                "skills/mcp-server-architect/tools/generate_dotnet_server.py",
                str(target),
                "--namespace",
                "Locked",
                "--name",
                "Locked MCP",
            ],
            cwd=ROOT,
            check=True,
        )
        smoke = target / "tests/Locked.Mcp.Smoke/Locked.Mcp.Smoke.csproj"
        subprocess.run(["dotnet", "restore", str(smoke)], cwd=ROOT, check=True)
        copies = {
            target / "src/Locked.Mcp.Server/packages.lock.json": ROOT
            / "skills/mcp-server-architect/tools/dotnet-template/src/"
            "__NAMESPACE__.Mcp.Server/packages.lock.json.template",
            target / "tests/Locked.Mcp.Smoke/packages.lock.json": ROOT
            / "skills/mcp-server-architect/tools/dotnet-template/tests/"
            "__NAMESPACE__.Mcp.Smoke/packages.lock.json.template",
        }
        for source, destination in copies.items():
            if not source.is_file():
                raise RuntimeError(f"expected NuGet lock file was not generated: {source}")
            shutil.copyfile(source, destination)


def main() -> int:
    apply_source_fixes()
    materialize_lock_files()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
