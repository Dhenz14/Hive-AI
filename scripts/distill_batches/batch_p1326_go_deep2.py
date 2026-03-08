"""Go deep reasoning pairs batch 2: networking and HTTP."""
PAIRS = [
    ("go_deep/graceful_shutdown_http", r'''How do I build a production-grade HTTP server in Go that shuts down gracefully on SIGINT/SIGTERM, finishing in-flight requests before exiting?''', r'''<think>
Graceful shutdown is critical for production servers — if we just call os.Exit, in-flight
requests get dropped, database transactions left half-done, etc. Go's http.Server has a
Shutdown(ctx) method since Go 1.8 that stops accepting new connections and waits for
existing ones to complete.

The pattern is:
1. Create the server explicitly (not http.ListenAndServe global).
2. Start it in a goroutine so main doesn't block.
3. Use signal.NotifyContext or a channel with signal.Notify to catch SIGINT/SIGTERM.
4. When signal fires, call srv.Shutdown(ctx) with a deadline context.
5. If shutdown doesn't complete in time, the context cancels and we force-exit.

Key subtlety: ListenAndServe returns http.ErrServerClosed after Shutdown is called — that's
not an error, it's expected. We must check for it to avoid logging a spurious error.

Another subtlety: Shutdown only drains HTTP connections. If we have background goroutines
(workers, cron jobs), we need a separate WaitGroup or done channel for those. I'll show
both the HTTP drain and a background worker drain.

I should also set sensible timeouts on the server (ReadTimeout, WriteTimeout, IdleTimeout)
because without them, a slow client can hold a connection open forever, blocking shutdown.

The shutdown deadline (e.g., 30 seconds) gives in-flight handlers time to finish but
prevents indefinite hangs. After Shutdown returns, we clean up remaining resources.

Let me write a complete example with a slow handler to demonstrate the drain behavior.
</think>

Here is a production-grade HTTP server with graceful shutdown:

```go
package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

func main() {
	// Background worker tracking
	var wg sync.WaitGroup

	mux := http.NewServeMux()

	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, "OK")
	})

	// Slow endpoint to demonstrate graceful drain
	mux.HandleFunc("/slow", func(w http.ResponseWriter, r *http.Request) {
		wg.Add(1)
		defer wg.Done()
		log.Println("slow request started")
		select {
		case <-time.After(5 * time.Second):
			fmt.Fprintln(w, "slow request completed")
		case <-r.Context().Done():
			log.Println("slow request cancelled by client")
		}
	})

	srv := &http.Server{
		Addr:         ":8080",
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Start server in background
	go func() {
		log.Printf("listening on %s", srv.Addr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("listen error: %v", err)
		}
	}()

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	sig := <-quit
	log.Printf("received signal %v, shutting down...", sig)

	// Give in-flight requests up to 30 seconds to finish
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("forced shutdown: %v", err)
	} else {
		log.Println("http server drained cleanly")
	}

	// Wait for background workers to finish
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		log.Println("all background work completed")
	case <-ctx.Done():
		log.Println("timed out waiting for background work")
	}

	log.Println("server exited")
	os.Exit(0)
}
```

Key design points:

- **`http.ErrServerClosed`** is the expected return from `ListenAndServe` after `Shutdown` — not an error.
- **Timeouts on the server** prevent slow/malicious clients from blocking shutdown forever.
- **`sync.WaitGroup`** tracks background work that outlives the HTTP request/response cycle.
- **30-second shutdown deadline** balances giving handlers time to finish vs. not hanging indefinitely.
- **Signal channel buffer of 1** ensures the signal is not lost if we are not yet receiving on the channel.'''),

    ("go_deep/middleware_chain_context", r'''What is the idiomatic way to build an HTTP middleware chain in Go that passes typed values through context, avoiding the stringly-typed context.WithValue pitfall?''', r'''<think>
The common mistake with context.WithValue is using string keys, which creates collision
risks and loses type safety. The idiomatic Go pattern uses unexported types as context
keys — since the type is unexported, no external package can accidentally collide with it.

For a middleware chain, I need to think about:
1. Key type safety: unexported struct or int type per value.
2. Accessor functions: exported Get/Set functions that hide the key type.
3. Chaining: each middleware wraps the next http.Handler.
4. Ordering: middleware executes outside-in (first added = outermost wrapper).

The func(http.Handler) http.Handler signature is the standard middleware type. I can
compose them with a simple loop or a Chain() helper.

For typed context values, the pattern is:
  type contextKey struct{} // unexported, zero-size
  func WithRequestID(ctx context.Context, id string) context.Context
  func RequestID(ctx context.Context) (string, bool)

This is better than string keys because:
- No possible collision even if two packages both use "requestID" as a concept.
- The compiler catches type mismatches.
- Zero-size struct keys don't allocate.

I should show a realistic chain: logging, request ID injection, auth, and a handler
that reads values set by upstream middleware. I'll also show the Chain combinator that
applies middleware in the correct order.

One subtlety: middleware order matters. If auth middleware needs the request ID for
logging, the request ID middleware must run first (be outermost). The Chain function
should make this obvious.
</think>

Here is a clean middleware chain with type-safe context values:

```go
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"
)

// ---------- Type-safe context keys ----------

// Each key is an unexported zero-size type — impossible to collide.

type requestIDKey struct{}

func WithRequestID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, requestIDKey{}, id)
}

func RequestID(ctx context.Context) string {
	id, _ := ctx.Value(requestIDKey{}).(string)
	return id
}

type userKey struct{}

type User struct {
	ID   string
	Role string
}

func WithUser(ctx context.Context, u User) context.Context {
	return context.WithValue(ctx, userKey{}, u)
}

func GetUser(ctx context.Context) (User, bool) {
	u, ok := ctx.Value(userKey{}).(User)
	return u, ok
}

// ---------- Middleware type and combinator ----------

type Middleware func(http.Handler) http.Handler

// Chain applies middleware in the order given: first argument is outermost.
func Chain(handler http.Handler, mws ...Middleware) http.Handler {
	for i := len(mws) - 1; i >= 0; i-- {
		handler = mws[i](handler)
	}
	return handler
}

// ---------- Middleware implementations ----------

func RequestIDMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get("X-Request-ID")
		if id == "" {
			b := make([]byte, 8)
			rand.Read(b)
			id = hex.EncodeToString(b)
		}
		ctx := WithRequestID(r.Context(), id)
		w.Header().Set("X-Request-ID", id)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func LoggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		log.Printf("[%s] %s %s %v",
			RequestID(r.Context()), r.Method, r.URL.Path, time.Since(start))
	})
}

func AuthMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token := r.Header.Get("Authorization")
		if !strings.HasPrefix(token, "Bearer ") {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		// In production, validate the token and look up the user.
		user := User{ID: "u_123", Role: "admin"}
		ctx := WithUser(r.Context(), user)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// ---------- Application handler ----------

func profileHandler(w http.ResponseWriter, r *http.Request) {
	user, ok := GetUser(r.Context())
	if !ok {
		http.Error(w, "no user in context", http.StatusInternalServerError)
		return
	}
	fmt.Fprintf(w, "request=%s user=%s role=%s\n",
		RequestID(r.Context()), user.ID, user.Role)
}

func main() {
	handler := Chain(
		http.HandlerFunc(profileHandler),
		RequestIDMiddleware, // outermost — runs first
		LoggingMiddleware,   // logs after inner handlers complete
		AuthMiddleware,      // innermost before handler
	)

	log.Fatal(http.ListenAndServe(":8080", handler))
}
```

Why this pattern works:

- **Unexported key types** (`requestIDKey{}`) guarantee no collisions — even if another package uses the same concept, the types differ.
- **Zero-size structs** as keys add no allocation overhead.
- **Accessor functions** (`RequestID()`, `GetUser()`) give you type-safe reads with no casting at call sites.
- **`Chain()` applies middleware in reading order** — first argument is outermost, matching how you reason about the pipeline.'''),

    ("go_deep/body_limit_timeout_middleware", r'''How do I write HTTP middleware in Go that limits request body size AND enforces a per-request timeout, and what are the subtle gotchas?''', r'''<think>
Two distinct concerns here, but they interact in subtle ways:

1. Body size limiting: http.MaxBytesReader wraps the body and returns an error after N bytes.
   But there's a gotcha — if you just set r.Body = http.MaxBytesReader(...), downstream
   handlers that check the error type need to handle *http.MaxBytesError specifically.
   Also, MaxBytesReader was improved in Go 1.19 to automatically send 413 status.

2. Timeout: http.TimeoutHandler is built-in but has issues — it uses a buffered ResponseWriter,
   which breaks streaming, SSE, flushing, and hijacking. For more control, we use
   context.WithTimeout on the request context.

Gotchas to cover:
- MaxBytesReader must be set BEFORE the body is read. If middleware order is wrong,
  JSON decoding happens first and the limit is useless.
- context.WithTimeout creates a goroutine for the timer. We must defer cancel() to avoid
  a leak. But the handler goroutine doesn't magically stop — the handler must check
  r.Context().Done() or the timeout just causes the client to get an error while the
  handler keeps running.
- http.TimeoutHandler writes "timeout" as the body — not JSON, which breaks API clients.
- When both are combined: a slow upload could hit either limit. The timeout should be
  generous enough for the allowed body size at expected bandwidth.
- We should also set ReadHeaderTimeout on the server itself to prevent slowloris.

I'll write both as composable middleware and show the interaction.
</think>

Here is middleware for body size limiting and per-request timeouts with all the subtle gotchas addressed:

```go
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"time"
)

// ---------- Body size limit middleware ----------

func MaxBodySize(maxBytes int64) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Must wrap BEFORE any downstream reads the body.
			r.Body = http.MaxBytesReader(w, r.Body, maxBytes)
			next.ServeHTTP(w, r)
		})
	}
}

// ---------- Timeout middleware ----------

// RequestTimeout cancels the request context after the duration.
// Unlike http.TimeoutHandler, this does NOT buffer the response,
// so streaming and flushing still work.
func RequestTimeout(d time.Duration) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ctx, cancel := context.WithTimeout(r.Context(), d)
			defer cancel()

			// Replace request with timeout context.
			r = r.WithContext(ctx)

			// Channel signals handler completion.
			done := make(chan struct{})
			go func() {
				next.ServeHTTP(w, r)
				close(done)
			}()

			select {
			case <-done:
				// Handler finished normally.
			case <-ctx.Done():
				// Timeout fired before handler finished.
				// Gotcha: the handler goroutine is still running!
				// We can only write an error if the handler hasn't
				// already started writing.
				if errors.Is(ctx.Err(), context.DeadlineExceeded) {
					writeJSON(w, http.StatusGatewayTimeout,
						map[string]string{"error": "request timed out"})
				}
				// Wait for handler to observe cancellation and exit.
				<-done
			}
		})
	}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

// ---------- Application handler ----------

func uploadHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}

	var payload map[string]any
	err := json.NewDecoder(r.Body).Decode(&payload)
	if err != nil {
		// Check if MaxBytesReader triggered.
		var maxBytesErr *http.MaxBytesError
		if errors.As(err, &maxBytesErr) {
			writeJSON(w, http.StatusRequestEntityTooLarge,
				map[string]string{"error": fmt.Sprintf("body exceeds %d bytes", maxBytesErr.Limit)})
			return
		}
		writeJSON(w, http.StatusBadRequest,
			map[string]string{"error": err.Error()})
		return
	}

	// Simulate slow processing — check context for cancellation.
	select {
	case <-time.After(2 * time.Second):
		writeJSON(w, http.StatusOK, payload)
	case <-r.Context().Done():
		// Timeout or client disconnect — stop work immediately.
		log.Println("handler cancelled:", r.Context().Err())
		return
	}
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/upload", uploadHandler)

	// Chain: timeout wraps body limit wraps handler.
	// Order matters — timeout is outermost so it covers body reading too.
	handler := RequestTimeout(5 * time.Second)(
		MaxBodySize(1 << 20)( // 1 MB
			mux,
		),
	)

	srv := &http.Server{
		Addr:              ":8080",
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second, // Prevents slowloris
	}
	log.Fatal(srv.ListenAndServe())
}
```

Gotchas addressed in the code:

1. **`MaxBytesReader` must wrap the body before any read** — if your JSON decoder runs first, the limit is bypassed.
2. **`http.TimeoutHandler` buffers the entire response**, breaking streaming, SSE, and WebSocket upgrades. The custom timeout middleware here avoids buffering.
3. **The handler goroutine does not stop when the timeout fires** — it must cooperatively check `r.Context().Done()`. The `<-done` at the end prevents goroutine leaks.
4. **`*http.MaxBytesError`** (Go 1.19+) lets you distinguish "body too large" from other read errors via `errors.As`.
5. **`ReadHeaderTimeout`** on the server prevents slowloris attacks that send headers very slowly — a concern separate from body/handler timeouts.
6. **Middleware ordering**: timeout must be outermost so it covers the time spent reading the body, not just handler execution.'''),

    ("go_deep/http_client_pool_transport", r'''How should I configure an HTTP client in Go with connection pooling, custom timeouts, and a reusable transport for high-throughput microservice communication?''', r'''<think>
The default http.DefaultClient and http.DefaultTransport in Go are usable but not tuned
for high-throughput service-to-service calls. Problems with defaults:
- DefaultTransport has MaxIdleConns=100 total and MaxIdleConnsPerHost=2. If you're talking
  to one backend at high concurrency, you'll constantly close and reopen connections.
- No per-request timeout on DefaultClient — a hanging backend blocks the goroutine forever.
- No explicit TLS handshake timeout or response header timeout.

Key parameters to tune:
- MaxIdleConnsPerHost: should match your expected concurrency to that host.
- MaxConnsPerHost (Go 1.11+): hard cap on total connections to a host (idle + active).
- IdleConnTimeout: how long idle connections sit in the pool before closing.
- TLSHandshakeTimeout, ResponseHeaderTimeout: prevent slow backends from stalling.
- DisableKeepAlives: never do this for high-throughput — kills connection reuse.
- Client.Timeout: overall deadline including body read. But for streaming responses,
  you want per-request context timeouts instead.

Important: create ONE client/transport and reuse it across goroutines. http.Transport is
safe for concurrent use and manages its own pool. Creating a new transport per request
defeats connection pooling entirely.

I should also show how to add retry logic with exponential backoff, since transient
failures are common in microservice architectures. But the user asked specifically about
pooling and transport, so I'll keep retries brief.

One more subtlety: if you're doing HTTPS and the server rotates certificates, the
connection pool might hold stale TLS sessions. IdleConnTimeout handles this naturally
for most cases.
</think>

Here is a production-tuned HTTP client with connection pooling:

```go
package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"sync"
	"time"
)

// NewServiceClient builds a reusable HTTP client tuned for
// high-throughput communication with a specific backend.
func NewServiceClient(baseURL string, maxConns int) *ServiceClient {
	transport := &http.Transport{
		// Connection pooling
		MaxIdleConns:        maxConns,
		MaxIdleConnsPerHost: maxConns, // Match per-host to total if single backend
		MaxConnsPerHost:     maxConns, // Hard cap prevents connection storms
		IdleConnTimeout:     90 * time.Second,

		// Dialer settings
		DialContext: (&net.Dialer{
			Timeout:   5 * time.Second,  // TCP connect timeout
			KeepAlive: 30 * time.Second, // TCP keepalive interval
		}).DialContext,

		// TLS
		TLSHandshakeTimeout: 5 * time.Second,
		TLSClientConfig: &tls.Config{
			MinVersion: tls.VersionTLS12,
		},

		// Response
		ResponseHeaderTimeout: 10 * time.Second, // Time to first response byte
		ExpectContinueTimeout: 1 * time.Second,

		// Enable HTTP/2 (default when using TLS)
		ForceAttemptHTTP2: true,
	}

	client := &http.Client{
		Transport: transport,
		// Do NOT set Client.Timeout here for streaming responses.
		// Use per-request context deadlines instead.
	}

	return &ServiceClient{
		client:  client,
		baseURL: baseURL,
	}
}

type ServiceClient struct {
	client  *http.Client
	baseURL string
}

// Get performs a GET with a per-request timeout.
func (sc *ServiceClient) Get(ctx context.Context, path string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, sc.baseURL+path, nil)
	if err != nil {
		return nil, fmt.Errorf("build request: %w", err)
	}

	resp, err := sc.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("do request: %w", err)
	}
	defer resp.Body.Close()

	// Limit response read to prevent OOM from misbehaving backends.
	body, err := io.ReadAll(io.LimitReader(resp.Body, 10<<20)) // 10 MB
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("status %d: %s", resp.StatusCode, body)
	}

	return body, nil
}

// Close drains idle connections. Call on shutdown.
func (sc *ServiceClient) Close() {
	sc.client.CloseIdleConnections()
}

// ---------- Demo: concurrent requests ----------

func main() {
	client := NewServiceClient("https://httpbin.org", 50)
	defer client.Close()

	var wg sync.WaitGroup
	results := make(chan string, 20)

	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			body, err := client.Get(context.Background(), "/get")
			if err != nil {
				results <- fmt.Sprintf("req %d: error: %v", i, err)
				return
			}
			var data map[string]any
			json.Unmarshal(body, &data)
			results <- fmt.Sprintf("req %d: origin=%v", i, data["origin"])
		}(i)
	}

	go func() {
		wg.Wait()
		close(results)
	}()

	for r := range results {
		log.Println(r)
	}
}
```

Critical tuning points:

| Parameter | Default | Recommended | Why |
|---|---|---|---|
| `MaxIdleConnsPerHost` | 2 | Match your concurrency | Default of 2 causes constant TCP churn |
| `MaxConnsPerHost` | 0 (unlimited) | Set a cap | Prevents connection storms during spikes |
| `IdleConnTimeout` | 90s | 90s is fine | Too short wastes connections, too long wastes FDs |
| `ResponseHeaderTimeout` | 0 (none) | 10-30s | Prevents hanging on a backend that accepts but never responds |
| `Client.Timeout` | 0 (none) | Avoid for streaming | Use per-request `context.WithTimeout` instead |

**Key rule**: create one `*http.Client` with one `*http.Transport` and share it across all goroutines. Both are concurrency-safe and manage the pool internally.'''),

    ("go_deep/reverse_proxy_lb", r'''How do I build a reverse proxy in Go that load-balances across multiple backends using round-robin, with health checking to skip unhealthy backends?''', r'''<think>
Go's net/http/httputil.ReverseProxy does most of the heavy lifting. The key hook is the
Director function (or the newer Rewrite function in Go 1.20+) that modifies the outbound
request to point at the chosen backend.

For round-robin with health checks, I need:
1. A list of backends with their URLs and health status.
2. An atomic counter for round-robin (or mutex-protected index).
3. A health check goroutine that periodically pings each backend.
4. The next() function skips unhealthy backends, falling back to 503 if all are down.

Design decisions:
- Use atomic.AddUint64 for the round-robin counter — lock-free and safe for concurrent use.
- Health checks run on a ticker in a background goroutine. Each check does a GET to
  a /health endpoint with a short timeout.
- Use sync.RWMutex on the alive status so health checks (write) don't block request
  routing (read) excessively.
- httputil.ReverseProxy.ErrorHandler lets us customize the error response when a backend
  fails mid-request.
- ModifyResponse can inject headers like X-Backend to indicate which backend served.

Subtle issues:
- If a backend fails mid-request (after Director chose it), the proxy returns 502.
  We could retry on the next backend, but that's only safe for idempotent requests.
- The round-robin counter will wrap around for uint64, but that's fine — we mod by len.
- Health check should use a separate http.Client with aggressive timeouts, not the
  proxy's transport.

I'll use the Director approach for compatibility with pre-1.20 Go.
</think>

Here is a reverse proxy with round-robin load balancing and health checks:

```go
package main

import (
	"context"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"sync"
	"sync/atomic"
	"time"
)

type Backend struct {
	URL   *url.URL
	mu    sync.RWMutex
	alive bool
}

func (b *Backend) IsAlive() bool {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return b.alive
}

func (b *Backend) SetAlive(alive bool) {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.alive != alive {
		log.Printf("backend %s alive=%v", b.URL, alive)
	}
	b.alive = alive
}

type LoadBalancer struct {
	backends []*Backend
	current  uint64
}

// Next picks the next alive backend using round-robin.
// Returns nil if all backends are down.
func (lb *LoadBalancer) Next() *Backend {
	n := len(lb.backends)
	start := int(atomic.AddUint64(&lb.current, 1))

	for i := 0; i < n; i++ {
		idx := (start + i) % n
		if lb.backends[idx].IsAlive() {
			return lb.backends[idx]
		}
	}
	return nil
}

// HealthCheck pings each backend periodically.
func (lb *LoadBalancer) HealthCheck(ctx context.Context, interval time.Duration) {
	client := &http.Client{Timeout: 2 * time.Second}

	check := func() {
		for _, b := range lb.backends {
			req, _ := http.NewRequestWithContext(ctx, http.MethodGet,
				b.URL.String()+"/health", nil)
			resp, err := client.Do(req)
			if err != nil {
				b.SetAlive(false)
				continue
			}
			resp.Body.Close()
			b.SetAlive(resp.StatusCode < 500)
		}
	}

	check() // Initial check
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			check()
		case <-ctx.Done():
			return
		}
	}
}

func main() {
	backendURLs := []string{
		"http://localhost:8081",
		"http://localhost:8082",
		"http://localhost:8083",
	}

	var backends []*Backend
	for _, rawURL := range backendURLs {
		u, err := url.Parse(rawURL)
		if err != nil {
			log.Fatalf("bad backend URL %s: %v", rawURL, err)
		}
		backends = append(backends, &Backend{URL: u, alive: true})
	}

	lb := &LoadBalancer{backends: backends}

	proxy := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			backend := lb.Next()
			if backend == nil {
				// All backends down — leave request as-is,
				// ErrorHandler will fire on connection failure.
				return
			}
			req.URL.Scheme = backend.URL.Scheme
			req.URL.Host = backend.URL.Host
			req.Host = backend.URL.Host
			req.Header.Set("X-Forwarded-Host", req.Host)
		},
		ModifyResponse: func(resp *http.Response) error {
			resp.Header.Set("X-Proxy", "go-lb")
			return nil
		},
		ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) {
			log.Printf("proxy error: %v", err)
			if netErr, ok := err.(net.Error); ok && netErr.Timeout() {
				http.Error(w, "backend timeout", http.StatusGatewayTimeout)
			} else {
				http.Error(w, "service unavailable", http.StatusServiceUnavailable)
			}
		},
		Transport: &http.Transport{
			MaxIdleConnsPerHost: 50,
			IdleConnTimeout:     90 * time.Second,
			DialContext: (&net.Dialer{
				Timeout: 3 * time.Second,
			}).DialContext,
		},
	}

	// Start background health checks
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go lb.HealthCheck(ctx, 10*time.Second)

	log.Println("load balancer listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", proxy))
}
```

Design rationale:

- **`atomic.AddUint64`** for the counter avoids mutex contention on the hot path — every request goes through `Next()`.
- **Skipping unhealthy backends** in `Next()` scans up to N peers before returning nil (all down).
- **Separate health-check client** with a 2-second timeout prevents a slow backend health endpoint from affecting proxy performance.
- **`ErrorHandler`** distinguishes timeouts (504) from connection failures (503).
- **`X-Forwarded-Host`** header lets backends know the original host — important for routing and logging.'''),

    ("go_deep/websocket_heartbeat", r'''How do I build a WebSocket server in Go with proper ping/pong heartbeat to detect dead connections and avoid resource leaks?''', r'''<think>
WebSocket connections can silently go dead — the TCP connection stays open but the remote
end is gone (crashed, NAT timeout, network change). Without heartbeat, the server holds
goroutines and memory for dead connections forever.

The WebSocket protocol has built-in Ping/Pong control frames for this. The pattern in
gorilla/websocket (or nhooyr.io/websocket):
1. Server sends Ping frames periodically (e.g., every 30s).
2. Client must respond with Pong within a deadline (e.g., 40s).
3. If no Pong arrives, the server closes the connection.

Implementation details with gorilla/websocket:
- SetReadDeadline controls how long we wait for ANY message (including Pong).
- SetPongHandler resets the read deadline each time a Pong arrives.
- We cannot write from multiple goroutines with gorilla — writes must be serialized.
  So the ping loop runs in a separate goroutine and writes pings, while the read loop
  is in another goroutine.
- The write goroutine handles both pings and outgoing messages via a channel.

Key gotcha: gorilla/websocket's WriteMessage is not concurrent-safe. We need either
a mutex or a dedicated write goroutine. The channel approach is cleaner.

Another gotcha: the Pong handler runs inside ReadMessage. So we must be actively reading
for pongs to be processed. A common bug is to only read when expecting data and missing
pongs during idle periods.

I'll use gorilla/websocket since it's the most widely used. The nhooyr.io/websocket
library handles some of this automatically but has a different API.

Let me also handle the upgrade properly and show clean shutdown of per-connection
goroutines.
</think>

Here is a WebSocket server with robust ping/pong heartbeat using `gorilla/websocket`:

```go
package main

import (
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

const (
	pingInterval = 30 * time.Second
	pongWait     = 40 * time.Second // Must be > pingInterval
	writeWait    = 10 * time.Second
	maxMsgSize   = 4096
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin:     func(r *http.Request) bool { return true }, // Restrict in production
}

// Hub tracks all active connections for broadcast.
type Hub struct {
	mu    sync.RWMutex
	conns map[*Client]struct{}
}

func NewHub() *Hub {
	return &Hub{conns: make(map[*Client]struct{})}
}

func (h *Hub) Register(c *Client)   { h.mu.Lock(); h.conns[c] = struct{}{}; h.mu.Unlock() }
func (h *Hub) Unregister(c *Client) { h.mu.Lock(); delete(h.conns, c); h.mu.Unlock() }

func (h *Hub) Broadcast(msg []byte) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	for c := range h.conns {
		select {
		case c.send <- msg:
		default:
			// Client too slow, drop message.
			log.Printf("dropping message for slow client %s", c.id)
		}
	}
}

type Client struct {
	id   string
	hub  *Hub
	conn *websocket.Conn
	send chan []byte
}

// readPump reads messages and keeps the Pong handler active.
// Runs in its own goroutine per connection.
func (c *Client) readPump() {
	defer func() {
		c.hub.Unregister(c)
		c.conn.Close()
		log.Printf("client %s disconnected", c.id)
	}()

	c.conn.SetReadLimit(maxMsgSize)
	c.conn.SetReadDeadline(time.Now().Add(pongWait))

	// Pong handler resets the read deadline, proving the client is alive.
	c.conn.SetPongHandler(func(appData string) error {
		c.conn.SetReadDeadline(time.Now().Add(pongWait))
		return nil
	})

	for {
		_, message, err := c.conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err,
				websocket.CloseGoingAway, websocket.CloseNormalClosure) {
				log.Printf("client %s read error: %v", c.id, err)
			}
			return
		}
		log.Printf("client %s: %s", c.id, message)
		// Echo to all clients.
		c.hub.Broadcast(message)
	}
}

// writePump sends messages and pings from a single goroutine.
// gorilla/websocket is NOT safe for concurrent writes.
func (c *Client) writePump() {
	ticker := time.NewTicker(pingInterval)
	defer func() {
		ticker.Stop()
		c.conn.Close()
	}()

	for {
		select {
		case msg, ok := <-c.send:
			c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if !ok {
				// Hub closed the channel.
				c.conn.WriteMessage(websocket.CloseMessage, nil)
				return
			}
			if err := c.conn.WriteMessage(websocket.TextMessage, msg); err != nil {
				return
			}

		case <-ticker.C:
			c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				log.Printf("client %s ping failed: %v", c.id, err)
				return
			}
		}
	}
}

func serveWS(hub *Hub, w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("upgrade error: %v", err)
		return
	}

	client := &Client{
		id:   r.RemoteAddr,
		hub:  hub,
		conn: conn,
		send: make(chan []byte, 64),
	}

	hub.Register(client)
	log.Printf("client %s connected", client.id)

	// Both pumps close the connection on exit, which unblocks the other.
	go client.writePump()
	go client.readPump()
}

func main() {
	hub := NewHub()

	http.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		serveWS(hub, w, r)
	})
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, "index.html")
	})

	log.Println("WebSocket server on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
```

Why the heartbeat pattern works this way:

1. **Server sends Pings, client auto-replies with Pongs** — the WebSocket spec requires this, and browsers/gorilla clients handle it automatically.
2. **`SetReadDeadline(now + pongWait)`** is the actual dead-connection detector. If no Pong (or any message) arrives before the deadline, `ReadMessage` returns an error and the read pump exits.
3. **`pongWait > pingInterval`** is required — otherwise the deadline expires before the next ping even goes out.
4. **Dedicated write goroutine** serializes all writes (messages + pings) because gorilla's `WriteMessage` is not concurrent-safe.
5. **Both pumps close `conn`** on exit, which causes the other pump's blocked read/write to fail and return, preventing goroutine leaks.'''),

    ("go_deep/sse_streaming", r'''How do I implement a Server-Sent Events (SSE) streaming endpoint in Go that supports multiple concurrent clients and proper cleanup?''', r'''<think>
SSE is simpler than WebSocket — it's one-directional (server to client) over plain HTTP.
The protocol is straightforward:
- Set Content-Type to text/event-stream
- Set Cache-Control to no-cache
- Each event is "data: ...\n\n" (double newline terminates an event)
- Named events use "event: name\n" before the data line
- Retry field tells the browser how long to wait before reconnecting
- Last-Event-ID header from client enables resumption

Implementation challenges:
1. Must use http.Flusher to push data immediately — without flushing, Go buffers the
   response and the client sees nothing until the buffer fills or the handler returns.
2. Detecting client disconnect: use r.Context().Done(). When the client closes the
   connection, the request context is cancelled.
3. Multiple clients: need a broker/hub that tracks subscriptions. Each client gets a
   channel; the broker sends events to all channels.
4. Slow clients: if a client's channel is full, we should drop events (not block the
   broker). Buffered channels handle this.
5. http.ResponseController (Go 1.20+) can also be used for flushing, but the Flusher
   interface is more widely compatible.

The pattern is: handler checks for Flusher support, registers with the broker, then
loops reading from its channel and writing SSE-formatted lines with Flush after each.

I need to be careful about headers — once we start writing the SSE stream, we can't
change status codes or headers. Also, some reverse proxies buffer responses; the
X-Accel-Buffering: no header helps with nginx.
</think>

Here is a complete SSE implementation with a broker for multiple clients:

```go
package main

import (
	"fmt"
	"log"
	"net/http"
	"sync"
	"time"
)

// Broker manages SSE client subscriptions.
type Broker struct {
	mu      sync.RWMutex
	clients map[chan string]struct{}
}

func NewBroker() *Broker {
	return &Broker{clients: make(map[chan string]struct{})}
}

func (b *Broker) Subscribe() chan string {
	ch := make(chan string, 16) // Buffered to tolerate slow clients
	b.mu.Lock()
	b.clients[ch] = struct{}{}
	b.mu.Unlock()
	log.Printf("client subscribed (%d total)", b.Count())
	return ch
}

func (b *Broker) Unsubscribe(ch chan string) {
	b.mu.Lock()
	delete(b.clients, ch)
	close(ch)
	b.mu.Unlock()
	log.Printf("client unsubscribed (%d total)", b.Count())
}

func (b *Broker) Publish(event string) {
	b.mu.RLock()
	defer b.mu.RUnlock()
	for ch := range b.clients {
		select {
		case ch <- event:
		default:
			// Client too slow — drop event to avoid blocking.
			log.Println("dropped event for slow client")
		}
	}
}

func (b *Broker) Count() int {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return len(b.clients)
}

// SSEHandler streams events to a single client.
func SSEHandler(broker *Broker) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// Must support flushing for SSE to work.
		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "streaming not supported", http.StatusInternalServerError)
			return
		}

		// SSE headers — must be set before first write.
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("Connection", "keep-alive")
		w.Header().Set("X-Accel-Buffering", "no") // Disable nginx buffering

		// Tell browser to retry after 3 seconds on disconnect.
		fmt.Fprintf(w, "retry: 3000\n\n")
		flusher.Flush()

		ch := broker.Subscribe()
		defer broker.Unsubscribe(ch)

		// Stream until client disconnects.
		for {
			select {
			case event, ok := <-ch:
				if !ok {
					return // Channel closed, broker shutting down.
				}
				// SSE format: "data: ...\n\n"
				// Multi-line data needs "data: " prefix on each line.
				fmt.Fprintf(w, "data: %s\n\n", event)
				flusher.Flush()

			case <-r.Context().Done():
				// Client disconnected.
				return
			}
		}
	}
}

func main() {
	broker := NewBroker()

	// Background: publish events every 2 seconds.
	go func() {
		i := 0
		for {
			time.Sleep(2 * time.Second)
			i++
			msg := fmt.Sprintf(`{"seq":%d,"time":"%s","clients":%d}`,
				i, time.Now().Format(time.RFC3339), broker.Count())
			broker.Publish(msg)
		}
	}()

	http.HandleFunc("/events", SSEHandler(broker))

	// Simple test page.
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		fmt.Fprint(w, `<!DOCTYPE html>
<html><body>
<h2>SSE Demo</h2>
<div id="events"></div>
<script>
const es = new EventSource("/events");
es.onmessage = (e) => {
    const div = document.getElementById("events");
    div.innerHTML = e.data + "<br>" + div.innerHTML;
};
es.onerror = () => console.log("reconnecting...");
</script>
</body></html>`)
	})

	log.Println("SSE server on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
```

Key points for production SSE:

1. **`http.Flusher`** is essential — without `Flush()` after each event, the response buffers and the client sees nothing.
2. **Buffered subscription channels** (`make(chan string, 16)`) prevent a slow client from blocking the broker's publish loop.
3. **`r.Context().Done()`** fires when the client disconnects, letting the handler clean up immediately.
4. **`retry: 3000\n\n`** tells the browser to automatically reconnect after 3 seconds — SSE has built-in reconnection, unlike WebSocket.
5. **`X-Accel-Buffering: no`** disables nginx response buffering, which otherwise kills SSE.
6. **`Unsubscribe` closes the channel** to unblock the handler if it is waiting on `<-ch` when the broker removes it.'''),

    ("go_deep/http2_server_push", r'''How does HTTP/2 Server Push work in Go, what are the practical patterns, and why has it fallen out of favor?''', r'''<think>
HTTP/2 Server Push allows the server to proactively send resources (CSS, JS, images)
before the browser requests them. In Go, this is exposed via http.Pusher interface on
the ResponseWriter.

The API in Go:
  if pusher, ok := w.(http.Pusher); ok {
      pusher.Push("/style.css", nil)
  }

This tells the HTTP/2 layer to initiate a PUSH_PROMISE frame for /style.css. The browser
receives the pushed resource and puts it in its cache, so when it parses the HTML and
sees <link href="/style.css">, it already has it.

However, Server Push has significant problems and is effectively deprecated:
1. Chrome removed support in Chrome 106 (2022). No other browser actively supports it.
2. The server doesn't know what the client already has cached. You end up pushing
   resources the client already has, wasting bandwidth.
3. Cache Digests (RFC draft) was supposed to solve this but was never standardized.
4. Service Workers and preload hints (<link rel="preload">) provide similar benefits
   without the complexity.
5. 103 Early Hints is the modern replacement — it sends Link headers before the response.

So this is mostly educational now. But Go still supports it, and the API is instructive
for understanding HTTP/2 internals. I should show the pattern but also explain the
modern alternative (103 Early Hints, which Go supports since 1.20).

Let me show both the push pattern and the Early Hints alternative.
</think>

Here is HTTP/2 Server Push in Go, plus the modern alternative:

```go
package main

import (
	"fmt"
	"log"
	"net/http"
)

func indexHandler(w http.ResponseWriter, r *http.Request) {
	// ---------- HTTP/2 Server Push (legacy) ----------
	// Only works over HTTP/2 TLS connections.
	if pusher, ok := w.(http.Pusher); ok {
		// Push CSS and JS before the browser even parses the HTML.
		resources := []string{"/static/style.css", "/static/app.js"}
		for _, res := range resources {
			if err := pusher.Push(res, nil); err != nil {
				log.Printf("push %s failed: %v", res, err)
			}
		}
	}

	// ---------- 103 Early Hints (modern, Go 1.20+) ----------
	// Works with HTTP/1.1 and HTTP/2, supported by modern browsers.
	w.Header().Add("Link", `</static/style.css>; rel=preload; as=style`)
	w.Header().Add("Link", `</static/app.js>; rel=preload; as=script`)
	w.WriteHeader(http.StatusEarlyHints) // 103

	// Now send the actual response.
	w.Header().Set("Content-Type", "text/html")
	fmt.Fprint(w, `<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="/static/style.css">
    <script src="/static/app.js" defer></script>
</head>
<body>
    <h1>HTTP/2 Push + 103 Early Hints Demo</h1>
</body>
</html>`)
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/", indexHandler)
	mux.Handle("/static/", http.StripPrefix("/static/",
		http.FileServer(http.Dir("./static"))))

	// HTTP/2 Server Push requires TLS.
	// Generate self-signed certs for testing:
	//   openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem \
	//     -days 365 -nodes -subj "/CN=localhost"
	log.Println("HTTPS server on :8443")
	log.Fatal(http.ListenAndServeTLS(":8443", "cert.pem", "key.pem", mux))
}
```

Why Server Push failed and what replaced it:

| Aspect | Server Push | 103 Early Hints |
|---|---|---|
| Browser support | Removed from Chrome 106+ | Supported in Chrome 103+, Firefox |
| Protocol | HTTP/2 only | HTTP/1.1 and HTTP/2 |
| Caching issue | Pushes even if client has it cached | Hints only; browser decides |
| Server complexity | Must track push state | Just send Link headers |
| Go API | `http.Pusher` interface | `w.WriteHeader(103)` |

**Use `103 Early Hints` for new code.** Server Push is shown here for educational purposes and legacy system maintenance only.'''),

    ("go_deep/mtls_setup", r'''How do I set up mutual TLS (mTLS) authentication in Go where both server and client present certificates and verify each other?''', r'''<think>
mTLS means both sides of the connection authenticate via certificates. Normal TLS only
has the client verify the server's certificate. With mTLS, the server also requires the
client to present a valid certificate signed by a trusted CA.

The Go setup requires:
1. A CA certificate (or pool) that both sides trust.
2. Server: tls.Config with ClientAuth set to RequireAndVerifyClientCert, and ClientCAs
   set to the CA pool.
3. Client: tls.Config with Certificates containing the client cert+key, and RootCAs
   set to the CA pool for verifying the server.

Generating test certs (all with the same CA for simplicity):
- CA key + cert (self-signed)
- Server key + cert (signed by CA, with SAN for localhost)
- Client key + cert (signed by CA)

In production, you'd use a real PKI. For Go, the key insight is that tls.Config is where
all the policy lives.

ClientAuth options in Go:
- NoClientCert (default) — standard TLS
- RequestClientCert — ask but don't verify
- RequireAnyClientCert — require cert but don't verify chain
- VerifyClientCertIfGiven — verify if presented
- RequireAndVerifyClientCert — full mTLS

I should show the full flow: CA setup, server config, client config, and extracting
the client identity from the verified cert in the handler.

One gotcha: when loading the CA cert for ClientCAs/RootCAs, you use x509.CertPool, not
tls.Certificate. The tls.Certificate is for YOUR OWN cert+key pair.

Another gotcha: the server cert must have a Subject Alternative Name (SAN) matching the
hostname. Common Name alone is deprecated and Go's TLS library rejects it since Go 1.15.
</think>

Here is a complete mTLS setup with server, client, and certificate verification:

```go
package main

import (
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
)

// ---------- Server ----------

func startServer() {
	// Load CA cert to verify client certificates.
	caCert, err := os.ReadFile("ca-cert.pem")
	if err != nil {
		log.Fatal("load CA cert:", err)
	}
	caPool := x509.NewCertPool()
	if !caPool.AppendCertsFromPEM(caCert) {
		log.Fatal("failed to parse CA cert")
	}

	// Load server's own certificate and private key.
	serverCert, err := tls.LoadX509KeyPair("server-cert.pem", "server-key.pem")
	if err != nil {
		log.Fatal("load server cert:", err)
	}

	tlsConfig := &tls.Config{
		Certificates: []tls.Certificate{serverCert},
		ClientCAs:    caPool,
		ClientAuth:   tls.RequireAndVerifyClientCert, // Full mTLS
		MinVersion:   tls.VersionTLS13,
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		// Extract verified client identity.
		if len(r.TLS.VerifiedChains) > 0 && len(r.TLS.VerifiedChains[0]) > 0 {
			clientCert := r.TLS.VerifiedChains[0][0]
			fmt.Fprintf(w, "Hello %s (org: %v)\n",
				clientCert.Subject.CommonName,
				clientCert.Subject.Organization)
		} else {
			fmt.Fprintln(w, "no client certificate")
		}
	})

	srv := &http.Server{
		Addr:      ":8443",
		Handler:   mux,
		TLSConfig: tlsConfig,
	}

	log.Println("mTLS server on :8443")
	// Empty strings because certs are in TLSConfig already.
	log.Fatal(srv.ListenAndServeTLS("", ""))
}

// ---------- Client ----------

func startClient() {
	// Load CA cert to verify server certificate.
	caCert, err := os.ReadFile("ca-cert.pem")
	if err != nil {
		log.Fatal("load CA cert:", err)
	}
	caPool := x509.NewCertPool()
	if !caPool.AppendCertsFromPEM(caCert) {
		log.Fatal("failed to parse CA cert")
	}

	// Load client's own certificate and private key.
	clientCert, err := tls.LoadX509KeyPair("client-cert.pem", "client-key.pem")
	if err != nil {
		log.Fatal("load client cert:", err)
	}

	tlsConfig := &tls.Config{
		Certificates: []tls.Certificate{clientCert},
		RootCAs:      caPool,
		MinVersion:   tls.VersionTLS13,
	}

	client := &http.Client{
		Transport: &http.Transport{
			TLSClientConfig: tlsConfig,
		},
	}

	resp, err := client.Get("https://localhost:8443/")
	if err != nil {
		log.Fatal("request failed:", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("response: %s", body)
}

func main() {
	if len(os.Args) < 2 {
		log.Fatal("usage: go run main.go [server|client]")
	}

	switch os.Args[1] {
	case "server":
		startServer()
	case "client":
		startClient()
	default:
		log.Fatalf("unknown mode: %s", os.Args[1])
	}
}
```

Generate test certificates with this script:

```bash
#!/bin/bash
# Generate CA
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -keyout ca-key.pem -out ca-cert.pem -days 365 -nodes \
  -subj "/CN=Test CA/O=Test"

# Generate server cert (SAN is mandatory since Go 1.15)
openssl req -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -keyout server-key.pem -out server.csr -nodes \
  -subj "/CN=localhost/O=Server"
openssl x509 -req -in server.csr -CA ca-cert.pem -CAkey ca-key.pem \
  -CAcreateserial -out server-cert.pem -days 365 \
  -extfile <(echo "subjectAltName=DNS:localhost,IP:127.0.0.1")

# Generate client cert
openssl req -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -keyout client-key.pem -out client.csr -nodes \
  -subj "/CN=my-service/O=Client"
openssl x509 -req -in client.csr -CA ca-cert.pem -CAkey ca-key.pem \
  -CAcreateserial -out client-cert.pem -days 365

rm -f *.csr *.srl
```

Key points:

- **`ClientCAs`** (server) vs **`RootCAs`** (client) — different pools for different roles. ClientCAs verifies incoming client certs; RootCAs verifies the server you connect to.
- **`RequireAndVerifyClientCert`** is the strictest mode — connection fails if the client has no cert or an untrusted cert.
- **`r.TLS.VerifiedChains`** gives you the validated certificate chain so you can extract the client identity (CN, organization, serial) for authorization decisions.
- **SAN is mandatory** — Go rejects certificates that rely only on Common Name since Go 1.15.
- **TLS 1.3 minimum** — no reason to support older versions in new code.'''),

    ("go_deep/grpc_unary_interceptor", r'''How do I build a gRPC unary service in Go with server interceptors for logging, authentication, and recovery?''', r'''<think>
gRPC in Go uses google.golang.org/grpc. Interceptors are the gRPC equivalent of HTTP
middleware. There are four types:
- Unary server interceptor: wraps each unary (request-response) RPC.
- Stream server interceptor: wraps each streaming RPC.
- Unary client interceptor: wraps outgoing unary calls.
- Stream client interceptor: wraps outgoing stream calls.

For unary server interceptors, the signature is:
  func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error)

To chain multiple interceptors, use grpc.ChainUnaryInterceptor() (Go gRPC 1.28+).
Before that, you had to manually nest them.

I need to show:
1. A proto definition (or at least describe it — I'll show the generated interface).
2. The service implementation.
3. Three interceptors: logging, auth (metadata-based), and recovery (panic handler).
4. Wiring them together with ChainUnaryInterceptor.

For auth, gRPC uses metadata (similar to HTTP headers). The client sends a token via
metadata, and the auth interceptor extracts and validates it.

For recovery, catching panics in gRPC handlers is important because a panic in one
handler crashes the entire server. The recovery interceptor wraps the handler in
defer/recover and returns codes.Internal.

Ordering matters: recovery should be outermost (to catch panics in other interceptors),
then logging, then auth.

I'll write a complete example assuming a simple Greeter service proto. I won't include
the proto file itself but will show the generated interface and implementation.
</think>

Here is a gRPC unary service with chained interceptors:

```go
package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"runtime/debug"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"

	pb "yourmodule/proto/greeter" // Generated from .proto file
)

// ---------- Service implementation ----------

type greeterServer struct {
	pb.UnimplementedGreeterServer
}

func (s *greeterServer) SayHello(ctx context.Context, req *pb.HelloRequest) (*pb.HelloReply, error) {
	if req.GetName() == "" {
		return nil, status.Error(codes.InvalidArgument, "name is required")
	}
	return &pb.HelloReply{
		Message: fmt.Sprintf("Hello, %s!", req.GetName()),
	}, nil
}

// ---------- Interceptors ----------

// RecoveryInterceptor catches panics and returns Internal error.
// Must be outermost to catch panics in other interceptors.
func RecoveryInterceptor(
	ctx context.Context,
	req any,
	info *grpc.UnaryServerInfo,
	handler grpc.UnaryHandler,
) (resp any, err error) {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("PANIC in %s: %v\n%s", info.FullMethod, r, debug.Stack())
			err = status.Errorf(codes.Internal, "internal server error")
		}
	}()
	return handler(ctx, req)
}

// LoggingInterceptor logs the method, duration, and status code.
func LoggingInterceptor(
	ctx context.Context,
	req any,
	info *grpc.UnaryServerInfo,
	handler grpc.UnaryHandler,
) (any, error) {
	start := time.Now()
	resp, err := handler(ctx, req)
	duration := time.Since(start)

	code := codes.OK
	if err != nil {
		code = status.Code(err)
	}

	log.Printf("grpc %s | %s | %v | %v", info.FullMethod, code, duration, err)
	return resp, err
}

// AuthInterceptor validates a bearer token from gRPC metadata.
func AuthInterceptor(
	ctx context.Context,
	req any,
	info *grpc.UnaryServerInfo,
	handler grpc.UnaryHandler,
) (any, error) {
	// Skip auth for health checks or reflection.
	if info.FullMethod == "/grpc.health.v1.Health/Check" {
		return handler(ctx, req)
	}

	md, ok := metadata.FromIncomingContext(ctx)
	if !ok {
		return nil, status.Error(codes.Unauthenticated, "missing metadata")
	}

	tokens := md.Get("authorization")
	if len(tokens) == 0 {
		return nil, status.Error(codes.Unauthenticated, "missing authorization token")
	}

	token := tokens[0]
	// In production, validate JWT or call an auth service.
	if token != "Bearer valid-token" {
		return nil, status.Error(codes.Unauthenticated, "invalid token")
	}

	// Optionally inject user info into context.
	ctx = context.WithValue(ctx, userIDKey{}, "user-123")
	return handler(ctx, req)
}

type userIDKey struct{}

// ---------- Main ----------

func main() {
	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatalf("listen: %v", err)
	}

	srv := grpc.NewServer(
		// ChainUnaryInterceptor applies in order: first = outermost.
		grpc.ChainUnaryInterceptor(
			RecoveryInterceptor, // Outermost — catches all panics
			LoggingInterceptor,  // Logs everything including auth failures
			AuthInterceptor,     // Innermost — only authed requests reach handler
		),
	)

	pb.RegisterGreeterServer(srv, &greeterServer{})

	log.Printf("gRPC server on %s", lis.Addr())
	if err := srv.Serve(lis); err != nil {
		log.Fatalf("serve: %v", err)
	}
}
```

Corresponding proto file (`greeter.proto`):

```protobuf
syntax = "proto3";
package greeter;
option go_package = "yourmodule/proto/greeter";

service Greeter {
  rpc SayHello (HelloRequest) returns (HelloReply);
}

message HelloRequest {
  string name = 1;
}

message HelloReply {
  string message = 1;
}
```

Interceptor design patterns:

1. **Recovery outermost**: if logging or auth panics, recovery still catches it.
2. **Logging wraps auth**: you see "Unauthenticated" in logs even for rejected requests.
3. **Auth skips certain methods**: health checks and gRPC reflection should not require auth.
4. **`status.Error` and `status.Code`**: always use gRPC status types, not plain errors — clients depend on the code for retry/fallback logic.
5. **`ChainUnaryInterceptor`**: applies interceptors in the order listed. First argument is outermost.'''),

    ("go_deep/grpc_server_streaming_backpressure", r'''How do I implement gRPC server streaming in Go with proper backpressure handling so a slow client does not cause the server to buffer unbounded data?''', r'''<think>
In gRPC server streaming, the server calls stream.Send() repeatedly to push messages
to the client. The question is: what happens when the client reads slowly?

gRPC uses HTTP/2 flow control under the hood. When the client's receive buffer is full,
the HTTP/2 layer applies backpressure — stream.Send() will eventually block when the
send buffer is full. So there IS built-in backpressure.

However, there are subtleties:
1. stream.Send() blocks when the transport buffer is full, but the buffer can be quite
   large before blocking starts (~64KB default window per stream, configurable).
2. If the server generates data faster than the client consumes, memory accumulates in
   the send buffer before backpressure kicks in.
3. If you're generating data from a database cursor or expensive computation, you want
   to pause generation when the client is slow, not just queue up messages.
4. Context cancellation: if the client disconnects, stream.Context().Done() fires.

Strategies for explicit backpressure:
1. Rely on gRPC's built-in flow control (stream.Send blocks) — simplest, works for most
   cases. The server goroutine just slows down naturally.
2. Use a bounded channel between the data producer and the Send loop, with a select on
   context cancellation.
3. For very large streams, implement client-driven pagination: the client sends requests
   in a bidirectional stream, each requesting the next batch.

I should show the built-in flow control approach (most idiomatic) and also the channel
approach for when the data producer is a separate goroutine.

Also important: server-side keepalive settings. If the client is alive but slow, keepalive
pings keep the connection open. If the client is dead, keepalive detects it and cancels
the stream context.
</think>

Here is gRPC server streaming with backpressure awareness:

```go
package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/keepalive"
	"google.golang.org/grpc/status"

	pb "yourmodule/proto/feed"
)

// Proto definition assumed:
// service Feed {
//   rpc Subscribe (SubscribeRequest) returns (stream Event);
// }
// message SubscribeRequest { string topic = 1; }
// message Event { int64 seq = 1; string data = 2; }

type feedServer struct {
	pb.UnimplementedFeedServer
}

// Subscribe demonstrates two backpressure patterns.
func (s *feedServer) Subscribe(req *pb.SubscribeRequest, stream pb.Feed_SubscribeServer) error {
	log.Printf("client subscribed to topic %q", req.GetTopic())

	// Pattern 1: Direct Send with built-in flow control.
	// stream.Send() blocks when the HTTP/2 send window is full.
	// This is the simplest and most correct approach.
	for seq := int64(1); ; seq++ {
		// Check if client disconnected.
		if err := stream.Context().Err(); err != nil {
			log.Printf("client gone: %v", err)
			return status.Error(codes.Canceled, "client disconnected")
		}

		event := &pb.Event{
			Seq:  seq,
			Data: fmt.Sprintf("event %d for topic %s", seq, req.GetTopic()),
		}

		// Send blocks if client is slow — this IS the backpressure.
		if err := stream.Send(event); err != nil {
			return err
		}

		// Simulate event production rate.
		time.Sleep(100 * time.Millisecond)
	}
}

// SubscribeWithProducer demonstrates Pattern 2: decoupled producer
// with a bounded channel for explicit backpressure control.
func (s *feedServer) SubscribeWithProducer(req *pb.SubscribeRequest, stream pb.Feed_SubscribeServer) error {
	ctx := stream.Context()
	events := make(chan *pb.Event, 32) // Bounded buffer

	// Producer goroutine — pauses when channel is full.
	go func() {
		defer close(events)
		for seq := int64(1); ; seq++ {
			event := &pb.Event{
				Seq:  seq,
				Data: fmt.Sprintf("event %d", seq),
			}
			select {
			case events <- event:
				// Enqueued successfully.
			case <-ctx.Done():
				return
			}
			time.Sleep(50 * time.Millisecond) // Production rate
		}
	}()

	// Send loop — drains the channel into the stream.
	for event := range events {
		if err := stream.Send(event); err != nil {
			return err
		}
	}

	return nil
}

func main() {
	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatalf("listen: %v", err)
	}

	srv := grpc.NewServer(
		// Keepalive detects dead clients that stop reading.
		grpc.KeepaliveParams(keepalive.ServerParameters{
			Time:    30 * time.Second, // Ping if no activity
			Timeout: 10 * time.Second, // Close if no pong
		}),
		grpc.KeepaliveEnforcementPolicy(keepalive.EnforcementPolicy{
			MinTime:             10 * time.Second, // Min interval client can ping
			PermitWithoutStream: true,
		}),
		// Limit per-stream receive/send window.
		grpc.InitialWindowSize(64*1024),     // 64 KB per stream
		grpc.InitialConnWindowSize(256*1024), // 256 KB per connection
	)

	pb.RegisterFeedServer(srv, &feedServer{})

	log.Printf("streaming gRPC server on %s", lis.Addr())
	if err := srv.Serve(lis); err != nil {
		log.Fatal(err)
	}
}

// ---------- Client example ----------

func exampleClient() {
	conn, _ := grpc.Dial("localhost:50051", grpc.WithInsecure())
	defer conn.Close()

	client := pb.NewFeedClient(conn)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	stream, err := client.Subscribe(ctx, &pb.SubscribeRequest{Topic: "orders"})
	if err != nil {
		log.Fatal(err)
	}

	for {
		event, err := stream.Recv()
		if err != nil {
			log.Printf("stream ended: %v", err)
			return
		}
		log.Printf("received: seq=%d data=%s", event.Seq, event.Data)

		// Simulate slow consumer.
		time.Sleep(500 * time.Millisecond)
	}
}
```

How backpressure works at each layer:

1. **HTTP/2 flow control** (automatic): each stream has a send window (default 64KB). When full, `Send()` blocks until the client reads and acknowledges data. This prevents unbounded server-side buffering.
2. **Bounded channel** (Pattern 2): decouples the data producer from the network layer. When the channel is full, the producer blocks on `events <-`, pausing expensive work like database queries.
3. **`InitialWindowSize`**: tune the HTTP/2 window to control how much data queues before backpressure engages. Smaller window = earlier backpressure = less memory use.
4. **Keepalive**: detects clients that disconnect without a clean close. Without it, the server could block on `Send()` indefinitely for a dead connection.'''),

    ("go_deep/grpc_bidi_streaming_chat", r'''Show me how to build a gRPC bidirectional streaming chat service in Go where multiple clients can send and receive messages concurrently.''', r'''<think>
Bidirectional streaming in gRPC means both client and server send messages independently
on the same connection. Unlike server streaming, the client can also send messages at any
time — they don't have to alternate.

For a chat service, I need:
1. A proto with a bidirectional streaming RPC.
2. A hub/room that tracks connected clients and broadcasts messages.
3. Server-side: for each client connection, one goroutine reads from stream.Recv() and
   broadcasts, while the Send loop is driven by a per-client channel.
4. Proper cleanup when a client disconnects.

Concurrency model for bidi streaming in Go gRPC:
- stream.Recv() and stream.Send() can be called concurrently from different goroutines.
  This is explicitly documented as safe in the gRPC-Go API.
- But you cannot call stream.Send() from multiple goroutines concurrently. So I need a
  dedicated send loop per client.

The architecture mirrors the WebSocket chat server:
- ChatRoom has a map of connected clients.
- Each client has a send channel.
- When a message arrives via Recv(), broadcast to all other clients' channels.
- The send loop reads from the channel and calls stream.Send().

One tricky part: the RPC handler (Chat method) must not return until the client disconnects.
If it returns, the stream is closed. So the handler blocks on the receive loop and returns
when Recv() fails (client disconnect or error).

The send goroutine runs alongside the handler. When the handler returns, the stream
is closed, which causes any pending Send to fail, and the send goroutine exits.

I should also handle the case where a client sends a "join" message to set their username,
then subsequent messages are chat messages.
</think>

Here is a bidirectional streaming chat service:

```go
package main

import (
	"io"
	"log"
	"net"
	"sync"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	pb "yourmodule/proto/chat"
)

// Proto:
// service Chat {
//   rpc Connect (stream ChatMessage) returns (stream ChatMessage);
// }
// message ChatMessage {
//   string user = 1;
//   string text = 2;
//   enum Type { TEXT = 0; JOIN = 1; LEAVE = 2; }
//   Type type = 3;
// }

// ---------- Chat Room ----------

type Client struct {
	name string
	send chan *pb.ChatMessage
}

type Room struct {
	mu      sync.RWMutex
	clients map[*Client]struct{}
}

func NewRoom() *Room {
	return &Room{clients: make(map[*Client]struct{})}
}

func (r *Room) Join(c *Client) {
	r.mu.Lock()
	r.clients[c] = struct{}{}
	r.mu.Unlock()
	r.Broadcast(&pb.ChatMessage{
		User: "system",
		Text: c.name + " joined the chat",
		Type: pb.ChatMessage_JOIN,
	}, c)
	log.Printf("%s joined (%d online)", c.name, r.Count())
}

func (r *Room) Leave(c *Client) {
	r.mu.Lock()
	delete(r.clients, c)
	close(c.send)
	r.mu.Unlock()
	r.Broadcast(&pb.ChatMessage{
		User: "system",
		Text: c.name + " left the chat",
		Type: pb.ChatMessage_LEAVE,
	}, nil)
	log.Printf("%s left (%d online)", c.name, r.Count())
}

func (r *Room) Broadcast(msg *pb.ChatMessage, exclude *Client) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	for c := range r.clients {
		if c == exclude {
			continue
		}
		select {
		case c.send <- msg:
		default:
			log.Printf("dropping message for slow client %s", c.name)
		}
	}
}

func (r *Room) Count() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return len(r.clients)
}

// ---------- gRPC Service ----------

type chatServer struct {
	pb.UnimplementedChatServer
	room *Room
}

func (s *chatServer) Connect(stream pb.Chat_ConnectServer) error {
	// First message must be a JOIN with the username.
	msg, err := stream.Recv()
	if err != nil {
		return status.Error(codes.InvalidArgument, "expected join message")
	}
	if msg.GetType() != pb.ChatMessage_JOIN || msg.GetUser() == "" {
		return status.Error(codes.InvalidArgument, "first message must be JOIN with user name")
	}

	client := &Client{
		name: msg.GetUser(),
		send: make(chan *pb.ChatMessage, 64),
	}

	s.room.Join(client)
	defer s.room.Leave(client)

	// Send goroutine: reads from client.send and writes to stream.
	// Runs until the channel is closed (on Leave) or stream errors.
	sendErr := make(chan error, 1)
	go func() {
		for msg := range client.send {
			if err := stream.Send(msg); err != nil {
				sendErr <- err
				return
			}
		}
		sendErr <- nil
	}()

	// Receive loop: reads from stream and broadcasts.
	// Blocks here until client disconnects.
	for {
		msg, err := stream.Recv()
		if err == io.EOF {
			break // Client closed their send side.
		}
		if err != nil {
			log.Printf("recv error from %s: %v", client.name, err)
			break
		}

		msg.User = client.name // Server sets user, not client (prevent spoofing).
		msg.Type = pb.ChatMessage_TEXT
		s.room.Broadcast(msg, nil) // Include sender so they see their own message.
	}

	// Wait for send goroutine to finish.
	// Leave() closes client.send, which causes the range loop to exit.
	return <-sendErr
}

func main() {
	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatalf("listen: %v", err)
	}

	srv := grpc.NewServer()
	pb.RegisterChatServer(srv, &chatServer{room: NewRoom()})

	log.Printf("chat server on %s", lis.Addr())
	if err := srv.Serve(lis); err != nil {
		log.Fatal(err)
	}
}
```

Concurrency model:

1. **`stream.Recv()` and `stream.Send()` are safe to call from different goroutines** — this is documented in gRPC-Go. But two concurrent `Send()` calls are NOT safe, hence the dedicated send goroutine.
2. **The RPC handler blocks in the receive loop** — it only returns when the client disconnects. Returning early closes the stream.
3. **`Leave()` closes `client.send`** — this causes the send goroutine's `range` loop to exit cleanly, even if it is blocked waiting for data.
4. **Server sets `msg.User`** — never trust the client to honestly identify itself. The username is locked at JOIN time.
5. **Buffered send channel (64)** absorbs short bursts. If a client falls behind permanently, messages are dropped via the `default` case in `Broadcast`.'''),

    ("go_deep/custom_net_conn_framing", r'''How do I write a custom net.Conn wrapper in Go that adds length-prefix framing for a binary protocol?''', r'''<think>
Length-prefix framing is the most common wire protocol pattern: each message is preceded
by its length (typically 4 bytes big-endian), allowing the receiver to know exactly how
many bytes to read.

The challenge: net.Conn's Read/Write are byte-oriented with no message boundaries. TCP
is a stream protocol — a single Write of 100 bytes might arrive as two Reads of 50 bytes,
or ten Reads of 10 bytes. So we need to:
1. On write: prepend a 4-byte length header before each message.
2. On read: read exactly 4 bytes for the header, then read exactly N bytes for the body.

Implementation approach:
- Wrap net.Conn in a struct that provides ReadMessage() and WriteMessage() methods.
- Use io.ReadFull to ensure we read exactly the required number of bytes.
- Use encoding/binary for big-endian uint32 encoding.
- Add a max message size check to prevent OOM from malformed headers.
- Use a bufio.Reader for efficient reads (avoid syscalls for small reads).

I could implement the net.Conn interface directly, but that's actually a bad idea here.
The standard Read([]byte) interface doesn't map well to message framing because the
caller doesn't know how big the buffer should be. Better to expose a message-oriented
API: ReadMessage() ([]byte, error) and WriteMessage([]byte) error.

However, I can also make it implement io.ReadWriteCloser and net.Conn for compatibility,
forwarding deadline methods etc. Let me show both the message API and the net.Conn wrapper.

I should also handle partial writes — though in practice, Go's net.Conn.Write on TCP
sends all bytes or returns an error, unlike C's write() which can return short.
Actually, the Go docs say Write must return a non-nil error if n < len(p), so we
don't need a write loop, but I'll use bufio.Writer for efficiency.
</think>

Here is a length-prefix framing protocol layer wrapping `net.Conn`:

```go
package main

import (
	"bufio"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"sync"
	"time"
)

const (
	headerSize     = 4             // uint32 big-endian length prefix
	maxMessageSize = 16 * 1024 * 1024 // 16 MB max message
)

var (
	ErrMessageTooLarge = errors.New("message exceeds max size")
	ErrInvalidHeader   = errors.New("invalid message header")
)

// FramedConn wraps a net.Conn with length-prefix framing.
// Each message is: [4-byte big-endian length][payload]
type FramedConn struct {
	conn   net.Conn
	reader *bufio.Reader
	wmu    sync.Mutex // Serialize writes from multiple goroutines
}

func NewFramedConn(conn net.Conn) *FramedConn {
	return &FramedConn{
		conn:   conn,
		reader: bufio.NewReaderSize(conn, 4096),
	}
}

// ReadMessage reads one complete framed message.
// Blocks until a full message is available.
func (fc *FramedConn) ReadMessage() ([]byte, error) {
	// Read the 4-byte length header.
	var header [headerSize]byte
	if _, err := io.ReadFull(fc.reader, header[:]); err != nil {
		return nil, fmt.Errorf("read header: %w", err)
	}

	length := binary.BigEndian.Uint32(header[:])
	if length == 0 {
		return []byte{}, nil // Empty message is valid.
	}
	if length > maxMessageSize {
		return nil, fmt.Errorf("%w: %d bytes", ErrMessageTooLarge, length)
	}

	// Read exactly `length` bytes of payload.
	payload := make([]byte, length)
	if _, err := io.ReadFull(fc.reader, payload); err != nil {
		return nil, fmt.Errorf("read payload (%d bytes): %w", length, err)
	}

	return payload, nil
}

// WriteMessage writes one framed message atomically.
// Safe to call from multiple goroutines.
func (fc *FramedConn) WriteMessage(data []byte) error {
	if len(data) > maxMessageSize {
		return ErrMessageTooLarge
	}

	fc.wmu.Lock()
	defer fc.wmu.Unlock()

	// Write header + payload together to minimize syscalls.
	var header [headerSize]byte
	binary.BigEndian.PutUint32(header[:], uint32(len(data)))

	// Use writev-like behavior: write header then payload.
	if _, err := fc.conn.Write(header[:]); err != nil {
		return fmt.Errorf("write header: %w", err)
	}
	if len(data) > 0 {
		if _, err := fc.conn.Write(data); err != nil {
			return fmt.Errorf("write payload: %w", err)
		}
	}
	return nil
}

// Delegate deadline and close methods to the underlying conn.
func (fc *FramedConn) SetDeadline(t time.Time) error      { return fc.conn.SetDeadline(t) }
func (fc *FramedConn) SetReadDeadline(t time.Time) error   { return fc.conn.SetReadDeadline(t) }
func (fc *FramedConn) SetWriteDeadline(t time.Time) error  { return fc.conn.SetWriteDeadline(t) }
func (fc *FramedConn) Close() error                        { return fc.conn.Close() }
func (fc *FramedConn) RemoteAddr() net.Addr                { return fc.conn.RemoteAddr() }

// ---------- Example: echo server + client ----------

func runServer() {
	ln, err := net.Listen("tcp", ":9000")
	if err != nil {
		log.Fatal(err)
	}
	defer ln.Close()
	log.Println("framed server listening on :9000")

	for {
		conn, err := ln.Accept()
		if err != nil {
			log.Println("accept:", err)
			continue
		}
		go handleClient(NewFramedConn(conn))
	}
}

func handleClient(fc *FramedConn) {
	defer fc.Close()
	log.Printf("client connected: %s", fc.RemoteAddr())

	for {
		msg, err := fc.ReadMessage()
		if err != nil {
			if errors.Is(err, io.EOF) {
				log.Printf("client %s disconnected", fc.RemoteAddr())
			} else {
				log.Printf("read error: %v", err)
			}
			return
		}

		log.Printf("received %d bytes: %s", len(msg), msg)

		// Echo back.
		if err := fc.WriteMessage(msg); err != nil {
			log.Printf("write error: %v", err)
			return
		}
	}
}

func runClient() {
	conn, err := net.Dial("tcp", "localhost:9000")
	if err != nil {
		log.Fatal(err)
	}
	fc := NewFramedConn(conn)
	defer fc.Close()

	messages := []string{
		"hello",
		"this is a framed message",
		"messages can be any binary data",
	}

	for _, msg := range messages {
		if err := fc.WriteMessage([]byte(msg)); err != nil {
			log.Fatal("write:", err)
		}

		reply, err := fc.ReadMessage()
		if err != nil {
			log.Fatal("read:", err)
		}
		fmt.Printf("echo: %s\n", reply)
	}
}

func main() {
	go runServer()
	time.Sleep(100 * time.Millisecond) // Let server start.
	runClient()
}
```

Key design decisions:

1. **`io.ReadFull`** is essential — plain `Read` can return fewer bytes than requested. `ReadFull` loops until exactly N bytes are read or an error occurs.
2. **`bufio.Reader`** avoids one syscall per 4-byte header read. Without it, reading the header is a separate syscall, which is expensive at high message rates.
3. **Write mutex** serializes concurrent writes. Without it, two goroutines' headers and payloads could interleave, corrupting the stream.
4. **Max message size** prevents a malformed header (e.g., `0xFFFFFFFF`) from allocating 4GB of memory.
5. **Not implementing `net.Conn.Read/Write`** directly — the framed protocol has message semantics, not stream semantics. Exposing `Read([]byte)` would be misleading because callers expect stream behavior.'''),

    ("go_deep/tcp_connection_pool", r'''How do I build a TCP connection pool in Go with health checks, idle timeouts, and proper connection lifecycle management?''', r'''<think>
A TCP connection pool is useful for protocols like Redis, memcached, or custom TCP
services where establishing a connection is expensive (TLS handshake, auth, etc.).

Design requirements:
1. Get() returns an idle connection or creates a new one.
2. Put() returns a connection to the pool.
3. Max pool size limits total connections.
4. Idle timeout closes connections that sit unused too long.
5. Health checks verify connections before returning them from Get().
6. Close() drains the pool.

Implementation approach:
- Use a channel as the pool (buffered channel = bounded pool). This gives us thread-safe
  get/put without explicit locking.
- Actually, a channel-based pool has limitations: you can't iterate to expire idle
  connections. Better to use a slice/list with a mutex.
- Each pooled connection tracks its creation time and last-used time.
- On Get(): try to get an idle connection, check if it's healthy, if not discard and try
  again. If no idle connections, create a new one (up to max).
- Use a semaphore (buffered channel or sync.WaitGroup) to limit total connections.

Health check strategy:
- Before returning a connection from Get(), do a non-blocking read. If we get data or
  an error, the connection is stale (server sent something unexpected or closed it).
- Alternatively, set a short read deadline and check for timeout (healthy) vs. other error.
- For TCP specifically, we can also check conn.(*net.TCPConn).SetKeepAlive().

Idle reaping: a background goroutine periodically scans the pool and closes connections
that have been idle too long.

I'll use a mutex + slice approach for flexibility.
</think>

Here is a robust TCP connection pool:

```go
package main

import (
	"errors"
	"fmt"
	"log"
	"net"
	"sync"
	"time"
)

var (
	ErrPoolClosed  = errors.New("pool is closed")
	ErrPoolFull    = errors.New("pool is at max capacity")
	ErrConnUnusable = errors.New("connection is unusable")
)

type pooledConn struct {
	conn     net.Conn
	created  time.Time
	lastUsed time.Time
}

type Pool struct {
	mu          sync.Mutex
	idle        []*pooledConn
	active      int
	maxSize     int
	maxIdle     int
	idleTimeout time.Duration
	maxLifetime time.Duration
	dialFunc    func() (net.Conn, error)
	closed      bool
	done        chan struct{}
}

type PoolConfig struct {
	MaxSize     int           // Total max connections (idle + active)
	MaxIdle     int           // Max idle connections to keep
	IdleTimeout time.Duration // Close idle connections after this duration
	MaxLifetime time.Duration // Close connections older than this
	DialFunc    func() (net.Conn, error)
}

func NewPool(cfg PoolConfig) *Pool {
	if cfg.MaxSize <= 0 {
		cfg.MaxSize = 10
	}
	if cfg.MaxIdle <= 0 {
		cfg.MaxIdle = cfg.MaxSize
	}
	if cfg.IdleTimeout <= 0 {
		cfg.IdleTimeout = 5 * time.Minute
	}
	if cfg.MaxLifetime <= 0 {
		cfg.MaxLifetime = 30 * time.Minute
	}

	p := &Pool{
		maxSize:     cfg.MaxSize,
		maxIdle:     cfg.MaxIdle,
		idleTimeout: cfg.IdleTimeout,
		maxLifetime: cfg.MaxLifetime,
		dialFunc:    cfg.DialFunc,
		done:        make(chan struct{}),
	}

	// Background reaper closes expired idle connections.
	go p.reaper()

	return p
}

// Get returns a healthy connection from the pool, or dials a new one.
func (p *Pool) Get() (net.Conn, error) {
	p.mu.Lock()

	if p.closed {
		p.mu.Unlock()
		return nil, ErrPoolClosed
	}

	// Try to find a healthy idle connection.
	for len(p.idle) > 0 {
		// Take from the back (LIFO — most recently used, likely healthiest).
		pc := p.idle[len(p.idle)-1]
		p.idle = p.idle[:len(p.idle)-1]

		if p.isExpired(pc) {
			p.mu.Unlock()
			pc.conn.Close()
			p.mu.Lock()
			continue
		}

		if !p.isHealthy(pc) {
			p.mu.Unlock()
			pc.conn.Close()
			p.mu.Lock()
			continue
		}

		p.active++
		p.mu.Unlock()
		return pc.conn, nil
	}

	// No idle connections. Create a new one if under limit.
	total := len(p.idle) + p.active
	if total >= p.maxSize {
		p.mu.Unlock()
		return nil, ErrPoolFull
	}

	p.active++
	p.mu.Unlock()

	conn, err := p.dialFunc()
	if err != nil {
		p.mu.Lock()
		p.active--
		p.mu.Unlock()
		return nil, fmt.Errorf("dial: %w", err)
	}

	return conn, nil
}

// Put returns a connection to the pool. Pass err != nil to discard it.
func (p *Pool) Put(conn net.Conn, err error) {
	p.mu.Lock()
	defer p.mu.Unlock()

	p.active--

	if p.closed || err != nil {
		conn.Close()
		return
	}

	if len(p.idle) >= p.maxIdle {
		conn.Close()
		return
	}

	pc := &pooledConn{
		conn:     conn,
		created:  time.Now(), // Approximate; ideally tracked from dial.
		lastUsed: time.Now(),
	}

	p.idle = append(p.idle, pc)
}

// Close drains and shuts down the pool.
func (p *Pool) Close() {
	p.mu.Lock()
	if p.closed {
		p.mu.Unlock()
		return
	}
	p.closed = true
	idle := p.idle
	p.idle = nil
	close(p.done)
	p.mu.Unlock()

	for _, pc := range idle {
		pc.conn.Close()
	}
}

func (p *Pool) isExpired(pc *pooledConn) bool {
	now := time.Now()
	if now.Sub(pc.lastUsed) > p.idleTimeout {
		return true
	}
	if now.Sub(pc.created) > p.maxLifetime {
		return true
	}
	return false
}

// isHealthy does a non-blocking read check.
// If the server closed the connection, we'll get an error.
func (p *Pool) isHealthy(pc *pooledConn) bool {
	pc.conn.SetReadDeadline(time.Now().Add(1 * time.Millisecond))
	one := make([]byte, 1)
	_, err := pc.conn.Read(one)
	pc.conn.SetReadDeadline(time.Time{}) // Clear deadline.

	if err == nil {
		return false // Unexpected data — protocol violation or stale.
	}

	netErr, ok := err.(net.Error)
	if ok && netErr.Timeout() {
		return true // Timeout = no data waiting = healthy.
	}

	return false // EOF or other error = dead connection.
}

func (p *Pool) reaper() {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			p.reapIdle()
		case <-p.done:
			return
		}
	}
}

func (p *Pool) reapIdle() {
	p.mu.Lock()
	var live []*pooledConn
	var expired []*pooledConn

	for _, pc := range p.idle {
		if p.isExpired(pc) {
			expired = append(expired, pc)
		} else {
			live = append(live, pc)
		}
	}
	p.idle = live
	p.mu.Unlock()

	for _, pc := range expired {
		pc.conn.Close()
	}

	if len(expired) > 0 {
		log.Printf("pool: reaped %d expired connections", len(expired))
	}
}

// Stats returns pool statistics.
func (p *Pool) Stats() (idle, active, max int) {
	p.mu.Lock()
	defer p.mu.Unlock()
	return len(p.idle), p.active, p.maxSize
}

// ---------- Usage ----------

func main() {
	pool := NewPool(PoolConfig{
		MaxSize:     20,
		MaxIdle:     5,
		IdleTimeout: 2 * time.Minute,
		MaxLifetime: 10 * time.Minute,
		DialFunc: func() (net.Conn, error) {
			return net.DialTimeout("tcp", "localhost:6379", 3*time.Second)
		},
	})
	defer pool.Close()

	// Use the pool.
	conn, err := pool.Get()
	if err != nil {
		log.Fatal(err)
	}

	// Do work with conn...
	_, writeErr := conn.Write([]byte("PING\r\n"))

	// Always return to pool. Pass the error to discard broken connections.
	pool.Put(conn, writeErr)

	idle, active, max := pool.Stats()
	log.Printf("pool: idle=%d active=%d max=%d", idle, active, max)
}
```

Design rationale:

1. **LIFO order** (take from back of slice): recently used connections are more likely to be healthy. FIFO would return the stalest connection first.
2. **Non-blocking read health check**: if `Read` returns data or EOF, the connection is stale. If it returns a timeout, the connection is alive and idle.
3. **Background reaper**: periodically evicts expired connections instead of checking only on Get(). This prevents the pool from holding dead connections during idle periods.
4. **`Put(conn, err)`**: the caller passes the error from their last operation. If they got a write/read error, the connection is discarded, not returned to the pool.
5. **`maxLifetime`**: even healthy connections are recycled after 30 minutes to handle server-side resource rotation (e.g., load balancer draining).'''),

    ("go_deep/udp_multicast_discovery", r'''How do I implement UDP multicast in Go for service discovery, where services announce themselves and clients discover available instances?''', r'''<think>
UDP multicast allows sending a single packet that is received by all listeners on a
multicast group. This is perfect for service discovery on a LAN — services periodically
announce their presence, and clients listen for announcements.

Key concepts:
1. Multicast group: an IP in the 224.0.0.0-239.255.255.255 range (IPv4).
2. Services join the multicast group and send announcements periodically.
3. Clients join the same group and listen for announcements.
4. Each announcement includes the service name, address, port, and a TTL.

Go's net package supports multicast via:
- net.ListenMulticastUDP(network, ifi, gaddr) — joins a multicast group.
- Or manually: create a UDPConn and use the golang.org/x/net/ipv4 package for
  fine-grained control (JoinGroup, SetMulticastLoopback, etc.).

For simplicity, I'll use net.ListenMulticastUDP for the listener and regular UDP
send to the multicast address for the announcer.

Gotchas:
- Multicast only works on LAN — routers don't forward multicast by default.
- On machines with multiple interfaces, you need to specify which interface to use.
- net.ListenMulticastUDP sets SO_REUSEADDR, allowing multiple listeners on the same port.
- Announcements need a TTL/expiry so clients can detect when a service goes offline.
- The announcement should be idempotent — receiving the same announcement twice is fine.

I'll use a simple JSON announcement format and build both the announcer and the registry
(listener that tracks available services).
</think>

Here is a UDP multicast service discovery system:

```go
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net"
	"os"
	"sync"
	"time"
)

const (
	multicastAddr = "239.1.1.1:9999"
	announceInterval = 5 * time.Second
	serviceTTL       = 15 * time.Second // 3x announce interval
)

// Announcement is the discovery payload.
type Announcement struct {
	Service  string `json:"service"`
	Host     string `json:"host"`
	Port     int    `json:"port"`
	Metadata map[string]string `json:"metadata,omitempty"`
}

// ---------- Announcer (Service side) ----------

type Announcer struct {
	ann  Announcement
	done chan struct{}
}

func NewAnnouncer(ann Announcement) *Announcer {
	return &Announcer{ann: ann, done: make(chan struct{})}
}

func (a *Announcer) Start() error {
	addr, err := net.ResolveUDPAddr("udp4", multicastAddr)
	if err != nil {
		return fmt.Errorf("resolve: %w", err)
	}

	conn, err := net.DialUDP("udp4", nil, addr)
	if err != nil {
		return fmt.Errorf("dial: %w", err)
	}

	payload, err := json.Marshal(a.ann)
	if err != nil {
		conn.Close()
		return fmt.Errorf("marshal: %w", err)
	}

	go func() {
		defer conn.Close()
		ticker := time.NewTicker(announceInterval)
		defer ticker.Stop()

		// Send immediately, then on each tick.
		send := func() {
			if _, err := conn.Write(payload); err != nil {
				log.Printf("announce error: %v", err)
			}
		}
		send()

		for {
			select {
			case <-ticker.C:
				send()
			case <-a.done:
				return
			}
		}
	}()

	log.Printf("announcing %s on %s every %v", a.ann.Service, multicastAddr, announceInterval)
	return nil
}

func (a *Announcer) Stop() { close(a.done) }

// ---------- Registry (Client side) ----------

type serviceEntry struct {
	Announcement
	lastSeen time.Time
}

type Registry struct {
	mu       sync.RWMutex
	services map[string]*serviceEntry // key: "service:host:port"
	done     chan struct{}
}

func NewRegistry() *Registry {
	return &Registry{
		services: make(map[string]*serviceEntry),
		done:     make(chan struct{}),
	}
}

func (r *Registry) Listen() error {
	addr, err := net.ResolveUDPAddr("udp4", multicastAddr)
	if err != nil {
		return err
	}

	conn, err := net.ListenMulticastUDP("udp4", nil, addr)
	if err != nil {
		return fmt.Errorf("listen multicast: %w", err)
	}
	conn.SetReadBuffer(4096)

	// Receive loop.
	go func() {
		defer conn.Close()
		buf := make([]byte, 2048)

		for {
			n, src, err := conn.ReadFromUDP(buf)
			if err != nil {
				select {
				case <-r.done:
					return
				default:
					log.Printf("read error: %v", err)
					continue
				}
			}

			var ann Announcement
			if err := json.Unmarshal(buf[:n], &ann); err != nil {
				log.Printf("bad announcement from %s: %v", src, err)
				continue
			}

			r.register(ann)
		}
	}()

	// Expiry reaper.
	go func() {
		ticker := time.NewTicker(serviceTTL / 2)
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				r.reap()
			case <-r.done:
				return
			}
		}
	}()

	log.Printf("listening for service announcements on %s", multicastAddr)
	return nil
}

func (r *Registry) register(ann Announcement) {
	key := fmt.Sprintf("%s:%s:%d", ann.Service, ann.Host, ann.Port)
	r.mu.Lock()
	defer r.mu.Unlock()

	existing, ok := r.services[key]
	if !ok {
		log.Printf("discovered: %s at %s:%d", ann.Service, ann.Host, ann.Port)
	}
	if ok {
		existing.lastSeen = time.Now()
	} else {
		r.services[key] = &serviceEntry{
			Announcement: ann,
			lastSeen:     time.Now(),
		}
	}
}

func (r *Registry) reap() {
	r.mu.Lock()
	defer r.mu.Unlock()
	now := time.Now()
	for key, entry := range r.services {
		if now.Sub(entry.lastSeen) > serviceTTL {
			log.Printf("expired: %s at %s:%d", entry.Service, entry.Host, entry.Port)
			delete(r.services, key)
		}
	}
}

// Lookup returns all healthy instances of a service.
func (r *Registry) Lookup(service string) []Announcement {
	r.mu.RLock()
	defer r.mu.RUnlock()
	var result []Announcement
	for _, entry := range r.services {
		if entry.Service == service {
			result = append(result, entry.Announcement)
		}
	}
	return result
}

func (r *Registry) Stop() { close(r.done) }

// ---------- Main ----------

func main() {
	if len(os.Args) < 2 {
		log.Fatal("usage: go run main.go [announce|discover]")
	}

	switch os.Args[1] {
	case "announce":
		a := NewAnnouncer(Announcement{
			Service:  "api-server",
			Host:     "192.168.1.100",
			Port:     8080,
			Metadata: map[string]string{"version": "1.2.3"},
		})
		if err := a.Start(); err != nil {
			log.Fatal(err)
		}
		select {} // Block forever.

	case "discover":
		reg := NewRegistry()
		if err := reg.Listen(); err != nil {
			log.Fatal(err)
		}
		// Periodically print discovered services.
		for {
			time.Sleep(3 * time.Second)
			instances := reg.Lookup("api-server")
			fmt.Printf("found %d instance(s) of api-server:\n", len(instances))
			for _, inst := range instances {
				fmt.Printf("  %s:%d (meta=%v)\n", inst.Host, inst.Port, inst.Metadata)
			}
		}
	}
}
```

Design considerations:

1. **`net.ListenMulticastUDP`** sets `SO_REUSEADDR` automatically, so multiple processes on the same machine can listen on the same multicast group.
2. **3x TTL ratio**: announce every 5s, expire after 15s. This tolerates 2 lost packets before a service appears offline.
3. **LIFO announce** (send immediately on start): new services are discovered without waiting for the first tick.
4. **Separate reaper goroutine**: cleans up services that stop announcing. Without it, the registry grows forever.
5. **LAN only**: UDP multicast does not cross router boundaries unless the routers are configured for multicast routing (rare). For cross-network discovery, use a dedicated registry like Consul or etcd.'''),

    ("go_deep/dns_cache_ttl", r'''How do I build a DNS resolver in Go with an in-memory cache that respects TTL values from DNS responses?''', r'''<think>
Go's net.Resolver doesn't expose TTL information — it returns IPs but not the TTL from
the DNS record. To build a caching resolver with TTL awareness, I need to use a lower-level
DNS library like github.com/miekg/dns, or use net.Resolver and apply a fixed TTL.

The cleaner approach for production is miekg/dns since it gives full access to DNS
response fields including TTL. But for a simpler approach that works with the standard
library, I can use net.Resolver with a configurable cache TTL.

Let me show both approaches:
1. Standard library approach with a fixed cache duration.
2. miekg/dns approach with actual TTL from records.

For the cache itself:
- Use sync.Map or a map + RWMutex.
- Each entry stores the IPs and expiration time.
- On lookup: check cache first, if miss or expired, do a real lookup.
- Background cleanup to remove expired entries.

Important considerations:
- Negative caching: cache DNS failures briefly to avoid hammering the resolver.
- Concurrent lookups for the same domain: use singleflight.Group to deduplicate.
  Without this, 100 goroutines looking up the same domain simultaneously fire 100 DNS
  queries instead of 1.
- Thread safety: lookups happen from many goroutines.

singleflight is the key insight here — it's from golang.org/x/sync/singleflight and
is exactly what http.Transport uses internally for DNS deduplication.
</think>

Here is a DNS caching resolver with TTL support and query deduplication:

```go
package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"sync"
	"time"

	"golang.org/x/sync/singleflight"
)

// ---------- Cached DNS Resolver ----------

type cacheEntry struct {
	addrs   []string
	expires time.Time
}

type CachingResolver struct {
	resolver   *net.Resolver
	mu         sync.RWMutex
	cache      map[string]*cacheEntry
	defaultTTL time.Duration
	negativeTTL time.Duration
	group      singleflight.Group
	done       chan struct{}
}

type ResolverConfig struct {
	DefaultTTL  time.Duration // TTL for positive results
	NegativeTTL time.Duration // TTL for negative results (NXDOMAIN)
	DNSServer   string        // Custom DNS server (optional, e.g., "8.8.8.8:53")
}

func NewCachingResolver(cfg ResolverConfig) *CachingResolver {
	if cfg.DefaultTTL <= 0 {
		cfg.DefaultTTL = 5 * time.Minute
	}
	if cfg.NegativeTTL <= 0 {
		cfg.NegativeTTL = 30 * time.Second
	}

	resolver := net.DefaultResolver
	if cfg.DNSServer != "" {
		resolver = &net.Resolver{
			PreferGo: true,
			Dial: func(ctx context.Context, network, address string) (net.Conn, error) {
				d := net.Dialer{Timeout: 3 * time.Second}
				return d.DialContext(ctx, "udp", cfg.DNSServer)
			},
		}
	}

	cr := &CachingResolver{
		resolver:    resolver,
		cache:       make(map[string]*cacheEntry),
		defaultTTL:  cfg.DefaultTTL,
		negativeTTL: cfg.NegativeTTL,
		done:        make(chan struct{}),
	}

	go cr.reaper()
	return cr
}

// LookupHost resolves a hostname, returning cached results when available.
func (cr *CachingResolver) LookupHost(ctx context.Context, host string) ([]string, error) {
	// Check cache first.
	if addrs, ok := cr.fromCache(host); ok {
		return addrs, nil
	}

	// Use singleflight to deduplicate concurrent lookups for the same host.
	result, err, _ := cr.group.Do(host, func() (any, error) {
		// Double-check cache after acquiring singleflight slot.
		if addrs, ok := cr.fromCache(host); ok {
			return addrs, nil
		}

		addrs, err := cr.resolver.LookupHost(ctx, host)
		if err != nil {
			// Negative cache: remember failures briefly.
			cr.toCache(host, nil, cr.negativeTTL)
			return nil, err
		}

		cr.toCache(host, addrs, cr.defaultTTL)
		return addrs, nil
	})

	if err != nil {
		return nil, err
	}
	return result.([]string), nil
}

func (cr *CachingResolver) fromCache(host string) ([]string, bool) {
	cr.mu.RLock()
	defer cr.mu.RUnlock()
	entry, ok := cr.cache[host]
	if !ok || time.Now().After(entry.expires) {
		return nil, false
	}
	if entry.addrs == nil {
		return nil, false // Negative cache entry.
	}
	// Return a copy to prevent mutation.
	addrs := make([]string, len(entry.addrs))
	copy(addrs, entry.addrs)
	return addrs, true
}

func (cr *CachingResolver) toCache(host string, addrs []string, ttl time.Duration) {
	cr.mu.Lock()
	defer cr.mu.Unlock()
	cr.cache[host] = &cacheEntry{
		addrs:   addrs,
		expires: time.Now().Add(ttl),
	}
}

func (cr *CachingResolver) reaper() {
	ticker := time.NewTicker(1 * time.Minute)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			cr.mu.Lock()
			now := time.Now()
			for host, entry := range cr.cache {
				if now.After(entry.expires) {
					delete(cr.cache, host)
				}
			}
			cr.mu.Unlock()
		case <-cr.done:
			return
		}
	}
}

// Stats returns cache size.
func (cr *CachingResolver) Stats() int {
	cr.mu.RLock()
	defer cr.mu.RUnlock()
	return len(cr.cache)
}

func (cr *CachingResolver) Close() { close(cr.done) }

// ---------- Custom Dialer using cached resolver ----------

// NewCachedDialer returns a net.Dialer-compatible function that uses
// the caching resolver. Plug into http.Transport.DialContext.
func NewCachedDialer(cr *CachingResolver) func(ctx context.Context, network, addr string) (net.Conn, error) {
	dialer := &net.Dialer{Timeout: 5 * time.Second}

	return func(ctx context.Context, network, addr string) (net.Conn, error) {
		host, port, err := net.SplitHostPort(addr)
		if err != nil {
			return dialer.DialContext(ctx, network, addr)
		}

		addrs, err := cr.LookupHost(ctx, host)
		if err != nil {
			return nil, fmt.Errorf("resolve %s: %w", host, err)
		}

		// Try each resolved address.
		var lastErr error
		for _, ip := range addrs {
			conn, err := dialer.DialContext(ctx, network, net.JoinHostPort(ip, port))
			if err == nil {
				return conn, nil
			}
			lastErr = err
		}
		return nil, lastErr
	}
}

// ---------- Demo ----------

func main() {
	resolver := NewCachingResolver(ResolverConfig{
		DefaultTTL:  5 * time.Minute,
		NegativeTTL: 30 * time.Second,
		DNSServer:   "8.8.8.8:53",
	})
	defer resolver.Close()

	hosts := []string{"google.com", "github.com", "google.com", "github.com"}

	for _, host := range hosts {
		start := time.Now()
		addrs, err := resolver.LookupHost(context.Background(), host)
		dur := time.Since(start)
		if err != nil {
			log.Printf("%s: error: %v (%v)", host, err, dur)
		} else {
			log.Printf("%s: %v (%v, cache_size=%d)", host, addrs, dur, resolver.Stats())
		}
	}
}
```

Key design elements:

1. **`singleflight.Group`** deduplicates concurrent lookups. If 50 goroutines resolve `api.example.com` simultaneously, only one DNS query is sent. This is the same pattern `net/http` uses internally.
2. **Negative caching** with a shorter TTL (30s) prevents hammering DNS for domains that do not exist. Without this, every request to a bad host triggers a DNS query.
3. **Copy-on-read** from cache prevents callers from mutating cached slices.
4. **`NewCachedDialer`** integrates with `http.Transport.DialContext`, so the entire `http.Client` benefits from caching without any code changes.
5. **Custom DNS server** via `net.Resolver.Dial` allows using a specific resolver (e.g., `8.8.8.8`) instead of the system default.'''),

    ("go_deep/http_retry_idempotency", r'''How do I implement HTTP request retry with exponential backoff and idempotency keys in Go to safely retry failed requests?''', r'''<think>
Retrying HTTP requests is tricky because:
1. Not all requests are safe to retry — POST that creates a resource could create duplicates.
2. You need to distinguish retryable errors (network timeout, 503, 429) from permanent
   errors (400, 404, 401).
3. Exponential backoff with jitter prevents thundering herd when many clients retry.
4. Idempotency keys let the server deduplicate retried requests — the client sends a
   unique key (usually a UUID) in a header, and the server returns the same response
   for duplicate keys instead of processing again.

Design:
- A RetryTransport that wraps http.RoundTripper.
- Checks the response status code to decide if retry is appropriate.
- For non-GET requests, attaches an Idempotency-Key header if not already present.
- Uses exponential backoff: delay = baseDelay * 2^attempt + jitter.
- Respects Retry-After header from 429/503 responses.
- The request body must be re-readable for retries — we need to buffer it or use
  GetBody.

Body re-reading is the biggest gotcha. After the first attempt reads and closes the body,
it's gone. http.Request.GetBody is a function that returns a new reader. For requests
created with http.NewRequest from a bytes.Reader, GetBody is set automatically. But for
streaming bodies, retries are impossible without buffering.

I should also limit total retry duration, not just retry count, to avoid retrying forever
when each attempt takes a long time.
</think>

Here is a retry transport with idempotency keys:

```go
package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"fmt"
	"io"
	"log"
	"math"
	"math/big"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// RetryConfig controls retry behavior.
type RetryConfig struct {
	MaxRetries   int           // Max number of retries (not counting initial attempt)
	BaseDelay    time.Duration // Initial delay before first retry
	MaxDelay     time.Duration // Cap on delay between retries
	MaxTotalTime time.Duration // Max total time across all attempts
}

var DefaultRetryConfig = RetryConfig{
	MaxRetries:   3,
	BaseDelay:    500 * time.Millisecond,
	MaxDelay:     30 * time.Second,
	MaxTotalTime: 2 * time.Minute,
}

// RetryTransport wraps an http.RoundTripper with retry logic.
type RetryTransport struct {
	Base   http.RoundTripper
	Config RetryConfig
}

func (rt *RetryTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	cfg := rt.Config
	base := rt.Base
	if base == nil {
		base = http.DefaultTransport
	}

	// Attach idempotency key for non-GET requests if not already present.
	if req.Method != http.MethodGet && req.Header.Get("Idempotency-Key") == "" {
		req.Header.Set("Idempotency-Key", generateKey())
	}

	// Buffer the body for retries. Without this, the body is consumed on first attempt.
	if req.Body != nil && req.GetBody == nil {
		bodyBytes, err := io.ReadAll(req.Body)
		req.Body.Close()
		if err != nil {
			return nil, fmt.Errorf("buffer request body: %w", err)
		}
		req.GetBody = func() (io.ReadCloser, error) {
			return io.NopCloser(bytes.NewReader(bodyBytes)), nil
		}
		req.Body, _ = req.GetBody()
	}

	deadline := time.Now().Add(cfg.MaxTotalTime)
	var lastResp *http.Response
	var lastErr error

	for attempt := 0; attempt <= cfg.MaxRetries; attempt++ {
		if time.Now().After(deadline) {
			break
		}

		// Reset body for retry.
		if attempt > 0 && req.GetBody != nil {
			var err error
			req.Body, err = req.GetBody()
			if err != nil {
				return nil, fmt.Errorf("reset body: %w", err)
			}
		}

		resp, err := base.RoundTrip(req)
		if err != nil {
			lastErr = err
			// Network errors are retryable.
			if req.Context().Err() != nil {
				return nil, err // Context cancelled — don't retry.
			}
			log.Printf("attempt %d/%d failed: %v", attempt+1, cfg.MaxRetries+1, err)
			rt.backoff(req.Context(), attempt, cfg, nil)
			continue
		}

		// Check if response is retryable.
		if !isRetryableStatus(resp.StatusCode) {
			return resp, nil // Success or permanent error.
		}

		log.Printf("attempt %d/%d: status %d, retrying",
			attempt+1, cfg.MaxRetries+1, resp.StatusCode)

		// Must drain and close body before retry.
		retryAfter := parseRetryAfter(resp)
		io.Copy(io.Discard, resp.Body)
		resp.Body.Close()

		lastResp = resp
		lastErr = nil

		if attempt < cfg.MaxRetries {
			rt.backoff(req.Context(), attempt, cfg, retryAfter)
		}
	}

	if lastResp != nil {
		return lastResp, nil // Return the last retryable response.
	}
	return nil, fmt.Errorf("all %d attempts failed: %w", cfg.MaxRetries+1, lastErr)
}

func isRetryableStatus(code int) bool {
	switch code {
	case http.StatusTooManyRequests,       // 429
		http.StatusServiceUnavailable,      // 503
		http.StatusGatewayTimeout,          // 504
		http.StatusBadGateway:              // 502
		return true
	}
	return false
}

func (rt *RetryTransport) backoff(ctx context.Context, attempt int, cfg RetryConfig, retryAfter *time.Duration) {
	delay := cfg.BaseDelay * time.Duration(math.Pow(2, float64(attempt)))
	if delay > cfg.MaxDelay {
		delay = cfg.MaxDelay
	}

	// Add jitter: +/- 25%.
	jitterRange := int64(delay) / 4
	if jitterRange > 0 {
		n, _ := rand.Int(rand.Reader, big.NewInt(jitterRange*2))
		delay += time.Duration(n.Int64() - jitterRange)
	}

	// Respect Retry-After header if present and longer.
	if retryAfter != nil && *retryAfter > delay {
		delay = *retryAfter
	}

	select {
	case <-time.After(delay):
	case <-ctx.Done():
	}
}

func parseRetryAfter(resp *http.Response) *time.Duration {
	val := resp.Header.Get("Retry-After")
	if val == "" {
		return nil
	}
	// Try as seconds first.
	if seconds, err := strconv.Atoi(val); err == nil {
		d := time.Duration(seconds) * time.Second
		return &d
	}
	// Try as HTTP date.
	if t, err := http.ParseTime(val); err == nil {
		d := time.Until(t)
		if d < 0 {
			d = 0
		}
		return &d
	}
	return nil
}

func generateKey() string {
	b := make([]byte, 16)
	rand.Read(b)
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:])
}

// ---------- Server with idempotency support ----------

func idempotentServer() {
	seen := struct {
		sync.Mutex
		keys map[string]string
	}{keys: make(map[string]string)}

	http.HandleFunc("/create", func(w http.ResponseWriter, r *http.Request) {
		key := r.Header.Get("Idempotency-Key")
		if key != "" {
			seen.Lock()
			if result, ok := seen.keys[key]; ok {
				seen.Unlock()
				log.Printf("idempotent replay for key %s", key)
				w.Write([]byte(result))
				return
			}
			seen.Unlock()
		}

		// Process the request.
		result := fmt.Sprintf("created resource at %s\n", time.Now().Format(time.RFC3339))

		if key != "" {
			seen.Lock()
			seen.keys[key] = result
			seen.Unlock()
		}

		w.Write([]byte(result))
	})

	log.Fatal(http.ListenAndServe(":8080", nil))
}

func main() {
	go idempotentServer()
	time.Sleep(100 * time.Millisecond)

	client := &http.Client{
		Transport: &RetryTransport{
			Base:   http.DefaultTransport,
			Config: DefaultRetryConfig,
		},
	}

	body := strings.NewReader(`{"name": "test"}`)
	resp, err := client.Post("http://localhost:8080/create", "application/json", body)
	if err != nil {
		log.Fatal(err)
	}
	defer resp.Body.Close()

	result, _ := io.ReadAll(resp.Body)
	fmt.Printf("result: %s", result)
}
```

Key points:

1. **Body buffering** via `GetBody`: the body stream is consumed on the first attempt. Without buffering it into `GetBody`, retries send an empty body.
2. **Idempotency key** is a UUID sent in a header. The server stores the response keyed by this value and replays it on duplicate requests, preventing double-creates.
3. **Exponential backoff with jitter** prevents thundering herd — without jitter, all clients that failed at the same time retry at the same time.
4. **Retry-After header** from 429/503 overrides the computed backoff, respecting the server's rate limit.
5. **Drain and close the response body** before retrying — failing to do this leaks connections in the transport's pool.
6. **`MaxTotalTime`** caps the total wall-clock time across all attempts, preventing indefinite retry loops when each attempt itself takes a long time.'''),

    ("go_deep/otel_tracing_propagation", r'''How do I implement distributed tracing in Go with OpenTelemetry, including context propagation across HTTP service boundaries?''', r'''<think>
OpenTelemetry (OTel) is the standard for distributed tracing. The key concepts:
1. Trace: a complete request flow across services.
2. Span: a single operation within a trace (e.g., one HTTP handler, one DB query).
3. Context propagation: passing trace/span IDs between services via HTTP headers
   (typically W3C Trace Context format: traceparent/tracestate headers).

In Go, the OTel SDK has:
- TracerProvider: creates tracers.
- Tracer: creates spans.
- TextMapPropagator: injects/extracts trace context from HTTP headers.
- Exporter: sends spans to a backend (Jaeger, Zipkin, OTLP collector).

For HTTP services, the pattern is:
1. Initialize a TracerProvider with an exporter.
2. Outgoing requests: use otelhttp.NewTransport to automatically inject headers.
3. Incoming requests: use otelhttp.NewHandler to automatically extract headers and
   create server spans.
4. Within handlers: use trace.SpanFromContext(ctx) to get the current span, or
   tracer.Start(ctx, "name") to create child spans.

Context propagation is the critical piece — without it, each service creates independent
traces. The W3C traceparent header carries the trace ID and parent span ID, so the
receiving service can create spans that are children of the caller's span.

I need to show:
1. TracerProvider setup with OTLP exporter.
2. HTTP server with automatic span creation.
3. HTTP client with automatic context injection.
4. Manual span creation for internal operations.
5. Adding attributes and events to spans.
</think>

Here is distributed tracing with OpenTelemetry across Go HTTP services:

```go
package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
	"go.opentelemetry.io/otel/trace"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

// ---------- Tracer setup ----------

func initTracer(ctx context.Context, serviceName string) (func(), error) {
	// OTLP exporter sends spans to a collector (e.g., Jaeger, Grafana Tempo).
	exporter, err := otlptracehttp.New(ctx,
		otlptracehttp.WithEndpoint("localhost:4318"),
		otlptracehttp.WithInsecure(),
	)
	if err != nil {
		return nil, fmt.Errorf("create exporter: %w", err)
	}

	// Resource describes this service.
	res, err := resource.Merge(
		resource.Default(),
		resource.NewWithAttributes(
			semconv.SchemaURL,
			semconv.ServiceName(serviceName),
			semconv.ServiceVersion("1.0.0"),
			attribute.String("environment", "development"),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("create resource: %w", err)
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sdktrace.AlwaysSample()), // Sample everything in dev
	)

	// Set global tracer provider and propagator.
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{}, // W3C traceparent/tracestate
		propagation.Baggage{},     // W3C baggage
	))

	cleanup := func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := tp.Shutdown(ctx); err != nil {
			log.Printf("tracer shutdown error: %v", err)
		}
	}

	return cleanup, nil
}

// ---------- Service A (Gateway) ----------

func serviceA() {
	cleanup, err := initTracer(context.Background(), "gateway")
	if err != nil {
		log.Fatal(err)
	}
	defer cleanup()

	tracer := otel.Tracer("gateway")

	// HTTP client with automatic trace context injection.
	client := &http.Client{
		Transport: otelhttp.NewTransport(http.DefaultTransport),
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/order", func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		span := trace.SpanFromContext(ctx)
		span.SetAttributes(attribute.String("order.source", "web"))

		// Create a child span for business logic.
		ctx, bizSpan := tracer.Start(ctx, "validate-order")
		time.Sleep(10 * time.Millisecond) // Simulate work.
		bizSpan.AddEvent("order validated", trace.WithAttributes(
			attribute.Int("item_count", 3),
		))
		bizSpan.End()

		// Call downstream service — trace context is automatically injected.
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet,
			"http://localhost:8082/inventory", nil)
		resp, err := client.Do(req)
		if err != nil {
			span.RecordError(err)
			span.SetStatus(codes.Error, err.Error())
			http.Error(w, "downstream error", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()

		span.SetStatus(codes.Ok, "")
		fmt.Fprintln(w, "order processed")
	})

	// otelhttp.NewHandler auto-creates server spans and extracts incoming context.
	handler := otelhttp.NewHandler(mux, "gateway",
		otelhttp.WithSpanNameFormatter(func(operation string, r *http.Request) string {
			return fmt.Sprintf("%s %s", r.Method, r.URL.Path)
		}),
	)

	log.Println("Service A (gateway) on :8081")
	log.Fatal(http.ListenAndServe(":8081", handler))
}

// ---------- Service B (Inventory) ----------

func serviceB() {
	cleanup, err := initTracer(context.Background(), "inventory")
	if err != nil {
		log.Fatal(err)
	}
	defer cleanup()

	tracer := otel.Tracer("inventory")

	mux := http.NewServeMux()
	mux.HandleFunc("/inventory", func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		// This span is automatically a child of the gateway's span
		// because otelhttp extracted the traceparent header.
		ctx, dbSpan := tracer.Start(ctx, "db.query",
			trace.WithAttributes(
				attribute.String("db.system", "postgresql"),
				attribute.String("db.statement", "SELECT stock FROM items"),
			),
		)
		time.Sleep(20 * time.Millisecond) // Simulate DB query.
		dbSpan.End()

		// Access the parent span.
		span := trace.SpanFromContext(r.Context())
		span.SetAttributes(attribute.Bool("in_stock", true))

		fmt.Fprintln(w, "in stock")
	})

	handler := otelhttp.NewHandler(mux, "inventory")

	log.Println("Service B (inventory) on :8082")
	log.Fatal(http.ListenAndServe(":8082", handler))
}

func main() {
	go serviceB()
	time.Sleep(100 * time.Millisecond)
	serviceA()
}
```

How context propagation works:

```
Client → Service A (gateway) → Service B (inventory)

1. Client sends GET /order to Service A.
2. otelhttp.NewHandler creates span "GET /order" with traceID=abc123.
3. Service A calls Service B. otelhttp.NewTransport injects:
     traceparent: 00-abc123-spanID1-01
4. Service B's otelhttp.NewHandler extracts the traceparent header,
   creates a child span with the same traceID=abc123 but a new spanID.
5. All spans share traceID=abc123, forming a connected trace.
```

Key components:

- **`otelhttp.NewHandler`** (server): extracts trace context from incoming headers and creates server spans automatically.
- **`otelhttp.NewTransport`** (client): injects trace context into outgoing request headers automatically.
- **`propagation.TraceContext{}`**: implements the W3C Trace Context standard (`traceparent` / `tracestate` headers).
- **`tracer.Start(ctx, "name")`**: creates a child span under whatever span is in the context.
- **`span.RecordError(err)`**: records an error event on the span with stack trace.
- **`sdktrace.WithBatcher`**: batches spans before export, reducing overhead in production.'''),

    ("go_deep/correlation_id_middleware", r'''How do I build request correlation ID middleware in Go that propagates the ID through the entire request lifecycle including downstream HTTP calls and log output?''', r'''<think>
Correlation IDs (also called request IDs or trace IDs) let you follow a single request
across logs, downstream services, and error reports. The pattern:

1. Middleware extracts or generates a correlation ID from the incoming request.
2. Stores it in the request context.
3. All log output includes the correlation ID.
4. Outgoing HTTP calls propagate the ID in a header.

This is simpler than full distributed tracing but covers 80% of debugging needs.

Key design decisions:
- Header name: X-Request-ID or X-Correlation-ID (both are common).
- ID format: UUID v4, or something shorter like a random hex string.
- Log integration: use a structured logger (slog in Go 1.21+) with a handler that
  reads the correlation ID from context.
- HTTP client integration: a custom RoundTripper that injects the header.

I should show integration with Go's slog package since it's the standard structured
logging solution. The trick is creating a custom slog.Handler that automatically adds
the correlation ID from context to every log record.

For the HTTP client, I'll wrap the transport to automatically forward the correlation ID.
</think>

Here is a complete correlation ID system with logging and HTTP client propagation:

```go
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"time"
)

const (
	CorrelationHeader = "X-Correlation-ID"
)

// ---------- Context key ----------

type correlationIDKey struct{}

func WithCorrelationID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, correlationIDKey{}, id)
}

func CorrelationID(ctx context.Context) string {
	id, _ := ctx.Value(correlationIDKey{}).(string)
	return id
}

func generateID() string {
	b := make([]byte, 12)
	rand.Read(b)
	return hex.EncodeToString(b)
}

// ---------- HTTP Middleware ----------

func CorrelationMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get(CorrelationHeader)
		if id == "" {
			id = generateID()
		}

		ctx := WithCorrelationID(r.Context(), id)
		w.Header().Set(CorrelationHeader, id)

		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// ---------- Structured logger with correlation ID ----------

// CorrelationHandler wraps an slog.Handler to inject the correlation ID.
type CorrelationHandler struct {
	inner slog.Handler
}

func NewCorrelationHandler(inner slog.Handler) *CorrelationHandler {
	return &CorrelationHandler{inner: inner}
}

func (h *CorrelationHandler) Enabled(ctx context.Context, level slog.Level) bool {
	return h.inner.Enabled(ctx, level)
}

func (h *CorrelationHandler) Handle(ctx context.Context, r slog.Record) error {
	if id := CorrelationID(ctx); id != "" {
		r.AddAttrs(slog.String("correlation_id", id))
	}
	return h.inner.Handle(ctx, r)
}

func (h *CorrelationHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return &CorrelationHandler{inner: h.inner.WithAttrs(attrs)}
}

func (h *CorrelationHandler) WithGroup(name string) slog.Handler {
	return &CorrelationHandler{inner: h.inner.WithGroup(name)}
}

// ---------- HTTP client with correlation propagation ----------

type CorrelationTransport struct {
	Base http.RoundTripper
}

func (t *CorrelationTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	base := t.Base
	if base == nil {
		base = http.DefaultTransport
	}

	if id := CorrelationID(req.Context()); id != "" {
		// Clone the request to avoid mutating the original.
		req = req.Clone(req.Context())
		req.Header.Set(CorrelationHeader, id)
	}

	return base.RoundTrip(req)
}

// NewCorrelatedClient creates an HTTP client that propagates correlation IDs.
func NewCorrelatedClient() *http.Client {
	return &http.Client{
		Transport: &CorrelationTransport{
			Base: http.DefaultTransport,
		},
		Timeout: 10 * time.Second,
	}
}

// ---------- Application ----------

func main() {
	// Set up structured logger with correlation ID support.
	jsonHandler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})
	logger := slog.New(NewCorrelationHandler(jsonHandler))
	slog.SetDefault(logger)

	client := NewCorrelatedClient()

	mux := http.NewServeMux()

	mux.HandleFunc("/api/orders", func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		// All log lines automatically include correlation_id.
		slog.InfoContext(ctx, "processing order",
			"method", r.Method,
			"path", r.URL.Path,
		)

		// Downstream call propagates the correlation ID automatically.
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet,
			"http://localhost:8081/inventory", nil)
		resp, err := client.Do(req)
		if err != nil {
			slog.ErrorContext(ctx, "downstream call failed", "error", err)
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}
		defer resp.Body.Close()

		slog.InfoContext(ctx, "order complete",
			"downstream_status", resp.StatusCode,
		)
		fmt.Fprintln(w, "order processed")
	})

	handler := CorrelationMiddleware(mux)

	slog.Info("server starting", "addr", ":8080")
	http.ListenAndServe(":8080", handler)
}
```

Log output looks like:

```json
{"time":"2024-01-15T10:30:00Z","level":"INFO","msg":"processing order","method":"GET","path":"/api/orders","correlation_id":"a1b2c3d4e5f6a1b2c3d4e5f6"}
{"time":"2024-01-15T10:30:00Z","level":"INFO","msg":"order complete","downstream_status":200,"correlation_id":"a1b2c3d4e5f6a1b2c3d4e5f6"}
```

How the pieces fit together:

1. **Middleware** generates or extracts the ID and stores it in context. Every downstream handler gets it automatically.
2. **Custom `slog.Handler`** reads the ID from context in `Handle()` and adds it as an attribute. Zero effort at call sites — `slog.InfoContext(ctx, ...)` is all you need.
3. **Custom `RoundTripper`** reads the ID from the request's context and sets the header. Downstream services receive the same correlation ID.
4. **The ID flows**: incoming header → context → logs + outgoing headers. A single grep for the correlation ID shows the complete request lifecycle across all services.'''),

    ("go_deep/api_versioning_strategies", r'''What are the main API versioning strategies in Go HTTP routers, and how do I implement each one cleanly?''', r'''<think>
There are three main API versioning strategies:
1. URL path versioning: /v1/users, /v2/users
2. Header versioning: Accept: application/vnd.myapi.v2+json
3. Query parameter versioning: /users?version=2

Each has trade-offs. Let me think about idiomatic Go implementations:

URL path:
- Simplest, most visible, easiest to test (just curl different paths).
- With Go 1.22 routing patterns, you can do mux.HandleFunc("GET /v1/users", ...)
- Or group handlers behind /v1/ and /v2/ prefixes.
- Downside: URLs change between versions, breaking bookmarks and caches.

Header versioning:
- REST purists prefer this since the URL represents the resource, not the version.
- Need middleware to parse the Accept header and route accordingly.
- Harder to test casually (need to set headers).

Query parameter:
- Easy to use, but query params are semantically for filtering, not versioning.
- Least popular in practice.

For a clean Go implementation, I should show:
1. URL-path approach with version-grouped handlers.
2. Header-based approach with a version-negotiation middleware.
3. A shared handler pattern where one handler serves multiple versions with minor
   differences (avoiding code duplication).

The key insight is that most version differences are small — a new field, a renamed
field. Full duplication of handlers per version is wasteful. Better to branch within
a shared handler or use response transformers.
</think>

Here are the three API versioning strategies implemented in Go:

```go
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"strings"
)

// ---------- Shared domain types ----------

type User struct {
	ID        int    `json:"id"`
	Name      string `json:"name"`
	Email     string `json:"email"`
	FullName  string `json:"full_name,omitempty"`  // v2 only
	FirstName string `json:"first_name,omitempty"` // v1 only
	LastName  string `json:"last_name,omitempty"`  // v1 only
}

// ---------- Strategy 1: URL Path Versioning ----------
// /v1/users and /v2/users

func setupPathVersioning(mux *http.ServeMux) {
	// v1 handlers
	mux.HandleFunc("GET /v1/users/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, _ := strconv.Atoi(r.PathValue("id"))
		user := map[string]any{
			"id":         id,
			"first_name": "John",
			"last_name":  "Doe",
			"email":      "john@example.com",
		}
		writeJSON(w, http.StatusOK, user)
	})

	// v2 handlers — different response shape
	mux.HandleFunc("GET /v2/users/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, _ := strconv.Atoi(r.PathValue("id"))
		user := map[string]any{
			"id":        id,
			"full_name": "John Doe",
			"email":     "john@example.com",
			"avatar":    "https://cdn.example.com/avatars/1.jpg",
		}
		writeJSON(w, http.StatusOK, user)
	})
}

// ---------- Strategy 2: Header Versioning ----------
// Accept: application/vnd.myapi.v2+json

type apiVersion int

const (
	versionUnknown apiVersion = 0
	version1       apiVersion = 1
	version2       apiVersion = 2
)

type versionKey struct{}

func VersionFromContext(ctx interface{ Value(any) any }) apiVersion {
	v, _ := ctx.Value(versionKey{}).(apiVersion)
	return v
}

func HeaderVersionMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		accept := r.Header.Get("Accept")
		ver := version1 // Default to v1.

		// Parse: application/vnd.myapi.v2+json
		if strings.Contains(accept, "vnd.myapi.v") {
			parts := strings.Split(accept, "vnd.myapi.v")
			if len(parts) > 1 {
				numStr := strings.TrimRight(parts[1], "+json")
				if n, err := strconv.Atoi(numStr); err == nil {
					ver = apiVersion(n)
				}
			}
		}

		ctx := r.Context()
		ctx = context.WithValue(ctx, versionKey{}, ver)
		w.Header().Set("X-API-Version", strconv.Itoa(int(ver)))
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func setupHeaderVersioning(mux *http.ServeMux) {
	mux.HandleFunc("GET /users/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, _ := strconv.Atoi(r.PathValue("id"))
		ver := VersionFromContext(r.Context())

		switch ver {
		case version1:
			writeJSON(w, http.StatusOK, map[string]any{
				"id":         id,
				"first_name": "John",
				"last_name":  "Doe",
			})
		case version2:
			writeJSON(w, http.StatusOK, map[string]any{
				"id":        id,
				"full_name": "John Doe",
				"avatar":    "https://cdn.example.com/avatars/1.jpg",
			})
		default:
			http.Error(w, "unsupported API version", http.StatusBadRequest)
		}
	})
}

// ---------- Strategy 3: Response Transformer ----------
// Shared handler + version-specific transformers (best for evolving APIs)

type ResponseTransformer func(data map[string]any) map[string]any

var transformers = map[apiVersion]ResponseTransformer{
	version1: func(data map[string]any) map[string]any {
		// v1: split full_name into first/last, remove new fields.
		if name, ok := data["full_name"].(string); ok {
			parts := strings.SplitN(name, " ", 2)
			data["first_name"] = parts[0]
			if len(parts) > 1 {
				data["last_name"] = parts[1]
			}
			delete(data, "full_name")
		}
		delete(data, "avatar")
		return data
	},
	version2: func(data map[string]any) map[string]any {
		// v2: canonical format, no transform needed.
		return data
	},
}

func versionedResponse(w http.ResponseWriter, r *http.Request, data map[string]any) {
	ver := VersionFromContext(r.Context())
	if transform, ok := transformers[ver]; ok {
		data = transform(data)
	}
	writeJSON(w, http.StatusOK, data)
}

func setupTransformerPattern(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/users/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, _ := strconv.Atoi(r.PathValue("id"))

		// Single source of truth — always produce the latest format.
		data := map[string]any{
			"id":        id,
			"full_name": "John Doe",
			"email":     "john@example.com",
			"avatar":    "https://cdn.example.com/avatars/1.jpg",
		}

		versionedResponse(w, r, data)
	})
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

// Need context import for Strategy 2.
import "context"

func main() {
	mux := http.NewServeMux()

	// Strategy 1: URL path
	setupPathVersioning(mux)

	// Strategy 2: Header-based (needs middleware)
	// setupHeaderVersioning(mux)

	// Strategy 3: Transformer pattern (also needs middleware)
	// setupTransformerPattern(mux)

	var handler http.Handler = mux
	handler = HeaderVersionMiddleware(handler) // For strategies 2 and 3.

	log.Println("server on :8080")
	log.Fatal(http.ListenAndServe(":8080", handler))
}
```

Comparison:

| Strategy | Pros | Cons | Use When |
|---|---|---|---|
| URL path (`/v1/`) | Simple, visible, cacheable | URL changes break clients | Public APIs, major version bumps |
| Header (`Accept: vnd.v2`) | Clean URLs, REST-correct | Hard to test, easy to forget | Internal APIs, fine-grained versioning |
| Transformer | No code duplication, single handler | Complexity in transform layer | Evolving APIs with minor differences |

**Recommendation**: Start with URL path versioning for simplicity. Use the response transformer pattern to avoid duplicating handler logic between versions. Reserve header versioning for internal microservice APIs where clients are controlled.'''),

    ("go_deep/content_negotiation", r'''How do I implement proper HTTP content negotiation in Go, parsing the Accept header with quality values and selecting the best response format?''', r'''<think>
Content negotiation means the server selects the response format based on the client's
Accept header. The Accept header can contain multiple media types with quality values:
  Accept: text/html, application/json;q=0.9, text/plain;q=0.5

Quality (q) values range from 0 to 1, defaulting to 1 if omitted. The server should:
1. Parse the Accept header into a list of (media type, quality) pairs.
2. Sort by quality descending.
3. Match against the formats the server supports.
4. Return 406 Not Acceptable if no match is found.

Parsing subtleties:
- Media types can have parameters: text/html;charset=utf-8;q=0.9
- The q parameter is special (quality), not a media type parameter.
- Wildcards: */* matches anything, text/* matches any text subtype.
- Missing Accept header = accept anything (equivalent to */*).

Go's standard library doesn't include Accept header parsing. I need to write the parser
or use a library. Since this is a training example, I'll write the parser from scratch
to show the logic.

I should also show how to use this in a handler to serve JSON, XML, and plain text
from the same endpoint.
</think>

Here is a complete content negotiation implementation:

```go
package main

import (
	"encoding/json"
	"encoding/xml"
	"fmt"
	"log"
	"net/http"
	"sort"
	"strconv"
	"strings"
)

// ---------- Accept header parser ----------

type MediaRange struct {
	Type    string  // e.g., "text"
	Subtype string  // e.g., "html"
	Quality float64 // 0.0 to 1.0
	Params  map[string]string
}

// ParseAccept parses an Accept header into sorted media ranges.
// Example: "text/html, application/json;q=0.9, */*;q=0.1"
func ParseAccept(header string) []MediaRange {
	if header == "" {
		return []MediaRange{{Type: "*", Subtype: "*", Quality: 1.0}}
	}

	var ranges []MediaRange

	for _, part := range strings.Split(header, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}

		mr := MediaRange{Quality: 1.0, Params: make(map[string]string)}

		// Split media type from parameters.
		segments := strings.Split(part, ";")
		mediaType := strings.TrimSpace(segments[0])

		// Parse type/subtype.
		slash := strings.IndexByte(mediaType, '/')
		if slash < 0 {
			continue // Malformed.
		}
		mr.Type = strings.TrimSpace(mediaType[:slash])
		mr.Subtype = strings.TrimSpace(mediaType[slash+1:])

		// Parse parameters (including q).
		for _, param := range segments[1:] {
			param = strings.TrimSpace(param)
			eq := strings.IndexByte(param, '=')
			if eq < 0 {
				continue
			}
			key := strings.TrimSpace(param[:eq])
			val := strings.TrimSpace(param[eq+1:])

			if strings.ToLower(key) == "q" {
				if q, err := strconv.ParseFloat(val, 64); err == nil {
					mr.Quality = q
				}
			} else {
				mr.Params[key] = val
			}
		}

		ranges = append(ranges, mr)
	}

	// Sort by quality descending, then by specificity.
	sort.SliceStable(ranges, func(i, j int) bool {
		if ranges[i].Quality != ranges[j].Quality {
			return ranges[i].Quality > ranges[j].Quality
		}
		// More specific types win ties.
		return specificity(ranges[i]) > specificity(ranges[j])
	})

	return ranges
}

func specificity(mr MediaRange) int {
	if mr.Type == "*" && mr.Subtype == "*" {
		return 0
	}
	if mr.Subtype == "*" {
		return 1
	}
	return 2 + len(mr.Params)
}

func (mr MediaRange) Matches(contentType string) bool {
	slash := strings.IndexByte(contentType, '/')
	if slash < 0 {
		return false
	}
	t := contentType[:slash]
	s := contentType[slash+1:]

	if mr.Type == "*" && mr.Subtype == "*" {
		return true
	}
	if mr.Type == t && mr.Subtype == "*" {
		return true
	}
	return mr.Type == t && mr.Subtype == s
}

// ---------- Content negotiation ----------

type Encoder struct {
	ContentType string
	Encode      func(w http.ResponseWriter, v any) error
}

var encoders = []Encoder{
	{
		ContentType: "application/json",
		Encode: func(w http.ResponseWriter, v any) error {
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			enc := json.NewEncoder(w)
			enc.SetIndent("", "  ")
			return enc.Encode(v)
		},
	},
	{
		ContentType: "application/xml",
		Encode: func(w http.ResponseWriter, v any) error {
			w.Header().Set("Content-Type", "application/xml; charset=utf-8")
			w.Write([]byte(xml.Header))
			return xml.NewEncoder(w).Encode(v)
		},
	},
	{
		ContentType: "text/plain",
		Encode: func(w http.ResponseWriter, v any) error {
			w.Header().Set("Content-Type", "text/plain; charset=utf-8")
			_, err := fmt.Fprintf(w, "%+v\n", v)
			return err
		},
	},
}

// Negotiate selects the best encoder for the client's Accept header.
func Negotiate(accept string) (*Encoder, bool) {
	ranges := ParseAccept(accept)

	for _, mr := range ranges {
		if mr.Quality == 0 {
			continue // q=0 means explicitly rejected.
		}
		for i := range encoders {
			if mr.Matches(encoders[i].ContentType) {
				return &encoders[i], true
			}
		}
	}
	return nil, false
}

// ---------- Negotiation middleware ----------

func NegotiateMiddleware(next http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Set Vary header so caches key on Accept.
			w.Header().Set("Vary", "Accept")
			next.ServeHTTP(w, r)
		})
	}(next)
}

// WriteNegotiated encodes the response using the best format.
func WriteNegotiated(w http.ResponseWriter, r *http.Request, status int, v any) {
	encoder, ok := Negotiate(r.Header.Get("Accept"))
	if !ok {
		http.Error(w, "Not Acceptable. Supported: application/json, application/xml, text/plain",
			http.StatusNotAcceptable)
		return
	}

	w.WriteHeader(status)
	if err := encoder.Encode(w, v); err != nil {
		log.Printf("encode error: %v", err)
	}
}

// ---------- Application ----------

type Product struct {
	XMLName xml.Name `json:"-" xml:"product"`
	ID      int      `json:"id" xml:"id"`
	Name    string   `json:"name" xml:"name"`
	Price   float64  `json:"price" xml:"price"`
}

func main() {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /products/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, _ := strconv.Atoi(r.PathValue("id"))
		product := Product{ID: id, Name: "Widget", Price: 29.99}
		WriteNegotiated(w, r, http.StatusOK, product)
	})

	handler := NegotiateMiddleware(mux)

	log.Println("server on :8080")
	log.Fatal(http.ListenAndServe(":8080", handler))
}

// Test:
// curl -H "Accept: application/json" localhost:8080/products/1
// curl -H "Accept: application/xml" localhost:8080/products/1
// curl -H "Accept: text/plain" localhost:8080/products/1
// curl -H "Accept: image/png" localhost:8080/products/1  → 406
```

Key implementation details:

1. **Quality sorting with specificity tiebreaker**: `text/html` (specificity=2) beats `text/*` (specificity=1) beats `*/*` (specificity=0) at the same quality value.
2. **`q=0` means "do not send"**: a client can explicitly reject formats with `application/xml;q=0`.
3. **`Vary: Accept` header**: tells HTTP caches that the response varies by the Accept header, preventing incorrect cached responses.
4. **Empty Accept = accept anything**: per RFC 7231, a missing Accept header means the client accepts any media type.
5. **Encoder registry pattern**: adding a new format (e.g., YAML, MessagePack) requires only adding an entry to the `encoders` slice.'''),

    ("go_deep/ndjson_streaming", r'''How do I implement streaming JSON responses (newline-delimited JSON / ndjson) in Go for large datasets?''', r'''<think>
NDJSON (Newline Delimited JSON) is a format where each line is a complete JSON object,
separated by newlines. It's perfect for streaming large datasets because:
1. The client can parse each line as it arrives.
2. Memory usage is O(1) on both sides — no need to buffer the entire response.
3. It works over plain HTTP without WebSockets or SSE.

Content-Type for NDJSON is application/x-ndjson.

Implementation:
- Server: use json.Encoder to write one object per line, flush after each line.
- Client: use bufio.Scanner or json.Decoder to read one object per line.

Key concerns:
- Must flush after each line so the client receives data incrementally.
- Set appropriate headers before writing (Content-Type, no Content-Length since streaming).
- Handle client disconnection via context.
- For large datasets from a database, stream rows directly — don't load all into memory.

I should show both the server and client side, plus error handling in the stream
(how to signal errors when you're mid-stream and can't change the status code).

For errors mid-stream, a common pattern is to send an error object as the last line:
  {"error": "database timeout", "partial": true}
</think>

Here is a complete NDJSON streaming implementation:

```go
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"
)

// ---------- Server ----------

type Record struct {
	ID        int       `json:"id"`
	Name      string    `json:"name"`
	CreatedAt time.Time `json:"created_at"`
}

type StreamError struct {
	Error   string `json:"error"`
	Partial bool   `json:"partial"`
}

// StreamHandler sends records as NDJSON.
func StreamHandler(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming not supported", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/x-ndjson")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	// No Content-Length — streaming response.

	enc := json.NewEncoder(w)

	// Simulate streaming 1000 records from a database cursor.
	for i := 1; i <= 1000; i++ {
		// Check for client disconnect.
		if r.Context().Err() != nil {
			log.Printf("client disconnected at record %d", i)
			return
		}

		record := Record{
			ID:        i,
			Name:      fmt.Sprintf("record-%d", i),
			CreatedAt: time.Now(),
		}

		// Encode writes JSON + newline (json.Encoder appends \n by default).
		if err := enc.Encode(record); err != nil {
			log.Printf("encode error at record %d: %v", i, err)
			return
		}

		// Flush pushes the data to the client immediately.
		flusher.Flush()

		// Simulate database cursor latency.
		time.Sleep(10 * time.Millisecond)
	}
}

// StreamWithErrors shows how to signal errors mid-stream.
func StreamWithErrors(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming not supported", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/x-ndjson")
	enc := json.NewEncoder(w)

	for i := 1; i <= 100; i++ {
		if r.Context().Err() != nil {
			return
		}

		// Simulate an error at record 50.
		if i == 50 {
			enc.Encode(StreamError{
				Error:   "database connection lost",
				Partial: true,
			})
			flusher.Flush()
			return
		}

		enc.Encode(Record{ID: i, Name: fmt.Sprintf("item-%d", i), CreatedAt: time.Now()})
		flusher.Flush()
	}
}

// ---------- Client ----------

// StreamRecords reads NDJSON from a URL, calling fn for each record.
func StreamRecords(ctx context.Context, url string, fn func(Record) error) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/x-ndjson")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return fmt.Errorf("status %d: %s", resp.StatusCode, body)
	}

	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024) // Up to 1MB per line

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}

		// Check for error object.
		var errObj StreamError
		if json.Unmarshal(line, &errObj) == nil && errObj.Error != "" {
			return fmt.Errorf("stream error: %s (partial=%v)", errObj.Error, errObj.Partial)
		}

		var record Record
		if err := json.Unmarshal(line, &record); err != nil {
			return fmt.Errorf("decode line: %w", err)
		}

		if err := fn(record); err != nil {
			return err // Caller wants to stop.
		}
	}

	return scanner.Err()
}

// ---------- Main ----------

func main() {
	// Server
	mux := http.NewServeMux()
	mux.HandleFunc("GET /stream", StreamHandler)
	mux.HandleFunc("GET /stream-errors", StreamWithErrors)

	go func() {
		log.Println("server on :8080")
		log.Fatal(http.ListenAndServe(":8080", mux))
	}()
	time.Sleep(100 * time.Millisecond)

	// Client
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	count := 0
	err := StreamRecords(ctx, "http://localhost:8080/stream", func(r Record) error {
		count++
		if count%100 == 0 {
			log.Printf("received %d records (latest: %s)", count, r.Name)
		}
		return nil
	})

	if err != nil {
		log.Printf("stream ended with error: %v", err)
	}
	log.Printf("total records received: %d", count)
}
```

Why NDJSON over alternatives:

| Format | Memory | Parsing | Browser Support | Bidirectional |
|---|---|---|---|---|
| JSON array | O(n) — must buffer all | Parse after complete | Native | No |
| NDJSON | O(1) — line at a time | Parse incrementally | fetch + reader | No |
| SSE | O(1) | EventSource API | Native | No |
| WebSocket | O(1) | Per-message | Native | Yes |

Key implementation details:

1. **`json.Encoder` appends `\n` automatically** — each `Encode()` call produces one NDJSON line.
2. **`Flush()` after every line** ensures the client receives data immediately, not buffered until the handler returns.
3. **Error signaling mid-stream**: since the status code (200) is already sent, errors must be encoded as a special JSON object in the stream.
4. **`bufio.Scanner` on the client** reads line-by-line, keeping memory usage constant regardless of stream length.
5. **Context cancellation** lets the client stop the stream early, and the server detects it via `r.Context().Err()`.'''),

    ("go_deep/multipart_upload_progress", r'''How do I handle multipart file uploads in Go with progress tracking and size limits?''', r'''<think>
Multipart file uploads in Go use the multipart package. The standard approach is
r.ParseMultipartForm(maxMemory), but for large files with progress tracking, we need
a different approach:
1. Don't use ParseMultipartForm — it buffers the entire upload into memory/temp files.
2. Instead, use multipart.Reader to stream the parts.
3. Wrap the reader with a progress-tracking io.Reader.
4. Set MaxBytesReader to limit total upload size.

For progress tracking:
- Use a custom io.Reader that counts bytes and reports progress.
- Progress can be sent via SSE to the client, or stored in a shared map for polling.
- For simplicity, I'll use a progress channel and a separate SSE endpoint.

Size limiting:
- http.MaxBytesReader on the request body limits total upload size.
- Individual file size limits can be enforced in the streaming reader.

Important considerations:
- Temp file handling: for large files, write to disk as we stream, not into memory.
- Content-Disposition header on each part tells us the filename.
- Multiple files: iterate over parts with reader.NextPart().
- Cleanup: if the upload fails partway, delete any files already written.
</think>

Here is a multipart upload handler with progress tracking:

```go
package main

import (
	"fmt"
	"io"
	"log"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// ---------- Progress tracker ----------

type UploadProgress struct {
	UploadID     string `json:"upload_id"`
	Filename     string `json:"filename"`
	BytesRead    int64  `json:"bytes_read"`
	TotalBytes   int64  `json:"total_bytes"` // -1 if unknown
	PercentDone  int    `json:"percent_done"`
	Complete     bool   `json:"complete"`
	Error        string `json:"error,omitempty"`
}

type ProgressStore struct {
	mu       sync.RWMutex
	uploads  map[string]*UploadProgress
}

func NewProgressStore() *ProgressStore {
	return &ProgressStore{uploads: make(map[string]*UploadProgress)}
}

func (ps *ProgressStore) Set(p *UploadProgress) {
	ps.mu.Lock()
	ps.uploads[p.UploadID] = p
	ps.mu.Unlock()
}

func (ps *ProgressStore) Get(id string) (*UploadProgress, bool) {
	ps.mu.RLock()
	defer ps.mu.RUnlock()
	p, ok := ps.uploads[id]
	return p, ok
}

// ProgressReader wraps an io.Reader and reports bytes read.
type ProgressReader struct {
	reader    io.Reader
	bytesRead int64
	onRead    func(bytesRead int64)
}

func (pr *ProgressReader) Read(p []byte) (int, error) {
	n, err := pr.reader.Read(p)
	pr.bytesRead += int64(n)
	if pr.onRead != nil {
		pr.onRead(pr.bytesRead)
	}
	return n, err
}

// ---------- Upload handler ----------

const (
	maxUploadSize  = 100 << 20 // 100 MB total
	maxFileSize    = 50 << 20  // 50 MB per file
	uploadDir      = "./uploads"
)

func uploadHandler(store *ProgressStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", http.StatusMethodNotAllowed)
			return
		}

		// Limit total request body size.
		r.Body = http.MaxBytesReader(w, r.Body, maxUploadSize)

		uploadID := r.Header.Get("X-Upload-ID")
		if uploadID == "" {
			uploadID = fmt.Sprintf("%d", time.Now().UnixNano())
		}
		totalBytes := r.ContentLength // May be -1.

		contentType := r.Header.Get("Content-Type")
		if contentType == "" {
			http.Error(w, "missing Content-Type", http.StatusBadRequest)
			return
		}

		// Parse the boundary from Content-Type.
		mr, err := r.MultipartReader()
		if err != nil {
			http.Error(w, "not a multipart request: "+err.Error(), http.StatusBadRequest)
			return
		}

		os.MkdirAll(uploadDir, 0o755)
		var savedFiles []string

		// Cleanup on error.
		cleanup := func() {
			for _, f := range savedFiles {
				os.Remove(f)
			}
		}

		for {
			part, err := mr.NextPart()
			if err == io.EOF {
				break // No more parts.
			}
			if err != nil {
				cleanup()
				http.Error(w, "read part: "+err.Error(), http.StatusBadRequest)
				return
			}

			// Skip non-file parts (form fields).
			if part.FileName() == "" {
				part.Close()
				continue
			}

			filename := filepath.Base(part.FileName()) // Sanitize.
			destPath := filepath.Join(uploadDir, filename)

			progress := &UploadProgress{
				UploadID:   uploadID,
				Filename:   filename,
				TotalBytes: totalBytes,
			}
			store.Set(progress)

			// Stream the file to disk with progress tracking.
			if err := saveFile(part, destPath, maxFileSize, func(bytesRead int64) {
				progress.BytesRead = bytesRead
				if totalBytes > 0 {
					progress.PercentDone = int(bytesRead * 100 / totalBytes)
				}
				store.Set(progress)
			}); err != nil {
				progress.Error = err.Error()
				store.Set(progress)
				part.Close()
				cleanup()
				http.Error(w, err.Error(), http.StatusRequestEntityTooLarge)
				return
			}

			part.Close()
			savedFiles = append(savedFiles, destPath)
			log.Printf("saved %s (%d bytes)", destPath, progress.BytesRead)
		}

		// Mark complete.
		store.Set(&UploadProgress{
			UploadID:    uploadID,
			Complete:    true,
			PercentDone: 100,
		})

		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"upload_id":"%s","files":%d,"status":"complete"}`+"\n",
			uploadID, len(savedFiles))
	}
}

func saveFile(src io.Reader, destPath string, maxSize int64, onProgress func(int64)) error {
	f, err := os.Create(destPath)
	if err != nil {
		return fmt.Errorf("create file: %w", err)
	}
	defer f.Close()

	pr := &ProgressReader{
		reader: io.LimitReader(src, maxSize+1), // +1 to detect overflow.
		onRead: onProgress,
	}

	n, err := io.Copy(f, pr)
	if err != nil {
		os.Remove(destPath)
		return fmt.Errorf("write file: %w", err)
	}
	if n > maxSize {
		os.Remove(destPath)
		return fmt.Errorf("file %s exceeds %d byte limit", filepath.Base(destPath), maxSize)
	}

	return nil
}

// ---------- Progress polling endpoint ----------

func progressHandler(store *ProgressStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.URL.Query().Get("id")
		if id == "" {
			http.Error(w, "missing ?id=", http.StatusBadRequest)
			return
		}

		progress, ok := store.Get(id)
		if !ok {
			http.Error(w, "unknown upload", http.StatusNotFound)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"upload_id":"%s","filename":"%s","bytes_read":%d,"percent":%d,"complete":%v}`+"\n",
			progress.UploadID, progress.Filename, progress.BytesRead,
			progress.PercentDone, progress.Complete)
	}
}

func main() {
	store := NewProgressStore()

	http.HandleFunc("/upload", uploadHandler(store))
	http.HandleFunc("/progress", progressHandler(store))

	log.Println("upload server on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}

// Test:
// curl -X POST -F "file=@largefile.bin" -H "X-Upload-ID: test123" localhost:8080/upload
// curl "localhost:8080/progress?id=test123"
```

Key design choices:

1. **`r.MultipartReader()` instead of `ParseMultipartForm()`**: streams parts one at a time instead of buffering the entire upload into memory or temp files.
2. **`io.LimitReader(src, maxSize+1)`**: the +1 trick lets us detect overflow — if we read exactly `maxSize+1` bytes, the file exceeds the limit. Reading exactly `maxSize` bytes is fine.
3. **`ProgressReader`** wraps the reader and calls a callback on every `Read()`. The callback updates the shared progress store.
4. **`filepath.Base(part.FileName())`** sanitizes the filename to prevent path traversal attacks (e.g., `../../etc/passwd`).
5. **Cleanup on error**: if a multi-file upload fails on file 3, files 1 and 2 are deleted to avoid orphans.
6. **Polling endpoint** for progress — simpler than SSE for most use cases. The client polls `/progress?id=X` periodically.'''),

    ("go_deep/etag_caching", r'''How do I implement HTTP response caching with ETag and Last-Modified headers in a Go server?''', r'''<think>
HTTP caching with ETags and Last-Modified involves:
1. On first response: server sends ETag and/or Last-Modified headers.
2. On subsequent requests: client sends If-None-Match (ETag) or If-Modified-Since.
3. Server checks: if content hasn't changed, return 304 Not Modified (no body).

ETag is a hash or version identifier of the content. Two types:
- Strong ETag: exact byte-for-byte match (e.g., "abc123")
- Weak ETag: semantic equivalence (e.g., W/"abc123")

Implementation in Go:
- For static content: use http.ServeFile/http.FileServer which handle this automatically.
- For dynamic content: we need to compute ETags and check conditional headers ourselves.

Computing ETags for dynamic content:
- Option 1: Hash the response body (SHA-256 or xxHash). Requires buffering.
- Option 2: Use a version number or last-modified timestamp from the data source.
- Option 3: Content-based ETag from database record version.

The tricky part is that we need to compute the ETag BEFORE writing the response to
check If-None-Match. This means we either:
1. Buffer the response, compute ETag, check conditional, then write (or 304).
2. Use a pre-computed ETag from the data source.

Option 2 is better for performance. For a database-backed API, the record's updated_at
timestamp or version column works perfectly.

I should show both approaches: the middleware approach that buffers and hashes, and
the handler-level approach using pre-computed values.
</think>

Here is HTTP caching with ETag and Last-Modified:

```go
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"
)

// ---------- Approach 1: Handler-level with pre-computed ETag ----------

type Article struct {
	ID        int       `json:"id"`
	Title     string    `json:"title"`
	Body      string    `json:"body"`
	Version   int       `json:"version"`
	UpdatedAt time.Time `json:"updated_at"`
}

// Simulated database.
var articles = map[int]*Article{
	1: {
		ID: 1, Title: "Hello World", Body: "Content here.",
		Version: 3, UpdatedAt: time.Date(2024, 1, 15, 10, 30, 0, 0, time.UTC),
	},
}

func articleHandler(w http.ResponseWriter, r *http.Request) {
	article, ok := articles[1]
	if !ok {
		http.Error(w, "not found", http.StatusNotFound)
		return
	}

	// Compute ETag from version (cheap, no serialization needed).
	etag := fmt.Sprintf(`"%d-%d"`, article.ID, article.Version)
	lastModified := article.UpdatedAt

	// Check If-None-Match (ETag).
	if match := r.Header.Get("If-None-Match"); match != "" {
		if etagMatch(match, etag) {
			w.WriteHeader(http.StatusNotModified)
			return
		}
	}

	// Check If-Modified-Since.
	if ims := r.Header.Get("If-Modified-Since"); ims != "" {
		if t, err := http.ParseTime(ims); err == nil {
			if !lastModified.After(t) {
				w.WriteHeader(http.StatusNotModified)
				return
			}
		}
	}

	// Set caching headers.
	w.Header().Set("ETag", etag)
	w.Header().Set("Last-Modified", lastModified.UTC().Format(http.TimeFormat))
	w.Header().Set("Cache-Control", "private, max-age=60") // Cache for 60s, revalidate after.
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(article)
}

// etagMatch checks if the client's If-None-Match contains our ETag.
func etagMatch(header, etag string) bool {
	if header == "*" {
		return true
	}
	// If-None-Match can contain multiple ETags: "abc", "def"
	for _, candidate := range strings.Split(header, ",") {
		candidate = strings.TrimSpace(candidate)
		if candidate == etag {
			return true
		}
		// Handle weak comparison: W/"abc" matches "abc".
		if strings.TrimPrefix(candidate, "W/") == strings.TrimPrefix(etag, "W/") {
			return true
		}
	}
	return false
}

// ---------- Approach 2: Middleware with content hashing ----------

type bufferedWriter struct {
	http.ResponseWriter
	buf    []byte
	status int
	wrote  bool
}

func (bw *bufferedWriter) WriteHeader(code int) {
	bw.status = code
}

func (bw *bufferedWriter) Write(b []byte) (int, error) {
	bw.buf = append(bw.buf, b...)
	return len(b), nil
}

// ETagMiddleware computes ETags by hashing response bodies.
// Use for responses that are expensive to generate but small enough to buffer.
func ETagMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Only apply to GET/HEAD.
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			next.ServeHTTP(w, r)
			return
		}

		bw := &bufferedWriter{
			ResponseWriter: w,
			status:         http.StatusOK,
		}

		next.ServeHTTP(bw, r)

		// Don't cache error responses.
		if bw.status >= 400 {
			w.WriteHeader(bw.status)
			w.Write(bw.buf)
			return
		}

		// Compute ETag from content hash.
		hash := sha256.Sum256(bw.buf)
		etag := `"` + hex.EncodeToString(hash[:8]) + `"` // First 8 bytes = 16 hex chars

		// Check If-None-Match.
		if match := r.Header.Get("If-None-Match"); match != "" {
			if etagMatch(match, etag) {
				w.Header().Set("ETag", etag)
				w.WriteHeader(http.StatusNotModified)
				return
			}
		}

		// Send full response with ETag.
		w.Header().Set("ETag", etag)
		w.Header().Set("Cache-Control", "no-cache") // Always revalidate.
		w.WriteHeader(bw.status)
		w.Write(bw.buf)
	})
}

func main() {
	mux := http.NewServeMux()

	// Approach 1: Handler-level caching (preferred for DB-backed content).
	mux.HandleFunc("GET /articles/1", articleHandler)

	// Approach 2: Middleware-level caching (for any handler).
	mux.HandleFunc("GET /computed", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"time":   time.Now().Truncate(time.Minute).Format(time.RFC3339),
			"data":   "this changes every minute",
		})
	})

	handler := ETagMiddleware(mux)

	log.Println("server on :8080")
	log.Fatal(http.ListenAndServe(":8080", handler))
}

// Test:
// First request:
//   curl -v localhost:8080/articles/1
//   → 200 OK, ETag: "1-3"
//
// Second request with ETag:
//   curl -v -H 'If-None-Match: "1-3"' localhost:8080/articles/1
//   → 304 Not Modified (no body)
```

Two approaches compared:

| Aspect | Handler-level (Approach 1) | Middleware (Approach 2) |
|---|---|---|
| ETag source | DB version/timestamp | SHA-256 of response body |
| Performance | No buffering needed | Must buffer entire response |
| Accuracy | Exact (version-based) | Content-based (always correct) |
| Best for | DB-backed APIs | Static/computed content |
| Setup effort | Per-handler | One middleware for all routes |

Key implementation details:

1. **`Cache-Control: no-cache`** does NOT mean "don't cache" — it means "cache but revalidate every time." Use `no-store` to truly prevent caching.
2. **ETag format**: strong ETags are `"value"`, weak ETags are `W/"value"`. Strong means byte-for-byte identical; weak means semantically equivalent.
3. **`If-None-Match` can contain multiple ETags** separated by commas — the server must check all of them.
4. **304 responses must not include a body** but should include the ETag, Cache-Control, and other metadata headers.
5. **Handler-level ETags from DB versions** are far more efficient than hashing — you skip serialization entirely on cache hits.'''),

    ("go_deep/health_check_dependencies", r'''How do I build a health check endpoint in Go that checks all dependencies (database, cache, external APIs) and returns structured health status?''', r'''<think>
A proper health check endpoint goes beyond returning 200 OK. It should:
1. Check each dependency (DB, Redis, external APIs, disk space, etc.).
2. Return structured results showing which dependencies are healthy/unhealthy.
3. Have two levels: liveness (is the process alive?) and readiness (can it serve traffic?).
4. Not take too long — each check should have a timeout.
5. Not be too aggressive — don't hammer dependencies with health checks.

Kubernetes uses two probes:
- /healthz (liveness): is the process alive? If not, restart it.
- /readyz (readiness): can it serve traffic? If not, remove from load balancer.

Design:
- Define a Checker interface with a Name() and Check(ctx) method.
- Register multiple checkers.
- The health endpoint runs all checks concurrently with a timeout.
- Returns 200 if all pass, 503 if any fail.
- Structured JSON response with per-dependency status.

I should also show caching of health check results — you don't want every health check
probe to hammer the database. Cache the result for a few seconds.

For liveness: just return 200. No dependency checks — liveness means "the process is not
deadlocked."

For readiness: check all dependencies. This determines if the pod should receive traffic.
</think>

Here is a comprehensive health check system:

```go
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"log"
	"net"
	"net/http"
	"sync"
	"time"
)

// ---------- Health check types ----------

type Status string

const (
	StatusUp   Status = "up"
	StatusDown Status = "down"
)

type CheckResult struct {
	Name     string        `json:"name"`
	Status   Status        `json:"status"`
	Duration time.Duration `json:"duration_ms"`
	Error    string        `json:"error,omitempty"`
	Details  any           `json:"details,omitempty"`
}

func (cr CheckResult) MarshalJSON() ([]byte, error) {
	type Alias CheckResult
	return json.Marshal(struct {
		Alias
		Duration int64 `json:"duration_ms"`
	}{
		Alias:    Alias(cr),
		Duration: cr.Duration.Milliseconds(),
	})
}

type HealthResponse struct {
	Status  Status        `json:"status"`
	Checks  []CheckResult `json:"checks"`
	Uptime  string        `json:"uptime"`
}

// Checker is implemented by each dependency.
type Checker interface {
	Name() string
	Check(ctx context.Context) error
}

// ---------- Concrete checkers ----------

// DatabaseChecker pings a SQL database.
type DatabaseChecker struct {
	db *sql.DB
}

func (c *DatabaseChecker) Name() string { return "database" }

func (c *DatabaseChecker) Check(ctx context.Context) error {
	return c.db.PingContext(ctx)
}

// TCPChecker checks if a TCP service is reachable.
type TCPChecker struct {
	name    string
	address string
	timeout time.Duration
}

func (c *TCPChecker) Name() string { return c.name }

func (c *TCPChecker) Check(ctx context.Context) error {
	d := net.Dialer{Timeout: c.timeout}
	conn, err := d.DialContext(ctx, "tcp", c.address)
	if err != nil {
		return err
	}
	conn.Close()
	return nil
}

// HTTPChecker checks an HTTP endpoint.
type HTTPChecker struct {
	name   string
	url    string
	client *http.Client
}

func (c *HTTPChecker) Name() string { return c.name }

func (c *HTTPChecker) Check(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.url, nil)
	if err != nil {
		return err
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return err
	}
	resp.Body.Close()
	if resp.StatusCode >= 500 {
		return &CheckError{Code: resp.StatusCode}
	}
	return nil
}

type CheckError struct{ Code int }

func (e *CheckError) Error() string {
	return http.StatusText(e.Code)
}

// CustomChecker wraps a function as a Checker.
type CustomChecker struct {
	name  string
	check func(ctx context.Context) error
}

func (c *CustomChecker) Name() string                       { return c.name }
func (c *CustomChecker) Check(ctx context.Context) error    { return c.check(ctx) }

// ---------- Health service ----------

type HealthService struct {
	checkers  []Checker
	startTime time.Time
	timeout   time.Duration

	// Cached result to avoid hammering dependencies.
	mu         sync.RWMutex
	cached     *HealthResponse
	cachedAt   time.Time
	cacheTTL   time.Duration
}

func NewHealthService(timeout, cacheTTL time.Duration) *HealthService {
	return &HealthService{
		startTime: time.Now(),
		timeout:   timeout,
		cacheTTL:  cacheTTL,
	}
}

func (hs *HealthService) Register(c Checker) {
	hs.checkers = append(hs.checkers, c)
}

func (hs *HealthService) Check(ctx context.Context) *HealthResponse {
	// Return cached result if fresh.
	hs.mu.RLock()
	if hs.cached != nil && time.Since(hs.cachedAt) < hs.cacheTTL {
		result := hs.cached
		hs.mu.RUnlock()
		return result
	}
	hs.mu.RUnlock()

	ctx, cancel := context.WithTimeout(ctx, hs.timeout)
	defer cancel()

	results := make([]CheckResult, len(hs.checkers))
	var wg sync.WaitGroup

	// Run all checks concurrently.
	for i, checker := range hs.checkers {
		wg.Add(1)
		go func(i int, c Checker) {
			defer wg.Done()
			start := time.Now()
			err := c.Check(ctx)
			duration := time.Since(start)

			result := CheckResult{
				Name:     c.Name(),
				Status:   StatusUp,
				Duration: duration,
			}
			if err != nil {
				result.Status = StatusDown
				result.Error = err.Error()
			}
			results[i] = result
		}(i, checker)
	}

	wg.Wait()

	overall := StatusUp
	for _, r := range results {
		if r.Status == StatusDown {
			overall = StatusDown
			break
		}
	}

	response := &HealthResponse{
		Status: overall,
		Checks: results,
		Uptime: time.Since(hs.startTime).Truncate(time.Second).String(),
	}

	// Cache the result.
	hs.mu.Lock()
	hs.cached = response
	hs.cachedAt = time.Now()
	hs.mu.Unlock()

	return response
}

// ---------- HTTP handlers ----------

func (hs *HealthService) LivenessHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// Liveness = "is the process alive?" No dependency checks.
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{
			"status": "up",
			"uptime": time.Since(hs.startTime).Truncate(time.Second).String(),
		})
	}
}

func (hs *HealthService) ReadinessHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		result := hs.Check(r.Context())

		w.Header().Set("Content-Type", "application/json")
		if result.Status == StatusDown {
			w.WriteHeader(http.StatusServiceUnavailable)
		} else {
			w.WriteHeader(http.StatusOK)
		}

		enc := json.NewEncoder(w)
		enc.SetIndent("", "  ")
		enc.Encode(result)
	}
}

// ---------- Main ----------

func main() {
	health := NewHealthService(
		5*time.Second,  // Per-check timeout
		10*time.Second, // Cache results for 10 seconds
	)

	// Register dependency checks.
	health.Register(&TCPChecker{
		name:    "redis",
		address: "localhost:6379",
		timeout: 2 * time.Second,
	})

	health.Register(&HTTPChecker{
		name:   "payment-api",
		url:    "https://api.payment.example.com/health",
		client: &http.Client{Timeout: 3 * time.Second},
	})

	health.Register(&CustomChecker{
		name: "disk-space",
		check: func(ctx context.Context) error {
			// Check available disk space, return error if < 100MB.
			return nil // Placeholder.
		},
	})

	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", health.LivenessHandler())
	mux.HandleFunc("GET /readyz", health.ReadinessHandler())

	log.Println("server on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}

// Response example:
// GET /readyz
// {
//   "status": "up",
//   "checks": [
//     {"name": "redis", "status": "up", "duration_ms": 1},
//     {"name": "payment-api", "status": "up", "duration_ms": 45},
//     {"name": "disk-space", "status": "up", "duration_ms": 0}
//   ],
//   "uptime": "2h15m30s"
// }
```

Design rationale:

1. **Liveness vs. Readiness separation**: liveness (`/healthz`) checks only if the process is alive — never check dependencies here, or a DB outage causes restarts which makes things worse. Readiness (`/readyz`) checks dependencies and controls load balancer routing.
2. **Concurrent checks**: all dependencies are checked in parallel, bounded by a single timeout context. A slow Redis check does not delay the database check.
3. **Result caching** (10s TTL): prevents health check probes from hammering dependencies. Kubernetes probes typically fire every 10-30 seconds; caching ensures at most one real check per cycle.
4. **Checker interface**: adding a new dependency requires only implementing `Name()` and `Check(ctx)`. No changes to the health service itself.
5. **503 on failure**: the readiness endpoint returns 503 when any check fails, which tells Kubernetes to remove the pod from the Service's endpoint list.'''),
]
