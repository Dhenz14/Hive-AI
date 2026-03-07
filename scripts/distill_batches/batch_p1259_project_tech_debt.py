"""
Real-world project help training pairs - Tackling tech debt
"""

pairs = [
    {
        "instruction": r'''Our Django project has 47 dependencies in requirements.txt and none of them have been updated in 2 years. Some have known CVEs. How do I approach updating them without breaking everything?''',
        "output": r'''<think>
47 dependencies, 2 years stale. This is a common situation. You can't update everything at once -- some packages have breaking changes. The approach is: triage by risk, update in groups, test after each group.
</think>

Don't run `pip install --upgrade -r requirements.txt` -- that's a recipe for a broken afternoon. Do it in layers.

Step 1: Audit what you have:

```bash
# See what's outdated
pip list --outdated --format=columns

# Check for security vulnerabilities
pip install pip-audit
pip-audit
```

Step 2: Categorize dependencies into tiers:

Tier 1 -- Security fixes (do these NOW):
```bash
# pip-audit shows CVEs -- these are non-negotiable
pip-audit --fix --dry-run  # see what it would do
```

Tier 2 -- Framework and ORM (highest breakage risk):
- Django itself
- djangorestframework
- celery
- SQLAlchemy (if used)

Tier 3 -- Utility libraries (usually safe):
- requests, httpx
- Pillow
- python-dateutil
- boto3

Tier 4 -- Dev tools (lowest risk):
- pytest, coverage, flake8, black

Step 3: Pin versions properly. Change your requirements.txt to use compatible release specifiers:

```txt
# requirements.txt -- BEFORE:
Django==2.2.28
djangorestframework==3.11.2
celery==4.4.7
requests==2.25.1

# AFTER (pin major, allow minor/patch):
Django~=4.2.0
djangorestframework~=3.15.0
celery~=5.3.0
requests~=2.31.0
```

Step 4: Update in reverse tier order (safest first):

```bash
# Round 1: Dev tools (if tests break, it's a test config issue, not app breakage)
pip install --upgrade pytest coverage ruff
pytest  # verify

# Round 2: Utility libraries
pip install --upgrade requests boto3 Pillow python-dateutil
pytest  # verify

# Round 3: Framework (read the release notes!)
pip install Django~=4.2.0
python manage.py check  # Django's built-in compatibility check
pytest  # verify, fix deprecation warnings

# Round 4: Security-critical packages
pip-audit --fix
pytest  # verify
```

Step 5: Read changelogs for major version bumps. For Django 2.2 -> 4.2, you MUST step through LTS versions (see Django's upgrade docs). For Celery 4 -> 5, read the migration guide.

Step 6: Lock your dependencies so this doesn't happen again:

```bash
pip install pip-tools
pip-compile requirements.in --output-file requirements.txt
# requirements.in has your direct deps, requirements.txt gets fully pinned
```

Set up Dependabot or Renovate to create PRs for updates weekly. Never let deps go stale for 2 years again.

Budget 1-2 weeks for this if you have good test coverage, 3-4 weeks if you don't.'''
    },
    {
        "instruction": r'''We have a lot of tech debt and limited time. My manager wants me to come up with a plan to address it. We have: no tests, inconsistent code style, a monolithic views.py, raw SQL scattered everywhere, no logging, and hardcoded config values. Where do I start?''',
        "output": r'''Prioritize by blast radius and cost-to-fix. Some of these are quick wins, others are ongoing projects. Here's the order:

Priority 1 -- Hardcoded config values (1-2 days, prevents outages):

This is the most dangerous one. Hardcoded database passwords, API keys, and URLs mean you can't deploy to different environments and secrets are in your git history.

```python
# settings.py
import os

DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
API_KEY = os.environ["PAYMENT_API_KEY"]
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
```

Create a `.env.example` file (no real values) and add `.env` to `.gitignore`. Use python-dotenv or django-environ to load them.

Priority 2 -- Add logging (1 day, saves hours debugging):

```python
# settings.py
LOGGING = {
    "version": 1,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "app.log",
            "maxBytes": 10_000_000,
        },
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING"},
        "myapp": {"handlers": ["console", "file"], "level": "INFO"},
    },
}
```

Add logging to critical paths: payments, auth, data imports.

Priority 3 -- Code style enforcement (half day, prevents style debt from growing):

```bash
pip install ruff
ruff check . --fix  # auto-fix what it can
```

Add to pre-commit hooks so new code is always clean. Don't reformat the entire codebase at once -- it makes git blame useless.

Priority 4 -- Add tests for critical paths only (ongoing, 1-2 tests per week):

Don't aim for 100% coverage. Test the things that would cause the most damage if broken:
- Payment processing
- User registration/login
- Data import/export
- Any endpoint that modifies money or user data

Priority 5 -- Raw SQL cleanup (ongoing, as you touch each file):

Don't migrate all 200 queries at once. Rule: every time you modify a file with raw SQL, convert those queries to ORM. Over months, coverage grows organically.

Priority 6 -- Monolithic views.py (ongoing, extract as needed):

Same strategy: when you add a feature or fix a bug in views.py, extract that section into a service layer. Don't do a big-bang refactor.

Present this to your manager as: "2-3 days of immediate fixes (config, logging, linting), then ongoing improvements as part of regular development." The key selling point: Priorities 1-3 reduce incident frequency, which saves time that funds Priorities 4-6.'''
    },
    {
        "instruction": r'''Our codebase has zero type hints. We're a Python shop with about 50k lines of code across 200 files. I want to add type hints gradually. What's a practical strategy that doesn't require typing everything at once?''',
        "output": r'''<think>
Gradual type hint adoption for a large codebase. The key is: start with the boundaries (function signatures), enforce on new code, and backfill strategically. Don't try to type everything -- focus on where types give the most value.
</think>

Enforce types on new code immediately, backfill strategically. Here's the playbook:

Step 1: Set up mypy in gradual mode (30 minutes):

```bash
pip install mypy
```

```ini
# mypy.ini
[mypy]
python_version = 3.11
warn_return_any = True
warn_unused_configs = True
# Start permissive -- don't check existing code
ignore_missing_imports = True

# Only enforce on specific modules (grow this list over time)
[mypy-myapp.services.*]
disallow_untyped_defs = True

[mypy-myapp.models.*]
disallow_untyped_defs = True
```

Step 2: Add types to function signatures at boundaries first. These give the most value:

```python
# Public API functions -- callers benefit from knowing types
def create_order(user_id: int, items: list[dict], coupon: str | None = None) -> Order:
    ...

# Don't bother typing internal variables unless it helps readability
def process_batch(records: list[dict]) -> tuple[int, int]:
    success = 0  # mypy infers int, no annotation needed
    failed = 0
    for r in records:
        ...
    return success, failed
```

Step 3: Type your models and data classes first -- they're the foundation everything else depends on:

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class OrderSummary:
    order_id: int
    total: float
    status: str
    created_at: datetime
    items: list[dict[str, Any]]
```

Step 4: Add a pre-commit hook that enforces types on changed files:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/mirrors-mypy
    hooks:
      - id: mypy
        args: [--strict]
        # Only check files that are already typed
        files: ^(myapp/services/|myapp/models/)
```

Step 5: Backfill priority order:
1. Models and data classes (foundation)
2. Service layer functions (business logic)
3. API endpoints / view functions (interface)
4. Utility functions
5. Tests (lowest priority -- types in tests add less value)

Step 6: Use `reveal_type()` and pyright to find type issues interactively:

```python
# Temporarily add this to understand what mypy infers
result = some_function()
reveal_type(result)  # mypy tells you what type it sees
```

Practical tips:
- Use `from __future__ import annotations` at the top of every file you touch (allows forward references and cleaner syntax)
- Start with `Any` for complex types, refine later
- Don't type private helper functions unless they're complex
- Use TypeAlias for repeated complex types:

```python
from typing import TypeAlias

OrderData: TypeAlias = dict[str, str | int | list[dict[str, Any]]]
```

Expect 3-6 months for a 50k-line codebase to reach reasonable coverage, at the pace of "type every file you touch."'''
    },
    {
        "instruction": r'''We have a Django app where every view function does its own authentication check, database queries, error handling, and response formatting. There's massive code duplication -- the same 10 lines of auth checking are copy-pasted in 40 views. How do I DRY this up?''',
        "output": r'''Layer by layer. Each type of duplication has a different solution.

1. Auth checking duplication -- use decorators or DRF permissions:

```python
# BEFORE -- in every single view:
def order_detail(request, order_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)
    if not request.user.has_perm("orders.view_order"):
        return JsonResponse({"error": "Forbidden"}, status=403)
    order = Order.objects.filter(id=order_id, company=request.user.company).first()
    if not order:
        return JsonResponse({"error": "Not found"}, status=404)
    # ... actual logic ...

# AFTER -- decorator handles it:
from functools import wraps

def require_auth(perm=None):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({"error": "Not authenticated"}, status=401)
            if perm and not request.user.has_perm(perm):
                return JsonResponse({"error": "Forbidden"}, status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

@require_auth(perm="orders.view_order")
def order_detail(request, order_id):
    # Auth is already handled
    ...
```

2. "Get object or 404" pattern -- use a helper:

```python
# helpers.py
def get_company_object_or_404(model, user, **kwargs):
    obj = model.objects.filter(company=user.company, **kwargs).first()
    if not obj:
        raise Http404
    return obj

# Usage in views:
@require_auth(perm="orders.view_order")
def order_detail(request, order_id):
    order = get_company_object_or_404(Order, request.user, id=order_id)
    return JsonResponse(serialize_order(order))
```

3. Response formatting -- use a standard response helper:

```python
# helpers.py
def api_response(data=None, error=None, status=200):
    if error:
        return JsonResponse({"success": False, "error": error}, status=status)
    return JsonResponse({"success": True, "data": data}, status=status)

# Usage:
return api_response(data={"order": serialize_order(order)})
return api_response(error="Order not found", status=404)
```

4. Error handling -- use middleware instead of try/except in every view:

```python
# middleware.py
class APIErrorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, PermissionError):
            return api_response(error=str(exception), status=403)
        if isinstance(exception, ValueError):
            return api_response(error=str(exception), status=400)
        # Let 500s propagate to Django's default handler
        return None
```

Now a view goes from 25 lines to 5:

```python
# BEFORE: 25 lines of boilerplate + logic
# AFTER:
@require_auth(perm="orders.view_order")
def order_detail(request, order_id):
    order = get_company_object_or_404(Order, request.user, id=order_id)
    return api_response(data=serialize_order(order))
```

Migration strategy: create the helpers first, then convert 3-5 views per day. Each conversion is a small, safe change. After a few weeks, all 40 views are clean.'''
    },
    {
        "instruction": r'''We have a growing Python monolith (100k lines) and people keep talking about breaking it into microservices. Is it actually the right call? We're a team of 6 developers and the app serves about 10k requests per minute.''',
        "output": r'''<think>
6 developers, 10k rpm, 100k lines. Let me think about whether microservices make sense here.

Arguments against microservices for this team:
- 6 developers is too small to operate multiple services (each service needs on-call, deployment, monitoring)
- 10k rpm is easily handled by a well-structured monolith
- The operational overhead of microservices (service mesh, distributed tracing, API contracts) would slow them down

Arguments for staying monolith:
- Simpler deployment
- Simpler debugging (one process, one log stream)
- No network latency between components
- Easier to refactor

The right move is usually: clean up the monolith's internal structure first.
</think>

Almost certainly no. Here's why:

The microservices tax for a team of 6:
- Each service needs its own repo, CI/CD, monitoring, and on-call
- Distributed debugging is 10x harder than monolith debugging
- Network calls between services add latency and failure modes
- Data consistency across services requires sagas or event sourcing
- You need infrastructure: service discovery, API gateway, distributed tracing

That's easily 30-40% of your engineering time on infrastructure instead of features.

What you actually need is a well-structured monolith. The problems people usually blame on "monolith" are actually caused by poor internal structure:

```
BAD monolith (what you probably have):
  app/
    models.py      # 3000 lines, everything mixed
    views.py       # 5000 lines
    utils.py       # 2000 lines of random helpers

GOOD monolith (what you should build):
  app/
    orders/
      models.py
      services.py   # business logic
      api.py         # endpoints
      tests/
    payments/
      models.py
      services.py
      api.py
      tests/
    users/
      models.py
      services.py
      api.py
      tests/
    shared/
      email.py
      permissions.py
```

Rules for internal boundaries:
1. Each module owns its models and data
2. Modules communicate through service functions, not by importing each other's models directly
3. No circular dependencies between modules

```python
# WRONG -- payments directly queries orders table
from orders.models import Order
orders = Order.objects.filter(user=user)

# RIGHT -- payments asks orders service
from orders.services import get_user_orders
orders = get_user_orders(user_id=user.id)
```

This gives you the organizational benefits of microservices (clear boundaries, independent teams, isolated logic) without the operational cost.

When microservices actually make sense:
- 30+ developers (multiple teams need independent deployment)
- Different scaling requirements (one service needs GPUs, another needs high throughput)
- Different tech stacks (ML team uses Python, frontend team uses Node)
- Regulatory isolation (PCI compliance for payments)

At 6 developers and 10k rpm, a single Django/FastAPI instance with good structure handles your load and keeps your team productive. Revisit microservices if you grow to 20+ engineers and have clear team boundaries.'''
    },
]
