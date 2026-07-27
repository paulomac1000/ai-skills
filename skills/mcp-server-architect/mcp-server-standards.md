---
description: Deprecated compatibility entry point for the MCP server standard.
doc_id: reference.mcp-server-standard-legacy-entrypoint
type: reference
status: deprecated
rigor: operational
owners: [repository-maintainers]
verification: Validate this document and confirm every link resolves to the active MCP server standard.
---

# MCP server standard compatibility entry point

This stable path is retained for repositories that linked to the former monolithic standard.

The active normative contract is [MCP server standard](STANDARD.md). Implementation detail is split into focused references:

- [Capability manifests and versioning](references/capability-manifests-and-versioning.md)
- [Transport, lifecycle, and conformance](references/transport-lifecycle-and-conformance.md)
- [Python and FastMCP](references/python-fastmcp.md)
- [.NET MCP](references/dotnet-mcp.md)
- [Testing strategy](references/testing-strategy.md)
- [Security and operations](references/security-and-operations.md)

Do not add new rules here. Update the canonical owner and keep this file as a compatibility redirect.
