"""
Batch P3 — Go: Concurrency patterns, generics, production HTTP servers, testing.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Go Concurrency Patterns ---
    (
        "go_concurrency_patterns_production",
        "Explain Go's concurrency model in depth — goroutines, channels, select statements, "
        "and common patterns (fan-out/fan-in, pipeline, worker pool, rate limiter, circuit breaker). "
        "Show production-grade implementations with proper context cancellation, error propagation, "
        "graceful shutdown, and benchmarks. Include testing concurrent code with race detection.",
        """\
# Go Concurrency Patterns: From Goroutines to Production Systems

## Go's Concurrency Model

Go's concurrency is built on **CSP (Communicating Sequential Processes)**: goroutines
communicate through channels rather than sharing memory. This is fundamentally different
from thread-based concurrency in Java/C++ where shared state requires locks.

**Key insight**: Goroutines are not OS threads. They're **multiplexed** onto a small
number of OS threads by the Go runtime scheduler. A goroutine starts with ~2KB of stack
(vs ~1MB for OS threads), and Go can run millions of goroutines on a single machine.

```
Go runtime scheduler (M:N scheduling):
  G = Goroutine (user-space, ~2KB)
  M = OS Thread (machine thread, ~1MB)
  P = Processor (logical CPU, GOMAXPROCS)

  P0: G1, G2, G3  →  M0 (OS thread)
  P1: G4, G5      →  M1 (OS thread)
  P2: G6, G7, G8  →  M2 (OS thread)

  When G1 blocks (I/O, channel): runtime moves G2 onto M0, no context switch cost
  When G1 unblocks: runtime schedules it on any available P
```

## Pattern 1: Worker Pool with Graceful Shutdown

```go
package workerpool

import (
    "context"
    "fmt"
    "log/slog"
    "sync"
    "time"
)

// Job represents a unit of work with input and result types.
type Job[In, Out any] struct {
    ID    int
    Input In
}

// Result wraps a job result with error handling.
type Result[Out any] struct {
    JobID int
    Value Out
    Err   error
}

// WorkerPool processes jobs concurrently with bounded parallelism.
// The key design decision is using a buffered job channel as the work queue —
// this provides natural backpressure: if workers are busy, the sender blocks
// until a worker is free. No separate queue data structure needed.
type WorkerPool[In, Out any] struct {
    numWorkers int
    jobCh      chan Job[In, Out]
    resultCh   chan Result[Out]
    processor  func(context.Context, In) (Out, error)
    wg         sync.WaitGroup
    logger     *slog.Logger
}

// NewWorkerPool creates a pool with the specified number of workers.
func NewWorkerPool[In, Out any](
    numWorkers int,
    bufferSize int,
    processor func(context.Context, In) (Out, error),
    logger *slog.Logger,
) *WorkerPool[In, Out] {
    return &WorkerPool[In, Out]{
        numWorkers: numWorkers,
        jobCh:      make(chan Job[In, Out], bufferSize),
        resultCh:   make(chan Result[Out], bufferSize),
        processor:  processor,
        logger:     logger,
    }
}

// Start launches worker goroutines that process jobs until the context is cancelled.
func (p *WorkerPool[In, Out]) Start(ctx context.Context) {
    for i := 0; i < p.numWorkers; i++ {
        p.wg.Add(1)
        go p.worker(ctx, i)
    }

    // Close result channel when all workers are done
    go func() {
        p.wg.Wait()
        close(p.resultCh)
    }()
}

func (p *WorkerPool[In, Out]) worker(ctx context.Context, id int) {
    defer p.wg.Done()
    p.logger.Info("worker started", "worker_id", id)

    for {
        select {
        case <-ctx.Done():
            p.logger.Info("worker shutting down", "worker_id", id)
            return
        case job, ok := <-p.jobCh:
            if !ok {
                return // Channel closed, no more jobs
            }

            start := time.Now()
            value, err := p.processor(ctx, job.Input)
            duration := time.Since(start)

            if err != nil {
                p.logger.Error("job failed",
                    "worker_id", id, "job_id", job.ID,
                    "duration", duration, "error", err,
                )
            } else {
                p.logger.Debug("job completed",
                    "worker_id", id, "job_id", job.ID,
                    "duration", duration,
                )
            }

            select {
            case p.resultCh <- Result[Out]{JobID: job.ID, Value: value, Err: err}:
            case <-ctx.Done():
                return
            }
        }
    }
}

// Submit adds a job to the work queue. Blocks if the queue is full (backpressure).
func (p *WorkerPool[In, Out]) Submit(job Job[In, Out]) {
    p.jobCh <- job
}

// Results returns the channel for reading results.
func (p *WorkerPool[In, Out]) Results() <-chan Result[Out] {
    return p.resultCh
}

// Close signals no more jobs will be submitted and waits for completion.
func (p *WorkerPool[In, Out]) Close() {
    close(p.jobCh)
    p.wg.Wait()
}
```

