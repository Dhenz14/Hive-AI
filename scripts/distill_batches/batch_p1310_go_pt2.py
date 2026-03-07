"""Go training pairs (part 2): advanced concurrency, gRPC, CLI, profiling, unsafe."""

PAIRS = [
    (
        "go/circuit-breaker",
        r'''Implement a circuit breaker pattern in Go for wrapping unreliable service calls. It should support closed, open, and half-open states with configurable thresholds.''',
        r'''<think>
Circuit breaker needs three states: closed (normal), open (failing, reject calls), half-open (testing recovery).
Track consecutive failures, trip to open after threshold, use a timer to move to half-open.
Half-open allows one probe request — success resets to closed, failure reopens.
Need thread safety since multiple goroutines will call through it concurrently.
I'll use sync.Mutex and a clean state machine approach.
</think>

Here's a thread-safe circuit breaker implementation:

```go
package circuitbreaker

import (
	"errors"
	"sync"
	"time"
)

type State int

const (
	Closed   State = iota
	Open
	HalfOpen
)

var (
	ErrCircuitOpen = errors.New("circuit breaker is open")
)

type CircuitBreaker struct {
	mu               sync.Mutex
	state            State
	failureCount     int
	successCount     int
	failureThreshold int
	successThreshold int // successes needed in half-open to close
	timeout          time.Duration
	lastFailure      time.Time
}

func New(failureThreshold, successThreshold int, timeout time.Duration) *CircuitBreaker {
	return &CircuitBreaker{
		state:            Closed,
		failureThreshold: failureThreshold,
		successThreshold: successThreshold,
		timeout:          timeout,
	}
}

func (cb *CircuitBreaker) Execute(fn func() error) error {
	cb.mu.Lock()
	if cb.state == Open {
		if time.Since(cb.lastFailure) > cb.timeout {
			cb.state = HalfOpen
			cb.successCount = 0
		} else {
			cb.mu.Unlock()
			return ErrCircuitOpen
		}
	}
	cb.mu.Unlock()

	err := fn()

	cb.mu.Lock()
	defer cb.mu.Unlock()

	if err != nil {
		cb.failureCount++
		cb.lastFailure = time.Now()
		if cb.state == HalfOpen || cb.failureCount >= cb.failureThreshold {
			cb.state = Open
		}
		return err
	}

	if cb.state == HalfOpen {
		cb.successCount++
		if cb.successCount >= cb.successThreshold {
			cb.state = Closed
			cb.failureCount = 0
		}
	} else {
		cb.failureCount = 0
	}
	return nil
}

func (cb *CircuitBreaker) State() State {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	return cb.state
}
```

Usage:

```go
cb := circuitbreaker.New(3, 2, 10*time.Second)

err := cb.Execute(func() error {
    resp, err := http.Get("https://unreliable-service.example.com/api")
    if err != nil {
        return err
    }
    defer resp.Body.Close()
    if resp.StatusCode >= 500 {
        return fmt.Errorf("server error: %d", resp.StatusCode)
    }
    return nil
})

if errors.Is(err, circuitbreaker.ErrCircuitOpen) {
    // fallback logic
    log.Println("circuit open, using cached response")
}
```

The breaker trips open after 3 consecutive failures, waits 10 seconds, then enters half-open where 2 successes are needed to fully close again.'''
    ),
    (
        "go/retry-backoff",
        r'''Write a Go retry function with exponential backoff, jitter, and a configurable maximum number of attempts. It should work with any fallible operation.''',
        r'''<think>
Exponential backoff: delay doubles each attempt. Jitter prevents thundering herd.
Use functional options for clean configuration.
The retry function should accept a context for cancellation and a func() error.
Add full jitter: random duration between 0 and the calculated backoff.
Cap the maximum backoff to prevent absurd wait times.
</think>

```go
package retry

import (
	"context"
	"math"
	"math/rand"
	"time"
)

type Config struct {
	MaxAttempts int
	BaseDelay   time.Duration
	MaxDelay    time.Duration
	Jitter      bool
}

func DefaultConfig() Config {
	return Config{
		MaxAttempts: 5,
		BaseDelay:   100 * time.Millisecond,
		MaxDelay:    30 * time.Second,
		Jitter:      true,
	}
}

type Option func(*Config)

func WithMaxAttempts(n int) Option    { return func(c *Config) { c.MaxAttempts = n } }
func WithBaseDelay(d time.Duration) Option { return func(c *Config) { c.BaseDelay = d } }
func WithMaxDelay(d time.Duration) Option  { return func(c *Config) { c.MaxDelay = d } }

func Do(ctx context.Context, fn func() error, opts ...Option) error {
	cfg := DefaultConfig()
	for _, o := range opts {
		o(&cfg)
	}

	var lastErr error
	for attempt := 0; attempt < cfg.MaxAttempts; attempt++ {
		if err := ctx.Err(); err != nil {
			return err
		}

		lastErr = fn()
		if lastErr == nil {
			return nil
		}

		if attempt == cfg.MaxAttempts-1 {
			break
		}

		delay := float64(cfg.BaseDelay) * math.Pow(2, float64(attempt))
		if delay > float64(cfg.MaxDelay) {
			delay = float64(cfg.MaxDelay)
		}

		if cfg.Jitter {
			delay = rand.Float64() * delay
		}

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(time.Duration(delay)):
		}
	}
	return lastErr
}
```

Usage:

```go
ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
defer cancel()

err := retry.Do(ctx, func() error {
    return callExternalAPI()
}, retry.WithMaxAttempts(4), retry.WithBaseDelay(200*time.Millisecond))

if err != nil {
    log.Fatalf("all retries exhausted: %v", err)
}
```

The backoff sequence with base=100ms is roughly 100ms, 200ms, 400ms, 800ms... capped at MaxDelay, with jitter randomizing each wait to avoid correlated retries across clients.'''
    ),
    (
        "go/grpc-service-definition",
        r'''Show how to define a gRPC service in Go from scratch: the .proto file, generated code usage, server implementation, and client call. Use a simple user lookup service as the example.''',
        r'''<think>
Need to show the full gRPC workflow: proto definition, how to generate, server impl, client usage.
The proto defines the service contract with messages and RPCs.
Server implements the generated interface. Client uses the generated stub.
I'll use a UserService with GetUser as a unary RPC.
Keep it practical — show registration, listener, dial, and error handling.
</think>

**1. Proto definition** (`proto/user.proto`):

```protobuf
syntax = "proto3";

package user;

option go_package = "myapp/gen/userpb";

service UserService {
  rpc GetUser(GetUserRequest) returns (GetUserResponse);
}

message GetUserRequest {
  string user_id = 1;
}

message GetUserResponse {
  string user_id = 1;
  string name = 2;
  string email = 3;
}
```

Generate with:
```bash
protoc --go_out=. --go-grpc_out=. proto/user.proto
```

**2. Server implementation**:

```go
package main

import (
	"context"
	"log"
	"net"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	pb "myapp/gen/userpb"
)

type userServer struct {
	pb.UnimplementedUserServiceServer
	users map[string]*pb.GetUserResponse
}

func (s *userServer) GetUser(ctx context.Context, req *pb.GetUserRequest) (*pb.GetUserResponse, error) {
	if req.UserId == "" {
		return nil, status.Error(codes.InvalidArgument, "user_id is required")
	}
	user, ok := s.users[req.UserId]
	if !ok {
		return nil, status.Errorf(codes.NotFound, "user %s not found", req.UserId)
	}
	return user, nil
}

func main() {
	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatalf("failed to listen: %v", err)
	}

	srv := grpc.NewServer()
	pb.RegisterUserServiceServer(srv, &userServer{
		users: map[string]*pb.GetUserResponse{
			"u1": {UserId: "u1", Name: "Alice", Email: "alice@example.com"},
		},
	})

	log.Println("gRPC server listening on :50051")
	if err := srv.Serve(lis); err != nil {
		log.Fatalf("failed to serve: %v", err)
	}
}
```

**3. Client usage**:

```go
package main

import (
	"context"
	"log"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	pb "myapp/gen/userpb"
)

func main() {
	conn, err := grpc.NewClient("localhost:50051",
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		log.Fatalf("dial failed: %v", err)
	}
	defer conn.Close()

	client := pb.NewUserServiceClient(conn)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	resp, err := client.GetUser(ctx, &pb.GetUserRequest{UserId: "u1"})
	if err != nil {
		log.Fatalf("GetUser failed: %v", err)
	}
	log.Printf("User: %s (%s)", resp.Name, resp.Email)
}
```

Embed `UnimplementedUserServiceServer` so your server compiles even if you haven't implemented all RPCs yet — this is forward-compatible by design.'''
    ),
    (
        "go/grpc-streaming",
        r'''Implement a gRPC server-streaming RPC in Go where the server streams log entries to the client as they arrive, with the client printing each one. Show proto, server, and client.''',
        r'''<think>
Server streaming: client sends one request, server sends a stream of responses.
The proto uses `stream` keyword on the return type only.
Server calls stream.Send() repeatedly. Client calls Recv() in a loop until EOF.
I'll model a log tailing service — client subscribes with a filter, server pushes matching entries.
Need to show graceful handling of context cancellation on both sides.
</think>

**Proto** (`proto/logs.proto`):

```protobuf
syntax = "proto3";

package logs;

option go_package = "myapp/gen/logspb";

service LogService {
  rpc TailLogs(TailRequest) returns (stream LogEntry);
}

message TailRequest {
  string level_filter = 1; // "INFO", "ERROR", etc. Empty = all
}

message LogEntry {
  string timestamp = 1;
  string level = 2;
  string message = 3;
}
```

**Server**:

```go
package main

import (
	"fmt"
	"log"
	"math/rand"
	"net"
	"time"

	"google.golang.org/grpc"
	pb "myapp/gen/logspb"
)

type logServer struct {
	pb.UnimplementedLogServiceServer
}

func (s *logServer) TailLogs(req *pb.TailRequest, stream pb.LogService_TailLogsServer) error {
	levels := []string{"INFO", "WARN", "ERROR", "DEBUG"}
	messages := []string{"request processed", "connection timeout", "cache miss", "user login"}

	for i := 0; i < 50; i++ {
		if err := stream.Context().Err(); err != nil {
			return err // client disconnected
		}

		level := levels[rand.Intn(len(levels))]
		if req.LevelFilter != "" && level != req.LevelFilter {
			continue
		}

		entry := &pb.LogEntry{
			Timestamp: time.Now().Format(time.RFC3339),
			Level:     level,
			Message:   fmt.Sprintf("[%d] %s", i, messages[rand.Intn(len(messages))]),
		}

		if err := stream.Send(entry); err != nil {
			return err
		}
		time.Sleep(200 * time.Millisecond)
	}
	return nil
}

func main() {
	lis, err := net.Listen("tcp", ":50052")
	if err != nil {
		log.Fatal(err)
	}
	srv := grpc.NewServer()
	pb.RegisterLogServiceServer(srv, &logServer{})
	log.Println("log stream server on :50052")
	srv.Serve(lis)
}
```

**Client**:

```go
package main

import (
	"context"
	"fmt"
	"io"
	"log"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	pb "myapp/gen/logspb"
)

func main() {
	conn, err := grpc.NewClient("localhost:50052",
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		log.Fatal(err)
	}
	defer conn.Close()

	client := pb.NewLogServiceClient(conn)

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	stream, err := client.TailLogs(ctx, &pb.TailRequest{LevelFilter: "ERROR"})
	if err != nil {
		log.Fatal(err)
	}

	for {
		entry, err := stream.Recv()
		if err == io.EOF {
			fmt.Println("stream ended")
			return
		}
		if err != nil {
			log.Fatalf("recv error: %v", err)
		}
		fmt.Printf("[%s] %s: %s\n", entry.Timestamp, entry.Level, entry.Message)
	}
}
```

The server checks `stream.Context().Err()` each iteration so it stops immediately when the client disconnects or the context expires.'''
    ),
    (
        "go/cli-cobra",
        r'''Build a CLI tool in Go using Cobra that has a root command, a "serve" subcommand with a --port flag, and a "migrate" subcommand with --direction (up/down) and --steps flags. Show proper structure.''',
        r'''<think>
Cobra uses a tree of Command objects. Root command holds global flags, subcommands branch off.
Each subcommand gets its own RunE function. PersistentFlags live on root and inherit downward.
I'll show a clean layout with each command in its own function for maintainability.
Use RunE instead of Run so errors propagate properly.
Add flag validation and default values.
</think>

```go
package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

func main() {
	if err := rootCmd().Execute(); err != nil {
		os.Exit(1)
	}
}

func rootCmd() *cobra.Command {
	var verbose bool

	root := &cobra.Command{
		Use:   "myapp",
		Short: "MyApp CLI — server and migration tool",
	}

	root.PersistentFlags().BoolVarP(&verbose, "verbose", "v", false, "enable verbose output")

	root.AddCommand(serveCmd(&verbose))
	root.AddCommand(migrateCmd(&verbose))
	return root
}

func serveCmd(verbose *bool) *cobra.Command {
	var port int
	var host string

	cmd := &cobra.Command{
		Use:   "serve",
		Short: "Start the HTTP server",
		RunE: func(cmd *cobra.Command, args []string) error {
			if port < 1 || port > 65535 {
				return fmt.Errorf("invalid port: %d", port)
			}
			addr := fmt.Sprintf("%s:%d", host, port)
			if *verbose {
				fmt.Printf("starting server on %s (verbose mode)\n", addr)
			}
			fmt.Printf("listening on %s\n", addr)
			// http.ListenAndServe(addr, router) — real server here
			return nil
		},
	}

	cmd.Flags().IntVarP(&port, "port", "p", 8080, "port to listen on")
	cmd.Flags().StringVar(&host, "host", "0.0.0.0", "host to bind to")
	return cmd
}

func migrateCmd(verbose *bool) *cobra.Command {
	var direction string
	var steps int

	cmd := &cobra.Command{
		Use:   "migrate",
		Short: "Run database migrations",
		RunE: func(cmd *cobra.Command, args []string) error {
			if direction != "up" && direction != "down" {
				return fmt.Errorf("direction must be 'up' or 'down', got %q", direction)
			}
			if steps < 1 {
				return fmt.Errorf("steps must be >= 1")
			}

			if *verbose {
				fmt.Printf("running %d migration(s) %s\n", steps, direction)
			}

			for i := 1; i <= steps; i++ {
				fmt.Printf("migration step %d/%d (%s) — applied\n", i, steps, direction)
			}
			return nil
		},
	}

	cmd.Flags().StringVarP(&direction, "direction", "d", "up", "migration direction (up/down)")
	cmd.Flags().IntVarP(&steps, "steps", "n", 1, "number of migration steps")
	return cmd
}
```

Usage:

```bash
myapp serve --port 3000
myapp serve -p 3000 --host 127.0.0.1 -v
myapp migrate --direction down --steps 3
myapp migrate -d up -n 5 -v
myapp --help
```

Key Cobra conventions: use `RunE` (not `Run`) so errors are printed consistently, use `PersistentFlags` on the root for flags that apply to all subcommands, and validate flags inside the run function rather than relying on Cobra's limited built-in validation.'''
    ),
    (
        "go/pprof-profiling",
        r'''How do I profile a Go HTTP server for CPU and memory using pprof? Show how to enable it in code, collect profiles, and interpret the results.''',
        r'''<think>
The net/http/pprof package registers handlers on the default mux automatically.
For CPU profiling, hit /debug/pprof/profile. For heap, /debug/pprof/heap.
Use `go tool pprof` to analyze the output interactively or generate flamegraphs.
Important: if using a custom mux (chi, gorilla), you must register pprof routes manually.
Show both the blank import approach and manual registration.
</think>

**1. Enable pprof in your server:**

```go
package main

import (
	"log"
	"net/http"
	_ "net/http/pprof" // registers /debug/pprof/* on default mux
)

func main() {
	// If using DefaultServeMux, pprof endpoints are already registered.
	// For production, run pprof on a separate port:
	go func() {
		log.Println("pprof on :6060")
		log.Println(http.ListenAndServe("localhost:6060", nil))
	}()

	// Your real server on a different mux/port
	mux := http.NewServeMux()
	mux.HandleFunc("/api/data", handleData)
	log.Fatal(http.ListenAndServe(":8080", mux))
}

func handleData(w http.ResponseWriter, r *http.Request) {
	// simulate work
	data := make([]byte, 1<<20)
	for i := range data {
		data[i] = byte(i % 256)
	}
	w.Write(data[:100])
}
```

**2. Collect profiles:**

```bash
# CPU profile (30-second sample by default)
go tool pprof http://localhost:6060/debug/pprof/profile?seconds=15

# Heap (memory) profile
go tool pprof http://localhost:6060/debug/pprof/heap

# Goroutine dump
curl http://localhost:6060/debug/pprof/goroutine?debug=2

# Allocations (all, not just live)
go tool pprof -alloc_space http://localhost:6060/debug/pprof/heap
```

**3. Analyze interactively:**

```bash
# Inside pprof interactive shell:
(pprof) top 10          # top 10 functions by CPU/memory
(pprof) list handleData # source-annotated view of a function
(pprof) web             # opens SVG graph in browser

# Generate a flamegraph (requires graphviz):
go tool pprof -http=:9090 cpu.prof
```

**4. For custom routers** (chi, gorilla, etc.):

```go
import "net/http/pprof"

r := chi.NewRouter()
r.HandleFunc("/debug/pprof/", pprof.Index)
r.HandleFunc("/debug/pprof/cmdline", pprof.Cmdline)
r.HandleFunc("/debug/pprof/profile", pprof.Profile)
r.HandleFunc("/debug/pprof/symbol", pprof.Symbol)
r.HandleFunc("/debug/pprof/trace", pprof.Trace)
r.Handle("/debug/pprof/heap", pprof.Handler("heap"))
r.Handle("/debug/pprof/goroutine", pprof.Handler("goroutine"))
```

Always run pprof on a separate listener bound to localhost in production so it's never exposed publicly.'''
    ),
    (
        "go/memory-optimization",
        r'''I have a Go service processing millions of small structs and GC pauses are hurting latency. What are practical techniques to reduce allocations and GC pressure?''',
        r'''<think>
GC pressure in Go comes from heap allocations. Key strategies: reduce allocations, reuse memory, help escape analysis keep things on the stack.
sync.Pool for transient objects, pre-allocated slices, struct-of-arrays layout, avoid pointer-heavy structures.
Reducing pointer count helps GC scanning. GOGC tuning and ballast are also options.
I'll show concrete patterns rather than just listing tips.
</think>

**1. Pre-allocate slices and maps with known sizes:**

```go
// Bad: grows and re-allocates during append
var results []Result
for _, item := range items {
    results = append(results, process(item))
}

// Good: single allocation
results := make([]Result, 0, len(items))
for _, item := range items {
    results = append(results, process(item))
}
```

**2. Use sync.Pool for frequently allocated/discarded objects:**

```go
var bufPool = sync.Pool{
    New: func() any { return new(bytes.Buffer) },
}

func processRequest(data []byte) string {
    buf := bufPool.Get().(*bytes.Buffer)
    buf.Reset()
    defer bufPool.Put(buf)

    buf.Write(data)
    // ... transform ...
    return buf.String()
}
```

**3. Avoid pointers in hot structs (reduces GC scan work):**

```go
// Bad: each *string is a pointer the GC must scan
type Record struct {
    Name  *string
    Value *string
}

// Good: value types, no GC scanning needed for fields
type Record struct {
    Name  [64]byte
    NameLen int
    Value float64
}
```

**4. Struct-of-arrays instead of array-of-structs for large datasets:**

```go
// Array-of-structs: each struct may escape, lots of pointers
type Entries struct {
    Items []Entry // each Entry has pointers inside
}

// Struct-of-arrays: contiguous memory, fewer pointers
type Entries struct {
    IDs    []int64
    Names  []string
    Values []float64
}
```

**5. Reuse byte slices for encoding/decoding:**

```go
type Encoder struct {
    buf []byte
}

func (e *Encoder) Encode(v any) []byte {
    e.buf = e.buf[:0] // reuse backing array
    e.buf = append(e.buf, marshal(v)...)
    return e.buf
}
```

**6. GOGC tuning and memory ballast:**

```go
import "runtime/debug"

func init() {
    // Set GC target to 50% (default 100) — more frequent but shorter pauses
    debug.SetGCPercent(50)

    // Or use SetMemoryLimit (Go 1.19+) for hard cap
    debug.SetMemoryLimit(512 << 20) // 512 MB
}
```

**7. Check escape analysis to find unexpected heap allocations:**

```bash
go build -gcflags="-m" ./... 2>&1 | grep "escapes to heap"
```

The biggest wins usually come from sync.Pool on hot paths and pre-allocating slices. Profile first with `go tool pprof -alloc_objects` to find the actual allocation hotspots before optimizing.'''
    ),
    (
        "go/reflection-basics",
        r'''Show the fundamentals of Go reflection: inspecting struct fields, reading tags, and dynamically getting/setting values. Include a practical example like building a simple struct-to-map converter.''',
        r'''<think>
reflect package gives runtime type introspection. reflect.TypeOf for type info, reflect.ValueOf for values.
Struct tags are accessed via field.Tag.Get("key").
Setting values requires the reflect.Value to be addressable (pass pointer).
A struct-to-map converter is a good practical example — reads json tags for keys.
Need to handle unexported fields (skip them) and pointer dereferencing.
</think>

```go
package main

import (
	"fmt"
	"reflect"
	"strings"
)

// StructToMap converts a struct to map[string]any using json tags as keys.
// Unexported fields and fields tagged `json:"-"` are skipped.
func StructToMap(v any) map[string]any {
	val := reflect.ValueOf(v)
	// Dereference pointer if needed
	if val.Kind() == reflect.Ptr {
		val = val.Elem()
	}
	if val.Kind() != reflect.Struct {
		panic("StructToMap requires a struct")
	}

	typ := val.Type()
	result := make(map[string]any, typ.NumField())

	for i := 0; i < typ.NumField(); i++ {
		field := typ.Field(i)

		// Skip unexported fields
		if !field.IsExported() {
			continue
		}

		// Determine the map key from the json tag
		key := field.Name
		if tag := field.Tag.Get("json"); tag != "" {
			parts := strings.Split(tag, ",")
			if parts[0] == "-" {
				continue
			}
			if parts[0] != "" {
				key = parts[0]
			}
		}

		result[key] = val.Field(i).Interface()
	}
	return result
}

// SetField sets a struct field by name using reflection.
func SetField(obj any, fieldName string, value any) error {
	val := reflect.ValueOf(obj)
	if val.Kind() != reflect.Ptr || val.Elem().Kind() != reflect.Struct {
		return fmt.Errorf("expected pointer to struct")
	}
	field := val.Elem().FieldByName(fieldName)
	if !field.IsValid() {
		return fmt.Errorf("no field %q", fieldName)
	}
	if !field.CanSet() {
		return fmt.Errorf("cannot set field %q", fieldName)
	}
	newVal := reflect.ValueOf(value)
	if !newVal.Type().AssignableTo(field.Type()) {
		return fmt.Errorf("type %s not assignable to %s", newVal.Type(), field.Type())
	}
	field.Set(newVal)
	return nil
}

type User struct {
	ID    int    `json:"id" db:"user_id"`
	Name  string `json:"name"`
	Email string `json:"email"`
	hash  string // unexported — will be skipped
}

func main() {
	u := User{ID: 1, Name: "Alice", Email: "alice@example.com", hash: "secret"}

	m := StructToMap(u)
	fmt.Println(m) // map[id:1 name:Alice email:alice@example.com]

	// Read a specific tag
	typ := reflect.TypeOf(u)
	f, _ := typ.FieldByName("ID")
	fmt.Println("db tag:", f.Tag.Get("db")) // "user_id"

	// Set a field dynamically
	if err := SetField(&u, "Name", "Bob"); err != nil {
		panic(err)
	}
	fmt.Println(u.Name) // Bob
}
```

Key rules of Go reflection: you need a pointer to set values (`reflect.ValueOf(&obj).Elem()`), unexported fields are visible but not settable, and `Interface()` converts back from `reflect.Value` to `any`.'''
    ),
    (
        "go/unsafe-pointer",
        r'''When is it appropriate to use unsafe.Pointer in Go, and show a correct example of using it for zero-copy type conversion between compatible struct layouts?''',
        r'''<think>
unsafe.Pointer allows bypassing Go's type system. Legitimate uses: interop with C, zero-copy conversions between identically-laid-out structs, and low-level memory tricks.
Must follow the six legal conversion patterns from the Go spec.
The key safe pattern: *T1 -> unsafe.Pointer -> *T2 where T1 and T2 have identical memory layout.
Important to warn about pitfalls: GC can move memory, alignment matters, layouts must match exactly.
</think>

`unsafe.Pointer` is appropriate in narrow cases: C interop, performance-critical zero-copy conversions, and accessing struct internals (e.g., reflect header tricks). Always prefer safe alternatives first.

**Zero-copy conversion between compatible structs:**

```go
package main

import (
	"fmt"
	"unsafe"
)

// These two structs have identical memory layouts.
// internal package defines this:
type internalUser struct {
	ID   int64
	Age  int32
	Flag byte
}

// our package wants this:
type User struct {
	ID   int64
	Age  int32
	Flag byte
}

func main() {
	src := internalUser{ID: 42, Age: 30, Flag: 1}

	// Safe: identical layouts, no pointers involved
	dst := *(*User)(unsafe.Pointer(&src))
	fmt.Printf("User: %+v\n", dst) // {ID:42 Age:30 Flag:1}

	// Verify sizes match at compile time
	_ = [1]struct{}{}[unsafe.Sizeof(internalUser{})-unsafe.Sizeof(User{})]
}
```

**Accessing slice header (read-only, e.g., for string<->[]byte):**

```go
// Zero-copy string to []byte — ONLY safe if you never modify the result
func unsafeStringToBytes(s string) []byte {
	return unsafe.Slice(unsafe.StringData(s), len(s))
}

// Zero-copy []byte to string
func unsafeBytesToString(b []byte) string {
	return unsafe.String(unsafe.SliceData(b), len(b))
}
```

**Rules you must follow** (from the Go spec):

```go
// Legal conversion patterns:
// 1. *T -> unsafe.Pointer
// 2. unsafe.Pointer -> *T
// 3. unsafe.Pointer -> uintptr (only in specific patterns)
// 4. uintptr -> unsafe.Pointer (only combined with 3 in one expression)

// NEVER store a uintptr and convert it back later:
p := unsafe.Pointer(&x)
u := uintptr(p)
// ... GC can move x here ...
q := unsafe.Pointer(u) // BROKEN: u may be stale

// CORRECT: combine in one expression
val := *(*int)(unsafe.Pointer(uintptr(unsafe.Pointer(&s)) + unsafe.Offsetof(s.field)))
```

**Compile-time layout check:**

```go
func init() {
	if unsafe.Sizeof(internalUser{}) != unsafe.Sizeof(User{}) {
		panic("struct layout mismatch")
	}
}
```

Avoid unsafe unless you've profiled and the safe version is genuinely too slow. Most code never needs it.'''
    ),
    (
        "go/build-tags",
        r'''Explain Go build tags (build constraints) with examples. How do I conditionally compile code for different OS, testing, or custom feature flags?''',
        r'''<think>
Build tags control which files get compiled. Go 1.17+ uses //go:build syntax (boolean expressions).
Common uses: OS/arch targeting, test-only code, feature flags, integration test separation.
File naming conventions also act as implicit build tags (e.g., _linux.go).
Show practical examples of each use case.
</think>

**1. OS/architecture constraints:**

```go
// server_linux.go
//go:build linux

package server

func platformInit() {
    // Linux-specific: epoll, systemd notify, etc.
    setupEpoll()
}
```

```go
// server_windows.go
//go:build windows

package server

func platformInit() {
    // Windows-specific: IOCP, service registration, etc.
    setupIOCP()
}
```

No build tag needed if you use file naming conventions: `file_GOOS.go` or `file_GOOS_GOARCH.go` are automatically constrained.

**2. Boolean expressions:**

```go
//go:build (linux || darwin) && amd64

package optimized

// Only compiled on Linux or macOS, and only on amd64
```

**3. Custom feature flags:**

```go
// cache_redis.go
//go:build redis

package cache

import "github.com/redis/go-redis/v9"

type Store struct {
    client *redis.Client
}

func New(addr string) *Store {
    return &Store{client: redis.NewClient(&redis.Options{Addr: addr})}
}
```

```go
// cache_memory.go
//go:build !redis

package cache

import "sync"

type Store struct {
    mu   sync.RWMutex
    data map[string][]byte
}

func New(_ string) *Store {
    return &Store{data: make(map[string][]byte)}
}
```

Build with:
```bash
go build -tags redis ./...   # uses Redis
go build ./...                # uses in-memory (default)
```

**4. Integration test separation:**

```go
// db_integration_test.go
//go:build integration

package db_test

import "testing"

func TestDatabaseMigration(t *testing.T) {
    // Only runs with: go test -tags integration ./...
    db := connectTestDB(t)
    defer db.Close()
    // ...
}
```

```bash
go test ./...                    # skips integration tests
go test -tags integration ./...  # includes them
```

**5. Ignore a file entirely:**

```go
//go:build ignore

package main

// This file is never compiled, useful for code generators or examples
```

The `//go:build` line must be followed by a blank line before the `package` statement. The older `// +build` syntax still works but `//go:build` is preferred since Go 1.17.'''
    ),
    (
        "go/websocket-server",
        r'''Build a WebSocket echo server in Go using the nhooyr.io/websocket library. It should handle multiple concurrent connections and broadcast messages to all connected clients.''',
        r'''<think>
WebSocket server with broadcast needs a hub pattern: central coordinator that tracks connections and fans out messages.
Each connection gets a read goroutine and the hub writes to all clients.
Use nhooyr.io/websocket which is the modern, well-maintained Go websocket library.
Need proper cleanup when clients disconnect and context handling.
</think>

```go
package main

import (
	"context"
	"log"
	"net/http"
	"sync"
	"time"

	"nhooyr.io/websocket"
	"nhooyr.io/websocket/wsjson"
)

type Hub struct {
	mu      sync.RWMutex
	clients map[*Client]struct{}
}

type Client struct {
	conn *websocket.Conn
	send chan Message
}

type Message struct {
	From string `json:"from"`
	Text string `json:"text"`
}

func NewHub() *Hub {
	return &Hub{clients: make(map[*Client]struct{})}
}

func (h *Hub) Register(c *Client) {
	h.mu.Lock()
	h.clients[c] = struct{}{}
	h.mu.Unlock()
	log.Printf("client connected (%d total)", len(h.clients))
}

func (h *Hub) Unregister(c *Client) {
	h.mu.Lock()
	delete(h.clients, c)
	close(c.send)
	h.mu.Unlock()
}

func (h *Hub) Broadcast(msg Message) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	for c := range h.clients {
		select {
		case c.send <- msg:
		default:
			// slow client, drop message
		}
	}
}

func (h *Hub) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	conn, err := websocket.Accept(w, r, &websocket.AcceptOptions{
		OriginPatterns: []string{"*"},
	})
	if err != nil {
		log.Printf("accept error: %v", err)
		return
	}

	client := &Client{
		conn: conn,
		send: make(chan Message, 16),
	}
	h.Register(client)
	defer h.Unregister(client)

	ctx, cancel := context.WithCancel(r.Context())
	defer cancel()

	// Writer goroutine
	go func() {
		defer cancel()
		for msg := range client.send {
			writeCtx, writeCancel := context.WithTimeout(ctx, 5*time.Second)
			err := wsjson.Write(writeCtx, conn, msg)
			writeCancel()
			if err != nil {
				return
			}
		}
	}()

	// Reader loop (blocks until disconnect)
	remoteAddr := r.RemoteAddr
	for {
		var msg Message
		err := wsjson.Read(ctx, conn, &msg)
		if err != nil {
			log.Printf("client %s disconnected: %v", remoteAddr, err)
			return
		}
		msg.From = remoteAddr
		h.Broadcast(msg)
	}
}

func main() {
	hub := NewHub()

	mux := http.NewServeMux()
	mux.Handle("/ws", hub)
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.Write([]byte(`<!DOCTYPE html><html><body>
			<input id="msg" type="text"><button onclick="send()">Send</button>
			<pre id="log"></pre>
			<script>
			const ws = new WebSocket("ws://"+location.host+"/ws");
			ws.onmessage = e => document.getElementById("log").textContent += e.data+"\n";
			function send() {
				ws.send(JSON.stringify({text: document.getElementById("msg").value}));
				document.getElementById("msg").value = "";
			}
			</script></body></html>`))
	})

	log.Println("listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}
```

The hub pattern keeps the broadcast logic centralized. Each client has a buffered `send` channel — if a client is too slow and the buffer fills, messages are dropped rather than blocking the broadcaster.'''
    ),
    (
        "go/concurrent-sharded-map",
        r'''Implement a concurrent map in Go using shard-based locking instead of a single sync.RWMutex, to reduce lock contention under high concurrency.''',
        r'''<think>
A sharded map splits data across N shards, each with its own lock.
Hash the key to pick a shard — concurrent operations on different shards don't contend.
Typically use a power-of-2 shard count for fast modulo via bitmask.
Need Get, Set, Delete, and a way to iterate safely (lock all shards).
Use FNV hash for speed.
</think>

```go
package shardmap

import (
	"hash/fnv"
	"sync"
)

const defaultShardCount = 32

type ShardMap[V any] struct {
	shards []*shard[V]
	mask   uint32
}

type shard[V any] struct {
	mu    sync.RWMutex
	items map[string]V
}

func New[V any]() *ShardMap[V] {
	sm := &ShardMap[V]{
		shards: make([]*shard[V], defaultShardCount),
		mask:   uint32(defaultShardCount - 1),
	}
	for i := range sm.shards {
		sm.shards[i] = &shard[V]{items: make(map[string]V)}
	}
	return sm
}

func (sm *ShardMap[V]) getShard(key string) *shard[V] {
	h := fnv.New32a()
	h.Write([]byte(key))
	return sm.shards[h.Sum32()&sm.mask]
}

func (sm *ShardMap[V]) Set(key string, value V) {
	s := sm.getShard(key)
	s.mu.Lock()
	s.items[key] = value
	s.mu.Unlock()
}

func (sm *ShardMap[V]) Get(key string) (V, bool) {
	s := sm.getShard(key)
	s.mu.RLock()
	v, ok := s.items[key]
	s.mu.RUnlock()
	return v, ok
}

func (sm *ShardMap[V]) Delete(key string) {
	s := sm.getShard(key)
	s.mu.Lock()
	delete(s.items, key)
	s.mu.Unlock()
}

func (sm *ShardMap[V]) Len() int {
	total := 0
	for _, s := range sm.shards {
		s.mu.RLock()
		total += len(s.items)
		s.mu.RUnlock()
	}
	return total
}

// Range calls fn for every key-value pair. Acquires each shard lock sequentially.
// Do NOT call Set/Delete from within fn (deadlock).
func (sm *ShardMap[V]) Range(fn func(key string, value V) bool) {
	for _, s := range sm.shards {
		s.mu.RLock()
		for k, v := range s.items {
			if !fn(k, v) {
				s.mu.RUnlock()
				return
			}
		}
		s.mu.RUnlock()
	}
}
```

Usage:

```go
m := shardmap.New[int]()

// Safe for concurrent use from many goroutines
var wg sync.WaitGroup
for i := 0; i < 1000; i++ {
    wg.Add(1)
    go func(n int) {
        defer wg.Done()
        key := fmt.Sprintf("key-%d", n)
        m.Set(key, n)
        if v, ok := m.Get(key); ok {
            _ = v
        }
    }(i)
}
wg.Wait()

fmt.Println("entries:", m.Len()) // 1000
```

With 32 shards, contention drops to roughly 1/32 compared to a single-mutex map. This is the same approach used by `sync.Map` internally and by libraries like `orcaman/concurrent-map`.'''
    ),
    (
        "go/pipeline-pattern",
        r'''Implement the pipeline pattern in Go where data flows through a series of processing stages connected by channels, with proper cancellation and error handling.''',
        r'''<think>
Pipeline pattern: chain of stages, each reading from input channel and writing to output channel.
Each stage runs in its own goroutine. Use context for cancellation.
Need to handle errors without deadlocking — errgroup is perfect here.
Show a concrete example: read numbers, filter, transform, collect.
Each stage function returns a channel and starts a goroutine.
</think>

```go
package main

import (
	"context"
	"fmt"
	"math"
	"sync"
)

// Stage: generate integers from 2 to max
func generate(ctx context.Context, max int) <-chan int {
	out := make(chan int)
	go func() {
		defer close(out)
		for i := 2; i <= max; i++ {
			select {
			case out <- i:
			case <-ctx.Done():
				return
			}
		}
	}()
	return out
}

// Stage: filter — only pass values where predicate is true
func filter(ctx context.Context, in <-chan int, pred func(int) bool) <-chan int {
	out := make(chan int)
	go func() {
		defer close(out)
		for v := range in {
			if pred(v) {
				select {
				case out <- v:
				case <-ctx.Done():
					return
				}
			}
		}
	}()
	return out
}

// Stage: transform — apply a function to each value
func transform(ctx context.Context, in <-chan int, fn func(int) int) <-chan int {
	out := make(chan int)
	go func() {
		defer close(out)
		for v := range in {
			select {
			case out <- fn(v):
			case <-ctx.Done():
				return
			}
		}
	}()
	return out
}

// Fan-out: run n workers on the same input, merge results
func fanOut(ctx context.Context, in <-chan int, fn func(int) int, workers int) <-chan int {
	out := make(chan int)
	var wg sync.WaitGroup
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for v := range in {
				select {
				case out <- fn(v):
				case <-ctx.Done():
					return
				}
			}
		}()
	}
	go func() {
		wg.Wait()
		close(out)
	}()
	return out
}

func isPrime(n int) bool {
	if n < 2 {
		return false
	}
	for i := 2; i <= int(math.Sqrt(float64(n))); i++ {
		if n%i == 0 {
			return false
		}
	}
	return true
}

func main() {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Pipeline: generate 2..1000 -> filter primes -> square them
	numbers := generate(ctx, 1000)
	primes := filter(ctx, numbers, isPrime)
	squared := fanOut(ctx, primes, func(n int) int { return n * n }, 4)

	// Sink: collect results
	count := 0
	for v := range squared {
		fmt.Printf("%d ", v)
		count++
		if count >= 20 {
			cancel() // early termination
			break
		}
	}
	fmt.Printf("\nprocessed %d items\n", count)
}
```

Each stage owns its output channel (creates and closes it). The `select` on `ctx.Done()` in every stage ensures the entire pipeline tears down cleanly when cancelled. Fan-out with multiple workers is a natural extension — just ensure the merge goroutine waits for all workers before closing the output channel.'''
    ),
    (
        "go/errgroup-parallel",
        r'''Show how to use errgroup to run multiple tasks in parallel, collect results, and cancel all remaining tasks if any one fails.''',
        r'''<think>
errgroup from golang.org/x/sync provides goroutine group management with error propagation.
WithContext gives a derived context that cancels when any goroutine returns an error.
Need to show collecting results safely (mutex or pre-allocated slice by index).
Common use case: fetching data from multiple APIs concurrently.
</think>

```go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"

	"golang.org/x/sync/errgroup"
)

type APIResult struct {
	Source string
	Data   map[string]any
}

func fetchJSON(ctx context.Context, url string) (map[string]any, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var data map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return nil, fmt.Errorf("decode %s: %w", url, err)
	}
	return data, nil
}

func fetchAll(ctx context.Context, urls map[string]string) ([]APIResult, error) {
	g, ctx := errgroup.WithContext(ctx)

	var mu sync.Mutex
	var results []APIResult

	for source, url := range urls {
		g.Go(func() error {
			data, err := fetchJSON(ctx, url)
			if err != nil {
				return fmt.Errorf("%s: %w", source, err)
			}
			mu.Lock()
			results = append(results, APIResult{Source: source, Data: data})
			mu.Unlock()
			return nil
		})
	}

	if err := g.Wait(); err != nil {
		return nil, err
	}
	return results, nil
}

// Bounded parallelism with errgroup.SetLimit
func processItems(ctx context.Context, items []string) error {
	g, ctx := errgroup.WithContext(ctx)
	g.SetLimit(5) // max 5 concurrent goroutines

	for _, item := range items {
		g.Go(func() error {
			select {
			case <-ctx.Done():
				return ctx.Err()
			default:
			}
			fmt.Printf("processing %s\n", item)
			time.Sleep(100 * time.Millisecond) // simulate work
			return nil
		})
	}

	return g.Wait()
}

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	urls := map[string]string{
		"posts":   "https://jsonplaceholder.typicode.com/posts/1",
		"users":   "https://jsonplaceholder.typicode.com/users/1",
		"todos":   "https://jsonplaceholder.typicode.com/todos/1",
	}

	results, err := fetchAll(ctx, urls)
	if err != nil {
		fmt.Printf("error (other fetches were cancelled): %v\n", err)
		return
	}

	for _, r := range results {
		fmt.Printf("got %s: %d fields\n", r.Source, len(r.Data))
	}
}
```

Key points: `errgroup.WithContext` returns a context that is cancelled as soon as any goroutine returns an error, which automatically cancels in-flight HTTP requests. `SetLimit(n)` provides bounded concurrency without manual semaphore channels.'''
    ),
    (
        "go/context-http-client",
        r'''Build a context-aware HTTP client wrapper in Go with request timeouts, default headers, and response validation. Show proper context propagation.''',
        r'''<think>
A good HTTP client wrapper sets sensible defaults, propagates context for cancellation,
adds common headers, and validates responses. Should be reusable across the codebase.
Use functional options for configuration.
Important: always use http.NewRequestWithContext, never set timeouts on http.Client
AND context (they interact poorly).
</think>

```go
package httpclient

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"time"
)

type Client struct {
	base       *http.Client
	baseURL    string
	headers    map[string]string
	maxBodyLen int64
}

type Option func(*Client)

func WithBaseURL(url string) Option {
	return func(c *Client) { c.baseURL = url }
}

func WithHeader(key, value string) Option {
	return func(c *Client) { c.headers[key] = value }
}

func WithTimeout(d time.Duration) Option {
	return func(c *Client) { c.base.Timeout = d }
}

func WithMaxBody(n int64) Option {
	return func(c *Client) { c.maxBodyLen = n }
}

func New(opts ...Option) *Client {
	c := &Client{
		base: &http.Client{
			Timeout: 30 * time.Second,
		},
		headers:    make(map[string]string),
		maxBodyLen: 10 << 20, // 10 MB default
	}
	c.headers["User-Agent"] = "myapp/1.0"
	for _, o := range opts {
		o(c)
	}
	return c
}

type Response struct {
	StatusCode int
	Headers    http.Header
	Body       []byte
}

func (c *Client) Do(ctx context.Context, method, path string, body io.Reader) (*Response, error) {
	url := c.baseURL + path

	req, err := http.NewRequestWithContext(ctx, method, url, body)
	if err != nil {
		return nil, fmt.Errorf("creating request: %w", err)
	}

	for k, v := range c.headers {
		req.Header.Set(k, v)
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return nil, fmt.Errorf("executing request: %w", err)
	}
	defer resp.Body.Close()

	limited := io.LimitReader(resp.Body, c.maxBodyLen)
	data, err := io.ReadAll(limited)
	if err != nil {
		return nil, fmt.Errorf("reading body: %w", err)
	}

	return &Response{
		StatusCode: resp.StatusCode,
		Headers:    resp.Headers,
		Body:       data,
	}, nil
}

func (c *Client) Get(ctx context.Context, path string) (*Response, error) {
	return c.Do(ctx, http.MethodGet, path, nil)
}

func (c *Client) Post(ctx context.Context, path string, body io.Reader) (*Response, error) {
	return c.Do(ctx, http.MethodPost, path, body)
}

// MustOK wraps a call and returns error if status is not 2xx
func MustOK(resp *Response, err error) (*Response, error) {
	if err != nil {
		return nil, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return resp, fmt.Errorf("unexpected status %d: %s", resp.StatusCode, string(resp.Body))
	}
	return resp, nil
}
```

Usage:

```go
client := httpclient.New(
    httpclient.WithBaseURL("https://api.example.com"),
    httpclient.WithHeader("Authorization", "Bearer "+token),
    httpclient.WithTimeout(10*time.Second),
)

ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()

resp, err := httpclient.MustOK(client.Get(ctx, "/users/123"))
if err != nil {
    log.Fatal(err)
}
fmt.Println(string(resp.Body))
```

The context flows from caller through the HTTP request — if the caller's context is cancelled (e.g., incoming request terminated), the outgoing HTTP call is aborted immediately.'''
    ),
    (
        "go/custom-http-transport",
        r'''Show how to create a custom http.RoundTripper in Go that adds logging, request IDs, and retry logic as middleware layers.''',
        r'''<think>
RoundTripper is the interface for HTTP transport — implement it to intercept all requests.
Chain multiple RoundTrippers for layered middleware (like HTTP middleware but for outgoing requests).
Each wrapper calls the next RoundTripper's RoundTrip method.
Show logging, request ID injection, and a simple retry wrapper.
Important: RoundTrip must not modify the original request (clone it).
</think>

```go
package transport

import (
	"log"
	"net/http"
	"time"

	"github.com/google/uuid"
)

// LoggingTransport logs request method, URL, status, and duration.
type LoggingTransport struct {
	Next http.RoundTripper
}

func (t *LoggingTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	start := time.Now()
	reqID := req.Header.Get("X-Request-ID")

	resp, err := t.Next.RoundTrip(req)

	duration := time.Since(start)
	if err != nil {
		log.Printf("[%s] %s %s -> ERROR: %v (%s)", reqID, req.Method, req.URL, err, duration)
	} else {
		log.Printf("[%s] %s %s -> %d (%s)", reqID, req.Method, req.URL, resp.StatusCode, duration)
	}
	return resp, err
}

// RequestIDTransport injects a unique X-Request-ID header if not present.
type RequestIDTransport struct {
	Next http.RoundTripper
}

func (t *RequestIDTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if req.Header.Get("X-Request-ID") == "" {
		// Clone request to avoid mutating the original
		req = req.Clone(req.Context())
		req.Header.Set("X-Request-ID", uuid.NewString())
	}
	return t.Next.RoundTrip(req)
}

// RetryTransport retries on 5xx errors and network failures.
type RetryTransport struct {
	Next       http.RoundTripper
	MaxRetries int
}

func (t *RetryTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	var resp *http.Response
	var err error

	for attempt := 0; attempt <= t.MaxRetries; attempt++ {
		if attempt > 0 {
			time.Sleep(time.Duration(attempt*100) * time.Millisecond)
		}

		// Body can only be read once — only retry if GetBody is available
		if attempt > 0 && req.GetBody != nil {
			body, bodyErr := req.GetBody()
			if bodyErr != nil {
				return nil, bodyErr
			}
			req = req.Clone(req.Context())
			req.Body = body
		}

		resp, err = t.Next.RoundTrip(req)
		if err != nil {
			continue // network error, retry
		}
		if resp.StatusCode < 500 {
			return resp, nil // success or client error, don't retry
		}
		// 5xx — close body and retry
		resp.Body.Close()
	}
	return resp, err
}

// Build a layered client:
func NewClient() *http.Client {
	base := http.DefaultTransport

	// Chain: retry -> requestID -> logging -> base transport
	chain := &LoggingTransport{
		Next: &RequestIDTransport{
			Next: &RetryTransport{
				Next:       base,
				MaxRetries: 2,
			},
		},
	}

	return &http.Client{
		Transport: chain,
		Timeout:   30 * time.Second,
	}
}
```

Usage:

```go
client := transport.NewClient()

resp, err := client.Get("https://api.example.com/data")
// Logs: [abc-123-...] GET https://api.example.com/data -> 200 (45ms)
```

The chain executes outermost first: logging wraps the entire call (including retries), request ID is injected once, and the retry transport is closest to the base. Always call `req.Clone()` before modifying headers — `RoundTrip` must not mutate the original request per the interface contract.'''
    ),
    (
        "go/connection-pooling",
        r'''How does HTTP connection pooling work in Go's standard library, and how do I tune it for high-throughput scenarios?''',
        r'''<think>
Go's http.Transport maintains a pool of idle connections per host.
Default limits are conservative: MaxIdleConns=100, MaxIdleConnsPerHost=2.
For high-throughput to a single backend, MaxIdleConnsPerHost is the bottleneck.
Must also configure timeouts properly and always read+close response bodies.
Show how to configure and common mistakes that break pooling.
</think>

Go's `http.Transport` pools TCP connections automatically, but the defaults are tuned for general-purpose use, not high-throughput:

```go
package main

import (
	"net"
	"net/http"
	"time"
)

func newHighThroughputClient() *http.Client {
	transport := &http.Transport{
		// Connection pool sizing
		MaxIdleConns:        200,             // total across all hosts
		MaxIdleConnsPerHost: 100,             // per-host (default is only 2!)
		MaxConnsPerHost:     0,               // 0 = unlimited active connections

		// Timeouts for the connection lifecycle
		DialContext: (&net.Dialer{
			Timeout:   5 * time.Second,        // TCP connect timeout
			KeepAlive: 30 * time.Second,       // TCP keepalive interval
		}).DialContext,
		TLSHandshakeTimeout:   5 * time.Second,
		IdleConnTimeout:        90 * time.Second, // close idle conns after this
		ResponseHeaderTimeout:  10 * time.Second, // wait for response headers
		ExpectContinueTimeout:  1 * time.Second,

		// Enable HTTP/2 (enabled by default if TLS is used)
		ForceAttemptHTTP2: true,
	}

	return &http.Client{
		Transport: transport,
		// Do NOT set Timeout here if using context timeouts — they stack
	}
}
```

**Critical rules for connection reuse:**

```go
// WRONG: leaks connections, pool never reuses them
resp, _ := client.Get(url)
data := processHeaders(resp)
// forgot to read and close body!

// CORRECT: always drain and close
resp, err := client.Get(url)
if err != nil {
    return err
}
defer resp.Body.Close()

// Even if you don't need the body, drain it:
io.Copy(io.Discard, resp.Body)
```

**Monitoring pool usage:**

```go
import "net/http/httptrace"

trace := &httptrace.ClientTrace{
    GotConn: func(info httptrace.GotConnInfo) {
        fmt.Printf("reused: %v, idle: %v, idle_time: %v\n",
            info.Reused, info.WasIdle, info.IdleTime)
    },
}

req, _ := http.NewRequestWithContext(
    httptrace.WithClientTrace(ctx, trace),
    "GET", url, nil,
)
client.Do(req)
```

**Common mistakes that break pooling:**

1. Creating a new `http.Client` per request (each gets its own pool)
2. Not reading the response body fully before closing
3. Setting `MaxIdleConnsPerHost` too low for a single-backend service
4. Using `http.DefaultClient` in production (no timeout, pool defaults)

For services that talk to a single backend, set `MaxIdleConnsPerHost` equal to your expected concurrency. Monitor with httptrace to verify connections are actually being reused.'''
    ),
    (
        "go/request-tracing",
        r'''Implement correlation ID / request tracing in a Go HTTP service. Each incoming request should get a unique ID that propagates through all downstream calls and appears in logs.''',
        r'''<think>
Correlation IDs flow via context in Go. Middleware extracts or generates the ID,
stores it in context, and all downstream code reads it from context.
For outgoing HTTP calls, inject the ID as a header.
For logging, create a context-aware logger that always includes the ID.
Show middleware, context helpers, and outgoing request propagation.
</think>

```go
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"

	"github.com/google/uuid"
)

// --- Context key and helpers ---

type ctxKey string

const correlationIDKey ctxKey = "correlation_id"

func WithCorrelationID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, correlationIDKey, id)
}

func CorrelationID(ctx context.Context) string {
	if id, ok := ctx.Value(correlationIDKey).(string); ok {
		return id
	}
	return "unknown"
}

// --- Middleware ---

func CorrelationMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get("X-Correlation-ID")
		if id == "" {
			id = uuid.NewString()
		}

		ctx := WithCorrelationID(r.Context(), id)
		w.Header().Set("X-Correlation-ID", id)

		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// --- Context-aware logger ---

func LoggerFromCtx(ctx context.Context) *slog.Logger {
	return slog.Default().With("correlation_id", CorrelationID(ctx))
}

// --- Outgoing HTTP client that propagates the ID ---

type TracingTransport struct {
	Base http.RoundTripper
}

func (t *TracingTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	req = req.Clone(req.Context())
	if id := CorrelationID(req.Context()); id != "unknown" {
		req.Header.Set("X-Correlation-ID", id)
	}
	base := t.Base
	if base == nil {
		base = http.DefaultTransport
	}
	return base.RoundTrip(req)
}

var tracingClient = &http.Client{
	Transport: &TracingTransport{},
}

// --- Handlers ---

func handleOrder(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	log := LoggerFromCtx(ctx)

	log.Info("processing order")

	// Downstream call automatically gets the correlation ID
	req, _ := http.NewRequestWithContext(ctx, "GET", "http://inventory-svc/check", nil)
	resp, err := tracingClient.Do(req)
	if err != nil {
		log.Error("inventory check failed", "error", err)
		http.Error(w, "internal error", 500)
		return
	}
	defer resp.Body.Close()

	log.Info("order complete", "inventory_status", resp.StatusCode)
	w.Write([]byte("order processed"))
}

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))

	mux := http.NewServeMux()
	mux.HandleFunc("POST /orders", handleOrder)

	handler := CorrelationMiddleware(mux)
	http.ListenAndServe(":8080", handler)
}
```

Every log line includes `"correlation_id":"abc-123-..."`, and when this service calls another service, the same ID is forwarded via the `X-Correlation-ID` header. The downstream service's correlation middleware picks it up, completing the distributed trace chain. This pattern works without any tracing infrastructure — just headers and context.'''
    ),
    (
        "go/graceful-lifecycle",
        r'''Implement a graceful service lifecycle in Go: start multiple components (HTTP server, background workers), handle SIGTERM/SIGINT, and shut everything down cleanly with a timeout.''',
        r'''<think>
A production service needs coordinated startup and shutdown.
Use signal.NotifyContext for clean signal handling.
errgroup to manage multiple long-running goroutines.
Shutdown order matters: stop accepting new work, drain in-flight, close resources.
Add a shutdown timeout to prevent hanging forever.
</think>

```go
package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"golang.org/x/sync/errgroup"
)

type Service struct {
	httpServer *http.Server
	stopWorker context.CancelFunc
}

func NewService() *Service {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("ok"))
	})
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(2 * time.Second) // simulate work
		w.Write([]byte("hello"))
	})

	return &Service{
		httpServer: &http.Server{
			Addr:    ":8080",
			Handler: mux,
		},
	}
}

// Background worker that processes a queue
func (s *Service) runWorker(ctx context.Context) error {
	log.Println("worker started")
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			log.Println("worker stopping...")
			return nil
		case <-ticker.C:
			log.Println("worker: processing job")
		}
	}
}

func (s *Service) Run() error {
	// Trap SIGINT, SIGTERM
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	g, gCtx := errgroup.WithContext(ctx)

	// Start HTTP server
	g.Go(func() error {
		log.Printf("HTTP server starting on %s", s.httpServer.Addr)
		err := s.httpServer.ListenAndServe()
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	})

	// Start background worker
	workerCtx, workerCancel := context.WithCancel(gCtx)
	s.stopWorker = workerCancel
	g.Go(func() error {
		return s.runWorker(workerCtx)
	})

	// Shutdown coordinator
	g.Go(func() error {
		<-gCtx.Done() // wait for signal or error
		log.Println("shutting down...")

		// Give in-flight requests up to 15 seconds to complete
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer shutdownCancel()

		// Ordered shutdown
		var shutdownErr error
		var mu sync.Mutex

		var wg sync.WaitGroup
		wg.Add(1)
		go func() {
			defer wg.Done()
			if err := s.httpServer.Shutdown(shutdownCtx); err != nil {
				mu.Lock()
				shutdownErr = fmt.Errorf("http shutdown: %w", err)
				mu.Unlock()
			}
			log.Println("HTTP server stopped")
		}()

		// Stop worker
		s.stopWorker()
		log.Println("worker stop signal sent")

		wg.Wait()
		return shutdownErr
	})

	return g.Wait()
}

func main() {
	svc := NewService()
	if err := svc.Run(); err != nil {
		log.Fatalf("service error: %v", err)
	}
	log.Println("service exited cleanly")
}
```

Flow: signal arrives -> context cancels -> shutdown coordinator runs -> HTTP server stops accepting (in-flight requests finish within 15s) -> worker receives cancellation -> `g.Wait()` returns when all goroutines exit. If shutdown exceeds 15 seconds, the shutdown context expires and forces termination.'''
    ),
    (
        "go/health-check-endpoint",
        r'''Design health check endpoints for a Go microservice that reports readiness (can serve traffic) and liveness (is not deadlocked), including dependency checks.''',
        r'''<think>
Kubernetes-style health checks: /healthz (liveness) and /readyz (readiness).
Liveness: is the process alive and not deadlocked? Should be cheap and always pass unless stuck.
Readiness: can we serve traffic? Check DB connections, cache, downstream dependencies.
Each check should have a timeout to avoid blocking the probe.
Return structured JSON with individual check results.
</think>

```go
package health

import (
	"context"
	"encoding/json"
	"net/http"
	"sync"
	"time"
)

type Status string

const (
	StatusUp   Status = "up"
	StatusDown Status = "down"
)

type CheckResult struct {
	Status  Status `json:"status"`
	Message string `json:"message,omitempty"`
	Latency string `json:"latency"`
}

type HealthResponse struct {
	Status Status                 `json:"status"`
	Checks map[string]CheckResult `json:"checks"`
}

type CheckFunc func(ctx context.Context) error

type Checker struct {
	mu             sync.RWMutex
	livenessChecks map[string]CheckFunc
	readyChecks    map[string]CheckFunc
	timeout        time.Duration
}

func NewChecker(timeout time.Duration) *Checker {
	return &Checker{
		livenessChecks: make(map[string]CheckFunc),
		readyChecks:    make(map[string]CheckFunc),
		timeout:        timeout,
	}
}

func (c *Checker) AddLiveness(name string, fn CheckFunc) {
	c.mu.Lock()
	c.livenessChecks[name] = fn
	c.mu.Unlock()
}

func (c *Checker) AddReadiness(name string, fn CheckFunc) {
	c.mu.Lock()
	c.readyChecks[name] = fn
	c.mu.Unlock()
}

func (c *Checker) runChecks(checks map[string]CheckFunc) HealthResponse {
	resp := HealthResponse{
		Status: StatusUp,
		Checks: make(map[string]CheckResult, len(checks)),
	}

	var mu sync.Mutex
	var wg sync.WaitGroup

	for name, fn := range checks {
		wg.Add(1)
		go func() {
			defer wg.Done()
			ctx, cancel := context.WithTimeout(context.Background(), c.timeout)
			defer cancel()

			start := time.Now()
			err := fn(ctx)
			latency := time.Since(start)

			result := CheckResult{
				Status:  StatusUp,
				Latency: latency.String(),
			}
			if err != nil {
				result.Status = StatusDown
				result.Message = err.Error()
			}

			mu.Lock()
			resp.Checks[name] = result
			if result.Status == StatusDown {
				resp.Status = StatusDown
			}
			mu.Unlock()
		}()
	}

	wg.Wait()
	return resp
}

func (c *Checker) LivenessHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		c.mu.RLock()
		checks := c.livenessChecks
		c.mu.RUnlock()

		resp := c.runChecks(checks)
		writeResponse(w, resp)
	}
}

func (c *Checker) ReadinessHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		c.mu.RLock()
		checks := c.readyChecks
		c.mu.RUnlock()

		resp := c.runChecks(checks)
		writeResponse(w, resp)
	}
}

func writeResponse(w http.ResponseWriter, resp HealthResponse) {
	w.Header().Set("Content-Type", "application/json")
	if resp.Status == StatusDown {
		w.WriteHeader(http.StatusServiceUnavailable)
	}
	json.NewEncoder(w).Encode(resp)
}
```

Usage:

```go
checker := health.NewChecker(3 * time.Second)

checker.AddReadiness("postgres", func(ctx context.Context) error {
    return db.PingContext(ctx)
})

checker.AddReadiness("redis", func(ctx context.Context) error {
    return redisClient.Ping(ctx).Err()
})

checker.AddLiveness("goroutine_count", func(ctx context.Context) error {
    if runtime.NumGoroutine() > 10000 {
        return fmt.Errorf("goroutine leak: %d", runtime.NumGoroutine())
    }
    return nil
})

mux.HandleFunc("GET /healthz", checker.LivenessHandler())
mux.HandleFunc("GET /readyz", checker.ReadinessHandler())
```

Response example:
```json
{"status":"up","checks":{"postgres":{"status":"up","latency":"2ms"},"redis":{"status":"up","latency":"1ms"}}}
```

All dependency checks run concurrently with individual timeouts so one slow check doesn't block the others.'''
    ),
    (
        "go/config-management",
        r'''Show a clean configuration pattern in Go that loads from environment variables, command-line flags, and a config file, with proper precedence: flags > env > file > defaults.''',
        r'''<think>
Layer configs with clear precedence. Start with defaults, overlay file, then env, then flags.
Use a struct with tags for env var names. No external dependencies needed for a clean approach.
json or yaml config file, os.Getenv for env vars, flag package for CLI.
Validate required fields after loading all layers.
Show a complete working example.
</think>

```go
package config

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strconv"
	"time"
)

type Config struct {
	Host         string        `json:"host"`
	Port         int           `json:"port"`
	DatabaseURL  string        `json:"database_url"`
	LogLevel     string        `json:"log_level"`
	ReadTimeout  time.Duration `json:"read_timeout"`
	WriteTimeout time.Duration `json:"write_timeout"`
	Debug        bool          `json:"debug"`
}

func defaults() Config {
	return Config{
		Host:         "0.0.0.0",
		Port:         8080,
		LogLevel:     "info",
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
		Debug:        false,
	}
}

func fromFile(path string, cfg *Config) error {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil // config file is optional
		}
		return err
	}
	return json.Unmarshal(data, cfg)
}

func fromEnv(cfg *Config) {
	if v := os.Getenv("APP_HOST"); v != "" {
		cfg.Host = v
	}
	if v := os.Getenv("APP_PORT"); v != "" {
		if p, err := strconv.Atoi(v); err == nil {
			cfg.Port = p
		}
	}
	if v := os.Getenv("APP_DATABASE_URL"); v != "" {
		cfg.DatabaseURL = v
	}
	if v := os.Getenv("APP_LOG_LEVEL"); v != "" {
		cfg.LogLevel = v
	}
	if v := os.Getenv("APP_DEBUG"); v != "" {
		cfg.Debug = v == "true" || v == "1"
	}
	if v := os.Getenv("APP_READ_TIMEOUT"); v != "" {
		if d, err := time.ParseDuration(v); err == nil {
			cfg.ReadTimeout = d
		}
	}
}

func fromFlags(cfg *Config) {
	host := flag.String("host", "", "bind host")
	port := flag.Int("port", 0, "bind port")
	dbURL := flag.String("database-url", "", "database connection string")
	logLevel := flag.String("log-level", "", "log level (debug, info, warn, error)")
	debug := flag.Bool("debug", false, "enable debug mode")
	configFile := flag.String("config", "config.json", "path to config file")

	flag.Parse()

	// Load file first (only if flag tells us where)
	fromFile(*configFile, cfg)

	// Then env
	fromEnv(cfg)

	// Then flags (only override if explicitly set)
	flag.Visit(func(f *flag.Flag) {
		switch f.Name {
		case "host":
			cfg.Host = *host
		case "port":
			cfg.Port = *port
		case "database-url":
			cfg.DatabaseURL = *dbURL
		case "log-level":
			cfg.LogLevel = *logLevel
		case "debug":
			cfg.Debug = *debug
		}
	})
}

func (c Config) Validate() error {
	if c.DatabaseURL == "" {
		return fmt.Errorf("database_url is required (set APP_DATABASE_URL or --database-url)")
	}
	if c.Port < 1 || c.Port > 65535 {
		return fmt.Errorf("port must be between 1 and 65535")
	}
	return nil
}

func Load() (Config, error) {
	cfg := defaults()
	fromFlags(&cfg) // internally calls fromFile, then fromEnv, then applies flags
	if err := cfg.Validate(); err != nil {
		return Config{}, err
	}
	return cfg, nil
}
```

Usage:

```go
func main() {
    cfg, err := config.Load()
    if err != nil {
        log.Fatalf("config: %v", err)
    }
    log.Printf("starting on %s:%d (debug=%v)", cfg.Host, cfg.Port, cfg.Debug)
}
```

```bash
# All equivalent ways to set the port (later layers win):
# config.json: {"port": 3000}
# APP_PORT=3001
# --port 3002
```

The `flag.Visit` trick is key — it only iterates over flags that were explicitly set on the command line, so unset flags don't clobber env/file values with zero values.'''
    ),
    (
        "go/dependency-injection",
        r'''Show clean dependency injection patterns in Go without a DI framework. How do I structure a service layer that's testable and doesn't rely on globals?''',
        r'''<think>
Go DI is just passing interfaces through constructors. No framework needed.
Define interfaces at the consumer side (not the provider).
Use constructor injection — each struct receives its dependencies as constructor args.
Show a layered example: handler -> service -> repository, all wired via interfaces.
This makes testing trivial — pass in mocks that satisfy the interface.
</think>

```go
package main

// --- Interfaces defined by consumers ---

// Repository interface — defined where it's used, not where it's implemented
type UserRepository interface {
	FindByID(id string) (*User, error)
	Save(user *User) error
}

type EmailSender interface {
	Send(to, subject, body string) error
}

// --- Domain model ---

type User struct {
	ID    string
	Name  string
	Email string
}

// --- Service layer (depends on interfaces) ---

type UserService struct {
	repo  UserRepository
	email EmailSender
}

func NewUserService(repo UserRepository, email EmailSender) *UserService {
	return &UserService{repo: repo, email: email}
}

func (s *UserService) Register(name, email string) (*User, error) {
	user := &User{
		ID:    generateID(),
		Name:  name,
		Email: email,
	}
	if err := s.repo.Save(user); err != nil {
		return nil, fmt.Errorf("saving user: %w", err)
	}
	if err := s.email.Send(email, "Welcome!", "Hello "+name); err != nil {
		// Log but don't fail — email is best-effort
		log.Printf("welcome email failed for %s: %v", email, err)
	}
	return user, nil
}

// --- Concrete implementations ---

type PostgresUserRepo struct {
	db *sql.DB
}

func NewPostgresUserRepo(db *sql.DB) *PostgresUserRepo {
	return &PostgresUserRepo{db: db}
}

func (r *PostgresUserRepo) FindByID(id string) (*User, error) {
	var u User
	err := r.db.QueryRow("SELECT id, name, email FROM users WHERE id=$1", id).
		Scan(&u.ID, &u.Name, &u.Email)
	return &u, err
}

func (r *PostgresUserRepo) Save(user *User) error {
	_, err := r.db.Exec("INSERT INTO users (id, name, email) VALUES ($1, $2, $3)",
		user.ID, user.Name, user.Email)
	return err
}

type SMTPSender struct {
	host string
	port int
}

func (s *SMTPSender) Send(to, subject, body string) error {
	// real SMTP logic
	return nil
}

// --- HTTP handler (depends on service) ---

type UserHandler struct {
	svc *UserService
}

func NewUserHandler(svc *UserService) *UserHandler {
	return &UserHandler{svc: svc}
}

func (h *UserHandler) HandleRegister(w http.ResponseWriter, r *http.Request) {
	// parse request, call h.svc.Register(), write response
}

// --- Wiring (composition root) ---

func main() {
	db, _ := sql.Open("postgres", os.Getenv("DATABASE_URL"))

	// Wire dependencies
	repo := NewPostgresUserRepo(db)
	emailer := &SMTPSender{host: "smtp.example.com", port: 587}
	userSvc := NewUserService(repo, emailer)
	userHandler := NewUserHandler(userSvc)

	mux := http.NewServeMux()
	mux.HandleFunc("POST /users", userHandler.HandleRegister)
	http.ListenAndServe(":8080", mux)
}
```

**Testing with mocks — no framework needed:**

```go
type mockRepo struct {
	users map[string]*User
}

func (m *mockRepo) FindByID(id string) (*User, error) {
	u, ok := m.users[id]
	if !ok {
		return nil, fmt.Errorf("not found")
	}
	return u, nil
}

func (m *mockRepo) Save(user *User) error {
	m.users[user.ID] = user
	return nil
}

type mockEmail struct {
	sent []string
}

func (m *mockEmail) Send(to, subject, body string) error {
	m.sent = append(m.sent, to)
	return nil
}

func TestRegister(t *testing.T) {
	repo := &mockRepo{users: make(map[string]*User)}
	email := &mockEmail{}
	svc := NewUserService(repo, email)

	user, err := svc.Register("Alice", "alice@test.com")
	if err != nil {
		t.Fatal(err)
	}
	if user.Name != "Alice" {
		t.Errorf("got name %q, want Alice", user.Name)
	}
	if len(email.sent) != 1 {
		t.Errorf("expected 1 email sent, got %d", len(email.sent))
	}
}
```

The key Go idiom: accept interfaces, return structs. Define the interface where it's consumed (UserService defines what it needs from a repository), not where it's implemented. All wiring happens in `main()` — the composition root.'''
    ),
    (
        "go/generic-iterator",
        r'''Implement an iterator pattern using Go generics that supports map, filter, and reduce operations on any iterable collection, similar to functional programming styles.''',
        r'''<think>
Go 1.23+ has range-over-func iterators (iter.Seq). For broader compatibility, can also show
a pull-based iterator with generics. I'll show the modern iter.Seq approach plus a
standalone version that works without the iter package.
Map, Filter, Reduce as generic functions that compose.
Keep it practical and show chaining.
</think>

```go
package itertools

// Seq is a pull-based iterator (compatible with Go 1.21+ generics).
// For Go 1.23+, you can use iter.Seq instead.
type Seq[T any] func(yield func(T) bool)

// FromSlice creates an iterator from a slice.
func FromSlice[T any](s []T) Seq[T] {
	return func(yield func(T) bool) {
		for _, v := range s {
			if !yield(v) {
				return
			}
		}
	}
}

// Filter returns elements where pred is true.
func Filter[T any](seq Seq[T], pred func(T) bool) Seq[T] {
	return func(yield func(T) bool) {
		seq(func(v T) bool {
			if pred(v) {
				return yield(v)
			}
			return true
		})
	}
}

// Map transforms each element.
func Map[T, U any](seq Seq[T], fn func(T) U) Seq[U] {
	return func(yield func(U) bool) {
		seq(func(v T) bool {
			return yield(fn(v))
		})
	}
}

// Reduce folds all elements into a single value.
func Reduce[T, U any](seq Seq[T], initial U, fn func(U, T) U) U {
	acc := initial
	seq(func(v T) bool {
		acc = fn(acc, v)
		return true
	})
	return acc
}

// Take returns at most n elements.
func Take[T any](seq Seq[T], n int) Seq[T] {
	return func(yield func(T) bool) {
		count := 0
		seq(func(v T) bool {
			if count >= n {
				return false
			}
			count++
			return yield(v)
		})
	}
}

// Collect gathers all elements into a slice.
func Collect[T any](seq Seq[T]) []T {
	var result []T
	seq(func(v T) bool {
		result = append(result, v)
		return true
	})
	return result
}

// Zip combines two iterators into pairs.
func Zip[A, B any](a Seq[A], b Seq[B]) Seq[Pair[A, B]] {
	return func(yield func(Pair[A, B]) bool) {
		sa := Collect(a)
		sb := Collect(b)
		n := len(sa)
		if len(sb) < n {
			n = len(sb)
		}
		for i := 0; i < n; i++ {
			if !yield(Pair[A, B]{First: sa[i], Second: sb[i]}) {
				return
			}
		}
	}
}

type Pair[A, B any] struct {
	First  A
	Second B
}
```

Usage:

```go
package main

import (
	"fmt"
	"strings"

	"myapp/itertools"
)

func main() {
	names := []string{"Alice", "Bob", "Charlie", "Dave", "Eve"}

	// Chain: filter names > 3 chars, uppercase, take first 2
	result := itertools.Collect(
		itertools.Take(
			itertools.Map(
				itertools.Filter(
					itertools.FromSlice(names),
					func(s string) bool { return len(s) > 3 },
				),
				strings.ToUpper,
			),
			2,
		),
	)
	fmt.Println(result) // [ALICE CHARLIE]

	// Reduce: sum of lengths
	numbers := []int{1, 2, 3, 4, 5}
	sum := itertools.Reduce(
		itertools.Filter(
			itertools.FromSlice(numbers),
			func(n int) bool { return n%2 == 0 },
		),
		0,
		func(acc, v int) int { return acc + v },
	)
	fmt.Println(sum) // 6
}
```

The `Seq[T]` type matches Go 1.23's `iter.Seq[T]` signature, so this code is forward-compatible with range-over-func. All operations are lazy — Filter and Map don't allocate slices until you call Collect or Reduce.'''
    ),
    (
        "go/testing-with-mocks",
        r'''Show how to write testable Go code using interface-based mocking, without any external mocking framework. Include table-driven tests and test helpers.''',
        r'''<think>
Go testing best practices: small interfaces, hand-written mocks, table-driven tests.
Show a real scenario: testing a service that depends on a database and an external API.
Include test helpers for setup/teardown and t.Helper() for clean stack traces.
Table-driven tests are idiomatic Go — loop over test cases with subtests.
</think>

```go
// --- Production code ---
package order

import (
	"context"
	"fmt"
	"time"
)

type Product struct {
	ID    string
	Name  string
	Price float64
}

type Inventory interface {
	CheckStock(ctx context.Context, productID string) (int, error)
}

type PaymentGateway interface {
	Charge(ctx context.Context, amount float64, token string) (string, error)
}

type OrderService struct {
	inventory Inventory
	payments  PaymentGateway
}

func NewOrderService(inv Inventory, pay PaymentGateway) *OrderService {
	return &OrderService{inventory: inv, payments: pay}
}

type OrderResult struct {
	OrderID   string
	ChargeID  string
	Total     float64
	CreatedAt time.Time
}

func (s *OrderService) PlaceOrder(ctx context.Context, productID string, qty int, payToken string) (*OrderResult, error) {
	stock, err := s.inventory.CheckStock(ctx, productID)
	if err != nil {
		return nil, fmt.Errorf("checking stock: %w", err)
	}
	if stock < qty {
		return nil, fmt.Errorf("insufficient stock: have %d, need %d", stock, qty)
	}

	total := float64(qty) * 29.99 // simplified pricing
	chargeID, err := s.payments.Charge(ctx, total, payToken)
	if err != nil {
		return nil, fmt.Errorf("payment failed: %w", err)
	}

	return &OrderResult{
		OrderID:   "ord-123",
		ChargeID:  chargeID,
		Total:     total,
		CreatedAt: time.Now(),
	}, nil
}
```

```go
// --- Test file ---
package order_test

import (
	"context"
	"errors"
	"testing"
)

// Hand-written mocks

type mockInventory struct {
	stock    int
	stockErr error
	called   bool
}

func (m *mockInventory) CheckStock(ctx context.Context, productID string) (int, error) {
	m.called = true
	return m.stock, m.stockErr
}

type mockPayments struct {
	chargeID  string
	chargeErr error
	charged   float64
}

func (m *mockPayments) Charge(ctx context.Context, amount float64, token string) (string, error) {
	m.charged = amount
	return m.chargeID, m.chargeErr
}

// Test helper

func setupService(t *testing.T, inv *mockInventory, pay *mockPayments) *order.OrderService {
	t.Helper()
	if inv == nil {
		inv = &mockInventory{stock: 100}
	}
	if pay == nil {
		pay = &mockPayments{chargeID: "ch_test"}
	}
	return order.NewOrderService(inv, pay)
}

// Table-driven tests

func TestPlaceOrder(t *testing.T) {
	tests := []struct {
		name      string
		stock     int
		stockErr  error
		chargeID  string
		chargeErr error
		qty       int
		wantErr   string
	}{
		{
			name:     "successful order",
			stock:    10,
			chargeID: "ch_ok",
			qty:      2,
		},
		{
			name:    "insufficient stock",
			stock:   1,
			qty:     5,
			wantErr: "insufficient stock",
		},
		{
			name:     "inventory error",
			stockErr: errors.New("db down"),
			qty:      1,
			wantErr:  "checking stock",
		},
		{
			name:      "payment failure",
			stock:     10,
			chargeErr: errors.New("card declined"),
			qty:       1,
			wantErr:   "payment failed",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			inv := &mockInventory{stock: tt.stock, stockErr: tt.stockErr}
			pay := &mockPayments{chargeID: tt.chargeID, chargeErr: tt.chargeErr}
			svc := setupService(t, inv, pay)

			result, err := svc.PlaceOrder(context.Background(), "prod-1", tt.qty, "tok_test")

			if tt.wantErr != "" {
				if err == nil {
					t.Fatalf("expected error containing %q, got nil", tt.wantErr)
				}
				if !contains(err.Error(), tt.wantErr) {
					t.Fatalf("error %q doesn't contain %q", err.Error(), tt.wantErr)
				}
				return
			}

			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if result.ChargeID != tt.chargeID {
				t.Errorf("charge ID = %q, want %q", result.ChargeID, tt.chargeID)
			}
			wantTotal := float64(tt.qty) * 29.99
			if result.Total != wantTotal {
				t.Errorf("total = %.2f, want %.2f", result.Total, wantTotal)
			}
		})
	}
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && (s == sub || len(s) > 0 && containsStr(s, sub))
}

func containsStr(s, sub string) bool {
	for i := 0; i <= len(s)-len(sub); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
```

Key patterns: define interfaces where they're consumed (small, focused), hand-write mocks as simple structs, use `t.Helper()` in setup functions so test failures point to the right line, and use table-driven subtests for comprehensive coverage without repetition.'''
    ),
    (
        "go/integration-testing",
        r'''Show patterns for writing integration tests in Go that test against real databases and external services, with proper setup/teardown and test isolation.''',
        r'''<think>
Integration tests need real infrastructure. Use build tags to separate from unit tests.
TestMain for one-time setup/teardown. testcontainers-go for spinning up Docker containers.
Each test should get a clean state — either transactions that rollback or fresh schemas.
Show a practical example with PostgreSQL using testcontainers.
</think>

```go
//go:build integration

package db_test

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"testing"
	"time"

	_ "github.com/lib/pq"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"
)

var testDB *sql.DB

// TestMain runs once for the entire test file — start container, run tests, cleanup.
func TestMain(m *testing.M) {
	ctx := context.Background()

	// Start a PostgreSQL container
	pg, err := testcontainers.GenericContainer(ctx, testcontainers.GenericContainerRequest{
		ContainerRequest: testcontainers.ContainerRequest{
			Image:        "postgres:16-alpine",
			ExposedPorts: []string{"5432/tcp"},
			Env: map[string]string{
				"POSTGRES_USER":     "test",
				"POSTGRES_PASSWORD": "test",
				"POSTGRES_DB":       "testdb",
			},
			WaitingFor: wait.ForListeningPort("5432/tcp").WithStartupTimeout(30 * time.Second),
		},
		Started: true,
	})
	if err != nil {
		panic(fmt.Sprintf("starting postgres container: %v", err))
	}
	defer pg.Terminate(ctx)

	host, _ := pg.Host(ctx)
	port, _ := pg.MappedPort(ctx, "5432")

	dsn := fmt.Sprintf("postgres://test:test@%s:%s/testdb?sslmode=disable", host, port.Port())
	testDB, err = sql.Open("postgres", dsn)
	if err != nil {
		panic(err)
	}

	// Run migrations
	migrate(testDB)

	os.Exit(m.Run())
}

func migrate(db *sql.DB) {
	db.Exec(`CREATE TABLE IF NOT EXISTS users (
		id SERIAL PRIMARY KEY,
		name TEXT NOT NULL,
		email TEXT UNIQUE NOT NULL,
		created_at TIMESTAMPTZ DEFAULT NOW()
	)`)
}

// txTest wraps each test in a transaction that rolls back — perfect isolation.
func txTest(t *testing.T) *sql.Tx {
	t.Helper()
	tx, err := testDB.Begin()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		tx.Rollback() // always rollback — test data never persists
	})
	return tx
}

// --- Actual integration tests ---

func TestCreateUser(t *testing.T) {
	tx := txTest(t)

	_, err := tx.Exec("INSERT INTO users (name, email) VALUES ($1, $2)", "Alice", "alice@test.com")
	if err != nil {
		t.Fatalf("insert failed: %v", err)
	}

	var count int
	tx.QueryRow("SELECT COUNT(*) FROM users WHERE email = $1", "alice@test.com").Scan(&count)
	if count != 1 {
		t.Errorf("expected 1 user, got %d", count)
	}
}

func TestUniqueEmailConstraint(t *testing.T) {
	tx := txTest(t)

	tx.Exec("INSERT INTO users (name, email) VALUES ($1, $2)", "Alice", "dupe@test.com")
	_, err := tx.Exec("INSERT INTO users (name, email) VALUES ($1, $2)", "Bob", "dupe@test.com")
	if err == nil {
		t.Fatal("expected unique constraint error, got nil")
	}
}

func TestListUsers(t *testing.T) {
	tx := txTest(t)

	// Seed test data
	for i := 0; i < 5; i++ {
		tx.Exec("INSERT INTO users (name, email) VALUES ($1, $2)",
			fmt.Sprintf("User%d", i), fmt.Sprintf("user%d@test.com", i))
	}

	rows, err := tx.Query("SELECT name FROM users ORDER BY name")
	if err != nil {
		t.Fatal(err)
	}
	defer rows.Close()

	var names []string
	for rows.Next() {
		var name string
		rows.Scan(&name)
		names = append(names, name)
	}

	if len(names) != 5 {
		t.Errorf("expected 5 users, got %d", len(names))
	}
}
```

Run:
```bash
go test -tags integration -v ./...
```

Key patterns:
- **Build tag** (`//go:build integration`) keeps these out of normal `go test`
- **TestMain** handles one-time container lifecycle
- **txTest helper** wraps each test in a transaction that auto-rollbacks, so tests are fully isolated without manual cleanup
- **testcontainers-go** spins up real PostgreSQL — no mocking the database layer'''
    ),
]
