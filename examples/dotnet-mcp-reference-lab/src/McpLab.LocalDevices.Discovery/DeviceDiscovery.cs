using McpLab.Common;

public sealed class DeviceDiscovery
{
    private static readonly DeviceSummary[] Devices =
    [
        new("openbk-a1", "openbk", "192.0.2.10", true),
        new("tasmota-b2", "tasmota", "192.0.2.11", true),
        new("tuya-c3", "tuya", "192.0.2.12", false),
    ];

    public IReadOnlyList<DeviceSummary> Discover(string network, int limit)
    {
        if (limit is < 1 or > 100) throw new ArgumentOutOfRangeException(nameof(limit));
        if (!TryParseDocumentationNetwork(network, out var prefix))
        {
            throw new ArgumentException("The lab only permits documentation networks 192.0.2.0/24, 198.51.100.0/24, and 203.0.113.0/24.", nameof(network));
        }

        return Devices.Where(device => device.Address.StartsWith(prefix, StringComparison.Ordinal)).Take(limit).ToArray();
    }

    private static bool TryParseDocumentationNetwork(string value, out string prefix)
    {
        prefix = string.Empty;
        var allowed = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["192.0.2.0/24"] = "192.0.2.",
            ["198.51.100.0/24"] = "198.51.100.",
            ["203.0.113.0/24"] = "203.0.113.",
        };
        if (allowed.TryGetValue(value, out var allowedPrefix))
        {
            prefix = allowedPrefix;
            return true;
        }

        return false;
    }
}
