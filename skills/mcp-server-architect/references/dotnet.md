# .NET MCP profile

Use the official C# SDK packages selected by host type:

- `ModelContextProtocol` for hosted stdio servers and clients,
- `ModelContextProtocol.AspNetCore` for HTTP servers,
- `ModelContextProtocol.Core` for low-level or dependency-minimal scenarios.

Package versions live in `Directory.Packages.props` and are updated by Dependabot. Do not copy them into instructions.

## Shape

- Register tools with `[McpServerToolType]` and `[McpServerTool]` for straightforward surfaces.
- Put domain behavior in injected services; static tool classes are adapters.
- Use `Host.CreateApplicationBuilder`, DI, options validation, `HttpClientFactory`, cancellation tokens, and structured logging.
- Configure console logs to stderr for stdio.
- Use ASP.NET Core host filtering and restrictive CORS only when browser access is intentional.
- Prefer stateless HTTP when server-to-client features and session state are not needed.
- Add handler filters or middleware for identity, authorization, audit, rate limiting, and validation rather than repeating checks in every tool.

See `examples/dotnet-mcp-reference-lab` for five isolated pattern experiments derived from the author's Python servers.
