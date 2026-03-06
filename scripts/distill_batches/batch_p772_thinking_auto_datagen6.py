r'''Phase 4A: Self-Improvement — Training Data Generation (Part 6)

Generate and evaluate training pairs for code quality topics.
Each answer creates 3 graded training pairs with quality analysis.
'''

PAIRS = [
    (
        "thinking/auto-datagen-code-review",
        r'''Generate 3 high-quality training pairs that teach code review best practices. For each pair, explain why it's effective training data.''',
        r'''<think>
To create effective training data for code review, I need to consider:
1. Common misconceptions: focusing only on style, not reviewing for design, being too harsh or too lenient, rubber-stamping reviews
2. Real scenarios: reviewing a pull request, giving actionable feedback, handling disagreements
3. Difficulty progression: identifying issues in code -> writing constructive feedback -> reviewing architecture and design decisions

Code review is both a technical and interpersonal skill, so the training pairs should cover both dimensions.
</think>

Here are 3 training pairs for code review best practices:

**Pair 1 (Beginner):**
```
Q: I've been asked to review a pull request for the first time. What should I look for, and how do I structure my feedback?

A: Focus your review on these layers, from most to least important:

**1. Correctness (Critical)**
- Does the code actually solve the problem described in the PR?
- Are there edge cases that are not handled (null inputs, empty collections, concurrent access)?
- Are error conditions handled gracefully?

**2. Security (Critical)**
- Is user input validated before use?
- Are there SQL injection, XSS, or path traversal vulnerabilities?
- Are secrets or sensitive data exposed in logs?

**3. Design (Important)**
- Is the code in the right place architecturally?
- Are responsibilities clearly separated?
- Will this be easy to modify when requirements change?

**4. Readability (Important)**
- Can you understand the code without the PR description?
- Are variable and function names descriptive?
- Are complex sections commented with "why" not "what"?

**5. Style (Minor)**
- Let automated tools (linters, formatters) handle this. Do not spend review time on bracket placement or import ordering.

**Structuring feedback:**
- Prefix comments with severity: "nit:", "suggestion:", "concern:", "blocker:"
- Always explain WHY something is a problem, not just that it is
- Suggest a fix when possible: "Consider using a dict lookup instead of this if/elif chain because..."
- Acknowledge what is done well: "Nice use of a context manager here"
```
**Why this works:** It provides a prioritized checklist that prevents the common mistake of spending review time on style while missing bugs. The severity prefixes are immediately actionable and reduce ambiguity in review comments.

**Pair 2 (Intermediate):**
```
Q: Here is a function from a pull request I am reviewing. What feedback would you give?

def process_data(data, type, format="json"):
    if type == "user":
        result = []
        for item in data:
            if item["active"] == True:
                user = {"name": item["first_name"] + " " + item["last_name"],
                        "email": item["email"]}
                if format == "json":
                    result.append(json.dumps(user))
                elif format == "csv":
                    result.append(f"{user['name']},{user['email']}")
        return result
    elif type == "order":
        result = []
        for item in data:
            if item["status"] != "cancelled":
                order = {"id": item["order_id"], "total": item["amount"]}
                if format == "json":
                    result.append(json.dumps(order))
                elif format == "csv":
                    result.append(f"{order['id']},{order['total']}")
        return result

A: Here is the review feedback I would provide:

**blocker: KeyError risk** — accessing item["active"], item["first_name"], etc. without checking if keys exist. If any item is missing a key, this crashes. Use item.get("active", False) or validate the input schema.

**concern: `type` shadows a Python builtin** — the parameter name `type` shadows Python's built-in type() function. Use `data_type` or `record_kind` instead.

**concern: Boolean comparison** — `if item["active"] == True` should be `if item["active"]` or, if the value might not be a bool, `if item.get("active") is True`.

**suggestion: Extract the formatting logic** — the format handling (JSON vs CSV) is duplicated in both branches. Extract it:

def serialize(record, format):
    if format == "json":
        return json.dumps(record)
    elif format == "csv":
        return ",".join(str(v) for v in record.values())
    raise ValueError(f"Unsupported format: {format}")

**suggestion: Use list comprehension** — the pattern of building a list with a loop and conditional is a textbook case for a comprehension or filter+map.

**nit: Missing type hints** — adding type hints would make the expected input structure clearer:
def process_data(data: list[dict], data_type: str, format: str = "json") -> list[str]:

This review covers correctness (KeyError), naming (shadowing builtins), DRY principle (duplicated formatting), and maintainability (type hints) in priority order.
```
**Why this works:** It demonstrates review skills on real (flawed) code rather than discussing review in the abstract. The severity prefixes show how to prioritize feedback. The suggestions include concrete replacement code, modeling the "suggest a fix" best practice.

**Pair 3 (Advanced):**
```
Q: A senior engineer submitted a PR that refactors the authentication module. The code works correctly and passes all tests, but you have concerns about the architectural approach. They chose to implement a custom JWT validation library instead of using a well-maintained open-source one. How do you handle this review?

A: This requires balancing technical judgment with interpersonal skill. Here is the approach:

**1. Start with genuine questions, not accusations:**
"I want to understand the reasoning behind the custom JWT library. Could you share what requirements led to this choice over existing libraries like PyJWT or python-jose?"

Possible valid reasons: unique algorithm requirements, avoiding a dependency with known CVEs, performance constraints, or organizational policy against certain licenses.

**2. If the reason is not compelling, articulate the risk:**
"concern: Custom cryptographic code carries long-term maintenance risk. The JWT spec has edge cases (algorithm confusion attacks, key ID handling, clock skew) that mature libraries have already addressed through years of security audits. If we maintain our own implementation, we become responsible for tracking and patching these vulnerabilities ourselves.

Specifically, I notice the current implementation does not handle:
- Algorithm confusion (accepting 'none' algorithm)
- Token expiration clock skew tolerance
- JWK key rotation via JWKS endpoints

These are not theoretical — they are exploited in the wild."

**3. Propose a concrete alternative:**
"Would it work to use PyJWT for the core validation and wrap it in a thin adapter that enforces our specific requirements (allowed algorithms, required claims, audience validation)? This gives us the customization we need without reimplementing cryptographic verification."

**4. Know when to escalate vs defer:**
- If the risk is security-critical (as it is here), do not approve the PR even if the author is senior. Request a security review.
- If you are overruled after presenting your case, document your concerns in the PR comments and move on. The record matters.

**5. Never make it personal:**
Frame everything as "the code" and "the risk," never as "you made a bad decision." The goal is to make the codebase better, not to win an argument.
```
**Why this works:** It addresses the hardest part of code review — disagreeing with senior colleagues on design decisions. The scenario is specific (custom JWT vs library), the concerns are technically grounded (algorithm confusion attacks), and the communication strategy models professional engineering culture. This teaches judgment, not just mechanics.

**Quality assessment:**
- Concept coverage: Review checklist and prioritization, concrete code feedback with severity levels, architectural review and interpersonal communication
- Realism: Progresses from "my first review" to "reviewing real code" to "navigating a design disagreement" — genuine skill progression
- Difficulty curve: Learning what to look for -> applying it to real code -> handling the social complexity of senior-level design review'''
    ),
    (
        "thinking/auto-datagen-refactoring",
        r'''Generate 3 high-quality training pairs that teach refactoring techniques. For each pair, explain why it's effective training data.''',
        r'''<think>
For refactoring training data, I need to consider:
1. Common misconceptions: refactoring means rewriting, refactoring without tests, big-bang refactors, refactoring for fun rather than need
2. Real scenarios: extracting functions from long methods, replacing conditionals with polymorphism, simplifying nested logic
3. Difficulty progression: simple extract method -> structural refactoring patterns -> safe large-scale refactoring strategies

Each pair should show before and after code with clear motivation for why the refactoring improves the code.
</think>

Here are 3 training pairs for refactoring techniques:

**Pair 1 (Beginner):**
```
Q: This function is 80 lines long and does too many things. How do I break it down?

def process_order(order_data):
    # Validate order
    if not order_data.get("items"):
        raise ValueError("Order must have items")
    if not order_data.get("customer_id"):
        raise ValueError("Order must have customer_id")
    for item in order_data["items"]:
        if item["quantity"] <= 0:
            raise ValueError(f"Invalid quantity for {item['product_id']}")

    # Calculate totals
    subtotal = 0
    for item in order_data["items"]:
        price = get_product_price(item["product_id"])
        subtotal += price * item["quantity"]
    tax = subtotal * 0.08
    shipping = 5.99 if subtotal < 50 else 0
    total = subtotal + tax + shipping

    # Create order record
    order = {
        "id": generate_order_id(),
        "customer_id": order_data["customer_id"],
        "items": order_data["items"],
        "subtotal": subtotal,
        "tax": tax,
        "shipping": shipping,
        "total": total,
        "status": "pending"
    }
    db.orders.insert(order)

    # Send notifications
    customer = db.customers.find(order_data["customer_id"])
    send_email(customer["email"], "Order Confirmed", f"Order {order['id']}...")
    notify_warehouse(order)

    return order

A: Apply "Extract Method" refactoring. Each comment block is a natural function boundary:

def process_order(order_data):
    validate_order(order_data)
    totals = calculate_totals(order_data["items"])
    order = create_order_record(order_data, totals)
    send_order_notifications(order)
    return order

def validate_order(order_data):
    if not order_data.get("items"):
        raise ValueError("Order must have items")
    if not order_data.get("customer_id"):
        raise ValueError("Order must have customer_id")
    for item in order_data["items"]:
        if item["quantity"] <= 0:
            raise ValueError(f"Invalid quantity for {item['product_id']}")

def calculate_totals(items):
    subtotal = sum(get_product_price(i["product_id"]) * i["quantity"] for i in items)
    tax = subtotal * 0.08
    shipping = 5.99 if subtotal < 50 else 0
    return {"subtotal": subtotal, "tax": tax, "shipping": shipping,
            "total": subtotal + tax + shipping}

def create_order_record(order_data, totals):
    order = {"id": generate_order_id(), "customer_id": order_data["customer_id"],
             "items": order_data["items"], **totals, "status": "pending"}
    db.orders.insert(order)
    return order

def send_order_notifications(order):
    customer = db.customers.find(order["customer_id"])
    send_email(customer["email"], "Order Confirmed", f"Order {order['id']}...")
    notify_warehouse(order)

**Why this is better:**
- Each function has a single responsibility and is testable in isolation
- The main function reads like a high-level description of the process
- calculate_totals can be unit tested without a database or email service
- The existing comments literally told you where to extract — comments that describe "what" a block does are a smell indicating the block should be a function
```
**Why this works:** The before/after pattern is the most effective way to teach refactoring. The original code has a clear smell (long function with section comments), and the refactored version shows how comments become function names. The point about comments revealing extraction boundaries is a valuable meta-insight.

**Pair 2 (Intermediate):**
```
Q: This code has deeply nested conditionals that are hard to follow. How do I flatten it?

def get_shipping_rate(order):
    if order.destination_country == "US":
        if order.is_prime_member:
            if order.total > 25:
                return 0  # Free shipping
            else:
                return 3.99
        else:
            if order.total > 50:
                return 0  # Free shipping
            else:
                if order.weight > 10:
                    return 12.99
                else:
                    return 7.99
    else:
        if order.destination_country in SUPPORTED_COUNTRIES:
            if order.weight > 5:
                return 24.99
            else:
                return 14.99
        else:
            raise UnsupportedCountryError(order.destination_country)

A: Two techniques to flatten nested conditionals:

**Technique 1: Guard clauses (early returns)**
Handle edge cases first, then the main logic:

def get_shipping_rate(order):
    if order.destination_country not in SUPPORTED_COUNTRIES | {"US"}:
        raise UnsupportedCountryError(order.destination_country)

    if order.destination_country != "US":
        return 24.99 if order.weight > 5 else 14.99

    # US domestic shipping
    free_threshold = 25 if order.is_prime_member else 50
    if order.total > free_threshold:
        return 0

    if order.is_prime_member:
        return 3.99
    return 12.99 if order.weight > 10 else 7.99

**Technique 2: Table-driven logic** (when conditions are data, not behavior)

SHIPPING_RULES = [
    {"country": "US", "prime": True,  "min_total": 25, "rate": 0},
    {"country": "US", "prime": True,  "min_total": 0,  "rate": 3.99},
    {"country": "US", "prime": False, "min_total": 50, "rate": 0},
    {"country": "US", "prime": False, "min_total": 0,  "max_weight": 10, "rate": 7.99},
    {"country": "US", "prime": False, "min_total": 0,  "rate": 12.99},
]

This is beneficial when the rules change frequently — product managers can update a configuration table without modifying code logic.

**When to use which:**
- Guard clauses: when there are 2-3 special cases and one main path
- Table-driven: when the logic is pure data mapping and rules change often
- Strategy pattern: when each branch has complex behavior, not just a return value
```
**Why this works:** It shows two different solutions to the same problem, teaching that refactoring is about choosing the right technique for the situation. The decision criteria at the end build judgment, not just mechanical skill.

**Pair 3 (Advanced):**
```
Q: We need to refactor a large legacy module (3000 lines, no tests, tightly coupled to the database). How do we do this safely without breaking production?

A: Use the "Strangler Fig" pattern combined with characterization tests. Here is the step-by-step strategy:

**Phase 1: Add characterization tests (1-2 weeks)**
Before changing any code, write tests that capture the current behavior, including bugs:

def test_process_order_with_valid_data():
    """Characterization test — documents existing behavior."""
    result = process_order(SAMPLE_ORDER)
    # Assert whatever the current code actually returns
    # Even if the behavior seems wrong, assert it
    assert result["tax"] == 7.99  # Tax calc may be wrong, but this is current behavior

Run the legacy code against many inputs, record the outputs, and turn them into assertions. You are not testing correctness — you are creating a safety net for refactoring.

**Phase 2: Extract seams (1-2 weeks)**
Identify coupling points and introduce interfaces without changing behavior:

# Before: function directly queries the database
def get_user_orders(user_id):
    return db.query("SELECT * FROM orders WHERE user_id = ?", user_id)

# After: inject the dependency
def get_user_orders(user_id, order_repo=None):
    if order_repo is None:
        order_repo = DatabaseOrderRepo()  # Default preserves old behavior
    return order_repo.get_by_user(user_id)

This makes the function testable without a database while keeping the default behavior identical.

**Phase 3: Parallel implementation**
Build the new module alongside the old one. Route a percentage of traffic through both and compare results:

def process_order(order_data):
    old_result = legacy_process_order(order_data)
    try:
        new_result = new_process_order(order_data)
        if old_result != new_result:
            log.warning("Result mismatch", old=old_result, new=new_result)
    except Exception as e:
        log.error("New implementation failed", error=e)
    return old_result  # Always return old result until verified

**Phase 4: Gradual cutover**
Once the new implementation matches the old one for 2+ weeks with zero mismatches, switch the return to new_result. Keep the comparison running for another week, then remove the old code.

**Key principle:** At no point do you do a "big bang" replacement. Every step is independently deployable and reversible.
```
**Why this works:** It addresses the hardest refactoring scenario — large legacy code with no tests. The Strangler Fig pattern, characterization tests, and parallel running are battle-tested techniques. The phased approach with reversibility at each step teaches risk management, which is the real skill in large-scale refactoring.

**Quality assessment:**
- Concept coverage: Extract method, guard clauses, table-driven logic, characterization tests, strangler fig pattern, dependency injection, parallel running
- Realism: Progresses from "break up a long function" to "flatten nested conditionals" to "safely refactor a legacy monolith" — the exact challenges developers face as they advance
- Difficulty curve: Mechanical extraction -> choosing between refactoring strategies -> managing risk in large-scale rewrites'''
    ),
    (
        "thinking/auto-datagen-tdd",
        r'''Generate 3 high-quality training pairs that teach test-driven development. For each pair, explain why it's effective training data.''',
        r'''<think>
For TDD training data, I need to consider:
1. Common misconceptions: TDD means writing tests after code, TDD requires 100% coverage, TDD slows you down, TDD only works for simple functions
2. Real scenarios: implementing a feature TDD-style, testing code with external dependencies, knowing when TDD is and is not appropriate
3. Difficulty progression: basic red-green-refactor cycle -> testing with mocks and dependencies -> TDD for complex features

I should show the actual red-green-refactor cycle step by step, not just the final test and code.
</think>

Here are 3 training pairs for test-driven development:

**Pair 1 (Beginner):**
```
Q: Explain the TDD red-green-refactor cycle by implementing a function that validates email addresses. Show each step.

A: TDD follows three steps: write a failing test (Red), make it pass with minimal code (Green), then improve the code (Refactor). Let us walk through it:

**Red — Write the first failing test:**
def test_valid_email():
    assert validate_email("user@example.com") is True

Run it: NameError: name 'validate_email' is not defined. Good — this is Red.

**Green — Write minimal code to pass:**
def validate_email(email):
    return True

The test passes. Yes, the implementation is absurd. That is the point — we let tests drive the design.

**Red — Add the next test to force better logic:**
def test_email_without_at_sign():
    assert validate_email("userexample.com") is False

Run it: FAIL — validate_email returns True for everything.

**Green — Make both tests pass:**
def validate_email(email):
    return "@" in email

**Red — Push further:**
def test_email_without_domain():
    assert validate_email("user@") is False

def test_email_with_multiple_at_signs():
    assert validate_email("user@@example.com") is False

**Green:**
def validate_email(email):
    parts = email.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts
    return bool(local) and "." in domain

**Refactor — Clean up while tests stay green:**
import re

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

Run all tests — still green. The refactor is safe because the tests verify behavior.

**Key insight:** Each test added one new constraint. The implementation grew organically to satisfy all constraints. You never wrote more code than the tests required.
```
**Why this works:** It shows the actual iterative cycle with multiple red-green-refactor iterations, not just the final result. The "absurd" first implementation (return True) demonstrates the discipline of writing minimal code. Most TDD tutorials skip the messy middle steps, but that is where learning happens.

**Pair 2 (Intermediate):**
```
Q: How do I apply TDD when my code needs to call an external API? I am building a function that fetches a user's GitHub repositories and returns the ones with more than 100 stars.

A: Use dependency injection and mocking to isolate external dependencies. Here is the TDD approach:

**Step 1: Define the interface, not the implementation**
Write tests that describe WHAT the function does, not HOW it fetches data:

def test_filters_repos_by_star_count():
    mock_client = Mock()
    mock_client.get_repos.return_value = [
        {"name": "popular-lib", "stars": 500},
        {"name": "side-project", "stars": 12},
        {"name": "another-hit", "stars": 200},
    ]

    result = get_popular_repos("octocat", github_client=mock_client)

    assert len(result) == 2
    assert result[0]["name"] == "popular-lib"
    assert result[1]["name"] == "another-hit"

def test_returns_empty_list_for_user_with_no_popular_repos():
    mock_client = Mock()
    mock_client.get_repos.return_value = [
        {"name": "tiny-project", "stars": 3},
    ]

    result = get_popular_repos("newuser", github_client=mock_client)
    assert result == []

def test_handles_api_error_gracefully():
    mock_client = Mock()
    mock_client.get_repos.side_effect = ConnectionError("API down")

    with pytest.raises(GitHubUnavailableError):
        get_popular_repos("octocat", github_client=mock_client)

**Step 2: Implement to pass the tests:**
class GitHubUnavailableError(Exception):
    pass

def get_popular_repos(username, github_client=None, min_stars=100):
    if github_client is None:
        github_client = GitHubClient()  # Real client as default
    try:
        repos = github_client.get_repos(username)
    except ConnectionError:
        raise GitHubUnavailableError(f"Could not reach GitHub API")
    return [r for r in repos if r["stars"] >= min_stars]

**Step 3: Write a separate integration test** (not part of TDD cycle, runs less frequently):
@pytest.mark.integration
def test_real_github_api():
    result = get_popular_repos("torvalds")
    assert len(result) > 0  # Torvalds definitely has popular repos

**Key principle:** TDD tests are fast and deterministic. They never call real APIs, databases, or file systems. Integration tests verify the real connections but run separately.
```
**Why this works:** It solves the number one obstacle to TDD adoption — "but my code calls external services." The dependency injection approach is shown through the test design itself, which teaches that TDD naturally leads to better architecture. The separation of unit and integration tests is a critical concept.

**Pair 3 (Advanced):**
```
Q: When should I NOT use TDD? Are there cases where writing tests first is counterproductive?

A: TDD is powerful but not universal. Here are cases where it adds friction without proportional value:

**TDD works best for:**
- Business logic with clear inputs and outputs (pricing, validation, data transformation)
- Bug fixes (write a test that reproduces the bug, then fix it — guaranteed regression protection)
- API design (tests force you to think about the caller's perspective)
- Algorithmic code where edge cases matter

**TDD is less effective for:**

1. **Exploratory/prototype code** — When you do not know what you are building yet. If you are experimenting with a new library or spiking a proof of concept, writing tests first locks you into a design prematurely. Instead: prototype without tests, then write tests before promoting to production.

2. **UI layout and styling** — TDD cannot tell you whether a button looks right. Visual regression tests (screenshot comparison) work better here. Test behavior (click handler fires), not appearance.

3. **Framework glue code** — If a function just calls framework.configure(settings), testing it just tests the framework. Example:
   def create_app():
       app = Flask(__name__)
       app.config.from_object(Config)
       return app
   A test for this adds no value. Test the routes and behavior instead.

4. **One-time scripts** — A migration script that runs once and is deleted does not benefit from a full TDD cycle. Manual verification is acceptable.

5. **Code where requirements are genuinely unknown** — If the product manager says "we will figure it out as we go," spending time on tests for features that may be cut next week is waste. Write characterization tests after the design stabilizes.

**The pragmatic approach:**
- Use TDD for core domain logic (always)
- Use test-after for infrastructure and glue code (write tests, but after implementation)
- Use no tests for prototypes and spikes (but set a deadline to either add tests or delete the code)
- Never use "we're moving fast" as a permanent excuse — it is valid for a sprint, not a quarter
```
**Why this works:** Most TDD content is advocacy. This pair honestly addresses limitations, which builds trust and teaches judgment. The categorization of when to use TDD vs test-after vs no-tests gives a practical framework rather than dogma. The closing note about "moving fast" being a temporary exception is important for team culture.

**Quality assessment:**
- Concept coverage: Red-green-refactor cycle, mocking external dependencies, dependency injection, integration vs unit tests, when TDD is and is not appropriate
- Realism: Progresses from "learn the cycle" to "handle real-world complexity" to "develop judgment about when to apply TDD" — this matches actual practitioner growth
- Difficulty curve: Mechanical TDD on a pure function -> TDD with external dependencies -> strategic judgment about testing approaches'''
    ),
    (
        "thinking/auto-datagen-design-patterns",
        r'''Generate 3 high-quality training pairs that teach design patterns, including when to use and when to avoid them. For each pair, explain why it's effective training data.''',
        r'''<think>
For design patterns training data, I need to consider:
1. Common misconceptions: patterns are always good, more patterns = better code, patterns from the GoF book apply directly to modern languages, forcing patterns where they do not fit
2. Real scenarios: recognizing when a pattern solves a real problem, simplifying over-engineered code, choosing between patterns
3. Difficulty progression: understanding common patterns with examples -> recognizing when to apply them -> knowing when patterns hurt more than they help

The key is to teach patterns as tools for specific problems, not as goals in themselves.
</think>

Here are 3 training pairs for design patterns (when to use/avoid):

**Pair 1 (Beginner):**
```
Q: I keep seeing the Strategy pattern mentioned. Can you explain it with a practical Python example and tell me when I should actually use it?

A: The Strategy pattern lets you swap algorithms at runtime without changing the code that uses them. In Python, you often implement it with simple functions rather than classes.

**Real example: Payment processing**
Without Strategy (bad — hard to extend):
def process_payment(amount, method):
    if method == "credit_card":
        # 20 lines of credit card logic
    elif method == "paypal":
        # 20 lines of PayPal logic
    elif method == "crypto":
        # 20 lines of crypto logic
    # Adding a new method means modifying this function

With Strategy (Pythonic version using functions):
def charge_credit_card(amount, details):
    stripe.Charge.create(amount=amount, source=details["token"])

def charge_paypal(amount, details):
    paypal.Payment.create(amount=amount, payer=details["payer_id"])

def charge_crypto(amount, details):
    crypto_gateway.send(amount=amount, wallet=details["wallet"])

PAYMENT_STRATEGIES = {
    "credit_card": charge_credit_card,
    "paypal": charge_paypal,
    "crypto": charge_crypto,
}

def process_payment(amount, method, details):
    strategy = PAYMENT_STRATEGIES.get(method)
    if not strategy:
        raise ValueError(f"Unknown payment method: {method}")
    return strategy(amount, details)

Adding a new payment method means writing one function and adding one dictionary entry. The process_payment function never changes.

**When to use Strategy:**
- You have 3+ variants of an algorithm and expect more to be added
- The variants share the same interface (same inputs, same output type)
- You want to select behavior at runtime (user choice, configuration, A/B testing)

**When NOT to use Strategy:**
- You have only 2 variants and they are unlikely to grow — a simple if/else is clearer
- The "strategies" have completely different interfaces — you need something else
- You are using it just because you learned about it — if a simple conditional works, use it
```
**Why this works:** It uses Python's first-class functions instead of the traditional Java class hierarchy, showing that patterns adapt to language features. The "when NOT to use" section is crucial — it teaches restraint and prevents over-engineering.

**Pair 2 (Intermediate):**
```
Q: I am building a notification system that needs to send messages via email, SMS, Slack, and push notifications. Sometimes a single event needs to go to multiple channels. Which design pattern should I use?

A: This problem benefits from combining the Observer pattern (for event subscription) with the Strategy pattern (for channel-specific sending logic).

**Implementation:**

from dataclasses import dataclass
from typing import Protocol

class NotificationChannel(Protocol):
    def send(self, recipient: str, message: str) -> bool: ...

class EmailChannel:
    def send(self, recipient: str, message: str) -> bool:
        return smtp_client.send(to=recipient, body=message)

class SlackChannel:
    def send(self, recipient: str, message: str) -> bool:
        return slack_client.post_message(channel=recipient, text=message)

class SMSChannel:
    def send(self, recipient: str, message: str) -> bool:
        return twilio_client.send(to=recipient, body=message[:160])

@dataclass
class NotificationPreference:
    user_id: str
    channels: list[str]  # ["email", "slack"]

class NotificationService:
    def __init__(self):
        self._channels = {
            "email": EmailChannel(),
            "slack": SlackChannel(),
            "sms": SMSChannel(),
        }

    def notify(self, user_id: str, message: str):
        prefs = self._get_preferences(user_id)
        results = {}
        for channel_name in prefs.channels:
            channel = self._channels[channel_name]
            contact = self._get_contact(user_id, channel_name)
            results[channel_name] = channel.send(contact, message)
        return results

**Why this design works:**
- Adding a new channel (e.g., Microsoft Teams) means writing one class and registering it — open/closed principle
- Users control which channels they receive on — subscription logic is separate from sending logic
- Each channel handles its own formatting (SMS truncates to 160 chars) — single responsibility
- The Protocol class provides type safety without inheritance

**What I did NOT use and why:**
- Abstract Factory: overkill here — we are not creating families of related objects
- Decorator pattern: would add unnecessary layering for this use case
- Mediator: adds complexity when direct channel invocation is straightforward
```
**Why this works:** It shows pattern selection as a design decision, explaining both what was chosen and what was rejected. The Protocol-based approach demonstrates modern Python patterns. Including user preferences shows how patterns interact with business requirements.

**Pair 3 (Advanced):**
```
Q: A colleague's PR introduces the Abstract Factory pattern, the Builder pattern, and a Facade, all to handle configuration loading from JSON, YAML, and environment variables. The implementation is 400 lines across 12 classes. The existing code was a 60-line function. Is this over-engineered?

A: Almost certainly yes. Here is how to evaluate:

**Signs of over-engineering:**
1. **Class count vs behavior count** — 12 classes for 3 input formats suggests each format spawned a factory, a builder, a product, and a facade wrapper. But loading configuration from a file is not complex enough to warrant this.

2. **The "what if we need to add more" fallacy** — The argument for Abstract Factory is usually "what if we add XML, TOML, INI formats later?" But configuration loading is not the core business logic — it runs once at startup. Even if you add 5 more formats, a dictionary dispatch is sufficient:

   LOADERS = {
       ".json": json.load,
       ".yaml": yaml.safe_load,
       ".toml": tomllib.load,
   }

   def load_config(path: str) -> dict:
       ext = Path(path).suffix
       loader = LOADERS.get(ext)
       if not loader:
           raise ValueError(f"Unsupported config format: {ext}")
       with open(path, 'rb' if ext == '.toml' else 'r') as f:
           config = loader(f)
       # Override with environment variables
       for key, value in os.environ.items():
           if key.startswith("APP_"):
               config[key.removeprefix("APP_").lower()] = value
       return config

   This is 15 lines, handles all formats, and is trivially extensible.

3. **The test tells the story** — If the test setup for the new code requires constructing multiple factories and builders just to load a YAML file, the abstraction is not serving the user of the code.

**How to give this feedback constructively:**
"The implementation handles all the formats correctly, and I can see the extensibility thinking behind the factory structure. However, I think the configuration loading use case is simple enough that a lighter approach would be easier to maintain. Since we load config once at startup and the behavior per format is essentially one function call, could we simplify to a dispatch table? I put together a sketch in this comment — what do you think?"

**The rule of three:**
Do not introduce a pattern until you have three concrete examples of the problem it solves. One format does not justify Strategy. Two formats do not justify Abstract Factory. Three or more formats might justify a simple dispatch — but probably still not a class hierarchy.
```
**Why this works:** It teaches the hardest design pattern skill — knowing when NOT to use one. The concrete comparison (400 lines vs 15 lines) makes the cost of over-engineering visceral. The constructive feedback example shows how to push back on over-engineering without dismissing the colleague's thinking. The "rule of three" gives a memorable heuristic.

**Quality assessment:**
- Concept coverage: Strategy pattern implementation, combining patterns for real problems, recognizing and addressing over-engineering
- Realism: Progresses from "learn a pattern" to "choose patterns for a real system" to "critique pattern misuse" — the actual arc of design pattern mastery
- Difficulty curve: Understanding and applying a pattern -> selecting and combining patterns -> recognizing when patterns hurt and pushing back'''
    ),
    (
        "thinking/auto-datagen-tech-debt",
        r'''Generate 3 high-quality training pairs that teach technical debt management. For each pair, explain why it's effective training data.''',
        r'''<think>
For technical debt management training data, I need to consider:
1. Common misconceptions: all tech debt is bad, tech debt should always be paid off immediately, tech debt is just messy code, tech debt tracking is unnecessary
2. Real scenarios: identifying and categorizing debt, making the business case for addressing debt, balancing feature work with debt reduction
3. Difficulty progression: recognizing tech debt -> tracking and prioritizing it -> building organizational processes for managing it

This topic bridges technical and organizational skills, so the pairs should cover both.
</think>

Here are 3 training pairs for technical debt management:

**Pair 1 (Beginner):**
```
Q: What exactly is technical debt, and how do I recognize it in a codebase? Can you give concrete examples?

A: Technical debt is the implied cost of future rework caused by choosing an expedient solution now instead of a better approach that would take longer. Like financial debt, it accrues "interest" — the longer it exists, the more it slows you down.

**Types of technical debt with examples:**

1. **Deliberate, prudent** — "We know this is not ideal, but we need to ship by Friday. We will fix it next sprint."
   Example: Hardcoding a feature flag instead of building a proper feature flag system. Acceptable if you actually schedule the follow-up.

2. **Deliberate, reckless** — "We do not have time for tests."
   Example: Skipping input validation because "only internal users will use this API." Then external partners get access six months later.

3. **Inadvertent, prudent** — "Now I know how this should have been designed."
   Example: After building an event system, realizing it should have used an event bus instead of direct function calls. This is natural learning.

4. **Inadvertent, reckless** — "What is a design pattern?"
   Example: Copy-pasting the same database query logic into 30 different endpoints because the developer did not know about the repository pattern.

**How to recognize tech debt in code:**
- Functions or classes that everyone is afraid to touch
- Areas where bugs keep recurring after fixes
- Code that requires reading a "tribal knowledge" doc to understand
- Tests that are skipped or commented out
- TODO comments older than 6 months
- Workarounds that reference tickets that were never completed
- Build times or test suites that have grown unreasonably slow

**Key insight:** Not all tech debt is bad. Taking on deliberate, prudent debt to meet a real deadline is a legitimate engineering decision — as long as you track it and plan to address it.
```
**Why this works:** The 2x2 matrix (deliberate/inadvertent x prudent/reckless) from Martin Fowler gives a framework for categorizing debt, which is more useful than just listing examples. The "how to recognize" checklist is immediately actionable for any developer looking at an unfamiliar codebase.

**Pair 2 (Intermediate):**
```
Q: Our team has a lot of technical debt but management says we cannot spend time on it because we need to ship features. How do I make the business case for addressing tech debt?

A: You need to translate technical debt into business terms. Managers do not care about "clean code" — they care about velocity, reliability, and cost.

**Step 1: Quantify the impact**
Track these metrics over 2-4 weeks:
- Time to implement a feature in the debt-heavy module vs a clean module
- Number of production incidents caused by the debt-heavy area
- Developer onboarding time (how long until a new hire can contribute to the module)
- Number of times a "simple change" required unexpected additional work

Present it concretely: "Adding payment support for a new country takes 3 weeks in our current payment module. In our newer catalog module with similar complexity, equivalent features take 4 days. The difference is tech debt."

**Step 2: Reframe debt as a feature tax**
Every feature you build costs more because of debt. If the payment module is 3x slower to modify, every feature roadmap item that touches payments takes 3x longer. This is a permanent tax on all future development.

"If we spend 2 sprints reducing debt in the payment module, every payment feature for the next 2 years ships 60% faster. That is equivalent to adding an extra engineer to the team."

**Step 3: Propose a sustainable approach, not a big rewrite**
Managers rightly fear multi-month refactoring projects. Instead, propose:
- **20% rule:** Dedicate 20% of each sprint to debt reduction (1 day per week per developer)
- **Boy Scout rule:** Every PR that touches a debt-heavy area must leave it slightly better
- **Debt sprints:** One sprint per quarter focused entirely on debt reduction
- **Attach to features:** When a feature requires changing a debt-heavy module, budget extra time to clean up as you go

**Step 4: Track and report progress**
Create a tech debt backlog with estimated "interest cost" per item. Report monthly:
- Items resolved and time saved
- Remaining high-impact debt items
- Incident count in debt-heavy vs clean modules

This makes debt work visible and builds trust that the time is well spent.
```
**Why this works:** It addresses the organizational challenge, which is the actual bottleneck in most teams. The quantification approach (measuring the "tax") converts an abstract concern into concrete business impact. The sustainable approaches (20% rule, Boy Scout rule) are more realistic than requesting dedicated refactoring sprints.

**Pair 3 (Advanced):**
```
Q: We have a monolithic Django application with 200+ models, no service boundaries, and circular dependencies between apps. The team wants to migrate to microservices to address the debt. Is this the right approach, and if so, how?

A: Microservices migration is one of the most commonly attempted and commonly failed tech debt projects. Before committing, evaluate whether the monolith's problems actually require microservices.

**First, diagnose the real problems:**
- Circular dependencies between apps -> This is a modularity problem, not a deployment problem. Microservices with circular dependencies are even worse than a monolith with them.
- Slow deployments -> Can be solved with better CI/CD without splitting the codebase.
- Team scaling issues -> This IS a valid reason for microservices, if teams need to deploy independently.

**If you do proceed, use the Modular Monolith as a stepping stone:**

Phase 1: Enforce module boundaries within the monolith (3-6 months)
- Define domain boundaries: which models and logic belong together?
- Create internal APIs between modules (function calls, not HTTP — yet):
  # Instead of: from orders.models import Order (direct import)
  # Use: order_data = order_service.get_order(order_id) (service layer)
- Eliminate circular dependencies by introducing shared interfaces
- Each module gets its own database schema (separate Django apps with explicit foreign keys only through IDs, not ORM relations)

Phase 2: Extract the first service (2-3 months)
- Choose the module with the least incoming dependencies and the clearest boundary
- Common good candidates: notifications, billing, user authentication
- Run it alongside the monolith using the Strangler Fig pattern
- Keep the database shared initially, then split the data

Phase 3: Iterate for remaining services (ongoing)
- Extract one service per quarter at most
- Each extraction must prove its value before starting the next
- Stop extracting when the remaining monolith is manageable

**Warning signs this migration will fail:**
- The team lacks DevOps maturity (no CI/CD, no container orchestration, no monitoring) — microservices require excellent infrastructure
- The architecture has no clear domain boundaries — you will just create a "distributed monolith"
- The team is too small (fewer than 15-20 engineers) — microservices add coordination overhead that small teams cannot absorb
- Management expects it to be done in 3 months — realistic timeline is 1-2 years

**The uncomfortable truth:** Most tech debt in monoliths can be addressed by better modularization without microservices. The modular monolith (Phase 1) often solves 80% of the pain, and many teams stop there because the remaining 20% does not justify the operational complexity of distributed systems.
```
**Why this works:** It challenges the assumption that microservices solve tech debt problems, which is one of the most expensive mistakes teams make. The phased approach with the modular monolith as a stepping stone is battle-tested advice. The warning signs section helps teams avoid starting a migration that will fail. The "uncomfortable truth" ending is the kind of honest guidance that builds real engineering judgment.

**Quality assessment:**
- Concept coverage: Recognizing and categorizing debt, making the business case, quantifying impact, sustainable reduction strategies, large-scale debt migration planning
- Realism: Progresses from "what is tech debt" to "convince my manager to fix it" to "plan a major architectural migration" — the full lifecycle of tech debt management
- Difficulty curve: Individual recognition -> organizational advocacy -> strategic architecture decisions'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
