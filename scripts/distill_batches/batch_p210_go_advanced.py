"""Go advanced patterns — channels/select, context, generics, error handling, HTTP middleware."""

PAIRS = [
    (
        "go/channels-select-patterns",
        "Explain Go channels and select patterns with practical examples including buffered channels, directional channels, and multiplexing.",
        '''Go channels and select patterns for concurrent communication:

```go
// --- Channel fundamentals ---

package main

import (
    "context"
    "fmt"
    "math/rand"
    "sync"
    "time"
)

// Directional channel types enforce compile-time safety
func producer(out chan<- int, id int) {
    for i := 0; i < 5; i++ {
        val := id*100 + i
        out <- val
        time.Sleep(time.Duration(rand.Intn(100)) * time.Millisecond)
    }
}

func consumer(in <-chan int, done chan<- struct{}) {
    for val := range in {
        fmt.Printf("Received: %d\\n", val)
    }
    done <- struct{}{}
}

func main() {
    ch := make(chan int, 10) // Buffered channel — non-blocking up to 10
    done := make(chan struct{})

    go producer(ch, 1)
    go producer(ch, 2)
    go consumer(ch, done)

    // Wait then close
    time.Sleep(1 * time.Second)
    close(ch)
    <-done
}
```

```go
// --- Select for multiplexing ---

package main

import (
    "context"
    "fmt"
    "time"
)

// Merge combines multiple channels into one (fan-in)
func Merge[T any](channels ...<-chan T) <-chan T {
    out := make(chan T)
    var wg sync.WaitGroup
    wg.Add(len(channels))

    for _, ch := range channels {
        go func(c <-chan T) {
            defer wg.Done()
            for val := range c {
                out <- val
            }
        }(ch)
    }

    go func() {
        wg.Wait()
        close(out)
    }()
    return out
}

// Timeout pattern with select
func fetchWithTimeout(ctx context.Context, url string) (string, error) {
    resultCh := make(chan string, 1)
    errCh := make(chan error, 1)

    go func() {
        // Simulate HTTP fetch
        time.Sleep(200 * time.Millisecond)
        resultCh <- fmt.Sprintf("data from %s", url)
    }()

    select {
    case result := <-resultCh:
        return result, nil
    case err := <-errCh:
        return "", err
    case <-ctx.Done():
        return "", ctx.Err()
    }
}

// Non-blocking send/receive
func trySend(ch chan<- int, val int) bool {
    select {
    case ch <- val:
        return true
    default:
        return false // Channel full, skip
    }
}

// Ticker + quit pattern
func poller(ctx context.Context, interval time.Duration) {
    ticker := time.NewTicker(interval)
    defer ticker.Stop()

    for {
        select {
        case t := <-ticker.C:
            fmt.Printf("Poll at %v\\n", t)
        case <-ctx.Done():
            fmt.Println("Poller stopped")
            return
        }
    }
}
```

```go
// --- Pipeline pattern with channels ---

package main

import "fmt"

// Stage 1: Generate values
func generate(nums ...int) <-chan int {
    out := make(chan int)
    go func() {
        defer close(out)
        for _, n := range nums {
            out <- n
        }
    }()
    return out
}

// Stage 2: Square each value
func square(in <-chan int) <-chan int {
    out := make(chan int)
    go func() {
        defer close(out)
        for n := range in {
            out <- n * n
        }
    }()
    return out
}

// Stage 3: Filter values above threshold
func filter(in <-chan int, threshold int) <-chan int {
    out := make(chan int)
    go func() {
        defer close(out)
        for n := range in {
            if n > threshold {
                out <- n
            }
        }
    }()
    return out
}

func main() {
    // Pipeline: generate -> square -> filter
    pipeline := filter(square(generate(1, 2, 3, 4, 5, 6)), 10)

    for val := range pipeline {
        fmt.Println(val) // 16, 25, 36
    }
}
```

```go
// --- Or-done channel pattern ---

// OrDone wraps a channel read with context cancellation
func OrDone[T any](ctx context.Context, ch <-chan T) <-chan T {
    out := make(chan T)
    go func() {
        defer close(out)
        for {
            select {
            case <-ctx.Done():
                return
            case val, ok := <-ch:
                if !ok {
                    return
                }
                select {
                case out <- val:
                case <-ctx.Done():
                    return
                }
            }
        }
    }()
    return out
}

// Tee splits one channel into two
func Tee[T any](ctx context.Context, in <-chan T) (<-chan T, <-chan T) {
    out1, out2 := make(chan T), make(chan T)
    go func() {
        defer close(out1)
        defer close(out2)
        for val := range OrDone(ctx, in) {
            // Shadow to allow nil-ing after send
            ch1, ch2 := out1, out2
            for i := 0; i < 2; i++ {
                select {
                case ch1 <- val:
                    ch1 = nil
                case ch2 <- val:
                    ch2 = nil
                }
            }
        }
    }()
    return out1, out2
}
```

Channel and select pattern comparison:

| Pattern | Use Case | Blocking? | Channel Type |
|---------|----------|-----------|--------------|
| `ch <- v` | Send value | Yes (unbuffered/full) | `chan<- T` |
| `v := <-ch` | Receive value | Yes (empty) | `<-chan T` |
| `select` + `default` | Non-blocking try | No | Any |
| `select` + `ctx.Done()` | Cancellable wait | Conditional | Any |
| `for v := range ch` | Drain until close | Yes per item | `<-chan T` |
| Buffered `make(chan T, n)` | Decouple speed | No (until full) | `chan T` |
| `close(ch)` | Signal completion | N/A | `chan<- T` |

Key patterns:
1. Always use directional channel types (`chan<-` / `<-chan`) in function signatures for compile-time safety
2. Use buffered channels to decouple producer/consumer speeds and prevent goroutine leaks
3. Use `select` with `context.Done()` for cancellable operations — never use bare channel reads in production
4. Close channels from the sender side only; receivers should use `range` or comma-ok idiom
5. The pipeline pattern composes stages via channels — each stage is a goroutine reading from input and writing to output
6. The `OrDone` wrapper prevents goroutine leaks when context cancels during channel operations'''
    ),
    (
        "go/context-cancellation",
        "Show Go context and cancellation patterns including context propagation, timeouts, values, and graceful shutdown with context.",
        '''Go context and cancellation for managing goroutine lifecycles:

```go
// --- Context fundamentals ---

package main

import (
    "context"
    "errors"
    "fmt"
    "log"
    "net/http"
    "time"
)

// Service demonstrates context propagation through layers
type UserService struct {
    repo UserRepository
    cache CacheClient
}

type User struct {
    ID    int
    Name  string
    Email string
}

type UserRepository interface {
    FindByID(ctx context.Context, id int) (*User, error)
}

type CacheClient interface {
    Get(ctx context.Context, key string) ([]byte, error)
    Set(ctx context.Context, key string, val []byte, ttl time.Duration) error
}

// GetUser propagates context through cache -> repo layers
func (s *UserService) GetUser(ctx context.Context, id int) (*User, error) {
    // Check context before starting work
    if err := ctx.Err(); err != nil {
        return nil, fmt.Errorf("context already done: %w", err)
    }

    // Try cache first with a shorter timeout
    cacheCtx, cancel := context.WithTimeout(ctx, 100*time.Millisecond)
    defer cancel()

    key := fmt.Sprintf("user:%d", id)
    if data, err := s.cache.Get(cacheCtx, key); err == nil {
        return deserializeUser(data), nil
    }

    // Fall back to DB — uses parent context timeout
    user, err := s.repo.FindByID(ctx, id)
    if err != nil {
        return nil, fmt.Errorf("repo.FindByID(%d): %w", id, err)
    }

    // Cache in background (detached context — don't let parent cancel this)
    go func() {
        bgCtx, bgCancel := context.WithTimeout(context.Background(), 2*time.Second)
        defer bgCancel()
        _ = s.cache.Set(bgCtx, key, serializeUser(user), 5*time.Minute)
    }()

    return user, nil
}

func deserializeUser(data []byte) *User { return &User{} }
func serializeUser(u *User) []byte      { return nil }
```

```go
// --- Context with timeout, deadline, and cancel ---

package main

import (
    "context"
    "fmt"
    "time"
)

func main() {
    // 1. WithCancel — manual cancellation
    ctx, cancel := context.WithCancel(context.Background())
    go func() {
        time.Sleep(2 * time.Second)
        cancel() // Signal all goroutines to stop
    }()

    // 2. WithTimeout — auto-cancel after duration
    ctx2, cancel2 := context.WithTimeout(ctx, 5*time.Second)
    defer cancel2() // Always defer cancel to free resources

    // 3. WithDeadline — cancel at specific time
    deadline := time.Now().Add(10 * time.Second)
    ctx3, cancel3 := context.WithDeadline(ctx, deadline)
    defer cancel3()

    // 4. WithValue — attach request-scoped metadata
    type contextKey string
    const requestIDKey contextKey = "request_id"
    ctx4 := context.WithValue(ctx2, requestIDKey, "req-abc-123")

    // Extract value downstream
    if reqID, ok := ctx4.Value(requestIDKey).(string); ok {
        fmt.Printf("Request ID: %s\\n", reqID)
    }

    // 5. WithCancelCause (Go 1.20+) — attach error reason
    ctx5, cancelCause := context.WithCancelCause(ctx)
    go func() {
        time.Sleep(1 * time.Second)
        cancelCause(fmt.Errorf("upstream service unavailable"))
    }()
    <-ctx5.Done()
    fmt.Println("Cause:", context.Cause(ctx5))

    _ = ctx3
}

// Middleware that injects request ID into context
func RequestIDMiddleware(next http.Handler) http.Handler {
    type contextKey string
    const requestIDKey contextKey = "request_id"

    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        reqID := r.Header.Get("X-Request-ID")
        if reqID == "" {
            reqID = generateUUID()
        }
        ctx := context.WithValue(r.Context(), requestIDKey, reqID)
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}

func generateUUID() string { return "uuid-placeholder" }
```

```go
// --- Graceful shutdown with context ---

package main

import (
    "context"
    "fmt"
    "log"
    "net/http"
    "os"
    "os/signal"
    "sync"
    "syscall"
    "time"
)

type App struct {
    server     *http.Server
    workers    sync.WaitGroup
    shutdownCh chan struct{}
}

func NewApp() *App {
    mux := http.NewServeMux()
    app := &App{
        server: &http.Server{
            Addr:         ":8080",
            Handler:      mux,
            ReadTimeout:  15 * time.Second,
            WriteTimeout: 15 * time.Second,
            IdleTimeout:  60 * time.Second,
        },
        shutdownCh: make(chan struct{}),
    }

    mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
        w.WriteHeader(http.StatusOK)
    })

    return app
}

func (a *App) StartWorker(ctx context.Context, name string) {
    a.workers.Add(1)
    go func() {
        defer a.workers.Done()
        log.Printf("Worker %s started\\n", name)
        ticker := time.NewTicker(1 * time.Second)
        defer ticker.Stop()

        for {
            select {
            case <-ctx.Done():
                log.Printf("Worker %s stopping: %v\\n", name, ctx.Err())
                return
            case <-ticker.C:
                log.Printf("Worker %s tick\\n", name)
            }
        }
    }()
}

func (a *App) Run() error {
    // Root context cancelled on OS signal
    ctx, stop := signal.NotifyContext(
        context.Background(),
        os.Interrupt,
        syscall.SIGTERM,
    )
    defer stop()

    // Start background workers
    a.StartWorker(ctx, "metrics-collector")
    a.StartWorker(ctx, "queue-processor")

    // Start HTTP server in goroutine
    serverErr := make(chan error, 1)
    go func() {
        log.Println("Server starting on :8080")
        if err := a.server.ListenAndServe(); err != http.ErrServerClosed {
            serverErr <- err
        }
        close(serverErr)
    }()

    // Wait for signal or server error
    select {
    case <-ctx.Done():
        log.Println("Shutdown signal received")
    case err := <-serverErr:
        return fmt.Errorf("server error: %w", err)
    }

    // Graceful shutdown: give 30s for in-flight requests
    shutdownCtx, shutdownCancel := context.WithTimeout(
        context.Background(), 30*time.Second,
    )
    defer shutdownCancel()

    if err := a.server.Shutdown(shutdownCtx); err != nil {
        return fmt.Errorf("server shutdown: %w", err)
    }

    // Wait for workers to finish
    workerDone := make(chan struct{})
    go func() {
        a.workers.Wait()
        close(workerDone)
    }()

    select {
    case <-workerDone:
        log.Println("All workers stopped cleanly")
    case <-shutdownCtx.Done():
        log.Println("Shutdown timed out, forcing exit")
    }

    return nil
}
```

Context function comparison:

| Function | Cancellation | Use Case |
|----------|-------------|----------|
| `context.Background()` | Never | Root context for main/init |
| `context.TODO()` | Never | Placeholder during refactoring |
| `WithCancel(parent)` | Manual `cancel()` | Long-running goroutines |
| `WithTimeout(parent, d)` | After duration | HTTP/RPC calls with SLA |
| `WithDeadline(parent, t)` | At specific time | Batch job deadlines |
| `WithValue(parent, k, v)` | Inherits parent | Request-scoped metadata |
| `WithCancelCause(parent)` | Manual with error | Debugging cancellation reasons |
| `signal.NotifyContext(parent)` | On OS signal | Graceful server shutdown |

Key patterns:
1. Always call `defer cancel()` immediately after creating a cancellable context to prevent resource leaks
2. Check `ctx.Err()` before starting expensive work to fail fast
3. Use `context.Background()` for detached operations (like caching) that should survive parent cancellation
4. Propagate context through every function boundary — it is the first parameter by convention
5. Use typed keys (not bare strings) for `WithValue` to avoid collisions across packages
6. `signal.NotifyContext` replaces manual signal handling for clean server shutdown'''
    ),
    (
        "go/generics-type-constraints",
        "Show Go generics patterns including type constraints, generic data structures, and type inference with practical examples.",
        '''Go generics (Go 1.18+) with type constraints and generic data structures:

```go
// --- Type constraints and interfaces ---

package main

import (
    "cmp"
    "fmt"
    "slices"
    "strings"
)

// Built-in constraint: comparable (supports == and !=)
// Built-in constraint: any (alias for interface{})

// Custom constraint using type union
type Number interface {
    ~int | ~int8 | ~int16 | ~int32 | ~int64 |
    ~uint | ~uint8 | ~uint16 | ~uint32 | ~uint64 |
    ~float32 | ~float64
}

// Constraint with method requirement
type Stringer interface {
    String() string
}

// Combined constraint: type union + method
type FormattableNumber interface {
    Number
    fmt.Stringer
}

// Generic functions with constraints
func Min[T cmp.Ordered](a, b T) T {
    if a < b {
        return a
    }
    return b
}

func Sum[T Number](nums []T) T {
    var total T
    for _, n := range nums {
        total += n
    }
    return total
}

func Map[T any, U any](slice []T, fn func(T) U) []U {
    result := make([]U, len(slice))
    for i, v := range slice {
        result[i] = fn(v)
    }
    return result
}

func Filter[T any](slice []T, predicate func(T) bool) []T {
    var result []T
    for _, v := range slice {
        if predicate(v) {
            result = append(result, v)
        }
    }
    return result
}

func Reduce[T any, U any](slice []T, initial U, fn func(U, T) U) U {
    acc := initial
    for _, v := range slice {
        acc = fn(acc, v)
    }
    return acc
}

func Contains[T comparable](slice []T, target T) bool {
    for _, v := range slice {
        if v == target {
            return true
        }
    }
    return false
}

func main() {
    nums := []int{3, 1, 4, 1, 5, 9}
    fmt.Println(Sum(nums))                  // 23
    fmt.Println(Min(3, 7))                  // 3
    fmt.Println(Contains(nums, 5))          // true

    names := []string{"Alice", "Bob", "Charlie"}
    upper := Map(names, strings.ToUpper)    // [ALICE BOB CHARLIE]
    long := Filter(names, func(s string) bool { return len(s) > 3 })

    fmt.Println(upper, long)
}
```

```go
// --- Generic data structures ---

package collections

import (
    "fmt"
    "sync"
)

// Generic Set backed by map
type Set[T comparable] struct {
    items map[T]struct{}
}

func NewSet[T comparable](vals ...T) *Set[T] {
    s := &Set[T]{items: make(map[T]struct{}, len(vals))}
    for _, v := range vals {
        s.Add(v)
    }
    return s
}

func (s *Set[T]) Add(val T)           { s.items[val] = struct{}{} }
func (s *Set[T]) Remove(val T)        { delete(s.items, val) }
func (s *Set[T]) Contains(val T) bool { _, ok := s.items[val]; return ok }
func (s *Set[T]) Len() int            { return len(s.items) }

func (s *Set[T]) Union(other *Set[T]) *Set[T] {
    result := NewSet[T]()
    for k := range s.items {
        result.Add(k)
    }
    for k := range other.items {
        result.Add(k)
    }
    return result
}

func (s *Set[T]) Intersection(other *Set[T]) *Set[T] {
    result := NewSet[T]()
    for k := range s.items {
        if other.Contains(k) {
            result.Add(k)
        }
    }
    return result
}

// Generic thread-safe map
type SyncMap[K comparable, V any] struct {
    mu    sync.RWMutex
    items map[K]V
}

func NewSyncMap[K comparable, V any]() *SyncMap[K, V] {
    return &SyncMap[K, V]{items: make(map[K]V)}
}

func (m *SyncMap[K, V]) Get(key K) (V, bool) {
    m.mu.RLock()
    defer m.mu.RUnlock()
    val, ok := m.items[key]
    return val, ok
}

func (m *SyncMap[K, V]) Set(key K, val V) {
    m.mu.Lock()
    defer m.mu.Unlock()
    m.items[key] = val
}

func (m *SyncMap[K, V]) Delete(key K) {
    m.mu.Lock()
    defer m.mu.Unlock()
    delete(m.items, key)
}

func (m *SyncMap[K, V]) GetOrSet(key K, defaultFn func() V) V {
    m.mu.Lock()
    defer m.mu.Unlock()
    if val, ok := m.items[key]; ok {
        return val
    }
    val := defaultFn()
    m.items[key] = val
    return val
}

// Generic Result type (like Rust's Result)
type Result[T any] struct {
    value T
    err   error
}

func Ok[T any](val T) Result[T]     { return Result[T]{value: val} }
func Err[T any](err error) Result[T] { return Result[T]{err: err} }

func (r Result[T]) Unwrap() (T, error) { return r.value, r.err }
func (r Result[T]) IsOk() bool         { return r.err == nil }

func (r Result[T]) Map(fn func(T) T) Result[T] {
    if r.err != nil {
        return r
    }
    return Ok(fn(r.value))
}

func (r Result[T]) OrElse(defaultVal T) T {
    if r.err != nil {
        return defaultVal
    }
    return r.value
}
```

```go
// --- Generic repository pattern ---

package repo

import (
    "context"
    "database/sql"
    "fmt"
)

// Entity constraint — all DB entities must have an ID
type Entity interface {
    GetID() int64
    TableName() string
}

// Generic CRUD repository
type Repository[T Entity] struct {
    db *sql.DB
    scanner func(*sql.Row) (T, error)
}

func NewRepository[T Entity](db *sql.DB, scanner func(*sql.Row) (T, error)) *Repository[T] {
    return &Repository[T]{db: db, scanner: scanner}
}

func (r *Repository[T]) FindByID(ctx context.Context, id int64) (T, error) {
    var zero T
    query := fmt.Sprintf("SELECT * FROM %s WHERE id = $1", zero.TableName())

    row := r.db.QueryRowContext(ctx, query, id)
    entity, err := r.scanner(row)
    if err != nil {
        return zero, fmt.Errorf("FindByID(%d): %w", id, err)
    }
    return entity, nil
}

func (r *Repository[T]) FindAll(ctx context.Context, limit, offset int) ([]T, error) {
    var zero T
    query := fmt.Sprintf(
        "SELECT * FROM %s ORDER BY id LIMIT $1 OFFSET $2",
        zero.TableName(),
    )

    rows, err := r.db.QueryContext(ctx, query, limit, offset)
    if err != nil {
        return nil, fmt.Errorf("FindAll: %w", err)
    }
    defer rows.Close()

    var results []T
    for rows.Next() {
        entity, err := r.scanner(&sql.Row{})
        if err != nil {
            return nil, err
        }
        results = append(results, entity)
    }
    return results, rows.Err()
}

func (r *Repository[T]) Delete(ctx context.Context, id int64) error {
    var zero T
    query := fmt.Sprintf("DELETE FROM %s WHERE id = $1", zero.TableName())
    _, err := r.db.ExecContext(ctx, query, id)
    return err
}

// Usage:
// type User struct { ID int64; Name string; Email string }
// func (u User) GetID() int64      { return u.ID }
// func (u User) TableName() string { return "users" }
// userRepo := NewRepository[User](db, scanUser)
```

Generics constraint comparison:

| Constraint | What It Allows | Example |
|-----------|---------------|---------|
| `any` | All types | `func Print[T any](v T)` |
| `comparable` | `==`, `!=` operators | Map keys, set items |
| `cmp.Ordered` | `<`, `>`, `<=`, `>=` | Sorting, min/max |
| `~int \| ~float64` | Type union with approximation | Custom numeric types |
| `interface{ Method() }` | Method constraint | Types implementing interface |
| Combined | Union + methods | `Number + Stringer` |

Key patterns:
1. Use `~T` (tilde) in constraints to match underlying types — `~int` matches `type MyInt int`
2. Prefer `cmp.Ordered` over custom `Number` constraints when you need ordering
3. Generic data structures (Set, SyncMap, Result) eliminate runtime type assertions
4. The repository pattern with entity constraints provides type-safe CRUD without code generation
5. Type inference usually eliminates explicit type arguments at call sites — `Min(3, 7)` not `Min[int](3, 7)`
6. Use `comparable` constraint for map keys and equality checks'''
    ),
    (
        "go/error-handling-patterns",
        "Show Go error handling patterns including errors.Is, errors.As, sentinel errors, error wrapping, and custom error types.",
        '''Go error handling with wrapping, sentinel errors, and custom types:

```go
// --- Sentinel errors and custom error types ---

package apperr

import (
    "errors"
    "fmt"
    "net/http"
)

// Sentinel errors — package-level constants for known conditions
var (
    ErrNotFound      = errors.New("not found")
    ErrUnauthorized  = errors.New("unauthorized")
    ErrForbidden     = errors.New("forbidden")
    ErrConflict      = errors.New("conflict")
    ErrRateLimited   = errors.New("rate limited")
    ErrInternal      = errors.New("internal error")
)

// Custom error type with structured context
type ValidationError struct {
    Field   string
    Message string
    Value   any
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation failed on %s: %s (got %v)", e.Field, e.Message, e.Value)
}

// Multi-field validation error
type ValidationErrors struct {
    Errors []ValidationError
}

func (e *ValidationErrors) Error() string {
    return fmt.Sprintf("%d validation error(s)", len(e.Errors))
}

func (e *ValidationErrors) Add(field, message string, value any) {
    e.Errors = append(e.Errors, ValidationError{
        Field: field, Message: message, Value: value,
    })
}

func (e *ValidationErrors) HasErrors() bool {
    return len(e.Errors) > 0
}

// AppError wraps errors with HTTP status and operation context
type AppError struct {
    Op         string // Operation that failed (e.g., "UserService.Create")
    Kind       error  // Category (sentinel error)
    Err        error  // Underlying error
    StatusCode int
}

func (e *AppError) Error() string {
    if e.Err != nil {
        return fmt.Sprintf("%s: %v: %v", e.Op, e.Kind, e.Err)
    }
    return fmt.Sprintf("%s: %v", e.Op, e.Kind)
}

func (e *AppError) Unwrap() error {
    return e.Err
}

// E constructs an AppError
func E(op string, kind error, err error) *AppError {
    return &AppError{
        Op:         op,
        Kind:       kind,
        Err:        err,
        StatusCode: kindToStatus(kind),
    }
}

func kindToStatus(kind error) int {
    switch {
    case errors.Is(kind, ErrNotFound):
        return http.StatusNotFound
    case errors.Is(kind, ErrUnauthorized):
        return http.StatusUnauthorized
    case errors.Is(kind, ErrForbidden):
        return http.StatusForbidden
    case errors.Is(kind, ErrConflict):
        return http.StatusConflict
    case errors.Is(kind, ErrRateLimited):
        return http.StatusTooManyRequests
    default:
        return http.StatusInternalServerError
    }
}
```

```go
// --- Error wrapping and inspection ---

package main

import (
    "database/sql"
    "errors"
    "fmt"
    "log"

    "myapp/apperr"
)

// Repository layer wraps DB errors
func (r *UserRepo) FindByEmail(ctx context.Context, email string) (*User, error) {
    const op = "UserRepo.FindByEmail"

    var user User
    err := r.db.QueryRowContext(ctx,
        "SELECT id, name, email FROM users WHERE email = $1", email,
    ).Scan(&user.ID, &user.Name, &user.Email)

    if err != nil {
        if errors.Is(err, sql.ErrNoRows) {
            return nil, apperr.E(op, apperr.ErrNotFound, err)
        }
        return nil, apperr.E(op, apperr.ErrInternal, err)
    }
    return &user, nil
}

// Service layer adds business context via %w wrapping
func (s *UserService) GetUserByEmail(ctx context.Context, email string) (*User, error) {
    const op = "UserService.GetUserByEmail"

    if email == "" {
        return nil, &apperr.ValidationError{
            Field: "email", Message: "required", Value: email,
        }
    }

    user, err := s.repo.FindByEmail(ctx, email)
    if err != nil {
        return nil, fmt.Errorf("%s: %w", op, err) // Wrap preserves chain
    }
    return user, nil
}

// Handler inspects errors with errors.Is and errors.As
func (h *UserHandler) GetUser(w http.ResponseWriter, r *http.Request) {
    user, err := h.service.GetUserByEmail(r.Context(), r.URL.Query().Get("email"))
    if err != nil {
        // errors.Is checks the entire error chain for a match
        if errors.Is(err, apperr.ErrNotFound) {
            http.Error(w, "User not found", http.StatusNotFound)
            return
        }

        // errors.As extracts a specific error type from the chain
        var validErr *apperr.ValidationError
        if errors.As(err, &validErr) {
            http.Error(w,
                fmt.Sprintf("Invalid %s: %s", validErr.Field, validErr.Message),
                http.StatusBadRequest,
            )
            return
        }

        var appErr *apperr.AppError
        if errors.As(err, &appErr) {
            http.Error(w, appErr.Error(), appErr.StatusCode)
            return
        }

        // Unknown error — log and return 500
        log.Printf("ERROR: %+v\\n", err)
        http.Error(w, "Internal server error", http.StatusInternalServerError)
        return
    }

    // Success response...
    fmt.Fprintf(w, "User: %s", user.Name)
}
```

```go
// --- Error handling utilities ---

package errutil

import (
    "errors"
    "fmt"
    "runtime"
    "strings"
)

// WithStack captures a stack trace alongside an error
type StackError struct {
    Err   error
    Stack string
}

func (e *StackError) Error() string { return e.Err.Error() }
func (e *StackError) Unwrap() error { return e.Err }

func WithStack(err error) error {
    if err == nil {
        return nil
    }
    buf := make([]byte, 4096)
    n := runtime.Stack(buf, false)
    return &StackError{Err: err, Stack: string(buf[:n])}
}

// Must panics on error — only use in init() or tests
func Must[T any](val T, err error) T {
    if err != nil {
        panic(fmt.Sprintf("Must: %v", err))
    }
    return val
}

// IgnoreError discards error (use sparingly, document why)
func IgnoreError(err error) {
    if err != nil {
        // Optionally log
    }
}

// Retry with error classification
type RetryableError struct {
    Err     error
    Retries int
}

func (e *RetryableError) Error() string { return e.Err.Error() }
func (e *RetryableError) Unwrap() error { return e.Err }

func IsRetryable(err error) bool {
    var retryErr *RetryableError
    return errors.As(err, &retryErr)
}

// JoinErrors combines multiple errors (Go 1.20+)
func ValidateUser(u *User) error {
    var errs []error

    if u.Name == "" {
        errs = append(errs, &ValidationError{Field: "name", Message: "required"})
    }
    if len(u.Name) > 100 {
        errs = append(errs, &ValidationError{Field: "name", Message: "too long"})
    }
    if u.Email == "" {
        errs = append(errs, &ValidationError{Field: "email", Message: "required"})
    }

    return errors.Join(errs...) // Returns nil if no errors
}

type User struct {
    Name  string
    Email string
}

type ValidationError struct {
    Field   string
    Message string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("%s: %s", e.Field, e.Message)
}
```

Error handling function comparison:

| Function | Purpose | Example |
|----------|---------|---------|
| `fmt.Errorf("...%w", err)` | Wrap with context | Preserves error chain |
| `errors.Is(err, target)` | Check chain for sentinel | `errors.Is(err, sql.ErrNoRows)` |
| `errors.As(err, &target)` | Extract typed error | `errors.As(err, &validErr)` |
| `errors.Unwrap(err)` | Get wrapped error | One level only |
| `errors.Join(errs...)` | Combine multiple errors | Validation errors (Go 1.20+) |
| `errors.New("msg")` | Create sentinel error | Package-level `var` |

Key patterns:
1. Use `fmt.Errorf("op: %w", err)` to wrap errors with context while preserving the chain for `errors.Is`/`errors.As`
2. Define sentinel errors as package-level `var` with `errors.New` for known error conditions
3. Custom error types should implement `Error() string` and `Unwrap() error` for chain compatibility
4. Use `errors.Is` for sentinel checks and `errors.As` for type extraction — both traverse the full chain
5. The `AppError` pattern (Op + Kind + Err) provides structured error context from repo to handler
6. Use `errors.Join` (Go 1.20+) to combine multiple validation errors into a single error'''
    ),
    (
        "go/http-middleware-chains",
        "Show Go HTTP middleware chain patterns including logging, auth, recovery, CORS, and middleware composition.",
        '''Go HTTP middleware chains for production web servers:

```go
// --- Middleware type and chaining ---

package middleware

import (
    "context"
    "fmt"
    "log/slog"
    "net/http"
    "runtime/debug"
    "strings"
    "time"
)

// Middleware is a function that wraps an http.Handler
type Middleware func(http.Handler) http.Handler

// Chain composes middleware in order: first applied = outermost
func Chain(middlewares ...Middleware) Middleware {
    return func(final http.Handler) http.Handler {
        for i := len(middlewares) - 1; i >= 0; i-- {
            final = middlewares[i](final)
        }
        return final
    }
}

// --- Logging middleware ---

type responseWriter struct {
    http.ResponseWriter
    statusCode int
    size       int
}

func (rw *responseWriter) WriteHeader(code int) {
    rw.statusCode = code
    rw.ResponseWriter.WriteHeader(code)
}

func (rw *responseWriter) Write(b []byte) (int, error) {
    n, err := rw.ResponseWriter.Write(b)
    rw.size += n
    return n, err
}

func Logger(logger *slog.Logger) Middleware {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            start := time.Now()
            wrapped := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}

            next.ServeHTTP(wrapped, r)

            logger.Info("request",
                slog.String("method", r.Method),
                slog.String("path", r.URL.Path),
                slog.Int("status", wrapped.statusCode),
                slog.Int("size", wrapped.size),
                slog.Duration("duration", time.Since(start)),
                slog.String("remote", r.RemoteAddr),
            )
        })
    }
}

// --- Recovery middleware (panic handler) ---

func Recovery(logger *slog.Logger) Middleware {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            defer func() {
                if err := recover(); err != nil {
                    stack := debug.Stack()
                    logger.Error("panic recovered",
                        slog.Any("error", err),
                        slog.String("stack", string(stack)),
                        slog.String("path", r.URL.Path),
                    )
                    http.Error(w, "Internal Server Error", http.StatusInternalServerError)
                }
            }()
            next.ServeHTTP(wrapped, r)
        })
    }
}

// --- Request ID middleware ---

type contextKey string

const RequestIDKey contextKey = "request_id"

func RequestID(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        id := r.Header.Get("X-Request-ID")
        if id == "" {
            id = generateID()
        }
        ctx := context.WithValue(r.Context(), RequestIDKey, id)
        w.Header().Set("X-Request-ID", id)
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}

func generateID() string {
    return fmt.Sprintf("%d", time.Now().UnixNano())
}
```

```go
// --- Auth and CORS middleware ---

package middleware

import (
    "context"
    "net/http"
    "strings"
)

// CORS middleware
type CORSConfig struct {
    AllowOrigins     []string
    AllowMethods     []string
    AllowHeaders     []string
    ExposeHeaders    []string
    AllowCredentials bool
    MaxAge           int // Preflight cache seconds
}

func DefaultCORSConfig() CORSConfig {
    return CORSConfig{
        AllowOrigins: []string{"*"},
        AllowMethods: []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
        AllowHeaders: []string{"Content-Type", "Authorization"},
        MaxAge:       86400,
    }
}

func CORS(cfg CORSConfig) Middleware {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            origin := r.Header.Get("Origin")
            allowed := false
            for _, o := range cfg.AllowOrigins {
                if o == "*" || o == origin {
                    allowed = true
                    break
                }
            }

            if allowed {
                w.Header().Set("Access-Control-Allow-Origin", origin)
                w.Header().Set("Access-Control-Allow-Methods",
                    strings.Join(cfg.AllowMethods, ", "))
                w.Header().Set("Access-Control-Allow-Headers",
                    strings.Join(cfg.AllowHeaders, ", "))
                if cfg.AllowCredentials {
                    w.Header().Set("Access-Control-Allow-Credentials", "true")
                }
            }

            // Handle preflight
            if r.Method == http.MethodOptions {
                w.Header().Set("Access-Control-Max-Age",
                    fmt.Sprintf("%d", cfg.MaxAge))
                w.WriteHeader(http.StatusNoContent)
                return
            }

            next.ServeHTTP(w, r)
        })
    }
}

// JWT Auth middleware
type Claims struct {
    UserID string
    Role   string
}

const UserClaimsKey contextKey = "user_claims"

func Auth(validateToken func(string) (*Claims, error)) Middleware {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            authHeader := r.Header.Get("Authorization")
            if authHeader == "" {
                http.Error(w, "Missing authorization header", http.StatusUnauthorized)
                return
            }

            parts := strings.SplitN(authHeader, " ", 2)
            if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") {
                http.Error(w, "Invalid authorization format", http.StatusUnauthorized)
                return
            }

            claims, err := validateToken(parts[1])
            if err != nil {
                http.Error(w, "Invalid token", http.StatusUnauthorized)
                return
            }

            ctx := context.WithValue(r.Context(), UserClaimsKey, claims)
            next.ServeHTTP(w, r.WithContext(ctx))
        })
    }
}

// Role-based access control
func RequireRole(roles ...string) Middleware {
    roleSet := make(map[string]struct{}, len(roles))
    for _, r := range roles {
        roleSet[r] = struct{}{}
    }

    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            claims, ok := r.Context().Value(UserClaimsKey).(*Claims)
            if !ok {
                http.Error(w, "Unauthorized", http.StatusUnauthorized)
                return
            }
            if _, allowed := roleSet[claims.Role]; !allowed {
                http.Error(w, "Forbidden", http.StatusForbidden)
                return
            }
            next.ServeHTTP(w, r)
        })
    }
}
```

```go
// --- Rate limiting and composition ---

package main

import (
    "log/slog"
    "net/http"
    "sync"
    "time"

    "myapp/middleware"
)

// Simple in-memory rate limiter
type RateLimiter struct {
    mu       sync.Mutex
    visitors map[string]*visitor
    limit    int
    window   time.Duration
}

type visitor struct {
    count    int
    lastSeen time.Time
}

func NewRateLimiter(limit int, window time.Duration) *RateLimiter {
    rl := &RateLimiter{
        visitors: make(map[string]*visitor),
        limit:    limit,
        window:   window,
    }
    go rl.cleanup()
    return rl
}

func (rl *RateLimiter) cleanup() {
    ticker := time.NewTicker(1 * time.Minute)
    for range ticker.C {
        rl.mu.Lock()
        for ip, v := range rl.visitors {
            if time.Since(v.lastSeen) > rl.window {
                delete(rl.visitors, ip)
            }
        }
        rl.mu.Unlock()
    }
}

func (rl *RateLimiter) Allow(ip string) bool {
    rl.mu.Lock()
    defer rl.mu.Unlock()

    v, exists := rl.visitors[ip]
    if !exists || time.Since(v.lastSeen) > rl.window {
        rl.visitors[ip] = &visitor{count: 1, lastSeen: time.Now()}
        return true
    }

    v.count++
    v.lastSeen = time.Now()
    return v.count <= rl.limit
}

func RateLimit(limiter *RateLimiter) middleware.Middleware {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            if !limiter.Allow(r.RemoteAddr) {
                http.Error(w, "Rate limit exceeded", http.StatusTooManyRequests)
                return
            }
            next.ServeHTTP(w, r)
        })
    }
}

// --- Composing the full stack ---

func main() {
    logger := slog.Default()
    limiter := NewRateLimiter(100, 1*time.Minute)

    // Global middleware stack (applied to ALL routes)
    global := middleware.Chain(
        middleware.Recovery(logger),
        middleware.RequestID,
        middleware.Logger(logger),
        middleware.CORS(middleware.DefaultCORSConfig()),
        RateLimit(limiter),
    )

    // Auth-protected middleware stack
    protected := middleware.Chain(
        middleware.Auth(validateJWT),
    )

    // Admin-only middleware stack
    admin := middleware.Chain(
        middleware.Auth(validateJWT),
        middleware.RequireRole("admin"),
    )

    mux := http.NewServeMux()

    // Public routes
    mux.Handle("GET /health", http.HandlerFunc(healthHandler))
    mux.Handle("POST /login", http.HandlerFunc(loginHandler))

    // Protected routes
    mux.Handle("GET /api/profile", protected(http.HandlerFunc(profileHandler)))
    mux.Handle("GET /api/data", protected(http.HandlerFunc(dataHandler)))

    // Admin routes
    mux.Handle("GET /admin/users", admin(http.HandlerFunc(adminUsersHandler)))
    mux.Handle("DELETE /admin/users/{id}", admin(http.HandlerFunc(adminDeleteHandler)))

    // Wrap entire mux with global middleware
    server := &http.Server{
        Addr:    ":8080",
        Handler: global(mux),
    }

    logger.Info("Server starting", slog.String("addr", server.Addr))
    server.ListenAndServe()
}

func validateJWT(token string) (*middleware.Claims, error) { return nil, nil }
func healthHandler(w http.ResponseWriter, r *http.Request)      {}
func loginHandler(w http.ResponseWriter, r *http.Request)       {}
func profileHandler(w http.ResponseWriter, r *http.Request)     {}
func dataHandler(w http.ResponseWriter, r *http.Request)        {}
func adminUsersHandler(w http.ResponseWriter, r *http.Request)  {}
func adminDeleteHandler(w http.ResponseWriter, r *http.Request) {}
```

Middleware execution order:

| Layer | Middleware | Runs On | Purpose |
|-------|-----------|---------|---------|
| 1 (outermost) | Recovery | All requests | Catch panics |
| 2 | RequestID | All requests | Trace correlation |
| 3 | Logger | All requests | Access logs |
| 4 | CORS | All requests | Cross-origin headers |
| 5 | RateLimit | All requests | Abuse prevention |
| 6 | Auth | Protected routes | Token validation |
| 7 | RequireRole | Admin routes | Authorization |
| 8 (innermost) | Handler | Matched route | Business logic |

Key patterns:
1. Define `Middleware` as `func(http.Handler) http.Handler` for composable, framework-free middleware
2. Use `Chain()` to compose middleware in declared order — first listed = outermost wrapper
3. Wrap `http.ResponseWriter` to capture status codes and response sizes for logging
4. Recovery middleware must be outermost to catch panics from any inner handler
5. Use `context.WithValue` to pass request-scoped data (auth claims, request ID) — always use typed keys
6. Layer middleware: global (all routes) -> route-group (protected) -> per-route (admin)'''
    ),
]
