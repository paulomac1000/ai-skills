---
afds_schema_version: 2
description: Compatibility pointer for the retired ambiguous Python FastMCP profile filename.
doc_id: reference.python-fastmcp-compatibility-pointer
type: reference
status: deprecated
rigor: informative
owners: [repository-maintainers]
supersedes: []
---

# Python FastMCP profile compatibility pointer

This filename is retained only so historical repository links do not become broken evidence. It is **not** an SDK profile and must not be used to choose an implementation by class name.

Use [Official Python MCP SDK](python-official-mcp-sdk.md) when the installed distribution is `mcp` and production imports are owned by the official `mcp` namespace. Use [FastMCP package profile](python-fastmcp-package.md) when the installed distribution and import namespace are `fastmcp`.

New documentation must link directly to the resolved profile above.
