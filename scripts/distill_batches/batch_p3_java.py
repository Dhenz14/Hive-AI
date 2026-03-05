"""
Batch P3 — Java: Modern Java features, virtual threads, GraalVM, Spring Boot 3.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Java Virtual Threads (Project Loom) ---
    (
        "java_virtual_threads_loom",
        "Explain Java virtual threads from Project Loom — how they differ from platform threads, "
        "the continuation-based implementation, structured concurrency with StructuredTaskScope, "
        "and how to migrate existing thread-pool-based applications. Show production code with "
        "proper error handling, testing, and performance comparison against platform threads.",
        """\
# Java Virtual Threads: Million-Thread Concurrency

## Why Virtual Threads Change Everything

Java's platform threads are **OS threads** — each one costs ~1MB of stack space and requires
a kernel context switch. This means a typical server can handle ~10,000 concurrent platform
threads before running out of memory. Virtual threads remove this limitation by implementing
**user-space scheduling** — they're managed by the JVM, not the OS.

```
Platform threads (before Loom):
  Thread → OS thread → kernel scheduling → 1MB stack → limited to ~10K

Virtual threads (with Loom):
  Virtual thread → JVM continuation → carrier thread → ~1KB overhead → millions possible

The key insight: virtual threads are cheap to create and cheap to block.
Blocking a virtual thread (I/O wait, sleep, lock) simply parks it and
frees the carrier thread for another virtual thread. No OS thread is wasted.
```

**When to use virtual threads**: Any I/O-bound workload — HTTP servers, database clients,
message consumers. NOT for CPU-bound work (virtual threads share carrier threads).

## Implementation Internals

```java
/**
 * Virtual thread scheduling works through continuations:
 *
 * 1. VThread starts on a carrier thread (ForkJoinPool)
 * 2. When VThread blocks (I/O, sleep, lock), the JVM:
 *    a. Saves the VThread's stack as a continuation (heap-allocated)
 *    b. Unmounts VThread from carrier thread
 *    c. Carrier thread picks up another VThread from the queue
 * 3. When blocking operation completes:
 *    a. VThread is re-scheduled to a carrier thread
 *    b. Stack is restored from continuation
 *    c. Execution resumes exactly where it left off
 *
 * This is why virtual threads are "cheap" — a blocked VThread
 * consumes only heap memory (~1KB), not an OS thread.
 */
```

## Production HTTP Server

