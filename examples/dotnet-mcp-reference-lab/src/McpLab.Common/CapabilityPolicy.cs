namespace McpLab.Common;

public enum CapabilityEffect
{
    Read,
    Write,
    Destructive,
    RawCommand
}

public sealed record CapabilityRequest(
    string Capability,
    CapabilityEffect Effect,
    string Target,
    bool WriteEnabled,
    bool IsAuthorized,
    bool UserConfirmed);

public sealed record PolicyDecision(bool Allowed, string ReasonCode)
{
    public static PolicyDecision Allow() => new(true, "allowed");
    public static PolicyDecision Deny(string reasonCode) => new(false, reasonCode);
}

public interface ICapabilityPolicy
{
    PolicyDecision Evaluate(CapabilityRequest request);
}

public sealed class DefaultCapabilityPolicy : ICapabilityPolicy
{
    public PolicyDecision Evaluate(CapabilityRequest request)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(request.Capability);
        ArgumentException.ThrowIfNullOrWhiteSpace(request.Target);

        if (request.Effect is CapabilityEffect.Read)
        {
            return request.IsAuthorized ? PolicyDecision.Allow() : PolicyDecision.Deny("not_authorized");
        }

        if (!request.WriteEnabled)
        {
            return PolicyDecision.Deny("write_disabled");
        }

        if (!request.IsAuthorized)
        {
            return PolicyDecision.Deny("not_authorized");
        }

        if (request.Effect is CapabilityEffect.Destructive or CapabilityEffect.RawCommand && !request.UserConfirmed)
        {
            return PolicyDecision.Deny("confirmation_required");
        }

        return PolicyDecision.Allow();
    }
}
