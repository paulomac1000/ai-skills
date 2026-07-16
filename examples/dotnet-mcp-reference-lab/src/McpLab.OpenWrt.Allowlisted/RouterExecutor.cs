using McpLab.Common;

public sealed class RouterExecutor(IDiagnosticCommandCatalog catalog)
{
    public IReadOnlyList<string> ListDiagnostics() => catalog.Names;

    public RouterDiagnostic Run(string name, string? argument)
    {
        var arguments = catalog.Build(name, argument);
        // The lab does not execute a process. A production adapter would pass this argument array
        // to SSH without a shell and would capture a bounded, sanitized result.
        return new RouterDiagnostic(name, arguments, $"simulated: {string.Join(' ', arguments)}");
    }
}
