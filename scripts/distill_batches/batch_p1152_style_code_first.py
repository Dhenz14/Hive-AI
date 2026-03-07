"""
Response variety training pairs - Code first, explain after
Opens immediately with a code block, then explains below.
"""

pairs = [
    {
        "instruction": r'''Write a Python decorator that retries a function on failure with exponential backoff.''',
        "output": r'''```python
import time
import random
from functools import wraps

def retry(max_attempts=3, base_delay=1.0, backoff_factor=2.0, exceptions=(Exception,)):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        break
                    # Add jitter to prevent thundering herd
                    jittered = delay * (0.5 + random.random())
                    print(f"Attempt {attempt} failed: {e}. Retrying in {jittered:.1f}s...")
                    time.sleep(jittered)
                    delay *= backoff_factor
            raise last_exception
        return wrapper
    return decorator

# Usage
@retry(max_attempts=4, base_delay=0.5, exceptions=(ConnectionError, TimeoutError))
def fetch_data(url):
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()
```

What this does: the decorator wraps any function so that if it raises one of the specified exceptions, it waits and tries again. The delay doubles each time (exponential backoff) with random jitter added so that if many clients fail at once, they don't all retry at the exact same moment.

The `exceptions` parameter is important -- you don't want to retry on every error. A `ValueError` from bad input will fail every time, but a `ConnectionError` might succeed on the next attempt.

For async code, swap `time.sleep` for `await asyncio.sleep` and make the wrapper an `async def`.'''
    },
    {
        "instruction": r'''How do I implement a debounce function in JavaScript?''',
        "output": r'''```javascript
function debounce(func, delay, { leading = false } = {}) {
    let timeoutId = null;

    function debounced(...args) {
        const callNow = leading && timeoutId === null;

        clearTimeout(timeoutId);

        timeoutId = setTimeout(() => {
            timeoutId = null;
            if (!leading) {
                func.apply(this, args);
            }
        }, delay);

        if (callNow) {
            func.apply(this, args);
        }
    }

    debounced.cancel = () => {
        clearTimeout(timeoutId);
        timeoutId = null;
    };

    return debounced;
}

// Usage: search input that waits 300ms after user stops typing
const searchInput = document.getElementById('search');
const debouncedSearch = debounce((query) => {
    fetch(`/api/search?q=${encodeURIComponent(query)}`)
        .then(res => res.json())
        .then(results => renderResults(results));
}, 300);

searchInput.addEventListener('input', (e) => debouncedSearch(e.target.value));

// With leading edge -- fires immediately, then ignores for `delay`ms
const debouncedSave = debounce(saveDocument, 1000, { leading: true });
```

What this does: `debounce` delays calling the function until a specified time has passed since the last invocation. Every time the debounced function is called, it resets the timer.

The `leading` option flips the behavior -- it fires immediately on the first call, then ignores subsequent calls until the delay passes. This is useful for things like a save button where you want instant feedback but don't want double-clicks.

The `.cancel()` method lets you clean up if the component unmounts or the user navigates away before the timer fires.'''
    },
    {
        "instruction": r'''Write a Python context manager that temporarily changes the working directory.''',
        "output": r'''```python
import os
from contextlib import contextmanager

@contextmanager
def chdir(path):
    """Temporarily change working directory, restoring it on exit."""
    original = os.getcwd()
    try:
        os.chdir(path)
        yield os.path.abspath(path)
    finally:
        os.chdir(original)

# Usage
print(os.getcwd())  # /home/user/project

with chdir('/tmp') as new_dir:
    print(os.getcwd())     # /tmp
    print(new_dir)         # /tmp
    # Do file operations in /tmp
    with open('scratch.txt', 'w') as f:
        f.write('temporary work')

print(os.getcwd())  # /home/user/project (restored)

# Works great for running subprocesses in specific directories
import subprocess

with chdir('frontend'):
    subprocess.run(['npm', 'run', 'build'], check=True)

# Also safe if an exception is raised inside the block
with chdir('/some/path'):
    raise ValueError("oops")
# cwd is still restored thanks to the finally block
```

What this does: `chdir` saves the current working directory, changes to the new one, and guarantees the original is restored when the `with` block exits -- even if an exception occurs.

The `yield` gives back the absolute path of the new directory, which is handy when you pass a relative path and want to know where you actually ended up.

Note: Python 3.11+ added `contextlib.chdir` to the standard library, which does exactly this. If you're on 3.11+, just use `from contextlib import chdir` directly.'''
    },
    {
        "instruction": r'''Implement a simple rate limiter in Python using the token bucket algorithm.''',
        "output": r'''```python
import time
import threading

class TokenBucket:
    def __init__(self, rate, capacity):
        self.rate = rate          # tokens added per second
        self.capacity = capacity  # max tokens
        self.tokens = capacity    # start full
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def acquire(self, tokens=1):
        """Try to consume tokens. Returns True if allowed, False if rejected."""
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def wait(self, tokens=1):
        """Block until tokens are available."""
        while True:
            with self.lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
                # Calculate wait time
                deficit = tokens - self.tokens
                wait_time = deficit / self.rate
            time.sleep(wait_time)

# Usage: allow 10 requests per second with burst of 20
limiter = TokenBucket(rate=10, capacity=20)

def handle_request(request):
    if not limiter.acquire():
        return {"error": "Rate limit exceeded"}, 429
    return process(request), 200

# Or block until allowed (useful for outgoing API calls)
def call_external_api(data):
    limiter.wait()  # blocks until a token is available
    return requests.post("https://api.example.com/data", json=data)
```

What this does: the token bucket starts full (allowing a burst) and refills at a steady rate. Each request consumes a token. If the bucket is empty, the request is either rejected (`acquire`) or the caller waits (`wait`).

The `rate` parameter controls sustained throughput (tokens per second), while `capacity` controls burst size. For example, `rate=10, capacity=20` means 10 requests/second sustained, but allows a burst of 20 if the client has been idle.

The implementation is thread-safe via a lock. For async code, you'd replace `threading.Lock` with `asyncio.Lock` and `time.sleep` with `asyncio.sleep`.'''
    },
    {
        "instruction": r'''Write a TypeScript function that deep merges two objects.''',
        "output": r'''```typescript
type DeepPartial<T> = {
    [K in keyof T]?: T[K] extends object ? DeepPartial<T[K]> : T[K];
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object'
        && value !== null
        && !Array.isArray(value)
        && !(value instanceof Date)
        && !(value instanceof RegExp);
}

function deepMerge<T extends Record<string, unknown>>(
    target: T,
    ...sources: DeepPartial<T>[]
): T {
    const result = { ...target };

    for (const source of sources) {
        if (!isPlainObject(source)) continue;

        for (const key of Object.keys(source) as (keyof T)[]) {
            const targetVal = result[key];
            const sourceVal = source[key as string];

            if (isPlainObject(targetVal) && isPlainObject(sourceVal)) {
                (result as Record<string, unknown>)[key as string] =
                    deepMerge(
                        targetVal as Record<string, unknown>,
                        sourceVal as Record<string, unknown>
                    );
            } else if (sourceVal !== undefined) {
                (result as Record<string, unknown>)[key as string] = sourceVal;
            }
        }
    }

    return result;
}

// Usage
const defaults = {
    server: { host: 'localhost', port: 3000, ssl: { enabled: false, cert: '' } },
    logging: { level: 'info', format: 'json' },
    features: { darkMode: false },
};

const userConfig = {
    server: { port: 8080, ssl: { enabled: true } },
    features: { darkMode: true },
};

const config = deepMerge(defaults, userConfig);
// Result:
// {
//   server: { host: 'localhost', port: 8080, ssl: { enabled: true, cert: '' } },
//   logging: { level: 'info', format: 'json' },
//   features: { darkMode: true },
// }
```

What this does: recursively merges objects so nested properties are combined rather than overwritten. If both the target and source have an object at the same key, it recurses. Otherwise the source value wins.

The `isPlainObject` check is critical -- without it, Date objects, arrays, RegExps, and other non-plain objects would be incorrectly treated as mergeable. Arrays are intentionally replaced wholesale rather than merged element-by-element, which is the behavior most config-merging use cases expect.

The function is immutable -- it returns a new object and doesn't modify the inputs.'''
    },
]
