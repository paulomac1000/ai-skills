using System.ComponentModel;
using McpLab.Common;
using ModelContextProtocol.Server;

[McpServerToolType]
public sealed class LocalDeviceTools(DeviceDiscovery discovery)
{
    [McpServerTool(ReadOnly = true, UseStructuredContent = true), Description("Discovers normalized local devices inside one explicitly allowed network scope.")]
    public IReadOnlyList<DeviceSummary> DiscoverDevices(
        [Description("Exact CIDR network allowed by deployment policy.")] string network,
        [Description("Maximum number of devices from 1 to 100.")] int limit = 25) => discovery.Discover(network, limit);
}
