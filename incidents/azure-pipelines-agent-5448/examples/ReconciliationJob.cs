using System.Net.Http.Json;

namespace Billing.Jobs;

public sealed record LedgerBatch(string BatchId, IReadOnlyList<string> UnmatchedEntries);

public sealed class ReconciliationJob : ScheduledJob
{
    private const int MaxAttempts = 5;
    private static readonly TimeSpan RetryDelay = TimeSpan.FromSeconds(2);

    public ReconciliationJob(HttpClient ledger)
        : base(ledger, schedule: "0 * * * *")
    {
    }

    protected override async Task RunAsync(CancellationToken ct)
    {
        var batch = await GetOpenBatchAsync(ct);
        if (batch is null)
        {
            return;
        }

        foreach (var entry in batch.UnmatchedEntries)
        {
            await Ledger.PostAsJsonAsync($"batches/{batch.BatchId}/match", entry, ct);
        }
    }

    private async Task<LedgerBatch?> GetOpenBatchAsync(CancellationToken ct)
    {
        for (var attempt = 1; attempt <= MaxAttempts; attempt++)
        {
            try
            {
                return await Ledger.GetFromJsonAsync<LedgerBatch>("batches/open", ct);
            }
            catch (HttpRequestException) when (attempt < MaxAttempts)
            {
                await Task.Delay(RetryDelay, ct);
            }
        }

        throw new InvalidOperationException("Retry loop exited without a result.");
    }
}