## Pattern 2: Fan-Out/Fan-In Pipeline

```go
package pipeline

import (
    "context"
    "sync"
)

// Stage represents a pipeline processing stage.
// Each stage reads from input channel, processes, writes to output channel.
// This is the idiomatic Go pipeline pattern — each stage is a goroutine.
type Stage[In, Out any] func(ctx context.Context, in <-chan In) <-chan Out

// FanOut distributes work from one input to N workers, then merges results.
// This is the most common pattern for parallel processing in Go.
func FanOut[In, Out any](
    ctx context.Context,
    input <-chan In,
    numWorkers int,
    process func(context.Context, In) Out,
) <-chan Out {
    // Fan-out: distribute to workers
    workers := make([]<-chan Out, numWorkers)
    for i := 0; i < numWorkers; i++ {
        workers[i] = startWorker(ctx, input, process)
    }

    // Fan-in: merge all worker outputs into one channel
    return merge(ctx, workers...)
}

func startWorker[In, Out any](
    ctx context.Context,
    input <-chan In,
    process func(context.Context, In) Out,
) <-chan Out {
    out := make(chan Out)
    go func() {
        defer close(out)
        for item := range input {
            select {
            case <-ctx.Done():
                return
            case out <- process(ctx, item):
            }
        }
    }()
    return out
}

func merge[T any](ctx context.Context, channels ...<-chan T) <-chan T {
    out := make(chan T)
    var wg sync.WaitGroup

    for _, ch := range channels {
        wg.Add(1)
        go func(c <-chan T) {
            defer wg.Done()
            for val := range c {
                select {
                case <-ctx.Done():
                    return
                case out <- val:
                }
            }
        }(ch)
    }

    go func() {
        wg.Wait()
        close(out)
    }()

    return out
}
```

## Pattern 3: Rate Limiter and Circuit Breaker