```java
package com.example.server;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.ArrayList;
import java.util.concurrent.*;
import java.util.stream.Collectors;

/**
 * Production HTTP service using virtual threads for high-concurrency I/O.
 * This server can handle 100K+ concurrent requests on a single JVM
 * because each request runs in a virtual thread that costs ~1KB.
 */
public class ProductService implements AutoCloseable {

    private final HttpClient httpClient;
    private final ExecutorService executor;
    private final String apiBaseUrl;

    public ProductService(String apiBaseUrl) {
        this.apiBaseUrl = apiBaseUrl;
        // Virtual thread executor — creates a new virtual thread per task
        // No thread pool sizing needed — the JVM handles scheduling
        this.executor = Executors.newVirtualThreadPerTaskExecutor();

        // HttpClient using virtual threads for I/O
        this.httpClient = HttpClient.newBuilder()
            .executor(executor)
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    }

    /**
     * Fetch product details from multiple microservices concurrently.
     *
     * With platform threads, this would require a bounded thread pool
     * and careful sizing. With virtual threads, we just create one per
     * request — the JVM efficiently multiplexes them onto carrier threads.
     */
    public ProductDetails getProductDetails(String productId)
            throws InterruptedException, ExecutionException {

        // Structured concurrency — all subtasks complete or fail together
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {

            // Fan out: 4 concurrent calls to different services
            var productFuture = scope.fork(() ->
                fetchJson(apiBaseUrl + "/products/" + productId));

            var pricingFuture = scope.fork(() ->
                fetchJson(apiBaseUrl + "/pricing/" + productId));

            var inventoryFuture = scope.fork(() ->
                fetchJson(apiBaseUrl + "/inventory/" + productId));

            var reviewsFuture = scope.fork(() ->
                fetchJson(apiBaseUrl + "/reviews/" + productId));

            // Wait for all to complete (or first failure)
            scope.join();
            scope.throwIfFailed();

            // All succeeded — combine results
            return new ProductDetails(
                productFuture.get(),
                pricingFuture.get(),
                inventoryFuture.get(),
                reviewsFuture.get()
            );
        }
    }

    /**
     * Batch fetch with concurrency limit — prevents overwhelming downstream services.
     *
     * Even with virtual threads, you need to limit concurrent outbound connections.
     * A Semaphore provides the throttle without wasting OS threads while waiting.
     */
    public List<String> batchFetch(List<String> urls, int maxConcurrency)
            throws InterruptedException {

        Semaphore semaphore = new Semaphore(maxConcurrency);
        List<Future<String>> futures = new ArrayList<>();

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            for (String url : urls) {
                futures.add(executor.submit(() -> {
                    semaphore.acquire();
                    try {
                        return fetchJson(url);
                    } finally {
                        semaphore.release();
                    }
                }));
            }
        }

        return futures.stream()
            .map(f -> {
                try {
                    return f.get(30, TimeUnit.SECONDS);
                } catch (Exception e) {
                    return "{\"error\": \"" + e.getMessage() + "\"}";
                }
            })
            .collect(Collectors.toList());
    }

    private String fetchJson(String url) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .header("Accept", "application/json")
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        HttpResponse<String> response = httpClient.send(
            request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() >= 400) {
            throw new RuntimeException(
                "HTTP " + response.statusCode() + " from " + url);
        }
        return response.body();
    }

    @Override
    public void close() {
        executor.close();
    }
}

record ProductDetails(
    String product,
    String pricing,
    String inventory,
    String reviews
) {}
```

## Structured Concurrency Deep Dive

```java
/**
 * StructuredTaskScope ensures that concurrent subtasks have a clear lifecycle:
 * - All subtasks complete before the scope exits
 * - If one fails, others are cancelled (ShutdownOnFailure)
 * - No orphaned threads — unlike raw CompletableFuture chains
 *
 * This is critical because without structured concurrency, cancellation
 * is notoriously hard. Consider: if pricing service fails, you want to
 * cancel the still-running reviews call. CompletableFuture doesn't do
 * this automatically — you must wire up cancellation manually.
 */

// Pattern 1: Fail fast — first failure cancels everything
public String failFast() throws Exception {
    try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
        var task1 = scope.fork(() -> riskyOperation1());
        var task2 = scope.fork(() -> riskyOperation2());
        scope.join().throwIfFailed();
        return task1.get() + task2.get();
    }
}

// Pattern 2: First success — take the fastest response
public String raceForFirst() throws Exception {
    try (var scope = new StructuredTaskScope.ShutdownOnSuccess<String>()) {
        // Query multiple replicas — use the first response
        scope.fork(() -> queryReplica("us-east"));
        scope.fork(() -> queryReplica("us-west"));
        scope.fork(() -> queryReplica("eu-west"));
        scope.join();
        return scope.result();  // Returns first successful result
    }
}

// Pattern 3: Custom policy — collect partial results
public class CollectingScope<T> extends StructuredTaskScope<T> {
    private final List<T> results = new CopyOnWriteArrayList<>();
    private final List<Throwable> errors = new CopyOnWriteArrayList<>();

    @Override
    protected void handleComplete(Subtask<? extends T> subtask) {
        switch (subtask.state()) {
            case SUCCESS -> results.add(subtask.get());
            case FAILED -> errors.add(subtask.exception());
            case UNAVAILABLE -> {} // Cancelled
        }
    }

    public List<T> results() { return results; }
    public List<Throwable> errors() { return errors; }
}
```

## Performance Comparison

