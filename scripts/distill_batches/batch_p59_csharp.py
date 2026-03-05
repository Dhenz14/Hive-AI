"""C# — .NET patterns, ASP.NET Core, Entity Framework, and LINQ."""

PAIRS = [
    (
        "csharp/aspnet-core-api",
        "Show ASP.NET Core minimal API and controller patterns: routing, dependency injection, middleware, and validation.",
        '''ASP.NET Core API patterns:

```csharp
// --- Minimal API (modern approach) ---

var builder = WebApplication.CreateBuilder(args);

// Services
builder.Services.AddDbContext<AppDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("Default")));
builder.Services.AddScoped<IUserService, UserService>();
builder.Services.AddScoped<IOrderService, OrderService>();
builder.Services.AddAuthentication().AddJwtBearer();
builder.Services.AddAuthorization();

var app = builder.Build();

// Middleware pipeline
app.UseExceptionHandler("/error");
app.UseAuthentication();
app.UseAuthorization();

// --- Route groups ---

var api = app.MapGroup("/api/v1").RequireAuthorization();

var users = api.MapGroup("/users");
users.MapGet("/", async (IUserService svc,
    [AsParameters] PaginationQuery query) =>
{
    var result = await svc.GetAllAsync(query.Page, query.Size);
    return Results.Ok(result);
});

users.MapGet("/{id:guid}", async (Guid id, IUserService svc) =>
{
    var user = await svc.GetByIdAsync(id);
    return user is not null ? Results.Ok(user) : Results.NotFound();
});

users.MapPost("/", async (UserCreateDto dto, IUserService svc) =>
{
    var created = await svc.CreateAsync(dto);
    return Results.Created($"/api/v1/users/{created.Id}", created);
})
.AddEndpointFilter<ValidationFilter<UserCreateDto>>();

users.MapPut("/{id:guid}", async (Guid id, UserUpdateDto dto, IUserService svc) =>
{
    var updated = await svc.UpdateAsync(id, dto);
    return updated is not null ? Results.Ok(updated) : Results.NotFound();
});

users.MapDelete("/{id:guid}", async (Guid id, IUserService svc) =>
{
    await svc.DeleteAsync(id);
    return Results.NoContent();
})
.RequireAuthorization("AdminOnly");


// --- DTOs with validation ---

public record UserCreateDto(
    [Required] [StringLength(100, MinimumLength = 2)] string Name,
    [Required] [EmailAddress] string Email,
    [Range(13, 150)] int Age
);

public record UserUpdateDto(
    [StringLength(100, MinimumLength = 2)] string? Name,
    [StringLength(500)] string? Bio
);

public record UserResponse(Guid Id, string Name, string Email,
    int Age, DateTime CreatedAt);

public record PaginationQuery(int Page = 1, int Size = 20);


// --- Validation endpoint filter ---

public class ValidationFilter<T> : IEndpointFilter where T : class
{
    public async ValueTask<object?> InvokeAsync(
        EndpointFilterInvocationContext ctx,
        EndpointFilterDelegate next)
    {
        var dto = ctx.Arguments.OfType<T>().FirstOrDefault();
        if (dto is null)
            return Results.BadRequest("Request body required");

        var validationResults = new List<ValidationResult>();
        if (!Validator.TryValidateObject(dto, new ValidationContext(dto),
            validationResults, validateAllProperties: true))
        {
            var errors = validationResults
                .ToDictionary(v => v.MemberNames.First(), v => v.ErrorMessage!);
            return Results.ValidationProblem(errors);
        }

        return await next(ctx);
    }
}


// --- Service layer ---

public interface IUserService
{
    Task<PagedResult<UserResponse>> GetAllAsync(int page, int size);
    Task<UserResponse?> GetByIdAsync(Guid id);
    Task<UserResponse> CreateAsync(UserCreateDto dto);
    Task<UserResponse?> UpdateAsync(Guid id, UserUpdateDto dto);
    Task DeleteAsync(Guid id);
}

public class UserService : IUserService
{
    private readonly AppDbContext _db;
    private readonly ILogger<UserService> _logger;

    public UserService(AppDbContext db, ILogger<UserService> logger)
    {
        _db = db;
        _logger = logger;
    }

    public async Task<PagedResult<UserResponse>> GetAllAsync(int page, int size)
    {
        var total = await _db.Users.CountAsync();
        var users = await _db.Users
            .OrderByDescending(u => u.CreatedAt)
            .Skip((page - 1) * size)
            .Take(size)
            .Select(u => new UserResponse(u.Id, u.Name, u.Email,
                u.Age, u.CreatedAt))
            .ToListAsync();

        return new PagedResult<UserResponse>(users, total, page, size);
    }

    public async Task<UserResponse> CreateAsync(UserCreateDto dto)
    {
        if (await _db.Users.AnyAsync(u => u.Email == dto.Email.ToLower()))
            throw new ConflictException("Email already registered");

        var user = new User
        {
            Name = dto.Name,
            Email = dto.Email.ToLower(),
            Age = dto.Age,
        };

        _db.Users.Add(user);
        await _db.SaveChangesAsync();

        _logger.LogInformation("Created user {UserId}", user.Id);
        return new UserResponse(user.Id, user.Name, user.Email,
            user.Age, user.CreatedAt);
    }

    // ... other methods
}


// --- Global error handling ---

app.MapGet("/error", (HttpContext ctx) =>
{
    var exception = ctx.Features.Get<IExceptionHandlerFeature>()?.Error;

    return exception switch
    {
        NotFoundException e => Results.NotFound(
            new { error = "not_found", message = e.Message }),
        ConflictException e => Results.Conflict(
            new { error = "conflict", message = e.Message }),
        _ => Results.Problem(
            statusCode: 500, title: "Internal server error")
    };
});

app.Run();
```

ASP.NET Core patterns:
1. **Minimal APIs** — concise route-to-handler mapping with `MapGet`/`MapPost`
2. **Route groups** — shared prefix and authorization with `MapGroup`
3. **Endpoint filters** — validation, logging without middleware overhead
4. **Records for DTOs** — immutable data carriers with built-in equality
5. **`Results.*`** — type-safe HTTP response helpers (Ok, NotFound, Created)'''
    ),
    (
        "csharp/entity-framework",
        "Show Entity Framework Core patterns: DbContext, migrations, LINQ queries, and performance.",
        '''Entity Framework Core patterns:

```csharp
// --- DbContext ---

public class AppDbContext : DbContext
{
    public DbSet<User> Users => Set<User>();
    public DbSet<Order> Orders => Set<Order>();
    public DbSet<Product> Products => Set<Product>();

    public AppDbContext(DbContextOptions<AppDbContext> options)
        : base(options) { }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.ApplyConfigurationsFromAssembly(
            typeof(AppDbContext).Assembly);

        // Global query filter (soft delete)
        modelBuilder.Entity<User>()
            .HasQueryFilter(u => !u.IsDeleted);
    }

    // Auto-set audit fields
    public override async Task<int> SaveChangesAsync(
        CancellationToken ct = default)
    {
        foreach (var entry in ChangeTracker.Entries<BaseEntity>())
        {
            switch (entry.State)
            {
                case EntityState.Added:
                    entry.Entity.CreatedAt = DateTime.UtcNow;
                    break;
                case EntityState.Modified:
                    entry.Entity.UpdatedAt = DateTime.UtcNow;
                    break;
            }
        }
        return await base.SaveChangesAsync(ct);
    }
}


// --- Entity configuration (separate from entity) ---

public class UserConfiguration : IEntityTypeConfiguration<User>
{
    public void Configure(EntityTypeBuilder<User> builder)
    {
        builder.HasKey(u => u.Id);

        builder.Property(u => u.Name)
            .IsRequired()
            .HasMaxLength(100);

        builder.Property(u => u.Email)
            .IsRequired()
            .HasMaxLength(255);

        builder.HasIndex(u => u.Email).IsUnique();

        builder.HasMany(u => u.Orders)
            .WithOne(o => o.User)
            .HasForeignKey(o => o.UserId)
            .OnDelete(DeleteBehavior.Cascade);

        // Owned type (value object)
        builder.OwnsOne(u => u.Address, a =>
        {
            a.Property(x => x.Street).HasMaxLength(200);
            a.Property(x => x.City).HasMaxLength(100);
            a.Property(x => x.ZipCode).HasMaxLength(20);
        });

        // Concurrency token
        builder.Property(u => u.Version)
            .IsRowVersion();
    }
}


// --- LINQ queries ---

public class UserRepository
{
    private readonly AppDbContext _db;

    public UserRepository(AppDbContext db) => _db = db;

    // Efficient: only loads needed columns
    public async Task<List<UserSummary>> GetSummariesAsync()
    {
        return await _db.Users
            .Select(u => new UserSummary(u.Id, u.Name, u.Email))
            .ToListAsync();
    }

    // Eager loading (avoid N+1)
    public async Task<User?> GetWithOrdersAsync(Guid id)
    {
        return await _db.Users
            .Include(u => u.Orders)
                .ThenInclude(o => o.OrderItems)
                    .ThenInclude(oi => oi.Product)
            .FirstOrDefaultAsync(u => u.Id == id);
    }

    // Split query (multiple SQL queries, avoids Cartesian explosion)
    public async Task<List<User>> GetAllWithOrdersAsync()
    {
        return await _db.Users
            .Include(u => u.Orders)
            .AsSplitQuery()
            .ToListAsync();
    }

    // Compiled query (cached expression tree)
    private static readonly Func<AppDbContext, string, Task<User?>>
        _findByEmail = EF.CompileAsyncQuery(
            (AppDbContext db, string email) =>
                db.Users.FirstOrDefault(u => u.Email == email));

    public Task<User?> FindByEmailAsync(string email) =>
        _findByEmail(_db, email);

    // Complex filtering with specification pattern
    public async Task<PagedResult<User>> SearchAsync(UserSearchSpec spec)
    {
        var query = _db.Users.AsQueryable();

        if (!string.IsNullOrEmpty(spec.Name))
            query = query.Where(u => u.Name.Contains(spec.Name));

        if (spec.MinAge.HasValue)
            query = query.Where(u => u.Age >= spec.MinAge.Value);

        if (spec.Status.HasValue)
            query = query.Where(u => u.Status == spec.Status.Value);

        var total = await query.CountAsync();
        var items = await query
            .OrderBy(u => u.Name)
            .Skip((spec.Page - 1) * spec.PageSize)
            .Take(spec.PageSize)
            .ToListAsync();

        return new PagedResult<User>(items, total, spec.Page, spec.PageSize);
    }

    // Bulk operations (EF Core 7+)
    public async Task<int> DeactivateInactiveUsersAsync(DateTime cutoff)
    {
        return await _db.Users
            .Where(u => u.LastLoginAt < cutoff && u.Status == UserStatus.Active)
            .ExecuteUpdateAsync(u => u
                .SetProperty(x => x.Status, UserStatus.Inactive)
                .SetProperty(x => x.UpdatedAt, DateTime.UtcNow));
    }

    public async Task<int> PurgeDeletedUsersAsync()
    {
        return await _db.Users
            .Where(u => u.IsDeleted && u.DeletedAt < DateTime.UtcNow.AddDays(-30))
            .ExecuteDeleteAsync();
    }

    // Raw SQL when needed
    public async Task<List<TopCustomer>> GetTopCustomersAsync(int limit)
    {
        return await _db.Database
            .SqlQuery<TopCustomer>($"""
                SELECT u.id AS Id, u.name AS Name,
                       SUM(o.total) AS TotalSpend,
                       COUNT(o.id) AS OrderCount
                FROM users u
                JOIN orders o ON u.id = o.user_id
                GROUP BY u.id, u.name
                ORDER BY TotalSpend DESC
                LIMIT {limit}
            """)
            .ToListAsync();
    }
}
```

EF Core patterns:
1. **`IEntityTypeConfiguration`** — separate configuration from entities
2. **`AsSplitQuery()`** — prevent Cartesian explosion with multiple Includes
3. **`EF.CompileAsyncQuery`** — cached expression tree for hot-path queries
4. **`ExecuteUpdateAsync`** — bulk updates without loading entities (EF 7+)
5. **Global query filters** — auto-apply soft-delete or tenant filtering'''
    ),
    (
        "csharp/linq-patterns",
        "Show advanced LINQ patterns: grouping, aggregation, joins, custom extensions, and async enumerables.",
        '''Advanced LINQ patterns:

```csharp
// --- Grouping and aggregation ---

var salesByRegion = orders
    .GroupBy(o => o.Region)
    .Select(g => new
    {
        Region = g.Key,
        TotalRevenue = g.Sum(o => o.Total),
        OrderCount = g.Count(),
        AvgOrder = g.Average(o => o.Total),
        TopProduct = g
            .SelectMany(o => o.Items)
            .GroupBy(i => i.ProductName)
            .OrderByDescending(pg => pg.Sum(i => i.Quantity))
            .First().Key,
    })
    .OrderByDescending(r => r.TotalRevenue);


// Multi-level grouping
var hierarchical = orders
    .GroupBy(o => new { o.Year, o.Month })
    .Select(g => new
    {
        g.Key.Year,
        g.Key.Month,
        Revenue = g.Sum(o => o.Total),
        ByCategory = g
            .SelectMany(o => o.Items)
            .GroupBy(i => i.Category)
            .Select(cg => new
            {
                Category = cg.Key,
                Total = cg.Sum(i => i.Price * i.Quantity),
            })
            .OrderByDescending(c => c.Total)
            .ToList(),
    });


// --- Joins ---

// Join with projection
var enrichedOrders = orders
    .Join(customers,
        o => o.CustomerId,
        c => c.Id,
        (o, c) => new { Order = o, Customer = c })
    .Join(products,
        oc => oc.Order.ProductId,
        p => p.Id,
        (oc, p) => new
        {
            OrderId = oc.Order.Id,
            CustomerName = oc.Customer.Name,
            ProductName = p.Name,
            Total = oc.Order.Total,
        });

// Left join with GroupJoin
var customersWithOrders = customers
    .GroupJoin(orders,
        c => c.Id,
        o => o.CustomerId,
        (c, orderGroup) => new
        {
            Customer = c.Name,
            OrderCount = orderGroup.Count(),
            TotalSpend = orderGroup.Sum(o => o.Total),
            LastOrder = orderGroup
                .OrderByDescending(o => o.Date)
                .FirstOrDefault()?.Date,
        });


// --- Chunk and partition ---

// Process in batches (LINQ .Chunk from .NET 6)
var batches = items.Chunk(100);
foreach (var batch in batches)
{
    await ProcessBatchAsync(batch);
}

// Partition by predicate
var (active, inactive) = users
    .Aggregate(
        (Active: new List<User>(), Inactive: new List<User>()),
        (acc, user) =>
        {
            if (user.IsActive)
                acc.Active.Add(user);
            else
                acc.Inactive.Add(user);
            return acc;
        });


// --- Custom LINQ extensions ---

public static class LinqExtensions
{
    // WhereIf: conditionally apply filter
    public static IQueryable<T> WhereIf<T>(
        this IQueryable<T> query,
        bool condition,
        Expression<Func<T, bool>> predicate)
    {
        return condition ? query.Where(predicate) : query;
    }

    // Paginate
    public static IQueryable<T> Paginate<T>(
        this IQueryable<T> query, int page, int size)
    {
        return query.Skip((page - 1) * size).Take(size);
    }

    // DistinctBy (before .NET 6)
    public static IEnumerable<T> DistinctBy<T, TKey>(
        this IEnumerable<T> source,
        Func<T, TKey> keySelector)
    {
        var seen = new HashSet<TKey>();
        foreach (var item in source)
        {
            if (seen.Add(keySelector(item)))
                yield return item;
        }
    }

    // ToHashSet with selector
    public static HashSet<TKey> ToHashSet<T, TKey>(
        this IEnumerable<T> source,
        Func<T, TKey> selector)
    {
        return new HashSet<TKey>(source.Select(selector));
    }
}

// Usage:
// var results = _db.Users
//     .WhereIf(!string.IsNullOrEmpty(name), u => u.Name.Contains(name))
//     .WhereIf(minAge.HasValue, u => u.Age >= minAge!.Value)
//     .WhereIf(status.HasValue, u => u.Status == status!.Value)
//     .Paginate(page, size)
//     .ToListAsync();


// --- Async enumerable (streaming) ---

public async IAsyncEnumerable<UserDto> StreamUsersAsync(
    [EnumeratorCancellation] CancellationToken ct = default)
{
    await foreach (var user in _db.Users.AsAsyncEnumerable()
        .WithCancellation(ct))
    {
        yield return new UserDto(user.Id, user.Name, user.Email);
    }
}

// Consume:
// await foreach (var user in service.StreamUsersAsync())
// {
//     Console.WriteLine(user.Name);
// }
```

LINQ patterns:
1. **`GroupBy` + `Select`** — multi-level aggregation with nested grouping
2. **`GroupJoin`** — left outer join preserving all left-side elements
3. **`WhereIf` extension** — conditionally apply filters for dynamic queries
4. **`.Chunk(n)`** — split sequences into fixed-size batches (.NET 6+)
5. **`IAsyncEnumerable`** — stream large result sets without loading all into memory'''
    ),
]
"""
