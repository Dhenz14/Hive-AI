# Go Concurrency Patterns

## Goroutines + WaitGroup
```go
import "sync"

var wg sync.WaitGroup
for _, item := range items {
    wg.Add(1)
    go func(it Item) {
        defer wg.Done()
        process(it)
    }(item)
}
wg.Wait()
```

## Channels
```go
// Unbuffered (synchronous handoff)
ch := make(chan Result)

// Buffered (async up to capacity)
ch := make(chan Result, 100)

// Fan-out / fan-in
func fanOut(input <-chan Job, workers int) <-chan Result {
    results := make(chan Result)
    var wg sync.WaitGroup
    for i := 0; i < workers; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for job := range input {
                results <- process(job)
            }
        }()
    }
    go func() {
        wg.Wait()
        close(results)
    }()
    return results
}
```

## Worker Pool
```go
func workerPool(jobs <-chan Job, results chan<- Result, numWorkers int) {
    var wg sync.WaitGroup
    for i := 0; i < numWorkers; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for job := range jobs {
                results <- doWork(job)
            }
        }()
    }
    go func() {
        wg.Wait()
        close(results)
    }()
}
```

## Context (Cancellation + Timeout)
```go
import "context"

// Timeout
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()

// Manual cancellation
ctx, cancel := context.WithCancel(context.Background())
// Later: cancel()

// Pass context through call chain
func fetchData(ctx context.Context, url string) ([]byte, error) {
    req, _ := http.NewRequestWithContext(ctx, "GET", url, nil)
    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    return io.ReadAll(resp.Body)
}

// Select on context cancellation
select {
case result := <-ch:
    return result, nil
case <-ctx.Done():
    return nil, ctx.Err()  // context.DeadlineExceeded or context.Canceled
}
```

## Bounded Concurrency (Semaphore)
```go
sem := make(chan struct{}, 10)  // Max 10 concurrent
var wg sync.WaitGroup
for _, url := range urls {
    wg.Add(1)
    sem <- struct{}{}  // Acquire
    go func(u string) {
        defer wg.Done()
        defer func() { <-sem }()  // Release
        fetch(u)
    }(url)
}
wg.Wait()
```

## errgroup (Goroutines with Error Propagation)
```go
import "golang.org/x/sync/errgroup"

g, ctx := errgroup.WithContext(context.Background())
g.SetLimit(10)  // Bounded concurrency

for _, url := range urls {
    url := url  // Capture (Go <1.22)
    g.Go(func() error {
        return fetch(ctx, url)
    })
}
if err := g.Wait(); err != nil {
    // First error cancels ctx, Wait returns it
}
```

## Mutex vs Channel
| Use Mutex | Use Channel |
|-----------|-------------|
| Protecting shared state (map, counter) | Passing ownership of data |
| Short critical sections | Pipeline stages |
| sync.RWMutex for read-heavy | Fan-out / fan-in |

```go
// Mutex for shared state
var mu sync.RWMutex
var cache map[string]Value

func get(key string) (Value, bool) {
    mu.RLock()
    defer mu.RUnlock()
    v, ok := cache[key]
    return v, ok
}
```

## Key Gotchas
- **Always close channels from sender side**, never receiver. Closing a closed channel panics.
- **Range over channel** blocks until channel is closed: `for v := range ch { ... }`
- **Goroutine leak**: If nobody reads from a channel, the writing goroutine blocks forever. Always ensure consumers exist or use buffered channels.
- **Race detector**: Run `go test -race ./...` to catch data races.
- **sync.Once** for one-time initialization (thread-safe singleton).
- **Loop variable capture**: In Go <1.22, `go func() { use(v) }()` captures the loop variable by reference. Copy it: `go func(v T) { use(v) }(v)`.
