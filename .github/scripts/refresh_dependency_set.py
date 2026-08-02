from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_CI_REVISION = "46568f9b87e6431eb1add23514046616dfa74fbb"
SELF = ".github/scripts/refresh_dependency_set.py"
GENERATOR_IMPL = "skills/mcp-server-architect/tools/generate_python_server_impl.py"
GENERATOR_TEST = "tests/test_mcp_generator.py"
PYTHON_PROFILE = "skills/mcp-server-architect/references/python-fastmcp.md"

ACTION_UPDATES = {
    "actions/checkout": (
        "34e114876b0b11c390a56381ad16ebd13914f8d5",
        "3d3c42e5aac5ba805825da76410c181273ba90b1",
        "v7.0.1",
    ),
    "actions/setup-python": (
        "a26af69be951a213d495a4c3e4e4022e16d87065",
        "5fda3b95a4ea91299a34e894583c3862153e4b97",
        "v7.0.0",
    ),
    "actions/setup-dotnet": (
        "9a946fdbd5fb07b82b2f5a4466058b876ab72bb2",
        "a98b56852c35b8e3190ac28c8c2271da59106c68",
        "v6.0.0",
    ),
}

PACKAGE_UPDATES = {
    "mcp==1.28.1": "mcp==2.0.0",
    "mcp>=1.27.2,<2": "mcp>=2.0.0,<3",
    "mcp>=1.28.1,<2": "mcp>=2.0.0,<3",
    "ruff==0.15.22": "ruff==0.16.0",
    "types-PyYAML==6.0.12.20260518": "types-PyYAML==6.0.12.20260724",
}

VERSION_COMMENT = re.compile(r"#\s*v?\d+(?:\.\d+){0,2}\s*$")
ACTION_REFERENCE = re.compile(
    r"(?P<action>actions/(?:checkout|setup-python|setup-dotnet))@(?P<revision>[^\s#\"']+)"
)
TEXT_SUFFIXES = {".in", ".j2", ".json", ".md", ".py", ".template", ".toml", ".yaml", ".yml"}


