"""Spring Boot 3 patterns — WebFlux, Security 6, Data JPA, observability, testing."""

PAIRS = [
    (
        "java/spring-webflux-reactive",
        "Show Spring Boot reactive patterns with WebFlux and R2DBC including reactive endpoints, error handling, and streaming.",
        '''Spring Boot reactive patterns with WebFlux and R2DBC:

```java
// --- Reactive REST controller ---

import org.springframework.web.bind.annotation.*;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import java.time.Duration;
import java.util.Map;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    // Reactive GET — returns Flux (stream of items)
    @GetMapping
    public Flux<ProductDTO> listProducts(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return productService.findAll(page, size)
            .map(ProductDTO::from);
    }

    // Reactive GET by ID — returns Mono (single item)
    @GetMapping("/{id}")
    public Mono<ResponseEntity<ProductDTO>> getProduct(@PathVariable Long id) {
        return productService.findById(id)
            .map(ProductDTO::from)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    // Reactive POST with validation
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<ProductDTO> createProduct(@Valid @RequestBody Mono<CreateProductRequest> request) {
        return request
            .flatMap(productService::create)
            .map(ProductDTO::from);
    }

    // Server-Sent Events — streaming response
    @GetMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ProductDTO> streamProducts() {
        return productService.streamUpdates()
            .map(ProductDTO::from);
    }

    // Reactive error handling
    @ExceptionHandler(ProductNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public Mono<Map<String, String>> handleNotFound(ProductNotFoundException ex) {
        return Mono.just(Map.of(
            "error", "Product not found",
            "message", ex.getMessage()
        ));
    }
}

record CreateProductRequest(
    @NotBlank String name,
    @NotBlank String category,
    @Positive double price,
    @Min(0) int stockCount
) {}

record ProductDTO(Long id, String name, String category, double price, int stockCount) {
    static ProductDTO from(Product product) {
        return new ProductDTO(
            product.getId(), product.getName(),
            product.getCategory(), product.getPrice(),
            product.getStockCount()
        );
    }
}
```

```java
// --- R2DBC reactive repository and service ---

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import io.r2dbc.spi.R2dbcDataIntegrityViolationException;
import java.time.Duration;

@Table("products")
public class Product {
    @Id private Long id;
    private String name;
    private String category;
    private double price;
    private int stockCount;

    // Getters, setters...
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }
    public double getPrice() { return price; }
    public void setPrice(double price) { this.price = price; }
    public int getStockCount() { return stockCount; }
    public void setStockCount(int stockCount) { this.stockCount = stockCount; }
}

public interface ProductRepository extends ReactiveCrudRepository<Product, Long> {
    Flux<Product> findByCategory(String category);
    Flux<Product> findByPriceBetween(double min, double max);
    Mono<Long> countByCategory(String category);
}

@Service
public class ProductService {

    private final ProductRepository repository;
    private final ProductEventPublisher eventPublisher;

    public ProductService(ProductRepository repository, ProductEventPublisher eventPublisher) {
        this.repository = repository;
        this.eventPublisher = eventPublisher;
    }

    public Flux<Product> findAll(int page, int size) {
        return repository.findAll()
            .skip((long) page * size)
            .take(size);
    }

    public Mono<Product> findById(Long id) {
        return repository.findById(id)
            .switchIfEmpty(Mono.error(new ProductNotFoundException(id)));
    }

    @Transactional
    public Mono<Product> create(CreateProductRequest request) {
        Product product = new Product();
        product.setName(request.name());
        product.setCategory(request.category());
        product.setPrice(request.price());
        product.setStockCount(request.stockCount());

        return repository.save(product)
            .doOnSuccess(p -> eventPublisher.publish(new ProductCreatedEvent(p)))
            .onErrorMap(
                R2dbcDataIntegrityViolationException.class,
                ex -> new DuplicateProductException(request.name())
            );
    }

    @Transactional
    public Mono<Product> updateStock(Long id, int delta) {
        return repository.findById(id)
            .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
            .flatMap(product -> {
                int newStock = product.getStockCount() + delta;
                if (newStock < 0) {
                    return Mono.error(new InsufficientStockException(id, product.getStockCount(), -delta));
                }
                product.setStockCount(newStock);
                return repository.save(product);
            })
            .retryWhen(reactor.util.retry.Retry.backoff(3, Duration.ofMillis(100))
                .filter(ex -> ex instanceof org.springframework.dao.OptimisticLockingFailureException));
    }

    // SSE stream of product updates
    public Flux<Product> streamUpdates() {
        return eventPublisher.getEventFlux()
            .flatMap(event -> repository.findById(event.productId()));
    }
}

class ProductNotFoundException extends RuntimeException {
    ProductNotFoundException(Long id) { super("Product not found: " + id); }
}
class DuplicateProductException extends RuntimeException {
    DuplicateProductException(String name) { super("Product already exists: " + name); }
}
class InsufficientStockException extends RuntimeException {
    InsufficientStockException(Long id, int current, int requested) {
        super("Insufficient stock for product " + id + ": have " + current + ", need " + requested);
    }
}
```

```java
// --- WebClient for reactive HTTP calls ---

import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.util.retry.Retry;
import java.time.Duration;

@Service
public class ExternalApiClient {

    private final WebClient webClient;

    public ExternalApiClient(WebClient.Builder builder) {
        this.webClient = builder
            .baseUrl("https://api.external-service.com")
            .defaultHeader("Accept", "application/json")
            .filter((request, next) -> {
                long start = System.nanoTime();
                return next.exchange(request)
                    .doOnSuccess(response -> {
                        long duration = (System.nanoTime() - start) / 1_000_000;
                        // Log request timing
                    });
            })
            .build();
    }

    public Mono<ExternalProduct> fetchProduct(String externalId) {
        return webClient.get()
            .uri("/products/{id}", externalId)
            .retrieve()
            .bodyToMono(ExternalProduct.class)
            .timeout(Duration.ofSeconds(5))
            .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
                .filter(this::isRetryable)
                .maxBackoff(Duration.ofSeconds(2)))
            .onErrorResume(WebClientResponseException.NotFound.class,
                ex -> Mono.empty())
            .onErrorMap(WebClientResponseException.class,
                ex -> new ExternalServiceException(ex.getStatusCode().value(), ex.getMessage()));
    }

    // Parallel calls with Mono.zip
    public Mono<EnrichedProduct> enrichProduct(Product product) {
        Mono<ExternalProduct> externalMono = fetchProduct(product.getName());
        Mono<PricingInfo> pricingMono = fetchPricing(product.getName());
        Mono<List<Review>> reviewsMono = fetchReviews(product.getName());

        return Mono.zip(externalMono, pricingMono, reviewsMono)
            .map(tuple -> new EnrichedProduct(
                product,
                tuple.getT1(),
                tuple.getT2(),
                tuple.getT3()
            ))
            .timeout(Duration.ofSeconds(10));
    }

    private boolean isRetryable(Throwable ex) {
        if (ex instanceof WebClientResponseException wcex) {
            return wcex.getStatusCode().is5xxServerError();
        }
        return ex instanceof java.net.ConnectException;
    }

    private Mono<PricingInfo> fetchPricing(String name) { return Mono.empty(); }
    private Mono<List<Review>> fetchReviews(String name) { return Mono.empty(); }

    record ExternalProduct(String id, String name, Map<String, Object> metadata) {}
    record PricingInfo(double price, String currency) {}
    record Review(String author, int rating, String text) {}
    record EnrichedProduct(Product product, ExternalProduct external, PricingInfo pricing, List<Review> reviews) {}
    record ExternalServiceException(int status, String message) extends RuntimeException {}
}
```

Reactive operator comparison:

| Operator | Mono/Flux | Purpose |
|----------|-----------|---------|
| `map` | Both | Transform element synchronously |
| `flatMap` | Both | Transform to another Mono/Flux (async) |
| `switchIfEmpty` | Both | Fallback if empty |
| `defaultIfEmpty` | Both | Default value if empty |
| `zip` | Both | Combine multiple publishers |
| `onErrorResume` | Both | Recover from errors |
| `onErrorMap` | Both | Transform error type |
| `retryWhen` | Both | Retry with backoff strategy |
| `timeout` | Both | Cancel if exceeds duration |
| `doOnSuccess` | Both | Side effect on success |
| `take(n)` | Flux | Limit to first N items |
| `buffer(n)` | Flux | Group into batches |

Key patterns:
1. Use `Mono` for single-value responses and `Flux` for collections or streams
2. Chain `switchIfEmpty(Mono.error(...))` to convert empty results to domain-specific errors
3. Use `Mono.zip()` to execute multiple independent reactive calls in parallel
4. Configure `retryWhen` with `Retry.backoff()` for resilient external service calls
5. R2DBC repositories follow the same pattern as JPA but return `Mono`/`Flux` instead of `Optional`/`List`
6. Never block in a reactive chain — use `flatMap` for async composition, not `block()`'''
    ),
    (
        "java/spring-security-6",
        "Show Spring Security 6 patterns including OAuth2 resource server, method security, and SecurityFilterChain configuration.",
        '''Spring Security 6 with OAuth2 resource server and method security:

```java
// --- SecurityFilterChain configuration ---

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import java.util.List;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity  // Enables @PreAuthorize, @PostAuthorize, @Secured
public class SecurityConfig {

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            // Disable CSRF for stateless API
            .csrf(csrf -> csrf.disable())
            // Stateless session (no cookies)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // CORS configuration
            .cors(cors -> cors.configurationSource(corsConfigurationSource()))
            // URL-based authorization
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health", "/actuator/info").permitAll()
                .requestMatchers("/api/auth/**").permitAll()
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/users/**").hasAnyRole("USER", "ADMIN")
                .anyRequest().authenticated()
            )
            // OAuth2 Resource Server with JWT
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(jwtAuthenticationConverter())
                )
            )
            // Custom exception handling
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, authException) -> {
                    response.setContentType("application/json");
                    response.setStatus(401);
                    response.getWriter().write(
                        "{\"error\":\"Unauthorized\",\"message\":\"" +
                        authException.getMessage() + "\"}"
                    );
                })
                .accessDeniedHandler((request, response, accessDeniedException) -> {
                    response.setContentType("application/json");
                    response.setStatus(403);
                    response.getWriter().write(
                        "{\"error\":\"Forbidden\",\"message\":\"Insufficient privileges\"}"
                    );
                })
            );

        return http.build();
    }

    @Bean
    public JwtAuthenticationConverter jwtAuthenticationConverter() {
        var converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            // Extract roles from JWT claims
            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles == null) return List.of();

            return roles.stream()
                .map(role -> new org.springframework.security.core.authority
                    .SimpleGrantedAuthority("ROLE_" + role.toUpperCase()))
                .collect(java.util.stream.Collectors.toList());
        });
        return converter;
    }

    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        config.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        config.setAllowCredentials(true);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12);
    }
}
```

```java
// --- Method security and custom authorization ---

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/users")
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    // Inject authenticated user from JWT
    @GetMapping("/me")
    public UserDTO getCurrentUser(@AuthenticationPrincipal Jwt jwt) {
        String userId = jwt.getSubject();
        String email = jwt.getClaimAsString("email");
        List<String> roles = jwt.getClaimAsStringList("roles");
        return userService.getProfile(userId);
    }

    // Admin-only endpoint
    @GetMapping
    @PreAuthorize("hasRole('ADMIN')")
    public List<UserDTO> listUsers(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return userService.listUsers(page, size);
    }

    // Owner or admin can access
    @GetMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN') or #id == authentication.name")
    public UserDTO getUser(@PathVariable String id) {
        return userService.getProfile(id);
    }

    // Only owner can update their profile
    @PutMapping("/{id}")
    @PreAuthorize("#id == authentication.name")
    public UserDTO updateUser(
            @PathVariable String id,
            @RequestBody UpdateUserRequest request) {
        return userService.updateProfile(id, request);
    }

    // Post-authorize: check result after method execution
    @GetMapping("/{id}/sensitive-data")
    @PostAuthorize("returnObject.ownerId == authentication.name or hasRole('ADMIN')")
    public SensitiveData getSensitiveData(@PathVariable String id) {
        return userService.getSensitiveData(id);
    }
}

@Service
public class UserService {

    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    // Service-level authorization
    @PreAuthorize("hasAnyRole('USER', 'ADMIN')")
    public UserDTO getProfile(String userId) {
        return userRepository.findById(userId)
            .map(UserDTO::from)
            .orElseThrow(() -> new UserNotFoundException(userId));
    }

    // Custom permission evaluator
    @PreAuthorize("@permissionService.canModifyUser(authentication, #userId)")
    public UserDTO updateProfile(String userId, UpdateUserRequest request) {
        // Update logic
        return getProfile(userId);
    }

    public List<UserDTO> listUsers(int page, int size) {
        return userRepository.findAll(
            org.springframework.data.domain.PageRequest.of(page, size)
        ).map(UserDTO::from).getContent();
    }

    public SensitiveData getSensitiveData(String id) {
        return new SensitiveData(id, "data");
    }
}

// Custom permission evaluator
@Service("permissionService")
public class PermissionService {
    public boolean canModifyUser(
            org.springframework.security.core.Authentication auth,
            String targetUserId) {
        // Check if user is admin or is the target user
        return auth.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_ADMIN"))
            || auth.getName().equals(targetUserId);
    }
}

record UserDTO(String id, String name, String email, String role) {
    static UserDTO from(Object user) { return new UserDTO("", "", "", ""); }
}
record UpdateUserRequest(String name, String email) {}
record SensitiveData(String ownerId, String data) {}
class UserNotFoundException extends RuntimeException {
    UserNotFoundException(String id) { super("User not found: " + id); }
}
```

```java
// --- JWT token generation and validation ---

import org.springframework.security.oauth2.jwt.*;
import org.springframework.beans.factory.annotation.Value;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.UUID;

@Service
public class TokenService {

    private final JwtEncoder jwtEncoder;

    @Value("${app.jwt.expiration-minutes:60}")
    private long expirationMinutes;

    public TokenService(JwtEncoder jwtEncoder) {
        this.jwtEncoder = jwtEncoder;
    }

    public String generateToken(String userId, String email, List<String> roles) {
        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
            .id(UUID.randomUUID().toString())
            .subject(userId)
            .issuer("myapp")
            .issuedAt(now)
            .expiresAt(now.plus(expirationMinutes, ChronoUnit.MINUTES))
            .claim("email", email)
            .claim("roles", roles)
            .build();

        JwsHeader header = JwsHeader.with(
            org.springframework.security.oauth2.jose.jws.MacAlgorithm.HS256
        ).build();

        return jwtEncoder.encode(JwtEncoderParameters.from(header, claims)).getTokenValue();
    }

    public record TokenResponse(String accessToken, String tokenType, long expiresIn) {
        public static TokenResponse of(String token, long expiresInSeconds) {
            return new TokenResponse(token, "Bearer", expiresInSeconds);
        }
    }
}

// application.yml:
// spring:
//   security:
//     oauth2:
//       resourceserver:
//         jwt:
//           issuer-uri: https://auth.example.com
//           # OR for symmetric key:
//           # secret-key: ${JWT_SECRET}
```

Spring Security annotation comparison:

| Annotation | Check Time | Use Case |
|-----------|-----------|----------|
| `@PreAuthorize("hasRole('X')")` | Before method | Role-based access |
| `@PreAuthorize("#id == auth.name")` | Before method | Owner-only access |
| `@PostAuthorize("returnObj.owner == auth.name")` | After method | Filter by result |
| `@Secured("ROLE_ADMIN")` | Before method | Simple role check |
| `@RolesAllowed("ADMIN")` | Before method | JSR-250 standard |
| `@PreAuthorize("@svc.check(auth)")` | Before method | Custom bean check |

Key patterns:
1. Use `SecurityFilterChain` bean (not extending `WebSecurityConfigurerAdapter` which is removed in Spring Security 6)
2. Set `SessionCreationPolicy.STATELESS` for JWT-based APIs — no server-side session
3. Extract roles from JWT claims with a custom `JwtAuthenticationConverter` — map to `ROLE_` prefixed authorities
4. Use `@PreAuthorize` with SpEL for fine-grained method-level authorization
5. Custom permission evaluators (`@svc.check(auth, #id)`) enable complex business rules in authorization
6. Always configure custom `authenticationEntryPoint` and `accessDeniedHandler` for JSON error responses'''
    ),
    (
        "java/spring-data-jpa-advanced",
        "Show Spring Data JPA advanced patterns including projections, specifications, auditing, and custom repository implementations.",
        '''Spring Data JPA advanced patterns with projections, specifications, and auditing:

```java
// --- Entity with auditing ---

import jakarta.persistence.*;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;
import java.time.Instant;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @CreatedDate
    @Column(updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    @Column(updatable = false)
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    @Version  // Optimistic locking
    private Long version;

    // Getters/setters omitted for brevity
    public Long getId() { return id; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public String getCreatedBy() { return createdBy; }
    public Long getVersion() { return version; }
}

@Entity
@Table(name = "orders", indexes = {
    @Index(name = "idx_orders_customer", columnList = "customer_id"),
    @Index(name = "idx_orders_status", columnList = "status"),
})
public class Order extends BaseEntity {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status = OrderStatus.PENDING;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<OrderLine> lines = new ArrayList<>();

    @Column(nullable = false)
    private long totalCents;

    @Column
    private String notes;

    // Business methods
    public void addLine(Product product, int quantity) {
        OrderLine line = new OrderLine(this, product, quantity);
        lines.add(line);
        recalculateTotal();
    }

    private void recalculateTotal() {
        this.totalCents = lines.stream()
            .mapToLong(l -> l.getPriceCents() * l.getQuantity())
            .sum();
    }

    // Getters/setters...
    public Customer getCustomer() { return customer; }
    public OrderStatus getStatus() { return status; }
    public void setStatus(OrderStatus status) { this.status = status; }
    public List<OrderLine> getLines() { return lines; }
    public long getTotalCents() { return totalCents; }
}

public enum OrderStatus { PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED }

// Auditor provider (wires into @CreatedBy / @LastModifiedBy)
@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorProvider")
public class JpaConfig {
    @Bean
    public AuditorAware<String> auditorProvider() {
        return () -> Optional.ofNullable(
            SecurityContextHolder.getContext().getAuthentication()
        ).map(Authentication::getName);
    }
}
```

```java
// --- Projections and custom queries ---

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

// Interface-based projection (lightweight — only fetches listed columns)
public interface OrderSummary {
    Long getId();
    OrderStatus getStatus();
    long getTotalCents();
    Instant getCreatedAt();

    // Nested projection
    CustomerInfo getCustomer();

    interface CustomerInfo {
        String getName();
        String getEmail();
    }
}

// Class-based projection (DTO)
public record OrderReport(
    Long orderId,
    String customerName,
    long totalCents,
    long lineCount,
    Instant createdAt
) {}

// Repository with projections and specifications
public interface OrderRepository extends
        JpaRepository<Order, Long>,
        JpaSpecificationExecutor<Order> {

    // Interface projection
    Page<OrderSummary> findByStatus(OrderStatus status, Pageable pageable);

    // Class projection with JPQL
    @Query("""
        SELECT new com.example.OrderReport(
            o.id, c.name, o.totalCents, SIZE(o.lines), o.createdAt
        )
        FROM Order o JOIN o.customer c
        WHERE o.status = :status
        ORDER BY o.createdAt DESC
        """)
    List<OrderReport> findReportByStatus(@Param("status") OrderStatus status);

    // Dynamic projection — caller chooses the projection type
    <T> List<T> findByCustomerId(Long customerId, Class<T> projectionType);

    // Bulk update with @Modifying
    @Modifying
    @Query("UPDATE Order o SET o.status = :status WHERE o.id IN :ids")
    int bulkUpdateStatus(@Param("ids") List<Long> ids, @Param("status") OrderStatus status);

    // Native query for complex SQL
    @Query(value = """
        SELECT o.status, COUNT(*) as count, SUM(o.total_cents) as revenue
        FROM orders o
        WHERE o.created_at >= :since
        GROUP BY o.status
        """, nativeQuery = true)
    List<Object[]> getStatusAggregation(@Param("since") Instant since);

    // EntityGraph to control eager/lazy loading
    @EntityGraph(attributePaths = {"customer", "lines", "lines.product"})
    Optional<Order> findWithDetailsById(Long id);
}
```

```java
// --- Specifications for dynamic queries ---

import org.springframework.data.jpa.domain.Specification;
import jakarta.persistence.criteria.*;
import java.time.Instant;
import java.util.List;

public class OrderSpecifications {

    public static Specification<Order> hasStatus(OrderStatus status) {
        return (root, query, cb) -> cb.equal(root.get("status"), status);
    }

    public static Specification<Order> totalGreaterThan(long minCents) {
        return (root, query, cb) -> cb.greaterThan(root.get("totalCents"), minCents);
    }

    public static Specification<Order> createdBetween(Instant start, Instant end) {
        return (root, query, cb) -> cb.between(root.get("createdAt"), start, end);
    }

    public static Specification<Order> customerNameContains(String name) {
        return (root, query, cb) -> {
            Join<Order, Customer> customer = root.join("customer");
            return cb.like(cb.lower(customer.get("name")),
                "%" + name.toLowerCase() + "%");
        };
    }

    public static Specification<Order> hasAnyStatus(List<OrderStatus> statuses) {
        return (root, query, cb) -> root.get("status").in(statuses);
    }
}

// Service composing specifications dynamically
@Service
public class OrderQueryService {

    private final OrderRepository orderRepository;

    public OrderQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public Page<OrderSummary> searchOrders(OrderSearchRequest request, Pageable pageable) {
        Specification<Order> spec = Specification.where(null);

        if (request.status() != null) {
            spec = spec.and(OrderSpecifications.hasStatus(request.status()));
        }
        if (request.minTotal() != null) {
            spec = spec.and(OrderSpecifications.totalGreaterThan(request.minTotal()));
        }
        if (request.startDate() != null && request.endDate() != null) {
            spec = spec.and(OrderSpecifications.createdBetween(
                request.startDate(), request.endDate()));
        }
        if (request.customerName() != null) {
            spec = spec.and(OrderSpecifications.customerNameContains(request.customerName()));
        }

        return orderRepository.findAll(spec, pageable)
            .map(order -> /* convert to OrderSummary */ null);
    }

    record OrderSearchRequest(
        OrderStatus status,
        Long minTotal,
        Instant startDate,
        Instant endDate,
        String customerName
    ) {}
}
```

JPA query approach comparison:

| Approach | Dynamic? | Type-Safe? | Performance | Best For |
|----------|----------|-----------|-------------|----------|
| Derived query methods | No | Yes | Optimal (generated SQL) | Simple filters |
| `@Query` JPQL | No | Partial | Good | Complex joins, aggregations |
| `@Query` native SQL | No | No | Best (raw SQL) | DB-specific features |
| Specifications | Yes | Yes | Good | Dynamic search/filter UIs |
| Interface projections | N/A | Yes | Optimal (select subset) | Read-only views |
| Class projections (DTO) | N/A | Yes | Good | Aggregation results |
| `@EntityGraph` | N/A | Yes | Controls fetch strategy | Avoiding N+1 queries |

Key patterns:
1. Use `@MappedSuperclass` with `@EntityListeners(AuditingEntityListener.class)` for automatic audit fields
2. Interface projections fetch only declared columns — use them for list views to reduce data transfer
3. Specifications compose with `.and()` / `.or()` for dynamic query building from filter UIs
4. Use `@EntityGraph` to control eager loading and avoid N+1 query problems
5. `@Version` enables optimistic locking — JPA throws `OptimisticLockException` on concurrent updates
6. Dynamic projections (`<T> List<T> findBy(Class<T> type)`) let the caller choose the projection at runtime'''
    ),
    (
        "java/spring-boot-observability",
        "Show Spring Boot observability patterns with Micrometer metrics, distributed tracing, and health indicators.",
        '''Spring Boot observability with Micrometer, distributed tracing, and health checks:

```java
// --- Custom metrics with Micrometer ---

import io.micrometer.core.instrument.*;
import io.micrometer.core.instrument.binder.MeterBinder;
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

@Service
public class OrderService {

    private final Counter orderCreatedCounter;
    private final Counter orderFailedCounter;
    private final Timer orderProcessingTimer;
    private final DistributionSummary orderValueSummary;
    private final AtomicInteger activeOrdersGauge;

    public OrderService(MeterRegistry registry) {
        // Counter: monotonically increasing
        this.orderCreatedCounter = Counter.builder("orders.created")
            .description("Total orders created")
            .tag("service", "order-service")
            .register(registry);

        this.orderFailedCounter = Counter.builder("orders.failed")
            .description("Total failed order attempts")
            .register(registry);

        // Timer: measures duration + count + histogram
        this.orderProcessingTimer = Timer.builder("orders.processing.duration")
            .description("Order processing time")
            .publishPercentiles(0.5, 0.95, 0.99)  // p50, p95, p99
            .publishPercentileHistogram()
            .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(500),
                Duration.ofSeconds(1)
            )
            .register(registry);

        // Distribution summary: value distribution
        this.orderValueSummary = DistributionSummary.builder("orders.value")
            .description("Order value distribution in cents")
            .baseUnit("cents")
            .publishPercentiles(0.5, 0.95)
            .register(registry);

        // Gauge: current value (tracks active orders)
        this.activeOrdersGauge = new AtomicInteger(0);
        Gauge.builder("orders.active", activeOrdersGauge, AtomicInteger::get)
            .description("Currently active orders")
            .register(registry);
    }

    public Order createOrder(CreateOrderRequest request) {
        activeOrdersGauge.incrementAndGet();
        try {
            return orderProcessingTimer.record(() -> {
                Order order = processOrder(request);
                orderCreatedCounter.increment();
                orderValueSummary.record(order.getTotalCents());
                return order;
            });
        } catch (Exception e) {
            orderFailedCounter.increment();
            throw e;
        } finally {
            activeOrdersGauge.decrementAndGet();
        }
    }

    // @Observed annotation for automatic observation (metrics + tracing)
    @Observed(
        name = "order.lookup",
        contextualName = "finding-order",
        lowCardinalityKeyValues = {"service", "order-service"}
    )
    public Order findOrder(Long id) {
        return new Order(); // Lookup logic
    }

    private Order processOrder(CreateOrderRequest req) { return new Order(); }
    static class Order { long getTotalCents() { return 0; } }
    record CreateOrderRequest(String customerId) {}
}
```

```java
// --- Distributed tracing with Micrometer Observation ---

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.annotation.Observed;
import org.springframework.web.filter.ServerHttpObservationFilter;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationAutoConfiguration;

@Service
public class PaymentService {

    private final ObservationRegistry observationRegistry;
    private final PaymentGateway gateway;

    public PaymentService(ObservationRegistry observationRegistry, PaymentGateway gateway) {
        this.observationRegistry = observationRegistry;
        this.gateway = gateway;
    }

    // Manual observation for fine-grained control
    public PaymentResult processPayment(PaymentRequest request) {
        return Observation.createNotStarted("payment.process", observationRegistry)
            .lowCardinalityKeyValue("payment.method", request.method())
            .lowCardinalityKeyValue("currency", request.currency())
            .highCardinalityKeyValue("customer.id", request.customerId())
            .observe(() -> {
                // This block is automatically timed and traced
                PaymentResult result = gateway.charge(request);

                // Add result to observation context
                if (!result.success()) {
                    throw new PaymentFailedException(result.errorCode());
                }
                return result;
            });
    }

    // Scoped observation for multi-step processes
    public void processRefund(String orderId) {
        Observation observation = Observation.start("refund.process", observationRegistry);
        try (Observation.Scope scope = observation.openScope()) {
            // Step 1: Validate
            observation.event(Observation.Event.of("refund.validated"));
            validateRefund(orderId);

            // Step 2: Process
            observation.event(Observation.Event.of("refund.processed"));
            executeRefund(orderId);

            // Step 3: Notify
            observation.event(Observation.Event.of("refund.notified"));
            notifyCustomer(orderId);
        } catch (Exception e) {
            observation.error(e);
            throw e;
        } finally {
            observation.stop();
        }
    }

    record PaymentRequest(String customerId, long amountCents, String method, String currency) {}
    record PaymentResult(boolean success, String transactionId, String errorCode) {}
    interface PaymentGateway { PaymentResult charge(PaymentRequest req); }
    class PaymentFailedException extends RuntimeException {
        PaymentFailedException(String code) { super("Payment failed: " + code); }
    }
    void validateRefund(String id) {}
    void executeRefund(String id) {}
    void notifyCustomer(String id) {}
}

// application.yml for tracing:
// management:
//   tracing:
//     sampling:
//       probability: 1.0  # Sample 100% in dev, lower in prod
//   otlp:
//     tracing:
//       endpoint: http://localhost:4318/v1/traces
//   endpoints:
//     web:
//       exposure:
//         include: health,info,metrics,prometheus
```

```java
// --- Custom health indicators and info contributors ---

import org.springframework.boot.actuate.health.*;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.actuate.info.Info;
import org.springframework.stereotype.Component;
import java.sql.Connection;
import javax.sql.DataSource;
import java.util.Map;

// Custom health indicator
@Component
public class ExternalServiceHealthIndicator extends AbstractHealthIndicator {

    private final ExternalServiceClient client;

    public ExternalServiceHealthIndicator(ExternalServiceClient client) {
        super("External service health check failed");
        this.client = client;
    }

    @Override
    protected void doHealthCheck(Health.Builder builder) throws Exception {
        long start = System.currentTimeMillis();
        try {
            boolean reachable = client.ping();
            long latency = System.currentTimeMillis() - start;

            if (reachable) {
                builder.up()
                    .withDetail("latency_ms", latency)
                    .withDetail("endpoint", client.getEndpoint());
            } else {
                builder.down()
                    .withDetail("reason", "Service unreachable")
                    .withDetail("endpoint", client.getEndpoint());
            }
        } catch (Exception e) {
            builder.down(e);
        }
    }

    interface ExternalServiceClient {
        boolean ping();
        String getEndpoint();
    }
}

// Composite health for readiness vs liveness
// application.yml:
// management:
//   endpoint:
//     health:
//       group:
//         readiness:
//           include: db,redis,externalService
//         liveness:
//           include: ping
//       show-details: when_authorized

// Custom info contributor
@Component
public class AppInfoContributor implements InfoContributor {
    @Override
    public void contribute(Info.Builder builder) {
        builder.withDetail("app", Map.of(
            "name", "order-service",
            "version", "2.1.0",
            "environment", System.getenv().getOrDefault("APP_ENV", "development"),
            "features", Map.of(
                "newCheckout", true,
                "darkMode", false
            )
        ));
    }
}

// Custom MeterBinder for business metrics
@Component
public class BusinessMetrics implements MeterBinder {

    private final OrderRepository orderRepository;

    public BusinessMetrics(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        // Gauge that queries DB periodically
        Gauge.builder("business.orders.pending", orderRepository,
                repo -> repo.countByStatus(OrderStatus.PENDING))
            .description("Number of pending orders")
            .register(registry);

        Gauge.builder("business.orders.total_value", orderRepository,
                repo -> repo.sumTotalCentsByStatus(OrderStatus.CONFIRMED))
            .description("Total value of confirmed orders")
            .baseUnit("cents")
            .register(registry);
    }

    interface OrderRepository {
        long countByStatus(OrderStatus status);
        double sumTotalCentsByStatus(OrderStatus status);
    }
    enum OrderStatus { PENDING, CONFIRMED }
}
```

Observability component comparison:

| Component | Type | Purpose | Endpoint |
|-----------|------|---------|----------|
| Micrometer Counter | Metric | Monotonic count (events) | `/actuator/metrics/orders.created` |
| Micrometer Timer | Metric | Duration + count + histogram | `/actuator/metrics/orders.processing.duration` |
| Micrometer Gauge | Metric | Current value | `/actuator/metrics/orders.active` |
| Distribution Summary | Metric | Value distribution | `/actuator/metrics/orders.value` |
| `@Observed` | Observation | Auto metrics + trace spans | Metrics + traces |
| Health Indicator | Health | Component health check | `/actuator/health` |
| Health Groups | Health | Liveness/readiness probes | `/actuator/health/readiness` |
| Info Contributor | Info | App metadata | `/actuator/info` |

Key patterns:
1. Use `@Observed` annotation for automatic metrics + trace spans on service methods
2. Timer with `publishPercentiles` and `serviceLevelObjectives` enables SLO monitoring
3. Use low-cardinality tags for metric dimensions (e.g., status, method) — never use high-cardinality values as tags
4. Health groups separate liveness (is the process alive?) from readiness (can it accept traffic?)
5. `MeterBinder` registers gauges that query data sources — useful for business KPI dashboards
6. Micrometer Observation API unifies metrics and distributed tracing into a single instrumentation point'''
    ),
    (
        "java/spring-boot-testing",
        "Show Spring Boot testing patterns with WebMvcTest, DataJpaTest, Testcontainers, and MockMvc.",
        '''Spring Boot testing with slice tests, Testcontainers, and MockMvc:

```java
// --- @WebMvcTest for controller testing ---

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.DisplayName;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.hamcrest.Matchers.*;

@WebMvcTest(OrderController.class)  // Only loads web layer for this controller
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean  // Mock the service dependency
    private OrderService orderService;

    @Test
    @DisplayName("GET /api/orders/{id} returns order when found")
    @WithMockUser(roles = "USER")
    void getOrder_found() throws Exception {
        // Arrange
        OrderDTO order = new OrderDTO(1L, "ORD-001", "CONFIRMED", 5000L);
        when(orderService.findById(1L)).thenReturn(order);

        // Act & Assert
        mockMvc.perform(get("/api/orders/1")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentType(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.orderNumber").value("ORD-001"))
            .andExpect(jsonPath("$.status").value("CONFIRMED"))
            .andExpect(jsonPath("$.totalCents").value(5000));

        verify(orderService).findById(1L);
    }

    @Test
    @DisplayName("GET /api/orders/{id} returns 404 when not found")
    @WithMockUser(roles = "USER")
    void getOrder_notFound() throws Exception {
        when(orderService.findById(99L))
            .thenThrow(new OrderNotFoundException(99L));

        mockMvc.perform(get("/api/orders/99"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.error").value("Order not found: 99"));
    }

    @Test
    @DisplayName("POST /api/orders creates order with valid payload")
    @WithMockUser(roles = "USER")
    void createOrder_valid() throws Exception {
        OrderDTO created = new OrderDTO(1L, "ORD-002", "PENDING", 3000L);
        when(orderService.create(any())).thenReturn(created);

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                        "customerId": "cust-123",
                        "items": [
                            {"productId": "prod-1", "quantity": 2}
                        ]
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.orderNumber").value("ORD-002"));
    }

    @Test
    @DisplayName("POST /api/orders returns 400 for invalid payload")
    @WithMockUser(roles = "USER")
    void createOrder_invalid() throws Exception {
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))  // Missing required fields
            .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("GET /api/orders requires authentication")
    void getOrders_unauthenticated() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    record OrderDTO(Long id, String orderNumber, String status, Long totalCents) {}
    static class OrderNotFoundException extends RuntimeException {
        OrderNotFoundException(Long id) { super("Order not found: " + id); }
    }
}
```

```java
// --- @DataJpaTest for repository testing ---

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.ActiveProfiles;
import static org.assertj.core.api.Assertions.*;

@DataJpaTest  // Only loads JPA components (repo + entity manager)
@ActiveProfiles("test")
class OrderRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    @DisplayName("findByStatus returns matching orders with pagination")
    void findByStatus() {
        // Arrange: insert test data
        Customer customer = new Customer("Alice", "alice@example.com");
        entityManager.persist(customer);

        Order order1 = new Order(customer, OrderStatus.CONFIRMED, 5000);
        Order order2 = new Order(customer, OrderStatus.CONFIRMED, 3000);
        Order order3 = new Order(customer, OrderStatus.PENDING, 7000);
        entityManager.persist(order1);
        entityManager.persist(order2);
        entityManager.persist(order3);
        entityManager.flush();

        // Act
        var page = orderRepository.findByStatus(
            OrderStatus.CONFIRMED,
            org.springframework.data.domain.PageRequest.of(0, 10)
        );

        // Assert
        assertThat(page.getContent()).hasSize(2);
        assertThat(page.getTotalElements()).isEqualTo(2);
    }

    @Test
    @DisplayName("Specifications compose correctly for dynamic queries")
    void specificationComposition() {
        Customer customer = new Customer("Bob", "bob@example.com");
        entityManager.persist(customer);

        Order highValue = new Order(customer, OrderStatus.CONFIRMED, 50000);
        Order lowValue = new Order(customer, OrderStatus.CONFIRMED, 1000);
        entityManager.persist(highValue);
        entityManager.persist(lowValue);
        entityManager.flush();

        var spec = OrderSpecifications.hasStatus(OrderStatus.CONFIRMED)
            .and(OrderSpecifications.totalGreaterThan(10000));

        var results = orderRepository.findAll(spec);

        assertThat(results).hasSize(1);
        assertThat(results.get(0).getTotalCents()).isEqualTo(50000);
    }

    @Test
    @DisplayName("Optimistic locking prevents concurrent modification")
    void optimisticLocking() {
        Customer customer = new Customer("Carol", "carol@example.com");
        entityManager.persist(customer);

        Order order = new Order(customer, OrderStatus.PENDING, 5000);
        entityManager.persistAndFlush(order);

        // Simulate concurrent update
        Order copy1 = orderRepository.findById(order.getId()).orElseThrow();
        Order copy2 = orderRepository.findById(order.getId()).orElseThrow();

        copy1.setStatus(OrderStatus.CONFIRMED);
        orderRepository.saveAndFlush(copy1);

        copy2.setStatus(OrderStatus.CANCELLED);
        assertThatThrownBy(() -> orderRepository.saveAndFlush(copy2))
            .isInstanceOf(org.springframework.orm.ObjectOptimisticLockingFailureException.class);
    }
}
```

```java
// --- Integration tests with Testcontainers ---

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import static org.assertj.core.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Testcontainers
class OrderIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine")
        .withDatabaseName("testdb")
        .withUsername("test")
        .withPassword("test");

    @Container
    static GenericContainer<?> redis = new GenericContainer<>("redis:7-alpine")
        .withExposedPorts(6379);

    @DynamicPropertySource
    static void configureProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port", () -> redis.getMappedPort(6379));
    }

    @Autowired
    private TestRestTemplate restTemplate;

    @LocalServerPort
    private int port;

    @Test
    @DisplayName("Full order lifecycle: create -> confirm -> ship -> deliver")
    void orderLifecycle() {
        // Create order
        var createRequest = Map.of(
            "customerId", "cust-001",
            "items", List.of(
                Map.of("productId", "prod-1", "quantity", 2)
            )
        );

        var createResponse = restTemplate.postForEntity(
            "/api/orders", createRequest, Map.class);
        assertThat(createResponse.getStatusCode().value()).isEqualTo(201);

        Long orderId = ((Number) createResponse.getBody().get("id")).longValue();

        // Confirm order
        restTemplate.put("/api/orders/" + orderId + "/confirm", null);
        var confirmed = restTemplate.getForObject("/api/orders/" + orderId, Map.class);
        assertThat(confirmed.get("status")).isEqualTo("CONFIRMED");

        // Ship order
        restTemplate.put("/api/orders/" + orderId + "/ship", null);
        var shipped = restTemplate.getForObject("/api/orders/" + orderId, Map.class);
        assertThat(shipped.get("status")).isEqualTo("SHIPPED");
    }

    @Test
    @DisplayName("Concurrent stock updates maintain consistency")
    void concurrentStockUpdates() throws Exception {
        // This test uses a real Postgres instance for true concurrency testing
        var executor = java.util.concurrent.Executors.newFixedThreadPool(10);
        var futures = new java.util.ArrayList<java.util.concurrent.Future<?>>();

        for (int i = 0; i < 100; i++) {
            futures.add(executor.submit(() -> {
                restTemplate.put("/api/products/1/decrement-stock?amount=1", null);
            }));
        }

        for (var future : futures) {
            future.get(10, java.util.concurrent.TimeUnit.SECONDS);
        }
        executor.shutdown();

        // Verify final stock count is consistent
        var product = restTemplate.getForObject("/api/products/1", Map.class);
        assertThat(((Number) product.get("stockCount")).intValue()).isGreaterThanOrEqualTo(0);
    }
}
```

Spring Boot test annotation comparison:

| Annotation | Scope | Loads | Speed | Use Case |
|-----------|-------|-------|-------|----------|
| `@WebMvcTest` | Controller slice | Web layer only | Fast | REST endpoint testing |
| `@DataJpaTest` | Repository slice | JPA + H2/testcontainer | Fast | Query and entity testing |
| `@SpringBootTest` | Full context | Everything | Slow | Integration testing |
| `@WebFluxTest` | Reactive controller | WebFlux layer | Fast | Reactive endpoint testing |
| `@JsonTest` | Serialization | Jackson only | Very fast | JSON ser/de testing |
| `@MockBean` | N/A | Replaces bean with mock | N/A | Isolate dependencies |
| `@Testcontainers` | N/A | Docker containers | Medium | Real database testing |

Key patterns:
1. Use `@WebMvcTest` for controller-only tests — it loads only the web layer, mocking services with `@MockBean`
2. Use `@DataJpaTest` for repository tests — auto-configures an in-memory DB and TestEntityManager
3. Use Testcontainers with `@DynamicPropertySource` for integration tests against real databases
4. `@WithMockUser` injects a fake authenticated user for security-protected endpoint testing
5. AssertJ fluent assertions (`assertThat(...).hasSize(2)`) are more readable than JUnit assertions
6. Test slices (`@WebMvcTest`, `@DataJpaTest`) are much faster than `@SpringBootTest` — prefer them for unit tests'''
    ),
]
