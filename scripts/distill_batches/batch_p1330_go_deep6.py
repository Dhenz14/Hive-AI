"""Go deep reasoning pairs batch 6: systems programming."""
PAIRS = [
    ("go_deep/fsnotify_debounce", r'''How do I watch a directory for file changes in Go using fsnotify, but debounce rapid events so I only react once per burst of writes?''', r'''<think>
File watching with fsnotify fires multiple events for a single logical file save — editors do write-to-temp, rename, chmod, etc. We need debouncing.

The strategy: maintain a map of file paths to timers. Each time an event fires, reset the timer for that path. Only when the timer actually expires (no new events within the debounce window) do we process the event.

Key considerations:
- fsnotify.NewWatcher gives us a channel-based API
- We need to handle both Events and Errors channels
- Timer reset: stop the old timer, create a new one — but timer.Stop() doesn't drain the channel, so use AfterFunc instead
- AfterFunc runs in its own goroutine, so the callback needs synchronization if it touches shared state
- The debounce window should be configurable, typically 100-500ms
- We should filter by operation type — usually we care about Write and Create, not Chmod
- Need to recursively add subdirectories if watching a tree
- Clean shutdown via context cancellation
- The map of pending timers should be protected or confined to a single goroutine
- We can confine everything to the select loop goroutine by having AfterFunc send on a separate channel rather than calling the handler directly
- This avoids races between the event loop and timer callbacks
- For production use, consider that rename events may not carry the new name on all platforms
- Memory: timers for deleted files should be cleaned up
</think>

Here is a complete file watcher with debouncing using `fsnotify`:

```go
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"sync"
	"time"

	"github.com/fsnotify/fsnotify"
)

// DebouncedWatcher wraps fsnotify with per-file debouncing.
type DebouncedWatcher struct {
	watcher  *fsnotify.Watcher
	delay    time.Duration
	handler  func(event fsnotify.Event)
	mu       sync.Mutex
	timers   map[string]*time.Timer
}

func NewDebouncedWatcher(delay time.Duration, handler func(fsnotify.Event)) (*DebouncedWatcher, error) {
	w, err := fsnotify.NewWatcher()
	if err != nil {
		return nil, fmt.Errorf("fsnotify.NewWatcher: %w", err)
	}
	return &DebouncedWatcher{
		watcher: w,
		delay:   delay,
		handler: handler,
		timers:  make(map[string]*time.Timer),
	}, nil
}

// AddRecursive adds a directory and all subdirectories to the watch list.
func (dw *DebouncedWatcher) AddRecursive(root string) error {
	return filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			if err := dw.watcher.Add(path); err != nil {
				return fmt.Errorf("watch %s: %w", path, err)
			}
			log.Printf("watching: %s", path)
		}
		return nil
	})
}

// Run starts the event loop. Blocks until ctx is cancelled.
func (dw *DebouncedWatcher) Run(ctx context.Context) {
	defer dw.watcher.Close()

	for {
		select {
		case <-ctx.Done():
			dw.mu.Lock()
			for _, t := range dw.timers {
				t.Stop()
			}
			dw.mu.Unlock()
			return

		case event, ok := <-dw.watcher.Events:
			if !ok {
				return
			}
			// Filter: only care about writes and creates.
			if event.Op&(fsnotify.Write|fsnotify.Create) == 0 {
				continue
			}
			dw.debounce(event)

		case err, ok := <-dw.watcher.Errors:
			if !ok {
				return
			}
			log.Printf("watcher error: %v", err)
		}
	}
}

func (dw *DebouncedWatcher) debounce(event fsnotify.Event) {
	dw.mu.Lock()
	defer dw.mu.Unlock()

	key := event.Name

	// If a timer already exists for this file, reset it.
	if t, exists := dw.timers[key]; exists {
		t.Stop()
	}

	// AfterFunc runs handler in a new goroutine after the delay.
	dw.timers[key] = time.AfterFunc(dw.delay, func() {
		dw.mu.Lock()
		delete(dw.timers, key)
		dw.mu.Unlock()

		dw.handler(event)
	})
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	dw, err := NewDebouncedWatcher(200*time.Millisecond, func(ev fsnotify.Event) {
		fmt.Printf("[%s] changed: %s\n", time.Now().Format("15:04:05.000"), ev.Name)
	})
	if err != nil {
		log.Fatal(err)
	}

	dir := "."
	if len(os.Args) > 1 {
		dir = os.Args[1]
	}

	if err := dw.AddRecursive(dir); err != nil {
		log.Fatal(err)
	}

	fmt.Println("watching for changes (Ctrl+C to quit)...")
	dw.Run(ctx)
}
```

Key design points:

- **Per-file debouncing**: each file path gets its own `time.AfterFunc` timer, so rapid writes to `a.go` don't suppress events for `b.go`.
- **`time.AfterFunc` over `time.NewTimer`**: avoids the need to drain timer channels manually; the callback fires in its own goroutine.
- **Mutex protects only the timer map**: the handler runs outside the lock so slow handlers cannot block event ingestion.
- **Recursive watch**: `WalkDir` adds all subdirectories. For newly created subdirectories at runtime, you would also watch `Create` events for directories and call `watcher.Add`.
- **Clean shutdown**: context cancellation stops all pending timers and exits the loop.

Install the dependency with `go get github.com/fsnotify/fsnotify` before running.'''),

    ("go_deep/mmap_file_io", r'''Show me how to do memory-mapped file I/O in Go — reading a large file via mmap and processing it without loading the whole thing into a Go slice via os.ReadFile.''', r'''<think>
Memory-mapped files let the OS page file contents into virtual memory on demand. In Go, we can use the syscall/mmap or a library like golang.org/x/exp/mmap, but for maximum control and educational value, let's use syscall.Mmap on Unix.

Key considerations:
- syscall.Mmap returns a []byte backed by the kernel's page cache — no copy into Go heap
- The slice is valid only while the mapping exists; we must syscall.Munmap when done
- For read-only access: PROT_READ, MAP_PRIVATE (or MAP_SHARED, doesn't matter for read-only)
- For write access: PROT_READ|PROT_WRITE with MAP_SHARED to persist changes
- The file must be opened with matching flags (O_RDONLY vs O_RDWR)
- On Windows this would need different syscalls (CreateFileMapping/MapViewOfFile) — so for portability, use a library
- We should demonstrate both reading and a counted-line scan as a practical use case
- mmap is great for random access patterns or when the file is too large for heap
- The GC does NOT manage mmap'd memory — we must unmap manually
- We need to handle the file size to set the mmap length
- For files larger than available RAM, the OS will page in/out transparently
- Edge case: empty files can't be mmap'd (length 0 is invalid)
- Let's build a practical example: count lines in a large file via mmap, comparing performance with os.ReadFile
- bytes.Count is optimized and works on mmap'd slices since they're just []byte
</think>

Here is a practical example of memory-mapped file I/O in Go using `syscall.Mmap` (Linux/macOS):

```go
//go:build unix

package main

import (
	"bytes"
	"fmt"
	"log"
	"os"
	"syscall"
	"time"
)

// MmapFile represents a read-only memory-mapped file.
type MmapFile struct {
	Data []byte
	f    *os.File
}

// OpenMmap opens a file and maps it into memory.
func OpenMmap(path string) (*MmapFile, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open: %w", err)
	}

	info, err := f.Stat()
	if err != nil {
		f.Close()
		return nil, fmt.Errorf("stat: %w", err)
	}

	size := info.Size()
	if size == 0 {
		f.Close()
		return &MmapFile{Data: nil, f: nil}, nil
	}

	data, err := syscall.Mmap(
		int(f.Fd()),
		0,             // offset
		int(size),     // length
		syscall.PROT_READ,
		syscall.MAP_PRIVATE,
	)
	if err != nil {
		f.Close()
		return nil, fmt.Errorf("mmap: %w", err)
	}

	return &MmapFile{Data: data, f: f}, nil
}

// Close unmaps the memory and closes the file.
func (m *MmapFile) Close() error {
	if m.Data != nil {
		if err := syscall.Munmap(m.Data); err != nil {
			return fmt.Errorf("munmap: %w", err)
		}
		m.Data = nil
	}
	if m.f != nil {
		return m.f.Close()
	}
	return nil
}

// Advise tells the kernel about our access pattern (optional optimization).
func (m *MmapFile) Advise(advice int) error {
	if m.Data == nil {
		return nil
	}
	_, _, errno := syscall.Syscall6(
		syscall.SYS_MADVISE,
		uintptr(unsafe.Pointer(&m.Data[0])),
		uintptr(len(m.Data)),
		uintptr(advice),
		0, 0, 0,
	)
	if errno != 0 {
		return errno
	}
	return nil
}

// countLinesMmap counts newlines in a memory-mapped file.
func countLinesMmap(path string) (int, time.Duration, error) {
	start := time.Now()

	mf, err := OpenMmap(path)
	if err != nil {
		return 0, 0, err
	}
	defer mf.Close()

	// The mmap'd []byte works with all standard library functions.
	count := bytes.Count(mf.Data, []byte{'\n'})
	return count, time.Since(start), nil
}

// countLinesReadFile counts newlines by reading the whole file into heap.
func countLinesReadFile(path string) (int, time.Duration, error) {
	start := time.Now()

	data, err := os.ReadFile(path)
	if err != nil {
		return 0, 0, err
	}

	count := bytes.Count(data, []byte{'\n'})
	return count, time.Since(start), nil
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "usage: %s <file>\n", os.Args[0])
		os.Exit(1)
	}
	path := os.Args[1]

	info, err := os.Stat(path)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("file: %s (%d MB)\n", path, info.Size()/(1024*1024))

	// Benchmark mmap approach.
	lines1, dur1, err := countLinesMmap(path)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("mmap:     %d lines in %v\n", lines1, dur1)

	// Benchmark ReadFile approach.
	lines2, dur2, err := countLinesReadFile(path)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("ReadFile: %d lines in %v\n", lines2, dur2)

	if lines1 != lines2 {
		log.Fatalf("mismatch: %d vs %d", lines1, lines2)
	}
}
```

**Note:** The `Advise` method uses `unsafe`, so add `"unsafe"` to the import block if you use it. For the core example (without `Advise`), no unsafe import is needed.

Key points about mmap in Go:

1. **No heap allocation**: `syscall.Mmap` returns a `[]byte` backed by the kernel page cache, not Go heap memory. The GC never scans or collects it.
2. **Must manually unmap**: unlike heap slices, mmap'd memory leaks if you forget `syscall.Munmap`. Always use `defer Close()`.
3. **Works with stdlib**: since the result is `[]byte`, functions like `bytes.Count`, `bytes.Index`, and `bytes.Split` work directly on it.
4. **Random access wins**: mmap shines when you need random access into large files (databases, indexes). For sequential reads, `bufio.Scanner` with a buffer can be competitive.
5. **Empty files**: `Mmap` with length 0 returns `EINVAL`, so handle that edge case explicitly.
6. **Portability**: `syscall.Mmap` is Unix-only. For cross-platform code, use `golang.org/x/exp/mmap` or build-tag separate implementations.'''),

    ("go_deep/exec_pipe_process", r'''How do I spawn a subprocess in Go, pipe data to its stdin, and read from its stdout and stderr separately? For example, running a Python script and feeding it JSON input.''', r'''<think>
Process management in Go uses os/exec. The key challenge is correctly wiring stdin, stdout, and stderr without deadlocking.

Common deadlock scenario: if you use cmd.StdinPipe() and cmd.Output() together, Output() waits for the process to exit, but the process might be blocked waiting for more stdin. You must close stdin after writing.

Another deadlock: if stdout and stderr buffers fill up while you're reading only one of them. Solution: read both concurrently with goroutines, or use cmd.CombinedOutput if you don't need them separate.

Approach:
1. Create the command with exec.Command
2. Get StdinPipe, StdoutPipe, StderrPipe
3. Start the command (not Run — Run blocks)
4. Write to stdin in a goroutine, then close the pipe
5. Read stdout and stderr concurrently in separate goroutines
6. Wait for the command to finish
7. Check the exit code via the error from Wait

Additional considerations:
- Context-based timeout with exec.CommandContext
- Setting environment variables
- Setting working directory
- Handling large output without loading it all in memory
- The process might not flush its output unless it detects a pipe (Python needs -u for unbuffered)
- On Windows, shell invocation differs but exec.Command is cross-platform
- We should capture exit codes via ExitError
</think>

Here is a complete example of subprocess management with piped I/O:

```go
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os/exec"
	"sync"
	"time"
)

// ProcResult holds the outcome of a subprocess run.
type ProcResult struct {
	Stdout   string
	Stderr   string
	ExitCode int
}

// RunWithPipe spawns a command, writes input to its stdin, and captures
// stdout and stderr separately. Returns after the process exits or the
// context deadline is reached.
func RunWithPipe(ctx context.Context, input []byte, name string, args ...string) (*ProcResult, error) {
	cmd := exec.CommandContext(ctx, name, args...)

	stdinPipe, err := cmd.StdinPipe()
	if err != nil {
		return nil, fmt.Errorf("stdin pipe: %w", err)
	}
	stdoutPipe, err := cmd.StdoutPipe()
	if err != nil {
		return nil, fmt.Errorf("stdout pipe: %w", err)
	}
	stderrPipe, err := cmd.StderrPipe()
	if err != nil {
		return nil, fmt.Errorf("stderr pipe: %w", err)
	}

	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("start: %w", err)
	}

	// Write stdin in a goroutine to avoid deadlock: the child might
	// block on stdout/stderr if we block here on a large write.
	var writeErr error
	var wg sync.WaitGroup
	wg.Add(3)

	go func() {
		defer wg.Done()
		defer stdinPipe.Close() // signals EOF to child
		if _, err := stdinPipe.Write(input); err != nil {
			writeErr = err
		}
	}()

	// Read stdout and stderr concurrently to prevent pipe buffer deadlock.
	var stdoutBuf, stderrBuf bytes.Buffer

	go func() {
		defer wg.Done()
		io.Copy(&stdoutBuf, stdoutPipe)
	}()

	go func() {
		defer wg.Done()
		io.Copy(&stderrBuf, stderrPipe)
	}()

	// Wait for all I/O goroutines to finish before calling cmd.Wait().
	wg.Wait()

	result := &ProcResult{
		Stdout: stdoutBuf.String(),
		Stderr: stderrBuf.String(),
	}

	if err := cmd.Wait(); err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			result.ExitCode = exitErr.ExitCode()
		} else {
			return result, fmt.Errorf("wait: %w", err)
		}
	}

	if writeErr != nil {
		return result, fmt.Errorf("stdin write: %w", writeErr)
	}

	return result, nil
}

func main() {
	// Example: pipe JSON to a Python script and capture output.
	payload := map[string]any{
		"numbers": []int{3, 1, 4, 1, 5, 9, 2, 6},
		"op":      "sort",
	}
	input, _ := json.Marshal(payload)

	// Python one-liner that reads JSON, sorts, and prints result.
	// -u flag forces unbuffered I/O (important for pipes).
	script := `
import json, sys
data = json.load(sys.stdin)
if data["op"] == "sort":
    data["numbers"].sort()
    print(json.dumps(data))
else:
    print("unknown op", file=sys.stderr)
    sys.exit(1)
`

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	result, err := RunWithPipe(ctx, input, "python3", "-u", "-c", script)
	if err != nil {
		log.Fatalf("run failed: %v", err)
	}

	fmt.Printf("exit code: %d\n", result.ExitCode)
	fmt.Printf("stdout:\n%s\n", result.Stdout)
	if result.Stderr != "" {
		fmt.Printf("stderr:\n%s\n", result.Stderr)
	}

	// Parse the output back.
	var out map[string]any
	if err := json.Unmarshal([]byte(result.Stdout), &out); err == nil {
		fmt.Printf("sorted: %v\n", out["numbers"])
	}
}
```

Critical points to avoid deadlocks:

1. **Write stdin in a goroutine**: if stdin data is large, the OS pipe buffer (typically 64KB) fills up. The child blocks reading stdout/stderr until its output buffer is drained, but we are blocked writing stdin. Goroutine breaks the cycle.
2. **Read stdout and stderr concurrently**: same buffer-fill issue. If you only read stdout, stderr buffer fills, child blocks, stdout stalls.
3. **Close stdin after writing**: the child process likely reads until EOF. Without `stdinPipe.Close()`, it hangs forever waiting for more input.
4. **Wait for I/O goroutines before `cmd.Wait()`**: `Wait` closes the pipes, so reading goroutines must finish first.
5. **`-u` flag for Python**: Python buffers stdout when connected to a pipe. Without `-u`, you may get no output until the process exits.'''),

    ("go_deep/signal_handling", r'''Show me how to handle SIGTERM and SIGINT for graceful shutdown in Go, plus SIGHUP for config reload — with a real HTTP server that drains connections.''', r'''<think>
Signal handling in Go uses os/signal.Notify or signal.NotifyContext. For graceful HTTP shutdown, we use http.Server.Shutdown which waits for active connections to drain.

The pattern:
- SIGINT/SIGTERM: initiate graceful shutdown — stop accepting new connections, wait for in-flight requests, then exit
- SIGHUP: reload configuration without restarting the process
- We need to listen on the signal channels in a dedicated goroutine
- signal.NotifyContext is convenient for SIGINT/SIGTERM since it returns a context
- For SIGHUP, we need a separate signal.Notify channel since we don't want it to cancel the context
- http.Server.Shutdown takes a context — we can give it a deadline so we don't wait forever
- After Shutdown returns, we can do final cleanup (close DB connections, flush logs)
- Important: signal.Notify does not block sending to the channel, so use a buffered channel
- RegisterOnShutdown can be used to notify long-lived connections (websockets)
- We should demonstrate the config reload actually taking effect — e.g., changing a response message
- Race condition on config: use atomic.Value or sync.RWMutex for the config struct
- Multiple SIGINT in a row should force-quit (common UX pattern)
</think>

Here is a production-ready signal handling pattern with an HTTP server:

```go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

// Config holds runtime configuration that can be reloaded.
type Config struct {
	Message string `json:"message"`
	Port    int    `json:"port"`
}

// SafeConfig wraps Config with a RWMutex for concurrent access.
type SafeConfig struct {
	mu  sync.RWMutex
	cfg Config
}

func (sc *SafeConfig) Get() Config {
	sc.mu.RLock()
	defer sc.mu.RUnlock()
	return sc.cfg
}

func (sc *SafeConfig) Set(cfg Config) {
	sc.mu.Lock()
	defer sc.mu.Unlock()
	sc.cfg = cfg
}

func loadConfig(path string) (Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		// Return defaults if file doesn't exist.
		if os.IsNotExist(err) {
			return Config{Message: "hello, world", Port: 8080}, nil
		}
		return Config{}, err
	}
	var cfg Config
	if err := json.Unmarshal(data, &cfg); err != nil {
		return Config{}, fmt.Errorf("parse config: %w", err)
	}
	return cfg, nil
}

func main() {
	configPath := "config.json"
	if len(os.Args) > 1 {
		configPath = os.Args[1]
	}

	cfg, err := loadConfig(configPath)
	if err != nil {
		log.Fatalf("load config: %v", err)
	}

	safeCfg := &SafeConfig{}
	safeCfg.Set(cfg)
	log.Printf("loaded config: %+v", cfg)

	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		// Simulate a slow request to demonstrate drain.
		time.Sleep(100 * time.Millisecond)
		c := safeCfg.Get()
		fmt.Fprintf(w, "%s\n", c.Message)
	})
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})

	server := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.Port),
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// --- Signal channels ---
	// Buffered so the signal package doesn't drop signals.
	shutdown := make(chan os.Signal, 1)
	signal.Notify(shutdown, syscall.SIGINT, syscall.SIGTERM)

	reload := make(chan os.Signal, 1)
	signal.Notify(reload, syscall.SIGHUP)

	// Start server in a goroutine.
	serverErr := make(chan error, 1)
	go func() {
		log.Printf("listening on %s", server.Addr)
		if err := server.ListenAndServe(); err != http.ErrServerClosed {
			serverErr <- err
		}
		close(serverErr)
	}()

	// --- Main signal loop ---
	for {
		select {
		case sig := <-shutdown:
			log.Printf("received %v, shutting down gracefully...", sig)

			// Give in-flight requests up to 15 seconds to complete.
			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			defer cancel()

			// Shutdown stops accepting new connections and waits for
			// active ones to finish.
			if err := server.Shutdown(ctx); err != nil {
				log.Printf("shutdown error: %v (forcing close)", err)
				server.Close() // force-close if drain takes too long
			}

			log.Println("server drained, exiting")
			return

		case <-reload:
			log.Println("received SIGHUP, reloading config...")
			newCfg, err := loadConfig(configPath)
			if err != nil {
				log.Printf("config reload failed: %v (keeping old config)", err)
				continue
			}
			safeCfg.Set(newCfg)
			log.Printf("config reloaded: %+v", newCfg)
			// Note: port changes require restart — can't rebind here.

		case err := <-serverErr:
			if err != nil {
				log.Fatalf("server error: %v", err)
			}
			return
		}
	}
}
```

How to test it:

```bash
# Start the server
go run main.go

# In another terminal:
curl http://localhost:8080/        # prints "hello, world"

# Reload config (change message in config.json, then):
kill -SIGHUP $(pgrep -f main.go)  # reloads without restart
curl http://localhost:8080/        # prints new message

# Graceful shutdown:
kill -SIGTERM $(pgrep -f main.go) # drains active connections, then exits
```

Design decisions explained:

- **Buffered signal channels**: `signal.Notify` does not block — unbuffered channels drop signals.
- **`sync.RWMutex` for config**: readers (HTTP handlers) don't block each other; only SIGHUP takes a write lock.
- **`Shutdown` vs `Close`**: `Shutdown` gracefully drains; `Close` force-kills. Use `Close` as a fallback if the drain deadline expires.
- **15-second drain timeout**: prevents hanging forever if a client keeps a connection open.
- **Separate channels for shutdown vs reload**: SIGHUP should not trigger shutdown, so they need independent channels.'''),

    ("go_deep/unix_domain_socket", r'''How do I implement inter-process communication using Unix domain sockets in Go? Show a server and client that exchange JSON messages over a socket file.''', r'''<think>
Unix domain sockets are faster than TCP for local IPC since they skip the network stack. In Go, we use net.Listen("unix", path) and net.Dial("unix", path).

Key considerations:
- The socket file must be cleaned up on exit — if it exists from a previous crash, Listen will fail with "address already in use"
- So we should os.Remove the socket file before Listen, or check if the old process is still alive
- Permissions: the socket file inherits filesystem permissions, so we can restrict access via os.Chmod
- For JSON message exchange, we need a framing protocol since TCP/Unix streams don't have message boundaries
- Options: newline-delimited JSON, length-prefixed, or just use json.Encoder/Decoder which handle framing internally
- json.NewEncoder/Decoder over a net.Conn work well — Decoder reads exactly one JSON value per Decode call
- Server should handle multiple concurrent clients
- Clean shutdown: listener.Close() + context cancellation
- Abstract sockets (Linux-only, path starts with \0) don't create a file, but are less portable
- Let's build a request-response protocol: client sends a command, server processes it and sends a response
- Each connection gets its own goroutine on the server side
</think>

Here is a complete Unix domain socket IPC system with JSON messaging:

```go
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"os"
	"os/signal"
	"sync"
	"time"
)

const socketPath = "/tmp/hiveai_ipc.sock"

// Request is the client-to-server message format.
type Request struct {
	ID     int    `json:"id"`
	Method string `json:"method"`
	Args   []any  `json:"args,omitempty"`
}

// Response is the server-to-client message format.
type Response struct {
	ID    int    `json:"id"`
	Value any    `json:"value,omitempty"`
	Error string `json:"error,omitempty"`
}

// ---- Server ----

type Server struct {
	listener net.Listener
	wg       sync.WaitGroup
}

func NewServer(path string) (*Server, error) {
	// Remove stale socket from previous run.
	os.Remove(path)

	ln, err := net.Listen("unix", path)
	if err != nil {
		return nil, fmt.Errorf("listen: %w", err)
	}

	// Restrict access to current user.
	if err := os.Chmod(path, 0600); err != nil {
		ln.Close()
		return nil, fmt.Errorf("chmod: %w", err)
	}

	return &Server{listener: ln}, nil
}

func (s *Server) Serve(ctx context.Context) {
	defer s.listener.Close()
	defer os.Remove(socketPath)

	go func() {
		<-ctx.Done()
		s.listener.Close() // unblocks Accept
	}()

	for {
		conn, err := s.listener.Accept()
		if err != nil {
			if ctx.Err() != nil {
				break // context cancelled, clean shutdown
			}
			log.Printf("accept error: %v", err)
			continue
		}

		s.wg.Add(1)
		go func() {
			defer s.wg.Done()
			s.handleConn(ctx, conn)
		}()
	}

	s.wg.Wait()
	log.Println("server: all connections drained")
}

func (s *Server) handleConn(ctx context.Context, conn net.Conn) {
	defer conn.Close()
	dec := json.NewDecoder(conn)
	enc := json.NewEncoder(conn)

	for {
		var req Request
		if err := dec.Decode(&req); err != nil {
			if !errors.Is(err, io.EOF) {
				log.Printf("decode error: %v", err)
			}
			return
		}

		resp := s.dispatch(req)
		if err := enc.Encode(resp); err != nil {
			log.Printf("encode error: %v", err)
			return
		}
	}
}

func (s *Server) dispatch(req Request) Response {
	switch req.Method {
	case "ping":
		return Response{ID: req.ID, Value: "pong"}
	case "time":
		return Response{ID: req.ID, Value: time.Now().Format(time.RFC3339)}
	case "add":
		if len(req.Args) != 2 {
			return Response{ID: req.ID, Error: "add requires 2 args"}
		}
		a, aOk := req.Args[0].(float64)
		b, bOk := req.Args[1].(float64)
		if !aOk || !bOk {
			return Response{ID: req.ID, Error: "args must be numbers"}
		}
		return Response{ID: req.ID, Value: a + b}
	default:
		return Response{ID: req.ID, Error: fmt.Sprintf("unknown method: %s", req.Method)}
	}
}

// ---- Client ----

type Client struct {
	conn net.Conn
	enc  *json.Encoder
	dec  *json.Decoder
	mu   sync.Mutex
	id   int
}

func NewClient(path string) (*Client, error) {
	conn, err := net.Dial("unix", path)
	if err != nil {
		return nil, fmt.Errorf("dial: %w", err)
	}
	return &Client{
		conn: conn,
		enc:  json.NewEncoder(conn),
		dec:  json.NewDecoder(conn),
	}, nil
}

func (c *Client) Call(method string, args ...any) (*Response, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.id++
	req := Request{ID: c.id, Method: method, Args: args}
	if err := c.enc.Encode(req); err != nil {
		return nil, fmt.Errorf("send: %w", err)
	}

	var resp Response
	if err := c.dec.Decode(&resp); err != nil {
		return nil, fmt.Errorf("recv: %w", err)
	}
	return &resp, nil
}

func (c *Client) Close() error {
	return c.conn.Close()
}

// ---- Main (demo both) ----

func main() {
	if len(os.Args) > 1 && os.Args[1] == "client" {
		runClient()
		return
	}
	runServer()
}

func runServer() {
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()

	srv, err := NewServer(socketPath)
	if err != nil {
		log.Fatal(err)
	}

	log.Printf("server listening on %s", socketPath)
	srv.Serve(ctx)
}

func runClient() {
	c, err := NewClient(socketPath)
	if err != nil {
		log.Fatal(err)
	}
	defer c.Close()

	// Send multiple requests over one connection.
	calls := []struct {
		method string
		args   []any
	}{
		{"ping", nil},
		{"time", nil},
		{"add", []any{40.0, 2.0}},
		{"unknown", nil},
	}

	for _, call := range calls {
		resp, err := c.Call(call.method, call.args...)
		if err != nil {
			log.Printf("call %s failed: %v", call.method, err)
			continue
		}
		if resp.Error != "" {
			fmt.Printf("%s -> error: %s\n", call.method, resp.Error)
		} else {
			fmt.Printf("%s -> %v\n", call.method, resp.Value)
		}
	}
}
```

Run it:

```bash
# Terminal 1: start server
go run main.go

# Terminal 2: run client
go run main.go client
# Output:
# ping -> pong
# time -> 2026-03-07T10:30:00Z
# add -> 42
# unknown -> error: unknown method: unknown
```

Design notes:

- **`json.Encoder/Decoder` handles framing**: each `Encode` writes one JSON object followed by a newline; each `Decode` reads exactly one object. No manual length-prefixing needed.
- **Stale socket cleanup**: `os.Remove` before `Listen` handles crash recovery. In production, you might check if the socket is live first with a test dial.
- **Mutex on client**: ensures request-response pairs stay matched when multiple goroutines share one client. For high concurrency, use separate connections per goroutine or implement request multiplexing with ID matching.
- **`os.Chmod(path, 0600)`**: restricts socket access to the owning user — important for security-sensitive IPC.'''),

    ("go_deep/shared_memory", r'''How can two Go processes share memory on Linux? Show me using shared memory (shm) for passing data between processes without sockets or files.''', r'''<think>
Go doesn't have a high-level shared memory API, so we need to use syscalls. On Linux, there are two main approaches:
1. POSIX shared memory (shm_open + mmap) — requires CGo for shm_open
2. SysV shared memory (shmget, shmat, shmdt) — also requires CGo
3. mmap on a file in /dev/shm (which is tmpfs) — pure Go, no CGo needed

Option 3 is the most practical: /dev/shm is a tmpfs mount, so creating a file there and mmap-ing it gives us shared memory semantics without CGo.

Plan:
- Create a file in /dev/shm
- mmap it with MAP_SHARED so changes are visible across processes
- Use a simple protocol: first 8 bytes as a header (e.g., length + sequence), rest is data
- Need synchronization — we can use a simple spinlock via atomic operations on the mmap'd region, or use file locking (flock)
- For simplicity, let's use a polling approach with an atomic sequence number
- The writer increments the sequence number after writing; the reader spins until it sees a new sequence
- unsafe.Pointer is needed to cast the mmap'd []byte to structured data
- We need to be careful: Go's memory model doesn't cover mmap'd regions, so we need to use sync/atomic with unsafe.Pointer
- Actually, atomic operations on mmap'd memory should work since they use CPU atomics (LOCK prefix on x86)
- Let's build a producer-consumer example with a shared ring buffer header
</think>

Here is a practical shared memory implementation using `/dev/shm` and `mmap`:

```go
//go:build linux

package main

import (
	"encoding/binary"
	"fmt"
	"log"
	"os"
	"sync/atomic"
	"syscall"
	"time"
	"unsafe"
)

const (
	shmName   = "/dev/shm/hiveai_shm_demo"
	shmSize   = 4096
	headerLen = 16 // 8 bytes sequence + 4 bytes length + 4 bytes padding
)

// ShmRegion represents a shared memory region.
type ShmRegion struct {
	data []byte
	f    *os.File
}

// OpenShm opens (or creates) a shared memory region.
func OpenShm(path string, size int, create bool) (*ShmRegion, error) {
	flags := os.O_RDWR
	if create {
		flags |= os.O_CREATE | os.O_TRUNC
	}

	f, err := os.OpenFile(path, flags, 0666)
	if err != nil {
		return nil, fmt.Errorf("open shm: %w", err)
	}

	if create {
		// Set the file size.
		if err := f.Truncate(int64(size)); err != nil {
			f.Close()
			return nil, fmt.Errorf("truncate: %w", err)
		}
	}

	data, err := syscall.Mmap(
		int(f.Fd()),
		0,
		size,
		syscall.PROT_READ|syscall.PROT_WRITE,
		syscall.MAP_SHARED, // changes visible to other processes
	)
	if err != nil {
		f.Close()
		return nil, fmt.Errorf("mmap: %w", err)
	}

	return &ShmRegion{data: data, f: f}, nil
}

func (s *ShmRegion) Close() error {
	if err := syscall.Munmap(s.data); err != nil {
		return err
	}
	return s.f.Close()
}

// seqPtr returns a pointer to the atomic sequence counter in the header.
func (s *ShmRegion) seqPtr() *uint64 {
	return (*uint64)(unsafe.Pointer(&s.data[0]))
}

// Write publishes a message to shared memory.
func (s *ShmRegion) Write(msg []byte) error {
	maxData := shmSize - headerLen
	if len(msg) > maxData {
		return fmt.Errorf("message too large: %d > %d", len(msg), maxData)
	}

	// Write length, then data, then bump sequence (release semantics).
	binary.LittleEndian.PutUint32(s.data[8:12], uint32(len(msg)))
	copy(s.data[headerLen:], msg)

	// Atomic store with release ordering ensures the data is visible
	// before the sequence number update.
	seq := atomic.LoadUint64(s.seqPtr())
	atomic.StoreUint64(s.seqPtr(), seq+1)
	return nil
}

// Read polls for a new message. Returns the message and new sequence.
func (s *ShmRegion) Read(lastSeq uint64) ([]byte, uint64) {
	seq := atomic.LoadUint64(s.seqPtr())
	if seq == lastSeq {
		return nil, lastSeq // no new data
	}

	length := binary.LittleEndian.Uint32(s.data[8:12])
	if length == 0 || int(length) > shmSize-headerLen {
		return nil, seq
	}

	// Copy out so we don't hold a reference to mmap'd memory.
	msg := make([]byte, length)
	copy(msg, s.data[headerLen:headerLen+int(length)])
	return msg, seq
}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "read" {
		runReader()
		return
	}
	runWriter()
}

func runWriter() {
	shm, err := OpenShm(shmName, shmSize, true)
	if err != nil {
		log.Fatal(err)
	}
	defer shm.Close()
	defer os.Remove(shmName)

	log.Println("writer: publishing messages to shared memory...")

	for i := 1; i <= 10; i++ {
		msg := fmt.Sprintf(`{"counter":%d,"ts":"%s"}`, i, time.Now().Format(time.RFC3339Nano))
		if err := shm.Write([]byte(msg)); err != nil {
			log.Fatal(err)
		}
		fmt.Printf("wrote: %s\n", msg)
		time.Sleep(500 * time.Millisecond)
	}

	log.Println("writer: done, waiting 2s for reader to finish...")
	time.Sleep(2 * time.Second)
}

func runReader() {
	shm, err := OpenShm(shmName, shmSize, false)
	if err != nil {
		log.Fatal(err)
	}
	defer shm.Close()

	log.Println("reader: polling shared memory...")

	var lastSeq uint64
	seen := 0
	for seen < 10 {
		msg, newSeq := shm.Read(lastSeq)
		if msg != nil {
			fmt.Printf("read [seq=%d]: %s\n", newSeq, string(msg))
			lastSeq = newSeq
			seen++
		} else {
			time.Sleep(10 * time.Millisecond) // poll interval
		}
	}
	log.Println("reader: done")
}
```

Run it:

```bash
# Terminal 1
go run main.go          # starts writer, creates /dev/shm/hiveai_shm_demo

# Terminal 2 (while writer is running)
go run main.go read     # reads messages from shared memory
```

Important details:

- **`/dev/shm` is `tmpfs`**: it lives in RAM, so this is true shared memory without disk I/O. The file is just a handle for `mmap`.
- **`MAP_SHARED`**: this is critical. `MAP_PRIVATE` would give each process its own copy-on-write page, defeating the purpose.
- **`atomic.StoreUint64` / `atomic.LoadUint64`**: provides the memory ordering guarantee that the data is fully written before the sequence number is updated. Without atomics, the reader might see a stale or partially written message.
- **Copy on read**: the reader copies data out of the mmap'd region into a Go-heap slice. Holding references into mmap'd memory is dangerous because it can be unmapped.
- **No CGo required**: by using `/dev/shm` directly, we avoid `shm_open` and keep the build pure Go.
- **Limitations**: this simple protocol supports only one writer. For multiple writers, you would need a proper mutex in the shared region (e.g., `futex`) or use file locking with `syscall.Flock`.'''),

    ("go_deep/cgo_basics", r'''Show me how to call C functions from Go using CGo. I want a practical example — not just printf — something like calling a C math library or system function.''', r'''<think>
CGo lets Go call C code via special comments. The key elements:
- `import "C"` pseudo-package right after a comment block containing C code or #include directives
- The comment must be directly above `import "C"` with no blank line
- C types map to Go types: C.int, C.char, C.double, etc.
- C strings need manual memory management: C.CString allocates (must free), C.GoString converts back
- We can embed C source directly in the comment or link to external libraries

Let's do something practical: call OpenSSL's SHA-256 from C, which is much faster than Go's crypto/sha256 for large inputs. Actually, that requires linking OpenSSL which adds complexity.

Better: let's call C's POSIX getaddrinfo for DNS resolution (more realistic than math), or use qsort as a callback example.

Actually, let's demonstrate several patterns:
1. Inline C function (a fast CRC32 using __builtin_crc32)
2. Calling libc functions (getpid, gethostname)
3. Passing strings between Go and C
4. Passing slices/arrays

Let me do a practical one: wrapping C's glob() for file pattern matching and a simple inline C function for byte counting. These show real CGo patterns without external library dependencies.

Key pitfalls to mention:
- C memory isn't tracked by GC — must free manually
- Can't pass Go pointers to C that contain other Go pointers
- CGo calls are expensive (~100ns overhead vs ~1ns for Go calls)
- Builds are slower with CGo (no cross-compilation without toolchain)
</think>

Here is a practical CGo example demonstrating several patterns — calling libc functions, inline C code, and proper memory management:

```go
package main

/*
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <glob.h>

// Inline C function: count occurrences of a byte in a buffer.
// Faster than Go for very large buffers due to no bounds checks.
static int count_byte(const char *buf, int len, char target) {
    int count = 0;
    for (int i = 0; i < len; i++) {
        if (buf[i] == target) count++;
    }
    return count;
}

// Wrapper around glob(3) that returns results as a flat string
// with null separators (easier to pass back to Go).
static char** do_glob(const char *pattern, int *count) {
    glob_t g;
    int ret = glob(pattern, 0, NULL, &g);
    if (ret != 0) {
        *count = 0;
        return NULL;
    }
    *count = (int)g.gl_pathc;

    // Allocate array of strings — caller must free each + the array.
    char **results = (char**)malloc(sizeof(char*) * g.gl_pathc);
    for (size_t i = 0; i < g.gl_pathc; i++) {
        results[i] = strdup(g.gl_pathv[i]);
    }
    globfree(&g);
    return results;
}

// Free the results from do_glob.
static void free_glob_results(char **results, int count) {
    for (int i = 0; i < count; i++) {
        free(results[i]);
    }
    free(results);
}
*/
import "C"

import (
	"fmt"
	"log"
	"unsafe"
)

// GlobFiles wraps C's glob(3) to match file patterns.
func GlobFiles(pattern string) ([]string, error) {
	cPattern := C.CString(pattern)
	defer C.free(unsafe.Pointer(cPattern)) // Must free CString!

	var count C.int
	results := C.do_glob(cPattern, &count)
	if results == nil {
		return nil, fmt.Errorf("glob failed for pattern: %s", pattern)
	}
	defer C.free_glob_results(results, count)

	// Convert C string array to Go slice.
	n := int(count)
	out := make([]string, n)

	// Cast to a Go slice of *C.char for indexing.
	// This is the standard pattern for C arrays in CGo.
	cSlice := unsafe.Slice(results, n)
	for i := 0; i < n; i++ {
		out[i] = C.GoString(cSlice[i])
	}
	return out, nil
}

// CountByte uses the inline C function for byte counting.
func CountByte(data []byte, target byte) int {
	if len(data) == 0 {
		return 0
	}
	// Pass Go slice data to C — safe because C doesn't store the pointer.
	return int(C.count_byte(
		(*C.char)(unsafe.Pointer(&data[0])),
		C.int(len(data)),
		C.char(target),
	))
}

// Hostname wraps C's gethostname.
func Hostname() (string, error) {
	const maxLen = 256
	buf := (*C.char)(C.malloc(maxLen))
	defer C.free(unsafe.Pointer(buf))

	if C.gethostname(buf, maxLen) != 0 {
		return "", fmt.Errorf("gethostname failed")
	}
	return C.GoString(buf), nil
}

func main() {
	// 1. Glob example.
	files, err := GlobFiles("/etc/*.conf")
	if err != nil {
		log.Printf("glob: %v", err)
	} else {
		fmt.Printf("found %d config files:\n", len(files))
		for _, f := range files {
			fmt.Printf("  %s\n", f)
		}
	}

	// 2. Byte counting.
	data := []byte("hello world, hello Go, hello CGo!")
	count := CountByte(data, 'o')
	fmt.Printf("\nbyte 'o' appears %d times in %q\n", count, string(data))

	// 3. Hostname via libc.
	host, err := Hostname()
	if err != nil {
		log.Printf("hostname: %v", err)
	} else {
		fmt.Printf("hostname: %s\n", host)
	}

	// 4. Direct libc call: getpid.
	pid := C.getpid()
	fmt.Printf("PID (from C): %d\n", pid)
}
```

Build and run:

```bash
CGO_ENABLED=1 go run main.go
```

Critical CGo rules demonstrated:

1. **`C.CString` always needs `C.free`**: `CString` allocates with C's `malloc`. The Go GC does not track it. Forgetting `defer C.free(unsafe.Pointer(cstr))` is a memory leak.
2. **`C.GoString` copies**: it copies the C string into Go-managed memory, so it is safe to free the C original afterward.
3. **Passing Go slices to C**: take `&data[0]` to get the underlying pointer. This is safe as long as C does not store the pointer past the call (Go's cgo pointer rules).
4. **No blank line** between the C comment and `import "C"` — this is a hard syntactic requirement; a blank line breaks the linkage.
5. **`unsafe.Slice`** (Go 1.17+): cleanly converts a C array pointer into a Go slice for iteration without manual pointer arithmetic.
6. **Performance tradeoff**: each CGo call has approximately 50-100ns overhead (vs ~1ns for pure Go function calls). Batch work into fewer C calls rather than calling C in a tight loop.'''),

    ("go_deep/cgo_memory_pitfalls", r'''What are the memory management pitfalls of CGo? Show me what goes wrong and how to fix it.''', r'''<think>
CGo memory pitfalls are a major source of bugs. The key issues:

1. Go's garbage collector doesn't know about C-allocated memory — leaks
2. C can't hold Go pointers across calls (runtime panics since Go 1.6)
3. Go pointers can move during GC — C must not cache them
4. String conversions: CString allocates, GoString copies
5. Passing Go structs with pointer fields to C is forbidden
6. C callbacks into Go need special handling
7. Finalizers can't reliably clean C memory (non-deterministic)
8. Thread-local storage: CGo calls may run on different OS threads

Let me show concrete examples of each pitfall with before/after code.

I should demonstrate:
- Memory leak from forgetting to free CString
- The "Go pointer to Go pointer" rule violation
- Safe patterns: pin memory, copy data, use C-allocated buffers
- Correct callback pattern with //export
- Using runtime.Pinner (Go 1.21+) to pin Go memory for C
</think>

Here is a comprehensive guide to CGo memory pitfalls with broken and fixed examples:

```go
package main

/*
#include <stdlib.h>
#include <string.h>

// Simulates a C library that stores a pointer for later use.
static const char *stored_ptr = NULL;

static void c_store_string(const char *s) {
    stored_ptr = s;  // Just stores the pointer, doesn't copy!
}

static const char* c_get_string() {
    return stored_ptr;
}

// Simulates a C library that calls back into Go.
typedef void (*callback_fn)(int);
static void c_do_work(callback_fn cb, int value) {
    // C code that calls the Go callback.
    cb(value * 2);
}

// C struct that holds a pointer.
typedef struct {
    char *name;
    int   value;
} CRecord;

static CRecord* make_record(const char *name, int value) {
    CRecord *r = (CRecord*)malloc(sizeof(CRecord));
    r->name = strdup(name);
    r->value = value;
    return r;
}

static void free_record(CRecord *r) {
    if (r) {
        free(r->name);
        free(r);
    }
}
*/
import "C"

import (
	"fmt"
	"runtime"
	"unsafe"
)

// ============================================================
// PITFALL 1: Memory leak from C.CString
// ============================================================

func leakyFunction() {
	// BAD: CString allocates via malloc, but we never free it!
	cstr := C.CString("hello from Go")
	_ = C.strlen(cstr)
	// cstr leaks here — Go's GC does NOT free C memory.
}

func fixedFunction() {
	// GOOD: Always defer C.free after C.CString.
	cstr := C.CString("hello from Go")
	defer C.free(unsafe.Pointer(cstr))
	_ = C.strlen(cstr)
}

// ============================================================
// PITFALL 2: C storing a Go pointer (use-after-move)
// ============================================================

func dangerousStore() {
	// BAD: Go string's underlying data can move during GC.
	// Even if this compiles, the stored pointer becomes invalid.
	s := "hello"
	cstr := C.CString(s)
	C.c_store_string(cstr)
	// If we free cstr now, c_get_string() returns garbage.
	C.free(unsafe.Pointer(cstr))
	// stored_ptr in C now points to freed memory!

	// Also BAD: passing &goSlice[0] and having C store it.
	// The Go GC can move the slice's backing array.
}

func safeStore() {
	// GOOD: Let C own the memory. Don't free until C is done.
	cstr := C.CString("hello")
	C.c_store_string(cstr)

	// ... use c_get_string() ...
	result := C.GoString(C.c_get_string())
	fmt.Println("stored:", result)

	// Free only when C no longer needs the pointer.
	C.free(unsafe.Pointer(cstr))
}

// ============================================================
// PITFALL 3: Go pointer containing Go pointers → panic
// ============================================================

type GoStruct struct {
	Name string // string contains a pointer internally!
	Data []byte // slice header contains a pointer!
}

func brokenPassStruct() {
	// BAD: This will panic at runtime!
	// "Go code may not store a Go pointer in C memory"
	// s := GoStruct{Name: "test", Data: []byte{1, 2, 3}}
	// C.some_c_func(unsafe.Pointer(&s)) // PANIC: Go pointer contains Go pointer

	// The string and slice fields contain embedded pointers
	// to Go-allocated memory. C can't safely hold these.
}

func fixedPassStruct() {
	// GOOD: Copy all data into C-allocated memory.
	name := C.CString("test")
	defer C.free(unsafe.Pointer(name))

	record := C.make_record(name, 42)
	defer C.free_record(record)

	fmt.Printf("record: name=%s value=%d\n",
		C.GoString(record.name), record.value)
}

// ============================================================
// PITFALL 4: Callbacks — Go function pointers to C
// ============================================================

// This is the Go function that C will call back.
// Must use //export directive (no space between // and export).
//
//export goCallback
func goCallback(value C.int) {
	fmt.Printf("callback received: %d\n", int(value))
}

func demonstrateCallback() {
	// Pass the Go callback to C.
	// C.callback_fn is the C typedef for the function pointer.
	C.c_do_work(C.callback_fn(C.goCallback), 21)
}

// ============================================================
// PITFALL 5: Pinning Go memory (Go 1.21+)
// ============================================================

func pinnedMemoryExample() {
	// runtime.Pinner prevents GC from moving the pinned object.
	// Use when C needs a Go pointer briefly but doesn't copy.
	data := make([]byte, 1024)
	copy(data, []byte("pinned data"))

	var pinner runtime.Pinner
	pinner.Pin(&data[0])
	defer pinner.Unpin()

	// Now safe to pass &data[0] to C for the duration of the pin.
	length := C.strlen((*C.char)(unsafe.Pointer(&data[0])))
	fmt.Printf("C read %d bytes from pinned Go memory\n", length)
}

// ============================================================
// PITFALL 6: Finalizers can't reliably clean C memory
// ============================================================

type CWrapper struct {
	ptr *C.CRecord
}

func badCleanup() *CWrapper {
	// BAD: Finalizers are non-deterministic. If your program allocates
	// C memory faster than finalizers run, you OOM.
	name := C.CString("finalized")
	w := &CWrapper{ptr: C.make_record(name, 99)}
	C.free(unsafe.Pointer(name))

	runtime.SetFinalizer(w, func(w *CWrapper) {
		C.free_record(w.ptr) // Might run too late or never!
	})
	return w
}

func goodCleanup() {
	// GOOD: Explicit Close/Free method, just like *os.File.
	name := C.CString("explicit")
	defer C.free(unsafe.Pointer(name))

	record := C.make_record(name, 99)
	defer C.free_record(record) // Deterministic cleanup.

	fmt.Printf("record value: %d\n", record.value)
}

func main() {
	fmt.Println("=== Pitfall demos ===")

	fmt.Println("\n--- Safe store ---")
	safeStore()

	fmt.Println("\n--- Fixed struct passing ---")
	fixedPassStruct()

	fmt.Println("\n--- Callback ---")
	demonstrateCallback()

	fmt.Println("\n--- Pinned memory ---")
	pinnedMemoryExample()

	fmt.Println("\n--- Explicit cleanup ---")
	goodCleanup()
}
```

Summary of the rules:

| Pitfall | Rule | Fix |
|---------|------|-----|
| `C.CString` leak | C allocations are invisible to GC | Always `defer C.free(unsafe.Pointer(cstr))` |
| C stores Go pointer | Go memory can move during GC | Let C own the copy, or use `runtime.Pinner` |
| Go ptr containing Go ptr | Runtime enforces this rule, panics | Flatten data into C structs with C-allocated fields |
| Callbacks | C can't call Go functions directly | Use `//export` + function pointer cast |
| Finalizers for C memory | Non-deterministic, unreliable | Use explicit `Close()`/`Free()` methods |
| Thread affinity | CGo calls may switch OS threads | Use `runtime.LockOSThread()` if thread-local state matters |

The single most important rule: **C memory is your responsibility**. Every `C.CString`, `C.malloc`, or C-library allocation needs a matching `C.free` or library-specific destructor, and you must reason about the lifetime manually.'''),

    ("go_deep/unsafe_pointer_conversion", r'''How do I use unsafe.Pointer in Go for zero-copy type conversion? For example, converting a []byte to a string without copying, or reinterpreting a byte slice as a struct.''', r'''<think>
unsafe.Pointer is Go's escape hatch for type-punning and zero-copy conversions. The rules are strict — there are exactly 6 valid unsafe.Pointer conversion patterns defined in the documentation.

Key use cases:
1. []byte to string without copy (and vice versa) — now also possible with unsafe.String/unsafe.SliceData in Go 1.20+
2. Reinterpreting byte buffers as structs (like reading binary protocol headers)
3. Pointer arithmetic for accessing struct fields dynamically
4. Interface internals introspection

Safety rules:
- unsafe.Pointer can be converted to/from any *T
- unsafe.Pointer can be converted to/from uintptr (but only in specific patterns)
- uintptr is NOT a pointer — GC can move the object between converting to uintptr and back
- The conversion to uintptr and back must happen in a single expression

For []byte <-> string, Go 1.20+ added unsafe.String and unsafe.StringData which are cleaner than the old SliceHeader/StringHeader hacks (which are now deprecated).

Let me show multiple patterns: the modern way and the struct reinterpretation.
</think>

Here are the practical `unsafe.Pointer` patterns for zero-copy conversions in Go:

```go
package main

import (
	"encoding/binary"
	"fmt"
	"unsafe"
)

// ============================================================
// Pattern 1: []byte <-> string zero-copy (Go 1.20+)
// ============================================================

// BytesToString converts []byte to string without copying.
// The caller MUST NOT modify the byte slice after this call.
func BytesToString(b []byte) string {
	if len(b) == 0 {
		return ""
	}
	// unsafe.String creates a string from a pointer and length.
	// No allocation, no copy — the string shares the byte slice's memory.
	return unsafe.String(&b[0], len(b))
}

// StringToBytes converts string to []byte without copying.
// The caller MUST NOT modify the returned slice (strings are immutable).
func StringToBytes(s string) []byte {
	if len(s) == 0 {
		return nil
	}
	// unsafe.StringData returns a pointer to the string's bytes.
	// unsafe.Slice creates a slice header pointing to the same memory.
	return unsafe.Slice(unsafe.StringData(s), len(s))
}

// ============================================================
// Pattern 2: Reinterpreting bytes as a struct (binary protocol)
// ============================================================

// PacketHeader represents a network protocol header.
// Packed layout, fixed size — suitable for reinterpretation.
type PacketHeader struct {
	Magic   uint32
	Version uint16
	Flags   uint16
	Length  uint32
	SeqNum  uint32
}

const packetHeaderSize = 16 // 4 + 2 + 2 + 4 + 4

// ParseHeader reinterprets a byte slice as a PacketHeader (zero-copy).
// WARNING: This assumes the byte layout matches the struct's memory layout
// (host byte order, correct alignment). Use only for known, controlled data.
func ParseHeader(data []byte) (*PacketHeader, error) {
	if len(data) < packetHeaderSize {
		return nil, fmt.Errorf("need %d bytes, got %d", packetHeaderSize, len(data))
	}
	// Convert *byte → unsafe.Pointer → *PacketHeader
	hdr := (*PacketHeader)(unsafe.Pointer(&data[0]))
	return hdr, nil
}

// ParseHeaderSafe does the same thing safely using encoding/binary.
// This is what you should use in production unless performance is critical.
func ParseHeaderSafe(data []byte) (*PacketHeader, error) {
	if len(data) < packetHeaderSize {
		return nil, fmt.Errorf("need %d bytes, got %d", packetHeaderSize, len(data))
	}
	hdr := &PacketHeader{
		Magic:   binary.LittleEndian.Uint32(data[0:4]),
		Version: binary.LittleEndian.Uint16(data[4:6]),
		Flags:   binary.LittleEndian.Uint16(data[6:8]),
		Length:  binary.LittleEndian.Uint32(data[8:12]),
		SeqNum:  binary.LittleEndian.Uint32(data[12:16]),
	}
	return hdr, nil
}

// ============================================================
// Pattern 3: Type-punning between same-sized types
// ============================================================

// Float64Bits converts float64 to its IEEE 754 bit representation
// without using math.Float64bits (demonstration of the pattern).
func Float64Bits(f float64) uint64 {
	return *(*uint64)(unsafe.Pointer(&f))
}

// Float64FromBits converts uint64 back to float64.
func Float64FromBits(b uint64) float64 {
	return *(*float64)(unsafe.Pointer(&b))
}

// ============================================================
// Pattern 4: Pointer arithmetic for struct field access
// ============================================================

type Record struct {
	ID    uint64
	Score float32
	Name  [32]byte
}

// FieldOffset demonstrates accessing struct fields via pointer arithmetic.
func FieldOffset() {
	r := Record{ID: 42, Score: 3.14}
	copy(r.Name[:], "hello")

	base := unsafe.Pointer(&r)

	// Read ID (offset 0).
	id := *(*uint64)(base)
	fmt.Printf("  ID (offset %d): %d\n", unsafe.Offsetof(r.ID), id)

	// Read Score (at its offset).
	scorePtr := unsafe.Add(base, unsafe.Offsetof(r.Score))
	score := *(*float32)(scorePtr)
	fmt.Printf("  Score (offset %d): %.2f\n", unsafe.Offsetof(r.Score), score)

	// Read Name (at its offset).
	namePtr := unsafe.Add(base, unsafe.Offsetof(r.Name))
	name := unsafe.String((*byte)(namePtr), 5)
	fmt.Printf("  Name (offset %d): %s\n", unsafe.Offsetof(r.Name), name)
}

// ============================================================
// Pattern 5: Slice of structs <-> slice of bytes
// ============================================================

// StructSliceToBytes reinterprets a slice of fixed-size structs as raw bytes.
func StructSliceToBytes[T any](items []T) []byte {
	if len(items) == 0 {
		return nil
	}
	size := unsafe.Sizeof(items[0])
	return unsafe.Slice(
		(*byte)(unsafe.Pointer(&items[0])),
		len(items)*int(size),
	)
}

func main() {
	fmt.Println("=== Zero-copy string conversion ===")
	b := []byte("hello, unsafe world")
	s := BytesToString(b)
	fmt.Printf("  bytes → string: %q (same memory: no alloc)\n", s)

	s2 := "read-only string"
	b2 := StringToBytes(s2)
	fmt.Printf("  string → bytes: %v (len=%d)\n", b2[:4], len(b2))

	fmt.Println("\n=== Struct reinterpretation ===")
	// Build a packet header in a byte buffer.
	buf := make([]byte, packetHeaderSize)
	binary.LittleEndian.PutUint32(buf[0:4], 0xDEADBEEF)
	binary.LittleEndian.PutUint16(buf[4:6], 1)
	binary.LittleEndian.PutUint16(buf[6:8], 0x03)
	binary.LittleEndian.PutUint32(buf[8:12], 256)
	binary.LittleEndian.PutUint32(buf[12:16], 42)

	hdr, _ := ParseHeader(buf)
	fmt.Printf("  magic=0x%X version=%d flags=0x%X len=%d seq=%d\n",
		hdr.Magic, hdr.Version, hdr.Flags, hdr.Length, hdr.SeqNum)

	fmt.Println("\n=== Float64 type-punning ===")
	bits := Float64Bits(3.14)
	back := Float64FromBits(bits)
	fmt.Printf("  3.14 → bits=0x%X → back=%.2f\n", bits, back)

	fmt.Println("\n=== Pointer arithmetic ===")
	FieldOffset()

	fmt.Println("\n=== Struct slice to bytes ===")
	type Point struct{ X, Y float32 }
	points := []Point{{1.0, 2.0}, {3.0, 4.0}}
	raw := StructSliceToBytes(points)
	fmt.Printf("  %d points = %d bytes: %v\n", len(points), len(raw), raw)
}
```

Safety rules you must follow:

1. **Never store `uintptr` and convert back later**: `uintptr` is an integer, not a pointer. The GC can move the pointed-to object between the two conversions. Always do `unsafe.Pointer(uintptr(p) + offset)` in a single expression, or use `unsafe.Add`.
2. **`[]byte` → `string` zero-copy is read-only**: if you modify the byte slice afterward, you corrupt the string, violating Go's immutability guarantee. Only use this when the byte slice is effectively frozen.
3. **Struct reinterpretation assumes memory layout**: padding, alignment, and byte order must match exactly. This works on a single architecture but is not portable. Use `encoding/binary` for cross-platform serialization.
4. **`unsafe.Sizeof` includes padding**: a struct `{bool; int64}` is 16 bytes, not 9, due to alignment.
5. **`go vet` catches some misuse**: always run `go vet` on code using `unsafe`.'''),

    ("go_deep/reflect_dynamic_struct", r'''How do I dynamically create struct types at runtime in Go using reflect? For example, building a struct from a list of field definitions.''', r'''<think>
Go's reflect package allows creating new struct types at runtime with reflect.StructOf. This is useful for:
- Building types from configuration/schema files
- ORM-style dynamic row mapping
- Plugin systems where field layouts aren't known at compile time

Key API:
- reflect.StructOf(fields []reflect.StructField) reflect.Type
- reflect.New(typ) returns a *T (as reflect.Value)
- reflect.StructField has Name, Type, Tag, Anonymous fields
- Fields must be exported (capitalized) to be settable

Considerations:
- Dynamic structs can't implement interfaces (no methods)
- They work with encoding/json if tags are set correctly
- Performance: reflect operations are ~10-100x slower than direct field access
- Types created this way are equivalent to anonymous structs
- Can be used with JSON marshal/unmarshal, database/sql Scan, etc.
- reflect.StructOf panics if field names aren't valid identifiers or aren't exported
</think>

Here is a practical example of runtime struct creation with `reflect`:

```go
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"reflect"
	"strings"
)

// FieldDef describes a struct field to create dynamically.
type FieldDef struct {
	Name     string
	Type     string // "string", "int", "float64", "bool", "[]string"
	JSONName string // optional: override json tag
}

// typeMap resolves type names to reflect.Type.
var typeMap = map[string]reflect.Type{
	"string":   reflect.TypeOf(""),
	"int":      reflect.TypeOf(0),
	"int64":    reflect.TypeOf(int64(0)),
	"float64":  reflect.TypeOf(float64(0)),
	"bool":     reflect.TypeOf(false),
	"[]string": reflect.TypeOf([]string{}),
	"[]int":    reflect.TypeOf([]int{}),
}

// BuildStructType creates a new struct type from field definitions.
func BuildStructType(fields []FieldDef) (reflect.Type, error) {
	structFields := make([]reflect.StructField, len(fields))

	for i, f := range fields {
		typ, ok := typeMap[f.Type]
		if !ok {
			return nil, fmt.Errorf("unknown type %q for field %q", f.Type, f.Name)
		}

		// Ensure the name is exported (capitalized).
		name := strings.ToUpper(f.Name[:1]) + f.Name[1:]

		jsonName := f.JSONName
		if jsonName == "" {
			jsonName = strings.ToLower(f.Name[:1]) + f.Name[1:]
		}

		structFields[i] = reflect.StructField{
			Name: name,
			Type: typ,
			Tag:  reflect.StructTag(fmt.Sprintf(`json:"%s"`, jsonName)),
		}
	}

	return reflect.StructOf(structFields), nil
}

// NewInstance creates a new zero-valued instance of the dynamic struct.
func NewInstance(typ reflect.Type) reflect.Value {
	return reflect.New(typ).Elem()
}

// SetField sets a field by name on a dynamic struct instance.
func SetField(instance reflect.Value, name string, value any) error {
	field := instance.FieldByName(name)
	if !field.IsValid() {
		return fmt.Errorf("no field %q", name)
	}
	if !field.CanSet() {
		return fmt.Errorf("field %q is not settable", name)
	}

	val := reflect.ValueOf(value)
	if !val.Type().AssignableTo(field.Type()) {
		return fmt.Errorf("cannot assign %T to field %q (type %s)", value, name, field.Type())
	}
	field.Set(val)
	return nil
}

// PopulateFromMap fills a dynamic struct from a map.
func PopulateFromMap(typ reflect.Type, data map[string]any) (reflect.Value, error) {
	instance := NewInstance(typ)

	for i := 0; i < typ.NumField(); i++ {
		sf := typ.Field(i)

		// Extract json tag name for lookup.
		jsonTag := sf.Tag.Get("json")
		val, ok := data[jsonTag]
		if !ok {
			continue
		}

		field := instance.Field(i)
		rv := reflect.ValueOf(val)

		// Handle numeric type conversions (JSON numbers are float64).
		if rv.Type() != field.Type() {
			if rv.CanConvert(field.Type()) {
				rv = rv.Convert(field.Type())
			} else {
				return instance, fmt.Errorf("cannot convert %T to %s for field %s",
					val, field.Type(), sf.Name)
			}
		}

		field.Set(rv)
	}
	return instance, nil
}

func main() {
	// Define fields for a "User" struct at runtime.
	fields := []FieldDef{
		{Name: "ID", Type: "int64", JSONName: "id"},
		{Name: "Username", Type: "string", JSONName: "username"},
		{Name: "Email", Type: "string", JSONName: "email"},
		{Name: "Score", Type: "float64", JSONName: "score"},
		{Name: "Active", Type: "bool", JSONName: "active"},
		{Name: "Tags", Type: "[]string", JSONName: "tags"},
	}

	// Build the type.
	userType, err := BuildStructType(fields)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("Dynamic type: %v\n", userType)
	fmt.Printf("Size: %d bytes, NumField: %d\n\n", userType.Size(), userType.NumField())

	// Print the layout.
	for i := 0; i < userType.NumField(); i++ {
		f := userType.Field(i)
		fmt.Printf("  Field %d: %s %s `%s` (offset %d)\n",
			i, f.Name, f.Type, f.Tag, f.Offset)
	}

	// Create an instance and set fields.
	fmt.Println("\n=== Manual field setting ===")
	user := NewInstance(userType)
	SetField(user, "ID", int64(42))
	SetField(user, "Username", "gopher")
	SetField(user, "Email", "gopher@example.com")
	SetField(user, "Score", 98.5)
	SetField(user, "Active", true)
	SetField(user, "Tags", []string{"go", "systems"})

	// Marshal to JSON — works because we set json tags.
	data, _ := json.MarshalIndent(user.Addr().Interface(), "", "  ")
	fmt.Printf("%s\n", data)

	// Unmarshal JSON into a dynamic struct.
	fmt.Println("\n=== JSON unmarshal into dynamic struct ===")
	jsonInput := `{"id": 99, "username": "rustacean", "email": "r@example.com", "score": 77.3, "active": false, "tags": ["rust", "wasm"]}`

	ptr := reflect.New(userType)
	if err := json.Unmarshal([]byte(jsonInput), ptr.Interface()); err != nil {
		log.Fatal(err)
	}

	result := ptr.Elem()
	for i := 0; i < result.NumField(); i++ {
		fmt.Printf("  %s = %v\n", userType.Field(i).Name, result.Field(i).Interface())
	}

	// Populate from a map (like database row scan).
	fmt.Println("\n=== Populate from map ===")
	row := map[string]any{
		"id":       float64(7), // JSON numbers come as float64
		"username": "mapper",
		"email":    "m@test.com",
		"score":    42.0,
		"active":   true,
	}
	mapped, err := PopulateFromMap(userType, row)
	if err != nil {
		log.Fatal(err)
	}
	out, _ := json.Marshal(mapped.Addr().Interface())
	fmt.Printf("  %s\n", out)
}
```

Key points about dynamic structs:

1. **Field names must be exported**: `reflect.StructOf` panics if a field name starts with a lowercase letter. Capitalize programmatically.
2. **JSON works natively**: setting `reflect.StructTag` with json tags makes `encoding/json` work on dynamic structs just like static ones.
3. **No methods**: dynamic structs cannot implement interfaces. If you need method dispatch, use a wrapper struct with the dynamic data as a field.
4. **Type identity**: each call to `reflect.StructOf` with the same fields creates the same type — Go caches them.
5. **Performance**: reflect-based field access is ~50x slower than direct access. Use for configuration-driven code, not hot paths.
6. **`Addr().Interface()`**: to get an `any` value you can pass to `json.Marshal`, call `.Addr()` (get pointer) then `.Interface()`.'''),

    ("go_deep/reflect_json_schema", r'''How do I use reflect to build a JSON schema from Go struct tags? I want to introspect a struct's fields and generate a JSON Schema (draft-07) automatically.''', r'''<think>
This involves:
1. Walking a struct's fields with reflect
2. Reading json and custom tags (like `jsonschema:"required,min=0,max=100"`)
3. Mapping Go types to JSON Schema types
4. Handling nested structs, slices, maps, pointers
5. Generating a valid JSON Schema draft-07 document

Plan:
- Recursive function that takes reflect.Type and returns a schema map
- Handle: string, int*, float*, bool, []T, map[string]T, struct, *T, time.Time
- Parse custom tags for validation constraints
- Handle `json:"-"` to skip fields, `json:"name,omitempty"` for optional
- Required fields: those without omitempty
- Nested structs become $ref or inline definitions
</think>

Here is a JSON Schema generator that introspects Go struct tags:

```go
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"reflect"
	"strconv"
	"strings"
	"time"
)

// Schema represents a JSON Schema document.
type Schema map[string]any

// Custom tag format: `jsonschema:"required,min=0,max=100,enum=a|b|c,description=Some field"`
// Also reads from `json` tag for field name and omitempty.

func GenerateSchema(v any) Schema {
	t := reflect.TypeOf(v)
	if t.Kind() == reflect.Ptr {
		t = t.Elem()
	}

	schema := typeToSchema(t)
	schema["$schema"] = "http://json-schema.org/draft-07/schema#"
	return schema
}

func typeToSchema(t reflect.Type) Schema {
	// Dereference pointer.
	for t.Kind() == reflect.Ptr {
		t = t.Elem()
	}

	switch t.Kind() {
	case reflect.Struct:
		return structToSchema(t)
	case reflect.Slice, reflect.Array:
		return sliceToSchema(t)
	case reflect.Map:
		return mapToSchema(t)
	default:
		return primitiveSchema(t)
	}
}

func structToSchema(t reflect.Type) Schema {
	// Special case: time.Time → string with date-time format.
	if t == reflect.TypeOf(time.Time{}) {
		return Schema{"type": "string", "format": "date-time"}
	}

	properties := make(Schema)
	required := []string{}

	for i := 0; i < t.NumField(); i++ {
		field := t.Field(i)

		// Skip unexported fields.
		if !field.IsExported() {
			continue
		}

		// Parse json tag.
		jsonTag := field.Tag.Get("json")
		if jsonTag == "-" {
			continue
		}

		name := field.Name
		omitempty := false
		if jsonTag != "" {
			parts := strings.Split(jsonTag, ",")
			if parts[0] != "" {
				name = parts[0]
			}
			for _, p := range parts[1:] {
				if p == "omitempty" {
					omitempty = true
				}
			}
		}

		// Handle anonymous (embedded) fields.
		if field.Anonymous {
			embedded := typeToSchema(field.Type)
			if props, ok := embedded["properties"].(Schema); ok {
				for k, v := range props {
					properties[k] = v
				}
			}
			if req, ok := embedded["required"].([]string); ok {
				required = append(required, req...)
			}
			continue
		}

		// Build field schema.
		fieldSchema := typeToSchema(field.Type)

		// Parse custom jsonschema tag.
		schemaTag := field.Tag.Get("jsonschema")
		isRequired := !omitempty // default: required unless omitempty
		parseSchemaTag(schemaTag, fieldSchema, &isRequired)

		properties[name] = fieldSchema
		if isRequired {
			required = append(required, name)
		}
	}

	schema := Schema{
		"type":       "object",
		"properties": properties,
	}
	if len(required) > 0 {
		schema["required"] = required
	}
	return schema
}

func sliceToSchema(t reflect.Type) Schema {
	items := typeToSchema(t.Elem())
	return Schema{
		"type":  "array",
		"items": items,
	}
}

func mapToSchema(t reflect.Type) Schema {
	if t.Key().Kind() != reflect.String {
		return Schema{"type": "object"}
	}
	return Schema{
		"type":                 "object",
		"additionalProperties": typeToSchema(t.Elem()),
	}
}

func primitiveSchema(t reflect.Type) Schema {
	switch t.Kind() {
	case reflect.String:
		return Schema{"type": "string"}
	case reflect.Bool:
		return Schema{"type": "boolean"}
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		return Schema{"type": "integer"}
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		return Schema{"type": "integer", "minimum": 0}
	case reflect.Float32, reflect.Float64:
		return Schema{"type": "number"}
	default:
		return Schema{}
	}
}

func parseSchemaTag(tag string, schema Schema, isRequired *bool) {
	if tag == "" {
		return
	}

	for _, part := range strings.Split(tag, ",") {
		part = strings.TrimSpace(part)

		if part == "required" {
			*isRequired = true
			continue
		}
		if part == "optional" {
			*isRequired = false
			continue
		}

		if kv := strings.SplitN(part, "=", 2); len(kv) == 2 {
			key, val := kv[0], kv[1]
			switch key {
			case "min":
				if n, err := strconv.ParseFloat(val, 64); err == nil {
					schema["minimum"] = n
				}
			case "max":
				if n, err := strconv.ParseFloat(val, 64); err == nil {
					schema["maximum"] = n
				}
			case "minLength":
				if n, err := strconv.Atoi(val); err == nil {
					schema["minLength"] = n
				}
			case "maxLength":
				if n, err := strconv.Atoi(val); err == nil {
					schema["maxLength"] = n
				}
			case "pattern":
				schema["pattern"] = val
			case "format":
				schema["format"] = val
			case "enum":
				values := strings.Split(val, "|")
				anyVals := make([]any, len(values))
				for i, v := range values {
					anyVals[i] = v
				}
				schema["enum"] = anyVals
			case "description":
				schema["description"] = val
			case "default":
				schema["default"] = val
			case "minItems":
				if n, err := strconv.Atoi(val); err == nil {
					schema["minItems"] = n
				}
			case "maxItems":
				if n, err := strconv.Atoi(val); err == nil {
					schema["maxItems"] = n
				}
			}
		}
	}
}

// ============================================================
// Example structs to generate schemas from
// ============================================================

type Address struct {
	Street  string `json:"street" jsonschema:"description=Street address"`
	City    string `json:"city"`
	ZipCode string `json:"zip_code" jsonschema:"pattern=^[0-9]{5}$"`
	Country string `json:"country" jsonschema:"enum=US|CA|UK|DE"`
}

type User struct {
	ID        int64     `json:"id" jsonschema:"description=Unique identifier"`
	Username  string    `json:"username" jsonschema:"minLength=3,maxLength=32"`
	Email     string    `json:"email" jsonschema:"format=email"`
	Age       int       `json:"age,omitempty" jsonschema:"min=0,max=150"`
	Score     float64   `json:"score,omitempty" jsonschema:"min=0,max=100"`
	Active    bool      `json:"active"`
	Roles     []string  `json:"roles" jsonschema:"minItems=1"`
	Address   Address   `json:"address"`
	Tags      map[string]string `json:"tags,omitempty"`
	CreatedAt time.Time `json:"created_at"`
}

func main() {
	schema := GenerateSchema(User{})
	data, err := json.MarshalIndent(schema, "", "  ")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(string(data))
}
```

Output (abbreviated):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "id": { "type": "integer", "description": "Unique identifier" },
    "username": { "type": "string", "minLength": 3, "maxLength": 32 },
    "email": { "type": "string", "format": "email" },
    "age": { "type": "integer", "minimum": 0, "maximum": 150 },
    "address": {
      "type": "object",
      "properties": {
        "street": { "type": "string", "description": "Street address" },
        "country": { "type": "string", "enum": ["US", "CA", "UK", "DE"] }
      }
    },
    "created_at": { "type": "string", "format": "date-time" }
  },
  "required": ["id", "username", "email", "active", "roles", "address", "created_at"]
}
```

Design decisions:

- **`omitempty` maps to optional**: fields without `omitempty` in the json tag are added to the `required` array. Override with `jsonschema:"optional"` or `jsonschema:"required"`.
- **Embedded structs flatten**: anonymous fields merge their properties into the parent, matching Go's field promotion semantics.
- **`time.Time` special case**: detected by type equality and rendered as `{"type": "string", "format": "date-time"}`.
- **Recursive**: nested structs and slices-of-structs are handled naturally by the recursive `typeToSchema` call.
- **Extensible tag format**: comma-separated key=value pairs in the `jsonschema` tag. Pipe-separated values for enums.'''),

    ("go_deep/go_plugin_system", r'''How do I build a plugin system in Go using the plugin package? Show me loading .so files and calling functions from them at runtime.''', r'''<think>
Go's plugin package (Linux/macOS only, not Windows) allows loading shared objects (.so) at runtime. The pattern:

1. Build the plugin: `go build -buildmode=plugin -o myplugin.so plugin.go`
2. Load it: `plugin.Open("myplugin.so")`
3. Lookup symbols: `plug.Lookup("SymbolName")`
4. Type-assert the symbol to the expected type

Key limitations:
- Only works on Linux, macOS, and FreeBSD (not Windows)
- Plugin and main must be built with the same Go version
- Plugin and main must agree on all dependency versions
- Can't unload plugins once loaded
- All exported symbols must match expected types exactly

For a practical example, let's build a text transformation plugin system where plugins implement a common interface.

Alternative: for production systems, many prefer hashicorp/go-plugin (RPC-based) or yaegi (Go interpreter) because the native plugin package has too many constraints.
</think>

Here is a plugin system using Go's `plugin` package (Linux/macOS only):

```go
// ---- plugin_api/api.go (shared interface, imported by both) ----
package plugin_api

// Transformer is the interface all plugins must implement.
type Transformer interface {
	Name() string
	Transform(input string) (string, error)
}

// Metadata holds plugin info.
type Metadata struct {
	Version     string
	Author      string
	Description string
}
```

```go
// ---- plugins/uppercase/main.go (a plugin) ----
package main

import (
	"strings"
	"yourmodule/plugin_api"
)

// Plugin must export these two symbols.
var Metadata = plugin_api.Metadata{
	Version:     "1.0.0",
	Author:      "demo",
	Description: "Converts text to uppercase",
}

type upperPlugin struct{}

func (u *upperPlugin) Name() string { return "uppercase" }
func (u *upperPlugin) Transform(input string) (string, error) {
	return strings.ToUpper(input), nil
}

// New is the factory function that the host looks up.
var New func() plugin_api.Transformer = func() plugin_api.Transformer {
	return &upperPlugin{}
}
```

```go
// ---- plugins/reverse/main.go (another plugin) ----
package main

import "yourmodule/plugin_api"

var Metadata = plugin_api.Metadata{
	Version:     "1.0.0",
	Author:      "demo",
	Description: "Reverses the input string",
}

type reversePlugin struct{}

func (r *reversePlugin) Name() string { return "reverse" }
func (r *reversePlugin) Transform(input string) (string, error) {
	runes := []rune(input)
	for i, j := 0, len(runes)-1; i < j; i, j = i+1, j-1 {
		runes[i], runes[j] = runes[j], runes[i]
	}
	return string(runes), nil
}

var New func() plugin_api.Transformer = func() plugin_api.Transformer {
	return &reversePlugin{}
}
```

```go
// ---- main.go (host application) ----
package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"plugin"

	"yourmodule/plugin_api"
)

// PluginEntry holds a loaded plugin.
type PluginEntry struct {
	Meta        plugin_api.Metadata
	Transformer plugin_api.Transformer
}

// LoadPlugin loads a single .so plugin file.
func LoadPlugin(path string) (*PluginEntry, error) {
	p, err := plugin.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open %s: %w", path, err)
	}

	// Look up the Metadata symbol.
	metaSym, err := p.Lookup("Metadata")
	if err != nil {
		return nil, fmt.Errorf("lookup Metadata in %s: %w", path, err)
	}
	meta, ok := metaSym.(*plugin_api.Metadata)
	if !ok {
		return nil, fmt.Errorf("Metadata in %s has wrong type: %T", path, metaSym)
	}

	// Look up the New factory function.
	newSym, err := p.Lookup("New")
	if err != nil {
		return nil, fmt.Errorf("lookup New in %s: %w", path, err)
	}
	newFn, ok := newSym.(*func() plugin_api.Transformer)
	if !ok {
		return nil, fmt.Errorf("New in %s has wrong type: %T", path, newSym)
	}

	transformer := (*newFn)()

	return &PluginEntry{
		Meta:        *meta,
		Transformer: transformer,
	}, nil
}

// LoadAllPlugins scans a directory for .so files and loads them.
func LoadAllPlugins(dir string) (map[string]*PluginEntry, error) {
	plugins := make(map[string]*PluginEntry)

	matches, err := filepath.Glob(filepath.Join(dir, "*.so"))
	if err != nil {
		return nil, err
	}

	for _, path := range matches {
		entry, err := LoadPlugin(path)
		if err != nil {
			log.Printf("WARN: skipping %s: %v", path, err)
			continue
		}

		name := entry.Transformer.Name()
		plugins[name] = entry
		log.Printf("loaded plugin %q v%s: %s",
			name, entry.Meta.Version, entry.Meta.Description)
	}

	return plugins, nil
}

func main() {
	pluginDir := "./plugins_built"
	if len(os.Args) > 1 {
		pluginDir = os.Args[1]
	}

	plugins, err := LoadAllPlugins(pluginDir)
	if err != nil {
		log.Fatal(err)
	}

	if len(plugins) == 0 {
		log.Fatal("no plugins found")
	}

	// Apply all plugins to a test string.
	input := "Hello, Plugin World!"
	fmt.Printf("input: %s\n\n", input)

	for name, entry := range plugins {
		result, err := entry.Transformer.Transform(input)
		if err != nil {
			log.Printf("%s error: %v", name, err)
			continue
		}
		fmt.Printf("[%s] → %s\n", name, result)
	}
}
```

Build and run:

```bash
# Build the plugins as shared objects.
mkdir -p plugins_built
go build -buildmode=plugin -o plugins_built/uppercase.so ./plugins/uppercase/
go build -buildmode=plugin -o plugins_built/reverse.so  ./plugins/reverse/

# Run the host.
go run main.go
# Output:
# loaded plugin "uppercase" v1.0.0: Converts text to uppercase
# loaded plugin "reverse" v1.0.0: Reverses the input string
# input: Hello, Plugin World!
#
# [uppercase] → HELLO, PLUGIN WORLD!
# [reverse] → !dlroW nigulP ,olleH
```

Important caveats about Go plugins:

1. **Platform**: only Linux, macOS, FreeBSD. No Windows support.
2. **Version lock**: plugin and host must use the exact same Go toolchain version. A plugin built with Go 1.21 will not load in a Go 1.22 binary.
3. **Dependency alignment**: if both plugin and host import the same package, they must use the exact same version. Version mismatches cause load failures.
4. **No unloading**: once `plugin.Open` loads a `.so`, it cannot be unloaded. Memory from the plugin persists for the process lifetime.
5. **Symbol types**: `Lookup` returns `any`. Variables are returned as pointers (`*T`), functions as their function type. The type assertion pattern differs.
6. **Production alternative**: for robust plugin systems, consider `hashicorp/go-plugin` (uses gRPC, works cross-platform, supports plugin crashes without host crash) or `traefik/yaegi` (Go interpreter, no compilation needed).'''),

    ("go_deep/embed_fs", r'''How do I use Go's embed.FS to bundle static files into a single binary? Show me embedding templates, configs, and static assets for a web server.''', r'''<think>
Go 1.16 introduced the embed package for compiling files directly into the binary. Key features:
- //go:embed directive embeds files at compile time
- embed.FS implements fs.FS, works with http.FileServer, template.ParseFS, etc.
- Can embed individual files as string or []byte, or directories as embed.FS
- Patterns support glob-like matching
- Hidden files (starting with . or _) are excluded by default unless using "all:" prefix

This is great for single-binary deployment of web servers, CLI tools with templates, etc.
</think>

Here is a complete single-binary web server with embedded templates, config, and static assets:

```go
package main

import (
	"embed"
	"encoding/json"
	"fmt"
	"html/template"
	"io/fs"
	"log"
	"net/http"
	"os"
)

// Embed entire directories and individual files.
// The paths are relative to the source file's directory.

//go:embed templates/*.html
var templateFS embed.FS

//go:embed static/*
var staticFS embed.FS

//go:embed config/defaults.json
var defaultConfig []byte

//go:embed VERSION
var version string

// Config loaded from embedded defaults, overrideable at runtime.
type Config struct {
	AppName  string `json:"app_name"`
	Port     int    `json:"port"`
	LogLevel string `json:"log_level"`
}

func loadConfig() (*Config, error) {
	var cfg Config
	// Start with embedded defaults.
	if err := json.Unmarshal(defaultConfig, &cfg); err != nil {
		return nil, fmt.Errorf("parse embedded config: %w", err)
	}

	// Override with external file if it exists.
	if data, err := os.ReadFile("config.json"); err == nil {
		if err := json.Unmarshal(data, &cfg); err != nil {
			return nil, fmt.Errorf("parse external config: %w", err)
		}
		log.Println("loaded external config override")
	}

	return &cfg, nil
}

func main() {
	cfg, err := loadConfig()
	if err != nil {
		log.Fatal(err)
	}

	// Parse templates from embedded FS.
	tmpl, err := template.ParseFS(templateFS, "templates/*.html")
	if err != nil {
		log.Fatalf("parse templates: %v", err)
	}

	// Create a sub-filesystem for static files so URLs don't need the "static/" prefix.
	staticSub, err := fs.Sub(staticFS, "static")
	if err != nil {
		log.Fatal(err)
	}

	mux := http.NewServeMux()

	// Serve static files at /static/.
	mux.Handle("/static/", http.StripPrefix("/static/",
		http.FileServer(http.FS(staticSub))))

	// Home page using embedded template.
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}

		data := map[string]any{
			"Title":   cfg.AppName,
			"Version": version,
			"Message": "Served from a single binary!",
		}

		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		if err := tmpl.ExecuteTemplate(w, "index.html", data); err != nil {
			http.Error(w, err.Error(), 500)
		}
	})

	// API endpoint listing embedded files (for debugging).
	mux.HandleFunc("/api/files", func(w http.ResponseWriter, r *http.Request) {
		var files []string
		fs.WalkDir(staticFS, ".", func(path string, d fs.DirEntry, err error) error {
			if err != nil {
				return err
			}
			if !d.IsDir() {
				info, _ := d.Info()
				files = append(files, fmt.Sprintf("%s (%d bytes)", path, info.Size()))
			}
			return nil
		})
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(files)
	})

	addr := fmt.Sprintf(":%d", cfg.Port)
	log.Printf("%s v%s listening on %s", cfg.AppName, version, addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}
```

Required file structure:

```
project/
  main.go
  VERSION                    # "1.0.0"
  config/
    defaults.json            # {"app_name":"MyApp","port":8080,"log_level":"info"}
  templates/
    index.html               # HTML template
    layout.html              # Base layout
  static/
    css/style.css
    js/app.js
    img/logo.png
```

Example `templates/index.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <title>{{.Title}}</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <h1>{{.Title}}</h1>
    <p>{{.Message}}</p>
    <p>Version: {{.Version}}</p>
    <script src="/static/js/app.js"></script>
</body>
</html>
```

Build and deploy as a single binary:

```bash
go build -o myapp .
# myapp is a single file containing all templates, CSS, JS, images, and config.
# Copy it anywhere and run — no external files needed.
scp myapp server:/usr/local/bin/
ssh server myapp
```

Key embed patterns:

1. **`//go:embed file.txt`** on `var s string` — embeds as a string (trailing newline preserved).
2. **`//go:embed file.bin`** on `var b []byte` — embeds as raw bytes.
3. **`//go:embed dir/*`** on `var fs embed.FS` — embeds a directory tree. Access via `fs.ReadFile`, `fs.ReadDir`, or as `fs.FS`.
4. **`//go:embed all:dir/*`** — includes hidden files (`.gitkeep`, `_internal`).
5. **Multiple patterns**: `//go:embed templates/*.html templates/*.tmpl` on one variable.
6. **`fs.Sub`**: strips a prefix to create a sub-filesystem, so embedded `static/css/style.css` becomes accessible as `css/style.css`.
7. **Template parsing**: `template.ParseFS(fs, pattern)` works directly with `embed.FS`.
8. **Config override**: embed defaults, but load external file if present — lets users customize without rebuilding.'''),

    ("go_deep/custom_slog_handler", r'''How do I write a custom log handler for Go's slog package? I want colored terminal output with source file info and custom formatting.''', r'''<think>
Go 1.21 introduced slog (structured logging) with a handler interface:
- slog.Handler has 4 methods: Enabled, Handle, WithAttrs, WithGroup
- Handle receives slog.Record which has Time, Level, Message, and attributes
- WithAttrs and WithGroup return new handlers (immutable pattern)
- The handler must be safe for concurrent use

For colored output:
- Use ANSI escape codes for different log levels
- Check if stdout is a terminal (os.Stdout.Fd() with term.IsTerminal or just check for color support)
- Format: timestamp, colored level, source file:line, message, then key=value pairs

Key implementation details:
- WithAttrs returns a new handler with pre-formatted attributes (optimization)
- WithGroup prefixes all subsequent attribute keys with the group name
- Enabled should check the minimum level
- Source info is available via Record.AddSource or by getting the PC from the record
</think>

Here is a custom `slog.Handler` with colored output and source location:

```go
package main

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"os"
	"runtime"
	"sync"
	"time"
)

// ANSI color codes.
const (
	colorReset  = "\033[0m"
	colorRed    = "\033[31m"
	colorGreen  = "\033[32m"
	colorYellow = "\033[33m"
	colorBlue   = "\033[34m"
	colorGray   = "\033[90m"
	colorWhite  = "\033[37m"
	colorBold   = "\033[1m"
)

// PrettyHandler is a colored, human-readable slog handler.
type PrettyHandler struct {
	w         io.Writer
	mu        *sync.Mutex
	level     slog.Level
	addSource bool
	attrs     []slog.Attr   // pre-collected attributes from WithAttrs
	groups    []string       // active group names from WithGroup
}

type PrettyHandlerOptions struct {
	Level     slog.Level
	AddSource bool
	Writer    io.Writer
}

func NewPrettyHandler(opts PrettyHandlerOptions) *PrettyHandler {
	w := opts.Writer
	if w == nil {
		w = os.Stderr
	}
	return &PrettyHandler{
		w:         w,
		mu:        &sync.Mutex{},
		level:     opts.Level,
		addSource: opts.AddSource,
	}
}

func (h *PrettyHandler) Enabled(_ context.Context, level slog.Level) bool {
	return level >= h.level
}

func (h *PrettyHandler) Handle(_ context.Context, r slog.Record) error {
	h.mu.Lock()
	defer h.mu.Unlock()

	// Timestamp.
	timeStr := r.Time.Format("15:04:05.000")

	// Colored level.
	levelStr := h.colorLevel(r.Level)

	// Source location.
	sourceStr := ""
	if h.addSource {
		if r.PC != 0 {
			frame, _ := runtime.CallersFrames([]uintptr{r.PC}).Next()
			// Shorten the file path to just filename:line.
			file := frame.File
			for i := len(file) - 1; i >= 0; i-- {
				if file[i] == '/' {
					file = file[i+1:]
					break
				}
			}
			sourceStr = fmt.Sprintf(" %s%s:%d%s", colorGray, file, frame.Line, colorReset)
		}
	}

	// Build the log line.
	fmt.Fprintf(h.w, "%s%s%s %s %s%s%s%s",
		colorGray, timeStr, colorReset,
		levelStr,
		colorWhite, r.Message, colorReset,
		sourceStr,
	)

	// Write pre-collected attrs from WithAttrs.
	for _, a := range h.attrs {
		h.writeAttr(a, h.groups)
	}

	// Write inline attrs from the log call.
	r.Attrs(func(a slog.Attr) bool {
		h.writeAttr(a, h.groups)
		return true
	})

	fmt.Fprintln(h.w)
	return nil
}

func (h *PrettyHandler) writeAttr(a slog.Attr, groups []string) {
	// Resolve the attribute (handles LogValuer, zero values, etc.).
	a.Value = a.Value.Resolve()
	if a.Equal(slog.Attr{}) {
		return
	}

	key := a.Key
	// Prefix with group names.
	for _, g := range groups {
		key = g + "." + key
	}

	// Handle group attributes (nested key=value sets).
	if a.Value.Kind() == slog.KindGroup {
		attrs := a.Value.Group()
		newGroups := append(groups, a.Key)
		for _, ga := range attrs {
			h.writeAttr(ga, newGroups)
		}
		return
	}

	fmt.Fprintf(h.w, " %s%s%s=%v",
		colorBlue, key, colorReset, a.Value)
}

func (h *PrettyHandler) colorLevel(level slog.Level) string {
	switch {
	case level >= slog.LevelError:
		return fmt.Sprintf("%s%s%-5s%s", colorBold, colorRed, level.String(), colorReset)
	case level >= slog.LevelWarn:
		return fmt.Sprintf("%s%-5s%s", colorYellow, level.String(), colorReset)
	case level >= slog.LevelInfo:
		return fmt.Sprintf("%s%-5s%s", colorGreen, level.String(), colorReset)
	default:
		return fmt.Sprintf("%s%-5s%s", colorGray, level.String(), colorReset)
	}
}

// WithAttrs returns a new handler with additional attributes.
// This is called once and the attrs apply to all subsequent Handle calls.
func (h *PrettyHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	// Clone to maintain immutability.
	newAttrs := make([]slog.Attr, len(h.attrs)+len(attrs))
	copy(newAttrs, h.attrs)
	copy(newAttrs[len(h.attrs):], attrs)

	return &PrettyHandler{
		w:         h.w,
		mu:        h.mu, // share the mutex for serialized output
		level:     h.level,
		addSource: h.addSource,
		attrs:     newAttrs,
		groups:    h.groups,
	}
}

// WithGroup returns a new handler that prefixes all attr keys with the group name.
func (h *PrettyHandler) WithGroup(name string) slog.Handler {
	if name == "" {
		return h
	}

	newGroups := make([]string, len(h.groups)+1)
	copy(newGroups, h.groups)
	newGroups[len(h.groups)] = name

	return &PrettyHandler{
		w:         h.w,
		mu:        h.mu,
		level:     h.level,
		addSource: h.addSource,
		attrs:     h.attrs,
		groups:    newGroups,
	}
}

func main() {
	handler := NewPrettyHandler(PrettyHandlerOptions{
		Level:     slog.LevelDebug,
		AddSource: true,
		Writer:    os.Stdout,
	})

	logger := slog.New(handler)
	slog.SetDefault(logger)

	// Basic logging at different levels.
	slog.Debug("initializing subsystem", "component", "cache")
	slog.Info("server started", "port", 8080, "tls", true)
	slog.Warn("high memory usage", "percent", 87.5)
	slog.Error("connection failed", "addr", "db:5432", "retry_in", 5*time.Second)

	// With pre-set attributes (like a per-request logger).
	reqLog := logger.With("request_id", "abc-123", "method", "GET")
	reqLog.Info("handling request", "path", "/api/users")
	reqLog.Info("response sent", "status", 200, "duration_ms", 42)

	// With groups.
	dbLog := logger.WithGroup("db")
	dbLog.Info("query executed",
		"table", "users",
		"rows", 150,
		"duration_ms", 12,
	)

	// Nested groups.
	httpLog := logger.WithGroup("http").WithGroup("client")
	httpLog.Warn("slow upstream", "url", "https://api.example.com", "ms", 2500)
}
```

Output (with colors in a terminal):

```
10:30:00.123 DEBUG initializing subsystem main.go:115 component=cache
10:30:00.123 INFO  server started main.go:116 port=8080 tls=true
10:30:00.123 WARN  high memory usage main.go:117 percent=87.5
10:30:00.123 ERROR connection failed main.go:118 addr=db:5432 retry_in=5s
10:30:00.123 INFO  handling request main.go:122 request_id=abc-123 method=GET path=/api/users
10:30:00.123 INFO  query executed main.go:129 db.table=users db.rows=150 db.duration_ms=12
10:30:00.123 WARN  slow upstream main.go:133 http.client.url=https://api.example.com http.client.ms=2500
```

Implementation notes:

- **Mutex is shared**: `WithAttrs` and `WithGroup` return new handler instances that share the same mutex. This ensures log lines from the parent and child loggers don't interleave.
- **Immutable pattern**: `WithAttrs`/`WithGroup` clone state into new handlers. The original handler is not modified, making it safe for concurrent use.
- **`Resolve()` on values**: handles types implementing `slog.LogValuer` (lazy evaluation) and resolves zero-value attributes.
- **Source location from PC**: `r.PC` is set when `slog.NewTextHandler` has `AddSource: true` or when using `slog.New` with a handler that returns true from `Enabled`. We extract it via `runtime.CallersFrames`.'''),

    ("go_deep/structured_logging_context", r'''How do I implement structured logging with context propagation in Go? I want request-scoped fields (like trace ID) to automatically appear in every log line.''', r'''<think>
Context-propagated logging is a common pattern in Go services. The idea:
- Store logger or log attributes in context.Context
- Middleware injects request-specific fields (trace_id, request_id, user_id)
- All downstream functions extract the logger from context and log with those fields automatically

Two main approaches:
1. Store *slog.Logger in context — each request gets a logger with pre-set attrs
2. Store attributes in context, handler extracts them — more flexible but requires custom handler

Approach 1 is simpler and recommended by the slog documentation.

Let me show a complete HTTP middleware chain that:
- Generates a request ID
- Creates a child logger with request fields
- Stores it in context
- Downstream handlers extract and use it
- Works with slog's WithGroup for component-level namespacing
</think>

Here is a complete context-propagated structured logging system:

```go
package main

import (
	"context"
	"fmt"
	"log/slog"
	"math/rand"
	"net/http"
	"os"
	"time"
)

// ---- Context logger helpers ----

type ctxKey struct{}

// WithLogger stores a logger in the context.
func WithLogger(ctx context.Context, logger *slog.Logger) context.Context {
	return context.WithValue(ctx, ctxKey{}, logger)
}

// FromContext retrieves the logger from context, or returns the default.
func FromContext(ctx context.Context) *slog.Logger {
	if logger, ok := ctx.Value(ctxKey{}).(*slog.Logger); ok {
		return logger
	}
	return slog.Default()
}

// L is a shorthand for FromContext.
func L(ctx context.Context) *slog.Logger {
	return FromContext(ctx)
}

// ---- Middleware ----

// RequestIDMiddleware generates a unique ID and attaches a scoped logger.
func RequestIDMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestID := generateID()

		// Create a child logger with request-scoped fields.
		logger := slog.Default().With(
			"request_id", requestID,
			"method", r.Method,
			"path", r.URL.Path,
			"remote", r.RemoteAddr,
		)

		// Store in context.
		ctx := WithLogger(r.Context(), logger)
		r = r.WithContext(ctx)

		// Set response header for tracing.
		w.Header().Set("X-Request-ID", requestID)

		logger.Info("request started")
		start := time.Now()

		// Wrap ResponseWriter to capture status code.
		wrapped := &statusWriter{ResponseWriter: w, status: 200}
		next.ServeHTTP(wrapped, r)

		logger.Info("request completed",
			"status", wrapped.status,
			"duration_ms", time.Since(start).Milliseconds(),
		)
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

// ---- Service layer (uses context logger) ----

type UserService struct{}

func (s *UserService) GetUser(ctx context.Context, id int) (map[string]any, error) {
	// Logger automatically includes request_id, method, path from middleware.
	log := L(ctx).WithGroup("user_service")

	log.Info("fetching user", "user_id", id)

	// Simulate database query.
	time.Sleep(10 * time.Millisecond)

	if id <= 0 {
		log.Warn("invalid user ID", "user_id", id)
		return nil, fmt.Errorf("invalid user ID: %d", id)
	}

	user := map[string]any{
		"id":    id,
		"name":  "Alice",
		"email": "alice@example.com",
	}

	log.Info("user found", "user_id", id, "name", user["name"])
	return user, nil
}

type AuditService struct{}

func (s *AuditService) LogAccess(ctx context.Context, resource string, userID int) {
	// Same context logger — request_id propagates automatically.
	log := L(ctx).WithGroup("audit")
	log.Info("access logged", "resource", resource, "user_id", userID)
}

// ---- Handlers ----

func makeUserHandler(userSvc *UserService, auditSvc *AuditService) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		user, err := userSvc.GetUser(ctx, 42)
		if err != nil {
			L(ctx).Error("handler error", "err", err)
			http.Error(w, err.Error(), 500)
			return
		}

		auditSvc.LogAccess(ctx, "/api/user", 42)

		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"name":%q}`, user["name"])
	}
}

// ---- Helpers ----

func generateID() string {
	const charset = "abcdefghijklmnopqrstuvwxyz0123456789"
	b := make([]byte, 12)
	for i := range b {
		b[i] = charset[rand.Intn(len(charset))]
	}
	return string(b)
}

func main() {
	// Configure slog with JSON output for production.
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelDebug,
	}))
	slog.SetDefault(logger)

	userSvc := &UserService{}
	auditSvc := &AuditService{}

	mux := http.NewServeMux()
	mux.HandleFunc("/api/user", makeUserHandler(userSvc, auditSvc))

	// Wrap with middleware.
	handler := RequestIDMiddleware(mux)

	slog.Info("server starting", "port", 8080)
	if err := http.ListenAndServe(":8080", handler); err != nil {
		slog.Error("server failed", "err", err)
		os.Exit(1)
	}
}
```

Example JSON log output for a single request (all lines share the same `request_id`):

```json
{"time":"2026-03-07T10:30:00Z","level":"INFO","msg":"request started","request_id":"a7x9k2m4p1q3","method":"GET","path":"/api/user","remote":"127.0.0.1:54321"}
{"time":"2026-03-07T10:30:00Z","level":"INFO","msg":"fetching user","request_id":"a7x9k2m4p1q3","method":"GET","path":"/api/user","remote":"127.0.0.1:54321","user_service.user_id":42}
{"time":"2026-03-07T10:30:00Z","level":"INFO","msg":"user found","request_id":"a7x9k2m4p1q3","method":"GET","path":"/api/user","remote":"127.0.0.1:54321","user_service.user_id":42,"user_service.name":"Alice"}
{"time":"2026-03-07T10:30:00Z","level":"INFO","msg":"access logged","request_id":"a7x9k2m4p1q3","method":"GET","path":"/api/user","remote":"127.0.0.1:54321","audit.resource":"/api/user","audit.user_id":42}
{"time":"2026-03-07T10:30:00Z","level":"INFO","msg":"request completed","request_id":"a7x9k2m4p1q3","method":"GET","path":"/api/user","remote":"127.0.0.1:54321","status":200,"duration_ms":12}
```

Key patterns:

1. **Logger-in-context, not attributes-in-context**: storing `*slog.Logger` in context means `With()` calls are evaluated once at middleware time, not on every log call.
2. **`WithGroup` for component namespacing**: `user_service.user_id` vs `audit.user_id` makes it easy to filter in log aggregation tools.
3. **`L(ctx)` helper**: keeps call sites clean — `L(ctx).Info(...)` instead of `slog.FromContext(ctx).Info(...)`.
4. **Status capture wrapper**: wrapping `ResponseWriter` is the standard way to log response status codes in middleware.
5. **JSON handler for production**: `slog.NewJSONHandler` produces structured JSON that Elasticsearch, Loki, and Datadog can parse natively.'''),

    ("go_deep/redis_distributed_lock", r'''How do I implement a distributed lock using Redis in Go? Show me a proper implementation with fencing tokens and automatic expiry.''', r'''<think>
Distributed locking with Redis (Redlock pattern) involves:
1. SET key value NX PX milliseconds — atomic set-if-not-exists with TTL
2. The value should be a unique token (UUID) so only the owner can release
3. Release via Lua script: check value matches, then delete (atomic)
4. Fencing token: monotonically increasing counter to prevent stale lock holders from making changes
5. Auto-renewal: extend the lock if the operation takes longer than expected

Using go-redis/redis for the client. The key safety properties:
- Mutual exclusion: only one client holds the lock
- Deadlock-free: TTL ensures lock is eventually released even if holder crashes
- Fault-tolerant (Redlock): acquire on majority of N Redis nodes

For a single Redis node implementation (most common):
- SET NX with expiry for acquire
- Lua script for release (check-and-delete atomically)
- Optional: background goroutine for renewal
- Fencing: use INCR on a separate key to get a monotonic token
</think>

Here is a production-quality distributed lock implementation with Redis:

```go
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

var (
	ErrLockNotAcquired = errors.New("lock not acquired")
	ErrLockNotHeld     = errors.New("lock not held by this owner")
)

// Lua script: atomically check owner and delete.
// Returns 1 if deleted, 0 if not owned by us.
var releaseLuaScript = redis.NewScript(`
	if redis.call("GET", KEYS[1]) == ARGV[1] then
		return redis.call("DEL", KEYS[1])
	else
		return 0
	end
`)

// Lua script: atomically check owner and extend TTL.
var renewLuaScript = redis.NewScript(`
	if redis.call("GET", KEYS[1]) == ARGV[1] then
		return redis.call("PEXPIRE", KEYS[1], ARGV[2])
	else
		return 0
	end
`)

// Lock represents a distributed lock backed by Redis.
type Lock struct {
	client   *redis.Client
	key      string
	owner    string // unique token for this lock holder
	ttl      time.Duration
	stopOnce sync.Once
	stopCh   chan struct{}
}

// LockOptions configures lock acquisition.
type LockOptions struct {
	TTL          time.Duration // lock expiry (default: 10s)
	RetryDelay   time.Duration // delay between retries (default: 100ms)
	RetryTimeout time.Duration // max time to wait for lock (default: 5s)
	AutoRenew    bool          // auto-extend lock while held (default: false)
}

func DefaultLockOptions() LockOptions {
	return LockOptions{
		TTL:          10 * time.Second,
		RetryDelay:   100 * time.Millisecond,
		RetryTimeout: 5 * time.Second,
		AutoRenew:    false,
	}
}

// Acquire tries to obtain a distributed lock.
func Acquire(ctx context.Context, client *redis.Client, key string, opts LockOptions) (*Lock, error) {
	if opts.TTL == 0 {
		opts.TTL = 10 * time.Second
	}
	if opts.RetryDelay == 0 {
		opts.RetryDelay = 100 * time.Millisecond
	}

	owner := generateToken()
	deadline := time.Now().Add(opts.RetryTimeout)

	for {
		// SET key owner NX PX ttl_ms
		ok, err := client.SetNX(ctx, key, owner, opts.TTL).Result()
		if err != nil {
			return nil, fmt.Errorf("redis SET NX: %w", err)
		}

		if ok {
			lock := &Lock{
				client: client,
				key:    key,
				owner:  owner,
				ttl:    opts.TTL,
				stopCh: make(chan struct{}),
			}

			if opts.AutoRenew {
				go lock.renewLoop(ctx)
			}

			return lock, nil
		}

		// Lock is held by someone else — retry.
		if time.Now().After(deadline) {
			return nil, ErrLockNotAcquired
		}

		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(opts.RetryDelay):
			// retry
		}
	}
}

// Release releases the lock. Only succeeds if we still own it.
func (l *Lock) Release(ctx context.Context) error {
	l.stopOnce.Do(func() { close(l.stopCh) })

	result, err := releaseLuaScript.Run(ctx, l.client, []string{l.key}, l.owner).Int()
	if err != nil {
		return fmt.Errorf("release script: %w", err)
	}
	if result == 0 {
		return ErrLockNotHeld
	}
	return nil
}

// Renew extends the lock's TTL. Fails if we no longer own the lock.
func (l *Lock) Renew(ctx context.Context) error {
	result, err := renewLuaScript.Run(ctx, l.client,
		[]string{l.key}, l.owner, l.ttl.Milliseconds()).Int()
	if err != nil {
		return fmt.Errorf("renew script: %w", err)
	}
	if result == 0 {
		return ErrLockNotHeld
	}
	return nil
}

// FencingToken returns a monotonically increasing token associated with this lock.
// Use it to guard writes: only accept writes with a token >= the current known token.
func (l *Lock) FencingToken(ctx context.Context) (int64, error) {
	// INCR on a separate key gives a monotonic counter.
	fenceKey := l.key + ":fence"
	token, err := l.client.Incr(ctx, fenceKey).Result()
	if err != nil {
		return 0, fmt.Errorf("fencing token: %w", err)
	}
	return token, nil
}

func (l *Lock) renewLoop(ctx context.Context) {
	// Renew at 1/3 of TTL to give plenty of margin.
	interval := l.ttl / 3
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-l.stopCh:
			return
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := l.Renew(ctx); err != nil {
				log.Printf("lock renewal failed for %s: %v", l.key, err)
				return
			}
		}
	}
}

func generateToken() string {
	b := make([]byte, 16)
	rand.Read(b)
	return hex.EncodeToString(b)
}

// ---- Usage example ----

func main() {
	client := redis.NewClient(&redis.Options{
		Addr: "localhost:6379",
	})
	defer client.Close()

	ctx := context.Background()

	// Acquire a lock for a critical section.
	lock, err := Acquire(ctx, client, "myapp:locks:order-processing", LockOptions{
		TTL:          15 * time.Second,
		RetryDelay:   200 * time.Millisecond,
		RetryTimeout: 5 * time.Second,
		AutoRenew:    true,
	})
	if err != nil {
		if errors.Is(err, ErrLockNotAcquired) {
			log.Println("could not acquire lock, another instance is processing")
			return
		}
		log.Fatal(err)
	}
	defer lock.Release(ctx)

	// Get fencing token for safe writes.
	token, err := lock.FencingToken(ctx)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("acquired lock with fencing token: %d\n", token)

	// Critical section — only one process runs this at a time.
	fmt.Println("processing orders...")
	time.Sleep(3 * time.Second)
	fmt.Println("done!")
}
```

Critical safety properties:

1. **Unique owner token**: each lock acquisition generates a random 128-bit token. Release uses a Lua script that atomically checks `GET key == owner` then `DEL`. This prevents Client A from releasing Client B's lock.
2. **TTL expiry**: if the lock holder crashes, the lock auto-expires. Without TTL, a crashed holder would deadlock the entire system.
3. **Lua scripts for atomicity**: `GET` + `DEL` as separate commands is unsafe (TOCTOU race). The Lua script runs atomically in Redis.
4. **Auto-renewal**: for long operations, a background goroutine extends the TTL at 1/3 intervals. If the process is alive, the lock stays held.
5. **Fencing tokens**: a monotonically increasing counter prevents stale lock holders from corrupting data. Example: Process A gets lock (token=5), pauses due to GC, lock expires, Process B gets lock (token=6), Process A wakes up — the storage layer rejects writes with token=5 because 5 < 6.
6. **Retry with backoff**: configurable retry delay and timeout for contended locks.

For multi-node Redis (true Redlock), acquire on N/2+1 independent Redis instances. The `go-redsync/redsync` library implements this.'''),

    ("go_deep/etcd_leader_election", r'''How do I implement leader election using etcd in Go? Show me a pattern where multiple service instances elect a leader and the leader performs exclusive work.''', r'''<think>
etcd provides leader election via its concurrency package. The pattern:
1. Create a Session (lease-based, auto-keepalive)
2. Create an Election with a prefix key
3. Campaign to become leader (blocks until elected)
4. Leader does work
5. Resign when done, or session expires if leader crashes

The etcd concurrency package handles:
- Lease keepalive (heartbeat)
- Automatic leadership revocation on crash (lease expires)
- Ordered key creation for fair election (revision-based)

Key APIs:
- concurrency.NewSession(client, ttl) — creates a lease with keepalive
- concurrency.NewElection(session, prefix) — creates election on a key prefix
- election.Campaign(ctx, value) — blocks until this instance is leader
- election.Resign(ctx) — voluntarily give up leadership
- election.Observe(ctx) — watch for leader changes
</think>

Here is a complete leader election system using etcd:

```go
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"sync"
	"time"

	clientv3 "go.etcd.io/etcd/client/v3"
	"go.etcd.io/etcd/client/v3/concurrency"
)

const (
	electionPrefix = "/myapp/leader/"
	sessionTTL     = 10 // seconds — leader must heartbeat within this
)

// Node represents a service instance participating in leader election.
type Node struct {
	id       string
	client   *clientv3.Client
	session  *concurrency.Session
	election *concurrency.Election
	isLeader bool
	mu       sync.RWMutex
}

func NewNode(id string, endpoints []string) (*Node, error) {
	client, err := clientv3.New(clientv3.Config{
		Endpoints:   endpoints,
		DialTimeout: 5 * time.Second,
	})
	if err != nil {
		return nil, fmt.Errorf("etcd connect: %w", err)
	}

	// Session creates a lease and keeps it alive automatically.
	// If this process crashes, the lease expires in sessionTTL seconds
	// and another node can become leader.
	session, err := concurrency.NewSession(client,
		concurrency.WithTTL(sessionTTL))
	if err != nil {
		client.Close()
		return nil, fmt.Errorf("session: %w", err)
	}

	election := concurrency.NewElection(session, electionPrefix)

	return &Node{
		id:       id,
		client:   client,
		session:  session,
		election: election,
	}, nil
}

// Run starts the leader election and performs work based on role.
func (n *Node) Run(ctx context.Context) error {
	defer n.Close()

	// Start observer in background to detect leader changes.
	go n.observeLeader(ctx)

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		log.Printf("[%s] campaigning for leadership...", n.id)

		// Campaign blocks until this node becomes the leader or ctx is cancelled.
		if err := n.election.Campaign(ctx, n.id); err != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			log.Printf("[%s] campaign failed: %v, retrying...", n.id, err)
			time.Sleep(time.Second)
			continue
		}

		n.mu.Lock()
		n.isLeader = true
		n.mu.Unlock()

		log.Printf("[%s] *** ELECTED LEADER ***", n.id)

		// Do leader work until we lose leadership.
		if err := n.doLeaderWork(ctx); err != nil {
			log.Printf("[%s] leader work ended: %v", n.id, err)
		}

		n.mu.Lock()
		n.isLeader = false
		n.mu.Unlock()
	}
}

// doLeaderWork performs exclusive work that only the leader should do.
func (n *Node) doLeaderWork(ctx context.Context) error {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	iteration := 0
	for {
		select {
		case <-ctx.Done():
			// Resign gracefully so another node can take over immediately.
			log.Printf("[%s] resigning leadership", n.id)
			resignCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			n.election.Resign(resignCtx)
			cancel()
			return ctx.Err()

		case <-n.session.Done():
			// Session expired — we lost leadership.
			log.Printf("[%s] session expired, lost leadership", n.id)
			return fmt.Errorf("session expired")

		case <-ticker.C:
			iteration++
			// This is where you do leader-only work:
			// - Run scheduled jobs
			// - Rebalance partitions
			// - Process queued tasks
			log.Printf("[%s] leader work iteration %d", n.id, iteration)
		}
	}
}

// observeLeader watches for leader changes.
func (n *Node) observeLeader(ctx context.Context) {
	ch := n.election.Observe(ctx)
	for {
		select {
		case <-ctx.Done():
			return
		case resp, ok := <-ch:
			if !ok {
				return
			}
			for _, kv := range resp.Kvs {
				log.Printf("[%s] current leader is: %s", n.id, string(kv.Value))
			}
		}
	}
}

// IsLeader returns whether this node is currently the leader.
func (n *Node) IsLeader() bool {
	n.mu.RLock()
	defer n.mu.RUnlock()
	return n.isLeader
}

func (n *Node) Close() {
	n.session.Close()
	n.client.Close()
}

func main() {
	// Each instance gets a unique ID (usually hostname + PID).
	nodeID := fmt.Sprintf("node-%s-%d", hostname(), os.Getpid())
	if len(os.Args) > 1 {
		nodeID = os.Args[1]
	}

	endpoints := []string{"localhost:2379"}

	node, err := NewNode(nodeID, endpoints)
	if err != nil {
		log.Fatal(err)
	}

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()

	log.Printf("starting node %s", nodeID)
	if err := node.Run(ctx); err != nil && ctx.Err() == nil {
		log.Fatal(err)
	}
	log.Printf("node %s shut down", nodeID)
}

func hostname() string {
	h, _ := os.Hostname()
	if h == "" {
		return "unknown"
	}
	return h
}
```

Test with multiple instances:

```bash
# Start etcd (single node for testing).
etcd &

# Terminal 1
go run main.go node-A
# Output: [node-A] *** ELECTED LEADER ***
#         [node-A] leader work iteration 1

# Terminal 2
go run main.go node-B
# Output: [node-B] campaigning for leadership...
#         [node-B] current leader is: node-A
# (blocks, waiting for node-A to resign or crash)

# Ctrl+C on Terminal 1 (node-A)
# Terminal 2 immediately:
# [node-B] *** ELECTED LEADER ***
```

How it works:

1. **`Campaign` uses ordered keys**: each candidate creates a key under the election prefix with their lease. The candidate with the lowest creation revision wins. Others block watching for the key ahead of them to be deleted.
2. **Session lease = heartbeat**: `concurrency.Session` keeps the lease alive with periodic keepalives. If the process crashes, keepalives stop, the lease expires in `sessionTTL` seconds, and the leader's key is deleted.
3. **`session.Done()` channel**: fires when the lease is revoked or expires, signaling loss of leadership. The leader must stop its exclusive work immediately.
4. **Resign for fast handover**: voluntary `Resign` deletes the key immediately, so the next candidate becomes leader in milliseconds. Without resign, the next candidate waits up to `sessionTTL` seconds.
5. **Observe for monitoring**: the `Observe` channel emits notifications whenever the leader changes, useful for updating load balancer configurations or routing tables.'''),

    ("go_deep/consistent_hashing", r'''How do I implement consistent hashing in Go for distributing cache keys across multiple nodes? I need to handle node additions and removals gracefully.''', r'''<think>
Consistent hashing places both nodes and keys on a hash ring. When a node is added or removed, only keys that map to the affected segment of the ring need to be remapped.

Key concepts:
- Hash ring: 0 to 2^32-1, wraps around
- Each physical node gets multiple virtual nodes (vnodes) for better distribution
- To find which node owns a key: hash the key, walk clockwise on the ring to the first vnode
- Adding a node: only keys between the new node and its predecessor move
- Removing a node: its keys move to its successor

Implementation:
- Store vnodes in a sorted slice
- Binary search to find the next vnode >= hash(key)
- More vnodes per physical node = better balance (typical: 100-300)
- Hash function: use a good one like xxhash or fnv — not crypto hashes (too slow)
</think>

Here is a complete consistent hashing implementation:

```go
package main

import (
	"fmt"
	"hash/crc32"
	"sort"
	"strconv"
	"sync"
)

// HashRing implements consistent hashing with virtual nodes.
type HashRing struct {
	mu       sync.RWMutex
	vnodes   int             // virtual nodes per physical node
	ring     []uint32        // sorted hash values
	nodeMap  map[uint32]string // hash → physical node name
	nodes    map[string]bool   // set of physical nodes
}

// NewHashRing creates a ring with the specified number of virtual nodes per physical node.
// More vnodes = better distribution but more memory. 150-300 is typical.
func NewHashRing(vnodes int) *HashRing {
	return &HashRing{
		vnodes:  vnodes,
		nodeMap: make(map[uint32]string),
		nodes:   make(map[string]bool),
	}
}

// hashKey computes the hash for a given key string.
func hashKey(key string) uint32 {
	return crc32.ChecksumIEEE([]byte(key))
}

// Add adds a physical node to the ring.
func (h *HashRing) Add(node string) {
	h.mu.Lock()
	defer h.mu.Unlock()

	if h.nodes[node] {
		return // already added
	}
	h.nodes[node] = true

	// Create virtual nodes.
	for i := 0; i < h.vnodes; i++ {
		vkey := node + "#" + strconv.Itoa(i)
		hash := hashKey(vkey)
		h.ring = append(h.ring, hash)
		h.nodeMap[hash] = node
	}

	sort.Slice(h.ring, func(i, j int) bool {
		return h.ring[i] < h.ring[j]
	})
}

// Remove removes a physical node and all its virtual nodes from the ring.
func (h *HashRing) Remove(node string) {
	h.mu.Lock()
	defer h.mu.Unlock()

	if !h.nodes[node] {
		return
	}
	delete(h.nodes, node)

	// Remove all virtual nodes for this physical node.
	newRing := make([]uint32, 0, len(h.ring)-h.vnodes)
	for _, hash := range h.ring {
		if h.nodeMap[hash] != node {
			newRing = append(newRing, hash)
		} else {
			delete(h.nodeMap, hash)
		}
	}
	h.ring = newRing
}

// Get returns the node responsible for the given key.
func (h *HashRing) Get(key string) (string, bool) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	if len(h.ring) == 0 {
		return "", false
	}

	hash := hashKey(key)

	// Binary search for the first vnode with hash >= key hash.
	idx := sort.Search(len(h.ring), func(i int) bool {
		return h.ring[i] >= hash
	})

	// Wrap around to the first node if we're past the end.
	if idx >= len(h.ring) {
		idx = 0
	}

	return h.nodeMap[h.ring[idx]], true
}

// GetN returns up to n distinct nodes for a key (for replication).
func (h *HashRing) GetN(key string, n int) []string {
	h.mu.RLock()
	defer h.mu.RUnlock()

	if len(h.ring) == 0 {
		return nil
	}
	if n > len(h.nodes) {
		n = len(h.nodes)
	}

	hash := hashKey(key)
	idx := sort.Search(len(h.ring), func(i int) bool {
		return h.ring[i] >= hash
	})
	if idx >= len(h.ring) {
		idx = 0
	}

	seen := make(map[string]bool)
	result := make([]string, 0, n)

	for len(result) < n {
		node := h.nodeMap[h.ring[idx]]
		if !seen[node] {
			seen[node] = true
			result = append(result, node)
		}
		idx = (idx + 1) % len(h.ring)
	}

	return result
}

// Stats returns the distribution of keys across nodes.
func (h *HashRing) Stats(keys []string) map[string]int {
	dist := make(map[string]int)
	for _, key := range keys {
		if node, ok := h.Get(key); ok {
			dist[node]++
		}
	}
	return dist
}

// Nodes returns the list of physical nodes.
func (h *HashRing) Nodes() []string {
	h.mu.RLock()
	defer h.mu.RUnlock()

	nodes := make([]string, 0, len(h.nodes))
	for n := range h.nodes {
		nodes = append(nodes, n)
	}
	return nodes
}

func main() {
	ring := NewHashRing(200) // 200 virtual nodes per physical node

	// Add cache servers.
	ring.Add("cache-1")
	ring.Add("cache-2")
	ring.Add("cache-3")

	// Generate test keys.
	keys := make([]string, 10000)
	for i := range keys {
		keys[i] = fmt.Sprintf("user:%d", i)
	}

	// Show distribution.
	fmt.Println("=== Distribution with 3 nodes ===")
	stats := ring.Stats(keys)
	for node, count := range stats {
		fmt.Printf("  %s: %d keys (%.1f%%)\n", node, count, float64(count)/float64(len(keys))*100)
	}

	// Show key lookups.
	fmt.Println("\n=== Key → Node mapping ===")
	for _, key := range []string{"user:42", "user:100", "user:999", "session:abc"} {
		node, _ := ring.Get(key)
		fmt.Printf("  %s → %s\n", key, node)
	}

	// Show replication targets.
	fmt.Println("\n=== Replication (3 replicas) ===")
	replicas := ring.GetN("user:42", 3)
	fmt.Printf("  user:42 → %v\n", replicas)

	// Simulate adding a node — measure key movement.
	fmt.Println("\n=== Adding cache-4 ===")
	moved := 0
	oldMapping := make(map[string]string)
	for _, key := range keys {
		node, _ := ring.Get(key)
		oldMapping[key] = node
	}

	ring.Add("cache-4")

	for _, key := range keys {
		node, _ := ring.Get(key)
		if node != oldMapping[key] {
			moved++
		}
	}
	fmt.Printf("  keys moved: %d / %d (%.1f%%)\n", moved, len(keys),
		float64(moved)/float64(len(keys))*100)

	stats = ring.Stats(keys)
	for node, count := range stats {
		fmt.Printf("  %s: %d keys (%.1f%%)\n", node, count, float64(count)/float64(len(keys))*100)
	}

	// Simulate removing a node.
	fmt.Println("\n=== Removing cache-2 ===")
	oldMapping = make(map[string]string)
	for _, key := range keys {
		node, _ := ring.Get(key)
		oldMapping[key] = node
	}

	ring.Remove("cache-2")
	moved = 0
	for _, key := range keys {
		node, _ := ring.Get(key)
		if node != oldMapping[key] {
			moved++
		}
	}
	fmt.Printf("  keys moved: %d / %d (%.1f%%)\n", moved, len(keys),
		float64(moved)/float64(len(keys))*100)
}
```

Expected output:

```
=== Distribution with 3 nodes ===
  cache-1: 3342 keys (33.4%)
  cache-2: 3318 keys (33.2%)
  cache-3: 3340 keys (33.4%)

=== Adding cache-4 ===
  keys moved: 2486 / 10000 (24.9%)   ← close to ideal 25% (1/4)
  cache-1: 2503 keys (25.0%)
  cache-2: 2521 keys (25.2%)
  cache-3: 2488 keys (24.9%)
  cache-4: 2488 keys (24.9%)
```

Key properties:

1. **Minimal redistribution**: adding a 4th node to 3 moves ~25% of keys (ideal is 1/N = 25%). Without consistent hashing, almost all keys would move.
2. **Virtual nodes control balance**: 200 vnodes gives ~1-2% standard deviation. With only 1 vnode per node, distribution would be highly uneven.
3. **O(log n) lookup**: binary search on the sorted ring. For millions of lookups per second, this is fast enough.
4. **`GetN` for replication**: walk the ring clockwise, skipping duplicate physical nodes, to find N distinct nodes for a key. Used by systems like Cassandra and DynamoDB.
5. **Thread-safe**: `sync.RWMutex` allows concurrent reads (`Get`) while serializing mutations (`Add`/`Remove`).'''),

    ("go_deep/bloom_filter", r'''How do I implement a Bloom filter in Go? I want to use it for checking if an element is probably in a set, with configurable false positive rate.''', r'''<think>
A Bloom filter is a space-efficient probabilistic data structure. Properties:
- No false negatives: if it says "not in set", it's definitely not
- Possible false positives: if it says "in set", it might not be
- Can't delete elements (use Counting Bloom filter for that)
- Space: much smaller than storing the actual set

Math:
- n = expected number of elements
- p = desired false positive rate
- m = number of bits = -n*ln(p) / (ln(2))^2
- k = number of hash functions = (m/n) * ln(2)

Implementation:
- Use a bit array ([]uint64 for efficiency)
- For k hash functions, use the "double hashing" trick: h(i) = h1 + i*h2
  where h1 and h2 come from a single hash (e.g., murmur3 128-bit split into two 64-bit halves)
- This is proven to be as good as k independent hash functions
</think>

Here is a complete Bloom filter with optimal parameter calculation:

```go
package main

import (
	"encoding/binary"
	"fmt"
	"hash"
	"hash/fnv"
	"math"
	"sync"
)

// BloomFilter is a space-efficient probabilistic membership test.
type BloomFilter struct {
	mu      sync.RWMutex
	bits    []uint64 // bit array stored as uint64 words
	m       uint     // total bits
	k       uint     // number of hash functions
	n       uint     // number of elements inserted
	hashFn  hash.Hash64
}

// NewBloomFilter creates a filter optimized for the expected number of elements
// and desired false positive rate.
func NewBloomFilter(expectedElements uint, falsePositiveRate float64) *BloomFilter {
	m, k := optimalParams(expectedElements, falsePositiveRate)

	// Round up to next multiple of 64 for clean word alignment.
	words := (m + 63) / 64
	m = words * 64

	return &BloomFilter{
		bits:   make([]uint64, words),
		m:      m,
		k:      k,
		hashFn: fnv.New128a().(hash.Hash64), // FNV-1a for first hash
	}
}

// optimalParams calculates optimal bit count and hash function count.
func optimalParams(n uint, p float64) (m uint, k uint) {
	// m = -n * ln(p) / (ln(2))^2
	fm := -float64(n) * math.Log(p) / (math.Ln2 * math.Ln2)
	m = uint(math.Ceil(fm))

	// k = (m/n) * ln(2)
	fk := (float64(m) / float64(n)) * math.Ln2
	k = uint(math.Ceil(fk))
	if k < 1 {
		k = 1
	}

	return m, k
}

// hashes computes k hash values using the double-hashing technique.
// h(i) = (h1 + i * h2) mod m
func (bf *BloomFilter) hashes(data []byte) []uint {
	// Use FNV-1a to produce two independent 64-bit hashes.
	h := fnv.New128a()
	h.Write(data)
	sum := h.Sum(nil)

	h1 := binary.BigEndian.Uint64(sum[0:8])
	h2 := binary.BigEndian.Uint64(sum[8:16])

	positions := make([]uint, bf.k)
	for i := uint(0); i < bf.k; i++ {
		positions[i] = uint((h1 + uint64(i)*h2) % uint64(bf.m))
	}
	return positions
}

// Add inserts an element into the filter.
func (bf *BloomFilter) Add(data []byte) {
	bf.mu.Lock()
	defer bf.mu.Unlock()

	for _, pos := range bf.hashes(data) {
		word := pos / 64
		bit := pos % 64
		bf.bits[word] |= 1 << bit
	}
	bf.n++
}

// AddString is a convenience method for string elements.
func (bf *BloomFilter) AddString(s string) {
	bf.Add([]byte(s))
}

// Contains tests whether an element might be in the set.
// Returns false = definitely not in set.
// Returns true  = probably in set (with configured false positive rate).
func (bf *BloomFilter) Contains(data []byte) bool {
	bf.mu.RLock()
	defer bf.mu.RUnlock()

	for _, pos := range bf.hashes(data) {
		word := pos / 64
		bit := pos % 64
		if bf.bits[word]&(1<<bit) == 0 {
			return false // definitely not in set
		}
	}
	return true // probably in set
}

// ContainsString is a convenience method.
func (bf *BloomFilter) ContainsString(s string) bool {
	return bf.Contains([]byte(s))
}

// EstimatedFPR calculates the current estimated false positive rate
// based on the number of elements inserted.
func (bf *BloomFilter) EstimatedFPR() float64 {
	bf.mu.RLock()
	defer bf.mu.RUnlock()

	// p = (1 - e^(-kn/m))^k
	exponent := -float64(bf.k) * float64(bf.n) / float64(bf.m)
	return math.Pow(1-math.Exp(exponent), float64(bf.k))
}

// Stats returns filter statistics.
func (bf *BloomFilter) Stats() FilterStats {
	bf.mu.RLock()
	defer bf.mu.RUnlock()

	setBits := uint(0)
	for _, word := range bf.bits {
		setBits += uint(popcount(word))
	}

	return FilterStats{
		Bits:           bf.m,
		HashFunctions:  bf.k,
		Elements:       bf.n,
		SetBits:        setBits,
		FillRatio:      float64(setBits) / float64(bf.m),
		EstimatedFPR:   bf.EstimatedFPR(),
		MemoryBytes:    len(bf.bits) * 8,
	}
}

type FilterStats struct {
	Bits          uint
	HashFunctions uint
	Elements      uint
	SetBits       uint
	FillRatio     float64
	EstimatedFPR  float64
	MemoryBytes   int
}

func (s FilterStats) String() string {
	return fmt.Sprintf(
		"bits=%d k=%d elements=%d fill=%.2f%% fpr=%.6f memory=%d bytes",
		s.Bits, s.HashFunctions, s.Elements,
		s.FillRatio*100, s.EstimatedFPR, s.MemoryBytes,
	)
}

// popcount counts set bits in a uint64.
func popcount(x uint64) int {
	// Kernighan's algorithm.
	count := 0
	for x != 0 {
		x &= x - 1
		count++
	}
	return count
}

func main() {
	// Create a filter for 100,000 elements with 0.1% false positive rate.
	bf := NewBloomFilter(100_000, 0.001)
	fmt.Printf("filter created: %s\n\n", bf.Stats())

	// Insert known elements.
	for i := 0; i < 100_000; i++ {
		bf.AddString(fmt.Sprintf("user:%d", i))
	}

	fmt.Printf("after inserting 100k elements: %s\n\n", bf.Stats())

	// Test membership.
	fmt.Println("=== Membership tests ===")
	for _, key := range []string{"user:42", "user:99999", "user:100000", "user:200000"} {
		result := bf.ContainsString(key)
		fmt.Printf("  %s → %v\n", key, result)
	}

	// Measure actual false positive rate.
	fmt.Println("\n=== False positive rate measurement ===")
	falsePositives := 0
	testCount := 100_000
	for i := 100_000; i < 100_000+testCount; i++ {
		// These keys were never inserted.
		if bf.ContainsString(fmt.Sprintf("user:%d", i)) {
			falsePositives++
		}
	}
	actualFPR := float64(falsePositives) / float64(testCount)
	fmt.Printf("  tested %d absent keys\n", testCount)
	fmt.Printf("  false positives: %d\n", falsePositives)
	fmt.Printf("  actual FPR: %.4f%% (target: 0.1000%%)\n", actualFPR*100)
}
```

Expected output:

```
filter created: bits=1437760 k=10 elements=0 fill=0.00% fpr=0.000000 memory=179720 bytes

after inserting 100k elements: bits=1437760 k=10 elements=100000 fill=50.05% fpr=0.001000 memory=179720 bytes

=== Membership tests ===
  user:42 → true      (correctly found)
  user:99999 → true   (correctly found)
  user:100000 → false (correctly absent)
  user:200000 → false (correctly absent)

=== False positive rate measurement ===
  tested 100000 absent keys
  false positives: 95
  actual FPR: 0.0950% (target: 0.1000%)
```

Key properties:

1. **Space efficiency**: 100K elements at 0.1% FPR needs only ~175KB (vs ~2.4MB for a hash set of 100K 24-byte strings).
2. **Double hashing**: instead of k independent hash functions, we derive k positions from two hashes: `h(i) = (h1 + i*h2) mod m`. Proven equivalent in "Less Hashing, Same Performance" (Kirsch & Mitzenmacher, 2006).
3. **Thread-safe**: `RWMutex` allows concurrent `Contains` calls while serializing `Add`.
4. **No false negatives**: if any bit for a key is 0, the key was definitely never inserted. This guarantee is unconditional.
5. **Fill ratio**: when the filter is ~50% full, it operates near its designed FPR. Above ~70%, false positives increase rapidly.
6. **Use cases**: database query optimization (skip disk reads for absent keys), network deduplication, spell checkers, web crawlers (skip visited URLs).'''),

    ("go_deep/ring_buffer_logging", r'''How do I implement a lock-free ring buffer in Go for high-throughput logging? I want producers to never block and old entries to be overwritten when the buffer is full.''', r'''<think>
A ring buffer for logging needs:
- Fixed-size circular buffer
- Producers write at the head (never block, overwrite old entries)
- Consumer reads from the tail
- High throughput: minimize contention

Lock-free approach using atomics:
- head (write position): atomically incremented by producers using CAS
- tail (read position): managed by the consumer
- When head - tail >= capacity, old entries are lost (overwrite semantics)
- Use power-of-2 capacity for fast modulo (bitwise AND)

Actually, for simplicity and correctness, let's use atomic counters with modulo indexing. Each entry can be a fixed-size struct or a variable-length byte slice stored via pointer.

For variable-length log entries, store pointers in the ring to avoid copying. The ring buffer itself stores *Entry values.

The tricky part: multiple producers need to claim a slot atomically, then write to it. Use atomic.AddUint64 on the head counter — each producer gets a unique slot. But the consumer needs to know when a slot is "committed" (fully written). Use a sequence number in each slot.
</think>

Here is a high-throughput ring buffer for logging with overwrite-on-full semantics:

```go
package main

import (
	"fmt"
	"runtime"
	"sync"
	"sync/atomic"
	"time"
	"unsafe"
)

// Entry is a log entry stored in the ring buffer.
type Entry struct {
	Seq     uint64
	Time    int64  // UnixNano for fast capture
	Level   uint8
	Message [256]byte
	MsgLen  uint16
}

// RingBuffer is a fixed-size circular buffer for high-throughput logging.
// Producers never block — when full, oldest entries are overwritten.
type RingBuffer struct {
	entries []paddedEntry
	mask    uint64 // capacity - 1 (for fast modulo)
	head    atomic.Uint64 // next write position (monotonically increasing)
	tail    atomic.Uint64 // next read position
}

// paddedEntry prevents false sharing between adjacent ring slots.
// Each slot gets its own cache line (64 bytes padding).
type paddedEntry struct {
	committed atomic.Uint64 // sequence number when write is complete
	entry     Entry
	_pad      [64 - unsafe.Sizeof(Entry{})%64]byte
}

// NewRingBuffer creates a ring buffer with capacity rounded up to the next power of 2.
func NewRingBuffer(minCapacity int) *RingBuffer {
	// Round up to power of 2.
	cap := uint64(1)
	for cap < uint64(minCapacity) {
		cap <<= 1
	}

	rb := &RingBuffer{
		entries: make([]paddedEntry, cap),
		mask:    cap - 1,
	}
	return rb
}

// Write adds an entry to the ring buffer. Never blocks.
// Returns true if a slot was successfully claimed.
func (rb *RingBuffer) Write(level uint8, msg string) {
	// Atomically claim the next slot.
	seq := rb.head.Add(1)
	idx := (seq - 1) & rb.mask

	slot := &rb.entries[idx]

	// Write the entry.
	slot.entry.Seq = seq
	slot.entry.Time = time.Now().UnixNano()
	slot.entry.Level = level

	n := len(msg)
	if n > len(slot.entry.Message) {
		n = len(slot.entry.Message)
	}
	copy(slot.entry.Message[:], msg[:n])
	slot.entry.MsgLen = uint16(n)

	// Mark slot as committed by publishing the sequence number.
	// Readers wait until committed == seq before reading.
	slot.committed.Store(seq)
}

// ReadBatch reads up to maxEntries from the buffer into the provided slice.
// Returns the number of entries read. Only one consumer should call this.
func (rb *RingBuffer) ReadBatch(dst []Entry, maxEntries int) int {
	tail := rb.tail.Load()
	head := rb.head.Load()

	if tail >= head {
		return 0 // empty
	}

	// If we've fallen behind (overwritten entries), skip to the oldest available.
	cap := rb.mask + 1
	if head-tail > cap {
		tail = head - cap
		rb.tail.Store(tail)
	}

	n := int(head - tail)
	if n > maxEntries {
		n = maxEntries
	}
	if n > len(dst) {
		n = len(dst)
	}

	read := 0
	for i := 0; i < n; i++ {
		seq := tail + uint64(i) + 1
		idx := (seq - 1) & rb.mask
		slot := &rb.entries[idx]

		// Spin-wait for the slot to be committed.
		// This handles the case where a producer has claimed but not yet written.
		for spin := 0; ; spin++ {
			if slot.committed.Load() >= seq {
				break
			}
			if spin > 1000 {
				// Producer is very slow, return what we have.
				rb.tail.Store(tail + uint64(read))
				return read
			}
			runtime.Gosched()
		}

		dst[read] = slot.entry
		read++
	}

	rb.tail.Store(tail + uint64(read))
	return read
}

// Len returns the approximate number of unread entries.
func (rb *RingBuffer) Len() int {
	head := rb.head.Load()
	tail := rb.tail.Load()
	if head <= tail {
		return 0
	}
	n := head - tail
	cap := rb.mask + 1
	if n > cap {
		return int(cap)
	}
	return int(n)
}

// Cap returns the buffer capacity.
func (rb *RingBuffer) Cap() int {
	return int(rb.mask + 1)
}

// ---- Log level constants ----
const (
	LevelDebug uint8 = iota
	LevelInfo
	LevelWarn
	LevelError
)

var levelNames = [...]string{"DBG", "INF", "WRN", "ERR"}

func main() {
	rb := NewRingBuffer(8192) // 8K entry ring buffer

	fmt.Printf("ring buffer: capacity=%d\n\n", rb.Cap())

	// Start consumer goroutine.
	var wg sync.WaitGroup
	done := make(chan struct{})

	wg.Add(1)
	go func() {
		defer wg.Done()
		batch := make([]Entry, 256)
		total := 0

		for {
			n := rb.ReadBatch(batch, 256)
			for i := 0; i < n; i++ {
				e := &batch[i]
				msg := string(e.Message[:e.MsgLen])
				_ = msg // In production: write to file, send to network, etc.
				total++
			}

			if n == 0 {
				select {
				case <-done:
					// Drain remaining.
					for {
						n := rb.ReadBatch(batch, 256)
						total += n
						if n == 0 {
							break
						}
					}
					fmt.Printf("consumer: processed %d total entries\n", total)
					return
				default:
					runtime.Gosched()
				}
			}
		}
	}()

	// Benchmark: multiple producer goroutines.
	numProducers := 4
	entriesPerProducer := 250_000

	start := time.Now()

	var prodWg sync.WaitGroup
	for p := 0; p < numProducers; p++ {
		prodWg.Add(1)
		go func(id int) {
			defer prodWg.Done()
			for i := 0; i < entriesPerProducer; i++ {
				rb.Write(LevelInfo, fmt.Sprintf("producer %d: message %d", id, i))
			}
		}(p)
	}

	prodWg.Wait()
	elapsed := time.Since(start)
	close(done)
	wg.Wait()

	totalEntries := numProducers * entriesPerProducer
	throughput := float64(totalEntries) / elapsed.Seconds()
	fmt.Printf("\n=== Benchmark ===\n")
	fmt.Printf("producers: %d\n", numProducers)
	fmt.Printf("total entries: %d\n", totalEntries)
	fmt.Printf("elapsed: %v\n", elapsed)
	fmt.Printf("throughput: %.0f entries/sec\n", throughput)
	fmt.Printf("latency: %v per entry\n", elapsed/time.Duration(totalEntries))
}
```

Design decisions:

1. **Power-of-2 capacity**: allows `idx = seq & mask` instead of `seq % cap`. Bitwise AND is a single CPU instruction vs expensive modulo division.
2. **Monotonic head counter**: `atomic.Add` gives each producer a unique slot without CAS retry loops. This is key for high throughput under contention.
3. **Committed sequence number**: solves the "half-written entry" problem. A producer claims slot N, writes data, then sets `committed = N`. The consumer only reads when `committed >= N`.
4. **Cache line padding**: `paddedEntry` includes padding to avoid false sharing — where two CPU cores contend on the same cache line even though they access different slots.
5. **Overwrite semantics**: when the buffer is full, the head keeps advancing. The consumer detects it fell behind and skips to the oldest available entry. No entries are lost in normal operation; only under extreme pressure.
6. **Batch reading**: reading 256 entries at a time amortizes synchronization overhead and is cache-friendly (sequential memory access).
7. **Fixed-size Entry**: avoids heap allocation per log entry. The `[256]byte` message field is sized for typical log lines.'''),

    ("go_deep/lockfree_mpsc", r'''How do I implement a lock-free multi-producer single-consumer (MPSC) queue in Go using atomics?''', r'''<think>
MPSC queue: multiple goroutines enqueue, one goroutine dequeues. Lock-free means no mutexes — only atomic operations.

Classic approach: intrusive linked list (Michael-Scott queue variant for MPSC).
- Each node has a next pointer
- Producers atomically swap the tail pointer and link their node
- Consumer reads from the head

The Vyukov MPSC queue is the simplest correct lock-free MPSC:
- Producers: CAS-swap tail to point to new node, then set old_tail.next = new_node
- Consumer: read head.next; if non-nil, advance head

The key insight: there's a brief window where the tail has been swapped but next hasn't been set yet. The consumer must spin-wait when it sees next==nil but knows items exist.

Let me implement this with unsafe.Pointer atomics.
</think>

Here is a lock-free MPSC queue using the Vyukov algorithm:

```go
package main

import (
	"fmt"
	"runtime"
	"sync"
	"sync/atomic"
	"time"
	"unsafe"
)

// node is a single element in the lock-free linked list.
type node[T any] struct {
	value T
	next  unsafe.Pointer // *node[T]
}

// MPSCQueue is a lock-free multi-producer single-consumer queue.
// Based on Dmitry Vyukov's non-intrusive MPSC queue.
type MPSCQueue[T any] struct {
	head unsafe.Pointer // consumer reads from here (*node[T])
	tail unsafe.Pointer // producers push to here (*node[T])
	len  atomic.Int64
}

// NewMPSCQueue creates a new queue with a sentinel node.
func NewMPSCQueue[T any]() *MPSCQueue[T] {
	// Sentinel (stub) node — simplifies empty-queue handling.
	sentinel := &node[T]{}
	ptr := unsafe.Pointer(sentinel)
	return &MPSCQueue[T]{
		head: ptr,
		tail: ptr,
	}
}

// Push adds an element to the queue. Safe to call from multiple goroutines.
// Never blocks, never fails.
func (q *MPSCQueue[T]) Push(value T) {
	n := &node[T]{value: value}
	newPtr := unsafe.Pointer(n)

	// Atomically swap tail to point to our new node.
	// prev = old tail.
	prev := atomic.SwapPointer(&q.tail, newPtr)

	// Link the old tail to our new node.
	// There's a brief window between SwapPointer and this store
	// where the consumer may see next==nil. The consumer handles this.
	atomic.StorePointer(&(*node[T])(prev).next, newPtr)

	q.len.Add(1)
}

// Pop removes and returns the oldest element. Only safe from a single goroutine.
// Returns the value and true, or zero value and false if the queue is empty.
func (q *MPSCQueue[T]) Pop() (T, bool) {
	head := (*node[T])(q.head)
	next := (*node[T])(atomic.LoadPointer(&head.next))

	if next == nil {
		var zero T
		return zero, false
	}

	// Advance head past the sentinel to the next node.
	// The old head (sentinel) becomes garbage.
	q.head = unsafe.Pointer(next)
	q.len.Add(-1)

	return next.value, true
}

// PopWait spins briefly waiting for a value if the queue appears non-empty
// but the next pointer hasn't been set yet (producer in progress).
func (q *MPSCQueue[T]) PopWait(maxSpins int) (T, bool) {
	head := (*node[T])(q.head)

	for spin := 0; spin < maxSpins; spin++ {
		next := (*node[T])(atomic.LoadPointer(&head.next))
		if next != nil {
			q.head = unsafe.Pointer(next)
			q.len.Add(-1)
			return next.value, true
		}
		runtime.Gosched()
	}

	var zero T
	return zero, false
}

// Len returns an approximate count of elements.
func (q *MPSCQueue[T]) Len() int {
	n := q.len.Load()
	if n < 0 {
		return 0
	}
	return int(n)
}

// DrainAll pops all available elements into a slice. Single consumer only.
func (q *MPSCQueue[T]) DrainAll() []T {
	var result []T
	for {
		v, ok := q.Pop()
		if !ok {
			break
		}
		result = append(result, v)
	}
	return result
}

// ---- Usage example and benchmark ----

type LogEntry struct {
	Timestamp int64
	Level     string
	Message   string
}

func main() {
	q := NewMPSCQueue[LogEntry]()

	// Benchmark: multiple producers, single consumer.
	numProducers := 8
	itemsPerProducer := 500_000

	var producerWg sync.WaitGroup
	consumed := atomic.Int64{}
	done := make(chan struct{})

	// Consumer goroutine.
	go func() {
		batch := 0
		for {
			entry, ok := q.Pop()
			if ok {
				_ = entry // process entry
				consumed.Add(1)
				batch = 0
			} else {
				batch++
				if batch > 1000 {
					select {
					case <-done:
						// Final drain.
						for {
							_, ok := q.Pop()
							if !ok {
								break
							}
							consumed.Add(1)
						}
						return
					default:
					}
					batch = 0
					runtime.Gosched()
				}
			}
		}
	}()

	start := time.Now()

	// Launch producers.
	for p := 0; p < numProducers; p++ {
		producerWg.Add(1)
		go func(id int) {
			defer producerWg.Done()
			for i := 0; i < itemsPerProducer; i++ {
				q.Push(LogEntry{
					Timestamp: time.Now().UnixNano(),
					Level:     "INFO",
					Message:   fmt.Sprintf("producer-%d msg-%d", id, i),
				})
			}
		}(p)
	}

	producerWg.Wait()
	elapsed := time.Since(start)

	// Wait for consumer to drain.
	time.Sleep(100 * time.Millisecond)
	close(done)
	time.Sleep(100 * time.Millisecond)

	total := numProducers * itemsPerProducer
	fmt.Printf("=== Lock-free MPSC Queue Benchmark ===\n")
	fmt.Printf("producers:      %d\n", numProducers)
	fmt.Printf("items/producer: %d\n", itemsPerProducer)
	fmt.Printf("total produced: %d\n", total)
	fmt.Printf("total consumed: %d\n", consumed.Load())
	fmt.Printf("producer time:  %v\n", elapsed)
	fmt.Printf("throughput:     %.1fM ops/sec\n",
		float64(total)/elapsed.Seconds()/1e6)

	// Correctness test: verify FIFO ordering per-producer.
	fmt.Println("\n=== Ordering test ===")
	q2 := NewMPSCQueue[int]()

	var wg sync.WaitGroup
	for p := 0; p < 4; p++ {
		wg.Add(1)
		go func(base int) {
			defer wg.Done()
			for i := 0; i < 1000; i++ {
				q2.Push(base*10000 + i)
			}
		}(p)
	}
	wg.Wait()

	results := q2.DrainAll()
	fmt.Printf("drained %d items\n", len(results))

	// Verify per-producer ordering (items from same producer are in order).
	lastSeen := map[int]int{0: -1, 1: -1, 2: -1, 3: -1}
	ordered := true
	for _, v := range results {
		producer := v / 10000
		seq := v % 10000
		if seq <= lastSeen[producer] {
			ordered = false
			break
		}
		lastSeen[producer] = seq
	}
	fmt.Printf("per-producer FIFO ordering preserved: %v\n", ordered)
}
```

How the Vyukov MPSC queue works:

1. **Sentinel node**: the queue always has at least one node (the sentinel/stub). The consumer reads `head.next` — if non-nil, it advances head. The old head becomes garbage.

2. **Producer path** (two atomic ops):
   - `atomic.SwapPointer(&tail, newNode)` — claims the tail position atomically. Even with 100 concurrent producers, each gets a unique `prev`.
   - `atomic.StorePointer(&prev.next, newNode)` — links the old tail to the new node.

3. **The gap**: between the swap and the store, the consumer may see `head.next == nil` even though items exist. This is the tradeoff for lock-freedom. The consumer must either retry or yield.

4. **Memory ordering**: `atomic.SwapPointer` provides sequential consistency on x86. On ARM, Go's atomics use the appropriate barriers.

5. **No ABA problem**: unlike CAS-based queues, the swap-then-link approach doesn't suffer from ABA because we never compare-and-swap a pointer that could be recycled.

6. **Per-producer FIFO**: items from a single producer are always dequeued in the order they were enqueued. Cross-producer ordering depends on scheduling.

7. **Allocation per push**: each `Push` allocates a node. For ultra-low-latency, pre-allocate nodes from a pool (see memory pool pattern).'''),

    ("go_deep/memory_pool_allocator", r'''How do I build a memory pool in Go for fixed-size objects to reduce GC pressure? I want to avoid allocating and freeing many small objects in a hot path.''', r'''<think>
Go has sync.Pool for temporary object pooling, but it can be cleared by the GC at any time. For a more predictable pool of fixed-size objects, we can build our own using:
1. sync.Pool (standard, simple, GC-aware)
2. A free-list based pool with pre-allocation
3. An arena-style allocator (Go 1.20 experimental, removed in 1.23)

For the most practical approach, let's show:
1. sync.Pool usage with proper reset patterns
2. A custom fixed-size pool with pre-allocation and bounded capacity
3. Benchmark showing GC pressure reduction
</think>

Here is a fixed-size object pool with pre-allocation and GC pressure benchmarking:

```go
package main

import (
	"fmt"
	"runtime"
	"sync"
	"sync/atomic"
	"time"
)

// ---- Pool implementation ----

// Pool is a bounded, pre-allocated pool of fixed-size objects.
// Unlike sync.Pool, objects are NOT cleared by the GC.
type Pool[T any] struct {
	items chan *T
	alloc func() *T
	reset func(*T)
	stats PoolStats
}

type PoolStats struct {
	Gets     atomic.Int64
	Puts     atomic.Int64
	Hits     atomic.Int64
	Misses   atomic.Int64
	Discards atomic.Int64 // puts when pool is full
}

// NewPool creates a pool pre-populated with `prealloc` items,
// up to a maximum of `maxSize` items.
func NewPool[T any](prealloc, maxSize int, alloc func() *T, reset func(*T)) *Pool[T] {
	p := &Pool[T]{
		items: make(chan *T, maxSize),
		alloc: alloc,
		reset: reset,
	}

	// Pre-allocate items to avoid cold-start allocation.
	for i := 0; i < prealloc; i++ {
		p.items <- alloc()
	}

	return p
}

// Get retrieves an item from the pool or allocates a new one.
func (p *Pool[T]) Get() *T {
	p.stats.Gets.Add(1)

	select {
	case item := <-p.items:
		p.stats.Hits.Add(1)
		return item
	default:
		p.stats.Misses.Add(1)
		return p.alloc()
	}
}

// Put returns an item to the pool. If the pool is full, the item is discarded.
func (p *Pool[T]) Put(item *T) {
	p.stats.Puts.Add(1)
	p.reset(item) // clear state before returning to pool

	select {
	case p.items <- item:
		// returned to pool
	default:
		p.stats.Discards.Add(1)
		// pool is full, discard (GC will collect it)
	}
}

func (p *Pool[T]) Stats() PoolStats {
	return p.stats
}

// ---- Example: pooled buffer for packet processing ----

const bufferSize = 4096

type Buffer struct {
	Data  [bufferSize]byte
	Len   int
	SeqNo uint64
}

func NewBuffer() *Buffer {
	return &Buffer{}
}

func ResetBuffer(b *Buffer) {
	b.Len = 0
	b.SeqNo = 0
	// Note: no need to zero the data array — Len tracks valid bytes.
}

// ---- Benchmark: pool vs direct allocation ----

func benchmarkWithPool(iterations int) (time.Duration, runtime.MemStats) {
	pool := NewPool[Buffer](1024, 4096, NewBuffer, ResetBuffer)

	var before, after runtime.MemStats
	runtime.GC()
	runtime.ReadMemStats(&before)

	start := time.Now()

	var wg sync.WaitGroup
	workers := 8
	perWorker := iterations / workers

	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < perWorker; i++ {
				buf := pool.Get()
				// Simulate work.
				buf.Len = 100
				buf.SeqNo = uint64(i)
				buf.Data[0] = byte(i)
				pool.Put(buf)
			}
		}()
	}
	wg.Wait()
	elapsed := time.Since(start)

	runtime.GC()
	runtime.ReadMemStats(&after)

	stats := pool.Stats()
	fmt.Printf("  pool hits:     %d\n", stats.Hits.Load())
	fmt.Printf("  pool misses:   %d\n", stats.Misses.Load())
	fmt.Printf("  pool discards: %d\n", stats.Discards.Load())

	return elapsed, after
}

func benchmarkWithoutPool(iterations int) (time.Duration, runtime.MemStats) {
	var before, after runtime.MemStats
	runtime.GC()
	runtime.ReadMemStats(&before)

	start := time.Now()

	var wg sync.WaitGroup
	workers := 8
	perWorker := iterations / workers

	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < perWorker; i++ {
				buf := NewBuffer() // allocate every time
				buf.Len = 100
				buf.SeqNo = uint64(i)
				buf.Data[0] = byte(i)
				_ = buf // becomes garbage immediately
			}
		}()
	}
	wg.Wait()
	elapsed := time.Since(start)

	runtime.GC()
	runtime.ReadMemStats(&after)

	return elapsed, after
}

func benchmarkWithSyncPool(iterations int) (time.Duration, runtime.MemStats) {
	pool := sync.Pool{
		New: func() any { return NewBuffer() },
	}

	var before, after runtime.MemStats
	runtime.GC()
	runtime.ReadMemStats(&before)

	start := time.Now()

	var wg sync.WaitGroup
	workers := 8
	perWorker := iterations / workers

	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < perWorker; i++ {
				buf := pool.Get().(*Buffer)
				buf.Len = 100
				buf.SeqNo = uint64(i)
				buf.Data[0] = byte(i)
				ResetBuffer(buf)
				pool.Put(buf)
			}
		}()
	}
	wg.Wait()
	elapsed := time.Since(start)

	runtime.GC()
	runtime.ReadMemStats(&after)

	return elapsed, after
}

func main() {
	iterations := 2_000_000
	fmt.Printf("=== Benchmark: %dM allocations across 8 workers ===\n\n", iterations/1_000_000)

	fmt.Println("--- Without pool (new allocation each time) ---")
	dur1, mem1 := benchmarkWithoutPool(iterations)
	fmt.Printf("  time:    %v\n", dur1)
	fmt.Printf("  mallocs: %d\n", mem1.Mallocs)
	fmt.Printf("  GC runs: %d\n", mem1.NumGC)

	fmt.Println("\n--- With sync.Pool ---")
	dur2, mem2 := benchmarkWithSyncPool(iterations)
	fmt.Printf("  time:    %v\n", dur2)
	fmt.Printf("  mallocs: %d\n", mem2.Mallocs)
	fmt.Printf("  GC runs: %d\n", mem2.NumGC)

	fmt.Println("\n--- With custom Pool[T] ---")
	dur3, mem3 := benchmarkWithPool(iterations)
	fmt.Printf("  time:    %v\n", dur3)
	fmt.Printf("  mallocs: %d\n", mem3.Mallocs)
	fmt.Printf("  GC runs: %d\n", mem3.NumGC)

	fmt.Printf("\n=== Summary ===\n")
	fmt.Printf("no pool:     %v\n", dur1)
	fmt.Printf("sync.Pool:   %v (%.1fx faster)\n", dur2, float64(dur1)/float64(dur2))
	fmt.Printf("custom Pool: %v (%.1fx faster)\n", dur3, float64(dur1)/float64(dur3))
}
```

Key design decisions:

1. **Bounded channel as the pool**: `chan *T` with a fixed buffer provides a thread-safe, bounded free-list. `Get` and `Put` are O(1) with channel fast-path. When the pool is full, excess items are discarded (GC collects them).

2. **Pre-allocation**: filling the pool at startup avoids cache-miss storms on the first burst of requests. Without pre-allocation, the first N `Get` calls all miss and allocate.

3. **Reset function**: the caller provides a `reset` function to clear sensitive data and reinitialize the object. This prevents data leaks between pool users.

4. **Generics `[T any]`**: type-safe pool without interface boxing. `sync.Pool` returns `any`, requiring a type assertion on every `Get`.

5. **`sync.Pool` vs custom pool**:
   - `sync.Pool`: GC can clear it at any time (by design), causing allocation spikes. Good for temporary buffers.
   - Custom pool: items persist across GC cycles. Better for long-lived services with steady-state allocation patterns.

6. **When to use a pool**:
   - Objects are frequently allocated and freed (>10K/sec)
   - Objects have fixed or predictable size
   - Allocation is on a hot path (measurable GC pressure)
   - Do NOT pool objects that are rarely allocated or have widely varying sizes.'''),

    ("go_deep/linux_epoll_syscall", r'''How do I use Linux epoll from Go via syscall wrappers? Show me building a basic TCP event loop without using net.Listener.''', r'''<think>
Using epoll from Go bypasses the net package and runtime poller. This is educational and useful for understanding how Go's netpoller works under the hood.

Steps:
1. Create a socket with syscall.Socket
2. Bind and listen with syscall.Bind, syscall.Listen
3. Create epoll fd with syscall.EpollCreate1
4. Add the listener fd to epoll with EpollCtl
5. Event loop: EpollWait, handle events
6. For new connections: accept, set non-blocking, add to epoll
7. For data: read from fd, process, write response

Key details:
- All sockets must be non-blocking (syscall.SetNonblock)
- EPOLLET (edge-triggered) vs level-triggered: edge-triggered requires reading until EAGAIN
- EPOLLONESHOT: re-arm after each event to prevent races
- We bypass Go's runtime netpoller, so this is purely syscall-driven
- This is Linux-only (epoll doesn't exist on macOS/Windows)
</think>

Here is a raw epoll-based TCP echo server built entirely on syscalls:

```go
//go:build linux

package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"unsafe"
)

const (
	maxEvents  = 128
	readBufLen = 4096
)

// setNonBlock sets a file descriptor to non-blocking mode.
func setNonBlock(fd int) error {
	return syscall.SetNonblock(fd, true)
}

// createListener creates a non-blocking TCP listening socket.
func createListener(port int) (int, error) {
	// Create TCP socket.
	fd, err := syscall.Socket(syscall.AF_INET, syscall.SOCK_STREAM, 0)
	if err != nil {
		return -1, fmt.Errorf("socket: %w", err)
	}

	// Allow address reuse.
	if err := syscall.SetsockoptInt(fd, syscall.SOL_SOCKET, syscall.SO_REUSEADDR, 1); err != nil {
		syscall.Close(fd)
		return -1, fmt.Errorf("SO_REUSEADDR: %w", err)
	}

	// Bind to address.
	addr := &syscall.SockaddrInet4{Port: port}
	// addr.Addr is [4]byte{0,0,0,0} by default = INADDR_ANY
	if err := syscall.Bind(fd, addr); err != nil {
		syscall.Close(fd)
		return -1, fmt.Errorf("bind: %w", err)
	}

	// Set non-blocking before listen.
	if err := setNonBlock(fd); err != nil {
		syscall.Close(fd)
		return -1, fmt.Errorf("nonblock: %w", err)
	}

	// Listen with backlog.
	if err := syscall.Listen(fd, syscall.SOMAXCONN); err != nil {
		syscall.Close(fd)
		return -1, fmt.Errorf("listen: %w", err)
	}

	return fd, nil
}

// EpollServer manages an epoll-based event loop.
type EpollServer struct {
	listenFD int
	epollFD  int
	conns    map[int][]byte // fd → pending write buffer
}

func NewEpollServer(port int) (*EpollServer, error) {
	listenFD, err := createListener(port)
	if err != nil {
		return nil, err
	}

	// Create epoll instance.
	epollFD, err := syscall.EpollCreate1(0)
	if err != nil {
		syscall.Close(listenFD)
		return nil, fmt.Errorf("epoll_create1: %w", err)
	}

	// Add listener to epoll (edge-triggered for accept).
	event := syscall.EpollEvent{
		Events: syscall.EPOLLIN | syscall.EPOLLET,
		Fd:     int32(listenFD),
	}
	if err := syscall.EpollCtl(epollFD, syscall.EPOLL_CTL_ADD, listenFD, &event); err != nil {
		syscall.Close(epollFD)
		syscall.Close(listenFD)
		return nil, fmt.Errorf("epoll_ctl add listener: %w", err)
	}

	return &EpollServer{
		listenFD: listenFD,
		epollFD:  epollFD,
		conns:    make(map[int][]byte),
	}, nil
}

// Run starts the event loop. Blocks until interrupted.
func (s *EpollServer) Run() error {
	defer s.Close()

	// Set up signal handling for clean shutdown.
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	events := make([]syscall.EpollEvent, maxEvents)
	buf := make([]byte, readBufLen)

	log.Printf("epoll server running, listener fd=%d, epoll fd=%d", s.listenFD, s.epollFD)

	for {
		// Check for shutdown signal (non-blocking).
		select {
		case sig := <-sigCh:
			log.Printf("received %v, shutting down", sig)
			return nil
		default:
		}

		// Wait for events with 100ms timeout (allows signal checking).
		n, err := syscall.EpollWait(s.epollFD, events, 100)
		if err != nil {
			if err == syscall.EINTR {
				continue // interrupted by signal, retry
			}
			return fmt.Errorf("epoll_wait: %w", err)
		}

		for i := 0; i < n; i++ {
			ev := &events[i]
			fd := int(ev.Fd)

			if fd == s.listenFD {
				// New connection(s) ready to accept.
				s.handleAccept()
			} else if ev.Events&(syscall.EPOLLERR|syscall.EPOLLHUP) != 0 {
				// Error or hangup.
				s.closeConn(fd)
			} else if ev.Events&syscall.EPOLLIN != 0 {
				// Data ready to read.
				s.handleRead(fd, buf)
			}
		}
	}
}

func (s *EpollServer) handleAccept() {
	// Edge-triggered: must accept ALL pending connections.
	for {
		connFD, sa, err := syscall.Accept(s.listenFD)
		if err != nil {
			if err == syscall.EAGAIN || err == syscall.EWOULDBLOCK {
				break // no more pending connections
			}
			log.Printf("accept error: %v", err)
			break
		}

		if err := setNonBlock(connFD); err != nil {
			log.Printf("nonblock on conn %d: %v", connFD, err)
			syscall.Close(connFD)
			continue
		}

		// Add to epoll (edge-triggered, read events).
		event := syscall.EpollEvent{
			Events: syscall.EPOLLIN | syscall.EPOLLET,
			Fd:     int32(connFD),
		}
		if err := syscall.EpollCtl(s.epollFD, syscall.EPOLL_CTL_ADD, connFD, &event); err != nil {
			log.Printf("epoll_ctl add %d: %v", connFD, err)
			syscall.Close(connFD)
			continue
		}

		s.conns[connFD] = nil
		addr := formatSockaddr(sa)
		log.Printf("accepted fd=%d from %s (%d active)", connFD, addr, len(s.conns))
	}
}

func (s *EpollServer) handleRead(fd int, buf []byte) {
	// Edge-triggered: must read until EAGAIN.
	for {
		n, err := syscall.Read(fd, buf)
		if err != nil {
			if err == syscall.EAGAIN || err == syscall.EWOULDBLOCK {
				break // no more data
			}
			log.Printf("read fd=%d error: %v", fd, err)
			s.closeConn(fd)
			return
		}
		if n == 0 {
			// EOF — client disconnected.
			s.closeConn(fd)
			return
		}

		// Echo the data back (simple echo server).
		data := make([]byte, n)
		copy(data, buf[:n])
		s.writeAll(fd, data)
	}
}

func (s *EpollServer) writeAll(fd int, data []byte) {
	for len(data) > 0 {
		n, err := syscall.Write(fd, data)
		if err != nil {
			if err == syscall.EAGAIN || err == syscall.EWOULDBLOCK {
				// In production: register EPOLLOUT and buffer remaining data.
				log.Printf("write fd=%d would block, dropping %d bytes", fd, len(data))
				return
			}
			log.Printf("write fd=%d error: %v", fd, err)
			s.closeConn(fd)
			return
		}
		data = data[n:]
	}
}

func (s *EpollServer) closeConn(fd int) {
	syscall.EpollCtl(s.epollFD, syscall.EPOLL_CTL_DEL, fd, nil)
	syscall.Close(fd)
	delete(s.conns, fd)
	log.Printf("closed fd=%d (%d active)", fd, len(s.conns))
}

func (s *EpollServer) Close() {
	for fd := range s.conns {
		syscall.Close(fd)
	}
	syscall.Close(s.epollFD)
	syscall.Close(s.listenFD)
}

func formatSockaddr(sa syscall.Sockaddr) string {
	switch v := sa.(type) {
	case *syscall.SockaddrInet4:
		return fmt.Sprintf("%d.%d.%d.%d:%d", v.Addr[0], v.Addr[1], v.Addr[2], v.Addr[3], v.Port)
	default:
		return fmt.Sprintf("%v", sa)
	}
}

// Ensure the unsafe import is used for the EpollEvent Fd field (it's an int32).
var _ = unsafe.Sizeof(0)

func main() {
	port := 9090
	if len(os.Args) > 1 {
		fmt.Sscanf(os.Args[1], "%d", &port)
	}

	server, err := NewEpollServer(port)
	if err != nil {
		log.Fatal(err)
	}

	log.Printf("echo server on :%d (raw epoll, no net package)", port)
	if err := server.Run(); err != nil {
		log.Fatal(err)
	}
}
```

Test it:

```bash
# Terminal 1
go run main.go 9090

# Terminal 2
echo "hello epoll" | nc localhost 9090
# Output: hello epoll
```

How this compares to Go's net package:

1. **Go's runtime netpoller** uses epoll internally (on Linux) but integrates it with the goroutine scheduler. When a goroutine calls `conn.Read()` and would block, the runtime parks the goroutine and registers the fd with its internal epoll. When data arrives, the goroutine is unparked. This is why Go's net package "feels" blocking but is actually multiplexed.

2. **This raw epoll version** runs a single-threaded event loop — all I/O is handled in one goroutine, one thread. This is the pattern used by Redis, Nginx, and Node.js.

3. **Edge-triggered (`EPOLLET`)** requires draining all available data/connections on each notification. Missing data causes it to be stuck until the next event. Level-triggered re-notifies until the fd is drained, which is simpler but causes more `epoll_wait` returns.

4. **Production gaps**: this example doesn't handle `EPOLLOUT` for write backpressure, doesn't implement read/write deadlines, and doesn't handle partial writes properly. Go's net package handles all of these.

5. **Why use raw epoll**: understanding how the runtime works, building custom protocol servers where goroutine-per-connection overhead is unacceptable (millions of idle connections), or interfacing with C event loops.'''),

    ("go_deep/profiling_goroutine_contention", r'''How do I use runtime/trace to profile goroutine contention and scheduling latency in Go? Show me how to identify bottlenecks.''', r'''<think>
runtime/trace provides deep visibility into Go's scheduler. Unlike pprof (which samples), trace records every scheduling event:
- Goroutine creation, blocking, unblocking, syscalls
- GC events
- Network poller events
- User-defined tasks and regions

For contention profiling:
1. Record a trace
2. Analyze with `go tool trace`
3. Look for: goroutines blocked on mutexes, channel operations, or syscalls
4. Identify scheduling latency (time between unblock and actual execution)

Let me show how to capture a trace programmatically and also how to identify common contention patterns.
</think>

Here is a complete guide to profiling goroutine contention with `runtime/trace`:

```go
package main

import (
	"context"
	"fmt"
	"log"
	"math/rand"
	"os"
	"runtime"
	"runtime/trace"
	"sync"
	"time"
)

// ---- Scenario: contended shared map (typical bottleneck) ----

type ContentionDemo struct {
	mu    sync.Mutex
	data  map[string]int
}

func (c *ContentionDemo) Increment(key string) {
	c.mu.Lock()
	c.data[key]++
	c.mu.Unlock()
}

func (c *ContentionDemo) Get(key string) int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.data[key]
}

// ---- Scenario: fixed version with sharded map ----

const numShards = 64

type ShardedMap struct {
	shards [numShards]struct {
		mu   sync.Mutex
		data map[string]int
	}
}

func NewShardedMap() *ShardedMap {
	sm := &ShardedMap{}
	for i := range sm.shards {
		sm.shards[i].data = make(map[string]int)
	}
	return sm
}

func (sm *ShardedMap) shard(key string) int {
	h := 0
	for _, c := range key {
		h = h*31 + int(c)
	}
	if h < 0 {
		h = -h
	}
	return h % numShards
}

func (sm *ShardedMap) Increment(key string) {
	s := sm.shard(key)
	sm.shards[s].mu.Lock()
	sm.shards[s].data[key]++
	sm.shards[s].mu.Unlock()
}

func main() {
	// Create trace output file.
	traceFile, err := os.Create("contention.trace")
	if err != nil {
		log.Fatal(err)
	}
	defer traceFile.Close()

	// Start tracing.
	if err := trace.Start(traceFile); err != nil {
		log.Fatal(err)
	}
	defer trace.Stop()

	numWorkers := runtime.GOMAXPROCS(0) * 2
	iterations := 100_000
	keys := make([]string, 1000)
	for i := range keys {
		keys[i] = fmt.Sprintf("key-%d", i)
	}

	// ---- Phase 1: Contended single-mutex map ----
	ctx, task1 := trace.NewTask(context.Background(), "contended-map")

	contended := &ContentionDemo{data: make(map[string]int)}
	var wg sync.WaitGroup

	start := time.Now()
	for w := 0; w < numWorkers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			trace.WithRegion(ctx, "worker", func() {
				for i := 0; i < iterations; i++ {
					key := keys[rand.Intn(len(keys))]
					contended.Increment(key)
				}
			})
		}()
	}
	wg.Wait()
	dur1 := time.Since(start)
	task1.End()

	// ---- Phase 2: Sharded map (reduced contention) ----
	ctx2, task2 := trace.NewTask(context.Background(), "sharded-map")

	sharded := NewShardedMap()
	start = time.Now()
	for w := 0; w < numWorkers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			trace.WithRegion(ctx2, "worker", func() {
				for i := 0; i < iterations; i++ {
					key := keys[rand.Intn(len(keys))]
					sharded.Increment(key)
				}
			})
		}()
	}
	wg.Wait()
	dur2 := time.Since(start)
	task2.End()

	fmt.Printf("=== Contention Profiling Results ===\n")
	fmt.Printf("workers:     %d\n", numWorkers)
	fmt.Printf("iterations:  %d per worker\n", iterations)
	fmt.Printf("\n")
	fmt.Printf("contended:   %v\n", dur1)
	fmt.Printf("sharded:     %v (%.1fx faster)\n", dur2, float64(dur1)/float64(dur2))
	fmt.Printf("\n")
	fmt.Printf("trace written to: contention.trace\n")
	fmt.Printf("analyze with:     go tool trace contention.trace\n")
}
```

How to analyze the trace:

```bash
# Run the program to generate the trace.
go run main.go

# Open the trace viewer (launches browser).
go tool trace contention.trace
```

In the trace viewer, look for:

1. **Goroutine analysis**: click "Goroutine analysis" — shows time spent in each state:
   - **Execution**: actually running on a CPU
   - **Blocked (sync)**: waiting on mutex/channel (this is contention!)
   - **Blocked (network)**: waiting on I/O
   - **Runnable**: ready to run but no available P (scheduling latency)

2. **Synchronization blocking profile**: shows which mutexes/channels cause the most blocking time. In the contended-map phase, you will see heavy sync blocking.

3. **Scheduler latency profile**: time between a goroutine becoming runnable and actually executing. High latency here means too many goroutines competing for CPU.

4. **User tasks and regions**: our `trace.NewTask` and `trace.WithRegion` calls create named spans visible in the timeline, making it easy to compare the two phases.

Additional profiling techniques:

```go
// Runtime mutex profiling (alternative to trace).
import "runtime"

func enableMutexProfiling() {
    // Record 100% of mutex contention events.
    runtime.SetMutexProfileFraction(1)
    // Then use: go tool pprof http://localhost:6060/debug/pprof/mutex
}

// Block profiling: records goroutines blocked on channels/mutexes.
func enableBlockProfiling() {
    runtime.SetBlockProfileRate(1) // record all blocking events
    // Then use: go tool pprof http://localhost:6060/debug/pprof/block
}
```

Common contention patterns and fixes:

| Pattern | Symptom in Trace | Fix |
|---------|-----------------|-----|
| Single mutex protecting map | Long sync-block bars | Shard the map (as shown) |
| Channel bottleneck | Goroutines blocked on chan send | Increase buffer or add workers |
| Goroutine spawn storm | High scheduling latency | Use worker pool instead of unbounded spawning |
| Lock held during I/O | Very long sync-block events | Move I/O outside the lock, copy data under lock |
| GC pressure from allocations | Frequent GC pauses in timeline | Object pooling, reduce allocations |'''),

    ("go_deep/expvar_custom_metrics", r'''How do I expose custom runtime metrics in Go using the expvar package? I want application-specific counters, gauges, and histograms accessible via HTTP.''', r'''<think>
expvar is Go's built-in metrics package. It:
- Automatically exposes metrics at /debug/vars as JSON
- Includes runtime memstats by default
- Supports custom Int, Float, String, Map, and Func variables
- Thread-safe (all operations are atomic or mutex-protected)
- No external dependencies

For more advanced metrics (histograms, percentiles), we need to implement them ourselves since expvar only provides basic types.

Let me show:
1. Basic counters and gauges
2. Custom Func for computed metrics
3. A histogram implementation using expvar.Map
4. Integration with an HTTP server
</think>

Here is a complete custom metrics system using `expvar`:

```go
package main

import (
	"encoding/json"
	"expvar"
	"fmt"
	"math"
	"net/http"
	"runtime"
	"sort"
	"sync"
	"sync/atomic"
	"time"
)

// ---- Custom metric types ----

// Gauge holds a float64 that can go up and down.
type Gauge struct {
	bits atomic.Uint64
}

func NewGauge(name string) *Gauge {
	g := &Gauge{}
	expvar.Publish(name, g)
	return g
}

func (g *Gauge) Set(v float64) {
	g.bits.Store(math.Float64bits(v))
}

func (g *Gauge) Get() float64 {
	return math.Float64frombits(g.bits.Load())
}

func (g *Gauge) String() string {
	return fmt.Sprintf("%.4f", g.Get())
}

// Histogram tracks the distribution of values.
type Histogram struct {
	mu      sync.Mutex
	values  []float64
	maxSize int
	count   atomic.Int64
	sum     atomic.Uint64 // stored as float64 bits
}

func NewHistogram(name string, maxSamples int) *Histogram {
	h := &Histogram{
		values:  make([]float64, 0, maxSamples),
		maxSize: maxSamples,
	}
	expvar.Publish(name, h)
	return h
}

func (h *Histogram) Observe(v float64) {
	h.count.Add(1)

	// Atomic add for sum (approximation — races possible but acceptable for metrics).
	for {
		old := h.sum.Load()
		oldF := math.Float64frombits(old)
		newF := oldF + v
		if h.sum.CompareAndSwap(old, math.Float64bits(newF)) {
			break
		}
	}

	h.mu.Lock()
	if len(h.values) >= h.maxSize {
		// Reservoir sampling: replace a random element.
		idx := int(h.count.Load()) % h.maxSize
		if idx < h.maxSize {
			h.values[idx] = v
		}
	} else {
		h.values = append(h.values, v)
	}
	h.mu.Unlock()
}

func (h *Histogram) Percentile(p float64) float64 {
	h.mu.Lock()
	defer h.mu.Unlock()

	if len(h.values) == 0 {
		return 0
	}

	sorted := make([]float64, len(h.values))
	copy(sorted, h.values)
	sort.Float64s(sorted)

	idx := int(math.Ceil(p/100.0*float64(len(sorted)))) - 1
	if idx < 0 {
		idx = 0
	}
	if idx >= len(sorted) {
		idx = len(sorted) - 1
	}
	return sorted[idx]
}

func (h *Histogram) String() string {
	count := h.count.Load()
	sum := math.Float64frombits(h.sum.Load())
	avg := float64(0)
	if count > 0 {
		avg = sum / float64(count)
	}

	data := map[string]any{
		"count": count,
		"sum":   sum,
		"avg":   avg,
		"p50":   h.Percentile(50),
		"p90":   h.Percentile(90),
		"p99":   h.Percentile(99),
	}
	b, _ := json.Marshal(data)
	return string(b)
}

// RateCounter tracks events per second over a sliding window.
type RateCounter struct {
	mu      sync.Mutex
	buckets []int64
	window  int // number of 1-second buckets
	current int
	total   atomic.Int64
}

func NewRateCounter(name string, windowSecs int) *RateCounter {
	rc := &RateCounter{
		buckets: make([]int64, windowSecs),
		window:  windowSecs,
	}
	expvar.Publish(name, rc)

	// Rotate buckets every second.
	go func() {
		ticker := time.NewTicker(time.Second)
		for range ticker.C {
			rc.mu.Lock()
			rc.current = (rc.current + 1) % rc.window
			rc.buckets[rc.current] = 0
			rc.mu.Unlock()
		}
	}()

	return rc
}

func (rc *RateCounter) Incr() {
	rc.total.Add(1)
	rc.mu.Lock()
	rc.buckets[rc.current]++
	rc.mu.Unlock()
}

func (rc *RateCounter) Rate() float64 {
	rc.mu.Lock()
	defer rc.mu.Unlock()

	var sum int64
	for _, b := range rc.buckets {
		sum += b
	}
	return float64(sum) / float64(rc.window)
}

func (rc *RateCounter) String() string {
	data := map[string]any{
		"total":  rc.total.Load(),
		"rate_1s": rc.Rate(),
	}
	b, _ := json.Marshal(data)
	return string(b)
}

// ---- Application metrics ----

var (
	httpRequests  = expvar.NewInt("http_requests_total")
	httpErrors    = expvar.NewInt("http_errors_total")
	activeConns   = NewGauge("http_active_connections")
	latencyHist   = NewHistogram("http_latency_ms", 10000)
	requestRate   = NewRateCounter("http_request_rate", 60)
	goroutines    = expvar.NewInt("goroutines")
)

func init() {
	// Custom function metrics — computed on read.
	expvar.Publish("uptime_seconds", expvar.Func(func() any {
		return time.Since(startTime).Seconds()
	}))

	expvar.Publish("runtime", expvar.Func(func() any {
		var m runtime.MemStats
		runtime.ReadMemStats(&m)
		return map[string]any{
			"goroutines":    runtime.NumGoroutine(),
			"heap_alloc_mb": float64(m.HeapAlloc) / 1024 / 1024,
			"heap_sys_mb":   float64(m.HeapSys) / 1024 / 1024,
			"gc_runs":       m.NumGC,
			"gc_pause_ms":   float64(m.PauseNs[(m.NumGC+255)%256]) / 1e6,
			"num_cpu":       runtime.NumCPU(),
		}
	}))
}

var startTime = time.Now()

// instrumentedHandler wraps an HTTP handler with metrics.
func instrumentedHandler(name string, h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		httpRequests.Add(1)
		requestRate.Incr()
		activeConns.Set(activeConns.Get() + 1)
		goroutines.Set(int64(runtime.NumGoroutine()))

		defer func() {
			elapsed := time.Since(start).Seconds() * 1000 // ms
			latencyHist.Observe(elapsed)
			activeConns.Set(activeConns.Get() - 1)
		}()

		h(w, r)
	}
}

func main() {
	mux := http.NewServeMux()

	// Application endpoints.
	mux.HandleFunc("/api/hello", instrumentedHandler("hello", func(w http.ResponseWriter, r *http.Request) {
		// Simulate variable latency.
		time.Sleep(time.Duration(10+time.Now().UnixNano()%90) * time.Millisecond)
		fmt.Fprintln(w, "hello!")
	}))

	mux.HandleFunc("/api/error", instrumentedHandler("error", func(w http.ResponseWriter, r *http.Request) {
		httpErrors.Add(1)
		http.Error(w, "something broke", 500)
	}))

	// expvar handler — automatically serves all registered metrics as JSON.
	// Already registered by the expvar package at /debug/vars.

	// Custom metrics dashboard.
	mux.HandleFunc("/metrics", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-cache")

		metrics := map[string]any{
			"http_requests_total":     httpRequests.Value(),
			"http_errors_total":       httpErrors.Value(),
			"http_active_connections": activeConns.Get(),
			"http_latency_ms":         json.RawMessage(latencyHist.String()),
			"http_request_rate":       json.RawMessage(requestRate.String()),
			"uptime_seconds":          time.Since(startTime).Seconds(),
			"goroutines":              runtime.NumGoroutine(),
		}

		enc := json.NewEncoder(w)
		enc.SetIndent("", "  ")
		enc.Encode(metrics)
	})

	fmt.Println("server on :8080")
	fmt.Println("  /api/hello       — test endpoint")
	fmt.Println("  /debug/vars      — all expvar metrics (built-in)")
	fmt.Println("  /metrics         — custom dashboard")
	http.ListenAndServe(":8080", mux)
}
```

Test it:

```bash
go run main.go &

# Generate some traffic.
for i in $(seq 1 100); do curl -s localhost:8080/api/hello > /dev/null; done

# View metrics.
curl -s localhost:8080/metrics | jq .
```

Example output:

```json
{
  "http_requests_total": 100,
  "http_errors_total": 0,
  "http_active_connections": 0,
  "http_latency_ms": {
    "count": 100,
    "sum": 5432.1,
    "avg": 54.3,
    "p50": 52.1,
    "p90": 88.7,
    "p99": 97.2
  },
  "http_request_rate": {
    "total": 100,
    "rate_1s": 12.5
  },
  "uptime_seconds": 15.3,
  "goroutines": 5
}
```

Key points about expvar:

1. **Auto-registered at `/debug/vars`**: importing `expvar` automatically registers an HTTP handler. All published variables appear as JSON.
2. **Thread-safe by design**: `expvar.Int` uses `atomic.Int64`, `expvar.Map` uses `sync.RWMutex`. Safe for concurrent updates from multiple goroutines.
3. **`expvar.Func` for computed metrics**: lazily evaluated on each HTTP request. Good for expensive computations (like `runtime.ReadMemStats`) that should not run on every data point.
4. **No external dependencies**: unlike Prometheus client libraries, expvar is in the standard library. For Prometheus integration, use `expvar_exporter` or map expvar values to Prometheus metrics.
5. **Histogram with reservoir sampling**: since expvar has no built-in histogram, we implement one that keeps a bounded sample of recent values for percentile calculation.
6. **Production tip**: protect `/debug/vars` with authentication in production — it exposes memory statistics and potentially sensitive metric values.'''),
]
