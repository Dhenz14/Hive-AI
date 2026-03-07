"""Documentation generation training pairs: changelog entries, release notes, migration guides."""

pairs = [
    {
        "instruction": r'''Write a changelog entry for version 3.2.0 based on these git commits:

feat: add WebSocket support for real-time notifications
feat: implement batch API endpoint for bulk operations
fix: prevent race condition in concurrent session updates
fix: correct timezone handling in scheduled task execution
fix: handle null values in CSV export gracefully
refactor: extract authentication logic into middleware
perf: add database query result caching (reduces p95 latency by 40%)
docs: update API reference for batch endpoint
chore: upgrade FastAPI from 0.104 to 0.109
chore: replace deprecated datetime.utcnow() calls''',
        "output": r'''# Changelog

## [3.2.0] - 2024-12-15

### Added
- **WebSocket notifications** -- Real-time event streaming via WebSocket connections. See the [WebSocket guide](docs/websocket.md) for setup.
- **Batch API endpoint** -- New `POST /api/v1/batch` endpoint for executing multiple operations in a single request, reducing round trips for bulk workflows.

### Fixed
- Race condition in concurrent session updates that could cause session data loss under high load.
- Timezone handling in the task scheduler -- scheduled tasks now correctly use UTC internally and convert to the user's timezone for display.
- CSV export no longer crashes when exported fields contain null values. Nulls are written as empty strings.

### Changed
- Authentication logic extracted into standalone middleware. No API changes, but custom auth integrations should review the [migration notes](#migrating-custom-auth).
- Upgraded FastAPI from 0.104 to 0.109. No breaking changes for API consumers.
- Replaced all `datetime.utcnow()` calls with `datetime.now(timezone.utc)` per Python 3.12 deprecation.

### Performance
- Added query result caching for frequently accessed endpoints. P95 latency reduced by approximately 40% on read-heavy workloads.'''
    },
    {
        "instruction": r'''Write a migration guide for users upgrading from v2.x to v3.0.0 based on these breaking changes:

1. Dropped Python 3.8 support, minimum is now 3.10
2. Config file format changed from INI to TOML
3. The `Client.connect()` method is now async (was sync)
4. Removed deprecated `Client.query_raw()` method (use `Client.execute()`)
5. Response objects now use `.data` instead of `.body` attribute
6. Error codes changed from strings to integer enums
7. Default timeout changed from 30s to 10s''',
        "output": r'''<think>
A migration guide needs to be actionable. For each breaking change, I should explain: what changed, why, and exactly what code the user needs to update. I should order by impact and provide before/after code examples for the code-level changes.
</think>

# Migration Guide: v2.x to v3.0.0

This guide covers all breaking changes in v3.0.0 and how to update your code.

## Prerequisites

**Python 3.10 or later is required.** v3.0.0 drops support for Python 3.8 and 3.9. Check your version with `python --version` and upgrade if needed.

## Configuration File

The config file format has changed from INI to TOML.

**Before (config.ini):**
```ini
[database]
host = localhost
port = 5432
```

**After (config.toml):**
```toml
[database]
host = "localhost"
port = 5432
```

Key differences: string values must be quoted in TOML. Boolean values use `true`/`false` (not `yes`/`no`). Run `python -m mylib.migrate_config config.ini` to auto-convert.

## Async Connection

`Client.connect()` is now an async method. Update all call sites to use `await`.

**Before:**
```python
client = Client()
client.connect("localhost:5432")
```

**After:**
```python
client = Client()
await client.connect("localhost:5432")
```

If you cannot use async, use `asyncio.run()`:
```python
import asyncio
asyncio.run(client.connect("localhost:5432"))
```

## Removed: query_raw()

`Client.query_raw()` was deprecated in v2.3 and is now removed. Replace with `Client.execute()`.

**Before:** `result = client.query_raw("SELECT * FROM users")`

**After:** `result = client.execute("SELECT * FROM users")`

## Response Attribute Rename

The `.body` attribute on response objects has been renamed to `.data`.

**Before:** `print(response.body)`

**After:** `print(response.data)`

Search your codebase: `grep -rn "\.body" --include="*.py"` to find all occurrences.

## Error Code Changes

Error codes are now integer enums instead of strings.

**Before:**
```python
if error.code == "NOT_FOUND":
    ...
```

**After:**
```python
from mylib import ErrorCode
if error.code == ErrorCode.NOT_FOUND:
    ...
```

## Default Timeout

The default timeout changed from 30s to 10s. If your operations need more time, set the timeout explicitly:

```python
client = Client(timeout=30)
```'''
    },
    {
        "instruction": r'''Write release notes for a major frontend framework release based on these changes:

- New JSX transform (no need to import React in every file)
- Server Components for zero-JS server rendering
- Concurrent rendering enabled by default
- Suspense now works with data fetching
- useTransition hook for non-blocking state updates
- Automatic batching of state updates across event handlers
- Deprecated: class component lifecycle methods componentWillMount, componentWillReceiveProps, componentWillUpdate
- Removed: support for IE11
- Removed: Legacy Context API (use createContext instead)
- Bundle size reduced by 15% through dead code elimination''',
        "output": r'''# Release Notes: ReactUI 5.0

We are excited to announce ReactUI 5.0 -- our largest release in two years, focused on performance, developer experience, and modern rendering patterns.

## Highlights

**Server Components** -- Render components on the server with zero client-side JavaScript. Database queries, file system access, and heavy computations stay on the server. Client components are only shipped when interactivity is needed.

**Concurrent Rendering (default)** -- Concurrent mode is now the default rendering behavior. React can prepare multiple versions of the UI simultaneously and commit the most up-to-date one, eliminating UI janks during heavy updates.

**Automatic State Batching** -- State updates are now automatically batched across event handlers, timeouts, and promises. Previously, batching only worked inside React event handlers. This reduces unnecessary re-renders with no code changes needed.

## New Features

- **Simplified JSX Transform** -- No more `import React from 'react'` at the top of every file. The compiler handles it automatically.
- **Suspense for Data Fetching** -- `<Suspense>` now works with data fetching libraries, not just code splitting. Show fallback UIs while data loads.
- **useTransition Hook** -- Mark state updates as non-urgent so they do not block user input. Ideal for search filters, tab switching, and large list updates.

## Breaking Changes

**Removed IE11 support.** If you need IE11, stay on ReactUI 4.x.

**Removed Legacy Context API.** Replace `contextTypes` and `getChildContext` with `createContext` and `useContext`. The legacy API was deprecated since ReactUI 3.0.

## Deprecations

The following class component lifecycle methods are deprecated and will be removed in v6.0:
- `componentWillMount` -- use `constructor` or `useEffect`
- `componentWillReceiveProps` -- use `getDerivedStateFromProps` or `useEffect`
- `componentWillUpdate` -- use `getSnapshotBeforeUpdate`

Run `npx reactui-codemod rename-unsafe-lifecycles` to add the `UNSAFE_` prefix automatically.

## Performance

- 15% smaller bundle size through improved dead code elimination and tree shaking.
- Concurrent rendering reduces interaction-to-paint times by up to 60% on complex UIs.'''
    },
    {
        "instruction": r'''Write a CHANGELOG.md entry for a patch release that fixes several security vulnerabilities:

- CVE-2024-1234: SQL injection via search parameter (CVSS 9.1 Critical)
- CVE-2024-1235: Path traversal in file download endpoint (CVSS 7.5 High)
- CVE-2024-1236: SSRF via webhook URL validation bypass (CVSS 6.8 Medium)
- Also fixed: memory leak in connection pool under sustained load
- Also fixed: incorrect Content-Type header on error responses''',
        "output": r'''## [2.4.1] - 2024-11-20

### Security

- **CRITICAL: SQL injection in search endpoint (CVE-2024-1234, CVSS 9.1).** The `q` parameter in `GET /api/search` was interpolated directly into a SQL query without parameterization. An attacker could extract or modify database contents. Fixed by using parameterized queries. All users should upgrade immediately.

- **HIGH: Path traversal in file downloads (CVE-2024-1235, CVSS 7.5).** The `GET /api/files/{path}` endpoint did not properly sanitize `..` sequences in the path parameter. An attacker could read arbitrary files from the server filesystem. Fixed by resolving the canonical path and verifying it falls within the allowed directory.

- **MEDIUM: SSRF via webhook URL bypass (CVE-2024-1236, CVSS 6.8).** Webhook URL validation could be bypassed using DNS rebinding or IPv6-mapped IPv4 addresses, allowing requests to internal services. Fixed by resolving URLs server-side and blocking private IP ranges after DNS resolution.

### Fixed

- Memory leak in the database connection pool when connections were not properly returned under sustained high load. The pool now enforces a checkout timeout and reclaims abandoned connections.
- Error responses now return `Content-Type: application/json` instead of `text/plain`, matching the documented API contract.

### Upgrade Priority

**Critical.** CVE-2024-1234 is remotely exploitable without authentication. Upgrade from any 2.x version by running:

```bash
pip install --upgrade mypackage==2.4.1
```

No configuration changes or database migrations are required.'''
    },
    {
        "instruction": r'''Generate a changelog entry from this git diff showing a breaking API change in a Go library:

-func NewClient(host string, port int) *Client {
-    return &Client{
-        host: host,
-        port: port,
-        timeout: 30 * time.Second,
-    }
-}
+type ClientOption func(*Client)
+
+func WithTimeout(d time.Duration) ClientOption {
+    return func(c *Client) { c.timeout = d }
+}
+
+func WithTLS(certFile, keyFile string) ClientOption {
+    return func(c *Client) {
+        c.tlsCert = certFile
+        c.tlsKey = keyFile
+    }
+}
+
+func WithRetry(maxRetries int, backoff time.Duration) ClientOption {
+    return func(c *Client) {
+        c.maxRetries = maxRetries
+        c.retryBackoff = backoff
+    }
+}
+
+func NewClient(addr string, opts ...ClientOption) *Client {
+    c := &Client{
+        addr:    addr,
+        timeout: 10 * time.Second,
+    }
+    for _, opt := range opts {
+        opt(c)
+    }
+    return c
+}''',
        "output": r'''<think>
This diff shows a change from positional arguments (host, port) to a single address string plus functional options. It is a breaking change because the function signature changed. The default timeout also changed from 30s to 10s. I should document the old vs new API and show how to migrate.
</think>

## [4.0.0] - 2024-12-01

### Breaking Changes

- **`NewClient` signature changed.** The constructor now takes a single address string and variadic functional options, replacing the previous `(host, port)` positional parameters.

  **Before (v3.x):**
  ```go
  client := NewClient("localhost", 8080)
  ```

  **After (v4.0):**
  ```go
  client := NewClient("localhost:8080")
  ```

- **Default timeout reduced from 30s to 10s.** To preserve the old behavior, use the `WithTimeout` option:
  ```go
  client := NewClient("localhost:8080", WithTimeout(30*time.Second))
  ```

### Added

- **Functional options pattern** for client configuration. New options:
  - `WithTimeout(d time.Duration)` -- Set request timeout (default: 10s)
  - `WithTLS(certFile, keyFile string)` -- Enable TLS with certificate files
  - `WithRetry(maxRetries int, backoff time.Duration)` -- Configure automatic retries with backoff

  Options can be combined freely:
  ```go
  client := NewClient("api.example.com:443",
      WithTLS("cert.pem", "key.pem"),
      WithRetry(3, 2*time.Second),
      WithTimeout(15*time.Second),
  )
  ```

### Migration

Replace `NewClient(host, port)` with `NewClient(host:port)` throughout your codebase. In Go, a simple find-and-replace may work for most cases. If you relied on the 30s default timeout, add `WithTimeout(30*time.Second)` explicitly.'''
    },
]