```go
package resilience

import (
    "context"
    "errors"
    "fmt"
    "sync"
    "sync/atomic"
    "time"
)

// RateLimiter implements a token bucket algorithm.
// Why token bucket over fixed window? Token bucket allows bursts while
// maintaining an average rate. A fixed window counter resets at boundaries,
// allowing 2x the rate at window edges (the boundary problem).
type RateLimiter struct {
    tokens     chan struct{}
    refillRate time.Duration
    done       chan struct{}
}

func NewRateLimiter(maxPerSecond int) *RateLimiter {
    rl := &RateLimiter{
        tokens:     make(chan struct{}, maxPerSecond),
        refillRate: time.Second / time.Duration(maxPerSecond),
        done:       make(chan struct{}),
    }
    // Pre-fill tokens
    for i := 0; i < maxPerSecond; i++ {
        rl.tokens <- struct{}{}
    }
    // Refill goroutine
    go rl.refill()
    return rl
}

func (rl *RateLimiter) refill() {
    ticker := time.NewTicker(rl.refillRate)
    defer ticker.Stop()
    for {
        select {
        case <-rl.done:
            return
        case <-ticker.C:
            select {
            case rl.tokens <- struct{}{}:
            default: // Bucket full, discard
            }
        }
    }
}

// Wait blocks until a token is available or context is cancelled.
func (rl *RateLimiter) Wait(ctx context.Context) error {
    select {
    case <-ctx.Done():
        return ctx.Err()
    case <-rl.tokens:
        return nil
    }
}

func (rl *RateLimiter) Close() {
    close(rl.done)
}

// CircuitBreaker prevents cascading failures by stopping calls to failing services.
//
// States:
//   Closed → requests pass through, failures counted
//   Open → requests immediately rejected (fast fail)
//   HalfOpen → limited requests pass through to test recovery
//
// The circuit breaker is essential for production microservices because without it,
// a failing downstream service causes all callers to wait (and eventually timeout),
// consuming threads/goroutines and cascading the failure upward.
type CircuitBreaker struct {
    maxFailures int32
    failures    atomic.Int32
    state       atomic.Int32 // 0=closed, 1=open, 2=half-open
    lastFailure atomic.Int64 // Unix nano
    timeout     time.Duration
    mu          sync.Mutex
}

const (
    stateClosed   int32 = 0
    stateOpen     int32 = 1
    stateHalfOpen int32 = 2
)

var ErrCircuitOpen = errors.New("circuit breaker is open")

func NewCircuitBreaker(maxFailures int32, timeout time.Duration) *CircuitBreaker {
    return &CircuitBreaker{
        maxFailures: maxFailures,
        timeout:     timeout,
    }
}

// Execute runs the given function if the circuit allows it.
func (cb *CircuitBreaker) Execute(fn func() error) error {
    state := cb.state.Load()

    switch state {
    case stateOpen:
        // Check if timeout has elapsed → transition to half-open
        lastFail := time.Unix(0, cb.lastFailure.Load())
        if time.Since(lastFail) > cb.timeout {
            cb.state.CompareAndSwap(stateOpen, stateHalfOpen)
        } else {
            return ErrCircuitOpen
        }

    case stateHalfOpen:
        // Allow one request through to test recovery
        cb.mu.Lock()
        defer cb.mu.Unlock()

        err := fn()
        if err != nil {
            cb.state.Store(stateOpen)
            cb.lastFailure.Store(time.Now().UnixNano())
            return err
        }
        // Success — close the circuit
        cb.failures.Store(0)
        cb.state.Store(stateClosed)
        return nil
    }

    // Closed state — normal operation
    err := fn()
    if err != nil {
        newCount := cb.failures.Add(1)
        cb.lastFailure.Store(time.Now().UnixNano())
        if newCount >= cb.maxFailures {
            cb.state.Store(stateOpen)
        }
        return err
    }

    cb.failures.Store(0) // Reset on success
    return nil
}

func (cb *CircuitBreaker) State() string {
    switch cb.state.Load() {
    case stateClosed: return "closed"
    case stateOpen: return "open"
    case stateHalfOpen: return "half-open"
    default: return "unknown"
    }
}
```

## Testing Concurrent Code

```go
package workerpool_test

import (
    "context"
    "fmt"
    "log/slog"
    "sync/atomic"
    "testing"
    "time"
)

// Run with: go test -race -count=1 ./...
// The -race flag detects data races at runtime — essential for concurrent code

func TestWorkerPool_ProcessesAllJobs(t *testing.T) {
    var processed atomic.Int32

    pool := NewWorkerPool[int, int](
        4, 10,
        func(ctx context.Context, n int) (int, error) {
            processed.Add(1)
            return n * 2, nil
        },
        slog.Default(),
    )

    ctx := context.Background()
    pool.Start(ctx)

    // Submit 100 jobs
    go func() {
        for i := 0; i < 100; i++ {
            pool.Submit(Job[int, int]{ID: i, Input: i})
        }
        pool.Close()
    }()

    // Collect results
    results := make(map[int]int)
    for result := range pool.Results() {
        if result.Err != nil {
            t.Errorf("job %d failed: %v", result.JobID, result.Err)
        }
        results[result.JobID] = result.Value
    }

    if len(results) != 100 {
        t.Errorf("expected 100 results, got %d", len(results))
    }
    if processed.Load() != 100 {
        t.Errorf("expected 100 processed, got %d", processed.Load())
    }
}

func TestWorkerPool_ContextCancellation(t *testing.T) {
    pool := NewWorkerPool[int, int](
        4, 10,
        func(ctx context.Context, n int) (int, error) {
            // Simulate slow work
            select {
            case <-ctx.Done():
                return 0, ctx.Err()
            case <-time.After(time.Second):
                return n, nil
            }
        },
        slog.Default(),
    )

    ctx, cancel := context.WithCancel(context.Background())
    pool.Start(ctx)

    // Submit some jobs
    go func() {
        for i := 0; i < 10; i++ {
            pool.Submit(Job[int, int]{ID: i, Input: i})
        }
    }()

    // Cancel after 100ms — workers should stop
    time.Sleep(100 * time.Millisecond)
    cancel()

    // Should not hang — workers respect context cancellation
    done := make(chan struct{})
    go func() {
        for range pool.Results() {}
        close(done)
    }()

    select {
    case <-done:
        // Good — pool shut down
    case <-time.After(5 * time.Second):
        t.Fatal("pool did not shut down within 5 seconds")
    }
}

func TestCircuitBreaker_OpensAfterFailures(t *testing.T) {
    cb := NewCircuitBreaker(3, time.Second)

    // 3 failures should open the circuit
    for i := 0; i < 3; i++ {
        cb.Execute(func() error { return fmt.Errorf("fail") })
    }

    if cb.State() != "open" {
        t.Errorf("expected open, got %s", cb.State())
    }

    // Next call should be rejected immediately
    err := cb.Execute(func() error { return nil })
    if err != ErrCircuitOpen {
        t.Errorf("expected ErrCircuitOpen, got %v", err)
    }
}

// Benchmark shows goroutine creation overhead
func BenchmarkGoroutineCreation(b *testing.B) {
    for i := 0; i < b.N; i++ {
        done := make(chan struct{})
        go func() { close(done) }()
        <-done
    }
    // Typical: ~200ns per goroutine creation
    // Compare: ~1μs for OS thread creation (5x slower)
}
```

