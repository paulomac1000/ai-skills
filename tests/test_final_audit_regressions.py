"""Regressions found during the final recovery audit of PR #12."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOTNET_TEMPLATE = ROOT / "skills/mcp-server-architect/tools/dotnet-template"


def test_dotnet_http_enforces_and_executes_loopback_origin_policy() -> None:
    program = (DOTNET_TEMPLATE / "src/__NAMESPACE__.Mcp.Server/Program.cs.template").read_text(encoding="utf-8")
    smoke = (DOTNET_TEMPLATE / "tests/__NAMESPACE__.Mcp.Smoke/Program.cs.template").read_text(encoding="utf-8")

    for token in (
        'request.Headers.TryGetValue("Origin"',
        "values.Count != 1",
        "origin.Port != expectedPort",
        "IPAddress.IsLoopback",
        "StatusCodes.Status403Forbidden",
    ):
        assert token in program
    assert program.index("IsAllowedOrigin(context.Request") < program.index("Headers.Authorization")

    assert '"Origin", "https://attacker.invalid"' in smoke
    assert "foreignOriginResponse.StatusCode != HttpStatusCode.Forbidden" in smoke


def test_dotnet_tool_attributes_and_manifests_share_canonical_names() -> None:
    manifests = (DOTNET_TEMPLATE / "src/__NAMESPACE__.Mcp.Server/CapabilityManifest.cs.template").read_text(
        encoding="utf-8"
    )
    tools = (DOTNET_TEMPLATE / "src/__NAMESPACE__.Mcp.Server/Tools.cs.template").read_text(encoding="utf-8")
    smoke = (DOTNET_TEMPLATE / "tests/__NAMESPACE__.Mcp.Smoke/Program.cs.template").read_text(encoding="utf-8")

    for constant in ("DescribeCapabilities", "ListItems", "PutItem"):
        assert f"Name = CapabilityNames.{constant}" in tools
        assert f"[CapabilityNames.{constant}]" in manifests
    assert "CapabilityNames.Registered" in manifests
    assert ".SetEquals(CapabilityNames.Registered)" in manifests

    # The public-client test deliberately keeps an independent expected catalog,
    # so a broken attribute/manifest projection cannot make all checks agree.
    for public_name in ("describe_capabilities", "list_items", "put_item"):
        assert f'"{public_name}"' in smoke
