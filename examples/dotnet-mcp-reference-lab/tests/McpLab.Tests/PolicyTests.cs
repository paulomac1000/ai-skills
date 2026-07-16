using McpLab.Common;

public sealed class PolicyTests
{
    private readonly DefaultCapabilityPolicy _policy = new();

    [Fact]
    public void Read_requires_authorization()
    {
        var decision = _policy.Evaluate(new("read", CapabilityEffect.Read, "target", false, false, false));
        Assert.False(decision.Allowed);
        Assert.Equal("not_authorized", decision.ReasonCode);
    }

    [Fact]
    public void Write_is_disabled_by_default()
    {
        var decision = _policy.Evaluate(new("write", CapabilityEffect.Write, "target", false, true, true));
        Assert.False(decision.Allowed);
        Assert.Equal("write_disabled", decision.ReasonCode);
    }

    [Fact]
    public void Destructive_requires_confirmation()
    {
        var decision = _policy.Evaluate(new("delete", CapabilityEffect.Destructive, "target", true, true, false));
        Assert.False(decision.Allowed);
        Assert.Equal("confirmation_required", decision.ReasonCode);
    }
}
