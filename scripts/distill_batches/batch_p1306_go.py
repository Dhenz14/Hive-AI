"""Go training pairs (part 1): goroutines, channels, interfaces, error handling, context."""

PAIRS = [
    (
        "go/goroutines-waitgroup",
        r'''Write a Go program that concurrently fetches multiple URLs and collects their HTTP status codes using goroutines and sync.WaitGroup.''',
        r'''<think>
Need goroutines to fetch URLs concurrently. WaitGroup tracks completion.
Must protect shared results with a mutex since multiple goroutines write to the map.
Use http.Head for lightweight status checks. Defer wg.Done() in each goroutine.
Pass the URL as a goroutine parameter to avoid closure capture bugs.
Collect results in a map[string]int guarded by sync.Mutex.
</think>

```go
package main

import (
	"fmt"
	"net/http"
	"sync"
)

func fetchStatuses(urls []string) map[string]int {
	var (
		mu      sync.Mutex
		wg      sync.WaitGroup
		results = make(map[string]int, len(urls))
	)

	for _, u := range urls {
		wg.Add(1)
		go func(url string) {
			defer wg.Done()
			resp, err := http.Head(url)
			status := -1
			if err == nil {
				status = resp.StatusCode
				resp.Body.Close()
			}
			mu.Lock()
			results[url] = status
			mu.Unlock()
		}(u)
	}

	wg.Wait()
	return results
}

func main() {
	urls := []string{
		"https://go.dev",
		"https://pkg.go.dev",
		"https://example.com",
	}
	for url, code := range fetchStatuses(urls) {
		fmt.Printf("%s -> %d\n", url, code)
	}
}
```

Each goroutine receives its own copy of `url` via the function parameter, avoiding the classic closure-over-loop-variable bug. The mutex serializes writes to the shared map since Go maps are not safe for concurrent writes.'''
    ),
    (
        "go/buffered-channels",
        r'''Explain the difference between buffered and unbuffered channels in Go with a practical example showing when buffered channels prevent goroutine leaks.''',
        r'''<think>
Unbuffered channels block the sender until a receiver is ready (synchronous).
Buffered channels allow sending up to capacity without blocking.
A common goroutine leak: launching a goroutine that sends on an unbuffered channel,
but the receiver gives up early (e.g., timeout). The goroutine blocks forever.
A buffered channel of size 1 lets the goroutine complete its send and exit.
Show both scenarios side by side for clarity.
</think>

**Unbuffered channels** block the sender until a receiver reads. **Buffered channels** allow `cap` sends before blocking.

```go
package main

import (
	"context"
	"fmt"
	"time"
)

// BAD: goroutine leak with unbuffered channel
func leakySearch(ctx context.Context) string {
	ch := make(chan string) // unbuffered
	go func() {
		// Simulate slow work
		time.Sleep(5 * time.Second)
		ch <- "result" // blocks forever if nobody reads
	}()

	select {
	case res := <-ch:
		return res
	case <-ctx.Done():
		return "timeout"
		// goroutine is stuck on ch <- "result" forever!
	}
}

// GOOD: buffered channel prevents the leak
func safeSearch(ctx context.Context) string {
	ch := make(chan string, 1) // buffered: goroutine can send and exit
	go func() {
		time.Sleep(5 * time.Second)
		ch <- "result" // succeeds even if no one reads
	}()

	select {
	case res := <-ch:
		return res
	case <-ctx.Done():
		return "timeout"
		// goroutine will send into the buffer and exit cleanly
	}
}

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer cancel()

	fmt.Println(safeSearch(ctx))
}
```

Rule of thumb: when a goroutine might outlive the receiver, use a buffered channel of size 1 so the send never blocks permanently.'''
    ),
    (
        "go/select-statement",
        r'''Show how to use Go's select statement to multiplex between two channels with a timeout, and explain what happens when multiple cases are ready simultaneously.''',
        r'''<think>
Select blocks until one of its cases can proceed. If multiple cases are ready
simultaneously, Go picks one at random (uniform pseudo-random selection).
This prevents starvation of any single channel.
Show a practical example with two producer channels and a timeout using time.After.
Include the default case concept briefly.
</think>

```go
package main

import (
	"fmt"
	"math/rand"
	"time"
)

func producer(name string, ch chan<- string) {
	for i := 0; ; i++ {
		time.Sleep(time.Duration(rand.Intn(500)) * time.Millisecond)
		ch <- fmt.Sprintf("%s-%d", name, i)
	}
}

func main() {
	ch1 := make(chan string)
	ch2 := make(chan string)

	go producer("sensor-A", ch1)
	go producer("sensor-B", ch2)

	timeout := time.After(3 * time.Second)

	for {
		select {
		case msg := <-ch1:
			fmt.Println("From ch1:", msg)
		case msg := <-ch2:
			fmt.Println("From ch2:", msg)
		case <-timeout:
			fmt.Println("Done: 3s elapsed")
			return
		}
	}
}
```

Key behaviors of `select`:

1. **Blocking**: without a `default` case, `select` blocks until at least one case is ready.
2. **Random selection**: if both `ch1` and `ch2` are ready, Go picks one uniformly at random -- this prevents one channel from starving the other.
3. **`default` case**: makes select non-blocking. Useful for try-send / try-receive patterns:

```go
select {
case ch <- val:
    // sent
default:
    // channel full or no receiver, skip
}
```

4. **Nil channel trick**: a nil channel blocks forever in select, so you can "disable" a case by setting its channel to nil.'''
    ),
    (
        "go/fan-out-fan-in",
        r'''Implement a fan-out/fan-in pipeline in Go that reads file paths from a channel, computes SHA256 checksums concurrently with N workers, and collects results.''',
        r'''<think>
Fan-out: multiple goroutines read from a single input channel.
Fan-in: a single channel collects results from all workers.
Use a WaitGroup to know when all workers are done, then close the results channel.
Launch the closer in a separate goroutine so the main goroutine can range over results.
Each worker reads paths, computes SHA256, and sends the result.
</think>

```go
package main

import (
	"crypto/sha256"
	"fmt"
	"io"
	"os"
	"sync"
)

type FileHash struct {
	Path string
	Hash string
	Err  error
}

func hashWorker(paths <-chan string, results chan<- FileHash, wg *sync.WaitGroup) {
	defer wg.Done()
	for path := range paths {
		h := sha256.New()
		f, err := os.Open(path)
		if err != nil {
			results <- FileHash{Path: path, Err: err}
			continue
		}
		_, err = io.Copy(h, f)
		f.Close()
		if err != nil {
			results <- FileHash{Path: path, Err: err}
			continue
		}
		results <- FileHash{Path: path, Hash: fmt.Sprintf("%x", h.Sum(nil))}
	}
}

func HashFiles(paths []string, numWorkers int) []FileHash {
	pathCh := make(chan string)
	resultCh := make(chan FileHash)

	// Fan-out: start N workers
	var wg sync.WaitGroup
	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		go hashWorker(pathCh, resultCh, &wg)
	}

	// Feed paths
	go func() {
		for _, p := range paths {
			pathCh <- p
		}
		close(pathCh)
	}()

	// Close results when all workers finish (fan-in merger)
	go func() {
		wg.Wait()
		close(resultCh)
	}()

	// Collect
	var results []FileHash
	for r := range resultCh {
		results = append(results, r)
	}
	return results
}

func main() {
	files := []string{"/etc/hosts", "/etc/resolv.conf", "/etc/hostname"}
	for _, fh := range HashFiles(files, 4) {
		if fh.Err != nil {
			fmt.Printf("ERR  %s: %v\n", fh.Path, fh.Err)
		} else {
			fmt.Printf("OK   %s: %s\n", fh.Path, fh.Hash)
		}
	}
}
```

The pattern has three stages: (1) a sender goroutine feeds the input channel and closes it, (2) N workers consume from that channel and produce results, (3) a closer goroutine waits on the WaitGroup and closes the results channel so the consumer can `range` over it cleanly.'''
    ),
    (
        "go/interfaces-implicit",
        r'''Show how Go interfaces work implicitly with a real example: define a Storage interface and implement it with both an in-memory store and a file-backed store, demonstrating polymorphism.''',
        r'''<think>
Go interfaces are satisfied implicitly -- no "implements" keyword.
Any type that has the right method set satisfies the interface.
Define a Storage interface with Get/Set/Delete methods.
Implement MemoryStorage using a map and FileStorage using the filesystem.
Show a function that accepts the interface, proving polymorphism.
Keep it practical and idiomatic.
</think>

```go
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

var ErrNotFound = errors.New("key not found")

// Interface -- no explicit "implements" needed
type Storage interface {
	Get(key string) ([]byte, error)
	Set(key string, value []byte) error
	Delete(key string) error
}

// --- In-memory implementation ---

type MemoryStorage struct {
	mu   sync.RWMutex
	data map[string][]byte
}

func NewMemoryStorage() *MemoryStorage {
	return &MemoryStorage{data: make(map[string][]byte)}
}

func (m *MemoryStorage) Get(key string) ([]byte, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	v, ok := m.data[key]
	if !ok {
		return nil, ErrNotFound
	}
	return v, nil
}

func (m *MemoryStorage) Set(key string, value []byte) error {
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

// --- File-backed implementation ---

type FileStorage struct {
	dir string
}

func NewFileStorage(dir string) (*FileStorage, error) {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, err
	}
	return &FileStorage{dir: dir}, nil
}

func (f *FileStorage) path(key string) string {
	return filepath.Join(f.dir, key+".dat")
}

func (f *FileStorage) Get(key string) ([]byte, error) {
	data, err := os.ReadFile(f.path(key))
	if errors.Is(err, os.ErrNotExist) {
		return nil, ErrNotFound
	}
	return data, err
}

func (f *FileStorage) Set(key string, value []byte) error {
	return os.WriteFile(f.path(key), value, 0o644)
}

func (f *FileStorage) Delete(key string) error {
	err := os.Remove(f.path(key))
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	return err
}

// --- Polymorphic consumer ---

func SaveJSON(s Storage, key string, v any) error {
	data, err := json.Marshal(v)
	if err != nil {
		return err
	}
	return s.Set(key, data)
}

func main() {
	// Both satisfy Storage without declaring "implements"
	var s Storage = NewMemoryStorage()
	_ = SaveJSON(s, "user:1", map[string]string{"name": "Alice"})
	data, _ := s.Get("user:1")
	fmt.Println("memory:", string(data))

	fs, _ := NewFileStorage("/tmp/store")
	s = fs // swap implementation seamlessly
	_ = SaveJSON(s, "user:1", map[string]string{"name": "Bob"})
	data, _ = s.Get("user:1")
	fmt.Println("file:", string(data))
}
```

The key insight: `SaveJSON` depends only on the `Storage` interface, not on concrete types. You can swap `MemoryStorage` for `FileStorage` (or a future `RedisStorage`) without changing any consuming code.'''
    ),
    (
        "go/interface-embedding-assertion",
        r'''Demonstrate Go interface embedding and type assertions. Create a ReadWriteCloser from smaller interfaces and show safe type assertion with the comma-ok idiom.''',
        r'''<think>
Interface embedding composes interfaces by including one inside another.
The standard library does this with io.ReadWriter embedding io.Reader and io.Writer.
Type assertions let you recover the concrete type or check for optional interfaces.
The comma-ok idiom prevents panics on failed assertions.
Show a practical example with a custom connection type.
</think>

```go
package main

import (
	"fmt"
	"strings"
)

// Small interfaces
type Reader interface {
	Read(p []byte) (int, error)
}

type Writer interface {
	Write(p []byte) (int, error)
}

type Closer interface {
	Close() error
}

// Embedded (composed) interface
type ReadWriteCloser interface {
	Reader
	Writer
	Closer
}

// Optional interface for types that support stats
type Statter interface {
	Stats() map[string]int64
}

// Concrete type satisfying ReadWriteCloser + Statter
type BufferedConn struct {
	buf       strings.Builder
	bytesIn   int64
	bytesOut  int64
	closed    bool
}

func (c *BufferedConn) Read(p []byte) (int, error) {
	n := copy(p, []byte(c.buf.String()))
	c.bytesIn += int64(n)
	return n, nil
}

func (c *BufferedConn) Write(p []byte) (int, error) {
	n, err := c.buf.Write(p)
	c.bytesOut += int64(n)
	return n, err
}

func (c *BufferedConn) Close() error {
	c.closed = true
	return nil
}

func (c *BufferedConn) Stats() map[string]int64 {
	return map[string]int64{"bytes_in": c.bytesIn, "bytes_out": c.bytesOut}
}

// Consumer uses the broad interface, optionally checks for Statter
func handleConn(rwc ReadWriteCloser) {
	rwc.Write([]byte("hello"))
	defer rwc.Close()

	// Safe type assertion with comma-ok
	if s, ok := rwc.(Statter); ok {
		fmt.Println("Stats available:", s.Stats())
	} else {
		fmt.Println("No stats support")
	}

	// Type switch for multiple possibilities
	switch v := rwc.(type) {
	case *BufferedConn:
		fmt.Printf("BufferedConn, closed=%v\n", v.closed)
	default:
		fmt.Printf("Unknown type: %T\n", v)
	}
}

func main() {
	conn := &BufferedConn{}
	handleConn(conn)
}
```

Key points:
- **Interface embedding**: `ReadWriteCloser` gets all methods from `Reader`, `Writer`, and `Closer` without repeating signatures.
- **Comma-ok assertion**: `s, ok := rwc.(Statter)` returns `ok=false` instead of panicking if the type doesn't implement `Statter`.
- **Type switch**: `switch v := rwc.(type)` branches on the concrete type, useful for optional optimizations.'''
    ),
    (
        "go/error-wrapping",
        r'''Show Go 1.13+ error wrapping with fmt.Errorf %w, errors.Is, and errors.As. Include a real scenario with a repository layer wrapping a database error.''',
        r'''<think>
Go 1.13 introduced error wrapping with %w in fmt.Errorf.
errors.Is checks if any error in the chain matches a target value.
errors.As checks if any error in the chain matches a target type.
Practical pattern: repo layer wraps sql.ErrNoRows into a domain ErrNotFound,
and the handler checks with errors.Is.
Show the full chain from DB to handler.
</think>

```go
package main

import (
	"database/sql"
	"errors"
	"fmt"
	"log"
)

// Domain errors
var (
	ErrNotFound    = errors.New("not found")
	ErrPermission  = errors.New("permission denied")
)

// Custom error type with context
type ValidationError struct {
	Field   string
	Message string
}

func (e *ValidationError) Error() string {
	return fmt.Sprintf("validation: %s - %s", e.Field, e.Message)
}

// Repository layer -- wraps DB errors into domain errors
func getUserByID(id int) (string, error) {
	// Simulate sql.ErrNoRows
	err := sql.ErrNoRows

	if errors.Is(err, sql.ErrNoRows) {
		// Wrap with %w to preserve the chain
		return "", fmt.Errorf("getUserByID(%d): %w", id, ErrNotFound)
	}
	return "", fmt.Errorf("getUserByID(%d): %w", id, err)
}

func validateAge(age int) error {
	if age < 0 || age > 150 {
		return &ValidationError{Field: "age", Message: fmt.Sprintf("invalid value %d", age)}
	}
	return nil
}

func main() {
	// errors.Is -- checks value match anywhere in the chain
	_, err := getUserByID(42)
	if errors.Is(err, ErrNotFound) {
		fmt.Println("User not found (matched via errors.Is)")
	}

	// The wrapped message includes context
	fmt.Println("Full error:", err)

	// errors.As -- extracts a specific error type from the chain
	err = fmt.Errorf("processing request: %w", validateAge(-5))

	var ve *ValidationError
	if errors.As(err, &ve) {
		fmt.Printf("Validation failed on field %q: %s\n", ve.Field, ve.Message)
	}

	// Wrapping multiple levels
	inner := fmt.Errorf("query failed: %w", sql.ErrConnDone)
	middle := fmt.Errorf("repo.GetUser: %w", inner)
	outer := fmt.Errorf("handler: %w", middle)

	// errors.Is traverses the entire chain
	if errors.Is(outer, sql.ErrConnDone) {
		log.Println("Connection issue detected through 3 layers of wrapping")
	}
}
```

Best practices:
- Use `%w` (not `%v`) to make errors unwrappable.
- Define sentinel errors (`var ErrNotFound = errors.New(...)`) for value comparisons with `errors.Is`.
- Define error types (`type ValidationError struct{...}`) for rich context extraction with `errors.As`.
- Wrap at each layer with added context so the full chain reads like a stack trace.'''
    ),
    (
        "go/custom-error-types",
        r'''Create a custom error type in Go for an HTTP API that includes status code, user-facing message, and internal details. Show how it integrates with errors.As and JSON responses.''',
        r'''<think>
A custom API error type should carry an HTTP status code, a safe user message,
and internal details for logging. Implement the error interface.
Show middleware that uses errors.As to extract the APIError and write a JSON response.
If the error is not an APIError, return 500 with a generic message.
This is a very common pattern in Go HTTP services.
</think>

```go
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
)

type APIError struct {
	Status   int    `json:"-"`
	Code     string `json:"code"`
	Message  string `json:"message"`
	Internal string `json:"-"` // never sent to client
}

func (e *APIError) Error() string {
	return fmt.Sprintf("[%d] %s: %s", e.Status, e.Code, e.Internal)
}

// Constructors for common errors
func ErrNotFound(resource string, id any) *APIError {
	return &APIError{
		Status:   http.StatusNotFound,
		Code:     "NOT_FOUND",
		Message:  fmt.Sprintf("%s not found", resource),
		Internal: fmt.Sprintf("%s with id=%v not found", resource, id),
	}
}

func ErrBadRequest(msg, detail string) *APIError {
	return &APIError{
		Status:   http.StatusBadRequest,
		Code:     "BAD_REQUEST",
		Message:  msg,
		Internal: detail,
	}
}

// Service layer returns wrapped APIErrors
func getUser(id int) (map[string]string, error) {
	if id <= 0 {
		return nil, ErrBadRequest("Invalid user ID", fmt.Sprintf("got id=%d", id))
	}
	// Simulate not found
	return nil, fmt.Errorf("getUser: %w", ErrNotFound("user", id))
}

// Error-handling middleware
func handleError(w http.ResponseWriter, err error) {
	var apiErr *APIError
	if errors.As(err, &apiErr) {
		log.Printf("API error: %s", apiErr.Error()) // log internal details
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(apiErr.Status)
		json.NewEncoder(w).Encode(apiErr) // only Code + Message sent
		return
	}

	// Unknown error: log everything, send generic 500
	log.Printf("Unexpected error: %v", err)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusInternalServerError)
	json.NewEncoder(w).Encode(map[string]string{
		"code":    "INTERNAL_ERROR",
		"message": "An unexpected error occurred",
	})
}

func userHandler(w http.ResponseWriter, r *http.Request) {
	user, err := getUser(-1)
	if err != nil {
		handleError(w, err)
		return
	}
	json.NewEncoder(w).Encode(user)
}

func main() {
	http.HandleFunc("/user", userHandler)
	log.Println("Listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
```

The `Internal` field is tagged `json:"-"` so it never leaks to clients. `errors.As` unwraps through `fmt.Errorf` wrapping to find the `*APIError` anywhere in the chain.'''
    ),
    (
        "go/context-timeout-cancel",
        r'''Show how to use context.WithTimeout and context.WithCancel in Go to manage a long-running operation with proper cleanup.''',
        r'''<think>
Context is Go's mechanism for cancellation, deadlines, and request-scoped values.
WithTimeout creates a context that auto-cancels after a duration.
WithCancel creates a manually cancellable context.
Always defer cancel() to release resources even if the context expires naturally.
Show a practical example: a service that queries an external API with a timeout
and a parent context that can cancel multiple child operations.
</think>

```go
package main

import (
	"context"
	"fmt"
	"math/rand"
	"time"
)

// Simulates an external API call that respects context cancellation
func queryAPI(ctx context.Context, endpoint string) (string, error) {
	delay := time.Duration(100+rand.Intn(400)) * time.Millisecond

	select {
	case <-time.After(delay):
		return fmt.Sprintf("data from %s", endpoint), nil
	case <-ctx.Done():
		return "", fmt.Errorf("queryAPI(%s): %w", endpoint, ctx.Err())
	}
}

// Aggregates results from multiple APIs with a shared timeout
func fetchAll(ctx context.Context) ([]string, error) {
	// Child context with 200ms timeout
	ctx, cancel := context.WithTimeout(ctx, 200*time.Millisecond)
	defer cancel() // always call cancel to free resources

	endpoints := []string{"/users", "/orders", "/inventory"}
	type result struct {
		data string
		err  error
	}

	ch := make(chan result, len(endpoints))
	for _, ep := range endpoints {
		go func(ep string) {
			data, err := queryAPI(ctx, ep)
			ch <- result{data, err}
		}(ep)
	}

	var results []string
	for range endpoints {
		r := <-ch
		if r.err != nil {
			return results, r.err // context.DeadlineExceeded if timed out
		}
		results = append(results, r.data)
	}
	return results, nil
}

func main() {
	// Parent context with manual cancel (e.g., on SIGINT)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Uncomment to simulate early cancellation:
	// go func() { time.Sleep(50*time.Millisecond); cancel() }()

	results, err := fetchAll(ctx)
	if err != nil {
		fmt.Println("Error:", err)
	}
	for _, r := range results {
		fmt.Println(r)
	}
}
```

Important rules:
1. **Always `defer cancel()`** -- even if the timeout fires, calling cancel releases timer resources.
2. **Check `ctx.Done()`** in `select` to respond to cancellation promptly.
3. **`ctx.Err()`** returns `context.DeadlineExceeded` or `context.Canceled` after the context is done.
4. **Pass context as the first parameter** by convention: `func Foo(ctx context.Context, ...)`.'''
    ),
    (
        "go/context-withvalue",
        r'''When and how should you use context.WithValue in Go? Show a middleware example that sets a request ID and a handler that retrieves it, with proper key typing.''',
        r'''<think>
context.WithValue stores request-scoped data. Common use: request IDs, auth info.
Use unexported custom types as keys to avoid collisions across packages.
Never store optional function parameters or config in context -- only request-scoped data.
Show a middleware that generates a request ID and a handler that reads it.
Use a typed key, not a bare string, to prevent key collisions.
</think>

```go
package main

import (
	"context"
	"fmt"
	"net/http"

	"github.com/google/uuid"
)

// Unexported type prevents key collisions across packages
type ctxKey string

const requestIDKey ctxKey = "request_id"

// WithRequestID stores a request ID in the context
func WithRequestID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, requestIDKey, id)
}

// RequestID retrieves the request ID (returns "" if missing)
func RequestID(ctx context.Context) string {
	if id, ok := ctx.Value(requestIDKey).(string); ok {
		return id
	}
	return ""
}

// Middleware injects request ID
func requestIDMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get("X-Request-ID")
		if id == "" {
			id = uuid.NewString()
		}
		ctx := WithRequestID(r.Context(), id)
		w.Header().Set("X-Request-ID", id)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// Handler reads the request ID from context
func helloHandler(w http.ResponseWriter, r *http.Request) {
	reqID := RequestID(r.Context())
	fmt.Fprintf(w, "Hello! Request ID: %s\n", reqID)
}

// Deep function can access request ID without threading it through params
func doWork(ctx context.Context) {
	fmt.Printf("Processing request %s\n", RequestID(ctx))
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/hello", helloHandler)

	handler := requestIDMiddleware(mux)
	http.ListenAndServe(":8080", handler)
}
```

Guidelines for `context.WithValue`:
- **DO**: request IDs, auth tokens, trace spans -- data that crosses API boundaries.
- **DON'T**: database connections, loggers, config -- pass those explicitly.
- **Always use typed keys** (`type ctxKey string`) to prevent collisions between packages.
- **Provide helper functions** (`WithRequestID` / `RequestID`) instead of exposing the raw key.'''
    ),
    (
        "go/table-driven-tests",
        r'''Write table-driven tests in Go for a function that validates email addresses. Include subtests with t.Run and show how to handle edge cases.''',
        r'''<think>
Table-driven tests are the idiomatic Go testing pattern: define a slice of
test cases with inputs and expected outputs, then loop with t.Run for subtests.
Each subtest gets its own name, so failures are easy to identify.
Use t.Parallel() for independent test cases.
Test a validateEmail function with various edge cases.
Keep the validation simple but realistic.
</think>

```go
package main

import (
	"regexp"
	"strings"
	"testing"
)

// Function under test
func ValidateEmail(email string) error {
	if email == "" {
		return &ValidationErr{"email is required"}
	}
	if len(email) > 254 {
		return &ValidationErr{"email too long"}
	}
	// Simplified RFC 5322 check
	pattern := `^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$`
	if !regexp.MustCompile(pattern).MatchString(email) {
		return &ValidationErr{"invalid email format"}
	}
	return nil
}

type ValidationErr struct{ Msg string }

func (e *ValidationErr) Error() string { return e.Msg }

// Table-driven tests
func TestValidateEmail(t *testing.T) {
	tests := []struct {
		name    string
		email   string
		wantErr bool
		errMsg  string
	}{
		{
			name:    "valid simple email",
			email:   "user@example.com",
			wantErr: false,
		},
		{
			name:    "valid with dots and plus",
			email:   "first.last+tag@sub.domain.org",
			wantErr: false,
		},
		{
			name:    "empty string",
			email:   "",
			wantErr: true,
			errMsg:  "email is required",
		},
		{
			name:    "missing @",
			email:   "userexample.com",
			wantErr: true,
			errMsg:  "invalid email format",
		},
		{
			name:    "missing domain",
			email:   "user@",
			wantErr: true,
			errMsg:  "invalid email format",
		},
		{
			name:    "missing TLD",
			email:   "user@example",
			wantErr: true,
			errMsg:  "invalid email format",
		},
		{
			name:    "double @",
			email:   "user@@example.com",
			wantErr: true,
			errMsg:  "invalid email format",
		},
		{
			name:    "spaces",
			email:   "user @example.com",
			wantErr: true,
			errMsg:  "invalid email format",
		},
		{
			name:    "too long",
			email:   strings.Repeat("a", 250) + "@b.co",
			wantErr: true,
			errMsg:  "email too long",
		},
		{
			name:    "single char TLD rejected",
			email:   "user@example.c",
			wantErr: true,
			errMsg:  "invalid email format",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel() // safe because test cases are independent

			err := ValidateEmail(tt.email)

			if tt.wantErr {
				if err == nil {
					t.Errorf("expected error for %q, got nil", tt.email)
					return
				}
				if tt.errMsg != "" && err.Error() != tt.errMsg {
					t.Errorf("error = %q, want %q", err.Error(), tt.errMsg)
				}
			} else if err != nil {
				t.Errorf("unexpected error for %q: %v", tt.email, err)
			}
		})
	}
}
```

Run with `go test -v -run TestValidateEmail`. Each subtest appears as `TestValidateEmail/valid_simple_email`, making failures easy to pinpoint. The `t.Parallel()` call lets independent subtests run concurrently, speeding up large test tables.'''
    ),
    (
        "go/benchmarks-subtests",
        r'''Write Go benchmarks comparing string concatenation methods: fmt.Sprintf, + operator, strings.Builder, and bytes.Buffer. Use sub-benchmarks with b.Run.''',
        r'''<think>
Go's testing.B provides benchmarking. Sub-benchmarks with b.Run let you compare
approaches in a single benchmark function. Each approach builds the same string
so the comparison is fair. Reset the timer if there's setup work.
Show b.ReportAllocs() to track allocations.
The Builder should win for repeated concatenation.
</think>

```go
package main

import (
	"bytes"
	"fmt"
	"strings"
	"testing"
)

const iterations = 100

func BenchmarkStringConcat(b *testing.B) {
	parts := make([]string, iterations)
	for i := range parts {
		parts[i] = fmt.Sprintf("segment-%d", i)
	}

	b.Run("plus_operator", func(b *testing.B) {
		b.ReportAllocs()
		for i := 0; i < b.N; i++ {
			var s string
			for _, p := range parts {
				s += p
			}
			_ = s
		}
	})

	b.Run("fmt.Sprintf", func(b *testing.B) {
		b.ReportAllocs()
		for i := 0; i < b.N; i++ {
			var s string
			for _, p := range parts {
				s = fmt.Sprintf("%s%s", s, p)
			}
			_ = s
		}
	})

	b.Run("strings.Builder", func(b *testing.B) {
		b.ReportAllocs()
		for i := 0; i < b.N; i++ {
			var sb strings.Builder
			sb.Grow(1000) // pre-allocate
			for _, p := range parts {
				sb.WriteString(p)
			}
			_ = sb.String()
		}
	})

	b.Run("bytes.Buffer", func(b *testing.B) {
		b.ReportAllocs()
		for i := 0; i < b.N; i++ {
			var buf bytes.Buffer
			buf.Grow(1000)
			for _, p := range parts {
				buf.WriteString(p)
			}
			_ = buf.String()
		}
	})

	b.Run("strings.Join", func(b *testing.B) {
		b.ReportAllocs()
		for i := 0; i < b.N; i++ {
			_ = strings.Join(parts, "")
		}
	})
}
```

Run with `go test -bench=BenchmarkStringConcat -benchmem`. Typical results:

```
plus_operator     ~50000 ns/op    ~50 allocs
fmt.Sprintf       ~80000 ns/op    ~150 allocs
strings.Builder   ~1500 ns/op     2 allocs
bytes.Buffer      ~1800 ns/op     3 allocs
strings.Join      ~1200 ns/op     1 alloc
```

`strings.Join` wins when you have all parts upfront. `strings.Builder` wins for streaming/incremental building. The `+` operator creates O(n^2) allocations and should never be used in loops.'''
    ),
    (
        "go/fuzz-testing",
        r'''Show how to write a fuzz test in Go 1.18+ for a URL parser function. Include seed corpus entries and explain the fuzzing process.''',
        r'''<think>
Go 1.18 added native fuzz testing. Fuzz functions start with FuzzXxx and take *testing.F.
Add seed corpus entries with f.Add(), then f.Fuzz() receives the mutated inputs.
The fuzzer finds inputs that cause panics, crashes, or test failures.
Show a ParseEndpoint function that should handle malformed URLs gracefully.
Fuzz testing is great for finding edge cases in parsers.
</think>

```go
package main

import (
	"fmt"
	"net/url"
	"strings"
	"testing"
)

// Function under test: extracts host and path from a URL string
type Endpoint struct {
	Scheme string
	Host   string
	Path   string
}

func ParseEndpoint(raw string) (Endpoint, error) {
	if raw == "" {
		return Endpoint{}, fmt.Errorf("empty URL")
	}

	// Ensure scheme exists
	if !strings.Contains(raw, "://") {
		raw = "https://" + raw
	}

	u, err := url.Parse(raw)
	if err != nil {
		return Endpoint{}, fmt.Errorf("parse error: %w", err)
	}

	if u.Host == "" {
		return Endpoint{}, fmt.Errorf("missing host in %q", raw)
	}

	return Endpoint{
		Scheme: u.Scheme,
		Host:   u.Host,
		Path:   u.Path,
	}, nil
}

// Fuzz test
func FuzzParseEndpoint(f *testing.F) {
	// Seed corpus: known interesting inputs
	f.Add("https://example.com/api/v1")
	f.Add("http://localhost:8080")
	f.Add("example.com")
	f.Add("https://user:pass@host.com:443/path?q=1#frag")
	f.Add("")
	f.Add("://")
	f.Add("http://[::1]:80/ipv6")
	f.Add(strings.Repeat("a", 10000))

	f.Fuzz(func(t *testing.T, input string) {
		ep, err := ParseEndpoint(input)
		if err != nil {
			return // errors are fine, just no panics
		}

		// Property: if parsing succeeds, host must be non-empty
		if ep.Host == "" {
			t.Errorf("ParseEndpoint(%q) returned empty host without error", input)
		}

		// Property: scheme must be set
		if ep.Scheme == "" {
			t.Errorf("ParseEndpoint(%q) returned empty scheme without error", input)
		}

		// Round-trip property: re-parsing should not fail
		reconstructed := fmt.Sprintf("%s://%s%s", ep.Scheme, ep.Host, ep.Path)
		if _, err := ParseEndpoint(reconstructed); err != nil {
			t.Errorf("round-trip failed: %q -> %q -> error: %v", input, reconstructed, err)
		}
	})
}
```

Run the fuzzer:
```bash
go test -fuzz=FuzzParseEndpoint -fuzztime=30s
```

How it works:
1. **Seed corpus** (`f.Add`): starting inputs the fuzzer mutates.
2. **Mutation engine**: Go's fuzzer flips bits, inserts bytes, combines seeds.
3. **Crash detection**: any panic, race condition, or `t.Error/Fatal` stops fuzzing and saves the failing input to `testdata/fuzz/FuzzParseEndpoint/`.
4. **Regression**: saved crash inputs are automatically included in future `go test` runs (without `-fuzz`).'''
    ),
    (
        "go/http-handlers",
        r'''Write a Go net/http server with JSON request/response handling, proper status codes, and input validation. Show idiomatic handler patterns without frameworks.''',
        r'''<think>
Idiomatic Go HTTP uses net/http directly. Key patterns: decode JSON with json.NewDecoder,
encode responses with json.NewEncoder, set Content-Type, use proper status codes.
Validate input and return structured error responses.
Use http.NewServeMux (Go 1.22+ has method routing).
Show a complete CRUD-style endpoint for a resource.
</think>

```go
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"sync"
	"time"
)

type Task struct {
	ID        string    `json:"id"`
	Title     string    `json:"title"`
	Done      bool      `json:"done"`
	CreatedAt time.Time `json:"created_at"`
}

type CreateTaskReq struct {
	Title string `json:"title"`
}

type ErrResponse struct {
	Error string `json:"error"`
}

// In-memory store
var (
	tasks   = make(map[string]Task)
	tasksMu sync.RWMutex
	nextID  int
)

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, ErrResponse{Error: msg})
}

func handleCreateTask(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "POST required")
		return
	}

	var req CreateTaskReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}

	// Validation
	if req.Title == "" {
		writeError(w, http.StatusUnprocessableEntity, "title is required")
		return
	}
	if len(req.Title) > 200 {
		writeError(w, http.StatusUnprocessableEntity, "title too long (max 200)")
		return
	}

	tasksMu.Lock()
	nextID++
	id := fmt.Sprintf("task_%d", nextID)
	task := Task{
		ID:        id,
		Title:     req.Title,
		Done:      false,
		CreatedAt: time.Now().UTC(),
	}
	tasks[id] = task
	tasksMu.Unlock()

	writeJSON(w, http.StatusCreated, task)
}

func handleListTasks(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "GET required")
		return
	}

	tasksMu.RLock()
	result := make([]Task, 0, len(tasks))
	for _, t := range tasks {
		result = append(result, t)
	}
	tasksMu.RUnlock()

	writeJSON(w, http.StatusOK, result)
}

func handleGetTask(w http.ResponseWriter, r *http.Request) {
	id := r.URL.Path[len("/tasks/"):]
	if id == "" {
		writeError(w, http.StatusBadRequest, "task ID required")
		return
	}

	tasksMu.RLock()
	task, ok := tasks[id]
	tasksMu.RUnlock()

	if !ok {
		writeError(w, http.StatusNotFound, "task not found")
		return
	}

	writeJSON(w, http.StatusOK, task)
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/tasks", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			handleListTasks(w, r)
		case http.MethodPost:
			handleCreateTask(w, r)
		default:
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		}
	})
	mux.HandleFunc("/tasks/", handleGetTask)

	log.Println("Listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}
```

Patterns used: helper functions for JSON responses, `json.NewDecoder` (not `ioutil.ReadAll` + `json.Unmarshal`), `RWMutex` for concurrent map access, proper HTTP status codes (201 Created, 422 Unprocessable Entity), and structured error responses.'''
    ),
    (
        "go/middleware-chains",
        r'''Implement a middleware chain in Go for an HTTP server with logging, recovery (panic handling), CORS, and authentication middlewares. Show the composition pattern.''',
        r'''<think>
Go middleware follows the pattern: func(http.Handler) http.Handler.
Each middleware wraps the next handler, forming a chain.
Order matters: recovery should be outermost, then logging, then auth.
Show each middleware separately and compose them.
Use the functional composition pattern that's idiomatic in Go.
</think>

```go
package main

import (
	"fmt"
	"log"
	"net/http"
	"runtime/debug"
	"strings"
	"time"
)

// Middleware type alias for clarity
type Middleware func(http.Handler) http.Handler

// Chain composes middlewares: first in the list wraps outermost
func Chain(handler http.Handler, middlewares ...Middleware) http.Handler {
	for i := len(middlewares) - 1; i >= 0; i-- {
		handler = middlewares[i](handler)
	}
	return handler
}

// Recovery middleware -- catches panics, returns 500
func Recovery(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if err := recover(); err != nil {
				log.Printf("PANIC: %v\n%s", err, debug.Stack())
				http.Error(w, `{"error":"internal server error"}`, http.StatusInternalServerError)
			}
		}()
		next.ServeHTTP(w, r)
	})
}

// Logging middleware -- logs method, path, status, duration
type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) WriteHeader(code int) {
	w.status = code
	w.ResponseWriter.WriteHeader(code)
}

func Logging(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		sw := &statusWriter{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(sw, r)
		log.Printf("%s %s %d %s", r.Method, r.URL.Path, sw.status, time.Since(start))
	})
}

// CORS middleware
func CORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// Auth middleware -- checks Bearer token
func Auth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		auth := r.Header.Get("Authorization")
		if !strings.HasPrefix(auth, "Bearer ") {
			http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}
		token := strings.TrimPrefix(auth, "Bearer ")
		if token != "valid-token" { // replace with real validation
			http.Error(w, `{"error":"forbidden"}`, http.StatusForbidden)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func apiHandler(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintln(w, `{"message":"authenticated request succeeded"}`)
}

func main() {
	api := http.HandlerFunc(apiHandler)

	// Compose: Recovery -> Logging -> CORS -> Auth -> handler
	handler := Chain(api, Recovery, Logging, CORS, Auth)

	http.Handle("/api/data", handler)

	// Public endpoint: no Auth middleware
	public := Chain(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, `{"status":"ok"}`)
	}), Recovery, Logging, CORS)

	http.Handle("/health", public)

	log.Println("Listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
```

Execution order for a request to `/api/data`: Recovery -> Logging (start timer) -> CORS (set headers) -> Auth (check token) -> apiHandler -> Logging (log duration) -> Recovery (catch panics). The `Chain` helper applies middlewares so the first in the list wraps outermost.'''
    ),
    (
        "go/graceful-shutdown",
        r'''Implement graceful HTTP server shutdown in Go that handles SIGINT/SIGTERM, drains in-flight requests, and has a shutdown timeout.''',
        r'''<think>
Graceful shutdown: catch OS signals, call server.Shutdown(ctx) which stops
accepting new connections and waits for in-flight requests to complete.
Use a context with timeout to cap the drain period.
Run the server in a goroutine so the main goroutine can block on the signal.
Show cleanup of other resources (DB connections, etc.) after shutdown.
This is production-essential Go code.
</think>

```go
package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	mux := http.NewServeMux()

	mux.HandleFunc("/slow", func(w http.ResponseWriter, r *http.Request) {
		log.Println("Slow request started")
		select {
		case <-time.After(5 * time.Second):
			fmt.Fprintln(w, "completed")
		case <-r.Context().Done():
			log.Println("Client disconnected")
			return
		}
	})

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, "ok")
	})

	server := &http.Server{
		Addr:         ":8080",
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Start server in a goroutine
	errCh := make(chan error, 1)
	go func() {
		log.Println("Server starting on :8080")
		if err := server.ListenAndServe(); err != http.ErrServerClosed {
			errCh <- err
		}
		close(errCh)
	}()

	// Block until signal or server error
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	select {
	case sig := <-quit:
		log.Printf("Received signal: %v", sig)
	case err := <-errCh:
		log.Printf("Server error: %v", err)
		os.Exit(1)
	}

	// Graceful shutdown with 30s timeout
	log.Println("Shutting down gracefully (30s timeout)...")
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		log.Printf("Forced shutdown: %v", err)
	}

	// Cleanup other resources
	log.Println("Closing database connections...")
	// db.Close()

	log.Println("Server stopped cleanly")
}
```

How `server.Shutdown` works:
1. Immediately stops accepting new connections.
2. Waits for all active requests to complete (or the context to expire).
3. Closes idle connections immediately.
4. Returns `nil` on clean drain, or `context.DeadlineExceeded` if the timeout hit.

Always set `ReadTimeout`, `WriteTimeout`, and `IdleTimeout` on production servers to prevent resource exhaustion from slow clients.'''
    ),
    (
        "go/worker-pool",
        r'''Implement a worker pool in Go that processes jobs from a channel with a configurable number of workers, error collection, and graceful shutdown via context.''',
        r'''<think>
Worker pool: N goroutines read from a jobs channel, process items, send results.
Use context for cancellation. Collect errors separately.
The pool should be reusable with a clean API: New, Submit, Shutdown, Errors.
Use sync.WaitGroup to wait for all workers to finish.
This is one of the most common Go concurrency patterns.
</think>

```go
package main

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"
)

type Job func(ctx context.Context) error

type Pool struct {
	jobs    chan Job
	wg      sync.WaitGroup
	errMu   sync.Mutex
	errors  []error
	ctx     context.Context
	cancel  context.CancelFunc
}

func NewPool(workers, queueSize int) *Pool {
	ctx, cancel := context.WithCancel(context.Background())
	p := &Pool{
		jobs:   make(chan Job, queueSize),
		ctx:    ctx,
		cancel: cancel,
	}

	for i := 0; i < workers; i++ {
		p.wg.Add(1)
		go p.worker(i)
	}

	return p
}

func (p *Pool) worker(id int) {
	defer p.wg.Done()
	for {
		select {
		case job, ok := <-p.jobs:
			if !ok {
				return // channel closed
			}
			if err := job(p.ctx); err != nil {
				p.errMu.Lock()
				p.errors = append(p.errors, err)
				p.errMu.Unlock()
			}
		case <-p.ctx.Done():
			// Drain remaining jobs from the channel
			for job := range p.jobs {
				_ = job // discard; context is cancelled
			}
			return
		}
	}
}

// Submit adds a job. Blocks if queue is full. Returns false if pool is shut down.
func (p *Pool) Submit(job Job) bool {
	select {
	case p.jobs <- job:
		return true
	case <-p.ctx.Done():
		return false
	}
}

// Shutdown stops accepting jobs, waits for in-flight work, and returns errors.
func (p *Pool) Shutdown() []error {
	close(p.jobs) // signal workers to finish after draining
	p.wg.Wait()
	p.errMu.Lock()
	defer p.errMu.Unlock()
	return p.errors
}

// Cancel immediately cancels all in-flight work.
func (p *Pool) Cancel() {
	p.cancel()
	p.Shutdown()
}

func main() {
	pool := NewPool(4, 20)

	// Submit 15 jobs
	for i := 0; i < 15; i++ {
		i := i
		pool.Submit(func(ctx context.Context) error {
			select {
			case <-time.After(time.Duration(100+i*50) * time.Millisecond):
				if i%5 == 0 {
					return fmt.Errorf("job %d failed", i)
				}
				log.Printf("Job %d completed", i)
				return nil
			case <-ctx.Done():
				return ctx.Err()
			}
		})
	}

	errs := pool.Shutdown()
	if len(errs) > 0 {
		log.Printf("Pool finished with %d errors:", len(errs))
		for _, e := range errs {
			log.Printf("  - %v", e)
		}
	}
}
```

Design decisions: the `queueSize` parameter controls backpressure -- `Submit` blocks when the queue is full. Workers check `ctx.Done()` to support immediate cancellation via `Cancel()`. Errors are collected thread-safely and returned from `Shutdown()`.'''
    ),
    (
        "go/rate-limiter",
        r'''Implement a token bucket rate limiter in Go for an HTTP API. Show both a per-handler limiter and a per-client (by IP) limiter using sync.Map.''',
        r'''<think>
Token bucket: tokens refill at a fixed rate, each request consumes one token.
Use golang.org/x/time/rate which implements this natively.
For per-client limiting, store a *rate.Limiter per IP in a sync.Map.
Need to clean up stale entries periodically to prevent memory leaks.
Show both global and per-IP middleware patterns.
</think>

```go
package main

import (
	"fmt"
	"log"
	"net"
	"net/http"
	"sync"
	"time"

	"golang.org/x/time/rate"
)

// --- Global rate limiter middleware ---

func GlobalRateLimit(rps float64, burst int) func(http.Handler) http.Handler {
	limiter := rate.NewLimiter(rate.Limit(rps), burst)

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if !limiter.Allow() {
				http.Error(w, `{"error":"rate limit exceeded"}`, http.StatusTooManyRequests)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// --- Per-client rate limiter ---

type clientLimiter struct {
	limiter  *rate.Limiter
	lastSeen time.Time
}

type PerClientLimiter struct {
	clients sync.Map
	rps     float64
	burst   int
}

func NewPerClientLimiter(rps float64, burst int) *PerClientLimiter {
	pcl := &PerClientLimiter{rps: rps, burst: burst}

	// Cleanup stale entries every minute
	go func() {
		for {
			time.Sleep(time.Minute)
			pcl.clients.Range(func(key, value any) bool {
				cl := value.(*clientLimiter)
				if time.Since(cl.lastSeen) > 3*time.Minute {
					pcl.clients.Delete(key)
				}
				return true
			})
		}
	}()

	return pcl
}

func (pcl *PerClientLimiter) getLimiter(ip string) *rate.Limiter {
	if v, ok := pcl.clients.Load(ip); ok {
		cl := v.(*clientLimiter)
		cl.lastSeen = time.Now()
		return cl.limiter
	}

	l := rate.NewLimiter(rate.Limit(pcl.rps), pcl.burst)
	pcl.clients.Store(ip, &clientLimiter{limiter: l, lastSeen: time.Now()})
	return l
}

func (pcl *PerClientLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ip, _, err := net.SplitHostPort(r.RemoteAddr)
		if err != nil {
			ip = r.RemoteAddr
		}

		if !pcl.getLimiter(ip).Allow() {
			w.Header().Set("Retry-After", "1")
			http.Error(w, `{"error":"rate limit exceeded"}`, http.StatusTooManyRequests)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func main() {
	// 10 requests/second per client, burst of 20
	perClient := NewPerClientLimiter(10, 20)

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, `{"message":"ok"}`)
	})

	mux := http.NewServeMux()
	mux.Handle("/api/", perClient.Middleware(handler))

	log.Println("Listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}
```

The `x/time/rate.Limiter` uses an efficient token bucket algorithm. `Allow()` is non-blocking (returns false immediately if no tokens). Use `Wait(ctx)` for blocking behavior or `Reserve()` for delayed execution. The cleanup goroutine prevents unbounded memory growth from unique IPs.'''
    ),
    (
        "go/semaphore-pattern",
        r'''Implement the semaphore pattern in Go to limit concurrent database connections. Show both the channel-based approach and golang.org/x/sync/semaphore.''',
        r'''<think>
Semaphore limits concurrency to N. Two approaches in Go:
1. Buffered channel of capacity N -- send to acquire, receive to release.
2. golang.org/x/sync/semaphore.Weighted -- supports weighted acquisition.
Show both with a practical database query scenario.
Channel approach is simpler, semaphore package supports weighted and context.
</think>

```go
package main

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	"golang.org/x/sync/semaphore"
)

// === Approach 1: Channel-based semaphore ===

type ChanSemaphore struct {
	ch chan struct{}
}

func NewChanSemaphore(maxConcurrent int) *ChanSemaphore {
	return &ChanSemaphore{ch: make(chan struct{}, maxConcurrent)}
}

func (s *ChanSemaphore) Acquire() { s.ch <- struct{}{} }
func (s *ChanSemaphore) Release() { <-s.ch }

func channelExample() {
	sem := NewChanSemaphore(3) // max 3 concurrent
	var wg sync.WaitGroup

	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			sem.Acquire()
			defer sem.Release()

			log.Printf("[chan] query %d started", id)
			time.Sleep(500 * time.Millisecond) // simulate DB query
			log.Printf("[chan] query %d done", id)
		}(i)
	}
	wg.Wait()
}

// === Approach 2: x/sync/semaphore (weighted, context-aware) ===

func weightedExample() {
	const maxConns int64 = 5

	sem := semaphore.NewWeighted(maxConns)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	type query struct {
		id     int
		weight int64 // heavy queries use more slots
	}

	queries := []query{
		{1, 1}, {2, 1}, {3, 3}, // query 3 is heavy, uses 3 slots
		{4, 1}, {5, 2}, {6, 1},
	}

	var wg sync.WaitGroup
	for _, q := range queries {
		wg.Add(1)
		go func(q query) {
			defer wg.Done()

			// Acquire with context -- respects timeout/cancellation
			if err := sem.Acquire(ctx, q.weight); err != nil {
				log.Printf("Query %d: failed to acquire: %v", q.id, err)
				return
			}
			defer sem.Release(q.weight)

			log.Printf("[weighted] query %d (weight=%d) running", q.id, q.weight)
			time.Sleep(time.Duration(q.weight) * 300 * time.Millisecond)
			log.Printf("[weighted] query %d done", q.id)
		}(q)
	}
	wg.Wait()
	fmt.Println("All queries completed")
}

func main() {
	fmt.Println("=== Channel semaphore ===")
	channelExample()

	fmt.Println("\n=== Weighted semaphore ===")
	weightedExample()
}
```

When to use each:
- **Channel**: simple, zero dependencies, fixed cost per operation.
- **`x/sync/semaphore`**: weighted acquisition (heavy vs light operations), context-aware (respects timeouts and cancellation), `TryAcquire` for non-blocking attempts.'''
    ),
    (
        "go/generics-constraints",
        r'''Show Go generics with type constraints: write a generic Map/Filter/Reduce and a custom constraint for numeric types. Go 1.18+.''',
        r'''<think>
Go 1.18 added generics with type parameters and constraints.
Constraints are interfaces that specify allowed types.
Show practical functional utilities (Map, Filter, Reduce) that work with any type.
Also show a custom Numeric constraint using the union syntax.
Include the constraints package from x/exp or define inline.
</think>

```go
package main

import (
	"fmt"
	"strings"

	"golang.org/x/exp/constraints"
)

// --- Generic utilities ---

func Map[T any, U any](slice []T, fn func(T) U) []U {
	result := make([]U, len(slice))
	for i, v := range slice {
		result[i] = fn(v)
	}
	return result
}

func Filter[T any](slice []T, pred func(T) bool) []T {
	var result []T
	for _, v := range slice {
		if pred(v) {
			result = append(result, v)
		}
	}
	return result
}

func Reduce[T any, U any](slice []T, init U, fn func(U, T) U) U {
	acc := init
	for _, v := range slice {
		acc = fn(acc, v)
	}
	return acc
}

// --- Custom constraint for numeric operations ---

type Numeric interface {
	constraints.Integer | constraints.Float
}

func Sum[T Numeric](values []T) T {
	var total T
	for _, v := range values {
		total += v
	}
	return total
}

func Max[T constraints.Ordered](values []T) (T, bool) {
	if len(values) == 0 {
		var zero T
		return zero, false
	}
	m := values[0]
	for _, v := range values[1:] {
		if v > m {
			m = v
		}
	}
	return m, true
}

// Generic set
type Set[T comparable] map[T]struct{}

func NewSet[T comparable](items ...T) Set[T] {
	s := make(Set[T], len(items))
	for _, item := range items {
		s[item] = struct{}{}
	}
	return s
}

func (s Set[T]) Contains(item T) bool {
	_, ok := s[item]
	return ok
}

func (s Set[T]) Intersect(other Set[T]) Set[T] {
	result := make(Set[T])
	for item := range s {
		if other.Contains(item) {
			result[item] = struct{}{}
		}
	}
	return result
}

func main() {
	// Map: int -> string
	nums := []int{1, 2, 3, 4, 5}
	strs := Map(nums, func(n int) string { return fmt.Sprintf("#%d", n) })
	fmt.Println(strs) // [#1 #2 #3 #4 #5]

	// Filter: keep even
	evens := Filter(nums, func(n int) bool { return n%2 == 0 })
	fmt.Println(evens) // [2 4]

	// Reduce: join strings
	words := []string{"hello", "generic", "world"}
	joined := Reduce(words, "", func(acc string, s string) string {
		if acc == "" {
			return s
		}
		return acc + " " + s
	})
	fmt.Println(joined)

	// Numeric constraint
	fmt.Println("Sum:", Sum([]float64{1.5, 2.5, 3.0}))

	// Ordered constraint
	max, _ := Max([]string{"banana", "apple", "cherry"})
	fmt.Println("Max:", max) // cherry

	// Generic Set
	a := NewSet(1, 2, 3, 4)
	b := NewSet(3, 4, 5, 6)
	fmt.Println("Intersect contains 3:", a.Intersect(b).Contains(3))

	_ = strings.NewReader("") // avoid unused import
}
```

Key generics concepts: `[T any]` is the unconstrained type parameter. `[T comparable]` allows `==` and `!=`. `[T constraints.Ordered]` allows `<`, `>`, etc. Custom constraints use `|` unions: `int | float64 | ...`. Type inference usually lets you omit explicit type arguments at call sites.'''
    ),
    (
        "go/json-marshal-unmarshal",
        r'''Show advanced JSON handling in Go: custom MarshalJSON/UnmarshalJSON, embedded structs, omitempty, string-to-int conversion, and handling unknown fields.''',
        r'''<think>
Go's encoding/json is powerful with struct tags and custom marshaler interfaces.
Show: omitempty, string tag for numbers-as-strings, embedded structs, custom
marshaler for time formatting, and json.RawMessage for dynamic fields.
Also show json.Decoder with DisallowUnknownFields for strict parsing.
These are daily patterns in Go API development.
</think>

```go
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"
)

// Custom time format
type DateTime struct {
	time.Time
}

const dateTimeFormat = "2006-01-02T15:04:05Z"

func (dt DateTime) MarshalJSON() ([]byte, error) {
	return json.Marshal(dt.Format(dateTimeFormat))
}

func (dt *DateTime) UnmarshalJSON(data []byte) error {
	var s string
	if err := json.Unmarshal(data, &s); err != nil {
		return err
	}
	t, err := time.Parse(dateTimeFormat, s)
	if err != nil {
		return err
	}
	dt.Time = t
	return nil
}

// Embedded struct (fields are promoted)
type Timestamps struct {
	CreatedAt DateTime `json:"created_at"`
	UpdatedAt DateTime `json:"updated_at"`
}

type User struct {
	Timestamps                          // embedded: fields appear at top level
	ID         int                      `json:"id"`
	Name       string                   `json:"name"`
	Email      string                   `json:"email,omitempty"` // omitted if empty
	Age        int                      `json:"age,string"`      // JSON string <-> Go int
	Role       string                   `json:"role,omitempty"`
	Metadata   map[string]any           `json:"metadata,omitempty"`
	Extra      json.RawMessage          `json:"extra,omitempty"` // defer parsing
}

// Enum-like type with custom JSON
type Status int

const (
	StatusActive Status = iota
	StatusInactive
	StatusBanned
)

var statusNames = map[Status]string{
	StatusActive:   "active",
	StatusInactive: "inactive",
	StatusBanned:   "banned",
}

var statusValues = map[string]Status{
	"active":   StatusActive,
	"inactive": StatusInactive,
	"banned":   StatusBanned,
}

func (s Status) MarshalJSON() ([]byte, error) {
	name, ok := statusNames[s]
	if !ok {
		return nil, fmt.Errorf("unknown status: %d", s)
	}
	return json.Marshal(name)
}

func (s *Status) UnmarshalJSON(data []byte) error {
	var name string
	if err := json.Unmarshal(data, &name); err != nil {
		return err
	}
	val, ok := statusValues[name]
	if !ok {
		return fmt.Errorf("unknown status: %q", name)
	}
	*s = val
	return nil
}

func main() {
	// Marshal
	user := User{
		ID:   1,
		Name: "Alice",
		Age:  30,
		Metadata: map[string]any{"theme": "dark"},
		Extra: json.RawMessage(`{"notifications": true}`),
	}
	user.CreatedAt = DateTime{time.Now().UTC()}
	user.UpdatedAt = DateTime{time.Now().UTC()}

	data, _ := json.MarshalIndent(user, "", "  ")
	fmt.Println("Marshaled:")
	fmt.Println(string(data))

	// Unmarshal with strict mode
	input := `{
		"id": 2,
		"name": "Bob",
		"age": "25",
		"created_at": "2025-06-15T10:30:00Z",
		"updated_at": "2025-06-15T10:30:00Z"
	}`

	var parsed User
	dec := json.NewDecoder(strings.NewReader(input))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&parsed); err != nil {
		log.Fatal(err)
	}
	fmt.Printf("\nParsed: %+v\n", parsed)
	fmt.Printf("Age (Go int): %d\n", parsed.Age) // string "25" -> int 25

	// Status enum
	s := StatusActive
	sJSON, _ := json.Marshal(s)
	fmt.Printf("\nStatus JSON: %s\n", sJSON) // "active"
}
```

Key patterns: `omitempty` skips zero-value fields, `json:",string"` converts between JSON strings and Go numbers, `json.RawMessage` defers parsing for dynamic schemas, `DisallowUnknownFields` enables strict parsing, and custom `MarshalJSON`/`UnmarshalJSON` give full control over the wire format.'''
    ),
    (
        "go/database-sql-prepared",
        r'''Show idiomatic Go database/sql usage with prepared statements, transactions, connection pooling configuration, and proper error handling with context.''',
        r'''<think>
database/sql is Go's standard database interface. Key patterns:
Prepared statements prevent SQL injection and improve performance.
Transactions with Rollback on error. Connection pool settings.
Always use context variants (QueryContext, ExecContext) for cancellation.
Use defer rows.Close() to prevent connection leaks.
Show a complete repository pattern with a real-world table.
</think>

```go
package main

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"time"

	_ "github.com/lib/pq" // PostgreSQL driver
)

type User struct {
	ID        int
	Email     string
	Name      string
	CreatedAt time.Time
}

type UserRepo struct {
	db         *sql.DB
	stmtGet    *sql.Stmt
	stmtInsert *sql.Stmt
}

func NewUserRepo(dsn string) (*UserRepo, error) {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, fmt.Errorf("open db: %w", err)
	}

	// Connection pool settings
	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(10)
	db.SetConnMaxLifetime(5 * time.Minute)
	db.SetConnMaxIdleTime(1 * time.Minute)

	// Verify connectivity
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		return nil, fmt.Errorf("ping db: %w", err)
	}

	// Prepare statements at init (parsed once, executed many times)
	stmtGet, err := db.PrepareContext(ctx,
		`SELECT id, email, name, created_at FROM users WHERE id = $1`)
	if err != nil {
		return nil, fmt.Errorf("prepare get: %w", err)
	}

	stmtInsert, err := db.PrepareContext(ctx,
		`INSERT INTO users (email, name) VALUES ($1, $2) RETURNING id, created_at`)
	if err != nil {
		return nil, fmt.Errorf("prepare insert: %w", err)
	}

	return &UserRepo{db: db, stmtGet: stmtGet, stmtInsert: stmtInsert}, nil
}

func (r *UserRepo) GetByID(ctx context.Context, id int) (*User, error) {
	var u User
	err := r.stmtGet.QueryRowContext(ctx, id).Scan(&u.ID, &u.Email, &u.Name, &u.CreatedAt)
	if err == sql.ErrNoRows {
		return nil, nil // not found
	}
	if err != nil {
		return nil, fmt.Errorf("get user %d: %w", id, err)
	}
	return &u, nil
}

func (r *UserRepo) Create(ctx context.Context, email, name string) (*User, error) {
	u := User{Email: email, Name: name}
	err := r.stmtInsert.QueryRowContext(ctx, email, name).Scan(&u.ID, &u.CreatedAt)
	if err != nil {
		return nil, fmt.Errorf("create user: %w", err)
	}
	return &u, nil
}

// Transaction example: transfer credits between users
func (r *UserRepo) TransferCredits(ctx context.Context, fromID, toID, amount int) error {
	tx, err := r.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	// Rollback is a no-op after Commit
	defer tx.Rollback()

	// Debit
	res, err := tx.ExecContext(ctx,
		`UPDATE users SET credits = credits - $1 WHERE id = $2 AND credits >= $1`, amount, fromID)
	if err != nil {
		return fmt.Errorf("debit: %w", err)
	}
	rows, _ := res.RowsAffected()
	if rows == 0 {
		return fmt.Errorf("insufficient credits for user %d", fromID)
	}

	// Credit
	_, err = tx.ExecContext(ctx,
		`UPDATE users SET credits = credits + $1 WHERE id = $2`, amount, toID)
	if err != nil {
		return fmt.Errorf("credit: %w", err)
	}

	return tx.Commit()
}

// Batch query with rows iteration
func (r *UserRepo) ListByIDs(ctx context.Context, ids []int) ([]User, error) {
	query := `SELECT id, email, name, created_at FROM users WHERE id = ANY($1)`
	rows, err := r.db.QueryContext(ctx, query, ids)
	if err != nil {
		return nil, fmt.Errorf("list users: %w", err)
	}
	defer rows.Close() // CRITICAL: prevents connection leak

	var users []User
	for rows.Next() {
		var u User
		if err := rows.Scan(&u.ID, &u.Email, &u.Name, &u.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan user: %w", err)
		}
		users = append(users, u)
	}
	// Check for iteration errors
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows iteration: %w", err)
	}
	return users, nil
}

func (r *UserRepo) Close() error {
	r.stmtGet.Close()
	r.stmtInsert.Close()
	return r.db.Close()
}

func main() {
	repo, err := NewUserRepo("postgres://localhost/myapp?sslmode=disable")
	if err != nil {
		log.Fatal(err)
	}
	defer repo.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	user, err := repo.Create(ctx, "alice@example.com", "Alice")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("Created: %+v\n", user)
}
```

Critical rules: always `defer rows.Close()`, always check `rows.Err()` after iteration, use `*Context` variants for timeout/cancellation, `defer tx.Rollback()` is safe after `Commit()` (it becomes a no-op), and prepared statements are safe for concurrent use.'''
    ),
    (
        "go/slog-structured-logging",
        r'''Show Go's log/slog package (Go 1.21+) for structured logging: JSON handler, log levels, groups, context integration, and custom attributes.''',
        r'''<think>
slog is Go's standard structured logging library since 1.21.
It supports text and JSON handlers, log levels, attribute groups,
and context-based logging. Show practical patterns: setting up a JSON logger,
adding request context, using LogAttrs for performance, and custom handler.
This replaces most third-party logging libraries.
</think>

```go
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"time"
)

func setupLogger() *slog.Logger {
	// JSON handler for production
	opts := &slog.HandlerOptions{
		Level: slog.LevelDebug,
		// Add source file info to log entries
		AddSource: true,
		// Custom level names or filtering
		ReplaceAttr: func(groups []string, a slog.Attr) slog.Attr {
			// Rename "msg" to "message" for ELK compatibility
			if a.Key == slog.MessageKey {
				a.Key = "message"
			}
			// Format time as RFC3339
			if a.Key == slog.TimeKey {
				a.Value = slog.StringValue(a.Value.Time().Format(time.RFC3339))
			}
			return a
		},
	}

	handler := slog.NewJSONHandler(os.Stdout, opts)
	return slog.New(handler)
}

// Middleware that adds request info to context logger
func loggingMiddleware(logger *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		// Create request-scoped logger with common fields
		reqLogger := logger.With(
			slog.String("method", r.Method),
			slog.String("path", r.URL.Path),
			slog.String("remote_addr", r.RemoteAddr),
		)

		// Store logger in context
		ctx := context.WithValue(r.Context(), loggerKey{}, reqLogger)

		reqLogger.Info("request started")
		next.ServeHTTP(w, r.WithContext(ctx))

		reqLogger.Info("request completed",
			slog.Duration("latency", time.Since(start)),
		)
	})
}

type loggerKey struct{}

// Extract logger from context
func LoggerFrom(ctx context.Context) *slog.Logger {
	if l, ok := ctx.Value(loggerKey{}).(*slog.Logger); ok {
		return l
	}
	return slog.Default()
}

// Service layer uses context logger
func processOrder(ctx context.Context, orderID string, amount float64) error {
	log := LoggerFrom(ctx)

	// Grouped attributes
	log.Info("processing order",
		slog.Group("order",
			slog.String("id", orderID),
			slog.Float64("amount", amount),
			slog.String("currency", "USD"),
		),
	)

	// LogAttrs is faster (avoids interface{} allocations)
	log.LogAttrs(ctx, slog.LevelDebug, "validation passed",
		slog.String("order_id", orderID),
		slog.Bool("fraud_check", true),
	)

	// Conditional logging
	if amount > 10000 {
		log.Warn("high-value order",
			slog.Float64("amount", amount),
			slog.String("order_id", orderID),
		)
	}

	return nil
}

func main() {
	logger := setupLogger()

	// Set as default (for slog.Info(), etc.)
	slog.SetDefault(logger)

	// Basic usage
	logger.Info("server starting",
		slog.Int("port", 8080),
		slog.String("env", "production"),
	)

	// With child logger (pre-set fields)
	dbLogger := logger.With(
		slog.String("component", "database"),
		slog.String("driver", "postgres"),
	)
	dbLogger.Info("connection pool ready", slog.Int("max_conns", 25))

	// Different levels
	logger.Debug("detailed trace info")
	logger.Info("normal operation")
	logger.Warn("something unusual", slog.Int("retry", 3))
	logger.Error("operation failed",
		slog.String("error", "connection refused"),
		slog.String("host", "db.internal:5432"),
	)

	// Simulate request handling
	ctx := context.Background()
	processOrder(ctx, "ord_123", 15000.50)
}
```

Output (JSON handler):
```json
{"time":"2025-06-15T10:30:00Z","level":"INFO","message":"server starting","port":8080,"env":"production"}
{"time":"2025-06-15T10:30:00Z","level":"WARN","message":"high-value order","amount":15000.5,"order_id":"ord_123"}
```

`slog.With()` creates child loggers that pre-set fields. `slog.Group()` nests attributes under a key. `LogAttrs` avoids allocations for hot paths. Use `HandlerOptions.Level` to control minimum log level per environment.'''
    ),
    (
        "go/sync-once-pool-map",
        r'''Show practical uses of sync.Once, sync.Pool, and sync.Map in Go with real-world scenarios and when to prefer them over alternatives.''',
        r'''<think>
sync.Once: thread-safe one-time initialization (singletons, config loading).
sync.Pool: reuse temporary objects to reduce GC pressure (buffers, parsers).
sync.Map: concurrent map for specific patterns (mostly-read, disjoint key sets).
Show each with a realistic use case and explain when NOT to use them.
Important: sync.Map is rarely the right choice over mutex+map.
</think>

```go
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"sync"
)

// === sync.Once: thread-safe singleton initialization ===

type Config struct {
	DBHost   string
	CacheURL string
}

var (
	globalConfig *Config
	configOnce   sync.Once
)

func GetConfig() *Config {
	configOnce.Do(func() {
		// Expensive initialization runs exactly once, even under concurrent access
		fmt.Println("Loading config (happens once)")
		globalConfig = &Config{
			DBHost:   "db.internal:5432",
			CacheURL: "redis://cache:6379",
		}
	})
	return globalConfig
}

// === sync.Pool: reuse buffers to reduce GC pressure ===

var bufPool = sync.Pool{
	New: func() any {
		return new(bytes.Buffer)
	},
}

func MarshalToJSON(v any) ([]byte, error) {
	buf := bufPool.Get().(*bytes.Buffer)
	buf.Reset() // CRITICAL: clear previous data
	defer bufPool.Put(buf)

	enc := json.NewEncoder(buf)
	if err := enc.Encode(v); err != nil {
		return nil, err
	}

	// Copy the bytes out before returning the buffer to the pool
	result := make([]byte, buf.Len())
	copy(result, buf.Bytes())
	return result, nil
}

// Benchmark shows ~60% fewer allocations with pool vs. new buffer each time

// === sync.Map: concurrent map for mostly-read workloads ===

// Use case: cache of expensive computations, keys are set once and read many times
type ExpensiveCache struct {
	m sync.Map
}

func (c *ExpensiveCache) GetOrCompute(key string, compute func() (any, error)) (any, error) {
	// Fast path: check if already cached
	if val, ok := c.m.Load(key); ok {
		return val, nil
	}

	// Slow path: compute and store
	val, err := compute()
	if err != nil {
		return nil, err
	}

	// LoadOrStore handles the race: if another goroutine stored first, use theirs
	actual, _ := c.m.LoadOrStore(key, val)
	return actual, nil
}

func main() {
	// sync.Once
	var wg sync.WaitGroup
	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			cfg := GetConfig() // only prints "Loading config" once
			_ = cfg
		}()
	}
	wg.Wait()
	fmt.Printf("Config: %+v\n\n", GetConfig())

	// sync.Pool
	data := map[string]any{"name": "Alice", "score": 95}
	jsonBytes, _ := MarshalToJSON(data)
	fmt.Printf("JSON: %s\n", jsonBytes)

	// sync.Map
	cache := &ExpensiveCache{}
	val, _ := cache.GetOrCompute("expensive_key", func() (any, error) {
		fmt.Println("Computing (happens once per key)...")
		return 42, nil
	})
	fmt.Println("Cached value:", val)

	// Second call hits cache
	val2, _ := cache.GetOrCompute("expensive_key", func() (any, error) {
		fmt.Println("This won't print")
		return 0, nil
	})
	fmt.Println("Cached again:", val2)
}
```

When to use each:

**sync.Once**: lazy initialization of globals (DB connections, config, loggers). Guaranteed to run exactly once even under races.

**sync.Pool**: high-throughput code where object allocation is a bottleneck (HTTP servers reusing buffers, JSON encoders). Objects may be collected by GC at any time -- never store critical state.

**sync.Map**: only when keys are stable (written once, read many) or goroutines access disjoint key sets. For most use cases, `sync.RWMutex` + regular map is simpler and faster.'''
    ),
    (
        "go/embed-fs",
        r'''Show how to use Go's embed.FS to bundle static files (HTML templates, config) into a binary. Include serving embedded files via net/http and template parsing.''',
        r'''<think>
Go 1.16 added embed package for bundling files into the binary at compile time.
Use //go:embed directive with embed.FS for directories or strings/bytes for single files.
Show: embedding a templates directory, serving static files, and parsing templates.
The binary becomes self-contained -- no need to ship files alongside it.
Important: the directive must be a comment directly above the variable.
</think>

```go
package main

import (
	"embed"
	"fmt"
	"html/template"
	"io/fs"
	"log"
	"net/http"
)

// Embed single file as string
//go:embed config/defaults.yaml
var defaultConfig string

// Embed single file as bytes
//go:embed VERSION
var version []byte

// Embed entire directory tree
//go:embed templates/*
var templateFS embed.FS

// Embed static assets (CSS, JS, images)
//go:embed static/*
var staticFS embed.FS

func main() {
	fmt.Printf("Version: %s\n", version)
	fmt.Printf("Default config:\n%s\n", defaultConfig)

	// Parse templates from embedded FS
	tmpl, err := template.ParseFS(templateFS, "templates/*.html")
	if err != nil {
		log.Fatal(err)
	}

	// Handler using embedded templates
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		data := map[string]any{
			"Title":   "Embedded App",
			"Message": "Served from binary!",
		}
		if err := tmpl.ExecuteTemplate(w, "index.html", data); err != nil {
			http.Error(w, err.Error(), 500)
		}
	})

	// Serve static files from embedded FS
	// Sub() strips the "static" prefix so /static/css/style.css works
	staticSub, err := fs.Sub(staticFS, "static")
	if err != nil {
		log.Fatal(err)
	}
	http.Handle("/static/", http.StripPrefix("/static/",
		http.FileServer(http.FS(staticSub))))

	// List embedded files (useful for debugging)
	fs.WalkDir(templateFS, ".", func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if !d.IsDir() {
			info, _ := d.Info()
			fmt.Printf("  embedded: %s (%d bytes)\n", path, info.Size())
		}
		return nil
	})

	log.Println("Listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
```

File structure expected at compile time:
```
project/
  main.go
  VERSION           (e.g., "1.2.3")
  config/
    defaults.yaml
  templates/
    index.html
    layout.html
  static/
    css/style.css
    js/app.js
```

Key details:
- `//go:embed` must be a **comment directly above** the var declaration (no blank lines between).
- Patterns support `*` globs but not `**` recursive globs -- use directory names instead.
- `embed.FS` implements `fs.FS`, so it works with `template.ParseFS`, `http.FS`, `fs.WalkDir`, etc.
- The embedded files are **read-only** and compiled into the binary -- `go build` produces a single self-contained executable.
- Hidden files (starting with `.` or `_`) are excluded by default; use `all:` prefix to include them: `//go:embed all:templates`.'''
    ),
]
