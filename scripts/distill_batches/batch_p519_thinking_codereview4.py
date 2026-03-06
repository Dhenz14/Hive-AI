"""Phase 1E: Foundation Thinking — Code Review & Refactoring (Part 4/4)
API design review, data flow analysis, complexity reduction, refactoring strategies."""

PAIRS = [
    (
        "thinking/review-api-design-consistency",
        "Review our REST API design — different team members built different endpoints:\n\n```\nGET    /api/users                    → {\"users\": [...]}\nGET    /api/users/123                → {\"user\": {...}}\nPOST   /api/users                    → {\"id\": 123, \"name\": \"...\"}\nGET    /api/orders?userId=123        → [{...}, {...}]\nGET    /api/order/456                → {\"data\": {...}, \"status\": \"ok\"}\nPOST   /api/createOrder              → {\"success\": true, \"orderId\": 456}\nDELETE /api/users/123/delete         → {\"message\": \"Deleted\"}\nPATCH  /api/users/123                → {\"updated\": true}\nGET    /api/getProductsByCategory/5  → {\"products\": [...], \"count\": 10}\nPOST   /api/products/search          → {\"results\": [...]}\n```\n\nWhat's wrong and how do we standardize?",
        r'''<think>
Let me catalog the inconsistencies:

1. **Response envelope**: Some use `{"users": [...]}`, some return bare arrays `[{...}]`, some use `{"data": {...}}`, some return the object directly
2. **Naming**: Mix of plural (`/users`) and singular (`/order`). Verbs in URLs (`/createOrder`, `/getProductsByCategory`, `/delete`)
3. **URL structure**: `/api/users/123/delete` — DELETE method already implies deletion, `/delete` is redundant
4. **POST for queries**: `/api/products/search` is a query, not a creation — should be GET with query params (unless the search body is complex)
5. **camelCase vs snake_case**: `userId` vs could be `user_id`
6. **Response inconsistency**: Success responses use different structures everywhere

Fix: establish a consistent API style guide.
</think>

Your API has 7 types of inconsistency. Here's the standardized version:

## Issues Found

| Problem | Examples |
|---------|----------|
| Mixed singular/plural | `/users` vs `/order` |
| Verbs in URLs | `/createOrder`, `/getProductsByCategory`, `/delete` |
| Inconsistent response envelopes | `{"users": [...]}` vs `[{...}]` vs `{"data": {...}}` |
| Redundant path segments | `DELETE /users/123/delete` |
| POST for reads | `POST /products/search` |
| Mixed success indicators | `{"success": true}` vs `{"status": "ok"}` vs bare data |
| No pagination metadata | Lists return bare arrays |

## Standardized API

```
# Consistent patterns:
# - Always plural nouns, never verbs
# - Consistent envelope: {data, meta, errors}
# - HTTP methods convey the action
# - Query params for filtering

GET    /api/v1/users                     → {"data": [...], "meta": {"total": 50, "page": 1}}
GET    /api/v1/users/123                 → {"data": {"id": 123, ...}}
POST   /api/v1/users                     → {"data": {"id": 123, ...}}  (201 Created)
PATCH  /api/v1/users/123                 → {"data": {"id": 123, ...}}
DELETE /api/v1/users/123                 → (204 No Content)

GET    /api/v1/orders?user_id=123        → {"data": [...], "meta": {...}}
GET    /api/v1/orders/456                → {"data": {"id": 456, ...}}
POST   /api/v1/orders                    → {"data": {"id": 456, ...}}  (201 Created)

GET    /api/v1/products?category_id=5    → {"data": [...], "meta": {...}}
GET    /api/v1/products?q=search_term    → {"data": [...], "meta": {...}}
```

## Standard Response Envelope

```json
// Success (single)
{"data": {"id": 123, "name": "Alice", "email": "alice@example.com"}}

// Success (list)
{"data": [{...}, {...}], "meta": {"total": 100, "page": 1, "per_page": 20}}

// Error
{"errors": [{"code": "validation_error", "field": "email", "message": "Invalid email"}]}
```

## API Style Guide (enforce in PR reviews)
1. **Nouns, not verbs** — the HTTP method is the verb
2. **Always plural** — `/users`, `/orders`, `/products`
3. **Consistent envelope** — always `{data}` for success, `{errors}` for failure
4. **snake_case** for JSON keys and query params
5. **HTTP status codes** convey success/failure, not response body fields
6. **Filter via query params**, not URL segments or POST bodies'''
    ),
    (
        "thinking/review-cyclomatic-complexity",
        "This function has been flagged by our linter for high cyclomatic complexity. How do I simplify it?\n\n```python\ndef calculate_price(product, user, quantity, coupon=None, is_wholesale=False):\n    base_price = product.price\n    \n    # Volume discounts\n    if quantity >= 1000:\n        base_price *= 0.7\n    elif quantity >= 500:\n        base_price *= 0.8\n    elif quantity >= 100:\n        base_price *= 0.85\n    elif quantity >= 50:\n        base_price *= 0.9\n    elif quantity >= 10:\n        base_price *= 0.95\n    \n    # User tier discounts\n    if user.tier == 'platinum':\n        base_price *= 0.9\n    elif user.tier == 'gold':\n        base_price *= 0.93\n    elif user.tier == 'silver':\n        base_price *= 0.95\n    elif user.tier == 'bronze':\n        base_price *= 0.97\n    \n    # Wholesale override\n    if is_wholesale:\n        if user.is_verified_wholesaler:\n            base_price *= 0.75\n        else:\n            raise PermissionError('Not a verified wholesaler')\n    \n    # Coupon\n    if coupon:\n        if coupon.is_expired():\n            pass  # Ignore expired\n        elif coupon.type == 'percent':\n            if coupon.min_quantity and quantity < coupon.min_quantity:\n                pass  # Doesn't meet minimum\n            else:\n                base_price *= (1 - coupon.value / 100)\n        elif coupon.type == 'fixed':\n            base_price -= coupon.value\n            if base_price < 0:\n                base_price = 0\n    \n    # Seasonal\n    now = datetime.now()\n    if now.month in (11, 12) and product.category == 'holiday':\n        base_price *= 0.85\n    elif now.month in (6, 7, 8) and product.category == 'summer':\n        base_price *= 0.8\n    \n    total = base_price * quantity\n    \n    # Tax\n    if user.state in ('OR', 'MT', 'NH', 'DE', 'AK'):\n        tax_rate = 0\n    elif user.state == 'CA':\n        tax_rate = 0.0725\n    elif user.state == 'NY':\n        tax_rate = 0.08\n    else:\n        tax_rate = 0.06  # Default\n    \n    total *= (1 + tax_rate)\n    \n    return round(total, 2)\n```",
        r'''<think>
High cyclomatic complexity from cascading if/elif chains. Each chain is a lookup table pretending to be logic. The fix is to extract each concern into a data-driven approach.

I see 5 independent concerns:
1. Volume discount → lookup table
2. User tier discount → lookup table
3. Wholesale check → separate method
4. Coupon application → separate method
5. Seasonal discount → separate method
6. Tax rate → lookup table

Each can be extracted into a focused function or data structure.
</think>

The complexity comes from **lookup tables masquerading as logic**. Each if/elif chain maps a value to a number — use actual lookup tables:

```python
VOLUME_DISCOUNTS = [
    (1000, Decimal('0.70')),
    (500,  Decimal('0.80')),
    (100,  Decimal('0.85')),
    (50,   Decimal('0.90')),
    (10,   Decimal('0.95')),
]

TIER_DISCOUNTS = {
    'platinum': Decimal('0.90'),
    'gold':     Decimal('0.93'),
    'silver':   Decimal('0.95'),
    'bronze':   Decimal('0.97'),
}

TAX_RATES = {
    'CA': Decimal('0.0725'),
    'NY': Decimal('0.08'),
}
NO_TAX_STATES = frozenset({'OR', 'MT', 'NH', 'DE', 'AK'})
DEFAULT_TAX_RATE = Decimal('0.06')

def calculate_price(product, user, quantity, coupon=None, is_wholesale=False):
    price = Decimal(str(product.price))

    price *= _volume_multiplier(quantity)
    price *= _tier_multiplier(user.tier)
    price = _apply_wholesale(price, user, is_wholesale)
    price = _apply_coupon(price, coupon, quantity)
    price = _apply_seasonal(price, product)

    total = price * quantity
    total *= (1 + _tax_rate(user.state))

    return total.quantize(Decimal('0.01'))

def _volume_multiplier(quantity):
    for threshold, multiplier in VOLUME_DISCOUNTS:
        if quantity >= threshold:
            return multiplier
    return Decimal(1)

def _tier_multiplier(tier):
    return TIER_DISCOUNTS.get(tier, Decimal(1))

def _apply_wholesale(price, user, is_wholesale):
    if not is_wholesale:
        return price
    if not user.is_verified_wholesaler:
        raise PermissionError('Not a verified wholesaler')
    return price * Decimal('0.75')

def _apply_coupon(price, coupon, quantity):
    if not coupon or coupon.is_expired():
        return price
    if coupon.type == 'percent':
        if coupon.min_quantity and quantity < coupon.min_quantity:
            return price
        return price * (1 - Decimal(coupon.value) / 100)
    if coupon.type == 'fixed':
        return max(price - Decimal(coupon.value), Decimal(0))
    return price

def _apply_seasonal(price, product):
    month = datetime.now().month
    if month in (11, 12) and product.category == 'holiday':
        return price * Decimal('0.85')
    if month in (6, 7, 8) and product.category == 'summer':
        return price * Decimal('0.80')
    return price

def _tax_rate(state):
    if state in NO_TAX_STATES:
        return Decimal(0)
    return TAX_RATES.get(state, DEFAULT_TAX_RATE)
```

**Results**: Main function is 10 lines. Each helper is independently testable. Discount/tax tables are data, not logic — update them without touching code. Also switched from `float` to `Decimal` for money.'''
    ),
    (
        "thinking/review-data-clumps",
        "Review this code. I feel like something is redundant but I'm not sure what:\n\n```python\ndef create_shipment(recipient_name, recipient_street, recipient_city,\n                    recipient_state, recipient_zip, recipient_country,\n                    sender_name, sender_street, sender_city,\n                    sender_state, sender_zip, sender_country,\n                    weight, dimensions, service_type):\n    validate_address(recipient_street, recipient_city, recipient_state,\n                     recipient_zip, recipient_country)\n    validate_address(sender_street, sender_city, sender_state,\n                     sender_zip, sender_country)\n    rate = calculate_rate(sender_zip, sender_country,\n                         recipient_zip, recipient_country,\n                         weight, dimensions, service_type)\n    label = generate_label(recipient_name, recipient_street, recipient_city,\n                          recipient_state, recipient_zip, recipient_country,\n                          sender_name, sender_street, sender_city,\n                          sender_state, sender_zip, sender_country)\n    return {'rate': rate, 'label': label}\n\ndef calculate_rate(from_zip, from_country, to_zip, to_country,\n                   weight, dimensions, service_type):\n    ...\n\ndef validate_address(street, city, state, zip_code, country):\n    ...\n\ndef generate_label(to_name, to_street, to_city, to_state, to_zip, to_country,\n                   from_name, from_street, from_city, from_state, from_zip, from_country):\n    ...\n```",
        r'''<think>
Classic **Data Clumps** smell. The same group of fields (name, street, city, state, zip, country) travels together through every function. They're an Address object waiting to be extracted.

Also a **Long Parameter List** smell — 15 parameters for `create_shipment`.
</think>

**Data Clumps** — the same 5-6 fields travel together through every function. They're an `Address` object:

```python
@dataclass(frozen=True)
class Address:
    name: str
    street: str
    city: str
    state: str
    zip_code: str
    country: str

    def validate(self):
        if not self.zip_code or not self.country:
            raise ValidationError("Zip and country required")
        # ... more validation

@dataclass(frozen=True)
class Package:
    weight: Decimal
    dimensions: tuple[float, float, float]
    service_type: str

def create_shipment(sender: Address, recipient: Address, package: Package):
    sender.validate()
    recipient.validate()
    rate = calculate_rate(sender, recipient, package)
    label = generate_label(sender, recipient)
    return Shipment(rate=rate, label=label)

def calculate_rate(sender: Address, recipient: Address, package: Package):
    ...

def generate_label(sender: Address, recipient: Address):
    ...
```

**15 parameters → 3 parameters.** The address validation logic now lives on `Address` where it belongs.

**Data clump rule**: If 3+ fields always appear together in function signatures, they're an object.'''
    ),
    (
        "thinking/review-strategy-refactoring",
        "We need to add PDF export to this report generator. Currently it only does HTML and CSV. Every time we add a format, we modify this class:\n\n```python\nclass ReportGenerator:\n    def generate(self, data, format_type, title='Report'):\n        if format_type == 'html':\n            output = f'<html><head><title>{title}</title></head><body>'\n            output += f'<h1>{title}</h1><table>'\n            output += '<tr>' + ''.join(f'<th>{h}</th>' for h in data[0].keys()) + '</tr>'\n            for row in data:\n                output += '<tr>' + ''.join(f'<td>{v}</td>' for v in row.values()) + '</tr>'\n            output += '</table></body></html>'\n            return output\n        elif format_type == 'csv':\n            import io, csv\n            output = io.StringIO()\n            writer = csv.DictWriter(output, fieldnames=data[0].keys())\n            writer.writeheader()\n            writer.writerows(data)\n            return output.getvalue()\n        elif format_type == 'json':\n            return json.dumps({'title': title, 'data': data}, indent=2)\n        else:\n            raise ValueError(f'Unknown format: {format_type}')\n```\n\nNow I need to add PDF, Excel, and Markdown. Show me the refactoring.",
        r'''<think>
Open/Closed Principle violation — adding a format requires modifying the class. Strategy pattern makes this extensible.

I should also point out that the title handling is inconsistent — HTML uses it, CSV ignores it, JSON includes it. A clean refactoring should standardize this.
</think>

Add formats by creating classes, not modifying existing code:

```python
from abc import ABC, abstractmethod

class ReportFormatter(ABC):
    @abstractmethod
    def format(self, title: str, data: list[dict]) -> str | bytes:
        ...

class HtmlFormatter(ReportFormatter):
    def format(self, title, data):
        headers = data[0].keys()
        rows = ''.join(
            '<tr>' + ''.join(f'<td>{v}</td>' for v in row.values()) + '</tr>'
            for row in data
        )
        return (
            f'<html><head><title>{title}</title></head><body>'
            f'<h1>{title}</h1><table>'
            f'<tr>{"".join(f"<th>{h}</th>" for h in headers)}</tr>'
            f'{rows}</table></body></html>'
        )

class CsvFormatter(ReportFormatter):
    def format(self, title, data):
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        return output.getvalue()

class JsonFormatter(ReportFormatter):
    def format(self, title, data):
        return json.dumps({'title': title, 'data': data}, indent=2)

class MarkdownFormatter(ReportFormatter):
    def format(self, title, data):
        headers = list(data[0].keys())
        lines = [f'# {title}', '']
        lines.append('| ' + ' | '.join(headers) + ' |')
        lines.append('| ' + ' | '.join('---' for _ in headers) + ' |')
        for row in data:
            lines.append('| ' + ' | '.join(str(v) for v in row.values()) + ' |')
        return '\n'.join(lines)

# Registry
FORMATTERS: dict[str, ReportFormatter] = {
    'html': HtmlFormatter(),
    'csv': CsvFormatter(),
    'json': JsonFormatter(),
    'markdown': MarkdownFormatter(),
}

class ReportGenerator:
    def generate(self, data: list[dict], format_type: str, title: str = 'Report') -> str | bytes:
        formatter = FORMATTERS.get(format_type)
        if not formatter:
            raise ValueError(
                f"Unknown format '{format_type}'. Available: {', '.join(FORMATTERS)}"
            )
        return formatter.format(title, data)
```

Adding PDF or Excel = one new class + one registry entry. Zero changes to `ReportGenerator`.'''
    ),
    (
        "thinking/review-test-code-smells",
        "Review our test suite. Tests keep breaking even when the feature works fine:\n\n```python\ndef test_user_registration():\n    # Test everything in one test\n    response = client.post('/api/register', json={\n        'email': 'test@example.com',\n        'password': 'Password123!',\n        'name': 'Test User'\n    })\n    assert response.status_code == 201\n    data = response.json()\n    assert data['id'] == 1  # Assumes auto-increment starts at 1\n    assert data['created_at'] == '2024-01-15T10:30:00Z'  # Hardcoded time\n    \n    # Verify in database\n    user = User.objects.get(email='test@example.com')\n    assert user.name == 'Test User'\n    assert user.is_active == True\n    \n    # Verify welcome email\n    assert len(mail.outbox) == 1\n    assert mail.outbox[0].subject == 'Welcome to Our Platform, Test User!'\n    assert 'Click here to verify' in mail.outbox[0].body\n    \n    # Verify analytics\n    assert analytics.events[-1] == {\n        'event': 'user_registered',\n        'user_id': 1,\n        'timestamp': '2024-01-15T10:30:00Z',\n        'properties': {'source': 'api', 'plan': 'free'}\n    }\n    \n    # Test login\n    response = client.post('/api/login', json={\n        'email': 'test@example.com',\n        'password': 'Password123!'\n    })\n    assert response.status_code == 200\n    assert 'token' in response.json()\n    \n    # Test duplicate registration\n    response = client.post('/api/register', json={\n        'email': 'test@example.com',\n        'password': 'Password123!',\n        'name': 'Duplicate'\n    })\n    assert response.status_code == 409\n```",
        r'''<think>
Multiple test smells:

1. **Test does too much** — registration, email verification, analytics, login, duplicate handling — all in one test. When it fails, you don't know which part broke.

2. **Brittle assertions** — `data['id'] == 1` depends on DB state. `created_at == '2024-01-15T10:30:00Z'` depends on wall clock time.

3. **Testing implementation details** — exact email subject text, exact analytics event structure. Any copy change breaks the test.

4. **No test isolation** — second POST depends on first POST having created the user.

5. **Missing edge cases** — no tests for invalid email, weak password, missing fields.

Fix: split into focused tests, use flexible assertions, freeze time.
</think>

This test has 5 smells causing false failures:

## 1. Tests Too Much (Split It)

One test covers registration, email, analytics, login, AND duplicates. When it fails, you can't tell which part broke.

## 2. Brittle Assertions

```python
assert data['id'] == 1              # Fails if another test ran first
assert data['created_at'] == '2024-01-15T10:30:00Z'  # Fails every second
```

## 3. Tests Implementation Details

```python
assert mail.outbox[0].subject == 'Welcome to Our Platform, Test User!'
# PM changes the copy → test breaks → feature still works
```

## Refactored

```python
class TestUserRegistration:
    def test_successful_registration(self, client, db):
        response = client.post('/api/register', json={
            'email': 'test@example.com',
            'password': 'Password123!',
            'name': 'Test User',
        })
        assert response.status_code == 201
        data = response.json()
        assert 'id' in data                    # Exists, don't assert value
        assert data['email'] == 'test@example.com'

    def test_sends_welcome_email(self, client, mail_outbox):
        client.post('/api/register', json={...})
        assert len(mail_outbox) == 1
        assert 'verify' in mail_outbox[0].body.lower()  # Behavior, not copy

    def test_tracks_registration_event(self, client, analytics):
        client.post('/api/register', json={...})
        assert analytics.has_event('user_registered')  # Behavior check

    def test_rejects_duplicate_email(self, client, existing_user):
        response = client.post('/api/register', json={
            'email': existing_user.email,   # Use fixture, not test ordering
            'password': 'Password123!',
            'name': 'Other',
        })
        assert response.status_code == 409

    def test_rejects_weak_password(self, client):
        response = client.post('/api/register', json={
            'email': 'new@example.com',
            'password': '123',
            'name': 'Test',
        })
        assert response.status_code == 400

    def test_rejects_invalid_email(self, client):
        response = client.post('/api/register', json={
            'email': 'not-an-email',
            'password': 'Password123!',
            'name': 'Test',
        })
        assert response.status_code == 400
```

## Test Writing Rules
1. **One assertion concept per test** — test name tells you what broke
2. **Assert behavior, not implementation** — "email contains verify link" not "subject equals exact string"
3. **Never assert auto-generated values** — IDs, timestamps, UUIDs
4. **Use fixtures for preconditions** — don't rely on test ordering
5. **Test edge cases separately** — invalid inputs, duplicates, boundary values'''
    ),
    (
        "thinking/review-null-object-pattern",
        "We have `if user.subscription is not None` checks everywhere:\n\n```python\ndef render_header(user):\n    if user.subscription is not None:\n        if user.subscription.is_active():\n            plan_badge = user.subscription.plan_name\n        else:\n            plan_badge = 'Expired'\n    else:\n        plan_badge = 'Free'\n    \n    if user.subscription is not None and user.subscription.is_active():\n        can_export = user.subscription.features.get('export', False)\n    else:\n        can_export = False\n    \n    if user.subscription is not None:\n        days_left = user.subscription.days_remaining()\n    else:\n        days_left = None\n    ...\n\ndef check_feature(user, feature_name):\n    if user.subscription is not None:\n        if user.subscription.is_active():\n            return user.subscription.features.get(feature_name, False)\n    return False\n\ndef get_storage_limit(user):\n    if user.subscription is not None and user.subscription.is_active():\n        return user.subscription.storage_limit_gb\n    return 1  # Free tier: 1GB\n```\n\nThis null checking is everywhere. How do I clean this up?",
        r'''<think>
Null Object Pattern — create a `FreeSubscription` that implements the same interface as a real subscription but returns free-tier defaults. Then eliminate all the null checks.
</think>

Use the **Null Object Pattern** — a `FreeSubscription` that behaves like a subscription but returns free-tier defaults:

```python
class Subscription:
    def __init__(self, plan_name, features, storage_limit_gb, expires_at):
        self.plan_name = plan_name
        self.features = features
        self.storage_limit_gb = storage_limit_gb
        self.expires_at = expires_at

    def is_active(self):
        return datetime.utcnow() < self.expires_at

    def days_remaining(self):
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)

    @property
    def badge(self):
        return self.plan_name if self.is_active() else 'Expired'

    def has_feature(self, feature_name):
        return self.is_active() and self.features.get(feature_name, False)

class FreeSubscription(Subscription):
    """Null Object — eliminates all None checks."""
    def __init__(self):
        pass  # No data needed

    def is_active(self):
        return True  # Free tier is always "active"

    def days_remaining(self):
        return None

    @property
    def badge(self):
        return 'Free'

    def has_feature(self, feature_name):
        return False

    @property
    def storage_limit_gb(self):
        return 1

# User always has a subscription (never None)
class User:
    @property
    def subscription(self):
        return self._subscription or FreeSubscription()
```

Now all that null-checking code becomes:

```python
def render_header(user):
    plan_badge = user.subscription.badge
    can_export = user.subscription.has_feature('export')
    days_left = user.subscription.days_remaining()

def check_feature(user, feature_name):
    return user.subscription.has_feature(feature_name)

def get_storage_limit(user):
    return user.subscription.storage_limit_gb
```

**Null Object rule**: When you see the same `if x is not None` check in 3+ places, create a null object that provides safe defaults.'''
    ),
    (
        "thinking/review-comment-smells",
        "Our senior dev insists on 'well-documented' code. Review this:\n\n```python\ndef process(data):\n    # Initialize the result list\n    result = []\n    \n    # Loop through each item in the data\n    for item in data:\n        # Check if the item is valid\n        if item.status == 'active':\n            # Calculate the discount\n            # 10% for orders over $100\n            # 20% for orders over $500\n            # 30% for orders over $1000\n            if item.total > 1000:\n                discount = 0.3\n            elif item.total > 500:\n                discount = 0.2\n            elif item.total > 100:\n                discount = 0.1\n            else:\n                discount = 0\n            \n            # Apply the discount to the item\n            final_price = item.total * (1 - discount)\n            \n            # Add the result to the list\n            result.append({\n                'id': item.id,\n                'original': item.total,\n                'discount': discount,\n                'final': final_price\n            })\n    \n    # Return the result\n    return result\n\n# TODO: Fix this later\n# HACK: This works but I don't know why\ndef calculate_tax(amount, state):\n    # John wrote this on 2023-03-15\n    # Updated by Sarah 2023-06-20 to fix bug #432\n    return amount * 0.08  # Tax rate\n```",
        r'''<think>
Comment smells:
1. **Narrating the code** — "Initialize the result list", "Loop through each item", "Return the result" — these add zero information
2. **Comments as names** — "Check if the item is valid" → the code should say `if item.is_active`; "Calculate the discount" → extract a function named `calculate_discount`
3. **Journal comments** — "John wrote this on 2023-03-15" — that's what git blame is for
4. **TODO/HACK** — "Fix this later" with no ticket number = never gets fixed; "works but I don't know why" = time bomb
5. **Comments that lie** — the discount thresholds are documented in comments AND code — when one changes, the other becomes a lie
</think>

These comments are all **code smells**, not documentation. Here's why each type is harmful:

## Comment Smell Catalog

### 1. Narrating the Obvious
```python
result = []          # Initialize the result list    ← reader can see this
for item in data:    # Loop through each item        ← reader can see this
return result        # Return the result             ← reader can see this
```
**Fix**: Delete them. They add noise, not information.

### 2. Comments Instead of Clear Code
```python
# Check if the item is valid
if item.status == 'active':
```
**Fix**: If you need a comment to explain what code does, rename the code:
```python
if item.is_active:
```

### 3. Comments Instead of Functions
```python
# Calculate the discount
# 10% for orders over $100, 20% for over $500, 30% for over $1000
if item.total > 1000: ...
```
**Fix**: Extract a function — the name IS the documentation:
```python
discount = volume_discount(item.total)
```

### 4. Journal Comments
```python
# John wrote this on 2023-03-15
# Updated by Sarah 2023-06-20 to fix bug #432
```
**Fix**: Delete. This is `git blame` and `git log`. Comments go stale; git history doesn't.

### 5. TODO/HACK Without Accountability
```python
# TODO: Fix this later
# HACK: This works but I don't know why
```
**Fix**: TODOs must have a ticket number or they never get fixed. HACKs mean you have a bug you don't understand.

## Refactored: Code That Documents Itself

```python
VOLUME_DISCOUNTS = [
    (1000, Decimal('0.30')),
    (500,  Decimal('0.20')),
    (100,  Decimal('0.10')),
]

def price_active_orders(orders):
    return [
        price_order(order)
        for order in orders
        if order.is_active
    ]

def price_order(order):
    discount = volume_discount(order.total)
    return {
        'id': order.id,
        'original': order.total,
        'discount': discount,
        'final': order.total * (1 - discount),
    }

def volume_discount(total):
    for threshold, rate in VOLUME_DISCOUNTS:
        if total > threshold:
            return rate
    return Decimal(0)
```

**Zero comments, fully self-documenting.** Good comments explain *why*, never *what*. If you need to explain what code does, the code needs better names.'''
    ),
    (
        "thinking/review-code-review-checklist",
        "I'm leading a team and want to establish code review standards. What should reviewers actually look for? Give me a practical checklist, not vague platitudes.",
        r'''<think>
The user wants a concrete, actionable code review checklist. Let me organize it by priority — what catches the most bugs and prevents the most tech debt.

I should focus on:
1. Correctness (does it work?)
2. Security (is it safe?)
3. Maintainability (can someone else understand and change it?)
4. Performance (are there obvious problems?)

I'll make it practical with "look for" items and "red flags."
</think>

## Code Review Checklist (Practical Edition)

### Tier 1: Must Check (Blocks Merge)

**Correctness**
- [ ] Does it handle the unhappy path? (empty input, null, zero, negative, max int)
- [ ] Off-by-one: `<` vs `<=`, range boundaries, loop termination
- [ ] Concurrent access: is shared state protected?
- [ ] Error handling: are errors caught at the right level? Not swallowed?
- [ ] Edge cases: empty collections, single element, Unicode, very large input

**Security**
- [ ] User input: sanitized before use in SQL, HTML, shell, file paths?
- [ ] Auth: does every endpoint check permissions, not just the frontend?
- [ ] Secrets: no API keys, passwords, or tokens in code?
- [ ] Data exposure: does the API return only what the client needs?

**Data Integrity**
- [ ] Database operations in transactions where needed?
- [ ] Idempotent where it should be? (retries safe?)
- [ ] Race conditions between check and action?

### Tier 2: Should Check (Quality Gate)

**Design**
- [ ] Does it change behavior of existing code unintentionally?
- [ ] Single Responsibility: does each function/class do one thing?
- [ ] Is the abstraction level consistent within a function?
- [ ] Could a new team member understand this in 5 minutes?

**Naming**
- [ ] Do names reveal intent? (`remaining_retries` not `r`)
- [ ] Are booleans phrased as questions? (`is_valid`, `has_permission`)
- [ ] Do function names describe the action and return value?

**Testing**
- [ ] Are the important behaviors tested? (not just the happy path)
- [ ] Do tests fail for the right reason? (test what, not how)
- [ ] No test interdependence? (each test works in isolation)

### Tier 3: Worth Checking (Polish)

**Performance**
- [ ] N+1 queries? (ORM code that triggers DB calls in loops)
- [ ] Unbounded collections? (loading all records into memory)
- [ ] Missing indexes for new query patterns?

**Maintainability**
- [ ] Duplicated logic that should be extracted?
- [ ] Magic numbers/strings that should be named constants?
- [ ] Comments explain *why*, not *what*?

### Red Flags (Always Flag These)

```
except Exception: pass          → Error swallowing
.objects.all()                  → Unbounded query
sleep()/time.sleep()            → Usually wrong approach
eval()/exec()                   → Code injection risk
# TODO / # HACK / # FIXME      → Must have ticket number
os.system() / subprocess        → Command injection risk
pickle.loads(user_input)        → Deserialization attack
```

### What NOT to Nitpick
- Formatting (automate with linter)
- Import ordering (automate with isort)
- Personal style preferences that don't affect readability
- "I would have done it differently" without a concrete improvement'''
    ),
    (
        "thinking/review-strangler-fig-refactoring",
        "We have a 5000-line monolithic `OrderProcessor` class that handles everything from validation to payment to shipping. We want to refactor it but can't do a big rewrite — the system processes $2M/day. How do we incrementally refactor without breaking anything?",
        r'''<think>
This is the Strangler Fig pattern — incrementally replacing parts of a monolith without a big-bang rewrite. Named after strangler fig trees that grow around a host tree and gradually replace it.

Key principles:
1. Never stop the existing system
2. Extract one behavior at a time
3. Route traffic gradually
4. Keep both old and new running until new is proven
5. Test at the integration boundary

Let me give a practical step-by-step approach.
</think>

Use the **Strangler Fig Pattern** — incrementally extract pieces while the old code keeps running.

## Step-by-Step Approach

### Phase 1: Understand the Monolith

```python
# Map the 5000-line class's responsibilities
class OrderProcessor:
    def process(self, order):
        self._validate(order)          # Lines 1-300
        self._check_inventory(order)    # Lines 301-600
        self._calculate_pricing(order)  # Lines 601-1100
        self._process_payment(order)    # Lines 1101-1800
        self._create_shipment(order)    # Lines 1801-2500
        self._send_notifications(order) # Lines 2501-3000
        self._update_analytics(order)   # Lines 3001-3500
        self._sync_erp(order)          # Lines 3501-5000
```

### Phase 2: Extract the Easiest, Least Risky Piece First

Start with something that has **no side effects on order state** — notifications or analytics:

```python
# New module: notifications.py
class OrderNotifier:
    def send_confirmation(self, order):
        # Extract the notification logic here
        ...

# Modified monolith — delegate, don't delete yet
class OrderProcessor:
    def __init__(self):
        self._notifier = OrderNotifier()

    def _send_notifications(self, order):
        # Old code commented out but kept for rollback
        self._notifier.send_confirmation(order)
```

### Phase 3: Add a Feature Flag for Safety

```python
class OrderProcessor:
    def _send_notifications(self, order):
        if feature_flags.is_enabled('new_notifier'):
            self._notifier.send_confirmation(order)
        else:
            self._legacy_send_notifications(order)  # Old code

    def _legacy_send_notifications(self, order):
        # Original 500 lines, untouched
        ...
```

### Phase 4: Verify with Dual-Write

```python
# For critical paths like payment, run BOTH and compare
class OrderProcessor:
    def _calculate_pricing(self, order):
        old_result = self._legacy_calculate_pricing(order)

        if feature_flags.is_enabled('new_pricing'):
            new_result = self._pricing_service.calculate(order)
            if old_result != new_result:
                logger.error(
                    "Pricing mismatch",
                    order_id=order.id,
                    old=old_result,
                    new=new_result,
                )
            return old_result  # Still use old result until verified
        return old_result
```

### Phase 5: Gradually Route Traffic

```
Week 1: 0% new code (dual-write comparison only)
Week 2: 1% traffic to new code (canary)
Week 3: 10% traffic
Week 4: 50% traffic
Week 5: 100% traffic, old code still present
Week 6: Delete old code
```

### Phase 6: Repeat for Each Responsibility

**Extraction order** (least to most risky):
1. Analytics/tracking (no business impact if wrong)
2. Notifications (can resend if needed)
3. Inventory checks (read-only)
4. Pricing calculation (verify with dual-write)
5. Shipment creation (verify with dual-write)
6. Payment processing (last — highest risk, most validation needed)
7. Validation (extract once everything else is out)

## Rules
- **Never rewrite more than one piece at a time**
- **Keep old code runnable** until new code is proven in production
- **Dual-write critical paths** before switching
- **Feature flags** on everything — instant rollback
- **Integration tests at the boundary** — test that the extracted module produces the same output as the monolith for the same input'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
