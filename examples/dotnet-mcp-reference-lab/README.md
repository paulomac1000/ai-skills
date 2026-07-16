# .NET MCP reference lab

This solution ports reusable ideas from five Python MCP servers without copying their historical scaffolding.

| Project | Source inspiration | Pattern under test |
|---|---|---|
| `McpLab.HomeAssistant.ReadOnly` | `ha-mcp-readonly` | compile-time read-only surface and bounded detail |
| `McpLab.Kontomierz.SafeWrite` | `kontomierz-mcp` | independent authorization, confirmation, and idempotency |
| `McpLab.OpenWrt.Allowlisted` | `openwrt-mcp` | typed diagnostic commands instead of arbitrary shell |
| `McpLab.Mikrus.Adapters` | `mikrus-mcp` | target adapters behind a stable tool contract |
| `McpLab.LocalDevices.Discovery` | `local-home-devices-mcp` | discovery boundary, normalization, and bounded scan scope |

All servers use stdio so the lab tests one concern at a time. Domain services are fake deterministic adapters; replace them with real clients only after adding contract fixtures or a sandbox.

```bash
dotnet restore McpLab.slnx
dotnet test McpLab.slnx
dotnet run --project src/McpLab.HomeAssistant.ReadOnly
```

Package versions are centrally declared in `Directory.Packages.props` and updated by Dependabot. Documentation never repeats them.