def tracked_files() -> list[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [item.decode("utf-8") for item in output.split(b"\0") if item]


def restore_production_ci() -> None:
    if os.environ.get("RESTORE_PRODUCTION_CI") != "1":
        return
    content = subprocess.check_output(
        ["git", "show", f"{PRODUCTION_CI_REVISION}:.github/workflows/ci.yml"],
        cwd=ROOT,
    )
    (ROOT / ".github/workflows/ci.yml").write_bytes(content)


def replace_action_reference(match: re.Match[str]) -> str:
    action = match.group("action")
    new_sha = ACTION_UPDATES[action][1]
    return f"{action}@{new_sha}"


def replace_required(text: str, old: str, new: str, *, path: str) -> str:
    if old not in text:
        raise RuntimeError(f"expected migration source not found in {path}: {old!r}")
    return text.replace(old, new)


def migrate_generator_impl(text: str) -> str:
    path = GENERATOR_IMPL
    replacements = (
        (
            "from mcp.server.fastmcp import Context, FastMCP",
            "from mcp.server.mcpserver import Context, MCPServer",
        ),
        (
            "from mcp.server.fastmcp.exceptions import ToolError",
            "from mcp.server.mcpserver.exceptions import ToolError",
        ),
        ("            from mcp.server.session import ServerSession\n", ""),
        (
            "def build_server(settings: Settings | None = None, approvals: ApprovalRegistry | None = None) -> FastMCP:",
            "def build_server(settings: Settings | None = None, approvals: ApprovalRegistry | None = None) -> MCPServer[AppContext]:",
        ),
        (
            "async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:",
            "async def lifespan(_server: MCPServer[AppContext]) -> AsyncIterator[AppContext]:",
        ),
        ("                mcp = FastMCP(\n", "                mcp = MCPServer(\n"),
        (
            "                    lifespan=lifespan,\n                    host=settings.host,\n                    port=settings.port,\n                    stateless_http=True,\n                    json_response=True,\n",
            "                    version=\"0.1.0\",\n                    lifespan=lifespan,\n",
        ),
        ("Context[ServerSession, AppContext]", "Context[AppContext]"),
        (
            "async def capability_catalog(ctx: Context[AppContext]) -> str:",
            "async def capability_catalog(ctx: Context) -> str:",
        ),
        (
            "async def readiness(ctx: Context[AppContext]) -> str:",
            "async def readiness(ctx: Context) -> str:",
        ),
        (
            "def build_http_app(server: FastMCP, settings: Settings) -> RequestBodyLimitMiddleware:",
            "def build_http_app(server: MCPServer[AppContext], settings: Settings) -> RequestBodyLimitMiddleware:",
        ),
        (
            "return RequestBodyLimitMiddleware(server.streamable_http_app(), settings.max_request_body_bytes)",
            "return RequestBodyLimitMiddleware(\n"
            "                    server.streamable_http_app(\n"
            "                        host=settings.host,\n"
            "                        json_response=True,\n"
            "                        stateless_http=True,\n"
            "                        max_request_body_size=settings.max_request_body_bytes,\n"
            "                    ),\n"
            "                    settings.max_request_body_bytes,\n"
            "                )",
        ),
        (
            "from mcp.shared.memory import create_connected_server_and_client_session",
            "from mcp.client import Client",
        ),
        (
            "async with create_connected_server_and_client_session(server, raise_exceptions=True) as session:",
            "async with Client(server, raise_exceptions=True) as client:",
        ),
        ("listed = await session.list_tools()", "listed = await client.list_tools()"),
        ("tool.inputSchema", "tool.input_schema"),
        ("result = await session.call_tool", "result = await client.call_tool"),
        ("result.isError", "result.is_error"),
        ("result.structuredContent", "result.structured_content"),
    )
    for old, new in replacements:
        text = replace_required(text, old, new, path=path)
    return text


def migrate_generator_test(text: str) -> str:
    path = GENERATOR_TEST
    replacements = (
        (
            '"from mcp.server.fastmcp import Context, FastMCP",',
            '"from mcp.server.mcpserver import Context, MCPServer",',
        ),
        (
            '"server.streamable_http_app()",',
            '"server.streamable_http_app(",\n        "max_request_body_size=settings.max_request_body_bytes",',
        ),
        ('        "max_request_body_size=",\n', ""),
    )
    for old, new in replacements:
        text = replace_required(text, old, new, path=path)
    return text


def migrate_python_profile(text: str) -> str:
    path = PYTHON_PROFILE
    replacements = (
        (
            "description: Python MCP implementation profile with generation, configuration, lifecycle, invocation-kernel, transport, manifest, concurrency, artifact, browser, and SDK-upgrade controls.",
            "description: Python MCP SDK v2 implementation profile with generation, configuration, lifecycle, invocation-kernel, transport, manifest, concurrency, artifact, browser, and SDK-upgrade controls.",
        ),
        ("# Python and FastMCP profile", "# Python official MCP SDK profile"),
        (
            "The repository CI installs the pinned stable SDK, generates a fresh project, compiles it, and runs its own suite through `mcp.shared.memory.create_connected_server_and_client_session`.",
            "The repository CI installs the pinned stable SDK, generates a fresh project, compiles it, and runs its own suite through the official in-process `mcp.client.Client`.",
        ),
        (
            "For production, use the stable official SDK line with an upper bound that excludes the next major until migration is complete. The generated baseline uses `mcp>=1.27.2,<2`, while repository verification uses an exact stable pin. While official SDK v2 is pre-release, it belongs to a separate experimental CI lane with an exact pin and cannot define the production artifact. A candidate major becomes production-supported only after registration, lifecycle, transport, policy parity, content, cancellation, and artifact matrices pass.",
            "For production, use the stable official SDK v2 line with an upper bound that excludes the next major until a reviewed migration is complete. The generated baseline uses `mcp>=2.0.0,<3`, while repository verification uses the exact `mcp==2.0.0` pin. The v1 maintenance line is not the generated production baseline. Any later major becomes production-supported only after registration, lifecycle, transport, policy parity, content, cancellation, and artifact matrices pass.",
        ),
    )
    for old, new in replacements:
        text = replace_required(text, old, new, path=path)
    return text


def transform_text(relative: str, original: str) -> str:
    updated = "".join(
        VERSION_COMMENT.sub(f"# {ACTION_UPDATES[action][2]}", ACTION_REFERENCE.sub(replace_action_reference, line))
        if (match := ACTION_REFERENCE.search(line)) and (action := match.group("action")) and "#" in line
        else ACTION_REFERENCE.sub(replace_action_reference, line)
        for line in original.splitlines(keepends=True)
    )
    for old, new in PACKAGE_UPDATES.items():
        updated = updated.replace(old, new)
    if relative == GENERATOR_IMPL:
        updated = migrate_generator_impl(updated)
    elif relative == GENERATOR_TEST:
        updated = migrate_generator_test(updated)
    elif relative == PYTHON_PROFILE:
        updated = migrate_python_profile(updated)
    return updated


def readable_tracked_text() -> list[tuple[str, str]]:
    documents: list[tuple[str, str]] = []
    for relative in tracked_files():
        if relative == SELF or relative.endswith(".lock"):
            continue
        path = ROOT / relative
        if path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        try:
            documents.append((relative, path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return documents


def update_tracked_text() -> list[str]:
    changed: list[str] = []
    for relative, original in readable_tracked_text():
        path = ROOT / relative
        updated = transform_text(relative, original)
        if updated == original:
            continue
        path.write_text(updated, encoding="utf-8", newline="")
        changed.append(relative)
    return changed


def verify_expected_inputs() -> None:
    requirements = (ROOT / "requirements-dev.in").read_text(encoding="utf-8")
    runtime = (ROOT / "skills/mcp-server-architect/locks/python-runtime.in").read_text(encoding="utf-8")
    generator = (ROOT / "skills/mcp-server-architect/tools/generate_python_server.py").read_text(encoding="utf-8")
    implementation = (ROOT / GENERATOR_IMPL).read_text(encoding="utf-8")
    generator_test = (ROOT / GENERATOR_TEST).read_text(encoding="utf-8")
    profile = (ROOT / PYTHON_PROFILE).read_text(encoding="utf-8")

    assert "mcp==2.0.0" in requirements
    assert "ruff==0.16.0" in requirements
    assert "types-PyYAML==6.0.12.20260724" in requirements
    assert "mcp==2.0.0" in runtime
    assert "mcp>=2.0.0,<3" in generator
    assert "mcp>=2.0.0,<3" in generator_test
    assert "from mcp.server.mcpserver import Context, MCPServer" in implementation
    assert "from mcp.server.mcpserver.exceptions import ToolError" in implementation
    assert "from mcp.client import Client" in implementation
    assert "Context[AppContext]" in implementation
    assert "max_request_body_size=settings.max_request_body_bytes" in implementation
    assert "mcp.client.Client" in profile
    assert "mcp>=2.0.0,<3" in profile

    forbidden = (
        "mcp.server.fastmcp",
        "create_connected_server_and_client_session",
        "Context[ServerSession, AppContext]",
        "mcp>=1.27.2,<2",
        "mcp>=1.28.1,<2",
        "result.isError",
        "result.structuredContent",
        "tool.inputSchema",
    )
    combined = "\n".join((implementation, generator_test, profile))
    for token in forbidden:
        assert token not in combined, token

    references: dict[str, list[tuple[str, int, str]]] = {action: [] for action in ACTION_UPDATES}
    for relative, text in readable_tracked_text():
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in ACTION_REFERENCE.finditer(line):
                action = match.group("action")
                references[action].append((relative, line_number, match.group("revision")))

    for action, (_, expected_sha, _) in ACTION_UPDATES.items():
        observed = references[action]
        assert observed, f"No pinned references found for {action}"
        offenders = [item for item in observed if item[2] != expected_sha]
        assert not offenders, f"Unexpected {action} revisions: {offenders}"


def main() -> int:
    restore_production_ci()
    changed = update_tracked_text()
    verify_expected_inputs()
    print("Updated dependency policy files:")
    for relative in changed:
        print(relative)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
