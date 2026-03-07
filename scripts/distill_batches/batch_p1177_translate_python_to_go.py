"""Code translation pairs: Python to Go (error handling, concurrency, types)."""

PAIRS = [
    (
        "code-translation/python-to-go",
        r'''Convert this Python HTTP server with JSON handling to Go:

from http.server import HTTPServer, BaseHTTPRequestHandler
import json

TODOS = []

class TodoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(TODOS).encode())

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        todo = {"id": len(TODOS) + 1, "title": body["title"], "done": False}
        TODOS.append(todo)
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(todo).encode())

HTTPServer(("", 8080), TodoHandler).serve_forever()''',
        r'''<think>
Python HTTP server to Go. Several major differences to handle:

1. Go has no class inheritance -- instead of subclassing BaseHTTPRequestHandler, Go uses http.HandleFunc or implements http.Handler interface.

2. JSON handling: Python json.dumps/loads vs Go encoding/json with Marshal/Unmarshal. Go requires struct definitions for JSON -- you can't just use arbitrary maps as easily.

3. Error handling: Python raises exceptions; Go returns error values that must be checked explicitly. Every json.Unmarshal, every io.ReadAll needs an error check.

4. Global mutable state: The Python version uses a global TODOS list. In Go, shared mutable state with concurrent HTTP requests needs synchronization. Go's net/http serves each request in its own goroutine, so I need a mutex.

5. Python's BaseHTTPRequestHandler handles routing by method name (do_GET, do_POST). In Go, a single handler function checks r.Method.

The mutex thing is important -- Python's HTTPServer is single-threaded by default, so the global list is safe. Go's server is concurrent by default, so I must add sync.Mutex or sync.RWMutex.
</think>

```go
package main

import (
	"encoding/json"
	"io"
	"net/http"
	"sync"
)

type Todo struct {
	ID    int    `json:"id"`
	Title string `json:"title"`
	Done  bool   `json:"done"`
}

var (
	todos []Todo
	mu    sync.Mutex
	nextID = 1
)

func todosHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		mu.Lock()
		data, err := json.Marshal(todos)
		mu.Unlock()
		if err != nil {
			http.Error(w, err.Error(), 500)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write(data)

	case http.MethodPost:
		body, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, "bad request", 400)
			return
		}
		defer r.Body.Close()

		var input struct {
			Title string `json:"title"`
		}
		if err := json.Unmarshal(body, &input); err != nil {
			http.Error(w, "invalid json", 400)
			return
		}

		mu.Lock()
		todo := Todo{ID: nextID, Title: input.Title, Done: false}
		nextID++
		todos = append(todos, todo)
		mu.Unlock()

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(201)
		json.NewEncoder(w).Encode(todo)

	default:
		http.Error(w, "method not allowed", 405)
	}
}

func main() {
	todos = make([]Todo, 0)
	http.HandleFunc("/", todosHandler)
	http.ListenAndServe(":8080", nil)
}
```

Key differences from Python:

- Go requires explicit struct types with JSON tags -- no duck-typed dicts
- Every operation that can fail returns an error that must be checked (json.Unmarshal, io.ReadAll)
- Go's HTTP server is concurrent by default, so shared state needs `sync.Mutex`. Python's HTTPServer is single-threaded
- Method dispatch is a manual `switch r.Method` instead of separate do_GET/do_POST methods
- `json.dumps(obj)` becomes `json.Marshal(obj)` returning `([]byte, error)`''',
    ),
    (
        "code-translation/python-to-go",
        r'''Translate this Python concurrent task runner to Go:

import asyncio
import aiohttp
from typing import List

async def fetch_url(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            return {"url": url, "status": resp.status, "size": len(await resp.text())}
    except Exception as e:
        return {"url": url, "error": str(e)}

async def fetch_all(urls: List[str], max_concurrent: int = 5):
    semaphore = asyncio.Semaphore(max_concurrent)
    async def limited_fetch(session, url):
        async with semaphore:
            return await fetch_url(session, url)
    async with aiohttp.ClientSession() as session:
        tasks = [limited_fetch(session, url) for url in urls]
        return await asyncio.gather(*tasks)

results = asyncio.run(fetch_all([
    "https://example.com",
    "https://httpbin.org/get",
    "https://jsonplaceholder.typicode.com/posts/1",
]))
for r in results:
    print(r)''',
        r'''```go
package main

import (
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"
)

type Result struct {
	URL    string `json:"url"`
	Status int    `json:"status,omitempty"`
	Size   int    `json:"size,omitempty"`
	Error  string `json:"error,omitempty"`
}

func fetchURL(client *http.Client, url string) Result {
	resp, err := client.Get(url)
	if err != nil {
		return Result{URL: url, Error: err.Error()}
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return Result{URL: url, Error: err.Error()}
	}
	return Result{URL: url, Status: resp.StatusCode, Size: len(body)}
}

func fetchAll(urls []string, maxConcurrent int) []Result {
	results := make([]Result, len(urls))
	sem := make(chan struct{}, maxConcurrent)
	var wg sync.WaitGroup

	client := &http.Client{Timeout: 5 * time.Second}

	for i, url := range urls {
		wg.Add(1)
		go func(idx int, u string) {
			defer wg.Done()
			sem <- struct{}{}        // acquire semaphore slot
			results[idx] = fetchURL(client, u)
			<-sem                    // release slot
		}(i, url)
	}

	wg.Wait()
	return results
}

func main() {
	urls := []string{
		"https://example.com",
		"https://httpbin.org/get",
		"https://jsonplaceholder.typicode.com/posts/1",
	}
	results := fetchAll(urls, 5)
	for _, r := range results {
		if r.Error != "" {
			fmt.Printf("URL: %s, Error: %s\n", r.URL, r.Error)
		} else {
			fmt.Printf("URL: %s, Status: %d, Size: %d\n", r.URL, r.Status, r.Size)
		}
	}
}
```

Key translation notes:

- `asyncio.Semaphore(n)` -> buffered channel `make(chan struct{}, n)`. Both limit concurrency to n
- `asyncio.gather(*tasks)` -> `sync.WaitGroup` with goroutines. Go has no gather equivalent; you manually track completion
- `async/await` disappears entirely -- Go uses goroutines and channels instead of coroutines
- Results are written to a pre-allocated slice by index, which is safe since each goroutine writes to a unique index
- `aiohttp.ClientSession` -> `http.Client` with shared transport for connection pooling
- Python exceptions in async context -> Go error return values checked at each step''',
    ),
    (
        "code-translation/python-to-go",
        r'''Convert this Python CLI tool with argument parsing to Go:

import argparse
import os
import hashlib

def hash_file(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser(description="File hasher")
    parser.add_argument("files", nargs="+", help="Files to hash")
    parser.add_argument("-a", "--algorithm", default="sha256",
                       choices=["md5", "sha1", "sha256", "sha512"])
    parser.add_argument("-c", "--check", help="Verify against expected hash")
    args = parser.parse_args()

    for filepath in args.files:
        if not os.path.exists(filepath):
            print(f"Error: {filepath} not found")
            continue
        digest = hash_file(filepath, args.algorithm)
        if args.check:
            status = "OK" if digest == args.check else "MISMATCH"
            print(f"{filepath}: {status}")
        else:
            print(f"{digest}  {filepath}")

if __name__ == "__main__":
    main()''',
        r'''<think>
Python argparse to Go. Go's standard library has the `flag` package, but it doesn't support positional arguments or choices natively. Options:

1. `flag` package -- basic but requires manual positional arg handling
2. Third-party like `cobra` or `pflag` -- more powerful but adds dependency

I'll use the `flag` package since it's stdlib-only and the requirements are simple enough. Positional args come from flag.Args() after parsing.

Hash algorithm mapping: Python's hashlib.new(name) dynamically creates hashers. In Go, I need to import specific crypto packages and use a map or switch.

The walrus operator `:=` in the while loop for chunked reading becomes a standard for loop with io.Reader in Go.

Go's os.Open returns (*File, error) -- no os.path.exists equivalent, just try to open and handle the error.
</think>

```go
package main

import (
	"crypto/md5"
	"crypto/sha1"
	"crypto/sha256"
	"crypto/sha512"
	"flag"
	"fmt"
	"hash"
	"io"
	"os"
)

func newHasher(algorithm string) (hash.Hash, error) {
	switch algorithm {
	case "md5":
		return md5.New(), nil
	case "sha1":
		return sha1.New(), nil
	case "sha256":
		return sha256.New(), nil
	case "sha512":
		return sha512.New(), nil
	default:
		return nil, fmt.Errorf("unsupported algorithm: %s", algorithm)
	}
}

func hashFile(path, algorithm string) (string, error) {
	h, err := newHasher(algorithm)
	if err != nil {
		return "", err
	}
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()

	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return fmt.Sprintf("%x", h.Sum(nil)), nil
}

func main() {
	algorithm := flag.String("a", "sha256", "Hash algorithm: md5, sha1, sha256, sha512")
	check := flag.String("c", "", "Verify against expected hash")
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: hasher [options] file1 [file2 ...]\n")
		flag.PrintDefaults()
	}
	flag.Parse()

	files := flag.Args()
	if len(files) == 0 {
		flag.Usage()
		os.Exit(1)
	}

	for _, filepath := range files {
		digest, err := hashFile(filepath, *algorithm)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %s: %v\n", filepath, err)
			continue
		}
		if *check != "" {
			status := "MISMATCH"
			if digest == *check {
				status = "OK"
			}
			fmt.Printf("%s: %s\n", filepath, status)
		} else {
			fmt.Printf("%s  %s\n", digest, filepath)
		}
	}
}
```

Key differences:

- `argparse` with positional + optional args -> `flag` package handles flags; positional args via `flag.Args()`
- `hashlib.new(name)` dynamic dispatch -> explicit switch statement mapping algorithm names to constructors
- Chunked file reading with walrus operator -> `io.Copy(h, f)` handles buffered copying internally
- `os.path.exists()` check before open -> Go idiom is to just `os.Open()` and check the error
- Python `print(f"...")` to stderr -> `fmt.Fprintf(os.Stderr, ...)`''',
    ),
    (
        "code-translation/python-to-go",
        r'''Translate this Python dict-heavy data processing to Go:

def analyze_logs(entries):
    stats = {
        "total": 0,
        "by_level": {},
        "by_service": {},
        "errors": [],
    }
    for entry in entries:
        stats["total"] += 1
        level = entry.get("level", "info")
        stats["by_level"][level] = stats["by_level"].get(level, 0) + 1
        svc = entry.get("service", "unknown")
        stats["by_service"][svc] = stats["by_service"].get(svc, 0) + 1
        if level == "error":
            stats["errors"].append({
                "service": svc,
                "message": entry.get("message", ""),
                "timestamp": entry.get("timestamp", ""),
            })
    return stats''',
        r'''```go
package main

import "fmt"

type LogEntry struct {
	Level     string `json:"level"`
	Service   string `json:"service"`
	Message   string `json:"message"`
	Timestamp string `json:"timestamp"`
}

type ErrorDetail struct {
	Service   string `json:"service"`
	Message   string `json:"message"`
	Timestamp string `json:"timestamp"`
}

type LogStats struct {
	Total     int            `json:"total"`
	ByLevel   map[string]int `json:"by_level"`
	ByService map[string]int `json:"by_service"`
	Errors    []ErrorDetail  `json:"errors"`
}

func analyzeLogs(entries []LogEntry) LogStats {
	stats := LogStats{
		ByLevel:   make(map[string]int),
		ByService: make(map[string]int),
		Errors:    make([]ErrorDetail, 0),
	}

	for _, entry := range entries {
		stats.Total++

		level := entry.Level
		if level == "" {
			level = "info"
		}
		stats.ByLevel[level]++

		svc := entry.Service
		if svc == "" {
			svc = "unknown"
		}
		stats.ByService[svc]++

		if level == "error" {
			stats.Errors = append(stats.Errors, ErrorDetail{
				Service:   svc,
				Message:   entry.Message,
				Timestamp: entry.Timestamp,
			})
		}
	}
	return stats
}

func main() {
	entries := []LogEntry{
		{Level: "info", Service: "auth", Message: "login ok"},
		{Level: "error", Service: "db", Message: "connection timeout"},
		{Level: "info", Service: "auth", Message: "login ok"},
		{Level: "error", Service: "api", Message: "500 response"},
	}
	stats := analyzeLogs(entries)
	fmt.Printf("Total: %d\n", stats.Total)
	fmt.Printf("By level: %v\n", stats.ByLevel)
	fmt.Printf("Errors: %d\n", len(stats.Errors))
}
```

Key differences from Python:

- Python dicts with arbitrary keys -> Go requires struct definitions for LogEntry, ErrorDetail, and LogStats. This is more verbose but catches typos at compile time
- `dict.get("key", default)` -> explicit zero-value check with `if level == ""`; Go map reads return the zero value for missing keys
- Maps must be initialized with `make(map[...])` -- nil maps panic on write
- Python's flexible `entry.get("level", "info")` pattern requires a manual default check in Go since struct fields always exist (with zero values)
- `stats["by_level"][level] = stats["by_level"].get(level, 0) + 1` simplifies to `stats.ByLevel[level]++` because Go map reads return 0 for missing int values''',
    ),
    (
        "code-translation/python-to-go",
        r'''Convert this Python context manager pattern to Go:

import time

class Timer:
    def __init__(self, label=""):
        self.label = label
        self.elapsed = 0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed = time.perf_counter() - self.start
        if self.label:
            print(f"{self.label}: {self.elapsed:.3f}s")

class DBConnection:
    def __init__(self, dsn):
        self.dsn = dsn
        self.conn = None

    def __enter__(self):
        self.conn = connect(self.dsn)  # hypothetical
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
            self.conn.close()
        return False  # do not suppress exceptions

# Usage:
# with Timer("query"):
#     with DBConnection("postgres://...") as conn:
#         conn.execute("SELECT ...")''',
        r'''<think>
Python context managers to Go. Go has no `with` statement but uses `defer` for cleanup, which is the closest equivalent.

For the Timer pattern, Go's idiomatic approach is either:
1. A function that returns a stop function: `stop := startTimer("label"); defer stop()`
2. A deferred closure that captures the start time

For the DBConnection pattern with commit/rollback on error, Go uses a common pattern:
1. Open connection
2. Begin transaction
3. defer a function that checks for error and commits or rolls back

The exc_type check in __exit__ determines commit vs rollback -- in Go, this is typically done by checking a named return error or using a committed flag.

One important difference: Python's __exit__ receives exception info automatically. Go has no equivalent -- you need to track success/failure explicitly, often with a named error return or a boolean flag.

I'll show both patterns clearly.
</think>

```go
package main

import (
	"database/sql"
	"fmt"
	"time"
)

// Timer -- equivalent to Python Timer context manager.
// Usage: defer NewTimer("label").Stop()
type Timer struct {
	Label string
	Start time.Time
}

func NewTimer(label string) *Timer {
	return &Timer{Label: label, Start: time.Now()}
}

func (t *Timer) Stop() time.Duration {
	elapsed := time.Since(t.Start)
	if t.Label != "" {
		fmt.Printf("%s: %.3fs\n", t.Label, elapsed.Seconds())
	}
	return elapsed
}

// DB transaction with auto commit/rollback.
// This mirrors the DBConnection context manager.
func withTransaction(db *sql.DB, fn func(tx *sql.Tx) error) error {
	tx, err := db.Begin()
	if err != nil {
		return err
	}

	// defer handles commit or rollback based on whether fn returned error
	defer func() {
		if err != nil {
			tx.Rollback()
		} else {
			err = tx.Commit()
		}
	}()

	err = fn(tx)
	return err
}

// Usage example:
//
// func main() {
//     defer NewTimer("query").Stop()
//
//     db, _ := sql.Open("postgres", "postgres://...")
//     defer db.Close()
//
//     err := withTransaction(db, func(tx *sql.Tx) error {
//         _, err := tx.Exec("INSERT INTO users (name) VALUES ($1)", "Alice")
//         return err
//     })
//     if err != nil {
//         fmt.Println("transaction failed:", err)
//     }
// }
```

Key differences:

- `with Timer("x"):` -> `defer NewTimer("x").Stop()`. Go's `defer` runs at function exit, similar to `__exit__`
- `with DBConnection(dsn) as conn:` -> a callback pattern `withTransaction(db, func(tx) error {...})` since Go cannot intercept the caller's error state like `__exit__` can
- Python `__exit__` receives `exc_type` to decide commit vs rollback; Go uses the error return from the callback function
- `return False` in `__exit__` (do not suppress) has no Go equivalent -- errors always propagate via return values
- `defer` only runs at function scope exit, not block scope like Python's `with`. This matters for loops''',
    ),
]
