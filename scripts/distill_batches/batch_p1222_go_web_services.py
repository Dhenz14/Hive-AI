"""
Go language training pairs - web services (net/http, Chi/Gin handlers, middleware, JSON APIs)
"""

pairs = [
    {
        "instruction": r'''Build a simple JSON REST API in Go using only the standard library net/http package with proper routing, JSON encoding/decoding, and error responses.''',
        "output": r'''Here is a clean REST API using Go 1.22+ enhanced ServeMux with method-based routing:

```go
package main

import (
	"encoding/json"
	"log"
	"net/http"
	"strconv"
	"sync"
)

type Todo struct {
	ID    int    `json:"id"`
	Title string `json:"title"`
	Done  bool   `json:"done"`
}

type TodoStore struct {
	mu     sync.RWMutex
	todos  map[int]Todo
	nextID int
}

func NewTodoStore() *TodoStore {
	return &TodoStore{todos: make(map[int]Todo), nextID: 1}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func (s *TodoStore) handleList(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	todos := make([]Todo, 0, len(s.todos))
	for _, t := range s.todos {
		todos = append(todos, t)
	}
	writeJSON(w, http.StatusOK, todos)
}

func (s *TodoStore) handleCreate(w http.ResponseWriter, r *http.Request) {
	var t Todo
	if err := json.NewDecoder(r.Body).Decode(&t); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON")
		return
	}
	if t.Title == "" {
		writeError(w, http.StatusBadRequest, "title is required")
		return
	}

	s.mu.Lock()
	t.ID = s.nextID
	s.nextID++
	s.todos[t.ID] = t
	s.mu.Unlock()

	writeJSON(w, http.StatusCreated, t)
}

func (s *TodoStore) handleGet(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.Atoi(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}

	s.mu.RLock()
	t, ok := s.todos[id]
	s.mu.RUnlock()

	if !ok {
		writeError(w, http.StatusNotFound, "todo not found")
		return
	}
	writeJSON(w, http.StatusOK, t)
}

func main() {
	store := NewTodoStore()
	mux := http.NewServeMux()

	// Go 1.22 pattern: "METHOD /path"
	mux.HandleFunc("GET /todos", store.handleList)
	mux.HandleFunc("POST /todos", store.handleCreate)
	mux.HandleFunc("GET /todos/{id}", store.handleGet)

	log.Println("listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}
```

Key points:
- Go 1.22 ServeMux supports method prefixes and path parameters via `{name}`
- `r.PathValue("id")` extracts named segments from the URL
- Always set Content-Type before WriteHeader
- Use sync.RWMutex for concurrent map access (RLock for reads, Lock for writes)
- json.NewDecoder streams from the body -- no need to read all bytes first'''
    },
    {
        "instruction": r'''<think>
The user wants to see Go middleware patterns. In Go, middleware is typically a function that takes an http.Handler and returns an http.Handler, forming a chain. This is the standard pattern used by the stdlib, Chi, and most Go routers. I should show logging, auth, and recovery middleware, plus how to compose them. The key insight is that middleware wraps handlers like layers of an onion.
</think>
Show me how to write and compose HTTP middleware in Go, including logging, authentication, and panic recovery.''',
        "output": r'''Middleware in Go follows the pattern: `func(http.Handler) http.Handler`. Stack them by nesting:

```go
package main

import (
	"log"
	"net/http"
	"strings"
	"time"
)

// Logging middleware -- records method, path, status, duration
func LoggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		// Wrap ResponseWriter to capture status code
		wrapped := &statusWriter{ResponseWriter: w, status: 200}
		next.ServeHTTP(wrapped, r)

		log.Printf("%s %s %d %v",
			r.Method, r.URL.Path, wrapped.status, time.Since(start))
	})
}

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) WriteHeader(code int) {
	w.status = code
	w.ResponseWriter.WriteHeader(code)
}

// Auth middleware -- checks Bearer token
func AuthMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		auth := r.Header.Get("Authorization")
		if !strings.HasPrefix(auth, "Bearer ") {
			http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}
		token := strings.TrimPrefix(auth, "Bearer ")
		if token != "secret-token" {
			http.Error(w, `{"error":"forbidden"}`, http.StatusForbidden)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// Recovery middleware -- catches panics and returns 500
func RecoveryMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if err := recover(); err != nil {
				log.Printf("panic recovered: %v", err)
				http.Error(w, `{"error":"internal server error"}`,
					http.StatusInternalServerError)
			}
		}()
		next.ServeHTTP(w, r)
	})
}

// Chain composes middleware in order (first applied = outermost)
func Chain(h http.Handler, mw ...func(http.Handler) http.Handler) http.Handler {
	for i := len(mw) - 1; i >= 0; i-- {
		h = mw[i](h)
	}
	return h
}

func main() {
	hello := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"message":"hello"}`))
	})

	// Public route: logging + recovery
	public := Chain(hello, LoggingMiddleware, RecoveryMiddleware)

	// Protected route: logging + recovery + auth
	protected := Chain(hello, LoggingMiddleware, RecoveryMiddleware, AuthMiddleware)

	mux := http.NewServeMux()
	mux.Handle("GET /public", public)
	mux.Handle("GET /private", protected)

	log.Fatal(http.ListenAndServe(":8080", mux))
}
```

The Chain helper applies middleware in reading order -- first argument is the outermost wrapper. Request flows: Recovery -> Logging -> Auth -> Handler. Response flows back out in reverse.'''
    },
    {
        "instruction": r'''How do I build a JSON API with the Chi router in Go, including route groups, URL parameters, and middleware?''',
        "output": r'''Chi is a lightweight router that is compatible with net/http and adds route groups, URL params, and inline middleware:

```go
package main

import (
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

type Article struct {
	ID        int       `json:"id"`
	Title     string    `json:"title"`
	Body      string    `json:"body"`
	CreatedAt time.Time `json:"created_at"`
}

var articles = []Article{
	{ID: 1, Title: "Getting started with Go", Body: "...", CreatedAt: time.Now()},
	{ID: 2, Title: "Chi router guide", Body: "...", CreatedAt: time.Now()},
}

func respond(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func listArticles(w http.ResponseWriter, r *http.Request) {
	respond(w, http.StatusOK, articles)
}

func getArticle(w http.ResponseWriter, r *http.Request) {
	idStr := chi.URLParam(r, "id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		respond(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	for _, a := range articles {
		if a.ID == id {
			respond(w, http.StatusOK, a)
			return
		}
	}
	respond(w, http.StatusNotFound, map[string]string{"error": "not found"})
}

func createArticle(w http.ResponseWriter, r *http.Request) {
	var a Article
	if err := json.NewDecoder(r.Body).Decode(&a); err != nil {
		respond(w, http.StatusBadRequest, map[string]string{"error": "bad json"})
		return
	}
	a.ID = len(articles) + 1
	a.CreatedAt = time.Now()
	articles = append(articles, a)
	respond(w, http.StatusCreated, a)
}

func main() {
	r := chi.NewRouter()

	// Global middleware
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(30 * time.Second))

	// Public routes
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("ok"))
	})

	// API route group with versioning
	r.Route("/api/v1", func(r chi.Router) {
		r.Route("/articles", func(r chi.Router) {
			r.Get("/", listArticles)
			r.Post("/", createArticle)
			r.Get("/{id}", getArticle)
		})
	})

	http.ListenAndServe(":8080", r)
}
```

Chi advantages over stdlib ServeMux:
- Route groups with shared middleware via r.Route and r.Group
- chi.URLParam for path parameters (works pre-Go 1.22)
- Built-in middleware: Logger, Recoverer, Timeout, Throttle, CORS
- Fully compatible with net/http -- handlers are standard http.HandlerFunc
- Mount sub-routers for modular applications'''
    },
    {
        "instruction": r'''Write a Go HTTP handler that validates JSON request bodies with struct tags and returns structured error responses.''',
        "output": r'''Use a validation helper that inspects struct fields and returns field-level errors:

```go
package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"regexp"
	"strings"
)

type CreateUserRequest struct {
	Name     string `json:"name" validate:"required,min=2,max=50"`
	Email    string `json:"email" validate:"required,email"`
	Age      int    `json:"age" validate:"required,min=18,max=120"`
	Password string `json:"password" validate:"required,min=8"`
}

type FieldError struct {
	Field   string `json:"field"`
	Message string `json:"message"`
}

type ErrorResponse struct {
	Errors []FieldError `json:"errors"`
}

var emailRe = regexp.MustCompile(`^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`)

func validateUser(u CreateUserRequest) []FieldError {
	var errs []FieldError

	name := strings.TrimSpace(u.Name)
	if name == "" {
		errs = append(errs, FieldError{"name", "is required"})
	} else if len(name) < 2 || len(name) > 50 {
		errs = append(errs, FieldError{"name", "must be 2-50 characters"})
	}

	if u.Email == "" {
		errs = append(errs, FieldError{"email", "is required"})
	} else if !emailRe.MatchString(u.Email) {
		errs = append(errs, FieldError{"email", "invalid format"})
	}

	if u.Age < 18 {
		errs = append(errs, FieldError{"age", "must be at least 18"})
	} else if u.Age > 120 {
		errs = append(errs, FieldError{"age", "must be at most 120"})
	}

	if len(u.Password) < 8 {
		errs = append(errs, FieldError{"password", "must be at least 8 characters"})
	}

	return errs
}

func createUserHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	var req CreateUserRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{
			"error": fmt.Sprintf("invalid JSON: %v", err),
		})
		return
	}

	if errs := validateUser(req); len(errs) > 0 {
		w.WriteHeader(http.StatusUnprocessableEntity)
		json.NewEncoder(w).Encode(ErrorResponse{Errors: errs})
		return
	}

	// Process valid request...
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]string{
		"message": fmt.Sprintf("user %s created", req.Name),
	})
}

func main() {
	http.HandleFunc("POST /users", createUserHandler)
	http.ListenAndServe(":8080", nil)
}
```

For production, use github.com/go-playground/validator/v10 instead of hand-rolled validation. It reads struct tags automatically and supports dozens of built-in rules. The manual approach above shows the underlying pattern.'''
    },
    {
        "instruction": r'''<think>
The user wants to understand graceful shutdown in Go HTTP servers. This is a critical production pattern -- when you get SIGTERM (from Kubernetes, systemd, etc.), you need to stop accepting new connections, finish in-flight requests, then exit. Go stdlib has http.Server.Shutdown for this. I should show the signal handling, shutdown with timeout, and how to drain connections properly. Also worth noting the difference between Shutdown (graceful) and Close (immediate).
</think>
How do I implement graceful shutdown for a Go HTTP server that finishes in-flight requests before exiting?''',
        "output": r'''Use `http.Server.Shutdown` with a context timeout to drain in-flight requests:

```go
package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /slow", func(w http.ResponseWriter, r *http.Request) {
		log.Println("slow request started")
		select {
		case <-time.After(5 * time.Second):
			w.Write([]byte("done"))
			log.Println("slow request completed")
		case <-r.Context().Done():
			log.Println("slow request cancelled by client")
		}
	})

	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("ok"))
	})

	server := &http.Server{
		Addr:         ":8080",
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Start server in a goroutine
	go func() {
		log.Printf("server listening on %s", server.Addr)
		if err := server.ListenAndServe(); err != http.ErrServerClosed {
			log.Fatalf("server error: %v", err)
		}
	}()

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	sig := <-quit
	log.Printf("received %v, starting graceful shutdown", sig)

	// Give in-flight requests 15 seconds to complete
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	// Shutdown stops accepting new connections and waits for
	// existing ones to finish (up to the context deadline)
	if err := server.Shutdown(ctx); err != nil {
		log.Printf("forced shutdown: %v", err)
		server.Close() // force-close remaining connections
	}

	log.Println("server stopped")
}
```

Key behaviors of Shutdown:
- Closes listeners immediately (no new connections accepted)
- Waits for active requests to complete or context to expire
- Returns nil if all requests finish in time, context error if timeout hit
- Does NOT close hijacked connections (WebSockets) -- track those separately
- In Kubernetes, set terminationGracePeriodSeconds > your shutdown timeout
- Set server timeouts (Read, Write, Idle) to prevent slow clients from blocking shutdown'''
    },
]
