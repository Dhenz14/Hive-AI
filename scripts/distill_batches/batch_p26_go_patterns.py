"""Go patterns — concurrency, interfaces, error handling, project structure."""

PAIRS = [
    (
        "go/concurrency-patterns",
        "Show Go concurrency patterns: goroutines, channels, select, context cancellation, worker pools, and fan-out/fan-in.",
        '''Go concurrency patterns for production systems:

```go
package main

import (
    "context"
    "fmt"
    "sync"
    "time"
)

// --- Worker Pool ---

func workerPool(ctx context.Context, jobs <-chan int, numWorkers int) <-chan int {
    results := make(chan int, numWorkers)
    var wg sync.WaitGroup

    for i := 0; i < numWorkers; i++ {
        wg.Add(1)
        go func(id int) {
            defer wg.Done()
            for {
                select {
                case job, ok := <-jobs:
                    if !ok {
                        return // Channel closed
                    }
                    result := process(job)
                    select {
                    case results <- result:
                    case <-ctx.Done():
                        return
                    }
                case <-ctx.Done():
                    return
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

// --- Fan-out / Fan-in ---

func fanOut(ctx context.Context, input <-chan int, numWorkers int) []<-chan int {
    outputs := make([]<-chan int, numWorkers)
    for i := 0; i < numWorkers; i++ {
        outputs[i] = worker(ctx, input)
    }
    return outputs
}

func fanIn(ctx context.Context, channels ...<-chan int) <-chan int {
    merged := make(chan int)
    var wg sync.WaitGroup

    for _, ch := range channels {
        wg.Add(1)
        go func(c <-chan int) {
            defer wg.Done()
            for {
                select {
                case v, ok := <-c:
                    if !ok {
                        return
                    }
                    select {
                    case merged <- v:
                    case <-ctx.Done():
                        return
                    }
                case <-ctx.Done():
                    return
                }
            }
        }(ch)
    }

    go func() {
        wg.Wait()
        close(merged)
    }()

    return merged
}

// --- Pipeline with error handling ---

type Result struct {
    Value int
    Err   error
}

func pipeline(ctx context.Context, input []int) <-chan Result {
    out := make(chan Result)

    go func() {
        defer close(out)
        for _, v := range input {
            select {
            case <-ctx.Done():
                out <- Result{Err: ctx.Err()}
                return
            default:
                result, err := transform(v)
                out <- Result{Value: result, Err: err}
            }
        }
    }()

    return out
}

// --- Rate-limited operations ---

func rateLimited(ctx context.Context, items []string, rps int) error {
    ticker := time.NewTicker(time.Second / time.Duration(rps))
    defer ticker.Stop()

    for _, item := range items {
        select {
        case <-ticker.C:
            if err := processItem(ctx, item); err != nil {
                return fmt.Errorf("processing %s: %w", item, err)
            }
        case <-ctx.Done():
            return ctx.Err()
        }
    }
    return nil
}

// --- Semaphore pattern (limit concurrency) ---

func withConcurrencyLimit(ctx context.Context, items []string, limit int) error {
    sem := make(chan struct{}, limit)
    var wg sync.WaitGroup
    errCh := make(chan error, len(items))

    for _, item := range items {
        wg.Add(1)
        go func(item string) {
            defer wg.Done()

            select {
            case sem <- struct{}{}:
                defer func() { <-sem }()
            case <-ctx.Done():
                errCh <- ctx.Err()
                return
            }

            if err := processItem(ctx, item); err != nil {
                errCh <- err
            }
        }(item)
    }

    wg.Wait()
    close(errCh)

    // Collect errors
    var errs []error
    for err := range errCh {
        errs = append(errs, err)
    }
    if len(errs) > 0 {
        return fmt.Errorf("%d errors occurred, first: %w", len(errs), errs[0])
    }
    return nil
}

// --- errgroup (structured concurrency) ---

import "golang.org/x/sync/errgroup"

func fetchAll(ctx context.Context, urls []string) ([]string, error) {
    g, ctx := errgroup.WithContext(ctx)
    results := make([]string, len(urls))

    for i, url := range urls {
        i, url := i, url // Capture loop variables
        g.Go(func() error {
            body, err := fetch(ctx, url)
            if err != nil {
                return fmt.Errorf("fetching %s: %w", url, err)
            }
            results[i] = body
            return nil
        })
    }

    if err := g.Wait(); err != nil {
        return nil, err
    }
    return results, nil
}
```

Key patterns:
- **Worker pool** — fixed goroutines, jobs via channel, graceful shutdown
- **Fan-out/fan-in** — distribute work, merge results
- **Context cancellation** — propagate cancellation through goroutine trees
- **Semaphore** — buffered channel limits concurrency
- **errgroup** — structured concurrency with error propagation'''
    ),
    (
        "go/error-handling",
        "Show Go error handling best practices: error wrapping, sentinel errors, custom error types, and the errors package.",
        '''Go error handling patterns for robust applications:

```go
package main

import (
    "errors"
    "fmt"
    "net/http"
)

// --- Sentinel errors (package-level constants) ---

var (
    ErrNotFound     = errors.New("not found")
    ErrUnauthorized = errors.New("unauthorized")
    ErrConflict     = errors.New("conflict")
)

// --- Custom error types ---

type ValidationError struct {
    Field   string
    Message string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation error: %s - %s", e.Field, e.Message)
}

type HTTPError struct {
    StatusCode int
    Message    string
    Cause      error
}

func (e *HTTPError) Error() string {
    if e.Cause != nil {
        return fmt.Sprintf("HTTP %d: %s: %v", e.StatusCode, e.Message, e.Cause)
    }
    return fmt.Sprintf("HTTP %d: %s", e.StatusCode, e.Message)
}

func (e *HTTPError) Unwrap() error {
    return e.Cause
}

// --- Error wrapping (add context) ---

func GetUser(id string) (*User, error) {
    user, err := db.FindUser(id)
    if err != nil {
        if errors.Is(err, sql.ErrNoRows) {
            return nil, fmt.Errorf("user %s: %w", id, ErrNotFound)
        }
        return nil, fmt.Errorf("fetching user %s: %w", id, err)
    }
    return user, nil
}

// --- Error checking patterns ---

func handleRequest(w http.ResponseWriter, r *http.Request) {
    user, err := GetUser(r.URL.Query().Get("id"))
    if err != nil {
        // Check for sentinel errors
        if errors.Is(err, ErrNotFound) {
            http.Error(w, "User not found", http.StatusNotFound)
            return
        }
        if errors.Is(err, ErrUnauthorized) {
            http.Error(w, "Unauthorized", http.StatusUnauthorized)
            return
        }

        // Check for custom error types
        var validErr *ValidationError
        if errors.As(err, &validErr) {
            http.Error(w, validErr.Error(), http.StatusBadRequest)
            return
        }

        // Unknown error — log and return 500
        log.Printf("unexpected error: %v", err)
        http.Error(w, "Internal error", http.StatusInternalServerError)
        return
    }

    json.NewEncoder(w).Encode(user)
}

// --- Multi-error collection ---

type MultiError struct {
    Errors []error
}

func (e *MultiError) Error() string {
    msgs := make([]string, len(e.Errors))
    for i, err := range e.Errors {
        msgs[i] = err.Error()
    }
    return fmt.Sprintf("%d errors: [%s]", len(e.Errors), strings.Join(msgs, "; "))
}

func (e *MultiError) Add(err error) {
    if err != nil {
        e.Errors = append(e.Errors, err)
    }
}

func (e *MultiError) Err() error {
    if len(e.Errors) == 0 {
        return nil
    }
    return e
}

func validateUser(u *User) error {
    errs := &MultiError{}
    if u.Name == "" {
        errs.Add(&ValidationError{"name", "required"})
    }
    if u.Email == "" {
        errs.Add(&ValidationError{"email", "required"})
    }
    if u.Age < 0 || u.Age > 150 {
        errs.Add(&ValidationError{"age", "must be 0-150"})
    }
    return errs.Err()
}

// --- Middleware error handler ---

type AppHandler func(w http.ResponseWriter, r *http.Request) error

func errorHandler(h AppHandler) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        err := h(w, r)
        if err == nil {
            return
        }

        var httpErr *HTTPError
        if errors.As(err, &httpErr) {
            http.Error(w, httpErr.Message, httpErr.StatusCode)
            return
        }

        // Map domain errors to HTTP status
        switch {
        case errors.Is(err, ErrNotFound):
            http.Error(w, "Not found", 404)
        case errors.Is(err, ErrUnauthorized):
            http.Error(w, "Unauthorized", 401)
        case errors.Is(err, ErrConflict):
            http.Error(w, "Conflict", 409)
        default:
            log.Printf("unhandled error: %+v", err)
            http.Error(w, "Internal error", 500)
        }
    }
}
```

Error handling rules:
1. **Always wrap with context**: `fmt.Errorf("doing X: %w", err)`
2. **Use sentinel errors** for expected conditions callers check with `errors.Is`
3. **Use custom types** when callers need error details via `errors.As`
4. **Don't log and return** — do one or the other
5. **Handle errors at the boundary** — middleware maps to HTTP/gRPC status'''
    ),
    (
        "go/interface-design",
        "Show Go interface design principles: small interfaces, interface segregation, dependency injection, and testing with mocks.",
        '''Go interface design for testable, maintainable code:

```go
package main

// --- Small, focused interfaces (Go idiom) ---

// BAD: large interface couples everything
type UserManager interface {
    GetUser(id string) (*User, error)
    CreateUser(u *User) error
    UpdateUser(u *User) error
    DeleteUser(id string) error
    ListUsers(filter Filter) ([]*User, error)
    SendEmail(to, subject, body string) error
    ValidateUser(u *User) error
    HashPassword(password string) (string, error)
}

// GOOD: small interfaces, composed as needed

type UserReader interface {
    GetUser(id string) (*User, error)
}

type UserWriter interface {
    CreateUser(u *User) error
    UpdateUser(u *User) error
}

type UserDeleter interface {
    DeleteUser(id string) error
}

// Compose interfaces
type UserStore interface {
    UserReader
    UserWriter
    UserDeleter
}

// Accept the smallest interface you need
func GetUserHandler(store UserReader) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        user, err := store.GetUser(r.URL.Query().Get("id"))
        if err != nil {
            http.Error(w, err.Error(), 500)
            return
        }
        json.NewEncoder(w).Encode(user)
    }
}

// --- Accept interfaces, return structs ---

type Logger interface {
    Info(msg string, fields ...any)
    Error(msg string, fields ...any)
}

type Notifier interface {
    Send(ctx context.Context, to string, message string) error
}

// Service accepts interfaces for testability
type OrderService struct {
    store    UserReader
    notifier Notifier
    logger   Logger
}

func NewOrderService(store UserReader, notifier Notifier, logger Logger) *OrderService {
    return &OrderService{store: store, notifier: notifier, logger: logger}
}

func (s *OrderService) PlaceOrder(ctx context.Context, userID string, items []Item) (*Order, error) {
    user, err := s.store.GetUser(userID)
    if err != nil {
        return nil, fmt.Errorf("getting user: %w", err)
    }

    order := &Order{UserID: userID, Items: items}
    // ... process order ...

    if err := s.notifier.Send(ctx, user.Email, "Order placed!"); err != nil {
        s.logger.Error("failed to notify", "user_id", userID, "error", err)
        // Don't fail the order for notification failure
    }

    return order, nil
}

// --- Testing with mock implementations ---

type MockUserStore struct {
    users map[string]*User
    err   error
}

func (m *MockUserStore) GetUser(id string) (*User, error) {
    if m.err != nil {
        return nil, m.err
    }
    user, ok := m.users[id]
    if !ok {
        return nil, ErrNotFound
    }
    return user, nil
}

type MockNotifier struct {
    sent []struct{ to, message string }
    err  error
}

func (m *MockNotifier) Send(_ context.Context, to, message string) error {
    if m.err != nil {
        return m.err
    }
    m.sent = append(m.sent, struct{ to, message string }{to, message})
    return nil
}

func TestPlaceOrder(t *testing.T) {
    store := &MockUserStore{
        users: map[string]*User{
            "user-1": {ID: "user-1", Email: "test@example.com"},
        },
    }
    notifier := &MockNotifier{}
    logger := &MockLogger{}

    svc := NewOrderService(store, notifier, logger)

    order, err := svc.PlaceOrder(context.Background(), "user-1", []Item{
        {SKU: "item-1", Qty: 2},
    })

    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }
    if order.UserID != "user-1" {
        t.Errorf("expected user-1, got %s", order.UserID)
    }
    if len(notifier.sent) != 1 {
        t.Errorf("expected 1 notification, got %d", len(notifier.sent))
    }
}

func TestPlaceOrder_UserNotFound(t *testing.T) {
    store := &MockUserStore{users: map[string]*User{}}
    svc := NewOrderService(store, &MockNotifier{}, &MockLogger{})

    _, err := svc.PlaceOrder(context.Background(), "unknown", nil)
    if !errors.Is(err, ErrNotFound) {
        t.Errorf("expected ErrNotFound, got %v", err)
    }
}
```

Go interface principles:
1. **Define interfaces where used** (consumer side), not where implemented
2. **Keep interfaces small** — 1-3 methods ideal
3. **Accept interfaces, return structs** — flexibility in, concrete out
4. **Implicit satisfaction** — no `implements` keyword, just match methods
5. **Test via interfaces** — mock only what you need'''
    ),
]
