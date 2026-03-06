"""Phase 2D: Advanced Reasoning — Multi-Perspective Analysis (Part 9)"""

PAIRS = [
    (
        "thinking/multiperspective-typescript-strict-adoption",
        "We have a 100K line JavaScript codebase and want to migrate to TypeScript. Should we do strict mode from the start or enable it gradually? The team is divided.",
        r'''<think>
TypeScript migration strategy for a large codebase. Let me think through perspectives.

**The "strict from day one" camp:**
- "If we start lax, we'll never get to strict. Technical debt compounds."
- "Strict mode catches the most bugs — that's the whole point of TypeScript."
- "One migration, one set of rules. Simpler."

**The "gradual strictness" camp:**
- "100K lines can't be converted overnight. We need to ship features too."
- "Team is new to TS — strict mode will frustrate them before they see the benefits."
- "Better to have 100K lines in loose TS than 10K in strict TS and 90K still in JS."

**Developer experience perspective:**
- Strict mode on unfamiliar code = hundreds of errors on day one
- Developers new to TS will be overwhelmed
- But loose mode teaches bad habits (any everywhere)

**Code quality perspective:**
- Strict catches: null/undefined errors, implicit any, incorrect function signatures
- Without strict, TypeScript is just "JavaScript with extra syntax" — marginal benefit
- The bugs strict catches are the ones that matter most in production

**Pragmatic perspective:**
You can have both — use tsconfig paths and per-directory config overrides.
Start with loose globally, make strict mandatory for new code and migrated modules.

For THIS codebase: 100K lines is large. Full strict conversion would take months.
But new code should be strict from day one.
</think>

Both sides have merit. Here's the multi-perspective breakdown and the path that actually works.

## The Two Camps

### "Strict From Day One"

```
Arguments:
  ✓ If you start lax, you'll accumulate technical debt in TypeScript too
  ✓ Strict mode is where the real value of TypeScript lives
  ✓ One set of rules is simpler than managing different strictness levels
  ✓ Re-migrating from loose TS to strict TS is a SECOND migration

The real cost:
  ✗ 100K lines of JS → strict TS = thousands of type errors
  ✗ Team needs to learn TS AND handle strict simultaneously
  ✗ Feature development freezes during migration
  ✗ Morale drops when every file change requires fixing 50 type errors
```

### "Gradual Strictness"

```
Arguments:
  ✓ Ship features while migrating — business doesn't stop
  ✓ Team learns TS incrementally (less overwhelming)
  ✓ 100K lines of loose TS is still better than 100K lines of JS
  ✓ Progressive adoption has higher success rate

The real cost:
  ✗ Loose TS allows `any` everywhere → "typed JavaScript" with no real safety
  ✗ Hard to tighten rules later (every strictness increase = new errors)
  ✗ Inconsistent rules confuse the team ("why is this strict but that isn't?")
```

## The Path That Works: Strict for New, Gradual for Old

```
NOT "strict everywhere now" (too painful)
NOT "loose everywhere forever" (defeats the purpose)
BUT "strict boundary that expands over time"
```

```jsonc
// tsconfig.json — base config (loose for existing code)
{
  "compilerOptions": {
    "strict": false,
    "allowJs": true,                // JS files can coexist
    "checkJs": false,               // Don't type-check JS yet
    "noImplicitAny": false,         // Allow implicit any (for now)
    "strictNullChecks": false,      // Allow null/undefined (for now)
    "target": "ES2020",
    "module": "commonjs",
    "outDir": "./dist"
  },
  "include": ["src/**/*"]
}
```

```jsonc
// src/new-features/tsconfig.json — strict for all new code
{
  "extends": "../tsconfig.json",
  "compilerOptions": {
    "strict": true,                 // Full strict mode
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noUncheckedIndexedAccess": true
  },
  "include": ["./**/*"]
}
```

## Migration Timeline

```
MONTH 1: Setup
  ├── Add TypeScript to project (alongside JS)
  ├── tsconfig with allowJs + loose settings
  ├── Rename entry points .js → .ts
  ├── CI: TypeScript compilation must pass
  └── Rule: ALL new files must be .ts (even if loosely typed)

MONTH 2-3: New code is strict
  ├── New features/modules written in strict TypeScript
  ├── Team learns TypeScript on new code (less legacy baggage)
  ├── @ts-expect-error for known issues at boundaries
  └── Don't rewrite old code yet — focus on new code quality

MONTH 4-6: Tighten incrementally
  ├── Enable noImplicitAny globally → fix errors
  ├── Enable strictNullChecks globally → fix errors (biggest change)
  ├── Each strictness flag = one PR, team reviews together
  └── Prioritize: critical modules first, utilities last

MONTH 7-12: Converge to strict
  ├── Enable strict: true globally
  ├── Convert remaining .js files to .ts
  ├── Remove allowJs
  └── All code under one strict standard
```

## The Critical Rules (Regardless of Approach)

```typescript
// RULE 1: Never use `any` in new code — use `unknown` instead
// ❌ any: silently disables ALL type checking
function process(data: any) {
    data.nonExistent.method();  // No error! Crashes at runtime.
}

// ✅ unknown: forces you to check types before using
function process(data: unknown) {
    if (typeof data === 'object' && data !== null && 'name' in data) {
        console.log(data.name);  // Safe
    }
}

// RULE 2: Ban // @ts-ignore without explanation
// CI check: grep for @ts-ignore without @ts-expect-error justification
// @ts-expect-error is better — it fails when the error is fixed (so you clean up)

// RULE 3: Enable strict ESLint rules even before strict TS
// @typescript-eslint/no-explicit-any: warn (then error)
// @typescript-eslint/no-non-null-assertion: warn
// @typescript-eslint/strict-boolean-expressions: warn
```

## What I'd Actually Recommend

```
For a 100K LOC codebase with a TS-new team:

1. Start with loose TS (allowJs, no strict) — get the tooling working
2. ALL new code in strict TypeScript — learn TS properly on fresh code
3. Enable strict flags one at a time (monthly) — gradual tightening
4. The goal: full strict within 6-12 months

The worst outcome is "loose TypeScript forever."
That's just JavaScript with extra syntax — all the cost, minimal benefit.

Strict TypeScript is the destination.
The question is just how quickly your team can get there.
```'''
    ),
    (
        "thinking/multiperspective-error-handling-strategy",
        "How should we handle errors in our API? Some developers throw exceptions everywhere, others return error codes, and some use Result types. We have no consistency.",
        r'''<think>
Error handling strategy — three competing approaches. Let me think through each perspective.

**Exceptions camp:**
- Familiar (most languages default to this)
- Don't clutter the "happy path" with error handling
- Stack traces for debugging
- But: invisible control flow, easy to forget to catch, performance cost

**Error codes camp:**
- Explicit — return value tells you if it worked
- No hidden control flow
- Simple to reason about
- But: easy to ignore return codes, verbose, can't carry context

**Result types camp:**
- Compiler forces you to handle errors (Rust, Haskell)
- Explicit in the function signature
- Can carry error context
- But: unfamiliar in Python/JavaScript, verbose, library-dependent

**For an API specifically:**
The internal error handling strategy is separate from the external API error response. Internally, use whatever works. But the API response must be consistent.

**My recommendation:**
- Exceptions for exceptional situations (DB down, network failure, programming errors)
- Result types / explicit returns for expected failures (validation, not found, business rules)
- Consistent API error response format regardless of internal mechanism

The key insight: not all errors are the same. "Database crashed" is fundamentally different from "email already taken." They should be handled differently.
</think>

The inconsistency is your actual problem — not which approach you pick. Let me break down each perspective, then give you a unified strategy.

## The Three Approaches

### Exceptions (Traditional)

```python
# Happy path is clean, errors are separate
def create_user(email, password):
    if not is_valid_email(email):
        raise ValidationError("Invalid email format")
    if User.exists(email=email):
        raise ConflictError("Email already registered")
    user = User.create(email=email, password=hash(password))
    return user

# Caller:
try:
    user = create_user(email, password)
except ValidationError as e:
    return {"error": str(e)}, 400
except ConflictError as e:
    return {"error": str(e)}, 409
```

```
✓ Clean happy path — error handling separate from business logic
✓ Stack traces — easy to debug in development
✓ Familiar — every Python/Java/JS developer knows try/catch
✗ Invisible control flow — any function might throw anything
✗ Easy to forget to catch — uncaught exception = 500 error
✗ Exception hierarchy management gets complex over time
```

### Error Codes / Return Values

```python
# Explicit return indicates success or failure
def create_user(email, password):
    if not is_valid_email(email):
        return None, "INVALID_EMAIL"
    if User.exists(email=email):
        return None, "EMAIL_EXISTS"
    user = User.create(email=email, password=hash(password))
    return user, None

# Caller:
user, error = create_user(email, password)
if error == "INVALID_EMAIL":
    return {"error": "Invalid email"}, 400
if error == "EMAIL_EXISTS":
    return {"error": "Email taken"}, 409
```

```
✓ Explicit — return value tells you if it worked
✓ No hidden control flow — error handling is visible
✗ Easy to ignore the error: user, _ = create_user(...)  ← bug!
✗ Can't carry context (just a string code, no details)
✗ Every call site needs if/else boilerplate
```

### Result Types (Functional)

```python
from dataclasses import dataclass
from typing import Union

@dataclass
class Success:
    value: any

@dataclass
class Failure:
    error: str
    details: dict = None

Result = Union[Success, Failure]

def create_user(email, password) -> Result:
    if not is_valid_email(email):
        return Failure("INVALID_EMAIL", {"email": email})
    if User.exists(email=email):
        return Failure("EMAIL_EXISTS", {"email": email})
    user = User.create(email=email, password=hash(password))
    return Success(user)

# Caller:
result = create_user(email, password)
match result:
    case Success(user):
        return {"id": user.id}, 201
    case Failure("INVALID_EMAIL", details):
        return {"error": "Invalid email", **details}, 400
    case Failure("EMAIL_EXISTS", _):
        return {"error": "Email already taken"}, 409
```

```
✓ Forces handling — can't use the value without unwrapping
✓ Carries context — error details alongside error type
✓ Type-safe — IDE knows the return type
✗ Unfamiliar in Python/JS (natural in Rust/Haskell)
✗ Verbose — wrapping/unwrapping everywhere
✗ Library-dependent — no standard Result type in Python
```

## The Unified Strategy: Not All Errors Are Equal

```
KEY INSIGHT: "database crashed" and "email already taken" are
fundamentally different kinds of errors. Treat them differently.

OPERATIONAL ERRORS (expected, recoverable):
  - Validation failure (bad user input)
  - Resource not found (404)
  - Business rule violation (insufficient funds)
  - Conflict (duplicate email)
  → Handle explicitly with Result types or domain exceptions
  → Return structured error responses to API clients

PROGRAMMING ERRORS (unexpected, bugs):
  - NullPointerException
  - IndexError
  - TypeError
  → Let these crash (they're bugs — fix them)
  → Caught by global error handler → 500 + logged

INFRASTRUCTURE ERRORS (external failures):
  - Database connection failed
  - External API timeout
  - Disk full
  → Catch at boundary, retry or degrade gracefully
  → Don't leak infrastructure details to API clients
```

## Practical Implementation

```python
# 1. Domain exceptions for business errors
class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status

class NotFoundError(AppError):
    def __init__(self, resource: str, id: any):
        super().__init__("NOT_FOUND", f"{resource} {id} not found", 404)

class ValidationError(AppError):
    def __init__(self, field: str, message: str):
        super().__init__("VALIDATION_ERROR", f"{field}: {message}", 422)

class ConflictError(AppError):
    def __init__(self, message: str):
        super().__init__("CONFLICT", message, 409)


# 2. Service layer uses domain exceptions
def create_user(email: str, password: str) -> User:
    if not is_valid_email(email):
        raise ValidationError("email", "Invalid format")
    if User.exists(email=email):
        raise ConflictError("Email already registered")
    return User.create(email=email, password=hash_password(password))


# 3. Global error handler maps exceptions to API responses
@app.exception_handler(AppError)
def handle_app_error(request, exc: AppError):
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message}}
    )

@app.exception_handler(Exception)
def handle_unexpected_error(request, exc: Exception):
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR",
                           "message": "An unexpected error occurred"}}
    )


# 4. Route handlers stay clean — no try/catch needed
@app.post("/users")
def create_user_endpoint(body: CreateUserRequest):
    user = create_user(body.email, body.password)  # Raises on failure
    return {"id": user.id, "email": user.email}    # Only reached on success
```

## Consistent API Error Response Format

```json
// ALWAYS this structure, regardless of internal error handling:
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Email: invalid format",
        "details": {
            "field": "email",
            "value": "not-an-email"
        }
    }
}

// HTTP Status codes:
// 400 — Bad request (malformed input)
// 401 — Unauthorized (not authenticated)
// 403 — Forbidden (authenticated but not allowed)
// 404 — Not found
// 409 — Conflict (duplicate resource)
// 422 — Validation error (valid JSON, invalid values)
// 429 — Rate limited
// 500 — Internal error (bug or infrastructure failure)
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
