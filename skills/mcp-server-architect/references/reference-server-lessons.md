# Lessons from the author's MCP servers

The Python servers provide strong patterns worth retaining:

- `ha-mcp-readonly`: hard read-only boundary, allowlisted filesystem access, broad contract and security tests, batch and diagnostic tools, data-quality metadata.
- `kontomierz-mcp`: writes disabled by default, distinct read/write/destructive capabilities, explicit public-access opt-in.
- `openwrt-mcp`: command allowlisting, validated arguments, operational diagnostics, separate mutation policy.
- `mikrus-mcp`: composition of API and SSH adapters, zero-I/O capability introspection, useful caching and target abstraction.
- `local-home-devices-mcp`: discovery isolation, device-family adapters, blocked raw commands, host-networking awareness.

Patterns that must not become universal requirements:

- one MCP tool per upstream endpoint,
- very large catalogs without measured selection quality,
- custom JSON `success` wrappers as the canonical protocol result,
- mandatory REST mirrors and three-port topology,
- legacy SSE as a default transport,
- risk prefixes in descriptions as a security control,
- framework-specific file names and helper functions in the core standard.

The .NET lab deliberately tests the reusable ideas without cloning the historical scaffolding.
