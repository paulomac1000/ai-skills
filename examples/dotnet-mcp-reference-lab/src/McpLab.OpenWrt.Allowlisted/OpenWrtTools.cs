using System.ComponentModel;
using McpLab.Common;
using ModelContextProtocol.Server;

[McpServerToolType]
public sealed class OpenWrtTools(RouterExecutor executor)
{
    [McpServerTool(ReadOnly = true, UseStructuredContent = true), Description("Lists typed OpenWrt diagnostic operations; arbitrary shell commands are not exposed.")]
    public IReadOnlyList<string> ListDiagnostics() => executor.ListDiagnostics();

    [McpServerTool(ReadOnly = true, UseStructuredContent = true), Description("Builds and runs one allowlisted OpenWrt diagnostic operation.")]
    public RouterDiagnostic RunDiagnostic(
        [Description("Diagnostic name returned by list_diagnostics.")] string name,
        [Description("Optional validated host or service argument required by selected diagnostics.")] string? argument = null) => executor.Run(name, argument);
}
