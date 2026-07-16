using System.Collections.Frozen;
using System.Text.RegularExpressions;

namespace McpLab.Common;

public interface IDiagnosticCommandCatalog
{
    IReadOnlyList<string> Names { get; }
    IReadOnlyList<string> Build(string name, string? argument);
}

public sealed partial class OpenWrtDiagnosticCatalog : IDiagnosticCommandCatalog
{
    private static readonly FrozenDictionary<string, Func<string?, string[]>> Commands =
        new Dictionary<string, Func<string?, string[]>>(StringComparer.Ordinal)
        {
            ["interfaces"] = _ => ["ip", "-json", "address", "show"],
            ["routes"] = _ => ["ip", "-json", "route", "show"],
            ["dns_lookup"] = host => ["nslookup", ValidateHost(host)],
            ["service_status"] = service => ["ubus", "call", "service", "list", $"{{\"name\":\"{ValidateService(service)}\"}}"],
        }.ToFrozenDictionary(StringComparer.Ordinal);

    public IReadOnlyList<string> Names => Commands.Keys.Order(StringComparer.Ordinal).ToArray();

    public IReadOnlyList<string> Build(string name, string? argument)
    {
        if (!Commands.TryGetValue(name, out var factory))
        {
            throw new ArgumentOutOfRangeException(nameof(name), "Unknown diagnostic command.");
        }

        return factory(argument);
    }

    private static string ValidateHost(string? value)
    {
        if (string.IsNullOrWhiteSpace(value) || !HostPattern().IsMatch(value))
        {
            throw new ArgumentException("Host must contain only letters, digits, dots, or hyphens.", nameof(value));
        }

        return value;
    }

    private static string ValidateService(string? value)
    {
        if (string.IsNullOrWhiteSpace(value) || !ServicePattern().IsMatch(value))
        {
            throw new ArgumentException("Service name is not allowlisted by syntax.", nameof(value));
        }

        return value;
    }

    [GeneratedRegex("^[A-Za-z0-9.-]{1,253}$", RegexOptions.CultureInvariant)]
    private static partial Regex HostPattern();

    [GeneratedRegex("^[a-z0-9_-]{1,64}$", RegexOptions.CultureInvariant)]
    private static partial Regex ServicePattern();
}
