using System.ComponentModel;
using McpLab.Common;
using ModelContextProtocol.Server;

[McpServerToolType]
public sealed class MikrusTools(ServerDirectory directory)
{
    [McpServerTool(ReadOnly = true, UseStructuredContent = true), Description("Lists servers from all configured provider adapters with stable identifiers.")]
    public IReadOnlyList<ServerSummary> ListServers() => directory.List();

    [McpServerTool(ReadOnly = true, UseStructuredContent = true), Description("Returns normalized metrics for one exact server identifier regardless of provider transport.")]
    public ServerMetrics GetServerMetrics([Description("Exact identifier returned by list_servers.")] string serverId) => directory.GetMetrics(serverId);
}