```java
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Benchmark: virtual threads vs platform threads for I/O-bound work.
 */
public class ThreadBenchmark {

    static AtomicInteger completed = new AtomicInteger(0);

    /** Simulate an I/O operation (database query, HTTP call) */
    static void simulatedIO() {
        try {
            Thread.sleep(Duration.ofMillis(100)); // 100ms I/O wait
            completed.incrementAndGet();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        int taskCount = 100_000;

        // Platform threads — limited by OS thread capacity
        System.out.println("Platform threads (capped at 1000):");
        completed.set(0);
        long start = System.currentTimeMillis();
        try (var exec = Executors.newFixedThreadPool(1000)) {
            for (int i = 0; i < taskCount; i++) {
                exec.submit(ThreadBenchmark::simulatedIO);
            }
        }
        long platformTime = System.currentTimeMillis() - start;
        System.out.printf("  %d tasks in %dms%n", completed.get(), platformTime);

        // Virtual threads — no limit
        System.out.println("Virtual threads:");
        completed.set(0);
        start = System.currentTimeMillis();
        try (var exec = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < taskCount; i++) {
                exec.submit(ThreadBenchmark::simulatedIO);
            }
        }
        long virtualTime = System.currentTimeMillis() - start;
        System.out.printf("  %d tasks in %dms%n", completed.get(), virtualTime);

        // Typical results:
        // Platform threads (1000 pool): 100K tasks in ~10,000ms (batched, 100 at a time)
        // Virtual threads: 100K tasks in ~200ms (all 100K concurrent, each sleeping 100ms)
        System.out.printf("Speedup: %.1fx%n", (double) platformTime / virtualTime);
    }
}
```

## Testing Virtual Thread Code

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.atomic.AtomicInteger;

class ProductServiceTest {

    @Test
    @Timeout(5) // Fail if test takes >5 seconds
    void testBatchFetchRespectsMaxConcurrency() throws Exception {
        AtomicInteger activeCalls = new AtomicInteger(0);
        AtomicInteger maxActive = new AtomicInteger(0);

        // Mock server that tracks concurrent calls
        var service = new ProductService("http://localhost:8080");

        // Verify max concurrency is respected
        var results = service.batchFetch(
            List.of("url1", "url2", "url3", "url4", "url5"),
            2  // Max 2 concurrent
        );

        assertEquals(5, results.size());
    }

    @Test
    void testStructuredConcurrencyCancellation() throws Exception {
        // Verify that when one subtask fails, others are cancelled
        AtomicInteger completedTasks = new AtomicInteger(0);

        assertThrows(ExecutionException.class, () -> {
            try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
                scope.fork(() -> {
                    Thread.sleep(10);
                    throw new RuntimeException("Intentional failure");
                });
                scope.fork(() -> {
                    Thread.sleep(5000); // Would take 5s if not cancelled
                    completedTasks.incrementAndGet();
                    return "done";
                });
                scope.join().throwIfFailed();
            }
        });

