"""Go — concurrency, error handling, interfaces, and HTTP patterns."""

PAIRS = [
    (
        "go/concurrency-patterns",
        "Show Go concurrency patterns: goroutines, channels, select, WaitGroup, and context cancellation.",
        '''Go concurrency patterns:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "sync"
    "time"
)

// --- Fan-out, fan-in ---

func fanOut(ctx context.Context, input <-chan int, workers int) <-chan int {
    results := make(chan int, workers)
    var wg sync.WaitGroup

    for i := 0; i < workers; i++ {
        wg.Add(1)
        go func(id int) {
            defer wg.Done()
            for val := range input {
                select {
                case <-ctx.Done():
                    return
                case results <- process(val):
                }
            }
        }(i)
    }

    go func() {
        wg.Wait()
        close(results)
    }()
    return results
}


// --- Pipeline pattern ---

func generate(ctx context.Context, nums ...int) <-chan int {
    out := make(chan int)
    go func() {
        defer close(out)
        for _, n := range nums {
            select {
            case <-ctx.Done():
                return
            case out <- n:
            }
        }
    }()
    return out
}

func square(ctx context.Context, in <-chan int) <-chan int {
    out := make(chan int)
    go func() {
        defer close(out)
        for n := range in {
            select {
            case <-ctx.Done():
                return
            case out <- n * n:
            }
        }
    }()
    return out
}

func merge(ctx context.Context, channels ...<-chan int) <-chan int {
    out := make(chan int)
    var wg sync.WaitGroup
    for _, ch := range channels {
        wg.Add(1)
        go func(c <-chan int) {
            defer wg.Done()
            for val := range c {
                select {
                case <-ctx.Done():
                    return
                case out <- val:
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


// --- Semaphore (bounded concurrency) ---

func processWithLimit(items []string, maxConcurrency int) []Result {
    sem := make(chan struct{}, maxConcurrency)
    results := make([]Result, len(items))
    var wg sync.WaitGroup

    for i, item := range items {
        wg.Add(1)
        sem <- struct{}{} // Acquire
        go func(idx int, val string) {
            defer wg.Done()
            defer func() { <-sem }() // Release
            results[idx] = doWork(val)
        }(i, item)
    }
    wg.Wait()
    return results
}


// --- Select with timeout ---

func fetchWithTimeout(ctx context.Context, url string) ([]byte, error) {
    ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel()

    resultCh := make(chan []byte, 1)
    errCh := make(chan error, 1)

    go func() {
        data, err := httpGet(ctx, url)
        if err != nil {
            errCh <- err
            return
        }
        resultCh <- data
    }()

    select {
    case data := <-resultCh:
        return data, nil
    case err := <-errCh:
        return nil, err
    case <-ctx.Done():
        return nil, ctx.Err()
    }
}


// --- Worker pool ---

type Job struct {
    ID   int
    Data string
}

type Result struct {
    JobID int
    Value string
    Err   error
}

func workerPool(ctx context.Context, jobs <-chan Job, numWorkers int) <-chan Result {
    results := make(chan Result, numWorkers)
    var wg sync.WaitGroup

    for i := 0; i < numWorkers; i++ {
        wg.Add(1)
        go func(workerID int) {
            defer wg.Done()
            for job := range jobs {
                select {
                case <-ctx.Done():
                    return
                default:
                    result := processJob(job)
                    results <- result
                }
            }
        }(i)
    }

    go func() {
        wg.Wait()
        close(results)
    }()
    return results
}


// --- ErrGroup (structured error propagation) ---

import "golang.org/x/sync/errgroup"

func fetchAll(ctx context.Context, urls []string) ([][]byte, error) {
    g, ctx := errgroup.WithContext(ctx)
    results := make([][]byte, len(urls))

    for i, url := range urls {
        i, url := i, url // Capture loop vars
        g.Go(func() error {
            data, err := httpGet(ctx, url)
            if err != nil {
                return fmt.Errorf("fetch %s: %w", url, err)
            }
            results[i] = data
            return nil
        })
    }

    if err := g.Wait(); err != nil {
        return nil, err
    }
    return results, nil
}
```

Go concurrency patterns:
1. **Fan-out/fan-in** — distribute work to goroutines, collect results
2. **Pipeline** — chain stages with channels (Unix pipe style)
3. **Context cancellation** — propagate cancellation through goroutine trees
4. **Semaphore** — buffered channel limits concurrent goroutines
5. **errgroup** — structured concurrency with first-error propagation'''
    ),
    (
        "go/http-patterns",
        "Show Go HTTP patterns: middleware, routing, JSON handling, graceful shutdown, and testing.",
        '''Go HTTP server patterns:

```go
package main

import (
    "context"
    "encoding/json"
    "fmt"
    "log/slog"
    "net/http"
    "os"
    "os/signal"
    "syscall"
    "time"
)

// --- Middleware chain ---

type Middleware func(http.Handler) http.Handler

func Chain(h http.Handler, middlewares ...Middleware) http.Handler {
    for i := len(middlewares) - 1; i >= 0; i-- {
        h = middlewares[i](h)
    }
    return h
}

func Logger(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        wrapped := &responseWriter{ResponseWriter: w, statusCode: 200}
        next.ServeHTTP(wrapped, r)
        slog.Info("request",
            "method", r.Method,
            "path", r.URL.Path,
            "status", wrapped.statusCode,
            "duration", time.Since(start),
        )
    })
}

func Recovery(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        defer func() {
            if err := recover(); err != nil {
                slog.Error("panic recovered", "error", err)
                http.Error(w, "Internal Server Error", http.StatusInternalServerError)
            }
        }()
        next.ServeHTTP(w, r)
    })
}

func CORS(origin string) Middleware {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            w.Header().Set("Access-Control-Allow-Origin", origin)
            w.Header().Set("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE")
            w.Header().Set("Access-Control-Allow-Headers", "Content-Type,Authorization")
            if r.Method == http.MethodOptions {
                w.WriteHeader(http.StatusNoContent)
                return
            }
            next.ServeHTTP(w, r)
        })
    }
}


// --- JSON helpers ---

func writeJSON(w http.ResponseWriter, status int, data any) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    json.NewEncoder(w).Encode(data)
}

func readJSON(r *http.Request, dst any) error {
    dec := json.NewDecoder(r.Body)
    dec.DisallowUnknownFields()
    if err := dec.Decode(dst); err != nil {
        return fmt.Errorf("invalid JSON: %w", err)
    }
    return nil
}

type APIError struct {
    Status  int    `json:"-"`
    Code    string `json:"code"`
    Message string `json:"message"`
}

func (e APIError) Error() string { return e.Message }

func writeError(w http.ResponseWriter, err error) {
    if apiErr, ok := err.(APIError); ok {
        writeJSON(w, apiErr.Status, apiErr)
    } else {
        writeJSON(w, 500, APIError{Code: "INTERNAL", Message: "Internal error"})
    }
}


// --- Handler with dependency injection ---

type Server struct {
    userRepo UserRepository
    logger   *slog.Logger
}

func (s *Server) handleGetUser(w http.ResponseWriter, r *http.Request) {
    id := r.PathValue("id") // Go 1.22+

    user, err := s.userRepo.FindByID(r.Context(), id)
    if err != nil {
        writeError(w, APIError{Status: 404, Code: "NOT_FOUND", Message: "User not found"})
        return
    }
    writeJSON(w, 200, user)
}

func (s *Server) handleCreateUser(w http.ResponseWriter, r *http.Request) {
    var input CreateUserInput
    if err := readJSON(r, &input); err != nil {
        writeError(w, APIError{Status: 400, Code: "INVALID_INPUT", Message: err.Error()})
        return
    }

    user, err := s.userRepo.Create(r.Context(), input)
    if err != nil {
        writeError(w, err)
        return
    }
    writeJSON(w, 201, user)
}


// --- Routes ---

func (s *Server) routes() http.Handler {
    mux := http.NewServeMux()

    mux.HandleFunc("GET /api/users/{id}", s.handleGetUser)
    mux.HandleFunc("POST /api/users", s.handleCreateUser)
    mux.HandleFunc("GET /api/health", func(w http.ResponseWriter, r *http.Request) {
        writeJSON(w, 200, map[string]string{"status": "ok"})
    })

    return Chain(mux, Recovery, Logger, CORS("*"))
}


// --- Graceful shutdown ---

func main() {
    srv := &Server{
        userRepo: NewPostgresUserRepo(db),
        logger:   slog.Default(),
    }

    httpServer := &http.Server{
        Addr:         ":8080",
        Handler:      srv.routes(),
        ReadTimeout:  10 * time.Second,
        WriteTimeout: 30 * time.Second,
        IdleTimeout:  60 * time.Second,
    }

    // Start server
    go func() {
        slog.Info("server starting", "addr", httpServer.Addr)
        if err := httpServer.ListenAndServe(); err != http.ErrServerClosed {
            slog.Error("server error", "err", err)
            os.Exit(1)
        }
    }()

    // Wait for shutdown signal
    quit := make(chan os.Signal, 1)
    signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
    <-quit

    slog.Info("shutting down")
    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()
    httpServer.Shutdown(ctx)
}
```

Go HTTP patterns:
1. **Middleware chain** — compose logging, recovery, CORS as handlers
2. **`http.NewServeMux`** — Go 1.22+ pattern matching with path params
3. **Dependency injection** — server struct holds repos, loggers
4. **Graceful shutdown** — signal handling + `server.Shutdown(ctx)`
5. **Structured errors** — `APIError` type for consistent error responses'''
    ),
    (
        "go/error-handling",
        "Show Go error handling patterns: custom errors, wrapping, sentinel errors, and error groups.",
        '''Go error handling patterns:

```go
package myapp

import (
    "errors"
    "fmt"
    "log/slog"
)

// --- Sentinel errors ---

var (
    ErrNotFound     = errors.New("not found")
    ErrUnauthorized = errors.New("unauthorized")
    ErrConflict     = errors.New("conflict")
    ErrValidation   = errors.New("validation error")
)


// --- Custom error type ---

type AppError struct {
    Code    string
    Message string
    Err     error  // Wrapped error
}

func (e *AppError) Error() string {
    if e.Err != nil {
        return fmt.Sprintf("%s: %v", e.Message, e.Err)
    }
    return e.Message
}

func (e *AppError) Unwrap() error { return e.Err }

func NewNotFound(resource, id string) error {
    return &AppError{
        Code:    "NOT_FOUND",
        Message: fmt.Sprintf("%s %s not found", resource, id),
        Err:     ErrNotFound,
    }
}

func NewValidation(field, reason string) error {
    return &AppError{
        Code:    "VALIDATION",
        Message: fmt.Sprintf("invalid %s: %s", field, reason),
        Err:     ErrValidation,
    }
}


// --- Error wrapping ---

func GetUser(ctx context.Context, id string) (*User, error) {
    user, err := db.FindUser(ctx, id)
    if err != nil {
        if errors.Is(err, sql.ErrNoRows) {
            return nil, NewNotFound("user", id)
        }
        return nil, fmt.Errorf("get user %s: %w", id, err)
    }
    return user, nil
}


// --- Error checking ---

func handleRequest(userID string) {
    user, err := GetUser(ctx, userID)
    if err != nil {
        // Check sentinel error
        if errors.Is(err, ErrNotFound) {
            respondNotFound(w)
            return
        }

        // Check error type
        var appErr *AppError
        if errors.As(err, &appErr) {
            respondError(w, appErr.Code, appErr.Message)
            return
        }

        // Unknown error
        slog.Error("unexpected error", "err", err)
        respondInternalError(w)
        return
    }
    respondJSON(w, user)
}


// --- Must pattern (panic on error, for init) ---

func must[T any](val T, err error) T {
    if err != nil {
        panic(err)
    }
    return val
}

// Usage (only in init/main, never in request handlers):
// config := must(loadConfig("config.yaml"))
// db := must(sql.Open("postgres", config.DatabaseURL))


// --- Multi-error collection ---

type ValidationErrors struct {
    Errors []FieldError
}

type FieldError struct {
    Field   string
    Message string
}

func (e *ValidationErrors) Error() string {
    return fmt.Sprintf("%d validation errors", len(e.Errors))
}

func (e *ValidationErrors) Add(field, message string) {
    e.Errors = append(e.Errors, FieldError{field, message})
}

func (e *ValidationErrors) HasErrors() bool {
    return len(e.Errors) > 0
}

func validateUser(input CreateUserInput) error {
    errs := &ValidationErrors{}

    if input.Name == "" {
        errs.Add("name", "required")
    }
    if len(input.Name) > 100 {
        errs.Add("name", "must be under 100 characters")
    }
    if !isValidEmail(input.Email) {
        errs.Add("email", "invalid format")
    }
    if len(input.Password) < 8 {
        errs.Add("password", "must be at least 8 characters")
    }

    if errs.HasErrors() {
        return errs
    }
    return nil
}


// --- Cleanup with defer ---

func processFile(path string) (err error) {
    f, err := os.Open(path)
    if err != nil {
        return fmt.Errorf("open %s: %w", path, err)
    }
    defer func() {
        if cerr := f.Close(); cerr != nil && err == nil {
            err = fmt.Errorf("close %s: %w", path, cerr)
        }
    }()

    // Process file...
    return nil
}
```

Go error patterns:
1. **Sentinel errors** — `var ErrNotFound = errors.New(...)` for comparison
2. **`fmt.Errorf("%w")`** — wrap errors to add context while preserving the chain
3. **`errors.Is`** — check error chain for sentinel values
4. **`errors.As`** — extract typed error from chain
5. **Named return** — `(err error)` with defer for cleanup error handling'''
    ),
]
"""
