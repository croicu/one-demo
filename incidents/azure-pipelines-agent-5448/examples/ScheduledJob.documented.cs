namespace Billing.Jobs;

/// <summary>
/// Base class for scheduled jobs. Jobs derived from this class run with one replica fleet-wide:
/// the scheduler starts a single instance per run, never one per host.
/// </summary>
public abstract class ScheduledJob
{
    protected ScheduledJob(HttpClient ledger, string schedule)
    {
        Ledger = ledger;
        Schedule = schedule;
    }

    protected HttpClient Ledger { get; }

    public string Schedule { get; }

    public Task ExecuteAsync(CancellationToken ct) => RunAsync(ct);

    protected abstract Task RunAsync(CancellationToken ct);
}
