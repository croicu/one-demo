using System.Net.Http.Json;

namespace Orders.Availability;

public sealed record StockLevel(string Sku, int Available);

public sealed class InventoryClient
{
    private const int MaxAttempts = 5;
    private static readonly TimeSpan RetryDelay = TimeSpan.FromSeconds(2);

    private readonly HttpClient _http;

    public InventoryClient(HttpClient http)
    {
        _http = http;
    }

    public async Task<StockLevel?> GetStockAsync(string sku, CancellationToken ct)
    {
        for (var attempt = 1; attempt <= MaxAttempts; attempt++)
        {
            try
            {
                return await _http.GetFromJsonAsync<StockLevel>($"stock/{sku}", ct);
            }
            catch (HttpRequestException) when (attempt < MaxAttempts)
            {
                await Task.Delay(RetryDelay, ct);
            }
        }

        throw new InvalidOperationException("Retry loop exited without a result.");
    }
}

public static class AvailabilityEndpoints
{
    public static IServiceCollection AddAvailability(this IServiceCollection services)
    {
        services.AddHttpClient<InventoryClient>(client =>
        {
            client.BaseAddress = new Uri("http://inventory-api:8080/");
        });
        return services;
    }

    public static IEndpointRouteBuilder MapAvailability(this IEndpointRouteBuilder routes)
    {
        routes.MapGet("/orders/{orderId}/lines/{sku}/availability",
            async (string orderId, string sku, InventoryClient inventory, CancellationToken ct) =>
            {
                var stock = await inventory.GetStockAsync(sku, ct);
                return stock is null ? Results.NotFound() : Results.Ok(stock);
            });
        return routes;
    }
}
