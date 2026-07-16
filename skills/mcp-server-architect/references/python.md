# Python MCP profile

Use the stable official Python SDK or a compatible framework with explicit protocol support.

- Keep registration thin; inject typed clients, policy, and clocks.
- Prefer async clients for concurrent network I/O and propagate cancellation.
- Route logs to stderr for stdio.
- Use typed result models and native structured output where the SDK supports it.
- Isolate optional integrations so import failure does not remove unrelated tools.
- Test internal services without starting a transport; add protocol tests through an SDK client.
- Do not copy the historic three-port, REST bridge, JSON-string envelope, or global manifest factory into every server. Adopt each only for a demonstrated consumer need.

For upstream HTTP, SSH, and device protocols, record representative contracts or use a sandbox. Pure mocks are insufficient evidence of compatibility.
