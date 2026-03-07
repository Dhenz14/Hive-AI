"""
Go language training pairs - patterns (interfaces, embedding, generics, functional options, context)
"""

pairs = [
    {
        "instruction": r'''Explain Go interfaces with practical examples. How do implicit interfaces differ from explicit interfaces in other languages?''',
        "output": r'''Go interfaces are satisfied implicitly -- any type with matching methods implements the interface without declaring it:

```go
package main

import (
	"fmt"
	"io"
	"strings"
)

// Small, focused interfaces (Go convention)
type Reader interface {
	Read(p []byte) (n int, err error)
}

type Writer interface {
	Write(p []byte) (n int, err error)
}

// Compose interfaces by embedding
type ReadWriter interface {
	Reader
	Writer
}

// --- Custom type that implicitly satisfies io.Writer ---
type LogWriter struct {
	prefix string
	buf    strings.Builder
}

// This method signature matches io.Writer -- no "implements" keyword needed
func (lw *LogWriter) Write(p []byte) (int, error) {
	line := fmt.Sprintf("[%s] %s", lw.prefix, string(p))
	return lw.buf.WriteString(line)
}

func (lw *LogWriter) String() string {
	return lw.buf.String()
}

// Accept interfaces, return structs
func process(w io.Writer, data string) error {
	_, err := fmt.Fprintf(w, "processed: %s\n", data)
	return err
}

func main() {
	// LogWriter satisfies io.Writer without any declaration
	lw := &LogWriter{prefix: "APP"}
	process(lw, "hello")
	process(lw, "world")
	fmt.Print(lw.String())

	// strings.Builder also satisfies io.Writer
	var sb strings.Builder
	process(&sb, "test")
	fmt.Print(sb.String())
}
```

Key differences from Java/C# interfaces:
- No "implements" keyword -- satisfaction is structural, not nominal
- Types can satisfy interfaces from other packages without importing them
- Convention: keep interfaces small (1-3 methods). io.Reader has one method
- Define interfaces where they are used (consumer side), not where types are defined
- Accept interfaces, return concrete types -- this maximizes flexibility

The empty interface `any` (alias for `interface{}`) accepts all types. Use it sparingly -- prefer specific interfaces that document expected behavior.'''
    },
    {
        "instruction": r'''<think>
The user wants to understand Go generics. Generics were added in Go 1.18 and use type parameters with constraints. The key concepts are: type parameters in square brackets, constraints (interfaces that specify allowed types), and the built-in constraints like any, comparable, and the constraints package. I should show practical examples -- a generic data structure and a generic function -- not just toy examples. The constraints package (golang.org/x/exp/constraints or the built-in cmp package in Go 1.21) provides Ordered, Signed, etc.
</think>
Show me how to use Go generics effectively with type parameters, constraints, and practical examples.''',
        "output": r'''Go generics (1.18+) use type parameters in square brackets with interface constraints:

```go
package main

import (
	"cmp"
	"fmt"
	"slices"
)

// --- Generic function with constraint ---
// cmp.Ordered constrains T to types that support < > == (int, float, string)
func Min[T cmp.Ordered](a, b T) T {
	if a < b {
		return a
	}
	return b
}

// --- Generic data structure ---
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

func (s *Stack[T]) Len() int {
	return len(s.items)
}

// --- Custom constraint interface ---
type Number interface {
	~int | ~int32 | ~int64 | ~float32 | ~float64
}

// ~ means underlying type -- allows named types like `type Meters float64`
func Sum[T Number](nums []T) T {
	var total T
	for _, n := range nums {
		total += n
	}
	return total
}

// --- Generic Map/Filter/Reduce ---
func Map[T any, U any](s []T, f func(T) U) []U {
	result := make([]U, len(s))
	for i, v := range s {
		result[i] = f(v)
	}
	return result
}

func Filter[T any](s []T, pred func(T) bool) []T {
	var result []T
	for _, v := range s {
		if pred(v) {
			result = append(result, v)
		}
	}
	return result
}

func main() {
	fmt.Println(Min(3, 7))       // 3
	fmt.Println(Min("a", "z"))   // "a"

	s := Stack[string]{}
	s.Push("hello")
	s.Push("world")
	val, _ := s.Pop()
	fmt.Println(val) // "world"

	nums := []int{1, 2, 3, 4, 5}
	fmt.Println(Sum(nums)) // 15

	doubled := Map(nums, func(n int) int { return n * 2 })
	fmt.Println(doubled) // [2 4 6 8 10]

	evens := Filter(nums, func(n int) bool { return n%2 == 0 })
	fmt.Println(evens) // [2 4]

	// stdlib generic functions (Go 1.21+)
	slices.Sort(nums)
	idx, found := slices.BinarySearch(nums, 3)
	fmt.Println(idx, found)
}
```

Generics guidelines:
- Use generics when the logic is truly type-independent (containers, algorithms)
- Prefer interfaces for behavioral polymorphism -- generics for data polymorphism
- The ~ tilde in constraints matches underlying types (useful for named types)
- Start with `any` constraint and narrow only when you need operators like < or +'''
    },
    {
        "instruction": r'''Show me the functional options pattern in Go for building configurable structs with clean APIs.''',
        "output": r'''The functional options pattern uses variadic function arguments to configure structs without large parameter lists or config structs with many zero values:

```go
package main

import (
	"fmt"
	"log"
	"net/http"
	"time"
)

// --- Server with functional options ---

type Server struct {
	host         string
	port         int
	readTimeout  time.Duration
	writeTimeout time.Duration
	maxConns     int
	tls          bool
	logger       *log.Logger
}

// Option is a function that configures the server
type Option func(*Server)

func WithPort(port int) Option {
	return func(s *Server) {
		s.port = port
	}
}

func WithTimeouts(read, write time.Duration) Option {
	return func(s *Server) {
		s.readTimeout = read
		s.writeTimeout = write
	}
}

func WithMaxConns(n int) Option {
	return func(s *Server) {
		s.maxConns = n
	}
}

func WithTLS() Option {
	return func(s *Server) {
		s.tls = true
	}
}

func WithLogger(l *log.Logger) Option {
	return func(s *Server) {
		s.logger = l
	}
}

// NewServer applies defaults then overrides with options
func NewServer(host string, opts ...Option) *Server {
	s := &Server{
		host:         host,
		port:         8080,
		readTimeout:  10 * time.Second,
		writeTimeout: 30 * time.Second,
		maxConns:     100,
	}

	for _, opt := range opts {
		opt(s)
	}

	return s
}

func (s *Server) Addr() string {
	scheme := "http"
	if s.tls {
		scheme = "https"
	}
	return fmt.Sprintf("%s://%s:%d", scheme, s.host, s.port)
}

func main() {
	// Clean, readable construction
	srv := NewServer("localhost",
		WithPort(9090),
		WithTLS(),
		WithMaxConns(500),
		WithTimeouts(5*time.Second, 15*time.Second),
	)

	fmt.Println(srv.Addr()) // https://localhost:9090

	// Minimal config -- all defaults
	basic := NewServer("0.0.0.0")
	fmt.Println(basic.Addr()) // http://0.0.0.0:8080
}
```

Why functional options over alternatives:
- Config struct: zero values are ambiguous (is port 0 intentional or unset?)
- Builder pattern: requires mutable intermediate state and a Build() call
- Functional options: self-documenting, composable, extensible without breaking callers
- New options can be added without changing existing call sites
- Used by google/go-cloud, gRPC-Go, uber/zap, and many popular libraries'''
    },
    {
        "instruction": r'''<think>
The user wants to understand context.Context in Go. Context is one of the most important patterns in Go -- it carries deadlines, cancellation signals, and request-scoped values across API boundaries and goroutines. The key insight is that context forms a tree: child contexts inherit from parents, and cancelling a parent cancels all children. I should show WithCancel, WithTimeout, WithValue, and the rules for how to propagate context. Also important: context.Value is for request-scoped data (trace IDs, auth tokens), NOT for passing function parameters.
</think>
Explain Go context.Context thoroughly -- cancellation, timeouts, values, and best practices for propagation.''',
        "output": r'''context.Context carries deadlines, cancellation signals, and request-scoped values across goroutines:

```go
package main

import (
	"context"
	"fmt"
	"time"
)

// Simulate a database query that respects context
func queryDB(ctx context.Context, query string) (string, error) {
	// Check if already cancelled before starting work
	select {
	case <-ctx.Done():
		return "", ctx.Err()
	default:
	}

	// Simulate slow query
	select {
	case <-time.After(2 * time.Second):
		return "result: 42", nil
	case <-ctx.Done():
		return "", fmt.Errorf("query cancelled: %w", ctx.Err())
	}
}

// Request-scoped values (trace IDs, auth info)
type contextKey string

const traceIDKey contextKey = "traceID"

func withTraceID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, traceIDKey, id)
}

func getTraceID(ctx context.Context) string {
	if id, ok := ctx.Value(traceIDKey).(string); ok {
		return id
	}
	return "unknown"
}

func handleRequest(ctx context.Context) {
	traceID := getTraceID(ctx)
	fmt.Printf("[%s] starting request\n", traceID)

	result, err := queryDB(ctx, "SELECT 1")
	if err != nil {
		fmt.Printf("[%s] query failed: %v\n", traceID, err)
		return
	}
	fmt.Printf("[%s] got: %s\n", traceID, result)
}

func main() {
	// --- WithTimeout: auto-cancel after duration ---
	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer cancel() // always defer cancel to release resources

	ctx = withTraceID(ctx, "req-abc-123")
	handleRequest(ctx) // will timeout (query takes 2s, deadline is 1s)

	// --- WithCancel: manual cancellation ---
	ctx2, cancel2 := context.WithCancel(context.Background())
	ctx2 = withTraceID(ctx2, "req-def-456")

	go func() {
		time.Sleep(500 * time.Millisecond)
		cancel2() // cancel from another goroutine
	}()

	handleRequest(ctx2) // cancelled after 500ms

	// --- WithDeadline: cancel at specific time ---
	deadline := time.Now().Add(3 * time.Second)
	ctx3, cancel3 := context.WithDeadline(context.Background(), deadline)
	defer cancel3()
	ctx3 = withTraceID(ctx3, "req-ghi-789")
	handleRequest(ctx3) // succeeds (3s deadline > 2s query)
}
```

Context rules (from the Go blog):
- Pass context as the first parameter: `func DoSomething(ctx context.Context, ...)`
- Never store context in a struct -- pass it explicitly
- Use context.Value only for request-scoped data (trace IDs, auth), not function args
- Always call the cancel function (defer it) to prevent goroutine leaks
- Use custom key types (not string) to avoid collisions between packages
- context.Background() for main/init; context.TODO() as placeholder during refactoring'''
    },
    {
        "instruction": r'''Show me Go struct embedding and how it enables composition over inheritance.''',
        "output": r'''Go uses struct embedding for composition instead of class inheritance. Embedded fields promote their methods to the outer type:

```go
package main

import (
	"encoding/json"
	"fmt"
	"sync"
	"time"
)

// --- Base types ---
type Timestamps struct {
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

func (t *Timestamps) Touch() {
	t.UpdatedAt = time.Now()
}

type SoftDelete struct {
	DeletedAt *time.Time `json:"deleted_at,omitempty"`
}

func (s *SoftDelete) Delete() {
	now := time.Now()
	s.DeletedAt = &now
}

func (s *SoftDelete) IsDeleted() bool {
	return s.DeletedAt != nil
}

// --- Composed types ---
type User struct {
	Timestamps            // embedded -- promotes CreatedAt, UpdatedAt, Touch()
	SoftDelete            // embedded -- promotes DeletedAt, Delete(), IsDeleted()
	ID         int        `json:"id"`
	Name       string     `json:"name"`
	Email      string     `json:"email"`
}

// --- Embedding for thread-safe wrapper ---
type SafeMap[K comparable, V any] struct {
	mu sync.RWMutex // embedded mutex
	m  map[K]V
}

func NewSafeMap[K comparable, V any]() *SafeMap[K, V] {
	return &SafeMap[K, V]{m: make(map[K]V)}
}

func (sm *SafeMap[K, V]) Set(key K, val V) {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	sm.m[key] = val
}

func (sm *SafeMap[K, V]) Get(key K) (V, bool) {
	sm.mu.RLock()
	defer sm.mu.RUnlock()
	v, ok := sm.m[key]
	return v, ok
}

// --- Interface satisfaction through embedding ---
type Logger interface {
	Log(msg string)
}

type ConsoleLogger struct{}

func (cl ConsoleLogger) Log(msg string) {
	fmt.Printf("[LOG] %s\n", msg)
}

type Service struct {
	ConsoleLogger // Service now satisfies Logger interface
	Name string
}

func process(l Logger) {
	l.Log("processing request")
}

func main() {
	u := User{
		ID:    1,
		Name:  "Alice",
		Email: "alice@example.com",
		Timestamps: Timestamps{
			CreatedAt: time.Now(),
			UpdatedAt: time.Now(),
		},
	}

	// Promoted methods -- called directly on User
	u.Touch()
	u.Delete()
	fmt.Println("Deleted:", u.IsDeleted())

	// JSON includes all embedded fields
	data, _ := json.MarshalIndent(u, "", "  ")
	fmt.Println(string(data))

	// Interface satisfaction via embedding
	svc := Service{Name: "auth"}
	process(svc) // works because ConsoleLogger.Log is promoted

	// Safe map usage
	sm := NewSafeMap[string, int]()
	sm.Set("count", 42)
	v, _ := sm.Get("count")
	fmt.Println("count:", v)
}
```

Embedding rules:
- Promoted methods have the embedded type as receiver, not the outer type
- If two embedded types have the same method, the outer type must disambiguate
- Embedding is not inheritance -- there is no polymorphism on the outer type
- Embed interfaces to require method implementations (common in mock testing)
- Embed sync.Mutex or sync.RWMutex to make types concurrency-safe'''
    },
]
