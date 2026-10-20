using System.Net.Http.Json;

namespace Host.Telemetry;

public sealed record AgentStatus(string State, double CpuPercent);

public sealed class StatusMonitor : BackgroundService
{
    private const int MaxAttempts = 5;
    private static readonly TimeSpan RetryDelay = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan PollInterval = TimeSpan.FromSeconds(30);

    private readonly HttpClient _http = new() { BaseAddress = new Uri("http://127.0.0.1:9100/") };
    private readonly ILogger<StatusMonitor> _logger;

    public StatusMonitor(ILogger<StatusMonitor> logger)
    {
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            var status = await GetStatusAsync(ct);
            _logger.LogInformation("Agent {State}, CPU {Cpu}%", status?.State, status?.CpuPercent);
            await Task.Delay(PollInterval, ct);
        }
    }

    private async Task<AgentStatus?> GetStatusAsync(CancellationToken ct)
    {
        for (var attempt = 1; attempt <= MaxAttempts; attempt++)
        {
            try
            {
                return await _http.GetFromJsonAsync<AgentStatus>("status", ct);
            }
            catch (HttpRequestException) when (attempt < MaxAttempts)
            {
                await Task.Delay(RetryDelay, ct);
            }
        }

        throw new InvalidOperationException("Retry loop exited without a result.");
    }
}
