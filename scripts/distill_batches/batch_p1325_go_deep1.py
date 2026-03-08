"""Go deep reasoning pairs batch 1: concurrency fundamentals."""
PAIRS = [
    ("go_deep/goroutine_lifecycle_stack_growth", r'''Explain how goroutine stacks grow in Go. Write a program that demonstrates goroutine creation, deep recursion triggering stack growth, and prints the number of active goroutines at various points.''', r'''<think>
The user wants to understand goroutine stack mechanics. Let me think carefully.
Goroutines start with a small stack — 2KB since Go 1.4.
This is radically smaller than OS thread stacks (typically 1-8MB).
That tiny initial size is how Go can spawn millions of goroutines cheaply.
Stack growth uses "stack copying" — the function preamble checks if the stack is too small.
If so, the runtime allocates a new 2x stack, copies old contents, updates pointers.
This replaced "segmented stacks" which had the "hot split" problem.
Edge case: deep recursion. Stack doubles each time: 2KB -> 4KB -> 8KB -> ... up to 1GB max.
runtime.debug.SetMaxStack can change this limit if needed.
For the demo, I'll use runtime.NumGoroutine() to track active goroutines.
Also runtime.MemStats.StackInuse to show aggregate stack memory changing during recursion.
One subtlety: NumGoroutine() includes the main goroutine plus runtime background goroutines.
So it won't start at 1 — there are always a few runtime goroutines for GC, finalizers, etc.
Stack shrinking also happens: during GC, stacks using less than 1/4 of capacity get shrunk.
This prevents goroutines with brief deep calls from permanently holding large stacks.
Cgo calls use the system stack (8KB), not the goroutine stack — source of overflow panics.
I'll demonstrate the full lifecycle: creation, stack growth under recursion, and cleanup.
When a goroutine returns, its stack is freed and NumGoroutine decreases.
I need sync.WaitGroup to properly synchronize so nothing races in the demo.
</think>

In Go, each goroutine starts with a tiny stack (2KB since Go 1.4). When a function prologue detects insufficient stack space, the runtime allocates a new, larger stack (typically 2x the current size), copies the old stack over, updates internal pointers, and frees the old stack. This "stack copying" approach replaced the earlier "segmented stacks" design which suffered from the "hot split" problem. Stacks can grow up to a default maximum of 1GB.

Here is a complete program demonstrating goroutine lifecycle and stack growth:

```go
package main

import (
	"fmt"
	"runtime"
	"sync"
)

func deepRecurse(depth int, result *int) {
	// Each frame adds local variables to the stack, forcing growth
	var padding [64]byte
	_ = padding
	*result = depth
	if depth > 0 {
		deepRecurse(depth-1, result)
	}
}

func printStats(label string) {
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	fmt.Printf("[%-30s] goroutines=%-4d stack_inuse=%-10d bytes\n",
		label, runtime.NumGoroutine(), m.StackInuse)
}

func main() {
	printStats("program start")

	var wg sync.WaitGroup

	// Spawn 100 goroutines that just sleep on a channel
	blocker := make(chan struct{})
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-blocker
		}()
	}
	runtime.Gosched() // let goroutines start
	printStats("100 goroutines waiting")

	// Release them
	close(blocker)
	wg.Wait()
	runtime.GC()
	printStats("after goroutines exit")

	// Now demonstrate stack growth via deep recursion
	printStats("before deep recursion")

	const numWorkers = 10
	const recursionDepth = 10_000

	var wg2 sync.WaitGroup
	for i := 0; i < numWorkers; i++ {
		wg2.Add(1)
		go func(id int) {
			defer wg2.Done()
			var result int
			deepRecurse(recursionDepth, &result)
			if id == 0 {
				// Only print from one goroutine to avoid interleaving
				printStats("during deep recursion")
			}
		}(i)
	}
	wg2.Wait()
	runtime.GC()
	printStats("after deep recursion done")

	fmt.Println("\nKey observations:")
	fmt.Println("- Goroutines start with 2KB stacks (very cheap to create)")
	fmt.Println("- Stack grows automatically during deep recursion (stack copying)")
	fmt.Println("- Stack memory is released when goroutines exit")
	fmt.Println("- runtime.NumGoroutine() includes the main goroutine + runtime goroutines")
}
```

Run with `go run main.go`. You will observe `StackInuse` increasing dramatically during deep recursion and dropping after those goroutines exit, demonstrating the full lifecycle of goroutine stack allocation, growth, and reclamation.'''),

    ("go_deep/channel_axioms_nil_closed", r'''What are the channel axioms in Go — specifically what happens when you send to or receive from a nil channel, and when you receive from a closed channel? Write a program demonstrating each case safely.''', r'''<think>
The channel axioms in Go are fundamental but often misunderstood. Let me lay them out carefully:

1. Send to nil channel: blocks forever
2. Receive from nil channel: blocks forever
3. Close nil channel: panic
4. Send to closed channel: panic
5. Receive from closed channel: returns the zero value immediately (after buffer is drained)
6. Close an already-closed channel: panic

These axioms are essential knowledge. Let me organize them carefully.
A nil channel in a select statement effectively disables that case.
This is a powerful pattern for dynamically enabling/disabling select branches.
For the demo, I can't just send to a nil channel on main — that deadlocks.
I need goroutines with timeouts or select to demonstrate blocking behavior safely.
For "receive from closed channel" I should show two forms:
- Single-value receive: v := <-ch gets the zero value
- Two-value receive: v, ok := <-ch where ok is false — this detects closure
The distinction matters because zero value could be a legitimate value (0 for int, "" for string).
Edge case: buffered channel with values, then closed.
Receives drain the buffer first, THEN start returning zero values.
Closing doesn't discard buffered data — the channel serves remaining items.
The three panic cases are: close(nil), send to closed, double close.
All three are runtime panics, not compile-time errors.
I should show them with recover() so the demo doesn't crash.
The nil-channel-in-select pattern is used for merging channels.
When one source is exhausted, set its variable to nil — its select case is permanently skipped.
Let me structure each axiom as an isolated demo function for clarity.
</think>

The Go channel axioms are a set of rules governing channel behavior in edge cases. They are essential knowledge for writing correct concurrent Go:

| Operation | nil channel | closed channel |
|-----------|-------------|----------------|
| Send      | blocks forever | **panic** |
| Receive   | blocks forever | returns zero value (ok=false) |
| Close     | **panic** | **panic** |

Here is a complete program demonstrating each axiom safely:

```go
package main

import (
	"fmt"
	"time"
)

func safeGo(name string, fn func()) {
	defer func() {
		if r := recover(); r != nil {
			fmt.Printf("  [PANIC recovered] %s: %v\n", name, r)
		}
	}()
	fn()
}

func demoNilChannelBlocks() {
	fmt.Println("\n=== Nil Channel Blocks Forever ===")

	var ch chan int // nil channel

	// Receive from nil — blocks, so we use a timeout to prove it
	done := make(chan string)
	go func() {
		select {
		case v := <-ch:
			done <- fmt.Sprintf("received %d (unexpected!)", v)
		case <-time.After(100 * time.Millisecond):
			done <- "receive from nil channel blocked (timed out as expected)"
		}
	}()
	fmt.Printf("  %s\n", <-done)

	// Send to nil — blocks, same approach
	go func() {
		select {
		case ch <- 42:
			done <- "sent to nil channel (unexpected!)"
		case <-time.After(100 * time.Millisecond):
			done <- "send to nil channel blocked (timed out as expected)"
		}
	}()
	fmt.Printf("  %s\n", <-done)
}

func demoCloseNilPanics() {
	fmt.Println("\n=== Close Nil Channel Panics ===")
	var ch chan int
	safeGo("close(nil)", func() {
		close(ch)
	})
}

func demoSendToClosedPanics() {
	fmt.Println("\n=== Send to Closed Channel Panics ===")
	ch := make(chan int, 1)
	close(ch)
	safeGo("send to closed", func() {
		ch <- 42
	})
}

func demoReceiveFromClosed() {
	fmt.Println("\n=== Receive from Closed Channel ===")

	// Unbuffered, closed immediately
	ch1 := make(chan int)
	close(ch1)
	v, ok := <-ch1
	fmt.Printf("  unbuffered closed: v=%d, ok=%v (zero value, not ok)\n", v, ok)

	// Buffered with data, then closed — drains buffer first
	ch2 := make(chan int, 3)
	ch2 <- 10
	ch2 <- 20
	close(ch2)

	for i := 0; i < 4; i++ {
		v, ok := <-ch2
		fmt.Printf("  buffered closed recv #%d: v=%d, ok=%v\n", i, v, ok)
	}
}

func demoDoubleClosePanics() {
	fmt.Println("\n=== Double Close Panics ===")
	ch := make(chan int)
	close(ch)
	safeGo("double close", func() {
		close(ch)
	})
}

func demoNilDisablesSelect() {
	fmt.Println("\n=== Nil Channel Disables Select Case (useful pattern) ===")
	a := make(chan int, 1)
	b := make(chan int, 1)
	a <- 1
	b <- 2

	for i := 0; i < 2; i++ {
		select {
		case v, ok := <-a:
			if ok {
				fmt.Printf("  got from a: %d (disabling a)\n", v)
				a = nil // disable this select case
			}
		case v, ok := <-b:
			if ok {
				fmt.Printf("  got from b: %d (disabling b)\n", v)
				b = nil
			}
		}
	}
	fmt.Println("  both channels disabled via nil — select would block")
}

func main() {
	demoNilChannelBlocks()
	demoCloseNilPanics()
	demoSendToClosedPanics()
	demoReceiveFromClosed()
	demoDoubleClosePanics()
	demoNilDisablesSelect()

	fmt.Println("\nAll channel axioms demonstrated safely.")
}
```

Key takeaway: the nil-channel-disables-select-case pattern is the most practically useful axiom. It lets you dynamically control which branches of a `select` are active without restructuring your code.'''),

    ("go_deep/buffered_vs_unbuffered_channels", r'''When should I use buffered vs unbuffered channels in Go? Write a program that demonstrates the behavioral differences and shows a real scenario where choosing wrong causes problems.''', r'''<think>
This is a subtle topic. Let me think through the real differences and when each matters.

Unbuffered channels (make(chan T)) provide synchronization — the sender blocks until a receiver is ready, and vice versa. This is a rendezvous point. It guarantees that when a send completes, the receiver has the value. This is great for signaling and handoff.

Buffered channels (make(chan T, N)) decouple sender and receiver timing. The sender only blocks when the buffer is full. This is useful when you know the production rate and want to absorb bursts, or when you have a known fixed number of results (e.g., N goroutines each sending one result → buffer of N).

Common mistakes:
1. Using buffered channel to "fix" a deadlock — this usually masks a design problem
2. Using buffer size 1 as a mutex (it works but sync.Mutex is clearer)
3. Unbounded buffer growth — Go doesn't have unbounded channels, but large buffers can hide backpressure issues

When to use unbuffered:
- Signaling (done channels)
- When you need synchronization guarantees
- When you want backpressure immediately

When to use buffered:
- Known number of results (fan-out where N goroutines each produce 1 result)
- Producer-consumer with bursty production
- Semaphore pattern (buffered channel as counting semaphore)

The "choosing wrong causes problems" scenario: if you use an unbuffered channel in a fire-and-forget goroutine that might not have a receiver, you leak the goroutine. A buffer of 1 would let it complete and be GC'd.

Let me also show the timing difference — unbuffered forces lockstep, buffered allows the producer to race ahead.
</think>

The core difference: unbuffered channels synchronize (rendezvous), buffered channels decouple timing. Here is a program demonstrating both the behavioral differences and a real bug caused by choosing wrong:

```go
package main

import (
	"fmt"
	"sync"
	"time"
)

// Demo 1: Timing behavior difference
func timingDemo() {
	fmt.Println("=== Timing Behavior ===")

	// Unbuffered: sender blocks until receiver is ready (lockstep)
	unbuf := make(chan int)
	start := time.Now()
	go func() {
		for i := 0; i < 3; i++ {
			unbuf <- i
			fmt.Printf("  unbuf: sent %d at %v\n", i, time.Since(start).Round(time.Millisecond))
		}
		close(unbuf)
	}()
	for v := range unbuf {
		time.Sleep(100 * time.Millisecond)
		_ = v
	}
	fmt.Printf("  unbuf total: %v (lockstep — ~300ms)\n\n", time.Since(start).Round(time.Millisecond))

	// Buffered: sender races ahead until buffer is full
	buf := make(chan int, 3)
	start = time.Now()
	go func() {
		for i := 0; i < 3; i++ {
			buf <- i
			fmt.Printf("  buf:   sent %d at %v\n", i, time.Since(start).Round(time.Millisecond))
		}
		close(buf)
	}()
	time.Sleep(10 * time.Millisecond) // let sender fill buffer
	for v := range buf {
		time.Sleep(100 * time.Millisecond)
		_ = v
	}
	fmt.Printf("  buf total: %v (producer raced ahead)\n", time.Since(start).Round(time.Millisecond))
}

// Demo 2: Goroutine leak with wrong channel type
func goroutineLeakDemo() {
	fmt.Println("\n=== Goroutine Leak: Wrong Channel Type ===")

	// Simulates an HTTP handler that starts background work
	// but sometimes abandons the result (e.g., client timeout)

	fetchResult := func(useBuf bool) chan string {
		var ch chan string
		if useBuf {
			ch = make(chan string, 1) // buffered: goroutine can finish even without receiver
		} else {
			ch = make(chan string) // unbuffered: goroutine BLOCKS if no receiver
		}
		go func() {
			time.Sleep(50 * time.Millisecond) // simulate work
			ch <- "result"                     // THIS BLOCKS FOREVER if unbuffered + no receiver
		}()
		return ch
	}

	// Scenario: caller gives up after 10ms (simulating client timeout)
	consume := func(label string, ch chan string) {
		select {
		case v := <-ch:
			fmt.Printf("  %s: got %s\n", label, v)
		case <-time.After(10 * time.Millisecond):
			fmt.Printf("  %s: timed out, abandoned channel\n", label)
		}
	}

	// Unbuffered: the goroutine leaks! It blocks on send forever.
	ch1 := fetchResult(false)
	consume("unbuffered", ch1)
	time.Sleep(100 * time.Millisecond)
	// The goroutine is still alive, blocked on ch1 <- "result"

	// Buffered(1): the goroutine completes, value sits in buffer, gets GC'd.
	ch2 := fetchResult(true)
	consume("buffered(1)", ch2)
	time.Sleep(100 * time.Millisecond)
	// The goroutine finished normally, channel+value will be garbage collected
}

// Demo 3: Buffered channel as counting semaphore
func semaphoreDemo() {
	fmt.Println("\n=== Buffered Channel as Semaphore ===")
	const maxConcurrent = 3
	sem := make(chan struct{}, maxConcurrent)

	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			sem <- struct{}{} // acquire
			fmt.Printf("  worker %d running (slots used: %d/%d)\n", id, len(sem), cap(sem))
			time.Sleep(50 * time.Millisecond)
			<-sem // release
		}(i)
	}
	wg.Wait()
}

// Demo 4: Known-count fan-out (buffer = number of goroutines)
func fanOutDemo() {
	fmt.Println("\n=== Fan-Out with Exact Buffer ===")
	const n = 5
	results := make(chan int, n) // buffer = n so no goroutine blocks

	for i := 0; i < n; i++ {
		go func(id int) {
			results <- id * id
		}(i)
	}

	for i := 0; i < n; i++ {
		fmt.Printf("  result: %d\n", <-results)
	}
}

func main() {
	timingDemo()
	goroutineLeakDemo()
	semaphoreDemo()
	fanOutDemo()

	fmt.Println("\nGuidelines:")
	fmt.Println("  Unbuffered: signaling, synchronization, backpressure")
	fmt.Println("  Buffered(1): fire-and-forget results, preventing goroutine leaks")
	fmt.Println("  Buffered(N): known fan-out count, semaphore, burst absorption")
	fmt.Println("  AVOID: large buffers to 'fix' deadlocks — masks design flaws")
}
```

Run with `go run main.go`. The goroutine leak demo is the most important lesson — using an unbuffered channel for a result that might be abandoned leaks the sending goroutine permanently. A buffer of 1 fixes this cleanly.'''),

    ("go_deep/select_default_nonblocking", r'''Show me how to use select with a default case for non-blocking channel operations in Go. Include examples of non-blocking send, non-blocking receive, and a polling loop pattern.''', r'''<think>
Select with default is how Go does non-blocking channel operations.
Without default, select blocks until one case is ready.
With default, it falls through immediately if no case can proceed.
Key patterns to demonstrate:
1. Non-blocking receive: try to read, fall through if nothing available
2. Non-blocking send: try to send, fall through if channel is full
3. Polling loop: periodically check channels with default that sleeps
Important subtlety: non-blocking send on a full buffered channel silently drops data.
The send case is skipped, nothing is queued. Caller must handle this explicitly.
When multiple cases are ready, Go picks one uniformly at random.
This prevents starvation but means case order doesn't matter for priority.
Common mistake: tight polling loop without sleep in default — burns 100% CPU.
Always add time.Sleep or time.After in the default for polling patterns.
Anti-pattern: using non-blocking receive in a tight loop instead of just blocking.
Blocking is correct and more efficient when you have nothing else to do.
Non-blocking is for specific cases like "drain a channel" or "check for cancellation."
Combining with context: check ctx.Done() as one case with default to continue work.
This is a cooperative cancellation check — goroutine does work chunks between checks.
Channel drain pattern: after close, discard remaining buffered values with select+default.
This lets you empty the buffer without blocking, then exit immediately.
Let me make all examples complete and runnable.
</think>

The `select` statement with a `default` case enables non-blocking channel operations. Without `default`, `select` blocks until a case is ready. With `default`, it executes immediately if no channel operation can proceed.

```go
package main

import (
	"context"
	"fmt"
	"math/rand"
	"sync"
	"time"
)

// 1. Non-blocking receive
func nonBlockingReceive() {
	fmt.Println("=== Non-Blocking Receive ===")
	ch := make(chan string, 1)

	// Channel is empty — receive would block, so default runs
	select {
	case msg := <-ch:
		fmt.Printf("  received: %s\n", msg)
	default:
		fmt.Println("  no message available (non-blocking)")
	}

	// Now put something in the channel
	ch <- "hello"

	// Channel has data — receive case runs
	select {
	case msg := <-ch:
		fmt.Printf("  received: %s\n", msg)
	default:
		fmt.Println("  no message available")
	}
}

// 2. Non-blocking send
func nonBlockingSend() {
	fmt.Println("\n=== Non-Blocking Send ===")
	ch := make(chan int, 2)

	// Send values until the buffer is full
	for i := 0; i < 5; i++ {
		select {
		case ch <- i:
			fmt.Printf("  sent %d (buffer: %d/%d)\n", i, len(ch), cap(ch))
		default:
			fmt.Printf("  dropped %d — channel full (buffer: %d/%d)\n", i, len(ch), cap(ch))
		}
	}

	// Drain
	close(ch)
	for v := range ch {
		fmt.Printf("  drained: %d\n", v)
	}
}

// 3. Polling loop with non-blocking checks
func pollingLoop() {
	fmt.Println("\n=== Polling Loop ===")
	events := make(chan string, 5)

	// Producer: sends events at random intervals
	go func() {
		msgs := []string{"click", "scroll", "keypress", "hover", "submit"}
		for _, m := range msgs {
			time.Sleep(time.Duration(rand.Intn(80)+20) * time.Millisecond)
			events <- m
		}
		close(events)
	}()

	// Poller: checks for events, does other work in between
	iterations := 0
	for {
		select {
		case evt, ok := <-events:
			if !ok {
				fmt.Printf("  event stream closed after %d poll iterations\n", iterations)
				return
			}
			fmt.Printf("  event: %-10s (iteration %d)\n", evt, iterations)
		default:
			// No event ready — do other work or sleep to avoid CPU spin
			iterations++
			time.Sleep(10 * time.Millisecond)
		}
	}
}

// 4. Cooperative cancellation check in a compute loop
func cooperativeCancellation() {
	fmt.Println("\n=== Cooperative Cancellation Check ===")
	ctx, cancel := context.WithTimeout(context.Background(), 150*time.Millisecond)
	defer cancel()

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		iterations := 0
		for {
			// Non-blocking check: is context cancelled?
			select {
			case <-ctx.Done():
				fmt.Printf("  cancelled after %d iterations: %v\n", iterations, ctx.Err())
				return
			default:
				// Continue working — default prevents blocking on ctx.Done()
			}

			// Simulate a chunk of compute work
			time.Sleep(10 * time.Millisecond)
			iterations++
		}
	}()
	wg.Wait()
}

// 5. Channel drain pattern — empty a channel without blocking
func drainChannel() {
	fmt.Println("\n=== Drain Channel (Non-Blocking) ===")
	ch := make(chan int, 10)
	for i := 0; i < 7; i++ {
		ch <- i
	}

	drained := 0
	for {
		select {
		case <-ch:
			drained++
		default:
			fmt.Printf("  drained %d items from channel\n", drained)
			return
		}
	}
}

func main() {
	nonBlockingReceive()
	nonBlockingSend()
	pollingLoop()
	cooperativeCancellation()
	drainChannel()

	fmt.Println("\nKey rules:")
	fmt.Println("  - default makes select non-blocking")
	fmt.Println("  - polling loops MUST sleep in default to avoid CPU spin")
	fmt.Println("  - prefer blocking select when you have nothing else to do")
	fmt.Println("  - non-blocking send drops data silently — always handle the default case")
}
```

Run with `go run main.go`. The most common mistake is using a non-blocking polling loop without sleeping in the `default` branch, which wastes CPU. Prefer a blocking `select` with `time.After` or `time.Tick` unless you genuinely have other work to do between checks.'''),

    ("go_deep/fanout_fanin_error_propagation", r'''Implement a fan-out/fan-in pattern in Go that properly propagates errors. Multiple workers should process URLs concurrently, and if any worker encounters an error, the result should include that error without losing successful results.''', r'''<think>
Fan-out/fan-in is a core Go concurrency pattern. The tricky part is error propagation. Let me think through the design:

Fan-out: launch N goroutines, each processing work items from a shared channel (or each assigned specific items).
Fan-in: collect all results into a single channel, then aggregate.

For error handling, there are two common approaches:
1. Result type: a struct containing both the value and the error. Every worker sends a Result, and the collector separates successes from failures.
2. errgroup: use golang.org/x/sync/errgroup which cancels on first error. But this loses partial results.

The user wants "without losing successful results" — so approach 1 is correct. errgroup with first-error-cancellation would discard in-flight work.

Design decisions:
- Use a result struct: { URL string, Body string, Err error }
- Workers read from an input channel, write to an output channel
- A WaitGroup or "close when done" pattern to signal completion
- The collector ranges over the output channel

Edge cases:
- What if a worker panics? We should recover in each worker goroutine.
- What about timeouts? We should use context with timeout for each HTTP request.
- Channel sizing: output channel should be buffered to prevent worker blocking. Buffer size = number of input items.

Actually, for a clean pattern, I'll:
1. Send all URLs into an input channel, close it
2. Start N workers that range over the input channel
3. Each worker sends Result to output channel
4. Use a WaitGroup to close the output channel when all workers are done
5. Main goroutine ranges over results

This is clean and standard. Let me implement it with real HTTP requests using net/http.
</think>

The key insight is to use a result type that carries both the value and the error, so successful results are never lost when other workers fail:

```go
package main

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"
)

// Result carries either a success value or an error — never discard partial results
type Result struct {
	URL    string
	Status int
	Size   int
	Err    error
}

// fanOut starts numWorkers goroutines that read from urls and write to results.
// Closing urls signals workers to finish; they close results via WaitGroup when done.
func fanOut(ctx context.Context, urls <-chan string, numWorkers int) <-chan Result {
	results := make(chan Result, numWorkers) // buffer prevents blocking on slow collector

	var wg sync.WaitGroup
	client := &http.Client{Timeout: 5 * time.Second}

	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		go func(workerID int) {
			defer wg.Done()
			defer func() {
				if r := recover(); r != nil {
					// Don't let a panicking worker kill the pipeline
					results <- Result{Err: fmt.Errorf("worker %d panicked: %v", workerID, r)}
				}
			}()

			for url := range urls {
				results <- fetchURL(ctx, client, url)
			}
		}(i)
	}

	// Fan-in: close results channel after all workers finish
	go func() {
		wg.Wait()
		close(results)
	}()

	return results
}

func fetchURL(ctx context.Context, client *http.Client, url string) Result {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return Result{URL: url, Err: fmt.Errorf("bad request: %w", err)}
	}

	resp, err := client.Do(req)
	if err != nil {
		return Result{URL: url, Err: fmt.Errorf("fetch failed: %w", err)}
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20)) // 1MB limit
	if err != nil {
		return Result{URL: url, Status: resp.StatusCode, Err: fmt.Errorf("read body: %w", err)}
	}

	return Result{URL: url, Status: resp.StatusCode, Size: len(body)}
}

func main() {
	urls := []string{
		"https://httpbin.org/get",
		"https://httpbin.org/status/200",
		"https://httpbin.org/status/404",        // will succeed with 404 status
		"https://invalid.example.invalid/nope",  // will fail: DNS resolution
		"https://httpbin.org/delay/1",
		"https://httpbin.org/status/500",        // will succeed with 500 status
		"not-a-url://???",                       // will fail: bad scheme
		"https://httpbin.org/bytes/1024",
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Fan-out: send URLs into input channel
	urlCh := make(chan string, len(urls))
	for _, u := range urls {
		urlCh <- u
	}
	close(urlCh)

	// Start 3 workers, collect results
	results := fanOut(ctx, urlCh, 3)

	// Aggregate — separate successes and failures
	var successes []Result
	var failures []Result
	for r := range results {
		if r.Err != nil {
			failures = append(failures, r)
		} else {
			successes = append(successes, r)
		}
	}

	fmt.Printf("Successes (%d):\n", len(successes))
	for _, r := range successes {
		fmt.Printf("  %-45s status=%d size=%d\n", r.URL, r.Status, r.Size)
	}

	fmt.Printf("\nFailures (%d):\n", len(failures))
	for _, r := range failures {
		fmt.Printf("  %-45s err=%v\n", r.URL, r.Err)
	}

	fmt.Printf("\nTotal: %d succeeded, %d failed out of %d URLs\n",
		len(successes), len(failures), len(urls))
}
```

Run with `go run main.go`. The critical design choice is using `Result{Value, Err}` rather than `errgroup` with first-error cancellation. With errgroup, a single DNS failure would cancel all in-flight requests and discard their results. The result-type pattern preserves every outcome, letting the caller decide what constitutes a fatal error versus an acceptable partial failure.'''),

    ("go_deep/context_cancellation_propagation", r'''How does context cancellation propagate through a tree of goroutines in Go? Write a program that creates a multi-level goroutine tree and demonstrates cancellation flowing from parent to all descendants.''', r'''<think>
Context cancellation in Go forms a tree structure that mirrors the goroutine hierarchy. When a parent context is cancelled, all derived child contexts are also cancelled. This is the fundamental mechanism for propagating shutdown signals.

Key points:
- context.WithCancel(parent) creates a child that is cancelled when parent is cancelled OR when the child's cancel function is called
- Cancellation flows DOWN the tree only — cancelling a child doesn't affect the parent or siblings
- ctx.Done() returns a channel that's closed when the context is cancelled
- ctx.Err() returns context.Canceled or context.DeadlineExceeded after cancellation

For the demo I want a multi-level tree:
- Root context with cancel
- Level 1: 2-3 goroutines with their own derived contexts
- Level 2: each level-1 goroutine spawns 2 children
- When root is cancelled, ALL should stop

I should show the timing — that cancellation is near-instantaneous because closing a channel wakes all receivers. The ctx.Done() channel is closed, which means every goroutine selecting on it gets woken simultaneously.

Also worth showing: cancelling a mid-level context only affects its subtree, not siblings. This is the most important property for understanding context trees.

One subtlety: context.WithCancel returns a cancel function. If you forget to call it (no defer cancel()), the context stays in the parent's child list forever, leaking memory. Go vet warns about this. Always defer cancel() immediately after creating a cancellable context.

Let me build a clean visual tree with indented output showing the cascade, and a second demo showing partial cancellation of a subtree.
</think>

Context cancellation propagates down the tree — cancelling a parent automatically cancels all descendants, but never affects parents or siblings. Here is a program that builds a goroutine tree and visualizes cancellation propagation:

```go
package main

import (
	"context"
	"fmt"
	"sync"
	"time"
)

func worker(ctx context.Context, name string, depth int, wg *sync.WaitGroup) {
	defer wg.Done()
	indent := ""
	for i := 0; i < depth; i++ {
		indent += "  "
	}
	fmt.Printf("%s[STARTED] %s\n", indent, name)

	<-ctx.Done() // block until cancelled

	fmt.Printf("%s[STOPPED] %s (reason: %v, lag: best-effort instant)\n", indent, name, ctx.Err())
}

func main() {
	fmt.Println("=== Demo 1: Root cancellation cascades to ALL descendants ===\n")

	rootCtx, rootCancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	// Level 1: two groups derived from root
	groupACtx, _ := context.WithCancel(rootCtx)
	groupBCtx, _ := context.WithCancel(rootCtx)

	// Level 2: children derived from each group
	childA1Ctx, _ := context.WithCancel(groupACtx)
	childA2Ctx, _ := context.WithCancel(groupACtx)
	childB1Ctx, _ := context.WithCancel(groupBCtx)

	// Level 3: grandchild derived from childA1
	grandchildCtx, _ := context.WithCancel(childA1Ctx)

	// Start all workers
	workers := []struct {
		ctx   context.Context
		name  string
		depth int
	}{
		{rootCtx, "root-worker", 0},
		{groupACtx, "group-A", 1},
		{groupBCtx, "group-B", 1},
		{childA1Ctx, "child-A1", 2},
		{childA2Ctx, "child-A2", 2},
		{childB1Ctx, "child-B1", 2},
		{grandchildCtx, "grandchild-A1-1", 3},
	}

	for _, w := range workers {
		wg.Add(1)
		go worker(w.ctx, w.name, w.depth, &wg)
	}

	time.Sleep(100 * time.Millisecond) // let all workers start
	fmt.Println("\n--- Cancelling ROOT context ---\n")
	rootCancel()
	wg.Wait()

	// Demo 2: Mid-level cancellation only affects subtree
	fmt.Println("\n=== Demo 2: Mid-level cancellation affects only subtree ===\n")

	rootCtx2, rootCancel2 := context.WithCancel(context.Background())
	defer rootCancel2()

	midCtx, midCancel := context.WithCancel(rootCtx2)
	siblingCtx, _ := context.WithCancel(rootCtx2)
	leafCtx, _ := context.WithCancel(midCtx)

	var wg2 sync.WaitGroup

	// Monitor function that reports status
	monitor := func(ctx context.Context, name string) {
		wg2.Add(1)
		go func() {
			defer wg2.Done()
			fmt.Printf("  [ALIVE] %s\n", name)
			select {
			case <-ctx.Done():
				fmt.Printf("  [DEAD]  %s — %v\n", name, ctx.Err())
			case <-time.After(500 * time.Millisecond):
				fmt.Printf("  [ALIVE] %s — survived (not in cancelled subtree)\n", name)
			}
		}()
	}

	monitor(rootCtx2, "root")
	monitor(midCtx, "mid-level")
	monitor(leafCtx, "leaf-of-mid")
	monitor(siblingCtx, "sibling")

	time.Sleep(50 * time.Millisecond)
	fmt.Println("\n--- Cancelling MID-LEVEL context (not root) ---\n")
	midCancel() // only mid and leaf should die; root and sibling survive

	wg2.Wait()

	fmt.Println("\nKey rules:")
	fmt.Println("  1. Cancellation flows DOWN only — parent → children → grandchildren")
	fmt.Println("  2. Siblings and parents are NOT affected")
	fmt.Println("  3. ctx.Done() channel is closed, waking ALL listeners simultaneously")
	fmt.Println("  4. Always defer cancel() to avoid context leaks")
}
```

Run with `go run main.go`. The output clearly shows that cancelling the root stops every goroutine in the tree, while cancelling a mid-level node only stops its subtree. The sibling and root survive. This is why `context.Context` should be threaded through every layer of concurrent code — it gives you a single kill switch for an entire call graph.'''),

    ("go_deep/context_timeout_vs_deadline", r'''What is the difference between context.WithTimeout and context.WithDeadline in Go? When should I use each? Write a program demonstrating both and showing how they interact with nested contexts.''', r'''<think>
WithTimeout and WithDeadline are closely related — in fact, WithTimeout is just syntactic sugar over WithDeadline. Looking at the Go source code:

func WithTimeout(parent Context, timeout time.Duration) (Context, CancelFunc) {
    return WithDeadline(parent, time.Now().Add(timeout))
}

So WithTimeout(ctx, 5*time.Second) is equivalent to WithDeadline(ctx, time.Now().Add(5*time.Second)).

When to use which:
- WithTimeout: when you think in terms of duration ("this operation should take at most 5 seconds")
- WithDeadline: when you have an absolute time ("this must finish by 2:00 PM" or "by the request deadline")

An important subtlety with nesting: a child context's deadline is always the EARLIER of its own deadline and its parent's deadline. You can't extend a parent's deadline by creating a child with a later deadline. This is a common gotcha — developers write WithTimeout(parentCtx, 5*time.Second) thinking they're giving the DB query 5 seconds, but if the parent only has 100ms left, the child effectively has 100ms.

How to check the effective deadline? Use ctx.Deadline() which returns the actual deadline (the earlier of parent and child). The ok return value tells you if a deadline is set at all.

In HTTP servers, the request context often has a deadline from the client or server timeout. Sub-operations should use WithTimeout on the request context so they automatically respect the overall request budget.

Let me demonstrate:
1. Basic WithTimeout vs WithDeadline — same behavior
2. Nested contexts where child has shorter timeout (works as expected)
3. Nested contexts where child has LONGER timeout (parent wins — the gotcha)
4. Practical example: HTTP handler with overall deadline, sub-operations with tighter timeouts
</think>

`context.WithTimeout(parent, duration)` is literally syntactic sugar for `context.WithDeadline(parent, time.Now().Add(duration))`. The real subtlety is in how they interact when nested — a child can never extend a parent's deadline.

```go
package main

import (
	"context"
	"fmt"
	"time"
)

func main() {
	// === 1. They are equivalent ===
	fmt.Println("=== WithTimeout vs WithDeadline: Equivalent ===")

	start := time.Now()

	ctx1, cancel1 := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel1()

	ctx2, cancel2 := context.WithDeadline(context.Background(), time.Now().Add(200*time.Millisecond))
	defer cancel2()

	dl1, _ := ctx1.Deadline()
	dl2, _ := ctx2.Deadline()
	fmt.Printf("  WithTimeout deadline:  %v from now\n", dl1.Sub(start).Round(time.Millisecond))
	fmt.Printf("  WithDeadline deadline: %v from now\n", dl2.Sub(start).Round(time.Millisecond))

	// === 2. Nested: child has SHORTER timeout (normal — child expires first) ===
	fmt.Println("\n=== Nested: Child Shorter Than Parent ===")

	parent, parentCancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer parentCancel()

	child, childCancel := context.WithTimeout(parent, 100*time.Millisecond)
	defer childCancel()

	<-child.Done()
	elapsed := time.Since(start).Round(time.Millisecond)
	fmt.Printf("  child expired at ~%v (its own 100ms timeout)\n", elapsed)
	fmt.Printf("  child err: %v\n", child.Err())

	// Parent is still alive
	select {
	case <-parent.Done():
		fmt.Println("  parent also expired (unexpected)")
	default:
		fmt.Println("  parent still alive (correct — 500ms hasn't elapsed)")
	}

	// === 3. THE GOTCHA: child with LONGER timeout (parent wins) ===
	fmt.Println("\n=== Nested: Child LONGER Than Parent (Gotcha!) ===")

	start2 := time.Now()
	shortParent, spCancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer spCancel()

	// Developer thinks: "I'll give the DB query 5 seconds"
	// But parent only has 100ms! The child will NEVER get 5 seconds.
	longChild, lcCancel := context.WithTimeout(shortParent, 5*time.Second)
	defer lcCancel()

	dl, _ := longChild.Deadline()
	fmt.Printf("  child requested deadline: 5s from now\n")
	fmt.Printf("  child actual deadline:    %v from now (clamped to parent!)\n",
		dl.Sub(start2).Round(time.Millisecond))

	<-longChild.Done()
	fmt.Printf("  child expired after %v (parent's 100ms, NOT child's 5s)\n",
		time.Since(start2).Round(time.Millisecond))
	fmt.Printf("  child err: %v\n", longChild.Err())

	// === 4. Practical: when to use which ===
	fmt.Println("\n=== Practical: HTTP Handler with Sub-Operation Timeouts ===")

	// Simulate: HTTP handler has an absolute deadline (from the request)
	requestDeadline := time.Now().Add(300 * time.Millisecond)
	reqCtx, reqCancel := context.WithDeadline(context.Background(), requestDeadline)
	defer reqCancel()

	// Sub-operation 1: DB query — use WithTimeout for relative budget
	dbCtx, dbCancel := context.WithTimeout(reqCtx, 100*time.Millisecond)
	defer dbCancel()
	start3 := time.Now()
	simulateWork(dbCtx, "db-query", 50*time.Millisecond)
	fmt.Printf("  db-query finished in %v\n", time.Since(start3).Round(time.Millisecond))

	// Sub-operation 2: external API call — also relative budget
	apiCtx, apiCancel := context.WithTimeout(reqCtx, 150*time.Millisecond)
	defer apiCancel()
	start4 := time.Now()
	simulateWork(apiCtx, "api-call", 80*time.Millisecond)
	fmt.Printf("  api-call finished in %v\n", time.Since(start4).Round(time.Millisecond))

	// Check remaining budget
	remaining := time.Until(requestDeadline)
	fmt.Printf("  remaining request budget: %v\n", remaining.Round(time.Millisecond))

	fmt.Println("\nGuidelines:")
	fmt.Println("  WithTimeout: relative durations ('at most 5s for this call')")
	fmt.Println("  WithDeadline: absolute times ('finish by request deadline')")
	fmt.Println("  GOTCHA: child CANNOT extend parent's deadline — always clamped")
	fmt.Println("  TIP: check deadline with ctx.Deadline() to see effective time remaining")
}

func simulateWork(ctx context.Context, name string, workTime time.Duration) {
	select {
	case <-time.After(workTime):
		// work completed
	case <-ctx.Done():
		fmt.Printf("  %s cancelled: %v\n", name, ctx.Err())
	}
}
```

Run with `go run main.go`. The most important takeaway is the gotcha in section 3: `context.WithTimeout(parent, 5*time.Second)` does NOT guarantee 5 seconds if the parent has a shorter deadline. Always check the effective deadline with `ctx.Deadline()` if your logic depends on it.'''),

    ("go_deep/waitgroup_patterns_pitfalls", r'''What are the common pitfalls with sync.WaitGroup in Go? Show me the correct patterns and the bugs that happen when you get it wrong.''', r'''<think>
WaitGroup pitfalls — let me enumerate the common ones carefully.
Pitfall 1: calling wg.Add() inside the goroutine instead of before it.
This is a race condition — the main goroutine might reach wg.Wait() before the child goroutine even starts.
It works 99% of the time in testing but fails under production load when the scheduler doesn't run the child before main.
Pitfall 2: forgetting defer wg.Done().
If the goroutine panics or hits an early return, Done is never called, and Wait blocks forever.
This is the most common cause of "my program hangs on shutdown."
Pitfall 3: passing WaitGroup by value instead of by pointer.
WaitGroup contains internal state — copying creates an independent counter.
Done() on the copy doesn't decrement the original's counter. Wait() on the original blocks forever.
Go vet catches this with the copylocks analyzer, but many teams don't run vet in CI.
Pitfall 4: calling Add with a negative delta that makes the counter go below zero — runtime panic.
This usually happens when Done() is called more times than Add() due to a loop logic bug.
Pitfall 5: reusing a WaitGroup before Wait returns — race condition on internal state.
Pitfall 6: the Add-before-go rule. Add(1) must happen BEFORE the go statement, not inside the goroutine.
Batch Add(n) before the loop is cleaner when you know the count upfront.
What about defer vs explicit Done()? If you defer wg.Done() and the goroutine panics, Done still runs.
But if you call wg.Done() at the end without defer, a panic skips it entirely.
This asymmetry is why defer wg.Done() is non-negotiable — it's correct in all cases.
The -race detector does NOT catch the pass-by-value bug since no data race occurs — it's a logic bug.
Only static analysis (go vet copylocks linter) detects it automatically.
Let me demonstrate each pitfall with before/after examples showing the bug and the fix.
</think>

`sync.WaitGroup` is deceptively simple but has several sharp edges. Here are the common pitfalls and correct patterns:

```go
package main

import (
	"fmt"
	"sync"
	"time"
)

// ============================================================
// BUG 1: Add() inside goroutine — race with Wait()
// ============================================================
func bugAddInsideGoroutine() {
	fmt.Println("=== BUG 1: Add() inside goroutine ===")
	var wg sync.WaitGroup

	for i := 0; i < 5; i++ {
		go func(id int) {
			wg.Add(1) // BUG: race! main might call Wait() before this runs
			defer wg.Done()
			fmt.Printf("  worker %d\n", id)
		}(i)
	}
	wg.Wait() // might return immediately if no goroutine has called Add yet!
	fmt.Println("  (may print 0-5 workers — race condition)\n")
}

func fixedAddBeforeGoroutine() {
	fmt.Println("=== FIX 1: Add() BEFORE go statement ===")
	var wg sync.WaitGroup

	for i := 0; i < 5; i++ {
		wg.Add(1) // CORRECT: Add in the launching goroutine, before go
		go func(id int) {
			defer wg.Done()
			fmt.Printf("  worker %d\n", id)
		}(i)
	}
	wg.Wait() // guaranteed to wait for all 5
	fmt.Println("  (always prints all 5 workers)\n")
}

// ============================================================
// BUG 2: Missing defer — early return or panic skips Done()
// ============================================================
func bugMissingDefer() {
	fmt.Println("=== BUG 2: Done() without defer ===")
	var wg sync.WaitGroup

	wg.Add(1)
	go func() {
		// If this function has multiple return paths or panics,
		// Done() might never be called
		result, err := riskyOperation()
		if err != nil {
			fmt.Printf("  error: %v — returning WITHOUT calling Done!\n", err)
			return // BUG: wg.Done() never called, Wait() blocks forever
		}
		fmt.Printf("  result: %s\n", result)
		wg.Done() // only reached on success path
	}()

	// Use a timeout to avoid actually hanging
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()
	select {
	case <-done:
		fmt.Println("  completed")
	case <-time.After(200 * time.Millisecond):
		fmt.Println("  DEADLOCK: Wait() blocked forever because Done() was skipped\n")
	}
}

func fixedWithDefer() {
	fmt.Println("=== FIX 2: Always use defer wg.Done() ===")
	var wg sync.WaitGroup

	wg.Add(1)
	go func() {
		defer wg.Done() // CORRECT: always runs, even on panic or early return
		_, err := riskyOperation()
		if err != nil {
			fmt.Printf("  error: %v — but Done() still called via defer\n", err)
			return
		}
	}()
	wg.Wait()
	fmt.Println("  completed normally\n")
}

// ============================================================
// BUG 3: Passing WaitGroup by value (copies don't share state)
// ============================================================
func bugPassByValue() {
	fmt.Println("=== BUG 3: WaitGroup passed by value ===")
	var wg sync.WaitGroup
	wg.Add(1)

	// This passes a COPY of wg — Done() on the copy doesn't affect original
	go doWorkBroken(wg, "value-copy")

	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()
	select {
	case <-done:
		fmt.Println("  completed")
	case <-time.After(200 * time.Millisecond):
		fmt.Println("  DEADLOCK: Done() called on copy, not original\n")
	}
}

func doWorkBroken(wg sync.WaitGroup, name string) { // BUG: value receiver
	defer wg.Done() // this calls Done on the copy!
	fmt.Printf("  %s: working\n", name)
}

func fixedPassByPointer() {
	fmt.Println("=== FIX 3: Pass *sync.WaitGroup (pointer) ===")
	var wg sync.WaitGroup
	wg.Add(1)
	go doWorkFixed(&wg, "pointer")
	wg.Wait()
	fmt.Println("  completed normally\n")
}

func doWorkFixed(wg *sync.WaitGroup, name string) { // CORRECT: pointer receiver
	defer wg.Done()
	fmt.Printf("  %s: working\n", name)
}

// ============================================================
// BUG 4: Negative counter — panics at runtime
// ============================================================
func bugNegativeCounter() {
	fmt.Println("=== BUG 4: Counter goes negative (panic) ===")
	defer func() {
		if r := recover(); r != nil {
			fmt.Printf("  PANIC: %v\n\n", r)
		}
	}()
	var wg sync.WaitGroup
	wg.Add(1)
	wg.Done()
	wg.Done() // BUG: counter is already 0, this makes it -1 → panic
}

// ============================================================
// PATTERN: Batch Add for known count
// ============================================================
func patternBatchAdd() {
	fmt.Println("=== PATTERN: Batch Add(n) for known count ===")
	var wg sync.WaitGroup
	tasks := []string{"alpha", "beta", "gamma", "delta"}

	wg.Add(len(tasks)) // add all at once — clean and safe
	for _, t := range tasks {
		go func(task string) {
			defer wg.Done()
			fmt.Printf("  processing: %s\n", task)
		}(t)
	}
	wg.Wait()
	fmt.Println("  all done\n")
}

func riskyOperation() (string, error) {
	return "", fmt.Errorf("simulated failure")
}

func main() {
	bugAddInsideGoroutine()
	time.Sleep(50 * time.Millisecond) // let stragglers print
	fixedAddBeforeGoroutine()
	bugMissingDefer()
	fixedWithDefer()
	bugPassByValue()
	fixedPassByPointer()
	bugNegativeCounter()
	patternBatchAdd()

	fmt.Println("Summary of WaitGroup rules:")
	fmt.Println("  1. Call Add() BEFORE the go statement, never inside")
	fmt.Println("  2. ALWAYS use defer wg.Done()")
	fmt.Println("  3. Pass *sync.WaitGroup (pointer), never by value")
	fmt.Println("  4. Never let the counter go negative")
	fmt.Println("  5. Use Add(n) for known batch sizes")
}
```

Run with `go run main.go`. The three most common bugs — `Add` inside the goroutine, missing `defer`, and passing by value — are all silent in testing but cause intermittent deadlocks or race conditions in production. The `-race` detector catches some of these, but not the by-value copy bug since it does not involve a data race.'''),

    ("go_deep/mutex_vs_rwmutex", r'''When should I use sync.RWMutex instead of sync.Mutex in Go? Write a benchmark showing when RWMutex actually helps and when it hurts.''', r'''<think>
RWMutex allows multiple concurrent readers OR one exclusive writer. The theory is that for read-heavy workloads, RWMutex should be faster because readers don't block each other.

But there's a subtlety: RWMutex has higher overhead per operation than Mutex because it needs to manage reader counts atomically. So for very short critical sections, the overhead of RWMutex can outweigh the parallelism benefit.

When RWMutex wins:
- Many more reads than writes (10:1 or higher ratio)
- Critical section is non-trivial (enough work inside the lock to amortize the overhead)
- High contention (many goroutines competing)

When RWMutex loses:
- Balanced read/write ratio
- Very short critical sections (the atomic operations in RLock/RUnlock dominate)
- Low contention (no goroutines waiting anyway)

Another gotcha: RWMutex has writer starvation prevention — when a writer is waiting, new readers are blocked. This is good for fairness but means reads can still be blocked by pending writes.

For the benchmark, I'll use Go's testing.B framework with a benchmark file. But since the user might want a standalone program, I'll write a self-contained benchmarking program with manual timing.

Let me show:
1. Read-heavy (95% read / 5% write) — RWMutex should win
2. Write-heavy (50% read / 50% write) — Mutex should win or be equal
3. Short vs long critical sections
</think>

`sync.RWMutex` allows concurrent readers but has higher per-operation overhead than `sync.Mutex`. It only helps when reads vastly outnumber writes AND the critical section is long enough to amortize the overhead.

```go
package main

import (
	"fmt"
	"sync"
	"time"
)

type MutexMap struct {
	mu   sync.Mutex
	data map[string]int
}

func (m *MutexMap) Get(key string) int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.data[key]
}

func (m *MutexMap) Set(key string, val int) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.data[key] = val
}

type RWMutexMap struct {
	mu   sync.RWMutex
	data map[string]int
}

func (m *RWMutexMap) Get(key string) int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.data[key]
}

func (m *RWMutexMap) Set(key string, val int) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.data[key] = val
}

type MapInterface interface {
	Get(key string) int
	Set(key string, val int)
}

func benchmark(name string, m MapInterface, numGoroutines, opsPerGoroutine int, readPct float64, workInLock time.Duration) time.Duration {
	// Pre-populate
	if mm, ok := m.(*MutexMap); ok {
		for i := 0; i < 100; i++ {
			mm.data[fmt.Sprintf("key%d", i)] = i
		}
	} else if rm, ok := m.(*RWMutexMap); ok {
		for i := 0; i < 100; i++ {
			rm.data[fmt.Sprintf("key%d", i)] = i
		}
	}

	var wg sync.WaitGroup
	start := time.Now()

	for g := 0; g < numGoroutines; g++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			for i := 0; i < opsPerGoroutine; i++ {
				key := fmt.Sprintf("key%d", i%100)
				isRead := float64(i%100)/100.0 < readPct

				if isRead {
					_ = m.Get(key)
				} else {
					m.Set(key, i)
				}

				// Simulate work inside the critical section being expensive
				if workInLock > 0 {
					time.Sleep(workInLock)
				}
			}
		}(g)
	}

	wg.Wait()
	return time.Since(start)
}

func main() {
	scenarios := []struct {
		name       string
		goroutines int
		opsEach    int
		readPct    float64
		workInLock time.Duration
	}{
		{"95%% read, short lock, 8 goroutines", 8, 10000, 0.95, 0},
		{"95%% read, 1us lock,  8 goroutines", 8, 5000, 0.95, time.Microsecond},
		{"50%% read, short lock, 8 goroutines", 8, 10000, 0.50, 0},
		{"50%% read, 1us lock,  8 goroutines", 8, 5000, 0.50, time.Microsecond},
		{"99%% read, short lock, 16 goroutines", 16, 5000, 0.99, 0},
		{"99%% read, 1us lock,  16 goroutines", 16, 2000, 0.99, time.Microsecond},
	}

	fmt.Printf("%-45s %12s %12s %10s\n", "Scenario", "Mutex", "RWMutex", "Winner")
	fmt.Println(string(make([]byte, 85)))

	for _, s := range scenarios {
		mutexMap := &MutexMap{data: make(map[string]int)}
		rwMap := &RWMutexMap{data: make(map[string]int)}

		mutexTime := benchmark("mutex", mutexMap, s.goroutines, s.opsEach, s.readPct, s.workInLock)
		rwTime := benchmark("rwmutex", rwMap, s.goroutines, s.opsEach, s.readPct, s.workInLock)

		winner := "Mutex"
		if rwTime < mutexTime {
			winner = "RWMutex"
		}

		fmt.Printf("%-45s %12v %12v %10s\n", s.name, mutexTime.Round(time.Millisecond), rwTime.Round(time.Millisecond), winner)
	}

	fmt.Println("\nKey findings:")
	fmt.Println("  - RWMutex wins with high read ratio (95%+) AND non-trivial lock hold time")
	fmt.Println("  - For short critical sections, Mutex often wins due to lower overhead")
	fmt.Println("  - At 50/50 read/write, RWMutex overhead makes it slower or equal")
	fmt.Println("  - RWMutex has writer-starvation prevention: pending writer blocks new readers")
	fmt.Println("  - Rule of thumb: start with Mutex, switch to RWMutex only after profiling")
}
```

Run with `go run main.go`. The results will vary by machine, but the pattern is consistent: RWMutex only wins when reads dominate (95%+) and the critical section holds the lock long enough for reader parallelism to matter. For trivial map lookups with no simulated work, plain `sync.Mutex` is often faster because `RLock`/`RUnlock` use atomic operations on a shared reader counter, which causes cache-line bouncing across cores.'''),

    ("go_deep/sync_once_error_handling", r'''sync.Once in Go guarantees a function runs exactly once, but what if that function fails? Show me patterns for lazy initialization with error handling using sync.Once.''', r'''<think>
sync.Once has a well-known limitation with error handling.
If the function passed to Do() panics or returns an error, Once still considers it "done."
It will never retry. A transient error permanently poisons the initialization.
Patterns to handle this:
1. Retry with custom once: mutex + bool, only set bool on success
2. Store the error: accept once-only, but cache the error for callers to check
3. sync.OnceValues (Go 1.21+): returns both value and error, still runs once
4. OnceFunc (Go 1.21+): convenience wrapper for functions with no return
sync.OnceValues is the modern approach but it still runs exactly once.
If init fails, it fails permanently. That's by design — exactly-once, not at-least-once-successful.
For retry-on-error, you need a custom implementation.
Key insight: mark "done" only on success using mutex + bool flag.
sync.Once's internal flag is set before the function even returns, so you can't use it.
What if init panics? sync.Once marks it done even on panic.
Custom RetryableOnce should let panics propagate but not mark done, allowing retry.
Concurrent access during retry window: multiple goroutines might attempt init simultaneously.
The mutex serializes them — correct behavior, we don't want N goroutines retrying at once.
Only one goroutine retries while others wait on the mutex.
Let me show three approaches: the problem, OnceValues, and custom RetryableOnce.
</think>

`sync.Once` considers the function "done" even if it panics or the initialization fails. A transient error permanently poisons the singleton. Here are patterns to handle this:

```go
package main

import (
	"errors"
	"fmt"
	"math/rand"
	"sync"
	"time"
)

// ============================================================
// Problem: sync.Once never retries after failure
// ============================================================
func demoProblem() {
	fmt.Println("=== PROBLEM: sync.Once never retries ===")
	var once sync.Once
	var conn string

	callCount := 0
	initConn := func() {
		callCount++
		fmt.Printf("  init attempt #%d\n", callCount)
		// Simulate: first call fails, but Once will never retry
		panic("connection refused") // or just set conn="" with an error
	}

	for i := 0; i < 3; i++ {
		func() {
			defer func() { recover() }()
			once.Do(initConn)
		}()
		fmt.Printf("  after attempt %d: conn=%q, total init calls=%d\n", i+1, conn, callCount)
	}
	fmt.Println("  Result: init ran ONCE, failed, and Once will NEVER retry\n")
}

// ============================================================
// Pattern 1: Store value + error, check error on access (Go 1.21+)
// ============================================================
// sync.OnceValues runs the function exactly once and caches both return values.
// This is clean but does NOT retry on failure.
func demoOnceValues() {
	fmt.Println("=== PATTERN 1: sync.OnceValues (Go 1.21+) ===")

	loadConfig := sync.OnceValues(func() (map[string]string, error) {
		fmt.Println("  loading config (runs exactly once)...")
		// Simulate success
		return map[string]string{"db_host": "localhost", "db_port": "5432"}, nil
	})

	// Multiple goroutines can call this safely
	var wg sync.WaitGroup
	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			cfg, err := loadConfig()
			if err != nil {
				fmt.Printf("  goroutine %d: config error: %v\n", id, err)
				return
			}
			fmt.Printf("  goroutine %d: db_host=%s\n", id, cfg["db_host"])
		}(i)
	}
	wg.Wait()
	fmt.Println()
}

// ============================================================
// Pattern 2: RetryableOnce — retries on failure, locks on success
// ============================================================
type RetryableOnce struct {
	mu   sync.Mutex
	done bool
}

func (o *RetryableOnce) Do(fn func() error) error {
	// Fast path: already initialized successfully
	o.mu.Lock()
	defer o.mu.Unlock()

	if o.done {
		return nil
	}

	err := fn()
	if err == nil {
		o.done = true // only mark done on success
	}
	return err
}

func demoRetryableOnce() {
	fmt.Println("=== PATTERN 2: RetryableOnce (retries on failure) ===")

	var once RetryableOnce
	var dbConn string
	attempts := 0

	connect := func() error {
		attempts++
		fmt.Printf("  connect attempt #%d\n", attempts)
		// Simulate: fails 60% of the time
		if rand.Float64() < 0.6 {
			return errors.New("connection refused")
		}
		dbConn = "postgres://localhost:5432/mydb"
		return nil
	}

	// Keep trying until success
	for i := 0; i < 10; i++ {
		err := once.Do(connect)
		if err != nil {
			fmt.Printf("  attempt %d failed: %v\n", i+1, err)
			time.Sleep(10 * time.Millisecond) // backoff
			continue
		}
		fmt.Printf("  connected on attempt %d: %s\n", i+1, dbConn)
		break
	}

	// Subsequent calls are no-ops (already succeeded)
	err := once.Do(connect)
	fmt.Printf("  subsequent call: err=%v, attempts=%d (no new attempt)\n\n", err, attempts)
}

// ============================================================
// Pattern 3: Lazy singleton with atomic check + error caching
// ============================================================
type DBPool struct {
	connStr string
	ready   bool
}

type LazyDB struct {
	mu   sync.Mutex
	pool *DBPool
	err  error
	init func() (*DBPool, error)
}

func NewLazyDB(initFn func() (*DBPool, error)) *LazyDB {
	return &LazyDB{init: initFn}
}

func (l *LazyDB) Get() (*DBPool, error) {
	l.mu.Lock()
	defer l.mu.Unlock()

	if l.pool != nil {
		return l.pool, nil
	}
	if l.err != nil {
		return nil, fmt.Errorf("permanently failed: %w", l.err)
	}

	pool, err := l.init()
	if err != nil {
		l.err = err // cache error permanently (or omit this for retry)
		return nil, err
	}
	l.pool = pool
	return l.pool, nil
}

func demoLazySingleton() {
	fmt.Println("=== PATTERN 3: Lazy Singleton with Error Caching ===")

	db := NewLazyDB(func() (*DBPool, error) {
		fmt.Println("  initializing pool...")
		return &DBPool{connStr: "postgres://localhost/app", ready: true}, nil
	})

	// Concurrent access
	var wg sync.WaitGroup
	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			pool, err := db.Get()
			if err != nil {
				fmt.Printf("  goroutine %d: error: %v\n", id, err)
				return
			}
			fmt.Printf("  goroutine %d: pool ready=%v\n", id, pool.ready)
		}(i)
	}
	wg.Wait()
}

func main() {
	demoProblem()
	demoOnceValues()
	demoRetryableOnce()
	demoLazySingleton()

	fmt.Println("\nGuidelines:")
	fmt.Println("  sync.Once: infallible init only (no errors possible)")
	fmt.Println("  sync.OnceValues: fallible init, error cached, no retry (Go 1.21+)")
	fmt.Println("  RetryableOnce: fallible init that MUST eventually succeed")
	fmt.Println("  LazyDB pattern: fallible init with permanent error caching")
}
```

Run with `go run main.go`. The core insight is that `sync.Once` was designed for infallible initialization. If your init can fail, use `sync.OnceValues` (Go 1.21+) when failure is permanent, or the `RetryableOnce` pattern when you need to keep trying until success.'''),

    ("go_deep/sync_pool_gc_pressure", r'''How does sync.Pool reduce GC pressure in Go? Write a program that demonstrates measurable GC improvement using sync.Pool for a high-allocation workload.''', r'''<think>
sync.Pool reduces GC pressure by reusing temporary objects. Let me think through the design.
Objects in the pool may be garbage collected at any time between GC cycles.
Pool is per-P (not per-CPU) to reduce contention — each P has private and shared victim caches.
The pool is drained on each GC cycle — don't use it for long-lived caching.
Use case: short-lived objects allocated/freed at high frequency (buffers, encoders).
For demonstrating improvement I need a controlled benchmark:
1. Run workload without pool (allocate/discard buffers each iteration)
2. Same workload with pool (Get/Put reuses buffers)
3. Compare using runtime.MemStats: Mallocs, TotalAlloc, NumGC, PauseTotalNs
The key metrics: Mallocs counts total heap allocations.
TotalAlloc is cumulative bytes. NumGC is GC cycle count. PauseTotalNs is total pause time.
Common gotcha: must reset objects before Put(). Stale data in pooled buffers can leak between requests.
In web servers this is a security vulnerability — response data from one user leaking to another.
Another gotcha: Pool.New should return a pointer to avoid interface boxing allocation.
Putting a non-pointer into interface{} causes a heap alloc. Use *[]byte not []byte.
Real-world usage: bytes.Buffer pooling for JSON encoding, HTTP responses, log formatting.
The standard library's fmt package uses sync.Pool internally for this reason.
Let me show both raw byte slice pools and bytes.Buffer pools.
</think>

`sync.Pool` maintains a per-CPU cache of reusable objects that reduces allocation frequency and GC pressure. Objects may be evicted between GC cycles, so Pool is for temporary, high-churn objects — not long-lived caches.

```go
package main

import (
	"bytes"
	"fmt"
	"runtime"
	"sync"
	"time"
)

const (
	numOps    = 500_000
	bufSize   = 4096
	numWorkers = 8
)

var bufPool = sync.Pool{
	New: func() any {
		buf := make([]byte, 0, bufSize)
		return &buf // return pointer to avoid interface boxing allocation
	},
}

// simulateWork does some byte manipulation to make the allocation realistic
func simulateWork(buf []byte) int {
	for i := range buf {
		buf[i] = byte(i % 256)
	}
	sum := 0
	for _, b := range buf {
		sum += int(b)
	}
	return sum
}

func withoutPool() (time.Duration, runtime.MemStats) {
	runtime.GC()
	var before runtime.MemStats
	runtime.ReadMemStats(&before)

	start := time.Now()
	var wg sync.WaitGroup
	opsPerWorker := numOps / numWorkers

	for w := 0; w < numWorkers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			sink := 0
			for i := 0; i < opsPerWorker; i++ {
				buf := make([]byte, bufSize) // allocate every time
				sink += simulateWork(buf)
				// buf becomes garbage immediately
			}
			_ = sink
		}()
	}
	wg.Wait()
	elapsed := time.Since(start)

	var after runtime.MemStats
	runtime.ReadMemStats(&after)

	// Return delta stats
	after.Mallocs -= before.Mallocs
	after.TotalAlloc -= before.TotalAlloc
	after.NumGC -= before.NumGC
	after.PauseTotalNs -= before.PauseTotalNs
	return elapsed, after
}

func withPool() (time.Duration, runtime.MemStats) {
	runtime.GC()
	var before runtime.MemStats
	runtime.ReadMemStats(&before)

	start := time.Now()
	var wg sync.WaitGroup
	opsPerWorker := numOps / numWorkers

	for w := 0; w < numWorkers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			sink := 0
			for i := 0; i < opsPerWorker; i++ {
				bufPtr := bufPool.Get().(*[]byte)
				buf := (*bufPtr)[:bufSize] // reset length
				sink += simulateWork(buf)
				*bufPtr = buf[:0] // reset before returning — CRITICAL
				bufPool.Put(bufPtr)
			}
			_ = sink
		}()
	}
	wg.Wait()
	elapsed := time.Since(start)

	var after runtime.MemStats
	runtime.ReadMemStats(&after)

	after.Mallocs -= before.Mallocs
	after.TotalAlloc -= before.TotalAlloc
	after.NumGC -= before.NumGC
	after.PauseTotalNs -= before.PauseTotalNs
	return elapsed, after
}

// Also demonstrate bytes.Buffer pool — the most common real-world use
func bytesBufferPoolDemo() {
	fmt.Println("\n=== bytes.Buffer Pool (Common Real-World Pattern) ===")

	pool := sync.Pool{
		New: func() any {
			return new(bytes.Buffer)
		},
	}

	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			buf := pool.Get().(*bytes.Buffer)
			buf.Reset() // always reset before use
			fmt.Fprintf(buf, "request-%d: processed at %v", id, time.Now().Format(time.RFC3339Nano))
			result := buf.String()
			buf.Reset() // reset before returning
			pool.Put(buf)
			_ = result
		}(i)
	}
	wg.Wait()
	fmt.Println("  bytes.Buffer pool: 10 requests processed with buffer reuse")
}

func main() {
	fmt.Println("=== sync.Pool GC Pressure Benchmark ===")
	fmt.Printf("Config: %d ops, %d workers, %d byte buffers\n\n", numOps, numWorkers, bufSize)

	// Warm up
	runtime.GC()

	noPoolTime, noPoolStats := withoutPool()
	poolTime, poolStats := withPool()

	fmt.Printf("%-20s %15s %15s\n", "Metric", "No Pool", "With Pool")
	fmt.Println(string(make([]byte, 55)))
	fmt.Printf("%-20s %15v %15v\n", "Time", noPoolTime.Round(time.Millisecond), poolTime.Round(time.Millisecond))
	fmt.Printf("%-20s %15d %15d\n", "Mallocs", noPoolStats.Mallocs, poolStats.Mallocs)
	fmt.Printf("%-20s %12d KB %12d KB\n", "TotalAlloc", noPoolStats.TotalAlloc/1024, poolStats.TotalAlloc/1024)
	fmt.Printf("%-20s %15d %15d\n", "GC cycles", noPoolStats.NumGC, poolStats.NumGC)
	fmt.Printf("%-20s %12v %12v\n", "GC pause total",
		time.Duration(noPoolStats.PauseTotalNs).Round(time.Microsecond),
		time.Duration(poolStats.PauseTotalNs).Round(time.Microsecond))

	if noPoolStats.Mallocs > 0 {
		reduction := float64(noPoolStats.Mallocs-poolStats.Mallocs) / float64(noPoolStats.Mallocs) * 100
		fmt.Printf("\nAllocation reduction: %.1f%%\n", reduction)
	}

	bytesBufferPoolDemo()

	fmt.Println("\nRules for sync.Pool:")
	fmt.Println("  1. ALWAYS Reset/clear objects before Put() — prevent data leaks")
	fmt.Println("  2. ALWAYS re-check/reset after Get() — pool may return stale objects")
	fmt.Println("  3. Pool is drained every GC cycle — not a cache, just allocation amortizer")
	fmt.Println("  4. Store pointers in Pool.New to avoid interface boxing allocations")
	fmt.Println("  5. Best for: byte buffers, encoder/decoder state, temporary structs")
}
```

Run with `go run main.go`. You should see a significant reduction in both allocation count and GC pause time with the pool. The pool works because instead of allocating 500K buffers that immediately become garbage, it reuses a small set of buffers (roughly numWorkers * 2 due to per-P caching), dropping the allocation count by orders of magnitude.'''),

    ("go_deep/sync_map_vs_mutex_map", r'''When should I use sync.Map vs a mutex-protected map in Go? Write a benchmark comparing both under different access patterns.''', r'''<think>
sync.Map is optimized for two specific patterns:
1. Keys written once but read many times (append-only / stable key set)
2. Multiple goroutines read/write disjoint sets of keys (per-connection state)
For general mixed read/write with overlapping keys, mutex+map is faster.
The Go docs say: "Most code should use a plain Go map, with separate locking."
Internally, sync.Map uses a read-only map (lock-free atomic load) and a dirty map (mutex).
Reads check the read-only map first — fast path, no lock needed.
Writes go to the dirty map. Periodically dirty is promoted to read-only.
Consequences of this design:
- Reads after stabilization are lock-free (just atomic.LoadPointer)
- Frequent writes prevent stabilization — each miss triggers promotion
- Type assertions needed on every Load (stores any/interface{})
- No Len() method — must Range() and count
- No iteration safety guarantee during concurrent modification
Memory: sync.Map maintains two copies during promotion — temporarily doubles memory.
No generic sync.Map as of Go 1.23 — type assertions on every Load are a runtime and readability cost.
A generic RWMutex+map wrapper gives type safety for free with better performance in most cases.
What about delete-heavy workloads? sync.Map handles deletes by marking entries as "expunged" in the read-only map.
These tombstones accumulate until the next promotion, which can waste memory.
Let me benchmark read-heavy, write-heavy, mixed, and disjoint vs shared key patterns.
</think>

`sync.Map` is optimized for two specific patterns: (1) append-only keys read many times, and (2) disjoint key sets per goroutine. For general mixed access, `mutex + map` is faster. Here is a benchmark proving it:

```go
package main

import (
	"fmt"
	"strconv"
	"sync"
	"time"
)

// Mutex-protected map
type MutexMap struct {
	mu sync.RWMutex
	m  map[string]int
}

func NewMutexMap() *MutexMap {
	return &MutexMap{m: make(map[string]int)}
}

func (m *MutexMap) Load(key string) (int, bool) {
	m.mu.RLock()
	v, ok := m.m[key]
	m.mu.RUnlock()
	return v, ok
}

func (m *MutexMap) Store(key string, val int) {
	m.mu.Lock()
	m.m[key] = val
	m.mu.Unlock()
}

// Benchmark harness
func benchMutexMap(numGoroutines, opsPerG int, readPct float64, disjoint bool) time.Duration {
	m := NewMutexMap()
	// Pre-populate
	for i := 0; i < 1000; i++ {
		m.Store(strconv.Itoa(i), i)
	}

	var wg sync.WaitGroup
	start := time.Now()

	for g := 0; g < numGoroutines; g++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			for i := 0; i < opsPerG; i++ {
				var key string
				if disjoint {
					key = strconv.Itoa(id*opsPerG + i%100)
				} else {
					key = strconv.Itoa(i % 1000)
				}

				if float64(i%100)/100.0 < readPct {
					m.Load(key)
				} else {
					m.Store(key, i)
				}
			}
		}(g)
	}
	wg.Wait()
	return time.Since(start)
}

func benchSyncMap(numGoroutines, opsPerG int, readPct float64, disjoint bool) time.Duration {
	var m sync.Map
	// Pre-populate
	for i := 0; i < 1000; i++ {
		m.Store(strconv.Itoa(i), i)
	}

	var wg sync.WaitGroup
	start := time.Now()

	for g := 0; g < numGoroutines; g++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			for i := 0; i < opsPerG; i++ {
				var key string
				if disjoint {
					key = strconv.Itoa(id*opsPerG + i%100)
				} else {
					key = strconv.Itoa(i % 1000)
				}

				if float64(i%100)/100.0 < readPct {
					m.Load(key)
				} else {
					m.Store(key, i)
				}
			}
		}(g)
	}
	wg.Wait()
	return time.Since(start)
}

func main() {
	scenarios := []struct {
		name     string
		readers  int
		opsPerG  int
		readPct  float64
		disjoint bool
	}{
		{"99%% read, shared keys, 8g", 8, 100_000, 0.99, false},
		{"90%% read, shared keys, 8g", 8, 100_000, 0.90, false},
		{"50%% read, shared keys, 8g", 8, 100_000, 0.50, false},
		{"10%% read, shared keys, 8g", 8, 100_000, 0.10, false},
		{"99%% read, disjoint keys, 8g", 8, 100_000, 0.99, true},
		{"50%% read, disjoint keys, 8g", 8, 100_000, 0.50, true},
	}

	fmt.Printf("%-40s %12s %12s %10s\n", "Scenario", "RWMutex+Map", "sync.Map", "Winner")
	fmt.Println(string(make([]byte, 78)))

	for _, s := range scenarios {
		mutexTime := benchMutexMap(s.readers, s.opsPerG, s.readPct, s.disjoint)
		syncTime := benchSyncMap(s.readers, s.opsPerG, s.readPct, s.disjoint)

		winner := "RWMutex+Map"
		if syncTime < mutexTime {
			winner = "sync.Map"
		}

		fmt.Printf("%-40s %12v %12v %10s\n",
			s.name,
			mutexTime.Round(time.Millisecond),
			syncTime.Round(time.Millisecond),
			winner)
	}

	fmt.Println("\nWhen to use sync.Map:")
	fmt.Println("  - Keys written once, read millions of times (config, caches)")
	fmt.Println("  - Each goroutine accesses its own key set (per-connection state)")
	fmt.Println("  - You need concurrent iteration with Range() during mutations")

	fmt.Println("\nWhen to use RWMutex + map:")
	fmt.Println("  - General-purpose concurrent map (most cases)")
	fmt.Println("  - Mixed read/write to overlapping keys")
	fmt.Println("  - You need type safety (sync.Map uses any)")
	fmt.Println("  - You need Len(), delete-heavy workloads, or custom logic in critical section")

	fmt.Println("\nRule of thumb: start with RWMutex+map. Only switch to sync.Map if")
	fmt.Println("profiling shows lock contention AND your access pattern is read-dominant/disjoint.")
}
```

Run with `go run main.go`. In most benchmarks, `RWMutex+map` wins for mixed read/write workloads with shared keys. `sync.Map` pulls ahead only in the 99% read scenario or disjoint key patterns where its lock-free read path avoids contention entirely. The type safety loss (`any` values requiring assertion) is another practical cost of `sync.Map`.'''),

    ("go_deep/sync_cond_producer_consumer", r'''Show me how to use sync.Cond for producer-consumer signaling in Go. When would I use sync.Cond instead of channels?''', r'''<think>
sync.Cond is rarely used in Go because channels handle most signaling patterns. But Cond is useful when:

1. You need to signal multiple waiters about a condition change (Broadcast)
2. The condition is complex (not just "an item is available" but "queue has > N items AND no writers active")
3. You're protecting shared state with a mutex anyway and want to wait on a condition of that state

Cond has three methods:
- Wait(): releases the lock, suspends the goroutine, reacquires the lock when signaled
- Signal(): wakes ONE waiting goroutine
- Broadcast(): wakes ALL waiting goroutines

The critical pattern with Wait() is the loop:
```
cond.L.Lock()
for !condition() {
    cond.Wait()
}
// condition is true, we hold the lock
cond.L.Unlock()
```

You MUST use a for loop, not if, because of spurious wakeups and because multiple waiters might be woken but only one should proceed.

Let me build a bounded queue with producer-consumer using sync.Cond, showing both Signal and Broadcast.
</think>

`sync.Cond` is useful when channels don't fit — specifically when you need to wait on complex conditions involving shared state protected by a mutex, or when you need `Broadcast` to wake all waiters at once.

```go
package main

import (
	"fmt"
	"math/rand"
	"sync"
	"time"
)

// BoundedQueue demonstrates sync.Cond for a producer-consumer queue
// with two conditions: "not full" (for producers) and "not empty" (for consumers).
// This is hard to do cleanly with channels alone because the capacity
// check and enqueue must be atomic with the mutex-protected state.
type BoundedQueue struct {
	mu       sync.Mutex
	notFull  *sync.Cond
	notEmpty *sync.Cond
	buf      []int
	capacity int
	closed   bool
}

func NewBoundedQueue(capacity int) *BoundedQueue {
	q := &BoundedQueue{
		buf:      make([]int, 0, capacity),
		capacity: capacity,
	}
	q.notFull = sync.NewCond(&q.mu)
	q.notEmpty = sync.NewCond(&q.mu)
	return q
}

func (q *BoundedQueue) Put(val int) bool {
	q.mu.Lock()
	defer q.mu.Unlock()

	// MUST use for-loop, not if — handles spurious wakeups and
	// the case where another producer grabs the slot after we wake
	for len(q.buf) >= q.capacity {
		if q.closed {
			return false
		}
		q.notFull.Wait() // releases lock, waits, reacquires lock
	}

	if q.closed {
		return false
	}

	q.buf = append(q.buf, val)
	q.notEmpty.Signal() // wake ONE consumer
	return true
}

func (q *BoundedQueue) Get() (int, bool) {
	q.mu.Lock()
	defer q.mu.Unlock()

	for len(q.buf) == 0 {
		if q.closed {
			return 0, false
		}
		q.notEmpty.Wait()
	}

	val := q.buf[0]
	q.buf = q.buf[1:]
	q.notFull.Signal() // wake ONE producer
	return val, true
}

func (q *BoundedQueue) Close() {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.closed = true
	// Broadcast wakes ALL waiters — they'll see closed=true and exit
	q.notFull.Broadcast()
	q.notEmpty.Broadcast()
}

func (q *BoundedQueue) Len() int {
	q.mu.Lock()
	defer q.mu.Unlock()
	return len(q.buf)
}

// === Demo 2: Broadcast for barrier synchronization ===
type Barrier struct {
	mu      sync.Mutex
	cond    *sync.Cond
	count   int
	total   int
	generation int
}

func NewBarrier(n int) *Barrier {
	b := &Barrier{total: n}
	b.cond = sync.NewCond(&b.mu)
	return b
}

func (b *Barrier) Wait() {
	b.mu.Lock()
	defer b.mu.Unlock()
	gen := b.generation
	b.count++
	if b.count >= b.total {
		// Last one in — release everyone
		b.count = 0
		b.generation++
		b.cond.Broadcast() // wake ALL — this is why we need Cond, not a channel
	} else {
		// Wait until this generation is complete
		for gen == b.generation {
			b.cond.Wait()
		}
	}
}

func main() {
	// === Producer-Consumer Demo ===
	fmt.Println("=== Producer-Consumer with sync.Cond ===")
	q := NewBoundedQueue(5) // small buffer to show blocking

	var wg sync.WaitGroup

	// 3 producers
	for p := 0; p < 3; p++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			for i := 0; i < 10; i++ {
				val := id*100 + i
				if ok := q.Put(val); ok {
					fmt.Printf("  producer-%d: put %d (qlen=%d)\n", id, val, q.Len())
				}
				time.Sleep(time.Duration(rand.Intn(20)) * time.Millisecond)
			}
		}(p)
	}

	// 2 consumers
	for c := 0; c < 2; c++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			for {
				val, ok := q.Get()
				if !ok {
					fmt.Printf("  consumer-%d: queue closed, exiting\n", id)
					return
				}
				fmt.Printf("  consumer-%d: got %d\n", id, val)
				time.Sleep(time.Duration(rand.Intn(30)) * time.Millisecond)
			}
		}(c)
	}

	// Let producers finish, then close
	time.Sleep(500 * time.Millisecond)
	q.Close()
	wg.Wait()

	// === Barrier Demo ===
	fmt.Println("\n=== Broadcast Barrier (all goroutines sync at a point) ===")
	const numWorkers = 5
	barrier := NewBarrier(numWorkers)

	var wg2 sync.WaitGroup
	for i := 0; i < numWorkers; i++ {
		wg2.Add(1)
		go func(id int) {
			defer wg2.Done()
			// Phase 1
			time.Sleep(time.Duration(rand.Intn(100)) * time.Millisecond)
			fmt.Printf("  worker-%d: phase 1 done, waiting at barrier\n", id)
			barrier.Wait()
			fmt.Printf("  worker-%d: passed barrier, starting phase 2\n", id)
		}(i)
	}
	wg2.Wait()

	fmt.Println("\nWhen to use sync.Cond vs channels:")
	fmt.Println("  Channels: simple producer-consumer, signaling, pipelines")
	fmt.Println("  sync.Cond: complex conditions on mutex-protected state,")
	fmt.Println("             Broadcast to wake ALL waiters, barrier patterns")
	fmt.Println("  Rule: prefer channels. Use Cond only when the condition")
	fmt.Println("        check and state mutation must be atomic under one lock")
}
```

Run with `go run main.go`. The key use case for `sync.Cond` over channels is `Broadcast` — waking all waiters simultaneously. With channels, you would need to close the channel (one-shot) or maintain a list of per-waiter channels. The bounded queue also benefits because the "is full" / "is empty" check is atomically coupled with the enqueue/dequeue under the same mutex.'''),

    ("go_deep/atomic_vs_mutex_counters", r'''When should I use sync/atomic instead of sync.Mutex for simple counters in Go? Show me the performance difference and the pitfalls of each.''', r'''<think>
Atomics vs mutex for counters — let me think through the tradeoffs carefully.

Atomics:
- Lock-free, use CPU atomic instructions (CAS, XADD on x86, LDXR/STXR on ARM)
- Much faster than mutex because no goroutine scheduling or OS involvement
- Limited to simple operations: load, store, add, swap, compare-and-swap
- Can't protect multi-variable invariants — each atomic op is independent

Mutex:
- Can protect arbitrary critical sections with multiple variables
- More expensive due to goroutine parking/unparking when contended
- Clearer semantics for complex read-modify-write operations

For a simple counter, atomic.Int64 (Go 1.19+) or atomic.AddInt64 is the right choice. Mutex is overkill and adds unnecessary contention.

But the pitfall with atomics is subtle: if you need to read a counter and make a decision based on it (like "if count < limit, increment"), you need CAS loops, which are harder to get right. The read and the conditional write are separate operations, so another goroutine can change the value between them.

And the critical rule: if you need to update TWO related values atomically (like count and total for computing an average), individual atomics on each field don't help. The pair of updates is NOT atomic, so readers can see an inconsistent snapshot. This requires a mutex.

Go 1.19 introduced typed atomics (atomic.Int64, atomic.Bool, atomic.Pointer) which are cleaner than the old atomic.AddInt64(&counter, 1) style. I should use the modern API.

Let me benchmark both approaches and show the multi-variable invariant gotcha.
</think>

For simple counters, `sync/atomic` is significantly faster than `sync.Mutex`. But atomics can only protect single variables — the moment you need to update two related values together, you need a mutex.

```go
package main

import (
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

const (
	numGoroutines = 8
	opsPerG       = 1_000_000
)

// === Benchmark: Simple counter increment ===
func benchAtomicCounter() time.Duration {
	var counter atomic.Int64
	var wg sync.WaitGroup

	start := time.Now()
	for g := 0; g < numGoroutines; g++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < opsPerG; i++ {
				counter.Add(1)
			}
		}()
	}
	wg.Wait()

	elapsed := time.Since(start)
	expected := int64(numGoroutines * opsPerG)
	if counter.Load() != expected {
		panic("atomic counter is wrong")
	}
	return elapsed
}

func benchMutexCounter() time.Duration {
	var mu sync.Mutex
	counter := 0
	var wg sync.WaitGroup

	start := time.Now()
	for g := 0; g < numGoroutines; g++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < opsPerG; i++ {
				mu.Lock()
				counter++
				mu.Unlock()
			}
		}()
	}
	wg.Wait()

	elapsed := time.Since(start)
	expected := numGoroutines * opsPerG
	if counter != expected {
		panic("mutex counter is wrong")
	}
	return elapsed
}

// === Pitfall: Atomics can't protect multi-variable invariants ===
type Stats struct {
	count atomic.Int64
	total atomic.Int64
	// BUG: reading count and total separately is NOT atomic
	// Another goroutine can update count after we read it but before we read total
}

func (s *Stats) Record(value int64) {
	s.count.Add(1)
	// WINDOW: another goroutine reads here → inconsistent count/total
	s.total.Add(value)
}

func (s *Stats) Average() float64 {
	c := s.count.Load()
	t := s.total.Load()
	// c and t might be from different "snapshots"
	if c == 0 {
		return 0
	}
	return float64(t) / float64(c)
}

// === Correct: Mutex for multi-variable invariant ===
type SafeStats struct {
	mu    sync.Mutex
	count int64
	total int64
}

func (s *SafeStats) Record(value int64) {
	s.mu.Lock()
	s.count++
	s.total += value
	s.mu.Unlock()
}

func (s *SafeStats) Average() float64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.count == 0 {
		return 0
	}
	return float64(s.total) / float64(s.count)
}

// === Pitfall: CAS loop complexity ===
func casLoopDemo() {
	fmt.Println("\n=== CAS Loop: Atomic max update ===")
	var maxVal atomic.Int64

	var wg sync.WaitGroup
	for g := 0; g < numGoroutines; g++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			newVal := int64(id * 100)
			// CAS loop to atomically update max
			for {
				old := maxVal.Load()
				if newVal <= old {
					break // our value isn't larger
				}
				if maxVal.CompareAndSwap(old, newVal) {
					break // successfully updated
				}
				// CAS failed — another goroutine changed it, retry
			}
		}(g)
	}
	wg.Wait()
	fmt.Printf("  atomic max = %d (expected %d)\n", maxVal.Load(), int64((numGoroutines-1)*100))
	fmt.Println("  CAS loops are correct but hard to reason about — prefer mutex for complex logic")
}

func main() {
	fmt.Println("=== Counter Benchmark ===")
	fmt.Printf("Config: %d goroutines x %d ops = %d total increments\n\n",
		numGoroutines, opsPerG, numGoroutines*opsPerG)

	atomicTime := benchAtomicCounter()
	mutexTime := benchMutexCounter()

	fmt.Printf("  atomic.Int64.Add: %v\n", atomicTime.Round(time.Millisecond))
	fmt.Printf("  sync.Mutex:       %v\n", mutexTime.Round(time.Millisecond))
	speedup := float64(mutexTime) / float64(atomicTime)
	fmt.Printf("  Atomic is %.1fx faster\n", speedup)

	// === Multi-variable invariant pitfall ===
	fmt.Println("\n=== PITFALL: Atomics can't protect multi-variable invariants ===")
	fmt.Println("  Stats with two atomic fields: count and total")
	fmt.Println("  Reading Average() = total/count is NOT atomic")
	fmt.Println("  Race window between reading count and total gives wrong average")
	fmt.Println("  Fix: use sync.Mutex when invariant spans multiple variables")

	// Demonstrate the inconsistency
	var broken Stats
	var correct SafeStats
	var wg sync.WaitGroup

	for g := 0; g < 100; g++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < 1000; i++ {
				broken.Record(10)
				correct.Record(10)
			}
		}()
	}
	wg.Wait()
	fmt.Printf("  broken average:  %.2f (should be 10.00, may be slightly off)\n", broken.Average())
	fmt.Printf("  correct average: %.2f (always exact)\n", correct.Average())

	casLoopDemo()

	fmt.Println("\nGuidelines:")
	fmt.Println("  atomic: single counter/flag, metrics, feature flags")
	fmt.Println("  mutex:  multi-variable invariants, complex read-modify-write")
	fmt.Println("  Go 1.19+ atomic types (atomic.Int64, atomic.Bool) are preferred over atomic.AddInt64")
}
```

Run with `go run main.go`. Atomics will typically be 3-10x faster than mutex for simple counter increments. But the multi-variable invariant pitfall is the critical lesson: the moment your correctness depends on two values being consistent with each other, atomic operations on individual fields are not enough — you need a mutex.'''),

    ("go_deep/goroutine_leak_detection", r'''How do I detect and prevent goroutine leaks in Go? Write a program that demonstrates common leak patterns and a detection utility.''', r'''<think>
Goroutine leaks are one of the most insidious bugs in Go. Common causes:

1. Blocked on channel with no sender/receiver and no way to cancel
2. Infinite loop without exit condition
3. Blocked on mutex that will never be released
4. HTTP handler that starts goroutines but client disconnects

Detection approaches:
- runtime.NumGoroutine() before and after a test — should return to baseline
- goleak package (uber-go/goleak) for test integration
- pprof goroutine profile at /debug/pprof/goroutine
- Manual monitoring: periodically log goroutine count

Prevention:
- Always pass context.Context and check ctx.Done()
- Use buffered channels when the receiver might abandon
- Defer cleanup in goroutines
- Use errgroup which handles lifecycle

Let me build a leak detector and show common leak patterns with fixes.
</think>

Goroutine leaks are silent memory and CPU drains. Here is a program demonstrating common leak patterns, their fixes, and a reusable leak detector:

```go
package main

import (
	"context"
	"fmt"
	"runtime"
	"strings"
	"time"
)

// ============================================================
// LeakDetector: monitors goroutine count and dumps stack traces
// ============================================================
type LeakDetector struct {
	baseline int
	label    string
}

func NewLeakDetector(label string) *LeakDetector {
	runtime.GC()
	time.Sleep(10 * time.Millisecond) // let finalizers run
	return &LeakDetector{
		baseline: runtime.NumGoroutine(),
		label:    label,
	}
}

func (d *LeakDetector) Check() (leaked int, report string) {
	runtime.GC()
	time.Sleep(50 * time.Millisecond) // let goroutines settle
	current := runtime.NumGoroutine()
	leaked = current - d.baseline

	if leaked > 0 {
		// Capture stack traces of all goroutines
		buf := make([]byte, 1<<16)
		n := runtime.Stack(buf, true) // true = all goroutines
		stacks := string(buf[:n])

		// Count goroutines in stack dump
		goroutineCount := strings.Count(stacks, "goroutine ")
		report = fmt.Sprintf("[%s] LEAK DETECTED: %d extra goroutines (baseline=%d, current=%d, in stack=%d)",
			d.label, leaked, d.baseline, current, goroutineCount)
	} else {
		report = fmt.Sprintf("[%s] OK: no leaks (baseline=%d, current=%d)",
			d.label, d.baseline, current)
	}
	return leaked, report
}

// ============================================================
// LEAK 1: Goroutine blocked on channel with no sender
// ============================================================
func leak1_blockedReceive() {
	fmt.Println("\n=== LEAK 1: Blocked receive, no sender ===")
	detector := NewLeakDetector("blocked-recv")

	ch := make(chan int)
	go func() {
		val := <-ch // blocks forever — nobody will ever send
		fmt.Println(val)
	}()

	leaked, report := detector.Check()
	fmt.Printf("  %s\n", report)
	_ = leaked
	// ch is never closed or sent to — goroutine leaked permanently
}

func fix1_contextCancellation() {
	fmt.Println("\n=== FIX 1: Use context for cancellation ===")
	detector := NewLeakDetector("ctx-cancel")

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	ch := make(chan int)
	go func() {
		select {
		case val := <-ch:
			fmt.Println(val)
		case <-ctx.Done():
			// Clean exit when context expires
			return
		}
	}()

	time.Sleep(100 * time.Millisecond) // let context expire
	_, report := detector.Check()
	fmt.Printf("  %s\n", report)
}

// ============================================================
// LEAK 2: Goroutine blocked on send to unbuffered channel
// ============================================================
func leak2_blockedSend() {
	fmt.Println("\n=== LEAK 2: Fire-and-forget send, no receiver ===")
	detector := NewLeakDetector("blocked-send")

	// Simulate: start background work, but caller gives up
	resultCh := make(chan string) // unbuffered!
	go func() {
		time.Sleep(10 * time.Millisecond)
		resultCh <- "result" // blocks forever if nobody receives
	}()

	// Caller "gives up" — never reads from resultCh
	time.Sleep(50 * time.Millisecond)
	_, report := detector.Check()
	fmt.Printf("  %s\n", report)
}

func fix2_bufferedChannel() {
	fmt.Println("\n=== FIX 2: Buffer of 1 for fire-and-forget ===")
	detector := NewLeakDetector("buffered-send")

	resultCh := make(chan string, 1) // buffer of 1!
	go func() {
		time.Sleep(10 * time.Millisecond)
		resultCh <- "result" // succeeds even without receiver
	}()

	time.Sleep(50 * time.Millisecond) // caller never reads
	_, report := detector.Check()
	fmt.Printf("  %s\n", report)
}

// ============================================================
// LEAK 3: Infinite loop without exit condition
// ============================================================
func leak3_infiniteLoop() {
	fmt.Println("\n=== LEAK 3: Infinite loop, no exit ===")
	detector := NewLeakDetector("inf-loop")

	go func() {
		for {
			time.Sleep(100 * time.Millisecond)
			// Does something periodically but has no way to stop
		}
	}()

	_, report := detector.Check()
	fmt.Printf("  %s\n", report)
}

func fix3_doneChannel() {
	fmt.Println("\n=== FIX 3: Done channel for loop exit ===")
	detector := NewLeakDetector("done-chan")

	done := make(chan struct{})
	go func() {
		for {
			select {
			case <-done:
				return
			case <-time.After(100 * time.Millisecond):
				// periodic work
			}
		}
	}()

	close(done) // signal the goroutine to stop
	time.Sleep(50 * time.Millisecond)
	_, report := detector.Check()
	fmt.Printf("  %s\n", report)
}

// ============================================================
// LEAK 4: Producer outlives consumer (pipeline leak)
// ============================================================
func leak4_pipelineLeak() {
	fmt.Println("\n=== LEAK 4: Pipeline producer outlives consumer ===")
	detector := NewLeakDetector("pipeline")

	// Producer generates values forever
	gen := func() <-chan int {
		ch := make(chan int)
		go func() {
			i := 0
			for {
				ch <- i // blocks when consumer stops reading
				i++
			}
		}()
		return ch
	}

	ch := gen()
	// Consumer reads only 3 values, then stops
	for i := 0; i < 3; i++ {
		<-ch
	}
	// Producer goroutine is now blocked on ch <- i forever

	_, report := detector.Check()
	fmt.Printf("  %s\n", report)
}

func fix4_contextPipeline() {
	fmt.Println("\n=== FIX 4: Pipeline with context cancellation ===")
	detector := NewLeakDetector("ctx-pipeline")

	gen := func(ctx context.Context) <-chan int {
		ch := make(chan int)
		go func() {
			defer close(ch)
			i := 0
			for {
				select {
				case ch <- i:
					i++
				case <-ctx.Done():
					return // clean exit
				}
			}
		}()
		return ch
	}

	ctx, cancel := context.WithCancel(context.Background())
	ch := gen(ctx)
	for i := 0; i < 3; i++ {
		<-ch
	}
	cancel() // stop the producer
	time.Sleep(50 * time.Millisecond)
	_, report := detector.Check()
	fmt.Printf("  %s\n", report)
}

func main() {
	fmt.Println("=== Goroutine Leak Detection and Prevention ===")
	fmt.Printf("Initial goroutine count: %d\n", runtime.NumGoroutine())

	leak1_blockedReceive()
	fix1_contextCancellation()

	leak2_blockedSend()
	fix2_bufferedChannel()

	leak3_infiniteLoop()
	fix3_doneChannel()

	leak4_pipelineLeak()
	fix4_contextPipeline()

	fmt.Println("\n=== Summary ===")
	fmt.Printf("Final goroutine count: %d (leaked goroutines still running)\n", runtime.NumGoroutine())
	fmt.Println("\nPrevention rules:")
	fmt.Println("  1. Every goroutine must have an exit path (context, done channel)")
	fmt.Println("  2. Use buffered(1) channels for fire-and-forget results")
	fmt.Println("  3. Pipeline producers must accept context for cancellation")
	fmt.Println("  4. In tests: check runtime.NumGoroutine() before/after")
	fmt.Println("  5. In production: monitor goroutine count via /debug/pprof/goroutine")
}
```

Run with `go run main.go`. The leak detector pattern (comparing `NumGoroutine` before and after) is what libraries like `go.uber.org/goleak` use under the hood. In production, export `runtime.NumGoroutine()` as a metric and alert if it trends upward over time — a monotonically increasing goroutine count is the signature of a leak.'''),

    ("go_deep/channel_direction_types", r'''How do channel direction types work in Go and why should I use them? Show me how directional channels improve API safety.''', r'''<think>
Channel directions in Go — three types:
- chan T: bidirectional (can send and receive)
- chan<- T: send-only
- <-chan T: receive-only
Bidirectional converts to directional implicitly, but NOT the reverse.
Enforced at compile time. The conversion is free at runtime — no allocation.
Why use them:
1. API contracts: a read-only function takes <-chan T, cannot accidentally send or close
2. Producer/consumer ownership: producer closes, consumer reads — types enforce this
3. Prevents bugs: closing from wrong goroutine causes panic if closed twice
Practical example: generator returns <-chan T (consumer can only read).
Internally uses bidirectional chan T, but the return type restricts the caller.
This looks minor but prevents real production bugs.
Closing a channel from the wrong place is a common source of panics.
Nuance: chan<- T (send-only) CAN still close the channel.
Closing is a form of signaling, and the sender owns the lifecycle.
But <-chan T (receive-only) cannot close — correct, receivers don't own the channel.
Pipeline composition: each stage takes <-chan T input, returns <-chan T output.
No stage can accidentally interfere with another stage's output channel.
The type system enforces the data flow direction through the entire pipeline.
I should show generators, pipeline workers, and server shutdown patterns.
</think>

Channel direction types are compile-time constraints that prevent misuse. A `<-chan T` can only receive; a `chan<- T` can only send. This enforces the producer/consumer contract at the type level.

```go
package main

import (
	"context"
	"fmt"
	"strings"
	"sync"
)

// ============================================================
// Pattern 1: Generator returns receive-only channel
// The caller CANNOT close it or send to it — only the producer can.
// ============================================================

// fibonacci returns a receive-only channel. The caller cannot
// accidentally close it or send values into it.
func fibonacci(ctx context.Context, n int) <-chan int {
	ch := make(chan int) // bidirectional internally
	go func() {
		defer close(ch) // only the producer closes
		a, b := 0, 1
		for i := 0; i < n; i++ {
			select {
			case ch <- a: // sends are fine — ch is bidirectional here
				a, b = b, a+b
			case <-ctx.Done():
				return
			}
		}
	}()
	return ch // implicitly converts chan int → <-chan int
}

// ============================================================
// Pattern 2: Worker takes send-only output channel
// The worker CANNOT read from the output or close it — the owner manages lifecycle.
// ============================================================

func toUpper(input <-chan string, output chan<- string, wg *sync.WaitGroup) {
	defer wg.Done()
	for s := range input {
		output <- strings.ToUpper(s)
	}
	// NOTE: worker does NOT close output — only the pipeline owner does
	// This prevents the "who closes the channel?" confusion

	// These would be compile errors:
	// close(output)    // actually this IS allowed on chan<- (send-only can close)
	// val := <-output  // ERROR: cannot receive from send-only channel
	// <-input          // fine: receive-only can receive (but not send)
}

// ============================================================
// Pattern 3: Signal channels — receive-only prevents accidental re-close
// ============================================================

type Server struct {
	quit     chan struct{}
	stopped  chan struct{}
}

func NewServer() *Server {
	s := &Server{
		quit:    make(chan struct{}),
		stopped: make(chan struct{}),
	}
	go s.run()
	return s
}

func (s *Server) run() {
	defer close(s.stopped)
	fmt.Println("  server: running")
	<-s.quit
	fmt.Println("  server: shutting down")
}

func (s *Server) Stop() {
	close(s.quit)
}

// Done returns receive-only channel — callers can wait but can't
// accidentally close it (which would panic on double-close)
func (s *Server) Done() <-chan struct{} {
	return s.stopped
}

// ============================================================
// Pattern 4: Compile-time enforcement demo
// ============================================================

func demonstrateCompileTimeSafety() {
	fmt.Println("\n=== Compile-Time Safety ===")

	ch := make(chan int, 1)

	// These conversions are implicit and safe:
	var sendOnly chan<- int = ch
	var recvOnly <-chan int = ch

	sendOnly <- 42
	val := <-recvOnly
	fmt.Printf("  sent via chan<-, received via <-chan: %d\n", val)

	// These would be compile errors (uncomment to verify):
	// sendOnly <- 42; _ = <-sendOnly  // ERROR: cannot receive from send-only
	// recvOnly <- 42                   // ERROR: cannot send to receive-only
	// val := <-sendOnly                // ERROR: cannot receive from send-only

	// You CANNOT convert directional back to bidirectional:
	// var bidir chan int = sendOnly     // ERROR: cannot use send-only as chan int
	// var bidir chan int = recvOnly     // ERROR: cannot use receive-only as chan int

	fmt.Println("  directional types prevent send/receive misuse at compile time")
}

func main() {
	fmt.Println("=== Channel Direction Types for API Safety ===")

	// Pattern 1: Generator
	fmt.Println("\n--- Fibonacci Generator (returns <-chan int) ---")
	ctx := context.Background()
	for v := range fibonacci(ctx, 8) {
		fmt.Printf("  fib: %d\n", v)
	}

	// Pattern 2: Pipeline workers
	fmt.Println("\n--- Pipeline Workers (send-only output) ---")
	input := make(chan string, 3)
	output := make(chan string, 3)

	var wg sync.WaitGroup
	wg.Add(2)
	go toUpper(input, output, &wg) // input is <-chan, output is chan<-
	go toUpper(input, output, &wg)

	words := []string{"hello", "concurrent", "go"}
	for _, w := range words {
		input <- w
	}
	close(input)
	wg.Wait()
	close(output) // pipeline owner closes output, not workers

	for result := range output {
		fmt.Printf("  upper: %s\n", result)
	}

	// Pattern 3: Server shutdown
	fmt.Println("\n--- Server Shutdown (Done() returns <-chan) ---")
	srv := NewServer()
	srv.Stop()
	<-srv.Done()
	fmt.Println("  server stopped cleanly")

	// Pattern 4: Compile-time safety
	demonstrateCompileTimeSafety()

	fmt.Println("\nRules:")
	fmt.Println("  1. Generators return <-chan T (receive-only)")
	fmt.Println("  2. Workers take <-chan T for input, chan<- T for output")
	fmt.Println("  3. Only the producer/owner closes channels")
	fmt.Println("  4. Done()/Stopped() methods return <-chan struct{}")
	fmt.Println("  5. Directional types catch misuse at compile time, not runtime")
}
```

Run with `go run main.go`. The most valuable pattern is the generator returning `<-chan T` — it makes it impossible for consumers to close the channel (which would panic the producer) or send values back (which would corrupt the data flow). This eliminates an entire class of concurrency bugs at compile time.'''),

    ("go_deep/pipeline_stage_cancellation", r'''Implement the pipeline pattern in Go with proper stage cancellation. Each stage should stop cleanly when downstream stops consuming or when an error occurs.''', r'''<think>
The pipeline pattern in Go chains stages where each stage is a goroutine that:
1. Receives from an input channel
2. Processes the data
3. Sends to an output channel

The challenge is cancellation: if the final consumer stops early (or any stage errors), all upstream stages must stop too. Without proper cancellation, upstream stages block on their output sends and leak.

Key design:
- Each stage takes a context.Context for cancellation
- Sends use select with ctx.Done() to avoid blocking
- Each stage closes its output channel when done (either input exhausted or context cancelled)
- Use errgroup or propagate errors through the pipeline

Let me build a concrete example: a text processing pipeline.
Stage 1: generate lines
Stage 2: filter lines matching a pattern
Stage 3: transform (uppercase)
Stage 4: collect results (consumer)

Show: cancelling after N results, error in a stage, clean shutdown.
</think>

The pipeline pattern chains stages via channels. The critical requirement is that cancelling downstream must propagate upstream to prevent goroutine leaks.

```go
package main

import (
	"context"
	"fmt"
	"runtime"
	"strings"
	"time"
	"unicode"
)

// Stage function signature: takes context + input channel, returns output channel + error channel
// Each stage is a self-contained goroutine that cleans up when context is cancelled.

// generate produces lines from a data source
func generate(ctx context.Context, lines []string) <-chan string {
	out := make(chan string)
	go func() {
		defer close(out)
		for _, line := range lines {
			select {
			case out <- line:
			case <-ctx.Done():
				fmt.Println("  [generate] cancelled, stopping")
				return
			}
		}
	}()
	return out
}

// filter passes through lines matching a predicate
func filter(ctx context.Context, in <-chan string, pred func(string) bool) <-chan string {
	out := make(chan string)
	go func() {
		defer close(out)
		for line := range in {
			if pred(line) {
				select {
				case out <- line:
				case <-ctx.Done():
					fmt.Println("  [filter] cancelled, stopping")
					return
				}
			}
		}
	}()
	return out
}

// transform applies a function to each line
func transform(ctx context.Context, in <-chan string, fn func(string) string) <-chan string {
	out := make(chan string)
	go func() {
		defer close(out)
		for line := range in {
			select {
			case out <- fn(line):
			case <-ctx.Done():
				fmt.Println("  [transform] cancelled, stopping")
				return
			}
		}
	}()
	return out
}

// take consumes at most n items, then cancels the context
func take(ctx context.Context, cancel context.CancelFunc, in <-chan string, n int) []string {
	var results []string
	for s := range in {
		results = append(results, s)
		if len(results) >= n {
			fmt.Printf("  [take] got %d items, cancelling pipeline\n", n)
			cancel() // signal all upstream stages to stop
			// Drain remaining items that are in-flight
			for range in {
			}
			return results
		}
	}
	return results
}

func main() {
	fmt.Println("=== Pipeline with Stage Cancellation ===")
	goroutinesBefore := runtime.NumGoroutine()

	// === Demo 1: Full pipeline, consume all ===
	fmt.Println("\n--- Demo 1: Full consumption ---")
	data := []string{
		"hello world",
		"go is great",
		"ALREADY UPPER",
		"concurrency rocks",
		"channels are typed",
		"select multiplexes",
		"goroutines are cheap",
		"context carries deadlines",
	}

	ctx1, cancel1 := context.WithCancel(context.Background())
	defer cancel1()

	// Build pipeline: generate → filter (contains "o") → uppercase → collect
	stage1 := generate(ctx1, data)
	stage2 := filter(ctx1, stage1, func(s string) bool {
		return strings.Contains(s, "o")
	})
	stage3 := transform(ctx1, stage2, func(s string) string {
		return strings.Map(unicode.ToUpper, s)
	})

	fmt.Println("  Results:")
	for result := range stage3 {
		fmt.Printf("    %s\n", result)
	}

	// === Demo 2: Early cancellation — take only 2 results ===
	fmt.Println("\n--- Demo 2: Early cancellation (take 2) ---")
	ctx2, cancel2 := context.WithCancel(context.Background())

	// Longer data set to show that upstream stops early
	longData := make([]string, 100)
	for i := range longData {
		longData[i] = fmt.Sprintf("item-%d-data", i)
	}

	s1 := generate(ctx2, longData)
	s2 := filter(ctx2, s1, func(s string) bool { return true }) // pass all
	s3 := transform(ctx2, s2, strings.ToUpper)

	results := take(ctx2, cancel2, s3, 2)
	fmt.Println("  Results:")
	for _, r := range results {
		fmt.Printf("    %s\n", r)
	}

	time.Sleep(50 * time.Millisecond) // let goroutines clean up

	// === Demo 3: Timeout cancellation ===
	fmt.Println("\n--- Demo 3: Timeout cancellation ---")
	ctx3, cancel3 := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel3()

	// Slow generator that exceeds the timeout
	slowGen := func(ctx context.Context) <-chan string {
		out := make(chan string)
		go func() {
			defer close(out)
			i := 0
			for {
				time.Sleep(30 * time.Millisecond) // slow
				select {
				case out <- fmt.Sprintf("slow-item-%d", i):
					i++
				case <-ctx.Done():
					fmt.Printf("  [slowGen] timeout after %d items: %v\n", i, ctx.Err())
					return
				}
			}
		}()
		return out
	}

	for item := range slowGen(ctx3) {
		fmt.Printf("    got: %s\n", item)
	}

	time.Sleep(50 * time.Millisecond)
	goroutinesAfter := runtime.NumGoroutine()
	fmt.Printf("\n  Goroutines: before=%d, after=%d (no leaks: %v)\n",
		goroutinesBefore, goroutinesAfter, goroutinesAfter <= goroutinesBefore+1)

	fmt.Println("\nPipeline rules:")
	fmt.Println("  1. Every stage takes context.Context")
	fmt.Println("  2. Every send uses select with ctx.Done()")
	fmt.Println("  3. Each stage closes its output channel via defer close(out)")
	fmt.Println("  4. Consumer cancels context when it has enough → upstream stops")
	fmt.Println("  5. Check goroutine count to verify no leaks after pipeline completes")
}
```

Run with `go run main.go`. The essential pattern is: every channel send in every stage must be wrapped in `select { case out <- val: case <-ctx.Done(): return }`. Without this, an upstream stage will block on send when the downstream consumer stops reading, leaking the goroutine. The `defer close(out)` ensures that downstream stages' `range` loops terminate when upstream exits.'''),

    ("go_deep/bounded_parallelism_semaphore", r'''Show me how to implement bounded parallelism using a semaphore channel in Go. I want to process many items concurrently but limit the number of simultaneous operations.''', r'''<think>
Bounded parallelism limits concurrent operations. Classic Go pattern: buffered channel as semaphore.
Buffer size = max concurrent operations.
Acquire: send to channel (blocks when full). Release: receive from channel.
Two implementations:
1. Semaphore channel: goroutine-per-item, but only N run simultaneously
2. Fixed worker pool: N goroutines pulling from a shared work queue
The semaphore approach is simpler and more idiomatic.
Important: WaitGroup Add must happen before the goroutine spawn.
Semaphore acquire should be INSIDE the goroutine, not outside.
If outside, the spawning loop blocks — can't even submit work while waiting.
If inside, all goroutines are created immediately but parked until a slot opens.
errgroup.SetLimit (Go 1.20+) wraps this pattern.
But manual semaphore gives full control over acquire/release timing.
You might acquire before launching the goroutine to enforce backpressure on the caller.
Context-aware acquire is critical for production.
Without it, Shutdown would block until a semaphore slot opens — could take forever.
Use select with sem channel and ctx.Done() for cancellable acquire.
Related but distinct: rate limiting limits throughput (ops/sec), bounded parallelism limits concurrency (simultaneous ops).
A system might need both — e.g., max 10 concurrent requests AND max 100 requests/second.
Let me demonstrate semaphore, worker pool, context-aware, and rate-limited patterns.
</think>

The semaphore channel pattern limits concurrency by using a buffered channel where buffer size equals the maximum concurrent operations.

```go
package main

import (
	"context"
	"fmt"
	"math/rand"
	"runtime"
	"sync"
	"time"
)

// ============================================================
// Pattern 1: Semaphore channel (most common)
// ============================================================
func semaphoreChannel() {
	fmt.Println("=== Pattern 1: Semaphore Channel ===")

	const maxConcurrent = 3
	items := make([]int, 20)
	for i := range items {
		items[i] = i
	}

	sem := make(chan struct{}, maxConcurrent)
	var wg sync.WaitGroup
	var mu sync.Mutex
	var results []string

	for _, item := range items {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()

			sem <- struct{}{} // acquire — blocks if maxConcurrent goroutines are running
			defer func() { <-sem }() // release

			// Simulated work
			duration := time.Duration(rand.Intn(50)+10) * time.Millisecond
			active := len(sem) // how many slots are in use
			fmt.Printf("  item %2d: start (active=%d/%d)\n", id, active, maxConcurrent)
			time.Sleep(duration)

			mu.Lock()
			results = append(results, fmt.Sprintf("item-%d", id))
			mu.Unlock()
		}(item)
	}

	wg.Wait()
	fmt.Printf("  processed %d items with max %d concurrent\n\n", len(results), maxConcurrent)
}

// ============================================================
// Pattern 2: Fixed worker pool (N workers pull from queue)
// ============================================================
func workerPool() {
	fmt.Println("=== Pattern 2: Fixed Worker Pool ===")

	const numWorkers = 3
	jobs := make(chan int, 10)
	results := make(chan string, 10)

	// Start fixed number of workers
	var wg sync.WaitGroup
	for w := 0; w < numWorkers; w++ {
		wg.Add(1)
		go func(workerID int) {
			defer wg.Done()
			for job := range jobs {
				time.Sleep(time.Duration(rand.Intn(30)+10) * time.Millisecond)
				results <- fmt.Sprintf("worker-%d processed job-%d", workerID, job)
			}
		}(w)
	}

	// Send jobs
	go func() {
		for i := 0; i < 15; i++ {
			jobs <- i
		}
		close(jobs)
	}()

	// Close results after all workers finish
	go func() {
		wg.Wait()
		close(results)
	}()

	count := 0
	for r := range results {
		fmt.Printf("  %s\n", r)
		count++
	}
	fmt.Printf("  completed %d jobs with %d workers\n\n", count, numWorkers)
}

// ============================================================
// Pattern 3: Semaphore with context cancellation
// ============================================================
func semaphoreWithContext() {
	fmt.Println("=== Pattern 3: Semaphore + Context Cancellation ===")

	const maxConcurrent = 4
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	sem := make(chan struct{}, maxConcurrent)
	var wg sync.WaitGroup
	processed := 0
	var mu sync.Mutex

	for i := 0; i < 100; i++ {
		// Check context before spawning
		select {
		case <-ctx.Done():
			fmt.Printf("  context expired after queueing %d items\n", i)
			goto done
		default:
		}

		wg.Add(1)
		go func(id int) {
			defer wg.Done()

			// Acquire with context — don't block forever if cancelled
			select {
			case sem <- struct{}{}:
				defer func() { <-sem }()
			case <-ctx.Done():
				return
			}

			// Do work
			time.Sleep(time.Duration(rand.Intn(50)+20) * time.Millisecond)

			mu.Lock()
			processed++
			mu.Unlock()
		}(i)
	}
done:
	wg.Wait()
	fmt.Printf("  processed %d items before timeout\n\n", processed)
}

// ============================================================
// Pattern 4: Rate-limited semaphore (N per second)
// ============================================================
func rateLimitedSemaphore() {
	fmt.Println("=== Pattern 4: Rate-Limited Processing ===")

	const ratePerSecond = 10
	ticker := time.NewTicker(time.Second / time.Duration(ratePerSecond))
	defer ticker.Stop()

	var wg sync.WaitGroup
	start := time.Now()

	for i := 0; i < 20; i++ {
		<-ticker.C // wait for next tick — enforces rate
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			elapsed := time.Since(start).Round(time.Millisecond)
			fmt.Printf("  item %2d started at %v\n", id, elapsed)
			time.Sleep(50 * time.Millisecond) // simulate work
		}(i)
	}

	wg.Wait()
	fmt.Printf("  20 items at %d/sec = ~%v\n\n", ratePerSecond, time.Since(start).Round(time.Millisecond))
}

func main() {
	fmt.Printf("CPUs available: %d\n\n", runtime.NumCPU())

	semaphoreChannel()
	workerPool()
	semaphoreWithContext()
	rateLimitedSemaphore()

	fmt.Println("Comparison:")
	fmt.Println("  Semaphore channel: simple, goroutine per item, idiomatic")
	fmt.Println("  Worker pool: fixed goroutines, better for long-lived processing")
	fmt.Println("  Semaphore + ctx: production pattern with timeout/cancellation")
	fmt.Println("  Rate limiter: controls operations per second, not just concurrency")
	fmt.Println("\n  Choose semaphore for short-lived tasks, worker pool for steady streams")
}
```

Run with `go run main.go`. The semaphore channel pattern (Pattern 1) is the most idiomatic in Go. The key insight is that the buffered channel acts as a token bucket — each goroutine must hold a token (buffer slot) to proceed, and releases it when done. For production use, always add context cancellation (Pattern 3) so the semaphore acquire does not block forever when the application is shutting down.'''),

    ("go_deep/errgroup_first_error_cancel", r'''How do I use golang.org/x/sync/errgroup to run parallel tasks with automatic cancellation on the first error? Show me the patterns and pitfalls.''', r'''<think>
errgroup is a popular package from the Go extended libraries. Let me think through the key features and pitfalls.

Core features:
1. Manages a group of goroutines and collects the first error — replaces WaitGroup + error channel boilerplate
2. WithContext variant: creates a derived context that's cancelled when any goroutine returns an error — this is the "first-error-cancels-all" pattern
3. SetLimit (Go 1.20+): bounds parallelism — internally uses a semaphore channel, same pattern we saw earlier

Key patterns:
- Basic: g.Go(func() error { ... }) — launches goroutines, g.Wait() returns first non-nil error
- WithContext: g, ctx := errgroup.WithContext(parentCtx) — ctx is cancelled on first error
- SetLimit: g.SetLimit(n) — limits concurrent goroutines, blocks new g.Go calls until a slot opens

Pitfalls I need to highlight:
- errgroup only returns the FIRST error — if you need all errors, use a different approach (e.g., collect into a mutex-protected slice)
- With WithContext, you MUST use the derived ctx in your goroutines, not the parent context. Using the parent means goroutines won't see the cancellation from sibling errors
- The derived context is cancelled when Wait() returns, so don't pass it to anything that outlives Wait()
- Without SetLimit, all goroutines start immediately — 10K g.Go calls means 10K goroutines competing for CPU
- Closures in loops: the classic Go gotcha. g.Go(func() error { /* uses loop var */ }) captures by reference. Use a local copy or the Go 1.22+ loop variable semantics.

Since I can't import the real errgroup in a self-contained demo, I'll implement a minimal compatible version to keep it runnable. Let me show practical examples with simulated service calls.
</think>

`errgroup` from `golang.org/x/sync` manages groups of goroutines, collects the first error, and optionally cancels remaining work when one fails.

```go
package main

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	// In a real project: "golang.org/x/sync/errgroup"
	// For this demo, we'll implement a minimal errgroup to keep it self-contained.
)

// Minimal errgroup implementation (matches golang.org/x/sync/errgroup API)
type Group struct {
	wg     sync.WaitGroup
	mu     sync.Mutex
	err    error
	cancel context.CancelFunc
	sem    chan struct{}
}

func WithContext(ctx context.Context) (*Group, context.Context) {
	ctx, cancel := context.WithCancel(ctx)
	return &Group{cancel: cancel}, ctx
}

func (g *Group) Go(fn func() error) {
	g.wg.Add(1)
	go func() {
		defer g.wg.Done()
		if g.sem != nil {
			g.sem <- struct{}{}        // acquire
			defer func() { <-g.sem }() // release
		}
		if err := fn(); err != nil {
			g.mu.Lock()
			if g.err == nil {
				g.err = err // store first error only
			}
			g.mu.Unlock()
			if g.cancel != nil {
				g.cancel() // cancel context for other goroutines
			}
		}
	}()
}

func (g *Group) SetLimit(n int) {
	g.sem = make(chan struct{}, n)
}

func (g *Group) Wait() error {
	g.wg.Wait()
	if g.cancel != nil {
		g.cancel()
	}
	return g.err
}

// ============================================================
// Simulated services
// ============================================================

func fetchUserProfile(ctx context.Context, userID int) (string, error) {
	select {
	case <-time.After(50 * time.Millisecond):
		return fmt.Sprintf("user-%d-profile", userID), nil
	case <-ctx.Done():
		return "", ctx.Err()
	}
}

func fetchUserOrders(ctx context.Context, userID int) (string, error) {
	select {
	case <-time.After(80 * time.Millisecond):
		return fmt.Sprintf("user-%d-orders", userID), nil
	case <-ctx.Done():
		return "", ctx.Err()
	}
}

func fetchUserRecommendations(ctx context.Context, userID int) (string, error) {
	select {
	case <-time.After(30 * time.Millisecond):
		// Simulate failure
		return "", errors.New("recommendation service unavailable")
	case <-ctx.Done():
		return "", ctx.Err()
	}
}

func main() {
	// ============================================================
	// Pattern 1: Parallel fetch — all must succeed
	// ============================================================
	fmt.Println("=== Pattern 1: All-or-nothing parallel fetch ===")
	{
		g, ctx := WithContext(context.Background())
		var profile, orders, recs string

		g.Go(func() error {
			var err error
			profile, err = fetchUserProfile(ctx, 42) // use derived ctx!
			return err
		})
		g.Go(func() error {
			var err error
			orders, err = fetchUserOrders(ctx, 42)
			return err
		})
		g.Go(func() error {
			var err error
			recs, err = fetchUserRecommendations(ctx, 42)
			return err
		})

		if err := g.Wait(); err != nil {
			fmt.Printf("  FAILED: %v\n", err)
			fmt.Printf("  profile=%q (may be empty — cancelled by first error)\n", profile)
			fmt.Printf("  orders=%q (may be empty — cancelled by first error)\n", orders)
			fmt.Printf("  recs=%q\n\n", recs)
		}
	}

	// ============================================================
	// Pattern 2: Parallel fetch — all succeed (no errors)
	// ============================================================
	fmt.Println("=== Pattern 2: Successful parallel fetch ===")
	{
		g, ctx := WithContext(context.Background())
		var profile, orders string

		g.Go(func() error {
			var err error
			profile, err = fetchUserProfile(ctx, 42)
			return err
		})
		g.Go(func() error {
			var err error
			orders, err = fetchUserOrders(ctx, 42)
			return err
		})

		if err := g.Wait(); err != nil {
			fmt.Printf("  FAILED: %v\n\n", err)
		} else {
			fmt.Printf("  profile=%q\n", profile)
			fmt.Printf("  orders=%q\n\n", orders)
		}
	}

	// ============================================================
	// Pattern 3: Bounded parallelism with SetLimit
	// ============================================================
	fmt.Println("=== Pattern 3: Bounded parallelism (SetLimit) ===")
	{
		g, ctx := WithContext(context.Background())
		g.SetLimit(3) // max 3 concurrent goroutines

		start := time.Now()
		for i := 0; i < 10; i++ {
			id := i
			g.Go(func() error {
				select {
				case <-time.After(50 * time.Millisecond):
					fmt.Printf("  task %d done at %v\n", id, time.Since(start).Round(time.Millisecond))
					return nil
				case <-ctx.Done():
					return ctx.Err()
				}
			})
		}

		if err := g.Wait(); err != nil {
			fmt.Printf("  error: %v\n", err)
		}
		fmt.Printf("  10 tasks, 3 concurrent, ~%v total\n\n", time.Since(start).Round(time.Millisecond))
	}

	// ============================================================
	// Pattern 4: errgroup with timeout
	// ============================================================
	fmt.Println("=== Pattern 4: errgroup + timeout ===")
	{
		ctx, cancel := context.WithTimeout(context.Background(), 60*time.Millisecond)
		defer cancel()

		g, ctx := WithContext(ctx) // derives from the timeout context

		g.Go(func() error {
			select {
			case <-time.After(30 * time.Millisecond):
				fmt.Println("  fast task: done")
				return nil
			case <-ctx.Done():
				return fmt.Errorf("fast task: %w", ctx.Err())
			}
		})
		g.Go(func() error {
			select {
			case <-time.After(200 * time.Millisecond): // longer than timeout
				fmt.Println("  slow task: done")
				return nil
			case <-ctx.Done():
				return fmt.Errorf("slow task: %w", ctx.Err())
			}
		})

		if err := g.Wait(); err != nil {
			fmt.Printf("  result: %v\n", err)
		}
	}

	fmt.Println("\nPitfalls:")
	fmt.Println("  1. Only the FIRST error is returned — others are silently dropped")
	fmt.Println("  2. Use the DERIVED ctx from WithContext, not the parent")
	fmt.Println("  3. The derived ctx is cancelled after Wait() — don't reuse it")
	fmt.Println("  4. Without SetLimit, ALL goroutines launch immediately")
	fmt.Println("  5. Closures must capture loop variables (use := inside loop)")
}
```

Run with `go run main.go` (in a real project, replace the embedded errgroup with `golang.org/x/sync/errgroup`). The key benefit over manual WaitGroup+channel patterns is that errgroup combines goroutine lifecycle management, error collection, and context cancellation into a single, composable API. Use it whenever you have N independent tasks where the first failure should abort the rest.'''),

    ("go_deep/singleflight_dedup_requests", r'''How does singleflight work in Go for deduplicating concurrent requests? Show me a practical example with a cache that prevents thundering herd.''', r'''<think>
singleflight deduplicates concurrent function calls for the same key.
If N goroutines call Do("key", fn) simultaneously, only ONE executes fn, and all N get the same result.
This prevents the "thundering herd" problem.
When a cache entry expires, hundreds of requests try to regenerate it simultaneously.
Without singleflight, 1000 QPS on a popular key means 1000 database queries for the same data.
Key API:
- Do(key, fn) returns (v, err, shared) where shared indicates the result was reused
- DoChan(key, fn) returns a channel — non-blocking, lets you select with a timeout
- Forget(key) removes the in-flight entry so the next call re-executes fn
Important subtlety: if fn returns an error, ALL waiting goroutines get that same error.
A transient network blip punishes everyone waiting on that key.
The Forget() method handles this — call Forget before returning an error so the next caller retries.
singleflight only deduplicates IN-FLIGHT calls — it is NOT a cache.
Once Do returns, the next call with the same key executes fn again.
The typical architecture is: check cache → singleflight → fetch → populate cache.
What about panics? singleflight propagates the panic to all waiting goroutines.
One panic becomes N panics — each caller should have its own recover.
Internally it uses a mutex protecting a map of calls, each with a WaitGroup.
The first caller adds the entry and runs fn; others find it and wg.Wait().
I will implement a minimal self-contained version, then show the thundering herd pattern with a cache wrapper.
</think>

`singleflight` deduplicates concurrent function calls for the same key. If 100 goroutines request the same cache key simultaneously, only one fetches from the database; the other 99 wait and receive the same result.

```go
package main

import (
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

// Minimal singleflight implementation (matches golang.org/x/sync/singleflight)
type call struct {
	wg  sync.WaitGroup
	val any
	err error
}

type SingleFlight struct {
	mu sync.Mutex
	m  map[string]*call
}

func (sf *SingleFlight) Do(key string, fn func() (any, error)) (any, error, bool) {
	sf.mu.Lock()
	if sf.m == nil {
		sf.m = make(map[string]*call)
	}
	if c, ok := sf.m[key]; ok {
		sf.mu.Unlock()
		c.wg.Wait() // wait for the in-flight call to finish
		return c.val, c.err, true // shared=true
	}
	c := &call{}
	c.wg.Add(1)
	sf.m[key] = c
	sf.mu.Unlock()

	c.val, c.err = fn() // only one goroutine executes this
	c.wg.Done()

	sf.mu.Lock()
	delete(sf.m, key)
	sf.mu.Unlock()

	return c.val, c.err, false // shared=false (we were the caller)
}

// ============================================================
// Simulated database and cache
// ============================================================

var dbQueryCount atomic.Int64

func expensiveDBQuery(userID string) (string, error) {
	dbQueryCount.Add(1)
	time.Sleep(100 * time.Millisecond) // simulate slow query
	return fmt.Sprintf("profile-data-for-%s", userID), nil
}

// Cache with singleflight protection
type Cache struct {
	mu    sync.RWMutex
	data  map[string]cacheEntry
	sf    SingleFlight
}

type cacheEntry struct {
	value   string
	expires time.Time
}

func NewCache() *Cache {
	return &Cache{data: make(map[string]cacheEntry)}
}

func (c *Cache) Get(key string) (string, bool) {
	c.mu.RLock()
	entry, ok := c.data[key]
	c.mu.RUnlock()
	if ok && time.Now().Before(entry.expires) {
		return entry.value, true
	}
	return "", false
}

func (c *Cache) Set(key, value string, ttl time.Duration) {
	c.mu.Lock()
	c.data[key] = cacheEntry{value: value, expires: time.Now().Add(ttl)}
	c.mu.Unlock()
}

// GetOrFetch uses singleflight to prevent thundering herd
func (c *Cache) GetOrFetch(key string, fetch func() (string, error)) (string, error) {
	// Check cache first
	if val, ok := c.Get(key); ok {
		return val, nil
	}

	// Cache miss — use singleflight to deduplicate concurrent fetches
	val, err, shared := c.sf.Do(key, func() (any, error) {
		// Double-check cache (another goroutine may have populated it)
		if val, ok := c.Get(key); ok {
			return val, nil
		}
		result, err := fetch()
		if err != nil {
			return nil, err
		}
		c.Set(key, result, 5*time.Second) // cache for 5s
		return result, nil
	})

	if err != nil {
		return "", err
	}
	if shared {
		fmt.Printf("    [shared result — deduped!]\n")
	}
	return val.(string), nil
}

func main() {
	// ============================================================
	// Demo 1: Without singleflight — thundering herd
	// ============================================================
	fmt.Println("=== WITHOUT singleflight: Thundering Herd ===")
	dbQueryCount.Store(0)

	var wg1 sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg1.Add(1)
		go func(id int) {
			defer wg1.Done()
			_, _ = expensiveDBQuery("user-42") // every goroutine hits the DB
		}(i)
	}
	wg1.Wait()
	fmt.Printf("  50 concurrent requests → %d DB queries (all 50 hit DB!)\n\n",
		dbQueryCount.Load())

	// ============================================================
	// Demo 2: With singleflight — deduplicated
	// ============================================================
	fmt.Println("=== WITH singleflight: Deduplicated ===")
	dbQueryCount.Store(0)
	cache := NewCache()

	var wg2 sync.WaitGroup
	start := time.Now()
	for i := 0; i < 50; i++ {
		wg2.Add(1)
		go func(id int) {
			defer wg2.Done()
			val, err := cache.GetOrFetch("user-42", func() (string, error) {
				return expensiveDBQuery("user-42")
			})
			if err != nil {
				fmt.Printf("  goroutine %d: error: %v\n", id, err)
				return
			}
			_ = val
		}(i)
	}
	wg2.Wait()
	elapsed := time.Since(start)
	fmt.Printf("  50 concurrent requests → %d DB query (deduplicated!)\n", dbQueryCount.Load())
	fmt.Printf("  Total time: %v (just one 100ms query, not 50)\n\n", elapsed.Round(time.Millisecond))

	// ============================================================
	// Demo 3: Different keys are NOT deduplicated
	// ============================================================
	fmt.Println("=== Different keys: separate queries ===")
	dbQueryCount.Store(0)
	cache2 := NewCache()

	var wg3 sync.WaitGroup
	for i := 0; i < 5; i++ {
		wg3.Add(1)
		go func(id int) {
			defer wg3.Done()
			key := fmt.Sprintf("user-%d", id) // different keys
			_, _ = cache2.GetOrFetch(key, func() (string, error) {
				return expensiveDBQuery(key)
			})
		}(i)
	}
	wg3.Wait()
	fmt.Printf("  5 different keys → %d DB queries (no dedup — different keys)\n\n",
		dbQueryCount.Load())

	// ============================================================
	// Demo 4: Second wave hits cache
	// ============================================================
	fmt.Println("=== Second wave: cache hit ===")
	dbQueryCount.Store(0)
	var wg4 sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg4.Add(1)
		go func(id int) {
			defer wg4.Done()
			_, _ = cache.GetOrFetch("user-42", func() (string, error) {
				return expensiveDBQuery("user-42")
			})
		}(i)
	}
	wg4.Wait()
	fmt.Printf("  50 more requests → %d DB queries (all served from cache)\n",
		dbQueryCount.Load())

	fmt.Println("\nKey points:")
	fmt.Println("  singleflight deduplicates IN-FLIGHT calls (same key, overlapping time)")
	fmt.Println("  It does NOT cache results — combine with a cache layer")
	fmt.Println("  If the function errors, all waiters get the same error")
	fmt.Println("  Use Forget(key) if you want to allow retries after an error")
	fmt.Println("  Real import: golang.org/x/sync/singleflight")
}
```

Run with `go run main.go`. The critical pattern is the `Cache.GetOrFetch` method: check cache first, then use singleflight for the fetch. This eliminates the thundering herd — instead of 50 database queries when a cache entry expires, exactly 1 query runs and 49 goroutines share its result. In production, this is one of the highest-impact optimizations for any read-heavy service.'''),

    ("go_deep/worker_pool_graceful_shutdown", r'''Implement a worker pool in Go with graceful shutdown that drains all in-flight work before stopping.''', r'''<think>
A worker pool with graceful shutdown needs several components. Let me think through the design.

Core requirements:
1. Fixed number of workers reading from a shared job channel — range over the channel for clean termination
2. A way to stop accepting new jobs — atomic flag or closed state
3. Drain phase: close the job channel, let workers finish in-flight jobs, wait via WaitGroup
4. Timeout on drain — don't wait forever if a job is stuck, have a hard deadline

The lifecycle is: RUNNING → DRAINING → STOPPED. The key insight is that close(jobs) is the drain trigger — workers' range loops will exhaust buffered jobs then exit naturally. No need for a separate "stop" channel.

Design decisions:
- Submit should be non-blocking (return error if full) or blocking (with context). I'll provide both.
- Results channel: workers write results, and it's closed only after ALL workers exit. This ordering is critical — closing results before workers finish causes a panic.
- Panic recovery: each worker wraps job handling in a recover. A panicking job should produce an error result, not kill the worker. Without this, one bad job reduces the pool by one worker permanently.
- The atomic stopped flag prevents submitting jobs after Shutdown is called but before close(jobs) executes. There's a tiny race window otherwise.

Edge case: what if Shutdown is called while Submit is blocking on a full channel? Submit should use select with a context or check the stopped flag. Otherwise it blocks forever because nobody is draining.

I should also show:
- How to handle panics in workers
- How to collect results via a results channel
- Timeout-based forced shutdown that doesn't wait indefinitely
</think>

A production worker pool needs three lifecycle phases: accepting work, draining in-flight jobs, and shutdown. Here is a complete implementation:

```go
package main

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

// Job represents a unit of work
type Job struct {
	ID      int
	Payload string
}

// Result represents a completed job
type Result struct {
	JobID int
	Value string
	Err   error
}

// Pool is a worker pool with graceful shutdown
type Pool struct {
	jobs       chan Job
	results    chan Result
	numWorkers int
	wg         sync.WaitGroup
	stopped    atomic.Bool
	handler    func(Job) Result
}

func NewPool(numWorkers, jobBuffer int, handler func(Job) Result) *Pool {
	p := &Pool{
		jobs:       make(chan Job, jobBuffer),
		results:    make(chan Result, jobBuffer),
		numWorkers: numWorkers,
		handler:    handler,
	}

	// Start workers
	for i := 0; i < numWorkers; i++ {
		p.wg.Add(1)
		go p.worker(i)
	}

	return p
}

func (p *Pool) worker(id int) {
	defer p.wg.Done()
	for job := range p.jobs {
		// Panic recovery — don't let one bad job kill a worker
		func() {
			defer func() {
				if r := recover(); r != nil {
					p.results <- Result{
						JobID: job.ID,
						Err:   fmt.Errorf("worker %d panic: %v", id, r),
					}
				}
			}()
			result := p.handler(job)
			p.results <- result
		}()
	}
	// Channel closed and drained — worker exits cleanly
}

// Submit adds a job to the pool. Returns error if pool is stopped.
func (p *Pool) Submit(job Job) error {
	if p.stopped.Load() {
		return errors.New("pool is stopped, not accepting new jobs")
	}
	select {
	case p.jobs <- job:
		return nil
	default:
		return errors.New("job queue is full")
	}
}

// SubmitWait adds a job, blocking if the queue is full.
func (p *Pool) SubmitWait(ctx context.Context, job Job) error {
	if p.stopped.Load() {
		return errors.New("pool is stopped")
	}
	select {
	case p.jobs <- job:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// Results returns the results channel for reading
func (p *Pool) Results() <-chan Result {
	return p.results
}

// Shutdown stops accepting new jobs and waits for all in-flight work to complete.
func (p *Pool) Shutdown(timeout time.Duration) error {
	p.stopped.Store(true)
	close(p.jobs) // workers will drain remaining jobs then exit

	// Wait with timeout
	done := make(chan struct{})
	go func() {
		p.wg.Wait()
		close(p.results) // safe to close after all workers are done
		close(done)
	}()

	select {
	case <-done:
		return nil
	case <-time.After(timeout):
		return errors.New("shutdown timed out — some workers may still be running")
	}
}

func main() {
	fmt.Println("=== Worker Pool with Graceful Shutdown ===\n")

	// Handler: simulates variable-time processing
	handler := func(job Job) Result {
		// Simulate work — some jobs take longer
		duration := time.Duration(20+job.ID%5*30) * time.Millisecond
		time.Sleep(duration)

		if job.ID == 7 {
			panic("simulated crash on job 7") // test panic recovery
		}

		return Result{
			JobID: job.ID,
			Value: fmt.Sprintf("processed:%s (took %v)", job.Payload, duration),
		}
	}

	pool := NewPool(3, 10, handler) // 3 workers, buffer of 10

	// Collect results in background
	var allResults []Result
	var resultsMu sync.Mutex
	resultsDone := make(chan struct{})
	go func() {
		for r := range pool.Results() {
			resultsMu.Lock()
			allResults = append(allResults, r)
			resultsMu.Unlock()
		}
		close(resultsDone)
	}()

	// Submit 15 jobs
	fmt.Println("Submitting 15 jobs...")
	for i := 0; i < 15; i++ {
		job := Job{ID: i, Payload: fmt.Sprintf("data-%d", i)}
		if err := pool.SubmitWait(context.Background(), job); err != nil {
			fmt.Printf("  submit job %d failed: %v\n", i, err)
		}
	}
	fmt.Println("All jobs submitted.")

	// Try to submit after stop signal
	fmt.Println("\nInitiating graceful shutdown (5s timeout)...")
	start := time.Now()
	if err := pool.Shutdown(5 * time.Second); err != nil {
		fmt.Printf("  shutdown error: %v\n", err)
	} else {
		fmt.Printf("  shutdown complete in %v\n", time.Since(start).Round(time.Millisecond))
	}

	// Try to submit after shutdown
	err := pool.Submit(Job{ID: 99, Payload: "late"})
	fmt.Printf("  submit after shutdown: %v\n", err)

	// Wait for result collector
	<-resultsDone

	// Print results
	fmt.Printf("\nResults (%d total):\n", len(allResults))
	for _, r := range allResults {
		if r.Err != nil {
			fmt.Printf("  job %2d: ERROR: %v\n", r.JobID, r.Err)
		} else {
			fmt.Printf("  job %2d: %s\n", r.JobID, r.Value)
		}
	}

	fmt.Println("\nPool lifecycle:")
	fmt.Println("  1. NewPool(): workers start, blocking on job channel")
	fmt.Println("  2. Submit(): jobs enter the channel buffer")
	fmt.Println("  3. Shutdown(): close(jobs) → workers drain remaining → wg.Wait()")
	fmt.Println("  4. After Shutdown(): Submit() returns error, results channel closed")
	fmt.Println("  5. Workers recover from panics — bad jobs don't kill the pool")
}
```

Run with `go run main.go`. The key design decisions are: (1) `close(jobs)` causes workers' `range` loops to exit naturally after draining the buffer, (2) `sync.WaitGroup` tracks worker completion, (3) `results` channel is closed only after all workers finish, and (4) each worker wraps job handling in a `recover` so panics produce error results instead of killing the worker. The timeout in `Shutdown` prevents hanging if a job is stuck.'''),

    ("go_deep/rate_limiting_token_bucket", r'''Implement a token bucket rate limiter in Go from scratch. Show me how it works and how to use it to limit API calls.''', r'''<think>
Token bucket algorithm — let me think through the design carefully.
Core concept: bucket has capacity C (max burst size) and refill rate R (tokens per second).
Each operation consumes 1 token. If no tokens, block (Wait) or reject (Allow).
Implementation: store token count and last refill timestamp.
On each request, calculate accumulated tokens: elapsed_seconds * rate.
Cap at capacity. This "lazy refill" avoids background goroutine overhead.
Key design decision: tokens should be float64, not int.
Float64 handles fractional accumulation — at 0.5 tokens/sec, after 1s you have 0.5 tokens.
With integers you'd lose this precision and the rate would be wrong.
Thread safety: mutex around token state. Critical section is tiny (refill + check + decrement).
For Wait(), calculate time until next token: deficit/rate seconds.
Sleep for that duration, but support context cancellation for shutdown.
Edge case: very slow rate (0.01/sec) means 100 second wait. Context timeout is essential.
Per-key rate limiting (per user/IP) requires a map of limiters.
The map needs synchronization and should evict stale limiters to prevent memory leaks.
Allow() is for non-blocking rejection (drop excess traffic at the edge).
Wait() is for blocking throttle (slow down your own outgoing API calls).
These are different from bounded parallelism which limits concurrent ops, not throughput.
I should also show the bucket starting full vs empty — starting full allows an initial burst.
</think>

The token bucket algorithm allows bursts up to the bucket capacity while enforcing a long-term average rate. Here is a complete implementation:

```go
package main

import (
	"context"
	"fmt"
	"sync"
	"time"
)

// TokenBucket implements the token bucket rate limiting algorithm.
// Tokens are refilled lazily — no background goroutine needed.
type TokenBucket struct {
	mu         sync.Mutex
	tokens     float64
	capacity   float64       // max burst size
	rate       float64       // tokens per second
	lastRefill time.Time
}

func NewTokenBucket(rate float64, capacity int) *TokenBucket {
	return &TokenBucket{
		tokens:     float64(capacity), // start full
		capacity:   float64(capacity),
		rate:       rate,
		lastRefill: time.Now(),
	}
}

// refill adds tokens based on elapsed time (called under lock)
func (tb *TokenBucket) refill() {
	now := time.Now()
	elapsed := now.Sub(tb.lastRefill).Seconds()
	tb.tokens += elapsed * tb.rate
	if tb.tokens > tb.capacity {
		tb.tokens = tb.capacity
	}
	tb.lastRefill = now
}

// Allow checks if a token is available (non-blocking).
// Returns true and consumes a token, or returns false.
func (tb *TokenBucket) Allow() bool {
	tb.mu.Lock()
	defer tb.mu.Unlock()

	tb.refill()
	if tb.tokens >= 1 {
		tb.tokens--
		return true
	}
	return false
}

// Wait blocks until a token is available or context is cancelled.
func (tb *TokenBucket) Wait(ctx context.Context) error {
	for {
		tb.mu.Lock()
		tb.refill()
		if tb.tokens >= 1 {
			tb.tokens--
			tb.mu.Unlock()
			return nil
		}
		// Calculate wait time for next token
		deficit := 1.0 - tb.tokens
		waitDuration := time.Duration(deficit / tb.rate * float64(time.Second))
		tb.mu.Unlock()

		select {
		case <-time.After(waitDuration):
			// Token should be available now — loop to recheck
		case <-ctx.Done():
			return ctx.Err()
		}
	}
}

// Tokens returns the current token count (for monitoring)
func (tb *TokenBucket) Tokens() float64 {
	tb.mu.Lock()
	defer tb.mu.Unlock()
	tb.refill()
	return tb.tokens
}

func main() {
	// ============================================================
	// Demo 1: Non-blocking rate limiting (Allow)
	// ============================================================
	fmt.Println("=== Demo 1: Non-Blocking (Allow) ===")
	limiter := NewTokenBucket(5, 3) // 5 tokens/sec, burst of 3

	fmt.Println("  Burst: consuming 3 tokens immediately")
	for i := 0; i < 5; i++ {
		allowed := limiter.Allow()
		fmt.Printf("    request %d: allowed=%v (tokens=%.1f)\n", i, allowed, limiter.Tokens())
	}

	fmt.Println("  Waiting 1 second for refill...")
	time.Sleep(1 * time.Second)
	fmt.Printf("  After 1s: tokens=%.1f\n\n", limiter.Tokens())

	// ============================================================
	// Demo 2: Blocking rate limiting (Wait)
	// ============================================================
	fmt.Println("=== Demo 2: Blocking (Wait) ===")
	limiter2 := NewTokenBucket(10, 1) // 10/sec, burst of 1

	start := time.Now()
	for i := 0; i < 10; i++ {
		if err := limiter2.Wait(context.Background()); err != nil {
			fmt.Printf("  request %d: error: %v\n", i, err)
			break
		}
		fmt.Printf("  request %d at %v\n", i, time.Since(start).Round(time.Millisecond))
	}
	fmt.Println()

	// ============================================================
	// Demo 3: Wait with timeout/cancellation
	// ============================================================
	fmt.Println("=== Demo 3: Wait with Timeout ===")
	limiter3 := NewTokenBucket(1, 1) // 1/sec, very slow
	limiter3.Allow()                  // consume the initial token

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	startT := time.Now()
	err := limiter3.Wait(ctx) // should timeout — next token in 1s
	fmt.Printf("  wait result: %v (after %v)\n\n",
		err, time.Since(startT).Round(time.Millisecond))

	// ============================================================
	// Demo 4: Concurrent API call simulation
	// ============================================================
	fmt.Println("=== Demo 4: Concurrent API Calls ===")
	apiLimiter := NewTokenBucket(5, 5) // 5 req/sec, burst of 5

	var wg sync.WaitGroup
	startC := time.Now()
	for i := 0; i < 15; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			if err := apiLimiter.Wait(context.Background()); err != nil {
				fmt.Printf("  api call %2d: rate limit error: %v\n", id, err)
				return
			}
			elapsed := time.Since(startC).Round(time.Millisecond)
			fmt.Printf("  api call %2d: executed at %v\n", id, elapsed)
		}(i)
	}
	wg.Wait()
	total := time.Since(startC).Round(time.Millisecond)
	fmt.Printf("  15 calls at 5/sec: took %v (expected ~2s burst + steady)\n\n", total)

	// ============================================================
	// Demo 5: Per-key rate limiting (e.g., per user)
	// ============================================================
	fmt.Println("=== Demo 5: Per-Key Rate Limiting ===")
	type PerKeyLimiter struct {
		mu       sync.Mutex
		limiters map[string]*TokenBucket
		rate     float64
		burst    int
	}

	pkl := &PerKeyLimiter{
		limiters: make(map[string]*TokenBucket),
		rate:     2,
		burst:    2,
	}

	getLimiter := func(key string) *TokenBucket {
		pkl.mu.Lock()
		defer pkl.mu.Unlock()
		if l, ok := pkl.limiters[key]; ok {
			return l
		}
		l := NewTokenBucket(pkl.rate, pkl.burst)
		pkl.limiters[key] = l
		return l
	}

	users := []string{"alice", "alice", "alice", "bob", "bob", "alice", "alice"}
	for _, user := range users {
		l := getLimiter(user)
		allowed := l.Allow()
		fmt.Printf("  user=%-6s allowed=%v\n", user, allowed)
	}

	fmt.Println("\nToken bucket properties:")
	fmt.Println("  - Capacity (burst): max requests in a burst")
	fmt.Println("  - Rate: sustained requests per second")
	fmt.Println("  - Lazy refill: no goroutine overhead, tokens calculated on demand")
	fmt.Println("  - Allow(): non-blocking, good for dropping excess traffic")
	fmt.Println("  - Wait(): blocking, good for throttling your own outgoing calls")
	fmt.Println("  - For production: use golang.org/x/time/rate (same algorithm, battle-tested)")
}
```

Run with `go run main.go`. The lazy refill approach is key — instead of a background goroutine adding tokens every tick, we calculate accumulated tokens from elapsed time on each call. This makes the limiter zero-overhead when idle. For production use, `golang.org/x/time/rate.Limiter` implements the same algorithm with additional features like reservation and event-based waiting.'''),

    ("go_deep/circuit_breaker_half_open", r'''Implement a circuit breaker in Go with closed, open, and half-open states. Show me how to test the half-open state transition.''', r'''<think>
Circuit breaker pattern — three states in a state machine.
Closed: normal operation, requests pass through. Track consecutive failures.
If failures exceed threshold, trip to Open — start failing fast.
Open: all requests fail immediately without calling the downstream service.
After a timeout period, transition to Half-Open for a recovery probe.
Half-Open: allow ONE trial request through. If it succeeds, close the circuit.
If it fails, reopen — the service is still down.
Implementation needs:
- Thread-safe state management for concurrent Execute calls
- Failure counter tracking consecutive failures, reset on success
- Timer for open-to-half-open transition using time.Since (no background goroutine)
- Configurable thresholds: failure count, open timeout, half-open success count
Edge case: two goroutines call Execute during half-open simultaneously.
Only one should be the probe — the mutex serializes them.
The second goroutine should fail fast, not also probe.
Should failures be consecutive or windowed? Consecutive is simpler.
But a single lucky success resets the counter, potentially masking instability.
Window-based (e.g., "5 failures in 30 seconds") is more robust but complex.
I'll use consecutive for clarity and note the alternative.
Half-open success threshold: requiring just 1 success is too aggressive.
In production, want 2-3 consecutive successes to prove genuine recovery.
I'll make this configurable via a Config struct.
Let me add a state change callback for observability and metrics.
</think>

A circuit breaker prevents cascading failures by failing fast when a downstream service is unhealthy. The half-open state is the recovery probe — it lets one request through to test if the service has recovered.

```go
package main

import (
	"errors"
	"fmt"
	"sync"
	"time"
)

type State int

const (
	Closed   State = iota // normal operation
	Open                  // failing fast
	HalfOpen              // testing recovery
)

func (s State) String() string {
	switch s {
	case Closed:
		return "CLOSED"
	case Open:
		return "OPEN"
	case HalfOpen:
		return "HALF-OPEN"
	default:
		return "UNKNOWN"
	}
}

var ErrCircuitOpen = errors.New("circuit breaker is open")

type CircuitBreaker struct {
	mu sync.Mutex

	state            State
	failureCount     int
	successCount     int
	failureThreshold int           // failures before tripping to Open
	successThreshold int           // successes in HalfOpen before closing
	openTimeout      time.Duration // time in Open before trying HalfOpen
	lastFailure      time.Time

	onStateChange func(from, to State) // optional callback
}

type Config struct {
	FailureThreshold int
	SuccessThreshold int
	OpenTimeout      time.Duration
	OnStateChange    func(from, to State)
}

func NewCircuitBreaker(cfg Config) *CircuitBreaker {
	return &CircuitBreaker{
		state:            Closed,
		failureThreshold: cfg.FailureThreshold,
		successThreshold: cfg.SuccessThreshold,
		openTimeout:      cfg.OpenTimeout,
		onStateChange:    cfg.OnStateChange,
	}
}

func (cb *CircuitBreaker) setState(newState State) {
	if cb.state == newState {
		return
	}
	old := cb.state
	cb.state = newState
	cb.failureCount = 0
	cb.successCount = 0
	if cb.onStateChange != nil {
		cb.onStateChange(old, newState)
	}
}

// Execute runs the function through the circuit breaker.
func (cb *CircuitBreaker) Execute(fn func() error) error {
	cb.mu.Lock()

	switch cb.state {
	case Open:
		// Check if timeout has elapsed → transition to HalfOpen
		if time.Since(cb.lastFailure) >= cb.openTimeout {
			cb.setState(HalfOpen)
			// Fall through to execute the trial request
		} else {
			cb.mu.Unlock()
			return ErrCircuitOpen // fail fast
		}

	case HalfOpen:
		// Only allow one request at a time in half-open
		// (already holding the lock, so this is serialized)
	}

	cb.mu.Unlock()

	// Execute the function
	err := fn()

	cb.mu.Lock()
	defer cb.mu.Unlock()

	if err != nil {
		cb.failureCount++
		cb.lastFailure = time.Now()

		switch cb.state {
		case Closed:
			if cb.failureCount >= cb.failureThreshold {
				cb.setState(Open)
			}
		case HalfOpen:
			// Trial request failed — back to Open
			cb.setState(Open)
		}
		return err
	}

	// Success
	switch cb.state {
	case HalfOpen:
		cb.successCount++
		if cb.successCount >= cb.successThreshold {
			cb.setState(Closed) // recovered!
		}
	case Closed:
		cb.failureCount = 0 // reset consecutive failures on success
	}

	return nil
}

func (cb *CircuitBreaker) State() State {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	// Check for automatic Open → HalfOpen transition
	if cb.state == Open && time.Since(cb.lastFailure) >= cb.openTimeout {
		return HalfOpen
	}
	return cb.state
}

func main() {
	fmt.Println("=== Circuit Breaker: State Machine Demo ===\n")

	cb := NewCircuitBreaker(Config{
		FailureThreshold: 3,            // 3 failures → Open
		SuccessThreshold: 2,            // 2 successes in HalfOpen → Closed
		OpenTimeout:      500 * time.Millisecond, // try HalfOpen after 500ms
		OnStateChange: func(from, to State) {
			fmt.Printf("  >>> STATE CHANGE: %s → %s\n", from, to)
		},
	})

	// Simulated service: fails when unhealthy
	serviceHealthy := true
	callService := func() error {
		if !serviceHealthy {
			return errors.New("service unavailable")
		}
		return nil
	}

	// === Phase 1: Normal operation (Closed) ===
	fmt.Println("--- Phase 1: Normal operation ---")
	for i := 0; i < 3; i++ {
		err := cb.Execute(callService)
		fmt.Printf("  call %d: err=%v, state=%s\n", i, err, cb.State())
	}

	// === Phase 2: Service goes down → circuit opens ===
	fmt.Println("\n--- Phase 2: Service fails → circuit opens ---")
	serviceHealthy = false
	for i := 0; i < 5; i++ {
		err := cb.Execute(callService)
		fmt.Printf("  call %d: err=%v, state=%s\n", i, err, cb.State())
	}

	// === Phase 3: Wait for timeout → half-open ===
	fmt.Println("\n--- Phase 3: Wait for open timeout → half-open ---")
	fmt.Printf("  state before wait: %s\n", cb.State())
	time.Sleep(600 * time.Millisecond)
	fmt.Printf("  state after wait:  %s\n", cb.State())

	// === Phase 4: Trial request in half-open fails → back to open ===
	fmt.Println("\n--- Phase 4: Half-open trial fails → back to open ---")
	err := cb.Execute(callService) // service still down
	fmt.Printf("  trial call: err=%v, state=%s\n", err, cb.State())

	// === Phase 5: Wait again, service recovers ===
	fmt.Println("\n--- Phase 5: Service recovers during half-open ---")
	time.Sleep(600 * time.Millisecond)
	serviceHealthy = true

	// Need successThreshold (2) successes in half-open to close
	for i := 0; i < 3; i++ {
		err := cb.Execute(callService)
		fmt.Printf("  trial call %d: err=%v, state=%s\n", i, err, cb.State())
	}

	// === Phase 6: Back to normal ===
	fmt.Println("\n--- Phase 6: Circuit closed, normal operation ---")
	for i := 0; i < 3; i++ {
		err := cb.Execute(callService)
		fmt.Printf("  call %d: err=%v, state=%s\n", i, err, cb.State())
	}

	fmt.Println("\nCircuit breaker state machine:")
	fmt.Println("  CLOSED ──[failures >= threshold]──→ OPEN")
	fmt.Println("  OPEN ────[timeout elapsed]────────→ HALF-OPEN")
	fmt.Println("  HALF-OPEN ──[trial fails]─────────→ OPEN")
	fmt.Println("  HALF-OPEN ──[N successes]─────────→ CLOSED")
	fmt.Println("\nProduction tips:")
	fmt.Println("  - Track metrics: state transitions, rejection count, recovery time")
	fmt.Println("  - Consider per-endpoint circuit breakers (not global)")
	fmt.Println("  - Exponential backoff on open timeout for repeated failures")
	fmt.Println("  - Libraries: sony/gobreaker, afex/hystrix-go")
}
```

Run with `go run main.go`. The half-open state is the most critical part of the design — it prevents the circuit from staying open forever while also protecting against premature recovery. The `successThreshold` parameter controls how many consecutive successes are needed before the circuit fully closes, preventing a single lucky request from reopening the floodgates.'''),

    ("go_deep/timeout_channel_vs_context", r'''Compare timeout patterns in Go: channel + select with time.After vs context.WithTimeout. When should I use each and what are the tradeoffs?''', r'''<think>
Two main timeout patterns in Go:

1. Channel + select + time.After:
```go
select {
case result := <-ch:
    // got result
case <-time.After(5 * time.Second):
    // timeout
}
```

2. Context:
```go
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
result, err := doSomething(ctx)
```

Tradeoffs:
- time.After creates a timer that's NOT garbage collected until it fires. In a loop, this leaks timers.
- context propagates through the call stack and is the standard Go API pattern
- time.After is simpler for one-shot operations
- context is composable (nested timeouts, cancellation chains)

When to use which:
- time.After: simple one-shot timeout in a select, ad-hoc timeouts
- context: anything that crosses function boundaries, HTTP handlers, database calls

The time.After leak is important: each call creates a timer. If you're in a loop doing `select { case <-ch: case <-time.After(d): }`, each iteration creates a new timer that won't be GC'd until it fires. Use time.NewTimer + timer.Stop() instead.
</think>

Both patterns achieve timeouts but have different composability, performance, and API design implications. Here is a thorough comparison:

```go
package main

import (
	"context"
	"fmt"
	"runtime"
	"time"
)

// ============================================================
// Pattern 1: time.After in select (simple, one-shot)
// ============================================================
func timeAfterPattern() {
	fmt.Println("=== Pattern 1: time.After + select ===")

	ch := make(chan string, 1)
	go func() {
		time.Sleep(200 * time.Millisecond)
		ch <- "result"
	}()

	// Simple timeout — clean and readable for one-shot
	select {
	case result := <-ch:
		fmt.Printf("  got: %s\n", result)
	case <-time.After(500 * time.Millisecond):
		fmt.Println("  timed out")
	}

	// But: will it timeout? Let's make the work slower
	ch2 := make(chan string, 1)
	go func() {
		time.Sleep(500 * time.Millisecond) // slower than timeout
		ch2 <- "late result"
	}()

	select {
	case result := <-ch2:
		fmt.Printf("  got: %s\n", result)
	case <-time.After(100 * time.Millisecond):
		fmt.Println("  timed out (as expected)")
	}
}

// ============================================================
// PROBLEM: time.After leaks timers in loops
// ============================================================
func timeAfterLeakDemo() {
	fmt.Println("\n=== PROBLEM: time.After leaks timers in loops ===")

	ch := make(chan int, 1)
	done := make(chan struct{})

	// BAD: each iteration creates a new timer that lives until it fires
	var m1 runtime.MemStats
	runtime.ReadMemStats(&m1)

	go func() {
		for i := 0; i < 100_000; i++ {
			select {
			case ch <- i:
			case <-time.After(1 * time.Hour): // these timers pile up!
				return
			}
		}
		close(done)
	}()

	// Drain
	count := 0
	for range ch {
		count++
		if count >= 100_000 {
			break
		}
	}
	<-done

	var m2 runtime.MemStats
	runtime.ReadMemStats(&m2)
	fmt.Printf("  100K iterations with time.After: allocs=%d\n", m2.Mallocs-m1.Mallocs)

	// GOOD: reuse a timer
	runtime.ReadMemStats(&m1)
	ch2 := make(chan int, 1)
	done2 := make(chan struct{})

	go func() {
		timer := time.NewTimer(1 * time.Hour)
		defer timer.Stop()
		for i := 0; i < 100_000; i++ {
			timer.Reset(1 * time.Hour)
			select {
			case ch2 <- i:
			case <-timer.C:
				return
			}
		}
		close(done2)
	}()

	count = 0
	for range ch2 {
		count++
		if count >= 100_000 {
			break
		}
	}
	<-done2

	runtime.ReadMemStats(&m2)
	fmt.Printf("  100K iterations with Timer.Reset: allocs=%d (much fewer)\n", m2.Mallocs-m1.Mallocs)
}

// ============================================================
// Pattern 2: context.WithTimeout (composable, standard)
// ============================================================
func contextTimeoutPattern() {
	fmt.Println("\n=== Pattern 2: context.WithTimeout ===")

	// Simulated service call that respects context
	fetchData := func(ctx context.Context, delay time.Duration) (string, error) {
		select {
		case <-time.After(delay):
			return "data", nil
		case <-ctx.Done():
			return "", ctx.Err()
		}
	}

	// Success case
	ctx1, cancel1 := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel1()
	result, err := fetchData(ctx1, 100*time.Millisecond)
	fmt.Printf("  fast call: result=%q, err=%v\n", result, err)

	// Timeout case
	ctx2, cancel2 := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel2()
	result, err = fetchData(ctx2, 500*time.Millisecond)
	fmt.Printf("  slow call: result=%q, err=%v\n", result, err)
}

// ============================================================
// Context advantage: composable nested timeouts
// ============================================================
func nestedTimeoutDemo() {
	fmt.Println("\n=== Context Advantage: Nested Timeouts ===")

	// Outer timeout: entire operation has 300ms
	outerCtx, outerCancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer outerCancel()

	step := func(ctx context.Context, name string, ownTimeout, workTime time.Duration) error {
		// Inner timeout: this step gets its own budget, but clamped to parent
		stepCtx, stepCancel := context.WithTimeout(ctx, ownTimeout)
		defer stepCancel()

		dl, _ := stepCtx.Deadline()
		fmt.Printf("  %s: own=%v, effective=%v\n", name,
			ownTimeout, time.Until(dl).Round(time.Millisecond))

		select {
		case <-time.After(workTime):
			fmt.Printf("  %s: completed\n", name)
			return nil
		case <-stepCtx.Done():
			fmt.Printf("  %s: cancelled: %v\n", name, stepCtx.Err())
			return stepCtx.Err()
		}
	}

	step(outerCtx, "step-1", 100*time.Millisecond, 50*time.Millisecond)
	step(outerCtx, "step-2", 100*time.Millisecond, 50*time.Millisecond)
	// Step 3 requests 500ms but outer context only has ~200ms left
	step(outerCtx, "step-3", 500*time.Millisecond, 300*time.Millisecond)
}

// ============================================================
// Side-by-side: same operation, both patterns
// ============================================================
func sideBySide() {
	fmt.Println("\n=== Side-by-Side Comparison ===")

	// Simulated slow operation
	slowOp := func() <-chan string {
		ch := make(chan string, 1)
		go func() {
			time.Sleep(200 * time.Millisecond)
			ch <- "done"
		}()
		return ch
	}

	// time.After approach
	start := time.Now()
	select {
	case v := <-slowOp():
		fmt.Printf("  time.After: got %q at %v\n", v, time.Since(start).Round(time.Millisecond))
	case <-time.After(100 * time.Millisecond):
		fmt.Printf("  time.After: timeout at %v\n", time.Since(start).Round(time.Millisecond))
	}

	// context approach
	start = time.Now()
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	select {
	case v := <-slowOp():
		fmt.Printf("  context:    got %q at %v\n", v, time.Since(start).Round(time.Millisecond))
	case <-ctx.Done():
		fmt.Printf("  context:    timeout at %v (%v)\n", time.Since(start).Round(time.Millisecond), ctx.Err())
	}
}

func main() {
	timeAfterPattern()
	timeAfterLeakDemo()
	contextTimeoutPattern()
	nestedTimeoutDemo()
	sideBySide()

	fmt.Println("\nDecision guide:")
	fmt.Println("  time.After:")
	fmt.Println("    + Simple, readable for one-shot select")
	fmt.Println("    - Leaks timers in loops (use time.NewTimer + Reset instead)")
	fmt.Println("    - Doesn't propagate through function calls")
	fmt.Println()
	fmt.Println("  context.WithTimeout:")
	fmt.Println("    + Standard Go API — every library accepts context")
	fmt.Println("    + Composable: nested timeouts, parent cancellation")
	fmt.Println("    + No timer leak (context manages its own timer)")
	fmt.Println("    + Carries values (request ID, auth tokens)")
	fmt.Println("    - Slightly more boilerplate (cancel function, defer)")
	fmt.Println()
	fmt.Println("  Rule: use context for anything crossing function boundaries.")
	fmt.Println("  Use time.After only for local, one-shot select statements.")
}
```

Run with `go run main.go`. The timer leak in `time.After` is the biggest practical concern — in a high-throughput loop, each iteration allocates a timer that persists until it fires (potentially hours). Use `time.NewTimer` with explicit `Reset` and `Stop` in loops. For any code that passes timeouts to other functions, `context.WithTimeout` is the only correct choice because it integrates with the entire Go ecosystem (net/http, database/sql, gRPC, etc.).'''),

    ("go_deep/deadlock_detection_debugging", r'''How does Go detect deadlocks at runtime? Write a program that demonstrates different deadlock scenarios and show me how to debug them.''', r'''<think>
Go's runtime detects deadlocks when ALL goroutines are blocked (sleeping). It prints "fatal error: all goroutines are asleep - deadlock!" and dumps goroutine stacks.

Important distinction: Go only detects TOTAL deadlock — where every goroutine is blocked. Partial deadlocks (some goroutines blocked while others are still running) are NOT detected by the runtime. In a real server with HTTP listeners, background workers, and health check goroutines, partial deadlocks are invisible — this is the dangerous case.

Common deadlock scenarios I should demonstrate:
1. Single goroutine blocking on an unbuffered channel (simplest case)
2. Circular channel dependency (A waits for B, B waits for A — classic dining philosophers)
3. Lock ordering violation (goroutine 1 locks A then B, goroutine 2 locks B then A — ABBA deadlock)
4. Forgetting to close a channel when using range (range blocks forever waiting for more values)

For debugging:
- GOTRACEBACK=all environment variable — full goroutine stacks on crash
- runtime.Stack(buf, true) — dump all goroutine stacks programmatically at any time
- net/http/pprof goroutine endpoint — inspect blocked goroutines via HTTP in production
- go vet — catches some lock issues statically (copylocks, etc.)
- -race detector finds data races but NOT deadlocks — different problem

I need to be careful in the demo — I can't actually trigger fatal deadlocks because they kill the process. I'll use wrapper goroutines with timeout detection to show the patterns without crashing. The detector pattern: run the potentially deadlocking code in a goroutine, wait with a timeout, report if it completed or hung.

The fix for lock ordering deadlocks is universal: always acquire locks in a consistent global order (e.g., by address or by a defined hierarchy). This is the same principle used in database systems.
</think>

Go's runtime detects deadlock only when ALL goroutines are asleep. Partial deadlocks (where some goroutines are still running) go undetected. Here is a program demonstrating deadlock patterns and debugging techniques:

```go
package main

import (
	"fmt"
	"runtime"
	"strings"
	"sync"
	"time"
)

// dumpGoroutines prints all goroutine stack traces (like GOTRACEBACK=all)
func dumpGoroutines() string {
	buf := make([]byte, 1<<16)
	n := runtime.Stack(buf, true)
	return string(buf[:n])
}

// detectDeadlock runs fn in a goroutine and checks if it completes within timeout
func detectDeadlock(name string, timeout time.Duration, fn func()) {
	done := make(chan struct{})
	go func() {
		fn()
		close(done)
	}()

	select {
	case <-done:
		fmt.Printf("  [%s] completed normally\n", name)
	case <-time.After(timeout):
		fmt.Printf("  [%s] DEADLOCKED (timed out after %v)\n", name, timeout)
		// Dump goroutine stacks for debugging
		stacks := dumpGoroutines()
		// Find the goroutines that are blocked
		blocked := 0
		for _, line := range strings.Split(stacks, "\n") {
			if strings.Contains(line, "chan receive") || strings.Contains(line, "chan send") ||
				strings.Contains(line, "semacquire") || strings.Contains(line, "Lock") {
				blocked++
			}
		}
		fmt.Printf("    (found ~%d blocked goroutine indicators in stack dump)\n", blocked)
	}
}

// ============================================================
// Deadlock 1: Single goroutine channel block
// ============================================================
func deadlock1() {
	fmt.Println("\n=== Deadlock 1: Channel blocks in same goroutine ===")
	detectDeadlock("unbuf-self", 200*time.Millisecond, func() {
		ch := make(chan int)
		// This goroutine sends and expects to receive,
		// but send blocks because nobody is receiving
		ch <- 42     // blocks here forever
		fmt.Println(<-ch) // never reached
	})
}

// ============================================================
// Deadlock 2: Circular channel dependency
// ============================================================
func deadlock2() {
	fmt.Println("\n=== Deadlock 2: Circular channel dependency ===")
	detectDeadlock("circular-chan", 200*time.Millisecond, func() {
		ch1 := make(chan int)
		ch2 := make(chan int)

		go func() {
			val := <-ch1  // waits for ch1
			ch2 <- val    // then sends to ch2
		}()

		go func() {
			val := <-ch2  // waits for ch2
			ch1 <- val    // then sends to ch1
		}()

		// Both goroutines wait for each other: ch1 waits for ch2, ch2 waits for ch1
		// We need to kickstart one of them, but we don't
		time.Sleep(300 * time.Millisecond)
	})
}

// ============================================================
// Deadlock 3: Lock ordering violation
// ============================================================
func deadlock3() {
	fmt.Println("\n=== Deadlock 3: Lock ordering violation (ABBA deadlock) ===")
	detectDeadlock("lock-order", 200*time.Millisecond, func() {
		var muA, muB sync.Mutex
		var wg sync.WaitGroup

		wg.Add(2)
		go func() {
			defer wg.Done()
			muA.Lock()                            // goroutine 1: lock A
			time.Sleep(10 * time.Millisecond)     // ensure interleaving
			muB.Lock()                            // goroutine 1: try lock B (BLOCKED — goroutine 2 holds B)
			muB.Unlock()
			muA.Unlock()
		}()

		go func() {
			defer wg.Done()
			muB.Lock()                            // goroutine 2: lock B
			time.Sleep(10 * time.Millisecond)
			muA.Lock()                            // goroutine 2: try lock A (BLOCKED — goroutine 1 holds A)
			muA.Unlock()
			muB.Unlock()
		}()

		wg.Wait()
	})
}

// ============================================================
// Deadlock 4: Forgetting to close channel (range blocks forever)
// ============================================================
func deadlock4() {
	fmt.Println("\n=== Deadlock 4: range over channel never closed ===")
	detectDeadlock("unclosed-range", 200*time.Millisecond, func() {
		ch := make(chan int, 3)
		ch <- 1
		ch <- 2
		ch <- 3
		// forgot: close(ch)

		for v := range ch { // blocks after reading 3 values — channel not closed
			_ = v
		}
	})
}

// ============================================================
// Fix examples
// ============================================================
func fix1() {
	fmt.Println("\n=== Fix 1: Use goroutine for send ===")
	detectDeadlock("fix-goroutine", 200*time.Millisecond, func() {
		ch := make(chan int)
		go func() { ch <- 42 }() // send in separate goroutine
		val := <-ch
		_ = val
	})
}

func fix3() {
	fmt.Println("\n=== Fix 3: Consistent lock ordering ===")
	detectDeadlock("fix-lock-order", 200*time.Millisecond, func() {
		var muA, muB sync.Mutex
		var wg sync.WaitGroup

		// BOTH goroutines lock A first, then B — consistent ordering
		lockBoth := func() {
			muA.Lock()
			muB.Lock()
			time.Sleep(5 * time.Millisecond)
			muB.Unlock()
			muA.Unlock()
		}

		wg.Add(2)
		go func() { defer wg.Done(); lockBoth() }()
		go func() { defer wg.Done(); lockBoth() }()
		wg.Wait()
	})
}

func fix4() {
	fmt.Println("\n=== Fix 4: Close channel when done sending ===")
	detectDeadlock("fix-close", 200*time.Millisecond, func() {
		ch := make(chan int, 3)
		ch <- 1
		ch <- 2
		ch <- 3
		close(ch) // now range will terminate

		for v := range ch {
			_ = v
		}
	})
}

// ============================================================
// Runtime deadlock detection demo
// ============================================================
func runtimeDetectionInfo() {
	fmt.Println("\n=== Go Runtime Deadlock Detection ===")
	fmt.Println("  Go detects deadlock ONLY when ALL goroutines are asleep.")
	fmt.Println("  If even one goroutine is runnable, no detection occurs.")
	fmt.Println()
	fmt.Println("  This program uses timeout-based detection because actual")
	fmt.Println("  runtime deadlock detection kills the process with:")
	fmt.Println("    'fatal error: all goroutines are asleep - deadlock!'")
	fmt.Println()
	fmt.Println("  To trigger it, run this in a separate file:")
	fmt.Println("    package main")
	fmt.Println("    func main() { <-make(chan int) } // instant deadlock")
}

func main() {
	fmt.Println("=== Deadlock Detection and Debugging in Go ===")

	deadlock1()
	fix1()
	deadlock2()
	deadlock3()
	fix3()
	deadlock4()
	fix4()
	runtimeDetectionInfo()

	fmt.Println("\nDebugging tools:")
	fmt.Println("  1. GOTRACEBACK=all ./program  — full goroutine dump on crash")
	fmt.Println("  2. runtime.Stack(buf, true)    — dump goroutines programmatically")
	fmt.Println("  3. /debug/pprof/goroutine      — HTTP endpoint in net/http/pprof")
	fmt.Println("  4. go vet ./...                — static analysis (some lock issues)")
	fmt.Println("  5. go run -race ./...          — data race detection (not deadlocks)")
	fmt.Println()
	fmt.Println("Prevention rules:")
	fmt.Println("  1. Always lock mutexes in the same order across all goroutines")
	fmt.Println("  2. Always close channels from the sender side")
	fmt.Println("  3. Use select with context.Done() to add escape hatches")
	fmt.Println("  4. Prefer channel-based designs over complex mutex hierarchies")
	fmt.Println("  5. Monitor runtime.NumGoroutine() — growing count means blocked goroutines")
}
```

Run with `go run main.go`. The most important takeaway is that Go's built-in deadlock detection only fires when ALL goroutines are blocked. In any real server (which has HTTP listeners, background workers, etc.), partial deadlocks are invisible to the runtime. That is why monitoring goroutine count and inspecting `/debug/pprof/goroutine` are essential production practices. A goroutine count that only grows over time is the primary signal of a deadlock or leak.'''),
]
