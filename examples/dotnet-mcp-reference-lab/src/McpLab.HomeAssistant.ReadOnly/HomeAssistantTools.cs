using System.ComponentModel;
using McpLab.Common;
using ModelContextProtocol.Server;

[McpServerToolType]
public sealed class HomeAssistantTools(HomeAssistantReader reader)
{
    [McpServerTool(ReadOnly = true, UseStructuredContent = true), Description("Searches Home Assistant entities with bounded output.")]
    public IReadOnlyList<EntitySummary> SearchEntities(
        [Description("Optional entity domain such as sensor or climate.")] string? domain = null,
        [Description("Maximum number of entities from 1 to 100.")] int limit = 25) => reader.Search(domain, limit);

    [McpServerTool(ReadOnly = true, UseStructuredContent = true), Description("Returns current state for one exact Home Assistant entity identifier.")]
    public EntityState GetEntityState([Description("Exact Home Assistant entity identifier.")] string entityId) => reader.Get(entityId);
}
