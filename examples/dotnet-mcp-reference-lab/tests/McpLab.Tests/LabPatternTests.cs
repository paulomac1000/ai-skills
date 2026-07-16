public sealed class LabPatternTests
{
    [Fact]
    public void Kontomierz_write_is_idempotent()
    {
        var ledger = new LedgerService();
        var first = ledger.Create("acc-demo", 10m, "PLN", "key-1");
        var second = ledger.Create("acc-demo", 10m, "PLN", "key-1");
        Assert.Equal(first, second);
    }

    [Fact]
    public void Mikrus_adapters_return_normalized_servers()
    {
        var directory = new ServerDirectory(new IServerAdapter[] { new FakeApiAdapter(), new FakeSshAdapter() });
        Assert.Equal(2, directory.List().Count);
        Assert.Equal("srv-api-1", directory.GetMetrics("srv-api-1").Id);
    }

    [Fact]
    public void Device_discovery_rejects_unbounded_real_networks()
    {
        var discovery = new DeviceDiscovery();
        Assert.Throws<ArgumentException>(() => discovery.Discover("192.168.1.0/24", 25));
    }
}
