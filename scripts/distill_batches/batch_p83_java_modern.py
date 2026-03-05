"""Java — streams API, records, sealed classes, virtual threads, and pattern matching."""

PAIRS = [
    (
        "java/streams-api",
        "Show Java Streams API patterns: map, filter, reduce, collectors, parallel streams, and custom collectors.",
        '''Java Streams API patterns:

```java
import java.util.*;
import java.util.stream.*;
import java.util.function.*;
import java.util.Map.Entry;

public class StreamPatterns {

    record Order(String id, String customerId, double total,
                 String status, List<String> tags) {}

    // --- Basic operations ---

    public static void basics(List<Order> orders) {
        // Filter + map + collect
        List<String> activeOrderIds = orders.stream()
            .filter(o -> "active".equals(o.status()))
            .map(Order::id)
            .collect(Collectors.toList());

        // toList() shorthand (Java 16+)
        var ids = orders.stream()
            .map(Order::id)
            .toList();  // Returns unmodifiable list

        // Reduce
        double totalRevenue = orders.stream()
            .filter(o -> "completed".equals(o.status()))
            .mapToDouble(Order::total)
            .sum();

        // Average with Optional
        OptionalDouble avgOrder = orders.stream()
            .mapToDouble(Order::total)
            .average();

        // Find
        Optional<Order> bigOrder = orders.stream()
            .filter(o -> o.total() > 1000)
            .findFirst();

        // All match / any match
        boolean allCompleted = orders.stream()
            .allMatch(o -> "completed".equals(o.status()));
    }


    // --- Grouping and partitioning ---

    public static void grouping(List<Order> orders) {
        // Group by status
        Map<String, List<Order>> byStatus = orders.stream()
            .collect(Collectors.groupingBy(Order::status));

        // Group by status, count per group
        Map<String, Long> countByStatus = orders.stream()
            .collect(Collectors.groupingBy(
                Order::status, Collectors.counting()));

        // Group by status, sum totals
        Map<String, Double> revenueByStatus = orders.stream()
            .collect(Collectors.groupingBy(
                Order::status,
                Collectors.summingDouble(Order::total)));

        // Partition (true/false split)
        Map<Boolean, List<Order>> partitioned = orders.stream()
            .collect(Collectors.partitioningBy(o -> o.total() > 100));

        // Nested grouping
        Map<String, Map<String, List<Order>>> nested = orders.stream()
            .collect(Collectors.groupingBy(
                Order::status,
                Collectors.groupingBy(Order::customerId)));
    }


    // --- FlatMap and distinct ---

    public static void flatMapExample(List<Order> orders) {
        // Flatten nested collections
        Set<String> allTags = orders.stream()
            .flatMap(o -> o.tags().stream())
            .collect(Collectors.toSet());

        // Distinct values
        List<String> uniqueCustomers = orders.stream()
            .map(Order::customerId)
            .distinct()
            .sorted()
            .toList();
    }


    // --- Collectors.toMap ---

    public static void toMapExamples(List<Order> orders) {
        // Simple toMap
        Map<String, Order> orderById = orders.stream()
            .collect(Collectors.toMap(Order::id, Function.identity()));

        // Handle duplicates (merge function)
        Map<String, Double> totalByCustomer = orders.stream()
            .collect(Collectors.toMap(
                Order::customerId,
                Order::total,
                Double::sum  // Merge: sum totals for same customer
            ));

        // Joining strings
        String summary = orders.stream()
            .map(o -> o.id() + ": $" + o.total())
            .collect(Collectors.joining(", ", "[", "]"));
    }


    // --- Custom collector ---

    public static <T> Collector<T, ?, Map<String, List<T>>>
    groupByFirstLetter(Function<T, String> nameExtractor) {
        return Collectors.groupingBy(
            item -> {
                String name = nameExtractor.apply(item);
                return name.isEmpty() ? "#" : name.substring(0, 1).toUpperCase();
            }
        );
    }


    // --- Stream from various sources ---

    public static void streamSources() {
        // From values
        Stream.of("a", "b", "c").toList();

        // Infinite streams
        Stream.iterate(0, n -> n + 2).limit(10).toList(); // [0, 2, 4, ..., 18]
        Stream.generate(Math::random).limit(5).toList();

        // From string
        "hello".chars().mapToObj(c -> (char) c).toList();

        // IntStream range
        IntStream.rangeClosed(1, 100).sum();

        // Concatenate streams
        Stream.concat(stream1, stream2).toList();
    }
}
```

Streams patterns:
1. **`Collectors.groupingBy()`** — group elements with optional downstream collector
2. **`flatMap()`** — flatten nested collections into single stream
3. **`Collectors.toMap()`** — with merge function for duplicate keys
4. **`mapToDouble().sum()`** — primitive specialization avoids boxing
5. **`Stream.iterate()`** — generate infinite sequences with seed and function'''
    ),
    (
        "java/records-sealed",
        "Show Java records, sealed classes, and pattern matching patterns.",
        '''Java records, sealed classes, and pattern matching:

```java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

// --- Records (immutable data carriers, Java 16+) ---

// Generates: constructor, getters, equals, hashCode, toString
public record User(String id, String name, String email, Instant createdAt) {

    // Compact constructor (validation)
    public User {
        Objects.requireNonNull(id, "id cannot be null");
        Objects.requireNonNull(email, "email cannot be null");
        if (!email.contains("@")) {
            throw new IllegalArgumentException("Invalid email: " + email);
        }
        email = email.toLowerCase(); // Can reassign in compact constructor
    }

    // Factory method
    public static User create(String name, String email) {
        return new User(
            java.util.UUID.randomUUID().toString(),
            name,
            email,
            Instant.now()
        );
    }

    // Custom method
    public String displayName() {
        return name != null ? name : email.split("@")[0];
    }
}


// --- Sealed classes (restricted hierarchy, Java 17+) ---

public sealed interface Shape
    permits Circle, Rectangle, Triangle {

    double area();
    double perimeter();
}

public record Circle(double radius) implements Shape {
    public double area() { return Math.PI * radius * radius; }
    public double perimeter() { return 2 * Math.PI * radius; }
}

public record Rectangle(double width, double height) implements Shape {
    public double area() { return width * height; }
    public double perimeter() { return 2 * (width + height); }
}

public record Triangle(double a, double b, double c) implements Shape {
    public double area() {
        double s = (a + b + c) / 2;
        return Math.sqrt(s * (s - a) * (s - b) * (s - c));
    }
    public double perimeter() { return a + b + c; }
}


// --- Pattern matching for switch (Java 21+) ---

public static String describe(Shape shape) {
    return switch (shape) {
        case Circle c when c.radius() > 100 ->
            "Large circle with radius " + c.radius();
        case Circle c ->
            "Circle with radius " + c.radius();
        case Rectangle r when r.width() == r.height() ->
            "Square with side " + r.width();
        case Rectangle r ->
            "Rectangle " + r.width() + "x" + r.height();
        case Triangle t ->
            "Triangle with sides " + t.a() + ", " + t.b() + ", " + t.c();
    };
}


// --- Sealed interface for Result type ---

public sealed interface Result<T>
    permits Result.Success, Result.Failure {

    record Success<T>(T value) implements Result<T> {}
    record Failure<T>(String error) implements Result<T> {}

    static <T> Result<T> of(T value) {
        return new Success<>(value);
    }

    static <T> Result<T> error(String message) {
        return new Failure<>(message);
    }

    default <U> Result<U> map(java.util.function.Function<T, U> fn) {
        return switch (this) {
            case Success<T> s -> Result.of(fn.apply(s.value()));
            case Failure<T> f -> Result.error(f.error());
        };
    }
}


// --- Pattern matching for instanceof (Java 16+) ---

public static double calculateArea(Object shape) {
    if (shape instanceof Circle c) {
        return c.area();
    } else if (shape instanceof Rectangle r && r.width() > 0) {
        return r.area();
    }
    throw new IllegalArgumentException("Unknown shape: " + shape);
}


// --- Record patterns (Java 21+) ---

record Point(int x, int y) {}
record Line(Point start, Point end) {}

public static String describeLine(Object obj) {
    return switch (obj) {
        // Destructure nested records
        case Line(Point(var x1, var y1), Point(var x2, var y2)) ->
            "Line from (%d,%d) to (%d,%d)".formatted(x1, y1, x2, y2);
        case Point(var x, var y) ->
            "Point at (%d,%d)".formatted(x, y);
        default ->
            "Unknown: " + obj;
    };
}
```

Java modern patterns:
1. **Records** — immutable data classes with auto-generated methods
2. **Sealed interfaces** — exhaustive hierarchies the compiler can check
3. **Pattern matching switch** — `case Circle c when ...` with guards
4. **Record patterns** — destructure nested records in switch/instanceof
5. **`Result<T>`** — sealed type for success/failure without exceptions'''
    ),
    (
        "java/virtual-threads",
        "Show Java virtual threads patterns: structured concurrency, scoped values, and high-throughput servers.",
        '''Java virtual threads (Project Loom, Java 21+):

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.*;
import java.util.stream.IntStream;

public class VirtualThreadPatterns {

    // --- Basic virtual threads ---

    public static void basics() throws Exception {
        // Start virtual thread (lightweight, not OS thread)
        Thread vt = Thread.startVirtualThread(() -> {
            System.out.println("Running on: " + Thread.currentThread());
        });
        vt.join();

        // Virtual thread factory
        ThreadFactory factory = Thread.ofVirtual()
            .name("worker-", 0)
            .factory();

        Thread t = factory.newThread(() -> doWork());
        t.start();

        // ExecutorService with virtual threads
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            // Each task gets its own virtual thread
            // Can handle millions of concurrent tasks
            IntStream.range(0, 10_000).forEach(i -> {
                executor.submit(() -> {
                    // Blocking I/O is fine — virtual thread yields
                    Thread.sleep(Duration.ofSeconds(1));
                    return fetchData(i);
                });
            });
        } // Auto-shutdown: waits for all tasks to complete
    }


    // --- Structured concurrency (preview) ---

    record UserProfile(User user, List<Order> orders, List<Review> reviews) {}

    public static UserProfile loadProfile(String userId)
            throws ExecutionException, InterruptedException {

        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            // Fork subtasks — each runs in its own virtual thread
            Subtask<User> userTask = scope.fork(() ->
                fetchUser(userId));

            Subtask<List<Order>> ordersTask = scope.fork(() ->
                fetchOrders(userId));

            Subtask<List<Review>> reviewsTask = scope.fork(() ->
                fetchReviews(userId));

            // Wait for all subtasks (or first failure)
            scope.join()
                 .throwIfFailed();

            // All succeeded — combine results
            return new UserProfile(
                userTask.get(),
                ordersTask.get(),
                reviewsTask.get()
            );
        }
        // If any subtask fails, others are automatically cancelled
    }


    // --- ShutdownOnSuccess (race pattern) ---

    public static String fetchFromFastestMirror(List<String> mirrorUrls)
            throws ExecutionException, InterruptedException {

        try (var scope = new StructuredTaskScope.ShutdownOnSuccess<String>()) {
            for (String url : mirrorUrls) {
                scope.fork(() -> fetchFromUrl(url));
            }

            scope.join();
            return scope.result(); // First successful result
        }
        // Remaining tasks are cancelled when first succeeds
    }


    // --- Scoped values (virtual thread-local, Java 21 preview) ---

    static final ScopedValue<String> CURRENT_USER = ScopedValue.newInstance();
    static final ScopedValue<String> REQUEST_ID = ScopedValue.newInstance();

    public static void handleRequest(String userId, String requestId) {
        ScopedValue
            .where(CURRENT_USER, userId)
            .where(REQUEST_ID, requestId)
            .run(() -> {
                // All code in this scope can read these values
                processRequest();
            });
    }

    private static void processRequest() {
        String user = CURRENT_USER.get();      // Available without passing
        String reqId = REQUEST_ID.get();
        System.out.println("Processing for " + user + " [" + reqId + "]");
        // Scoped values are inherited by child virtual threads
    }


    // --- High-throughput HTTP server ---

    // import com.sun.net.httpserver.HttpServer;
    //
    // public static void startServer() throws Exception {
    //     var server = HttpServer.create(
    //         new java.net.InetSocketAddress(8080), 0
    //     );
    //
    //     // Virtual thread executor handles millions of concurrent requests
    //     server.setExecutor(Executors.newVirtualThreadPerTaskExecutor());
    //
    //     server.createContext("/api/users", exchange -> {
    //         // Each request in its own virtual thread
    //         // Blocking I/O (DB, HTTP calls) is fine
    //         String response = fetchUserFromDB(exchange.getRequestURI());
    //         exchange.sendResponseHeaders(200, response.length());
    //         exchange.getResponseBody().write(response.getBytes());
    //         exchange.close();
    //     });
    //
    //     server.start();
    // }


    // --- Migration from thread pools ---

    // BEFORE (platform threads — limited):
    // var executor = Executors.newFixedThreadPool(200);

    // AFTER (virtual threads — unlimited):
    // var executor = Executors.newVirtualThreadPerTaskExecutor();

    // IMPORTANT: Don't pool virtual threads — they're cheap to create
    // IMPORTANT: Avoid synchronized blocks (use ReentrantLock instead)
    // IMPORTANT: Don't use ThreadLocal (use ScopedValue instead)
}
```

Virtual thread patterns:
1. **`newVirtualThreadPerTaskExecutor()`** — one virtual thread per task, millions ok
2. **`StructuredTaskScope`** — fork/join with automatic cancellation on failure
3. **`ShutdownOnSuccess`** — race pattern, first result wins
4. **`ScopedValue`** — lightweight context propagation (replaces ThreadLocal)
5. **No pooling needed** — virtual threads are cheap, create per-task not per-pool'''
    ),
]
"""
