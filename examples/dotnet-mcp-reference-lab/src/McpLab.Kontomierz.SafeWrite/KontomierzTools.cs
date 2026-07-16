using System.ComponentModel;
using McpLab.Common;
using ModelContextProtocol;
using ModelContextProtocol.Server;

[McpServerToolType]
public sealed class KontomierzTools(LedgerService ledger, ICapabilityPolicy policy)
{
    [McpServerTool(ReadOnly = true, UseStructuredContent = true), Description("Lists accounts visible to the caller.")]
    public IReadOnlyList<AccountSummary> ListAccounts() => ledger.ListAccounts();

    [McpServerTool(UseStructuredContent = true), Description("Creates one idempotent ledger transaction after server-side write authorization.")]
    public TransactionReceipt CreateTransaction(
        [Description("Exact account identifier returned by list_accounts.")] string accountId,
        [Description("Signed non-zero transaction amount.")] decimal amount,
        [Description("ISO currency code; the lab supports PLN.")] string currency,
        [Description("Stable key used to make retries idempotent.")] string idempotencyKey,
        [Description("Whether deployment policy enables write operations.")] bool writeEnabled = false,
        [Description("Whether the authenticated caller is authorized for this account.")] bool authorized = false)
    {
        var decision = policy.Evaluate(new CapabilityRequest(
            "create_transaction", CapabilityEffect.Write, accountId, writeEnabled, authorized, UserConfirmed: true));
        if (!decision.Allowed) throw new McpException($"Policy denied the operation: {decision.ReasonCode}.");
        return ledger.Create(accountId, amount, currency, idempotencyKey);
    }
}
