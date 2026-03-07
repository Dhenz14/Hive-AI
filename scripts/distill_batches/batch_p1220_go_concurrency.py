"""
Go language training pairs - concurrency (goroutines, channels, select, WaitGroup, errgroup)
"""

pairs = [
    {
        "instruction": r'''<think>
The user wants to understand Go concurrency patterns with goroutines and channels. I need to show how goroutines communicate via channels, and demonstrate common patterns like fan-out/fan-in. Let me think about what makes Go concurrency unique compared to threads -- goroutines are lightweight (a few KB stack), multiplexed onto OS threads by the Go scheduler. Channels enforce communication by sharing memory rather than sharing memory by locking. I should show a practical fan-out/fan-in pipeline since that is the most common real-world pattern.
</think>
Show me how to implement a fan-out/fan-in pipeline in Go using goroutines and channels. I want to process a stream of URLs concurrently with a bounded number of workers.''',
        "output": r'''Here is a fan-out/fan-in pipeline with bounded concurrency:

```go
package main

import (
	"fmt"
	"net/http"
	"sync"
	"time"
)

type Result struct {
	URL    string
	Status int
	Err    error
}

// generator produces URLs on a channel
func generator(urls []string) <-chan string {
	out := make(chan string)
	go func() {
		defer close(out)
		for _, u := range urls {
			out <- u
		}
	}()
	return out
}

// worker fetches URLs and sends results
func worker(id int, urls <-chan string, results chan<- Result, wg *sync.WaitGroup) {
	defer wg.Done()
	client := &http.Client{Timeout: 5 * time.Second}
	for url := range urls {
		resp, err := client.Get(url)
		if err != nil {
			results <- Result{URL: url, Err: err}
			continue
		}
		resp.Body.Close()
		results <- Result{URL: url, Status: resp.StatusCode}
	}
}

func main() {
	urls := []string{
		"https://go.dev",
		"https://pkg.go.dev",
		"https://example.com",
		"https://httpbin.org/get",
	}

	// Fan-out: spawn N workers reading from one channel
	numWorkers := 3
	urlCh := generator(urls)
	resultCh := make(chan Result, len(urls))

	var wg sync.WaitGroup
	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		go worker(i, urlCh, resultCh, &wg)
	}

	// Close results channel when all workers finish
	go func() {
		wg.Wait()
		close(resultCh)
	}()

	// Fan-in: collect all results
	for r := range resultCh {
		if r.Err != nil {
			fmt.Printf("ERROR %s: %v\n", r.URL, r.Err)
		} else {
			fmt.Printf("OK %s: %d\n", r.URL, r.Status)
		}
	}
}
```

Key points:
- The generator sends URLs on a channel and closes it when done
- Workers range over the input channel -- they stop when it closes
- WaitGroup tracks when all workers finish so we can close the results channel
- Buffered result channel prevents goroutine leaks if the consumer is slow
- Each worker reuses an http.Client for connection pooling'''
    },
    {
        "instruction": r'''How do I use Go select statement to implement a timeout and cancellation pattern for concurrent operations?''',
        "output": r'''Use `select` with `time.After` and `context.Context` for robust timeout and cancellation:

```go
package main

import (
	"context"
	"fmt"
	"math/rand"
	"time"
)

// slowOperation simulates work that may take variable time
func slowOperation(ctx context.Context, id int) <-chan string {
	ch := make(chan string, 1)
	go func() {
		delay := time.Duration(rand.Intn(3000)) * time.Millisecond
		select {
		case <-time.After(delay):
			ch <- fmt.Sprintf("task %d completed in %v", id, delay)
		case <-ctx.Done():
			ch <- fmt.Sprintf("task %d cancelled: %v", id, ctx.Err())
		}
	}()
	return ch
}

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	// Launch 5 concurrent tasks
	channels := make([]<-chan string, 5)
	for i := 0; i < 5; i++ {
		channels[i] = slowOperation(ctx, i)
	}

	// Collect results with per-task and global timeout
	for i, ch := range channels {
		select {
		case result := <-ch:
			fmt.Println(result)
		case <-time.After(1 * time.Second):
			fmt.Printf("task %d: individual timeout\n", i)
		case <-ctx.Done():
			fmt.Printf("task %d: global timeout\n", i)
		}
	}
}
```

The select statement multiplexes across channels:
- First matching case wins; if multiple are ready, one is chosen at random
- `time.After` returns a channel that fires once after the duration
- `ctx.Done()` fires when the context is cancelled or times out
- Always defer `cancel()` to release context resources
- Buffered channel (cap 1) in slowOperation prevents goroutine leak if nobody reads'''
    },
    {
        "instruction": r'''<think>
The user wants to see errgroup usage. errgroup is in golang.org/x/sync/errgroup and provides a cleaner API than WaitGroup when you need error propagation from goroutines. The key advantage over bare WaitGroup + error channel is that errgroup handles the synchronization, cancellation, and error collection automatically. I should show the SetLimit method too since that was added for bounded concurrency. Let me also show how errgroup integrates with context for automatic cancellation when one goroutine fails.
</think>
Show me how to use golang.org/x/sync/errgroup for concurrent operations with error handling and automatic cancellation.''',
        "output": r'''errgroup simplifies concurrent work with error propagation and context cancellation:

```go
package main

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"time"

	"golang.org/x/sync/errgroup"
)

type Page struct {
	URL  string
	Size int
}

func fetchPage(ctx context.Context, url string) (Page, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return Page{}, fmt.Errorf("creating request for %s: %w", url, err)
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return Page{}, fmt.Errorf("fetching %s: %w", url, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return Page{}, fmt.Errorf("reading %s: %w", url, err)
	}

	return Page{URL: url, Size: len(body)}, nil
}

func main() {
	urls := []string{
		"https://go.dev",
		"https://pkg.go.dev",
		"https://example.com",
	}

	// WithContext returns a group and derived context.
	// If any goroutine returns non-nil error, ctx is cancelled.
	g, ctx := errgroup.WithContext(context.Background())

	// SetLimit caps concurrent goroutines (like a semaphore)
	g.SetLimit(2)

	results := make([]Page, len(urls))
	for i, url := range urls {
		i, url := i, url // capture loop vars (needed before Go 1.22)
		g.Go(func() error {
			page, err := fetchPage(ctx, url)
			if err != nil {
				return err // cancels ctx for other goroutines
			}
			results[i] = page
			return nil
		})
	}

	// Wait blocks until all goroutines finish, returns first error
	if err := g.Wait(); err != nil {
		fmt.Printf("failed: %v\n", err)
		return
	}

	for _, p := range results {
		fmt.Printf("%s: %d bytes\n", p.URL, p.Size)
	}
}
```

Why errgroup over WaitGroup:
- Automatically propagates the first error from any goroutine
- WithContext cancels remaining work when one fails
- SetLimit provides built-in bounded concurrency
- No manual Add/Done/Wait bookkeeping
- Each index in the results slice is written by exactly one goroutine, so no mutex needed'''
    },
    {
        "instruction": r'''What is the proper way to use unbuffered vs buffered channels in Go, and when should I pick each?''',
        "output": r'''Unbuffered channels synchronize sender and receiver -- both block until the other side is ready. Buffered channels allow the sender to proceed until the buffer is full.

```go
package main

import (
	"fmt"
	"sync"
	"time"
)

func unbufferedDemo() {
	// Unbuffered: send blocks until someone receives
	ch := make(chan int)

	go func() {
		fmt.Println("sender: about to send")
		ch <- 42 // blocks until main receives
		fmt.Println("sender: sent")
	}()

	time.Sleep(500 * time.Millisecond)
	val := <-ch // unblocks the sender
	fmt.Println("receiver got:", val)
}

func bufferedDemo() {
	// Buffered: send succeeds immediately if buffer not full
	ch := make(chan string, 3)

	// Can send 3 values without a receiver
	ch <- "a"
	ch <- "b"
	ch <- "c"
	// ch <- "d" would block here (buffer full)

	fmt.Println(<-ch, <-ch, <-ch)
}

func semaphorePattern() {
	// Buffered channel as a semaphore to limit concurrency
	const maxConcurrent = 3
	sem := make(chan struct{}, maxConcurrent)

	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			sem <- struct{}{} // acquire slot
			defer func() { <-sem }() // release slot

			fmt.Printf("worker %d running\n", id)
			time.Sleep(100 * time.Millisecond)
		}(i)
	}
	wg.Wait()
}

func main() {
	unbufferedDemo()
	bufferedDemo()
	semaphorePattern()
}
```

When to use each:
- Unbuffered: when you need synchronization guarantees (handoff semantics)
- Buffered(1): when producer and consumer run at roughly equal speeds but you want to decouple them slightly
- Buffered(N): when you know the exact count of items (e.g., collecting N results)
- Buffered as semaphore: to limit concurrent access to a resource

Common mistake: using large buffers to "fix" deadlocks. If your program deadlocks with an unbuffered channel, a buffer just delays the deadlock -- fix the design instead.'''
    },
    {
        "instruction": r'''Write a Go program that uses a done channel pattern to gracefully shut down multiple worker goroutines.''',
        "output": r'''The done channel (or quit channel) pattern broadcasts a shutdown signal to all goroutines:

```go
package main

import (
	"fmt"
	"math/rand"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

func worker(id int, jobs <-chan int, done <-chan struct{}, wg *sync.WaitGroup) {
	defer wg.Done()
	for {
		select {
		case job, ok := <-jobs:
			if !ok {
				fmt.Printf("worker %d: jobs channel closed\n", id)
				return
			}
			// Simulate processing
			dur := time.Duration(rand.Intn(500)) * time.Millisecond
			fmt.Printf("worker %d: processing job %d\n", id, job)
			select {
			case <-time.After(dur):
				fmt.Printf("worker %d: finished job %d\n", id, job)
			case <-done:
				fmt.Printf("worker %d: interrupted during job %d\n", id, job)
				return
			}
		case <-done:
			fmt.Printf("worker %d: shutting down\n", id)
			return
		}
	}
}

func main() {
	done := make(chan struct{})
	jobs := make(chan int, 10)

	// Trap SIGINT/SIGTERM for graceful shutdown
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	var wg sync.WaitGroup
	numWorkers := 3
	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		go worker(i, jobs, done, &wg)
	}

	// Producer: send jobs until signal received
	go func() {
		for i := 0; ; i++ {
			select {
			case jobs <- i:
			case <-done:
				return
			}
			time.Sleep(200 * time.Millisecond)
		}
	}()

	// Wait for shutdown signal
	sig := <-sigCh
	fmt.Printf("\nreceived %v, shutting down...\n", sig)

	// Close done channel -- broadcasts to ALL goroutines
	close(done)

	// Wait for workers to finish current work
	wg.Wait()
	fmt.Println("all workers stopped, exiting")
}
```

Key design points:
- Closing a channel broadcasts to all receivers -- every goroutine selecting on `done` wakes up
- Never send on the done channel; always close it (send would only wake one receiver)
- Nest select inside the job processing to allow interruption mid-work
- WaitGroup ensures main waits for all workers to finish cleanly
- In production, prefer context.WithCancel over raw done channels -- it composes better with stdlib APIs'''
    },
]
