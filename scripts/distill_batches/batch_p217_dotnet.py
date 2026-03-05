"""C#/.NET 9 -- primary constructors, collection expressions, interceptors, AOT compilation, minimal APIs, Aspire cloud-native stack, source generators."""

PAIRS = [
    (
        "dotnet/primary-constructors-collections",
        "Show C# 12/13 primary constructors for classes and structs, collection expressions, and other modern C# syntax improvements for cleaner, more concise code.",
        '''C# 12 introduced primary constructors for all types (not just records) and collection expressions for uniform collection initialization. These features significantly reduce boilerplate.

```csharp
// --- Primary Constructors for classes and structs (C# 12) ---

// Before: classic constructor with field assignments
public class OldUserService
{
    private readonly IUserRepository _repo;
    private readonly ILogger<OldUserService> _logger;
    private readonly IEmailService _email;

    public OldUserService(
        IUserRepository repo,
        ILogger<OldUserService> logger,
        IEmailService email)
    {
        _repo = repo;
        _logger = logger;
        _email = email;
    }

    public async Task<User> GetUser(int id) => await _repo.FindByIdAsync(id);
}

// After: primary constructor -- parameters available throughout the class
public class UserService(
    IUserRepository repo,
    ILogger<UserService> logger,
    IEmailService email)
{
    // Parameters are captured and available in all members
    // No need for explicit fields or assignments

    public async Task<User> GetUserAsync(int id)
    {
        logger.LogInformation("Fetching user {Id}", id);
        return await repo.FindByIdAsync(id)
            ?? throw new NotFoundException($"User {id} not found");
    }

    public async Task<User> CreateUserAsync(CreateUserRequest request)
    {
        logger.LogInformation("Creating user {Email}", request.Email);
        var user = new User(request.Name, request.Email);
        await repo.SaveAsync(user);
        await email.SendWelcomeAsync(user.Email, user.Name);
        return user;
    }

    // Can still have explicit fields alongside primary constructor
    private readonly ConcurrentDictionary<int, User> _cache = new();

    public async Task<User> GetCachedUserAsync(int id)
    {
        return _cache.GetOrAdd(id, _ =>
            repo.FindByIdAsync(id).GetAwaiter().GetResult());
    }
}

// Primary constructors on structs
public readonly struct Point(double x, double y)
{
    public double X { get; } = x;
    public double Y { get; } = y;
    public double DistanceTo(Point other) =>
        Math.Sqrt(Math.Pow(X - other.X, 2) + Math.Pow(Y - other.Y, 2));
}

// Primary constructor with inheritance
public class BaseService(ILogger logger)
{
    protected void Log(string message) => logger.LogInformation(message);
}

public class OrderService(
    ILogger<OrderService> logger,
    IOrderRepository orderRepo)
    : BaseService(logger)  // pass to base primary constructor
{
    public async Task<Order> GetOrderAsync(int id)
    {
        Log($"Fetching order {id}");
        return await orderRepo.FindByIdAsync(id);
    }
}
```

```csharp
// --- Collection Expressions (C# 12) ---

// Before: different syntax for every collection type
List<int> oldList = new List<int> { 1, 2, 3 };
int[] oldArray = new int[] { 1, 2, 3 };

// After: uniform syntax with []
List<int> list = [1, 2, 3];
int[] array = [1, 2, 3];
Span<int> span = [1, 2, 3];
ImmutableArray<int> imm = [1, 2, 3];
HashSet<int> set = [1, 2, 3];

// Spread operator (..) for combining collections
int[] first = [1, 2, 3];
int[] second = [4, 5, 6];
int[] combined = [..first, ..second];        // [1, 2, 3, 4, 5, 6]
int[] withExtra = [0, ..first, ..second, 7]; // [0, 1, 2, 3, 4, 5, 6, 7]

// Conditional elements with spread
bool includeDefaults = true;
int[] defaults = [10, 20, 30];
int[] config = [1, 2, ..(includeDefaults ? defaults : [])];

// Collection expressions in method signatures
public static class Validator
{
    public static ValidationResult Validate(User user)
    {
        List<string> errors = [];  // empty collection

        if (string.IsNullOrWhiteSpace(user.Name))
            errors.Add("Name is required");
        if (string.IsNullOrWhiteSpace(user.Email))
            errors.Add("Email is required");
        if (user.Age is < 0 or > 150)
            errors.Add("Age is invalid");

        return new ValidationResult(errors is [], errors);
    }
}

// Lock object (C# 13) -- dedicated Lock type
public class ThreadSafeCounter
{
    private readonly Lock _lock = new();
    private int _count;

    public int Increment()
    {
        lock (_lock)  // uses Lock.EnterScope() -- faster than Monitor
        {
            return ++_count;
        }
    }
}

// params collections (C# 13) -- params works with any collection type
public static T[] Combine<T>(params ReadOnlySpan<T> items) =>
    items.ToArray();

// Alias any type (C# 12)
using Point2D = (double X, double Y);
using UserId = int;
using UserMap = System.Collections.Generic.Dictionary<int, User>;
```

Modern C# feature summary:

| Feature | C# Version | Replaces |
|---|---|---|
| Primary constructors | C# 12 | Constructor + field boilerplate |
| Collection expressions `[]` | C# 12 | `new List<T> { }`, `new T[] { }` |
| Spread `..` in collections | C# 12 | `Concat`, `AddRange` |
| `using` type aliases | C# 12 | Only namespace aliases before |
| Inline arrays | C# 12 | `unsafe fixed` buffers |
| `params` collections | C# 13 | Only `params T[]` before |
| `Lock` type | C# 13 | `object` + `Monitor` |
| Partial properties | C# 13 | Full property in generated code |

Key patterns:
- **Primary constructors** work on classes, structs, and records -- use for DI in services
- **Collection expressions** unify initialization across List, Array, Span, ImmutableArray
- **Spread operator** (`..`) makes collection composition clean and readable
- Primary constructor parameters are captured as fields -- mutable unless `readonly struct`
- **Do not expose primary constructor parameters** as public -- use explicit properties if needed'''
    ),
    (
        "dotnet/aot-compilation",
        "Show how to configure .NET 9 Native AOT compilation for web APIs and console apps, including trimming, reflection handling, source generators, and deployment considerations.",
        '''Native AOT in .NET 9 compiles C# directly to native code, producing self-contained executables with instant startup and no JIT. This is critical for serverless, CLI tools, and microservices.

```csharp
// --- Program.cs: Minimal API configured for AOT ---

// .csproj configuration:
// <PropertyGroup>
//     <PublishAot>true</PublishAot>
//     <InvariantGlobalization>true</InvariantGlobalization>
//     <TrimMode>full</TrimMode>
// </PropertyGroup>

using System.Text.Json.Serialization;

var builder = WebApplication.CreateSlimBuilder(args);

// Use source-generated JSON serialization (no reflection needed)
builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.TypeInfoResolverChain.Insert(0,
        AppJsonContext.Default);
});

var app = builder.Build();

// Minimal API endpoints -- AOT compatible
var todos = new List<Todo>();
var nextId = 1;

app.MapGet("/todos", () => todos);

app.MapGet("/todos/{id}", (int id) =>
    todos.FirstOrDefault(t => t.Id == id) is { } todo
        ? Results.Ok(todo)
        : Results.NotFound());

app.MapPost("/todos", (CreateTodoRequest request) =>
{
    var todo = new Todo(nextId++, request.Title, request.Description, false);
    todos.Add(todo);
    return Results.Created($"/todos/{todo.Id}", todo);
});

app.MapPut("/todos/{id}/complete", (int id) =>
{
    var index = todos.FindIndex(t => t.Id == id);
    if (index == -1) return Results.NotFound();
    todos[index] = todos[index] with { IsComplete = true };
    return Results.Ok(todos[index]);
});

app.MapDelete("/todos/{id}", (int id) =>
{
    var removed = todos.RemoveAll(t => t.Id == id);
    return removed > 0 ? Results.NoContent() : Results.NotFound();
});

app.Run();

// --- Records and DTOs ---
public record Todo(int Id, string Title, string? Description, bool IsComplete);
public record CreateTodoRequest(string Title, string? Description);

// --- Source-generated JSON context (required for AOT) ---
[JsonSerializable(typeof(List<Todo>))]
[JsonSerializable(typeof(Todo))]
[JsonSerializable(typeof(CreateTodoRequest))]
[JsonSourceGenerationOptions(
    PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
internal partial class AppJsonContext : JsonSerializerContext
{
}
```

```csharp
// --- AOT-compatible service with dependency injection ---

public interface IProductService
{
    Task<Product?> GetByIdAsync(int id);
    Task<IReadOnlyList<Product>> SearchAsync(string query, int limit);
    Task<Product> CreateAsync(CreateProductRequest request);
}

public class ProductService(
    IProductRepository repository,
    ILogger<ProductService> logger) : IProductService
{
    public async Task<Product?> GetByIdAsync(int id)
    {
        logger.LogInformation("Getting product {Id}", id);
        return await repository.FindByIdAsync(id);
    }

    public async Task<IReadOnlyList<Product>> SearchAsync(string query, int limit)
    {
        return await repository.SearchAsync(query, Math.Min(limit, 100));
    }

    public async Task<Product> CreateAsync(CreateProductRequest request)
    {
        var product = new Product(
            Id: 0,
            Name: request.Name,
            Price: request.Price,
            Category: request.Category,
            CreatedAt: DateTimeOffset.UtcNow);
        return await repository.SaveAsync(product);
    }
}

// Register services -- AOT needs concrete types
public static class ServiceRegistration
{
    public static IServiceCollection AddProductServices(
        this IServiceCollection services)
    {
        services.AddSingleton<IProductRepository, InMemoryProductRepository>();
        services.AddScoped<IProductService, ProductService>();
        return services;
    }
}

public record Product(
    int Id, string Name, decimal Price,
    string Category, DateTimeOffset CreatedAt);

public record CreateProductRequest(string Name, decimal Price, string Category);

// AOT publish commands:
// dotnet publish -c Release -r linux-x64
// dotnet publish -c Release -r win-x64
// dotnet publish -c Release -r osx-arm64
//
// Docker (chiseled image -- ~30MB):
// FROM mcr.microsoft.com/dotnet/nightly/runtime-deps:9.0-noble-chiseled
// COPY --from=build /app/publish /app
// ENTRYPOINT ["/app/myapi"]
```

AOT vs JIT comparison:

| Metric | JIT (.NET 9) | Native AOT |
|---|---|---|
| Startup time | 100-500 ms | 10-50 ms |
| Memory (RSS) | 50-150 MB | 15-40 MB |
| Peak throughput | Higher (tiered JIT) | ~90% of JIT |
| Binary size | Needs .NET runtime | 10-30 MB self-contained |
| Reflection | Full support | Limited (needs source gen) |
| Docker image | 100+ MB | 30 MB (chiseled) |

AOT compatibility checklist:
- **Use `JsonSerializerContext`** for all JSON serialization (no reflection)
- **Avoid `Assembly.LoadFrom`** and runtime code generation
- **Use `WebApplication.CreateSlimBuilder`** instead of `CreateBuilder` (lighter)
- **Mark dynamic code** with `[DynamicallyAccessedMembers]` or `[RequiresUnreferencedCode]`
- **Run publish with warnings enabled**: `dotnet publish -c Release` and fix all trim warnings
- **Test with AOT early** -- some libraries are not AOT-compatible'''
    ),
    (
        "dotnet/aspire-cloud-native",
        "Show .NET Aspire for building cloud-native distributed applications, including AppHost orchestration, service discovery, health checks, telemetry, and component integration.",
        '''.NET Aspire is a cloud-native application stack that simplifies building distributed applications with built-in service discovery, telemetry, health checks, and container orchestration.

```csharp
// --- AppHost project: orchestration entry point ---
// MyApp.AppHost/Program.cs

var builder = DistributedApplication.CreateBuilder(args);

// Add backing services (containers managed by Aspire)
var postgres = builder.AddPostgres("postgres")
    .WithDataVolume("postgres-data")
    .WithPgAdmin();

var catalogDb = postgres.AddDatabase("catalogdb");
var orderDb = postgres.AddDatabase("orderdb");

var redis = builder.AddRedis("redis")
    .WithRedisCommander();

var rabbitmq = builder.AddRabbitMQ("messaging")
    .WithManagementPlugin();

// Add application projects
var catalogApi = builder.AddProject<Projects.CatalogApi>("catalog-api")
    .WithReference(catalogDb)
    .WithReference(redis)
    .WithExternalHttpEndpoints();

var orderApi = builder.AddProject<Projects.OrderApi>("order-api")
    .WithReference(orderDb)
    .WithReference(rabbitmq)
    .WithReference(catalogApi);  // discovers catalog-api via name

var frontend = builder.AddProject<Projects.WebFrontend>("frontend")
    .WithReference(catalogApi)
    .WithReference(orderApi)
    .WithExternalHttpEndpoints();

builder.Build().Run();
// Running dotnet run in AppHost:
// 1. Starts PostgreSQL, Redis, RabbitMQ containers
// 2. Launches all .NET projects with correct connection strings
// 3. Opens the Aspire Dashboard (traces, logs, metrics)
```

```csharp
// --- Service project: CatalogApi ---

var builder = WebApplication.CreateBuilder(args);

// Aspire service defaults: telemetry, health checks, resilience
builder.AddServiceDefaults();

// Aspire component: PostgreSQL with EF Core
builder.AddNpgsqlDbContext<CatalogDbContext>("catalogdb");

// Aspire component: Redis distributed cache
builder.AddRedisDistributedCache("redis");

builder.Services.AddScoped<ICatalogService, CatalogService>();

var app = builder.Build();
app.MapDefaultEndpoints();

app.MapGet("/api/catalog/products", async (
    ICatalogService service, string? category, int page = 1) =>
    await service.GetProductsAsync(category, page))
    .CacheOutput(p => p.Expire(TimeSpan.FromMinutes(5)));

app.Run();

// --- CatalogService with caching and telemetry ---

using Microsoft.Extensions.Caching.Distributed;
using System.Diagnostics;

public class CatalogService(
    CatalogDbContext db,
    IDistributedCache cache,
    ILogger<CatalogService> logger) : ICatalogService
{
    private static readonly ActivitySource Activity = new("CatalogApi");

    public async Task<PagedResult<Product>> GetProductsAsync(
        string? category, int page)
    {
        using var activity = Activity.StartActivity("GetProducts");
        activity?.SetTag("catalog.category", category ?? "all");

        var cacheKey = $"products:{category}:{page}";
        var cached = await cache.GetStringAsync(cacheKey);
        if (cached is not null)
        {
            activity?.SetTag("cache.hit", true);
            return System.Text.Json.JsonSerializer
                .Deserialize<PagedResult<Product>>(cached)!;
        }

        activity?.SetTag("cache.hit", false);
        var query = db.Products.AsQueryable();
        if (!string.IsNullOrEmpty(category))
            query = query.Where(p => p.Category == category);

        var items = await query.OrderBy(p => p.Name)
            .Skip((page - 1) * 20).Take(20).ToListAsync();
        var total = await query.CountAsync();
        var result = new PagedResult<Product>(items, total, page, 20);

        await cache.SetStringAsync(cacheKey,
            System.Text.Json.JsonSerializer.Serialize(result),
            new DistributedCacheEntryOptions
            {
                AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(5)
            });

        return result;
    }
}
```

```csharp
// --- ServiceDefaults: shared configuration ---

using OpenTelemetry;
using OpenTelemetry.Metrics;
using OpenTelemetry.Trace;

public static class Extensions
{
    public static IHostApplicationBuilder AddServiceDefaults(
        this IHostApplicationBuilder builder)
    {
        builder.ConfigureOpenTelemetry();
        builder.AddDefaultHealthChecks();

        builder.Services.ConfigureHttpClientDefaults(http =>
        {
            http.AddStandardResilienceHandler();
            http.AddServiceDiscovery();
        });

        return builder;
    }

    public static IHostApplicationBuilder ConfigureOpenTelemetry(
        this IHostApplicationBuilder builder)
    {
        builder.Logging.AddOpenTelemetry(o =>
        {
            o.IncludeFormattedMessage = true;
            o.IncludeScopes = true;
        });

        builder.Services.AddOpenTelemetry()
            .WithMetrics(m => m
                .AddAspNetCoreInstrumentation()
                .AddHttpClientInstrumentation()
                .AddRuntimeInstrumentation())
            .WithTracing(t => t
                .AddAspNetCoreInstrumentation()
                .AddHttpClientInstrumentation()
                .AddEntityFrameworkCoreInstrumentation()
                .AddSource("CatalogApi", "OrderApi"));

        return builder;
    }

    public static IHostApplicationBuilder AddDefaultHealthChecks(
        this IHostApplicationBuilder builder)
    {
        builder.Services.AddHealthChecks()
            .AddCheck("self", () =>
                Microsoft.Extensions.Diagnostics.HealthChecks
                    .HealthCheckResult.Healthy(), ["live"]);
        return builder;
    }

    public static WebApplication MapDefaultEndpoints(this WebApplication app)
    {
        app.MapHealthChecks("/health");
        app.MapHealthChecks("/alive", new()
        {
            Predicate = r => r.Tags.Contains("live")
        });
        return app;
    }
}
```

Aspire architecture overview:

| Component | Purpose | Example |
|---|---|---|
| AppHost | Orchestration + service discovery | `builder.AddProject()`, `builder.AddPostgres()` |
| ServiceDefaults | Shared telemetry + resilience | OpenTelemetry, health checks, retries |
| Components | Pre-configured integrations | `AddNpgsqlDbContext`, `AddRedisDistributedCache` |
| Dashboard | Observability UI | Traces, logs, metrics, resource graph |

Key patterns:
- **AppHost orchestrates everything** -- databases, caches, brokers, and your services
- **`WithReference()`** provides both service discovery and connection string injection
- **Service defaults** give you OpenTelemetry, health checks, and HTTP resilience
- **Components** configure connection pooling, health checks, and telemetry automatically
- **Dashboard** shows distributed traces across services with correlated logs
- **Local dev** uses containers; **production** uses real cloud resources'''
    ),
    (
        "dotnet/source-generators",
        "Show how to build C# source generators for compile-time code generation, including incremental generators, syntax analysis, and practical examples like auto-mapping.",
        '''Source generators in .NET produce C# code at compile time, eliminating reflection overhead and enabling AOT compatibility. Incremental generators only re-run when relevant source changes.

```csharp
// --- Incremental Source Generator: Auto-mapper ---
// Generator project targets netstandard2.0
// <PackageReference Include="Microsoft.CodeAnalysis.CSharp" Version="4.12.0" />

using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Text;
using System.Collections.Immutable;
using System.Text;

namespace AutoMapper.Generator;

[Generator]
public class AutoMapperGenerator : IIncrementalGenerator
{
    public void Initialize(IncrementalGeneratorInitializationContext context)
    {
        // Step 1: Register the marker attribute
        context.RegisterPostInitializationOutput(ctx =>
        {
            ctx.AddSource("AutoMapAttribute.g.cs", SourceText.From(
                @"namespace AutoMapper;
                [System.AttributeUsage(System.AttributeTargets.Class)]
                public class AutoMapAttribute<TSource> : System.Attribute { }",
                Encoding.UTF8));
        });

        // Step 2: Find classes with [AutoMap<T>]
        var classDeclarations = context.SyntaxProvider
            .ForAttributeWithMetadataName(
                "AutoMapper.AutoMapAttribute`1",
                predicate: (node, _) => node is ClassDeclarationSyntax,
                transform: GetMapInfo)
            .Where(info => info is not null);

        // Step 3: Generate mapping code
        context.RegisterSourceOutput(classDeclarations,
            (spc, mapInfo) => GenerateMapper(spc, mapInfo!.Value));
    }

    private static MapInfo? GetMapInfo(
        GeneratorAttributeSyntaxContext context,
        CancellationToken ct)
    {
        var classSymbol = (INamedTypeSymbol)context.TargetSymbol;
        var attribute = context.Attributes[0];

        if (attribute.AttributeClass?.TypeArguments.FirstOrDefault()
            is not INamedTypeSymbol sourceType)
            return null;

        var sourceProps = sourceType.GetMembers()
            .OfType<IPropertySymbol>()
            .Where(p => p.DeclaredAccessibility == Accessibility.Public
                     && p.GetMethod is not null)
            .Select(p => new PropInfo(p.Name, p.Type.ToDisplayString()))
            .ToImmutableArray();

        var targetProps = classSymbol.GetMembers()
            .OfType<IPropertySymbol>()
            .Where(p => p.DeclaredAccessibility == Accessibility.Public
                     && p.SetMethod is not null)
            .Select(p => new PropInfo(p.Name, p.Type.ToDisplayString()))
            .ToImmutableArray();

        return new MapInfo(
            classSymbol.ContainingNamespace.ToDisplayString(),
            classSymbol.Name,
            sourceType.ToDisplayString(),
            sourceProps, targetProps);
    }

    private static void GenerateMapper(
        SourceProductionContext context, MapInfo info)
    {
        var sb = new StringBuilder();
        sb.AppendLine($"namespace {info.Namespace};");
        sb.AppendLine($"public partial class {info.ClassName}");
        sb.AppendLine("{");
        sb.AppendLine($"    public static {info.ClassName} MapFrom(");
        sb.AppendLine($"        {info.SourceFullName} source)");
        sb.AppendLine("    {");
        sb.AppendLine($"        return new {info.ClassName}");
        sb.AppendLine("        {");

        foreach (var targetProp in info.TargetProps)
        {
            var match = info.SourceProps.FirstOrDefault(
                s => s.Name == targetProp.Name
                  && s.TypeName == targetProp.TypeName);
            if (match.Name is not null)
            {
                sb.AppendLine(
                    $"            {targetProp.Name} = source.{match.Name},");
            }
        }

        sb.AppendLine("        };");
        sb.AppendLine("    }");
        sb.AppendLine("}");

        context.AddSource($"{info.ClassName}.Mapper.g.cs",
            SourceText.From(sb.ToString(), Encoding.UTF8));
    }
}

record struct PropInfo(string Name, string TypeName);
record struct MapInfo(
    string Namespace,
    string ClassName,
    string SourceFullName,
    ImmutableArray<PropInfo> SourceProps,
    ImmutableArray<PropInfo> TargetProps);
```

```csharp
// --- Usage of the AutoMapper generator ---

using AutoMapper;

public class UserEntity
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string Email { get; set; } = "";
    public DateTime CreatedAt { get; set; }
    public string PasswordHash { get; set; } = ""; // will NOT map
}

// Generator creates MapFrom() automatically at compile time
[AutoMap<UserEntity>]
public partial class UserDto
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string Email { get; set; } = "";
    public DateTime CreatedAt { get; set; }
    // PasswordHash not present here, so it is not mapped
}

// Generated code (compile-time, visible in IDE):
// public partial class UserDto
// {
//     public static UserDto MapFrom(UserEntity source)
//     {
//         return new UserDto
//         {
//             Id = source.Id,
//             Name = source.Name,
//             Email = source.Email,
//             CreatedAt = source.CreatedAt,
//         };
//     }
// }

// Usage:
var entity = new UserEntity
{
    Id = 1, Name = "Alice", Email = "alice@test.com",
    CreatedAt = DateTime.UtcNow, PasswordHash = "secret"
};
var dto = UserDto.MapFrom(entity); // zero reflection, AOT-safe
// dto.Id == 1, dto.Name == "Alice", no PasswordHash
```

```csharp
// --- Diagnostic reporting from generators ---

[Generator]
public class ValidationGenerator : IIncrementalGenerator
{
    private static readonly DiagnosticDescriptor MissingPartial = new(
        id: "VALID001",
        title: "Class must be partial",
        messageFormat: "Class '{0}' must be partial to use [AutoValidate]",
        category: "Validation",
        DiagnosticSeverity.Error,
        isEnabledByDefault: true);

    public void Initialize(IncrementalGeneratorInitializationContext context)
    {
        var classes = context.SyntaxProvider
            .ForAttributeWithMetadataName(
                "Validation.AutoValidateAttribute",
                predicate: (node, _) => node is ClassDeclarationSyntax,
                transform: (ctx, ct) =>
                {
                    var decl = (ClassDeclarationSyntax)ctx.TargetNode;
                    var symbol = (INamedTypeSymbol)ctx.TargetSymbol;
                    bool isPartial = decl.Modifiers.Any(
                        m => m.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind
                            .PartialKeyword));
                    return (symbol, isPartial, decl.GetLocation());
                });

        context.RegisterSourceOutput(classes, (spc, info) =>
        {
            if (!info.isPartial)
            {
                spc.ReportDiagnostic(Diagnostic.Create(
                    MissingPartial, info.Item3, info.symbol.Name));
                return;
            }
            // Generate validation logic here...
        });
    }
}
```

Source generator best practices:

| Practice | Why |
|---|---|
| Use `IIncrementalGenerator` | Only regenerates when inputs change (faster builds) |
| Target `netstandard2.0` | Compatible with all .NET SDK versions |
| Report diagnostics | Guide users with compiler warnings/errors |
| Use `ForAttributeWithMetadataName` | Efficient -- only examines attributed types |
| Output `*.g.cs` files | Convention for generated files |
| Make target types `partial` | Generated code extends user code |

Key patterns:
- **Marker attributes** trigger generation on specific types
- **Incremental pipeline**: SyntaxProvider -> transform -> RegisterSourceOutput
- Source generators run at **compile time** -- zero runtime reflection
- Generated code is visible in IDE (navigate to generated source)
- **Test generators** with `CSharpGeneratorDriver.RunGeneratorsAndUpdateCompilation()`'''
    ),
    (
        "dotnet/minimal-apis-advanced",
        "Show advanced .NET 9 minimal API patterns including endpoint filters, route groups, typed results, parameter binding, OpenAPI integration, and rate limiting.",
        '''Minimal APIs in .NET 9 are production-ready with endpoint filters, typed results, OpenAPI, and middleware integration. Here are advanced patterns for building real-world APIs.

```csharp
// --- Program.cs: Full-featured minimal API ---

using Microsoft.AspNetCore.Http.HttpResults;
using Microsoft.AspNetCore.RateLimiting;
using System.Threading.RateLimiting;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddOpenApi();

// Rate limiting
builder.Services.AddRateLimiter(options =>
{
    options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;

    // Fixed window: 100 requests per minute per IP
    options.AddPolicy("fixed", context =>
        RateLimitPartition.GetFixedWindowLimiter(
            partitionKey: context.Connection.RemoteIpAddress?.ToString()
                ?? "unknown",
            factory: _ => new FixedWindowRateLimiterOptions
            {
                PermitLimit = 100,
                Window = TimeSpan.FromMinutes(1),
                QueueLimit = 10,
                QueueProcessingOrder = QueueProcessingOrder.OldestFirst
            }));

    // Token bucket for API keys
    options.AddPolicy("api-key", context =>
    {
        var apiKey = context.Request.Headers["X-API-Key"].ToString();
        return RateLimitPartition.GetTokenBucketLimiter(
            partitionKey: apiKey,
            factory: _ => new TokenBucketRateLimiterOptions
            {
                TokenLimit = 1000,
                ReplenishmentPeriod = TimeSpan.FromHours(1),
                TokensPerPeriod = 1000,
                QueueLimit = 50
            });
    });
});

// Output caching
builder.Services.AddOutputCache(options =>
{
    options.AddBasePolicy(p => p.Expire(TimeSpan.FromSeconds(30)));
    options.AddPolicy("products", p =>
        p.Expire(TimeSpan.FromMinutes(5)).Tag("products"));
});

builder.Services.AddScoped<IProductService, ProductService>();

var app = builder.Build();

app.UseRateLimiter();
app.UseOutputCache();
app.MapOpenApi();
app.MapProductEndpoints();

app.Run();
```

```csharp
// --- Endpoint definitions with typed results ---

public static class ProductEndpoints
{
    public static void MapProductEndpoints(this WebApplication app)
    {
        var group = app.MapGroup("/api/products")
            .WithTags("Products")
            .RequireRateLimiting("fixed")
            .AddEndpointFilter<ValidationFilter>();

        // Typed results -- OpenAPI schema generated automatically
        group.MapGet("/", GetProducts)
            .CacheOutput("products")
            .WithName("GetProducts")
            .WithSummary("List products with pagination");

        group.MapGet("/{id:int}", GetProductById)
            .WithName("GetProductById");

        group.MapPost("/", CreateProduct)
            .RequireRateLimiting("api-key")
            .AddEndpointFilter<AuditLogFilter>()
            .WithName("CreateProduct");

        group.MapDelete("/{id:int}", DeleteProduct)
            .RequireAuthorization("admin")
            .WithName("DeleteProduct");
    }

    // Typed result return types -- compiler verifies all status codes
    static async Task<Results<Ok<PagedResult<ProductDto>>, BadRequest<string>>>
        GetProducts(
            IProductService service,
            string? category = null,
            int page = 1,
            int pageSize = 20)
    {
        if (page < 1 || pageSize < 1 || pageSize > 100)
            return TypedResults.BadRequest("Invalid pagination parameters");

        var result = await service.GetProductsAsync(
            category, page, pageSize);
        return TypedResults.Ok(result);
    }

    static async Task<Results<Ok<ProductDto>, NotFound>>
        GetProductById(int id, IProductService service)
    {
        var product = await service.GetByIdAsync(id);
        return product is not null
            ? TypedResults.Ok(product)
            : TypedResults.NotFound();
    }

    static async Task<Results<Created<ProductDto>, ValidationProblem>>
        CreateProduct(
            CreateProductRequest request, IProductService service)
    {
        var product = await service.CreateAsync(request);
        return TypedResults.Created(
            $"/api/products/{product.Id}", product);
    }

    static async Task<Results<NoContent, NotFound>>
        DeleteProduct(int id, IProductService service)
    {
        var deleted = await service.DeleteAsync(id);
        return deleted
            ? TypedResults.NoContent()
            : TypedResults.NotFound();
    }
}
```

```csharp
// --- Endpoint filters (middleware for individual endpoints) ---

public class ValidationFilter : IEndpointFilter
{
    public async ValueTask<object?> InvokeAsync(
        EndpointFilterInvocationContext context,
        EndpointFilterDelegate next)
    {
        foreach (var arg in context.Arguments)
        {
            if (arg is null) continue;

            var results = new List<
                System.ComponentModel.DataAnnotations.ValidationResult>();
            var ctx = new System.ComponentModel.DataAnnotations
                .ValidationContext(arg);

            if (!System.ComponentModel.DataAnnotations.Validator
                .TryValidateObject(arg, ctx, results, true))
            {
                var errors = results
                    .GroupBy(r => r.MemberNames.FirstOrDefault() ?? "")
                    .ToDictionary(
                        g => g.Key,
                        g => g.Select(r => r.ErrorMessage ?? "Invalid")
                              .ToArray());

                return Results.ValidationProblem(errors);
            }
        }

        return await next(context);
    }
}

// Audit log filter -- logs all mutations
public class AuditLogFilter(
    ILogger<AuditLogFilter> logger) : IEndpointFilter
{
    public async ValueTask<object?> InvokeAsync(
        EndpointFilterInvocationContext context,
        EndpointFilterDelegate next)
    {
        var method = context.HttpContext.Request.Method;
        var path = context.HttpContext.Request.Path;
        var user = context.HttpContext.User.Identity?.Name ?? "anonymous";

        logger.LogInformation(
            "Audit: {Method} {Path} by {User}", method, path, user);

        var sw = System.Diagnostics.Stopwatch.StartNew();
        var result = await next(context);
        sw.Stop();

        logger.LogInformation(
            "Audit: {Method} {Path} completed in {Ms}ms",
            method, path, sw.ElapsedMilliseconds);

        return result;
    }
}

// Custom parameter binding
public record PaginationParams(int Page, int PageSize)
{
    public static ValueTask<PaginationParams?> BindAsync(
        HttpContext context)
    {
        int.TryParse(context.Request.Query["page"], out var page);
        int.TryParse(context.Request.Query["pageSize"], out var ps);
        return ValueTask.FromResult<PaginationParams?>(
            new PaginationParams(
                Math.Max(1, page == 0 ? 1 : page),
                Math.Clamp(ps == 0 ? 20 : ps, 1, 100)));
    }
}
```

Minimal API feature comparison:

| Feature | Minimal APIs | Controllers |
|---|---|---|
| Startup overhead | Lower | Higher (reflection routing) |
| Route definition | Lambda / method group | Attribute-based |
| Filters | Endpoint filters | Action filters + middleware |
| Model validation | Manual or filter | Automatic with `[ApiController]` |
| AOT compatible | Yes (typed results) | Limited |
| OpenAPI | Built-in `MapOpenApi()` | Swashbuckle/NSwag |

Key patterns:
- **Typed results** (`Results<Ok<T>, NotFound>`) give compile-time safety and auto-generate OpenAPI schemas
- **Route groups** share configuration (tags, auth, rate limiting, filters) across related endpoints
- **Endpoint filters** are the minimal API equivalent of MVC action filters
- **`CacheOutput`** enables response caching with tag-based invalidation
- **Rate limiting** with built-in middleware supports fixed window, sliding window, token bucket, and concurrency
- **Custom `BindAsync`** lets complex types bind from query strings, headers, or route values'''
    ),
]