## Key Takeaways

Go's concurrency model is powerful because channels encode **both data transfer and
synchronization** in one primitive. The common mistake is over-using goroutines without
considering backpressure — spawning a goroutine per request without limiting concurrency
leads to resource exhaustion. The worker pool pattern provides bounded concurrency, and the
circuit breaker prevents cascading failures.

For production systems, always use `context.Context` for cancellation propagation, run
tests with `-race`, and prefer `select` with `ctx.Done()` in every goroutine to ensure
graceful shutdown. The trade-off between channels and mutexes: use channels for communication
between goroutines, use mutexes for protecting shared data structures. Don't use channels
as a mutex substitute — that's a common anti-pattern that's harder to reason about.
"""
    ),

    # --- 2. Go Generics and Type System ---
    (
        "go_generics_type_system_patterns",
        "Explain Go generics (type parameters) — constraints, type sets, comparable types, and "
        "practical patterns for generic data structures, functional utilities, and domain modeling. "
        "Show how generics interact with interfaces, when to use generics vs interfaces, and build "
        "a type-safe repository pattern with generics. Include testing and performance considerations.",
        """\
# Go Generics: Type-Safe Abstractions Without Reflection

## Why Generics Matter for Go

Before Go 1.18, writing reusable data structures required either:
1. **`interface{}`/`any`**: Loses type safety, requires runtime type assertions
2. **Code generation**: Tools like `go generate` produce type-specific code
3. **Copy-paste**: Duplicate code for each type

Generics solve this by allowing **type parameters** — you write the code once with a
placeholder type, and the compiler generates type-specific code at compile time.

```go
// Before generics: type assertions everywhere, runtime panics
func MaxBefore(a, b interface{}) interface{} {
    // Which comparison? int? float? string? Runtime panic if wrong type
    return a // Can't actually compare without type assertion
}

// With generics: type-safe, zero runtime overhead
func Max[T cmp.Ordered](a, b T) T {
    if a > b {
        return a
    }
    return b
}
// Usage: Max(3, 5) → 5, Max("a", "b") → "b"
// Compile error: Max(myStruct{}, myStruct{}) → myStruct doesn't satisfy Ordered
```

## Type Constraints

```go
package constraints

import "cmp"

// Basic constraint: any type that supports ordering
// cmp.Ordered includes all numeric types + string
func Min[T cmp.Ordered](a, b T) T {
    if a < b {
        return a
    }
    return b
}

// Custom constraint using type sets
// This is how you define which types are allowed
type Number interface {
    ~int | ~int8 | ~int16 | ~int32 | ~int64 |
    ~uint | ~uint8 | ~uint16 | ~uint32 | ~uint64 |
    ~float32 | ~float64
}

// The ~ prefix means "underlying type" — allows named types
// type UserID int → satisfies ~int
// type Amount float64 → satisfies ~float64

func Sum[T Number](values []T) T {
    var total T
    for _, v := range values {
        total += v
    }
    return total
}

// Constraint with methods — like an interface but for generics
type Stringer interface {
    String() string
}

type Validator interface {
    Validate() error
}

// Combined constraint: must satisfy both interfaces
type ValidStringer interface {
    Stringer
    Validator
}

func ProcessAndLog[T ValidStringer](items []T) error {
    for _, item := range items {
        if err := item.Validate(); err != nil {
            return fmt.Errorf("validation failed for %s: %w", item.String(), err)
        }
        slog.Info("processed", "item", item.String())
    }
    return nil
}
```

