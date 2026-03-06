"""Phase 3C: Metacognition — Socratic Self-Questioning (Part 9)"""

PAIRS = [
    (
        "thinking/meta-socratic-right-problem-slow-tests",
        r'''Our test suite takes 45 minutes to run. My team lead wants to parallelize the tests across multiple CI machines. Should we?''',
        r'''<think>
Q: Am I solving the right problem? WHY do the tests take 45 minutes?

Q: Is parallelization the first thing to try?
A: No. First find out what's actually slow. Common causes:
  1. Tests hitting a real database instead of mocking (each test = full DB setup/teardown)
  2. Tests making real HTTP requests to external APIs
  3. Sleep/wait statements in tests (someone added `time.sleep(5)` to "fix" a race condition)
  4. Tests not cleaning up — each test leaves state that slows subsequent tests
  5. Rebuilding the entire Docker environment per test
  6. Running ALL tests when only a few files changed

Q: Could we get 10x speedup without parallelization?
A: Very likely:
  - Replace real DB calls with in-memory SQLite or mocks → 10x faster
  - Mock external HTTP calls → removes network latency
  - Remove sleep() calls → immediate
  - Use fixtures with session scope for expensive setup → DB created once
  - Run only affected tests: `pytest --lf` or `pytest -x` for fast feedback

Q: What does parallelization actually solve?
A: It distributes the SAME slow tests across machines. If each test is slow (1 second for a DB test that should be 10ms), parallelization helps but doesn't fix the root cause. 4 machines × 45 min ÷ 4 = ~12 min. But fixing the root cause could get you to 5 min on ONE machine.

Q: What's the cost of parallel CI?
A: 4x the CI machine cost. More complex CI configuration. Test isolation issues (tests that accidentally share state fail randomly in parallel).

Q: What order should we optimize?
A: 1. Profile tests to find the slow ones. 2. Fix the slow tests. 3. THEN parallelize if still too slow.
</think>

**Don't parallelize yet. First find out WHY tests are slow — fixing the root cause is usually 10x more effective.**

**Step 1: Profile your test suite**
```bash
# Find the slowest tests
pytest --durations=20  # Shows 20 slowest tests

# Common finding:
# 3.2s test_user_registration (DB)
# 2.8s test_payment_flow (HTTP)
# 5.0s test_email_delivery (sleep!)
# 2.1s test_export_csv (DB + file I/O)
```

**Step 2: Fix the actual bottlenecks**

| Problem | Fix | Speedup |
|---------|-----|---------|
| Real DB per test | In-memory SQLite or transaction rollback | 10-50x |
| External HTTP calls | `responses` or `httpretty` mocking | 100x |
| `time.sleep()` in tests | Remove, use proper waits | Instant |
| Full Docker rebuild | Cached test containers | 5-10x |
| Expensive fixtures per test | `scope="session"` or `scope="module"` | 10x |

```python
# Before: 3 seconds (real DB)
def test_registration(db):
    user = User.create(name="Alice", email="alice@test.com")
    assert user.id is not None

# After: 30ms (transaction rollback)
@pytest.fixture
def db(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    yield Session(bind=connection)
    transaction.rollback()  # Instant cleanup, no data persists
```

**Step 3: Run only what changed**
```bash
# Only re-run failed tests
pytest --lf

# Only run tests related to changed files
pytest --co -q | grep "test_$(git diff --name-only)"
```

**Step 4: THEN parallelize (if still needed)**
```bash
# pytest-xdist — parallel tests on one machine
pytest -n auto  # Uses all CPU cores
```

**Expected results:**
- Before: 45 min on 1 machine
- After fixing root causes: ~5 min on 1 machine
- With parallelization: ~2 min on 1 machine

Fix the slow tests first. Parallelization on top of efficient tests is the right order.'''
    ),
    (
        "thinking/meta-socratic-blind-spots-pagination",
        r'''I implemented pagination for our API:

```python
@app.route('/products')
def list_products():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    products = Product.query.order_by(Product.id) \
        .offset((page - 1) * per_page) \
        .limit(per_page) \
        .all()

    return jsonify([p.to_dict() for p in products])
```

Standard offset pagination. Any blind spots?''',
        r'''<think>
Q: What am I not considering? Let me check for blind spots.

Q: What if per_page is 1000000?
A: No upper bound on per_page. An attacker sets per_page=1000000 and the query returns all products, potentially crashing the server or causing a timeout. Need a max limit.

Q: What if page is 0 or negative?
A: page=0 → offset = -20 → depends on database behavior. page=-1 → offset = -40 → undefined behavior. Need validation.

Q: What about deep pagination performance?
A: OFFSET 1000000 still scans 1,000,000 rows before returning results. Page 50000 of results is extremely slow. At scale, offset pagination degrades linearly.

Q: Is the ordering stable?
A: ORDER BY id gives stable ordering. Good. But if we were ordering by created_at (which can have duplicates), items could shift between pages.

Q: What if data changes between page requests?
A: User fetches page 1, a new product is inserted, user fetches page 2 → they might see a product that shifted from page 1 to page 2 (duplicate) or miss one that shifted forward.

Q: Is there any metadata?
A: No total count, no next/previous page URLs, no indication of whether more pages exist. The client can't build a proper paginator UI.

Q: What about empty results?
A: page=999999 returns []. No error, no indication this is past the end.

Several usability and security issues.
</think>

**Several blind spots.** Validation, performance, and usability issues:

**Fix 1: Input validation**
```python
@app.route('/products')
def list_products():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # Validate bounds
    page = max(1, page)
    per_page = min(max(1, per_page), 100)  # Cap at 100
```

**Fix 2: Return pagination metadata**
```python
    total = Product.query.count()
    products = Product.query.order_by(Product.id) \
        .offset((page - 1) * per_page) \
        .limit(per_page) \
        .all()

    return jsonify({
        'data': [p.to_dict() for p in products],
        'meta': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page,
            'has_next': page * per_page < total,
        }
    })
```

**Fix 3: For large datasets, use cursor pagination**
```python
# Offset pagination: page 50000 scans 1M rows
# Cursor pagination: always fast regardless of position

@app.route('/products')
def list_products():
    cursor = request.args.get('cursor', type=int)  # Last seen product ID
    limit = min(request.args.get('limit', 20, type=int), 100)

    query = Product.query.order_by(Product.id)
    if cursor:
        query = query.filter(Product.id > cursor)

    products = query.limit(limit + 1).all()  # Fetch one extra
    has_next = len(products) > limit
    products = products[:limit]

    return jsonify({
        'data': [p.to_dict() for p in products],
        'next_cursor': products[-1].id if has_next else None,
    })
```

**Blind spots found:**

| Issue | Impact |
|-------|--------|
| No per_page limit | `per_page=1000000` dumps entire DB |
| No page validation | `page=-1` → undefined behavior |
| No metadata | Client can't build paginator |
| Deep offset performance | Page 50000 scans millions of rows |
| No data stability | Items shift between pages on inserts |'''
    ),
    (
        "thinking/meta-socratic-overengineering-abstraction",
        r'''I'm writing a function to send Slack notifications in our app. I created this abstraction layer:

```python
from abc import ABC, abstractmethod

class NotificationProvider(ABC):
    @abstractmethod
    def send(self, channel, message): ...

class SlackNotifier(NotificationProvider):
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def send(self, channel, message):
        requests.post(self.webhook_url, json={'text': message, 'channel': channel})

class NotificationFactory:
    _providers = {}

    @classmethod
    def register(cls, name, provider_cls):
        cls._providers[name] = provider_cls

    @classmethod
    def create(cls, name, **kwargs):
        return cls._providers[name](**kwargs)

NotificationFactory.register('slack', SlackNotifier)

# Usage:
notifier = NotificationFactory.create('slack', webhook_url=SLACK_WEBHOOK)
notifier.send('#alerts', 'Deploy complete')
```

Is this good architecture for future extensibility?''',
        r'''<think>
Q: Am I over-engineering this? Let me ask some hard questions.

Q: How many notification providers do we have?
A: One. Slack.

Q: How many notification providers will we have in 6 months?
A: Almost certainly still one. MAYBE two. Adding "future extensibility" for a scenario that may never happen.

Q: What does the abstraction layer cost?
A: - ABC class with abstract method
   - Concrete implementation class
   - Factory class with registration
   - 25 lines of code for what should be 5 lines
   - Next developer needs to understand 3 classes to send a Slack message

Q: What does the factory pattern add over just instantiating SlackNotifier directly?
A: The factory adds indirection. Instead of `notifier = SlackNotifier(url)`, we do `notifier = NotificationFactory.create('slack', webhook_url=url)`. This is MORE code, harder to trace, and provides zero benefit with one provider.

Q: If we do add a second provider later, how hard is it to add the abstraction THEN?
A: 15 minutes. Extract the interface when you have two implementations. Don't build it preemptively.

Q: What's the simplest thing that works?
A: A function:
```python
def notify_slack(channel, message):
    requests.post(SLACK_WEBHOOK, json={'text': message, 'channel': channel})
```
One function. Five lines. Everyone understands it.

Q: What would a code reviewer say?
A: "Why are there 3 classes for a single webhook call?"
</think>

**Over-engineered.** You wrote 3 classes for a single webhook call. Here's all you need:

```python
import requests

def notify_slack(channel, message):
    requests.post(SLACK_WEBHOOK, json={'text': message, 'channel': channel})

# Usage:
notify_slack('#alerts', 'Deploy complete')
```

**5 lines instead of 25.** Does the same thing. Everyone understands it instantly.

**Your version's cost:**
- 3 classes to understand (ABC, implementation, factory)
- Factory registration boilerplate
- Indirection: `NotificationFactory.create('slack')` → "where does this go?" → trace through factory → find registration → find class
- All for ONE provider

**When to add the abstraction:**

```python
# When you ACTUALLY have 2 providers (not before):
def notify(channel, message, provider='slack'):
    if provider == 'slack':
        requests.post(SLACK_WEBHOOK, json={'text': message, 'channel': channel})
    elif provider == 'email':
        send_email(channel, message)
```

**When to use the full ABC + Factory pattern:**
- 5+ providers that change at runtime
- Providers loaded from plugins/config
- Different teams own different providers
- Provider selection is dynamic per request

**YAGNI**: You Ain't Gonna Need It. The abstraction takes 15 minutes to add when you actually need it. Don't pay the complexity cost today for a future that may never arrive.'''
    ),
    (
        "thinking/meta-socratic-not-considering-security-api-key",
        r'''I built an internal API for our team. I pass the API key in the URL for simplicity:

```python
@app.route('/api/data')
def get_data():
    api_key = request.args.get('key')
    if api_key != 'team-secret-key-2024':
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify(get_sensitive_data())
```

Usage: `curl https://api.ourapp.com/api/data?key=team-secret-key-2024`

It's just an internal API, so this should be fine, right?''',
        r'''<think>
Q: What am I not considering about security?

Q: Where does the API key in the URL end up?
A:
  1. Browser history — if accessed via browser
  2. Server access logs: `GET /api/data?key=team-secret-key-2024 200`
  3. Proxy/CDN logs — any intermediate proxy logs the full URL
  4. Referrer header — if the page links to another site, the full URL (with key) is sent as the Referrer
  5. Analytics tools — if the page loads Google Analytics or any tracker
  6. Browser bookmarks — users might bookmark the URL with key
  7. Shared terminal history — `curl` command stored in `.bash_history`

Q: Is a hardcoded API key safe?
A: The key is in source code. Anyone with repo access has it. It can't be rotated without code change + deploy.

Q: "Internal API" — is that actually secure?
A: "Internal" often means:
  - Accessible from the office network (but what about VPN users?)
  - Accessible to anyone who knows the URL (is it really firewalled?)
  - Trusted by all team members (until someone leaves the company)

Q: What if someone leaves the team?
A: They know the API key. It's hardcoded. Rotating it requires a code change. Everyone else needs to update their scripts.

Q: Is there any auditing?
A: No way to know WHO made a request — everyone uses the same key.

Even for "internal" APIs, this has multiple security and operational problems.
</think>

**Not fine, even for internal APIs.** API keys in URLs are logged everywhere.

**Where your key gets exposed:**
```
1. Server logs:     GET /api/data?key=team-secret-key-2024 200
2. Proxy/CDN logs:  Full URL with key
3. Browser history: Bookmarks, autocomplete
4. Shell history:   ~/.bash_history contains the curl command
5. Referrer header: Sent to any linked external site
6. Analytics:       Google Analytics sees the full URL
```

**Fix: Use Authorization header**
```python
@app.route('/api/data')
def get_data():
    api_key = request.headers.get('Authorization')
    if not api_key or not verify_key(api_key):
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify(get_sensitive_data())
```

```bash
# Headers are NOT logged by default
curl -H "Authorization: Bearer team-secret-key-2024" https://api.ourapp.com/api/data
```

**Additional fixes:**

```python
import os
import secrets
import hmac

# Don't hardcode — use environment variable
API_KEY = os.environ['API_KEY']

def verify_key(provided_key):
    # Constant-time comparison prevents timing attacks
    expected = f"Bearer {API_KEY}"
    return hmac.compare_digest(provided_key, expected)
```

**For team APIs, consider per-user keys:**
```python
API_KEYS = {
    os.environ['KEY_ALICE']: 'alice',
    os.environ['KEY_BOB']: 'bob',
}

def get_data():
    key = request.headers.get('Authorization', '').replace('Bearer ', '')
    user = API_KEYS.get(key)
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    logger.info(f"API access by {user}")  # Now you know WHO
```

**Why per-user keys matter:**
- **Audit**: Know who accessed what
- **Revocation**: Remove one person's key without affecting others
- **Rotation**: Each user rotates independently'''
    ),
    (
        "thinking/meta-socratic-data-assumption-json-parse",
        r'''I parse JSON API responses like this:

```python
def get_user_info(user_id):
    response = requests.get(f'{API_URL}/users/{user_id}')
    data = response.json()
    return {
        'name': data['user']['profile']['display_name'],
        'email': data['user']['profile']['email'],
        'plan': data['user']['subscription']['plan'],
        'avatar': data['user']['profile']['avatar_url'],
    }
```

Straightforward parsing. Any issues?''',
        r'''<think>
Q: Does my assumption about the data hold? Let me check each access.

Q: What if any nested key is missing?
A: `data['user']['profile']['display_name']` — if 'user' is missing → KeyError. If 'profile' is missing → KeyError. If 'display_name' is missing → KeyError. Four levels of nesting, four chances to crash.

Q: What if the API returns an error?
A: If response.status_code is 404 or 500, response.json() might return `{"error": "not found"}`. Then `data['user']` → KeyError with an unhelpful message.

Q: What if the user has no subscription?
A: `data['user']['subscription']['plan']` — free users might not have a subscription object at all. The API might return `null` for subscription, then `None['plan']` → TypeError.

Q: What if avatar_url is null?
A: The code would return `{'avatar': None}`, which might be fine, but the consumer might try to render it as an image URL.

Q: What if the API changes its response format?
A: Any field rename, nesting change, or schema evolution → crash. No graceful handling.

Q: What should robust parsing look like?
A: Check status code first, use .get() with defaults for optional fields, handle the error case.
</think>

**Fragile.** Four levels of nested key access with no safety — any missing field crashes the entire function.

**What can go wrong:**
```python
# API returns error → KeyError on 'user'
{"error": "User not found", "status": 404}

# Free user has no subscription → TypeError on None['plan']
{"user": {"profile": {...}, "subscription": null}}

# Profile incomplete → KeyError on 'display_name'
{"user": {"profile": {"email": "a@b.com"}, "subscription": {...}}}
```

**Robust version:**
```python
def get_user_info(user_id):
    response = requests.get(f'{API_URL}/users/{user_id}', timeout=10)

    if response.status_code != 200:
        raise APIError(f"Failed to fetch user {user_id}: {response.status_code}")

    data = response.json()
    user = data.get('user', {})
    profile = user.get('profile', {})
    subscription = user.get('subscription', {})

    return {
        'name': profile.get('display_name', 'Unknown'),
        'email': profile.get('email'),
        'plan': subscription.get('plan', 'free') if subscription else 'free',
        'avatar': profile.get('avatar_url'),
    }
```

**Improvements:**
1. **Status code check** — don't parse error responses as data
2. **`timeout=10`** — don't hang forever if API is down
3. **`.get()` with defaults** — graceful handling of missing fields
4. **`if subscription`** — handles `null` subscription object
5. **Sensible defaults** — 'Unknown' name, 'free' plan instead of crashing

**For critical data, validate with Pydantic:**
```python
from pydantic import BaseModel
from typing import Optional

class Profile(BaseModel):
    display_name: str = 'Unknown'
    email: Optional[str] = None
    avatar_url: Optional[str] = None

class Subscription(BaseModel):
    plan: str = 'free'

class UserData(BaseModel):
    profile: Profile = Profile()
    subscription: Optional[Subscription] = None

# Validates and provides defaults automatically
user = UserData(**data.get('user', {}))
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
