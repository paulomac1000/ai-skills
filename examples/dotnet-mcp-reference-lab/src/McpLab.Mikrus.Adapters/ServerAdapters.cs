using McpLab.Common;

public interface IServerAdapter
{
    string Provider { get; }
    IReadOnlyList<ServerSummary> List();
    ServerMetrics GetMetrics(string serverId);
}

public sealed class FakeApiAdapter : IServerAdapter
{
    public string Provider => "api";
    public IReadOnlyList<ServerSummary> List() => [new("srv-api-1", Provider, "running")];
    public ServerMetrics GetMetrics(string serverId) => serverId == "srv-api-1"
        ? new(serverId, 12.5, 512 * 1024 * 1024, DateTimeOffset.Parse("2026-07-17T00:00:00Z"))
        : throw new KeyNotFoundException($"Server '{serverId}' was not found by {Provider} adapter.");
}

public sealed class FakeSshAdapter : IServerAdapter
{
    public string Provider => "ssh";
    public IReadOnlyList<ServerSummary> List() => [new("srv-ssh-1", Provider, "running")];
    public ServerMetrics GetMetrics(string serverId) => serverId == "srv-ssh-1"
        ? new(serverId, 8.0, 256 * 1024 * 1024, DateTimeOffset.Parse("2026-07-17T00:00:00Z"))
        : throw new KeyNotFoundException($"Server '{serverId}' was not found by {Provider} adapter.");
}

public sealed class ServerDirectory(IEnumerable<IServerAdapter> adapters)
{
    private readonly IReadOnlyList<IServerAdapter> _adapters = adapters.ToArray();

    public IReadOnlyList<ServerSummary> List() => _adapters.SelectMany(adapter => adapter.List()).OrderBy(server => server.Id, StringComparer.Ordinal).ToArray();

    public ServerMetrics GetMetrics(string serverId)
    {
        var adapter = _adapters.SingleOrDefault(candidate => candidate.List().Any(server => server.Id == serverId));
        return adapter?.GetMetrics(serverId) ?? throw new KeyNotFoundException($"Server '{serverId}' was not found.");
    }
}