## Generic Data Structures

```go
package collections

import (
    "cmp"
    "sync"
)

// Set — generic hash set using Go's built-in map
type Set[T comparable] struct {
    items map[T]struct{}
}

func NewSet[T comparable](initial ...T) *Set[T] {
    s := &Set[T]{items: make(map[T]struct{}, len(initial))}
    for _, item := range initial {
        s.Add(item)
    }
    return s
}

func (s *Set[T]) Add(item T) { s.items[item] = struct{}{} }
func (s *Set[T]) Remove(item T) { delete(s.items, item) }
func (s *Set[T]) Contains(item T) bool { _, ok := s.items[item]; return ok }
func (s *Set[T]) Len() int { return len(s.items) }

func (s *Set[T]) Union(other *Set[T]) *Set[T] {
    result := NewSet[T]()
    for item := range s.items {
        result.Add(item)
    }
    for item := range other.items {
        result.Add(item)
    }
    return result
}

func (s *Set[T]) Intersection(other *Set[T]) *Set[T] {
    result := NewSet[T]()
    // Iterate over the smaller set for efficiency
    smaller, larger := s, other
    if s.Len() > other.Len() {
        smaller, larger = other, s
    }
    for item := range smaller.items {
        if larger.Contains(item) {
            result.Add(item)
        }
    }
    return result
}

// SyncMap — type-safe concurrent map (replaces sync.Map which uses any)
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

func (m *SyncMap[K, V]) Set(key K, value V) {
    m.mu.Lock()
    defer m.mu.Unlock()
    m.items[key] = value
}

func (m *SyncMap[K, V]) Delete(key K) {
    m.mu.Lock()
    defer m.mu.Unlock()
    delete(m.items, key)
}

// SortedSlice — maintains sorted order with binary search
type SortedSlice[T cmp.Ordered] struct {
    items []T
}

func (s *SortedSlice[T]) Insert(item T) {
    // Binary search for insertion point
    i, _ := slices.BinarySearch(s.items, item)
    s.items = slices.Insert(s.items, i, item)
}

func (s *SortedSlice[T]) Contains(item T) bool {
    _, found := slices.BinarySearch(s.items, item)
    return found
}
```

## Type-Safe Repository Pattern

```go
package repository

import (
    "context"
    "database/sql"
    "fmt"
    "strings"
)

// Entity constraint — all entities must have an ID
type Entity interface {
    GetID() int64
    TableName() string
}

// Repository provides type-safe CRUD operations for any entity type.
// This replaces the need for code generation (sqlc, entgo) for simple cases.
type Repository[T Entity] struct {
    db     *sql.DB
    scan   func(*sql.Row) (T, error)  // Type-specific scanner
    scanAll func(*sql.Rows) ([]T, error)
}

func NewRepository[T Entity](
    db *sql.DB,
    scan func(*sql.Row) (T, error),
    scanAll func(*sql.Rows) ([]T, error),
) *Repository[T] {
    return &Repository[T]{db: db, scan: scan, scanAll: scanAll}
}

func (r *Repository[T]) FindByID(ctx context.Context, id int64) (T, error) {
    var zero T
    tableName := zero.TableName()

    row := r.db.QueryRowContext(ctx,
        fmt.Sprintf("SELECT * FROM %s WHERE id = $1", tableName), id)
    return r.scan(row)
}

func (r *Repository[T]) FindAll(ctx context.Context, limit, offset int) ([]T, error) {
    var zero T
    tableName := zero.TableName()

    rows, err := r.db.QueryContext(ctx,
        fmt.Sprintf("SELECT * FROM %s ORDER BY id LIMIT $1 OFFSET $2", tableName),
        limit, offset)
    if err != nil {
        return nil, fmt.Errorf("querying %s: %w", tableName, err)
    }
    defer rows.Close()
    return r.scanAll(rows)
}

func (r *Repository[T]) Delete(ctx context.Context, id int64) error {
    var zero T
    tableName := zero.TableName()

    result, err := r.db.ExecContext(ctx,
        fmt.Sprintf("DELETE FROM %s WHERE id = $1", tableName), id)
    if err != nil {
        return fmt.Errorf("deleting from %s: %w", tableName, err)
    }
    rows, _ := result.RowsAffected()
    if rows == 0 {
        return fmt.Errorf("%s with id %d not found", tableName, id)
    }
    return nil
}

// --- Concrete entity example ---

type User struct {
    ID    int64
    Email string
    Name  string
}

func (u User) GetID() int64     { return u.ID }
func (u User) TableName() string { return "users" }

// Create a type-safe user repository
func NewUserRepo(db *sql.DB) *Repository[User] {
    return NewRepository[User](
        db,
        func(row *sql.Row) (User, error) {
            var u User
            err := row.Scan(&u.ID, &u.Email, &u.Name)
            return u, err
        },
        func(rows *sql.Rows) ([]User, error) {
            var users []User
            for rows.Next() {
                var u User
                if err := rows.Scan(&u.ID, &u.Email, &u.Name); err != nil {
                    return nil, err
                }
                users = append(users, u)
            }
            return users, rows.Err()
        },
    )
}
```

