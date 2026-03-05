"""Java — Spring Boot patterns, dependency injection, and JPA."""

PAIRS = [
    (
        "java/spring-boot-rest",
        "Show Spring Boot REST API patterns: controllers, services, DTOs, validation, and exception handling.",
        '''Spring Boot REST API patterns:

```java
// --- Controller layer ---

@RestController
@RequestMapping("/api/v1/users")
@RequiredArgsConstructor
@Validated
public class UserController {

    private final UserService userService;

    @GetMapping
    public ResponseEntity<Page<UserResponse>> listUsers(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String search) {
        Pageable pageable = PageRequest.of(page, size, Sort.by("createdAt").descending());
        Page<UserResponse> users = userService.findAll(search, pageable);
        return ResponseEntity.ok(users);
    }

    @GetMapping("/{id}")
    public ResponseEntity<UserResponse> getUser(@PathVariable UUID id) {
        return ResponseEntity.ok(userService.findById(id));
    }

    @PostMapping
    public ResponseEntity<UserResponse> createUser(
            @Valid @RequestBody UserCreateRequest request) {
        UserResponse created = userService.create(request);
        URI location = URI.create("/api/v1/users/" + created.id());
        return ResponseEntity.created(location).body(created);
    }

    @PutMapping("/{id}")
    public ResponseEntity<UserResponse> updateUser(
            @PathVariable UUID id,
            @Valid @RequestBody UserUpdateRequest request) {
        return ResponseEntity.ok(userService.update(id, request));
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteUser(@PathVariable UUID id) {
        userService.delete(id);
    }
}


// --- DTOs with validation ---

public record UserCreateRequest(
    @NotBlank @Size(min = 2, max = 100)
    String name,

    @NotBlank @Email
    String email,

    @NotNull @Min(13) @Max(150)
    Integer age,

    @Size(max = 500)
    String bio
) {}

public record UserUpdateRequest(
    @Size(min = 2, max = 100)
    String name,

    @Size(max = 500)
    String bio
) {}

public record UserResponse(
    UUID id,
    String name,
    String email,
    int age,
    String bio,
    LocalDateTime createdAt
) {
    public static UserResponse from(User user) {
        return new UserResponse(
            user.getId(), user.getName(), user.getEmail(),
            user.getAge(), user.getBio(), user.getCreatedAt()
        );
    }
}


// --- Service layer ---

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class UserService {

    private final UserRepository userRepository;
    private final ApplicationEventPublisher eventPublisher;

    public Page<UserResponse> findAll(String search, Pageable pageable) {
        Page<User> users = (search != null && !search.isBlank())
            ? userRepository.findByNameContainingIgnoreCase(search, pageable)
            : userRepository.findAll(pageable);
        return users.map(UserResponse::from);
    }

    public UserResponse findById(UUID id) {
        return userRepository.findById(id)
            .map(UserResponse::from)
            .orElseThrow(() -> new ResourceNotFoundException("User", id));
    }

    @Transactional
    public UserResponse create(UserCreateRequest request) {
        if (userRepository.existsByEmail(request.email())) {
            throw new ConflictException("Email already registered");
        }

        User user = User.builder()
            .name(request.name())
            .email(request.email().toLowerCase())
            .age(request.age())
            .bio(request.bio())
            .build();

        user = userRepository.save(user);
        eventPublisher.publishEvent(new UserCreatedEvent(user.getId()));
        return UserResponse.from(user);
    }

    @Transactional
    public UserResponse update(UUID id, UserUpdateRequest request) {
        User user = userRepository.findById(id)
            .orElseThrow(() -> new ResourceNotFoundException("User", id));

        if (request.name() != null) user.setName(request.name());
        if (request.bio() != null) user.setBio(request.bio());

        return UserResponse.from(userRepository.save(user));
    }

    @Transactional
    public void delete(UUID id) {
        if (!userRepository.existsById(id)) {
            throw new ResourceNotFoundException("User", id);
        }
        userRepository.deleteById(id);
    }
}


// --- Global exception handler ---

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ErrorResponse> handleNotFound(ResourceNotFoundException ex) {
        return ResponseEntity.status(404).body(
            new ErrorResponse("not_found", ex.getMessage())
        );
    }

    @ExceptionHandler(ConflictException.class)
    public ResponseEntity<ErrorResponse> handleConflict(ConflictException ex) {
        return ResponseEntity.status(409).body(
            new ErrorResponse("conflict", ex.getMessage())
        );
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(
            MethodArgumentNotValidException ex) {
        Map<String, String> errors = new HashMap<>();
        ex.getBindingResult().getFieldErrors().forEach(error ->
            errors.put(error.getField(), error.getDefaultMessage())
        );
        return ResponseEntity.badRequest().body(
            new ErrorResponse("validation_error", "Invalid input", errors)
        );
    }
}

public record ErrorResponse(
    String error,
    String message,
    Map<String, String> details
) {
    public ErrorResponse(String error, String message) {
        this(error, message, Map.of());
    }
}
```

Spring Boot REST patterns:
1. **Records for DTOs** — immutable, concise data carriers with validation
2. **`@Transactional(readOnly = true)`** — read-only default, override for writes
3. **`@RestControllerAdvice`** — centralized exception handling across controllers
4. **Event publishing** — decouple side effects from core logic
5. **`ResponseEntity.created()`** — proper 201 with Location header'''
    ),
    (
        "java/spring-data-jpa",
        "Show Spring Data JPA patterns: entities, repositories, query methods, specifications, and auditing.",
        '''Spring Data JPA patterns:

```java
// --- Entity with auditing ---

@Entity
@Table(name = "users",
    indexes = {
        @Index(name = "idx_user_email", columnList = "email", unique = true),
        @Index(name = "idx_user_created", columnList = "createdAt"),
    })
@EntityListeners(AuditingEntityListener.class)
@Getter @Setter
@Builder
@NoArgsConstructor @AllArgsConstructor
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(nullable = false)
    private int age;

    @Column(length = 500)
    private String bio;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    @Builder.Default
    private UserStatus status = UserStatus.ACTIVE;

    @OneToMany(mappedBy = "user", cascade = CascadeType.ALL, orphanRemoval = true)
    @Builder.Default
    private List<Order> orders = new ArrayList<>();

    @CreatedDate
    @Column(updatable = false)
    private LocalDateTime createdAt;

    @LastModifiedDate
    private LocalDateTime updatedAt;

    @Version  // Optimistic locking
    private Long version;

    // --- Helper methods for bidirectional relationship ---

    public void addOrder(Order order) {
        orders.add(order);
        order.setUser(this);
    }

    public void removeOrder(Order order) {
        orders.remove(order);
        order.setUser(null);
    }
}


// --- Repository with custom queries ---

public interface UserRepository extends JpaRepository<User, UUID>,
        JpaSpecificationExecutor<User> {

    // Derived query methods
    Optional<User> findByEmail(String email);
    boolean existsByEmail(String email);
    Page<User> findByNameContainingIgnoreCase(String name, Pageable pageable);
    List<User> findByStatusAndAgeBetween(UserStatus status, int minAge, int maxAge);

    // JPQL query
    @Query("SELECT u FROM User u WHERE u.status = :status " +
           "AND u.createdAt > :since ORDER BY u.createdAt DESC")
    List<User> findRecentByStatus(
        @Param("status") UserStatus status,
        @Param("since") LocalDateTime since
    );

    // Native query for complex operations
    @Query(value = """
        SELECT u.* FROM users u
        JOIN orders o ON u.id = o.user_id
        GROUP BY u.id
        HAVING SUM(o.total) > :minSpend
        ORDER BY SUM(o.total) DESC
        """, nativeQuery = true)
    List<User> findHighValueCustomers(@Param("minSpend") double minSpend);

    // Projection (return subset of fields)
    @Query("SELECT u.id as id, u.name as name, u.email as email FROM User u")
    List<UserSummary> findAllSummaries();

    // Modifying query
    @Modifying
    @Query("UPDATE User u SET u.status = :status WHERE u.id IN :ids")
    int updateStatusBatch(
        @Param("status") UserStatus status,
        @Param("ids") List<UUID> ids
    );
}

// Projection interface
public interface UserSummary {
    UUID getId();
    String getName();
    String getEmail();
}


// --- Specifications for dynamic queries ---

public class UserSpecifications {

    public static Specification<User> hasStatus(UserStatus status) {
        return (root, query, cb) -> cb.equal(root.get("status"), status);
    }

    public static Specification<User> nameContains(String name) {
        return (root, query, cb) ->
            cb.like(cb.lower(root.get("name")),
                    "%" + name.toLowerCase() + "%");
    }

    public static Specification<User> ageRange(Integer min, Integer max) {
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();
            if (min != null) predicates.add(cb.ge(root.get("age"), min));
            if (max != null) predicates.add(cb.le(root.get("age"), max));
            return cb.and(predicates.toArray(new Predicate[0]));
        };
    }

    public static Specification<User> createdAfter(LocalDateTime date) {
        return (root, query, cb) ->
            cb.greaterThan(root.get("createdAt"), date);
    }
}

// Usage in service:
// Specification<User> spec = Specification
//     .where(hasStatus(ACTIVE))
//     .and(nameContains("john"))
//     .and(ageRange(18, 65));
// Page<User> results = userRepository.findAll(spec, pageable);


// --- Auditing configuration ---

@Configuration
@EnableJpaAuditing
public class JpaConfig {
    @Bean
    public AuditorAware<String> auditorProvider() {
        return () -> Optional.ofNullable(
            SecurityContextHolder.getContext().getAuthentication()
        ).map(Authentication::getName);
    }
}
```

JPA patterns:
1. **`@Version`** — optimistic locking prevents concurrent update conflicts
2. **Specifications** — composable, reusable query predicates for dynamic filtering
3. **Projections** — fetch only needed columns with interface projections
4. **Auditing** — `@CreatedDate`/`@LastModifiedDate` auto-populated by Spring
5. **`orphanRemoval = true`** — auto-delete children removed from parent collection'''
    ),
    (
        "java/spring-security",
        "Show Spring Security patterns: JWT authentication, role-based access, method security, and OAuth2.",
        '''Spring Security with JWT patterns:

```java
// --- Security configuration ---

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
@RequiredArgsConstructor
public class SecurityConfig {

    private final JwtAuthFilter jwtAuthFilter;
    private final UserDetailsService userDetailsService;

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(sm ->
                sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/auth/**").permitAll()
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/products/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .addFilterBefore(jwtAuthFilter,
                UsernamePasswordAuthenticationFilter.class)
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((req, res, e) -> {
                    res.setStatus(401);
                    res.setContentType("application/json");
                    res.getWriter().write(
                        "{\"error\":\"unauthorized\",\"message\":\"" +
                        e.getMessage() + "\"}"
                    );
                })
            )
            .build();
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12);
    }

    @Bean
    public AuthenticationManager authenticationManager(
            AuthenticationConfiguration config) throws Exception {
        return config.getAuthenticationManager();
    }
}


// --- JWT filter ---

@Component
@RequiredArgsConstructor
public class JwtAuthFilter extends OncePerRequestFilter {

    private final JwtService jwtService;
    private final UserDetailsService userDetailsService;

    @Override
    protected void doFilterInternal(HttpServletRequest request,
            HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {

        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith("Bearer ")) {
            chain.doFilter(request, response);
            return;
        }

        String token = header.substring(7);
        String username = jwtService.extractUsername(token);

        if (username != null &&
                SecurityContextHolder.getContext().getAuthentication() == null) {
            UserDetails user = userDetailsService.loadUserByUsername(username);

            if (jwtService.isValid(token, user)) {
                var authToken = new UsernamePasswordAuthenticationToken(
                    user, null, user.getAuthorities()
                );
                authToken.setDetails(
                    new WebAuthenticationDetailsSource()
                        .buildDetails(request)
                );
                SecurityContextHolder.getContext()
                    .setAuthentication(authToken);
            }
        }

        chain.doFilter(request, response);
    }
}


// --- JWT service ---

@Service
public class JwtService {

    @Value("${jwt.secret}")
    private String secret;

    @Value("${jwt.expiration:86400000}")  // 24h default
    private long expiration;

    public String generateToken(UserDetails user) {
        return Jwts.builder()
            .subject(user.getUsername())
            .claim("roles", user.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList())
            .issuedAt(new Date())
            .expiration(new Date(System.currentTimeMillis() + expiration))
            .signWith(getSigningKey())
            .compact();
    }

    public String extractUsername(String token) {
        return extractClaim(token, Claims::getSubject);
    }

    public boolean isValid(String token, UserDetails user) {
        String username = extractUsername(token);
        return username.equals(user.getUsername()) && !isExpired(token);
    }

    private boolean isExpired(String token) {
        return extractClaim(token, Claims::getExpiration).before(new Date());
    }

    private <T> T extractClaim(String token, Function<Claims, T> resolver) {
        Claims claims = Jwts.parser()
            .verifyWith(getSigningKey())
            .build()
            .parseSignedClaims(token)
            .getPayload();
        return resolver.apply(claims);
    }

    private SecretKey getSigningKey() {
        return Keys.hmacShaKeyFor(
            Decoders.BASE64.decode(secret)
        );
    }
}


// --- Method-level security ---

@Service
public class OrderService {

    @PreAuthorize("hasRole('ADMIN') or #userId == authentication.principal.id")
    public List<Order> getUserOrders(UUID userId) {
        return orderRepository.findByUserId(userId);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void cancelOrder(UUID orderId) {
        // Only admins can cancel
    }

    @PostAuthorize("returnObject.userId == authentication.principal.id")
    public Order getOrder(UUID orderId) {
        // Checks access after retrieving the order
        return orderRepository.findById(orderId).orElseThrow();
    }
}
```

Spring Security patterns:
1. **Stateless JWT** — no server-side sessions, token carries claims
2. **`OncePerRequestFilter`** — extract and validate JWT on every request
3. **`@EnableMethodSecurity`** — `@PreAuthorize`/`@PostAuthorize` on service methods
4. **BCrypt(12)** — strong password hashing with appropriate work factor
5. **Role hierarchy** — `hasRole('ADMIN')` for coarse, `@PreAuthorize` SpEL for fine-grained'''
    ),
]
"""
