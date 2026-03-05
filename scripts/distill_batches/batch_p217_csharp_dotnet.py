"""C# and .NET 8+ — async/await, minimal APIs, EF Core advanced, source generators, pattern matching."""

PAIRS = [
    (
        "csharp/async-await-valuetask",
        "Show C# async/await patterns with ValueTask, cancellation, async streams, and concurrent async operations.",
        '''C# async/await with ValueTask, cancellation, and advanced patterns:

```csharp
// --- Async fundamentals and ValueTask ---

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;

public class AsyncPatterns
{
    private readonly HttpClient _httpClient = new();

    // ValueTask<T> for hot-path optimization (cache hit = no allocation)
    private string? _cachedValue;

    public ValueTask<string> GetCachedValueAsync()
    {
        if (_cachedValue is not null)
        {
            return ValueTask.FromResult(_cachedValue); // No Task allocation
        }
        return new ValueTask<string>(FetchAndCacheAsync());
    }

    private async Task<string> FetchAndCacheAsync()
    {
        _cachedValue = await _httpClient.GetStringAsync("https://api.example.com/data");
        return _cachedValue;
    }

    // Cancellation token propagation
    public async Task<List<string>> FetchMultipleAsync(
        IEnumerable<string> urls,
        CancellationToken cancellationToken = default)
    {
        var results = new List<string>();

        foreach (var url in urls)
        {
            // Check cancellation before each request
            cancellationToken.ThrowIfCancellationRequested();

            var response = await _httpClient.GetAsync(url, cancellationToken);
            response.EnsureSuccessStatusCode();
            var content = await response.Content.ReadAsStringAsync(cancellationToken);
            results.Add(content);
        }

        return results;
    }

    // Timeout with CancellationTokenSource
    public async Task<string> FetchWithTimeoutAsync(string url, TimeSpan timeout)
    {
        using var cts = new CancellationTokenSource(timeout);
        try
        {
            return await _httpClient.GetStringAsync(url, cts.Token);
        }
        catch (OperationCanceledException) when (cts.IsCancellationRequested)
        {
            throw new TimeoutException($"Request to {url} timed out after {timeout}");
        }
    }

    // Linked cancellation: cancel on timeout OR caller cancellation
    public async Task<string> FetchWithLinkedCancellationAsync(
        string url, TimeSpan timeout, CancellationToken externalToken)
    {
        using var timeoutCts = new CancellationTokenSource(timeout);
        using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(
            timeoutCts.Token, externalToken);

        return await _httpClient.GetStringAsync(url, linkedCts.Token);
    }
}
```

```csharp
// --- Concurrent async operations ---

using System.Threading.Tasks;
using System.Collections.Generic;
using System.Linq;

public class ConcurrentAsync
{
    private readonly HttpClient _http = new();

    // WhenAll: run multiple tasks concurrently, wait for all
    public async Task<UserDashboard> GetDashboardAsync(string userId, CancellationToken ct)
    {
        var profileTask = GetProfileAsync(userId, ct);
        var ordersTask = GetOrdersAsync(userId, ct);
        var notificationsTask = GetNotificationsAsync(userId, ct);

        // All three run concurrently
        await Task.WhenAll(profileTask, ordersTask, notificationsTask);

        return new UserDashboard(
            Profile: await profileTask,
            Orders: await ordersTask,
            Notifications: await notificationsTask
        );
    }

    // WhenAny: race multiple tasks, take first result
    public async Task<string> FetchFromFastestMirrorAsync(
        IReadOnlyList<string> urls, CancellationToken ct)
    {
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        var tasks = urls.Select(url => FetchAsync(url, cts.Token)).ToList();

        while (tasks.Count > 0)
        {
            var completed = await Task.WhenAny(tasks);
            tasks.Remove(completed);

            try
            {
                var result = await completed;
                cts.Cancel(); // Cancel remaining tasks
                return result;
            }
            catch (Exception)
            {
                // Try next task
                if (tasks.Count == 0) throw;
            }
        }

        throw new InvalidOperationException("No mirrors available");
    }

    // Bounded concurrency with SemaphoreSlim
    public async Task<List<string>> FetchAllBoundedAsync(
        IEnumerable<string> urls, int maxConcurrency, CancellationToken ct)
    {
        var semaphore = new SemaphoreSlim(maxConcurrency);
        var tasks = urls.Select(async url =>
        {
            await semaphore.WaitAsync(ct);
            try
            {
                return await FetchAsync(url, ct);
            }
            finally
            {
                semaphore.Release();
            }
        });

        return (await Task.WhenAll(tasks)).ToList();
    }

    // Async streams (IAsyncEnumerable)
    public async IAsyncEnumerable<int> GenerateNumbersAsync(
        int count,
        [EnumeratorCancellation] CancellationToken ct = default)
    {
        for (int i = 0; i < count; i++)
        {
            ct.ThrowIfCancellationRequested();
            await Task.Delay(100, ct); // Simulate async work
            yield return i;
        }
    }

    // Consuming async streams
    public async Task ProcessStreamAsync(CancellationToken ct)
    {
        await foreach (var number in GenerateNumbersAsync(100, ct))
        {
            Console.WriteLine($"Processing: {number}");
        }
    }

    // Channel-based producer/consumer
    public async Task ProducerConsumerAsync(CancellationToken ct)
    {
        var channel = Channel.CreateBounded<int>(new BoundedChannelOptions(10)
        {
            FullMode = BoundedChannelFullMode.Wait
        });

        var producer = Task.Run(async () =>
        {
            for (int i = 0; i < 100; i++)
            {
                await channel.Writer.WriteAsync(i, ct);
            }
            channel.Writer.Complete();
        }, ct);

        var consumer = Task.Run(async () =>
        {
            await foreach (var item in channel.Reader.ReadAllAsync(ct))
            {
                Console.WriteLine($"Consumed: {item}");
            }
        }, ct);

        await Task.WhenAll(producer, consumer);
    }

    private Task<UserProfile> GetProfileAsync(string id, CancellationToken ct) => Task.FromResult(new UserProfile());
    private Task<List<Order>> GetOrdersAsync(string id, CancellationToken ct) => Task.FromResult(new List<Order>());
    private Task<List<Notification>> GetNotificationsAsync(string id, CancellationToken ct) => Task.FromResult(new List<Notification>());
    private Task<string> FetchAsync(string url, CancellationToken ct) => _http.GetStringAsync(url, ct);

    public record UserDashboard(UserProfile Profile, List<Order> Orders, List<Notification> Notifications);
    public record UserProfile();
    public record Order();
    public record Notification();
}
```

```csharp
// --- Retry and resilience patterns ---

using Polly;
using Polly.Retry;
using System.Net;

public class ResilientHttpClient
{
    private readonly HttpClient _http;
    private readonly ResiliencePipeline<HttpResponseMessage> _pipeline;

    public ResilientHttpClient(HttpClient http)
    {
        _http = http;

        // Polly v8 resilience pipeline
        _pipeline = new ResiliencePipelineBuilder<HttpResponseMessage>()
            .AddRetry(new RetryStrategyOptions<HttpResponseMessage>
            {
                MaxRetryAttempts = 3,
                Delay = TimeSpan.FromMilliseconds(200),
                BackoffType = DelayBackoffType.Exponential,
                ShouldHandle = new PredicateBuilder<HttpResponseMessage>()
                    .Handle<HttpRequestException>()
                    .HandleResult(r => r.StatusCode >= HttpStatusCode.InternalServerError),
                OnRetry = args =>
                {
                    Console.WriteLine($"Retry {args.AttemptNumber} after {args.RetryDelay}");
                    return ValueTask.CompletedTask;
                }
            })
            .AddTimeout(TimeSpan.FromSeconds(10))
            .Build();
    }

    public async Task<string> GetAsync(string url, CancellationToken ct = default)
    {
        var response = await _pipeline.ExecuteAsync(
            async token => await _http.GetAsync(url, token), ct);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadAsStringAsync(ct);
    }
}
```

Async pattern comparison:

| Pattern | Use Case | Returns | Allocation |
|---------|----------|---------|-----------|
| `Task<T>` | Default async return | Heap-allocated Task | Always |
| `ValueTask<T>` | Hot-path cache hits | Stack or Task | Conditional |
| `Task.WhenAll` | Parallel independent work | All results | Per-task |
| `Task.WhenAny` | Race / hedged requests | First completed | Per-task |
| `SemaphoreSlim` | Bounded concurrency | N/A | One semaphore |
| `IAsyncEnumerable<T>` | Streaming async data | Lazy sequence | Per-yield |
| `Channel<T>` | Producer/consumer | Bounded buffer | Channel + items |
| `CancellationToken` | Cooperative cancellation | N/A | One CTS |

Key patterns:
1. Use `ValueTask<T>` when the synchronous (cached) path is common — avoids `Task` heap allocation
2. Always propagate `CancellationToken` through the entire call chain for cooperative cancellation
3. Use `CancellationTokenSource.CreateLinkedTokenSource` to combine timeout and external cancellation
4. `SemaphoreSlim` bounds concurrent async operations — prefer it over custom concurrency limiters
5. `IAsyncEnumerable<T>` with `await foreach` is ideal for streaming data without loading everything into memory
6. Channels provide backpressure-aware producer/consumer queues for async pipeline architectures'''
    ),
    (
        "csharp/minimal-apis-di",
        "Show C# minimal APIs with dependency injection, endpoint filters, validation, and structured responses.",
        '''C# minimal APIs with dependency injection and production patterns:

```csharp
// --- Program.cs: minimal API setup ---

using Microsoft.AspNetCore.Diagnostics;
using Microsoft.AspNetCore.Http.HttpResults;
using System.ComponentModel.DataAnnotations;

var builder = WebApplication.CreateBuilder(args);

// Register services
builder.Services.AddScoped<IUserRepository, UserRepository>();
builder.Services.AddScoped<IUserService, UserService>();
builder.Services.AddSingleton<IValidator<CreateUserRequest>, CreateUserValidator>();

// Add OpenAPI/Swagger
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// Add authentication
builder.Services.AddAuthentication().AddJwtBearer();
builder.Services.AddAuthorization();

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseAuthentication();
app.UseAuthorization();

// Global exception handler
app.UseExceptionHandler(exApp =>
{
    exApp.Run(async context =>
    {
        var exception = context.Features.Get<IExceptionHandlerFeature>()?.Error;
        var response = new ProblemDetails
        {
            Status = StatusCodes.Status500InternalServerError,
            Title = "Internal Server Error",
            Detail = app.Environment.IsDevelopment() ? exception?.Message : null
        };
        context.Response.StatusCode = 500;
        await context.Response.WriteAsJsonAsync(response);
    });
});

// Route groups with shared configuration
var api = app.MapGroup("/api")
    .AddEndpointFilter<ValidationFilter>()
    .RequireAuthorization();

var users = api.MapGroup("/users")
    .WithTags("Users");

var products = api.MapGroup("/products")
    .WithTags("Products");

// Map routes
users.MapGet("/", GetUsersAsync).WithName("GetUsers");
users.MapGet("/{id:int}", GetUserAsync).WithName("GetUser");
users.MapPost("/", CreateUserAsync).WithName("CreateUser");
users.MapPut("/{id:int}", UpdateUserAsync).WithName("UpdateUser");
users.MapDelete("/{id:int}", DeleteUserAsync).WithName("DeleteUser");

// Health check
app.MapGet("/health", () => Results.Ok(new { Status = "Healthy" }))
    .AllowAnonymous()
    .ExcludeFromDescription();

app.Run();
```

```csharp
// --- Endpoint handlers with typed results ---

using Microsoft.AspNetCore.Http.HttpResults;

// Typed results for OpenAPI documentation
static async Task<Results<Ok<PagedResponse<UserDto>>, BadRequest<ProblemDetails>>>
    GetUsersAsync(
        IUserService userService,
        int page = 1,
        int pageSize = 20,
        string? search = null,
        CancellationToken ct = default)
{
    if (page < 1 || pageSize < 1 || pageSize > 100)
    {
        return TypedResults.BadRequest(new ProblemDetails
        {
            Title = "Invalid pagination",
            Detail = "Page must be >= 1, pageSize must be 1-100"
        });
    }

    var result = await userService.GetUsersAsync(page, pageSize, search, ct);
    return TypedResults.Ok(result);
}

static async Task<Results<Ok<UserDto>, NotFound>>
    GetUserAsync(int id, IUserService userService, CancellationToken ct)
{
    var user = await userService.GetByIdAsync(id, ct);
    return user is not null
        ? TypedResults.Ok(user)
        : TypedResults.NotFound();
}

static async Task<Results<Created<UserDto>, BadRequest<ValidationProblemDetails>, Conflict>>
    CreateUserAsync(
        CreateUserRequest request,
        IUserService userService,
        CancellationToken ct)
{
    try
    {
        var user = await userService.CreateAsync(request, ct);
        return TypedResults.Created($"/api/users/{user.Id}", user);
    }
    catch (DuplicateEmailException)
    {
        return TypedResults.Conflict();
    }
}

static async Task<Results<Ok<UserDto>, NotFound, BadRequest<ProblemDetails>>>
    UpdateUserAsync(
        int id,
        UpdateUserRequest request,
        IUserService userService,
        CancellationToken ct)
{
    var user = await userService.UpdateAsync(id, request, ct);
    return user is not null
        ? TypedResults.Ok(user)
        : TypedResults.NotFound();
}

static async Task<Results<NoContent, NotFound>>
    DeleteUserAsync(int id, IUserService userService, CancellationToken ct)
{
    var deleted = await userService.DeleteAsync(id, ct);
    return deleted ? TypedResults.NoContent() : TypedResults.NotFound();
}

// DTOs and models
public record UserDto(int Id, string Name, string Email, DateTime CreatedAt);
public record CreateUserRequest(string Name, string Email);
public record UpdateUserRequest(string? Name, string? Email);
public record PagedResponse<T>(IReadOnlyList<T> Items, int Page, int PageSize, int TotalCount);
public class DuplicateEmailException : Exception { }
```

```csharp
// --- Endpoint filters and validation ---

using FluentValidation;
using Microsoft.AspNetCore.Http;

// Endpoint filter for validation
public class ValidationFilter : IEndpointFilter
{
    public async ValueTask<object?> InvokeAsync(
        EndpointFilterInvocationContext context,
        EndpointFilterDelegate next)
    {
        // Find the first argument that has a validator registered
        foreach (var arg in context.Arguments)
        {
            if (arg is null) continue;

            var argType = arg.GetType();
            var validatorType = typeof(IValidator<>).MakeGenericType(argType);
            var validator = context.HttpContext.RequestServices.GetService(validatorType);

            if (validator is not null)
            {
                var validateMethod = validatorType.GetMethod("Validate",
                    new[] { argType });
                var result = validateMethod?.Invoke(validator, new[] { arg })
                    as FluentValidation.Results.ValidationResult;

                if (result is not null && !result.IsValid)
                {
                    return TypedResults.ValidationProblem(
                        result.ToDictionary());
                }
            }
        }

        return await next(context);
    }
}

// FluentValidation validator
public class CreateUserValidator : AbstractValidator<CreateUserRequest>
{
    public CreateUserValidator()
    {
        RuleFor(x => x.Name)
            .NotEmpty().WithMessage("Name is required")
            .MinimumLength(2).WithMessage("Name must be at least 2 characters")
            .MaximumLength(100);

        RuleFor(x => x.Email)
            .NotEmpty().WithMessage("Email is required")
            .EmailAddress().WithMessage("Invalid email format");
    }
}

// Service with DI
public interface IUserService
{
    Task<PagedResponse<UserDto>> GetUsersAsync(int page, int pageSize, string? search, CancellationToken ct);
    Task<UserDto?> GetByIdAsync(int id, CancellationToken ct);
    Task<UserDto> CreateAsync(CreateUserRequest request, CancellationToken ct);
    Task<UserDto?> UpdateAsync(int id, UpdateUserRequest request, CancellationToken ct);
    Task<bool> DeleteAsync(int id, CancellationToken ct);
}

public interface IUserRepository
{
    Task<(List<User> Users, int Total)> GetPagedAsync(int skip, int take, string? search, CancellationToken ct);
    Task<User?> GetByIdAsync(int id, CancellationToken ct);
    Task<User> AddAsync(User user, CancellationToken ct);
    Task UpdateAsync(User user, CancellationToken ct);
    Task<bool> DeleteAsync(int id, CancellationToken ct);
}

public class User
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string Email { get; set; } = "";
    public DateTime CreatedAt { get; set; }
}
```

Minimal API vs controller comparison:

| Feature | Minimal API | Controller |
|---------|------------|-----------|
| Routing | `app.MapGet("/path", handler)` | `[HttpGet]` attribute |
| DI injection | Method parameters | Constructor injection |
| Filters | `AddEndpointFilter<T>()` | Action filters, middleware |
| Grouping | `MapGroup("/prefix")` | `[Route]` attribute |
| Validation | Manual or filter-based | `[ApiController]` auto-validation |
| OpenAPI | `WithTags`, `WithName` | Auto from controller name |
| Best for | Microservices, small APIs | Large APIs, full MVC features |

Key patterns:
1. Use `MapGroup` to share path prefixes, filters, and authorization across related endpoints
2. Typed results (`Results<Ok<T>, NotFound>`) generate accurate OpenAPI documentation automatically
3. Endpoint filters replace action filters for cross-cutting concerns (validation, logging)
4. DI works via method parameter injection — the runtime resolves registered services automatically
5. Use `CancellationToken` as a handler parameter to support request cancellation
6. `TypedResults.Created($"/path/{id}", value)` returns 201 with Location header and body'''
    ),
    (
        "csharp/ef-core-advanced",
        "Show Entity Framework Core advanced patterns including shadow properties, value conversions, global query filters, and raw SQL.",
        '''Entity Framework Core advanced patterns for production data access:

```csharp
// --- DbContext with advanced configuration ---

using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.ChangeTracking;
using Microsoft.EntityFrameworkCore.Storage.ValueConversion;
using System.Text.Json;

public class AppDbContext : DbContext
{
    public DbSet<Product> Products => Set<Product>();
    public DbSet<Order> Orders => Set<Order>();
    public DbSet<OrderLine> OrderLines => Set<OrderLine>();
    public DbSet<AuditLog> AuditLogs => Set<AuditLog>();

    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        // Shadow property: tracked by EF but not in the C# class
        modelBuilder.Entity<Product>()
            .Property<DateTime>("LastModified");

        modelBuilder.Entity<Product>()
            .Property<string>("ModifiedBy");

        // Value conversion: store enum as string
        modelBuilder.Entity<Order>()
            .Property(o => o.Status)
            .HasConversion(new EnumToStringConverter<OrderStatus>());

        // Value conversion: JSON column
        modelBuilder.Entity<Product>()
            .Property(p => p.Metadata)
            .HasConversion(
                v => JsonSerializer.Serialize(v, (JsonSerializerOptions?)null),
                v => JsonSerializer.Deserialize<Dictionary<string, string>>(v,
                    (JsonSerializerOptions?)null) ?? new(),
                new ValueComparer<Dictionary<string, string>>(
                    (a, b) => JsonSerializer.Serialize(a, (JsonSerializerOptions?)null) ==
                              JsonSerializer.Serialize(b, (JsonSerializerOptions?)null),
                    v => v.GetHashCode(),
                    v => new Dictionary<string, string>(v)
                )
            );

        // Value conversion: strongly-typed IDs
        modelBuilder.Entity<Product>()
            .Property(p => p.Id)
            .HasConversion(
                id => id.Value,
                value => new ProductId(value)
            );

        // Global query filter: soft delete
        modelBuilder.Entity<Product>()
            .HasQueryFilter(p => !p.IsDeleted);

        // Multi-tenant filter
        modelBuilder.Entity<Order>()
            .HasQueryFilter(o => o.TenantId == _tenantId);

        // Index configuration
        modelBuilder.Entity<Product>()
            .HasIndex(p => p.Sku)
            .IsUnique();

        modelBuilder.Entity<Order>()
            .HasIndex(o => new { o.CustomerId, o.CreatedAt });

        // Owned types (value objects)
        modelBuilder.Entity<Order>()
            .OwnsOne(o => o.ShippingAddress, sa =>
            {
                sa.Property(a => a.Street).HasMaxLength(200);
                sa.Property(a => a.City).HasMaxLength(100);
                sa.Property(a => a.ZipCode).HasMaxLength(20);
            });
    }

    // Automatic audit on SaveChanges
    private string? _tenantId;

    public override async Task<int> SaveChangesAsync(CancellationToken ct = default)
    {
        var entries = ChangeTracker.Entries()
            .Where(e => e.State is EntityState.Added or EntityState.Modified);

        foreach (var entry in entries)
        {
            entry.Property("LastModified").CurrentValue = DateTime.UtcNow;
            entry.Property("ModifiedBy").CurrentValue = "system"; // From auth context
        }

        // Create audit log entries
        var auditEntries = ChangeTracker.Entries()
            .Where(e => e.State is EntityState.Added or EntityState.Modified or EntityState.Deleted)
            .Select(e => new AuditLog
            {
                EntityType = e.Entity.GetType().Name,
                EntityId = e.Property("Id").CurrentValue?.ToString() ?? "",
                Action = e.State.ToString(),
                Changes = JsonSerializer.Serialize(
                    e.Properties
                        .Where(p => e.State == EntityState.Added || p.IsModified)
                        .ToDictionary(p => p.Metadata.Name, p => p.CurrentValue?.ToString())
                ),
                Timestamp = DateTime.UtcNow
            })
            .ToList();

        AuditLogs.AddRange(auditEntries);

        return await base.SaveChangesAsync(ct);
    }
}
```

```csharp
// --- Entity classes ---

// Strongly-typed ID
public readonly record struct ProductId(int Value);

public class Product
{
    public ProductId Id { get; set; }
    public string Name { get; set; } = "";
    public string Sku { get; set; } = "";
    public decimal Price { get; set; }
    public int StockCount { get; set; }
    public bool IsDeleted { get; set; } // Soft delete
    public Dictionary<string, string> Metadata { get; set; } = new();
    public List<OrderLine> OrderLines { get; set; } = new();
}

public class Order
{
    public int Id { get; set; }
    public string CustomerId { get; set; } = "";
    public string TenantId { get; set; } = "";
    public OrderStatus Status { get; set; }
    public Address ShippingAddress { get; set; } = new();
    public decimal TotalAmount { get; set; }
    public DateTime CreatedAt { get; set; }
    public List<OrderLine> Lines { get; set; } = new();
}

public class OrderLine
{
    public int Id { get; set; }
    public int OrderId { get; set; }
    public Order Order { get; set; } = null!;
    public ProductId ProductId { get; set; }
    public Product Product { get; set; } = null!;
    public int Quantity { get; set; }
    public decimal UnitPrice { get; set; }
}

// Value object (owned type)
public class Address
{
    public string Street { get; set; } = "";
    public string City { get; set; } = "";
    public string State { get; set; } = "";
    public string ZipCode { get; set; } = "";
    public string Country { get; set; } = "";
}

public class AuditLog
{
    public int Id { get; set; }
    public string EntityType { get; set; } = "";
    public string EntityId { get; set; } = "";
    public string Action { get; set; } = "";
    public string Changes { get; set; } = "";
    public DateTime Timestamp { get; set; }
}

public enum OrderStatus { Pending, Confirmed, Shipped, Delivered, Cancelled }
```

```csharp
// --- Repository with advanced queries ---

using Microsoft.EntityFrameworkCore;
using System.Linq.Expressions;

public class ProductRepository
{
    private readonly AppDbContext _db;

    public ProductRepository(AppDbContext db) => _db = db;

    // Specification pattern
    public async Task<List<Product>> FindAsync(
        Expression<Func<Product, bool>>? filter = null,
        Func<IQueryable<Product>, IOrderedQueryable<Product>>? orderBy = null,
        int? skip = null,
        int? take = null,
        CancellationToken ct = default)
    {
        IQueryable<Product> query = _db.Products;

        if (filter is not null)
            query = query.Where(filter);

        if (orderBy is not null)
            query = orderBy(query);

        if (skip.HasValue)
            query = query.Skip(skip.Value);

        if (take.HasValue)
            query = query.Take(take.Value);

        return await query.ToListAsync(ct);
    }

    // Compiled query for hot paths
    private static readonly Func<AppDbContext, ProductId, Task<Product?>> _getByIdCompiled =
        EF.CompileAsyncQuery((AppDbContext db, ProductId id) =>
            db.Products.FirstOrDefault(p => p.Id == id));

    public Task<Product?> GetByIdCompiledAsync(ProductId id)
        => _getByIdCompiled(_db, id);

    // Ignoring global query filters
    public async Task<List<Product>> GetAllIncludingDeletedAsync(CancellationToken ct)
    {
        return await _db.Products
            .IgnoreQueryFilters() // Bypass soft delete filter
            .ToListAsync(ct);
    }

    // Raw SQL with interpolation (parameterized automatically)
    public async Task<List<Product>> SearchAsync(string searchTerm, CancellationToken ct)
    {
        return await _db.Products
            .FromSqlInterpolated($@"
                SELECT * FROM ""Products""
                WHERE to_tsvector('english', ""Name"") @@ plainto_tsquery('english', {searchTerm})
                ORDER BY ts_rank(to_tsvector('english', ""Name""), plainto_tsquery('english', {searchTerm})) DESC
            ")
            .ToListAsync(ct);
    }

    // Bulk update (EF Core 7+)
    public async Task<int> MarkDiscontinuedAsync(string category, CancellationToken ct)
    {
        return await _db.Products
            .Where(p => p.Metadata.ContainsKey("category")
                && p.Metadata["category"] == category)
            .ExecuteUpdateAsync(setters => setters
                .SetProperty(p => p.IsDeleted, true)
                .SetProperty(p => EF.Property<DateTime>(p, "LastModified"), DateTime.UtcNow),
                ct);
    }

    // Bulk delete (EF Core 7+)
    public async Task<int> PurgeDeletedAsync(CancellationToken ct)
    {
        return await _db.Products
            .IgnoreQueryFilters()
            .Where(p => p.IsDeleted)
            .ExecuteDeleteAsync(ct);
    }
}
```

EF Core feature comparison:

| Feature | Purpose | EF Core Version |
|---------|---------|----------------|
| Shadow properties | DB columns without C# property | 1.0+ |
| Value conversions | Transform values to/from DB | 2.1+ |
| Global query filters | Auto-applied WHERE clauses | 2.0+ |
| Owned types | Value objects in same table | 2.0+ |
| Compiled queries | Pre-compiled LINQ for perf | 2.0+ |
| `ExecuteUpdate` | Bulk UPDATE without loading | 7.0+ |
| `ExecuteDelete` | Bulk DELETE without loading | 7.0+ |
| JSON columns | Map objects to JSON columns | 7.0+ |
| Complex types | Value objects (non-nullable) | 8.0+ |

Key patterns:
1. Shadow properties (`Property<T>("name")`) store audit fields without polluting domain models
2. Value conversions handle enums-as-strings, JSON columns, and strongly-typed IDs transparently
3. Global query filters enforce soft-delete and multi-tenancy at the DbContext level — use `IgnoreQueryFilters()` to bypass
4. `ExecuteUpdate`/`ExecuteDelete` (EF Core 7+) perform bulk operations without loading entities into memory
5. Override `SaveChangesAsync` for automatic audit logging via the ChangeTracker
6. Use compiled queries for frequently-executed lookups to avoid re-compiling LINQ expressions'''
    ),
    (
        "csharp/source-generators",
        "Show C# source generators for compile-time code generation including incremental generators and practical examples.",
        '''C# source generators for compile-time metaprogramming:

```csharp
// --- Incremental source generator ---

// In a separate .NET Standard 2.0 analyzer project:
// <Project Sdk="Microsoft.NET.Sdk">
//   <PropertyGroup>
//     <TargetFramework>netstandard2.0</TargetFramework>
//     <EnforceExtendedAnalyzerRules>true</EnforceExtendedAnalyzerRules>
//   </PropertyGroup>
//   <ItemGroup>
//     <PackageReference Include="Microsoft.CodeAnalysis.CSharp" Version="4.8.0" />
//   </ItemGroup>
// </Project>

using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Text;
using System.Collections.Immutable;
using System.Text;

// Marker attribute (emitted by the generator itself)
[Generator]
public class AutoDtoGenerator : IIncrementalGenerator
{
    public void Initialize(IncrementalGeneratorInitializationContext context)
    {
        // Step 1: Emit the marker attribute
        context.RegisterPostInitializationOutput(ctx =>
        {
            ctx.AddSource("GenerateDtoAttribute.g.cs", SourceText.From("""
                namespace AutoDto;

                [System.AttributeUsage(System.AttributeTargets.Class)]
                public class GenerateDtoAttribute : System.Attribute
                {
                    public string? Suffix { get; set; } = "Dto";
                }
                """, Encoding.UTF8));
        });

        // Step 2: Find classes with [GenerateDto] attribute
        var classDeclarations = context.SyntaxProvider
            .ForAttributeWithMetadataName(
                "AutoDto.GenerateDtoAttribute",
                predicate: (node, _) => node is ClassDeclarationSyntax,
                transform: (ctx, _) => GetClassInfo(ctx))
            .Where(info => info is not null);

        // Step 3: Generate DTO classes
        context.RegisterSourceOutput(classDeclarations, (spc, classInfo) =>
        {
            if (classInfo is null) return;
            var source = GenerateDtoSource(classInfo);
            spc.AddSource($"{classInfo.ClassName}Dto.g.cs", SourceText.From(source, Encoding.UTF8));
        });
    }

    private static ClassInfo? GetClassInfo(GeneratorAttributeSyntaxContext context)
    {
        if (context.TargetSymbol is not INamedTypeSymbol classSymbol)
            return null;

        var properties = classSymbol.GetMembers()
            .OfType<IPropertySymbol>()
            .Where(p => p.DeclaredAccessibility == Accessibility.Public
                     && p.GetMethod is not null
                     && !p.GetAttributes().Any(a =>
                         a.AttributeClass?.Name == "DtoIgnoreAttribute"))
            .Select(p => new PropertyInfo(
                p.Name,
                p.Type.ToDisplayString(),
                p.Type.IsValueType || p.Type.SpecialType == SpecialType.System_String))
            .ToImmutableArray();

        var ns = classSymbol.ContainingNamespace.IsGlobalNamespace
            ? null
            : classSymbol.ContainingNamespace.ToDisplayString();

        return new ClassInfo(classSymbol.Name, ns, properties);
    }

    private static string GenerateDtoSource(ClassInfo info)
    {
        var sb = new StringBuilder();
        sb.AppendLine("// Auto-generated by AutoDtoGenerator");
        sb.AppendLine("#nullable enable");
        sb.AppendLine();

        if (info.Namespace is not null)
        {
            sb.AppendLine($"namespace {info.Namespace};");
            sb.AppendLine();
        }

        // Generate record DTO
        sb.AppendLine($"public partial record {info.ClassName}Dto(");
        for (int i = 0; i < info.Properties.Length; i++)
        {
            var prop = info.Properties[i];
            var comma = i < info.Properties.Length - 1 ? "," : "";
            sb.AppendLine($"    {prop.TypeName} {prop.Name}{comma}");
        }
        sb.AppendLine(")");
        sb.AppendLine("{");

        // Generate FromEntity method
        sb.AppendLine($"    public static {info.ClassName}Dto FromEntity({info.ClassName} entity) =>");
        sb.AppendLine($"        new(");
        for (int i = 0; i < info.Properties.Length; i++)
        {
            var prop = info.Properties[i];
            var comma = i < info.Properties.Length - 1 ? "," : "";
            sb.AppendLine($"            entity.{prop.Name}{comma}");
        }
        sb.AppendLine("        );");

        sb.AppendLine("}");

        return sb.ToString();
    }

    private record ClassInfo(string ClassName, string? Namespace, ImmutableArray<PropertyInfo> Properties);
    private record PropertyInfo(string Name, string TypeName, bool IsValueType);
}
```

```csharp
// --- Using the generated DTO ---

// In the application project (references the generator):
using AutoDto;

namespace MyApp.Models;

// Mark class for DTO generation
[GenerateDto]
public class Product
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string Sku { get; set; } = "";
    public decimal Price { get; set; }
    public int StockCount { get; set; }

    [DtoIgnore]  // Excluded from generated DTO
    public string InternalNotes { get; set; } = "";
}

// Generated code (ProductDto.g.cs) will look like:
// public partial record ProductDto(
//     int Id,
//     string Name,
//     string Sku,
//     decimal Price,
//     int StockCount)
// {
//     public static ProductDto FromEntity(Product entity) =>
//         new(entity.Id, entity.Name, entity.Sku, entity.Price, entity.StockCount);
// }

// Usage in handlers:
public class ProductHandler
{
    public static ProductDto GetProduct(int id, AppDbContext db)
    {
        var product = db.Products.Find(id);
        return product is not null
            ? ProductDto.FromEntity(product)
            : throw new KeyNotFoundException();
    }

    public static List<ProductDto> ListProducts(AppDbContext db)
    {
        return db.Products
            .Select(p => ProductDto.FromEntity(p))
            .ToList();
    }
}
```

```csharp
// --- Practical source generator: Enum extensions ---

[Generator]
public class EnumExtensionsGenerator : IIncrementalGenerator
{
    public void Initialize(IncrementalGeneratorInitializationContext context)
    {
        // Emit marker attribute
        context.RegisterPostInitializationOutput(ctx =>
        {
            ctx.AddSource("EnumExtensionsAttribute.g.cs", SourceText.From("""
                namespace EnumGen;

                [System.AttributeUsage(System.AttributeTargets.Enum)]
                public class GenerateExtensionsAttribute : System.Attribute { }
                """, Encoding.UTF8));
        });

        var enumDeclarations = context.SyntaxProvider
            .ForAttributeWithMetadataName(
                "EnumGen.GenerateExtensionsAttribute",
                predicate: (node, _) => node is EnumDeclarationSyntax,
                transform: (ctx, _) =>
                {
                    var symbol = (INamedTypeSymbol)ctx.TargetSymbol;
                    var members = symbol.GetMembers()
                        .OfType<IFieldSymbol>()
                        .Where(f => f.HasConstantValue)
                        .Select(f => f.Name)
                        .ToImmutableArray();
                    var ns = symbol.ContainingNamespace.IsGlobalNamespace
                        ? null : symbol.ContainingNamespace.ToDisplayString();
                    return (Name: symbol.Name, Namespace: ns, Members: members);
                });

        context.RegisterSourceOutput(enumDeclarations, (spc, info) =>
        {
            var source = $$"""
                // Auto-generated enum extensions
                #nullable enable
                {{(info.Namespace is not null ? $"namespace {info.Namespace};" : "")}}

                public static class {{info.Name}}Extensions
                {
                    public static string ToStringFast(this {{info.Name}} value) => value switch
                    {
                        {{string.Join("\n        ",
                            info.Members.Select(m => $"{info.Name}.{m} => nameof({info.Name}.{m}),"))}
                        }
                        _ => value.ToString()
                    };

                    public static bool TryParseFast(string? value, out {{info.Name}} result)
                    {
                        result = default;
                        return value switch
                        {
                            {{string.Join("\n            ",
                                info.Members.Select(m =>
                                    $"nameof({info.Name}.{m}) => SetResult(out result, {info.Name}.{m}),"))}
                            }
                            _ => false
                        };
                    }

                    private static bool SetResult(out {{info.Name}} result, {{info.Name}} value)
                    {
                        result = value;
                        return true;
                    }

                    public static IReadOnlyList<{{info.Name}}> GetValues() =>
                        new[] { {{string.Join(", ", info.Members.Select(m => $"{info.Name}.{m}"))}} };

                    public static IReadOnlyList<string> GetNames() =>
                        new[] { {{string.Join(", ", info.Members.Select(m => $"nameof({info.Name}.{m})"))}} };
                }
                """;

            spc.AddSource($"{info.Name}Extensions.g.cs", SourceText.From(source, Encoding.UTF8));
        });
    }
}

// Usage:
// [GenerateExtensions]
// public enum OrderStatus { Pending, Confirmed, Shipped, Delivered, Cancelled }
//
// var name = OrderStatus.Confirmed.ToStringFast(); // "Confirmed" (no reflection)
// var values = OrderStatusExtensions.GetValues();
```

Source generator comparison:

| Approach | When | Speed | Complexity |
|----------|------|-------|-----------|
| Source generators | Compile-time | Zero runtime cost | High (Roslyn API) |
| Reflection | Runtime | Slower (reflection overhead) | Low |
| T4 templates | Pre-build | Zero runtime cost | Medium |
| Code-first (manual) | Development time | Zero runtime cost | Low (but tedious) |
| IL weaving (Fody) | Post-compile | Minimal | High |

Key patterns:
1. Incremental generators (`IIncrementalGenerator`) only re-run when inputs change — much faster than `ISourceGenerator`
2. Emit marker attributes in `RegisterPostInitializationOutput` so users can annotate their code
3. Use `ForAttributeWithMetadataName` to efficiently find annotated declarations without scanning all syntax
4. Generated files must use `.g.cs` suffix and include `// Auto-generated` header
5. Source generators cannot modify existing code — they only add new source files
6. Use raw string literals (`"""..."""`) in the generator for cleaner output templates'''
    ),
    (
        "csharp/pattern-matching-records",
        "Show C# pattern matching with switch expressions, property patterns, list patterns, and records.",
        '''C# pattern matching with records, switch expressions, and advanced patterns:

```csharp
// --- Pattern matching fundamentals ---

using System;
using System.Collections.Generic;
using System.Linq;

// Record types for pattern matching
public abstract record Shape;
public record Circle(double Radius) : Shape;
public record Rectangle(double Width, double Height) : Shape;
public record Triangle(double Base, double Height) : Shape;
public record Polygon(int Sides, double SideLength) : Shape;

public static class ShapeCalculator
{
    // Switch expression with type patterns
    public static double Area(Shape shape) => shape switch
    {
        Circle(var r) => Math.PI * r * r,
        Rectangle(var w, var h) => w * h,
        Triangle(var b, var h) => 0.5 * b * h,
        Polygon(var sides, var len) =>
            (sides * len * len) / (4 * Math.Tan(Math.PI / sides)),
        _ => throw new ArgumentException($"Unknown shape: {shape}")
    };

    // Guard clauses (when)
    public static string Classify(Shape shape) => shape switch
    {
        Circle(var r) when r > 100 => "Large circle",
        Circle(var r) when r > 10 => "Medium circle",
        Circle => "Small circle",
        Rectangle(var w, var h) when w == h => $"Square ({w}x{w})",
        Rectangle(var w, var h) => $"Rectangle ({w}x{h})",
        Triangle(var b, var h) when Math.Abs(b - h) < 0.01 => "Isoceles-like triangle",
        Triangle => "Triangle",
        Polygon(3, _) => "Triangle (polygon)",
        Polygon(4, _) => "Quadrilateral",
        Polygon(var n, _) => $"{n}-gon",
    };

    // Property patterns
    public static bool IsLargeShape(Shape shape) => shape switch
    {
        Circle { Radius: > 50 } => true,
        Rectangle { Width: > 100, Height: > 100 } => true,
        Polygon { Sides: > 6 } => true,
        _ => false,
    };

    // Nested patterns
    public record ShapeGroup(string Name, List<Shape> Shapes);

    public static string DescribeGroup(ShapeGroup group) => group switch
    {
        { Name: "empty", Shapes.Count: 0 } => "Empty group",
        { Shapes.Count: 1, Shapes: [Circle c] } => $"Single circle r={c.Radius}",
        { Shapes.Count: > 10 } => $"Large group: {group.Name}",
        { Name: var name } => $"Group: {name} ({group.Shapes.Count} shapes)",
    };
}
```

```csharp
// --- List patterns (C# 11+) ---

public static class ListPatterns
{
    // List pattern matching
    public static string DescribeList(int[] numbers) => numbers switch
    {
        [] => "Empty",
        [var single] => $"Single: {single}",
        [var first, var second] => $"Pair: {first}, {second}",
        [var first, .., var last] => $"Range: {first} to {last} ({numbers.Length} items)",
    };

    // Slice pattern (..) captures remaining elements
    public static int Sum(Span<int> values) => values switch
    {
        [] => 0,
        [var head, .. var tail] => head + Sum(tail),
    };

    // Pattern matching in validation
    public record Command(string Name, string[] Args);

    public static string ExecuteCommand(Command cmd) => cmd switch
    {
        { Name: "help", Args: [] } =>
            "Usage: tool <command> [args]",

        { Name: "get", Args: [var key] } =>
            $"Getting value for key: {key}",

        { Name: "set", Args: [var key, var value] } =>
            $"Setting {key} = {value}",

        { Name: "delete", Args: [var key, "--force"] } =>
            $"Force deleting: {key}",

        { Name: "delete", Args: [var key] } =>
            $"Deleting: {key} (use --force to skip confirmation)",

        { Name: "import", Args: [var file, ..var options] } =>
            $"Importing {file} with {options.Length} options",

        { Name: var name } =>
            $"Unknown command: {name}",
    };

    // Relational patterns
    public static string TemperatureDescription(double celsius) => celsius switch
    {
        < -40 => "Extreme cold",
        < 0 => "Below freezing",
        >= 0 and < 15 => "Cold",
        >= 15 and < 25 => "Comfortable",
        >= 25 and < 35 => "Warm",
        >= 35 and < 45 => "Hot",
        >= 45 => "Extreme heat",
    };

    // Combining patterns with and/or/not
    public static bool IsWorkingHour(int hour) => hour is >= 9 and <= 17;

    public static bool IsWeekend(DayOfWeek day) =>
        day is DayOfWeek.Saturday or DayOfWeek.Sunday;

    public static bool IsValidPort(int port) =>
        port is > 0 and <= 65535 and not (80 or 443);
}
```

```csharp
// --- Records: advanced patterns ---

// Record with init-only properties and custom equality
public record User
{
    public required int Id { get; init; }
    public required string Name { get; init; }
    public required string Email { get; init; }
    public string? Bio { get; init; }
    public IReadOnlyList<string> Roles { get; init; } = Array.Empty<string>();

    // Custom equality (ignore Bio for comparison)
    public virtual bool Equals(User? other) =>
        other is not null &&
        Id == other.Id &&
        Name == other.Name &&
        Email == other.Email;

    public override int GetHashCode() =>
        HashCode.Combine(Id, Name, Email);
}

// Record with factory and validation
public record Email
{
    public string Value { get; }

    private Email(string value) => Value = value;

    public static Email? TryCreate(string? input)
    {
        if (string.IsNullOrWhiteSpace(input)) return null;
        if (!input.Contains('@')) return null;
        return new Email(input.Trim().ToLowerInvariant());
    }

    // Implicit conversion
    public static implicit operator string(Email email) => email.Value;
    public override string ToString() => Value;
}

// Record with 'with' expressions for immutable updates
public record OrderState(
    int OrderId,
    OrderStatus Status,
    List<string> Items,
    decimal Total,
    DateTime LastModified)
{
    // State transitions using 'with'
    public OrderState Confirm() => this with
    {
        Status = OrderStatus.Confirmed,
        LastModified = DateTime.UtcNow
    };

    public OrderState Ship(string trackingNumber) => this with
    {
        Status = OrderStatus.Shipped,
        LastModified = DateTime.UtcNow
    };

    public OrderState Cancel(string reason) => this with
    {
        Status = OrderStatus.Cancelled,
        LastModified = DateTime.UtcNow
    };
}

// Discriminated union with records (before C# union types)
public abstract record Result<T>
{
    public record Success(T Value) : Result<T>;
    public record Failure(string Error, Exception? Exception = null) : Result<T>;

    public TOut Match<TOut>(Func<T, TOut> onSuccess, Func<string, TOut> onFailure) =>
        this switch
        {
            Success(var value) => onSuccess(value),
            Failure(var error, _) => onFailure(error),
            _ => throw new InvalidOperationException()
        };

    public Result<TOut> Map<TOut>(Func<T, TOut> fn) => this switch
    {
        Success(var value) => new Result<TOut>.Success(fn(value)),
        Failure(var error, var ex) => new Result<TOut>.Failure(error, ex),
        _ => throw new InvalidOperationException()
    };

    public async Task<Result<TOut>> MapAsync<TOut>(Func<T, Task<TOut>> fn) =>
        this switch
        {
            Success(var value) => new Result<TOut>.Success(await fn(value)),
            Failure(var error, var ex) => new Result<TOut>.Failure(error, ex),
            _ => throw new InvalidOperationException()
        };
}

// Usage
public class Example
{
    public static void Run()
    {
        Result<int> result = new Result<int>.Success(42);
        var message = result.Match(
            onSuccess: v => $"Got: {v}",
            onFailure: e => $"Error: {e}");

        var doubled = result.Map(v => v * 2);
    }
}

public enum OrderStatus { Pending, Confirmed, Shipped, Delivered, Cancelled }
```

C# pattern types:

| Pattern | C# Version | Example |
|---------|-----------|---------|
| Type pattern | 7.0 | `x is string s` |
| Constant pattern | 7.0 | `x is null`, `x is 42` |
| Property pattern | 8.0 | `{ Name: "Alice", Age: > 18 }` |
| Positional pattern | 8.0 | `(var x, var y)` for deconstructable types |
| Switch expression | 8.0 | `x switch { pattern => result }` |
| Relational pattern | 9.0 | `x is > 0 and < 100` |
| Logical pattern | 9.0 | `x is not null`, `x is A or B` |
| List pattern | 11.0 | `[first, .., last]` |
| Slice pattern | 11.0 | `[_, .. var rest]` |

Key patterns:
1. Records provide value semantics (structural equality), `with` expressions, and deconstruction for free
2. Switch expressions must be exhaustive — the compiler warns if patterns do not cover all cases
3. List patterns (`[first, .., last]`) match array/list structure directly in pattern matching
4. Relational patterns (`> 0 and < 100`) replace verbose if-else chains for range checking
5. Use `Result<T>` records with `Match` for monadic error handling without exceptions
6. The `with` expression creates a modified copy of a record — all other properties are preserved'''
    ),
]
