"""Go deep reasoning pairs batch 4: testing and tooling."""
PAIRS = [
    ("go_deep/table_driven_parallel_tests", r'''How do I write table-driven tests in Go with parallel subtests? I want to test a function that validates email addresses.''', r'''<think>
Table-driven tests are idiomatic Go. The pattern uses a slice of structs, each defining
inputs and expected outputs. Adding parallel subtests requires care: you must capture the
loop variable to avoid the classic closure-over-loop-variable bug (fixed in Go 1.22+ with
loop var semantics, but good practice regardless). Each subtest calls t.Parallel() which
releases it from the parent's serial execution. The parent test should also call t.Parallel()
so the entire table doesn't block other top-level tests. Key considerations:
- Name each test case clearly for readable output
- Use tt := tt in the loop body for pre-1.22 safety
- Group related fields in the test struct (input, want, wantErr)
- t.Parallel() must be the first call in the subtest
- The parent goroutine continues after t.Run returns, so all subtests
  share the same test struct slice — no mutation allowed
- For email validation, I need to cover: valid emails, missing @, double dots,
  empty local part, unicode domains, plus addressing, and edge cases
- The validator function should use a reasonable regex or manual parse
- Each subtest runs in its own goroutine so the race detector can catch issues
- Avoid shared mutable state between test cases
- The test output groups results under the parent test name
</think>

Here is a complete example with a table-driven parallel test for email validation:

```go
package email

import (
	"regexp"
	"testing"
)

// ValidateEmail checks whether an email address is syntactically valid.
var emailRe = regexp.MustCompile(`^[a-zA-Z0-9.!#$%&'*+/=?^_` + "`" + `{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$`)

func ValidateEmail(addr string) bool {
	if len(addr) > 254 {
		return false
	}
	return emailRe.MatchString(addr)
}

func TestValidateEmail(t *testing.T) {
	t.Parallel() // allow this test group to run in parallel with others

	tests := []struct {
		name  string
		input string
		want  bool
	}{
		{name: "valid simple", input: "user@example.com", want: true},
		{name: "valid plus addressing", input: "user+tag@example.com", want: true},
		{name: "valid subdomain", input: "admin@mail.example.co.uk", want: true},
		{name: "missing at sign", input: "userexample.com", want: false},
		{name: "double at sign", input: "user@@example.com", want: false},
		{name: "empty local part", input: "@example.com", want: false},
		{name: "empty domain", input: "user@", want: false},
		{name: "empty string", input: "", want: false},
		{name: "spaces in local", input: "us er@example.com", want: false},
		{name: "valid dots in local", input: "first.last@example.com", want: true},
		{name: "domain starts with hyphen", input: "user@-example.com", want: false},
		{name: "very long address", input: string(make([]byte, 255)) + "@x.com", want: false},
	}

	for _, tt := range tests {
		tt := tt // capture for pre-Go-1.22 safety
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel() // each subtest runs concurrently
			got := ValidateEmail(tt.input)
			if got != tt.want {
				t.Errorf("ValidateEmail(%q) = %v, want %v", tt.input, got, tt.want)
			}
		})
	}
}
```

Key points:

1. **`t.Parallel()` on the parent** allows this test function to run alongside other parallel test functions.
2. **`t.Parallel()` on each subtest** allows all table entries to execute concurrently.
3. **`tt := tt`** captures the loop variable so each goroutine sees its own copy. In Go 1.22+ this is automatic, but the idiom remains safe and clear.
4. **Named test cases** produce output like `TestValidateEmail/valid_simple`, making failures easy to find.
5. **No shared mutable state** between subtests means the race detector stays happy.

Run with `go test -v -race ./...` to get verbose output and race detection.'''),

    ("go_deep/test_fixtures_cleanup", r'''What is the proper way to set up and tear down test fixtures in Go using t.Cleanup? I need to create temporary files and database connections for my tests.''', r'''<think>
t.Cleanup registers a function that runs after the test (and all its subtests) complete.
It is called in LIFO order (like defer but scoped to test lifetime, not function scope).
This is superior to defer in test helpers because:
- defer runs when the helper function returns, not when the test ends
- t.Cleanup runs after the test and ALL subtests finish
- Multiple Cleanup calls stack in reverse order (LIFO)
- Works correctly with parallel subtests
For fixtures, the pattern is: write a helper that creates the resource, registers
cleanup, and returns the resource. The caller never needs to worry about teardown.
For temp files: use t.TempDir() which auto-cleans, or os.CreateTemp + t.Cleanup.
For DB connections: open in helper, register Close in cleanup.
Important subtlety: if a fixture is used across parallel subtests, cleanup must
wait for all of them. t.Cleanup handles this — it runs after subtests complete.
I should show a realistic example with a temp file fixture, a mock DB fixture,
and demonstrate the LIFO ordering. Also show how t.TempDir() is the simplest
approach for directory-based fixtures. Show the helper pattern with t.Helper()
so that test failure line numbers point to the test, not the helper.
</think>

Here is a complete example demonstrating `t.Cleanup` for test fixtures:

```go
package fixtures

import (
	"database/sql"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	_ "github.com/mattn/go-sqlite3" // or use a mock
)

// --- Fixture helpers ---

// newTempConfig creates a temp JSON config file and cleans it up after the test.
func newTempConfig(t *testing.T, data map[string]string) string {
	t.Helper()

	dir := t.TempDir() // automatically cleaned up — no manual cleanup needed
	path := filepath.Join(dir, "config.json")

	b, err := json.Marshal(data)
	if err != nil {
		t.Fatalf("marshal config: %v", err)
	}
	if err := os.WriteFile(path, b, 0o644); err != nil {
		t.Fatalf("write config: %v", err)
	}

	t.Logf("created temp config at %s", path)
	return path
}

// newTestDB opens an in-memory SQLite database with a schema and registers cleanup.
func newTestDB(t *testing.T) *sql.DB {
	t.Helper()

	db, err := sql.Open("sqlite3", ":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}

	// Cleanup runs AFTER the test and all subtests finish
	t.Cleanup(func() {
		t.Log("closing database connection")
		if err := db.Close(); err != nil {
			t.Errorf("close db: %v", err)
		}
	})

	// Set up schema
	_, err = db.Exec(`CREATE TABLE users (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		name TEXT NOT NULL,
		email TEXT UNIQUE NOT NULL
	)`)
	if err != nil {
		t.Fatalf("create schema: %v", err)
	}

	return db
}

// seedUsers inserts test data and registers cleanup to truncate.
func seedUsers(t *testing.T, db *sql.DB, users []struct{ Name, Email string }) {
	t.Helper()

	for _, u := range users {
		_, err := db.Exec("INSERT INTO users (name, email) VALUES (?, ?)", u.Name, u.Email)
		if err != nil {
			t.Fatalf("seed user %s: %v", u.Name, err)
		}
	}

	// LIFO: this cleanup runs BEFORE the db.Close() cleanup
	t.Cleanup(func() {
		t.Log("truncating users table")
		db.Exec("DELETE FROM users")
	})
}

// --- Tests ---

func TestUserLookup(t *testing.T) {
	db := newTestDB(t) // cleanup: close DB

	seedUsers(t, db, []struct{ Name, Email string }{
		{"Alice", "alice@example.com"},
		{"Bob", "bob@example.com"},
	}) // cleanup: truncate users (runs before DB close due to LIFO)

	var name string
	err := db.QueryRow("SELECT name FROM users WHERE email = ?", "alice@example.com").Scan(&name)
	if err != nil {
		t.Fatalf("query: %v", err)
	}
	if name != "Alice" {
		t.Errorf("got name %q, want Alice", name)
	}

	// Cleanup order when test ends:
	// 1. truncate users (seedUsers cleanup — registered last)
	// 2. close DB (newTestDB cleanup — registered first)
}

func TestConfigLoading(t *testing.T) {
	path := newTempConfig(t, map[string]string{
		"host": "localhost",
		"port": "8080",
	})

	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read config: %v", err)
	}

	var cfg map[string]string
	if err := json.Unmarshal(data, &cfg); err != nil {
		t.Fatalf("parse config: %v", err)
	}
	if cfg["host"] != "localhost" {
		t.Errorf("host = %q, want localhost", cfg["host"])
	}
	// t.TempDir() auto-removes the directory when test ends
}
```

Key takeaways:

1. **`t.TempDir()`** is the simplest fixture for file-based tests; it auto-cleans with no manual `t.Cleanup` call needed.
2. **`t.Cleanup(fn)`** registers teardown that runs after the test and all its subtests complete, even if the test calls `t.Fatal`.
3. **LIFO ordering** means later-registered cleanups run first, which naturally handles dependency chains (truncate before close).
4. **`t.Helper()`** in fixture functions makes error messages point to the calling test, not the helper.
5. **Never use `defer`** in a test helper for cleanup. The `defer` runs when the helper returns, not when the test finishes. `t.Cleanup` is test-lifetime scoped.'''),

    ("go_deep/golden_file_testing", r'''How do I implement the golden file testing pattern in Go? I have a template engine that produces HTML output and I want to verify it against saved expected output files.''', r'''<think>
Golden file testing compares actual output against a "golden" file stored in testdata/.
The pattern works like this:
1. Generate actual output from the function under test
2. If -update flag is set, write actual output to the golden file
3. Otherwise, read the golden file and compare with actual output
This is great for template engines, code generators, serialization, CLI output, etc.
Key design decisions:
- Use testdata/ directory (ignored by go build, included in test binary)
- Use a global -update flag so you can refresh all golden files at once
- Normalize line endings (CRLF vs LF) for cross-platform compatibility
- Show a meaningful diff on mismatch, not just "not equal"
- The golden file name should derive from t.Name() for uniqueness
- t.Helper() on the assertion helper
- Consider using go-cmp or a simple line-by-line diff for readable output
I should show the full pattern: the update flag, the helper function,
the testdata directory structure, and a realistic template engine test.
The update workflow is: run `go test -update` once, review the golden
files in git diff, commit them. Future runs compare against them.
Edge case: binary output needs different handling than text.
</think>

Here is the complete golden file testing pattern:

```go
package render

import (
	"flag"
	"html/template"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

var update = flag.Bool("update", false, "update golden files")

// --- Production code ---

type Page struct {
	Title string
	Items []string
}

const pageTpl = `<!DOCTYPE html>
<html>
<head><title>{{.Title}}</title></head>
<body>
<h1>{{.Title}}</h1>
<ul>
{{- range .Items}}
  <li>{{.}}</li>
{{- end}}
</ul>
</body>
</html>`

func RenderPage(p Page) (string, error) {
	t, err := template.New("page").Parse(pageTpl)
	if err != nil {
		return "", err
	}
	var buf strings.Builder
	if err := t.Execute(&buf, p); err != nil {
		return "", err
	}
	return buf.String(), nil
}

// --- Golden file helpers ---

// goldenPath returns the path to a golden file based on the test name.
func goldenPath(t *testing.T, suffix string) string {
	t.Helper()
	// Replace slashes in subtest names with underscores
	name := strings.ReplaceAll(t.Name(), "/", "_")
	return filepath.Join("testdata", name+suffix)
}

// assertGolden compares got against the golden file, or updates it.
func assertGolden(t *testing.T, got string, suffix string) {
	t.Helper()

	path := goldenPath(t, suffix)

	// Normalize line endings for cross-platform consistency
	got = strings.ReplaceAll(got, "\r\n", "\n")

	if *update {
		// Ensure testdata/ directory exists
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatalf("create testdata dir: %v", err)
		}
		if err := os.WriteFile(path, []byte(got), 0o644); err != nil {
			t.Fatalf("update golden file: %v", err)
		}
		t.Logf("updated golden file: %s", path)
		return
	}

	want, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read golden file %s (run with -update to create): %v", path, err)
	}

	wantStr := strings.ReplaceAll(string(want), "\r\n", "\n")
	if got != wantStr {
		// Show a simple line-by-line diff
		gotLines := strings.Split(got, "\n")
		wantLines := strings.Split(wantStr, "\n")
		t.Errorf("output does not match golden file %s", path)
		maxLines := len(gotLines)
		if len(wantLines) > maxLines {
			maxLines = len(wantLines)
		}
		for i := 0; i < maxLines; i++ {
			g, w := "", ""
			if i < len(gotLines) {
				g = gotLines[i]
			}
			if i < len(wantLines) {
				w = wantLines[i]
			}
			if g != w {
				t.Errorf("  line %d:\n    got:  %q\n    want: %q", i+1, g, w)
			}
		}
	}
}

// --- Tests ---

func TestRenderPage(t *testing.T) {
	tests := []struct {
		name string
		page Page
	}{
		{
			name: "basic_page",
			page: Page{Title: "Groceries", Items: []string{"Milk", "Eggs", "Bread"}},
		},
		{
			name: "empty_list",
			page: Page{Title: "Nothing Here", Items: nil},
		},
		{
			name: "special_chars",
			page: Page{Title: "Tom & Jerry", Items: []string{"<script>", "\"quotes\""}},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := RenderPage(tt.page)
			if err != nil {
				t.Fatalf("RenderPage: %v", err)
			}
			assertGolden(t, got, ".html")
		})
	}
}
```

**Workflow:**

```bash
# First time or after changing output:
go test -run TestRenderPage -update
# Review the generated golden files:
git diff testdata/
# If they look correct, commit them:
git add testdata/

# Future runs compare against golden files:
go test -run TestRenderPage -v
```

**Directory structure:**

```
testdata/
  TestRenderPage_basic_page.html
  TestRenderPage_empty_list.html
  TestRenderPage_special_chars.html
```

Key points:

1. **`-update` flag** regenerates golden files. Without it, tests compare against existing files.
2. **`testdata/`** is a Go convention; `go build` ignores it, `go test` includes it.
3. **Line ending normalization** prevents false failures across Windows/Linux.
4. **Meaningful diff output** shows exactly which lines differ, not just "mismatch."
5. **Golden file names derive from `t.Name()`** so subtests get unique files automatically.'''),

    ("go_deep/fuzz_testing_seed_corpus", r'''How do I write fuzz tests in Go with a seed corpus? I want to fuzz test a URL parser that extracts query parameters.''', r'''<think>
Go 1.18+ has built-in fuzz testing. The function signature is FuzzXxx(f *testing.F).
The seed corpus is added via f.Add() calls — these are the starting inputs the fuzzer
uses to begin mutation. The fuzz target is f.Fuzz(func(t *testing.T, ...)) where the
parameter types must match the f.Add() types exactly.
Key considerations:
- Seed corpus should cover edge cases you already know about
- The fuzzer mutates seed inputs to find crashes and panics
- f.Add() types are limited: string, []byte, int, float64, bool, etc.
- The fuzz function must be deterministic — same input = same result
- Fuzz tests run as normal tests with `go test` (only seed corpus)
- Actual fuzzing happens with `go test -fuzz=FuzzXxx`
- Crashers are saved to testdata/fuzz/FuzzXxx/ as reproducible cases
- The function under test should not panic on any input — that's what we're verifying
- I need to show a realistic URL query parser, seed it with interesting cases
  (empty string, no query, multiple params, encoded chars, malformed input),
  and demonstrate what the fuzz target checks for (no panics, consistency)
- A good invariant to check: if Parse succeeds, the result should be consistent
  (re-encoding should produce equivalent output, or at minimum no panic)
- Also show the testdata/fuzz directory structure for committed seed corpus
</think>

Here is a complete fuzz test with seed corpus for a URL query parameter parser:

```go
package urlparse

import (
	"fmt"
	"net/url"
	"strings"
	"testing"
)

// ParseQuery extracts query parameters from a raw URL string.
// Returns a map of key to list of values.
func ParseQuery(rawURL string) (map[string][]string, error) {
	u, err := url.Parse(rawURL)
	if err != nil {
		return nil, fmt.Errorf("invalid URL: %w", err)
	}

	params := make(map[string][]string)
	query := u.RawQuery
	if query == "" {
		return params, nil
	}

	for query != "" {
		var part string
		if idx := strings.IndexByte(query, '&'); idx >= 0 {
			part, query = query[:idx], query[idx+1:]
		} else {
			part, query = query, ""
		}
		if part == "" {
			continue
		}

		key, value, _ := strings.Cut(part, "=")
		key, err1 := url.QueryUnescape(key)
		value, err2 := url.QueryUnescape(value)
		if err1 != nil || err2 != nil {
			continue // skip malformed pairs instead of failing
		}
		params[key] = append(params[key], value)
	}

	return params, nil
}

// --- Standard unit test to verify basic behavior ---
func TestParseQuery(t *testing.T) {
	params, err := ParseQuery("https://example.com/search?q=hello&lang=en&lang=fr")
	if err != nil {
		t.Fatal(err)
	}
	if got := params["q"]; len(got) != 1 || got[0] != "hello" {
		t.Errorf("q = %v, want [hello]", got)
	}
	if got := params["lang"]; len(got) != 2 {
		t.Errorf("lang = %v, want [en, fr]", got)
	}
}

// --- Fuzz test ---
func FuzzParseQuery(f *testing.F) {
	// Seed corpus: known interesting inputs the fuzzer will mutate
	f.Add("https://example.com/path?key=value")
	f.Add("https://example.com/search?q=hello+world&page=1")
	f.Add("https://example.com/?a=1&b=2&c=3")
	f.Add("https://example.com/path?key=val%20ue&k2=%26amp")
	f.Add("https://example.com/?empty=&also_empty=")
	f.Add("https://example.com/?=no_key")
	f.Add("https://example.com/?repeated=a&repeated=b&repeated=c")
	f.Add("")                          // empty string
	f.Add("not-a-url")                // no scheme
	f.Add("https://example.com/path") // no query at all
	f.Add("?just=query")              // query only, no host
	f.Add("https://example.com/?a=1&&b=2") // double ampersand
	f.Add("https://example.com/?%ZZ=bad")  // invalid percent encoding

	f.Fuzz(func(t *testing.T, rawURL string) {
		params, err := ParseQuery(rawURL)

		// Invariant 1: function must never panic (implicit — if it panics, fuzz catches it)

		if err != nil {
			// If it returns an error, that's fine — just no panic
			return
		}

		// Invariant 2: all returned keys and values must be valid strings (not corrupted)
		for key, values := range params {
			if key != strings.ToValidUTF8(key, "") {
				t.Errorf("key contains invalid UTF-8: %q", key)
			}
			for _, v := range values {
				if v != strings.ToValidUTF8(v, "") {
					t.Errorf("value contains invalid UTF-8: %q", v)
				}
			}
		}

		// Invariant 3: re-parsing should be stable (idempotent after normalization)
		if params != nil {
			rebuilt := url.Values(params).Encode()
			params2, err2 := ParseQuery("https://x.com/?" + rebuilt)
			if err2 != nil {
				t.Errorf("re-parse failed: %v (rebuilt query: %s)", err2, rebuilt)
			}
			// Check same number of keys
			if len(params2) != len(params) {
				t.Errorf("re-parse key count %d != original %d", len(params2), len(params))
			}
		}
	})
}
```

**Running:**

```bash
# Run seed corpus only (like a normal test):
go test -run FuzzParseQuery -v

# Actually fuzz (runs indefinitely until stopped or crash found):
go test -fuzz=FuzzParseQuery -fuzztime=30s

# Run a specific crasher found by the fuzzer:
go test -run FuzzParseQuery/testdata/fuzz/FuzzParseQuery/abc123
```

**Crasher files** are saved to `testdata/fuzz/FuzzParseQuery/` and look like:

```
go test fuzz v1
string("https://example.com/?%\x00=x")
```

Key design points:

1. **Seed corpus** covers edges you already know: empty strings, encoding, duplicates, malformed input.
2. **Invariants over exact assertions**: fuzz targets check properties (no panic, valid UTF-8, idempotent re-parse) rather than exact values.
3. **`f.Add` types must match `f.Fuzz` parameter types** exactly.
4. **Commit `testdata/fuzz/`** so found crashers become permanent regression tests.
5. **Seed corpus also runs as regular tests** with `go test`, no `-fuzz` flag needed.'''),

    ("go_deep/benchmark_memory_alloc", r'''How do I write benchmark tests in Go that track memory allocations? I want to compare two implementations of a string builder.''', r'''<think>
Go benchmark tests use testing.B. For memory allocation tracking:
- b.ReportAllocs() reports alloc stats per operation
- b.ResetTimer() excludes setup time
- The benchmark framework runs b.N iterations, automatically adjusting N
- Memory stats show allocs/op and bytes/op
- You can also use b.ReportMetric() for custom metrics
- benchstat tool compares benchmark results across runs
To compare two implementations, write separate Benchmark functions with
clear names. Run with -bench=. -benchmem. The -count flag runs multiple
times for statistical significance.
For string building: comparing naive concatenation vs strings.Builder vs
bytes.Buffer vs pre-allocated builder shows dramatic allocation differences.
I should show realistic implementations, proper benchmark structure, and
how to interpret the output. Also show how to use b.RunParallel for
concurrent benchmarks and sub-benchmarks for different input sizes.
Important: don't allocate the test data inside the benchmark loop,
use b.ResetTimer() after setup, and make sure the compiler doesn't
optimize away the result (assign to a package-level variable).
</think>

Here is a complete benchmark comparing string builder implementations with allocation tracking:

```go
package strbuild

import (
	"bytes"
	"strings"
	"testing"
)

// --- Implementations to benchmark ---

// ConcatNaive uses += concatenation (O(n^2) allocations).
func ConcatNaive(parts []string) string {
	var result string
	for _, p := range parts {
		result += p
	}
	return result
}

// ConcatBuilder uses strings.Builder (amortized O(1) append).
func ConcatBuilder(parts []string) string {
	var b strings.Builder
	for _, p := range parts {
		b.WriteString(p)
	}
	return b.String()
}

// ConcatBuilderPrealloc pre-sizes the buffer.
func ConcatBuilderPrealloc(parts []string) string {
	total := 0
	for _, p := range parts {
		total += len(p)
	}
	var b strings.Builder
	b.Grow(total)
	for _, p := range parts {
		b.WriteString(p)
	}
	return b.String()
}

// ConcatBuffer uses bytes.Buffer.
func ConcatBuffer(parts []string) string {
	var buf bytes.Buffer
	for _, p := range parts {
		buf.WriteString(p)
	}
	return buf.String()
}

// --- Benchmarks ---

// Prevent compiler from optimizing away results.
var sink string

func generateParts(n int) []string {
	parts := make([]string, n)
	for i := range parts {
		parts[i] = "hello world "
	}
	return parts
}

func BenchmarkConcat(b *testing.B) {
	sizes := []struct {
		name string
		n    int
	}{
		{"10_parts", 10},
		{"100_parts", 100},
		{"1000_parts", 1000},
	}

	for _, sz := range sizes {
		parts := generateParts(sz.n)

		b.Run("Naive/"+sz.name, func(b *testing.B) {
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				sink = ConcatNaive(parts)
			}
		})

		b.Run("Builder/"+sz.name, func(b *testing.B) {
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				sink = ConcatBuilder(parts)
			}
		})

		b.Run("BuilderPrealloc/"+sz.name, func(b *testing.B) {
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				sink = ConcatBuilderPrealloc(parts)
			}
		})

		b.Run("Buffer/"+sz.name, func(b *testing.B) {
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				sink = ConcatBuffer(parts)
			}
		})
	}
}

// BenchmarkBuilderParallel shows concurrent benchmark usage.
func BenchmarkBuilderParallel(b *testing.B) {
	parts := generateParts(100)

	b.ReportAllocs()
	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			_ = ConcatBuilderPrealloc(parts)
		}
	})
}
```

**Running benchmarks:**

```bash
# Run all benchmarks with memory stats:
go test -bench=. -benchmem -count=5 | tee bench.txt

# Example output:
# BenchmarkConcat/Naive/100_parts-8         15204    78542 ns/op   125408 B/op   99 allocs/op
# BenchmarkConcat/Builder/100_parts-8      542857     2208 ns/op     3072 B/op    7 allocs/op
# BenchmarkConcat/BuilderPrealloc/100_parts-8  818445  1463 ns/op  1200 B/op    1 allocs/op
# BenchmarkConcat/Buffer/100_parts-8       490446     2447 ns/op     3568 B/op    5 allocs/op

# Compare two runs with benchstat:
go test -bench=. -benchmem -count=10 > old.txt
# ... make changes ...
go test -bench=. -benchmem -count=10 > new.txt
benchstat old.txt new.txt
```

Key points:

1. **`b.ReportAllocs()`** adds `B/op` (bytes per operation) and `allocs/op` to output.
2. **`b.ResetTimer()`** excludes setup (generating test data) from timing.
3. **`sink` package variable** prevents the compiler from eliminating the function call as dead code.
4. **Sub-benchmarks** (`b.Run`) test multiple input sizes under one function.
5. **`-count=5`** runs each benchmark 5 times so `benchstat` can compute confidence intervals.
6. **Naive concatenation** shows O(n) allocations; `Builder.Grow` achieves exactly 1 allocation.'''),

    ("go_deep/mock_interfaces_no_deps", r'''How do I create mocks using interfaces in Go without any external mocking library? I want to test a service that sends notifications.''', r'''<think>
Go's interface-based design makes manual mocking natural and simple. The pattern:
1. Define a small interface for the dependency (not the implementation)
2. Production code accepts the interface
3. Test code provides a mock struct that implements the interface
4. The mock records calls and returns configurable values
Key principles:
- Accept interfaces, return structs
- Keep interfaces small (1-3 methods) — interface segregation
- The mock struct has fields for: return values, call counts, received args
- Use function fields for flexible per-test behavior
- No need for gomock, mockery, or any external tool
I should show a notification service that depends on an email sender and an SMS
sender. The test mocks both. I'll show two mock styles: struct-with-fields
(simple) and function-field (flexible). Also demonstrate verifying calls were
made with expected arguments, simulating errors, and testing retry logic.
Important to show t.Helper() on assertion helpers and how to verify
the mock was called the expected number of times.
</think>

Here is a complete example of interface-based mocking without external dependencies:

```go
package notify

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"testing"
)

// --- Interfaces (small, focused) ---

type EmailSender interface {
	SendEmail(ctx context.Context, to, subject, body string) error
}

type SMSSender interface {
	SendSMS(ctx context.Context, phone, message string) error
}

// --- Production service ---

type NotificationService struct {
	email EmailSender
	sms   SMSSender
}

func NewNotificationService(email EmailSender, sms SMSSender) *NotificationService {
	return &NotificationService{email: email, sms: sms}
}

type Alert struct {
	UserEmail string
	UserPhone string
	Title     string
	Message   string
}

func (s *NotificationService) SendAlert(ctx context.Context, alert Alert) error {
	emailErr := s.email.SendEmail(ctx, alert.UserEmail, alert.Title, alert.Message)
	smsErr := s.sms.SendSMS(ctx, alert.UserPhone, alert.Title+": "+alert.Message)
	return errors.Join(emailErr, smsErr)
}

// --- Mock: struct-with-fields style ---

type MockEmailSender struct {
	mu       sync.Mutex
	Calls    []EmailCall
	ErrToReturn error
}

type EmailCall struct {
	To, Subject, Body string
}

func (m *MockEmailSender) SendEmail(_ context.Context, to, subject, body string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.Calls = append(m.Calls, EmailCall{To: to, Subject: subject, Body: body})
	return m.ErrToReturn
}

func (m *MockEmailSender) CallCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.Calls)
}

// --- Mock: function-field style (more flexible) ---

type MockSMSSender struct {
	mu      sync.Mutex
	Calls   []SMSCall
	SendFn  func(ctx context.Context, phone, message string) error
}

type SMSCall struct {
	Phone, Message string
}

func (m *MockSMSSender) SendSMS(ctx context.Context, phone, message string) error {
	m.mu.Lock()
	m.Calls = append(m.Calls, SMSCall{Phone: phone, Message: message})
	m.mu.Unlock()

	if m.SendFn != nil {
		return m.SendFn(ctx, phone, message)
	}
	return nil
}

// --- Tests ---

func TestSendAlert_Success(t *testing.T) {
	email := &MockEmailSender{}
	sms := &MockSMSSender{}
	svc := NewNotificationService(email, sms)

	alert := Alert{
		UserEmail: "alice@example.com",
		UserPhone: "+15551234567",
		Title:     "Server Down",
		Message:   "Web server is not responding",
	}

	err := svc.SendAlert(context.Background(), alert)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Verify email was sent with correct args
	if email.CallCount() != 1 {
		t.Fatalf("email call count = %d, want 1", email.CallCount())
	}
	call := email.Calls[0]
	if call.To != "alice@example.com" {
		t.Errorf("email to = %q, want alice@example.com", call.To)
	}
	if call.Subject != "Server Down" {
		t.Errorf("email subject = %q, want Server Down", call.Subject)
	}

	// Verify SMS was sent
	if len(sms.Calls) != 1 {
		t.Fatalf("sms call count = %d, want 1", len(sms.Calls))
	}
	if sms.Calls[0].Phone != "+15551234567" {
		t.Errorf("sms phone = %q, want +15551234567", sms.Calls[0].Phone)
	}
}

func TestSendAlert_EmailFails_SMSStillSent(t *testing.T) {
	email := &MockEmailSender{ErrToReturn: fmt.Errorf("SMTP timeout")}
	sms := &MockSMSSender{}
	svc := NewNotificationService(email, sms)

	err := svc.SendAlert(context.Background(), Alert{
		UserEmail: "bob@example.com",
		UserPhone: "+15559876543",
		Title:     "Alert",
		Message:   "Disk full",
	})

	// Should return the email error but SMS should still be attempted
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, email.ErrToReturn) {
		t.Errorf("error = %v, want SMTP timeout", err)
	}
	if len(sms.Calls) != 1 {
		t.Error("SMS should still be sent even when email fails")
	}
}

func TestSendAlert_SMSFailsConditionally(t *testing.T) {
	email := &MockEmailSender{}
	callCount := 0
	sms := &MockSMSSender{
		SendFn: func(_ context.Context, phone, _ string) error {
			callCount++
			if phone == "+1invalid" {
				return fmt.Errorf("invalid phone number")
			}
			return nil
		},
	}
	svc := NewNotificationService(email, sms)

	err := svc.SendAlert(context.Background(), Alert{
		UserEmail: "x@y.com",
		UserPhone: "+1invalid",
		Title:     "Test",
		Message:   "msg",
	})

	if err == nil {
		t.Fatal("expected error for invalid phone")
	}
}
```

Key points:

1. **Accept interfaces, return structs** — `NewNotificationService` takes `EmailSender` and `SMSSender` interfaces, production code passes real implementations.
2. **Struct-with-fields mock** (`MockEmailSender`): set `ErrToReturn` before the test, inspect `Calls` after. Simple and covers most cases.
3. **Function-field mock** (`MockSMSSender`): set `SendFn` for per-test custom behavior like conditional errors.
4. **Mutex-protected Calls slice** makes mocks safe for concurrent tests.
5. **No external dependencies** — this pattern works with the standard library alone and is idiomatic Go.'''),

    ("go_deep/integration_tests_build_tags", r'''How do I use build tags to separate integration tests from unit tests in Go? I want integration tests to only run when explicitly requested.''', r'''<think>
Build tags (build constraints) control which files get compiled. For integration tests:
- Use //go:build integration at the top of test files
- Normal `go test` skips them (tag not set)
- Run with `go test -tags=integration` to include them
- Alternative approach: use testing.Short() but that's opt-out, not opt-in
Build tag approach is better because:
- Integration tests are completely invisible during normal `go test ./...`
- No risk of accidentally running slow/external tests in CI unit test step
- CI pipeline can have separate stages: unit (no tag) and integration (-tags=integration)
The //go:build line must be the first line in the file (before package).
Go 1.17+ uses //go:build syntax (replacing // +build).
I should show a realistic example: a service that talks to a database, with
unit tests in a normal file and integration tests in a tagged file.
Also show how to combine tags (e.g., integration AND postgres).
</think>

Here is the complete pattern for separating integration tests with build tags:

```go
// file: userstore.go
package userstore

import (
	"context"
	"database/sql"
	"fmt"
)

type User struct {
	ID    int64
	Name  string
	Email string
}

type Store struct {
	db *sql.DB
}

func NewStore(db *sql.DB) *Store {
	return &Store{db: db}
}

func (s *Store) Create(ctx context.Context, name, email string) (*User, error) {
	result, err := s.db.ExecContext(ctx,
		"INSERT INTO users (name, email) VALUES ($1, $2)", name, email)
	if err != nil {
		return nil, fmt.Errorf("insert user: %w", err)
	}
	id, _ := result.LastInsertId()
	return &User{ID: id, Name: name, Email: email}, nil
}

func (s *Store) GetByEmail(ctx context.Context, email string) (*User, error) {
	u := &User{}
	err := s.db.QueryRowContext(ctx,
		"SELECT id, name, email FROM users WHERE email = $1", email).
		Scan(&u.ID, &u.Name, &u.Email)
	if err != nil {
		return nil, fmt.Errorf("get user by email: %w", err)
	}
	return u, nil
}
```

```go
// file: userstore_test.go
// Unit tests — always run with `go test`
package userstore

import (
	"testing"
)

func TestUserValidation(t *testing.T) {
	// Pure logic tests that don't need a database
	tests := []struct {
		name  string
		email string
		valid bool
	}{
		{"valid", "alice@example.com", true},
		{"empty", "", false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			valid := tt.email != ""
			if valid != tt.valid {
				t.Errorf("validate(%q) = %v, want %v", tt.email, valid, tt.valid)
			}
		})
	}
}
```

```go
// file: userstore_integration_test.go
//go:build integration

// Integration tests — only run with `go test -tags=integration`
package userstore

import (
	"context"
	"database/sql"
	"os"
	"testing"

	_ "github.com/lib/pq"
)

var testDB *sql.DB

func TestMain(m *testing.M) {
	// Setup: connect to real database
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		dsn = "postgres://localhost:5432/testdb?sslmode=disable"
	}

	var err error
	testDB, err = sql.Open("postgres", dsn)
	if err != nil {
		panic("connect to test db: " + err.Error())
	}

	// Create schema
	testDB.Exec(`CREATE TABLE IF NOT EXISTS users (
		id SERIAL PRIMARY KEY,
		name TEXT NOT NULL,
		email TEXT UNIQUE NOT NULL
	)`)

	// Run tests
	code := m.Run()

	// Teardown
	testDB.Exec("DROP TABLE IF EXISTS users")
	testDB.Close()

	os.Exit(code)
}

func cleanTable(t *testing.T) {
	t.Helper()
	t.Cleanup(func() {
		testDB.Exec("DELETE FROM users")
	})
}

func TestStore_CreateAndGet(t *testing.T) {
	cleanTable(t)
	store := NewStore(testDB)
	ctx := context.Background()

	created, err := store.Create(ctx, "Alice", "alice@test.com")
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	if created.ID == 0 {
		t.Error("expected non-zero ID")
	}

	got, err := store.GetByEmail(ctx, "alice@test.com")
	if err != nil {
		t.Fatalf("GetByEmail: %v", err)
	}
	if got.Name != "Alice" {
		t.Errorf("name = %q, want Alice", got.Name)
	}
}

func TestStore_DuplicateEmail(t *testing.T) {
	cleanTable(t)
	store := NewStore(testDB)
	ctx := context.Background()

	_, err := store.Create(ctx, "Alice", "dup@test.com")
	if err != nil {
		t.Fatalf("first Create: %v", err)
	}

	_, err = store.Create(ctx, "Bob", "dup@test.com")
	if err == nil {
		t.Error("expected error on duplicate email, got nil")
	}
}
```

```go
// file: userstore_postgres_test.go
//go:build integration && postgres

// Tests specific to PostgreSQL features (e.g., JSONB, arrays)
package userstore

import (
	"testing"
)

func TestStore_PostgresSpecific(t *testing.T) {
	cleanTable(t)
	// Test PostgreSQL-specific features like JSONB columns
	t.Log("testing postgres-specific features")
}
```

**Running:**

```bash
# Unit tests only (default):
go test ./...

# Integration tests included:
go test -tags=integration ./...

# PostgreSQL-specific integration tests:
go test -tags='integration,postgres' ./...

# CI pipeline example:
# Stage 1: go test ./...
# Stage 2: go test -tags=integration -count=1 ./...
```

Key points:

1. **`//go:build integration`** must be the very first line of the file, before the blank line and `package` statement.
2. **Normal `go test ./...`** completely ignores tagged files. No slow tests, no external dependencies needed.
3. **`TestMain`** handles database setup/teardown for the entire test suite.
4. **`cleanTable` with `t.Cleanup`** isolates each test without worrying about ordering.
5. **Tags compose**: `//go:build integration && postgres` requires both tags.
6. **`-count=1` in CI** disables test caching so integration tests always hit the real database.'''),

    ("go_deep/testcontainers_database", r'''How do I use testcontainers-go to write database integration tests with a real PostgreSQL container?''', r'''<think>
testcontainers-go spins up Docker containers for integration tests. This gives you
a real database without needing a pre-configured test environment. The pattern:
1. Start a PostgreSQL container in TestMain or a helper
2. Get the dynamic port mapping
3. Connect with database/sql
4. Run tests against the real database
5. Container auto-cleans on test completion
Key details:
- testcontainers-go v0.20+ uses the Testcontainers module pattern
- The postgres module simplifies setup (auto-waits for readiness)
- Use t.Cleanup or TestMain for container lifecycle
- Each test can get a fresh database or use transaction rollback for isolation
- Container reuse across tests in the same package saves startup time
- Need Docker running on the host
I should show both approaches: TestMain for package-wide container, and
per-test container. Also show database migration within the test setup
and transaction rollback pattern for test isolation.
</think>

Here is a complete testcontainers-go setup for PostgreSQL integration tests:

```go
//go:build integration

package repo

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"testing"
	"time"

	_ "github.com/lib/pq"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/modules/postgres"
	"github.com/testcontainers/testcontainers-go/wait"
)

var testDB *sql.DB

func TestMain(m *testing.M) {
	ctx := context.Background()

	// Start a real PostgreSQL container
	pgContainer, err := postgres.Run(ctx,
		"postgres:16-alpine",
		postgres.WithDatabase("testdb"),
		postgres.WithUsername("testuser"),
		postgres.WithPassword("testpass"),
		testcontainers.WithWaitStrategy(
			wait.ForLog("database system is ready to accept connections").
				WithOccurrence(2).
				WithStartupTimeout(30*time.Second),
		),
	)
	if err != nil {
		panic("start postgres container: " + err.Error())
	}

	// Get the connection string with the dynamic port
	connStr, err := pgContainer.ConnectionString(ctx, "sslmode=disable")
	if err != nil {
		panic("get connection string: " + err.Error())
	}

	testDB, err = sql.Open("postgres", connStr)
	if err != nil {
		panic("connect: " + err.Error())
	}

	// Run migrations
	if err := migrate(testDB); err != nil {
		panic("migrate: " + err.Error())
	}

	// Run tests
	code := m.Run()

	// Cleanup: stop container
	testDB.Close()
	pgContainer.Terminate(ctx)

	os.Exit(code)
}

func migrate(db *sql.DB) error {
	_, err := db.Exec(`
		CREATE TABLE IF NOT EXISTS products (
			id SERIAL PRIMARY KEY,
			name TEXT NOT NULL,
			price_cents INT NOT NULL CHECK (price_cents >= 0),
			created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		);
		CREATE INDEX IF NOT EXISTS idx_products_name ON products (name);
	`)
	return err
}

// --- Production code ---

type Product struct {
	ID        int64
	Name      string
	PriceCents int
	CreatedAt time.Time
}

type ProductRepo struct {
	db *sql.DB
}

func NewProductRepo(db *sql.DB) *ProductRepo {
	return &ProductRepo{db: db}
}

func (r *ProductRepo) Create(ctx context.Context, name string, priceCents int) (*Product, error) {
	p := &Product{}
	err := r.db.QueryRowContext(ctx,
		`INSERT INTO products (name, price_cents)
		 VALUES ($1, $2)
		 RETURNING id, name, price_cents, created_at`,
		name, priceCents,
	).Scan(&p.ID, &p.Name, &p.PriceCents, &p.CreatedAt)
	if err != nil {
		return nil, fmt.Errorf("create product: %w", err)
	}
	return p, nil
}

func (r *ProductRepo) GetByID(ctx context.Context, id int64) (*Product, error) {
	p := &Product{}
	err := r.db.QueryRowContext(ctx,
		"SELECT id, name, price_cents, created_at FROM products WHERE id = $1", id,
	).Scan(&p.ID, &p.Name, &p.PriceCents, &p.CreatedAt)
	if err != nil {
		return nil, fmt.Errorf("get product %d: %w", id, err)
	}
	return p, nil
}

// --- Transaction rollback pattern for test isolation ---

func withTx(t *testing.T) *sql.Tx {
	t.Helper()
	tx, err := testDB.Begin()
	if err != nil {
		t.Fatalf("begin tx: %v", err)
	}
	t.Cleanup(func() {
		tx.Rollback() // always rollback — no data persists between tests
	})
	return tx
}

// TxProductRepo wraps ProductRepo to work within a transaction.
type TxProductRepo struct {
	tx *sql.Tx
}

func (r *TxProductRepo) Create(ctx context.Context, name string, priceCents int) (*Product, error) {
	p := &Product{}
	err := r.tx.QueryRowContext(ctx,
		`INSERT INTO products (name, price_cents)
		 VALUES ($1, $2)
		 RETURNING id, name, price_cents, created_at`,
		name, priceCents,
	).Scan(&p.ID, &p.Name, &p.PriceCents, &p.CreatedAt)
	if err != nil {
		return nil, fmt.Errorf("create product: %w", err)
	}
	return p, nil
}

// --- Tests ---

func TestProductRepo_Create(t *testing.T) {
	tx := withTx(t)
	repo := &TxProductRepo{tx: tx}
	ctx := context.Background()

	p, err := repo.Create(ctx, "Widget", 1999)
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	if p.ID == 0 {
		t.Error("expected non-zero ID")
	}
	if p.Name != "Widget" {
		t.Errorf("name = %q, want Widget", p.Name)
	}
	if p.PriceCents != 1999 {
		t.Errorf("price = %d, want 1999", p.PriceCents)
	}
	if p.CreatedAt.IsZero() {
		t.Error("created_at should be set")
	}
}

func TestProductRepo_CreateAndGet(t *testing.T) {
	// Uses direct DB (not tx) — cleanup via DELETE
	repo := NewProductRepo(testDB)
	ctx := context.Background()

	created, err := repo.Create(ctx, "Gadget", 4999)
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	t.Cleanup(func() {
		testDB.Exec("DELETE FROM products WHERE id = $1", created.ID)
	})

	got, err := repo.GetByID(ctx, created.ID)
	if err != nil {
		t.Fatalf("GetByID: %v", err)
	}
	if got.Name != "Gadget" {
		t.Errorf("name = %q, want Gadget", got.Name)
	}
}

func TestProductRepo_NegativePrice(t *testing.T) {
	tx := withTx(t)
	repo := &TxProductRepo{tx: tx}
	ctx := context.Background()

	_, err := repo.Create(ctx, "Bad Item", -100)
	if err == nil {
		t.Error("expected error for negative price, got nil")
	}
}
```

**Running:**

```bash
# Requires Docker running:
go test -tags=integration -v -count=1 ./repo/

# With custom timeout for slow CI:
go test -tags=integration -timeout=120s ./repo/
```

Key points:

1. **`postgres.Run`** starts a real PostgreSQL container with automatic readiness waiting.
2. **Dynamic port mapping** means no port conflicts. The container picks an available port.
3. **Transaction rollback** (`withTx`) gives each test a clean slate without deleting data — the rollback in `t.Cleanup` undoes all writes.
4. **Migrations run once** in `TestMain` and persist for all tests in the package.
5. **`pgContainer.Terminate`** stops and removes the container after all tests complete.
6. **Build tag `integration`** ensures these never run during normal `go test ./...`.'''),

    ("go_deep/httptest_handler_testing", r'''How do I test HTTP handlers in Go using httptest? I want to test a REST API with JSON request/response, middleware, and error handling.''', r'''<think>
The httptest package provides two key tools:
- httptest.NewRequest: creates an *http.Request for testing
- httptest.NewRecorder: captures the response (implements http.ResponseWriter)
- httptest.NewServer: starts a real HTTP server for integration-style tests
For handler testing, the recorder approach is preferred because it's fast
and doesn't need a network. For middleware testing, you wrap the handler.
Key patterns:
- Test the handler function directly with recorder
- Use json.NewDecoder on recorder.Body for response parsing
- Set request headers, body, URL params
- Test middleware by wrapping a simple handler
- Use httptest.NewServer for tests that need a real HTTP client
- For chi/gorilla/echo route params, you may need router-specific context
I should show: JSON POST handler, middleware (auth), error responses,
and a table-driven approach for multiple scenarios.
</think>

Here is a complete HTTP handler testing setup:

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

// --- Production handlers ---

type CreateUserRequest struct {
	Name  string `json:"name"`
	Email string `json:"email"`
}

type UserResponse struct {
	ID    int    `json:"id"`
	Name  string `json:"name"`
	Email string `json:"email"`
}

type ErrorResponse struct {
	Error string `json:"error"`
	Code  int    `json:"code"`
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func HandleCreateUser(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{
			Error: "method not allowed", Code: 405,
		})
		return
	}

	var req CreateUserRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{
			Error: "invalid JSON", Code: 400,
		})
		return
	}

	if req.Name == "" || req.Email == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{
			Error: "name and email are required", Code: 400,
		})
		return
	}

	// Simulate creation
	writeJSON(w, http.StatusCreated, UserResponse{
		ID: 1, Name: req.Name, Email: req.Email,
	})
}

// Middleware: API key authentication
func RequireAPIKey(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := r.Header.Get("X-API-Key")
		if key == "" || key != "secret-key-123" {
			writeJSON(w, http.StatusUnauthorized, ErrorResponse{
				Error: "invalid API key", Code: 401,
			})
			return
		}
		next.ServeHTTP(w, r)
	})
}

func HandleHealthCheck(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// --- Tests ---

func TestHandleCreateUser(t *testing.T) {
	tests := []struct {
		name       string
		method     string
		body       string
		wantStatus int
		wantBody   func(t *testing.T, body []byte)
	}{
		{
			name:       "success",
			method:     http.MethodPost,
			body:       `{"name":"Alice","email":"alice@example.com"}`,
			wantStatus: http.StatusCreated,
			wantBody: func(t *testing.T, body []byte) {
				var resp UserResponse
				if err := json.Unmarshal(body, &resp); err != nil {
					t.Fatalf("unmarshal: %v", err)
				}
				if resp.Name != "Alice" {
					t.Errorf("name = %q, want Alice", resp.Name)
				}
				if resp.ID == 0 {
					t.Error("expected non-zero ID")
				}
			},
		},
		{
			name:       "missing fields",
			method:     http.MethodPost,
			body:       `{"name":"Alice"}`,
			wantStatus: http.StatusBadRequest,
			wantBody: func(t *testing.T, body []byte) {
				var resp ErrorResponse
				json.Unmarshal(body, &resp)
				if resp.Error != "name and email are required" {
					t.Errorf("error = %q", resp.Error)
				}
			},
		},
		{
			name:       "invalid JSON",
			method:     http.MethodPost,
			body:       `{invalid`,
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "wrong method",
			method:     http.MethodGet,
			body:       "",
			wantStatus: http.StatusMethodNotAllowed,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var body io.Reader
			if tt.body != "" {
				body = strings.NewReader(tt.body)
			}

			req := httptest.NewRequest(tt.method, "/users", body)
			req.Header.Set("Content-Type", "application/json")

			rec := httptest.NewRecorder()
			HandleCreateUser(rec, req)

			if rec.Code != tt.wantStatus {
				t.Errorf("status = %d, want %d", rec.Code, tt.wantStatus)
			}
			if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
				t.Errorf("content-type = %q, want application/json", ct)
			}
			if tt.wantBody != nil {
				tt.wantBody(t, rec.Body.Bytes())
			}
		})
	}
}

func TestRequireAPIKey_Middleware(t *testing.T) {
	// Wrap a simple handler with the middleware
	handler := RequireAPIKey(http.HandlerFunc(HandleHealthCheck))

	t.Run("valid key", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/health", nil)
		req.Header.Set("X-API-Key", "secret-key-123")
		rec := httptest.NewRecorder()

		handler.ServeHTTP(rec, req)

		if rec.Code != http.StatusOK {
			t.Errorf("status = %d, want 200", rec.Code)
		}
	})

	t.Run("missing key", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/health", nil)
		rec := httptest.NewRecorder()

		handler.ServeHTTP(rec, req)

		if rec.Code != http.StatusUnauthorized {
			t.Errorf("status = %d, want 401", rec.Code)
		}
	})

	t.Run("wrong key", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/health", nil)
		req.Header.Set("X-API-Key", "wrong-key")
		rec := httptest.NewRecorder()

		handler.ServeHTTP(rec, req)

		if rec.Code != http.StatusUnauthorized {
			t.Errorf("status = %d, want 401", rec.Code)
		}
	})
}

// TestWithRealServer uses httptest.NewServer for full HTTP roundtrip.
func TestWithRealServer(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/users", HandleCreateUser)

	srv := httptest.NewServer(RequireAPIKey(mux))
	defer srv.Close()

	// Real HTTP request
	body := strings.NewReader(`{"name":"Bob","email":"bob@example.com"}`)
	req, _ := http.NewRequest(http.MethodPost, srv.URL+"/users", body)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-API-Key", "secret-key-123")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		t.Errorf("status = %d, want 201", resp.StatusCode)
	}

	var user UserResponse
	json.NewDecoder(resp.Body).Decode(&user)
	if user.Name != "Bob" {
		t.Errorf("name = %q, want Bob", user.Name)
	}
}
```

Key points:

1. **`httptest.NewRecorder()`** captures status code, headers, and body without network overhead.
2. **`httptest.NewRequest()`** creates a request without a running server.
3. **Table-driven tests** with a `wantBody` function field allow flexible per-case assertions.
4. **Middleware testing**: wrap a known handler, assert the middleware's behavior in isolation.
5. **`httptest.NewServer()`** starts a real server on a random port for full integration tests with `http.Client`.'''),

    ("go_deep/race_detector_tests", r'''How does the Go race detector work and how do I write race-free tests? Show me common race condition patterns and their fixes.''', r'''<think>
The Go race detector (-race flag) uses ThreadSanitizer to detect data races at runtime.
A data race occurs when two goroutines access the same variable concurrently and at
least one access is a write. The detector instruments memory accesses and reports races.
Common race patterns in tests:
1. Shared variable without synchronization
2. Closure capturing loop variable
3. Testing concurrent code without proper synchronization
4. Test helpers sharing state across parallel subtests
Fixes: mutexes, channels, atomic operations, or redesigning to avoid shared state.
Important: -race has ~2-10x CPU overhead and 5-10x memory overhead.
It only detects races that actually execute — it's not static analysis.
I should show concrete examples of races and their fixes, including
the subtle ones that people miss: map concurrent access, slice append
from multiple goroutines, and the classic test race where the test
reads a variable that a goroutine is still writing.
</think>

Here is a comprehensive guide to race detection and writing race-free code:

```go
package raceexamples

import (
	"sync"
	"sync/atomic"
	"testing"
)

// ============================================================
// PATTERN 1: Shared counter — RACE
// ============================================================

type UnsafeCounter struct {
	count int // BUG: unprotected
}

func (c *UnsafeCounter) Inc() { c.count++ }
func (c *UnsafeCounter) Val() int { return c.count }

// This test WILL trigger the race detector.
func TestUnsafeCounter_RACE(t *testing.T) {
	t.Skip("intentionally racy — demonstrates the bug")
	c := &UnsafeCounter{}
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			c.Inc() // DATA RACE: concurrent write
		}()
	}
	wg.Wait()
	t.Log(c.Val()) // DATA RACE: concurrent read
}

// FIX: Use atomic or mutex.

type AtomicCounter struct {
	count atomic.Int64
}

func (c *AtomicCounter) Inc()      { c.count.Add(1) }
func (c *AtomicCounter) Val() int64 { return c.count.Load() }

func TestAtomicCounter_Safe(t *testing.T) {
	c := &AtomicCounter{}
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			c.Inc()
		}()
	}
	wg.Wait()
	if got := c.Val(); got != 100 {
		t.Errorf("count = %d, want 100", got)
	}
}

// ============================================================
// PATTERN 2: Concurrent map access — RACE
// ============================================================

// Maps are NOT safe for concurrent use.
func TestMapRace_RACE(t *testing.T) {
	t.Skip("intentionally racy")
	m := make(map[string]int)
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			m["key"] = n // RACE: concurrent map writes cause panic
		}(i)
	}
	wg.Wait()
}

// FIX: Use sync.Map or mutex-protected map.

type SafeMap struct {
	mu sync.RWMutex
	m  map[string]int
}

func NewSafeMap() *SafeMap {
	return &SafeMap{m: make(map[string]int)}
}

func (s *SafeMap) Set(key string, val int) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.m[key] = val
}

func (s *SafeMap) Get(key string) (int, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	v, ok := s.m[key]
	return v, ok
}

func TestSafeMap_NoRace(t *testing.T) {
	m := NewSafeMap()
	var wg sync.WaitGroup

	// Concurrent writes
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			m.Set("key", n)
		}(i)
	}

	// Concurrent reads
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			m.Get("key")
		}()
	}

	wg.Wait()
}

// ============================================================
// PATTERN 3: Test goroutine outlives test — RACE
// ============================================================

func TestGoroutineOutlivesTest_RACE(t *testing.T) {
	t.Skip("intentionally racy")
	result := ""
	go func() {
		result = "done" // RACE: writes after test may have returned
	}()
	// Test returns immediately, goroutine still running
	// The next test may see this write — undefined behavior
}

// FIX: Always wait for goroutines to finish.

func TestGoroutineWaited_Safe(t *testing.T) {
	result := make(chan string, 1)
	go func() {
		result <- "done"
	}()
	got := <-result // blocks until goroutine finishes
	if got != "done" {
		t.Errorf("got %q", got)
	}
}

// ============================================================
// PATTERN 4: Parallel subtests with shared slice — RACE
// ============================================================

func TestParallelAppend_RACE(t *testing.T) {
	t.Skip("intentionally racy")
	var results []int
	for i := 0; i < 10; i++ {
		i := i
		t.Run("", func(t *testing.T) {
			t.Parallel()
			results = append(results, i) // RACE: concurrent slice append
		})
	}
}

// FIX: Use a mutex or collect via channels.

func TestParallelCollect_Safe(t *testing.T) {
	var mu sync.Mutex
	var results []int

	for i := 0; i < 10; i++ {
		i := i
		t.Run("", func(t *testing.T) {
			t.Parallel()
			mu.Lock()
			results = append(results, i)
			mu.Unlock()
		})
	}
	// After all subtests finish, we can safely read results
}

// ============================================================
// PATTERN 5: Correct concurrent service test
// ============================================================

type Cache struct {
	mu    sync.RWMutex
	items map[string]string
}

func NewCache() *Cache {
	return &Cache{items: make(map[string]string)}
}

func (c *Cache) Set(k, v string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.items[k] = v
}

func (c *Cache) Get(k string) (string, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	v, ok := c.items[k]
	return v, ok
}

func (c *Cache) Len() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return len(c.items)
}

func TestCache_ConcurrentAccess(t *testing.T) {
	c := NewCache()
	var wg sync.WaitGroup

	// Writers
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			c.Set(string(rune('a'+n%26)), "value")
		}(i)
	}

	// Readers
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			c.Get(string(rune('a' + n%26)))
		}(i)
	}

	wg.Wait()

	if c.Len() == 0 {
		t.Error("cache should not be empty")
	}
}
```

**Running with race detector:**

```bash
# Run all tests with race detection:
go test -race ./...

# Race detector output on failure:
# WARNING: DATA RACE
# Write at 0x00c0000b4018 by goroutine 8:
#   raceexamples.(*UnsafeCounter).Inc()
# Previous write at 0x00c0000b4018 by goroutine 7:
#   raceexamples.(*UnsafeCounter).Inc()
```

Key rules for race-free code:

1. **Every shared variable** must be protected by a mutex, atomic, or channel.
2. **Never let test goroutines outlive the test** — always `sync.WaitGroup` or channel-wait.
3. **Maps require explicit locking** — Go maps panic on concurrent read+write.
4. **`t.Parallel()` subtests** share the parent scope — protect any shared state.
5. **`-race` only detects executed races** — maximize code path coverage for effectiveness.
6. **Always run CI with `-race`** — it catches bugs that only manifest under load.'''),

    ("go_deep/test_coverage_analysis", r'''How do I analyze test coverage in Go and what are meaningful coverage targets? Show me how to find untested code paths.''', r'''<think>
Go has built-in coverage tooling since 1.2, with major improvements in 1.20
(coverage for integration tests and binaries). Key tools:
- go test -cover: shows coverage percentage
- go test -coverprofile=coverage.out: generates profile
- go tool cover -html=coverage.out: visual HTML report
- go tool cover -func=coverage.out: per-function breakdown
Coverage modes: set (hit/not-hit), count (hit count), atomic (thread-safe count)
Meaningful coverage targets:
- 100% is often counterproductive (testing trivial getters)
- 80% is a common reasonable target
- Focus on coverage of critical paths: error handling, edge cases, business logic
- Ignore generated code, main() bootstrapping, trivial accessors
I should show the full workflow: generating profiles, reading them,
finding gaps, and using coverprofile in CI. Also show the Go 1.20+
integration test coverage feature and how to exclude files from coverage.
</think>

Here is a complete coverage analysis workflow:

```go
// file: calc/calc.go
package calc

import (
	"errors"
	"math"
)

var (
	ErrDivisionByZero = errors.New("division by zero")
	ErrNegativeSqrt   = errors.New("cannot take square root of negative number")
	ErrOverflow       = errors.New("result would overflow")
)

func Add(a, b float64) float64 { return a + b }
func Sub(a, b float64) float64 { return a - b }
func Mul(a, b float64) float64 { return a * b }

func Div(a, b float64) (float64, error) {
	if b == 0 {
		return 0, ErrDivisionByZero
	}
	result := a / b
	if math.IsInf(result, 0) || math.IsNaN(result) {
		return 0, ErrOverflow
	}
	return result, nil
}

func Sqrt(x float64) (float64, error) {
	if x < 0 {
		return 0, ErrNegativeSqrt
	}
	return math.Sqrt(x), nil
}

func Power(base, exp float64) (float64, error) {
	result := math.Pow(base, exp)
	if math.IsInf(result, 0) {
		return 0, ErrOverflow
	}
	if math.IsNaN(result) {
		return 0, errors.New("result is NaN")
	}
	return result, nil
}

// Factorial computes n! for non-negative integers.
func Factorial(n int) (int, error) {
	if n < 0 {
		return 0, errors.New("negative factorial")
	}
	if n > 20 {
		return 0, ErrOverflow // 21! overflows int64
	}
	result := 1
	for i := 2; i <= n; i++ {
		result *= i
	}
	return result, nil
}
```

```go
// file: calc/calc_test.go
package calc

import (
	"errors"
	"testing"
)

func TestAdd(t *testing.T) {
	if got := Add(2, 3); got != 5 {
		t.Errorf("Add(2,3) = %f, want 5", got)
	}
}

func TestDiv(t *testing.T) {
	tests := []struct {
		name    string
		a, b    float64
		want    float64
		wantErr error
	}{
		{"normal", 10, 2, 5, nil},
		{"zero divisor", 10, 0, 0, ErrDivisionByZero},
		// NOTE: missing test for overflow case — coverage will show this gap
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := Div(tt.a, tt.b)
			if !errors.Is(err, tt.wantErr) {
				t.Errorf("err = %v, want %v", err, tt.wantErr)
			}
			if err == nil && got != tt.want {
				t.Errorf("Div(%f,%f) = %f, want %f", tt.a, tt.b, got, tt.want)
			}
		})
	}
}

func TestSqrt(t *testing.T) {
	got, err := Sqrt(16)
	if err != nil || got != 4 {
		t.Errorf("Sqrt(16) = %f, %v", got, err)
	}
	_, err = Sqrt(-1)
	if !errors.Is(err, ErrNegativeSqrt) {
		t.Errorf("Sqrt(-1) err = %v, want ErrNegativeSqrt", err)
	}
}

// NOTE: No test for Power() or Factorial() — intentional coverage gap
```

**Coverage commands and workflow:**

```bash
# 1. Quick coverage percentage:
go test -cover ./calc/
# output: ok  calc  0.003s  coverage: 52.6% of statements

# 2. Generate coverage profile:
go test -coverprofile=coverage.out -covermode=count ./calc/

# 3. Per-function breakdown (find uncovered functions):
go tool cover -func=coverage.out
# output:
# calc/calc.go:12:  Add         100.0%
# calc/calc.go:13:  Sub         0.0%      <-- never called
# calc/calc.go:14:  Mul         0.0%      <-- never called
# calc/calc.go:16:  Div         80.0%     <-- missing overflow branch
# calc/calc.go:26:  Sqrt        100.0%
# calc/calc.go:33:  Power       0.0%      <-- never called
# calc/calc.go:44:  Factorial   0.0%      <-- never called
# total:            (statements) 52.6%

# 4. Visual HTML report (opens in browser):
go tool cover -html=coverage.out -o coverage.html
# Green = covered, Red = uncovered, Yellow = partially covered

# 5. Coverage for multiple packages:
go test -coverprofile=coverage.out -coverpkg=./... ./...

# 6. CI enforcement (fail if below threshold):
# In a script or Makefile:
COVERAGE=$(go test -cover ./calc/ | grep -oP '[0-9]+\.[0-9]+(?=%)')
if (( $(echo "$COVERAGE < 80" | bc -l) )); then
    echo "Coverage $COVERAGE% is below 80% threshold"
    exit 1
fi
```

**Go 1.20+ integration test coverage:**

```bash
# Build a coverage-instrumented binary:
go build -cover -o myapp -coverdir=./covdata ./cmd/myapp

# Run integration tests against it:
GOCOVERDIR=./covdata ./myapp &
# ... run integration tests ...
kill %1

# Merge and view:
go tool covdata textfmt -i=./covdata -o=integration.out
go tool cover -html=integration.out
```

**Meaningful coverage guidelines:**

| Area | Target | Why |
|------|--------|-----|
| Business logic | 90%+ | Core correctness matters |
| Error handling | 85%+ | Untested error paths hide bugs |
| HTTP handlers | 80%+ | Cover success + error responses |
| Generated code | Skip | Not worth testing auto-generated code |
| main() / bootstrap | Skip | Tested by integration tests |
| Trivial getters | Optional | Low value per test |

The goal is not 100% coverage but **covering the code paths that matter**. Use `go tool cover -func` to find functions at 0% and prioritize those with complex logic.'''),

    ("go_deep/custom_test_helpers", r'''How do I write custom test helpers in Go using t.Helper()? I want reusable assertion functions that report errors at the correct line number.''', r'''<think>
t.Helper() marks a function as a test helper. When it calls t.Error/t.Fatal,
the error message points to the caller of the helper, not the helper itself.
This is critical for reusable assertions — without it, every error points to
the helper function, making failures hard to locate.
Key patterns:
- Always call t.Helper() as the first line in a helper function
- Helpers can be in the same package or a testutil package
- Chain t.Helper() — if helper A calls helper B, both should call t.Helper()
- Helpers should accept testing.TB (interface satisfied by *testing.T and *testing.B)
- Don't use t.Fatal in helpers called from goroutines (panic, doesn't terminate)
- Return errors from helpers if the caller might want to handle them
I should show common assertion helpers: assertEqual, requireNoError,
assertContains, assertPanics, and a JSON comparison helper. Also show
how to build a test fixture helper that returns values.
</think>

Here is a complete set of reusable test helpers:

```go
package testutil

import (
	"encoding/json"
	"fmt"
	"reflect"
	"strings"
	"testing"
)

// --- Core assertion helpers ---

// Equal fails the test if got != want.
func Equal[T comparable](tb testing.TB, got, want T) {
	tb.Helper()
	if got != want {
		tb.Errorf("got %v, want %v", got, want)
	}
}

// NotEqual fails the test if got == want.
func NotEqual[T comparable](tb testing.TB, got, want T) {
	tb.Helper()
	if got == want {
		tb.Errorf("got %v, should not equal %v", got, want)
	}
}

// RequireEqual fails the test immediately if got != want.
func RequireEqual[T comparable](tb testing.TB, got, want T) {
	tb.Helper()
	if got != want {
		tb.Fatalf("got %v, want %v", got, want)
	}
}

// NoError fails the test if err is not nil.
func NoError(tb testing.TB, err error) {
	tb.Helper()
	if err != nil {
		tb.Fatalf("unexpected error: %v", err)
	}
}

// WantError fails the test if err is nil.
func WantError(tb testing.TB, err error) {
	tb.Helper()
	if err == nil {
		tb.Fatal("expected error, got nil")
	}
}

// ErrorContains checks that err is non-nil and its message contains substr.
func ErrorContains(tb testing.TB, err error, substr string) {
	tb.Helper()
	if err == nil {
		tb.Fatalf("expected error containing %q, got nil", substr)
	}
	if !strings.Contains(err.Error(), substr) {
		tb.Errorf("error %q does not contain %q", err.Error(), substr)
	}
}

// Contains checks if a string contains a substring.
func Contains(tb testing.TB, s, substr string) {
	tb.Helper()
	if !strings.Contains(s, substr) {
		tb.Errorf("%q does not contain %q", s, substr)
	}
}

// DeepEqual compares two values using reflect.DeepEqual.
func DeepEqual(tb testing.TB, got, want any) {
	tb.Helper()
	if !reflect.DeepEqual(got, want) {
		tb.Errorf("got %+v, want %+v", got, want)
	}
}

// Panics verifies that fn panics.
func Panics(tb testing.TB, fn func()) {
	tb.Helper()
	defer func() {
		if r := recover(); r == nil {
			tb.Error("expected panic, but function returned normally")
		}
	}()
	fn()
}

// JSONEqual compares two values by marshaling to JSON (ignoring field order in maps).
func JSONEqual(tb testing.TB, got, want any) {
	tb.Helper()
	gotJSON, err := json.Marshal(got)
	if err != nil {
		tb.Fatalf("marshal got: %v", err)
	}
	wantJSON, err := json.Marshal(want)
	if err != nil {
		tb.Fatalf("marshal want: %v", err)
	}

	var gotVal, wantVal any
	json.Unmarshal(gotJSON, &gotVal)
	json.Unmarshal(wantJSON, &wantVal)

	if !reflect.DeepEqual(gotVal, wantVal) {
		tb.Errorf("JSON mismatch:\n  got:  %s\n  want: %s", gotJSON, wantJSON)
	}
}

// SliceContains checks that a slice contains the expected element.
func SliceContains[T comparable](tb testing.TB, slice []T, want T) {
	tb.Helper()
	for _, v := range slice {
		if v == want {
			return
		}
	}
	tb.Errorf("slice %v does not contain %v", slice, want)
}

// Len checks the length of a slice.
func Len[T any](tb testing.TB, slice []T, want int) {
	tb.Helper()
	if got := len(slice); got != want {
		tb.Errorf("len = %d, want %d", got, want)
	}
}

// --- Fixture helper that returns values ---

// MustParseJSON parses JSON into a map, failing the test on error.
func MustParseJSON(tb testing.TB, data string) map[string]any {
	tb.Helper()
	var result map[string]any
	if err := json.Unmarshal([]byte(data), &result); err != nil {
		tb.Fatalf("parse JSON: %v", err)
	}
	return result
}

// --- Chained helpers (both must call t.Helper) ---

// AssertResponse validates an HTTP-like response struct.
type Response struct {
	Status int
	Body   string
}

func AssertStatus(tb testing.TB, resp Response, want int) {
	tb.Helper()
	Equal(tb, resp.Status, want) // Equal also calls tb.Helper()
}

func AssertBodyContains(tb testing.TB, resp Response, substr string) {
	tb.Helper()
	Contains(tb, resp.Body, substr) // chains to Contains helper
}
```

```go
// file: calc_test.go — using the helpers
package calc

import (
	"errors"
	"fmt"
	"testing"

	"myproject/testutil"
)

func divide(a, b int) (int, error) {
	if b == 0 {
		return 0, fmt.Errorf("divide by zero")
	}
	return a / b, nil
}

func TestDivide(t *testing.T) {
	// Error points to THIS line, not inside the helper
	result, err := divide(10, 2)
	testutil.NoError(t, err)
	testutil.Equal(t, result, 5)

	_, err = divide(10, 0)
	testutil.WantError(t, err)
	testutil.ErrorContains(t, err, "divide by zero")
}

func TestSliceOperations(t *testing.T) {
	items := []string{"apple", "banana", "cherry"}
	testutil.Len(t, items, 3)
	testutil.SliceContains(t, items, "banana")
}

func TestPanicRecovery(t *testing.T) {
	testutil.Panics(t, func() {
		panic("oh no")
	})
}

// Works with benchmarks too (testing.TB interface).
func BenchmarkDivide(b *testing.B) {
	for i := 0; i < b.N; i++ {
		result, err := divide(100, 7)
		testutil.NoError(b, err)
		_ = result
	}
}
```

**Error output comparison:**

```
# WITHOUT t.Helper():
testutil/assert.go:15: got 3, want 5    <-- points to helper, useless

# WITH t.Helper():
calc_test.go:24: got 3, want 5          <-- points to test, useful
```

Key points:

1. **`tb.Helper()` must be the first call** in every helper function, including chained helpers.
2. **Use `testing.TB`** instead of `*testing.T` so helpers work in both tests and benchmarks.
3. **Generics** (`[T comparable]`) make type-safe helpers without interface{} casts.
4. **`t.Fatal` in helpers** stops the test immediately — use for preconditions. Use `t.Error` for assertions where you want to see all failures.
5. **Never call `t.Fatal` from a goroutine** — it calls `runtime.Goexit()` and only terminates that goroutine, not the test.'''),

    ("go_deep/property_based_testing_rapid", r'''How do I do property-based testing in Go using the rapid library? Show me how to test a sorting function with properties instead of specific examples.''', r'''<think>
Property-based testing generates random inputs and verifies invariant properties
hold for all of them, rather than checking specific example-based assertions.
The rapid library (pgregory.net/rapid) is the Go standard for this.
Properties for a sort function:
1. Output length equals input length
2. Output is sorted (each element <= next)
3. Output is a permutation of input (same elements, same count)
4. Idempotent: sorting a sorted slice gives the same result
5. Stability (for stable sort): equal elements maintain relative order
rapid provides generators: rapid.SliceOf, rapid.Int, rapid.String, etc.
The test function receives *rapid.T which has Draw methods for generating values.
If a property fails, rapid automatically shrinks the input to find the minimal
failing case. I should show a realistic example with a custom sort, demonstrate
multiple properties, and show how rapid shrinks failures.
</think>

Here is a complete property-based testing example using rapid:

```go
package sorting

import (
	"slices"
	"sort"
	"testing"

	"pgregory.net/rapid"
)

// --- Production code: custom sort implementation ---

// QuickSort sorts a slice of ints in-place.
func QuickSort(arr []int) []int {
	result := make([]int, len(arr))
	copy(result, arr)
	quicksort(result, 0, len(result)-1)
	return result
}

func quicksort(arr []int, lo, hi int) {
	if lo >= hi {
		return
	}
	pivot := arr[hi]
	i := lo
	for j := lo; j < hi; j++ {
		if arr[j] <= pivot {
			arr[i], arr[j] = arr[j], arr[i]
			i++
		}
	}
	arr[i], arr[hi] = arr[hi], arr[i]
	quicksort(arr, lo, i-1)
	quicksort(arr, i+1, hi)
}

// Deduplicate returns sorted unique elements.
func Deduplicate(arr []int) []int {
	if len(arr) == 0 {
		return nil
	}
	sorted := QuickSort(arr)
	result := []int{sorted[0]}
	for i := 1; i < len(sorted); i++ {
		if sorted[i] != sorted[i-1] {
			result = append(result, sorted[i])
		}
	}
	return result
}

// --- Property-based tests ---

func TestQuickSort_Properties(t *testing.T) {
	// Property 1: Output has same length as input
	t.Run("preserves_length", func(t *testing.T) {
		rapid.Check(t, func(t *rapid.T) {
			input := rapid.SliceOf(rapid.Int()).Draw(t, "input")
			output := QuickSort(input)
			if len(output) != len(input) {
				t.Fatalf("len(output)=%d != len(input)=%d", len(output), len(input))
			}
		})
	})

	// Property 2: Output is sorted
	t.Run("is_sorted", func(t *testing.T) {
		rapid.Check(t, func(t *rapid.T) {
			input := rapid.SliceOf(rapid.Int()).Draw(t, "input")
			output := QuickSort(input)
			if !sort.IntsAreSorted(output) {
				t.Fatalf("output is not sorted: %v", output)
			}
		})
	})

	// Property 3: Output is a permutation of input (same multiset)
	t.Run("is_permutation", func(t *testing.T) {
		rapid.Check(t, func(t *rapid.T) {
			input := rapid.SliceOf(rapid.IntRange(-100, 100)).Draw(t, "input")
			output := QuickSort(input)

			inputCounts := countElements(input)
			outputCounts := countElements(output)

			for k, v := range inputCounts {
				if outputCounts[k] != v {
					t.Fatalf("element %d: input has %d, output has %d",
						k, v, outputCounts[k])
				}
			}
		})
	})

	// Property 4: Idempotent — sorting a sorted slice changes nothing
	t.Run("idempotent", func(t *testing.T) {
		rapid.Check(t, func(t *rapid.T) {
			input := rapid.SliceOf(rapid.Int()).Draw(t, "input")
			once := QuickSort(input)
			twice := QuickSort(once)
			if !slices.Equal(once, twice) {
				t.Fatalf("sort(sort(x)) != sort(x): %v vs %v", twice, once)
			}
		})
	})

	// Property 5: Agrees with stdlib sort
	t.Run("matches_stdlib", func(t *testing.T) {
		rapid.Check(t, func(t *rapid.T) {
			input := rapid.SliceOf(rapid.Int()).Draw(t, "input")

			ours := QuickSort(input)

			stdlib := make([]int, len(input))
			copy(stdlib, input)
			sort.Ints(stdlib)

			if !slices.Equal(ours, stdlib) {
				t.Fatalf("our sort %v != stdlib %v", ours, stdlib)
			}
		})
	})
}

func TestDeduplicate_Properties(t *testing.T) {
	// Property: output is sorted, unique, and subset of input
	t.Run("sorted_unique_subset", func(t *testing.T) {
		rapid.Check(t, func(t *rapid.T) {
			input := rapid.SliceOf(rapid.IntRange(-50, 50)).Draw(t, "input")
			output := Deduplicate(input)

			if len(input) == 0 {
				if output != nil {
					t.Fatalf("expected nil for empty input, got %v", output)
				}
				return
			}

			// Must be sorted
			if !sort.IntsAreSorted(output) {
				t.Fatalf("not sorted: %v", output)
			}

			// Must have no duplicates
			for i := 1; i < len(output); i++ {
				if output[i] == output[i-1] {
					t.Fatalf("duplicate at index %d: %v", i, output)
				}
			}

			// Every output element must exist in input
			inputSet := make(map[int]bool)
			for _, v := range input {
				inputSet[v] = true
			}
			for _, v := range output {
				if !inputSet[v] {
					t.Fatalf("output contains %d not in input", v)
				}
			}

			// Output length <= input length
			if len(output) > len(input) {
				t.Fatalf("output longer than input")
			}
		})
	})
}

// --- Custom generators ---

func TestQuickSort_WithCustomGenerator(t *testing.T) {
	// Generate slices with specific structure: already sorted, reverse sorted, all same
	t.Run("adversarial_inputs", func(t *testing.T) {
		rapid.Check(t, func(t *rapid.T) {
			kind := rapid.IntRange(0, 2).Draw(t, "kind")
			size := rapid.IntRange(0, 100).Draw(t, "size")

			var input []int
			switch kind {
			case 0: // already sorted
				for i := 0; i < size; i++ {
					input = append(input, i)
				}
			case 1: // reverse sorted
				for i := size; i > 0; i-- {
					input = append(input, i)
				}
			case 2: // all same value
				val := rapid.Int().Draw(t, "val")
				for i := 0; i < size; i++ {
					input = append(input, val)
				}
			}

			output := QuickSort(input)
			if !sort.IntsAreSorted(output) {
				t.Fatalf("not sorted for kind=%d: %v -> %v", kind, input, output)
			}
		})
	})
}

func countElements(arr []int) map[int]int {
	counts := make(map[int]int)
	for _, v := range arr {
		counts[v]++
	}
	return counts
}
```

**Running:**

```bash
# Run property tests (default 100 iterations per property):
go test -v -run TestQuickSort_Properties

# On failure, rapid shows the minimal shrunk input:
# --- FAIL: TestQuickSort_Properties/is_sorted (0.02s)
#     rapid: found failing test case after 47 tests
#     Shrunk input: []int{3, 1}
#     output is not sorted: [3, 1]
```

Key points:

1. **Properties over examples**: instead of `sort([3,1,2]) == [1,2,3]`, assert "output is always sorted for any input."
2. **Automatic shrinking**: when rapid finds a failure, it reduces the input to the smallest case that still fails.
3. **`rapid.SliceOf(rapid.Int())`** generates random slices of random length. Use `IntRange` to bound values.
4. **Custom generators** test adversarial inputs (pre-sorted, reversed, all-same) that hit worst-case paths.
5. **Compare against a reference** (stdlib `sort.Ints`) to catch subtle correctness bugs your properties might miss.'''),

    ("go_deep/snapshot_testing", r'''How do I implement snapshot testing in Go for complex structured output like API responses or AST transformations?''', r'''<think>
Snapshot testing (similar to golden file testing but for in-memory structures) captures
the serialized form of complex output and compares against a stored snapshot. This is
useful when:
- The output is too complex to write manual assertions for
- You want to detect any change in output (regression detection)
- Testing serialization, AST transforms, code generation, etc.
The pattern:
1. Serialize the output to a deterministic string (JSON, text, etc.)
2. Compare against a stored snapshot file
3. Auto-update snapshots with a flag
Differences from golden file testing: snapshot testing typically handles multiple
snapshots per test file (named by test case), and focuses on structured data
rather than raw text output.
I should show a generic snapshot helper that handles multiple snapshots per
test, stores them in testdata/__snapshots__/, and provides clean diffs.
Also show how to make output deterministic (sort maps, stable timestamps).
</think>

Here is a complete snapshot testing implementation:

```go
package snapshot

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"
)

var updateSnapshots = flag.Bool("update-snapshots", false, "update snapshot files")

// --- Snapshot helper ---

// Snap compares a value's JSON representation against a stored snapshot.
func Snap(t *testing.T, name string, got any) {
	t.Helper()

	// Serialize to deterministic JSON
	data, err := json.MarshalIndent(got, "", "  ")
	if err != nil {
		t.Fatalf("marshal snapshot %q: %v", name, err)
	}
	actual := string(data) + "\n"

	// Snapshot file path: testdata/__snapshots__/TestName/snapshot_name.json
	dir := filepath.Join("testdata", "__snapshots__", sanitizeName(t.Name()))
	path := filepath.Join(dir, sanitizeName(name)+".json")

	if *updateSnapshots {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatalf("create snapshot dir: %v", err)
		}
		if err := os.WriteFile(path, []byte(actual), 0o644); err != nil {
			t.Fatalf("write snapshot: %v", err)
		}
		t.Logf("updated snapshot: %s", path)
		return
	}

	expected, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read snapshot %s (run with -update-snapshots to create): %v", path, err)
	}

	if actual != string(expected) {
		t.Errorf("snapshot %q mismatch:\n%s",
			name, diffStrings(string(expected), actual))
	}
}

// SnapString compares a raw string against a stored snapshot.
func SnapString(t *testing.T, name string, got string) {
	t.Helper()

	dir := filepath.Join("testdata", "__snapshots__", sanitizeName(t.Name()))
	path := filepath.Join(dir, sanitizeName(name)+".txt")

	if *updateSnapshots {
		os.MkdirAll(dir, 0o755)
		os.WriteFile(path, []byte(got), 0o644)
		t.Logf("updated snapshot: %s", path)
		return
	}

	expected, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read snapshot %s (run with -update-snapshots): %v", path, err)
	}

	if got != string(expected) {
		t.Errorf("snapshot %q mismatch:\n%s", name, diffStrings(string(expected), got))
	}
}

func sanitizeName(name string) string {
	r := strings.NewReplacer("/", "_", " ", "_", ":", "_")
	return r.Replace(name)
}

func diffStrings(want, got string) string {
	wantLines := strings.Split(want, "\n")
	gotLines := strings.Split(got, "\n")
	var buf strings.Builder
	maxLen := len(wantLines)
	if len(gotLines) > maxLen {
		maxLen = len(gotLines)
	}
	for i := 0; i < maxLen; i++ {
		w, g := "", ""
		if i < len(wantLines) {
			w = wantLines[i]
		}
		if i < len(gotLines) {
			g = gotLines[i]
		}
		if w != g {
			fmt.Fprintf(&buf, "  line %d:\n    - %q\n    + %q\n", i+1, w, g)
		}
	}
	return buf.String()
}

// --- Example: API response transformation ---

type APIResponse struct {
	Users []User `json:"users"`
	Total int    `json:"total"`
	Page  int    `json:"page"`
}

type User struct {
	ID        int      `json:"id"`
	Name      string   `json:"name"`
	Email     string   `json:"email"`
	Roles     []string `json:"roles"`
	CreatedAt string   `json:"created_at"` // use string, not time.Time for determinism
}

func TransformResponse(raw []map[string]any) APIResponse {
	var users []User
	for _, u := range raw {
		roles, _ := u["roles"].([]string)
		sort.Strings(roles) // deterministic ordering
		users = append(users, User{
			ID:        int(u["id"].(float64)),
			Name:      u["name"].(string),
			Email:     u["email"].(string),
			Roles:     roles,
			CreatedAt: u["created_at"].(string),
		})
	}
	// Sort by ID for deterministic output
	sort.Slice(users, func(i, j int) bool {
		return users[i].ID < users[j].ID
	})
	return APIResponse{
		Users: users,
		Total: len(users),
		Page:  1,
	}
}

// MakeDeterministic replaces non-deterministic fields for snapshot stability.
func MakeDeterministic(resp *APIResponse) {
	for i := range resp.Users {
		resp.Users[i].CreatedAt = "2024-01-01T00:00:00Z" // fixed timestamp
	}
}

// --- Tests ---

func TestTransformResponse(t *testing.T) {
	raw := []map[string]any{
		{"id": float64(2), "name": "Bob", "email": "bob@example.com",
			"roles": []string{"user"}, "created_at": "2024-01-01T00:00:00Z"},
		{"id": float64(1), "name": "Alice", "email": "alice@example.com",
			"roles": []string{"admin", "user"}, "created_at": "2024-01-01T00:00:00Z"},
	}

	result := TransformResponse(raw)
	Snap(t, "full_response", result)
	Snap(t, "first_user", result.Users[0])
}

func TestEmptyResponse(t *testing.T) {
	result := TransformResponse(nil)
	Snap(t, "empty", result)
}

// --- Making output deterministic ---

type Report struct {
	GeneratedAt time.Time          `json:"generated_at"`
	Metrics     map[string]float64 `json:"metrics"`
}

// SnappableReport converts to a deterministic representation.
func (r Report) ForSnapshot() map[string]any {
	// Sort map keys by extracting to ordered structure
	type metric struct {
		Name  string  `json:"name"`
		Value float64 `json:"value"`
	}
	var metrics []metric
	for k, v := range r.Metrics {
		metrics = append(metrics, metric{k, v})
	}
	sort.Slice(metrics, func(i, j int) bool {
		return metrics[i].Name < metrics[j].Name
	})
	return map[string]any{
		"generated_at": "FIXED_TIMESTAMP",
		"metrics":      metrics,
	}
}

func TestReport(t *testing.T) {
	r := Report{
		GeneratedAt: time.Now(),
		Metrics: map[string]float64{
			"cpu":    45.2,
			"memory": 72.1,
			"disk":   33.8,
		},
	}
	Snap(t, "report", r.ForSnapshot())
}
```

**Workflow:**

```bash
# Create or update all snapshots:
go test -update-snapshots -run TestTransformResponse

# Normal test run compares against stored snapshots:
go test -v -run TestTransformResponse

# Review snapshot changes in git:
git diff testdata/__snapshots__/
```

Key points:

1. **Deterministic serialization** is critical: sort maps, fix timestamps, use stable IDs.
2. **Named snapshots** allow multiple assertions per test, each with its own file.
3. **`-update-snapshots` flag** regenerates all snapshots. Review the diff before committing.
4. **`ForSnapshot()` methods** convert non-deterministic types to stable representations.
5. **Store in `testdata/__snapshots__/`** which is included in the test binary but ignored by `go build`.'''),

    ("go_deep/cli_testing_osargs", r'''How do I test CLI applications in Go, including os.Args manipulation, stdin/stdout capture, and exit code testing?''', r'''<think>
Testing CLI apps in Go requires several techniques:
1. os.Args manipulation: save/restore os.Args around tests
2. stdout/stderr capture: redirect os.Stdout or use a bytes.Buffer
3. Exit code: os.Exit can't be caught directly; use a subprocess pattern
4. Flag parsing: flag.CommandLine needs to be reset between tests
The best approach is to structure the CLI so the core logic is testable
without os.Args/os.Exit. The main() function should be a thin wrapper
around a run() function that takes args and returns an error.
For testing exit codes, the pattern is: the test re-executes itself as
a subprocess with a special env var, checks the exit code.
I should show the testable CLI architecture pattern, flag reset,
and the subprocess pattern for exit codes.
</think>

Here is a complete CLI testing approach:

```go
// file: cmd/mytool/main.go
package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
)

func main() {
	code := run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr)
	os.Exit(code)
}

// run contains all logic. Accepts explicit args and IO for testability.
func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("mytool", flag.ContinueOnError)
	fs.SetOutput(stderr)

	upper := fs.Bool("upper", false, "convert to uppercase")
	lower := fs.Bool("lower", false, "convert to lowercase")
	repeat := fs.Int("repeat", 1, "repeat count")

	if err := fs.Parse(args); err != nil {
		return 2 // flag parsing error
	}

	if fs.NArg() == 0 {
		fmt.Fprintln(stderr, "error: no input text provided")
		fmt.Fprintln(stderr, "usage: mytool [flags] <text>")
		return 1
	}

	if *upper && *lower {
		fmt.Fprintln(stderr, "error: cannot use both -upper and -lower")
		return 1
	}

	text := strings.Join(fs.Args(), " ")

	if *upper {
		text = strings.ToUpper(text)
	}
	if *lower {
		text = strings.ToLower(text)
	}

	for i := 0; i < *repeat; i++ {
		fmt.Fprintln(stdout, text)
	}

	return 0
}
```

```go
// file: cmd/mytool/main_test.go
package main

import (
	"bytes"
	"os"
	"os/exec"
	"strings"
	"testing"
)

// --- Test the run() function directly (preferred approach) ---

func TestRun_BasicText(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run([]string{"hello", "world"}, nil, &stdout, &stderr)

	if code != 0 {
		t.Fatalf("exit code = %d, want 0; stderr: %s", code, stderr.String())
	}
	if got := strings.TrimSpace(stdout.String()); got != "hello world" {
		t.Errorf("stdout = %q, want %q", got, "hello world")
	}
}

func TestRun_Uppercase(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run([]string{"-upper", "hello"}, nil, &stdout, &stderr)

	if code != 0 {
		t.Fatalf("exit code = %d; stderr: %s", code, stderr.String())
	}
	if got := strings.TrimSpace(stdout.String()); got != "HELLO" {
		t.Errorf("stdout = %q, want HELLO", got)
	}
}

func TestRun_Repeat(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run([]string{"-repeat", "3", "hi"}, nil, &stdout, &stderr)

	if code != 0 {
		t.Fatalf("exit code = %d", code)
	}
	lines := strings.Split(strings.TrimSpace(stdout.String()), "\n")
	if len(lines) != 3 {
		t.Errorf("got %d lines, want 3", len(lines))
	}
}

func TestRun_ConflictingFlags(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run([]string{"-upper", "-lower", "text"}, nil, &stdout, &stderr)

	if code != 1 {
		t.Errorf("exit code = %d, want 1", code)
	}
	if !strings.Contains(stderr.String(), "cannot use both") {
		t.Errorf("stderr = %q, want conflict error", stderr.String())
	}
}

func TestRun_NoArgs(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run(nil, nil, &stdout, &stderr)

	if code != 1 {
		t.Errorf("exit code = %d, want 1", code)
	}
	if !strings.Contains(stderr.String(), "no input text") {
		t.Errorf("stderr = %q, want usage error", stderr.String())
	}
}

func TestRun_InvalidFlag(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run([]string{"-invalid"}, nil, &stdout, &stderr)

	if code != 2 {
		t.Errorf("exit code = %d, want 2", code)
	}
}

// --- Table-driven CLI tests ---

func TestRun_Table(t *testing.T) {
	tests := []struct {
		name       string
		args       []string
		wantCode   int
		wantStdout string
		wantStderr string
	}{
		{
			name:       "simple text",
			args:       []string{"go", "is", "great"},
			wantCode:   0,
			wantStdout: "go is great",
		},
		{
			name:       "lowercase",
			args:       []string{"-lower", "HELLO"},
			wantCode:   0,
			wantStdout: "hello",
		},
		{
			name:     "no args error",
			args:     nil,
			wantCode: 1,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var stdout, stderr bytes.Buffer
			code := run(tt.args, nil, &stdout, &stderr)
			if code != tt.wantCode {
				t.Errorf("exit code = %d, want %d", code, tt.wantCode)
			}
			if tt.wantStdout != "" {
				got := strings.TrimSpace(stdout.String())
				if got != tt.wantStdout {
					t.Errorf("stdout = %q, want %q", got, tt.wantStdout)
				}
			}
		})
	}
}

// --- Subprocess pattern for testing actual os.Exit behavior ---

func TestMainExitCode(t *testing.T) {
	if os.Getenv("TEST_SUBPROCESS") == "1" {
		// We're in the subprocess — run the actual main()
		main()
		return
	}

	tests := []struct {
		name     string
		args     []string
		wantCode int
	}{
		{"success", []string{"hello"}, 0},
		{"no args", nil, 1},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Re-run this test binary as a subprocess
			cmd := exec.Command(os.Args[0], "-test.run=TestMainExitCode")
			cmd.Env = append(os.Environ(), "TEST_SUBPROCESS=1")
			// Pass our test args as the program's args
			cmd.Args = append(cmd.Args, "--")
			cmd.Args = append(cmd.Args, tt.args...)

			err := cmd.Run()
			if tt.wantCode == 0 && err != nil {
				t.Fatalf("expected success, got: %v", err)
			}
			if tt.wantCode != 0 {
				exitErr, ok := err.(*exec.ExitError)
				if !ok {
					t.Fatalf("expected ExitError, got %T: %v", err, err)
				}
				if exitErr.ExitCode() != tt.wantCode {
					t.Errorf("exit code = %d, want %d", exitErr.ExitCode(), tt.wantCode)
				}
			}
		})
	}
}
```

Key architecture:

1. **`run(args, stdin, stdout, stderr) int`** is the core testable function. It takes explicit dependencies instead of using globals.
2. **`flag.NewFlagSet`** instead of `flag.Parse()` avoids global flag state pollution between tests.
3. **`bytes.Buffer`** captures stdout/stderr for assertion.
4. **Return `int` exit code** instead of calling `os.Exit()` directly. Only `main()` calls `os.Exit`.
5. **Subprocess pattern** for testing actual `os.Exit`: the test re-runs itself with an env var, checks the process exit code.'''),

    ("go_deep/pprof_cpu_profiling", r'''How do I use pprof for CPU profiling in Go? Show me how to profile a program, generate flame graphs, and identify hot spots.''', r'''<think>
Go has built-in profiling via runtime/pprof and net/http/pprof. For CPU profiling:
1. Programmatic: runtime/pprof.StartCPUProfile / StopCPUProfile
2. Test-based: go test -cpuprofile=cpu.prof
3. HTTP endpoint: import _ "net/http/pprof" for live profiling
The workflow: collect a profile, then analyze with go tool pprof.
pprof commands: top, list, web (generates SVG/flamegraph).
For flame graphs, use go tool pprof -http=:8080 which opens a web UI.
Key concepts:
- Sampling profiler: records stack traces at ~100Hz
- top shows cumulative time per function
- list shows line-by-line time attribution
- flat vs cum: flat = time in the function itself, cum = time including callees
I should show a realistic CPU-bound program, how to profile it three ways,
and how to interpret the output. Also show how to profile benchmarks
and how to read flame graphs.
</think>

Here is a complete CPU profiling workflow:

```go
// file: hotspot/hotspot.go
package hotspot

import (
	"crypto/sha256"
	"encoding/hex"
	"math"
	"strings"
)

// ProcessData simulates a CPU-intensive pipeline.
func ProcessData(items []string) []Result {
	results := make([]Result, 0, len(items))
	for _, item := range items {
		r := Result{
			Original:  item,
			Hash:      hashString(item),
			Score:     computeScore(item),
			Processed: normalize(item),
		}
		results = append(results, r)
	}
	return results
}

type Result struct {
	Original  string
	Hash      string
	Score     float64
	Processed string
}

// hashString — intentionally inefficient: hashes multiple times.
func hashString(s string) string {
	data := []byte(s)
	for i := 0; i < 100; i++ { // HOT SPOT: unnecessary iterations
		h := sha256.Sum256(data)
		data = []byte(hex.EncodeToString(h[:]))
	}
	return string(data[:16])
}

// computeScore — heavy math operations.
func computeScore(s string) float64 {
	score := 0.0
	for i, c := range s {
		score += math.Sin(float64(c)) * math.Cos(float64(i))
		score += math.Sqrt(math.Abs(score) + 1)
	}
	return score
}

// normalize — string manipulation.
func normalize(s string) string {
	s = strings.ToLower(s)
	s = strings.TrimSpace(s)
	// Inefficient: builds new string each iteration
	result := ""
	for _, c := range s {
		if c >= 'a' && c <= 'z' || c >= '0' && c <= '9' || c == ' ' {
			result += string(c) // HOT SPOT: string concatenation in loop
		}
	}
	return result
}
```

```go
// file: hotspot/hotspot_test.go
package hotspot

import (
	"fmt"
	"testing"
)

func generateItems(n int) []string {
	items := make([]string, n)
	for i := range items {
		items[i] = fmt.Sprintf("Item %d with some extra text for processing", i)
	}
	return items
}

// Benchmark for profiling.
func BenchmarkProcessData(b *testing.B) {
	items := generateItems(100)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		ProcessData(items)
	}
}
```

```go
// file: cmd/profile/main.go
package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"runtime/pprof"
	"time"

	_ "net/http/pprof" // registers /debug/pprof/ handlers
	"myproject/hotspot"
)

func main() {
	mode := "programmatic"
	if len(os.Args) > 1 {
		mode = os.Args[1]
	}

	switch mode {
	case "programmatic":
		profileProgrammatic()
	case "http":
		profileHTTP()
	}
}

func profileProgrammatic() {
	// Method 1: Write CPU profile to file
	f, err := os.Create("cpu.prof")
	if err != nil {
		log.Fatal(err)
	}
	defer f.Close()

	if err := pprof.StartCPUProfile(f); err != nil {
		log.Fatal(err)
	}
	defer pprof.StopCPUProfile()

	// Run the workload
	items := make([]string, 1000)
	for i := range items {
		items[i] = fmt.Sprintf("Data item number %d with content", i)
	}

	start := time.Now()
	results := hotspot.ProcessData(items)
	fmt.Printf("Processed %d items in %v\n", len(results), time.Since(start))
	// Profile is written when StopCPUProfile runs (via defer)
}

func profileHTTP() {
	// Method 2: HTTP endpoint for live profiling
	go func() {
		// Process data continuously
		items := make([]string, 100)
		for i := range items {
			items[i] = fmt.Sprintf("Item %d", i)
		}
		for {
			hotspot.ProcessData(items)
		}
	}()

	fmt.Println("Profiling server at http://localhost:6060/debug/pprof/")
	fmt.Println("Capture 30s profile: go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30")
	log.Fatal(http.ListenAndServe(":6060", nil))
}
```

**Profiling workflow:**

```bash
# === Method 1: Profile a benchmark ===
go test -bench=BenchmarkProcessData -cpuprofile=cpu.prof -benchtime=5s ./hotspot/

# Analyze interactively:
go tool pprof cpu.prof
# (pprof) top 10
# Showing top 10 nodes out of 45
#       flat  flat%   cum%       cum  cum%
#     2.10s 35.00%  35.00%     2.10s 35.00%  crypto/sha256.block
#     1.20s 20.00%  55.00%     3.30s 55.00%  hotspot.hashString
#     0.80s 13.33%  68.33%     0.80s 13.33%  math.Sin
#     0.60s 10.00%  78.33%     1.40s 23.33%  hotspot.computeScore
#     0.40s  6.67%  85.00%     0.40s  6.67%  runtime.mallocgc
#     0.30s  5.00%  90.00%     0.70s 11.67%  hotspot.normalize

# Show line-level detail:
# (pprof) list hashString
# Shows time spent on each line of the function

# (pprof) web
# Opens SVG call graph in browser

# === Method 2: Web-based flame graph ===
go tool pprof -http=:8080 cpu.prof
# Opens browser with:
# - Flame graph (most useful)
# - Top functions
# - Call graph
# - Source view

# === Method 3: Profile a running service ===
go run cmd/profile/main.go http &
go tool pprof -http=:8080 http://localhost:6060/debug/pprof/profile?seconds=30

# === Comparing before/after optimization ===
# Before:
go test -bench=. -cpuprofile=before.prof ./hotspot/
# After fixing hotspots:
go test -bench=. -cpuprofile=after.prof ./hotspot/
# Compare:
go tool pprof -diff_base=before.prof after.prof
```

**Reading flame graphs:**

```
Width = time spent (wider = more CPU time)
Top-down: caller → callee
Bottom = main/goroutine root
Look for: wide bars (hot functions), deep stacks (unnecessary call depth)

In this example:
- hashString is the widest bar (35% of CPU) due to 100 SHA256 iterations
- normalize has unexpected malloc (string concatenation)
- Fix: reduce hash iterations, use strings.Builder in normalize
```

Key points:

1. **`go test -cpuprofile`** is the simplest way to profile benchmarks.
2. **`go tool pprof -http=:8080`** gives an interactive web UI with flame graphs.
3. **`flat` vs `cum`**: flat = time in the function body; cum = including everything it calls.
4. **`list functionName`** in pprof shows line-by-line CPU attribution.
5. **Profile for at least 5-30 seconds** to get statistically meaningful samples.
6. **`net/http/pprof`** gives live profiling of running services without restart.'''),

    ("go_deep/memory_profiling_fixing_allocs", r'''How do I profile memory allocations in Go, find allocation hot spots, and fix them? Show me the full workflow from profiling to optimization.''', r'''<think>
Memory profiling in Go uses runtime/pprof or go test -memprofile. The profiler
tracks allocation sites (where allocations happen) not live memory.
Two profiles matter:
- alloc_objects: number of allocations (hot allocation sites)
- alloc_space: bytes allocated (memory pressure)
- inuse_objects/inuse_space: current live objects (for leak detection)
Workflow: profile -> identify hot allocation sites -> optimize.
Common fixes:
- Pre-allocate slices with known capacity
- Use sync.Pool for frequently allocated/freed objects
- Use strings.Builder instead of concatenation
- Avoid interface boxing of small values
- Return values instead of pointers to avoid heap escape
- Use fixed-size arrays instead of slices for small known sizes
I should show a realistic example with allocation problems,
the profiling commands, and the fixed version with benchmarks
showing the improvement.
</think>

Here is a complete memory profiling and optimization workflow:

```go
// file: alloc/alloc.go
package alloc

import (
	"fmt"
	"strings"
	"sync"
)

// === BEFORE OPTIMIZATION ===

type Record struct {
	ID     int
	Name   string
	Tags   []string
	Score  float64
}

// ProcessRecords_Slow has multiple allocation problems.
func ProcessRecords_Slow(names []string) []*Record {
	var results []*Record // Problem 1: no capacity hint

	for i, name := range names {
		r := &Record{} // Problem 2: unnecessary pointer allocation
		r.ID = i
		r.Name = fmt.Sprintf("record_%s", name) // Problem 3: fmt.Sprintf allocates
		r.Tags = strings.Split(name, "")         // Problem 4: split every char allocates
		r.Score = float64(len(name)) / 100.0
		results = append(results, r) // Problem 5: slice grows, copies
	}

	return results
}

// FormatRecords_Slow builds a string by concatenation.
func FormatRecords_Slow(records []*Record) string {
	result := ""
	for _, r := range records {
		// Problem: string concatenation creates a new string each iteration
		result += fmt.Sprintf("ID=%d Name=%s Score=%.2f\n", r.ID, r.Name, r.Score)
	}
	return result
}

// === AFTER OPTIMIZATION ===

// ProcessRecords_Fast fixes all allocation hot spots.
func ProcessRecords_Fast(names []string) []Record {
	results := make([]Record, len(names)) // Fix 1: pre-allocate exact size, value type

	for i, name := range names {
		results[i] = Record{
			ID:    i,
			Name:  "record_" + name,               // Fix 2: simple concat, no fmt.Sprintf
			Tags:  splitChars(name),                // Fix 3: custom split, pre-allocated
			Score: float64(len(name)) / 100.0,
		}
	}

	return results
}

// splitChars avoids strings.Split's overhead for single-char splitting.
func splitChars(s string) []string {
	chars := make([]string, 0, len(s))
	for _, c := range s {
		chars = append(chars, string(c))
	}
	return chars
}

// FormatRecords_Fast uses strings.Builder.
func FormatRecords_Fast(records []Record) string {
	var b strings.Builder
	b.Grow(len(records) * 40) // estimate: ~40 bytes per record line

	for _, r := range records {
		fmt.Fprintf(&b, "ID=%d Name=%s Score=%.2f\n", r.ID, r.Name, r.Score)
	}
	return b.String()
}

// === sync.Pool for frequent alloc/free cycles ===

var bufferPool = sync.Pool{
	New: func() any {
		b := make([]byte, 0, 1024)
		return &b
	},
}

func ProcessWithPool(data string) string {
	bufPtr := bufferPool.Get().(*[]byte)
	buf := (*bufPtr)[:0] // reset length, keep capacity

	// Use the buffer
	buf = append(buf, "processed: "...)
	buf = append(buf, strings.ToUpper(data)...)

	result := string(buf)

	// Return buffer to pool
	*bufPtr = buf
	bufferPool.Put(bufPtr)

	return result
}
```

```go
// file: alloc/alloc_test.go
package alloc

import (
	"fmt"
	"testing"
)

func generateNames(n int) []string {
	names := make([]string, n)
	for i := range names {
		names[i] = fmt.Sprintf("user_%d_name", i)
	}
	return names
}

// --- Benchmarks to compare allocations ---

func BenchmarkProcessRecords_Slow(b *testing.B) {
	names := generateNames(1000)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		ProcessRecords_Slow(names)
	}
}

func BenchmarkProcessRecords_Fast(b *testing.B) {
	names := generateNames(1000)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		ProcessRecords_Fast(names)
	}
}

func BenchmarkFormatRecords_Slow(b *testing.B) {
	names := generateNames(100)
	records := ProcessRecords_Slow(names)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		FormatRecords_Slow(records)
	}
}

func BenchmarkFormatRecords_Fast(b *testing.B) {
	names := generateNames(100)
	records := ProcessRecords_Fast(names)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		FormatRecords_Fast(records)
	}
}

func BenchmarkPool(b *testing.B) {
	b.ReportAllocs()
	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			_ = ProcessWithPool("hello world")
		}
	})
}
```

**Profiling commands:**

```bash
# 1. Benchmark with memory profile:
go test -bench=BenchmarkProcessRecords -memprofile=mem.prof -benchmem ./alloc/

# Expected output:
# BenchmarkProcessRecords_Slow-8   1000   1543210 ns/op   892416 B/op   12034 allocs/op
# BenchmarkProcessRecords_Fast-8   3000    487234 ns/op   334120 B/op    4012 allocs/op

# 2. Analyze memory profile:
go tool pprof -alloc_space mem.prof
# (pprof) top
# Shows which functions allocated the most bytes

# (pprof) list ProcessRecords_Slow
# Shows line-by-line allocation attribution

# 3. Web UI with allocation flame graph:
go tool pprof -http=:8080 -alloc_objects mem.prof
# -alloc_objects: where allocations happen most frequently
# -alloc_space: where the most bytes are allocated
# -inuse_space: currently live memory (leak detection)

# 4. Compare before/after:
go test -bench=. -benchmem -count=5 > before.txt
# ... apply fixes ...
go test -bench=. -benchmem -count=5 > after.txt
benchstat before.txt after.txt
# Shows percentage improvement with confidence intervals
```

**Common optimizations summary:**

| Problem | Fix | Impact |
|---------|-----|--------|
| `append` without capacity | `make([]T, 0, n)` | Eliminates grow copies |
| `fmt.Sprintf` for simple concat | `"prefix_" + s` | Avoids reflect, allocations |
| String concatenation in loop | `strings.Builder` | O(1) amortized vs O(n) |
| `*Record` (pointer) | `Record` (value) | Avoids heap allocation |
| Frequent alloc/free | `sync.Pool` | Reuses memory |
| `strings.Split` | Custom split with capacity | Pre-sized slice |

Key points:

1. **`-alloc_objects`** finds hot allocation sites (where `mallocgc` is called most).
2. **`-alloc_space`** finds where the most bytes are allocated (large objects).
3. **`-inuse_space`** shows currently live memory (useful for leak detection).
4. **Pre-allocate slices** when you know the size; this is the single biggest win.
5. **`sync.Pool`** excels when objects are allocated and freed rapidly (e.g., per-request buffers).
6. **`benchstat`** gives statistically meaningful comparisons between optimization attempts.'''),

    ("go_deep/escape_analysis_stack_heap", r'''How does Go's escape analysis work? How do I determine whether a variable is allocated on the stack or heap, and why does it matter?''', r'''<think>
Escape analysis is the compiler's decision of whether to allocate a variable on
the stack (cheap, automatic cleanup) or heap (requires GC). A variable "escapes"
to the heap when the compiler can't prove it won't be referenced after the
function returns.
Key rules:
- If a pointer is returned or stored in a longer-lived location, it escapes
- If the compiler can't determine the size at compile time, it may escape
- Interface values often cause escape (the compiler doesn't know the concrete type's lifetime)
- Closures that capture variables may cause escape
- Slices that grow beyond their capacity escape to heap
How to check: go build -gcflags='-m' shows escape decisions
How to check more detail: -gcflags='-m -m' for verbose reasoning
Stack allocation is faster (just a pointer bump) and doesn't pressure the GC.
Heap allocation requires malloc and eventual garbage collection.
I should show concrete examples of what escapes and what doesn't, how to
read the compiler output, and patterns to keep allocations on the stack.
</think>

Here is a comprehensive guide to escape analysis:

```go
// file: escape/escape.go
package escape

import (
	"fmt"
	"io"
)

// === STACK ALLOCATED (does not escape) ===

// add: both arguments and return value stay on stack.
func add(a, b int) int {
	result := a + b // stack: local variable, not referenced after return
	return result   // value copy, not a pointer
}

// sumSlice: the slice stays on stack if capacity is known at compile time.
func sumSlice() int {
	nums := [5]int{1, 2, 3, 4, 5} // stack: fixed-size array
	sum := 0
	for _, n := range nums {
		sum += n
	}
	return sum
}

// processLocal: struct stays on stack when not returned as pointer.
type Point struct {
	X, Y float64
}

func processLocal() float64 {
	p := Point{X: 3.0, Y: 4.0} // stack: not referenced after return
	return p.X + p.Y
}

// === HEAP ALLOCATED (escapes) ===

// newPoint: returned pointer forces heap allocation.
func newPoint(x, y float64) *Point {
	p := Point{X: x, Y: y} // ESCAPES: returned as pointer
	return &p
}

// storeInInterface: interface boxing often causes escape.
func storeInInterface(x int) any {
	return x // ESCAPES: stored in interface value
}

// capturedByClosure: variable outlives the function scope.
func capturedByClosure() func() int {
	count := 0           // ESCAPES: captured by returned closure
	return func() int {
		count++
		return count
	}
}

// appendGrows: slice that grows beyond initial capacity may escape.
func appendGrows() []int {
	s := make([]int, 0) // ESCAPES: grows unpredictably, returned
	for i := 0; i < 100; i++ {
		s = append(s, i)
	}
	return s
}

// fmtSprintf: fmt functions use interface{} parameters, causing escape.
func fmtSprintf(name string) string {
	return fmt.Sprintf("hello %s", name) // name ESCAPES into interface{}
}

// === OPTIMIZED PATTERNS ===

// returnValue: return by value instead of pointer (stays on stack at call site).
func makePoint(x, y float64) Point {
	return Point{X: x, Y: y} // stack: returned by value
}

// acceptWriter: pass io.Writer instead of returning buffer.
// The caller controls the allocation.
func writeData(w io.Writer, data string) {
	fmt.Fprintf(w, "data: %s\n", data)
}

// knownCapacity: pre-sized slice with known bounds can stay on stack.
func smallSlice() [4]int {
	return [4]int{1, 2, 3, 4} // stack: fixed-size array
}

// avoidInterface: use concrete type instead of interface when possible.
func sumDirect(nums []int) int {
	total := 0
	for _, n := range nums {
		total += n
	}
	return total // no interface boxing, stays on stack
}

// pooledBuffer: reuse allocations instead of creating new ones.
// (See sync.Pool example in memory profiling)
```

```go
// file: escape/escape_test.go
package escape

import "testing"

// Benchmark to measure the impact of stack vs heap allocation.

var sinkPoint Point
var sinkPtr *Point

func BenchmarkReturnValue(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		sinkPoint = makePoint(3.0, 4.0) // 0 allocs/op (stack)
	}
}

func BenchmarkReturnPointer(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		sinkPtr = newPoint(3.0, 4.0) // 1 alloc/op (heap)
	}
}

var sinkInt int

func BenchmarkDirectCall(b *testing.B) {
	nums := []int{1, 2, 3, 4, 5}
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		sinkInt = sumDirect(nums) // 0 allocs
	}
}

func BenchmarkInterfaceBoxing(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = storeInInterface(42) // 1 alloc (interface boxing)
	}
}
```

**Analyzing escape decisions:**

```bash
# Basic escape analysis output:
go build -gcflags='-m' ./escape/
# escape/escape.go:30:2: moved to heap: p          <- newPoint
# escape/escape.go:35:9: x escapes to heap          <- storeInInterface
# escape/escape.go:40:2: moved to heap: count       <- capturedByClosure
# escape/escape.go:12:2: result does not escape      <- add (stays on stack)

# Verbose output (shows reasoning):
go build -gcflags='-m -m' ./escape/
# escape/escape.go:30:2: p escapes to heap:
#   flow: ~r0 = &p:
#     from &p (address-of) at escape/escape.go:31:9
#     from return &p (return) at escape/escape.go:31:2

# Check a specific function:
go build -gcflags='-m' ./escape/ 2>&1 | grep 'escapes\|does not escape'

# Combine with benchmarks to measure impact:
go test -bench=. -benchmem ./escape/
# BenchmarkReturnValue-8    1000000000   0.26 ns/op   0 B/op   0 allocs/op
# BenchmarkReturnPointer-8   258513882   4.63 ns/op   16 B/op  1 allocs/op
```

**Rules of thumb to minimize heap allocations:**

| Pattern | Stack | Heap |
|---------|-------|------|
| Return value | `return Point{1,2}` | `return &Point{1,2}` |
| Fixed array | `[10]int{}` | `make([]int, 10)` (sometimes) |
| Known slice cap | `make([]int, 0, 10)` with small n | `append` without cap |
| Concrete type | `func(x int)` | `func(x any)` |
| Local-only pointer | `p := &Point{}; use(p.X)` | `p := &Point{}; return p` |

Key points:

1. **`go build -gcflags='-m'`** shows what escapes and why.
2. **Return by value** when the struct is small (up to ~128 bytes is fine).
3. **Interface boxing** (`any`, `error`, `fmt.Stringer`) forces heap allocation of the underlying value.
4. **Stack allocation is ~20x faster** than heap: no malloc, no GC pressure, better cache locality.
5. **Don't over-optimize**: only fix escape issues that show up in profiles. Readability > micro-optimization.'''),

    ("go_deep/build_tags_platform_specific", r'''How do I use build tags for platform-specific code in Go? I need different implementations for Linux, macOS, and Windows.''', r'''<think>
Go supports platform-specific code through:
1. File name conventions: _linux.go, _darwin.go, _windows.go
2. Build tags: //go:build linux, //go:build darwin, etc.
3. Combinations: //go:build linux && amd64
File naming is simpler and preferred for GOOS/GOARCH selection.
Build tags are more flexible (custom tags, boolean logic).
Key rules:
- File naming: *_GOOS.go, *_GOARCH.go, *_GOOS_GOARCH.go
- Only one file per platform is compiled
- A common interface file defines the API
- Platform files implement it
- _test.go files also respect platform constraints
I should show a realistic example: a system info package that uses
different syscalls on each platform. Show both file naming and
build tag approaches, and how to test platform-specific code.
</think>

Here is a complete platform-specific code setup:

```go
// file: sysinfo/sysinfo.go
// Common interface — compiled on all platforms.
package sysinfo

// SystemInfo contains platform-specific system information.
type SystemInfo struct {
	Hostname    string
	OS          string
	Arch        string
	CPUCount    int
	MemoryBytes uint64
	TempDir     string
}

// GetInfo returns system information for the current platform.
// Implemented separately in _linux.go, _darwin.go, _windows.go.
// func GetInfo() (*SystemInfo, error)

// GetConfigDir returns the platform-appropriate config directory.
// func GetConfigDir() string

// SetFilePermissions sets platform-appropriate file permissions.
// func SetFilePermissions(path string, readonly bool) error
```

```go
// file: sysinfo/sysinfo_linux.go
// Automatically compiled only on Linux (no build tag needed — file name is enough).
package sysinfo

import (
	"os"
	"path/filepath"
	"runtime"
	"syscall"
)

func GetInfo() (*SystemInfo, error) {
	hostname, err := os.Hostname()
	if err != nil {
		return nil, err
	}

	var sysinfo syscall.Sysinfo_t
	if err := syscall.Sysinfo(&sysinfo); err != nil {
		return nil, err
	}

	return &SystemInfo{
		Hostname:    hostname,
		OS:          "linux",
		Arch:        runtime.GOARCH,
		CPUCount:    runtime.NumCPU(),
		MemoryBytes: sysinfo.Totalram,
		TempDir:     os.TempDir(),
	}, nil
}

func GetConfigDir() string {
	if xdg := os.Getenv("XDG_CONFIG_HOME"); xdg != "" {
		return xdg
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".config")
}

func SetFilePermissions(path string, readonly bool) error {
	if readonly {
		return os.Chmod(path, 0o444)
	}
	return os.Chmod(path, 0o644)
}
```

```go
// file: sysinfo/sysinfo_darwin.go
package sysinfo

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
)

func GetInfo() (*SystemInfo, error) {
	hostname, err := os.Hostname()
	if err != nil {
		return nil, err
	}

	// macOS: use sysctl for memory info
	memBytes := uint64(0)
	out, err := exec.Command("sysctl", "-n", "hw.memsize").Output()
	if err == nil {
		memBytes, _ = strconv.ParseUint(strings.TrimSpace(string(out)), 10, 64)
	}

	return &SystemInfo{
		Hostname:    hostname,
		OS:          "darwin",
		Arch:        runtime.GOARCH,
		CPUCount:    runtime.NumCPU(),
		MemoryBytes: memBytes,
		TempDir:     os.TempDir(),
	}, nil
}

func GetConfigDir() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, "Library", "Application Support")
}

func SetFilePermissions(path string, readonly bool) error {
	if readonly {
		return os.Chmod(path, 0o444)
	}
	return os.Chmod(path, 0o644)
}
```

```go
// file: sysinfo/sysinfo_windows.go
package sysinfo

import (
	"os"
	"path/filepath"
	"runtime"
	"unsafe"

	"golang.org/x/sys/windows"
)

func GetInfo() (*SystemInfo, error) {
	hostname, err := os.Hostname()
	if err != nil {
		return nil, err
	}

	// Windows: use GlobalMemoryStatusEx
	var memStatus windows.MEMORYSTATUSEX
	memStatus.Length = uint32(unsafe.Sizeof(memStatus))
	windows.GlobalMemoryStatusEx(&memStatus)

	return &SystemInfo{
		Hostname:    hostname,
		OS:          "windows",
		Arch:        runtime.GOARCH,
		CPUCount:    runtime.NumCPU(),
		MemoryBytes: memStatus.TotalPhys,
		TempDir:     os.TempDir(),
	}, nil
}

func GetConfigDir() string {
	if appData := os.Getenv("APPDATA"); appData != "" {
		return appData
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, "AppData", "Roaming")
}

func SetFilePermissions(path string, readonly bool) error {
	if readonly {
		return os.Chmod(path, 0o444)
	}
	return os.Chmod(path, 0o666) // Windows doesn't have Unix permissions
}
```

```go
// file: sysinfo/notify_linux.go
//go:build linux && !android

// Build tags for more complex constraints.
// This file compiles on Linux but NOT on Android.
package sysinfo

import "fmt"

func SendDesktopNotification(title, message string) error {
	// Uses D-Bus / notify-send on desktop Linux
	fmt.Printf("NOTIFY [%s]: %s\n", title, message)
	return nil
}
```

```go
// file: sysinfo/notify_other.go
//go:build !linux || android

// Fallback for all non-desktop-Linux platforms.
package sysinfo

import "fmt"

func SendDesktopNotification(title, message string) error {
	fmt.Printf("LOG [%s]: %s\n", title, message)
	return nil
}
```

```go
// file: sysinfo/sysinfo_test.go
// Tests that run on all platforms.
package sysinfo

import (
	"runtime"
	"testing"
)

func TestGetInfo(t *testing.T) {
	info, err := GetInfo()
	if err != nil {
		t.Fatalf("GetInfo: %v", err)
	}
	if info.OS != runtime.GOOS {
		t.Errorf("OS = %q, want %q", info.OS, runtime.GOOS)
	}
	if info.CPUCount < 1 {
		t.Errorf("CPUCount = %d, want >= 1", info.CPUCount)
	}
	if info.Hostname == "" {
		t.Error("Hostname is empty")
	}
}

func TestGetConfigDir(t *testing.T) {
	dir := GetConfigDir()
	if dir == "" {
		t.Error("GetConfigDir returned empty string")
	}
	t.Logf("Config dir: %s", dir)
}
```

```go
// file: sysinfo/sysinfo_linux_test.go
// Linux-specific tests.
package sysinfo

import "testing"

func TestLinuxMemory(t *testing.T) {
	info, err := GetInfo()
	if err != nil {
		t.Fatal(err)
	}
	if info.MemoryBytes == 0 {
		t.Error("MemoryBytes should be non-zero on Linux")
	}
}
```

**Build commands:**

```bash
# Build for current platform:
go build ./sysinfo/

# Cross-compile:
GOOS=linux GOARCH=amd64 go build ./sysinfo/
GOOS=darwin GOARCH=arm64 go build ./sysinfo/
GOOS=windows GOARCH=amd64 go build ./sysinfo/

# List files that would be compiled for a target:
go list -f '{{.GoFiles}}' ./sysinfo/
# On Linux: [sysinfo.go sysinfo_linux.go notify_linux.go]
# On macOS: [sysinfo.go sysinfo_darwin.go notify_other.go]
```

**Build tag reference:**

```go
//go:build linux                         // Linux only
//go:build darwin || linux               // macOS or Linux
//go:build linux && amd64                // Linux on x86-64 only
//go:build !windows                      // everything except Windows
//go:build (linux && amd64) || (darwin && arm64)  // specific combos
//go:build ignore                        // never compiled (documentation file)
```

Key points:

1. **File naming** (`_linux.go`) is preferred for simple GOOS/GOARCH selection. No build tag needed.
2. **Build tags** (`//go:build`) are for complex boolean logic or custom tags.
3. **One implementation per platform** — the compiler selects exactly one matching file.
4. **Cross-platform tests** go in `_test.go`; platform-specific tests go in `_linux_test.go`, etc.
5. **Always provide a fallback** (e.g., `_other.go` with `//go:build !linux`) so the package compiles everywhere.'''),

    ("go_deep/go_generate_code_generation", r'''How do I use go generate for code generation in Go? Show me practical patterns like generating string methods for enums and type-safe code.''', r'''<think>
go generate runs commands embedded in Go source files as //go:generate directives.
It's a build-time code generation tool, not run automatically by go build.
Common uses:
- stringer: generate String() methods for const enums
- mockgen: generate mock implementations
- Custom generators: generate boilerplate from templates
- protobuf/gRPC code generation
- Embedding assets
The directive format: //go:generate command args...
Must run `go generate ./...` explicitly. Generated files are committed to git.
Convention: generated files have a header comment "Code generated ... DO NOT EDIT."
I should show multiple practical examples: stringer for enums, a custom
generator using go/ast or text/template, and the workflow.
</think>

Here is a complete guide to `go generate` with practical patterns:

```go
// file: status/status.go
package status

//go:generate stringer -type=Status -trimprefix=Status
//go:generate go run gen_validator.go -type=Status

// Status represents the state of an order.
type Status int

const (
	StatusPending    Status = iota
	StatusProcessing
	StatusShipped
	StatusDelivered
	StatusCancelled
	StatusRefunded
)
```

After running `go generate`, the `stringer` tool creates:

```go
// file: status/status_string.go (auto-generated by stringer)
// Code generated by "stringer -type=Status -trimprefix=Status"; DO NOT EDIT.

package status

import "strconv"

func _() {
	// An "invalid array index" compiler error signifies that the constant values have changed.
	var x [1]struct{}
	_ = x[StatusPending-0]
	_ = x[StatusProcessing-1]
	_ = x[StatusShipped-2]
	_ = x[StatusDelivered-3]
	_ = x[StatusCancelled-4]
	_ = x[StatusRefunded-5]
}

const _Status_name = "PendingProcessingShippedDeliveredCancelledRefunded"

var _Status_index = [...]uint8{0, 7, 17, 24, 33, 42, 50}

func (i Status) String() string {
	if i < 0 || i >= Status(len(_Status_index)-1) {
		return "Status(" + strconv.FormatInt(int64(i), 10) + ")"
	}
	return _Status_name[_Status_index[i]:_Status_index[i+1]]
}
```

**Custom code generator using text/template:**

```go
// file: status/gen_validator.go
//go:build ignore

// This file is a generator — the "ignore" build tag prevents it from being
// compiled as part of the package. It's only run via go generate.
package main

import (
	"flag"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"strings"
	"text/template"
)

var typeName = flag.String("type", "", "type name to generate validator for")

const tmpl = `// Code generated by gen_validator.go; DO NOT EDIT.

package status

import "fmt"

// Valid{{.TypeName}}s returns all valid {{.TypeName}} values.
func Valid{{.TypeName}}s() []{{.TypeName}} {
	return []{{.TypeName}}{
		{{- range .Values}}
		{{.}},
		{{- end}}
	}
}

// IsValid returns true if the {{.TypeName}} is a known value.
func (s {{.TypeName}}) IsValid() bool {
	switch s {
	case {{range $i, $v := .Values}}{{if $i}}, {{end}}{{$v}}{{end}}:
		return true
	default:
		return false
	}
}

// Parse{{.TypeName}} converts a string to a {{.TypeName}}.
func Parse{{.TypeName}}(s string) ({{.TypeName}}, error) {
	{{- range .Values}}
	if s == {{.}}.String() {
		return {{.}}, nil
	}
	{{- end}}
	return 0, fmt.Errorf("invalid {{.TypeName}}: %q", s)
}
`

type templateData struct {
	TypeName string
	Values   []string
}

func main() {
	flag.Parse()
	if *typeName == "" {
		fmt.Fprintln(os.Stderr, "missing -type flag")
		os.Exit(1)
	}

	// Parse the Go source file to find const values
	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, "status.go", nil, parser.ParseComments)
	if err != nil {
		fmt.Fprintf(os.Stderr, "parse: %v\n", err)
		os.Exit(1)
	}

	var values []string
	for _, decl := range f.Decls {
		genDecl, ok := decl.(*ast.GenDecl)
		if !ok || genDecl.Tok != token.CONST {
			continue
		}
		for _, spec := range genDecl.Specs {
			vspec := spec.(*ast.ValueSpec)
			name := vspec.Names[0].Name
			if strings.HasPrefix(name, *typeName) {
				values = append(values, name)
			}
		}
	}

	// Generate the output file
	outFile, err := os.Create(strings.ToLower(*typeName) + "_validator.go")
	if err != nil {
		fmt.Fprintf(os.Stderr, "create: %v\n", err)
		os.Exit(1)
	}
	defer outFile.Close()

	t := template.Must(template.New("validator").Parse(tmpl))
	if err := t.Execute(outFile, templateData{
		TypeName: *typeName,
		Values:   values,
	}); err != nil {
		fmt.Fprintf(os.Stderr, "execute: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("generated %s_validator.go with %d values\n",
		strings.ToLower(*typeName), len(values))
}
```

Generated output:

```go
// file: status/status_validator.go (auto-generated)
// Code generated by gen_validator.go; DO NOT EDIT.

package status

import "fmt"

func ValidStatuss() []Status {
	return []Status{
		StatusPending,
		StatusProcessing,
		StatusShipped,
		StatusDelivered,
		StatusCancelled,
		StatusRefunded,
	}
}

func (s Status) IsValid() bool {
	switch s {
	case StatusPending, StatusProcessing, StatusShipped, StatusDelivered, StatusCancelled, StatusRefunded:
		return true
	default:
		return false
	}
}

func ParseStatus(s string) (Status, error) {
	for _, v := range ValidStatuss() {
		if s == v.String() {
			return v, nil
		}
	}
	return 0, fmt.Errorf("invalid Status: %q", s)
}
```

```go
// file: status/status_test.go
package status

import "testing"

func TestStatusString(t *testing.T) {
	tests := []struct {
		s    Status
		want string
	}{
		{StatusPending, "Pending"},
		{StatusShipped, "Shipped"},
		{Status(99), "Status(99)"},
	}
	for _, tt := range tests {
		if got := tt.s.String(); got != tt.want {
			t.Errorf("%d.String() = %q, want %q", tt.s, got, tt.want)
		}
	}
}

func TestStatusIsValid(t *testing.T) {
	if !StatusPending.IsValid() {
		t.Error("Pending should be valid")
	}
	if Status(99).IsValid() {
		t.Error("Status(99) should be invalid")
	}
}

func TestParseStatus(t *testing.T) {
	s, err := ParseStatus("Shipped")
	if err != nil || s != StatusShipped {
		t.Errorf("ParseStatus(Shipped) = %v, %v", s, err)
	}
	_, err = ParseStatus("bogus")
	if err == nil {
		t.Error("expected error for bogus status")
	}
}
```

**Workflow:**

```bash
# Install stringer:
go install golang.org/x/tools/cmd/stringer@latest

# Run all generators:
go generate ./...

# Run for specific package:
go generate ./status/

# Verify generated files are up to date in CI:
go generate ./...
git diff --exit-code
# Fails if generated files are stale
```

Key points:

1. **`//go:generate`** directives are comments — they don't affect compilation. Run explicitly with `go generate`.
2. **Generator files** use `//go:build ignore` so they're not compiled as part of the package.
3. **Generated files** should start with `// Code generated ... DO NOT EDIT.` (detected by `go vet` and editors).
4. **Commit generated files** to git so consumers don't need the generator tools.
5. **CI check**: run `go generate ./...` then `git diff --exit-code` to catch stale generated code.'''),

    ("go_deep/custom_linter_go_analysis", r'''How do I write a custom linter in Go using the go/analysis framework? I want to detect a specific anti-pattern in our codebase.''', r'''<think>
The go/analysis framework (golang.org/x/tools/go/analysis) is the standard way to
write custom linters/analyzers. It provides:
- AST inspection
- Type information
- Cross-package analysis
- Integration with `go vet` and golangci-lint
An analyzer is a struct with a Run function that inspects packages.
The pattern: define an Analyzer, implement Run using inspect.Analyzer
to walk the AST, report diagnostics for anti-patterns.
I should show a realistic custom linter that detects a common anti-pattern.
Good example: detecting context.Background() or context.TODO() used inside
HTTP handlers (they should use r.Context() instead). Or detecting
fmt.Errorf without %w for error wrapping.
I'll show: the analyzer definition, AST walking, type-checking,
testing with analysistest, and how to run it.
</think>

Here is a complete custom linter using the `go/analysis` framework:

```go
// file: linters/ctxcheck/ctxcheck.go
// Package ctxcheck detects context.Background() and context.TODO() calls
// inside HTTP handler functions, where r.Context() should be used instead.
package ctxcheck

import (
	"go/ast"
	"go/types"

	"golang.org/x/tools/go/analysis"
	"golang.org/x/tools/go/analysis/passes/inspect"
	"golang.org/x/tools/go/ast/inspector"
)

var Analyzer = &analysis.Analyzer{
	Name:     "ctxcheck",
	Doc:      "checks for context.Background()/TODO() inside HTTP handlers",
	Requires: []*analysis.Analyzer{inspect.Analyzer},
	Run:      run,
}

func run(pass *analysis.Pass) (interface{}, error) {
	inspct := pass.ResultOf[inspect.Analyzer].(*inspector.Inspector)

	// Find all function declarations and function literals
	nodeFilter := []ast.Node{
		(*ast.FuncDecl)(nil),
		(*ast.FuncLit)(nil),
	}

	inspct.Preorder(nodeFilter, func(n ast.Node) {
		switch fn := n.(type) {
		case *ast.FuncDecl:
			if isHTTPHandler(pass, fn.Type) {
				checkBody(pass, fn.Body)
			}
		case *ast.FuncLit:
			if isHTTPHandler(pass, fn.Type) {
				checkBody(pass, fn.Body)
			}
		}
	})

	return nil, nil
}

// isHTTPHandler checks if a function signature matches:
// func(http.ResponseWriter, *http.Request)
func isHTTPHandler(pass *analysis.Pass, ft *ast.FuncType) bool {
	if ft.Params == nil || len(ft.Params.List) < 2 {
		return false
	}

	// Flatten parameters (handles grouped params like `a, b int`)
	var params []ast.Expr
	for _, p := range ft.Params.List {
		for range p.Names {
			params = append(params, p.Type)
		}
		if len(p.Names) == 0 {
			params = append(params, p.Type)
		}
	}

	if len(params) < 2 {
		return false
	}

	// Check first param is http.ResponseWriter (interface)
	t0 := pass.TypesInfo.TypeOf(params[0])
	if t0 == nil || t0.String() != "net/http.ResponseWriter" {
		return false
	}

	// Check second param is *http.Request
	t1 := pass.TypesInfo.TypeOf(params[1])
	if t1 == nil {
		return false
	}
	ptr, ok := t1.(*types.Pointer)
	if !ok {
		return false
	}
	named, ok := ptr.Elem().(*types.Named)
	if !ok {
		return false
	}
	return named.Obj().Pkg() != nil &&
		named.Obj().Pkg().Path() == "net/http" &&
		named.Obj().Name() == "Request"
}

// checkBody walks a function body looking for context.Background() or context.TODO().
func checkBody(pass *analysis.Pass, body *ast.BlockStmt) {
	if body == nil {
		return
	}

	ast.Inspect(body, func(n ast.Node) bool {
		call, ok := n.(*ast.CallExpr)
		if !ok {
			return true
		}

		sel, ok := call.Fun.(*ast.SelectorExpr)
		if !ok {
			return true
		}

		// Check if it's context.Background() or context.TODO()
		if sel.Sel.Name != "Background" && sel.Sel.Name != "TODO" {
			return true
		}

		// Verify it's from the "context" package using type info
		obj := pass.TypesInfo.ObjectOf(sel.Sel)
		if obj == nil {
			return true
		}
		if obj.Pkg() != nil && obj.Pkg().Path() == "context" {
			pass.Reportf(call.Pos(),
				"use r.Context() instead of context.%s() inside HTTP handlers",
				sel.Sel.Name)
		}

		return true
	})
}
```

```go
// file: linters/ctxcheck/ctxcheck_test.go
package ctxcheck

import (
	"testing"

	"golang.org/x/tools/go/analysis/analysistest"
)

func TestAnalyzer(t *testing.T) {
	// testdata/ contains Go packages with expected diagnostics marked as comments
	testdata := analysistest.TestData()
	analysistest.Run(t, testdata, Analyzer, "handler")
}
```

```go
// file: linters/ctxcheck/testdata/src/handler/handler.go
package handler

import (
	"context"
	"fmt"
	"net/http"
)

// BAD: uses context.Background() inside handler
func HandleBad(w http.ResponseWriter, r *http.Request) {
	ctx := context.Background() // want `use r.Context\(\) instead of context.Background\(\) inside HTTP handlers`
	_ = ctx
	fmt.Fprintln(w, "bad")
}

// BAD: uses context.TODO() inside handler
func HandleTodo(w http.ResponseWriter, r *http.Request) {
	ctx := context.TODO() // want `use r.Context\(\) instead of context.TODO\(\) inside HTTP handlers`
	_ = ctx
	fmt.Fprintln(w, "todo")
}

// GOOD: uses r.Context()
func HandleGood(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	_ = ctx
	fmt.Fprintln(w, "good")
}

// GOOD: not an HTTP handler, context.Background() is fine
func regularFunction() {
	ctx := context.Background()
	_ = ctx
}

// BAD: function literal handler
var handlerLit = func(w http.ResponseWriter, r *http.Request) {
	_ = context.Background() // want `use r.Context\(\) instead of context.Background\(\) inside HTTP handlers`
}
```

```go
// file: linters/ctxcheck/cmd/ctxcheck/main.go
// Standalone binary for the linter.
package main

import (
	"golang.org/x/tools/go/analysis/singlechecker"
	"myproject/linters/ctxcheck"
)

func main() {
	singlechecker.Main(ctxcheck.Analyzer)
}
```

```go
// file: linters/ctxcheck/cmd/multi/main.go
// Multi-analyzer binary (combine multiple custom linters).
package main

import (
	"golang.org/x/tools/go/analysis/multichecker"
	"myproject/linters/ctxcheck"
	// Add more analyzers here
)

func main() {
	multichecker.Main(
		ctxcheck.Analyzer,
	)
}
```

**Running the linter:**

```bash
# Build and run standalone:
go build -o ctxcheck ./linters/ctxcheck/cmd/ctxcheck/
./ctxcheck ./...

# Run via go vet:
go vet -vettool=$(which ctxcheck) ./...

# Run tests (uses analysistest with testdata/):
go test ./linters/ctxcheck/

# Integration with golangci-lint (in .golangci.yml):
# linters:
#   enable:
#     - govet
# linters-settings:
#   govet:
#     enable:
#       - ctxcheck
```

**Test file convention:**

The `// want` comments in `testdata/` files tell `analysistest` what diagnostics to expect:

```go
context.Background() // want `use r.Context\(\)`
```

The regex in the backticks must match the diagnostic message. If the test expects no diagnostic, omit the comment.

Key points:

1. **`analysis.Analyzer`** is the standard unit of analysis. It has a name, doc, dependencies, and Run function.
2. **`inspect.Analyzer`** provides an efficient AST walker (shared across analyzers).
3. **`pass.TypesInfo`** gives type-checked information — use it to resolve imports and types accurately.
4. **`analysistest.Run`** is the standard way to test analyzers using `testdata/` packages with `// want` comments.
5. **`singlechecker.Main`** wraps an analyzer into a standalone binary compatible with `go vet -vettool`.'''),

    ("go_deep/dependency_injection_no_frameworks", r'''How do I implement dependency injection in Go without frameworks? Show me a clean pattern for a web service with multiple dependencies.''', r'''<think>
Go's approach to DI is simple: constructor injection with interfaces. No containers,
no reflection, no annotations. The pattern:
1. Define small interfaces for dependencies
2. Constructors accept interfaces as parameters
3. Wire everything in main()
4. Tests inject mocks
This is sometimes called "manual DI" or "poor man's DI" but it's actually the
cleanest approach in Go. It's explicit, type-safe, and easy to follow.
Key principles:
- Accept interfaces, return structs
- Wire in main() or a dedicated wire() function
- Use functional options for optional dependencies
- Group related dependencies into a struct if there are many
I should show a realistic web service with: database, cache, email service,
logger — all wired together with constructor injection. Show how this
makes testing easy and how to handle optional dependencies.
</think>

Here is a complete dependency injection pattern for a web service:

```go
// file: internal/domain/user.go
package domain

import "context"

type User struct {
	ID    string
	Name  string
	Email string
}

// Small, focused interfaces — defined by the consumer, not the provider.
type UserRepository interface {
	GetByID(ctx context.Context, id string) (*User, error)
	Create(ctx context.Context, user *User) error
}

type Cache interface {
	Get(ctx context.Context, key string) ([]byte, error)
	Set(ctx context.Context, key string, value []byte) error
}

type EmailSender interface {
	Send(ctx context.Context, to, subject, body string) error
}

type Logger interface {
	Info(msg string, args ...any)
	Error(msg string, args ...any)
}
```

```go
// file: internal/service/user_service.go
package service

import (
	"context"
	"encoding/json"
	"fmt"

	"myproject/internal/domain"
)

// UserService depends on interfaces, not implementations.
type UserService struct {
	repo   domain.UserRepository
	cache  domain.Cache
	email  domain.EmailSender
	logger domain.Logger
}

// NewUserService is the constructor — all dependencies are explicit.
func NewUserService(
	repo domain.UserRepository,
	cache domain.Cache,
	email domain.EmailSender,
	logger domain.Logger,
) *UserService {
	return &UserService{
		repo:   repo,
		cache:  cache,
		email:  email,
		logger: logger,
	}
}

func (s *UserService) GetUser(ctx context.Context, id string) (*domain.User, error) {
	// Try cache first
	cacheKey := "user:" + id
	if data, err := s.cache.Get(ctx, cacheKey); err == nil {
		var user domain.User
		if json.Unmarshal(data, &user) == nil {
			s.logger.Info("cache hit", "user_id", id)
			return &user, nil
		}
	}

	// Fall back to database
	user, err := s.repo.GetByID(ctx, id)
	if err != nil {
		s.logger.Error("get user failed", "user_id", id, "error", err)
		return nil, fmt.Errorf("get user %s: %w", id, err)
	}

	// Populate cache
	if data, err := json.Marshal(user); err == nil {
		s.cache.Set(ctx, cacheKey, data)
	}

	return user, nil
}

func (s *UserService) CreateUser(ctx context.Context, name, email string) (*domain.User, error) {
	user := &domain.User{
		ID:    generateID(),
		Name:  name,
		Email: email,
	}

	if err := s.repo.Create(ctx, user); err != nil {
		return nil, fmt.Errorf("create user: %w", err)
	}

	// Send welcome email (fire and forget)
	go func() {
		if err := s.email.Send(ctx, email, "Welcome!", "Welcome to our service, "+name); err != nil {
			s.logger.Error("welcome email failed", "email", email, "error", err)
		}
	}()

	s.logger.Info("user created", "user_id", user.ID)
	return user, nil
}

func generateID() string { return "uuid-placeholder" }
```

```go
// file: internal/handler/user_handler.go
package handler

import (
	"encoding/json"
	"net/http"

	"myproject/internal/service"
)

// UserHandler depends on the service layer.
type UserHandler struct {
	svc *service.UserService
}

func NewUserHandler(svc *service.UserService) *UserHandler {
	return &UserHandler{svc: svc}
}

func (h *UserHandler) GetUser(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id") // Go 1.22+ router
	user, err := h.svc.GetUser(r.Context(), id)
	if err != nil {
		http.Error(w, err.Error(), http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(user)
}
```

```go
// file: internal/infra/postgres.go
package infra

import (
	"context"
	"database/sql"

	"myproject/internal/domain"
)

// PostgresUserRepo implements domain.UserRepository.
type PostgresUserRepo struct {
	db *sql.DB
}

func NewPostgresUserRepo(db *sql.DB) *PostgresUserRepo {
	return &PostgresUserRepo{db: db}
}

func (r *PostgresUserRepo) GetByID(ctx context.Context, id string) (*domain.User, error) {
	user := &domain.User{}
	err := r.db.QueryRowContext(ctx,
		"SELECT id, name, email FROM users WHERE id = $1", id,
	).Scan(&user.ID, &user.Name, &user.Email)
	return user, err
}

func (r *PostgresUserRepo) Create(ctx context.Context, user *domain.User) error {
	_, err := r.db.ExecContext(ctx,
		"INSERT INTO users (id, name, email) VALUES ($1, $2, $3)",
		user.ID, user.Name, user.Email)
	return err
}
```

```go
// file: internal/infra/redis.go
package infra

import (
	"context"
	"time"

	"github.com/redis/go-redis/v9"
)

type RedisCache struct {
	client *redis.Client
	ttl    time.Duration
}

func NewRedisCache(client *redis.Client, ttl time.Duration) *RedisCache {
	return &RedisCache{client: client, ttl: ttl}
}

func (c *RedisCache) Get(ctx context.Context, key string) ([]byte, error) {
	return c.client.Get(ctx, key).Bytes()
}

func (c *RedisCache) Set(ctx context.Context, key string, value []byte) error {
	return c.client.Set(ctx, key, value, c.ttl).Err()
}
```

```go
// file: cmd/server/main.go
// main() is the composition root — this is where all wiring happens.
package main

import (
	"database/sql"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/redis/go-redis/v9"
	_ "github.com/lib/pq"

	"myproject/internal/handler"
	"myproject/internal/infra"
	"myproject/internal/service"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	// Build dependency graph — bottom up
	db, _ := sql.Open("postgres", os.Getenv("DATABASE_URL"))
	defer db.Close()

	redisClient := redis.NewClient(&redis.Options{Addr: os.Getenv("REDIS_URL")})
	defer redisClient.Close()

	// Infrastructure implementations
	userRepo := infra.NewPostgresUserRepo(db)
	cache := infra.NewRedisCache(redisClient, 5*time.Minute)
	emailer := infra.NewSMTPSender(os.Getenv("SMTP_HOST"))

	// Service layer (depends on infrastructure)
	userSvc := service.NewUserService(userRepo, cache, emailer, logger)

	// HTTP handlers (depend on services)
	userHandler := handler.NewUserHandler(userSvc)

	// Routes
	mux := http.NewServeMux()
	mux.HandleFunc("GET /users/{id}", userHandler.GetUser)

	logger.Info("starting server", "addr", ":8080")
	http.ListenAndServe(":8080", mux)
}
```

```go
// file: internal/service/user_service_test.go
package service

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"

	"myproject/internal/domain"
)

// Test mocks — simple implementations of the interfaces.
type mockRepo struct {
	users map[string]*domain.User
}

func (m *mockRepo) GetByID(_ context.Context, id string) (*domain.User, error) {
	u, ok := m.users[id]
	if !ok {
		return nil, fmt.Errorf("not found")
	}
	return u, nil
}

func (m *mockRepo) Create(_ context.Context, user *domain.User) error {
	m.users[user.ID] = user
	return nil
}

type mockCache struct {
	data map[string][]byte
}

func (m *mockCache) Get(_ context.Context, key string) ([]byte, error) {
	v, ok := m.data[key]
	if !ok {
		return nil, fmt.Errorf("miss")
	}
	return v, nil
}

func (m *mockCache) Set(_ context.Context, key string, val []byte) error {
	m.data[key] = val
	return nil
}

type mockEmail struct{ sent []string }

func (m *mockEmail) Send(_ context.Context, to, _, _ string) error {
	m.sent = append(m.sent, to)
	return nil
}

type mockLogger struct{}

func (m *mockLogger) Info(_ string, _ ...any) {}
func (m *mockLogger) Error(_ string, _ ...any) {}

func TestGetUser_CacheMiss(t *testing.T) {
	repo := &mockRepo{users: map[string]*domain.User{
		"123": {ID: "123", Name: "Alice", Email: "alice@example.com"},
	}}
	cache := &mockCache{data: make(map[string][]byte)}

	svc := NewUserService(repo, cache, &mockEmail{}, &mockLogger{})

	user, err := svc.GetUser(context.Background(), "123")
	if err != nil {
		t.Fatal(err)
	}
	if user.Name != "Alice" {
		t.Errorf("name = %q, want Alice", user.Name)
	}

	// Verify cache was populated
	if _, err := cache.Get(context.Background(), "user:123"); err != nil {
		t.Error("expected cache to be populated")
	}
}

func TestGetUser_CacheHit(t *testing.T) {
	user := &domain.User{ID: "123", Name: "Cached Alice"}
	data, _ := json.Marshal(user)

	cache := &mockCache{data: map[string][]byte{"user:123": data}}
	repo := &mockRepo{users: make(map[string]*domain.User)} // empty repo

	svc := NewUserService(repo, cache, &mockEmail{}, &mockLogger{})

	got, err := svc.GetUser(context.Background(), "123")
	if err != nil {
		t.Fatal(err)
	}
	if got.Name != "Cached Alice" {
		t.Errorf("expected cached result, got %q", got.Name)
	}
}
```

Key principles:

1. **Constructor injection**: dependencies are explicit function parameters, not globals or singletons.
2. **Interfaces defined by consumers** (`domain` package), not implementors (`infra` package).
3. **`main()` is the composition root**: all wiring happens here, not scattered across the codebase.
4. **Testing is trivial**: inject mock structs that implement the same interfaces.
5. **No framework needed**: Go's interfaces + constructors give you compile-time verified DI.'''),

    ("go_deep/graceful_service_lifecycle", r'''How do I implement graceful service lifecycle management in Go with proper initialization, running, and shutdown phases? I need to handle OS signals and clean up resources.''', r'''<think>
Graceful lifecycle involves:
1. Init: set up resources (DB connections, caches, message queues)
2. Run: start serving, handle requests
3. Shutdown: catch OS signals, drain connections, close resources in reverse order
Key tools:
- os/signal.NotifyContext for signal-aware context
- errgroup for managing concurrent services
- Context cancellation for propagating shutdown
- sync.WaitGroup or errgroup for waiting on goroutines
- HTTP server's Shutdown(ctx) for graceful HTTP drain
The order matters: stop accepting new work, drain in-flight work, close resources
in reverse order (close DB last since other services depend on it).
I should show a realistic service with HTTP server + background workers +
database, all with proper shutdown ordering.
</think>

Here is a complete graceful service lifecycle implementation:

```go
package main

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

// --- Service interface ---

type Service interface {
	Name() string
	Start(ctx context.Context) error
	Stop(ctx context.Context) error
}

// --- Application lifecycle manager ---

type App struct {
	logger   *slog.Logger
	services []Service
	shutdown []func(ctx context.Context) error // cleanup funcs in LIFO order
}

func NewApp(logger *slog.Logger) *App {
	return &App{logger: logger}
}

// AddService registers a service to be started and stopped.
func (a *App) AddService(svc Service) {
	a.services = append(a.services, svc)
}

// OnShutdown registers a cleanup function (called in LIFO order).
func (a *App) OnShutdown(fn func(ctx context.Context) error) {
	a.shutdown = append(a.shutdown, fn)
}

// Run starts all services and blocks until a shutdown signal is received.
func (a *App) Run(ctx context.Context) error {
	// Create signal-aware context
	ctx, stop := signal.NotifyContext(ctx, syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// Start all services concurrently
	var wg sync.WaitGroup
	errCh := make(chan error, len(a.services))

	for _, svc := range a.services {
		svc := svc
		wg.Add(1)
		go func() {
			defer wg.Done()
			a.logger.Info("starting service", "name", svc.Name())
			if err := svc.Start(ctx); err != nil && !errors.Is(err, context.Canceled) {
				a.logger.Error("service failed", "name", svc.Name(), "error", err)
				errCh <- fmt.Errorf("%s: %w", svc.Name(), err)
			}
		}()
	}

	// Wait for shutdown signal or service error
	select {
	case <-ctx.Done():
		a.logger.Info("shutdown signal received")
	case err := <-errCh:
		a.logger.Error("service error triggered shutdown", "error", err)
	}

	// Graceful shutdown with timeout
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	return a.gracefulShutdown(shutdownCtx, &wg)
}

func (a *App) gracefulShutdown(ctx context.Context, wg *sync.WaitGroup) error {
	var errs []error

	// Stop services in reverse order (last added = first stopped)
	for i := len(a.services) - 1; i >= 0; i-- {
		svc := a.services[i]
		a.logger.Info("stopping service", "name", svc.Name())
		if err := svc.Stop(ctx); err != nil {
			a.logger.Error("stop failed", "name", svc.Name(), "error", err)
			errs = append(errs, err)
		}
	}

	// Wait for service goroutines to finish
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		a.logger.Info("all services stopped")
	case <-ctx.Done():
		a.logger.Error("shutdown timed out")
		errs = append(errs, ctx.Err())
	}

	// Run cleanup functions in LIFO order
	for i := len(a.shutdown) - 1; i >= 0; i-- {
		if err := a.shutdown[i](ctx); err != nil {
			errs = append(errs, err)
		}
	}

	return errors.Join(errs...)
}

// --- HTTP Server service ---

type HTTPServer struct {
	server *http.Server
	logger *slog.Logger
}

func NewHTTPServer(addr string, handler http.Handler, logger *slog.Logger) *HTTPServer {
	return &HTTPServer{
		server: &http.Server{
			Addr:         addr,
			Handler:      handler,
			ReadTimeout:  10 * time.Second,
			WriteTimeout: 30 * time.Second,
			IdleTimeout:  60 * time.Second,
		},
		logger: logger,
	}
}

func (s *HTTPServer) Name() string { return "http-server" }

func (s *HTTPServer) Start(ctx context.Context) error {
	s.logger.Info("HTTP server listening", "addr", s.server.Addr)
	err := s.server.ListenAndServe()
	if errors.Is(err, http.ErrServerClosed) {
		return nil // expected during shutdown
	}
	return err
}

func (s *HTTPServer) Stop(ctx context.Context) error {
	s.logger.Info("draining HTTP connections")
	return s.server.Shutdown(ctx) // waits for in-flight requests
}

// --- Background worker service ---

type Worker struct {
	name     string
	interval time.Duration
	work     func(ctx context.Context) error
	logger   *slog.Logger
}

func NewWorker(name string, interval time.Duration, work func(ctx context.Context) error, logger *slog.Logger) *Worker {
	return &Worker{name: name, interval: interval, work: work, logger: logger}
}

func (w *Worker) Name() string { return w.name }

func (w *Worker) Start(ctx context.Context) error {
	ticker := time.NewTicker(w.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			w.logger.Info("worker stopping", "name", w.name)
			return ctx.Err()
		case <-ticker.C:
			if err := w.work(ctx); err != nil {
				w.logger.Error("worker tick failed", "name", w.name, "error", err)
				// Continue running — don't crash on transient errors
			}
		}
	}
}

func (w *Worker) Stop(ctx context.Context) error {
	// Worker stops when context is cancelled in Start()
	return nil
}

// --- Health checker ---

type HealthChecker struct {
	checks map[string]func() error
	mu     sync.RWMutex
	ready  bool
}

func NewHealthChecker() *HealthChecker {
	return &HealthChecker{checks: make(map[string]func() error)}
}

func (h *HealthChecker) Register(name string, check func() error) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.checks[name] = check
}

func (h *HealthChecker) SetReady(ready bool) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.ready = ready
}

func (h *HealthChecker) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		h.mu.RLock()
		defer h.mu.RUnlock()
		for name, check := range h.checks {
			if err := check(); err != nil {
				http.Error(w, name+": "+err.Error(), http.StatusServiceUnavailable)
				return
			}
		}
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})
	mux.HandleFunc("GET /readyz", func(w http.ResponseWriter, r *http.Request) {
		h.mu.RLock()
		defer h.mu.RUnlock()
		if !h.ready {
			http.Error(w, "not ready", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ready")
	})
	return mux
}

// --- Main: wiring everything together ---

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

	app := NewApp(logger)

	// Initialize resources
	db, err := sql.Open("postgres", os.Getenv("DATABASE_URL"))
	if err != nil {
		logger.Error("connect db", "error", err)
		os.Exit(1)
	}

	// Register DB cleanup (runs LAST due to LIFO)
	app.OnShutdown(func(ctx context.Context) error {
		logger.Info("closing database connection")
		return db.Close()
	})

	// Health checks
	health := NewHealthChecker()
	health.Register("db", db.Ping)

	// HTTP API
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/users/{id}", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintf(w, `{"id": "%s"}`, r.PathValue("id"))
	})
	mux.Handle("/", health.Handler())

	httpSvc := NewHTTPServer(":8080", mux, logger)
	app.AddService(httpSvc)

	// Background worker
	metricsSvc := NewWorker("metrics-flusher", 30*time.Second, func(ctx context.Context) error {
		logger.Info("flushing metrics")
		return nil
	}, logger)
	app.AddService(metricsSvc)

	// Mark as ready after all services are registered
	health.SetReady(true)

	// Run blocks until shutdown
	if err := app.Run(context.Background()); err != nil {
		logger.Error("app shutdown error", "error", err)
		os.Exit(1)
	}

	logger.Info("clean shutdown complete")
}
```

**Shutdown sequence:**

```
1. SIGINT/SIGTERM received
2. Stop HTTP server (drain in-flight requests, stop accepting new ones)
3. Stop background workers (context cancellation)
4. Wait for all goroutines to finish (with 30s timeout)
5. Run cleanup functions in LIFO order (close DB last)
6. Exit
```

Key points:

1. **`signal.NotifyContext`** creates a context that cancels on OS signals. Clean and composable.
2. **Services stop in reverse order**: HTTP server stops first (stops accepting requests), DB closes last.
3. **`http.Server.Shutdown`** gracefully drains in-flight connections without dropping requests.
4. **30-second timeout** prevents hanging forever if a service won't stop.
5. **Health and readiness endpoints** (`/healthz`, `/readyz`) let load balancers route traffic away before shutdown.
6. **`errors.Join`** collects all shutdown errors instead of losing them.'''),

    ("go_deep/feature_flags_runtime_toggle", r'''How do I implement feature flags in Go with runtime toggling? I need to enable/disable features without redeployment.''', r'''<think>
Feature flags in Go can be implemented with:
1. Atomic booleans for simple on/off flags
2. A flag store backed by config file, env vars, or external service
3. Middleware for HTTP-level flag checking
4. Context-based flag propagation for per-request flags
Key requirements:
- Thread-safe reads (flags are checked on every request)
- Runtime toggling without restart (file watcher, API endpoint, or polling)
- Type-safe flag access (not just strings)
- Default values for unknown flags
- Per-user/percentage rollout support
I should show a practical implementation: a FlagStore that loads from JSON,
supports runtime reload via API or file watcher, provides typed access,
and integrates with HTTP middleware for feature gating.
</think>

Here is a complete feature flag system with runtime toggling:

```go
package feature

import (
	"context"
	"encoding/json"
	"fmt"
	"hash/fnv"
	"net/http"
	"os"
	"sync"
	"sync/atomic"
	"time"
)

// --- Flag definitions ---

type Flag struct {
	Name        string  `json:"name"`
	Enabled     bool    `json:"enabled"`
	Percentage  float64 `json:"percentage,omitempty"`  // 0-100 for gradual rollout
	AllowList   []string `json:"allow_list,omitempty"` // user IDs with explicit access
	Description string  `json:"description,omitempty"`
}

// --- Flag store ---

type Store struct {
	flags    atomic.Value // map[string]*Flag
	mu       sync.Mutex   // protects writes
	onChange []func(name string, flag *Flag)
}

func NewStore() *Store {
	s := &Store{}
	s.flags.Store(make(map[string]*Flag))
	return s
}

// Get returns a flag by name. Returns a disabled flag if not found.
func (s *Store) Get(name string) *Flag {
	flags := s.flags.Load().(map[string]*Flag)
	if f, ok := flags[name]; ok {
		return f
	}
	return &Flag{Name: name, Enabled: false}
}

// IsEnabled checks if a flag is enabled (simple on/off).
func (s *Store) IsEnabled(name string) bool {
	return s.Get(name).Enabled
}

// IsEnabledFor checks if a flag is enabled for a specific user.
// Supports: simple on/off, percentage rollout, and allow lists.
func (s *Store) IsEnabledFor(name, userID string) bool {
	f := s.Get(name)

	if !f.Enabled {
		return false
	}

	// Check allow list first
	for _, id := range f.AllowList {
		if id == userID {
			return true
		}
	}

	// Check percentage rollout
	if f.Percentage > 0 && f.Percentage < 100 {
		return hashUserToPercent(name, userID) < f.Percentage
	}

	return f.Enabled
}

// Set updates a single flag at runtime.
func (s *Store) Set(name string, flag *Flag) {
	s.mu.Lock()
	defer s.mu.Unlock()

	current := s.flags.Load().(map[string]*Flag)
	updated := make(map[string]*Flag, len(current)+1)
	for k, v := range current {
		updated[k] = v
	}
	updated[name] = flag
	s.flags.Store(updated)

	for _, fn := range s.onChange {
		fn(name, flag)
	}
}

// OnChange registers a callback for flag changes.
func (s *Store) OnChange(fn func(name string, flag *Flag)) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.onChange = append(s.onChange, fn)
}

// LoadFromFile loads flags from a JSON file.
func (s *Store) LoadFromFile(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read flags file: %w", err)
	}

	var flags []Flag
	if err := json.Unmarshal(data, &flags); err != nil {
		return fmt.Errorf("parse flags: %w", err)
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	flagMap := make(map[string]*Flag, len(flags))
	for i := range flags {
		flagMap[flags[i].Name] = &flags[i]
	}
	s.flags.Store(flagMap)

	return nil
}

// All returns all flags (for admin API).
func (s *Store) All() []*Flag {
	flags := s.flags.Load().(map[string]*Flag)
	result := make([]*Flag, 0, len(flags))
	for _, f := range flags {
		result = append(result, f)
	}
	return result
}

// WatchFile polls a file for changes and reloads flags.
func (s *Store) WatchFile(ctx context.Context, path string, interval time.Duration) {
	var lastMod time.Time

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			info, err := os.Stat(path)
			if err != nil {
				continue
			}
			if info.ModTime().After(lastMod) {
				if err := s.LoadFromFile(path); err == nil {
					lastMod = info.ModTime()
				}
			}
		}
	}
}

// Deterministic hash for percentage rollout (consistent per user+flag).
func hashUserToPercent(flagName, userID string) float64 {
	h := fnv.New32a()
	h.Write([]byte(flagName + ":" + userID))
	return float64(h.Sum32()%10000) / 100.0 // 0.00 - 99.99
}

// --- Context-based flag propagation ---

type ctxKey struct{}

// WithFlags adds a flag store to context.
func WithFlags(ctx context.Context, store *Store) context.Context {
	return context.WithValue(ctx, ctxKey{}, store)
}

// FromContext retrieves the flag store from context.
func FromContext(ctx context.Context) *Store {
	s, ok := ctx.Value(ctxKey{}).(*Store)
	if !ok {
		return NewStore() // return empty store as fallback
	}
	return s
}

// --- HTTP middleware and admin API ---

func Middleware(store *Store) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ctx := WithFlags(r.Context(), store)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// AdminHandler provides HTTP endpoints for flag management.
func AdminHandler(store *Store) http.Handler {
	mux := http.NewServeMux()

	// List all flags
	mux.HandleFunc("GET /flags", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(store.All())
	})

	// Toggle a flag
	mux.HandleFunc("PUT /flags/{name}", func(w http.ResponseWriter, r *http.Request) {
		name := r.PathValue("name")
		var flag Flag
		if err := json.NewDecoder(r.Body).Decode(&flag); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		flag.Name = name
		store.Set(name, &flag)
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(flag)
	})

	return mux
}

// --- Usage in application code ---

func HandleNewDashboard(w http.ResponseWriter, r *http.Request) {
	flags := FromContext(r.Context())
	userID := r.Header.Get("X-User-ID")

	if flags.IsEnabledFor("new_dashboard", userID) {
		fmt.Fprintln(w, "Welcome to the new dashboard!")
	} else {
		fmt.Fprintln(w, "Classic dashboard")
	}
}
```

**Flags JSON file:**

```json
[
  {"name": "new_dashboard", "enabled": true, "percentage": 25, "description": "Rollout new dashboard UI"},
  {"name": "dark_mode", "enabled": true, "description": "Enable dark mode option"},
  {"name": "beta_search", "enabled": true, "allow_list": ["user-123", "user-456"], "description": "Beta search for specific users"},
  {"name": "maintenance_mode", "enabled": false, "description": "Show maintenance page"}
]
```

**Usage:**

```go
func main() {
	store := feature.NewStore()
	store.LoadFromFile("flags.json")

	// Watch for file changes every 10 seconds
	go store.WatchFile(context.Background(), "flags.json", 10*time.Second)

	// Log flag changes
	store.OnChange(func(name string, flag *feature.Flag) {
		slog.Info("flag changed", "name", name, "enabled", flag.Enabled)
	})

	mux := http.NewServeMux()
	mux.HandleFunc("GET /dashboard", feature.HandleNewDashboard)
	mux.Handle("/admin/", http.StripPrefix("/admin", feature.AdminHandler(store)))

	// Wrap with middleware to inject flags into context
	handler := feature.Middleware(store)(mux)
	http.ListenAndServe(":8080", handler)
}

// Toggle via API:
// curl -X PUT localhost:8080/admin/flags/new_dashboard \
//   -d '{"enabled": true, "percentage": 50}'
```

Key points:

1. **`atomic.Value`** for the flag map gives lock-free reads on every request.
2. **Percentage rollout** uses deterministic hashing so the same user always gets the same result.
3. **File watching** enables toggling by editing a JSON file — no restart needed.
4. **Admin API** enables toggling via HTTP calls at runtime.
5. **Context propagation** makes flags available deep in the call stack without passing them explicitly.
6. **Allow lists** enable targeted rollout to specific users before broader percentage rollout.'''),

    ("go_deep/structured_error_types_is_as", r'''How do I implement structured error types in Go with proper Is/As chains? I need a rich error hierarchy for an API service.''', r'''<think>
Go 1.13+ introduced errors.Is and errors.As for error inspection, and error wrapping
with %w in fmt.Errorf. For structured error types:
- Implement the error interface (Error() string)
- Implement Unwrap() error for wrapping chains
- Use errors.Is to check for sentinel errors
- Use errors.As to extract typed errors from the chain
- Implement Is() or As() methods for custom matching logic
Key patterns:
- Sentinel errors (var ErrNotFound = errors.New("not found"))
- Typed errors with context (struct implementing error)
- Error wrapping chains (wrapping with %w preserves the chain)
- Multi-error unwrapping (Unwrap() []error for Go 1.20+)
I should show a realistic API error hierarchy: base error types for different
HTTP status codes, domain-specific errors with fields, and how to unwrap
them in middleware for proper HTTP responses. Show Is, As, and custom
matching behavior.
</think>

Here is a complete structured error type system:

```go
package apierr

import (
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// --- Sentinel errors (for simple Is checks) ---

var (
	ErrNotFound      = errors.New("not found")
	ErrUnauthorized  = errors.New("unauthorized")
	ErrForbidden     = errors.New("forbidden")
	ErrConflict      = errors.New("conflict")
	ErrRateLimit     = errors.New("rate limit exceeded")
	ErrInternal      = errors.New("internal error")
)

// --- Structured error types ---

// APIError is the base error type for all API errors.
type APIError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Detail  string `json:"detail,omitempty"`
	Err     error  `json:"-"` // wrapped error, not serialized
}

func (e *APIError) Error() string {
	if e.Detail != "" {
		return fmt.Sprintf("[%d] %s: %s", e.Code, e.Message, e.Detail)
	}
	return fmt.Sprintf("[%d] %s", e.Code, e.Message)
}

func (e *APIError) Unwrap() error {
	return e.Err
}

// Is allows matching APIError by status code.
// errors.Is(err, &APIError{Code: 404}) matches any 404 APIError.
func (e *APIError) Is(target error) bool {
	t, ok := target.(*APIError)
	if !ok {
		return false
	}
	// Match by code if target has a code set
	if t.Code != 0 {
		return e.Code == t.Code
	}
	return false
}

// --- Typed domain errors ---

// ValidationError contains field-level validation details.
type ValidationError struct {
	Fields []FieldError
}

type FieldError struct {
	Field   string `json:"field"`
	Message string `json:"message"`
}

func (e *ValidationError) Error() string {
	msgs := make([]string, len(e.Fields))
	for i, f := range e.Fields {
		msgs[i] = f.Field + ": " + f.Message
	}
	return "validation failed: " + strings.Join(msgs, "; ")
}

// ResourceError identifies which resource had the problem.
type ResourceError struct {
	Resource string // e.g., "user", "order"
	ID       string // e.g., "123"
	Op       string // e.g., "create", "update", "delete"
	Err      error  // underlying error
}

func (e *ResourceError) Error() string {
	return fmt.Sprintf("%s %s (id=%s): %v", e.Op, e.Resource, e.ID, e.Err)
}

func (e *ResourceError) Unwrap() error {
	return e.Err
}

// RetryableError indicates the operation can be retried.
type RetryableError struct {
	Err        error
	RetryAfter time.Duration
}

func (e *RetryableError) Error() string {
	return fmt.Sprintf("retryable: %v (retry after %v)", e.Err, e.RetryAfter)
}

func (e *RetryableError) Unwrap() error {
	return e.Err
}

// --- Constructor functions ---

func NewNotFound(resource, id string) error {
	return &ResourceError{
		Resource: resource,
		ID:       id,
		Op:       "get",
		Err: &APIError{
			Code:    http.StatusNotFound,
			Message: resource + " not found",
			Detail:  fmt.Sprintf("no %s with id %s", resource, id),
			Err:     ErrNotFound,
		},
	}
}

func NewValidation(fields ...FieldError) error {
	return &APIError{
		Code:    http.StatusBadRequest,
		Message: "validation error",
		Err:     &ValidationError{Fields: fields},
	}
}

func NewConflict(resource, field, value string) error {
	return &APIError{
		Code:    http.StatusConflict,
		Message: "resource conflict",
		Detail:  fmt.Sprintf("%s with %s=%s already exists", resource, field, value),
		Err:     ErrConflict,
	}
}

func NewRateLimit(retryAfter time.Duration) error {
	return &RetryableError{
		RetryAfter: retryAfter,
		Err: &APIError{
			Code:    http.StatusTooManyRequests,
			Message: "rate limit exceeded",
			Err:     ErrRateLimit,
		},
	}
}

func Wrap(err error, op string) error {
	return fmt.Errorf("%s: %w", op, err)
}

// --- HTTP error middleware ---

func ErrorToHTTP(err error) (int, map[string]any) {
	// Check for APIError to get the status code
	var apiErr *APIError
	if errors.As(err, &apiErr) {
		response := map[string]any{
			"error":   apiErr.Message,
			"code":    apiErr.Code,
		}
		if apiErr.Detail != "" {
			response["detail"] = apiErr.Detail
		}

		// Check if validation error is wrapped inside
		var valErr *ValidationError
		if errors.As(err, &valErr) {
			response["fields"] = valErr.Fields
		}

		// Check if retryable
		var retryErr *RetryableError
		if errors.As(err, &retryErr) {
			response["retry_after_seconds"] = retryErr.RetryAfter.Seconds()
		}

		return apiErr.Code, response
	}

	// Unknown error — return 500
	return http.StatusInternalServerError, map[string]any{
		"error": "internal server error",
		"code":  500,
	}
}

// --- Usage in service layer ---

func GetUser(id string) error {
	// Simulate DB lookup
	if id == "" {
		return NewValidation(FieldError{Field: "id", Message: "required"})
	}

	// Wrap with operation context
	err := NewNotFound("user", id)
	return Wrap(err, "GetUser")
}

func CreateUser(email string) error {
	// Simulate duplicate email
	return Wrap(
		NewConflict("user", "email", email),
		"CreateUser",
	)
}
```

```go
// file: apierr/apierr_test.go
package apierr

import (
	"errors"
	"net/http"
	"testing"
	"time"
)

func TestErrorChain_Is(t *testing.T) {
	err := GetUser("missing-id")

	// Is checks traverse the entire chain
	if !errors.Is(err, ErrNotFound) {
		t.Error("should match ErrNotFound sentinel")
	}

	// Match by APIError code
	if !errors.Is(err, &APIError{Code: http.StatusNotFound}) {
		t.Error("should match 404 APIError")
	}

	// Does not match wrong sentinel
	if errors.Is(err, ErrUnauthorized) {
		t.Error("should not match ErrUnauthorized")
	}
}

func TestErrorChain_As(t *testing.T) {
	err := GetUser("missing-id")

	// Extract ResourceError from chain
	var resErr *ResourceError
	if !errors.As(err, &resErr) {
		t.Fatal("should extract ResourceError")
	}
	if resErr.Resource != "user" {
		t.Errorf("resource = %q, want user", resErr.Resource)
	}
	if resErr.ID != "missing-id" {
		t.Errorf("id = %q, want missing-id", resErr.ID)
	}

	// Extract APIError from deeper in the chain
	var apiErr *APIError
	if !errors.As(err, &apiErr) {
		t.Fatal("should extract APIError")
	}
	if apiErr.Code != 404 {
		t.Errorf("code = %d, want 404", apiErr.Code)
	}
}

func TestValidationError(t *testing.T) {
	err := NewValidation(
		FieldError{Field: "name", Message: "required"},
		FieldError{Field: "email", Message: "invalid format"},
	)

	// Extract validation details
	var valErr *ValidationError
	if !errors.As(err, &valErr) {
		t.Fatal("should extract ValidationError")
	}
	if len(valErr.Fields) != 2 {
		t.Errorf("fields count = %d, want 2", len(valErr.Fields))
	}

	// Convert to HTTP response
	code, body := ErrorToHTTP(err)
	if code != http.StatusBadRequest {
		t.Errorf("code = %d, want 400", code)
	}
	if body["error"] != "validation error" {
		t.Errorf("error = %v", body["error"])
	}
}

func TestRetryableError(t *testing.T) {
	err := NewRateLimit(30 * time.Second)

	// Check Is chain
	if !errors.Is(err, ErrRateLimit) {
		t.Error("should match ErrRateLimit")
	}

	// Extract retry info
	var retryErr *RetryableError
	if !errors.As(err, &retryErr) {
		t.Fatal("should extract RetryableError")
	}
	if retryErr.RetryAfter != 30*time.Second {
		t.Errorf("retry after = %v, want 30s", retryErr.RetryAfter)
	}

	// HTTP conversion includes retry info
	code, body := ErrorToHTTP(err)
	if code != http.StatusTooManyRequests {
		t.Errorf("code = %d, want 429", code)
	}
	if body["retry_after_seconds"] != 30.0 {
		t.Errorf("retry_after = %v", body["retry_after_seconds"])
	}
}

func TestWrappedError_FullChain(t *testing.T) {
	// Build a deep chain: Wrap -> ResourceError -> APIError -> ErrNotFound
	err := GetUser("42")

	t.Logf("Full error: %v", err)
	// Output: GetUser: get user (id=42): [404] user not found: no user with id 42

	// errors.Is walks the full chain
	if !errors.Is(err, ErrNotFound) {
		t.Error("Is(ErrNotFound) should be true")
	}

	// errors.As extracts from anywhere in the chain
	var apiErr *APIError
	errors.As(err, &apiErr)
	if apiErr.Code != 404 {
		t.Errorf("code = %d", apiErr.Code)
	}
}
```

**Error chain visualization:**

```
Wrap("GetUser")
  └── ResourceError{Resource: "user", ID: "42", Op: "get"}
        └── APIError{Code: 404, Message: "user not found"}
              └── ErrNotFound (sentinel)
```

`errors.Is(err, ErrNotFound)` walks the entire chain and finds it.
`errors.As(err, &apiErr)` extracts the first `*APIError` in the chain.

Key points:

1. **`Unwrap() error`** enables `errors.Is` and `errors.As` to traverse the chain.
2. **Custom `Is()` method** on `APIError` enables matching by status code, not identity.
3. **Constructor functions** (`NewNotFound`, `NewValidation`) build correct error chains consistently.
4. **`Wrap()` adds context** without losing the underlying error type information.
5. **`errors.As` extracts typed errors** from anywhere in the chain for structured handling (HTTP response, logging, retry logic).
6. **Sentinel errors + typed errors compose**: `errors.Is` checks category, `errors.As` extracts details.'''),
]
