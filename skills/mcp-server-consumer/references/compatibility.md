# Legacy MCP compatibility

Some servers expose custom `success`, `error`, `_meta`, risk-prefix, REST-mirror, or capability-manifest conventions. Treat these as adapters:

1. Parse native MCP status first.
2. If the native call succeeds, parse the documented legacy envelope.
3. Resolve contradictions toward failure and preserve both signals.
4. Do not treat a `[READ]` prefix or custom manifest as permission.
5. Prefer the standard protocol schema when duplicate metadata disagrees.
6. Record the adapter and remove it after the server migrates.
