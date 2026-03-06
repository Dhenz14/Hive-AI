r"""Thinking-trace pairs: simplify refactoring code review."""

PAIRS = [
    ("thinking/code-review", r'''Review this code and suggest simplification:

```python
def calculate_discount(customer, order):
    discount = 0

    if customer.tier == "gold":
        if order.total > 100:
            if order.items_count > 5:
                discount = 15
            else:
                if order.total > 200:
                    discount = 12
                else:
                    discount = 10
        else:
            if order.items_count > 10:
                discount = 8
            else:
                discount = 5
    elif customer.tier == "silver":
        if order.total > 100:
            if order.items_count > 5:
                discount = 10
            else:
                if order.total > 200:
                    discount = 8
                else:
                    discount = 7
        else:
            if order.items_count > 10:
                discount = 5
            else:
                discount = 3
    elif customer.tier == "bronze":
        if order.total > 100:
            if order.items_count > 5:
                discount = 7
            else:
                if order.total > 200:
                    discount = 5
                else:
                    discount = 3
        else:
            if order.items_count > 10:
                discount = 3
            else:
                discount = 1
    else:
        if order.total > 200:
            discount = 2
        elif order.total > 100:
            discount = 1
        else:
            discount = 0

    if customer.is_new and discount < 10:
        discount = 10

    if order.has_coupon:
        coupon_discount = order.coupon_value
        if coupon_discount > discount:
            discount = coupon_discount

    if discount > 25:
        discount = 25

    return discount
```''', r'''<think>
Let me look at this function... my first instinct is "just flatten the if/else chain with early returns." But wait, that would not actually help here -- the nesting is not from validation guards, it is from a combinatorial decision tree. Every branch leads to an assignment, not a return.

So what is the actual structure? Let me trace through it... Customer tier determines the outer branch, then order total, then item count. That is three dimensions. I almost missed that the item count threshold changes between the branches -- it is >5 for high-total orders but >10 for low-total orders. That is a sneaky business rule buried in the nesting.

My first thought was to flatten with early returns, but actually this is a lookup table problem, not a control flow problem. The nested ifs are encoding what should be data. If I pull out the discount values into a dictionary keyed by (tier, total_bucket, items_bucket), the whole structure becomes obvious and the hidden threshold difference becomes explicit.

But wait -- should I use a flat dictionary or a nested one? A flat dict with tuple keys like ("gold", "high", "many") is simpler to scan, but a nested dict preserves the tier grouping which might match how the business thinks about it. I will go with a structured approach since it makes it easier for a product manager to verify the values.

One thing that almost tripped me up: the three modifiers at the end (new customer floor, coupon override, max cap) are independent of the tier logic. They should be a separate function. Mixing the base calculation with the modifiers in one function is why this code is so hard to reason about -- you cannot tell where "business rules" end and "adjustments" begin.
</think>

## Code Review: Simplify Deeply Nested Conditionals

### CRITICAL - 5-Level Nested If/Else (Cyclomatic Complexity)
The function has 5 levels of nesting with 15+ branches. This is extremely difficult to read, test, and modify. Adding a new tier or threshold requires duplicating the entire nested structure.

**Simplification using a lookup table:**
```python
DISCOUNT_TABLE = {
    "gold":   {"high_many": 15, "high_few": 12, "mid_many": 15, "mid_few": 10, "low_many": 8, "low_few": 5},
    "silver": {"high_many": 10, "high_few": 8,  "mid_many": 10, "mid_few": 7,  "low_many": 5, "low_few": 3},
    "bronze": {"high_many": 7,  "high_few": 5,  "mid_many": 7,  "mid_few": 3,  "low_many": 3, "low_few": 1},
    None:     {"high_many": 2,  "high_few": 2,  "mid_many": 1,  "mid_few": 1,  "low_many": 0, "low_few": 0},
}

def calculate_discount(customer, order):
    base = _get_base_discount(customer.tier, order.total, order.items_count)
    base = _apply_modifiers(base, customer, order)
    return min(base, 25)

def _get_base_discount(tier, total, items_count):
    tier_discounts = DISCOUNT_TABLE.get(tier, DISCOUNT_TABLE[None])
    many_items = items_count > 5

    if total > 200:
        key = "high_many" if many_items else "high_few"
    elif total > 100:
        key = "mid_many" if many_items else "mid_few"
    else:
        many_items = items_count > 10  # Different threshold for low total
        key = "low_many" if many_items else "low_few"

    return tier_discounts[key]

def _apply_modifiers(discount, customer, order):
    if customer.is_new:
        discount = max(discount, 10)
    if order.has_coupon:
        discount = max(discount, order.coupon_value)
    return discount
```

### HIGH - Magic Numbers Throughout
The discount percentages (15, 12, 10, 8, 7, 5, 3, 2, 1, 0) and thresholds (100, 200, 5, 10, 25) are all magic numbers with no explanation. Changing any value requires reading the entire nested structure.

**Fix:** The lookup table approach above makes all values visible in one place. Adding named constants for thresholds:
```python
HIGH_ORDER_THRESHOLD = 200
MID_ORDER_THRESHOLD = 100
MANY_ITEMS_THRESHOLD = 5
MAX_DISCOUNT = 25
NEW_CUSTOMER_MIN_DISCOUNT = 10
```

### MEDIUM - Different Item Thresholds Hidden in Nesting
The item count threshold is >5 for high-total orders but >10 for low-total orders. This business rule is buried deep in the nesting and easy to miss. It should be explicit and documented.

### MEDIUM - Modifier Logic Can Be Simplified
The three modifier blocks (new customer, coupon, cap) each use if-then assignment. Using `max()` and `min()` is cleaner:
```python
discount = max(discount, 10) if customer.is_new else discount
discount = max(discount, order.coupon_value) if order.has_coupon else discount
discount = min(discount, 25)
```

### LOW - No Input Validation
No checks for negative order totals, negative item counts, or invalid tier values. Edge cases could produce unexpected results.'''),

    ("thinking/code-review", r'''Review this code and suggest duplication removal:

```python
class UserAPI:
    def get_users(self, filters=None):
        query = "SELECT id, username, email, role, created_at FROM users WHERE 1=1"
        params = []

        if filters:
            if filters.get("role"):
                query += " AND role = %s"
                params.append(filters["role"])
            if filters.get("status"):
                query += " AND status = %s"
                params.append(filters["status"])
            if filters.get("created_after"):
                query += " AND created_at > %s"
                params.append(filters["created_after"])
            if filters.get("search"):
                query += " AND (username ILIKE %s OR email ILIKE %s)"
                params.append(f"%{filters['search']}%")
                params.append(f"%{filters['search']}%")

        query += " ORDER BY created_at DESC"
        query += f" LIMIT {filters.get('limit', 20)} OFFSET {filters.get('offset', 0)}"

        results = self.db.execute(query, params)
        users = []
        for row in results:
            users.append({
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "role": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
            })
        return users

    def get_products(self, filters=None):
        query = "SELECT id, name, price, category, stock, created_at FROM products WHERE 1=1"
        params = []

        if filters:
            if filters.get("category"):
                query += " AND category = %s"
                params.append(filters["category"])
            if filters.get("min_price"):
                query += " AND price >= %s"
                params.append(filters["min_price"])
            if filters.get("max_price"):
                query += " AND price <= %s"
                params.append(filters["max_price"])
            if filters.get("in_stock"):
                query += " AND stock > 0"
            if filters.get("search"):
                query += " AND (name ILIKE %s OR description ILIKE %s)"
                params.append(f"%{filters['search']}%")
                params.append(f"%{filters['search']}%")

        query += " ORDER BY created_at DESC"
        query += f" LIMIT {filters.get('limit', 20)} OFFSET {filters.get('offset', 0)}"

        results = self.db.execute(query, params)
        products = []
        for row in results:
            products.append({
                "id": row[0],
                "name": row[1],
                "price": float(row[2]),
                "category": row[3],
                "stock": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
            })
        return products

    def get_orders(self, filters=None):
        query = "SELECT id, user_id, total, status, created_at FROM orders WHERE 1=1"
        params = []

        if filters:
            if filters.get("user_id"):
                query += " AND user_id = %s"
                params.append(filters["user_id"])
            if filters.get("status"):
                query += " AND status = %s"
                params.append(filters["status"])
            if filters.get("min_total"):
                query += " AND total >= %s"
                params.append(filters["min_total"])
            if filters.get("created_after"):
                query += " AND created_at > %s"
                params.append(filters["created_after"])

        query += " ORDER BY created_at DESC"
        query += f" LIMIT {filters.get('limit', 20)} OFFSET {filters.get('offset', 0)}"

        results = self.db.execute(query, params)
        orders = []
        for row in results:
            orders.append({
                "id": row[0],
                "user_id": row[1],
                "total": float(row[2]),
                "status": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
            })
        return orders
```''', r'''<think>
Let me scan these three methods... get_users, get_products, get_orders. They look almost identical. My first instinct is "extract a base method" but let me check if the differences are actually uniform enough for that.

Looking closer... the query construction is identical: WHERE 1=1, append conditions, ORDER BY, LIMIT, OFFSET. The filter field names differ per entity but the pattern is the same. The row-to-dict mapping is different per method. So I could extract the query-building part and the execution part, but the filter definitions and mapping need to stay entity-specific.

Wait, I almost missed something critical -- the LIMIT and OFFSET values are interpolated directly with f-strings! That is an SQL injection vulnerability. If someone passes filters={"limit": "1; DROP TABLE users; --"}, that SQL is executed directly. All the other filter values correctly use parameterized queries with %s, but limit and offset skip that protection. This is the most urgent fix.

Now for the duplication... I considered just extracting a helper method, but actually a QueryBuilder class is more appropriate because the pattern involves accumulating state (conditions, params) across multiple steps. A simple function would need to return multiple values or use mutable arguments, which gets messy.

The row-to-dict mapping is another source of fragility -- using tuple indices like row[0], row[1] means reordering columns in the SELECT breaks everything silently. Using cursor.description or a named mapping would eliminate that whole class of bugs. But I need to be careful not to over-engineer this. A simple _row_to_dict(row, columns) helper is probably the right level of abstraction. An ORM would be even better, but that is a bigger change than the question is asking for.
</think>

## Code Review: Remove Duplication

### CRITICAL - SQL Injection in LIMIT/OFFSET
All three methods interpolate limit and offset directly into the SQL string:
```python
query += f" LIMIT {filters.get('limit', 20)} OFFSET {filters.get('offset', 0)}"
```
If a caller passes `filters={"limit": "1; DROP TABLE users; --"}`, the SQL is injected.

**Fix:** Use parameterized values:
```python
query += " LIMIT %s OFFSET %s"
params.extend([filters.get("limit", 20), filters.get("offset", 0)])
```

### HIGH - Three Methods With Identical Structure
`get_users`, `get_products`, and `get_orders` share ~80% identical code. The pattern (build query, apply filters, paginate, execute, map rows) is duplicated three times. Adding pagination improvements or a new common filter requires changing all three methods.

**Extract a generic query builder:**
```python
class QueryBuilder:
    def __init__(self, table, columns):
        self.table = table
        self.columns = columns
        self.conditions = []
        self.params = []

    def where(self, condition, *params):
        self.conditions.append(condition)
        self.params.extend(params)
        return self

    def where_if(self, value, condition, *params):
        if value:
            self.where(condition, *params)
        return self

    def build(self, limit=20, offset=0):
        cols = ", ".join(self.columns)
        query = f"SELECT {cols} FROM {self.table}"
        if self.conditions:
            query += " WHERE " + " AND ".join(self.conditions)
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        self.params.extend([limit, offset])
        return query, self.params
```

**Simplified usage:**
```python
def get_users(self, filters=None):
    filters = filters or {}
    qb = QueryBuilder("users", ["id", "username", "email", "role", "created_at"])
    qb.where_if(filters.get("role"), "role = %s", filters.get("role"))
    qb.where_if(filters.get("status"), "status = %s", filters.get("status"))
    if filters.get("search"):
        qb.where("(username ILIKE %s OR email ILIKE %s)",
                 f"%{filters['search']}%", f"%{filters['search']}%")

    query, params = qb.build(filters.get("limit", 20), filters.get("offset", 0))
    return self._execute_and_map(query, params, qb.columns)
```

### MEDIUM - Manual Row-to-Dict Mapping
Each method manually maps tuple indices to dictionary keys. This is error-prone (wrong index = wrong column) and breaks if columns are reordered.

**Extract a reusable mapper:**
```python
def _execute_and_map(self, query, params, columns):
    results = self.db.execute(query, params)
    return [
        self._row_to_dict(row, columns)
        for row in results
    ]

def _row_to_dict(self, row, columns):
    record = {}
    for i, col in enumerate(columns):
        value = row[i]
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = float(value)
        record[col] = value
    return record
```

### MEDIUM - Duplicated Search Pattern
The ILIKE search pattern with `%search%` is duplicated in get_users and get_products. Extract to a reusable search condition:
```python
def _add_search(self, qb, search_term, *fields):
    if search_term:
        conditions = " OR ".join(f"{f} ILIKE %s" for f in fields)
        qb.where(f"({conditions})", *[f"%{search_term}%"] * len(fields))
```

### LOW - "WHERE 1=1" Antipattern
The `WHERE 1=1` trick allows appending conditions with AND without checking if it is the first condition. While functional, the QueryBuilder approach above eliminates the need for this hack.'''),

    ("thinking/code-review", r'''Review this code and suggest flattening nested logic:

```python
def process_payment(self, payment_data):
    if payment_data:
        if payment_data.get("method"):
            method = payment_data["method"]
            if method in ["credit_card", "debit_card"]:
                if payment_data.get("card_number"):
                    if len(payment_data["card_number"]) >= 13:
                        if payment_data.get("expiry"):
                            month, year = payment_data["expiry"].split("/")
                            if int(year) >= datetime.now().year % 100:
                                if int(month) >= 1 and int(month) <= 12:
                                    if payment_data.get("cvv"):
                                        if len(payment_data["cvv"]) in [3, 4]:
                                            result = self.gateway.charge(
                                                card=payment_data["card_number"],
                                                expiry=payment_data["expiry"],
                                                cvv=payment_data["cvv"],
                                                amount=payment_data["amount"]
                                            )
                                            if result.success:
                                                self.db.save_transaction(result)
                                                self.send_receipt(payment_data, result)
                                                return {"status": "success", "transaction_id": result.id}
                                            else:
                                                return {"status": "failed", "error": result.error}
                                        else:
                                            return {"status": "error", "error": "Invalid CVV"}
                                    else:
                                        return {"status": "error", "error": "CVV required"}
                                else:
                                    return {"status": "error", "error": "Invalid month"}
                            else:
                                return {"status": "error", "error": "Card expired"}
                        else:
                            return {"status": "error", "error": "Expiry required"}
                    else:
                        return {"status": "error", "error": "Invalid card number"}
                else:
                    return {"status": "error", "error": "Card number required"}
            elif method == "paypal":
                if payment_data.get("paypal_token"):
                    result = self.gateway.charge_paypal(
                        token=payment_data["paypal_token"],
                        amount=payment_data["amount"]
                    )
                    if result.success:
                        self.db.save_transaction(result)
                        return {"status": "success", "transaction_id": result.id}
                    else:
                        return {"status": "failed", "error": result.error}
                else:
                    return {"status": "error", "error": "PayPal token required"}
            else:
                return {"status": "error", "error": "Unsupported payment method"}
        else:
            return {"status": "error", "error": "Payment method required"}
    else:
        return {"status": "error", "error": "No payment data"}
```''', r'''<think>
Wow, 10+ levels of nesting. My eyes are literally zigzagging right trying to trace which else belongs to which if. This is the classic "pyramid of doom" pattern.

My first thought is to flatten with guard clauses -- invert each condition and return early. But actually, I need to think about this more carefully. There are two separate concerns tangled together: input validation (is the data present and well-formed?) and business logic (charge the card, save the transaction). Let me separate those first.

For the validation part, guard clauses with early returns are perfect -- each check is independent. For the payment method dispatch, a method-per-type strategy works well. So the top-level function becomes: validate common fields -> dispatch to method handler -> handle result. That brings nesting from 10+ to about 2 levels.

Wait, I just noticed a real bug in the expiry validation. The check `int(year) >= datetime.now().year % 100` only validates the year. If the card expires 01/25 and today is 03/25, the year check passes but the card is actually expired. The month check exists but it only validates the range 1-12, not whether the month has already passed in the current year. That is a real production bug.

I also notice an inconsistency between the card and PayPal paths -- the card path calls self.send_receipt() but PayPal does not. That means PayPal customers silently never get receipts. This is the kind of bug that duplication creates: when you add a feature to one path but forget the other. If I extract a common _handle_success method, this becomes impossible to miss.

One more thing -- should the validation return the first error or all errors? Returning just the first error is simpler but frustrating for users who have to fix one thing at a time. For a payment form, collecting all errors in one pass is probably better UX, though the original code returns on first failure. I will keep the fail-fast approach since it matches the existing behavior, but flag it as something to improve.
</think>

## Code Review: Flatten Nested Logic

### CRITICAL - 10+ Levels of Nesting (Arrow Code)
The function has extreme nesting depth, making it nearly impossible to follow the control flow. Each validation adds another indentation level, creating a "pyramid of doom."

**Flatten using guard clauses (early returns):**
```python
def process_payment(self, payment_data):
    if not payment_data:
        return {"status": "error", "error": "No payment data"}

    method = payment_data.get("method")
    if not method:
        return {"status": "error", "error": "Payment method required"}

    if method in ["credit_card", "debit_card"]:
        return self._process_card_payment(payment_data)
    elif method == "paypal":
        return self._process_paypal_payment(payment_data)
    else:
        return {"status": "error", "error": "Unsupported payment method"}

def _process_card_payment(self, payment_data):
    errors = self._validate_card(payment_data)
    if errors:
        return {"status": "error", "error": errors[0]}

    result = self.gateway.charge(
        card=payment_data["card_number"],
        expiry=payment_data["expiry"],
        cvv=payment_data["cvv"],
        amount=payment_data["amount"]
    )

    if not result.success:
        return {"status": "failed", "error": result.error}

    self.db.save_transaction(result)
    self.send_receipt(payment_data, result)
    return {"status": "success", "transaction_id": result.id}

def _validate_card(self, data):
    errors = []
    if not data.get("card_number") or len(data["card_number"]) < 13:
        errors.append("Invalid card number")
    if not data.get("expiry"):
        errors.append("Expiry required")
    elif not self._is_valid_expiry(data["expiry"]):
        errors.append("Card expired or invalid expiry")
    if not data.get("cvv") or len(data["cvv"]) not in [3, 4]:
        errors.append("Invalid CVV")
    return errors
```

This reduces maximum nesting from 10+ levels to 2 levels.

### HIGH - Incorrect Expiry Validation
The current check `int(year) >= datetime.now().year % 100` does not handle the case where the card expires in the current year but in a past month. A card with expiry 01/25 would pass validation in March 2025.

**Fix:**
```python
def _is_valid_expiry(self, expiry):
    try:
        month, year = expiry.split("/")
        month, year = int(month), int(year)
        if month < 1 or month > 12:
            return False
        now = datetime.now()
        current_year = now.year % 100
        return (year > current_year) or (year == current_year and month >= now.month)
    except (ValueError, AttributeError):
        return False
```

### HIGH - Inconsistent Behavior Between Payment Methods
The credit card path calls `self.send_receipt()` after a successful payment, but the PayPal path does not. This means PayPal customers never receive receipts.

**Fix:** Extract common post-payment logic:
```python
def _handle_success(self, payment_data, result):
    self.db.save_transaction(result)
    self.send_receipt(payment_data, result)
    return {"status": "success", "transaction_id": result.id}
```

### MEDIUM - No Amount Validation
The function never validates `payment_data["amount"]`. Negative amounts, zero, or extremely large values are passed directly to the payment gateway.

### MEDIUM - Card Number and CVV Handling
The card number and CVV are passed as plaintext strings. They should never be logged, and in a PCI-compliant system, they should be tokenized before reaching this layer.

### LOW - Inconsistent Error Response Keys
Error responses use `"status": "error"` for validation failures but `"status": "failed"` for gateway failures. The distinction is unclear. Standardize on a single format with a machine-readable error code.'''),

    ("thinking/code-review", r'''Review this code and suggest simplifying conditionals:

```python
class OrderStatusManager:
    def can_cancel(self, order):
        if order.status == "pending":
            return True
        elif order.status == "confirmed":
            if order.payment_status == "pending":
                return True
            elif order.payment_status == "completed":
                if (datetime.now() - order.confirmed_at).total_seconds() < 3600:
                    return True
                else:
                    return False
            else:
                return False
        elif order.status == "processing":
            return False
        elif order.status == "shipped":
            return False
        elif order.status == "delivered":
            return False
        elif order.status == "cancelled":
            return False
        else:
            return False

    def get_next_actions(self, order):
        actions = []

        if order.status == "pending":
            actions.append("confirm")
            actions.append("cancel")
        elif order.status == "confirmed":
            actions.append("process")
            if order.payment_status == "pending":
                actions.append("cancel")
            elif order.payment_status == "completed":
                if (datetime.now() - order.confirmed_at).total_seconds() < 3600:
                    actions.append("cancel")
        elif order.status == "processing":
            actions.append("ship")
        elif order.status == "shipped":
            actions.append("deliver")
            actions.append("return")
        elif order.status == "delivered":
            actions.append("return")
            actions.append("review")

        if order.status not in ["cancelled", "returned"]:
            actions.append("contact_support")

        return actions

    def transition(self, order, action):
        if action == "confirm":
            if order.status == "pending":
                order.status = "confirmed"
                order.confirmed_at = datetime.now()
                return True
            return False
        elif action == "process":
            if order.status == "confirmed":
                if order.payment_status == "completed":
                    order.status = "processing"
                    return True
                return False
            return False
        elif action == "ship":
            if order.status == "processing":
                order.status = "shipped"
                order.shipped_at = datetime.now()
                return True
            return False
        elif action == "deliver":
            if order.status == "shipped":
                order.status = "delivered"
                order.delivered_at = datetime.now()
                return True
            return False
        elif action == "cancel":
            if self.can_cancel(order):
                order.status = "cancelled"
                order.cancelled_at = datetime.now()
                return True
            return False
        elif action == "return":
            if order.status in ["shipped", "delivered"]:
                order.status = "returned"
                return True
            return False
        else:
            return False
```''', r'''<think>
Three methods, all dealing with order status transitions... Let me see if they are actually consistent with each other.

Looking at can_cancel first. It returns True for pending, True for confirmed+pending_payment, True for confirmed+completed_payment if within 1 hour, and False for everything else. But there are 5 explicit "return False" branches for processing, shipped, delivered, cancelled, and else. Those are all redundant -- a single "return False" at the end would do the same thing. The author is being defensive, but it makes the logic look more complex than it is.

Now get_next_actions... wait, it re-implements the can_cancel logic! It checks payment_status and the time window independently instead of calling can_cancel. So if the cancel window changes from 1 hour to 2 hours, you have to update it in TWO places. That is a bug waiting to happen.

And transition... each branch follows the same pattern: check current state, update state, set timestamp, return True. This is clearly a state machine encoded as a chain of if/elif. The question is whether to use a data-driven approach (transition table) or keep the procedural approach.

I was initially going to suggest a simple transition table like {"pending": {"confirm": "confirmed"}, ...}. But then I realized some transitions have guards (process requires payment_status == "completed") and some have side effects (setting timestamps). A pure data table cannot express those.

Actually, I think a hybrid approach works best: define the basic transitions as data, but keep special conditions (like can_cancel's time check and process's payment check) as explicit guard functions. The transition table handles the common case, and named exceptions handle the edge cases. This gives you a single source of truth for "what transitions exist" while keeping the complex conditions readable.

The most critical insight: can_cancel is really just "can I transition to cancelled from the current state?" -- it is a special case of transition validation. If the transition table is the single source of truth, can_cancel becomes a one-liner, and get_next_actions just reads the table.
</think>

## Code Review: Simplify Conditionals with State Machine

### HIGH - Three Methods Encode the Same State Machine Differently
`can_cancel`, `get_next_actions`, and `transition` all independently encode order status transition rules. If a new status is added or a rule changes, all three methods must be updated consistently. This duplication guarantees they will drift out of sync.

**Simplify with a state machine definition:**
```python
class OrderStatusManager:
    TRANSITIONS = {
        "pending":    {"confirm": "confirmed", "cancel": "cancelled"},
        "confirmed":  {"process": "processing", "cancel": "cancelled"},
        "processing": {"ship": "shipped"},
        "shipped":    {"deliver": "delivered", "return": "returned"},
        "delivered":  {"return": "returned"},
    }

    CANCEL_CONDITIONS = {
        "pending": lambda order: True,
        "confirmed": lambda order: (
            order.payment_status == "pending" or
            (order.payment_status == "completed" and
             (datetime.now() - order.confirmed_at).total_seconds() < 3600)
        ),
    }

    def can_cancel(self, order):
        check = self.CANCEL_CONDITIONS.get(order.status)
        return check(order) if check else False

    def get_next_actions(self, order):
        actions = list(self.TRANSITIONS.get(order.status, {}).keys())
        # Filter cancel based on conditions
        if "cancel" in actions and not self.can_cancel(order):
            actions.remove("cancel")
        if order.status not in ["cancelled", "returned"]:
            actions.append("contact_support")
        if order.status == "delivered":
            actions.append("review")
        return actions

    def transition(self, order, action):
        allowed = self.TRANSITIONS.get(order.status, {})
        if action not in allowed:
            return False
        if action == "cancel" and not self.can_cancel(order):
            return False
        if action == "process" and order.payment_status != "completed":
            return False

        order.status = allowed[action]
        setattr(order, f"{action}ed_at", datetime.now())
        return True
```

### HIGH - can_cancel Has Unnecessary Branches
The original `can_cancel` explicitly returns False for processing, shipped, delivered, cancelled, and the else case. These 5 branches can be replaced with a single default `return False`.

**Simplified version:**
```python
def can_cancel(self, order):
    if order.status == "pending":
        return True
    if order.status == "confirmed":
        if order.payment_status == "pending":
            return True
        if order.payment_status == "completed":
            return (datetime.now() - order.confirmed_at).total_seconds() < 3600
    return False
```

This reduces the method from 18 lines to 8 lines with zero nesting depth beyond 1.

### MEDIUM - get_next_actions Duplicates Cancel Logic
The cancel-availability check in `get_next_actions` (payment_status + time check) duplicates `can_cancel`. If the cancellation rules change, both methods must be updated.

**Fix:** Call `can_cancel` from `get_next_actions`:
```python
if self.can_cancel(order):
    actions.append("cancel")
```

### MEDIUM - transition Uses elif Chain Instead of Dispatch
The `transition` method is a long elif chain mapping action names to behavior. This is a natural fit for a dictionary dispatch:
```python
TRANSITION_HANDLERS = {
    "confirm": ("pending", "confirmed", "confirmed_at"),
    "process": ("confirmed", "processing", None),
    "ship": ("processing", "shipped", "shipped_at"),
    "deliver": ("shipped", "delivered", "delivered_at"),
}
```

### LOW - Magic Number for Cancel Window
`3600` (seconds) for the cancel window is a magic number. Extract to a named constant:
```python
CANCEL_WINDOW_SECONDS = 3600  # 1 hour
```'''),

    ("thinking/code-review", r'''Review this code and suggest reducing complexity:

```python
def format_report_data(data, report_type, include_summary=True,
                       include_charts=False, date_format="YYYY-MM-DD",
                       currency="USD", timezone="UTC",
                       group_by=None, sort_by=None, sort_order="asc",
                       filters=None, limit=None, custom_fields=None):

    result = {"type": report_type, "generated_at": datetime.now().isoformat()}

    formatted_items = []
    for item in data:
        formatted = {}

        if report_type == "sales":
            formatted["date"] = format_date(item["date"], date_format, timezone)
            formatted["revenue"] = format_currency(item["amount"], currency)
            formatted["units"] = item["quantity"]
            formatted["product"] = item["product_name"]
            if custom_fields:
                for field in custom_fields:
                    if field in item:
                        formatted[field] = item[field]
        elif report_type == "inventory":
            formatted["product"] = item["name"]
            formatted["sku"] = item["sku"]
            formatted["stock"] = item["quantity"]
            formatted["value"] = format_currency(item["quantity"] * item["price"], currency)
            if custom_fields:
                for field in custom_fields:
                    if field in item:
                        formatted[field] = item[field]
        elif report_type == "customers":
            formatted["name"] = item["full_name"]
            formatted["email"] = item["email"]
            formatted["total_orders"] = item["order_count"]
            formatted["total_spent"] = format_currency(item["total_spent"], currency)
            formatted["joined"] = format_date(item["created_at"], date_format, timezone)
            if custom_fields:
                for field in custom_fields:
                    if field in item:
                        formatted[field] = item[field]
        elif report_type == "performance":
            formatted["metric"] = item["metric_name"]
            formatted["value"] = item["value"]
            formatted["target"] = item["target"]
            formatted["achievement"] = f"{(item['value'] / item['target'] * 100):.1f}%"
            if custom_fields:
                for field in custom_fields:
                    if field in item:
                        formatted[field] = item[field]

        formatted_items.append(formatted)

    if filters:
        for key, value in filters.items():
            formatted_items = [i for i in formatted_items if i.get(key) == value]

    if group_by:
        groups = {}
        for item in formatted_items:
            group_key = item.get(group_by, "Other")
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(item)
        result["groups"] = groups
    else:
        if sort_by:
            formatted_items.sort(
                key=lambda x: x.get(sort_by, ""),
                reverse=(sort_order == "desc")
            )
        if limit:
            formatted_items = formatted_items[:limit]
        result["items"] = formatted_items

    if include_summary:
        # ... 40 more lines of summary calculation per report type

    if include_charts:
        # ... 30 more lines of chart data preparation

    return result
```''', r'''<think>
12 parameters. That is immediately a code smell, but let me figure out which ones actually belong together before suggesting a fix.

Looking at the parameters... report_type, include_summary, include_charts, date_format, currency, timezone -- those are all "how to format" options. group_by, sort_by, sort_order, filters, limit -- those are "how to query/shape" options. custom_fields is a "what extra data to include" option. So there are really three groups: formatting config, query config, and field config. A single ReportOptions dataclass could hold all of these, but honestly two objects (format options + query options) might be cleaner.

Now the bigger problem: the elif chain for report types. Each branch does essentially the same thing -- map source field names to output field names with optional transformations (date formatting, currency formatting). That is data, not logic. If I express the field mappings as a dictionary, adding a fifth report type is just adding another entry instead of another 15-line elif branch.

Wait, I almost missed something -- the custom_fields block is copy-pasted identically four times! It is the exact same three lines in every branch. That should be pulled out after the type-specific formatting, not duplicated inside each branch. This is the lowest-hanging fruit here.

But there is a subtler issue: the filtering happens AFTER formatting. That means if 90% of items get filtered out, we wasted time formatting them. Should filtering happen on the raw data first? That depends on whether filters reference raw field names or formatted field names. Looking at the code... it filters on formatted keys (i.get(key)), so the filters use output field names. That means we cannot easily filter before formatting without knowing the mapping. Hmm, actually we could -- if the field mapping is data, we could reverse-map filter keys to source keys and filter the raw data. But that might be over-engineering for this review. I will flag it as wasteful but suggest the simple fix of just moving the filter before the format step if filters use source field names.

The most critical issue is the god function problem: format, filter, group, sort, limit, summarize, and chart all in one function. Each of those is an independent step in a pipeline. Extracting them into separate functions makes each one testable and the pipeline composable.
</think>

## Code Review: Reduce Complexity

### CRITICAL - 12 Parameters (Excessive Function Signature)
The function takes 12 parameters, most of which are configuration options. This makes the function difficult to call, test, and understand. Callers must remember parameter order and meaning.

**Fix:** Use a parameter object:
```python
@dataclass
class ReportOptions:
    report_type: str
    include_summary: bool = True
    include_charts: bool = False
    date_format: str = "YYYY-MM-DD"
    currency: str = "USD"
    timezone: str = "UTC"
    group_by: Optional[str] = None
    sort_by: Optional[str] = None
    sort_order: str = "asc"
    filters: Optional[Dict] = None
    limit: Optional[int] = None
    custom_fields: Optional[List[str]] = None

def format_report_data(data, options: ReportOptions):
    ...
```

### HIGH - Duplicated Custom Fields Handling
The custom_fields block is copied identically four times (once per report type). Extract it after the type-specific formatting:

```python
# After type-specific formatting
if custom_fields:
    for field in custom_fields:
        if field in item:
            formatted[field] = item[field]
```

### HIGH - Type-Based Branching Should Use Strategy Pattern
Four report types with similar but different field mappings create a long elif chain. Adding a fifth type requires modifying this function.

**Fix:** Define field mappings as data:
```python
FIELD_MAPPINGS = {
    "sales": {
        "date": ("date", "date"),       # (source_field, transform_type)
        "revenue": ("amount", "currency"),
        "units": ("quantity", None),
        "product": ("product_name", None),
    },
    "inventory": {
        "product": ("name", None),
        "sku": ("sku", None),
        "stock": ("quantity", None),
        "value": (lambda item: item["quantity"] * item["price"], "currency"),
    },
    # ...
}

def _format_item(self, item, report_type, options):
    mapping = FIELD_MAPPINGS[report_type]
    formatted = {}
    for output_key, (source, transform) in mapping.items():
        value = source(item) if callable(source) else item.get(source)
        if transform == "date":
            value = format_date(value, options.date_format, options.timezone)
        elif transform == "currency":
            value = format_currency(value, options.currency)
        formatted[output_key] = value
    return formatted
```

### MEDIUM - God Function (Format + Filter + Group + Sort + Summarize + Chart)
The function handles six distinct operations in sequence. Each should be its own method in a pipeline:

```python
def format_report_data(data, options):
    items = [_format_item(item, options) for item in data]
    items = _apply_filters(items, options.filters)
    result = _apply_grouping_or_sorting(items, options)

    if options.include_summary:
        result["summary"] = _compute_summary(items, options)
    if options.include_charts:
        result["charts"] = _prepare_charts(items, options)

    return result
```

### MEDIUM - Filtering After Formatting Is Wasteful
Filters are applied to already-formatted items. If 90% of items are filtered out, the formatting work on those items was wasted. Filter the raw data first:

```python
if filters:
    data = [item for item in data if _matches_filters(item, filters)]
# Then format
items = [_format_item(item, options) for item in data]
```

### LOW - Division by Zero in Performance Report
`item['value'] / item['target'] * 100` will raise ZeroDivisionError if target is 0.

**Fix:** `f"{(item['value'] / item['target'] * 100):.1f}%" if item['target'] else "N/A"`'''),
]
