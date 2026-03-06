"""Phase 4A: Self-Improvement -- Training Data Generation (Part 15)

Generate and evaluate training pairs for error handling topics.
Each answer creates 3 graded training pairs with quality analysis.
"""

PAIRS = [
    (
        "thinking/auto-datagen-error-handling-basics",
        r'''Generate 3 high-quality training pairs that teach error handling fundamentals: when to catch, when to raise, and how to write good error messages. For each pair, explain why it's effective training data.''',
        r'''<think>
Error handling is one of the most misunderstood programming topics:
1. Most developers either catch too broadly or not at all
2. Error messages are usually terrible (not actionable)
3. The distinction between recoverable and unrecoverable errors is critical

Progression: when to catch vs raise -> writing useful error messages -> error propagation strategies
</think>

Here are 3 training pairs for error handling fundamentals:

**Pair 1 (Beginner):**
```
Q: I am catching all exceptions with a bare `except` clause because I do not want my program to crash. Is this a good practice?

```python
try:
    result = do_something()
except:
    pass  # Ignore all errors
```

A: **No. This is one of the worst patterns in programming.** It hides bugs, swallows critical errors, and makes debugging nearly impossible.

**What you are actually catching and hiding:**
```python
try:
    result = do_something()
except:  # This catches ALL of these:
    pass
    # - TypeError: you passed wrong arguments (BUG in your code)
    # - NameError: you misspelled a variable (BUG in your code)
    # - KeyboardInterrupt: user pressed Ctrl+C (should exit!)
    # - SystemExit: program should terminate (should exit!)
    # - MemoryError: system is out of memory (critical!)
    # - Your actual expected error: file not found, network timeout
```

**The right approach: catch SPECIFIC exceptions you can HANDLE:**
```python
# BAD: Catch everything, handle nothing
try:
    data = json.loads(user_input)
except:
    pass

# GOOD: Catch specific error, handle it meaningfully
try:
    data = json.loads(user_input)
except json.JSONDecodeError as e:
    print(f"Invalid JSON input: {e}")
    data = {}  # Meaningful fallback

# GOOD: Catch multiple specific errors
try:
    response = requests.get(url, timeout=10)
    data = response.json()
except requests.Timeout:
    print("Request timed out, retrying...")
    data = retry_request(url)
except requests.ConnectionError:
    print("Cannot reach server, using cached data")
    data = load_cache()
except json.JSONDecodeError:
    print(f"Server returned invalid JSON: {response.text[:100]}")
    data = None
```

**Rules:**
1. Catch specific exceptions, never bare `except`
2. Only catch exceptions you can actually handle
3. If you cannot handle it, let it propagate
4. Never use `except: pass` -- at minimum, log the error
```

**Why this is effective:** Directly addresses the most common bad habit. Shows exactly what gets hidden by bare except, making the danger concrete rather than abstract.

**Pair 2 (Intermediate):**
```
Q: How do I write error messages that actually help the person debugging the problem? My error messages just say "An error occurred" and they are useless.

A: Good error messages answer three questions: **What happened? Why? How to fix it?**

```python
# BAD error messages:
raise ValueError("Invalid input")
raise RuntimeError("An error occurred")
raise Exception("Failed")

# GOOD error messages:
raise ValueError(
    f"Expected a positive integer for 'quantity', got {quantity!r}. "
    f"Quantity must be >= 1."
)

raise ConnectionError(
    f"Failed to connect to database at {host}:{port} after {retries} retries. "
    f"Check that the database is running and the credentials are correct. "
    f"Last error: {last_error}"
)

raise FileNotFoundError(
    f"Configuration file not found at '{config_path}'. "
    f"Create it by copying the template: cp config.example.yaml config.yaml"
)
```

**Error message template:**
```python
# Template: What happened + Context + How to fix
raise ExceptionType(
    f"[What] Failed to {action}. "
    f"[Context] Input was {input!r}, expected {expected}. "
    f"[Fix] {suggestion_to_fix}."
)
```

**Real-world examples:**
```python
def connect_to_database(url):
    if not url:
        raise ValueError(
            "Database URL is empty. "
            "Set the DATABASE_URL environment variable or pass it as an argument. "
            "Example: postgresql://user:pass@localhost:5432/mydb"
        )

    try:
        conn = psycopg2.connect(url)
    except psycopg2.OperationalError as e:
        if "password authentication failed" in str(e):
            raise ConnectionError(
                f"Database authentication failed for URL: {_mask_password(url)}. "
                f"Verify the username and password are correct."
            ) from e
        elif "could not connect to server" in str(e):
            raise ConnectionError(
                f"Cannot reach database server at {_extract_host(url)}. "
                f"Check that PostgreSQL is running: sudo systemctl status postgresql"
            ) from e
        raise  # Unknown error, propagate as-is

def parse_config(path):
    try:
        with open(path) as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(
            f"Configuration file '{path}' contains invalid YAML at line {e.problem_mark.line}. "
            f"Error: {e.problem}. "
            f"Validate your YAML at https://yamlchecker.com"
        ) from e

    required_keys = ['database_url', 'secret_key', 'debug']
    missing = [k for k in required_keys if k not in config]
    if missing:
        raise KeyError(
            f"Configuration file '{path}' is missing required keys: {', '.join(missing)}. "
            f"See config.example.yaml for all required fields."
        )
    return config
```

**Checklist for every error message:**
- Does it say WHAT went wrong? (not just "error")
- Does it include the ACTUAL value that caused the problem?
- Does it say what was EXPECTED?
- Does it suggest HOW TO FIX it?
- Does it avoid exposing secrets (passwords, tokens)?
```

**Why this is effective:** Transforms error handling from a chore into a communication skill. The template and checklist are immediately actionable. The real-world examples show production-quality error messages.

**Pair 3 (Advanced):**
```
Q: When should I create custom exception classes versus using built-in exceptions? I see some projects with dozens of custom exceptions and others that only use ValueError and RuntimeError.

A: **Create custom exceptions when callers need to handle different errors differently. Use built-in exceptions when the error type is standard.**

**Use built-in exceptions for standard situations:**
```python
# Good use of built-in exceptions:
def calculate_discount(price, percentage):
    if not isinstance(price, (int, float)):
        raise TypeError(f"price must be a number, got {type(price).__name__}")
    if percentage < 0 or percentage > 100:
        raise ValueError(f"percentage must be 0-100, got {percentage}")
    return price * (1 - percentage / 100)
```

**Create custom exceptions when callers need to distinguish errors:**
```python
# Define a hierarchy:
class PaymentError(Exception):
    """Base class for payment errors."""
    pass

class InsufficientFundsError(PaymentError):
    def __init__(self, balance, amount):
        self.balance = balance
        self.amount = amount
        super().__init__(
            f"Insufficient funds: balance is ${balance:.2f}, "
            f"tried to charge ${amount:.2f}. "
            f"Shortfall: ${amount - balance:.2f}"
        )

class CardDeclinedError(PaymentError):
    def __init__(self, reason, card_last_four):
        self.reason = reason
        self.card_last_four = card_last_four
        super().__init__(
            f"Card ending in {card_last_four} was declined: {reason}"
        )

class PaymentGatewayError(PaymentError):
    def __init__(self, gateway, status_code):
        self.gateway = gateway
        self.status_code = status_code
        super().__init__(
            f"Payment gateway '{gateway}' returned error {status_code}. "
            f"This is a temporary issue. Retry in a few minutes."
        )

# Now callers can handle each case differently:
try:
    charge_customer(customer_id, amount)
except InsufficientFundsError as e:
    show_message(f"Not enough funds. You need ${e.amount - e.balance:.2f} more.")
    suggest_add_funds()
except CardDeclinedError as e:
    show_message(f"Your card was declined: {e.reason}")
    suggest_different_card()
except PaymentGatewayError:
    show_message("Payment system is temporarily unavailable. Please try again.")
    queue_for_retry()
except PaymentError:
    # Catch-all for any payment error we did not specifically handle
    show_message("Payment failed. Please contact support.")
```

**Design guidelines:**
```
1. Create a base exception for your module/domain
   class MyLibraryError(Exception): pass

2. Subclass for errors that need different handling
   class AuthenticationError(MyLibraryError): pass
   class AuthorizationError(MyLibraryError): pass

3. Add useful attributes to custom exceptions
   class RateLimitError(MyLibraryError):
       def __init__(self, retry_after):
           self.retry_after = retry_after

4. Do NOT create exceptions for things that are not errors
   BAD:  raise UserNotFoundError()   # This is a normal case, not an error
   GOOD: return None   # or use Optional[User]

5. Do NOT create too many custom exceptions
   BAD:  InvalidFirstNameError, InvalidLastNameError, InvalidEmailError
   GOOD: ValidationError(field="first_name", reason="too short")
```

**When to use which:**
| Situation | Use |
|-----------|-----|
| Wrong argument type | TypeError |
| Wrong argument value | ValueError |
| Key not in dict | KeyError |
| File/path issues | FileNotFoundError, PermissionError |
| Domain-specific, caller needs to handle differently | Custom exception |
| Multiple error variants need different handling | Custom hierarchy |
| Too many similar errors | Single custom exception with attributes |
```

**Why this is effective:** Shows the decision framework for custom vs built-in exceptions. The payment example demonstrates a realistic hierarchy where custom exceptions enable better caller code. The guidelines prevent over-engineering.'''
    ),
    (
        "thinking/auto-datagen-error-propagation",
        r'''Generate 3 high-quality training pairs that teach error propagation and exception chaining across application layers. For each pair, explain why it's effective training data.''',
        r'''<think>
Error propagation across layers is poorly understood:
1. Where to catch vs where to let propagate
2. How to wrap low-level errors into domain errors
3. Exception chaining with `from` to preserve root cause

Progression: understanding propagation -> layer-appropriate handling -> exception chaining
</think>

Here are 3 training pairs for error propagation:

**Pair 1 (Beginner):**
```
Q: I have a function that calls another function that calls another function. Where should I catch the exception -- at every level?

A: **Catch exceptions at the level where you can HANDLE them, not everywhere.**

```python
# BAD: Catching at every level (catch-and-rethrow noise)
def controller():
    try:
        service_layer()
    except Exception as e:
        raise Exception(f"Controller error: {e}")

def service_layer():
    try:
        data_layer()
    except Exception as e:
        raise Exception(f"Service error: {e}")

def data_layer():
    try:
        db.execute("SELECT ...")
    except Exception as e:
        raise Exception(f"Data error: {e}")

# This gives you: "Controller error: Service error: Data error: connection refused"
# USELESS. Just noise wrapping noise.
```

```python
# GOOD: Catch only where you can meaningfully handle it
def controller(request):
    try:
        user = get_user_profile(request.user_id)
        return {"status": "ok", "user": user}
    except UserNotFoundError:
        return {"status": "error", "message": "User not found"}, 404
    except DatabaseError:
        log.error("Database error in get_user_profile", exc_info=True)
        return {"status": "error", "message": "Service unavailable"}, 503

def get_user_profile(user_id):
    # No try/except here -- let errors propagate
    row = db.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    if not row:
        raise UserNotFoundError(user_id)
    return User.from_row(row)
```

**The principle:**
```
data layer:    Raises specific errors
service layer: May transform errors, usually lets them propagate
controller:    Catches and converts to user-facing responses
```
```

**Why this is effective:** Shows the anti-pattern (catch everywhere) alongside the correct pattern (catch where you can handle). The layered architecture principle is immediately applicable.

**Pair 2 (Intermediate):**
```
Q: How do I wrap low-level exceptions into domain-appropriate exceptions without losing the original error information?

A: Use **exception chaining** with `raise ... from ...`:

```python
# WITHOUT chaining (original error LOST):
def get_user(user_id):
    try:
        row = db.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    except psycopg2.OperationalError:
        raise ServiceUnavailableError("Cannot fetch user")
    # The original database error (connection refused? timeout? syntax error?)
    # is GONE. Debugging is now much harder.

# WITH chaining (original error PRESERVED):
def get_user(user_id):
    try:
        row = db.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    except psycopg2.OperationalError as e:
        raise ServiceUnavailableError(
            f"Cannot fetch user {user_id}: database unavailable"
        ) from e
    # Traceback shows BOTH errors:
    # psycopg2.OperationalError: could not connect to server
    #
    # The above exception was the direct cause of the following exception:
    #
    # ServiceUnavailableError: Cannot fetch user 42: database unavailable
```

**Full example across layers:**
```python
# Data layer: wraps driver errors into repository errors
class UserRepository:
    def find_by_id(self, user_id):
        try:
            return self.db.execute(
                "SELECT * FROM users WHERE id = %s", (user_id,)
            )
        except psycopg2.IntegrityError as e:
            raise DataCorruptionError(f"User {user_id} data is corrupt") from e
        except psycopg2.OperationalError as e:
            raise RepositoryUnavailableError("User database unavailable") from e
        # Other psycopg2 errors propagate unchanged

# Service layer: wraps repository errors into service errors
class UserService:
    def get_profile(self, user_id):
        try:
            row = self.repo.find_by_id(user_id)
        except RepositoryUnavailableError as e:
            raise ServiceUnavailableError("User service is down") from e

        if not row:
            raise UserNotFoundError(user_id)
        return UserProfile.from_row(row)

# Controller: converts service errors to HTTP responses
@app.route("/users/<int:user_id>")
def get_user(user_id):
    try:
        profile = user_service.get_profile(user_id)
        return jsonify(profile.to_dict()), 200
    except UserNotFoundError:
        return jsonify({"error": "User not found"}), 404
    except ServiceUnavailableError:
        return jsonify({"error": "Service temporarily unavailable"}), 503
```

**The chain is preserved for debugging:**
```
psycopg2.OperationalError: connection refused
  -> RepositoryUnavailableError: User database unavailable
    -> ServiceUnavailableError: User service is down
```
Each layer adds CONTEXT. The original cause is never lost.
```

**Why this is effective:** Shows the exact mechanism (`from e`) and demonstrates a realistic three-layer architecture. The traceback output makes the benefit of chaining concrete.

**Pair 3 (Advanced):**
```
Q: How do I implement a global error handling strategy for a web application that properly logs, reports, and responds to different categories of errors?

A: Design error handling as an architectural concern, not ad-hoc try/except blocks:

```python
import logging
import traceback
from enum import Enum
from functools import wraps

logger = logging.getLogger(__name__)

class ErrorCategory(Enum):
    CLIENT = "client"         # 4xx: bad input, not found, unauthorized
    TRANSIENT = "transient"   # Retry-able: timeouts, rate limits
    INTERNAL = "internal"     # 5xx: bugs, unexpected failures
    EXTERNAL = "external"     # Third-party service failures

class AppError(Exception):
    """Base application error with category and HTTP status."""
    category = ErrorCategory.INTERNAL
    status_code = 500
    user_message = "An unexpected error occurred"

    def __init__(self, message=None, details=None):
        self.details = details or {}
        super().__init__(message or self.user_message)

class ValidationError(AppError):
    category = ErrorCategory.CLIENT
    status_code = 400
    user_message = "Invalid input"

class NotFoundError(AppError):
    category = ErrorCategory.CLIENT
    status_code = 404
    user_message = "Resource not found"

class RateLimitError(AppError):
    category = ErrorCategory.TRANSIENT
    status_code = 429
    user_message = "Too many requests"

    def __init__(self, retry_after=60):
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after {retry_after}s")

class ExternalServiceError(AppError):
    category = ErrorCategory.EXTERNAL
    status_code = 502
    user_message = "A dependent service is unavailable"

# Global error handler
def handle_error(error):
    """Central error handling -- log, report, respond."""
    if isinstance(error, AppError):
        category = error.category
        status_code = error.status_code
        user_message = error.user_message
    else:
        category = ErrorCategory.INTERNAL
        status_code = 500
        user_message = "An unexpected error occurred"

    # Log based on category
    if category == ErrorCategory.CLIENT:
        logger.info(f"Client error: {error}")
    elif category == ErrorCategory.TRANSIENT:
        logger.warning(f"Transient error: {error}")
    elif category == ErrorCategory.EXTERNAL:
        logger.error(f"External service error: {error}", exc_info=True)
    else:  # INTERNAL
        logger.critical(f"Internal error: {error}", exc_info=True)
        send_to_error_tracker(error)  # Sentry, Datadog, etc.

    # Build response
    response = {"error": user_message}
    if isinstance(error, RateLimitError):
        response["retry_after"] = error.retry_after
    if isinstance(error, ValidationError) and error.details:
        response["validation_errors"] = error.details

    return response, status_code

# Flask integration
@app.errorhandler(Exception)
def global_error_handler(error):
    response, status_code = handle_error(error)
    return jsonify(response), status_code

# Usage in routes -- clean, no try/except clutter
@app.route("/api/users", methods=["POST"])
def create_user():
    data = request.json
    errors = validate_user_data(data)
    if errors:
        raise ValidationError("Invalid user data", details=errors)

    user = user_service.create(data)  # May raise NotFoundError, ExternalServiceError, etc.
    return jsonify(user.to_dict()), 201
    # No try/except needed! Global handler catches everything.
```

**Error category behavior:**
| Category | Log level | Alert team? | Show details to user? | Retry? |
|----------|-----------|-------------|----------------------|--------|
| CLIENT | INFO | No | Yes (validation errors) | No |
| TRANSIENT | WARNING | If frequent | No | Yes |
| EXTERNAL | ERROR | Yes | No | Maybe |
| INTERNAL | CRITICAL | Immediately | Never | No |
```

**Why this is effective:** Shows error handling as an architectural pattern rather than scattered try/except blocks. The category-based approach is how production systems actually work. The clean route code demonstrates the benefit of centralized handling.'''
    ),
    (
        "thinking/auto-datagen-retry-patterns",
        r'''Generate 3 high-quality training pairs that teach retry and resilience patterns for handling transient failures. For each pair, explain why it's effective training data.''',
        r'''<think>
Retry patterns are essential for reliable systems:
1. Not all errors should be retried -- only transient ones
2. Naive retries can make problems worse (thundering herd)
3. Patterns: exponential backoff, circuit breaker, bulkhead

Progression: basic retry with backoff -> circuit breaker -> comprehensive resilience
</think>

Here are 3 training pairs for retry and resilience patterns:

**Pair 1 (Beginner):**
```
Q: My application calls an external API that sometimes returns 500 errors. How do I add retry logic without hammering the server?

A: Use **exponential backoff** -- wait longer between each retry:

```python
import time
import random
import requests

def call_api_with_retry(url, max_retries=3, base_delay=1.0):
    """Retry with exponential backoff and jitter."""
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code < 500:
                raise  # 4xx errors are NOT retryable (client error)
            last_error = e
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_error = e

        if attempt < max_retries:
            # Exponential backoff: 1s, 2s, 4s (with jitter)
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            print(f"Attempt {attempt + 1} failed, retrying in {delay:.1f}s...")
            time.sleep(delay)

    raise last_error  # All retries exhausted

# Usage:
data = call_api_with_retry("https://api.example.com/data")
```

**Why exponential backoff?**
| Attempt | Delay (no backoff) | Delay (exponential) |
|---------|-------------------|-------------------|
| 1 | 1s | 1s |
| 2 | 1s | 2s |
| 3 | 1s | 4s |
| 4 | 1s | 8s |

Without backoff: if the server is overloaded, retries hit it every second, making it worse.
With backoff: retries space out, giving the server time to recover.

**Why jitter?** If 1000 clients retry at exactly the same intervals, they all hit the server simultaneously. Random jitter spreads them out.
```

**Why this is effective:** Starts with the common problem, shows the simplest correct solution, and explains WHY each element (exponential, jitter) matters with concrete scenarios.

**Pair 2 (Intermediate):**
```
Q: What is a circuit breaker pattern and when should I use it instead of simple retries?

A: A **circuit breaker** stops calling a failing service entirely, preventing cascading failures:

```python
import time
import threading
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation, requests go through
    OPEN = "open"           # Service is down, fail immediately
    HALF_OPEN = "half_open" # Testing if service has recovered

class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=30, success_threshold=3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.lock = threading.Lock()

    def call(self, func, *args, **kwargs):
        with self.lock:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                else:
                    raise CircuitOpenError(
                        f"Circuit is open. Service unavailable. "
                        f"Retry after {self.recovery_timeout}s"
                    )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        with self.lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
            else:
                self.failure_count = 0

    def _on_failure(self):
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

# Usage:
payment_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

def charge_customer(amount):
    return payment_breaker.call(payment_api.charge, amount)
```

**How it works:**
```
CLOSED (normal) ----[5 failures]----> OPEN (fail fast)
                                        |
                                   [60s timeout]
                                        |
                                   HALF_OPEN (test)
                                        |
                          [3 successes] / \ [1 failure]
                              |               |
                          CLOSED          OPEN
```

**Retry vs Circuit Breaker:**
| Scenario | Retry | Circuit Breaker |
|----------|-------|----------------|
| Occasional flaky errors | Good | Unnecessary |
| Service is completely down | Wastes time on every request | Fails instantly after threshold |
| Downstream service overloaded | Makes it worse | Gives it time to recover |
| Cost of waiting | Acceptable | Unacceptable (user-facing) |
```

**Why this is effective:** Shows a complete implementation the learner can use, with a state diagram and comparison table explaining when to use each pattern.

**Pair 3 (Advanced):**
```
Q: How do I combine retry, circuit breaker, timeout, and fallback into a comprehensive resilience strategy?

A: Layer resilience patterns from inside out:

```python
import asyncio
import time
from functools import wraps

class ResiliencePolicy:
    """Composable resilience: timeout -> retry -> circuit breaker -> fallback."""

    def __init__(self, timeout=5.0, max_retries=3, circuit_threshold=5,
                 circuit_timeout=60, fallback=None):
        self.timeout_seconds = timeout
        self.max_retries = max_retries
        self.circuit = CircuitBreaker(circuit_threshold, circuit_timeout)
        self.fallback_fn = fallback

    def execute(self, func, *args, **kwargs):
        try:
            # Layer 1: Circuit breaker (outermost -- fail fast if service is down)
            return self.circuit.call(
                self._retry_with_timeout, func, *args, **kwargs
            )
        except Exception as e:
            # Layer 4: Fallback (last resort)
            if self.fallback_fn:
                return self.fallback_fn(e)
            raise

    def _retry_with_timeout(self, func, *args, **kwargs):
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                # Layer 2: Timeout (per-attempt)
                return self._with_timeout(func, *args, **kwargs)
            except (TimeoutError, ConnectionError, IOError) as e:
                last_error = e
                if attempt < self.max_retries:
                    # Layer 3: Exponential backoff between retries
                    delay = (2 ** attempt) + (time.time() % 1)
                    time.sleep(delay)
        raise last_error

    def _with_timeout(self, func, *args, **kwargs):
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=self.timeout_seconds)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(
                    f"Call to {func.__name__} timed out after {self.timeout_seconds}s"
                )

# Usage:
def get_cached_recommendations(error):
    """Fallback: return cached data when recommendation service is down."""
    return load_from_cache("recommendations")

recommendation_policy = ResiliencePolicy(
    timeout=3.0,
    max_retries=2,
    circuit_threshold=5,
    circuit_timeout=30,
    fallback=get_cached_recommendations,
)

def get_recommendations(user_id):
    return recommendation_policy.execute(
        recommendation_api.fetch, user_id
    )
```

**The resilience onion (inside to outside):**
```
Request
  -> Timeout (3s): prevents hanging
    -> Retry (3 attempts): handles transient failures
      -> Circuit breaker: prevents flooding a dead service
        -> Fallback: returns degraded but usable response
```

**Complete resilience decision matrix:**
| Failure type | Pattern | Example |
|-------------|---------|---------|
| Slow response | Timeout | API takes 30s instead of 1s |
| Intermittent error | Retry + backoff | 500 error, works on retry |
| Service down | Circuit breaker | Database unreachable |
| Service permanently degraded | Fallback | Return cached/default data |
| Upstream overload | Rate limiting | Too many requests per second |
| Resource exhaustion | Bulkhead | Separate thread pools per service |

**Key insight:** These patterns compose. Use timeout inside retry inside circuit breaker. Each layer handles a different failure mode.
```

**Why this is effective:** Shows how individual patterns compose into a comprehensive strategy. The "resilience onion" mental model and decision matrix give the learner a framework for designing resilient systems.'''
    ),
    (
        "thinking/auto-datagen-logging-errors",
        r'''Generate 3 high-quality training pairs that teach effective error logging -- what to log, how to structure logs, and how to make errors searchable in production. For each pair, explain why it's effective training data.''',
        r'''<think>
Error logging is the bridge between error handling and debugging:
1. Most logs are useless because they lack context
2. Structured logging makes errors searchable
3. Log levels matter -- too much noise hides real problems

Progression: what to include in error logs -> structured logging -> correlation and tracing
</think>

Here are 3 training pairs for effective error logging:

**Pair 1 (Beginner):**
```
Q: I log errors with `print(e)` but when something goes wrong in production I cannot figure out what happened. How do I log errors properly?

A: Use the `logging` module and include CONTEXT, not just the error message:

```python
import logging

logger = logging.getLogger(__name__)

# BAD: No context
def process_order(order_id):
    try:
        charge_customer(order_id)
    except Exception as e:
        print(e)  # Output: "connection refused"
        # WHO? WHAT? WHEN? WHERE? No idea.

# GOOD: Full context with traceback
def process_order(order_id):
    try:
        order = get_order(order_id)
        charge_customer(order.customer_id, order.total)
    except PaymentError as e:
        logger.error(
            "Payment failed for order %s (customer %s, amount $%.2f): %s",
            order_id, order.customer_id, order.total / 100, e,
            exc_info=True,  # Includes full traceback
            extra={
                "order_id": order_id,
                "customer_id": order.customer_id,
                "amount_cents": order.total,
            }
        )
        raise  # Re-raise after logging
```

**The difference in production:**

BAD log:
```
connection refused
```

GOOD log:
```
2024-03-15 14:23:01 ERROR process_order Payment failed for order 12345
(customer 67, amount $49.99): connection refused
Traceback (most recent call last):
  File "orders.py", line 42, in process_order
    charge_customer(order.customer_id, order.total)
  File "payments.py", line 15, in charge_customer
    response = stripe.Charge.create(amount=amount)
  File "stripe/api.py", line 88, in create
    raise ConnectionError("connection refused")
```

**What to always include:**
1. What operation was being performed
2. What input/identifiers were involved
3. The full traceback (`exc_info=True`)
4. Any relevant state (amounts, statuses, counts)
```

**Why this is effective:** Shows the stark contrast between useless and useful error logs. The checklist of what to include is immediately actionable.

**Pair 2 (Intermediate):**
```
Q: How do I implement structured logging so I can search and filter errors in production monitoring tools?

A: Use structured logging (JSON format) instead of plain text:

```python
import logging
import json
import traceback
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields
        if hasattr(record, "order_id"):
            log_entry["order_id"] = record.order_id
        if hasattr(record, "customer_id"):
            log_entry["customer_id"] = record.customer_id
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms

        # Add exception info
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log_entry)

# Configure
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("myapp")
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Usage:
logger.error(
    "Payment processing failed",
    extra={"order_id": 12345, "customer_id": 67, "duration_ms": 3400},
    exc_info=True
)
```

**Output (one line of JSON, formatted here for readability):**
```json
{
    "timestamp": "2024-03-15T14:23:01.456Z",
    "level": "ERROR",
    "logger": "myapp",
    "message": "Payment processing failed",
    "module": "orders",
    "function": "process_order",
    "line": 42,
    "order_id": 12345,
    "customer_id": 67,
    "duration_ms": 3400,
    "exception": {
        "type": "ConnectionError",
        "message": "connection refused",
        "traceback": ["..."]
    }
}
```

**Now you can search in your monitoring tool:**
- All errors for order 12345: `order_id:12345 AND level:ERROR`
- All payment errors over 3 seconds: `duration_ms:>3000 AND message:"Payment"`
- All errors for customer 67: `customer_id:67 AND level:ERROR`
```

**Why this is effective:** Shows the complete implementation and demonstrates how structured logs enable powerful searching. The example queries make the benefit tangible.

**Pair 3 (Advanced):**
```
Q: How do I trace a single user request across multiple services and log files? When a request fails, I need to find all related logs across the system.

A: Use **correlation IDs** (also called request IDs or trace IDs):

```python
import uuid
import logging
import threading
from contextvars import ContextVar

# Store request ID in context (thread-safe, async-safe)
request_id_var: ContextVar[str] = ContextVar("request_id", default="no-request-id")

class RequestIDFilter(logging.Filter):
    """Automatically adds request_id to every log entry."""
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True

# Middleware: assign request ID at the start of every request
@app.before_request
def assign_request_id():
    # Use incoming header if present (from upstream service), otherwise generate
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request_id_var.set(req_id)
    # Add to response headers so caller can correlate
    g.request_id = req_id

@app.after_request
def add_request_id_header(response):
    response.headers["X-Request-ID"] = g.request_id
    return response

# When calling other services, pass the request ID along
def call_payment_service(order_id, amount):
    return requests.post(
        "https://payments.internal/charge",
        json={"order_id": order_id, "amount": amount},
        headers={"X-Request-ID": request_id_var.get()},
        timeout=10,
    )

# Now EVERY log line includes the request ID:
logger.info("Processing order", extra={"order_id": 123})
# {"request_id": "abc-123-def", "message": "Processing order", "order_id": 123}

logger.info("Charging customer")
# {"request_id": "abc-123-def", "message": "Charging customer"}

# Payment service also logs with the same request_id:
# {"request_id": "abc-123-def", "message": "Charge successful", "service": "payments"}
```

**Tracing a failed request across services:**
```
Search: request_id:"abc-123-def"

Results (across all services, chronological):
14:23:01.100  [api-gateway]  Incoming request POST /orders
14:23:01.102  [order-service] Processing order 123
14:23:01.105  [order-service] Validating inventory
14:23:01.200  [inventory-svc] Reserved 2 items for order 123
14:23:01.300  [order-service] Charging customer
14:23:01.301  [payment-svc]  Charge request: $49.99
14:23:04.500  [payment-svc]  ERROR: Stripe timeout after 3s
14:23:04.501  [order-service] ERROR: Payment failed, releasing inventory
14:23:04.600  [inventory-svc] Released 2 items for order 123
14:23:04.601  [order-service] Returning 503 to client
```

**With one search query, you see the complete story of a request.**

**Implementation checklist:**
1. Generate/propagate request ID in every service
2. Add request ID to every log entry (use logging Filter)
3. Pass request ID in HTTP headers between services
4. Use ContextVar (not thread-local) for async compatibility
5. Include request ID in error responses so users can report it
```

**Why this is effective:** Shows the complete distributed tracing pattern that production systems use. The example trace output demonstrates the dramatic debugging improvement. The ContextVar approach works correctly with both threads and async.'''
    ),
    (
        "thinking/auto-datagen-error-recovery",
        r'''Generate 3 high-quality training pairs that teach error recovery strategies: graceful degradation, fallbacks, and partial failure handling. For each pair, explain why it's effective training data.''',
        r'''<think>
Error recovery is about what happens AFTER the error is detected:
1. Graceful degradation -- keep working with reduced functionality
2. Fallbacks -- alternative paths when primary path fails
3. Partial failure handling -- some operations succeed, some fail

Progression: simple fallbacks -> graceful degradation strategies -> handling partial success
</think>

Here are 3 training pairs for error recovery strategies:

**Pair 1 (Beginner):**
```
Q: My application crashes when the recommendation engine is unavailable. But recommendations are optional -- the page should still work without them. How do I handle this?

A: Use a **fallback pattern** -- provide a default when the optional service fails:

```python
def get_product_page(product_id):
    product = product_service.get(product_id)  # Required -- fail if unavailable

    # Optional service with fallback:
    try:
        recommendations = recommendation_service.get_similar(product_id, timeout=2)
    except (ConnectionError, TimeoutError):
        recommendations = get_popular_products()  # Fallback: show popular items
    except Exception:
        recommendations = []  # Ultimate fallback: show nothing

    return render_template('product.html',
                          product=product,
                          recommendations=recommendations)
```

**Fallback hierarchy:**
```
Primary:   Personalized recommendations from ML service
Fallback 1: Popular products from cache
Fallback 2: Recently viewed products from session
Fallback 3: Empty list (show nothing)
```

**Key principle:** Classify every dependency as REQUIRED or OPTIONAL.
- Required (product data): if it fails, the page fails
- Optional (recommendations): if it fails, the page works without it
```

**Why this is effective:** Shows a practical pattern with a clear hierarchy. The required vs optional classification is a principle the learner can apply to any page or endpoint.

**Pair 2 (Intermediate):**
```
Q: How do I design graceful degradation so my application gets worse gradually instead of failing all at once?

A: Define **degradation levels** and automatically switch between them based on system health:

```python
from enum import IntEnum

class DegradationLevel(IntEnum):
    FULL = 0         # Everything works
    REDUCED = 1      # Non-essential features disabled
    MINIMAL = 2      # Only core features
    EMERGENCY = 3    # Static fallback page

class ServiceHealth:
    def __init__(self):
        self.checks = {}

    def register_check(self, name, check_fn, required=True):
        self.checks[name] = {"fn": check_fn, "required": required}

    def get_degradation_level(self):
        failed_required = []
        failed_optional = []

        for name, check in self.checks.items():
            try:
                check["fn"]()
            except Exception:
                if check["required"]:
                    failed_required.append(name)
                else:
                    failed_optional.append(name)

        if failed_required:
            return DegradationLevel.EMERGENCY
        elif len(failed_optional) > 2:
            return DegradationLevel.MINIMAL
        elif failed_optional:
            return DegradationLevel.REDUCED
        return DegradationLevel.FULL

# Feature flags based on degradation level:
health = ServiceHealth()

@app.route('/dashboard')
def dashboard():
    level = health.get_degradation_level()

    data = {"level": level.name}

    if level <= DegradationLevel.FULL:
        data["recommendations"] = get_recommendations()
        data["analytics"] = get_analytics()
        data["notifications"] = get_notifications()

    if level <= DegradationLevel.REDUCED:
        data["recent_activity"] = get_recent_activity()

    if level <= DegradationLevel.MINIMAL:
        data["core_data"] = get_core_data()  # Always try this

    if level >= DegradationLevel.EMERGENCY:
        return render_template('emergency.html')  # Static page

    return render_template('dashboard.html', **data)
```
```

**Why this is effective:** Shows a concrete implementation of degradation levels with automatic health-based switching. The learner can adapt the pattern to their own application.

**Pair 3 (Advanced):**
```
Q: I have a batch operation that processes 1000 items. Some will succeed and some will fail. How do I handle partial failures without losing the successful operations?

A: Use a **partial success pattern** with detailed result tracking:

```python
from dataclasses import dataclass, field
from typing import List, Any, Optional

@dataclass
class OperationResult:
    item_id: str
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None

@dataclass
class BatchResult:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: List[OperationResult] = field(default_factory=list)

    @property
    def partial_success(self):
        return 0 < self.succeeded < self.total

    def summary(self):
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "success_rate": f"{self.succeeded/self.total:.1%}" if self.total > 0 else "N/A",
            "failed_items": [r.item_id for r in self.results if not r.success],
        }

def process_batch(items, process_fn, max_failures=None):
    batch = BatchResult(total=len(items))

    for item in items:
        try:
            result = process_fn(item)
            batch.results.append(OperationResult(
                item_id=item.id, success=True, result=result
            ))
            batch.succeeded += 1
        except Exception as e:
            batch.results.append(OperationResult(
                item_id=item.id, success=False, error=str(e)
            ))
            batch.failed += 1

            # Circuit breaker: stop if too many failures
            if max_failures and batch.failed >= max_failures:
                # Mark remaining items as not attempted
                break

    return batch

# Usage:
result = process_batch(orders, charge_order, max_failures=50)
if result.failed > 0:
    logger.warning(f"Partial batch failure: {result.summary()}")
    retry_queue.enqueue(result.summary()["failed_items"])
```

**API response for partial success:**
```json
{
    "status": "partial_success",
    "total": 1000,
    "succeeded": 987,
    "failed": 13,
    "failed_items": [
        {"id": "order-42", "error": "Payment declined"},
        {"id": "order-99", "error": "Insufficient inventory"}
    ],
    "retry_url": "/api/batch/retry/abc123"
}
```

HTTP status: **207 Multi-Status** (not 200 or 500).
```

**Why this is effective:** Shows the complete partial-success pattern including result tracking, circuit breaking, and the 207 HTTP status code. The retry queue for failed items is a production-quality pattern.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
