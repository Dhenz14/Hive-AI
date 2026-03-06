"""Thinking-trace pairs: API error design."""

PAIRS = [
    (
        "thinking/error-handling",
        r'''How should I design error codes for my REST API? I want something more useful than just HTTP status codes but I am not sure how to structure the error response body.''',
        r'''<think>
API error design needs:
1. HTTP status codes used correctly (not everything is 400 or 500)
2. Application-level error codes for programmatic handling
3. Human-readable messages for developers
4. Enough detail to debug without exposing internals
5. Consistent structure across all endpoints

I should show a well-designed error response schema with examples
for different error categories, plus how to implement it in a framework.
</think>

Good API error design uses HTTP status codes for the category and structured error bodies for the details. Here is a complete design:

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Any
import json
import time
import uuid


# ============================================================
# ERROR CODE REGISTRY
# ============================================================

class ErrorCategory(Enum):
    """Top-level error categories mapped to HTTP status ranges."""
    VALIDATION = "validation"      # 400
    AUTHENTICATION = "auth"        # 401
    AUTHORIZATION = "authz"        # 403
    NOT_FOUND = "not_found"        # 404
    CONFLICT = "conflict"          # 409
    RATE_LIMIT = "rate_limit"      # 429
    INTERNAL = "internal"          # 500
    UNAVAILABLE = "unavailable"    # 503


# Error codes follow the pattern: CATEGORY.SPECIFIC_ERROR
# This makes them grep-able, sortable, and self-documenting.
ERROR_CODES = {
    # Validation errors (400)
    "VALIDATION.REQUIRED_FIELD": {
        "status": 400,
        "title": "Required field missing",
    },
    "VALIDATION.INVALID_FORMAT": {
        "status": 400,
        "title": "Field format is invalid",
    },
    "VALIDATION.OUT_OF_RANGE": {
        "status": 400,
        "title": "Value is out of allowed range",
    },
    "VALIDATION.INVALID_ENUM": {
        "status": 400,
        "title": "Value is not one of the allowed options",
    },

    # Authentication errors (401)
    "AUTH.TOKEN_EXPIRED": {
        "status": 401,
        "title": "Authentication token has expired",
    },
    "AUTH.TOKEN_INVALID": {
        "status": 401,
        "title": "Authentication token is invalid",
    },
    "AUTH.CREDENTIALS_INVALID": {
        "status": 401,
        "title": "Invalid credentials",
    },

    # Authorization errors (403)
    "AUTHZ.INSUFFICIENT_PERMISSIONS": {
        "status": 403,
        "title": "You do not have permission for this action",
    },
    "AUTHZ.RESOURCE_FORBIDDEN": {
        "status": 403,
        "title": "Access to this resource is forbidden",
    },

    # Not found (404)
    "NOT_FOUND.RESOURCE": {
        "status": 404,
        "title": "Resource not found",
    },
    "NOT_FOUND.ENDPOINT": {
        "status": 404,
        "title": "API endpoint not found",
    },

    # Conflict (409)
    "CONFLICT.ALREADY_EXISTS": {
        "status": 409,
        "title": "Resource already exists",
    },
    "CONFLICT.VERSION_MISMATCH": {
        "status": 409,
        "title": "Resource was modified by another request",
    },

    # Rate limiting (429)
    "RATE_LIMIT.TOO_MANY_REQUESTS": {
        "status": 429,
        "title": "Too many requests",
    },

    # Internal (500)
    "INTERNAL.UNEXPECTED": {
        "status": 500,
        "title": "An unexpected error occurred",
    },
    "INTERNAL.DATABASE": {
        "status": 500,
        "title": "A database error occurred",
    },

    # Unavailable (503)
    "UNAVAILABLE.MAINTENANCE": {
        "status": 503,
        "title": "Service is under maintenance",
    },
    "UNAVAILABLE.DEPENDENCY": {
        "status": 503,
        "title": "A required service is unavailable",
    },
}


# ============================================================
# ERROR RESPONSE BUILDER
# ============================================================

@dataclass
class APIError:
    """Structured API error following RFC 7807 (Problem Details)."""
    code: str                          # e.g., "VALIDATION.REQUIRED_FIELD"
    detail: str                        # Human-readable explanation
    field: Optional[str] = None        # Which field caused it (for validation)
    meta: dict = field(default_factory=dict)  # Extra context

    def to_dict(self) -> dict:
        result = {
            "code": self.code,
            "title": ERROR_CODES.get(self.code, {}).get("title", "Error"),
            "detail": self.detail,
        }
        if self.field:
            result["field"] = self.field
        if self.meta:
            result["meta"] = self.meta
        return result


@dataclass
class ErrorResponse:
    """Complete API error response."""
    errors: list[APIError]
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    @property
    def status_code(self) -> int:
        """Use the highest-priority status code from all errors."""
        if not self.errors:
            return 500
        codes = [
            ERROR_CODES.get(e.code, {}).get("status", 500)
            for e in self.errors
        ]
        # Prefer 5xx over 4xx, higher over lower
        return max(codes)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "errors": [e.to_dict() for e in self.errors],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ============================================================
# ERROR BUILDER HELPERS
# ============================================================

def validation_error(field_name: str, detail: str,
                      code: str = "VALIDATION.INVALID_FORMAT") -> APIError:
    return APIError(code=code, detail=detail, field=field_name)


def not_found_error(resource_type: str, resource_id: str) -> APIError:
    return APIError(
        code="NOT_FOUND.RESOURCE",
        detail=f"{resource_type} with ID '{resource_id}' was not found",
        meta={"resource_type": resource_type, "resource_id": resource_id},
    )


def auth_error(detail: str, code: str = "AUTH.TOKEN_INVALID") -> APIError:
    return APIError(code=code, detail=detail)


def rate_limit_error(limit: int, window: str,
                      retry_after: int) -> APIError:
    return APIError(
        code="RATE_LIMIT.TOO_MANY_REQUESTS",
        detail=f"Rate limit of {limit} requests per {window} exceeded",
        meta={"limit": limit, "window": window, "retry_after": retry_after},
    )


# ============================================================
# FRAMEWORK INTEGRATION (FastAPI example)
# ============================================================

# from fastapi import FastAPI, Request
# from fastapi.responses import JSONResponse
#
# app = FastAPI()
#
# class APIException(Exception):
#     def __init__(self, errors: list[APIError]):
#         self.response = ErrorResponse(errors=errors)
#
# @app.exception_handler(APIException)
# async def api_error_handler(request: Request, exc: APIException):
#     return JSONResponse(
#         status_code=exc.response.status_code,
#         content=exc.response.to_dict(),
#         headers={"X-Request-ID": exc.response.request_id},
#     )
#
# @app.get("/users/{user_id}")
# async def get_user(user_id: str):
#     user = await db.find_user(user_id)
#     if not user:
#         raise APIException([not_found_error("User", user_id)])
#     return user


# ============================================================
# EXAMPLE RESPONSES
# ============================================================

# Single validation error:
resp = ErrorResponse(errors=[
    validation_error("email", "Must be a valid email address"),
])
print(resp.to_json())
# {
#   "request_id": "a1b2c3d4e5f6",
#   "timestamp": "2025-01-15T10:30:00Z",
#   "errors": [{
#     "code": "VALIDATION.INVALID_FORMAT",
#     "title": "Field format is invalid",
#     "detail": "Must be a valid email address",
#     "field": "email"
#   }]
# }

# Multiple validation errors (returned together):
resp = ErrorResponse(errors=[
    validation_error("name", "Name is required", "VALIDATION.REQUIRED_FIELD"),
    validation_error("age", "Age must be between 0 and 150", "VALIDATION.OUT_OF_RANGE"),
    validation_error("role", "Must be one of: admin, user, viewer", "VALIDATION.INVALID_ENUM"),
])
print(f"Status: {resp.status_code}")  # 400
print(resp.to_json())
```

**Design principles:**

1. **Dotted error codes** (`CATEGORY.SPECIFIC`) are grep-able, hierarchical, and self-documenting
2. **Multiple errors per response**: for validation, return ALL errors at once so the client can fix everything in one pass
3. **Separate title vs detail**: title is generic ("Field format is invalid"), detail is specific ("Must be a valid email address")
4. **Request ID in every error**: enables correlation between client reports and server logs
5. **Meta field for machine-readable context**: retry_after for rate limits, resource_type for 404s -- clients can handle these programmatically''',
    ),
    (
        "thinking/error-handling",
        r'''What is RFC 7807 Problem Details and how do I implement it properly in my API? I have heard it is the standard way to return errors but I am not sure about all the fields.''',
        r'''<think>
RFC 7807 defines a standard JSON format for HTTP API error responses.
The spec defines these members:
- type: URI identifying the error type (acts as documentation link)
- title: short human-readable summary (same for all instances of this type)
- status: HTTP status code
- detail: human-readable explanation specific to this occurrence
- instance: URI identifying this specific occurrence

I should show a proper implementation that follows the spec exactly,
including content-type header and extensibility.
</think>

RFC 7807 (Problem Details for HTTP APIs) defines a standard error response format. Here is a spec-compliant implementation:

```python
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Any


# ============================================================
# RFC 7807 PROBLEM DETAILS
# ============================================================

@dataclass
class ProblemDetail:
    """RFC 7807 Problem Details response.

    Required by the spec:
    - Content-Type: application/problem+json
    - Members: type, title, status, detail, instance

    All other members are "extension members" and are allowed.
    """

    # REQUIRED by RFC 7807
    type: str           # URI reference identifying the problem type
                        # Ideally a URL that resolves to documentation
    title: str          # Short human-readable summary (NOT instance-specific)
    status: int         # HTTP status code

    # OPTIONAL by RFC 7807
    detail: str = ""    # Human-readable explanation of THIS occurrence
    instance: str = ""  # URI reference for this specific occurrence

    # Extension members (allowed by the spec)
    extensions: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
        }
        if self.detail:
            result["detail"] = self.detail
        if self.instance:
            result["instance"] = self.instance
        # Extension members go at the top level, not nested
        result.update(self.extensions)
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @property
    def content_type(self) -> str:
        """RFC 7807 requires this specific content type."""
        return "application/problem+json"


# ============================================================
# PROBLEM TYPE REGISTRY
# ============================================================

# The "type" field should be a URI. Best practice is to use URLs
# that actually resolve to documentation pages.
BASE_URL = "https://api.example.com/problems"


class ProblemTypes:
    """Registry of all problem types in your API."""

    # Validation problems
    VALIDATION_ERROR = f"{BASE_URL}/validation-error"
    INVALID_FORMAT = f"{BASE_URL}/invalid-format"

    # Auth problems
    TOKEN_EXPIRED = f"{BASE_URL}/token-expired"
    INSUFFICIENT_SCOPE = f"{BASE_URL}/insufficient-scope"

    # Business logic problems
    INSUFFICIENT_FUNDS = f"{BASE_URL}/insufficient-funds"
    ORDER_NOT_CANCELLABLE = f"{BASE_URL}/order-not-cancellable"
    DUPLICATE_SUBMISSION = f"{BASE_URL}/duplicate-submission"

    # Infrastructure problems
    SERVICE_UNAVAILABLE = f"{BASE_URL}/service-unavailable"
    RATE_LIMITED = f"{BASE_URL}/rate-limited"

    # Fallback (RFC 7807 says use about:blank for generic HTTP errors)
    GENERIC = "about:blank"


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def validation_problem(field_name: str, detail: str,
                        invalid_value: Any = None) -> ProblemDetail:
    extensions = {
        "field": field_name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if invalid_value is not None:
        extensions["invalid_value"] = str(invalid_value)

    return ProblemDetail(
        type=ProblemTypes.VALIDATION_ERROR,
        title="Validation Error",
        status=400,
        detail=detail,
        instance=f"/errors/{uuid.uuid4().hex[:12]}",
        extensions=extensions,
    )


def not_found_problem(resource_type: str, resource_id: str) -> ProblemDetail:
    return ProblemDetail(
        type=ProblemTypes.GENERIC,
        title="Not Found",
        status=404,
        detail=f"No {resource_type} found with ID '{resource_id}'",
        instance=f"/errors/{uuid.uuid4().hex[:12]}",
    )


def rate_limit_problem(limit: int, window_seconds: int,
                        retry_after: int) -> ProblemDetail:
    return ProblemDetail(
        type=ProblemTypes.RATE_LIMITED,
        title="Rate Limit Exceeded",
        status=429,
        detail=f"You have exceeded the limit of {limit} requests per {window_seconds} seconds",
        instance=f"/errors/{uuid.uuid4().hex[:12]}",
        extensions={
            "limit": limit,
            "window": window_seconds,
            "retry_after": retry_after,
        },
    )


def insufficient_funds_problem(account_id: str, required: float,
                                 available: float,
                                 currency: str = "USD") -> ProblemDetail:
    return ProblemDetail(
        type=ProblemTypes.INSUFFICIENT_FUNDS,
        title="Insufficient Funds",
        status=422,
        detail=(
            f"Account {account_id} has insufficient funds. "
            f"Required: {required:.2f} {currency}, "
            f"Available: {available:.2f} {currency}"
        ),
        instance=f"/errors/{uuid.uuid4().hex[:12]}",
        extensions={
            "account_id": account_id,
            "required": required,
            "available": available,
            "currency": currency,
        },
    )


def internal_problem(correlation_id: str = None) -> ProblemDetail:
    """For unexpected errors -- never expose internal details."""
    cid = correlation_id or uuid.uuid4().hex[:12]
    return ProblemDetail(
        type=ProblemTypes.GENERIC,
        title="Internal Server Error",
        status=500,
        detail=f"An unexpected error occurred. Reference: {cid}",
        instance=f"/errors/{cid}",
        extensions={"correlation_id": cid},
    )


# ============================================================
# FRAMEWORK INTEGRATION (FastAPI)
# ============================================================

# from fastapi import FastAPI, Request
# from fastapi.responses import JSONResponse
#
# app = FastAPI()
#
# class ProblemException(Exception):
#     def __init__(self, problem: ProblemDetail):
#         self.problem = problem
#
# @app.exception_handler(ProblemException)
# async def problem_handler(request: Request, exc: ProblemException):
#     return JSONResponse(
#         status_code=exc.problem.status,
#         content=exc.problem.to_dict(),
#         media_type=exc.problem.content_type,  # application/problem+json
#         headers={"X-Request-ID": exc.problem.instance.split("/")[-1]},
#     )
#
# @app.exception_handler(Exception)
# async def generic_error_handler(request: Request, exc: Exception):
#     # Log the real error server-side
#     import logging
#     logging.error(f"Unhandled exception: {exc}", exc_info=True)
#     # Return safe problem detail to client
#     problem = internal_problem()
#     return JSONResponse(
#         status_code=500,
#         content=problem.to_dict(),
#         media_type=problem.content_type,
#     )
#
# @app.post("/transfer")
# async def transfer(body: dict):
#     if body["amount"] > get_balance(body["from_account"]):
#         raise ProblemException(
#             insufficient_funds_problem(
#                 account_id=body["from_account"],
#                 required=body["amount"],
#                 available=get_balance(body["from_account"]),
#             )
#         )


# ============================================================
# EXAMPLE OUTPUTS
# ============================================================

# Business logic error with extension members:
p = insufficient_funds_problem("acct-123", 150.00, 42.50)
print(p.to_json())
# {
#   "type": "https://api.example.com/problems/insufficient-funds",
#   "title": "Insufficient Funds",
#   "status": 422,
#   "detail": "Account acct-123 has insufficient funds. Required: 150.00 USD, Available: 42.50 USD",
#   "instance": "/errors/a1b2c3d4e5f6",
#   "account_id": "acct-123",
#   "required": 150.0,
#   "available": 42.5,
#   "currency": "USD"
# }

# Rate limit error with retry-after:
p = rate_limit_problem(100, 60, retry_after=23)
print(p.to_json())
# {
#   "type": "https://api.example.com/problems/rate-limited",
#   "title": "Rate Limit Exceeded",
#   "status": 429,
#   "detail": "You have exceeded the limit of 100 requests per 60 seconds",
#   "instance": "/errors/f6e5d4c3b2a1",
#   "limit": 100,
#   "window": 60,
#   "retry_after": 23
# }
```

**RFC 7807 key rules:**

1. **Content-Type must be `application/problem+json`** -- this tells clients to parse the body as a problem detail
2. **`type` should be a dereferenceable URI** -- ideally a link to your API docs explaining this error type
3. **`title` is generic, `detail` is specific** -- title stays the same for all instances of this error type; detail describes this particular occurrence
4. **`instance` is a URI for this occurrence** -- useful for log correlation and support tickets
5. **Extension members are top-level** -- do NOT nest them under a "data" or "meta" key; the spec says they go at the root
6. **Use `about:blank` for generic HTTP errors** -- the spec says if you have no specific type URI, use `about:blank` and set `title` to the HTTP status phrase''',
    ),
    (
        "thinking/error-handling",
        r'''How do I handle error localization in my API? I need to return error messages in different languages based on the user's locale, but I also need the errors to be machine-readable.''',
        r'''<think>
Error localization requires separating:
1. Machine-readable error codes (never localized)
2. Human-readable messages (localized per user's locale)
3. Accept-Language header parsing
4. Translation storage and lookup
5. Fallback language handling

The key insight: error codes stay in English, messages get translated.
Parameters in messages need placeholder substitution.
</think>

Error localization separates machine-readable codes from human-readable messages. The code is always the same; only the message changes per locale. Here is how to implement it:

```python
import re
from dataclasses import dataclass, field
from typing import Any, Optional


# ============================================================
# TRANSLATION REGISTRY
# ============================================================

class ErrorTranslations:
    """Stores error message translations with parameter substitution.

    Message templates use {param_name} placeholders that get
    filled with context-specific values.
    """

    def __init__(self):
        # Structure: {locale: {error_code: message_template}}
        self._translations: dict[str, dict[str, str]] = {}
        self._default_locale = "en"

    def add(self, locale: str, code: str, template: str):
        self._translations.setdefault(locale, {})[code] = template

    def get(self, code: str, locale: str,
            params: dict = None) -> str:
        """Get a localized error message.

        Falls back: requested locale -> default locale -> raw code.
        """
        # Try requested locale
        template = (
            self._translations.get(locale, {}).get(code)
            or self._translations.get(self._default_locale, {}).get(code)
            or code  # Ultimate fallback: just return the code
        )

        # Substitute parameters
        if params:
            try:
                return template.format(**params)
            except (KeyError, IndexError):
                return template
        return template

    def load_from_dict(self, locale: str, translations: dict[str, str]):
        """Bulk load translations for a locale."""
        for code, template in translations.items():
            self.add(locale, code, template)


# ============================================================
# INITIALIZE TRANSLATIONS
# ============================================================

translations = ErrorTranslations()

# English (default)
translations.load_from_dict("en", {
    "VALIDATION.REQUIRED":
        "The field '{field}' is required",
    "VALIDATION.MIN_LENGTH":
        "'{field}' must be at least {min} characters long",
    "VALIDATION.MAX_LENGTH":
        "'{field}' must be at most {max} characters long",
    "VALIDATION.INVALID_EMAIL":
        "'{value}' is not a valid email address",
    "VALIDATION.OUT_OF_RANGE":
        "'{field}' must be between {min} and {max}",
    "AUTH.TOKEN_EXPIRED":
        "Your session has expired. Please sign in again.",
    "AUTH.INVALID_CREDENTIALS":
        "The email or password you entered is incorrect.",
    "AUTHZ.FORBIDDEN":
        "You do not have permission to {action}",
    "NOT_FOUND.RESOURCE":
        "The {resource_type} you requested could not be found",
    "RATE_LIMIT.EXCEEDED":
        "Too many requests. Please wait {retry_after} seconds.",
    "PAYMENT.INSUFFICIENT_FUNDS":
        "Insufficient funds. You need {required} {currency} but only have {available} {currency}.",
    "ORDER.NOT_CANCELLABLE":
        "This order cannot be cancelled because it is already {status}",
})

# Spanish
translations.load_from_dict("es", {
    "VALIDATION.REQUIRED":
        "El campo '{field}' es obligatorio",
    "VALIDATION.MIN_LENGTH":
        "'{field}' debe tener al menos {min} caracteres",
    "VALIDATION.MAX_LENGTH":
        "'{field}' debe tener como maximo {max} caracteres",
    "VALIDATION.INVALID_EMAIL":
        "'{value}' no es una direccion de correo valida",
    "VALIDATION.OUT_OF_RANGE":
        "'{field}' debe estar entre {min} y {max}",
    "AUTH.TOKEN_EXPIRED":
        "Su sesion ha expirado. Por favor, inicie sesion de nuevo.",
    "AUTH.INVALID_CREDENTIALS":
        "El correo o la contrasena que ingreso es incorrecto.",
    "AUTHZ.FORBIDDEN":
        "No tiene permiso para {action}",
    "NOT_FOUND.RESOURCE":
        "No se encontro el {resource_type} solicitado",
    "RATE_LIMIT.EXCEEDED":
        "Demasiadas solicitudes. Espere {retry_after} segundos.",
    "PAYMENT.INSUFFICIENT_FUNDS":
        "Fondos insuficientes. Necesita {required} {currency} pero solo tiene {available} {currency}.",
    "ORDER.NOT_CANCELLABLE":
        "Este pedido no se puede cancelar porque ya esta {status}",
})

# Japanese
translations.load_from_dict("ja", {
    "VALIDATION.REQUIRED":
        "'{field}' wa hissu desu",
    "VALIDATION.INVALID_EMAIL":
        "'{value}' wa yuukou na meeru adoresu dewa arimasen",
    "AUTH.TOKEN_EXPIRED":
        "Sesshon ga kiremashita. Mou ichido roguin shite kudasai.",
    "NOT_FOUND.RESOURCE":
        "Goshitei no {resource_type} wa mitsukarimasen deshita",
    "RATE_LIMIT.EXCEEDED":
        "Rikuesuto ga oosugimasu. {retry_after} byou omachi kudasai.",
})


# ============================================================
# LOCALE DETECTION
# ============================================================

def parse_accept_language(header: str) -> list[str]:
    """Parse Accept-Language header into ordered list of locales.

    Example: "es-MX,es;q=0.9,en;q=0.8" -> ["es-MX", "es", "en"]
    """
    if not header:
        return ["en"]

    locales = []
    for part in header.split(","):
        part = part.strip()
        if ";q=" in part:
            lang, q = part.split(";q=")
            try:
                quality = float(q)
            except ValueError:
                quality = 0.0
        else:
            lang = part
            quality = 1.0
        locales.append((lang.strip(), quality))

    # Sort by quality descending
    locales.sort(key=lambda x: x[1], reverse=True)
    return [lang for lang, _ in locales]


def resolve_locale(accept_header: str,
                    supported: set[str] = None) -> str:
    """Find the best matching locale from the Accept-Language header.

    Tries exact match first, then language-only match.
    """
    if supported is None:
        supported = {"en", "es", "ja"}

    for locale in parse_accept_language(accept_header):
        # Exact match
        if locale in supported:
            return locale
        # Language-only match (e.g., "es-MX" -> "es")
        lang = locale.split("-")[0]
        if lang in supported:
            return lang

    return "en"  # Default fallback


# ============================================================
# LOCALIZED ERROR RESPONSE
# ============================================================

@dataclass
class LocalizedError:
    code: str                    # Machine-readable, never changes
    message: str                 # Human-readable, localized
    field: Optional[str] = None
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = {
            "code": self.code,
            "message": self.message,
        }
        if self.field:
            result["field"] = self.field
        return result


def make_error(code: str, locale: str,
               params: dict = None,
               field_name: str = None) -> LocalizedError:
    """Create a localized error."""
    message = translations.get(code, locale, params or {})
    return LocalizedError(
        code=code,
        message=message,
        field=field_name,
        params=params or {},
    )


# ============================================================
# USAGE EXAMPLES
# ============================================================

# English user
locale_en = resolve_locale("en-US,en;q=0.9")
err = make_error("VALIDATION.REQUIRED", locale_en,
                  {"field": "email"}, field_name="email")
print(err.to_dict())
# {"code": "VALIDATION.REQUIRED", "message": "The field 'email' is required", "field": "email"}

# Spanish user
locale_es = resolve_locale("es-MX,es;q=0.9,en;q=0.8")
err = make_error("VALIDATION.REQUIRED", locale_es,
                  {"field": "email"}, field_name="email")
print(err.to_dict())
# {"code": "VALIDATION.REQUIRED", "message": "El campo 'email' es obligatorio", "field": "email"}

# Business error with parameters
err = make_error("PAYMENT.INSUFFICIENT_FUNDS", "es",
                  {"required": "150.00", "available": "42.50", "currency": "USD"})
print(err.to_dict())
# {"code": "PAYMENT.INSUFFICIENT_FUNDS",
#  "message": "Fondos insuficientes. Necesita 150.00 USD pero solo tiene 42.50 USD."}

# Fallback: Japanese user requests a message not translated to Japanese
err = make_error("PAYMENT.INSUFFICIENT_FUNDS", "ja",
                  {"required": "150.00", "available": "42.50", "currency": "JPY"})
print(err.to_dict())
# Falls back to English since ja translation is missing for this code
```

**Key design decisions:**

1. **Error codes are never localized**: `VALIDATION.REQUIRED` is the same in every language -- clients switch on this, not the message text
2. **Parameterized templates**: `{field}`, `{min}`, `{max}` get substituted with actual values, so translators only write one template per error
3. **Locale resolution with fallback**: `es-MX` falls back to `es`, which falls back to `en` -- you do not need a translation for every regional variant
4. **Accept-Language header parsing**: follows HTTP spec quality values (`q=0.9`) for proper priority ordering
5. **Graceful degradation**: if a translation is missing, fall back to default locale rather than crashing''',
    ),
    (
        "thinking/error-handling",
        r'''How should my API handle rate limiting errors? I want to return useful information so the client knows when to retry, and I want to support different rate limit tiers.''',
        r'''<think>
Rate limiting error responses need:
1. Standard HTTP 429 status code
2. Retry-After header (required by HTTP spec for 429)
3. Rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset)
4. Body with machine-readable details (limit, window, remaining, reset time)
5. Support for multiple rate limit tiers (per-user, per-endpoint, global)

I should show both the response format and the server-side implementation
for tracking and enforcing multiple rate limit tiers.
</think>

Rate limit errors need both standard HTTP headers and a detailed response body so clients can implement proper backoff. Here is a complete implementation:

```python
import time
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
from threading import Lock


# ============================================================
# RATE LIMIT CONFIGURATION
# ============================================================

@dataclass
class RateLimitTier:
    """Defines a rate limit tier."""
    name: str
    requests_per_window: int
    window_seconds: int
    description: str = ""

    @property
    def requests_per_second(self) -> float:
        return self.requests_per_window / self.window_seconds


# Define tiers for different API access levels
TIERS = {
    "free": RateLimitTier("free", 60, 60, "60 requests per minute"),
    "basic": RateLimitTier("basic", 600, 60, "600 requests per minute"),
    "pro": RateLimitTier("pro", 6000, 60, "6000 requests per minute"),
    "enterprise": RateLimitTier("enterprise", 60000, 60, "60000 requests per minute"),
}

# Per-endpoint overrides (some endpoints are more expensive)
ENDPOINT_LIMITS = {
    "/api/search": RateLimitTier("search", 10, 60, "10 searches per minute"),
    "/api/export": RateLimitTier("export", 5, 3600, "5 exports per hour"),
    "/api/upload": RateLimitTier("upload", 20, 3600, "20 uploads per hour"),
}


# ============================================================
# SLIDING WINDOW RATE LIMITER
# ============================================================

class SlidingWindowLimiter:
    """Token bucket rate limiter with sliding window."""

    def __init__(self):
        self._buckets: dict[str, dict] = {}
        self._lock = Lock()

    def _get_bucket(self, key: str, tier: RateLimitTier) -> dict:
        now = time.time()
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = {
                    "tokens": tier.requests_per_window,
                    "last_refill": now,
                    "tier": tier,
                }
            bucket = self._buckets[key]

            # Refill tokens based on elapsed time
            elapsed = now - bucket["last_refill"]
            refill = elapsed * tier.requests_per_second
            bucket["tokens"] = min(
                tier.requests_per_window,
                bucket["tokens"] + refill,
            )
            bucket["last_refill"] = now

            return bucket

    def check(self, key: str, tier: RateLimitTier,
              cost: int = 1) -> "RateLimitResult":
        """Check if a request is allowed and consume tokens if so."""
        bucket = self._get_bucket(key, tier)
        now = time.time()

        with self._lock:
            remaining = int(bucket["tokens"])
            if bucket["tokens"] >= cost:
                bucket["tokens"] -= cost
                return RateLimitResult(
                    allowed=True,
                    limit=tier.requests_per_window,
                    remaining=max(0, int(bucket["tokens"])),
                    reset_at=now + tier.window_seconds,
                    retry_after=0,
                    tier_name=tier.name,
                    window_seconds=tier.window_seconds,
                )
            else:
                # Calculate when enough tokens will be available
                tokens_needed = cost - bucket["tokens"]
                wait_seconds = tokens_needed / tier.requests_per_second
                return RateLimitResult(
                    allowed=False,
                    limit=tier.requests_per_window,
                    remaining=0,
                    reset_at=now + wait_seconds,
                    retry_after=int(wait_seconds) + 1,
                    tier_name=tier.name,
                    window_seconds=tier.window_seconds,
                )


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_at: float          # Unix timestamp
    retry_after: int         # Seconds to wait
    tier_name: str
    window_seconds: int

    def headers(self) -> dict[str, str]:
        """Generate standard rate limit headers."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(int(self.reset_at)),
            "X-RateLimit-Policy": f"{self.limit};w={self.window_seconds}",
        }
        if not self.allowed:
            headers["Retry-After"] = str(self.retry_after)
        return headers

    def error_body(self) -> dict:
        """Generate RFC 7807 problem detail for rate limit errors."""
        return {
            "type": "https://api.example.com/problems/rate-limited",
            "title": "Rate Limit Exceeded",
            "status": 429,
            "detail": (
                f"You have exceeded the rate limit of {self.limit} "
                f"requests per {self.window_seconds} seconds for the "
                f"'{self.tier_name}' tier. Please retry after "
                f"{self.retry_after} seconds."
            ),
            "limit": self.limit,
            "remaining": self.remaining,
            "reset": int(self.reset_at),
            "retry_after": self.retry_after,
            "tier": self.tier_name,
        }


# ============================================================
# MULTI-TIER RATE LIMIT MIDDLEWARE
# ============================================================

class RateLimitMiddleware:
    """Applies multiple rate limit tiers per request.

    A request must pass ALL applicable limits:
    1. Global tier limit (based on user's plan)
    2. Per-endpoint limit (if the endpoint has one)
    3. Per-IP limit (for unauthenticated requests)
    """

    def __init__(self):
        self._limiter = SlidingWindowLimiter()

    def check_request(self, user_id: str, user_tier: str,
                       endpoint: str, client_ip: str) -> RateLimitResult:
        """Check all applicable rate limits for a request.

        Returns the most restrictive result.
        """
        results = []

        # Check 1: User tier limit
        tier = TIERS.get(user_tier, TIERS["free"])
        user_result = self._limiter.check(
            f"user:{user_id}", tier
        )
        results.append(user_result)

        # Check 2: Per-endpoint limit (if configured)
        if endpoint in ENDPOINT_LIMITS:
            endpoint_tier = ENDPOINT_LIMITS[endpoint]
            endpoint_result = self._limiter.check(
                f"endpoint:{user_id}:{endpoint}", endpoint_tier
            )
            results.append(endpoint_result)

        # Check 3: Per-IP limit (defense against abuse)
        ip_tier = RateLimitTier("ip", 1000, 60, "1000 per minute per IP")
        ip_result = self._limiter.check(f"ip:{client_ip}", ip_tier)
        results.append(ip_result)

        # Return the most restrictive (first denied, or least remaining)
        denied = [r for r in results if not r.allowed]
        if denied:
            # Return the one with the longest retry_after
            return max(denied, key=lambda r: r.retry_after)

        # All passed -- return the one with fewest remaining
        return min(results, key=lambda r: r.remaining)


# ============================================================
# USAGE EXAMPLE
# ============================================================

middleware = RateLimitMiddleware()

# Simulate a free-tier user making requests
for i in range(65):
    result = middleware.check_request(
        user_id="user-42",
        user_tier="free",
        endpoint="/api/data",
        client_ip="192.168.1.100",
    )

    if not result.allowed:
        print(f"Request {i+1}: BLOCKED")
        print(f"Headers: {json.dumps(result.headers(), indent=2)}")
        print(f"Body: {json.dumps(result.error_body(), indent=2)}")
        break

# Example blocked response:
# Headers:
# {
#   "X-RateLimit-Limit": "60",
#   "X-RateLimit-Remaining": "0",
#   "X-RateLimit-Reset": "1705312260",
#   "X-RateLimit-Policy": "60;w=60",
#   "Retry-After": "1"
# }
#
# Body:
# {
#   "type": "https://api.example.com/problems/rate-limited",
#   "title": "Rate Limit Exceeded",
#   "status": 429,
#   "detail": "You have exceeded the rate limit of 60 requests per 60 seconds
#              for the 'free' tier. Please retry after 1 seconds.",
#   "limit": 60,
#   "remaining": 0,
#   "reset": 1705312260,
#   "retry_after": 1,
#   "tier": "free"
# }
```

**Rate limit response best practices:**

1. **Always include `Retry-After` header** on 429 responses -- it is required by HTTP spec and most client libraries use it for automatic retry
2. **Include `X-RateLimit-*` headers on ALL responses** (not just 429) so clients can proactively throttle before hitting the limit
3. **Provide the tier name** so users know which limit they hit and can consider upgrading
4. **Per-endpoint limits** protect expensive operations (search, export) independently of the global rate
5. **Layer multiple limits**: user tier + endpoint + IP prevents both legitimate overuse and abuse''',
    ),
    (
        "thinking/error-handling",
        r'''How do I design API responses for partial success -- when a batch request succeeds for some items and fails for others? I do not want to return 200 (misleading) or 500 (too broad).''',
        r'''<think>
Partial success is a common problem with batch APIs. Options:
1. HTTP 207 Multi-Status (WebDAV, but widely used)
2. HTTP 200 with per-item status in the body
3. HTTP 202 Accepted with async results

Key design decisions:
- Each item needs its own status
- The overall response needs a summary
- Clients need to know which items succeeded and which failed
- Failed items need enough detail to retry or fix

I should show multiple approaches with their trade-offs.
</think>

Partial success in batch APIs requires per-item status reporting. Here are the proven patterns:

```python
import json
import uuid
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


# ============================================================
# APPROACH 1: HTTP 207 MULTI-STATUS
# ============================================================

class ItemStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class BatchItemResult:
    """Result for a single item in a batch request."""
    index: int                   # Position in the original request
    item_id: str                 # Client-provided or server-generated ID
    status: ItemStatus
    http_status: int             # Per-item HTTP status code
    data: Optional[dict] = None  # Result data on success
    error: Optional[dict] = None # Error details on failure

    def to_dict(self) -> dict:
        result = {
            "index": self.index,
            "id": self.item_id,
            "status": self.status.value,
            "http_status": self.http_status,
        }
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        return result


@dataclass
class BatchResponse:
    """Complete batch operation response."""
    results: list[BatchItemResult] = field(default_factory=list)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.status == ItemStatus.SUCCESS)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == ItemStatus.FAILED)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == ItemStatus.SKIPPED)

    @property
    def http_status(self) -> int:
        """Choose the overall HTTP status code.

        - All succeeded -> 200
        - All failed -> 400 (or most common error status)
        - Mixed -> 207 Multi-Status
        """
        if self.failed == 0:
            return 200
        if self.succeeded == 0:
            # Return the most common error status
            statuses = [r.http_status for r in self.results if r.status == ItemStatus.FAILED]
            return max(set(statuses), key=statuses.count)
        return 207  # Multi-Status

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "summary": {
                "total": self.total,
                "succeeded": self.succeeded,
                "failed": self.failed,
                "skipped": self.skipped,
            },
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ============================================================
# BATCH PROCESSOR
# ============================================================

class BatchProcessor:
    """Process batch requests with per-item error handling."""

    def __init__(self, max_batch_size: int = 100):
        self.max_batch_size = max_batch_size

    def process(self, items: list[dict],
                handler) -> BatchResponse:
        """Process a list of items, collecting per-item results.

        The handler function receives (item, index) and returns
        a dict on success or raises an exception on failure.
        """
        response = BatchResponse()

        if len(items) > self.max_batch_size:
            # Reject the entire batch if too large
            for i, item in enumerate(items):
                response.results.append(BatchItemResult(
                    index=i,
                    item_id=item.get("id", f"item-{i}"),
                    status=ItemStatus.FAILED,
                    http_status=400,
                    error={
                        "code": "BATCH.TOO_LARGE",
                        "message": f"Batch size {len(items)} exceeds maximum {self.max_batch_size}",
                    },
                ))
            return response

        for i, item in enumerate(items):
            item_id = item.get("id", f"item-{i}")
            try:
                result_data = handler(item, i)
                response.results.append(BatchItemResult(
                    index=i,
                    item_id=item_id,
                    status=ItemStatus.SUCCESS,
                    http_status=200,
                    data=result_data,
                ))
            except ValidationError as exc:
                response.results.append(BatchItemResult(
                    index=i,
                    item_id=item_id,
                    status=ItemStatus.FAILED,
                    http_status=400,
                    error={
                        "code": "VALIDATION_ERROR",
                        "message": str(exc),
                        "field": getattr(exc, "field", None),
                    },
                ))
            except NotFoundException as exc:
                response.results.append(BatchItemResult(
                    index=i,
                    item_id=item_id,
                    status=ItemStatus.FAILED,
                    http_status=404,
                    error={
                        "code": "NOT_FOUND",
                        "message": str(exc),
                    },
                ))
            except ConflictError as exc:
                response.results.append(BatchItemResult(
                    index=i,
                    item_id=item_id,
                    status=ItemStatus.FAILED,
                    http_status=409,
                    error={
                        "code": "CONFLICT",
                        "message": str(exc),
                    },
                ))
            except Exception as exc:
                response.results.append(BatchItemResult(
                    index=i,
                    item_id=item_id,
                    status=ItemStatus.FAILED,
                    http_status=500,
                    error={
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred processing this item",
                    },
                ))

        return response


# Custom exceptions for the handler
class ValidationError(Exception):
    def __init__(self, message, field_name=None):
        super().__init__(message)
        self.field = field_name

class NotFoundException(Exception):
    pass

class ConflictError(Exception):
    pass


# ============================================================
# USAGE EXAMPLE
# ============================================================

def create_user(item: dict, index: int) -> dict:
    """Handler that creates a single user."""
    if not item.get("email"):
        raise ValidationError("Email is required", "email")
    if item.get("email") == "exists@example.com":
        raise ConflictError(f"User with email {item['email']} already exists")
    return {"id": f"user-{uuid.uuid4().hex[:8]}", "email": item["email"]}


processor = BatchProcessor(max_batch_size=100)

items = [
    {"id": "req-1", "email": "alice@example.com"},      # Success
    {"id": "req-2", "email": ""},                         # Validation error
    {"id": "req-3", "email": "exists@example.com"},       # Conflict
    {"id": "req-4", "email": "bob@example.com"},          # Success
]

response = processor.process(items, create_user)
print(f"HTTP Status: {response.http_status}")  # 207 (mixed results)
print(response.to_json())

# Output:
# {
#   "request_id": "a1b2c3d4e5f6",
#   "summary": {
#     "total": 4,
#     "succeeded": 2,
#     "failed": 2,
#     "skipped": 0
#   },
#   "results": [
#     {
#       "index": 0, "id": "req-1", "status": "success",
#       "http_status": 200,
#       "data": {"id": "user-abc12345", "email": "alice@example.com"}
#     },
#     {
#       "index": 1, "id": "req-2", "status": "failed",
#       "http_status": 400,
#       "error": {"code": "VALIDATION_ERROR", "message": "Email is required", "field": "email"}
#     },
#     {
#       "index": 2, "id": "req-3", "status": "failed",
#       "http_status": 409,
#       "error": {"code": "CONFLICT", "message": "User with email exists@example.com already exists"}
#     },
#     {
#       "index": 3, "id": "req-4", "status": "success",
#       "http_status": 200,
#       "data": {"id": "user-def67890", "email": "bob@example.com"}
#     }
#   ]
# }
```

**Choosing the overall HTTP status:**

| Scenario | Status | Reason |
|----------|--------|--------|
| All items succeed | 200 | Complete success |
| Some succeed, some fail | 207 | Multi-Status (partial success) |
| All items fail (same error) | 400/422 | Uniform failure |
| All items fail (mixed errors) | 207 | Each item has its own status |
| Batch too large | 400 | Reject the entire batch |

**Design rules:**

1. **Every item gets its own status**: clients must know which items succeeded and which failed
2. **Include the original index**: clients map results back to their request items by position
3. **Client-provided IDs**: let clients include an `id` field per item for their own correlation
4. **Summary block**: `total/succeeded/failed/skipped` counts at the top save clients from counting
5. **Failed items include error details**: enough information to fix and retry just the failed items
6. **Never silently drop items**: if an item was skipped (e.g., duplicate), report it explicitly with status "skipped"''',
    ),
]
