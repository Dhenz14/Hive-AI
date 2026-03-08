"""Multi-turn conversation training pairs: realistic back-and-forth coding interactions."""

PAIRS = [
    # =====================================================================
    # 1-5: ITERATIVE REFINEMENT
    # =====================================================================
    (
        "multi_turn/python-csv-parser-refinement",
        r'''<conversation>
User: Write a Python function that reads a CSV file and returns a list of dictionaries.
Assistant: Here's a simple CSV parser:

```python
import csv

def read_csv(filepath: str) -> list[dict]:
    with open(filepath, newline='') as f:
        reader = csv.DictReader(f)
        return list(reader)
```

Each row becomes a dictionary with column headers as keys.
User: Can you add error handling for missing files and malformed CSV data?
Assistant: Sure, here's the version with error handling:

```python
import csv

def read_csv(filepath: str) -> list[dict]:
    try:
        with open(filepath, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = []
            for i, row in enumerate(reader):
                if None in row:
                    raise ValueError(f"Row {i+1} has more fields than headers")
                rows.append(row)
            return rows
    except FileNotFoundError:
        raise FileNotFoundError(f"CSV file not found: {filepath}")
    except csv.Error as e:
        raise ValueError(f"Malformed CSV at line {reader.line_num}: {e}")
```
User: Now optimize it for large files — I need to process CSVs with millions of rows without loading everything into memory.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user started with a basic CSV reader, added error handling, and now needs
it to handle millions of rows. The current implementation loads everything into
a list, which would consume too much memory for large files. I should convert
it to a generator that yields rows one at a time, keeping the error handling
from the previous iteration. I'll also add optional chunk-based reading for
batch processing use cases.
</think>

For millions of rows, switch to a generator so you only hold one row in memory at a time:

```python
import csv
from typing import Generator
from collections.abc import Iterator

def read_csv(filepath: str) -> Generator[dict, None, None]:
    """Lazily yield rows from a CSV file as dictionaries."""
    try:
        with open(filepath, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if None in row:
                    raise ValueError(f"Row {i+1} has more fields than headers")
                yield row
    except FileNotFoundError:
        raise FileNotFoundError(f"CSV file not found: {filepath}")
    except csv.Error as e:
        raise ValueError(f"Malformed CSV at line {reader.line_num}: {e}")


def read_csv_chunks(filepath: str, chunk_size: int = 10_000) -> Generator[list[dict], None, None]:
    """Yield chunks of rows for batch processing."""
    chunk = []
    for row in read_csv(filepath):
        chunk.append(row)
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
```

Key changes from the previous version:

- **`read_csv` is now a generator** — uses `yield` instead of building a list, so memory usage is O(1) regardless of file size.
- **`read_csv_chunks`** — batch variant that yields lists of `chunk_size` rows, useful when you need to do bulk inserts or DataFrame conversions.
- Error handling from the previous iteration is preserved.

Usage stays almost identical — just be aware it's lazy now:

```python
# Stream one row at a time
for row in read_csv("huge_file.csv"):
    process(row)

# Or process in batches of 10k
for batch in read_csv_chunks("huge_file.csv", chunk_size=10_000):
    df = pd.DataFrame(batch)
    save_to_db(df)
```'''
    ),
    (
        "multi_turn/rust-http-client-refinement",
        r'''<conversation>
User: Write a Rust function that fetches a URL and returns the response body as a string.
Assistant: Here's a basic async HTTP GET using `reqwest`:

```rust
use reqwest;

pub async fn fetch_url(url: &str) -> Result<String, reqwest::Error> {
    let body = reqwest::get(url).await?.text().await?;
    Ok(body)
}
```

Add `reqwest = { version = "0.12", features = ["json"] }` and `tokio` to your `Cargo.toml`.
User: Add retry logic — sometimes the server returns 503 and I need to retry up to 3 times with exponential backoff.
Assistant: Here's the version with retries:

```rust
use reqwest::{self, StatusCode};
use std::time::Duration;
use tokio::time::sleep;

pub async fn fetch_url(url: &str) -> Result<String, Box<dyn std::error::Error>> {
    let client = reqwest::Client::new();
    let max_retries = 3;

    for attempt in 0..=max_retries {
        let response = client.get(url).send().await?;

        if response.status() == StatusCode::SERVICE_UNAVAILABLE && attempt < max_retries {
            let delay = Duration::from_millis(100 * 2u64.pow(attempt as u32));
            sleep(delay).await;
            continue;
        }

        let body = response.error_for_status()?.text().await?;
        return Ok(body);
    }

    Err("Max retries exceeded".into())
}
```
User: Good, now add a timeout per request and also retry on 429 Too Many Requests, but respect the Retry-After header if present.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user wants two additions to the retry logic: a per-request timeout, and
handling 429 with Retry-After header support. I need to parse the Retry-After
header (which can be seconds or an HTTP date), use it as the backoff delay
when present, and fall back to exponential backoff otherwise. I'll set the
timeout on the client builder. I should also retry on both 503 and 429.
</think>

Here's the updated version with per-request timeout and `Retry-After` support for 429s:

```rust
use reqwest::{self, StatusCode};
use std::time::Duration;
use tokio::time::sleep;

pub async fn fetch_url(url: &str) -> Result<String, Box<dyn std::error::Error>> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(30))
        .build()?;

    let max_retries = 3;

    for attempt in 0..=max_retries {
        let response = client.get(url).send().await?;
        let status = response.status();

        let is_retryable = status == StatusCode::SERVICE_UNAVAILABLE
            || status == StatusCode::TOO_MANY_REQUESTS;

        if is_retryable && attempt < max_retries {
            let delay = if status == StatusCode::TOO_MANY_REQUESTS {
                parse_retry_after(&response)
                    .unwrap_or_else(|| Duration::from_millis(100 * 2u64.pow(attempt as u32)))
            } else {
                Duration::from_millis(100 * 2u64.pow(attempt as u32))
            };

            // Consume the response body before retrying
            let _ = response.bytes().await;
            sleep(delay).await;
            continue;
        }

        let body = response.error_for_status()?.text().await?;
        return Ok(body);
    }

    Err("Max retries exceeded".into())
}

fn parse_retry_after(response: &reqwest::Response) -> Option<Duration> {
    let header = response.headers().get("retry-after")?;
    let value = header.to_str().ok()?;

    // Retry-After can be seconds (integer) or an HTTP date
    if let Ok(seconds) = value.parse::<u64>() {
        Some(Duration::from_secs(seconds))
    } else {
        // Parse HTTP date format
        httpdate::parse_http_date(value)
            .ok()
            .and_then(|target| target.duration_since(std::time::SystemTime::now()).ok())
    }
}
```

Add `httpdate = "1"` to your `Cargo.toml` for parsing HTTP date formats.

Changes from the previous version:
- **30-second timeout** set on the client builder — applies to each individual request.
- **429 is now retryable** alongside 503.
- **`parse_retry_after`** reads the `Retry-After` header — handles both integer seconds and HTTP-date formats. Falls back to exponential backoff if the header is missing or unparseable.
- The response body is consumed (`response.bytes().await`) before retrying, which avoids connection pool issues with reqwest.'''
    ),
    (
        "multi_turn/go-api-handler-refinement",
        r'''<conversation>
User: Write a Go HTTP handler that accepts a JSON body with a "name" field and responds with a greeting.
Assistant: Here's a simple handler:

```go
package main

import (
    "encoding/json"
    "fmt"
    "net/http"
)

type GreetRequest struct {
    Name string `json:"name"`
}

func greetHandler(w http.ResponseWriter, r *http.Request) {
    var req GreetRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        http.Error(w, "invalid JSON", http.StatusBadRequest)
        return
    }
    fmt.Fprintf(w, "Hello, %s!", req.Name)
}
```
User: Add input validation — name should be 1-100 characters, only letters and spaces. Also return JSON instead of plain text.
Assistant: Updated with validation and JSON response:

```go
import (
    "encoding/json"
    "net/http"
    "regexp"
)

var namePattern = regexp.MustCompile(`^[a-zA-Z ]{1,100}$`)

type GreetRequest struct {
    Name string `json:"name"`
}

type GreetResponse struct {
    Message string `json:"message"`
}

type ErrorResponse struct {
    Error string `json:"error"`
}

func greetHandler(w http.ResponseWriter, r *http.Request) {
    var req GreetRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        w.WriteHeader(http.StatusBadRequest)
        json.NewEncoder(w).Encode(ErrorResponse{Error: "invalid JSON body"})
        return
    }

    if !namePattern.MatchString(req.Name) {
        w.WriteHeader(http.StatusBadRequest)
        json.NewEncoder(w).Encode(ErrorResponse{Error: "name must be 1-100 characters, letters and spaces only"})
        return
    }

    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(GreetResponse{Message: "Hello, " + req.Name + "!"})
}
```
User: Now add rate limiting — max 10 requests per minute per IP, and add proper middleware structure so I can reuse the rate limiter on other handlers.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user wants rate limiting as reusable middleware. I should implement a
per-IP rate limiter using a token bucket or sliding window approach. The
standard Go pattern is a middleware function that wraps http.Handler. I'll
use golang.org/x/time/rate for the limiter and a sync.Map to store per-IP
limiters. Need to handle cleanup of stale entries too, otherwise it's a
memory leak. I'll keep the greetHandler unchanged and show how to compose.
</think>

Here's a reusable rate-limiting middleware using `golang.org/x/time/rate`:

```go
package main

import (
    "encoding/json"
    "net"
    "net/http"
    "regexp"
    "sync"
    "time"

    "golang.org/x/time/rate"
)

// --- Rate limiter middleware ---

type IPRateLimiter struct {
    mu       sync.Mutex
    limiters map[string]*rateLimiterEntry
    rate     rate.Limit
    burst    int
}

type rateLimiterEntry struct {
    limiter  *rate.Limiter
    lastSeen time.Time
}

func NewIPRateLimiter(r rate.Limit, burst int) *IPRateLimiter {
    rl := &IPRateLimiter{
        limiters: make(map[string]*rateLimiterEntry),
        rate:     r,
        burst:    burst,
    }
    go rl.cleanup(5 * time.Minute)
    return rl
}

func (rl *IPRateLimiter) getLimiter(ip string) *rate.Limiter {
    rl.mu.Lock()
    defer rl.mu.Unlock()

    entry, exists := rl.limiters[ip]
    if !exists {
        limiter := rate.NewLimiter(rl.rate, rl.burst)
        rl.limiters[ip] = &rateLimiterEntry{limiter: limiter, lastSeen: time.Now()}
        return limiter
    }
    entry.lastSeen = time.Now()
    return entry.limiter
}

func (rl *IPRateLimiter) cleanup(interval time.Duration) {
    for {
        time.Sleep(interval)
        rl.mu.Lock()
        for ip, entry := range rl.limiters {
            if time.Since(entry.lastSeen) > 10*time.Minute {
                delete(rl.limiters, ip)
            }
        }
        rl.mu.Unlock()
    }
}

func RateLimit(rl *IPRateLimiter) func(http.Handler) http.Handler {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            ip, _, err := net.SplitHostPort(r.RemoteAddr)
            if err != nil {
                ip = r.RemoteAddr
            }

            if !rl.getLimiter(ip).Allow() {
                w.Header().Set("Content-Type", "application/json")
                w.WriteHeader(http.StatusTooManyRequests)
                json.NewEncoder(w).Encode(ErrorResponse{Error: "rate limit exceeded, try again later"})
                return
            }
            next.ServeHTTP(w, r)
        })
    }
}

// --- Existing handler code (unchanged) ---

var namePattern = regexp.MustCompile(`^[a-zA-Z ]{1,100}$`)

type GreetRequest struct{ Name string `json:"name"` }
type GreetResponse struct{ Message string `json:"message"` }
type ErrorResponse struct{ Error string `json:"error"` }

func greetHandler(w http.ResponseWriter, r *http.Request) {
    var req GreetRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        w.Header().Set("Content-Type", "application/json")
        w.WriteHeader(http.StatusBadRequest)
        json.NewEncoder(w).Encode(ErrorResponse{Error: "invalid JSON body"})
        return
    }
    if !namePattern.MatchString(req.Name) {
        w.Header().Set("Content-Type", "application/json")
        w.WriteHeader(http.StatusBadRequest)
        json.NewEncoder(w).Encode(ErrorResponse{Error: "name must be 1-100 characters, letters and spaces only"})
        return
    }
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(GreetResponse{Message: "Hello, " + req.Name + "!"})
}

func main() {
    // 10 requests per minute per IP (rate.Every converts interval to rate.Limit)
    limiter := NewIPRateLimiter(rate.Every(6*time.Second), 10)
    rateMw := RateLimit(limiter)

    // Apply to any handler
    http.Handle("/greet", rateMw(http.HandlerFunc(greetHandler)))
    http.Handle("/other", rateMw(http.HandlerFunc(otherHandler)))

    http.ListenAndServe(":8080", nil)
}
```

Run `go get golang.org/x/time/rate` to add the dependency.

How it works:
- **`IPRateLimiter`** stores a `rate.Limiter` per IP with a `lastSeen` timestamp for cleanup.
- **`RateLimit()`** returns standard middleware (`func(http.Handler) http.Handler`) so you can wrap any handler.
- **Cleanup goroutine** evicts IPs not seen in 10 minutes to prevent unbounded memory growth.
- **`rate.Every(6*time.Second)` with burst 10** means 10 requests per minute sustained, with burst capacity of 10 for short spikes.
- Your `greetHandler` is completely unchanged from the previous version.'''
    ),
    (
        "multi_turn/typescript-form-validation-refinement",
        r'''<conversation>
User: Write a TypeScript function to validate an email address.
Assistant: Here's a basic email validator:

```typescript
function isValidEmail(email: string): boolean {
  const pattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return pattern.test(email);
}
```

This checks for the basic `local@domain.tld` structure.
User: Now I need to validate a whole registration form — email, password (min 8 chars, one uppercase, one number), and age (18+). Return all validation errors at once, not just the first one.
Assistant: Here's a form validator that collects all errors:

```typescript
interface RegistrationForm {
  email: string;
  password: string;
  age: number;
}

interface ValidationResult {
  valid: boolean;
  errors: Record<string, string[]>;
}

function validateRegistration(form: RegistrationForm): ValidationResult {
  const errors: Record<string, string[]> = {};

  // Email
  const emailErrors: string[] = [];
  if (!form.email) emailErrors.push("Email is required");
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email))
    emailErrors.push("Invalid email format");
  if (emailErrors.length) errors.email = emailErrors;

  // Password
  const pwErrors: string[] = [];
  if (!form.password) pwErrors.push("Password is required");
  else {
    if (form.password.length < 8) pwErrors.push("Must be at least 8 characters");
    if (!/[A-Z]/.test(form.password)) pwErrors.push("Must contain an uppercase letter");
    if (!/[0-9]/.test(form.password)) pwErrors.push("Must contain a number");
  }
  if (pwErrors.length) errors.password = pwErrors;

  // Age
  const ageErrors: string[] = [];
  if (form.age == null) ageErrors.push("Age is required");
  else if (form.age < 18) ageErrors.push("Must be at least 18 years old");
  if (ageErrors.length) errors.age = ageErrors;

  return { valid: Object.keys(errors).length === 0, errors };
}
```
User: This works but it's not reusable. Refactor it into a composable validation library where I can define field rules declaratively and reuse them across different forms.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user wants a composable, declarative validation system. I should create
a builder pattern or schema-based approach where validators are small
reusable functions that can be composed per-field. Think Zod-like but simpler
and focused on form validation. I'll define a Validator type, some built-in
validators, and a schema builder that combines them. The API should let you
declare something like: schema({ email: [required(), email()], password: [required(), minLength(8)] }).
</think>

Here's a composable validation library with declarative field rules:

```typescript
// --- Core types ---

type Validator = (value: unknown) => string | null;

interface ValidationResult {
  valid: boolean;
  errors: Record<string, string[]>;
}

type Schema = Record<string, Validator[]>;

// --- Validation engine ---

function validate(schema: Schema, data: Record<string, unknown>): ValidationResult {
  const errors: Record<string, string[]> = {};

  for (const [field, validators] of Object.entries(schema)) {
    const fieldErrors: string[] = [];
    for (const validator of validators) {
      const error = validator(data[field]);
      if (error) fieldErrors.push(error);
    }
    if (fieldErrors.length) errors[field] = fieldErrors;
  }

  return { valid: Object.keys(errors).length === 0, errors };
}

// --- Built-in validators (composable) ---

const required = (msg = "This field is required"): Validator =>
  (value) => (value == null || value === "" ? msg : null);

const minLength = (min: number, msg?: string): Validator =>
  (value) =>
    typeof value === "string" && value.length < min
      ? msg ?? `Must be at least ${min} characters`
      : null;

const maxLength = (max: number, msg?: string): Validator =>
  (value) =>
    typeof value === "string" && value.length > max
      ? msg ?? `Must be at most ${max} characters`
      : null;

const pattern = (regex: RegExp, msg: string): Validator =>
  (value) =>
    typeof value === "string" && !regex.test(value) ? msg : null;

const email = (msg = "Invalid email format"): Validator =>
  pattern(/^[^\s@]+@[^\s@]+\.[^\s@]+$/, msg);

const minValue = (min: number, msg?: string): Validator =>
  (value) =>
    typeof value === "number" && value < min
      ? msg ?? `Must be at least ${min}`
      : null;

// --- Usage: define schemas declaratively ---

const registrationSchema: Schema = {
  email: [required(), email()],
  password: [
    required(),
    minLength(8),
    pattern(/[A-Z]/, "Must contain an uppercase letter"),
    pattern(/[0-9]/, "Must contain a number"),
  ],
  age: [required(), minValue(18, "Must be at least 18 years old")],
};

const profileSchema: Schema = {
  displayName: [required(), minLength(2), maxLength(50)],
  bio: [maxLength(500)],
};

// Both use the same engine
const regResult = validate(registrationSchema, { email: "bad", password: "short", age: 16 });
const profileResult = validate(profileSchema, { displayName: "", bio: "Hello" });
```

The same validators from the registration form are now reusable across any schema. To add a new rule, just write a function matching `(value: unknown) => string | null`. The `validate()` engine stays the same regardless of how many forms or fields you have.'''
    ),
    (
        "multi_turn/hive-transfer-refinement",
        r'''<conversation>
User: How do I send HIVE tokens to another account using dhive in JavaScript?
Assistant: Here's a basic HIVE transfer:

```javascript
const { Client, PrivateKey } = require('@hiveio/dhive');

const client = new Client(['https://api.hive.blog']);
const key = PrivateKey.fromString('your-active-key');

async function transferHive(from, to, amount, memo) {
  const op = ['transfer', { from, to, amount: `${amount.toFixed(3)} HIVE`, memo }];
  const result = await client.broadcast.sendOperations([op], key);
  console.log('TX ID:', result.id);
}

transferHive('alice', 'bob', 1.0, 'payment for services');
```
User: This doesn't handle errors well. What if the account doesn't exist, or I have insufficient balance? Also I need to support both HIVE and HBD.
Assistant: Here's the improved version:

```javascript
const { Client, PrivateKey } = require('@hiveio/dhive');

const client = new Client([
  'https://api.hive.blog',
  'https://api.deathwing.me',
  'https://anyx.io',
]);

async function transferTokens(from, to, amount, currency, memo, activeKey) {
  // Validate currency
  if (!['HIVE', 'HBD'].includes(currency)) {
    throw new Error(`Invalid currency: ${currency}. Use HIVE or HBD.`);
  }

  // Check recipient exists
  const [account] = await client.database.getAccounts([to]);
  if (!account) {
    throw new Error(`Recipient account @${to} does not exist`);
  }

  // Check sender balance
  const [sender] = await client.database.getAccounts([from]);
  const balanceField = currency === 'HIVE' ? 'balance' : 'hbd_balance';
  const balance = parseFloat(sender[balanceField]);
  if (balance < amount) {
    throw new Error(`Insufficient ${currency} balance: ${balance.toFixed(3)} < ${amount.toFixed(3)}`);
  }

  const key = PrivateKey.fromString(activeKey);
  const op = ['transfer', {
    from, to,
    amount: `${amount.toFixed(3)} ${currency}`,
    memo
  }];

  const result = await client.broadcast.sendOperations([op], key);
  return { txId: result.id, block: result.block_num };
}
```
User: Perfect. Now I need to support encrypted memos too. And wrap this as a proper class with transaction history tracking so I can query past transfers I've made in this session.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user wants two additions: encrypted memos (Hive supports memo encryption
using the recipient's public memo key, prefixed with #) and a class wrapper
that tracks transaction history for the session. I'll use dhive's Memo.encode
for encryption. The class should store each successful transfer in an array
with timestamps and provide query methods. I need the sender's memo private
key and the recipient's public memo key from the chain.
</think>

Here's the class-based version with encrypted memos and session history:

```javascript
const { Client, PrivateKey, Memo } = require('@hiveio/dhive');

class HiveWallet {
  constructor(username, activeKey, memoKey = null) {
    this.username = username;
    this.activeKey = PrivateKey.fromString(activeKey);
    this.memoKey = memoKey ? PrivateKey.fromString(memoKey) : null;
    this.client = new Client([
      'https://api.hive.blog',
      'https://api.deathwing.me',
      'https://anyx.io',
    ]);
    this.history = [];
  }

  async transfer(to, amount, currency, memo = '', { encrypt = false } = {}) {
    if (!['HIVE', 'HBD'].includes(currency)) {
      throw new Error(`Invalid currency: ${currency}. Use HIVE or HBD.`);
    }

    // Validate recipient
    const [recipient] = await this.client.database.getAccounts([to]);
    if (!recipient) {
      throw new Error(`Recipient account @${to} does not exist`);
    }

    // Check balance
    const [sender] = await this.client.database.getAccounts([this.username]);
    const balanceField = currency === 'HIVE' ? 'balance' : 'hbd_balance';
    const available = parseFloat(sender[balanceField]);
    if (available < amount) {
      throw new Error(
        `Insufficient ${currency}: have ${available.toFixed(3)}, need ${amount.toFixed(3)}`
      );
    }

    // Encrypt memo if requested
    let finalMemo = memo;
    if (encrypt && memo) {
      if (!this.memoKey) {
        throw new Error('Memo private key required for encryption. Pass memoKey to constructor.');
      }
      const recipientMemoPublic = recipient.memo_key;
      finalMemo = Memo.encode(this.memoKey, recipientMemoPublic, `#${memo}`);
    }

    // Broadcast
    const op = ['transfer', {
      from: this.username,
      to,
      amount: `${amount.toFixed(3)} ${currency}`,
      memo: finalMemo,
    }];

    const result = await this.client.broadcast.sendOperations([op], this.activeKey);

    // Track in session history
    const record = {
      txId: result.id,
      block: result.block_num,
      to,
      amount,
      currency,
      memo: encrypt ? '(encrypted)' : memo,
      encrypted: encrypt,
      timestamp: new Date().toISOString(),
    };
    this.history.push(record);

    return record;
  }

  getHistory({ to = null, currency = null, minAmount = 0 } = {}) {
    return this.history.filter((tx) => {
      if (to && tx.to !== to) return false;
      if (currency && tx.currency !== currency) return false;
      if (tx.amount < minAmount) return false;
      return true;
    });
  }

  getTotalSent(currency = 'HIVE') {
    return this.history
      .filter((tx) => tx.currency === currency)
      .reduce((sum, tx) => sum + tx.amount, 0);
  }
}

// Usage
const wallet = new HiveWallet('alice', '5K...activeKey', '5K...memoKey');

await wallet.transfer('bob', 1.5, 'HIVE', 'Thanks!');
await wallet.transfer('carol', 10.0, 'HBD', 'Secret payment', { encrypt: true });

console.log(wallet.getHistory({ to: 'bob' }));
console.log(`Total HIVE sent: ${wallet.getTotalSent('HIVE')}`);
```

Key additions over the previous version:
- **Encrypted memos** — pass `{ encrypt: true }` to use Hive's built-in memo encryption. It uses your private memo key and the recipient's public memo key from the chain. The encrypted memo is prefixed with `#` per Hive protocol convention.
- **Session history** — every successful transfer is recorded with a timestamp. The history is stored in memory (cleared when the instance is garbage collected).
- **`getHistory()`** — filter past transfers by recipient, currency, or minimum amount.
- **`getTotalSent()`** — quick sum of all outgoing transfers by currency.'''
    ),

    # =====================================================================
    # 6-10: BUG REPORT FLOW
    # =====================================================================
    (
        "multi_turn/python-sorting-bug",
        r'''<conversation>
User: My sorting function isn't working. It's supposed to sort a list of dicts by a "priority" key, but the output order is wrong.

```python
def sort_tasks(tasks):
    return sorted(tasks, key=lambda t: t['priority'])

tasks = [
    {'name': 'Deploy', 'priority': 'high'},
    {'name': 'Test', 'priority': 'medium'},
    {'name': 'Fix bug', 'priority': 'critical'},
    {'name': 'Docs', 'priority': 'low'},
]
print(sort_tasks(tasks))
```

It prints: critical, high, low, medium. But I want: critical, high, medium, low.
Assistant: The issue is that you're sorting strings alphabetically. "critical" < "high" < "low" < "medium" in lexicographic order, which happens to almost look right but isn't. You need to define a priority ordering:

```python
PRIORITY_ORDER = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}

def sort_tasks(tasks):
    return sorted(tasks, key=lambda t: PRIORITY_ORDER[t['priority']])
```
User: I tried that but now I'm getting a KeyError. Some tasks have priority "urgent" which isn't in the mapping.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user has tasks with priority values not in the mapping dict. A KeyError
occurs when a priority like "urgent" is looked up. I need to handle unknown
priorities gracefully — either by using dict.get() with a default value, or
by raising a clearer error. Using a default is more resilient. I should
suggest placing unknown priorities either first (highest) or last, depending
on what makes sense. I'll default unknowns to -1 (sort first) since an
unrecognized priority probably needs attention.
</think>

The `KeyError` is because `"urgent"` isn't in your `PRIORITY_ORDER` dict. Use `.get()` with a sensible default:

```python
PRIORITY_ORDER = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}

def sort_tasks(tasks):
    # Unknown priorities sort first (value -1) so they get attention
    return sorted(tasks, key=lambda t: PRIORITY_ORDER.get(t['priority'], -1))
```

Now `"urgent"` (or any unknown priority) gets value `-1` and sorts to the top of the list, which is usually what you want — unrecognized priorities are likely important and should be visible.

If you'd rather unknown priorities sort to the bottom instead, change `-1` to `999`. Or if you want to fail loudly on bad data during development but be lenient in production:

```python
import os

def priority_key(task):
    p = task['priority']
    if p not in PRIORITY_ORDER:
        if os.getenv('DEBUG'):
            raise ValueError(f"Unknown priority: {p!r}. Valid: {list(PRIORITY_ORDER)}")
        return -1  # sort first in production
    return PRIORITY_ORDER[p]

def sort_tasks(tasks):
    return sorted(tasks, key=priority_key)
```'''
    ),
    (
        "multi_turn/rust-lifetime-bug",
        r'''<conversation>
User: I'm getting a confusing lifetime error in Rust. Here's my code:

```rust
struct Config {
    name: String,
}

fn get_greeting(config: &Config) -> &str {
    let greeting = format!("Hello, {}!", config.name);
    &greeting
}
```

Error: `cannot return reference to local variable 'greeting'`
Assistant: The problem is that `greeting` is a `String` created inside the function. When the function returns, `greeting` is dropped, so the reference would dangle. You need to return an owned `String` instead:

```rust
fn get_greeting(config: &Config) -> String {
    format!("Hello, {}!", config.name)
}
```
User: OK that works, but now I have a different issue. I'm calling this in a loop and the allocations are killing performance. I profiled it and `get_greeting` is called millions of times. Can I avoid the allocation somehow?
Assistant: You could pass a reusable buffer:

```rust
use std::fmt::Write;

fn write_greeting(config: &Config, buf: &mut String) {
    buf.clear();
    write!(buf, "Hello, {}!", config.name).unwrap();
}

// In your loop:
let mut buf = String::with_capacity(256);
for config in &configs {
    write_greeting(config, &mut buf);
    process(&buf);
}
```

This reuses the same allocation across iterations.
User: I tried this but now I'm getting a borrow checker error in my actual code. Here's what I really have:

```rust
let mut buf = String::with_capacity(256);
let mut results: Vec<&str> = Vec::new();
for config in &configs {
    write_greeting(config, &mut buf);
    results.push(&buf);  // ERROR: cannot borrow `buf` as mutable because it is also borrowed as immutable
}
```
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user is pushing &buf into a Vec, which borrows buf immutably, then on
the next loop iteration they call write_greeting which mutably borrows buf
(via buf.clear()). This conflicts. The fundamental issue is they want to
keep references to a buffer that gets overwritten each iteration. They need
to either collect owned Strings (which defeats the purpose), use an arena
allocator, or restructure to process results inline. Let me suggest a few
approaches depending on their actual use case.
</think>

This is a classic Rust borrow conflict. You're holding `&buf` in `results` (immutable borrow) while also calling `write_greeting` which does `buf.clear()` (mutable borrow). The borrow checker is right to stop you — if it allowed this, `results` would contain dangling references to overwritten data.

You have a few options depending on what you actually need:

**Option 1: Process inline instead of collecting** (zero allocation)
```rust
let mut buf = String::with_capacity(256);
for config in &configs {
    write_greeting(config, &mut buf);
    process(&buf);  // handle each result immediately
}
```

**Option 2: Collect owned Strings** (one allocation per result, but simple)
```rust
let results: Vec<String> = configs.iter().map(|c| get_greeting(c)).collect();
```

**Option 3: Arena allocator** (many results, minimal allocations)
```rust
// Add `bumpalo = "3"` to Cargo.toml
use bumpalo::Bump;

let arena = Bump::new();
let mut buf = String::with_capacity(256);
let mut results: Vec<&str> = Vec::new();

for config in &configs {
    write_greeting(config, &mut buf);
    // Copy the current buf contents into the arena — the arena outlives the loop
    let stored: &str = arena.alloc_str(&buf);
    results.push(stored);
}
// results is valid here; all strings live in the arena
```

Option 3 gives you the best of both worlds — reuse the formatting buffer, but store each result in an arena that keeps everything alive. The arena does one big allocation instead of millions of small ones.

Choose based on your actual need: if you can process results one at a time, Option 1 is best. If you truly need to collect them all, Option 3 avoids per-string allocation overhead.'''
    ),
    (
        "multi_turn/go-goroutine-leak-bug",
        r'''<conversation>
User: I have a Go service that's leaking memory. After running for a few hours the RSS keeps growing. Here's the relevant code:

```go
func processJobs(jobs <-chan Job) {
    for job := range jobs {
        go func() {
            result := heavyComputation(job)
            saveResult(result)
        }()
    }
}
```
Assistant: I see a goroutine variable capture bug. The closure captures `job` by reference, but since the loop variable changes each iteration, multiple goroutines may end up processing the same job (or the wrong one). Fix with a parameter:

```go
go func(j Job) {
    result := heavyComputation(j)
    saveResult(result)
}(job)
```

But this alone shouldn't cause a memory leak — it would cause incorrect results. Is there something else going on?
User: Good catch on the capture bug, but you're right — the memory is still growing after fixing that. I added pprof and the goroutine count keeps increasing. Thousands of goroutines are stuck.
Assistant: If goroutines are stuck, either `heavyComputation` or `saveResult` is blocking and never returning. Can you share what those functions do? Specifically, do they make network calls, write to channels, or acquire locks?
User: `heavyComputation` is CPU-bound, that's fine. But `saveResult` writes to a channel:

```go
var resultChan = make(chan Result)

func saveResult(r Result) {
    resultChan <- r
}
```

And in another goroutine I read from it:

```go
go func() {
    for r := range resultChan {
        db.Insert(r)
    }
}()
```
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The issue is now clear. `resultChan` is an unbuffered channel. If `db.Insert`
is slow (network, disk, lock contention), the single reader goroutine can't
keep up with the writers. Each goroutine calling `saveResult` blocks on the
channel send until the reader is available. With hundreds of jobs being
spawned as goroutines, they all pile up blocked on the channel send, leading
to the goroutine count growing forever. Solutions: buffer the channel, use a
worker pool to limit concurrency, or both.
</think>

Found it. `resultChan` is **unbuffered** (`make(chan Result)` with no capacity), and you have a **single reader** goroutine. Here's what happens:

1. Jobs spawn goroutines as fast as they arrive.
2. Each goroutine finishes `heavyComputation` and tries to send on `resultChan`.
3. The single reader can only consume one result at a time (blocked on `db.Insert`).
4. All other goroutines block on `resultChan <- r`, waiting for the reader.
5. New jobs keep spawning new goroutines, which also block. Goroutine count grows without bound.

Two-part fix — **buffer the channel AND limit concurrency**:

```go
var resultChan = make(chan Result, 1000) // buffered

func processJobs(jobs <-chan Job) {
    // Worker pool: limit to N concurrent goroutines
    sem := make(chan struct{}, 20)

    for job := range jobs {
        sem <- struct{}{} // blocks when 20 goroutines are active
        go func(j Job) {
            defer func() { <-sem }()
            result := heavyComputation(j)
            saveResult(result)
        }(job)
    }
}
```

And optionally use multiple reader goroutines for `db.Insert`:

```go
// Multiple DB writers to drain the channel faster
for i := 0; i < 5; i++ {
    go func() {
        for r := range resultChan {
            db.Insert(r)
        }
    }()
}
```

The key fixes:
- **Buffered channel** (`make(chan Result, 1000)`) absorbs bursts so goroutines don't block immediately.
- **Semaphore** (`sem` channel) caps active goroutines at 20, preventing unbounded spawning.
- **Multiple readers** drain the channel faster when `db.Insert` is the bottleneck.

The buffered channel alone isn't enough — if the producer is faster than the consumer long-term, it will eventually fill up and goroutines will block again. The semaphore is the real fix because it applies backpressure to job processing.'''
    ),
    (
        "multi_turn/typescript-async-race-bug",
        r'''<conversation>
User: I have a React component that fetches data on mount, but sometimes it shows stale data from a previous search. Here's the code:

```typescript
function SearchResults({ query }: { query: string }) {
  const [results, setResults] = useState<Item[]>([]);

  useEffect(() => {
    async function fetchData() {
      const data = await api.search(query);
      setResults(data);
    }
    fetchData();
  }, [query]);

  return <ResultList items={results} />;
}
```

If I type fast, sometimes results from an earlier query appear after the latest one.
Assistant: This is a classic race condition. When `query` changes rapidly, multiple `api.search()` calls are in flight simultaneously. If an earlier request returns after a later one, it overwrites the results. You need to ignore stale responses:

```typescript
useEffect(() => {
  let cancelled = false;

  async function fetchData() {
    const data = await api.search(query);
    if (!cancelled) {
      setResults(data);
    }
  }
  fetchData();

  return () => { cancelled = true; };
}, [query]);
```

The cleanup function sets `cancelled = true` when the effect is re-run, so stale responses are discarded.
User: That fixed the stale data issue, but now I have another problem. When the component unmounts during a fetch, I get a React warning: "Can't perform a React state update on an unmounted component." The cancelled flag should handle that too, right?
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The cancelled flag should handle unmount too, since the cleanup function runs
on unmount as well. If they're still seeing the warning, it could be because
there's another state update happening that isn't guarded, or they have
multiple async operations. But actually, in React 18+, this warning was
removed. Let me think about what else could cause it... Maybe they have a
loading state or error state that's also being set without checking cancelled.
Or they're on React 17. Let me address both possibilities.
</think>

Yes, the `cancelled` flag should handle unmount too — React runs the cleanup function both when dependencies change AND when the component unmounts. If you're still seeing the warning, there are two likely causes:

**1. You have other state updates that aren't guarded:**

```typescript
useEffect(() => {
  let cancelled = false;

  async function fetchData() {
    setLoading(true);  // <-- this one is fine (synchronous, runs before any await)
    try {
      const data = await api.search(query);
      if (!cancelled) {
        setResults(data);
        setLoading(false);  // guarded - good
      }
    } catch (err) {
      if (!cancelled) {
        setError(err);     // guard this too!
        setLoading(false);  // and this
      }
    }
  }
  fetchData();

  return () => { cancelled = true; };
}, [query]);
```

Every `setState` call after an `await` needs the `cancelled` check.

**2. You're on React 17 or earlier.** In React 18+, this warning was actually removed — React silently ignores state updates on unmounted components. If you're on 17, upgrading to 18 eliminates the warning entirely.

For a cleaner approach that handles both problems, use `AbortController` to actually cancel the network request (not just ignore the response):

```typescript
useEffect(() => {
  const controller = new AbortController();

  async function fetchData() {
    try {
      const data = await api.search(query, { signal: controller.signal });
      setResults(data);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return; // request was cancelled, do nothing
      }
      setError(err);
    }
  }
  fetchData();

  return () => controller.abort();
}, [query]);
```

This is better because it actually cancels the HTTP request, saving bandwidth and server resources — the `cancelled` flag approach still lets the request complete, it just ignores the result.'''
    ),
    (
        "multi_turn/hive-voting-power-bug",
        r'''<conversation>
User: I'm building a Hive bot that auto-votes on posts, but my voting power calculation seems wrong. Here's my code:

```javascript
async function getVotingPower(username) {
  const [account] = await client.database.getAccounts([username]);
  return account.voting_power / 100; // should give percentage
}
```

It always returns the same number even after I vote multiple times.
Assistant: The `voting_power` field in the account object is not updated in real-time — it represents a snapshot value. Voting power regenerates over time (it takes ~5 days to go from 0% to 100%). You need to calculate the current power based on `last_vote_time` and the stored value:

```javascript
async function getVotingPower(username) {
  const [account] = await client.database.getAccounts([username]);
  const lastVoteTime = new Date(account.last_vote_time + 'Z').getTime();
  const now = Date.now();
  const secondsSinceVote = (now - lastVoteTime) / 1000;

  // Regenerates 20% per day (full regen in 5 days)
  const regenPerSecond = 10000 / (5 * 24 * 3600); // in basis points
  const currentPower = Math.min(
    10000,
    account.voting_power + secondsSinceVote * regenPerSecond
  );

  return currentPower / 100; // percentage
}
```
User: OK that's better, but when I compare my calculated power with what HiveBuzz shows, I'm off by about 2-3%. Not sure what's wrong.
Assistant: The discrepancy might be because `last_vote_time` is in UTC but you might be comparing at different times. Also, make sure you're appending 'Z' to the timestamp to parse it as UTC. Let me also check — are you using this value to calculate vote weight for your bot?
User: Yes I append the Z already. And yes, I use the power value to decide if I should vote (only vote if above 80%). But the discrepancy is consistent — my value is always higher than what HiveBuzz reports. Could it be that votes I cast aren't reflected in `voting_power` immediately?
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user's calculated value is consistently higher than what HiveBuzz shows.
The issue is likely that `account.voting_power` from `getAccounts` is a
stale snapshot from the last time the blockchain recorded a vote. Each vote
reduces voting power, but if the user's bot has cast votes that haven't been
reflected in a new `getAccounts` call, the calculation will be off. Actually,
more precisely — the `voting_power` field IS updated each time a vote is
broadcast and included in a block. But if the user is voting through their
bot and then immediately checking, there could be a delay. However, the more
likely issue is that the account has cast votes from OTHER sources (manual
votes, other bots) that the bot doesn't know about. Each vote deducts power,
and the calculation above only regenerates from the last recorded vote, but
doesn't account for multiple votes. Actually wait — `voting_power` and
`last_vote_time` ARE updated on-chain with each vote, so getAccounts should
reflect the latest state. The 2-3% discrepancy... HiveBuzz might be using
the newer HF26 manabar system which replaced `voting_power`. Since HF26,
voting power uses the `voting_manabar` field with `current_mana` and
`last_update_time`.
</think>

The problem is that you're using the **deprecated** `voting_power` field. Since Hive hard fork 26 (and even earlier with HF20's manabar system), the correct field is `voting_manabar`:

```javascript
async function getVotingPower(username) {
  const [account] = await client.database.getAccounts([username]);

  const maxMana = getEffectiveVests(account);
  const { current_mana, last_update_time } = account.voting_manabar;

  const now = Math.floor(Date.now() / 1000);
  const elapsed = now - last_update_time;

  // Mana regenerates fully in 5 days (432000 seconds)
  const regenerated = (maxMana * elapsed) / 432000;
  const currentMana = Math.min(maxMana, Number(current_mana) + regenerated);

  return (currentMana / maxMana) * 100; // percentage
}

function getEffectiveVests(account) {
  // Effective vesting = own vests + received delegations - outgoing delegations
  const own = parseFloat(account.vesting_shares);
  const received = parseFloat(account.received_vesting_shares);
  const delegated = parseFloat(account.delegated_vesting_shares);
  return (own + received - delegated) * 1e6; // convert to base units
}
```

Why your old code was always higher:
- `voting_power` is a legacy field that isn't accurately maintained post-HF26.
- `voting_manabar.current_mana` is the actual value the blockchain uses when you broadcast a vote.
- HiveBuzz uses the manabar system, which is why their number was always lower (and correct).

The `getEffectiveVests` calculation is also important — if you have delegations in or out, that changes your max mana and therefore your percentage. The old `voting_power` field didn't account for delegation changes properly.'''
    ),

    # =====================================================================
    # 11-15: REQUIREMENTS CHANGE
    # =====================================================================
    (
        "multi_turn/python-cache-requirements-change",
        r'''<conversation>
User: I need a simple in-memory cache in Python with a max size. When it's full, evict the oldest entry.
Assistant: Here's an LRU cache using `OrderedDict`:

```python
from collections import OrderedDict

class LRUCache:
    def __init__(self, max_size: int = 100):
        self._cache = OrderedDict()
        self._max_size = max_size

    def get(self, key):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        elif len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        self._cache[key] = value
```
User: Actually, I also need TTL (time-to-live) support. Each entry should expire after N seconds regardless of whether the cache is full.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user wants TTL on top of the LRU cache. I need to store timestamps with
each entry and check expiry on get. I should also handle lazy expiry (check
on access) and optionally periodic cleanup. I'll store (value, expiry_time)
tuples and add a default_ttl parameter. Let me also add a cleanup method
to purge expired entries proactively.
</think>

Here's the cache with TTL support added:

```python
import time
from collections import OrderedDict
from typing import Any

class LRUCache:
    def __init__(self, max_size: int = 100, default_ttl: float = 300.0):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any:
        if key not in self._cache:
            return None

        value, expires_at = self._cache[key]

        # Expired — remove and return None
        if time.monotonic() >= expires_at:
            del self._cache[key]
            return None

        self._cache.move_to_end(key)
        return value

    def put(self, key: str, value: Any, ttl: float | None = None) -> None:
        if ttl is None:
            ttl = self._default_ttl

        expires_at = time.monotonic() + ttl

        if key in self._cache:
            self._cache.move_to_end(key)
        elif len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)

        self._cache[key] = (value, expires_at)

    def cleanup(self) -> int:
        """Remove all expired entries. Returns number of entries removed."""
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._cache.items() if now >= exp]
        for k in expired:
            del self._cache[k]
        return len(expired)

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None
```

Changes from the original:

- Each entry stores `(value, expires_at)` instead of just `value`.
- **`time.monotonic()`** instead of `time.time()` — immune to clock adjustments.
- **Per-key TTL** — `put("key", val, ttl=60)` overrides the default for that entry.
- **Lazy expiry** — expired entries are removed on `get()`. No background thread needed.
- **`cleanup()`** — call periodically if you want proactive eviction (e.g., from a timer or before serialization).
- LRU eviction still works as before when the cache is full.'''
    ),
    (
        "multi_turn/rust-cli-requirements-change",
        r'''<conversation>
User: Write a Rust CLI tool that counts lines in a file.
Assistant: Here's a simple line counter using `clap`:

```rust
use clap::Parser;
use std::fs;

#[derive(Parser)]
#[command(name = "lc", about = "Count lines in a file")]
struct Cli {
    /// File to count lines in
    file: String,
}

fn main() {
    let cli = Cli::parse();
    let content = fs::read_to_string(&cli.file).expect("Failed to read file");
    let count = content.lines().count();
    println!("{}", count);
}
```
User: Works great, but I also need to count words and characters too, with flags to choose which counts to show. Like `wc` on Unix. And support reading from stdin if no file is given.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user wants to expand this from a simple line counter to a wc clone with
flags for lines/words/chars, and stdin support. I need to add clap flags,
read from either file or stdin, and compute all three counts. If no flags
are specified, show all counts (like wc does).
</think>

Here's the expanded version with word/char counts, flags, and stdin support:

```rust
use clap::Parser;
use std::fs;
use std::io::{self, Read};

#[derive(Parser)]
#[command(name = "lc", about = "Count lines, words, and characters")]
struct Cli {
    /// File to process (reads stdin if omitted)
    file: Option<String>,

    /// Count lines
    #[arg(short, long)]
    lines: bool,

    /// Count words
    #[arg(short, long)]
    words: bool,

    /// Count characters
    #[arg(short, long)]
    chars: bool,
}

struct Counts {
    lines: usize,
    words: usize,
    chars: usize,
}

fn count(text: &str) -> Counts {
    Counts {
        lines: text.lines().count(),
        words: text.split_whitespace().count(),
        chars: text.chars().count(),
    }
}

fn read_input(file: Option<&str>) -> Result<String, io::Error> {
    match file {
        Some(path) => fs::read_to_string(path),
        None => {
            let mut buf = String::new();
            io::stdin().read_to_string(&mut buf)?;
            Ok(buf)
        }
    }
}

fn main() {
    let cli = Cli::parse();

    let content = read_input(cli.file.as_deref()).unwrap_or_else(|e| {
        eprintln!("Error: {e}");
        std::process::exit(1);
    });

    let counts = count(&content);

    // If no flags specified, show everything (like wc)
    let show_all = !cli.lines && !cli.words && !cli.chars;

    let mut parts = Vec::new();
    if show_all || cli.lines {
        parts.push(format!("{:>8}", counts.lines));
    }
    if show_all || cli.words {
        parts.push(format!("{:>8}", counts.words));
    }
    if show_all || cli.chars {
        parts.push(format!("{:>8}", counts.chars));
    }

    let label = cli.file.as_deref().unwrap_or("");
    println!("{} {}", parts.join(""), label);
}
```

Usage:
```bash
# All counts for a file
lc myfile.txt
#     42     300    1850 myfile.txt

# Lines only
lc -l myfile.txt

# Words and chars from stdin
echo "hello world" | lc -w -c

# Combine flags
lc -lw myfile.txt
```

Key differences from the original:
- **`file` is now `Option<String>`** — when `None`, reads from stdin.
- **Three flags** (`-l`, `-w`, `-c`) control output. If none are specified, all counts are shown, matching `wc` behavior.
- **Output is right-aligned to 8 columns** to match the `wc` format.'''
    ),
    (
        "multi_turn/go-worker-requirements-change",
        r'''<conversation>
User: I need a Go function that processes items from a slice concurrently using a worker pool of N goroutines.
Assistant: Here's a basic worker pool:

```go
func processItems[T any](items []T, workers int, fn func(T) error) error {
    ch := make(chan T)
    var wg sync.WaitGroup

    // Start workers
    for i := 0; i < workers; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for item := range ch {
                if err := fn(item); err != nil {
                    log.Printf("error processing item: %v", err)
                }
            }
        }()
    }

    // Send items
    for _, item := range items {
        ch <- item
    }
    close(ch)
    wg.Wait()
    return nil
}
```
User: Actually, I need to collect results too — each worker produces an output value. And I need to be able to cancel the whole pool if any single worker encounters a critical error.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user needs two additions: collecting results from workers, and
cancellation on error. I should use generics for input/output types, an
errgroup or context for cancellation, and a results channel to collect
outputs. I'll use errgroup since it handles the cancel-on-first-error
pattern well. Need to be careful about the results channel — it should be
buffered or drained to avoid deadlock.
</think>

Here's the pool with result collection and cancellation:

```go
package pool

import (
    "context"
    "sync"

    "golang.org/x/sync/errgroup"
)

type Result[T any] struct {
    Value T
    Err   error
}

func ProcessItems[In, Out any](
    ctx context.Context,
    items []In,
    workers int,
    fn func(context.Context, In) (Out, error),
) ([]Out, error) {
    g, ctx := errgroup.WithContext(ctx)
    inputCh := make(chan In)

    // Collect results safely
    var mu sync.Mutex
    results := make([]Out, 0, len(items))

    // Start workers
    for i := 0; i < workers; i++ {
        g.Go(func() error {
            for item := range inputCh {
                // Check cancellation before processing
                select {
                case <-ctx.Done():
                    return ctx.Err()
                default:
                }

                out, err := fn(ctx, item)
                if err != nil {
                    return err // cancels the group
                }

                mu.Lock()
                results = append(results, out)
                mu.Unlock()
            }
            return nil
        })
    }

    // Feed items (in a separate goroutine so we don't block)
    g.Go(func() error {
        defer close(inputCh)
        for _, item := range items {
            select {
            case inputCh <- item:
            case <-ctx.Done():
                return ctx.Err()
            }
        }
        return nil
    })

    if err := g.Wait(); err != nil {
        return nil, err
    }
    return results, nil
}
```

Usage:

```go
ctx := context.Background()

urls := []string{"https://a.com", "https://b.com", "https://c.com"}

bodies, err := pool.ProcessItems(ctx, urls, 5, func(ctx context.Context, url string) (string, error) {
    req, _ := http.NewRequestWithContext(ctx, "GET", url, nil)
    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return "", err  // critical error — cancels all workers
    }
    defer resp.Body.Close()
    body, _ := io.ReadAll(resp.Body)
    return string(body), nil
})

if err != nil {
    log.Fatal("pool failed:", err)
}
fmt.Println("got", len(bodies), "results")
```

Key changes from the original:
- **Two generic types** (`In`, `Out`) — workers take an input and produce an output.
- **`errgroup.WithContext`** — when any worker returns an error, the context is cancelled, which signals all other workers to stop.
- **The `fn` receives a `context.Context`** so it can pass cancellation through to downstream calls (HTTP requests, DB queries, etc.).
- **Input feeder runs in the errgroup** too — it checks `ctx.Done()` so it stops sending items when the pool is cancelled.
- **Results are collected with a mutex** — simpler than a results channel and avoids deadlock risk.

Note: results are in arbitrary order since workers run concurrently. If you need ordered results, add an index to the output and sort after.'''
    ),
    (
        "multi_turn/typescript-api-requirements-change",
        r'''<conversation>
User: I need a TypeScript function to fetch user data from an API endpoint.
Assistant: Here's a typed fetch wrapper:

```typescript
interface User {
  id: number;
  name: string;
  email: string;
}

async function getUser(id: number): Promise<User> {
  const response = await fetch(`/api/users/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch user: ${response.status}`);
  }
  return response.json();
}
```
User: That works, but now I realize I need this for multiple endpoints — users, posts, comments. They all follow the same REST pattern. Can you make it generic? And actually, I also need POST/PUT/DELETE support.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user wants a generic REST client that works with any resource type and
supports all CRUD operations. I'll create a typed API client class with
generics, where you define resource types and get type-safe CRUD methods.
I'll use a builder or factory pattern so you can create typed endpoints easily.
</think>

Here's a generic, type-safe REST client:

```typescript
// --- Core types ---

interface ApiClientConfig {
  baseUrl: string;
  headers?: Record<string, string>;
}

interface RequestOptions {
  params?: Record<string, string>;
  signal?: AbortSignal;
}

class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body: unknown
  ) {
    super(`API error ${status}: ${statusText}`);
  }
}

// --- Generic API client ---

class ApiClient {
  constructor(private config: ApiClientConfig) {}

  resource<T extends { id: number | string }>(path: string) {
    return new Resource<T>(this.config, path);
  }

  private static async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const body = await response.text().catch(() => "");
      throw new ApiError(response.status, response.statusText, body);
    }
    return response.json();
  }
}

class Resource<T extends { id: number | string }> {
  constructor(
    private config: ApiClientConfig,
    private path: string
  ) {}

  private url(id?: number | string, params?: Record<string, string>): string {
    let url = `${this.config.baseUrl}${this.path}`;
    if (id !== undefined) url += `/${id}`;
    if (params) {
      const qs = new URLSearchParams(params).toString();
      if (qs) url += `?${qs}`;
    }
    return url;
  }

  private headers(extra?: Record<string, string>): Record<string, string> {
    return {
      "Content-Type": "application/json",
      ...this.config.headers,
      ...extra,
    };
  }

  private async request<R>(url: string, init: RequestInit): Promise<R> {
    const response = await fetch(url, init);
    if (!response.ok) {
      const body = await response.text().catch(() => "");
      throw new ApiError(response.status, response.statusText, body);
    }
    return response.json();
  }

  async list(opts?: RequestOptions): Promise<T[]> {
    return this.request<T[]>(this.url(undefined, opts?.params), {
      headers: this.headers(),
      signal: opts?.signal,
    });
  }

  async get(id: number | string, opts?: RequestOptions): Promise<T> {
    return this.request<T>(this.url(id, opts?.params), {
      headers: this.headers(),
      signal: opts?.signal,
    });
  }

  async create(data: Omit<T, "id">, opts?: RequestOptions): Promise<T> {
    return this.request<T>(this.url(undefined, opts?.params), {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(data),
      signal: opts?.signal,
    });
  }

  async update(id: number | string, data: Partial<T>, opts?: RequestOptions): Promise<T> {
    return this.request<T>(this.url(id, opts?.params), {
      method: "PUT",
      headers: this.headers(),
      body: JSON.stringify(data),
      signal: opts?.signal,
    });
  }

  async delete(id: number | string, opts?: RequestOptions): Promise<void> {
    const response = await fetch(this.url(id, opts?.params), {
      method: "DELETE",
      headers: this.headers(),
      signal: opts?.signal,
    });
    if (!response.ok) {
      throw new ApiError(response.status, response.statusText, "");
    }
  }
}

// --- Usage: define your types and create resources ---

interface User { id: number; name: string; email: string; }
interface Post { id: number; title: string; body: string; userId: number; }
interface Comment { id: number; postId: number; text: string; author: string; }

const api = new ApiClient({
  baseUrl: "https://api.example.com",
  headers: { Authorization: "Bearer token123" },
});

const users = api.resource<User>("/users");
const posts = api.resource<Post>("/posts");
const comments = api.resource<Comment>("/comments");

// Fully typed CRUD
const allUsers = await users.list();                          // User[]
const user = await users.get(1);                              // User
const newUser = await users.create({ name: "Dan", email: "dan@x.com" }); // User (Omit<User, "id">)
await users.update(1, { name: "Daniel" });                    // Partial<User>
await users.delete(1);

// With query params
const userPosts = await posts.list({ params: { userId: "1" } });
```

This gives you a single generic pattern for all your REST endpoints. Each `resource()` call returns a fully typed CRUD interface — `create()` accepts `Omit<T, "id">` and `update()` accepts `Partial<T>` so the types enforce valid payloads at compile time.'''
    ),
    (
        "multi_turn/hive-bot-requirements-change",
        r'''<conversation>
User: I want a simple Hive bot that follows a curation trail — when a designated leader account votes on a post, my bot votes on the same post with the same weight. Can you set that up?
Assistant: Here's a basic curation trail follower using dhive and the Hive streaming API:

```javascript
const { Client, PrivateKey } = require('@hiveio/dhive');

const client = new Client(['https://api.hive.blog']);
const LEADER = 'curatorleader';
const FOLLOWER = 'mybotaccount';
const POSTING_KEY = PrivateKey.fromString('5K...');

async function followTrail() {
  const stream = client.blockchain.getOperationsStream();

  stream.on('data', async (op) => {
    if (op.op[0] === 'vote') {
      const { voter, author, permlink, weight } = op.op[1];
      if (voter === LEADER) {
        console.log(`Leader voted on @${author}/${permlink} (${weight})`);
        await client.broadcast.vote({
          voter: FOLLOWER,
          author,
          permlink,
          weight,
        }, POSTING_KEY);
        console.log('Followed vote!');
      }
    }
  });
}

followTrail();
```
User: This works but I need a few changes. I want to support multiple leader accounts, each with a configurable weight multiplier. Also, I need a cooldown period so the bot doesn't vote on the same post twice (in case multiple leaders vote on it). And I realized I need to check my voting power before voting — only vote if above 80%.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user needs three additions: multiple leaders with weight multipliers,
dedup cooldown, and voting power check. I'll restructure with a config
object for leaders, a Set or Map to track recently voted posts, and the
manabar-based voting power calculation from the earlier Hive pair.
</think>

Here's the expanded bot with multi-leader support, dedup, and power checks:

```javascript
const { Client, PrivateKey } = require('@hiveio/dhive');

// --- Configuration ---

const CONFIG = {
  account: 'mybotaccount',
  postingKey: PrivateKey.fromString('5K...'),
  minVotingPower: 80, // only vote if above 80%
  cooldownMinutes: 60, // ignore re-votes on same post within this window

  leaders: {
    curatorleader:   { weightMultiplier: 1.0 },    // full weight
    anotherleader:   { weightMultiplier: 0.5 },    // half weight
    whaleaccount:    { weightMultiplier: 0.25 },   // quarter weight
  },
};

// --- State ---

const recentVotes = new Map(); // "author/permlink" -> timestamp

const client = new Client([
  'https://api.hive.blog',
  'https://api.deathwing.me',
  'https://anyx.io',
]);

// --- Voting power check (manabar-based) ---

async function getVotingPower(username) {
  const [account] = await client.database.getAccounts([username]);
  const { current_mana, last_update_time } = account.voting_manabar;

  const own = parseFloat(account.vesting_shares);
  const received = parseFloat(account.received_vesting_shares);
  const delegated = parseFloat(account.delegated_vesting_shares);
  const maxMana = (own + received - delegated) * 1e6;

  const now = Math.floor(Date.now() / 1000);
  const elapsed = now - last_update_time;
  const currentMana = Math.min(maxMana, Number(current_mana) + (maxMana * elapsed) / 432000);

  return (currentMana / maxMana) * 100;
}

// --- Cooldown check ---

function isOnCooldown(author, permlink) {
  const key = `${author}/${permlink}`;
  const lastVote = recentVotes.get(key);
  if (!lastVote) return false;
  return (Date.now() - lastVote) < CONFIG.cooldownMinutes * 60 * 1000;
}

function recordVote(author, permlink) {
  const key = `${author}/${permlink}`;
  recentVotes.set(key, Date.now());

  // Prune old entries every 100 votes
  if (recentVotes.size > 500) {
    const cutoff = Date.now() - CONFIG.cooldownMinutes * 60 * 1000;
    for (const [k, ts] of recentVotes) {
      if (ts < cutoff) recentVotes.delete(k);
    }
  }
}

// --- Main trail logic ---

async function followTrail() {
  console.log(`Trail bot started for @${CONFIG.account}`);
  console.log(`Following: ${Object.keys(CONFIG.leaders).join(', ')}`);

  const stream = client.blockchain.getOperationsStream();

  stream.on('data', async (op) => {
    if (op.op[0] !== 'vote') return;

    const { voter, author, permlink, weight } = op.op[1];
    const leaderConfig = CONFIG.leaders[voter];
    if (!leaderConfig) return;

    // Skip downvotes (negative weight)
    if (weight <= 0) return;

    console.log(`[${voter}] voted on @${author}/${permlink} (${weight / 100}%)`);

    // Check cooldown
    if (isOnCooldown(author, permlink)) {
      console.log(`  -> Skipped: already voted on this post recently`);
      return;
    }

    // Check voting power
    const power = await getVotingPower(CONFIG.account);
    if (power < CONFIG.minVotingPower) {
      console.log(`  -> Skipped: voting power ${power.toFixed(1)}% < ${CONFIG.minVotingPower}%`);
      return;
    }

    // Calculate adjusted weight
    const adjustedWeight = Math.round(weight * leaderConfig.weightMultiplier);
    if (adjustedWeight <= 0) return;

    try {
      await client.broadcast.vote({
        voter: CONFIG.account,
        author,
        permlink,
        weight: Math.min(adjustedWeight, 10000), // cap at 100%
      }, CONFIG.postingKey);

      recordVote(author, permlink);
      console.log(`  -> Voted ${adjustedWeight / 100}% (power: ${power.toFixed(1)}%)`);
    } catch (err) {
      console.error(`  -> Vote failed: ${err.message}`);
    }
  });

  stream.on('error', (err) => {
    console.error('Stream error:', err.message);
    console.log('Reconnecting in 5s...');
    setTimeout(followTrail, 5000);
  });
}

followTrail();
```

Changes from the original:
- **Multiple leaders** with per-leader weight multipliers. The first leader to vote triggers the bot; subsequent leaders voting on the same post are deduplicated.
- **Cooldown dedup** — tracks recent votes in a `Map` with automatic pruning. If `curatorleader` and `anotherleader` both vote on the same post, the bot only follows the first one.
- **Voting power gate** — uses the manabar calculation (HF26-correct) and skips voting when below 80%.
- **Error recovery** — reconnects the stream on errors with a 5-second delay.
- **Downvote filtering** — ignores negative-weight votes from leaders.'''
    ),

    # =====================================================================
    # 16-20: CLARIFICATION NEEDED
    # =====================================================================
    (
        "multi_turn/python-flatten-clarification",
        r'''<conversation>
User: How do I flatten a list in Python?
Assistant: Could you clarify what you mean by "flatten"? There are a few interpretations:

1. **Flatten one level** — `[[1, 2], [3, 4]]` → `[1, 2, 3, 4]`
2. **Deep flatten** — `[[1, [2, 3]], [4, [5, [6]]]]` → `[1, 2, 3, 4, 5, 6]`
3. **Flatten a dict** — `{"a": {"b": 1}}` → `{"a.b": 1}`

Which case are you dealing with?
User: Deep flatten — I have nested lists of unknown depth.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user needs recursive deep flattening of arbitrarily nested lists.
I'll provide a recursive generator approach which is clean and handles
any depth. I should also mention the itertools-based approach for one-level
and show that the recursive one handles all cases.
</think>

For deep flattening with unknown nesting depth, use a recursive generator:

```python
from collections.abc import Iterable

def deep_flatten(lst):
    """Recursively flatten nested iterables (except strings)."""
    for item in lst:
        if isinstance(item, Iterable) and not isinstance(item, (str, bytes)):
            yield from deep_flatten(item)
        else:
            yield item

# Usage
nested = [[1, [2, 3]], [4, [5, [6]]], 7]
print(list(deep_flatten(nested)))
# [1, 2, 3, 4, 5, 6, 7]
```

The `str`/`bytes` check is important — without it, strings get flattened into individual characters since strings are iterable in Python.

If you're worried about extremely deep nesting hitting Python's recursion limit (~1000 by default), here's an iterative version using an explicit stack:

```python
def deep_flatten_iterative(lst):
    stack = list(reversed(lst))
    while stack:
        item = stack.pop()
        if isinstance(item, Iterable) and not isinstance(item, (str, bytes)):
            stack.extend(reversed(list(item)))
        else:
            yield item
```

The iterative version handles any depth without risk of `RecursionError`.'''
    ),
    (
        "multi_turn/rust-string-conversion-clarification",
        r'''<conversation>
User: What's the best way to convert between string types in Rust? I keep getting confused.
Assistant: It depends on which conversion you need. Can you tell me which specific case is tripping you up?

Common scenarios:
1. `&str` → `String` (borrowed to owned)
2. `String` → `&str` (owned to borrowed)
3. `&[u8]` → `String` (bytes to string)
4. `String` → `Vec<u8>` (string to bytes)
5. Number → `String` or `String` → number
6. `OsString` / `CString` / `PathBuf` conversions

Which ones do you hit most often?
User: Mostly 1, 2, and 3. I'm writing a parser that reads bytes from a file and needs to work with both owned and borrowed strings.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user needs practical guidance on &str ↔ String and bytes → String
conversions for a file parser context. I'll give clear, concise examples
for each conversion with notes on when to use which.
</think>

Here's a concise reference for the three conversions you need:

**1. `&str` → `String` (borrowed to owned)**
```rust
let s: &str = "hello";

// These are all equivalent — pick one style and be consistent
let owned: String = s.to_string();
let owned: String = s.to_owned();
let owned: String = String::from(s);
let owned: String = s.into();
```
Use `to_owned()` in a parser — it's the most semantically clear ("I need to own this data").

**2. `String` → `&str` (owned to borrowed)**
```rust
let owned = String::from("hello");

let borrowed: &str = &owned;      // auto-deref
let borrowed: &str = owned.as_str(); // explicit

// Works in function calls automatically:
fn process(s: &str) { /* ... */ }
process(&owned); // String auto-derefs to &str
```
This is free (no allocation) — it's just borrowing the String's internal buffer.

**3. `&[u8]` → `String` (bytes to string)**
```rust
let bytes: &[u8] = b"hello";

// If you know the bytes are valid UTF-8:
let s = std::str::from_utf8(bytes).expect("invalid UTF-8"); // &[u8] → &str
let s = String::from_utf8(bytes.to_vec()).expect("invalid UTF-8"); // Vec<u8> → String

// If you're not sure and want to handle errors:
match std::str::from_utf8(bytes) {
    Ok(valid) => println!("Valid: {valid}"),
    Err(e) => println!("Invalid UTF-8 at byte {}", e.valid_up_to()),
}

// If you want lossy conversion (replaces invalid bytes with '�'):
let s = String::from_utf8_lossy(bytes); // Returns Cow<str>
```

For your parser reading bytes from a file, the typical pattern is:

```rust
use std::fs;

// If the file is definitely UTF-8:
let content: String = fs::read_to_string("file.txt")?;
let slice: &str = &content; // borrow for parsing

// If the file might not be UTF-8:
let bytes: Vec<u8> = fs::read("file.bin")?;
let text = String::from_utf8(bytes)?; // fails if invalid
// or
let text = String::from_utf8_lossy(&fs::read("file.bin")?); // never fails
```

Rule of thumb for parsers: read the file once into a `String` with `read_to_string`, then pass `&str` slices around during parsing. Only create new `String`s when you need to store a parsed value that outlives the input.'''
    ),
    (
        "multi_turn/go-error-handling-clarification",
        r'''<conversation>
User: How should I handle errors in Go? I'm coming from Python where I just use try/except.
Assistant: Go doesn't have exceptions — it uses explicit error returns. But there are several patterns depending on your needs. Can you tell me more about your situation?

1. Are you writing a library or an application?
2. Do you need to wrap errors with context (like a stack trace)?
3. Are you dealing with recoverable vs. fatal errors?

The approach differs quite a bit between these cases.
User: Application-level code — a web API server. I want to add context to errors so when they bubble up I can tell where they originated. In Python I'd just read the traceback.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user wants error handling patterns for a Go web API, specifically with
context wrapping. I'll cover fmt.Errorf with %w, errors.Is/As for checking,
and how to structure error handling in an HTTP handler context. I'll also
show custom error types for API-specific errors.
</think>

Go's equivalent of Python tracebacks is **error wrapping** — you add context at each level as the error bubbles up. Here's the full pattern for a web API:

**1. Wrap errors with `fmt.Errorf` and `%w`:**
```go
func getUser(id int) (*User, error) {
    row := db.QueryRow("SELECT * FROM users WHERE id = $1", id)
    var u User
    if err := row.Scan(&u.ID, &u.Name, &u.Email); err != nil {
        return nil, fmt.Errorf("getUser(%d): %w", id, err)
    }
    return &u, nil
}

func handleGetUser(w http.ResponseWriter, r *http.Request) {
    id := parseID(r)
    user, err := getUser(id)
    if err != nil {
        // Error message: "getUser(42): sql: no rows in result set"
        // Full context chain, like a traceback
        log.Printf("handler error: %v", err)
        http.Error(w, "user not found", http.StatusNotFound)
        return
    }
    json.NewEncoder(w).Encode(user)
}
```

**2. Check error types with `errors.Is` and `errors.As`:**
```go
import "errors"

// Check for specific errors (works through wrapped layers)
if errors.Is(err, sql.ErrNoRows) {
    http.Error(w, "not found", 404)
} else if err != nil {
    http.Error(w, "internal error", 500)
}
```

**3. Define API-specific error types:**
```go
type APIError struct {
    Status  int    // HTTP status code
    Message string // user-facing message
    Err     error  // underlying error (for logging)
}

func (e *APIError) Error() string {
    return fmt.Sprintf("%s: %v", e.Message, e.Err)
}

func (e *APIError) Unwrap() error { return e.Err }

// Helper constructors
func NotFound(msg string, err error) *APIError {
    return &APIError{Status: 404, Message: msg, Err: err}
}

func Internal(msg string, err error) *APIError {
    return &APIError{Status: 500, Message: msg, Err: err}
}

// Use in service layer
func getUser(id int) (*User, error) {
    user, err := db.FindUser(id)
    if errors.Is(err, sql.ErrNoRows) {
        return nil, NotFound("user not found", fmt.Errorf("getUser(%d): %w", id, err))
    }
    if err != nil {
        return nil, Internal("database error", fmt.Errorf("getUser(%d): %w", id, err))
    }
    return user, nil
}
```

**4. Centralized error handling middleware:**
```go
type handlerFunc func(w http.ResponseWriter, r *http.Request) error

func errorHandler(fn handlerFunc) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        err := fn(w, r)
        if err == nil {
            return
        }

        // Check if it's our APIError
        var apiErr *APIError
        if errors.As(err, &apiErr) {
            log.Printf("[%d] %v", apiErr.Status, apiErr.Err) // log full context
            http.Error(w, apiErr.Message, apiErr.Status)      // send safe message
        } else {
            log.Printf("[500] unexpected: %v", err)
            http.Error(w, "internal server error", 500)
        }
    }
}

// Handlers return errors instead of writing responses on failure
func handleGetUser(w http.ResponseWriter, r *http.Request) error {
    user, err := getUser(parseID(r))
    if err != nil {
        return err // let middleware handle it
    }
    return json.NewEncoder(w).Encode(user)
}

// Register
http.HandleFunc("/users/", errorHandler(handleGetUser))
```

This gives you Python-like ergonomics: handlers just return errors, the middleware logs the full chain (like a traceback) and sends an appropriate HTTP response. The `%w` wrapping at each layer builds the context chain, and `errors.Is`/`errors.As` let you inspect through it.'''
    ),
    (
        "multi_turn/typescript-state-management-clarification",
        r'''<conversation>
User: Should I use Redux or Context API for state management in my React app?
Assistant: It depends on the complexity of your state. Can you describe:

1. How many components need to share state?
2. Is the state mostly UI state (modals, forms) or server/data state (API responses)?
3. How often does the state update?
4. Are you already using any data fetching library like React Query or SWR?
User: It's mostly server state — fetching data from REST APIs. About 20 components spread across 5 pages need the same data. We're not using React Query yet. Updates are moderate — maybe every few seconds for some real-time data.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user's main state is server/API state with moderate real-time updates.
Redux would be overkill for this — React Query (TanStack Query) is the right
tool. It handles caching, refetching, deduplication, and real-time polling
out of the box. I should explain why and show a practical example that matches
their use case (REST API data shared across many components).
</think>

For server state from REST APIs, **skip both Redux and Context API** and use **TanStack Query** (React Query). It's purpose-built for exactly your use case.

Here's why: Redux and Context manage client-side state. When you use them for server data, you end up writing boilerplate for loading states, caching, refetching, error handling, and cache invalidation. TanStack Query handles all of that automatically.

```typescript
// Setup — wrap your app once
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <YourRoutes />
    </QueryClientProvider>
  );
}

// Define typed fetch functions
async function fetchUsers(): Promise<User[]> {
  const res = await fetch('/api/users');
  if (!res.ok) throw new Error('Failed to fetch users');
  return res.json();
}

async function fetchUser(id: number): Promise<User> {
  const res = await fetch(`/api/users/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch user ${id}`);
  return res.json();
}

// Use in ANY component — data is cached and shared automatically
function UserList() {
  const { data: users, isLoading, error } = useQuery({
    queryKey: ['users'],
    queryFn: fetchUsers,
    staleTime: 30_000, // cache for 30s before refetching
  });

  if (isLoading) return <Spinner />;
  if (error) return <ErrorMessage error={error} />;
  return <ul>{users.map(u => <li key={u.id}>{u.name}</li>)}</ul>;
}

// Same data used in another component — no extra fetch, shares the cache
function UserCount() {
  const { data: users } = useQuery({
    queryKey: ['users'],
    queryFn: fetchUsers,
  });
  return <span>{users?.length ?? 0} users</span>;
}

// Real-time polling for data that updates every few seconds
function LiveDashboard() {
  const { data: metrics } = useQuery({
    queryKey: ['metrics'],
    queryFn: fetchMetrics,
    refetchInterval: 5_000, // poll every 5 seconds
  });
  return <Dashboard data={metrics} />;
}

// Mutations with automatic cache invalidation
function CreateUserForm() {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (newUser: CreateUserDTO) =>
      fetch('/api/users', { method: 'POST', body: JSON.stringify(newUser) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] }); // refetches user list
    },
  });

  return <form onSubmit={() => mutation.mutate({ name: 'Dan' })} />;
}
```

What you get for free:
- **20 components** sharing the same data? They all use the same `queryKey` and TanStack deduplicates the requests. One fetch, shared cache.
- **Real-time data** — `refetchInterval: 5000` polls automatically. It also refetches when the tab regains focus.
- **Loading/error states** built in — no more manual `isLoading` state management.
- **Cache invalidation** — after a mutation, `invalidateQueries` triggers a refetch so the UI stays fresh.

Reserve Redux or Context for **client-only state** like theme, sidebar open/closed, or form wizard steps — things that don't come from the server.

Install with: `npm install @tanstack/react-query`'''
    ),
    (
        "multi_turn/hive-posting-clarification",
        r'''<conversation>
User: How do I post content to Hive?
Assistant: I can help with that. A few clarifying questions first:

1. Are you posting from a **web app**, a **Node.js bot**, or a **CLI script**?
2. Do you need to support **Markdown formatting** in the post body?
3. Do you need to set **beneficiaries** or other advanced options?
4. Are you using **Hive Keychain**, **HiveSigner**, or a **private key directly**?
User: Node.js bot using dhive with the posting key directly. I need Markdown support and want to set beneficiaries — 5% goes to a curation project.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user wants to create a Hive post from Node.js using dhive with the posting
key, Markdown body, and beneficiary settings. Hive posts use the comment
operation (posts are top-level comments). Beneficiaries are set via
comment_options operation. I need to include both operations in a single
broadcast. The JSON metadata needs to include tags and app name.
</think>

Here's a complete Hive post function with Markdown and beneficiaries:

```javascript
const { Client, PrivateKey } = require('@hiveio/dhive');

const client = new Client([
  'https://api.hive.blog',
  'https://api.deathwing.me',
]);

async function createPost({
  author,
  postingKey,
  title,
  body,          // Markdown string
  tags,          // e.g., ['hive', 'dev', 'tutorial']
  beneficiaries, // e.g., [{ account: 'curationproject', weight: 500 }]
}) {
  const key = PrivateKey.fromString(postingKey);

  // Generate permlink from title
  const permlink = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    + '-' + Date.now().toString(36);

  // JSON metadata
  const jsonMetadata = JSON.stringify({
    tags,
    app: 'mybot/1.0',
    format: 'markdown',
    image: extractImages(body),
  });

  // Operation 1: the post itself (a top-level "comment" with parent_author = "")
  const commentOp = ['comment', {
    parent_author: '',              // empty = top-level post
    parent_permlink: tags[0],       // primary tag = category
    author,
    permlink,
    title,
    body,                           // Markdown is stored as-is; frontends render it
    json_metadata: jsonMetadata,
  }];

  // Operation 2: comment_options for beneficiaries and reward settings
  const optionsOp = ['comment_options', {
    author,
    permlink,
    max_accepted_payout: '1000000.000 HBD',
    percent_hbd: 10000,             // 100% — let the author choose power up vs liquid later
    allow_votes: true,
    allow_curation_rewards: true,
    extensions: [
      [0, {
        beneficiaries: beneficiaries.sort((a, b) => a.account.localeCompare(b.account)),
      }],
    ],
  }];

  // Broadcast both operations atomically
  const result = await client.broadcast.sendOperations([commentOp, optionsOp], key);

  return {
    txId: result.id,
    block: result.block_num,
    url: `https://hive.blog/${tags[0]}/@${author}/${permlink}`,
  };
}

// Extract image URLs from Markdown for metadata
function extractImages(markdown) {
  const regex = /!\[.*?\]\((https?:\/\/[^\s)]+)\)/g;
  const images = [];
  let match;
  while ((match = regex.exec(markdown)) !== null) {
    images.push(match[1]);
  }
  return images;
}

// --- Usage ---

createPost({
  author: 'mybotaccount',
  postingKey: '5K...',
  title: 'My First Automated Post',
  body: `# Hello Hive!

This post was created by a **Node.js bot**.

## Features
- Markdown rendering
- Beneficiary support
- Automated posting

![example](https://example.com/image.png)
`,
  tags: ['hive', 'dev', 'automation'],
  beneficiaries: [
    { account: 'curationproject', weight: 500 },  // 5% (weight is in basis points: 500 = 5%)
  ],
}).then(result => {
  console.log('Posted!', result.url);
}).catch(err => {
  console.error('Failed:', err.message);
});
```

Key details:
- **Posts are `comment` operations** with `parent_author: ""` — that's how Hive distinguishes posts from replies.
- **Beneficiaries use basis points** — `weight: 500` = 5%. They must be sorted alphabetically by account name, or the transaction will be rejected.
- **`comment_options` must be broadcast atomically** with the `comment` — you can't add beneficiaries after the post exists.
- **Markdown is stored raw** — Hive frontends (PeakD, Ecency, etc.) render it. The `format: 'markdown'` in metadata tells them how to render it.
- **Permlink** must be unique per author. Appending a timestamp in base36 prevents collisions.'''
    ),

    # =====================================================================
    # 21-25: SELF-CORRECTION
    # =====================================================================
    (
        "multi_turn/python-singleton-correction",
        r'''<conversation>
User: How do I implement the singleton pattern in Python?
Assistant: Here's a simple singleton using a class variable:

```python
class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.connection = create_connection()
```

Every call to `Database()` returns the same instance.
User: Wait, there's a problem. I tried this and `create_connection()` is called every time I do `Database()`, not just the first time. Isn't `__init__` called on every instantiation?
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user is right. `__new__` returns the same instance, but `__init__` is
still called every time `Database()` is invoked. So `create_connection()`
runs on every call, potentially resetting the connection. This is a real
bug in my previous answer. I need to acknowledge the mistake and fix it
by either guarding `__init__` with a flag, or moving initialization into
`__new__`, or using a different singleton pattern entirely.
</think>

You're absolutely right — that's a bug in my previous answer. In Python, `__init__` is called after `__new__` on every instantiation, even when `__new__` returns an existing instance. So `create_connection()` runs every time, potentially resetting state.

Here's the corrected version with a guard flag:

```python
class Database:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if Database._initialized:
            return
        Database._initialized = True
        self.connection = create_connection()
```

Or, a cleaner approach — skip `__init__` entirely and initialize in `__new__`:

```python
class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            instance = super().__new__(cls)
            instance.connection = create_connection()
            cls._instance = instance
        return cls._instance
```

Or the most Pythonic approach — use a module-level instance. Since Python modules are imported once, this is naturally a singleton:

```python
# db.py
class Database:
    def __init__(self):
        self.connection = create_connection()

# Single instance — created on first import, reused thereafter
db = Database()

# Other files:
from db import db  # always the same instance
```

The module-level approach is generally preferred in Python because it's simple, thread-safe at import time, and doesn't fight the language's object model.'''
    ),
    (
        "multi_turn/rust-clone-correction",
        r'''<conversation>
User: What's the most efficient way to pass a large struct between functions in Rust?
Assistant: Use references to avoid copying:

```rust
struct LargeData {
    buffer: Vec<u8>,
    metadata: HashMap<String, String>,
}

fn process(data: &LargeData) {
    // read-only access, no copy
    println!("Size: {}", data.buffer.len());
}

fn modify(data: &mut LargeData) {
    // mutable access, still no copy
    data.buffer.push(0);
}

fn main() {
    let mut data = LargeData { /* ... */ };
    process(&data);
    modify(&mut data);
}
```

Always prefer `&T` or `&mut T` over cloning large structs.
User: But what if I need to send it to another thread? I can't send a reference to a thread because the borrow checker won't let me — the data might be dropped before the thread finishes.
Assistant: Good point. For threads, you'd need to transfer ownership using `move`:

```rust
use std::thread;

fn main() {
    let data = LargeData { /* ... */ };
    let handle = thread::spawn(move || {
        process_in_thread(data);
    });
    handle.join().unwrap();
}
```

This moves `data` into the thread, so no copy happens.
User: But what if I need to use `data` in the main thread AND the spawned thread? Moving it means I can't use it in main anymore. You said to avoid cloning — is there no other option?
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user caught a gap in my advice. I said "always prefer references over
cloning" and "use move for threads," but those two pieces of advice conflict
when you need the data in multiple threads. I should correct myself: cloning
isn't always wrong, but for large data, `Arc` (atomic reference counting) is
the right tool. `Arc` lets multiple threads share the same data without
cloning the contents. If they need mutation, `Arc<Mutex<T>>` or
`Arc<RwLock<T>>`. I should acknowledge that my earlier blanket advice was
too simplistic.
</think>

I should correct my earlier advice — "always avoid cloning" was too absolute. For sharing across threads, **`Arc` (Atomic Reference Counting)** is the right tool:

```rust
use std::sync::Arc;
use std::thread;

fn main() {
    let data = Arc::new(LargeData {
        buffer: vec![0u8; 10_000_000],
        metadata: HashMap::new(),
    });

    // Clone the Arc, not the data — this is cheap (just increments a counter)
    let data_for_thread = Arc::clone(&data);

    let handle = thread::spawn(move || {
        // Read-only access to the same underlying data
        println!("Thread sees {} bytes", data_for_thread.buffer.len());
    });

    // Main thread still has access
    println!("Main sees {} bytes", data.buffer.len());
    handle.join().unwrap();
}
```

`Arc::clone()` is O(1) — it just increments an atomic reference counter. The 10 million bytes in the buffer are not copied. Both threads point to the same heap allocation.

If you also need **mutable access** from multiple threads, wrap in `RwLock` or `Mutex`:

```rust
use std::sync::{Arc, RwLock};

let data = Arc::new(RwLock::new(LargeData { /* ... */ }));
let data_for_thread = Arc::clone(&data);

thread::spawn(move || {
    let mut d = data_for_thread.write().unwrap();
    d.buffer.push(42); // exclusive write access
});

{
    let d = data.read().unwrap();
    println!("Size: {}", d.buffer.len()); // shared read access
}
```

To revise my earlier advice more accurately:
- **Single thread** — use `&T` / `&mut T` references. No overhead.
- **Multiple threads, read-only** — use `Arc<T>`. Near-zero overhead (one atomic increment per clone).
- **Multiple threads, read-write** — use `Arc<RwLock<T>>` (many readers OR one writer) or `Arc<Mutex<T>>` (one accessor at a time).
- **Cloning** — only clone when the data is small or you genuinely need independent copies.'''
    ),
    (
        "multi_turn/go-json-unmarshal-correction",
        r'''<conversation>
User: How do I parse a JSON API response where some fields might be null or missing in Go?
Assistant: Use pointer types for nullable fields:

```go
type APIResponse struct {
    ID     int     `json:"id"`
    Name   string  `json:"name"`
    Email  *string `json:"email"`   // null → nil
    Age    *int    `json:"age"`     // null → nil
}

func parse(data []byte) (*APIResponse, error) {
    var resp APIResponse
    err := json.Unmarshal(data, &resp)
    if err != nil {
        return nil, err
    }
    return &resp, nil
}

// Check nullable fields
if resp.Email != nil {
    fmt.Println("Email:", *resp.Email)
}
```
User: I tried this but there's a subtle issue. When the API returns `{"id": 1, "name": "Dan"}` (email field completely absent from the JSON), and `{"id": 1, "name": "Dan", "email": null}` (email explicitly null), both result in `Email` being `nil`. But I need to distinguish between "field missing" and "field explicitly null" because my PATCH endpoint needs to know whether to leave the field unchanged or set it to NULL in the database.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user is right — pointer fields can't distinguish between absent and null.
Both result in nil. This is a real problem for PATCH semantics. I need to
acknowledge this limitation. Solutions: use json.RawMessage and check if the
key exists, use a custom "Optional" wrapper type, or use a map[string]any
to check key presence. The cleanest approach is a wrapper type with a
"present" flag.
</think>

You're right — that's a real limitation of the pointer approach that I didn't address. Both absent and `null` produce `nil`, and for PATCH semantics you absolutely need to tell them apart.

Here's a generic `Optional` type that tracks presence:

```go
package main

import "encoding/json"

// Optional distinguishes between absent, null, and present.
type Optional[T any] struct {
    Value   T
    Present bool // true if the key existed in the JSON (even if null)
    Null    bool // true if the value was explicitly null
}

func (o *Optional[T]) UnmarshalJSON(data []byte) error {
    o.Present = true
    if string(data) == "null" {
        o.Null = true
        return nil
    }
    return json.Unmarshal(data, &o.Value)
}

// For serialization: omit if not present, write null if null
func (o Optional[T]) MarshalJSON() ([]byte, error) {
    if o.Null {
        return []byte("null"), nil
    }
    return json.Marshal(o.Value)
}

// --- Usage ---

type PatchUser struct {
    Name  Optional[string] `json:"name"`
    Email Optional[string] `json:"email"`
    Age   Optional[int]    `json:"age"`
}

func applyPatch(patch PatchUser, userID int) error {
    // Only update fields that were present in the request
    if patch.Name.Present {
        if patch.Name.Null {
            // SET name = NULL
        } else {
            // SET name = patch.Name.Value
        }
    }
    // Name not present → don't touch it

    if patch.Email.Present {
        if patch.Email.Null {
            // SET email = NULL (user explicitly cleared their email)
        } else {
            // SET email = patch.Email.Value
        }
    }
    return nil
}
```

Three states for each field:
| JSON | `Present` | `Null` | Meaning |
|---|---|---|---|
| field absent | `false` | `false` | Don't modify |
| `"email": null` | `true` | `true` | Set to NULL |
| `"email": "a@b.com"` | `true` | `false` | Set to value |

This works because `json.Unmarshal` only calls `UnmarshalJSON` on fields that are present in the JSON input. If the key is completely absent, the `Optional` keeps its zero value (`Present: false`).

This is the correct way to implement RFC 7386 (JSON Merge Patch) semantics in Go. My original pointer-based answer was fine for simple reads but doesn't work for PATCH operations.'''
    ),
    (
        "multi_turn/typescript-map-filter-correction",
        r'''<conversation>
User: How do I filter and transform an array in TypeScript in a type-safe way?
Assistant: Chain `.filter()` and `.map()`:

```typescript
interface User {
  id: number;
  name: string;
  age: number | null;
}

const users: User[] = [
  { id: 1, name: "Alice", age: 30 },
  { id: 2, name: "Bob", age: null },
  { id: 3, name: "Carol", age: 25 },
];

// Get names of users with known ages
const names = users
  .filter(u => u.age !== null)
  .map(u => ({ name: u.name, age: u.age }));
```

Clean and type-safe.
User: But `names` has type `{ name: string; age: number | null }[]` — the `age` is still typed as `number | null` even after the filter. TypeScript doesn't narrow the type through filter. Your answer said type-safe but it's not actually narrowing.
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user is correct. TypeScript doesn't narrow types through .filter()
unless you use a type predicate. My claim that it was "type-safe" was wrong.
I need to use a type guard function as the filter predicate so TypeScript
narrows the type in the subsequent .map().
</think>

You're correct — I was wrong to call that type-safe. TypeScript's `.filter()` doesn't narrow the array element type unless you use a **type predicate** (also called a type guard). Here's the fix:

```typescript
interface User {
  id: number;
  name: string;
  age: number | null;
}

interface UserWithAge extends User {
  age: number; // override to non-null
}

// Type predicate: tells TypeScript that if this returns true, the user has a non-null age
function hasAge(user: User): user is UserWithAge {
  return user.age !== null;
}

const users: User[] = [
  { id: 1, name: "Alice", age: 30 },
  { id: 2, name: "Bob", age: null },
  { id: 3, name: "Carol", age: 25 },
];

// Now TypeScript narrows correctly
const result = users
  .filter(hasAge)
  .map(u => ({ name: u.name, age: u.age }));
// result: { name: string; age: number }[]  ← age is number, not number | null
```

The key is `user is UserWithAge` — this is a type predicate that tells TypeScript to narrow the type when the filter returns `true`.

You can also inline it if you prefer:

```typescript
const result = users
  .filter((u): u is UserWithAge => u.age !== null)
  .map(u => ({ name: u.name, age: u.age }));
// result: { name: string; age: number }[]
```

The `(u): u is UserWithAge =>` syntax is the inline type predicate form. Without the `u is UserWithAge` return type annotation, TypeScript treats it as a regular boolean filter and doesn't narrow.

This is a common TypeScript pitfall — `.filter()` with a plain boolean callback never narrows. You always need the `is` predicate for type narrowing to propagate through the chain.'''
    ),
    (
        "multi_turn/hive-resource-credits-correction",
        r'''<conversation>
User: I'm building a Hive dapp and want to check if a user has enough Resource Credits to make a transaction before broadcasting. How do I do that?
Assistant: You can check RC using the `rc_api`:

```javascript
const { Client } = require('@hiveio/dhive');
const client = new Client(['https://api.hive.blog']);

async function hasEnoughRC(username) {
  const rc = await client.call('rc_api', 'find_rc_accounts', { accounts: [username] });
  const rcAccount = rc.rc_accounts[0];
  const currentRC = parseInt(rcAccount.rc_manabar.current_mana);
  return currentRC > 1000000000; // 1 billion RC should be enough for most ops
}
```

If this returns true, the user has enough RC for a standard transaction.
User: That hardcoded threshold of 1 billion RC is wrong. A comment operation costs way more RC than a vote. And the RC cost changes based on blockchain state. Is there a way to get the actual cost of a specific operation?
</conversation>

Respond to the user's latest message.''',
        r'''<think>
The user is right — the hardcoded threshold was a bad approach. Hive has an
`rc_api.get_resource_cost` call that returns the current cost of resource
pools, and you can estimate operation costs. Actually, the correct approach
is to use `rc_api.find_rc_accounts` for current mana AND calculate the
actual cost of the specific operation. There's also the `rc_api.get_resource_params`
and `rc_api.get_resource_pool` calls. Let me correct this properly.

The right approach is to calculate RC mana regeneration (like voting power)
and compare against the estimated cost for the specific operation type.
</think>

You're right — the hardcoded threshold was a bad approach. Different operations cost vastly different amounts of RC, and costs change dynamically based on blockchain resource pool utilization. Here's the corrected version:

```javascript
const { Client } = require('@hiveio/dhive');
const client = new Client(['https://api.hive.blog']);

async function getCurrentRC(username) {
  const result = await client.call('rc_api', 'find_rc_accounts', {
    accounts: [username],
  });
  const rcAccount = result.rc_accounts[0];

  // Calculate current mana with regeneration (same pattern as voting power)
  const maxMana = parseInt(rcAccount.max_rc);
  const currentMana = parseInt(rcAccount.rc_manabar.current_mana);
  const lastUpdate = rcAccount.rc_manabar.last_update_time;

  const now = Math.floor(Date.now() / 1000);
  const elapsed = now - lastUpdate;

  // RC regenerates fully in 5 days (432000 seconds)
  const regenerated = (maxMana * elapsed) / 432000;
  const actualMana = Math.min(maxMana, currentMana + regenerated);

  return { current: actualMana, max: maxMana, pct: (actualMana / maxMana) * 100 };
}

async function estimateOperationCost(operations) {
  // Use the rc_api to estimate cost for specific operations
  const result = await client.call('rc_api', 'get_resource_cost', {
    operations: operations,
  });
  return result;
}

async function canAffordOperation(username, operations) {
  const [rc, cost] = await Promise.all([
    getCurrentRC(username),
    estimateOperationCost(operations),
  ]);

  // get_resource_cost returns the total RC cost
  const totalCost = parseInt(cost.rc_cost);

  return {
    canAfford: rc.current >= totalCost,
    currentRC: rc.current,
    cost: totalCost,
    rcPct: rc.pct,
    remaining: rc.current - totalCost,
  };
}

// --- Usage ---

// Check if user can afford a comment
const commentOp = ['comment', {
  parent_author: 'someblog',
  parent_permlink: 'some-post',
  author: 'myuser',
  permlink: 're-some-post-reply',
  title: '',
  body: 'Great post!',
  json_metadata: '{}',
}];

const result = await canAffordOperation('myuser', [commentOp]);
console.log(result);
// { canAfford: true, currentRC: 5234567890, cost: 1200000, rcPct: 87.3, remaining: 5233367890 }

if (!result.canAfford) {
  console.log(`Not enough RC. Need ${result.cost}, have ${result.currentRC}`);
  console.log(`RC at ${result.rcPct.toFixed(1)}% — wait for regeneration`);
}
```

Key corrections from my previous answer:
- **No hardcoded threshold** — the actual operation is passed to `get_resource_cost` to get the real cost.
- **RC regeneration** is calculated the same way as voting power (5-day full regeneration cycle), so the "current" value reflects what the user actually has right now, not a stale snapshot.
- **Different operations have different costs** — a `comment` uses much more RC than a `vote` because it consumes more blockchain storage. This approach handles that correctly.
- The `canAffordOperation` function gives the caller everything needed to show a useful message if the operation can't be performed.'''
    ),
]