## Testing Generic Code

```go
func TestSet_Operations(t *testing.T) {
    s1 := NewSet(1, 2, 3, 4, 5)
    s2 := NewSet(3, 4, 5, 6, 7)

    // Union
    union := s1.Union(s2)
    if union.Len() != 7 {
        t.Errorf("union should have 7 elements, got %d", union.Len())
    }

    // Intersection
    inter := s1.Intersection(s2)
    if inter.Len() != 3 {
        t.Errorf("intersection should have 3 elements, got %d", inter.Len())
    }
    for _, v := range []int{3, 4, 5} {
        if !inter.Contains(v) {
            t.Errorf("intersection should contain %d", v)
        }
    }
}

// Generics work with any comparable type
func TestSet_StringType(t *testing.T) {
    s := NewSet("go", "rust", "python")
    if !s.Contains("go") {
        t.Error("should contain 'go'")
    }
    s.Remove("python")
    if s.Contains("python") {
        t.Error("should not contain 'python' after removal")
    }
}

func TestSyncMap_ConcurrentAccess(t *testing.T) {
    m := NewSyncMap[string, int]()
    var wg sync.WaitGroup

    // Concurrent writes
    for i := 0; i < 100; i++ {
        wg.Add(1)
        go func(n int) {
            defer wg.Done()
            m.Set(fmt.Sprintf("key-%d", n), n)
        }(i)
    }
    wg.Wait()

    // Verify all values present
    for i := 0; i < 100; i++ {
        val, ok := m.Get(fmt.Sprintf("key-%d", i))
        if !ok || val != i {
            t.Errorf("expected key-%d = %d, got %v (exists=%v)", i, i, val, ok)
        }
    }
}
```

## When to Use Generics vs Interfaces

```
Use GENERICS when:
  - You need type-safe collections (Set[T], SyncMap[K,V])
  - You want to avoid interface{}/any type assertions
  - The operation is the same regardless of type (Sort, Filter, Map)
  - Performance matters (generics avoid boxing/interface overhead)

Use INTERFACES when:
  - You need runtime polymorphism (different types at runtime)
  - The behavior differs between types (each type has its own method)
  - You're defining a contract for dependency injection
  - The type parameter would only appear in method signatures

Combine both:
  - Generic function with interface constraint
  - Repository[T Entity] — T is generic, Entity is an interface

Anti-pattern: Using generics where a simple interface would suffice
  Bad:  func Process[T Processor](p T) { p.Process() }
  Good: func Process(p Processor) { p.Process() }
  // If you're just calling methods, use an interface directly
```

## Key Takeaways

Go generics are deliberately simple compared to Rust or C++ templates — no specialization,
no variadic type parameters, no associated types. This is a design trade-off: less power
but much easier to understand and maintain. The best practice is to use generics for
data structures and utility functions where type safety matters, and interfaces for behavior
abstraction. The common mistake is overusing generics for everything — if a simple interface
works, prefer the interface. Generics shine when you need type-safe containers, avoid
`interface{}` type assertions, or eliminate code duplication across concrete types.
"""
    ),
]
