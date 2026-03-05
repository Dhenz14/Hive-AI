"""Go concurrency deep dive — worker pools, fan-out/fan-in, sync primitives, rate limiting, graceful shutdown."""

PAIRS = [
    (
        "go/worker-pool-pattern",
        "Show the Go worker pool pattern with bounded concurrency, job queues, and result collection.",
        '''Go worker pool pattern for bounded concurrent processing:

```go
// --- Generic worker pool ---

package workerpool

import (
    "context"
    "fmt"
    "sync"
    "time"
)

// Job represents a unit of work
type Job[T any, R any] struct {
    ID    int
    Input T
}

// Result represents the outcome of a job
type Result[R any] struct {
    JobID int
    Value R
    Err   error
    Duration time.Duration
}

// Pool manages a fixed number of workers processing jobs
type Pool[T any, R any] struct {
    workers   int
    jobs      chan Job[T, R]
    results   chan Result[R]
    processor func(context.Context, T) (R, error)
}

// NewPool creates a worker pool with the given concurrency
func NewPool[T any, R any](
    workers int,
    bufferSize int,
    processor func(context.Context, T) (R, error),
) *Pool[T, R] {
    return &Pool[T, R]{
        workers:   workers,
        jobs:      make(chan Job[T, R], bufferSize),
        results:   make(chan Result[R], bufferSize),
        processor: processor,
    }
}

// Start launches worker goroutines and returns when all jobs complete
func (p *Pool[T, R]) Start(ctx context.Context) {
    var wg sync.WaitGroup

    // Launch workers
    for i := 0; i < p.workers; i++ {
        wg.Add(1)
        go func(workerID int) {
            defer wg.Done()
            for job := range p.jobs {
                // Check context before processing
                if ctx.Err() != nil {
                    p.results <- Result[R]{
                        JobID: job.ID,
                        Err:   ctx.Err(),
                    }
                    continue
                }

                start := time.Now()
                value, err := p.processor(ctx, job.Input)
                p.results <- Result[R]{
                    JobID:    job.ID,
                    Value:    value,
                    Err:      err,
                    Duration: time.Since(start),
                }
            }
        }(i)
    }

    // Close results channel when all workers finish
    go func() {
        wg.Wait()
        close(p.results)
    }()
}

// Submit adds a job to the queue (blocks if buffer full)
func (p *Pool[T, R]) Submit(job Job[T, R]) {
    p.jobs <- job
}

// CloseJobs signals no more jobs will be submitted
func (p *Pool[T, R]) CloseJobs() {
    close(p.jobs)
}

// Results returns the results channel for reading
func (p *Pool[T, R]) Results() <-chan Result[R] {
    return p.results
}
```

```go
// --- Using the worker pool ---

package main

import (
    "context"
    "fmt"
    "math/rand"
    "net/http"
    "time"

    "myapp/workerpool"
)

// FetchResult holds the outcome of an HTTP fetch
type FetchResult struct {
    URL        string
    StatusCode int
    Size       int
}

func fetchURL(ctx context.Context, url string) (FetchResult, error) {
    req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
    if err != nil {
        return FetchResult{}, fmt.Errorf("create request: %w", err)
    }

    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return FetchResult{}, fmt.Errorf("fetch %s: %w", url, err)
    }
    defer resp.Body.Close()

    return FetchResult{
        URL:        url,
        StatusCode: resp.StatusCode,
        Size:       int(resp.ContentLength),
    }, nil
}

func main() {
    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()

    urls := []string{
        "https://example.com",
        "https://httpbin.org/get",
        "https://httpbin.org/delay/1",
        "https://httpbin.org/status/404",
        "https://httpbin.org/status/500",
    }

    // Create pool with 3 workers
    pool := workerpool.NewPool[string, FetchResult](3, len(urls), fetchURL)
    pool.Start(ctx)

    // Submit jobs
    for i, url := range urls {
        pool.Submit(workerpool.Job[string, FetchResult]{
            ID:    i,
            Input: url,
        })
    }
    pool.CloseJobs()

    // Collect results
    var succeeded, failed int
    for result := range pool.Results() {
        if result.Err != nil {
            fmt.Printf("Job %d FAILED: %v (took %v)\\n",
                result.JobID, result.Err, result.Duration)
            failed++
        } else {
            fmt.Printf("Job %d OK: %s -> %d (took %v)\\n",
                result.JobID, result.Value.URL,
                result.Value.StatusCode, result.Duration)
            succeeded++
        }
    }
    fmt.Printf("\\nCompleted: %d succeeded, %d failed\\n", succeeded, failed)
}
```

```go
// --- Semaphore-based bounded concurrency (alternative) ---

package main

import (
    "context"
    "fmt"
    "sync"

    "golang.org/x/sync/semaphore"
)

// BoundedProcess limits concurrent goroutines using a semaphore
func BoundedProcess[T any, R any](
    ctx context.Context,
    items []T,
    maxConcurrency int64,
    process func(context.Context, T) (R, error),
) ([]R, []error) {
    sem := semaphore.NewWeighted(maxConcurrency)
    var mu sync.Mutex
    results := make([]R, len(items))
    errs := make([]error, len(items))

    var wg sync.WaitGroup
    for i, item := range items {
        if err := sem.Acquire(ctx, 1); err != nil {
            errs[i] = err
            continue
        }

        wg.Add(1)
        go func(idx int, input T) {
            defer wg.Done()
            defer sem.Release(1)

            result, err := process(ctx, input)
            mu.Lock()
            results[idx] = result
            errs[idx] = err
            mu.Unlock()
        }(i, item)
    }

    wg.Wait()
    return results, errs
}

// errgroup alternative (recommended for most use cases)
// import "golang.org/x/sync/errgroup"
func ProcessWithErrGroup[T any](
    ctx context.Context,
    items []T,
    maxConcurrency int,
    process func(context.Context, T) error,
) error {
    g, ctx := errgroup.WithContext(ctx)
    g.SetLimit(maxConcurrency)

    for _, item := range items {
        item := item // Capture for goroutine
        g.Go(func() error {
            return process(ctx, item)
        })
    }

    return g.Wait() // Returns first error, cancels rest
}
```

Worker pool pattern comparison:

| Approach | Best For | Cancellation | Error Handling |
|----------|----------|-------------|----------------|
| Channel-based pool | Custom job/result types | Via context | Per-job errors |
| `errgroup` + `SetLimit` | Simple bounded work | Auto-cancel on first error | First error wins |
| `semaphore.Weighted` | Fine-grained concurrency | Via `Acquire(ctx)` | Per-item errors |
| Unbounded goroutines | Small, known input size | Manual | Manual collection |

Key patterns:
1. Always bound concurrency — unbounded goroutines can exhaust memory and file descriptors
2. Use buffered channels for job/result queues to prevent producer/consumer blocking
3. Close the jobs channel from the submitter side to signal workers that no more work is coming
4. Use `errgroup.SetLimit()` for the simplest bounded concurrency with automatic cancellation
5. Pre-check `ctx.Err()` inside workers to avoid wasted work after cancellation
6. The generic `Pool[T, R]` eliminates type assertions and provides compile-time safety'''
    ),
    (
        "go/fan-out-fan-in",
        "Demonstrate Go fan-out/fan-in patterns with goroutines, including pipeline stages and result aggregation.",
        '''Go fan-out/fan-in for parallel pipeline processing:

```go
// --- Fan-out/fan-in pipeline ---

package pipeline

import (
    "context"
    "fmt"
    "sync"
)

// Stage represents a pipeline processing stage
type Stage[In any, Out any] func(ctx context.Context, in In) (Out, error)

// FanOut distributes input across N workers processing in parallel
func FanOut[In any, Out any](
    ctx context.Context,
    input <-chan In,
    workers int,
    stage Stage[In, Out],
) []<-chan Result[Out] {
    channels := make([]<-chan Result[Out], workers)

    for i := 0; i < workers; i++ {
        ch := make(chan Result[Out])
        channels[i] = ch

        go func(out chan<- Result[Out]) {
            defer close(out)
            for item := range input {
                select {
                case <-ctx.Done():
                    return
                default:
                    val, err := stage(ctx, item)
                    out <- Result[Out]{Value: val, Err: err}
                }
            }
        }(ch)
    }

    return channels
}

// FanIn merges multiple channels into a single output channel
func FanIn[T any](ctx context.Context, channels ...<-chan T) <-chan T {
    out := make(chan T)
    var wg sync.WaitGroup

    wg.Add(len(channels))
    for _, ch := range channels {
        go func(c <-chan T) {
            defer wg.Done()
            for val := range c {
                select {
                case out <- val:
                case <-ctx.Done():
                    return
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

type Result[T any] struct {
    Value T
    Err   error
}

// Generator creates a channel from a slice
func Generator[T any](ctx context.Context, items ...T) <-chan T {
    out := make(chan T)
    go func() {
        defer close(out)
        for _, item := range items {
            select {
            case out <- item:
            case <-ctx.Done():
                return
            }
        }
    }()
    return out
}
```

```go
// --- Real-world fan-out/fan-in: image processing pipeline ---

package main

import (
    "context"
    "crypto/sha256"
    "fmt"
    "io"
    "net/http"
    "sync"
    "time"

    "myapp/pipeline"
)

type ImageJob struct {
    URL      string
    OutputID string
}

type ProcessedImage struct {
    ID       string
    Hash     string
    Size     int
    Duration time.Duration
}

// Stage 1: Download images (I/O bound — more workers)
func downloadImage(ctx context.Context, job ImageJob) ([]byte, error) {
    req, err := http.NewRequestWithContext(ctx, "GET", job.URL, nil)
    if err != nil {
        return nil, err
    }
    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return nil, fmt.Errorf("download %s: %w", job.URL, err)
    }
    defer resp.Body.Close()
    return io.ReadAll(resp.Body)
}

// Stage 2: Process images (CPU bound — fewer workers)
func processImage(ctx context.Context, data []byte) (ProcessedImage, error) {
    start := time.Now()
    hash := sha256.Sum256(data)
    // Simulate CPU-intensive processing
    return ProcessedImage{
        Hash:     fmt.Sprintf("%x", hash[:8]),
        Size:     len(data),
        Duration: time.Since(start),
    }, nil
}

func main() {
    ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
    defer cancel()

    jobs := []ImageJob{
        {URL: "https://picsum.photos/200", OutputID: "img-1"},
        {URL: "https://picsum.photos/300", OutputID: "img-2"},
        {URL: "https://picsum.photos/400", OutputID: "img-3"},
        {URL: "https://picsum.photos/500", OutputID: "img-4"},
    }

    // Stage 1: Fan-out downloads across 4 workers (I/O bound)
    jobCh := pipeline.Generator(ctx, jobs...)
    downloadResults := pipeline.FanOut(ctx, jobCh, 4,
        func(ctx context.Context, job ImageJob) ([]byte, error) {
            return downloadImage(ctx, job)
        },
    )

    // Merge download results
    merged := pipeline.FanIn(ctx, downloadResults...)

    // Stage 2: Fan-out processing across 2 workers (CPU bound)
    dataCh := make(chan []byte, len(jobs))
    go func() {
        defer close(dataCh)
        for result := range merged {
            if result.Err == nil {
                dataCh <- result.Value
            } else {
                fmt.Printf("Download error: %v\\n", result.Err)
            }
        }
    }()

    processResults := pipeline.FanOut(ctx, dataCh, 2,
        func(ctx context.Context, data []byte) (ProcessedImage, error) {
            return processImage(ctx, data)
        },
    )

    // Collect final results
    finalResults := pipeline.FanIn(ctx, processResults...)
    for result := range finalResults {
        if result.Err != nil {
            fmt.Printf("Process error: %v\\n", result.Err)
        } else {
            fmt.Printf("Processed: hash=%s size=%d took=%v\\n",
                result.Value.Hash, result.Value.Size, result.Value.Duration)
        }
    }
}
```

```go
// --- Map-reduce style fan-out/fan-in ---

package mapreduce

import (
    "context"
    "sync"
)

// MapReduce applies a map function in parallel, then reduces results
func MapReduce[T any, M any, R any](
    ctx context.Context,
    items []T,
    workers int,
    mapper func(context.Context, T) (M, error),
    reducer func(R, M) R,
    initial R,
) (R, error) {
    // Fan-out: map phase
    type mapResult struct {
        value M
        err   error
    }

    results := make(chan mapResult, len(items))
    sem := make(chan struct{}, workers) // Limit concurrency

    var wg sync.WaitGroup
    for _, item := range items {
        wg.Add(1)
        sem <- struct{}{} // Acquire slot

        go func(input T) {
            defer wg.Done()
            defer func() { <-sem }() // Release slot

            val, err := mapper(ctx, input)
            results <- mapResult{value: val, err: err}
        }(item)
    }

    go func() {
        wg.Wait()
        close(results)
    }()

    // Fan-in: reduce phase (sequential)
    acc := initial
    for result := range results {
        if result.err != nil {
            return acc, result.err
        }
        acc = reducer(acc, result.value)
    }
    return acc, nil
}

// Usage example: count words across multiple files
// totalWords, err := MapReduce(ctx, filePaths, 4,
//     func(ctx context.Context, path string) (int, error) {
//         data, err := os.ReadFile(path)
//         if err != nil { return 0, err }
//         return len(strings.Fields(string(data))), nil
//     },
//     func(total int, count int) int { return total + count },
//     0,
// )
```

Fan-out/fan-in pattern comparison:

| Pattern | Fan-Out | Fan-In | Ordering | Use Case |
|---------|---------|--------|----------|----------|
| Channel fan-out | N goroutines reading shared channel | `sync.WaitGroup` + merge | Unordered | Pipeline stages |
| Dedicated channels | One goroutine per channel | Select or merge | Unordered | Independent sources |
| MapReduce | Parallel map | Sequential reduce | Unordered | Aggregation |
| Indexed results | Goroutines write to `results[i]` | `sync.WaitGroup` | Ordered | When order matters |

Key patterns:
1. Fan-out scales workers to match the bottleneck: more workers for I/O-bound stages, fewer for CPU-bound
2. Fan-in uses a `sync.WaitGroup` to know when all producers are done, then closes the output channel
3. Always select on `ctx.Done()` inside fan-out workers to support cancellation
4. Use buffered channels between stages to prevent backpressure from stalling the pipeline
5. MapReduce combines fan-out mapping with sequential reduction for aggregation tasks
6. For ordered results, use an indexed slice with a mutex instead of channels'''
    ),
    (
        "go/sync-primitives",
        "Explain Go sync primitives: Mutex, RWMutex, Once, Pool, WaitGroup, and Cond with practical examples.",
        '''Go sync primitives for safe concurrent access:

```go
// --- Mutex and RWMutex ---

package cache

import (
    "sync"
    "time"
)

// Thread-safe cache with RWMutex (multiple readers, exclusive writer)
type Cache[K comparable, V any] struct {
    mu    sync.RWMutex
    items map[K]cacheItem[V]
    ttl   time.Duration
}

type cacheItem[V any] struct {
    value     V
    expiresAt time.Time
}

func NewCache[K comparable, V any](ttl time.Duration) *Cache[K, V] {
    c := &Cache[K, V]{
        items: make(map[K]cacheItem[V]),
        ttl:   ttl,
    }
    go c.evictLoop()
    return c
}

// Get uses RLock — multiple goroutines can read simultaneously
func (c *Cache[K, V]) Get(key K) (V, bool) {
    c.mu.RLock()
    defer c.mu.RUnlock()

    item, ok := c.items[key]
    if !ok || time.Now().After(item.expiresAt) {
        var zero V
        return zero, false
    }
    return item.value, true
}

// Set uses Lock — exclusive access, blocks all readers and writers
func (c *Cache[K, V]) Set(key K, value V) {
    c.mu.Lock()
    defer c.mu.Unlock()

    c.items[key] = cacheItem[V]{
        value:     value,
        expiresAt: time.Now().Add(c.ttl),
    }
}

// GetOrSet atomically checks and sets (requires write lock)
func (c *Cache[K, V]) GetOrSet(key K, fn func() V) V {
    // Try read first (common path)
    c.mu.RLock()
    if item, ok := c.items[key]; ok && time.Now().Before(item.expiresAt) {
        c.mu.RUnlock()
        return item.value
    }
    c.mu.RUnlock()

    // Upgrade to write lock (must release read lock first — no upgrade)
    c.mu.Lock()
    defer c.mu.Unlock()

    // Double-check after acquiring write lock
    if item, ok := c.items[key]; ok && time.Now().Before(item.expiresAt) {
        return item.value
    }

    value := fn()
    c.items[key] = cacheItem[V]{
        value:     value,
        expiresAt: time.Now().Add(c.ttl),
    }
    return value
}

func (c *Cache[K, V]) Delete(key K) {
    c.mu.Lock()
    defer c.mu.Unlock()
    delete(c.items, key)
}

func (c *Cache[K, V]) evictLoop() {
    ticker := time.NewTicker(1 * time.Minute)
    defer ticker.Stop()
    for range ticker.C {
        c.mu.Lock()
        now := time.Now()
        for key, item := range c.items {
            if now.After(item.expiresAt) {
                delete(c.items, key)
            }
        }
        c.mu.Unlock()
    }
}
```

```go
// --- sync.Once, sync.Pool, sync.WaitGroup ---

package main

import (
    "bytes"
    "database/sql"
    "fmt"
    "sync"
)

// sync.Once — lazy initialization (thread-safe singleton)
type DBConn struct {
    once sync.Once
    db   *sql.DB
    err  error
}

func (c *DBConn) Get() (*sql.DB, error) {
    c.once.Do(func() {
        c.db, c.err = sql.Open("postgres", "postgres://localhost/mydb")
        if c.err == nil {
            c.db.SetMaxOpenConns(25)
            c.db.SetMaxIdleConns(5)
        }
    })
    return c.db, c.err
}

// sync.Pool — reusable object pool to reduce GC pressure
var bufferPool = sync.Pool{
    New: func() any {
        return bytes.NewBuffer(make([]byte, 0, 4096))
    },
}

func processRequest(data []byte) string {
    // Get buffer from pool (or create new one)
    buf := bufferPool.Get().(*bytes.Buffer)
    defer func() {
        buf.Reset() // Clear before returning to pool
        bufferPool.Put(buf)
    }()

    buf.Write(data)
    buf.WriteString(" processed")
    return buf.String()
}

// sync.WaitGroup — wait for N goroutines to complete
func fetchAll(urls []string) []string {
    var wg sync.WaitGroup
    results := make([]string, len(urls))

    for i, url := range urls {
        wg.Add(1)
        go func(idx int, u string) {
            defer wg.Done()
            results[idx] = fmt.Sprintf("fetched: %s", u)
        }(i, url)
    }

    wg.Wait() // Block until all goroutines call Done()
    return results
}

// sync.Map — concurrent map (use when keys are stable)
// Prefer sync.RWMutex + map for most cases
func demonstrateSyncMap() {
    var m sync.Map

    // Store
    m.Store("key1", "value1")
    m.Store("key2", "value2")

    // Load
    if val, ok := m.Load("key1"); ok {
        fmt.Println(val.(string))
    }

    // LoadOrStore — atomic get-or-set
    actual, loaded := m.LoadOrStore("key3", "value3")
    fmt.Printf("value=%v existed=%v\\n", actual, loaded)

    // LoadAndDelete — atomic get-and-remove
    val, loaded := m.LoadAndDelete("key2")
    fmt.Printf("deleted=%v existed=%v\\n", val, loaded)

    // Range — iterate (not snapshot-safe)
    m.Range(func(key, value any) bool {
        fmt.Printf("%v: %v\\n", key, value)
        return true // Continue iteration
    })
}
```

```go
// --- sync.Cond and advanced synchronization ---

package main

import (
    "fmt"
    "sync"
    "time"
)

// Bounded queue using sync.Cond for producer/consumer coordination
type BoundedQueue[T any] struct {
    mu       sync.Mutex
    notEmpty *sync.Cond
    notFull  *sync.Cond
    items    []T
    capacity int
}

func NewBoundedQueue[T any](capacity int) *BoundedQueue[T] {
    q := &BoundedQueue[T]{
        items:    make([]T, 0, capacity),
        capacity: capacity,
    }
    q.notEmpty = sync.NewCond(&q.mu)
    q.notFull = sync.NewCond(&q.mu)
    return q
}

// Enqueue blocks if queue is full
func (q *BoundedQueue[T]) Enqueue(item T) {
    q.mu.Lock()
    defer q.mu.Unlock()

    for len(q.items) >= q.capacity {
        q.notFull.Wait() // Release lock and wait
    }

    q.items = append(q.items, item)
    q.notEmpty.Signal() // Wake one waiting consumer
}

// Dequeue blocks if queue is empty
func (q *BoundedQueue[T]) Dequeue() T {
    q.mu.Lock()
    defer q.mu.Unlock()

    for len(q.items) == 0 {
        q.notEmpty.Wait() // Release lock and wait
    }

    item := q.items[0]
    q.items = q.items[1:]
    q.notFull.Signal() // Wake one waiting producer
    return item
}

func (q *BoundedQueue[T]) Len() int {
    q.mu.Lock()
    defer q.mu.Unlock()
    return len(q.items)
}

// OnceValue (Go 1.21+) — sync.Once that returns a value
// var getConfig = sync.OnceValue(func() *Config {
//     cfg, _ := loadConfigFromFile("config.yaml")
//     return cfg
// })
// var getDBPool = sync.OnceValues(func() (*sql.DB, error) {
//     return sql.Open("postgres", os.Getenv("DATABASE_URL"))
// })

func main() {
    q := NewBoundedQueue[int](5)

    // Producer
    go func() {
        for i := 0; i < 20; i++ {
            q.Enqueue(i)
            fmt.Printf("Produced: %d (qlen=%d)\\n", i, q.Len())
        }
    }()

    // Consumer (slower)
    for i := 0; i < 20; i++ {
        time.Sleep(100 * time.Millisecond)
        val := q.Dequeue()
        fmt.Printf("Consumed: %d\\n", val)
    }
}
```

Sync primitive comparison:

| Primitive | Purpose | When to Use |
|-----------|---------|------------|
| `sync.Mutex` | Exclusive lock | Protecting shared mutable state |
| `sync.RWMutex` | Reader-writer lock | Read-heavy workloads (many readers, few writers) |
| `sync.Once` | Run exactly once | Singleton init, lazy loading |
| `sync.OnceValue` | Once + return value | Config loading, DB pool init (Go 1.21+) |
| `sync.Pool` | Object reuse pool | Reducing GC pressure (buffers, temp objects) |
| `sync.WaitGroup` | Wait for N goroutines | Parallel tasks with completion barrier |
| `sync.Map` | Concurrent map | Append-only or stable-key maps |
| `sync.Cond` | Condition variable | Complex wait/signal patterns |
| `atomic` package | Lock-free operations | Counters, flags, CAS loops |

Key patterns:
1. Prefer `sync.RWMutex` over `sync.Mutex` when reads far outnumber writes (>10:1 ratio)
2. Go does not support lock upgrades — release `RLock` before acquiring `Lock`, then double-check
3. `sync.Pool` objects may be garbage collected between GC cycles — never store state you cannot recreate
4. Always call `buf.Reset()` before returning buffers to `sync.Pool`
5. Use `sync.Once` for lazy initialization — it is safe even if `Do` panics (subsequent calls return immediately)
6. Prefer channels over `sync.Cond` unless you need broadcast (`Broadcast()`) or complex wait conditions'''
    ),
    (
        "go/rate-limiting",
        "Show Go rate limiting patterns including token bucket, sliding window, and per-client rate limiting.",
        '''Go rate limiting with token bucket, sliding window, and per-client limiting:

```go
// --- Token bucket rate limiter ---

package ratelimit

import (
    "context"
    "sync"
    "time"
)

// TokenBucket allows bursts up to capacity, then refills at a steady rate
type TokenBucket struct {
    mu         sync.Mutex
    tokens     float64
    capacity   float64
    refillRate float64 // Tokens per second
    lastRefill time.Time
}

func NewTokenBucket(capacity float64, refillRate float64) *TokenBucket {
    return &TokenBucket{
        tokens:     capacity, // Start full
        capacity:   capacity,
        refillRate: refillRate,
        lastRefill: time.Now(),
    }
}

func (tb *TokenBucket) refill() {
    now := time.Now()
    elapsed := now.Sub(tb.lastRefill).Seconds()
    tb.tokens += elapsed * tb.refillRate
    if tb.tokens > tb.capacity {
        tb.tokens = tb.capacity
    }
    tb.lastRefill = now
}

// Allow checks if a request is permitted (non-blocking)
func (tb *TokenBucket) Allow() bool {
    tb.mu.Lock()
    defer tb.mu.Unlock()

    tb.refill()
    if tb.tokens >= 1.0 {
        tb.tokens -= 1.0
        return true
    }
    return false
}

// AllowN checks if N tokens are available
func (tb *TokenBucket) AllowN(n float64) bool {
    tb.mu.Lock()
    defer tb.mu.Unlock()

    tb.refill()
    if tb.tokens >= n {
        tb.tokens -= n
        return true
    }
    return false
}

// Wait blocks until a token is available or context expires
func (tb *TokenBucket) Wait(ctx context.Context) error {
    for {
        if tb.Allow() {
            return nil
        }
        // Calculate wait time for next token
        tb.mu.Lock()
        deficit := 1.0 - tb.tokens
        waitTime := time.Duration(deficit/tb.refillRate*1000) * time.Millisecond
        tb.mu.Unlock()

        select {
        case <-ctx.Done():
            return ctx.Err()
        case <-time.After(waitTime):
            // Try again
        }
    }
}
```

```go
// --- Sliding window rate limiter ---

package ratelimit

import (
    "sync"
    "time"
)

// SlidingWindow tracks request counts in a rolling time window
type SlidingWindow struct {
    mu          sync.Mutex
    limit       int
    window      time.Duration
    timestamps  []time.Time
}

func NewSlidingWindow(limit int, window time.Duration) *SlidingWindow {
    return &SlidingWindow{
        limit:  limit,
        window: window,
    }
}

func (sw *SlidingWindow) Allow() bool {
    sw.mu.Lock()
    defer sw.mu.Unlock()

    now := time.Now()
    cutoff := now.Add(-sw.window)

    // Remove expired timestamps (slide window forward)
    valid := 0
    for _, ts := range sw.timestamps {
        if ts.After(cutoff) {
            sw.timestamps[valid] = ts
            valid++
        }
    }
    sw.timestamps = sw.timestamps[:valid]

    if len(sw.timestamps) >= sw.limit {
        return false
    }

    sw.timestamps = append(sw.timestamps, now)
    return true
}

func (sw *SlidingWindow) Remaining() int {
    sw.mu.Lock()
    defer sw.mu.Unlock()

    now := time.Now()
    cutoff := now.Add(-sw.window)
    count := 0
    for _, ts := range sw.timestamps {
        if ts.After(cutoff) {
            count++
        }
    }
    return sw.limit - count
}

// RetryAfter returns the duration until the next request is allowed
func (sw *SlidingWindow) RetryAfter() time.Duration {
    sw.mu.Lock()
    defer sw.mu.Unlock()

    if len(sw.timestamps) < sw.limit {
        return 0
    }

    oldest := sw.timestamps[0]
    return sw.window - time.Since(oldest)
}
```

```go
// --- Per-client rate limiter with cleanup ---

package ratelimit

import (
    "net/http"
    "sync"
    "time"
)

// PerClientLimiter maintains a separate rate limiter per client key
type PerClientLimiter struct {
    mu       sync.RWMutex
    clients  map[string]*clientEntry
    limit    int
    window   time.Duration
    cleanupInterval time.Duration
}

type clientEntry struct {
    limiter  *SlidingWindow
    lastSeen time.Time
}

func NewPerClientLimiter(limit int, window time.Duration) *PerClientLimiter {
    pcl := &PerClientLimiter{
        clients:         make(map[string]*clientEntry),
        limit:           limit,
        window:          window,
        cleanupInterval: 5 * time.Minute,
    }
    go pcl.cleanup()
    return pcl
}

func (pcl *PerClientLimiter) Allow(clientKey string) bool {
    pcl.mu.RLock()
    entry, exists := pcl.clients[clientKey]
    pcl.mu.RUnlock()

    if !exists {
        pcl.mu.Lock()
        // Double-check after acquiring write lock
        entry, exists = pcl.clients[clientKey]
        if !exists {
            entry = &clientEntry{
                limiter: NewSlidingWindow(pcl.limit, pcl.window),
            }
            pcl.clients[clientKey] = entry
        }
        pcl.mu.Unlock()
    }

    entry.lastSeen = time.Now()
    return entry.limiter.Allow()
}

func (pcl *PerClientLimiter) RetryAfter(clientKey string) time.Duration {
    pcl.mu.RLock()
    defer pcl.mu.RUnlock()

    if entry, ok := pcl.clients[clientKey]; ok {
        return entry.limiter.RetryAfter()
    }
    return 0
}

func (pcl *PerClientLimiter) cleanup() {
    ticker := time.NewTicker(pcl.cleanupInterval)
    defer ticker.Stop()

    for range ticker.C {
        pcl.mu.Lock()
        cutoff := time.Now().Add(-pcl.cleanupInterval * 2)
        for key, entry := range pcl.clients {
            if entry.lastSeen.Before(cutoff) {
                delete(pcl.clients, key)
            }
        }
        pcl.mu.Unlock()
    }
}

// HTTP middleware using per-client rate limiting
func RateLimitMiddleware(limiter *PerClientLimiter) func(http.Handler) http.Handler {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            // Use IP as client key (or API key from header)
            clientKey := r.Header.Get("X-API-Key")
            if clientKey == "" {
                clientKey = r.RemoteAddr
            }

            if !limiter.Allow(clientKey) {
                retryAfter := limiter.RetryAfter(clientKey)
                w.Header().Set("Retry-After",
                    fmt.Sprintf("%d", int(retryAfter.Seconds())))
                w.Header().Set("X-RateLimit-Limit",
                    fmt.Sprintf("%d", limiter.limit))
                w.Header().Set("X-RateLimit-Remaining", "0")
                http.Error(w, "Rate limit exceeded", http.StatusTooManyRequests)
                return
            }

            next.ServeHTTP(w, r)
        })
    }
}
```

```go
// --- Using stdlib golang.org/x/time/rate ---

package main

import (
    "context"
    "fmt"
    "time"

    "golang.org/x/time/rate"
)

func main() {
    // rate.NewLimiter(rate, burst)
    // rate = tokens per second, burst = max tokens at once
    limiter := rate.NewLimiter(10, 30) // 10 req/s, burst of 30

    // Non-blocking check
    if limiter.Allow() {
        fmt.Println("Request allowed")
    }

    // Blocking wait
    ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()

    if err := limiter.Wait(ctx); err != nil {
        fmt.Printf("Rate limited: %v\\n", err)
    }

    // Reserve a token for future use
    reservation := limiter.Reserve()
    if !reservation.OK() {
        fmt.Println("Cannot reserve")
    }
    delay := reservation.Delay()
    fmt.Printf("Wait %v before sending\\n", delay)
    time.Sleep(delay)

    // Dynamic rate adjustment
    limiter.SetLimit(rate.Limit(20))  // Change to 20 req/s
    limiter.SetBurst(50)              // Change burst to 50
}
```

Rate limiting algorithm comparison:

| Algorithm | Burst Handling | Memory | Precision | Best For |
|-----------|---------------|--------|-----------|----------|
| Token bucket | Allows bursts up to capacity | O(1) | Approximate | API rate limiting |
| Sliding window | Smooth limiting | O(n) per window | Exact count | Strict quotas |
| Fixed window | Allows 2x burst at boundary | O(1) | Per-window | Simple counting |
| Leaky bucket | Smooths output rate | O(queue size) | Exact rate | Traffic shaping |
| `x/time/rate` | Configurable burst | O(1) | Token bucket | Production Go apps |

Key patterns:
1. Use `golang.org/x/time/rate` for production — it implements an efficient token bucket with `Allow`, `Wait`, and `Reserve`
2. Per-client limiting requires a map of limiters — always include cleanup to prevent memory leaks
3. Set `Retry-After` and `X-RateLimit-*` headers in 429 responses for client backoff
4. Token bucket is best for APIs (allows bursts), sliding window for strict quotas
5. Use `limiter.Wait(ctx)` for client-side rate limiting (e.g., API client respecting server limits)
6. Dynamic rate adjustment with `SetLimit`/`SetBurst` enables adaptive throttling based on system load'''
    ),
    (
        "go/graceful-shutdown",
        "Show Go graceful shutdown patterns for HTTP servers, background workers, and multi-component applications.",
        '''Go graceful shutdown for production multi-component applications:

```go
// --- Graceful shutdown orchestrator ---

package shutdown

import (
    "context"
    "fmt"
    "log/slog"
    "os"
    "os/signal"
    "sync"
    "syscall"
    "time"
)

// Component represents a stoppable application component
type Component interface {
    Name() string
    Start(ctx context.Context) error
    Stop(ctx context.Context) error
}

// Manager orchestrates startup and graceful shutdown of all components
type Manager struct {
    logger     *slog.Logger
    components []Component
    timeout    time.Duration
}

func NewManager(logger *slog.Logger, timeout time.Duration) *Manager {
    return &Manager{
        logger:  logger,
        timeout: timeout,
    }
}

func (m *Manager) Register(c Component) {
    m.components = append(m.components, c)
}

// Run starts all components and blocks until shutdown signal
func (m *Manager) Run(ctx context.Context) error {
    // Create root context that cancels on SIGINT/SIGTERM
    ctx, stop := signal.NotifyContext(ctx, os.Interrupt, syscall.SIGTERM)
    defer stop()

    // Start all components
    errCh := make(chan error, len(m.components))
    for _, comp := range m.components {
        comp := comp
        go func() {
            m.logger.Info("Starting component", slog.String("name", comp.Name()))
            if err := comp.Start(ctx); err != nil {
                errCh <- fmt.Errorf("component %s: %w", comp.Name(), err)
            }
        }()
    }

    // Wait for signal or component error
    select {
    case <-ctx.Done():
        m.logger.Info("Shutdown signal received")
    case err := <-errCh:
        m.logger.Error("Component failed", slog.Any("error", err))
    }

    // Graceful shutdown with timeout
    return m.shutdown()
}

func (m *Manager) shutdown() error {
    shutdownCtx, cancel := context.WithTimeout(context.Background(), m.timeout)
    defer cancel()

    m.logger.Info("Starting graceful shutdown",
        slog.Duration("timeout", m.timeout),
        slog.Int("components", len(m.components)),
    )

    // Stop components in reverse order (LIFO)
    var firstErr error
    for i := len(m.components) - 1; i >= 0; i-- {
        comp := m.components[i]
        m.logger.Info("Stopping component", slog.String("name", comp.Name()))

        if err := comp.Stop(shutdownCtx); err != nil {
            m.logger.Error("Component stop failed",
                slog.String("name", comp.Name()),
                slog.Any("error", err),
            )
            if firstErr == nil {
                firstErr = err
            }
        } else {
            m.logger.Info("Component stopped", slog.String("name", comp.Name()))
        }
    }

    return firstErr
}
```

```go
// --- Concrete components ---

package main

import (
    "context"
    "database/sql"
    "fmt"
    "log/slog"
    "net/http"
    "time"

    "myapp/shutdown"
)

// HTTPServer component
type HTTPServer struct {
    server *http.Server
}

func NewHTTPServer(addr string, handler http.Handler) *HTTPServer {
    return &HTTPServer{
        server: &http.Server{
            Addr:         addr,
            Handler:      handler,
            ReadTimeout:  15 * time.Second,
            WriteTimeout: 15 * time.Second,
            IdleTimeout:  60 * time.Second,
        },
    }
}

func (s *HTTPServer) Name() string { return "http-server" }

func (s *HTTPServer) Start(ctx context.Context) error {
    errCh := make(chan error, 1)
    go func() {
        if err := s.server.ListenAndServe(); err != http.ErrServerClosed {
            errCh <- err
        }
        close(errCh)
    }()

    select {
    case err := <-errCh:
        return err
    case <-ctx.Done():
        return nil
    }
}

func (s *HTTPServer) Stop(ctx context.Context) error {
    return s.server.Shutdown(ctx) // Drains in-flight requests
}

// BackgroundWorker component
type BackgroundWorker struct {
    name     string
    interval time.Duration
    task     func(context.Context) error
    done     chan struct{}
}

func NewBackgroundWorker(name string, interval time.Duration, task func(context.Context) error) *BackgroundWorker {
    return &BackgroundWorker{
        name:     name,
        interval: interval,
        task:     task,
        done:     make(chan struct{}),
    }
}

func (w *BackgroundWorker) Name() string { return w.name }

func (w *BackgroundWorker) Start(ctx context.Context) error {
    ticker := time.NewTicker(w.interval)
    defer ticker.Stop()
    defer close(w.done)

    for {
        select {
        case <-ctx.Done():
            return nil
        case <-ticker.C:
            if err := w.task(ctx); err != nil {
                slog.Error("Worker task failed",
                    slog.String("worker", w.name),
                    slog.Any("error", err),
                )
            }
        }
    }
}

func (w *BackgroundWorker) Stop(ctx context.Context) error {
    select {
    case <-w.done:
        return nil
    case <-ctx.Done():
        return fmt.Errorf("worker %s: shutdown timeout", w.name)
    }
}

// Database component with connection pool
type Database struct {
    db  *sql.DB
    dsn string
}

func NewDatabase(dsn string) *Database {
    return &Database{dsn: dsn}
}

func (d *Database) Name() string { return "database" }

func (d *Database) Start(ctx context.Context) error {
    var err error
    d.db, err = sql.Open("postgres", d.dsn)
    if err != nil {
        return fmt.Errorf("open db: %w", err)
    }

    d.db.SetMaxOpenConns(25)
    d.db.SetMaxIdleConns(5)
    d.db.SetConnMaxLifetime(5 * time.Minute)

    if err := d.db.PingContext(ctx); err != nil {
        return fmt.Errorf("ping db: %w", err)
    }

    // Block until context cancelled
    <-ctx.Done()
    return nil
}

func (d *Database) Stop(ctx context.Context) error {
    if d.db != nil {
        return d.db.Close()
    }
    return nil
}

func (d *Database) DB() *sql.DB { return d.db }
```

```go
// --- Main: composing the application ---

package main

import (
    "context"
    "log/slog"
    "net/http"
    "os"
    "time"

    "myapp/shutdown"
)

func main() {
    logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
        Level: slog.LevelInfo,
    }))
    slog.SetDefault(logger)

    // Create shutdown manager with 30s timeout
    mgr := shutdown.NewManager(logger, 30*time.Second)

    // Register components in startup order
    // (shutdown happens in reverse: workers -> server -> database)

    // 1. Database (started first, stopped last)
    db := NewDatabase(os.Getenv("DATABASE_URL"))
    mgr.Register(db)

    // 2. HTTP server
    mux := http.NewServeMux()
    mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
        if err := db.DB().PingContext(r.Context()); err != nil {
            http.Error(w, "unhealthy", http.StatusServiceUnavailable)
            return
        }
        w.WriteHeader(http.StatusOK)
        w.Write([]byte(`{"status":"ok"}`))
    })
    mux.HandleFunc("GET /api/data", func(w http.ResponseWriter, r *http.Request) {
        w.Write([]byte(`{"data":"hello"}`))
    })

    server := NewHTTPServer(":8080", mux)
    mgr.Register(server)

    // 3. Background workers (started last, stopped first)
    metricsWorker := NewBackgroundWorker("metrics", 10*time.Second,
        func(ctx context.Context) error {
            logger.Info("Collecting metrics")
            return nil
        },
    )
    mgr.Register(metricsWorker)

    cleanupWorker := NewBackgroundWorker("cleanup", 1*time.Minute,
        func(ctx context.Context) error {
            logger.Info("Running cleanup")
            return nil
        },
    )
    mgr.Register(cleanupWorker)

    // Run blocks until shutdown
    logger.Info("Application starting")
    if err := mgr.Run(context.Background()); err != nil {
        logger.Error("Application error", slog.Any("error", err))
        os.Exit(1)
    }
    logger.Info("Application stopped cleanly")
}
```

Shutdown ordering strategy:

| Order | Component | Shutdown Action | Why This Order |
|-------|-----------|----------------|---------------|
| 1 (first to stop) | Background workers | Cancel context, wait for current task | Stop producing new work |
| 2 | HTTP server | `Shutdown()` drains in-flight requests | Stop accepting new requests |
| 3 | Message consumers | Stop polling, finish current batch | Stop consuming from queues |
| 4 | Connection pools | Close idle, wait for active | Release external resources |
| 5 (last to stop) | Database | `db.Close()` | Everything else depends on it |

Key patterns:
1. Use `signal.NotifyContext` for clean OS signal handling — replaces manual `signal.Notify` + channel
2. Stop components in reverse startup order (LIFO) to respect dependency ordering
3. Always set a shutdown timeout to prevent indefinite hangs during stop
4. Use `http.Server.Shutdown(ctx)` — it stops accepting new connections and drains in-flight requests
5. Background workers should check `ctx.Done()` in their loop and exit cleanly
6. The Component interface (`Start` + `Stop` + `Name`) provides a uniform lifecycle contract for any service component'''
    ),
]
