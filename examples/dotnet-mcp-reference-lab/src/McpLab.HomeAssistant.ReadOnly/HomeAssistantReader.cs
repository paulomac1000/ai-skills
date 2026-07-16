using McpLab.Common;

public sealed class HomeAssistantReader
{
    private static readonly EntityState[] Entities =
    [
        new("sensor.living_room_temperature", "22.4", DateTimeOffset.Parse("2026-07-17T00:00:00Z"), new Dictionary<string, object?> { ["unit"] = "°C" }),
        new("binary_sensor.balcony_window", "off", DateTimeOffset.Parse("2026-07-17T00:00:00Z"), new Dictionary<string, object?> { ["device_class"] = "window" }),
        new("climate.bedroom", "cool", DateTimeOffset.Parse("2026-07-17T00:00:00Z"), new Dictionary<string, object?> { ["temperature"] = 23.0 }),
    ];

    public IReadOnlyList<EntitySummary> Search(string? domain, int limit)
    {
        if (limit is < 1 or > 100) throw new ArgumentOutOfRangeException(nameof(limit));
        return Entities
            .Where(entity => domain is null || entity.Id.StartsWith(domain + ".", StringComparison.Ordinal))
            .Take(limit)
            .Select(entity => new EntitySummary(entity.Id, entity.Id.Split('.')[0], entity.State))
            .ToArray();
    }

    public EntityState Get(string entityId) =>
        Entities.SingleOrDefault(entity => entity.Id.Equals(entityId, StringComparison.Ordinal))
        ?? throw new KeyNotFoundException($"Entity '{entityId}' was not found.");
}
