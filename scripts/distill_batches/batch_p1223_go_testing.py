"""
Go language training pairs - testing (table-driven tests, subtests, benchmarks, testify, httptest)
"""

pairs = [
    {
        "instruction": r'''Show me how to write table-driven tests with subtests in Go, including edge cases and error conditions.''',
        "output": r'''Table-driven tests are the idiomatic Go testing pattern. Each test case is a struct in a slice, run as a named subtest:

```go
package calc

import (
	"math"
	"testing"
)

func Divide(a, b float64) (float64, error) {
	if b == 0 {
		return 0, ErrDivideByZero
	}
	return a / b, nil
}

var ErrDivideByZero = errors.New("division by zero")

func TestDivide(t *testing.T) {
	tests := []struct {
		name    string
		a, b    float64
		want    float64
		wantErr error
	}{
		{
			name: "positive integers",
			a:    10, b: 2,
			want: 5,
		},
		{
			name: "negative dividend",
			a:    -10, b: 2,
			want: -5,
		},
		{
			name: "fractional result",
			a:    1, b: 3,
			want: 0.333333,
		},
		{
			name:    "divide by zero",
			a:       5, b: 0,
			wantErr: ErrDivideByZero,
		},
		{
			name: "both zero numerator",
			a:    0, b: 5,
			want: 0,
		},
		{
			name: "very large numbers",
			a:    1e18, b: 1e9,
			want: 1e9,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := Divide(tt.a, tt.b)

			if tt.wantErr != nil {
				if !errors.Is(err, tt.wantErr) {
					t.Errorf("want error %v, got %v", tt.wantErr, err)
				}
				return
			}

			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}

			// Use tolerance for floating point comparison
			if math.Abs(got-tt.want) > 1e-4 {
				t.Errorf("Divide(%v, %v) = %v, want %v",
					tt.a, tt.b, got, tt.want)
			}
		})
	}
}
```

Benefits of table-driven tests:
- Adding a new case is one struct literal -- minimal boilerplate
- t.Run creates named subtests: `go test -run TestDivide/divide_by_zero`
- Each subtest runs independently -- failures do not skip remaining cases
- Use t.Fatalf for unexpected errors, t.Errorf for assertion failures
- Parallel subtests: add `t.Parallel()` inside t.Run for concurrent execution'''
    },
    {
        "instruction": r'''<think>
The user wants to see httptest usage in Go. The httptest package provides two main tools: httptest.NewRecorder for testing handlers without a real server, and httptest.NewServer for integration tests with a real HTTP server on localhost. I should show both approaches. The recorder is faster and better for unit tests; the server is better for testing middleware chains and full request lifecycle.
</think>
How do I test Go HTTP handlers using the httptest package? Show both recorder and server approaches.''',
        "output": r'''The httptest package provides two approaches: ResponseRecorder for unit tests and Server for integration tests:

```go
package api

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// Handler under test
func UserHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"name": "Alice"})
	case http.MethodPost:
		var body struct {
			Name string `json:"name"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		if body.Name == "" {
			http.Error(w, "name required", http.StatusUnprocessableEntity)
			return
		}
		w.WriteHeader(http.StatusCreated)
		json.NewEncoder(w).Encode(body)
	}
}

// --- Approach 1: httptest.NewRecorder (unit test) ---
func TestUserHandler_Get(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/user", nil)
	rec := httptest.NewRecorder()

	UserHandler(rec, req)

	res := rec.Result()
	defer res.Body.Close()

	if res.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", res.StatusCode)
	}

	var body map[string]string
	json.NewDecoder(res.Body).Decode(&body)
	if body["name"] != "Alice" {
		t.Errorf("name = %q, want Alice", body["name"])
	}
}

func TestUserHandler_Post_Invalid(t *testing.T) {
	payload := strings.NewReader(`{"name":""}`)
	req := httptest.NewRequest(http.MethodPost, "/user", payload)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	UserHandler(rec, req)

	if rec.Code != http.StatusUnprocessableEntity {
		t.Errorf("status = %d, want 422", rec.Code)
	}
}

// --- Approach 2: httptest.NewServer (integration test) ---
func TestUserAPI_Integration(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(UserHandler))
	defer srv.Close()

	// Real HTTP request to the test server
	resp, err := http.Post(
		srv.URL+"/user",
		"application/json",
		strings.NewReader(`{"name":"Bob"}`),
	)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		t.Fatalf("status %d, body: %s", resp.StatusCode, body)
	}
}
```

When to use which:
- NewRecorder: fast, no network, test single handlers in isolation
- NewServer: tests full middleware chain, real HTTP transport, connection handling
- NewTLSServer: same as NewServer but with TLS for testing HTTPS clients'''
    },
    {
        "instruction": r'''How do I write benchmarks in Go and interpret the results? Show benchmarking a function with different input sizes.''',
        "output": r'''Go benchmarks use `testing.B` and run with `go test -bench`. The framework auto-adjusts iteration count for stable timing:

```go
package search

import (
	"sort"
	"testing"
)

// Functions to benchmark
func LinearSearch(haystack []int, needle int) int {
	for i, v := range haystack {
		if v == needle {
			return i
		}
	}
	return -1
}

func BinarySearch(haystack []int, needle int) int {
	return sort.SearchInts(haystack, needle)
}

// Helper to generate sorted test data
func makeSlice(n int) []int {
	s := make([]int, n)
	for i := range s {
		s[i] = i * 2
	}
	return s
}

// Benchmark with sub-benchmarks for different sizes
func BenchmarkLinearSearch(b *testing.B) {
	sizes := []int{100, 1000, 10000, 100000}

	for _, size := range sizes {
		data := makeSlice(size)
		needle := size - 1 // worst case: near the end

		b.Run(
			testing.TB.Name(b)+"/"+string(rune(size)),
			func(b *testing.B) { /* skip */ },
		)

		// Use b.Run for sub-benchmarks with different sizes
		name := ""
		switch size {
		case 100:
			name = "size_100"
		case 1000:
			name = "size_1K"
		case 10000:
			name = "size_10K"
		case 100000:
			name = "size_100K"
		}

		b.Run(name, func(b *testing.B) {
			for i := 0; i < b.N; i++ {
				LinearSearch(data, needle)
			}
		})
	}
}

func BenchmarkBinarySearch(b *testing.B) {
	for _, size := range []int{100, 1000, 10000, 100000} {
		data := makeSlice(size)
		needle := size - 1

		name := ""
		switch size {
		case 100:
			name = "size_100"
		case 1000:
			name = "size_1K"
		case 10000:
			name = "size_10K"
		case 100000:
			name = "size_100K"
		}

		b.Run(name, func(b *testing.B) {
			for i := 0; i < b.N; i++ {
				BinarySearch(data, needle)
			}
		})
	}
}

// Track allocations with b.ReportAllocs
func BenchmarkAllocations(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = makeSlice(1000)
	}
}
```

Run with: `go test -bench=. -benchmem -count=3`

Reading results:
- `b.N` is adjusted automatically -- never hardcode it
- `-benchmem` shows allocations per operation (allocs/op, B/op)
- `-count=3` runs each benchmark 3 times for statistical stability
- Use `benchstat` tool to compare before/after: `benchstat old.txt new.txt`
- b.ResetTimer() if setup code should not be measured'''
    },
    {
        "instruction": r'''Show me how to use testify for assertions and mocking in Go tests.''',
        "output": r'''testify provides readable assertions with `assert`/`require` and interface mocking with `mock`:

```go
package service

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
)

// --- Domain types ---
type User struct {
	ID    int
	Name  string
	Email string
}

// Interface to mock
type UserRepository interface {
	GetByID(ctx context.Context, id int) (*User, error)
	Save(ctx context.Context, user *User) error
}

// Service under test
type UserService struct {
	repo UserRepository
}

func (s *UserService) GetUser(ctx context.Context, id int) (*User, error) {
	if id <= 0 {
		return nil, errors.New("invalid user ID")
	}
	return s.repo.GetByID(ctx, id)
}

// --- Mock implementation ---
type MockUserRepo struct {
	mock.Mock
}

func (m *MockUserRepo) GetByID(ctx context.Context, id int) (*User, error) {
	args := m.Called(ctx, id)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*User), args.Error(1)
}

func (m *MockUserRepo) Save(ctx context.Context, user *User) error {
	args := m.Called(ctx, user)
	return args.Error(0)
}

// --- Tests ---
func TestGetUser_Success(t *testing.T) {
	mockRepo := new(MockUserRepo)
	svc := &UserService{repo: mockRepo}

	expected := &User{ID: 1, Name: "Alice", Email: "alice@test.com"}
	mockRepo.On("GetByID", mock.Anything, 1).Return(expected, nil)

	user, err := svc.GetUser(context.Background(), 1)

	// require stops test immediately on failure (vs assert which continues)
	require.NoError(t, err)
	assert.Equal(t, "Alice", user.Name)
	assert.Equal(t, "alice@test.com", user.Email)

	mockRepo.AssertExpectations(t)
}

func TestGetUser_InvalidID(t *testing.T) {
	svc := &UserService{repo: new(MockUserRepo)}

	user, err := svc.GetUser(context.Background(), -1)

	assert.Nil(t, user)
	assert.EqualError(t, err, "invalid user ID")
}

func TestGetUser_NotFound(t *testing.T) {
	mockRepo := new(MockUserRepo)
	svc := &UserService{repo: mockRepo}

	mockRepo.On("GetByID", mock.Anything, 99).
		Return(nil, errors.New("not found"))

	user, err := svc.GetUser(context.Background(), 99)

	assert.Nil(t, user)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "not found")
	mockRepo.AssertCalled(t, "GetByID", mock.Anything, 99)
}
```

testify packages:
- assert: soft assertions (test continues on failure)
- require: hard assertions (test stops immediately)
- mock: interface mocking with expectation tracking
- suite: test suites with setup/teardown hooks

Use require for preconditions, assert for the actual checks.'''
    },
    {
        "instruction": r'''<think>
The user wants to see how to test concurrent Go code. Testing concurrency is tricky -- race conditions may only appear under specific timing. Go has the race detector (`go test -race`) which is essential. I should show testing with goroutines, using channels for synchronization in tests, and how to use t.Cleanup for resource management. Also worth showing how to test for race conditions and use sync primitives in test helpers.
</think>
How do I test concurrent Go code? Show testing goroutines, detecting race conditions, and using t.Cleanup for resource management.''',
        "output": r'''Testing concurrent code requires the race detector, proper synchronization, and cleanup:

```go
package cache

import (
	"sync"
	"testing"
	"time"
)

// Thread-safe cache to test
type Cache struct {
	mu    sync.RWMutex
	items map[string]string
	ttl   time.Duration
}

func NewCache(ttl time.Duration) *Cache {
	return &Cache{items: make(map[string]string), ttl: ttl}
}

func (c *Cache) Set(key, value string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.items[key] = value
}

func (c *Cache) Get(key string) (string, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	v, ok := c.items[key]
	return v, ok
}

func (c *Cache) Len() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return len(c.items)
}

// Test concurrent access -- run with: go test -race
func TestCache_ConcurrentAccess(t *testing.T) {
	c := NewCache(time.Minute)
	const numGoroutines = 100
	const opsPerGoroutine = 1000

	var wg sync.WaitGroup
	wg.Add(numGoroutines)

	for i := 0; i < numGoroutines; i++ {
		go func(id int) {
			defer wg.Done()
			for j := 0; j < opsPerGoroutine; j++ {
				key := "key"
				if j%2 == 0 {
					c.Set(key, "value")
				} else {
					c.Get(key)
				}
			}
		}(i)
	}

	// Wait with timeout to avoid hanging tests
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		// success
	case <-time.After(10 * time.Second):
		t.Fatal("test timed out -- possible deadlock")
	}
}

// Test with t.Cleanup for resource management
func TestCache_WithCleanup(t *testing.T) {
	c := NewCache(time.Minute)

	// t.Cleanup runs after the test (and subtests) finish
	t.Cleanup(func() {
		t.Log("cleaning up cache resources")
	})

	c.Set("a", "1")
	c.Set("b", "2")

	if c.Len() != 2 {
		t.Errorf("expected 2 items, got %d", c.Len())
	}
}

// Test helper that creates a pre-populated cache
func newTestCache(t *testing.T, items map[string]string) *Cache {
	t.Helper() // marks this as a helper -- errors report caller location
	c := NewCache(time.Minute)
	for k, v := range items {
		c.Set(k, v)
	}
	t.Cleanup(func() {
		// cleanup resources
	})
	return c
}

func TestCache_Prepopulated(t *testing.T) {
	c := newTestCache(t, map[string]string{
		"x": "10",
		"y": "20",
	})

	v, ok := c.Get("x")
	if !ok || v != "10" {
		t.Errorf("Get(x) = %q, %v; want 10, true", v, ok)
	}
}
```

Concurrency testing checklist:
- Always run `go test -race` in CI -- the race detector catches data races at runtime
- Use WaitGroup + timeout channel to detect deadlocks in tests
- t.Helper() makes error locations point to the calling test, not the helper
- t.Cleanup replaces manual defer -- works correctly with subtests and parallel tests
- t.Parallel() runs subtests concurrently to expose race conditions faster'''
    },
]
