"""Phase 3F: Metacognition — Code Quality Judgment (Part 1)

Scenario 1: Rate code readability (1-10) with justification.
Evaluate naming, structure, comments, idioms.
"""

PAIRS = [
    (
        "thinking/meta-quality-readability-dense-comprehension",
        r'''Rate the readability of this code (1-10):

```python
def f(d):
    return {k: [x for x in v if x > 0] for k, v in d.items() if any(x > 0 for x in v)}
```''',
        r'''<think>
Let me evaluate this code's readability on multiple axes:

**Naming**: 1/5 — `f`, `d`, `k`, `v`, `x` tell me nothing about what this function does.

**Structure**: 3/5 — It's a single line doing two things: filtering dict values to positives, and excluding keys with no positives. Nested comprehensions are hard to parse.

**Comments**: 0/5 — No docstring, no comments, no type hints.

**Idioms**: 4/5 — Dict and list comprehensions are Pythonic, but nesting them this deeply is pushing it.

**Intent clarity**: 1/5 — I have to mentally trace through the comprehension to understand what it does. The name `f` gives zero context.

Overall: (1 + 3 + 0 + 4 + 1) / 5 = 1.8, round to 2/10.
</think>

**Readability: 2/10**

| Axis | Score | Issue |
|------|-------|-------|
| Naming | 1/5 | `f`, `d`, `k`, `v`, `x` — completely opaque |
| Structure | 3/5 | Nested comprehension, two operations in one line |
| Comments | 0/5 | No docstring, no type hints |
| Idioms | 4/5 | Comprehensions are Pythonic, but over-nested |
| Intent | 1/5 | Must mentally execute to understand purpose |

**Improved version (8/10 readability):**
```python
def filter_positive_values(data: dict[str, list[float]]) -> dict[str, list[float]]:
    """Remove non-positive numbers from each list, dropping empty keys."""
    result = {}
    for key, values in data.items():
        positives = [v for v in values if v > 0]
        if positives:
            result[key] = positives
    return result
```

**What changed:**
- Function name describes what it does
- Type hints show expected input/output
- Docstring explains the purpose
- Explicit loop is easier to follow than nested comprehension
- Intermediate variable `positives` names the concept'''
    ),
    (
        "thinking/meta-quality-readability-good-naming",
        r'''Rate the readability of this code (1-10):

```python
def calculate_shipping_cost(order: Order) -> Decimal:
    """Calculate shipping based on weight tiers and destination."""
    base_rate = SHIPPING_RATES[order.destination_zone]
    weight_kg = sum(item.weight_kg * item.quantity for item in order.items)

    if weight_kg <= 1:
        return base_rate
    elif weight_kg <= 5:
        return base_rate + Decimal("2.50") * (weight_kg - 1)
    else:
        return base_rate + Decimal("10.00") + Decimal("1.50") * (weight_kg - 5)
```''',
        r'''<think>
Let me evaluate this code's readability:

**Naming**: 5/5 — `calculate_shipping_cost`, `base_rate`, `weight_kg`, `destination_zone` — all self-documenting.

**Structure**: 4/5 — Clear linear flow. The if/elif/else is easy to follow. Slight concern: the magic numbers (1, 5, 2.50, 10.00, 1.50) could be named constants, but the docstring and context make them clear enough.

**Comments**: 4/5 — Good docstring. The code is self-documenting enough that inline comments aren't needed. Could benefit from a note about the pricing formula.

**Idioms**: 5/5 — Proper use of Decimal for money, type hints, generator expression for weight sum.

**Intent clarity**: 5/5 — I can immediately tell what this does and how it works.

Overall: (5 + 4 + 4 + 5 + 5) / 5 = 4.6, round to 9/10.
</think>

**Readability: 9/10**

| Axis | Score | Notes |
|------|-------|-------|
| Naming | 5/5 | Self-documenting names throughout |
| Structure | 4/5 | Clean linear flow, clear tier structure |
| Comments | 4/5 | Good docstring, code speaks for itself |
| Idioms | 5/5 | Decimal for money, type hints, generator expression |
| Intent | 5/5 | Immediately clear what it does and why |

**Minor improvement (optional — would bring to 10/10):**
```python
LIGHT_WEIGHT_KG = 1
MEDIUM_WEIGHT_KG = 5
MEDIUM_RATE_PER_KG = Decimal("2.50")
HEAVY_BASE_SURCHARGE = Decimal("10.00")
HEAVY_RATE_PER_KG = Decimal("1.50")
```

But honestly, the magic numbers are clear enough in context. Named constants would help if the tiers are referenced elsewhere or change frequently.

**What makes this readable:**
- Function name IS the documentation
- Variable names describe their units (`weight_kg`)
- Type hints show the contract
- Simple control flow (no nesting beyond one level)
- Uses the right numeric type (Decimal, not float)'''
    ),
    (
        "thinking/meta-quality-readability-clever-bitwise",
        r'''Rate the readability of this code (1-10):

```python
def is_power_of_two(n):
    return n > 0 and (n & (n - 1)) == 0

def next_power_of_two(n):
    n -= 1
    n |= n >> 1
    n |= n >> 2
    n |= n >> 4
    n |= n >> 8
    n |= n >> 16
    n += 1
    return n

def count_set_bits(n):
    n = n - ((n >> 1) & 0x55555555)
    n = (n & 0x33333333) + ((n >> 2) & 0x33333333)
    return (((n + (n >> 4)) & 0x0F0F0F0F) * 0x01010101) >> 24
```''',
        r'''<think>
Let me evaluate this code's readability:

**Naming**: 3/5 — Function names are descriptive (`is_power_of_two`, `next_power_of_two`, `count_set_bits`). But the internal variable `n` with bitwise mutations is hard to follow without bit manipulation experience.

**Structure**: 2/5 — `is_power_of_two` is a single clean line. `next_power_of_two` is a series of obscure bitwise operations. `count_set_bits` is Hamming weight using bit tricks — essentially a magic spell to most developers.

**Comments**: 0/5 — Zero comments or docstrings. These algorithms NEED comments because they're non-obvious bit manipulation tricks.

**Idioms**: 3/5 — These are well-known bit manipulation patterns in systems programming. But in Python, they're unusual — most Python developers would use `bin(n).count('1')` for bit counting.

**Intent clarity**: 2/5 — Function names are good, but HOW they work is opaque without bit manipulation knowledge.

Overall: (3 + 2 + 0 + 3 + 2) / 5 = 2.0, so 4/10. The function names save it from being completely unreadable.
</think>

**Readability: 4/10**

| Axis | Score | Notes |
|------|-------|-------|
| Naming | 3/5 | Good function names, opaque internals |
| Structure | 2/5 | Bit tricks are sequential but non-obvious |
| Comments | 0/5 | Bit manipulation NEEDS comments — none present |
| Idioms | 3/5 | Known patterns in C/systems, unusual in Python |
| Intent | 2/5 | What → clear from names. How → opaque |

**Improved version (8/10):**
```python
def is_power_of_two(n: int) -> bool:
    """Check if n is a power of 2. Uses the bit trick: powers of 2
    have exactly one bit set, so n & (n-1) clears that bit to zero."""
    return n > 0 and (n & (n - 1)) == 0

def next_power_of_two(n: int) -> int:
    """Round up to the next power of 2.
    Works by filling all bits below the highest set bit, then adding 1.
    Example: 5 (101) → 7 (111) → 8 (1000)."""
    if n <= 0:
        return 1
    n -= 1
    n |= n >> 1   # Fill 2-bit groups
    n |= n >> 2   # Fill 4-bit groups
    n |= n >> 4   # Fill 8-bit groups
    n |= n >> 8   # Fill 16-bit groups
    n |= n >> 16  # Fill 32-bit groups
    return n + 1

def count_set_bits(n: int) -> int:
    """Count the number of 1-bits (Hamming weight / popcount).
    For readability, consider: bin(n).count('1') in Python."""
    return bin(n).count('1')  # Pythonic alternative
```

**The key insight:** Clever bit tricks sacrifice readability for performance. In Python (where function call overhead dwarfs bit operations), the simple version is usually fast enough AND readable.'''
    ),
    (
        "thinking/meta-quality-readability-long-function",
        r'''Rate the readability of this code (1-10):

```python
def process_order(request):
    email = request.json.get('email')
    if not email:
        return jsonify({"error": "Email required"}), 400
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify({"error": "Invalid email"}), 400
    items = request.json.get('items', [])
    if not items:
        return jsonify({"error": "No items"}), 400
    for item in items:
        if 'product_id' not in item:
            return jsonify({"error": "Product ID required"}), 400
        if 'quantity' not in item:
            return jsonify({"error": "Quantity required"}), 400
        if item['quantity'] < 1:
            return jsonify({"error": "Quantity must be positive"}), 400
    total = 0
    order_items = []
    for item in items:
        product = db.query(Product).get(item['product_id'])
        if not product:
            return jsonify({"error": f"Product {item['product_id']} not found"}), 404
        if product.stock < item['quantity']:
            return jsonify({"error": f"Insufficient stock for {product.name}"}), 400
        line_total = product.price * item['quantity']
        total += line_total
        order_items.append({"product": product, "quantity": item['quantity'], "price": line_total})
    tax = total * Decimal("0.08")
    shipping = Decimal("5.99") if total < 50 else Decimal("0")
    grand_total = total + tax + shipping
    order = Order(email=email, total=grand_total, tax=tax, shipping=shipping)
    db.add(order)
    for oi in order_items:
        db.add(OrderItem(order=order, product=oi['product'], quantity=oi['quantity'], price=oi['price']))
        oi['product'].stock -= oi['quantity']
    db.commit()
    send_confirmation_email(email, order)
    return jsonify({"order_id": order.id, "total": str(grand_total)}), 201
```''',
        r'''<think>
Let me evaluate this code's readability:

**Naming**: 3/5 — Variable names are reasonable (`email`, `items`, `total`, `grand_total`). But the function does too many things for one name to describe.

**Structure**: 1/5 — This is a 40+ line function with no separation of concerns. Validation, business logic, database operations, and email sending are all in one flat function. No helper functions, no blank lines separating logical sections.

**Comments**: 0/5 — No comments or docstring on a complex function.

**Idioms**: 2/5 — Direct database queries in request handlers. Mixed concerns. Magic numbers (0.08 tax, 5.99 shipping, 50 threshold). No use of validators or serializers.

**Intent clarity**: 2/5 — Each individual line is clear, but the overall flow is hard to follow because everything is at the same level of abstraction.

Overall: (3 + 1 + 0 + 2 + 2) / 5 = 1.6, round to 3/10.
</think>

**Readability: 3/10**

| Axis | Score | Notes |
|------|-------|-------|
| Naming | 3/5 | Reasonable var names, function does too much |
| Structure | 1/5 | 40+ lines, no separation of concerns |
| Comments | 0/5 | No docstring on a complex endpoint |
| Idioms | 2/5 | Magic numbers, mixed concerns, no validators |
| Intent | 2/5 | Individual lines clear, overall flow is lost |

**The core problem: one function doing 5 jobs.**
1. Input validation
2. Product lookup + stock check
3. Price calculation
4. Order creation
5. Email notification

**Improved version (8/10):**
```python
def process_order(request):
    """Create a new order from the request payload."""
    data = validate_order_request(request.json)
    order_items = resolve_products(data["items"])
    totals = calculate_totals(order_items)
    order = create_order(data["email"], order_items, totals)
    send_confirmation_email(data["email"], order)
    return jsonify({"order_id": order.id, "total": str(totals.grand_total)}), 201

def validate_order_request(data):
    """Validate and return cleaned order data. Raises ValidationError."""
    # ... validation logic here

def resolve_products(items):
    """Look up products and verify stock. Raises NotFound/InsufficientStock."""
    # ... product lookup here

def calculate_totals(order_items):
    """Calculate subtotal, tax, shipping, and grand total."""
    # ... calculation here
```

**What changed:**
- Main function reads like a recipe (5 high-level steps)
- Each step is a named function you can read/test independently
- Magic numbers move to named constants
- Each function is < 15 lines'''
    ),
    (
        "thinking/meta-quality-readability-well-structured",
        r'''Rate the readability of this code (1-10):

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class LogEntry:
    level: LogLevel
    message: str
    context: dict
    timestamp: float


class StructuredLogger:
    """JSON-based logger with context propagation."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self._context: dict = {}

    def with_context(self, **kwargs) -> "StructuredLogger":
        """Return a new logger with additional context fields."""
        new_logger = StructuredLogger(self.service_name)
        new_logger._context = {**self._context, **kwargs}
        return new_logger

    def info(self, message: str, **extra) -> None:
        self._emit(LogLevel.INFO, message, extra)

    def error(self, message: str, **extra) -> None:
        self._emit(LogLevel.ERROR, message, extra)

    def _emit(self, level: LogLevel, message: str, extra: dict) -> None:
        entry = LogEntry(
            level=level,
            message=message,
            context={**self._context, **extra, "service": self.service_name},
            timestamp=time.time(),
        )
        print(json.dumps(asdict(entry), default=str))
```''',
        r'''<think>
Let me evaluate this code's readability:

**Naming**: 5/5 — `StructuredLogger`, `LogEntry`, `LogLevel`, `with_context`, `_emit` — all clear and conventional. Private method prefix `_` used correctly.

**Structure**: 5/5 — Clean separation: Enum for levels, dataclass for entries, class for the logger. Methods are short (1-5 lines each). Single responsibility.

**Comments**: 4/5 — Class docstring explains the concept. `with_context` has a docstring. Individual methods don't need comments — they're self-documenting.

**Idioms**: 5/5 — Dataclasses, Enums, type hints, `**kwargs`, dict spread. All Pythonic. Immutable context propagation via `with_context` returning a new instance.

**Intent clarity**: 5/5 — The API is immediately obvious: create a logger, optionally add context, call info/error. The `with_context` pattern is clean.

Overall: (5 + 5 + 4 + 5 + 5) / 5 = 4.8, so 10/10.
</think>

**Readability: 10/10**

| Axis | Score | Notes |
|------|-------|-------|
| Naming | 5/5 | Self-documenting names, proper conventions |
| Structure | 5/5 | Clean separation, short methods, single responsibility |
| Comments | 4/5 | Docstrings where needed, self-documenting elsewhere |
| Idioms | 5/5 | Dataclasses, Enums, type hints, dict spread |
| Intent | 5/5 | API is immediately obvious |

**What makes this excellent:**

1. **Right abstractions**: Enum for fixed values, dataclass for data, class for behavior
2. **Immutable context propagation**: `with_context` returns new instance, not mutating
3. **Short methods**: Every method fits in your head (< 5 lines)
4. **Layered API**: Public `info()`/`error()` → private `_emit()` → single output point
5. **Type hints everywhere**: Contract is clear without reading implementation

**Usage is immediately clear:**
```python
logger = StructuredLogger("auth-service")
req_logger = logger.with_context(request_id="abc-123")
req_logger.info("User logged in", user_id=42)
```

This is the kind of code where new team members can understand, use, and extend it without asking questions.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