        // The slow task should have been cancelled
        assertEquals(0, completedTasks.get());
    }
}
```

## Migration Pitfalls

**Common mistake 1**: Using `synchronized` with virtual threads. When a virtual thread
enters a `synchronized` block, it **pins** the carrier thread (can't unmount). Use
`ReentrantLock` instead, which supports virtual thread parking.

**Common mistake 2**: Using `ThreadLocal` for caching. Virtual threads are cheap and
numerous — ThreadLocal creates one cache per virtual thread (potentially millions).
Use scoped values (`ScopedValue`) or shared concurrent data structures instead.

**Common mistake 3**: CPU-bound work in virtual threads. Virtual threads share a small
ForkJoinPool of carrier threads (default: CPU core count). CPU-intensive tasks block the
carrier thread and starve other virtual threads. Use platform threads for compute.

## Key Takeaways

Virtual threads are the most significant Java feature since lambdas. They eliminate the
need for reactive programming (CompletableFuture chains, WebFlux) for I/O-bound workloads,
because blocking is now cheap. However, they're not a universal solution — CPU-bound work
still needs platform threads, and you must avoid pinning (synchronized blocks) and excessive
ThreadLocal usage. The trade-off is simplicity: virtual thread code reads like sequential
blocking code but performs like asynchronous code.
"""
    ),

    # --- 2. GraalVM Native Image ---
    (
        "graalvm_native_image_production",
        "Explain GraalVM Native Image — ahead-of-time compilation for Java, the closed-world "
        "assumption, reflection configuration, and how to build production microservices with "
        "instant startup and low memory. Show a complete Spring Boot 3 native image build with "
        "custom hints, testing native images, and performance comparison against JIT.",
        """\
# GraalVM Native Image: Instant Startup Java

## Why Native Image?

Traditional Java:
1. JVM starts → loads classes → interprets bytecode → JIT compiles hot paths
2. Startup: 2-10 seconds, memory: 200-500MB for a simple service
3. Peak performance: excellent (after JIT warmup), but slow to start

GraalVM Native Image:
1. AOT (Ahead-of-Time) compiles Java to a native binary at build time
2. Startup: 10-50 milliseconds, memory: 30-80MB
3. Peak performance: good (no JIT optimization), but instant startup

**Trade-off**: Native image sacrifices peak throughput (no JIT runtime optimization) for
dramatically better startup time and memory usage. This makes it ideal for:
- **Serverless functions**: cold start matters (Lambda, Cloud Run)
- **CLI tools**: instant response time
- **Microservices**: fast scaling, low memory per instance
- **Containers**: smaller images, faster deployment

## The Closed-World Assumption

Native Image requires all reachable code to be known at **build time**. This means:

```
WORKS in Native Image:
  - Static method calls
  - Known class hierarchies
  - Compile-time constants
  - Most standard library usage

REQUIRES CONFIGURATION:
  - Reflection (Class.forName, getDeclaredMethods)
  - Dynamic proxies (java.lang.reflect.Proxy)
  - JNI calls
  - Resource loading (getResource)
  - Serialization

DOESN'T WORK:
  - Runtime class generation (some bytecode manipulation)
  - Some Java agents
  - invokedynamic patterns that generate classes at runtime
```

## Spring Boot 3 Native Image Application

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.*;
import org.springframework.stereotype.Service;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.http.ResponseEntity;
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;

import jakarta.persistence.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

// Entity — JPA reflection is auto-configured by Spring AOT
@Entity
@Table(name = "products")
class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    private String name;

    @Positive
    private double price;

    @Column(name = "created_at")
    private Instant createdAt = Instant.now();

    // Getters, setters, constructors
    public Product() {}
    public Product(String name, double price) {
        this.name = name;
        this.price = price;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public double getPrice() { return price; }
    public Instant getCreatedAt() { return createdAt; }
    public void setName(String name) { this.name = name; }
    public void setPrice(double price) { this.price = price; }
}

// Repository — Spring Data JPA works with native image via AOT processing
interface ProductRepository extends JpaRepository<Product, Long> {
    List<Product> findByPriceGreaterThan(double minPrice);
    List<Product> findByNameContainingIgnoreCase(String keyword);
}

// DTO — must register for reflection if used with Jackson serialization
record ProductDTO(
    Long id,
    String name,
    double price,
    String createdAt
) {
    static ProductDTO from(Product p) {
        return new ProductDTO(p.getId(), p.getName(), p.getPrice(),
            p.getCreatedAt().toString());
    }
}

record CreateProductRequest(
    @NotBlank String name,
    @Positive double price
) {}

// REST Controller
@RestController
@RequestMapping("/api/products")
class ProductController {
    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping
    List<ProductDTO> list(
        @RequestParam(required = false) String keyword,
        @RequestParam(defaultValue = "0") double minPrice
    ) {
        if (keyword != null) {
            return productService.search(keyword);
        }
        if (minPrice > 0) {
            return productService.findAbovePrice(minPrice);
        }
        return productService.findAll();
    }

    @PostMapping
    ResponseEntity<ProductDTO> create(@Valid @RequestBody CreateProductRequest req) {
        ProductDTO created = productService.create(req.name(), req.price());
        return ResponseEntity.status(201).body(created);
    }

    @GetMapping("/{id}")
    ResponseEntity<ProductDTO> get(@PathVariable Long id) {
        return productService.findById(id)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }
}

// Service layer
@Service
class ProductService {
    private final ProductRepository repository;

    ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    List<ProductDTO> findAll() {
        return repository.findAll().stream().map(ProductDTO::from).toList();
    }

    Optional<ProductDTO> findById(Long id) {
        return repository.findById(id).map(ProductDTO::from);
    }

    List<ProductDTO> findAbovePrice(double minPrice) {
        return repository.findByPriceGreaterThan(minPrice)
            .stream().map(ProductDTO::from).toList();
    }

    List<ProductDTO> search(String keyword) {
        return repository.findByNameContainingIgnoreCase(keyword)
            .stream().map(ProductDTO::from).toList();
    }

    ProductDTO create(String name, double price) {
        Product product = repository.save(new Product(name, price));
        return ProductDTO.from(product);
    }
}
```

