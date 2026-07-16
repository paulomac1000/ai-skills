using McpLab.Common;

public sealed class DiagnosticCatalogTests
{
    private readonly OpenWrtDiagnosticCatalog _catalog = new();

    [Fact]
    public void Builds_typed_command_without_shell()
    {
        var command = _catalog.Build("dns_lookup", "router.example");
        Assert.Equal(new[] { "nslookup", "router.example" }, command);
    }

    [Theory]
    [InlineData("router.example;reboot")]
    [InlineData("$(id)")]
    [InlineData("a b")]
    public void Rejects_shell_metacharacters(string host)
    {
        Assert.Throws<ArgumentException>(() => _catalog.Build("dns_lookup", host));
    }
}
