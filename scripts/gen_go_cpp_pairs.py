#!/usr/bin/env python3
"""Generate targeted Go and C++ training pairs for weak eval categories."""
import json, pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "loras" / "training_data" / "v8_go_cpp_pairs.jsonl"

SYSTEM = "You are a helpful AI coding assistant."

PAIRS = [
    # =========================================================================
    # GO — goroutines_waitgroup (D2)
    # =========================================================================
    (
        "How do I use goroutines with a WaitGroup in Go to run tasks concurrently?",
        """Goroutines are lightweight threads managed by the Go runtime. A `sync.WaitGroup` coordinates waiting for a collection of goroutines to finish.

```go
package main

import (
    "fmt"
    "sync"
    "time"
)

func worker(id int, wg *sync.WaitGroup) {
    defer wg.Done() // Decrement counter when goroutine completes
    fmt.Printf("Worker %d starting\\n", id)
    time.Sleep(time.Millisecond * 100) // Simulate work
    fmt.Printf("Worker %d done\\n", id)
}

func main() {
    var wg sync.WaitGroup

    for i := 1; i <= 5; i++ {
        wg.Add(1) // Increment counter before launching goroutine
        go worker(i, &wg)
    }

    wg.Wait() // Block until all goroutines finish
    fmt.Println("All workers completed")
}
```

**Key rules:**

1. **Always call `wg.Add()` before `go func()`** — if you call Add inside the goroutine, there's a race between the main goroutine reaching `Wait()` and the child goroutine calling `Add()`.

2. **Pass `*sync.WaitGroup` by pointer** — WaitGroup contains a mutex internally. Copying it breaks synchronization.

3. **Use `defer wg.Done()`** — placing it at the top of the goroutine ensures Done is called even if the goroutine panics.

**Testing concurrent code:**

```go
func TestConcurrentWorkers(t *testing.T) {
    var wg sync.WaitGroup
    results := make([]int, 0, 5)
    var mu sync.Mutex

    for i := 0; i < 5; i++ {
        wg.Add(1)
        go func(id int) {
            defer wg.Done()
            mu.Lock()
            results = append(results, id)
            mu.Unlock()
        }(i) // Capture loop variable by passing as argument
    }

    wg.Wait()
    if len(results) != 5 {
        t.Errorf("expected 5 results, got %d", len(results))
    }
}
```

The closure captures the loop variable `i` — always pass it as a function argument to avoid the classic Go closure bug where all goroutines see the final value of `i`."""
    ),

    # =========================================================================
    # GO — channels (D2)
    # =========================================================================
    (
        "Explain Go channels with practical examples. When should I use buffered vs unbuffered channels?",
        """Channels are Go's primary mechanism for communication between goroutines. They enforce synchronization by design.

**Unbuffered channels** block both sender and receiver until the other side is ready:

```go
package main

import "fmt"

func main() {
    ch := make(chan string) // unbuffered

    go func() {
        ch <- "hello" // blocks until main reads
    }()

    msg := <-ch // blocks until goroutine sends
    fmt.Println(msg)
}
```

**Buffered channels** allow sending without blocking until the buffer is full:

```go
func main() {
    ch := make(chan int, 3) // buffer size 3

    ch <- 1 // doesn't block
    ch <- 2 // doesn't block
    ch <- 3 // doesn't block
    // ch <- 4 would block — buffer full

    fmt.Println(<-ch) // 1 (FIFO order)
}
```

**Fan-out/fan-in pattern** — distribute work across goroutines, collect results:

```go
func fanOutFanIn(jobs []int) []int {
    jobCh := make(chan int, len(jobs))
    resultCh := make(chan int, len(jobs))

    // Fan-out: 3 workers
    var wg sync.WaitGroup
    for w := 0; w < 3; w++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for job := range jobCh {
                resultCh <- job * job // process
            }
        }()
    }

    // Send jobs
    for _, j := range jobs {
        jobCh <- j
    }
    close(jobCh) // Signal no more jobs

    // Close results after all workers done
    go func() {
        wg.Wait()
        close(resultCh)
    }()

    // Fan-in: collect results
    var results []int
    for r := range resultCh {
        results = append(results, r)
    }
    return results
}
```

**When to use which:**

| Use case | Channel type |
|----------|-------------|
| Signaling (done, cancel) | Unbuffered |
| Request-response | Unbuffered |
| Work queue with backpressure | Buffered (small) |
| Batch collection | Buffered (known size) |

**Common mistake** — forgetting to close channels causes goroutine leaks:

```go
// BAD: range over channel never terminates if not closed
for v := range ch {
    process(v)
}
// The goroutine running this loop leaks if ch is never closed
```

Always close channels from the **sender** side, never the receiver."""
    ),

    # =========================================================================
    # GO — select_statement (D3)
    # =========================================================================
    (
        "How does the select statement work in Go? Show me patterns for timeouts and multiplexing.",
        """The `select` statement lets a goroutine wait on multiple channel operations simultaneously. It blocks until one case is ready; if multiple are ready, it picks one at random.

**Basic multiplexing:**

```go
func multiplex(ch1, ch2 <-chan string) <-chan string {
    out := make(chan string)
    go func() {
        defer close(out)
        for ch1 != nil || ch2 != nil {
            select {
            case v, ok := <-ch1:
                if !ok {
                    ch1 = nil // Stop selecting on closed channel
                    continue
                }
                out <- v
            case v, ok := <-ch2:
                if !ok {
                    ch2 = nil
                    continue
                }
                out <- v
            }
        }
    }()
    return out
}
```

**Timeout pattern:**

```go
func fetchWithTimeout(url string, timeout time.Duration) (string, error) {
    resultCh := make(chan string, 1)
    errCh := make(chan error, 1)

    go func() {
        resp, err := http.Get(url)
        if err != nil {
            errCh <- err
            return
        }
        defer resp.Body.Close()
        body, _ := io.ReadAll(resp.Body)
        resultCh <- string(body)
    }()

    select {
    case result := <-resultCh:
        return result, nil
    case err := <-errCh:
        return "", err
    case <-time.After(timeout):
        return "", fmt.Errorf("timeout after %v", timeout)
    }
}
```

**Non-blocking send/receive with default:**

```go
select {
case msg := <-ch:
    fmt.Println("received:", msg)
default:
    fmt.Println("no message available") // Runs immediately if ch is empty
}
```

**Ticker + done pattern** for periodic work with clean shutdown:

```go
func periodicWorker(ctx context.Context, interval time.Duration) {
    ticker := time.NewTicker(interval)
    defer ticker.Stop()

    for {
        select {
        case <-ctx.Done():
            fmt.Println("shutting down")
            return
        case t := <-ticker.C:
            fmt.Println("tick at", t)
            doWork()
        }
    }
}
```

**Key insight:** `select` with `context.Done()` is the idiomatic Go pattern for cancellation. Never use `time.Sleep` in goroutines — use tickers or timers with select instead, so you can respond to cancellation signals."""
    ),

    # =========================================================================
    # GO — error_handling (D2)
    # =========================================================================
    (
        "What are Go's error handling best practices? How do I create custom errors and wrap errors?",
        """Go uses explicit error returns instead of exceptions. The `error` interface is simple: any type with an `Error() string` method satisfies it.

**Basic pattern — always check errors:**

```go
f, err := os.Open("config.json")
if err != nil {
    return fmt.Errorf("opening config: %w", err) // Wrap with context
}
defer f.Close()
```

**Custom error types** for structured error handling:

```go
type ValidationError struct {
    Field   string
    Message string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation failed on %s: %s", e.Field, e.Message)
}

func validateAge(age int) error {
    if age < 0 || age > 150 {
        return &ValidationError{
            Field:   "age",
            Message: fmt.Sprintf("must be 0-150, got %d", age),
        }
    }
    return nil
}
```

**Error wrapping** (Go 1.13+) preserves the error chain:

```go
func loadConfig(path string) (*Config, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, fmt.Errorf("loadConfig(%s): %w", path, err)
    }

    var cfg Config
    if err := json.Unmarshal(data, &cfg); err != nil {
        return nil, fmt.Errorf("parsing config: %w", err)
    }
    return &cfg, nil
}
```

**Checking wrapped errors** with `errors.Is` and `errors.As`:

```go
_, err := loadConfig("missing.json")

// Check for specific error value
if errors.Is(err, os.ErrNotExist) {
    fmt.Println("file not found, using defaults")
}

// Check for specific error type
var valErr *ValidationError
if errors.As(err, &valErr) {
    fmt.Printf("field %s: %s\\n", valErr.Field, valErr.Message)
}
```

**Sentinel errors** for known conditions:

```go
var (
    ErrNotFound     = errors.New("not found")
    ErrUnauthorized = errors.New("unauthorized")
    ErrRateLimit    = errors.New("rate limit exceeded")
)

func getUser(id string) (*User, error) {
    user, ok := db[id]
    if !ok {
        return nil, fmt.Errorf("getUser(%s): %w", id, ErrNotFound)
    }
    return user, nil
}
```

**Testing errors:**

```go
func TestGetUser_NotFound(t *testing.T) {
    _, err := getUser("nonexistent")
    if !errors.Is(err, ErrNotFound) {
        t.Errorf("expected ErrNotFound, got %v", err)
    }
}
```

The key principle: add context at each layer with `%w`, and check errors at the boundary with `errors.Is`/`errors.As`. Never compare error strings directly."""
    ),

    # =========================================================================
    # GO — interfaces (D3)
    # =========================================================================
    (
        "How do Go interfaces work? Show me practical patterns including the empty interface and type assertions.",
        """Go interfaces are satisfied implicitly — no `implements` keyword. If a type has the right methods, it satisfies the interface automatically.

**Defining and implementing interfaces:**

```go
type Storage interface {
    Get(key string) ([]byte, error)
    Put(key string, value []byte) error
    Delete(key string) error
}

// MemoryStorage satisfies Storage — no declaration needed
type MemoryStorage struct {
    data map[string][]byte
    mu   sync.RWMutex
}

func NewMemoryStorage() *MemoryStorage {
    return &MemoryStorage{data: make(map[string][]byte)}
}

func (m *MemoryStorage) Get(key string) ([]byte, error) {
    m.mu.RLock()
    defer m.mu.RUnlock()
    v, ok := m.data[key]
    if !ok {
        return nil, fmt.Errorf("key %q: %w", key, ErrNotFound)
    }
    return v, nil
}

func (m *MemoryStorage) Put(key string, value []byte) error {
    m.mu.Lock()
    defer m.mu.Unlock()
    m.data[key] = value
    return nil
}

func (m *MemoryStorage) Delete(key string) error {
    m.mu.Lock()
    defer m.mu.Unlock()
    delete(m.data, key)
    return nil
}
```

**Interface composition:**

```go
type Reader interface {
    Read(p []byte) (n int, err error)
}

type Writer interface {
    Write(p []byte) (n int, err error)
}

type ReadWriter interface {
    Reader
    Writer
}
```

**Type assertions and type switches:**

```go
func describe(i interface{}) string {
    switch v := i.(type) {
    case string:
        return fmt.Sprintf("string of length %d", len(v))
    case int:
        return fmt.Sprintf("integer: %d", v)
    case Storage:
        return "a Storage implementation"
    default:
        return fmt.Sprintf("unknown type: %T", v)
    }
}

// Safe type assertion (always use the two-value form)
if s, ok := i.(Storage); ok {
    data, _ := s.Get("key")
    fmt.Println(string(data))
}
```

**Accept interfaces, return structs** — the Go proverb:

```go
// Good: function accepts interface
func ProcessData(r io.Reader) error {
    data, err := io.ReadAll(r)
    if err != nil {
        return err
    }
    // process data...
    return nil
}

// Callers can pass *os.File, *bytes.Buffer, *http.Response.Body, etc.
```

**Testing with interfaces:**

```go
type MockStorage struct {
    getFunc func(string) ([]byte, error)
}

func (m *MockStorage) Get(key string) ([]byte, error) { return m.getFunc(key) }
func (m *MockStorage) Put(key string, val []byte) error { return nil }
func (m *MockStorage) Delete(key string) error { return nil }

func TestService(t *testing.T) {
    mock := &MockStorage{
        getFunc: func(key string) ([]byte, error) {
            return []byte("test-data"), nil
        },
    }
    svc := NewService(mock) // Inject mock
    result := svc.Process("mykey")
    // assert result...
}
```

Keep interfaces small (1-3 methods). The standard library's `io.Reader` (1 method) is the gold standard. Large interfaces force unnecessary implementation burden on consumers."""
    ),

    # =========================================================================
    # GO — context_package (D3)
    # =========================================================================
    (
        "How do I use the context package in Go for cancellation, timeouts, and request-scoped values?",
        """The `context` package provides a way to carry deadlines, cancellation signals, and request-scoped values across API boundaries and goroutines.

**Cancellation:**

```go
func longRunningTask(ctx context.Context) error {
    for i := 0; i < 100; i++ {
        select {
        case <-ctx.Done():
            return ctx.Err() // context.Canceled or context.DeadlineExceeded
        default:
            // Do one unit of work
            processChunk(i)
        }
    }
    return nil
}

func main() {
    ctx, cancel := context.WithCancel(context.Background())
    defer cancel() // Always defer cancel to free resources

    go func() {
        time.Sleep(2 * time.Second)
        cancel() // Signal cancellation after 2s
    }()

    if err := longRunningTask(ctx); err != nil {
        fmt.Println("task cancelled:", err)
    }
}
```

**Timeouts:**

```go
func fetchAPI(ctx context.Context, url string) ([]byte, error) {
    ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel()

    req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
    if err != nil {
        return nil, err
    }

    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    return io.ReadAll(resp.Body)
}
```

**Request-scoped values** (use sparingly — for cross-cutting concerns only):

```go
type contextKey string

const requestIDKey contextKey = "requestID"

func WithRequestID(ctx context.Context, id string) context.Context {
    return context.WithValue(ctx, requestIDKey, id)
}

func GetRequestID(ctx context.Context) string {
    if id, ok := ctx.Value(requestIDKey).(string); ok {
        return id
    }
    return "unknown"
}

// Middleware example
func requestIDMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        id := uuid.New().String()
        ctx := WithRequestID(r.Context(), id)
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}
```

**Best practices:**

1. **Context is always the first parameter**: `func DoSomething(ctx context.Context, arg1 string)`
2. **Never store context in a struct** — pass it explicitly
3. **Always call cancel()** — even if the context expires naturally, cancel frees resources early
4. **Don't use context.Value for passing function arguments** — it's for metadata (request ID, auth token, trace ID)
5. **Check `ctx.Err()` in loops** — this is how you make goroutines responsive to cancellation

```go
func TestContextCancellation(t *testing.T) {
    ctx, cancel := context.WithCancel(context.Background())
    cancel() // Cancel immediately

    err := longRunningTask(ctx)
    if !errors.Is(err, context.Canceled) {
        t.Errorf("expected context.Canceled, got %v", err)
    }
}
```"""
    ),

    # =========================================================================
    # GO — generics (D3)
    # =========================================================================
    (
        "How do Go generics work? Show me practical examples with type constraints.",
        """Go 1.18 introduced generics with type parameters and constraints. They eliminate the need for `interface{}` casts and code generation in many cases.

**Basic generic function:**

```go
func Map[T any, U any](slice []T, fn func(T) U) []U {
    result := make([]U, len(slice))
    for i, v := range slice {
        result[i] = fn(v)
    }
    return result
}

// Usage
names := Map([]int{1, 2, 3}, func(n int) string {
    return fmt.Sprintf("item_%d", n)
})
// ["item_1", "item_2", "item_3"]
```

**Type constraints** restrict what types can be used:

```go
// Built-in constraints from golang.org/x/exp/constraints (or define your own)
type Number interface {
    ~int | ~int32 | ~int64 | ~float32 | ~float64
}

func Sum[T Number](values []T) T {
    var total T
    for _, v := range values {
        total += v
    }
    return total
}

// Works with any type whose underlying type matches
type Score int
scores := []Score{10, 20, 30}
total := Sum(scores) // 60 — works because ~int matches Score
```

**Generic data structures:**

```go
type Stack[T any] struct {
    items []T
}

func (s *Stack[T]) Push(item T) {
    s.items = append(s.items, item)
}

func (s *Stack[T]) Pop() (T, bool) {
    if len(s.items) == 0 {
        var zero T
        return zero, false
    }
    item := s.items[len(s.items)-1]
    s.items = s.items[:len(s.items)-1]
    return item, true
}

func (s *Stack[T]) Peek() (T, bool) {
    if len(s.items) == 0 {
        var zero T
        return zero, false
    }
    return s.items[len(s.items)-1], true
}

func (s *Stack[T]) Len() int {
    return len(s.items)
}
```

**The `comparable` constraint** enables map keys and equality checks:

```go
func Contains[T comparable](slice []T, target T) bool {
    for _, v := range slice {
        if v == target {
            return true
        }
    }
    return false
}

func Unique[T comparable](slice []T) []T {
    seen := make(map[T]struct{})
    result := make([]T, 0, len(slice))
    for _, v := range slice {
        if _, ok := seen[v]; !ok {
            seen[v] = struct{}{}
            result = append(result, v)
        }
    }
    return result
}
```

**Testing generic functions:**

```go
func TestMap(t *testing.T) {
    doubled := Map([]int{1, 2, 3}, func(n int) int { return n * 2 })
    expected := []int{2, 4, 6}
    for i, v := range doubled {
        if v != expected[i] {
            t.Errorf("index %d: got %d, want %d", i, v, expected[i])
        }
    }
}

func TestStack(t *testing.T) {
    s := &Stack[string]{}
    s.Push("a")
    s.Push("b")
    v, ok := s.Pop()
    if !ok || v != "b" {
        t.Errorf("expected 'b', got %q", v)
    }
}
```

Use generics when you'd otherwise repeat the same logic for multiple types. Don't use them for single-type functions — regular Go code is simpler and clearer."""
    ),

    # =========================================================================
    # GO — http_servers (D2)
    # =========================================================================
    (
        "How do I build HTTP servers in Go with routing, middleware, and JSON handling?",
        """Go's `net/http` package provides a production-ready HTTP server out of the box.

**Basic server with routing (Go 1.22+ enhanced patterns):**

```go
package main

import (
    "encoding/json"
    "log"
    "net/http"
    "sync"
)

type User struct {
    ID    string `json:"id"`
    Name  string `json:"name"`
    Email string `json:"email"`
}

type UserStore struct {
    mu    sync.RWMutex
    users map[string]User
}

func NewUserStore() *UserStore {
    return &UserStore{users: make(map[string]User)}
}

func (s *UserStore) handleGetUser(w http.ResponseWriter, r *http.Request) {
    id := r.PathValue("id") // Go 1.22 path parameters
    s.mu.RLock()
    user, ok := s.users[id]
    s.mu.RUnlock()

    if !ok {
        http.Error(w, `{"error":"not found"}`, http.StatusNotFound)
        return
    }
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(user)
}

func (s *UserStore) handleCreateUser(w http.ResponseWriter, r *http.Request) {
    var user User
    if err := json.NewDecoder(r.Body).Decode(&user); err != nil {
        http.Error(w, `{"error":"invalid json"}`, http.StatusBadRequest)
        return
    }

    s.mu.Lock()
    s.users[user.ID] = user
    s.mu.Unlock()

    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusCreated)
    json.NewEncoder(w).Encode(user)
}

func main() {
    store := NewUserStore()
    mux := http.NewServeMux()

    mux.HandleFunc("GET /users/{id}", store.handleGetUser)
    mux.HandleFunc("POST /users", store.handleCreateUser)

    // Wrap with middleware
    handler := loggingMiddleware(mux)

    log.Println("Server starting on :8080")
    log.Fatal(http.ListenAndServe(":8080", handler))
}
```

**Middleware pattern:**

```go
func loggingMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        next.ServeHTTP(w, r)
        log.Printf("%s %s %v", r.Method, r.URL.Path, time.Since(start))
    })
}

func authMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        token := r.Header.Get("Authorization")
        if token == "" {
            http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
            return
        }
        // Validate token, add user to context
        next.ServeHTTP(w, r)
    })
}
```

**Graceful shutdown:**

```go
func main() {
    srv := &http.Server{
        Addr:         ":8080",
        Handler:      handler,
        ReadTimeout:  10 * time.Second,
        WriteTimeout: 30 * time.Second,
    }

    go func() {
        if err := srv.ListenAndServe(); err != http.ErrServerClosed {
            log.Fatal(err)
        }
    }()

    quit := make(chan os.Signal, 1)
    signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
    <-quit

    ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()
    srv.Shutdown(ctx) // Gracefully drain connections
}
```

Always set read/write timeouts on production servers — the zero-value `http.Server` has no timeouts, which makes it vulnerable to slowloris attacks."""
    ),

    # =========================================================================
    # GO — testing (D3)
    # =========================================================================
    (
        "How do I write effective tests in Go? Show me table-driven tests, benchmarks, and test helpers.",
        """Go's testing package is minimal but powerful. The convention is to put tests in `_test.go` files in the same package.

**Table-driven tests** — the idiomatic Go testing pattern:

```go
func TestAdd(t *testing.T) {
    tests := []struct {
        name     string
        a, b     int
        expected int
    }{
        {"positive", 2, 3, 5},
        {"negative", -1, -1, -2},
        {"zero", 0, 0, 0},
        {"mixed", -5, 10, 5},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got := Add(tt.a, tt.b)
            if got != tt.expected {
                t.Errorf("Add(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.expected)
            }
        })
    }
}
```

**Test helpers** with `t.Helper()`:

```go
func assertEqual[T comparable](t *testing.T, got, want T) {
    t.Helper() // Marks this as a helper — errors report caller's line
    if got != want {
        t.Errorf("got %v, want %v", got, want)
    }
}

func assertNoError(t *testing.T, err error) {
    t.Helper()
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }
}
```

**Benchmarks:**

```go
func BenchmarkFibonacci(b *testing.B) {
    for i := 0; i < b.N; i++ {
        Fibonacci(20)
    }
}

// Run with: go test -bench=. -benchmem
// Output: BenchmarkFibonacci-8  23456  50123 ns/op  0 B/op  0 allocs/op
```

**TestMain** for setup/teardown:

```go
var testDB *sql.DB

func TestMain(m *testing.M) {
    // Setup
    testDB = setupTestDatabase()

    code := m.Run() // Run all tests

    // Teardown
    testDB.Close()
    os.Exit(code)
}
```

**Parallel tests:**

```go
func TestParallel(t *testing.T) {
    tests := []struct{ name, input, want string }{
        {"upper", "hello", "HELLO"},
        {"lower", "WORLD", "world"},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            t.Parallel() // Run this subtest in parallel
            got := transform(tt.input)
            assertEqual(t, got, tt.want)
        })
    }
}
```

**Testing HTTP handlers:**

```go
func TestGetUser(t *testing.T) {
    store := NewUserStore()
    store.users["1"] = User{ID: "1", Name: "Alice"}

    req := httptest.NewRequest("GET", "/users/1", nil)
    req.SetPathValue("id", "1")
    w := httptest.NewRecorder()

    store.handleGetUser(w, req)

    if w.Code != http.StatusOK {
        t.Fatalf("status = %d, want 200", w.Code)
    }

    var user User
    json.NewDecoder(w.Body).Decode(&user)
    assertEqual(t, user.Name, "Alice")
}
```

Run tests with `go test ./...` for all packages, `go test -v` for verbose output, and `go test -race` to detect race conditions."""
    ),

    # =========================================================================
    # GO — race_conditions (D4)
    # =========================================================================
    (
        "How do I detect and fix race conditions in Go? What synchronization primitives should I use?",
        """Race conditions occur when multiple goroutines access shared data concurrently and at least one is writing. Go's race detector (`go test -race`) catches these at runtime.

**Common race — unsynchronized map access:**

```go
// BUG: concurrent map writes panic
m := make(map[string]int)
var wg sync.WaitGroup
for i := 0; i < 100; i++ {
    wg.Add(1)
    go func(n int) {
        defer wg.Done()
        m[fmt.Sprintf("key%d", n)] = n // RACE: concurrent write
    }(i)
}
```

**Fix 1: sync.Mutex** for exclusive access:

```go
type SafeCounter struct {
    mu sync.Mutex
    counts map[string]int
}

func (c *SafeCounter) Increment(key string) {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.counts[key]++
}

func (c *SafeCounter) Get(key string) int {
    c.mu.Lock()
    defer c.mu.Unlock()
    return c.counts[key]
}
```

**Fix 2: sync.RWMutex** for read-heavy workloads:

```go
type Cache struct {
    mu   sync.RWMutex
    data map[string][]byte
}

func (c *Cache) Get(key string) ([]byte, bool) {
    c.mu.RLock()         // Multiple readers allowed
    defer c.mu.RUnlock()
    v, ok := c.data[key]
    return v, ok
}

func (c *Cache) Set(key string, val []byte) {
    c.mu.Lock()          // Exclusive write access
    defer c.mu.Unlock()
    c.data[key] = val
}
```

**Fix 3: sync.Map** for concurrent map with many goroutines:

```go
var store sync.Map

store.Store("key", "value")
val, ok := store.Load("key")
store.Range(func(k, v interface{}) bool {
    fmt.Println(k, v)
    return true // continue iteration
})
```

**Fix 4: Channels** — share by communicating, don't communicate by sharing:

```go
func counterService() (increment func(string), get func(string) int) {
    type getReq struct {
        key  string
        resp chan int
    }

    incCh := make(chan string)
    getCh := make(chan getReq)

    go func() {
        counts := make(map[string]int)
        for {
            select {
            case key := <-incCh:
                counts[key]++
            case req := <-getCh:
                req.resp <- counts[req.key]
            }
        }
    }()

    increment = func(key string) { incCh <- key }
    get = func(key string) int {
        resp := make(chan int)
        getCh <- getReq{key, resp}
        return <-resp
    }
    return
}
```

**Fix 5: sync/atomic** for simple counters:

```go
var ops atomic.Int64

// Safe from any goroutine
ops.Add(1)
total := ops.Load()
```

**Detecting races in tests:**

```go
func TestConcurrentAccess(t *testing.T) {
    c := &SafeCounter{counts: make(map[string]int)}
    var wg sync.WaitGroup

    for i := 0; i < 1000; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            c.Increment("total")
        }()
    }
    wg.Wait()

    if got := c.Get("total"); got != 1000 {
        t.Errorf("got %d, want 1000", got)
    }
}
// Run: go test -race ./...
```

**Decision guide:** Use atomic for single values, Mutex for complex state, RWMutex when reads dominate, channels when the logic is naturally a pipeline or actor model."""
    ),

    # =========================================================================
    # C++ — smart_pointers_raii (D2)
    # =========================================================================
    (
        "Explain RAII and smart pointers in modern C++. When should I use unique_ptr vs shared_ptr?",
        """RAII (Resource Acquisition Is Initialization) is the most important C++ idiom. Resources are acquired in constructors and released in destructors — no manual cleanup needed.

**std::unique_ptr — exclusive ownership:**

```cpp
#include <memory>
#include <string>
#include <vector>
#include <iostream>

class DatabaseConnection {
    std::string connStr_;
public:
    explicit DatabaseConnection(const std::string& connStr)
        : connStr_(connStr) {
        std::cout << "Connected to " << connStr_ << "\\n";
    }
    ~DatabaseConnection() {
        std::cout << "Disconnected from " << connStr_ << "\\n";
    }

    void query(const std::string& sql) {
        std::cout << "Executing: " << sql << "\\n";
    }
};

void processData() {
    // unique_ptr: automatic cleanup when scope exits
    auto db = std::make_unique<DatabaseConnection>("localhost:5432");
    db->query("SELECT * FROM users");
    // ~DatabaseConnection called automatically here
}
```

**Ownership transfer with unique_ptr:**

```cpp
class ResourceManager {
    std::vector<std::unique_ptr<DatabaseConnection>> pools_;
public:
    void addConnection(std::unique_ptr<DatabaseConnection> conn) {
        pools_.push_back(std::move(conn)); // Transfer ownership
    }
};

// Usage
auto conn = std::make_unique<DatabaseConnection>("db1");
manager.addConnection(std::move(conn)); // conn is now nullptr
```

**std::shared_ptr — shared ownership with reference counting:**

```cpp
class Node {
    int value_;
    std::vector<std::shared_ptr<Node>> children_;
public:
    explicit Node(int v) : value_(v) {}

    void addChild(std::shared_ptr<Node> child) {
        children_.push_back(child);
    }
};

void buildTree() {
    auto root = std::make_shared<Node>(1);
    auto child = std::make_shared<Node>(2);
    root->addChild(child);  // ref count = 2
    // child goes out of scope: ref count = 1 (root still holds it)
    // root goes out of scope: ref count = 0, Node(2) destroyed
}
```

**std::weak_ptr — break circular references:**

```cpp
class Employee;

class Department {
    std::vector<std::shared_ptr<Employee>> members_;
};

class Employee {
    std::weak_ptr<Department> department_; // Weak reference — won't prevent destruction
public:
    void setDepartment(std::shared_ptr<Department> dept) {
        department_ = dept;
    }

    void doWork() {
        if (auto dept = department_.lock()) { // Promote to shared_ptr
            // Department still exists, use it
        } else {
            // Department was destroyed
        }
    }
};
```

**Decision guide:**

| Ownership | Smart pointer | Use case |
|-----------|--------------|----------|
| Single owner | `unique_ptr` | 95% of cases. Default choice. |
| Shared owner | `shared_ptr` | Caches, graphs, observer patterns |
| Non-owning ref | `weak_ptr` | Breaking cycles, optional references |
| No ownership | Raw pointer/reference | Function parameters that don't own |

**RAII for custom resources:**

```cpp
class FileHandle {
    FILE* f_;
public:
    explicit FileHandle(const char* path, const char* mode)
        : f_(std::fopen(path, mode)) {
        if (!f_) throw std::runtime_error("Cannot open file");
    }
    ~FileHandle() { if (f_) std::fclose(f_); }

    // Delete copy, allow move
    FileHandle(const FileHandle&) = delete;
    FileHandle& operator=(const FileHandle&) = delete;
    FileHandle(FileHandle&& other) noexcept : f_(other.f_) { other.f_ = nullptr; }

    FILE* get() { return f_; }
};
```

The rule of thumb: if you're writing `new` or `delete` in application code, you're probably doing it wrong. Use `make_unique` and `make_shared` instead."""
    ),

    # =========================================================================
    # C++ — move_semantics (D3)
    # =========================================================================
    (
        "Explain move semantics in C++. When does the compiler use moves vs copies, and how do I write move constructors?",
        """Move semantics avoid expensive deep copies by transferring resources from temporary objects. Introduced in C++11, this is one of the biggest performance wins in modern C++.

**The problem moves solve:**

```cpp
std::vector<int> createLargeVector() {
    std::vector<int> v(1'000'000);
    std::iota(v.begin(), v.end(), 0);
    return v; // Without moves: copies 1M integers. With moves: transfers the pointer.
}
```

**Writing a move constructor and move assignment:**

```cpp
class Buffer {
    size_t size_;
    int* data_;
public:
    // Constructor
    explicit Buffer(size_t size) : size_(size), data_(new int[size]{}) {}

    // Destructor
    ~Buffer() { delete[] data_; }

    // Copy constructor (deep copy)
    Buffer(const Buffer& other) : size_(other.size_), data_(new int[other.size_]) {
        std::copy(other.data_, other.data_ + size_, data_);
    }

    // Move constructor (steal resources)
    Buffer(Buffer&& other) noexcept
        : size_(other.size_), data_(other.data_) {
        other.size_ = 0;
        other.data_ = nullptr; // Leave source in valid but empty state
    }

    // Copy assignment
    Buffer& operator=(const Buffer& other) {
        if (this != &other) {
            delete[] data_;
            size_ = other.size_;
            data_ = new int[size_];
            std::copy(other.data_, other.data_ + size_, data_);
        }
        return *this;
    }

    // Move assignment
    Buffer& operator=(Buffer&& other) noexcept {
        if (this != &other) {
            delete[] data_;
            size_ = other.size_;
            data_ = other.data_;
            other.size_ = 0;
            other.data_ = nullptr;
        }
        return *this;
    }

    size_t size() const { return size_; }
};
```

**When moves happen automatically:**
1. Returning local variables (NRVO may elide the move entirely)
2. Passing temporaries: `process(Buffer(1000))`
3. `std::move()` — explicitly cast to rvalue reference

**std::move doesn't move — it casts:**

```cpp
Buffer a(100);
Buffer b = std::move(a); // Casts a to Buffer&&, triggering move constructor
// a is now in a valid but unspecified state — don't use its data
```

**Perfect forwarding** preserves value category in templates:

```cpp
template<typename T, typename... Args>
std::unique_ptr<T> makeUnique(Args&&... args) {
    return std::unique_ptr<T>(new T(std::forward<Args>(args)...));
}
```

**The noexcept guarantee matters:**

```cpp
// Mark move operations noexcept!
// std::vector won't use your move constructor during reallocation
// unless it's noexcept (it would risk losing elements on exception)
Buffer(Buffer&& other) noexcept;
Buffer& operator=(Buffer&& other) noexcept;
```

**Rule of Five:** If you define any of {destructor, copy constructor, copy assignment, move constructor, move assignment}, define all five. Or better — use the **Rule of Zero**: compose your class from types that manage themselves (smart pointers, std::vector, std::string) and define none.

```cpp
// Rule of Zero — compiler generates correct special members
class Person {
    std::string name_;
    std::vector<std::string> hobbies_;
    std::unique_ptr<Address> address_;
    // No destructor, no copy/move constructors needed
};
```"""
    ),

    # =========================================================================
    # C++ — template_metaprogramming (D3)
    # =========================================================================
    (
        "How does template metaprogramming work in C++? Show me practical examples beyond simple generics.",
        """Template metaprogramming (TMP) executes logic at compile time, producing zero-overhead abstractions. Modern C++ (17/20) has made TMP much more accessible.

**Compile-time computation with constexpr (preferred over old-style TMP):**

```cpp
constexpr int factorial(int n) {
    return n <= 1 ? 1 : n * factorial(n - 1);
}

static_assert(factorial(5) == 120); // Computed at compile time
```

**SFINAE and type traits — enable functions based on type properties:**

```cpp
#include <type_traits>
#include <iostream>

// Only enable for arithmetic types
template<typename T>
std::enable_if_t<std::is_arithmetic_v<T>, T>
clamp(T value, T lo, T hi) {
    return value < lo ? lo : (value > hi ? hi : value);
}

// Only enable for string-like types
template<typename T>
std::enable_if_t<std::is_convertible_v<T, std::string_view>, std::string>
repeat(const T& str, int n) {
    std::string result;
    for (int i = 0; i < n; ++i) result += str;
    return result;
}
```

**Variadic templates — type-safe printf:**

```cpp
// Base case
void print() {
    std::cout << "\\n";
}

// Recursive case — peel off one argument at a time
template<typename T, typename... Args>
void print(const T& first, const Args&... rest) {
    std::cout << first;
    if constexpr (sizeof...(rest) > 0) {
        std::cout << ", ";
    }
    print(rest...);
}

// Usage: print(1, "hello", 3.14); // Output: 1, hello, 3.14
```

**Tag dispatch — choose implementation based on type category:**

```cpp
template<typename Iter>
void advance_impl(Iter& it, int n, std::random_access_iterator_tag) {
    it += n; // O(1) for random access
}

template<typename Iter>
void advance_impl(Iter& it, int n, std::input_iterator_tag) {
    for (int i = 0; i < n; ++i) ++it; // O(n) for forward iterators
}

template<typename Iter>
void advance(Iter& it, int n) {
    advance_impl(it, n, typename std::iterator_traits<Iter>::iterator_category{});
}
```

**Compile-time type list processing:**

```cpp
template<typename... Ts>
struct TypeList {};

// Count types in list
template<typename List>
struct Size;

template<typename... Ts>
struct Size<TypeList<Ts...>> {
    static constexpr size_t value = sizeof...(Ts);
};

static_assert(Size<TypeList<int, float, double>>::value == 3);
```

**if constexpr (C++17) — cleaner than SFINAE for many cases:**

```cpp
template<typename T>
std::string serialize(const T& value) {
    if constexpr (std::is_arithmetic_v<T>) {
        return std::to_string(value);
    } else if constexpr (std::is_same_v<T, std::string>) {
        return "\"" + value + "\"";
    } else {
        return value.to_string(); // Assumes T has to_string()
    }
}
```

The modern advice: prefer `constexpr` functions over recursive templates, `if constexpr` over SFINAE, and C++20 concepts over `enable_if`. TMP is powerful but the readability cost is real — use it for library code, not application code."""
    ),

    # =========================================================================
    # C++ — containers_iterators (D2)
    # =========================================================================
    (
        "Give me a practical overview of C++ STL containers and iterators. Which container should I use when?",
        """The STL containers fall into three categories: sequence, associative, and unordered. Choosing the right one is critical for performance.

**Sequence containers:**

```cpp
#include <vector>
#include <deque>
#include <list>
#include <array>

// vector — contiguous memory, best cache performance
std::vector<int> v = {1, 2, 3, 4, 5};
v.push_back(6);      // Amortized O(1)
v[3] = 10;           // O(1) random access
// Best for: most use cases, iteration, random access

// deque — double-ended queue
std::deque<int> d;
d.push_front(1);     // O(1) at both ends
d.push_back(2);
// Best for: frequent front insertion + back insertion

// list — doubly linked list
std::list<int> l = {1, 2, 3};
auto it = std::next(l.begin());
l.insert(it, 10);   // O(1) insert at iterator position
// Best for: frequent mid-sequence insert/delete, no invalidation needed

// array — fixed size, stack allocated
std::array<int, 5> a = {1, 2, 3, 4, 5};
// Best for: known compile-time size, zero overhead
```

**Associative containers (sorted, O(log n)):**

```cpp
#include <map>
#include <set>

std::map<std::string, int> scores;
scores["Alice"] = 95;
scores.emplace("Bob", 87);     // Avoids temporary construction

// Structured bindings (C++17)
for (const auto& [name, score] : scores) {
    std::cout << name << ": " << score << "\\n";
}

// find vs [] — find doesn't insert on miss
if (auto it = scores.find("Charlie"); it != scores.end()) {
    std::cout << it->second << "\\n";
}
```

**Unordered containers (hash-based, O(1) average):**

```cpp
#include <unordered_map>
#include <unordered_set>

std::unordered_map<std::string, int> cache;
cache.reserve(1000);  // Pre-allocate buckets — avoids rehashing
cache["key1"] = 42;

// Custom hash for user types
struct Point { int x, y; };
struct PointHash {
    size_t operator()(const Point& p) const {
        return std::hash<int>{}(p.x) ^ (std::hash<int>{}(p.y) << 16);
    }
};
std::unordered_set<Point, PointHash> points;
```

**Iterator patterns:**

```cpp
// Range-based for (preferred)
for (const auto& elem : container) { /* read-only */ }
for (auto& elem : container) { /* modify in place */ }

// Iterator-based (when you need position control)
for (auto it = v.begin(); it != v.end(); ) {
    if (*it % 2 == 0) {
        it = v.erase(it); // erase returns next valid iterator
    } else {
        ++it;
    }
}

// Reverse iteration
for (auto it = v.rbegin(); it != v.rend(); ++it) {
    std::cout << *it << " ";
}
```

**Container selection guide:**

| Need | Container | Why |
|------|-----------|-----|
| Default / general purpose | `vector` | Cache-friendly, fast iteration |
| Key-value lookup | `unordered_map` | O(1) average lookup |
| Sorted key-value | `map` | O(log n), maintains order |
| Unique elements | `unordered_set` | O(1) contains check |
| FIFO queue | `deque` or `queue` | O(1) push/pop at both ends |
| Priority queue | `priority_queue` | O(log n) push/pop |
| Stable iteration + insert | `list` | Iterators never invalidated |

The most common mistake: using `std::list` when `std::vector` would be faster. Due to cache effects, vector beats list for almost every workload under ~1M elements, even with mid-sequence insertions."""
    ),

    # =========================================================================
    # C++ — algorithms_lambdas (D2)
    # =========================================================================
    (
        "Show me how to use C++ STL algorithms with lambdas effectively.",
        """The `<algorithm>` header provides 100+ algorithms that work with any iterator range. Combined with lambdas, they replace most hand-written loops.

**Searching and finding:**

```cpp
#include <algorithm>
#include <vector>
#include <string>
#include <numeric>

struct Employee {
    std::string name;
    int salary;
    std::string department;
};

std::vector<Employee> team = {
    {"Alice", 95000, "Engineering"},
    {"Bob", 87000, "Marketing"},
    {"Carol", 105000, "Engineering"},
    {"Dave", 72000, "Support"},
};

// find_if — first match
auto it = std::find_if(team.begin(), team.end(),
    [](const Employee& e) { return e.salary > 100000; });
if (it != team.end()) {
    std::cout << it->name << " earns over 100k\\n"; // Carol
}

// any_of, all_of, none_of
bool hasMarketing = std::any_of(team.begin(), team.end(),
    [](const Employee& e) { return e.department == "Marketing"; });
```

**Transforming and mapping:**

```cpp
// transform — map operation
std::vector<std::string> names;
std::transform(team.begin(), team.end(), std::back_inserter(names),
    [](const Employee& e) { return e.name; });

// Ranges version (C++20, cleaner)
auto names20 = team | std::views::transform(&Employee::name);
```

**Sorting and ordering:**

```cpp
// Sort by salary descending
std::sort(team.begin(), team.end(),
    [](const Employee& a, const Employee& b) {
        return a.salary > b.salary;
    });

// Partial sort — only need top 3
std::partial_sort(team.begin(), team.begin() + 3, team.end(),
    [](const Employee& a, const Employee& b) {
        return a.salary > b.salary;
    });

// nth_element — O(n) median finding
std::nth_element(salaries.begin(), salaries.begin() + n/2, salaries.end());
int median = salaries[n/2];
```

**Accumulating and reducing:**

```cpp
// Sum all salaries
int totalPayroll = std::accumulate(team.begin(), team.end(), 0,
    [](int sum, const Employee& e) { return sum + e.salary; });

// Count by department
auto engCount = std::count_if(team.begin(), team.end(),
    [](const Employee& e) { return e.department == "Engineering"; });
```

**Partitioning and filtering:**

```cpp
// stable_partition — split into two groups, maintain order
auto pivotIt = std::stable_partition(team.begin(), team.end(),
    [](const Employee& e) { return e.department == "Engineering"; });
// Now: [Engineering employees... | Other employees...]

// remove_if + erase idiom (pre-C++20)
team.erase(
    std::remove_if(team.begin(), team.end(),
        [](const Employee& e) { return e.salary < 80000; }),
    team.end());

// C++20: std::erase_if (much cleaner)
std::erase_if(team, [](const Employee& e) { return e.salary < 80000; });
```

**Lambda capture modes:**

```cpp
int threshold = 90000;
std::string dept = "Engineering";

// Capture by value
auto f1 = [threshold](const Employee& e) { return e.salary > threshold; };

// Capture by reference
auto f2 = [&threshold](const Employee& e) { return e.salary > threshold; };

// Capture all by value
auto f3 = [=](const Employee& e) { return e.salary > threshold && e.department == dept; };

// Capture all by reference (careful with lifetime!)
auto f4 = [&](const Employee& e) { return e.salary > threshold; };

// C++14: generic lambda
auto print = [](const auto& container) {
    for (const auto& elem : container) std::cout << elem << " ";
};
```

Prefer algorithms over raw loops — they express intent clearly (`find_if` says "search", a for loop could be doing anything), they're harder to get wrong (off-by-one errors), and the compiler can optimize them better."""
    ),

    # =========================================================================
    # C++ — threads_mutex (D3)
    # =========================================================================
    (
        "How do I use threads and mutexes in modern C++? Show me safe patterns for concurrent programming.",
        """Modern C++ (11/14/17) provides a comprehensive threading library. The key is managing shared state safely.

**Basic thread creation:**

```cpp
#include <thread>
#include <mutex>
#include <iostream>
#include <vector>

void worker(int id) {
    std::cout << "Worker " << id << " running on thread "
              << std::this_thread::get_id() << "\\n";
}

int main() {
    std::vector<std::thread> threads;
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back(worker, i);
    }
    for (auto& t : threads) {
        t.join(); // Wait for completion
    }
}
```

**Mutex and lock_guard — the fundamental pattern:**

```cpp
class ThreadSafeCounter {
    mutable std::mutex mu_;
    int count_ = 0;

public:
    void increment() {
        std::lock_guard<std::mutex> lock(mu_); // RAII lock
        ++count_;
    } // Automatically unlocked here

    int get() const {
        std::lock_guard<std::mutex> lock(mu_);
        return count_;
    }
};
```

**shared_mutex for read-heavy workloads (C++17):**

```cpp
#include <shared_mutex>

class ThreadSafeCache {
    mutable std::shared_mutex mu_;
    std::unordered_map<std::string, std::string> data_;

public:
    std::string get(const std::string& key) const {
        std::shared_lock lock(mu_); // Multiple readers allowed
        auto it = data_.find(key);
        return it != data_.end() ? it->second : "";
    }

    void set(const std::string& key, const std::string& value) {
        std::unique_lock lock(mu_); // Exclusive write access
        data_[key] = value;
    }
};
```

**Avoiding deadlocks with std::scoped_lock (C++17):**

```cpp
class Account {
    std::mutex mu_;
    double balance_;

public:
    explicit Account(double b) : balance_(b) {}

    friend void transfer(Account& from, Account& to, double amount) {
        // scoped_lock acquires both mutexes without deadlock
        std::scoped_lock lock(from.mu_, to.mu_);
        if (from.balance_ >= amount) {
            from.balance_ -= amount;
            to.balance_ += amount;
        }
    }
};
```

**Condition variables for producer-consumer:**

```cpp
template<typename T>
class ThreadSafeQueue {
    std::queue<T> queue_;
    mutable std::mutex mu_;
    std::condition_variable cv_;

public:
    void push(T value) {
        {
            std::lock_guard lock(mu_);
            queue_.push(std::move(value));
        }
        cv_.notify_one(); // Wake one waiting consumer
    }

    T pop() {
        std::unique_lock lock(mu_);
        cv_.wait(lock, [this] { return !queue_.empty(); }); // Sleep until data available
        T value = std::move(queue_.front());
        queue_.pop();
        return value;
    }

    bool tryPop(T& value, std::chrono::milliseconds timeout) {
        std::unique_lock lock(mu_);
        if (!cv_.wait_for(lock, timeout, [this] { return !queue_.empty(); })) {
            return false;
        }
        value = std::move(queue_.front());
        queue_.pop();
        return true;
    }
};
```

**std::jthread (C++20) — auto-joining thread:**

```cpp
void process(std::stop_token stoken) {
    while (!stoken.stop_requested()) {
        doWork();
    }
}

{
    std::jthread t(process); // Automatically joins on destruction
    // No need to call t.join()
}
```

**Key rules:**
1. Always use RAII locks (`lock_guard`, `unique_lock`, `scoped_lock`) — never raw `mutex.lock()`/`unlock()`
2. Keep critical sections as short as possible
3. Use `std::scoped_lock` when locking multiple mutexes
4. Prefer `std::atomic` for simple counters — no mutex overhead
5. Never hold a lock while calling user-supplied callbacks"""
    ),

    # =========================================================================
    # C++ — async_futures (D4)
    # =========================================================================
    (
        "Explain std::async, futures, and promises in C++. How do I handle asynchronous results?",
        """Futures and promises provide a higher-level abstraction for asynchronous operations, avoiding manual thread management.

**std::async — simplest way to run work asynchronously:**

```cpp
#include <future>
#include <chrono>
#include <iostream>

int computeExpensive(int n) {
    std::this_thread::sleep_for(std::chrono::seconds(2));
    return n * n;
}

int main() {
    // Launch async task (may run in new thread or deferred)
    auto future1 = std::async(std::launch::async, computeExpensive, 42);
    auto future2 = std::async(std::launch::async, computeExpensive, 100);

    // Do other work while computations run...
    std::cout << "Computing...\\n";

    // Block and get results
    int result1 = future1.get(); // Waits if not ready yet
    int result2 = future2.get();
    std::cout << "Results: " << result1 << ", " << result2 << "\\n";
}
```

**Launch policies:**
- `std::launch::async` — guaranteed new thread
- `std::launch::deferred` — lazy evaluation, runs when `.get()` is called
- Default — implementation chooses (avoid this, behavior varies)

**std::promise — manual control over the result:**

```cpp
void fetchData(std::promise<std::string> promise, const std::string& url) {
    try {
        std::string data = httpGet(url); // hypothetical HTTP call
        promise.set_value(std::move(data)); // Fulfill the promise
    } catch (...) {
        promise.set_exception(std::current_exception()); // Propagate error
    }
}

int main() {
    std::promise<std::string> promise;
    std::future<std::string> future = promise.get_future();

    std::thread t(fetchData, std::move(promise), "https://api.example.com");

    try {
        std::string data = future.get(); // Blocks, may rethrow exception
        std::cout << "Got: " << data << "\\n";
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\\n";
    }

    t.join();
}
```

**Waiting with timeout:**

```cpp
auto future = std::async(std::launch::async, longComputation);

auto status = future.wait_for(std::chrono::seconds(5));
switch (status) {
    case std::future_status::ready:
        std::cout << "Result: " << future.get() << "\\n";
        break;
    case std::future_status::timeout:
        std::cout << "Still computing...\\n";
        break;
    case std::future_status::deferred:
        std::cout << "Hasn't started yet\\n";
        break;
}
```

**Parallel map with futures:**

```cpp
template<typename T, typename F>
std::vector<std::invoke_result_t<F, T>> parallelMap(
    const std::vector<T>& input, F&& func)
{
    using ResultType = std::invoke_result_t<F, T>;
    std::vector<std::future<ResultType>> futures;
    futures.reserve(input.size());

    for (const auto& item : input) {
        futures.push_back(
            std::async(std::launch::async, std::forward<F>(func), item));
    }

    std::vector<ResultType> results;
    results.reserve(input.size());
    for (auto& f : futures) {
        results.push_back(f.get());
    }
    return results;
}

// Usage
auto squares = parallelMap(
    std::vector{1, 2, 3, 4, 5},
    [](int n) { return n * n; });
```

**std::packaged_task — reusable async wrapper:**

```cpp
std::packaged_task<int(int, int)> task([](int a, int b) {
    return a + b;
});

std::future<int> result = task.get_future();

std::thread t(std::move(task), 10, 20);
t.detach();

std::cout << "Sum: " << result.get() << "\\n"; // 30
```

**Key considerations:**
- `future.get()` can only be called **once** — it moves the result out
- Exceptions thrown in async tasks are rethrown by `future.get()`
- `std::shared_future` allows multiple readers of the same result
- For real production async I/O, consider libraries like Boost.Asio or C++20 coroutines instead of `std::async`"""
    ),

    # =========================================================================
    # C++ — cache_friendly_data (D4)
    # =========================================================================
    (
        "How do I write cache-friendly C++ code? What data layout patterns improve performance?",
        """Cache-friendly code can be 10-100x faster than cache-hostile code on the same hardware. The key insight: CPUs fetch data in cache lines (typically 64 bytes), and accessing sequential memory is dramatically faster than random access.

**Array of Structs (AoS) vs Struct of Arrays (SoA):**

```cpp
// AoS — bad for iterating over single field
struct ParticleAoS {
    float x, y, z;     // position
    float vx, vy, vz;  // velocity
    float mass;
    int type;
};
std::vector<ParticleAoS> particles(1'000'000);

// Iterating over mass touches x, y, z, vx, vy, vz too — wasted cache lines
float totalMass = 0;
for (const auto& p : particles) {
    totalMass += p.mass; // Only 4 bytes useful per 32-byte struct
}

// SoA — excellent for single-field iteration
struct ParticlesSoA {
    std::vector<float> x, y, z;
    std::vector<float> vx, vy, vz;
    std::vector<float> mass;
    std::vector<int> type;
};

ParticlesSoA particles;
// Now mass values are contiguous in memory
float totalMass = std::accumulate(particles.mass.begin(), particles.mass.end(), 0.0f);
```

**Data-oriented design — separate hot and cold data:**

```cpp
// Bad: cold data (name, description) mixed with hot data (position)
struct EntityBad {
    float x, y, z;
    std::string name;        // Rarely accessed during physics
    std::string description; // Almost never accessed
    float vx, vy, vz;
};

// Good: split hot path data
struct EntityTransform {
    float x, y, z;
    float vx, vy, vz;
};
struct EntityMetadata {
    std::string name;
    std::string description;
};
// Use parallel arrays or an ECS (Entity Component System)
std::vector<EntityTransform> transforms; // Hot: iterated every frame
std::vector<EntityMetadata> metadata;    // Cold: accessed on interaction
```

**Avoid pointer chasing:**

```cpp
// Bad: linked list — every node is a cache miss
std::list<int> values; // Each next() is a random memory access

// Good: contiguous storage
std::vector<int> values; // Sequential access, prefetcher works perfectly

// If you need stable pointers + contiguous storage:
// Use a deque or pool allocator
```

**Padding and alignment:**

```cpp
// Bad: 24 bytes due to padding
struct Wasteful {
    bool active;    // 1 byte + 7 bytes padding
    double value;   // 8 bytes
    bool visible;   // 1 byte + 7 bytes padding
};

// Good: 16 bytes — group by size
struct Efficient {
    double value;   // 8 bytes
    bool active;    // 1 byte
    bool visible;   // 1 byte + 6 bytes padding
};

static_assert(sizeof(Efficient) < sizeof(Wasteful));
```

**Loop tiling for matrix operations:**

```cpp
// Bad: column-major access on row-major storage — cache thrashing
for (int j = 0; j < N; ++j)
    for (int i = 0; i < N; ++i)
        result[i][j] = a[i][j] + b[i][j]; // Stride-N access pattern

// Good: row-major access
for (int i = 0; i < N; ++i)
    for (int j = 0; j < N; ++j)
        result[i][j] = a[i][j] + b[i][j]; // Sequential access

// Better: tiled loop for large matrices
constexpr int TILE = 64;
for (int ii = 0; ii < N; ii += TILE)
    for (int jj = 0; jj < N; jj += TILE)
        for (int i = ii; i < std::min(ii + TILE, N); ++i)
            for (int j = jj; j < std::min(jj + TILE, N); ++j)
                result[i][j] = a[i][j] + b[i][j];
```

**Benchmarking cache effects:**

```cpp
void BM_Sequential(benchmark::State& state) {
    std::vector<int> v(state.range(0));
    std::iota(v.begin(), v.end(), 0);
    for (auto _ : state) {
        long sum = 0;
        for (int x : v) sum += x;
        benchmark::DoNotOptimize(sum);
    }
    state.SetBytesProcessed(state.iterations() * state.range(0) * sizeof(int));
}

void BM_Random(benchmark::State& state) {
    std::vector<int> v(state.range(0));
    std::vector<int> indices(v.size());
    std::iota(indices.begin(), indices.end(), 0);
    std::shuffle(indices.begin(), indices.end(), std::mt19937{42});
    for (auto _ : state) {
        long sum = 0;
        for (int idx : indices) sum += v[idx];
        benchmark::DoNotOptimize(sum);
    }
}
```

The performance hierarchy: L1 cache (~1ns) > L2 (~3ns) > L3 (~10ns) > RAM (~100ns). Organizing data for sequential access keeps it in L1/L2 and can mean 10-50x speedup on real workloads."""
    ),

    # =========================================================================
    # C++ — concepts_ranges (D3)
    # =========================================================================
    (
        "How do C++20 concepts and ranges work? Show me practical examples.",
        """Concepts replace SFINAE with readable, declarative type constraints. Ranges provide composable, lazy data processing pipelines.

**Defining and using concepts:**

```cpp
#include <concepts>
#include <iostream>
#include <vector>
#include <ranges>

// Define a concept
template<typename T>
concept Numeric = std::integral<T> || std::floating_point<T>;

template<typename T>
concept Printable = requires(T t) {
    { std::cout << t } -> std::same_as<std::ostream&>;
};

template<typename T>
concept Container = requires(T c) {
    { c.begin() } -> std::input_or_output_iterator;
    { c.end() } -> std::sentinel_for<decltype(c.begin())>;
    { c.size() } -> std::convertible_to<std::size_t>;
};

// Use concepts as constraints
template<Numeric T>
T average(const std::vector<T>& values) {
    T sum = std::accumulate(values.begin(), values.end(), T{});
    return sum / static_cast<T>(values.size());
}

// Shorthand syntax
void print(const Printable auto& value) {
    std::cout << value << "\\n";
}
```

**Better error messages** — the main benefit over SFINAE:

```cpp
// With SFINAE: 50 lines of template error vomit
// With concepts: "constraint 'Numeric<std::string>' not satisfied"

average(std::vector<std::string>{"a", "b"}); // Clear error!
```

**Ranges — composable data pipelines:**

```cpp
#include <ranges>
#include <algorithm>

std::vector<int> numbers = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

// Pipe syntax — filter, transform, take
auto result = numbers
    | std::views::filter([](int n) { return n % 2 == 0; })  // even only
    | std::views::transform([](int n) { return n * n; })     // square
    | std::views::take(3);                                    // first 3

for (int v : result) {
    std::cout << v << " "; // 4 16 36
}
```

**Ranges are lazy** — no intermediate collections created:

```cpp
// This doesn't allocate any memory or do any work yet
auto pipeline = numbers
    | std::views::filter([](int n) { return n > 5; })
    | std::views::transform([](int n) { return n * 2; });

// Work happens only when you iterate
for (int v : pipeline) {
    // Each element is filtered and transformed on-the-fly
}
```

**Range algorithms — replace iterator pairs:**

```cpp
// Old style
std::sort(vec.begin(), vec.end());

// Ranges style (C++20)
std::ranges::sort(vec);
std::ranges::sort(vec, std::greater<>{}); // Descending

// Projection — sort by member
struct Person { std::string name; int age; };
std::vector<Person> people = {{"Bob", 30}, {"Alice", 25}};
std::ranges::sort(people, {}, &Person::age); // Sort by age ascending
```

**Custom views:**

```cpp
// Enumerate (index + value)
for (auto [i, val] : numbers | std::views::enumerate) {
    std::cout << i << ": " << val << "\\n";
}

// Chunk into groups
for (auto chunk : numbers | std::views::chunk(3)) {
    // chunk is a subrange: {1,2,3}, {4,5,6}, {7,8,9}, {10}
}

// Zip multiple ranges together (C++23)
std::vector<std::string> names = {"Alice", "Bob", "Carol"};
std::vector<int> scores = {95, 87, 92};
for (auto [name, score] : std::views::zip(names, scores)) {
    std::cout << name << ": " << score << "\\n";
}
```

**Combining concepts with ranges:**

```cpp
template<std::ranges::input_range R>
    requires Numeric<std::ranges::range_value_t<R>>
auto sum(R&& range) {
    using T = std::ranges::range_value_t<R>;
    T total{};
    for (const auto& val : range) {
        total += val;
    }
    return total;
}

// Works with any range of numeric values
auto s1 = sum(std::vector{1, 2, 3});
auto s2 = sum(std::array{1.0, 2.0, 3.0});
auto s3 = sum(numbers | std::views::filter([](int n) { return n > 5; }));
```

Concepts and ranges together make C++ templates nearly as readable as dynamically-typed languages, while keeping zero-cost abstraction guarantees."""
    ),

    # =========================================================================
    # C++ — SFINAE/type_traits (D4)
    # =========================================================================
    (
        "Explain SFINAE and type traits in C++. How do I use them for compile-time dispatch?",
        """SFINAE (Substitution Failure Is Not An Error) allows the compiler to silently discard template overloads that don't match, rather than producing an error. Type traits query type properties at compile time.

**Type traits — compile-time type introspection:**

```cpp
#include <type_traits>

// Check properties
static_assert(std::is_integral_v<int>);
static_assert(std::is_floating_point_v<double>);
static_assert(std::is_pointer_v<int*>);
static_assert(std::is_same_v<int, int32_t>); // Platform-dependent

// Transform types
using Unsigned = std::make_unsigned_t<int>; // unsigned int
using NoRef = std::remove_reference_t<int&>; // int
using NoConst = std::remove_const_t<const int>; // int
using Decayed = std::decay_t<const int&>; // int
```

**enable_if — conditional function overloads:**

```cpp
// Only for integral types
template<typename T>
std::enable_if_t<std::is_integral_v<T>, T>
safeDivide(T a, T b) {
    if (b == 0) throw std::domain_error("division by zero");
    return a / b;
}

// Only for floating point types
template<typename T>
std::enable_if_t<std::is_floating_point_v<T>, T>
safeDivide(T a, T b) {
    if (std::abs(b) < std::numeric_limits<T>::epsilon())
        throw std::domain_error("division by near-zero");
    return a / b;
}
```

**Custom type traits:**

```cpp
// Check if type has a .serialize() method
template<typename T, typename = void>
struct has_serialize : std::false_type {};

template<typename T>
struct has_serialize<T, std::void_t<decltype(std::declval<T>().serialize())>>
    : std::true_type {};

template<typename T>
constexpr bool has_serialize_v = has_serialize<T>::value;

// Use it
struct Serializable {
    std::string serialize() const { return "data"; }
};
struct NotSerializable {};

static_assert(has_serialize_v<Serializable>);
static_assert(!has_serialize_v<NotSerializable>);
```

**Compile-time dispatch with if constexpr (C++17, preferred):**

```cpp
template<typename T>
std::string toString(const T& value) {
    if constexpr (std::is_arithmetic_v<T>) {
        return std::to_string(value);
    } else if constexpr (has_serialize_v<T>) {
        return value.serialize();
    } else if constexpr (std::is_convertible_v<T, std::string>) {
        return std::string(value);
    } else {
        static_assert(always_false<T>::value, "No conversion available");
    }
}

// Helper for static_assert in else branch
template<typename> struct always_false : std::false_type {};
```

**Tag dispatch — classic SFINAE alternative:**

```cpp
namespace detail {
    template<typename T>
    void process_impl(const T& val, std::true_type /* is_integral */) {
        std::cout << "Integer: " << val << "\\n";
    }

    template<typename T>
    void process_impl(const T& val, std::false_type /* is_integral */) {
        std::cout << "Non-integer: " << val << "\\n";
    }
}

template<typename T>
void process(const T& val) {
    detail::process_impl(val, std::is_integral<T>{});
}
```

**Conditional member types:**

```cpp
template<typename T>
class SmartBuffer {
    using StorageType = std::conditional_t<
        sizeof(T) <= 16,
        std::array<T, 64>,  // Small objects: stack-allocate
        std::vector<T>       // Large objects: heap-allocate
    >;

    StorageType storage_;
};
```

**The evolution of compile-time dispatch:**

| Era | Technique | Readability |
|-----|-----------|-------------|
| C++11 | `enable_if` + SFINAE | Poor |
| C++17 | `if constexpr` | Good |
| C++20 | Concepts + `requires` | Excellent |

Prefer concepts (C++20) > `if constexpr` (C++17) > `enable_if` (C++11). Use SFINAE only when targeting older standards or writing library code that needs maximum compatibility."""
    ),

    # =========================================================================
    # Additional Go pairs for depth
    # =========================================================================
    (
        "How do I structure a Go project with packages, and what are the module system best practices?",
        """Go modules (introduced in Go 1.11, default since 1.16) manage dependencies and define project boundaries.

**Project structure for a medium-sized service:**

```
myservice/
├── go.mod
├── go.sum
├── main.go              # Entry point
├── cmd/
│   └── worker/
│       └── main.go      # Secondary binary
├── internal/            # Private to this module
│   ├── handler/
│   │   ├── handler.go
│   │   └── handler_test.go
│   ├── service/
│   │   ├── user.go
│   │   └── user_test.go
│   └── store/
│       ├── postgres.go
│       └── postgres_test.go
├── pkg/                 # Public API (other modules can import)
│   └── client/
│       └── client.go
└── config/
    └── config.go
```

**Module initialization:**

```bash
mkdir myservice && cd myservice
go mod init github.com/yourname/myservice
```

**go.mod file:**

```
module github.com/yourname/myservice

go 1.22

require (
    github.com/lib/pq v1.10.9
    github.com/gorilla/mux v1.8.1
)
```

**Key conventions:**

1. **`internal/` is enforced by the compiler** — code in `internal/` can only be imported by code rooted at the parent of `internal/`. This prevents other modules from depending on your implementation details.

2. **One package per directory** — all `.go` files in a directory must have the same `package` declaration.

3. **Package names are lowercase, single-word** — `store`, not `dataStore` or `data_store`.

4. **Don't stutter** — `store.Store` is fine, `store.StoreService` stutters.

```go
// internal/store/postgres.go
package store

type UserStore struct {
    db *sql.DB
}

func NewUserStore(db *sql.DB) *UserStore {
    return &UserStore{db: db}
}

func (s *UserStore) GetByID(ctx context.Context, id string) (*User, error) {
    var u User
    err := s.db.QueryRowContext(ctx,
        "SELECT id, name, email FROM users WHERE id = $1", id,
    ).Scan(&u.ID, &u.Name, &u.Email)
    if errors.Is(err, sql.ErrNoRows) {
        return nil, fmt.Errorf("user %s: %w", id, ErrNotFound)
    }
    return &u, err
}
```

**Dependency management:**

```bash
go get github.com/lib/pq@latest    # Add or update dependency
go mod tidy                         # Remove unused dependencies
go mod vendor                       # Copy deps to vendor/ (for reproducible builds)
```

**Testing across packages:**

```bash
go test ./...                      # All packages
go test ./internal/store/...       # Specific package tree
go test -race -count=1 ./...       # With race detector, no caching
```

The key principle: design packages around what they **do** (store, handler, client), not what they **are** (models, utils, helpers). A `utils` package is a code smell in Go."""
    ),

    # =========================================================================
    # Additional C++ pair for depth
    # =========================================================================
    (
        "How do I implement a thread pool in C++? Show me a production-quality implementation.",
        """A thread pool manages a fixed set of worker threads that process tasks from a queue, amortizing thread creation cost.

```cpp
#include <vector>
#include <thread>
#include <queue>
#include <mutex>
#include <condition_variable>
#include <functional>
#include <future>
#include <stdexcept>

class ThreadPool {
    std::vector<std::thread> workers_;
    std::queue<std::function<void()>> tasks_;
    std::mutex mu_;
    std::condition_variable cv_;
    bool shutdown_ = false;

public:
    explicit ThreadPool(size_t numThreads) {
        for (size_t i = 0; i < numThreads; ++i) {
            workers_.emplace_back([this] {
                for (;;) {
                    std::function<void()> task;
                    {
                        std::unique_lock lock(mu_);
                        cv_.wait(lock, [this] {
                            return shutdown_ || !tasks_.empty();
                        });
                        if (shutdown_ && tasks_.empty()) return;
                        task = std::move(tasks_.front());
                        tasks_.pop();
                    }
                    task(); // Execute outside the lock
                }
            });
        }
    }

    ~ThreadPool() {
        {
            std::lock_guard lock(mu_);
            shutdown_ = true;
        }
        cv_.notify_all();
        for (auto& worker : workers_) {
            worker.join();
        }
    }

    // Submit a task and get a future for the result
    template<typename F, typename... Args>
    auto submit(F&& f, Args&&... args) -> std::future<std::invoke_result_t<F, Args...>> {
        using ReturnType = std::invoke_result_t<F, Args...>;

        auto task = std::make_shared<std::packaged_task<ReturnType()>>(
            std::bind(std::forward<F>(f), std::forward<Args>(args)...)
        );

        std::future<ReturnType> result = task->get_future();
        {
            std::lock_guard lock(mu_);
            if (shutdown_) throw std::runtime_error("submit on stopped pool");
            tasks_.emplace([task]() { (*task)(); });
        }
        cv_.notify_one();
        return result;
    }

    // Non-copyable, non-movable
    ThreadPool(const ThreadPool&) = delete;
    ThreadPool& operator=(const ThreadPool&) = delete;
};
```

**Usage:**

```cpp
int main() {
    ThreadPool pool(std::thread::hardware_concurrency());

    // Submit tasks and collect futures
    std::vector<std::future<int>> results;
    for (int i = 0; i < 100; ++i) {
        results.push_back(pool.submit([i] {
            // Simulate work
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            return i * i;
        }));
    }

    // Collect results
    int total = 0;
    for (auto& f : results) {
        total += f.get();
    }
    std::cout << "Sum of squares: " << total << "\\n";
}
```

**Testing the thread pool:**

```cpp
#include <cassert>
#include <atomic>

void testBasic() {
    ThreadPool pool(4);
    auto f = pool.submit([] { return 42; });
    assert(f.get() == 42);
}

void testConcurrency() {
    ThreadPool pool(4);
    std::atomic<int> counter{0};
    std::vector<std::future<void>> futures;

    for (int i = 0; i < 1000; ++i) {
        futures.push_back(pool.submit([&counter] {
            counter.fetch_add(1, std::memory_order_relaxed);
        }));
    }

    for (auto& f : futures) f.get();
    assert(counter.load() == 1000);
}

void testExceptionPropagation() {
    ThreadPool pool(2);
    auto f = pool.submit([] {
        throw std::runtime_error("test error");
        return 0;
    });

    try {
        f.get();
        assert(false); // Should not reach
    } catch (const std::runtime_error& e) {
        assert(std::string(e.what()) == "test error");
    }
}
```

**Design decisions:**
- **Fixed thread count**: Use `hardware_concurrency()` for CPU-bound work, 2-4x that for I/O-bound
- **Task type erasure via `std::function<void()>`**: Allows any callable, the `packaged_task` wrapper handles return values
- **Graceful shutdown**: Finish all queued tasks before destroying workers
- **Exception safety**: Exceptions in tasks are captured by `packaged_task` and rethrown on `future.get()`"""
    ),
]

