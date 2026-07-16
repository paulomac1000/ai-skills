namespace McpLab.Common;

public sealed record EntitySummary(string Id, string Domain, string State);
public sealed record EntityState(string Id, string State, DateTimeOffset UpdatedAt, IReadOnlyDictionary<string, object?> Attributes);
public sealed record AccountSummary(string Id, string Name, decimal Balance, string Currency);
public sealed record TransactionReceipt(string Id, string AccountId, decimal Amount, string Currency, string IdempotencyKey);
public sealed record RouterDiagnostic(string Name, IReadOnlyList<string> Arguments, string Output);
public sealed record ServerSummary(string Id, string Provider, string Status);
public sealed record ServerMetrics(string Id, double CpuPercent, long MemoryBytes, DateTimeOffset SampledAt);
public sealed record DeviceSummary(string Id, string Kind, string Address, bool Online);
