"""Go — generics, concurrency patterns, testing, and error handling."""

PAIRS = [
    (
        "go/generics",
        "Show Go generics patterns: type parameters, constraints, generic data structures, and utility functions.",
        '''Go generics (1.18+):

```go
package collections

import (
    "cmp"
    "slices"
    "sync"
)

// --- Type constraints ---

// Built-in: any, comparable, cmp.Ordered

// Custom constraint
type Number interface {
    ~int | ~int32 | ~int64 | ~float32 | ~float64
}

type Stringer interface {
    String() string
}

// Combined constraint
type OrderedStringer interface {
    cmp.Ordered
    Stringer
}


// --- Generic functions ---

func Map[T, U any](items []T, fn func(T) U) []U {
    result := make([]U, len(items))
    for i, item := range items {
        result[i] = fn(item)
    }
    return result
}

func Filter[T any](items []T, predicate func(T) bool) []T {
    var result []T
    for _, item := range items {
        if predicate(item) {
            result = append(result, item)
        }
    }
    return result
}

func Reduce[T, U any](items []T, initial U, fn func(U, T) U) U {
    acc := initial
    for _, item := range items {
        acc = fn(acc, item)
    }
    return acc
}

func GroupBy[T any, K comparable](items []T, keyFn func(T) K) map[K][]T {
    groups := make(map[K][]T)
    for _, item := range items {
        key := keyFn(item)
        groups[key] = append(groups[key], item)
    }
    return groups
}

// Usage:
// names := Map(users, func(u User) string { return u.Name })
// adults := Filter(users, func(u User) bool { return u.Age >= 18 })
// total := Reduce(prices, 0.0, func(sum, p float64) float64 { return sum + p })


// --- Generic data structures ---

// Thread-safe generic map
type SyncMap[K comparable, V any] struct {
    mu sync.RWMutex
    m  map[K]V
}

func NewSyncMap[K comparable, V any]() *SyncMap[K, V] {
    return &SyncMap[K, V]{m: make(map[K]V)}
}

func (sm *SyncMap[K, V]) Get(key K) (V, bool) {
    sm.mu.RLock()
    defer sm.mu.RUnlock()
    v, ok := sm.m[key]
    return v, ok
}

func (sm *SyncMap[K, V]) Set(key K, value V) {
    sm.mu.Lock()
    defer sm.mu.Unlock()
    sm.m[key] = value
}

func (sm *SyncMap[K, V]) Delete(key K) {
    sm.mu.Lock()
    defer sm.mu.Unlock()
    delete(sm.m, key)
}

func (sm *SyncMap[K, V]) Len() int {
    sm.mu.RLock()
    defer sm.mu.RUnlock()
    return len(sm.m)
}


// Generic Result type
type Result[T any] struct {
    Value T
    Err   error
}

func Ok[T any](value T) Result[T] {
    return Result[T]{Value: value}
}

func Err[T any](err error) Result[T] {
    return Result[T]{Err: err}
}

func (r Result[T]) Unwrap() (T, error) {
    return r.Value, r.Err
}


// Generic Set
type Set[T comparable] map[T]struct{}

func NewSet[T comparable](items ...T) Set[T] {
    s := make(Set[T], len(items))
    for _, item := range items {
        s[item] = struct{}{}
    }
    return s
}

func (s Set[T]) Add(item T)           { s[item] = struct{}{} }
func (s Set[T]) Has(item T) bool      { _, ok := s[item]; return ok }
func (s Set[T]) Remove(item T)        { delete(s, item) }

func (s Set[T]) Union(other Set[T]) Set[T] {
    result := NewSet[T]()
    for k := range s { result.Add(k) }
    for k := range other { result.Add(k) }
    return result
}

func (s Set[T]) Intersection(other Set[T]) Set[T] {
    result := NewSet[T]()
    for k := range s {
        if other.Has(k) {
            result.Add(k)
        }
    }
    return result
}
```

Go generics patterns:
1. **`~int` tilde** — constraint matches underlying types (type aliases)
2. **`Map`/`Filter`/`Reduce`** — functional helpers with type inference
3. **`SyncMap[K, V]`** — type-safe concurrent map (vs `sync.Map` which uses `any`)
4. **`Result[T]`** — generic result type for error-or-value returns
5. **`Set[T comparable]`** — zero-value set using `map[T]struct{}`'''
    ),
    (
        "go/concurrency-patterns",
        "Show Go concurrency patterns: goroutines, channels, select, worker pools, and context cancellation.",
        '''Go concurrency patterns:

```go
package main

import (
    "context"
    "errors"
    "fmt"
    "log"
    "sync"
    "time"
)


// --- Fan-out / Fan-in ---

func FanOut[T, R any](ctx context.Context, items []T, workers int,
    process func(context.Context, T) (R, error)) ([]R, error) {

    type result struct {
        index int
        value R
        err   error
    }

    input := make(chan struct{ index int; item T }, len(items))
    output := make(chan result, len(items))

    // Start workers
    var wg sync.WaitGroup
    for i := 0; i < workers; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for job := range input {
                val, err := process(ctx, job.item)
                output <- result{job.index, val, err}
            }
        }()
    }

    // Send work
    for i, item := range items {
        input <- struct{ index int; item T }{i, item}
    }
    close(input)

    // Close output when all workers done
    go func() {
        wg.Wait()
        close(output)
    }()

    // Collect results in order
    results := make([]R, len(items))
    var firstErr error
    for r := range output {
        if r.err != nil && firstErr == nil {
            firstErr = r.err
        }
        results[r.index] = r.value
    }

    return results, firstErr
}


// --- Pipeline pattern ---

func Pipeline(ctx context.Context, input <-chan int) <-chan string {
    // Stage 1: Double
    doubled := stage(ctx, input, func(n int) int { return n * 2 })

    // Stage 2: Convert to string
    return stage(ctx, doubled, func(n int) string {
        return fmt.Sprintf("result: %d", n)
    })
}

func stage[In, Out any](ctx context.Context, input <-chan In,
    transform func(In) Out) <-chan Out {

    output := make(chan Out)
    go func() {
        defer close(output)
        for {
            select {
            case <-ctx.Done():
                return
            case val, ok := <-input:
                if !ok {
                    return
                }
                select {
                case output <- transform(val):
                case <-ctx.Done():
                    return
                }
            }
        }
    }()
    return output
}


// --- Rate limiter with token bucket ---

type RateLimiter struct {
    tokens chan struct{}
    done   chan struct{}
}

func NewRateLimiter(rate int, interval time.Duration) *RateLimiter {
    rl := &RateLimiter{
        tokens: make(chan struct{}, rate),
        done:   make(chan struct{}),
    }

    // Fill initial tokens
    for i := 0; i < rate; i++ {
        rl.tokens <- struct{}{}
    }

    // Refill tokens at rate
    go func() {
        ticker := time.NewTicker(interval / time.Duration(rate))
        defer ticker.Stop()
        for {
            select {
            case <-rl.done:
                return
            case <-ticker.C:
                select {
                case rl.tokens <- struct{}{}:
                default: // Bucket full
                }
            }
        }
    }()

    return rl
}

func (rl *RateLimiter) Wait(ctx context.Context) error {
    select {
    case <-rl.tokens:
        return nil
    case <-ctx.Done():
        return ctx.Err()
    }
}

func (rl *RateLimiter) Stop() { close(rl.done) }


// --- errgroup pattern (structured concurrency) ---

import "golang.org/x/sync/errgroup"

func FetchAll(ctx context.Context, urls []string) ([]string, error) {
    g, ctx := errgroup.WithContext(ctx)
    results := make([]string, len(urls))

    for i, url := range urls {
        i, url := i, url // Capture for goroutine
        g.Go(func() error {
            body, err := fetchURL(ctx, url)
            if err != nil {
                return fmt.Errorf("fetch %s: %w", url, err)
            }
            results[i] = body
            return nil
        })
    }

    if err := g.Wait(); err != nil {
        return nil, err
    }
    return results, nil
}


// --- Graceful shutdown ---

func GracefulServer(ctx context.Context) error {
    ctx, cancel := context.WithCancel(ctx)
    defer cancel()

    // Start server
    server := startHTTPServer()

    // Wait for shutdown signal
    <-ctx.Done()
    log.Println("Shutting down...")

    // Give in-flight requests 30s to complete
    shutdownCtx, shutdownCancel := context.WithTimeout(
        context.Background(), 30*time.Second,
    )
    defer shutdownCancel()

    return server.Shutdown(shutdownCtx)
}
```

Go concurrency patterns:
1. **Fan-out/Fan-in** — distribute work to N goroutines, collect results
2. **Pipeline** — chain channel stages with context cancellation
3. **`errgroup`** — structured concurrency with first-error cancellation
4. **Rate limiter** — token bucket via buffered channel
5. **Graceful shutdown** — context cancellation + shutdown timeout'''
    ),
    (
        "go/testing-patterns",
        "Show Go testing patterns: table-driven tests, test helpers, mocks, and benchmarks.",
        '''Go testing patterns:

```go
package auth_test

import (
    "context"
    "errors"
    "testing"
    "time"

    "myapp/auth"
)


// --- Table-driven tests ---

func TestValidatePassword(t *testing.T) {
    tests := []struct {
        name     string
        password string
        wantErr  bool
        errMsg   string
    }{
        {"valid password", "SecureP@ss123", false, ""},
        {"too short", "Ab1!", false, "at least 12 characters"},
        {"no uppercase", "lowercase123!", true, "uppercase letter"},
        {"no digit", "NoDigitsHere!", true, "digit"},
        {"empty", "", true, "at least 12 characters"},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            err := auth.ValidatePassword(tt.password)

            if tt.wantErr {
                if err == nil {
                    t.Fatal("expected error, got nil")
                }
                if tt.errMsg != "" && !containsStr(err.Error(), tt.errMsg) {
                    t.Errorf("error %q should contain %q", err, tt.errMsg)
                }
            } else if err != nil {
                t.Errorf("unexpected error: %v", err)
            }
        })
    }
}


// --- Test helpers ---

func newTestUser(t *testing.T) *auth.User {
    t.Helper() // Errors point to caller, not this function
    user, err := auth.NewUser("test@example.com", "TestP@ssword123")
    if err != nil {
        t.Fatalf("failed to create test user: %v", err)
    }
    return user
}

// Temporary directory cleanup
func testDir(t *testing.T) string {
    t.Helper()
    dir := t.TempDir() // Auto-cleaned after test
    return dir
}


// --- Interface-based mocking ---

// Define interface for dependency
type TokenStore interface {
    Save(ctx context.Context, token string, userID string, ttl time.Duration) error
    Get(ctx context.Context, token string) (string, error)
    Delete(ctx context.Context, token string) error
}

// Mock implementation
type mockTokenStore struct {
    tokens map[string]string
    saveErr error
}

func newMockTokenStore() *mockTokenStore {
    return &mockTokenStore{tokens: make(map[string]string)}
}

func (m *mockTokenStore) Save(_ context.Context, token, userID string,
    _ time.Duration) error {
    if m.saveErr != nil {
        return m.saveErr
    }
    m.tokens[token] = userID
    return nil
}

func (m *mockTokenStore) Get(_ context.Context, token string) (string, error) {
    uid, ok := m.tokens[token]
    if !ok {
        return "", errors.New("token not found")
    }
    return uid, nil
}

func (m *mockTokenStore) Delete(_ context.Context, token string) error {
    delete(m.tokens, token)
    return nil
}


func TestAuthService_Login(t *testing.T) {
    store := newMockTokenStore()
    svc := auth.NewService(store)

    t.Run("successful login", func(t *testing.T) {
        token, err := svc.Login(context.Background(), "test@example.com", "password")
        if err != nil {
            t.Fatalf("Login failed: %v", err)
        }
        if token == "" {
            t.Fatal("expected non-empty token")
        }

        // Verify token was stored
        uid, err := store.Get(context.Background(), token)
        if err != nil {
            t.Fatalf("token not stored: %v", err)
        }
        if uid == "" {
            t.Error("expected user ID in store")
        }
    })

    t.Run("store failure", func(t *testing.T) {
        store.saveErr = errors.New("connection refused")
        _, err := svc.Login(context.Background(), "test@example.com", "password")
        if err == nil {
            t.Fatal("expected error when store fails")
        }
        store.saveErr = nil // Reset
    })
}


// --- Benchmarks ---

func BenchmarkHashPassword(b *testing.B) {
    for i := 0; i < b.N; i++ {
        auth.HashPassword("SecureP@ss123")
    }
}

func BenchmarkValidateToken(b *testing.B) {
    token := auth.GenerateToken("user-123")
    b.ResetTimer() // Exclude setup from timing

    b.RunParallel(func(pb *testing.PB) {
        for pb.Next() {
            auth.ValidateToken(token)
        }
    })
}


// --- Test with cleanup ---

func TestWithDatabase(t *testing.T) {
    db := setupTestDB(t)
    t.Cleanup(func() {
        db.Close()
    })

    // Test code using db...
}


// --- Subtests for shared setup ---

func TestUserCRUD(t *testing.T) {
    db := setupTestDB(t)
    t.Cleanup(func() { db.Close() })

    var userID string

    t.Run("Create", func(t *testing.T) {
        var err error
        userID, err = db.CreateUser("test@example.com")
        if err != nil {
            t.Fatal(err)
        }
    })

    t.Run("Read", func(t *testing.T) {
        user, err := db.GetUser(userID)
        if err != nil {
            t.Fatal(err)
        }
        if user.Email != "test@example.com" {
            t.Errorf("got email %q, want %q", user.Email, "test@example.com")
        }
    })
}
```

Go testing patterns:
1. **Table-driven tests** — `[]struct{}` with `t.Run()` for named subtests
2. **`t.Helper()`** — error messages point to calling test, not helper
3. **Interface mocks** — define interface, implement mock struct for testing
4. **`b.RunParallel()`** — parallel benchmarks for concurrent performance
5. **`t.Cleanup()`** — guaranteed teardown even on test failure'''
    ),
]
"""
