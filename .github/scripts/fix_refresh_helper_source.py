from pathlib import Path

HELPER = Path(__file__).with_name("refresh_dependency_set.py")
OLD_PROFILE = (
    '            "For production, use the stable official SDK line with an upper bound that excludes the next major until migration is complete. '
    'The generated baseline uses `mcp>=1.27.2,<2`, while repository verification uses an exact stable pin. '
    'While official SDK v2 is pre-release, it belongs to a separate experimental CI lane with an exact pin and cannot define the production artifact. '
    'A candidate major becomes production-supported only after registration, lifecycle, transport, policy parity, content, cancellation, and artifact matrices pass.",'
)
NEW_PROFILE = OLD_PROFILE.replace("mcp>=1.27.2,<2", "mcp>=2.0.0,<3")
OLD_COMBINED = '    combined = "\\n".join((implementation, generator_test, profile))'
NEW_COMBINED = '    combined = "\\n".join((implementation, profile))'
OLD_LIFESPAN = '''        (
            "async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:",
            "async def lifespan(_server: MCPServer[AppContext]) -> AsyncIterator[AppContext]:",
        ),'''
NEW_LIFESPAN = '''        (
            "                @asynccontextmanager\\n"
            "                async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:\\n"
            "                    yield AppContext(settings, InvocationKernel(settings, InventoryService(), approvals))",
            "                kernel = InvocationKernel(settings, InventoryService(), approvals)\\n\\n"
            "                @asynccontextmanager\\n"
            "                async def lifespan(_server: MCPServer[AppContext]) -> AsyncIterator[AppContext]:\\n"
            "                    yield AppContext(settings, kernel)",
        ),'''
OLD_CATALOG = '''        (
            "async def capability_catalog(ctx: Context[AppContext]) -> str:",
            "async def capability_catalog(ctx: Context) -> str:",
        ),'''
NEW_CATALOG = '''        (
            "async def capability_catalog(ctx: Context[AppContext]) -> str:\\n"
            "                    return json.dumps(ctx.request_context.lifespan_context.kernel.catalog(), sort_keys=True)",
            "async def capability_catalog() -> str:\\n"
            "                    return json.dumps(kernel.catalog(), sort_keys=True)",
        ),'''
OLD_READINESS = '''        (
            "async def readiness(ctx: Context[AppContext]) -> str:",
            "async def readiness(ctx: Context) -> str:",
        ),'''
NEW_READINESS = '''        (
            "async def readiness(ctx: Context[AppContext]) -> str:\\n"
            "                    app = ctx.request_context.lifespan_context\\n"
            "                    return json.dumps({\\\"ready\\\": True, \\\"transport\\\": app.settings.transport, \\\"active_capabilities\\\": len(app.kernel.active_names)}, sort_keys=True)",
            "async def readiness() -> str:\\n"
            "                    return json.dumps({\\\"ready\\\": True, \\\"transport\\\": settings.transport, \\\"active_capabilities\\\": len(kernel.active_names)}, sort_keys=True)",
        ),'''
OLD_ASSERTION = '    assert "Context[AppContext]" in implementation'
NEW_ASSERTION = '''    assert "Context[AppContext]" in implementation
    assert "async def capability_catalog() -> str:" in implementation
    assert "async def readiness() -> str:" in implementation
    assert "async def capability_catalog(ctx:" not in implementation
    assert "async def readiness(ctx:" not in implementation'''

text = HELPER.read_text(encoding="utf-8")
replacements = (
    (OLD_PROFILE, NEW_PROFILE),
    (OLD_COMBINED, NEW_COMBINED),
    (OLD_LIFESPAN, NEW_LIFESPAN),
    (OLD_CATALOG, NEW_CATALOG),
    (OLD_READINESS, NEW_READINESS),
    (OLD_ASSERTION, NEW_ASSERTION),
)
for old, new in replacements:
    if old not in text:
        raise RuntimeError(f"expected helper source literal is missing: {old!r}")
    text = text.replace(old, new)
HELPER.write_text(text, encoding="utf-8", newline="")