## Build Configuration

```xml
<!-- pom.xml — key native image configuration -->
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.0</version>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
            <configuration>
                <buildArgs>
                    <!-- Optimize for size (serverless) or speed (long-running) -->
                    <arg>-O2</arg>
                    <arg>--gc=serial</arg>  <!-- Serial GC for low memory -->
                    <arg>-march=native</arg> <!-- CPU-specific optimizations -->
                    <arg>--enable-url-protocols=http,https</arg>
                    <!-- Build-time initialization for faster startup -->
                    <arg>--initialize-at-build-time=org.h2</arg>
                </buildArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
```

## Custom Native Hints for Reflection

```java
/**
 * RuntimeHintsRegistrar — tell GraalVM about dynamic features.
 *
 * Spring AOT handles most reflection automatically (JPA entities, controllers,
 * Jackson serialization). You only need custom hints for:
 * - Third-party libraries that use reflection without Spring integration
 * - Custom annotation processing
 * - Dynamic resource loading
 */
import org.springframework.aot.hint.*;
import org.springframework.context.annotation.ImportRuntimeHints;

@ImportRuntimeHints(NativeHints.class)
@SpringBootApplication
public class DemoApplication { /* ... */ }

class NativeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        // Register types that need reflection
        hints.reflection()
            .registerType(ProductDTO.class, MemberCategory.values())
            .registerType(CreateProductRequest.class, MemberCategory.values());

        // Register resources that are loaded dynamically
        hints.resources()
            .registerPattern("db/migration/*.sql")
            .registerPattern("templates/*.html");

        // Register serialization classes
        hints.serialization()
            .registerType(Product.class);
    }
}
```

## Testing Native Images

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;

