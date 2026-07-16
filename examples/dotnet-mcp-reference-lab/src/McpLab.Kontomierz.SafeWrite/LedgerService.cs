using McpLab.Common;

public sealed class LedgerService
{
    private readonly Dictionary<string, TransactionReceipt> _receipts = new(StringComparer.Ordinal);
    private static readonly AccountSummary[] Accounts = [new("acc-demo", "Demo account", 1250.00m, "PLN")];

    public IReadOnlyList<AccountSummary> ListAccounts() => Accounts;

    public TransactionReceipt Create(string accountId, decimal amount, string currency, string idempotencyKey)
    {
        if (amount == 0) throw new ArgumentOutOfRangeException(nameof(amount), "Amount cannot be zero.");
        if (!Accounts.Any(account => account.Id == accountId)) throw new KeyNotFoundException("Account was not found.");
        if (!string.Equals(currency, "PLN", StringComparison.Ordinal)) throw new ArgumentException("Only PLN is supported by the lab.", nameof(currency));
        if (string.IsNullOrWhiteSpace(idempotencyKey)) throw new ArgumentException("Idempotency key is required.", nameof(idempotencyKey));

        if (_receipts.TryGetValue(idempotencyKey, out var existing)) return existing;
        var receipt = new TransactionReceipt($"txn-{_receipts.Count + 1}", accountId, amount, currency, idempotencyKey);
        _receipts.Add(idempotencyKey, receipt);
        return receipt;
    }
}
