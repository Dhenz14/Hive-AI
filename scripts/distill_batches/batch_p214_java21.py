"""Java 21+ modern features — virtual threads, pattern matching, records, structured concurrency, Stream API."""

PAIRS = [
    (
        "java/virtual-threads-loom",
        "Show Java virtual threads (Project Loom) including creation, executors, pinning, and migration patterns from platform threads.",
        '''Java virtual threads (Project Loom) for high-throughput concurrent applications:

```java
// --- Virtual thread creation and basics ---

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.*;
import java.util.List;
import java.util.ArrayList;
import java.util.stream.IntStream;

public class VirtualThreadBasics {

    public static void main(String[] args) throws Exception {
        // 1. Direct creation with Thread.ofVirtual()
        Thread vThread = Thread.ofVirtual()
            .name("my-virtual-thread")
            .start(() -> {
                System.out.println("Running on: " + Thread.currentThread());
                System.out.println("Is virtual: " + Thread.currentThread().isVirtual());
            });
        vThread.join();

        // 2. Factory for named virtual threads
        ThreadFactory factory = Thread.ofVirtual()
            .name("worker-", 0)  // worker-0, worker-1, etc.
            .factory();

        Thread t1 = factory.newThread(() -> System.out.println(Thread.currentThread().getName()));
        t1.start();
        t1.join();

        // 3. Virtual thread executor (preferred for production)
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            // Submit 100,000 concurrent tasks — impossible with platform threads
            List<Future<String>> futures = new ArrayList<>();
            Instant start = Instant.now();

            for (int i = 0; i < 100_000; i++) {
                final int taskId = i;
                futures.add(executor.submit(() -> {
                    // Simulate I/O-bound work (DB query, HTTP call)
                    Thread.sleep(Duration.ofMillis(100));
                    return "Result-" + taskId;
                }));
            }

            int completed = 0;
            for (Future<String> future : futures) {
                future.get();
                completed++;
            }

            Duration elapsed = Duration.between(start, Instant.now());
            System.out.printf("Completed %d tasks in %s%n", completed, elapsed);
            // ~100ms (not 100,000 * 100ms) because virtual threads multiplex
        }
    }
}
```

```java
// --- Virtual threads in HTTP servers and database access ---

import java.net.http.*;
import java.net.URI;
import java.sql.*;
import java.util.concurrent.*;

public class VirtualThreadServer {

    // HTTP client configured for virtual threads
    private static final HttpClient httpClient = HttpClient.newBuilder()
        .executor(Executors.newVirtualThreadPerTaskExecutor())
        .connectTimeout(Duration.ofSeconds(10))
        .build();

    // Database access — virtual threads unmount during blocking JDBC calls
    public record User(long id, String name, String email) {}

    public static User findUser(Connection conn, long id) throws SQLException {
        // Virtual thread unmounts here while waiting for DB response
        // The carrier thread is freed to run other virtual threads
        try (PreparedStatement stmt = conn.prepareStatement(
                "SELECT id, name, email FROM users WHERE id = ?")) {
            stmt.setLong(1, id);
            try (ResultSet rs = stmt.executeQuery()) {
                if (rs.next()) {
                    return new User(rs.getLong("id"), rs.getString("name"), rs.getString("email"));
                }
                return null;
            }
        }
    }

    // Fan-out pattern: fetch data from multiple services concurrently
    public record ProductPage(String product, String reviews, String recommendations) {}

    public static ProductPage fetchProductPage(String productId) throws Exception {
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> productFuture = executor.submit(() ->
                fetchFromService("http://products-api/products/" + productId));
            Future<String> reviewsFuture = executor.submit(() ->
                fetchFromService("http://reviews-api/reviews/" + productId));
            Future<String> recoFuture = executor.submit(() ->
                fetchFromService("http://reco-api/recommendations/" + productId));

            return new ProductPage(
                productFuture.get(5, TimeUnit.SECONDS),
                reviewsFuture.get(5, TimeUnit.SECONDS),
                recoFuture.get(5, TimeUnit.SECONDS)
            );
        }
    }

    private static String fetchFromService(String url) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .timeout(Duration.ofSeconds(5))
            .build();
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        return response.body();
    }

    // PINNING WARNING: synchronized blocks pin the virtual thread to carrier
    // Use ReentrantLock instead
    private static final ReentrantLock lock = new ReentrantLock();

    public static void goodLocking() {
        lock.lock();  // Virtual thread can unmount while waiting
        try {
            // Critical section
        } finally {
            lock.unlock();
        }
    }

    // BAD: synchronized pins virtual thread to carrier
    // public static synchronized void badLocking() {
    //     // Virtual thread CANNOT unmount — pins carrier thread
    // }
}
```

```java
// --- Migration patterns and best practices ---

import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class VirtualThreadMigration {

    // BEFORE: Fixed thread pool (typical pre-Loom pattern)
    static ExecutorService oldStyle() {
        return new ThreadPoolExecutor(
            10, 50,  // core=10, max=50
            60L, TimeUnit.SECONDS,
            new LinkedBlockingQueue<>(1000),
            new ThreadPoolExecutor.CallerRunsPolicy()
        );
    }

    // AFTER: Virtual thread executor (one-line replacement for I/O-bound work)
    static ExecutorService newStyle() {
        return Executors.newVirtualThreadPerTaskExecutor();
    }

    // Monitoring virtual threads
    static void monitorVirtualThreads() {
        AtomicInteger activeCount = new AtomicInteger(0);

        Thread.ofVirtual()
            .name("monitored-vt")
            .start(() -> {
                activeCount.incrementAndGet();
                try {
                    // Work
                    Thread.sleep(Duration.ofSeconds(1));
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    activeCount.decrementAndGet();
                }
            });

        // JFR events for virtual thread monitoring:
        // jdk.VirtualThreadStart, jdk.VirtualThreadEnd
        // jdk.VirtualThreadPinned (detect pinning issues)
        // Enable with: -XX:StartFlightRecording:filename=recording.jfr
    }

    // ScopedValue: thread-local replacement for virtual threads (Preview)
    // static final ScopedValue<String> REQUEST_ID = ScopedValue.newInstance();
    //
    // void handleRequest(String reqId) {
    //     ScopedValue.runWhere(REQUEST_ID, reqId, () -> {
    //         // All code in this scope sees REQUEST_ID.get() == reqId
    //         processRequest();
    //     });
    // }

    // When NOT to use virtual threads:
    // 1. CPU-bound work — use ForkJoinPool or parallel streams instead
    // 2. Tasks using synchronized blocks with I/O inside (causes pinning)
    // 3. Tasks storing large data in ThreadLocal (each VT gets a copy)
}
```

Virtual threads vs platform threads:

| Aspect | Platform Threads | Virtual Threads |
|--------|-----------------|-----------------|
| Memory per thread | ~1 MB stack | ~few KB (grows on demand) |
| Max count | ~10K (OS limit) | Millions |
| Scheduling | OS scheduler | JVM ForkJoinPool |
| Blocking I/O | Blocks OS thread | Unmounts, frees carrier |
| `synchronized` | No issue | Pins carrier (avoid) |
| CPU-bound work | Good | No benefit (use platform) |
| Thread pools | Yes (size tuning) | No pool needed (one per task) |
| ThreadLocal | Fine | Expensive (use ScopedValue) |
| Best for | CPU-bound, long-lived | I/O-bound, short-lived |

Key patterns:
1. Use `Executors.newVirtualThreadPerTaskExecutor()` as a drop-in replacement for I/O-bound thread pools
2. Replace `synchronized` with `ReentrantLock` to avoid carrier thread pinning
3. Virtual threads shine for I/O-bound workloads (HTTP, DB, file) — they unmount during blocking calls
4. Do NOT pool virtual threads — create one per task, let the JVM manage carrier threads
5. Use JFR event `jdk.VirtualThreadPinned` to detect pinning issues in production
6. Migrate ThreadLocals to ScopedValues (preview) for efficient per-request data with virtual threads'''
    ),
    (
        "java/pattern-matching-sealed",
        "Show Java pattern matching with switch expressions, record patterns, sealed classes, and guarded patterns.",
        '''Java pattern matching with switch expressions, records, and sealed classes:

```java
// --- Sealed class hierarchy with pattern matching ---

// Sealed interface — only permits listed implementations
public sealed interface Shape
    permits Circle, Rectangle, Triangle, Polygon {

    double area();
    double perimeter();
}

public record Circle(double radius) implements Shape {
    public Circle {
        if (radius <= 0) throw new IllegalArgumentException("Radius must be positive");
    }

    @Override public double area() { return Math.PI * radius * radius; }
    @Override public double perimeter() { return 2 * Math.PI * radius; }
}

public record Rectangle(double width, double height) implements Shape {
    public Rectangle {
        if (width <= 0 || height <= 0) throw new IllegalArgumentException("Dimensions must be positive");
    }

    public boolean isSquare() { return width == height; }
    @Override public double area() { return width * height; }
    @Override public double perimeter() { return 2 * (width + height); }
}

public record Triangle(double a, double b, double c) implements Shape {
    public Triangle {
        if (a + b <= c || b + c <= a || a + c <= b) {
            throw new IllegalArgumentException("Invalid triangle sides");
        }
    }

    @Override public double area() {
        double s = (a + b + c) / 2;
        return Math.sqrt(s * (s - a) * (s - b) * (s - c));
    }
    @Override public double perimeter() { return a + b + c; }
}

public record Polygon(java.util.List<Point> vertices) implements Shape {
    public record Point(double x, double y) {}

    @Override public double area() { /* Shoelace formula */ return 0; }
    @Override public double perimeter() { /* Sum of edge lengths */ return 0; }
}
```

```java
// --- Switch expressions with pattern matching ---

public class ShapeProcessor {

    // Pattern matching in switch (Java 21+)
    public static String describe(Shape shape) {
        return switch (shape) {
            // Record patterns — destructure directly
            case Circle(var r) when r > 100 ->
                "Large circle with radius " + r;

            case Circle(var r) ->
                "Circle with radius " + r;

            case Rectangle(var w, var h) when w == h ->
                "Square with side " + w;

            case Rectangle(var w, var h) ->
                "Rectangle " + w + "x" + h;

            case Triangle(var a, var b, var c) when a == b && b == c ->
                "Equilateral triangle with side " + a;

            case Triangle(var a, var b, var c) ->
                "Triangle with sides " + a + ", " + b + ", " + c;

            case Polygon(var vertices) ->
                vertices.size() + "-sided polygon";
        };
        // No default needed — sealed interface is exhaustive!
    }

    // Nested record patterns
    public sealed interface Expr permits Num, Add, Mul, Neg {}
    public record Num(double value) implements Expr {}
    public record Add(Expr left, Expr right) implements Expr {}
    public record Mul(Expr left, Expr right) implements Expr {}
    public record Neg(Expr operand) implements Expr {}

    public static double evaluate(Expr expr) {
        return switch (expr) {
            case Num(var v) -> v;
            case Add(var l, var r) -> evaluate(l) + evaluate(r);
            case Mul(var l, var r) -> evaluate(l) * evaluate(r);
            case Neg(var op) -> -evaluate(op);
        };
    }

    // Nested pattern matching with guards
    public static String simplify(Expr expr) {
        return switch (expr) {
            case Add(Num(var a), Num(var b)) ->
                "constant: " + (a + b);
            case Mul(Num(var n), var other) when n == 0 ->
                "zero (multiply by 0)";
            case Mul(Num(var n), var other) when n == 1 ->
                "identity: " + simplify(other);
            case Neg(Neg(var inner)) ->
                "double negation: " + simplify(inner);
            default ->
                "complex expression";
        };
    }

    // Pattern matching with instanceof (Java 16+)
    public static void processObject(Object obj) {
        if (obj instanceof String s && s.length() > 5) {
            System.out.println("Long string: " + s.toUpperCase());
        } else if (obj instanceof Integer i && i > 0) {
            System.out.println("Positive integer: " + i);
        } else if (obj instanceof int[] arr && arr.length > 0) {
            System.out.println("Array starting with: " + arr[0]);
        }
    }
}
```

```java
// --- Practical example: command/event handling ---

import java.time.Instant;
import java.util.UUID;

public class EventSystem {

    // Sealed event hierarchy
    public sealed interface DomainEvent permits UserEvent, OrderEvent {
        UUID eventId();
        Instant timestamp();
    }

    public sealed interface UserEvent extends DomainEvent
        permits UserCreated, UserUpdated, UserDeleted {}

    public record UserCreated(
        UUID eventId, Instant timestamp,
        UUID userId, String name, String email
    ) implements UserEvent {}

    public record UserUpdated(
        UUID eventId, Instant timestamp,
        UUID userId, String field, String oldValue, String newValue
    ) implements UserEvent {}

    public record UserDeleted(
        UUID eventId, Instant timestamp,
        UUID userId, String reason
    ) implements UserEvent {}

    public sealed interface OrderEvent extends DomainEvent
        permits OrderPlaced, OrderCancelled {}

    public record OrderPlaced(
        UUID eventId, Instant timestamp,
        UUID orderId, UUID userId, long totalCents
    ) implements OrderEvent {}

    public record OrderCancelled(
        UUID eventId, Instant timestamp,
        UUID orderId, String reason
    ) implements OrderEvent {}

    // Exhaustive event handler using pattern matching
    public static String handleEvent(DomainEvent event) {
        return switch (event) {
            case UserCreated(var id, var ts, var uid, var name, var email) ->
                "Welcome email to " + email;

            case UserUpdated(_, _, var uid, var field, _, var newVal) ->
                "Audit log: user " + uid + " changed " + field + " to " + newVal;

            case UserDeleted(_, _, var uid, var reason) ->
                "Cleanup data for user " + uid + ": " + reason;

            case OrderPlaced(_, _, var oid, var uid, var total) ->
                "Process payment $" + (total / 100.0) + " for order " + oid;

            case OrderCancelled(_, _, var oid, var reason) ->
                "Refund order " + oid + ": " + reason;
        };
    }

    // Type-safe event routing
    public static void routeEvent(DomainEvent event) {
        switch (event) {
            case UserEvent ue -> handleUserEvent(ue);
            case OrderEvent oe -> handleOrderEvent(oe);
        }
    }

    private static void handleUserEvent(UserEvent event) {
        System.out.println("User event: " + event.eventId());
    }

    private static void handleOrderEvent(OrderEvent event) {
        System.out.println("Order event: " + event.eventId());
    }
}
```

Pattern matching feature progression:

| Feature | Java Version | Syntax |
|---------|-------------|--------|
| `instanceof` pattern | 16+ | `if (x instanceof String s)` |
| Sealed classes | 17+ | `sealed interface X permits A, B` |
| Switch pattern matching | 21+ | `case String s -> ...` |
| Record patterns | 21+ | `case Point(var x, var y) -> ...` |
| Guarded patterns | 21+ | `case String s when s.length() > 5` |
| Nested record patterns | 21+ | `case Add(Num(var a), Num(var b))` |
| Unnamed patterns | 22+ (preview) | `case Point(var x, _) -> ...` |

Key patterns:
1. Sealed interfaces + records create algebraic data types — the compiler ensures exhaustive switch coverage
2. Record patterns destructure directly in switch cases: `case Circle(var r)` extracts the radius
3. Guards (`when` clauses) add conditions to patterns — evaluated after the pattern matches
4. Nested patterns match deeply: `case Add(Num(var a), Num(var b))` matches addition of two constants
5. Use sealed hierarchies for domain events and commands — new variants cause compile errors in all handlers
6. Prefer switch expressions (returning a value) over switch statements for pattern matching'''
    ),
    (
        "java/records-data-oriented",
        "Show Java records and data-oriented programming patterns including compact constructors, local records, and immutable data pipelines.",
        '''Java records for data-oriented programming and immutable data:

```java
// --- Record fundamentals and compact constructors ---

import java.util.*;
import java.time.LocalDate;

// Basic record — auto-generates constructor, equals, hashCode, toString, accessors
public record Point(double x, double y) {
    // Compact constructor for validation (no explicit param assignment needed)
    public Point {
        if (Double.isNaN(x) || Double.isNaN(y)) {
            throw new IllegalArgumentException("Coordinates cannot be NaN");
        }
    }

    // Derived methods
    public double distanceTo(Point other) {
        return Math.sqrt(Math.pow(x - other.x, 2) + Math.pow(y - other.y, 2));
    }

    // Static factory methods
    public static Point origin() { return new Point(0, 0); }
    public static Point of(double x, double y) { return new Point(x, y); }
}

// Record with generic type
public record Pair<A, B>(A first, B second) {
    public <C> Pair<A, C> mapSecond(java.util.function.Function<B, C> fn) {
        return new Pair<>(first, fn.apply(second));
    }
}

// Record implementing interfaces
public record Range(int start, int end) implements Comparable<Range> {
    public Range {
        if (start > end) throw new IllegalArgumentException("start must be <= end");
    }

    public boolean contains(int value) { return value >= start && value <= end; }
    public boolean overlaps(Range other) { return start <= other.end && other.start <= end; }
    public int size() { return end - start; }

    @Override
    public int compareTo(Range other) {
        int cmp = Integer.compare(start, other.start);
        return cmp != 0 ? cmp : Integer.compare(end, other.end);
    }
}

// Immutable value object with builder-like "with" methods
public record Money(long amountCents, String currency) {
    public Money {
        Objects.requireNonNull(currency, "currency must not be null");
        if (currency.length() != 3) {
            throw new IllegalArgumentException("Currency must be ISO 4217 code");
        }
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Cannot add different currencies");
        }
        return new Money(amountCents + other.amountCents, currency);
    }

    public Money multiply(int factor) {
        return new Money(amountCents * factor, currency);
    }

    public String formatted() {
        return String.format("%s %.2f", currency, amountCents / 100.0);
    }

    public static Money usd(long cents) { return new Money(cents, "USD"); }
    public static Money eur(long cents) { return new Money(cents, "EUR"); }
}
```

```java
// --- Data-oriented programming with records ---

import java.util.*;
import java.util.stream.*;
import java.util.function.*;

public class DataOriented {

    // Domain model as records (immutable data)
    public record Customer(String id, String name, String email, String tier) {}
    public record Product(String id, String name, Money price, int stockCount) {}
    public record OrderLine(Product product, int quantity) {
        public Money total() { return product.price().multiply(quantity); }
    }
    public record Order(String id, Customer customer, List<OrderLine> lines, OrderStatus status) {
        public Money total() {
            return lines.stream()
                .map(OrderLine::total)
                .reduce(Money.usd(0), Money::add);
        }

        // "with" pattern — create modified copy
        public Order withStatus(OrderStatus newStatus) {
            return new Order(id, customer, lines, newStatus);
        }
    }

    public enum OrderStatus { PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED }

    // Data pipeline with records
    public record OrderSummary(String orderId, String customerName, Money total, int itemCount) {}

    public static List<OrderSummary> summarizeOrders(List<Order> orders) {
        return orders.stream()
            .filter(o -> o.status() != OrderStatus.CANCELLED)
            .map(o -> new OrderSummary(
                o.id(),
                o.customer().name(),
                o.total(),
                o.lines().size()
            ))
            .sorted(Comparator.comparing(OrderSummary::total,
                Comparator.comparingLong(Money::amountCents).reversed()))
            .toList(); // Immutable list (Java 16+)
    }

    // Local records for intermediate computation
    public static Map<String, Money> revenueByTier(List<Order> orders) {
        // Local record — scoped to this method
        record TierRevenue(String tier, Money revenue) {}

        return orders.stream()
            .filter(o -> o.status() == OrderStatus.DELIVERED)
            .map(o -> new TierRevenue(o.customer().tier(), o.total()))
            .collect(Collectors.groupingBy(
                TierRevenue::tier,
                Collectors.reducing(
                    Money.usd(0),
                    TierRevenue::revenue,
                    Money::add
                )
            ));
    }

    // Result type using sealed interface + records
    public sealed interface Result<T> permits Result.Success, Result.Failure {
        record Success<T>(T value) implements Result<T> {}
        record Failure<T>(String error, Exception cause) implements Result<T> {}

        default <U> Result<U> map(Function<T, U> fn) {
            return switch (this) {
                case Success<T>(var v) -> new Success<>(fn.apply(v));
                case Failure<T>(var err, var cause) -> new Failure<>(err, cause);
            };
        }

        default <U> Result<U> flatMap(Function<T, Result<U>> fn) {
            return switch (this) {
                case Success<T>(var v) -> fn.apply(v);
                case Failure<T>(var err, var cause) -> new Failure<>(err, cause);
            };
        }

        default T orElse(T defaultValue) {
            return switch (this) {
                case Success<T>(var v) -> v;
                case Failure<T> f -> defaultValue;
            };
        }
    }
}
```

```java
// --- Records with collections and serialization ---

import com.fasterxml.jackson.annotation.*;
import java.util.*;

// Record with defensive copying for mutable collections
public record Team(String name, List<String> members) {
    public Team {
        Objects.requireNonNull(name);
        // Defensive copy — prevent external mutation
        members = List.copyOf(members); // Immutable copy
    }

    public Team addMember(String member) {
        var newMembers = new ArrayList<>(members);
        newMembers.add(member);
        return new Team(name, newMembers);
    }

    public Team removeMember(String member) {
        return new Team(name, members.stream()
            .filter(m -> !m.equals(member))
            .toList());
    }
}

// Record with Jackson JSON annotations
@JsonIgnoreProperties(ignoreUnknown = true)
public record ApiResponse<T>(
    @JsonProperty("status_code") int statusCode,
    @JsonProperty("data") T data,
    @JsonProperty("errors") List<String> errors,
    @JsonProperty("metadata") Map<String, Object> metadata
) {
    public ApiResponse {
        errors = errors != null ? List.copyOf(errors) : List.of();
        metadata = metadata != null ? Map.copyOf(metadata) : Map.of();
    }

    public static <T> ApiResponse<T> success(T data) {
        return new ApiResponse<>(200, data, List.of(), Map.of());
    }

    public static <T> ApiResponse<T> error(int code, String... errors) {
        return new ApiResponse<>(code, null, List.of(errors), Map.of());
    }

    public boolean isSuccess() { return statusCode >= 200 && statusCode < 300; }
}

// Testing records
class RecordTests {
    void testEquality() {
        var p1 = new Point(1.0, 2.0);
        var p2 = new Point(1.0, 2.0);
        assert p1.equals(p2);           // Structural equality
        assert p1.hashCode() == p2.hashCode();

        var m1 = Money.usd(1000);
        var m2 = Money.usd(500);
        assert m1.add(m2).equals(Money.usd(1500));
    }

    void testImmutability() {
        var team = new Team("Dev", List.of("Alice", "Bob"));
        var newTeam = team.addMember("Charlie");

        assert team.members().size() == 2;   // Original unchanged
        assert newTeam.members().size() == 3; // New copy has 3
    }
}
```

Records vs classes comparison:

| Feature | Record | Class |
|---------|--------|-------|
| Fields | Final (immutable) | Any access modifier |
| Constructor | Auto-generated canonical | Manual |
| equals/hashCode | Auto (structural) | Manual or IDE-generated |
| toString | Auto (all fields) | Manual |
| Inheritance | Cannot extend classes | Full inheritance |
| Implements | Interfaces only | Interfaces + extends |
| Mutable state | No (immutable) | Yes |
| Serializable | Yes (with annotation) | Yes |
| Pattern matching | Destructurable | No |
| Best for | DTOs, value objects, events | Stateful entities, services |

Key patterns:
1. Use compact constructors for validation — field assignments happen automatically after the body
2. Use `List.copyOf()` and `Map.copyOf()` in constructors for defensive copying of mutable collections
3. Records are ideal for DTOs, value objects, events, and intermediate computation results
4. Local records (declared inside methods) are excellent for ad-hoc data grouping in stream pipelines
5. The "with" pattern (`withStatus()`) creates modified copies since records are immutable
6. Sealed interfaces + records create type-safe algebraic data types with exhaustive pattern matching'''
    ),
    (
        "java/structured-concurrency",
        "Show Java structured concurrency (Project Loom) with StructuredTaskScope, subtask management, and error handling.",
        '''Java structured concurrency for managing concurrent subtask lifecycles:

```java
// --- StructuredTaskScope basics (Java 21+ preview) ---

import java.util.concurrent.*;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.*;
import java.time.Duration;
import java.time.Instant;

public class StructuredConcurrencyBasics {

    // Domain types
    public record User(String id, String name, String email) {}
    public record Account(String userId, long balanceCents) {}
    public record Preferences(String userId, String theme, String locale) {}
    public record UserProfile(User user, Account account, Preferences preferences) {}

    // ShutdownOnFailure: cancel all subtasks if any fails
    public static UserProfile fetchUserProfile(String userId) throws Exception {
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            // Fork concurrent subtasks — all managed by the scope
            Subtask<User> userTask = scope.fork(() ->
                fetchUser(userId));

            Subtask<Account> accountTask = scope.fork(() ->
                fetchAccount(userId));

            Subtask<Preferences> prefsTask = scope.fork(() ->
                fetchPreferences(userId));

            // Wait for all subtasks to complete (or fail)
            scope.join()               // Blocks until all complete
                 .throwIfFailed();      // Propagates first exception

            // All succeeded — extract results
            return new UserProfile(
                userTask.get(),
                accountTask.get(),
                prefsTask.get()
            );
        }
        // If any subtask fails, others are automatically cancelled
        // Scope is closed and all resources cleaned up
    }

    // ShutdownOnSuccess: return first successful result, cancel rest
    public static String fetchFromMirror(String key) throws Exception {
        try (var scope = new StructuredTaskScope.ShutdownOnSuccess<String>()) {
            // Race multiple mirrors — first to respond wins
            scope.fork(() -> fetchFromMirror1(key));
            scope.fork(() -> fetchFromMirror2(key));
            scope.fork(() -> fetchFromMirror3(key));

            scope.join();

            return scope.result();  // Returns first successful result
        }
    }

    // Simulated service calls
    private static User fetchUser(String id) throws InterruptedException {
        Thread.sleep(100);
        return new User(id, "Alice", "alice@example.com");
    }

    private static Account fetchAccount(String userId) throws InterruptedException {
        Thread.sleep(150);
        return new Account(userId, 50000);
    }

    private static Preferences fetchPreferences(String userId) throws InterruptedException {
        Thread.sleep(80);
        return new Preferences(userId, "dark", "en-US");
    }

    private static String fetchFromMirror1(String key) throws Exception {
        Thread.sleep(200); return "mirror1:" + key;
    }
    private static String fetchFromMirror2(String key) throws Exception {
        Thread.sleep(100); return "mirror2:" + key;
    }
    private static String fetchFromMirror3(String key) throws Exception {
        Thread.sleep(300); return "mirror3:" + key;
    }
}
```

```java
// --- Custom StructuredTaskScope policies ---

import java.util.concurrent.*;
import java.util.concurrent.StructuredTaskScope.Subtask;
import java.util.*;
import java.util.stream.*;

public class CustomScopes {

    // Custom scope: collect all results, tolerate partial failures
    public static class CollectingScope<T> extends StructuredTaskScope<T> {
        private final List<Subtask<T>> subtasks = Collections.synchronizedList(new ArrayList<>());

        @Override
        protected void handleComplete(Subtask<T> subtask) {
            subtasks.add(subtask);
        }

        public List<T> successfulResults() {
            return subtasks.stream()
                .filter(st -> st.state() == Subtask.State.SUCCESS)
                .map(Subtask::get)
                .toList();
        }

        public List<Throwable> errors() {
            return subtasks.stream()
                .filter(st -> st.state() == Subtask.State.FAILED)
                .map(Subtask::exception)
                .toList();
        }

        public int totalCount() { return subtasks.size(); }
    }

    // Usage: fetch from multiple sources, accept partial results
    public record SearchResult(String source, List<String> items) {}

    public static List<SearchResult> searchAllSources(String query) throws Exception {
        try (var scope = new CollectingScope<SearchResult>()) {
            scope.fork(() -> searchDatabase(query));
            scope.fork(() -> searchElasticsearch(query));
            scope.fork(() -> searchExternalAPI(query));

            scope.join();

            List<SearchResult> results = scope.successfulResults();
            List<Throwable> errors = scope.errors();

            if (!errors.isEmpty()) {
                System.err.printf("Warning: %d/%d sources failed%n",
                    errors.size(), scope.totalCount());
            }

            return results;
        }
    }

    // Deadline-aware scope with timeout
    public static UserProfile fetchWithTimeout(String userId, Duration timeout) throws Exception {
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            var userTask = scope.fork(() -> fetchUser(userId));
            var accountTask = scope.fork(() -> fetchAccount(userId));
            var prefsTask = scope.fork(() -> fetchPreferences(userId));

            scope.joinUntil(Instant.now().plus(timeout)); // Deadline
            scope.throwIfFailed();

            return new UserProfile(
                userTask.get(),
                accountTask.get(),
                prefsTask.get()
            );
        }
    }

    // Nested scopes for hierarchical task decomposition
    public record DashboardData(UserProfile profile, List<Order> orders, Analytics analytics) {}
    public record Order(String id, long totalCents) {}
    public record Analytics(int views, int clicks) {}

    public static DashboardData fetchDashboard(String userId) throws Exception {
        try (var outer = new StructuredTaskScope.ShutdownOnFailure()) {
            // Each subtask can itself use structured concurrency
            var profileTask = outer.fork(() -> fetchUserProfile(userId));
            var ordersTask = outer.fork(() -> fetchOrders(userId));
            var analyticsTask = outer.fork(() -> fetchAnalytics(userId));

            outer.join().throwIfFailed();

            return new DashboardData(
                profileTask.get(),
                ordersTask.get(),
                analyticsTask.get()
            );
        }
    }

    // Stub methods
    private static User fetchUser(String id) throws Exception { Thread.sleep(50); return new User(id, "a", "b"); }
    private static Account fetchAccount(String id) throws Exception { Thread.sleep(50); return new Account(id, 0); }
    private static Preferences fetchPreferences(String id) throws Exception { Thread.sleep(50); return new Preferences(id, "l", "e"); }
    private static UserProfile fetchUserProfile(String id) throws Exception { return new UserProfile(fetchUser(id), fetchAccount(id), fetchPreferences(id)); }
    private static List<Order> fetchOrders(String id) throws Exception { return List.of(); }
    private static Analytics fetchAnalytics(String id) throws Exception { return new Analytics(0, 0); }
    private static SearchResult searchDatabase(String q) throws Exception { return new SearchResult("db", List.of()); }
    private static SearchResult searchElasticsearch(String q) throws Exception { return new SearchResult("es", List.of()); }
    private static SearchResult searchExternalAPI(String q) throws Exception { return new SearchResult("api", List.of()); }
}
```

```java
// --- Comparison: structured vs unstructured concurrency ---

import java.util.concurrent.*;

public class ConcurrencyComparison {

    // BEFORE: Unstructured (thread leak risk)
    public static UserProfile unstructuredFetch(String userId) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(3);
        try {
            Future<User> userFuture = executor.submit(() -> fetchUser(userId));
            Future<Account> accountFuture = executor.submit(() -> fetchAccount(userId));
            Future<Preferences> prefsFuture = executor.submit(() -> fetchPreferences(userId));

            // Problem 1: If userFuture.get() throws, accountFuture and prefsFuture
            // continue running (thread/resource leak)
            User user = userFuture.get(5, TimeUnit.SECONDS);

            // Problem 2: If this line throws, prefsFuture leaks
            Account account = accountFuture.get(5, TimeUnit.SECONDS);

            Preferences prefs = prefsFuture.get(5, TimeUnit.SECONDS);
            return new UserProfile(user, account, prefs);
        } finally {
            executor.shutdown(); // May not cancel in-flight tasks
        }
    }

    // AFTER: Structured (no leaks, automatic cancellation)
    public static UserProfile structuredFetch(String userId) throws Exception {
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            var userTask = scope.fork(() -> fetchUser(userId));
            var accountTask = scope.fork(() -> fetchAccount(userId));
            var prefsTask = scope.fork(() -> fetchPreferences(userId));

            scope.join().throwIfFailed();
            // If ANY task fails → all others are cancelled automatically
            // Scope guarantees: no leaked threads, no dangling tasks

            return new UserProfile(
                userTask.get(),
                accountTask.get(),
                prefsTask.get()
            );
        }
    }

    private static User fetchUser(String id) throws Exception { return new User(id, "", ""); }
    private static Account fetchAccount(String id) throws Exception { return new Account(id, 0); }
    private static Preferences fetchPreferences(String id) throws Exception { return new Preferences(id, "", ""); }
    public record User(String id, String name, String email) {}
    public record Account(String userId, long balanceCents) {}
    public record Preferences(String userId, String theme, String locale) {}
    public record UserProfile(User user, Account account, Preferences preferences) {}
}
```

Structured concurrency scope comparison:

| Scope Policy | Behavior | Use Case |
|-------------|----------|----------|
| `ShutdownOnFailure` | Cancel all if any fails, throw first error | All-or-nothing (fan-out) |
| `ShutdownOnSuccess` | Return first success, cancel rest | Racing / hedged requests |
| Custom scope | Override `handleComplete` | Partial results, custom logic |
| `joinUntil(deadline)` | Timeout-aware join | SLA-bound operations |
| Nested scopes | Inner scope is a subtask of outer | Hierarchical decomposition |

Key patterns:
1. Structured concurrency guarantees: subtask lifetimes never exceed the scope — no thread leaks
2. `ShutdownOnFailure` is the default choice — it propagates the first failure and cancels siblings
3. `ShutdownOnSuccess` is ideal for racing/hedging — first successful response wins
4. Custom scopes with `handleComplete` enable partial-success patterns (best-effort fan-out)
5. Always use try-with-resources for scopes — `close()` waits for all subtasks and cleans up
6. Scopes compose naturally with virtual threads — each `fork()` creates a virtual thread'''
    ),
    (
        "java/stream-api-advanced",
        "Show Java Stream API advanced patterns including custom collectors, gatherers (JEP 473), parallel streams, and complex pipeline operations.",
        '''Java Stream API advanced patterns with collectors, gatherers, and parallel streams:

```java
// --- Custom collectors ---

import java.util.*;
import java.util.function.*;
import java.util.stream.*;
import static java.util.stream.Collectors.*;

public class AdvancedStreams {

    public record Product(String name, String category, double price, int quantity) {}
    public record Sale(String productName, double amount, String region, java.time.LocalDate date) {}

    // Complex grouping and aggregation
    public record CategoryStats(
        String category, long count, double totalRevenue,
        double avgPrice, double maxPrice, double minPrice
    ) {}

    public static Map<String, CategoryStats> categoryAnalysis(List<Product> products) {
        return products.stream()
            .collect(groupingBy(
                Product::category,
                collectingAndThen(
                    toList(),
                    prods -> {
                        DoubleSummaryStatistics stats = prods.stream()
                            .mapToDouble(Product::price)
                            .summaryStatistics();
                        double revenue = prods.stream()
                            .mapToDouble(p -> p.price() * p.quantity())
                            .sum();
                        return new CategoryStats(
                            prods.getFirst().category(),
                            stats.getCount(),
                            revenue,
                            stats.getAverage(),
                            stats.getMax(),
                            stats.getMin()
                        );
                    }
                )
            ));
    }

    // Custom collector: top N elements
    public static <T> Collector<T, ?, List<T>> topN(int n, Comparator<T> comparator) {
        return Collector.of(
            () -> new PriorityQueue<>(n + 1, comparator),
            (queue, item) -> {
                queue.offer(item);
                if (queue.size() > n) queue.poll();
            },
            (q1, q2) -> {
                q1.addAll(q2);
                while (q1.size() > n) q1.poll();
                return q1;
            },
            queue -> {
                List<T> result = new ArrayList<>(queue);
                result.sort(comparator.reversed());
                return result;
            }
        );
    }

    // Custom collector: partition into fixed-size batches
    public static <T> Collector<T, ?, List<List<T>>> batching(int batchSize) {
        return Collector.of(
            ArrayList<List<T>>::new,
            (batches, item) -> {
                if (batches.isEmpty() || batches.getLast().size() >= batchSize) {
                    batches.add(new ArrayList<>());
                }
                batches.getLast().add(item);
            },
            (left, right) -> {
                if (!left.isEmpty() && !right.isEmpty()) {
                    List<T> lastLeft = left.getLast();
                    if (lastLeft.size() < batchSize) {
                        List<T> firstRight = right.removeFirst();
                        int space = batchSize - lastLeft.size();
                        lastLeft.addAll(firstRight.subList(0, Math.min(space, firstRight.size())));
                        if (firstRight.size() > space) {
                            left.add(new ArrayList<>(firstRight.subList(space, firstRight.size())));
                        }
                    }
                }
                left.addAll(right);
                return left;
            }
        );
    }

    // Sliding window with streams
    public static <T> List<List<T>> slidingWindow(List<T> list, int windowSize) {
        return IntStream.rangeClosed(0, list.size() - windowSize)
            .mapToObj(i -> list.subList(i, i + windowSize))
            .map(ArrayList::new)
            .toList();
    }
}
```

```java
// --- Gatherers (JEP 473, Java 22+ preview) ---

import java.util.stream.Gatherers;
import java.util.stream.Gatherer;

public class GathererExamples {

    // Built-in gatherers (Java 22+)
    public static void builtInGatherers() {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6, 7, 8, 9, 10);

        // windowFixed: non-overlapping fixed-size windows
        List<List<Integer>> windows = numbers.stream()
            .gather(Gatherers.windowFixed(3))
            .toList();
        // [[1,2,3], [4,5,6], [7,8,9], [10]]

        // windowSliding: overlapping sliding windows
        List<List<Integer>> sliding = numbers.stream()
            .gather(Gatherers.windowSliding(3))
            .toList();
        // [[1,2,3], [2,3,4], [3,4,5], ...]

        // fold: stateful reduction producing intermediate results
        List<Integer> runningSums = numbers.stream()
            .gather(Gatherers.fold(() -> 0, Integer::sum))
            .toList();
        // [1, 3, 6, 10, 15, 21, 28, 36, 45, 55]

        // scan: like fold but emits each intermediate result
        List<Integer> scanned = numbers.stream()
            .gather(Gatherers.scan(() -> 0, Integer::sum))
            .toList();

        // mapConcurrent: bounded concurrent mapping
        List<String> results = numbers.stream()
            .gather(Gatherers.mapConcurrent(4, n -> {
                Thread.sleep(100); // Simulated I/O
                return "processed-" + n;
            }))
            .toList();
    }

    // Custom gatherer: deduplicate consecutive elements
    public static <T> Gatherer<T, ?, T> deduplicateConsecutive() {
        return Gatherer.ofSequential(
            () -> new Object() { T last = null; boolean hasLast = false; },
            (state, element, downstream) -> {
                if (!state.hasLast || !Objects.equals(state.last, element)) {
                    state.last = element;
                    state.hasLast = true;
                    return downstream.push(element);
                }
                return true; // Skip duplicate, continue
            }
        );
    }

    // Custom gatherer: rate-limited emission
    public static <T> Gatherer<T, ?, T> throttle(java.time.Duration interval) {
        return Gatherer.ofSequential(
            () -> new Object() { long lastEmit = 0; },
            (state, element, downstream) -> {
                long now = System.nanoTime();
                long intervalNanos = interval.toNanos();
                if (now - state.lastEmit >= intervalNanos) {
                    state.lastEmit = now;
                    return downstream.push(element);
                }
                return true;
            }
        );
    }

    // Composing gatherers
    public static void composedGatherers() {
        List<Integer> data = List.of(1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 7, 7, 8);

        List<List<Integer>> result = data.stream()
            .gather(deduplicateConsecutive())     // Remove consecutive dupes
            .gather(Gatherers.windowFixed(3))     // Group into windows of 3
            .toList();
        // [[1, 2, 3], [4, 5, 6], [7, 8]]
    }
}
```

```java
// --- Parallel streams and performance ---

import java.util.concurrent.*;
import java.util.stream.*;

public class ParallelStreamPatterns {

    // When to use parallel streams
    public static long parallelSum(List<Integer> numbers) {
        // Good: large dataset, simple reduction, no shared state
        return numbers.parallelStream()
            .mapToLong(Integer::longValue)
            .sum();
    }

    // Custom ForkJoinPool for parallel streams (isolate from common pool)
    public static <T> List<T> parallelWithCustomPool(
        Stream<T> stream, int parallelism
    ) throws Exception {
        ForkJoinPool customPool = new ForkJoinPool(parallelism);
        try {
            return customPool.submit(() ->
                stream.parallel().toList()
            ).get();
        } finally {
            customPool.shutdown();
        }
    }

    // Parallel-safe collector: thread-safe accumulation
    public static Map<String, Long> parallelWordCount(List<String> texts) {
        return texts.parallelStream()
            .flatMap(text -> Arrays.stream(text.split("\\\\s+")))
            .map(String::toLowerCase)
            .collect(groupingByConcurrent(
                Function.identity(),
                counting()
            ));
    }

    // Ordered vs unordered parallel performance
    public static void orderedVsUnordered(List<Integer> data) {
        // Ordered (preserves encounter order — slower)
        List<Integer> ordered = data.parallelStream()
            .filter(n -> n > 0)
            .sorted()
            .limit(100)
            .toList();

        // Unordered (no order guarantee — faster)
        Set<Integer> unordered = data.parallelStream()
            .unordered()
            .filter(n -> n > 0)
            .limit(100)
            .collect(Collectors.toSet());
    }

    // Complex pipeline combining multiple techniques
    public static Map<String, List<String>> analyzeProducts(List<Product> products) {
        return products.stream()
            .filter(p -> p.price() > 0 && p.quantity() > 0)
            .sorted(Comparator.comparing(Product::price).reversed())
            .collect(groupingBy(
                Product::category,
                collectingAndThen(
                    toList(),
                    prods -> prods.stream()
                        .limit(5)
                        .map(Product::name)
                        .toList()
                )
            ));
    }

    public record Product(String name, String category, double price, int quantity) {}
}
```

Stream operation categories:

| Category | Operations | Parallel-Safe? |
|----------|-----------|---------------|
| Stateless intermediate | `filter`, `map`, `flatMap` | Yes |
| Stateful intermediate | `sorted`, `distinct`, `limit` | Yes (but slower) |
| Terminal (reducing) | `reduce`, `collect`, `sum`, `count` | Yes (with associative ops) |
| Terminal (iterating) | `forEach`, `forEachOrdered` | `forEach` unordered, `forEachOrdered` ordered |
| Short-circuiting | `findFirst`, `findAny`, `anyMatch` | `findAny` faster in parallel |
| Custom collectors | `Collector.of(...)` | Need combiner for parallel |
| Gatherers (Java 22+) | `gather(Gatherers.xxx())` | Sequential by default |

Key patterns:
1. Custom collectors need four functions: supplier, accumulator, combiner (for parallel), finisher
2. Gatherers (Java 22+) fill gaps collectors cannot: windowing, stateful mapping, concurrent mapping
3. Use `groupingByConcurrent` instead of `groupingBy` in parallel streams for thread-safe map collection
4. Parallel streams use the common ForkJoinPool by default — use a custom pool to avoid starving other tasks
5. Use `.unordered()` before `.limit()` in parallel streams for significant performance improvement
6. Avoid parallel streams for I/O-bound work — use virtual threads with structured concurrency instead'''
    ),
]