# Explicit category and eval-topic mapping for each pair (by index).
# This avoids brittle string-matching and ties directly to eval challenges.
PAIR_META = [
    # Go pairs (indices 0-10)
    {"category": "go", "eval_topic": "goroutines_waitgroup", "difficulty": 2},
    {"category": "go", "eval_topic": "channels", "difficulty": 2},
    {"category": "go", "eval_topic": "select_statement", "difficulty": 3},
    {"category": "go", "eval_topic": "error_handling", "difficulty": 2},
    {"category": "go", "eval_topic": "interfaces", "difficulty": 3},
    {"category": "go", "eval_topic": "context_package", "difficulty": 3},
    {"category": "go", "eval_topic": "generics", "difficulty": 3},
    {"category": "go", "eval_topic": "http_servers", "difficulty": 2},
    {"category": "go", "eval_topic": "testing", "difficulty": 3},
    {"category": "go", "eval_topic": "race_conditions", "difficulty": 4},
    # C++ pairs (indices 10-21)
    {"category": "cpp", "eval_topic": "smart_pointers_raii", "difficulty": 2},
    {"category": "cpp", "eval_topic": "move_semantics", "difficulty": 3},
    {"category": "cpp", "eval_topic": "template_metaprogramming", "difficulty": 3},
    {"category": "cpp", "eval_topic": "containers_iterators", "difficulty": 2},
    {"category": "cpp", "eval_topic": "algorithms_lambdas", "difficulty": 2},
    {"category": "cpp", "eval_topic": "threads_mutex", "difficulty": 3},
    {"category": "cpp", "eval_topic": "async_futures", "difficulty": 4},
    {"category": "cpp", "eval_topic": "cache_friendly_data", "difficulty": 4},
    {"category": "cpp", "eval_topic": "concepts_ranges", "difficulty": 3},
    {"category": "cpp", "eval_topic": "sfinae_type_traits", "difficulty": 4},
    # Additional depth pairs
    {"category": "go", "eval_topic": "project_structure", "difficulty": 2},
    {"category": "cpp", "eval_topic": "thread_pool", "difficulty": 4},
]

assert len(PAIR_META) == len(PAIRS), f"Metadata count {len(PAIR_META)} != pair count {len(PAIRS)}"

with open(OUT, "w", encoding="utf-8") as f:
    for i, (prompt, response) in enumerate(PAIRS):
        meta = PAIR_META[i]
        obj = {
            "instruction": prompt,
            "input": "",
            "output": response.strip(),
            "metadata": {
                "source": "claude-handcrafted",
                "category": meta["category"],
                "eval_topic": meta["eval_topic"],
                "difficulty": meta["difficulty"],
                "version": "v8",
            },
        }
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

go_count = sum(1 for m in PAIR_META if m["category"] == "go")
cpp_count = sum(1 for m in PAIR_META if m["category"] == "cpp")
print(f"Wrote {len(PAIRS)} Go/C++ training pairs to {OUT}")
print(f"  Go:  {go_count} pairs (covering {go_count} eval topics)")
print(f"  C++: {cpp_count} pairs (covering {cpp_count} eval topics)")