// This test runs in BOTH JVM and native mode
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ProductControllerIntegrationTest {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void createAndRetrieveProduct() {
        // Create
        var request = new CreateProductRequest("Widget", 9.99);
        var createResponse = restTemplate.postForEntity(
            "/api/products", request, ProductDTO.class);
        assertEquals(HttpStatus.CREATED, createResponse.getStatusCode());
        assertNotNull(createResponse.getBody().id());

        // Retrieve
        Long id = createResponse.getBody().id();
        var getResponse = restTemplate.getForEntity(
            "/api/products/" + id, ProductDTO.class);
        assertEquals(HttpStatus.OK, getResponse.getStatusCode());
        assertEquals("Widget", getResponse.getBody().name());
    }

    @Test
    void searchProducts() {
        restTemplate.postForEntity("/api/products",
            new CreateProductRequest("Blue Widget", 5.0), ProductDTO.class);
        restTemplate.postForEntity("/api/products",
            new CreateProductRequest("Red Gadget", 15.0), ProductDTO.class);

        var response = restTemplate.getForEntity(
            "/api/products?keyword=widget", ProductDTO[].class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertTrue(response.getBody().length >= 1);
    }
}
```

## Performance Comparison

```
                    JIT (JVM)         Native Image
Startup time        2.5s              0.035s (70x faster)
Memory (RSS)        280MB             48MB (6x less)
First request       2.6s              0.040s
Throughput (rps)    45,000            38,000 (15% lower at peak)
Binary size         JRE + JARs       65MB single binary
Container image     ~350MB            ~90MB

When to choose:
  JIT: Long-running services where peak throughput matters
  Native: Serverless, CLI tools, fast-scaling microservices
  Hybrid: Use CDS (Class Data Sharing) for moderate improvement
```

## Key Takeaways

GraalVM Native Image transforms Java from "slow to start, fast to run" into "instant start,
good throughput." The trade-off is the closed-world assumption — you must declare all
reflective access at build time, which requires more configuration effort. However, Spring
Boot 3's AOT engine handles most of this automatically, making native image practical
for production Spring applications. The common mistake is trying to make all services
native — focus on services where startup time and memory matter (serverless, scaling-heavy),
and keep long-running services on the JVM where JIT optimization provides better throughput.
"""
    ),

    # --- 2. Java Records, Sealed Classes, and Pattern Matching ---
    (
        "java_modern_patterns_21plus",
        "Explain Java 21+ modern features — records, sealed classes, pattern matching with switch "
        "expressions, and how they combine to create algebraic data types in Java. Show production "
        "patterns for domain modeling, JSON API design, and error handling using these features. "
        "Include proper testing approaches and explain how these features improve code safety.",
        """\
# Modern Java (21+): Algebraic Data Types and Pattern Matching

## The Evolution of Java's Type System

Java 21+ introduces features that, combined, give Java **algebraic data types** — a concept
from functional programming languages like Haskell, Rust, and Kotlin. This is significant
because algebraic types prevent entire categories of bugs at compile time.

```
Records         → Product types (data carriers with named fields)
Sealed classes  → Sum types (one of N possible types)
Pattern matching → Exhaustive destructuring (compiler checks all cases)
Combined        → Algebraic data types with compile-time safety
```

## Records: Immutable Data Carriers

```java
/**
 * Records replace boilerplate POJOs. They are:
 * - Immutable (fields are final)
 * - Automatically get equals(), hashCode(), toString()
 * - Perfect for DTOs, value objects, domain events
 *
 * The key benefit is NOT fewer lines — it's that records make
 * immutability the DEFAULT. Mutable state is the #1 source of bugs
 * in concurrent Java applications.
 */

// Domain value objects
record Money(double amount, String currency) {
    // Compact constructor — validation
    Money {
        if (amount < 0) throw new IllegalArgumentException("Amount cannot be negative");
        if (currency == null || currency.length() != 3)
            throw new IllegalArgumentException("Currency must be 3-letter ISO code");
        currency = currency.toUpperCase();
    }

    Money add(Money other) {
        if (!this.currency.equals(other.currency))
            throw new IllegalArgumentException("Cannot add different currencies");
        return new Money(this.amount + other.amount, this.currency);
    }

    Money multiply(double factor) {
        return new Money(this.amount * factor, this.currency);
    }
}

record EmailAddress(String value) {
    EmailAddress {
        if (value == null || !value.matches("^[^@]+@[^@]+\\\\.[^@]+$"))
            throw new IllegalArgumentException("Invalid email: " + value);
        value = value.toLowerCase().strip();
    }
}

// API response types — records make JSON serialization clean
record ApiResponse<T>(T data, String requestId, long timestamp) {
    static <T> ApiResponse<T> ok(T data) {
        return new ApiResponse<>(data, generateRequestId(), System.currentTimeMillis());
    }

    private static String generateRequestId() {
        return java.util.UUID.randomUUID().toString().substring(0, 8);
    }
}
```

## Sealed Classes: Controlled Inheritance

```java
/**
 * Sealed classes restrict which types can extend them.
 * Combined with records, they create sum types — a value is ONE OF the permitted types.
 *
 * The critical advantage: the compiler knows ALL possible subtypes,
 * so pattern matching can verify you've handled every case (exhaustiveness).
 * This prevents the "forgot to handle case X" bug category entirely.
 */

// Domain model: an order can be in exactly one of these states
sealed interface OrderState permits
    OrderState.Draft,
    OrderState.Pending,
    OrderState.Confirmed,
    OrderState.Shipped,
    OrderState.Delivered,
    OrderState.Cancelled {

    record Draft(List<OrderItem> items) implements OrderState {}
    record Pending(List<OrderItem> items, Money total, Instant submittedAt) implements OrderState {}
    record Confirmed(String orderId, Money total, Instant confirmedAt) implements OrderState {}
    record Shipped(String orderId, String trackingNumber, Instant shippedAt) implements OrderState {}
    record Delivered(String orderId, Instant deliveredAt) implements OrderState {}
    record Cancelled(String orderId, String reason, Instant cancelledAt) implements OrderState {}
}

record OrderItem(String productId, int quantity, Money price) {}

/**
 * State machine using pattern matching — compile-time exhaustiveness checking.
 *
 * This is a common mistake in traditional Java: using enums for state + mutable fields.
 * Each state carries DIFFERENT data, so using one class with nullable fields is error-prone.
 * Sealed records model this correctly: each state has exactly the data it needs.
 */
class OrderProcessor {

    OrderState transition(OrderState current, OrderEvent event) {
        return switch (current) {
            case OrderState.Draft draft -> switch (event) {
                case OrderEvent.Submit s ->
                    new OrderState.Pending(draft.items(), calculateTotal(draft.items()), Instant.now());
                default -> throw new InvalidTransition(current, event);
            };

            case OrderState.Pending pending -> switch (event) {
                case OrderEvent.Confirm c ->
                    new OrderState.Confirmed(c.orderId(), pending.total(), Instant.now());
                case OrderEvent.Cancel c ->
                    new OrderState.Cancelled("", c.reason(), Instant.now());
                default -> throw new InvalidTransition(current, event);
            };

            case OrderState.Confirmed confirmed -> switch (event) {
                case OrderEvent.Ship s ->
                    new OrderState.Shipped(confirmed.orderId(), s.trackingNumber(), Instant.now());
                case OrderEvent.Cancel c ->
                    new OrderState.Cancelled(confirmed.orderId(), c.reason(), Instant.now());
                default -> throw new InvalidTransition(current, event);
            };

            case OrderState.Shipped shipped -> switch (event) {
                case OrderEvent.Deliver d ->
                    new OrderState.Delivered(shipped.orderId(), Instant.now());
                default -> throw new InvalidTransition(current, event);
            };

            // Terminal states — no transitions allowed
            case OrderState.Delivered d -> throw new InvalidTransition(current, event);
            case OrderState.Cancelled c -> throw new InvalidTransition(current, event);
        };
        // NOTE: No default case needed! The compiler verifies all sealed subtypes are covered.
        // If you add a new OrderState, this switch will fail to compile until you handle it.
    }

    private Money calculateTotal(List<OrderItem> items) {
        return items.stream()
            .map(item -> item.price().multiply(item.quantity()))
            .reduce(new Money(0, "USD"), Money::add);
    }
}

// Events are also sealed — defines the complete set of possible events
sealed interface OrderEvent {
    record Submit() implements OrderEvent {}
    record Confirm(String orderId) implements OrderEvent {}
    record Ship(String trackingNumber) implements OrderEvent {}
    record Deliver() implements OrderEvent {}
    record Cancel(String reason) implements OrderEvent {}
}

class InvalidTransition extends RuntimeException {
    InvalidTransition(OrderState state, OrderEvent event) {
        super("Cannot apply " + event.getClass().getSimpleName() +
              " to " + state.getClass().getSimpleName());
    }
}
```

## Pattern Matching in Practice

```java
/**
 * Pattern matching with guards, named patterns, and destructuring.
 */
class OrderRenderer {

    // Exhaustive switch with pattern matching and guards
    String renderStatus(OrderState state) {
        return switch (state) {
            case OrderState.Draft(var items) when items.isEmpty() ->
                "Empty draft";
            case OrderState.Draft(var items) ->
                "Draft with " + items.size() + " items";
            case OrderState.Pending(_, var total, var at) ->
                "Pending: " + total.amount() + " " + total.currency() + " (submitted " + at + ")";
            case OrderState.Confirmed(var id, _, _) ->
                "Confirmed: " + id;
            case OrderState.Shipped(_, var tracking, _) ->
                "Shipped: tracking " + tracking;
            case OrderState.Delivered(var id, var at) ->
                "Delivered: " + id + " at " + at;
            case OrderState.Cancelled(_, var reason, _) ->
                "Cancelled: " + reason;
        };
    }

    // Using instanceof pattern matching for JSON-like parsing
    static Object parseJsonValue(String json) {
        json = json.strip();
        if (json.startsWith("\"") && json.endsWith("\""))
            return json.substring(1, json.length() - 1);
        if (json.equals("true")) return true;
        if (json.equals("false")) return false;
        if (json.equals("null")) return null;
        try { return Integer.parseInt(json); } catch (NumberFormatException e) {}
        try { return Double.parseDouble(json); } catch (NumberFormatException e) {}
        return json;
    }

    static String describe(Object value) {
        return switch (value) {
            case null -> "null value";
            case Integer i when i < 0 -> "negative integer: " + i;
            case Integer i -> "positive integer: " + i;
            case Double d -> "decimal: " + d;
            case String s when s.length() > 100 -> "long string (" + s.length() + " chars)";
            case String s -> "string: '" + s + "'";
            case Boolean b -> "boolean: " + b;
            default -> "unknown type: " + value.getClass().getSimpleName();
        };
    }
}
```

## Testing Algebraic Types

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import static org.junit.jupiter.api.Assertions.*;

class OrderProcessorTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void happyPath_draftToDelivered() {
        var items = List.of(new OrderItem("prod1", 2, new Money(10.0, "USD")));
        OrderState state = new OrderState.Draft(items);

        state = processor.transition(state, new OrderEvent.Submit());
        assertInstanceOf(OrderState.Pending.class, state);

        state = processor.transition(state, new OrderEvent.Confirm("ORD-001"));
        assertInstanceOf(OrderState.Confirmed.class, state);

        state = processor.transition(state, new OrderEvent.Ship("TRACK-123"));
        assertInstanceOf(OrderState.Shipped.class, state);

        state = processor.transition(state, new OrderEvent.Deliver());
        assertInstanceOf(OrderState.Delivered.class, state);

        // Verify delivered carries the order ID through the chain
        if (state instanceof OrderState.Delivered(var orderId, _)) {
            assertEquals("ORD-001", orderId);
        }
    }

    @Test
    void cannotShipDraftOrder() {
        var state = new OrderState.Draft(List.of());
        assertThrows(InvalidTransition.class, () ->
            processor.transition(state, new OrderEvent.Ship("TRACK-000"))
        );
    }

    @Test
    void cancelledOrderIsTerminal() {
        var state = new OrderState.Cancelled("ORD-001", "customer request", Instant.now());
        assertThrows(InvalidTransition.class, () ->
            processor.transition(state, new OrderEvent.Submit())
        );
    }

    @Test
    void moneyValidation() {
        assertThrows(IllegalArgumentException.class, () -> new Money(-5, "USD"));
        assertThrows(IllegalArgumentException.class, () -> new Money(10, "INVALID"));
        assertEquals(new Money(10, "usd"), new Money(10, "USD")); // Normalized
    }
}
```

## Key Takeaways

Modern Java (21+) with records, sealed classes, and pattern matching provides compile-time
safety that was previously only available in Rust, Kotlin, or Scala. The trade-off is that
this approach requires more upfront type design — you must model your domain states explicitly
instead of using mutable objects with nullable fields. However, the benefit is enormous:
the compiler catches missing state transitions, impossible state combinations, and unhandled
cases. This eliminates entire categories of runtime bugs, which is exactly what makes these
features production-essential rather than just syntactic sugar.

The best practice is to use sealed interfaces for domain state machines, records for value
objects and DTOs, and exhaustive pattern matching for state transitions and rendering. Avoid
the common mistake of mixing mutable state with records — records are value types, not entities.
"""
    ),
]
