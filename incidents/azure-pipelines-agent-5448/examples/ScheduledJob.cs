namespace Billing.Jobs;

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
