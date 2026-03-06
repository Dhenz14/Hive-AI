"""Phase 1F: Foundation Thinking — Testing Strategy (Part 4/4)
Testing patterns for specific domains: security testing, performance testing, data pipeline testing."""

PAIRS = [
    (
        "thinking/testing-security-testing",
        "How do I write automated security tests? I don't want to rely solely on manual pentesting.",
        r'''<think>
Automated security testing categories:
1. Authentication/authorization tests (access control)
2. Input validation tests (injection prevention)
3. OWASP Top 10 specific tests
4. Dependency vulnerability scanning
5. Secret detection

These can all be part of the regular test suite and CI pipeline.
</think>

Integrate security tests into your regular test suite:

## 1. Authentication Tests

```python
class TestAuthentication:
    def test_login_returns_token(self, client):
        response = client.post('/api/auth/login', json={
            'email': 'alice@example.com', 'password': 'correct_password',
        })
        assert response.status_code == 200
        assert 'access_token' in response.json()

    def test_wrong_password_returns_401(self, client):
        response = client.post('/api/auth/login', json={
            'email': 'alice@example.com', 'password': 'wrong',
        })
        assert response.status_code == 401
        # Must NOT reveal whether email exists
        assert 'Invalid credentials' in response.json()['message']

    def test_expired_token_rejected(self, client):
        expired_token = create_token(user_id=1, expires_in=timedelta(seconds=-1))
        response = client.get('/api/users/me',
                              headers={'Authorization': f'Bearer {expired_token}'})
        assert response.status_code == 401

    def test_tampered_token_rejected(self, client):
        token = create_token(user_id=1)
        tampered = token[:-5] + 'XXXXX'
        response = client.get('/api/users/me',
                              headers={'Authorization': f'Bearer {tampered}'})
        assert response.status_code == 401
```

## 2. Authorization Tests (IDOR Prevention)

```python
class TestAuthorization:
    def test_user_cannot_access_other_users_data(self, client, user_a_token, user_b):
        response = client.get(f'/api/users/{user_b.id}/orders',
                              headers={'Authorization': f'Bearer {user_a_token}'})
        assert response.status_code == 403

    def test_non_admin_cannot_access_admin_endpoints(self, client, user_token):
        response = client.get('/api/admin/users',
                              headers={'Authorization': f'Bearer {user_token}'})
        assert response.status_code == 403

    def test_unauthenticated_cannot_access_protected_endpoints(self, client):
        protected_endpoints = [
            ('GET', '/api/users/me'),
            ('POST', '/api/orders'),
            ('DELETE', '/api/users/1'),
        ]
        for method, path in protected_endpoints:
            response = client.open(path, method=method)
            assert response.status_code == 401, f"{method} {path} should require auth"
```

## 3. Injection Prevention

```python
class TestInjectionPrevention:
    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE users; --",
        "' OR '1'='1",
        "1; SELECT * FROM information_schema.tables",
        "' UNION SELECT password FROM users--",
    ])
    def test_sql_injection_prevented(self, client, auth_headers, payload):
        response = client.get(f'/api/search?q={payload}', headers=auth_headers)
        assert response.status_code in (200, 400)
        assert User.query.count() > 0  # Table still exists

    @pytest.mark.parametrize("payload", [
        '<script>alert("xss")</script>',
        '<img onerror="alert(1)" src=x>',
        'javascript:alert(1)',
    ])
    def test_xss_prevented(self, client, auth_headers, payload):
        client.post('/api/comments', json={'text': payload}, headers=auth_headers)
        response = client.get('/api/comments', headers=auth_headers)
        body = response.get_data(as_text=True)
        assert '<script>' not in body
        assert 'onerror=' not in body
```

## 4. Rate Limiting

```python
def test_login_rate_limited(self, client):
    for i in range(10):
        client.post('/api/auth/login', json={
            'email': 'alice@example.com', 'password': 'wrong',
        })
    response = client.post('/api/auth/login', json={
        'email': 'alice@example.com', 'password': 'wrong',
    })
    assert response.status_code == 429
```

## 5. CI Pipeline Security Checks

```yaml
# .github/workflows/security.yml
security:
  steps:
    - run: pip-audit                      # Known vulnerable dependencies
    - run: bandit -r src/                 # Python security linter
    - run: gitleaks detect                # Hardcoded secrets
    - run: safety check                   # Dependency CVEs
    - run: pytest tests/security/ -v      # Custom security tests
```'''
    ),
    (
        "thinking/testing-performance-testing",
        "How do I add performance tests to our CI pipeline? I want to catch performance regressions before they reach production.",
        r'''<think>
Performance testing in CI:
1. Benchmark critical operations with pytest-benchmark
2. Set performance budgets (max response time, max memory)
3. Compare against baselines (fail if >10% regression)
4. Load testing with locust for API endpoints

Key: performance tests should be deterministic. Run on consistent hardware (CI runner), compare relative to baseline, not absolute numbers.
</think>

## 1. Microbenchmarks with pytest-benchmark

```python
import pytest

def test_search_performance(benchmark, db_session):
    """Search must complete in <50ms for 10K records."""
    # Setup: create realistic data volume
    for i in range(10_000):
        db_session.add(Product(name=f'Product {i}', price=i * 1.5))
    db_session.commit()

    # Benchmark the actual operation
    result = benchmark(search_products, query='Product 500', limit=20)

    assert len(result) == 20
    # pytest-benchmark automatically tracks min/max/mean/stddev

def test_serialization_performance(benchmark):
    """Serialize 1000 orders in <100ms."""
    orders = [make_order() for _ in range(1000)]
    result = benchmark(lambda: [serialize_order(o) for o in orders])
    assert len(result) == 1000
```

```bash
pytest tests/benchmarks/ --benchmark-autosave
# Saves results to .benchmarks/ for comparison

pytest tests/benchmarks/ --benchmark-compare
# Compare against previous runs — highlights regressions
```

## 2. Response Time Budgets

```python
def test_api_response_time(client, auth_headers):
    """Critical endpoints must respond in <200ms."""
    import time

    endpoints = [
        ('GET', '/api/users/me'),
        ('GET', '/api/orders?page=1'),
        ('GET', '/api/products?q=widget'),
    ]

    for method, path in endpoints:
        start = time.perf_counter()
        response = client.open(path, method=method, headers=auth_headers)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 200, f"{method} {path} took {elapsed_ms:.0f}ms (budget: 200ms)"
```

## 3. Memory Usage Tests

```python
import tracemalloc

def test_batch_processing_memory():
    """Processing 100K records should use <500MB."""
    tracemalloc.start()

    process_batch(generate_records(100_000))

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak / 1024 / 1024
    assert peak_mb < 500, f"Peak memory: {peak_mb:.0f}MB (budget: 500MB)"
```

## 4. Load Testing with Locust (Pre-Deploy)

```python
# locustfile.py
from locust import HttpUser, task, between

class ApiUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        response = self.client.post('/api/auth/login', json={
            'email': 'loadtest@example.com', 'password': 'test123',
        })
        self.token = response.json()['access_token']

    @task(3)
    def browse_products(self):
        self.client.get('/api/products',
                        headers={'Authorization': f'Bearer {self.token}'})

    @task(1)
    def create_order(self):
        self.client.post('/api/orders', json={'product_id': 1, 'quantity': 1},
                         headers={'Authorization': f'Bearer {self.token}'})
```

```bash
locust -f locustfile.py --headless -u 100 -r 10 --run-time 60s
# 100 concurrent users, ramp up 10/sec, run for 60 seconds
# Fails if p95 > 500ms or error rate > 1%
```

## CI Integration

```yaml
performance:
  steps:
    - run: pytest tests/benchmarks/ --benchmark-compare --benchmark-compare-fail=mean:10%
    # Fail if any benchmark regressed >10% from baseline
```'''
    ),
    (
        "thinking/testing-data-pipeline-testing",
        "How do I test ETL/data pipelines? The data transformations are complex and we keep getting data quality issues in production.",
        r'''<think>
Data pipeline testing needs:
1. Schema validation (input/output schemas match expectations)
2. Transformation correctness (business logic in transforms)
3. Edge cases in data (nulls, duplicates, malformed records)
4. Idempotency (running pipeline twice gives same result)
5. Data quality assertions (completeness, uniqueness, referential integrity)
6. Volume testing (handles production-scale data)
</think>

Test data pipelines at three levels: **schema, transform logic, and data quality**.

## 1. Schema Validation (Catch Format Issues Early)

```python
import pandera as pa
from pandera import Column, Check

# Define expected schemas
raw_schema = pa.DataFrameSchema({
    "user_id": Column(int, Check.gt(0)),
    "event_type": Column(str, Check.isin(["click", "purchase", "view"])),
    "timestamp": Column(pa.DateTime),
    "amount": Column(float, Check.ge(0), nullable=True),
})

output_schema = pa.DataFrameSchema({
    "user_id": Column(int, Check.gt(0)),
    "daily_revenue": Column(float, Check.ge(0)),
    "event_count": Column(int, Check.gt(0)),
    "date": Column(pa.DateTime),
})

def test_raw_data_matches_schema():
    df = load_raw_events("2024-01-15")
    raw_schema.validate(df)  # Raises if schema violated

def test_output_matches_schema():
    raw = make_raw_events(n=100)
    result = transform_events(raw)
    output_schema.validate(result)
```

## 2. Transform Logic Tests

```python
def test_revenue_aggregation():
    raw = pd.DataFrame([
        {"user_id": 1, "event_type": "purchase", "timestamp": "2024-01-15", "amount": 50.0},
        {"user_id": 1, "event_type": "purchase", "timestamp": "2024-01-15", "amount": 30.0},
        {"user_id": 1, "event_type": "click",    "timestamp": "2024-01-15", "amount": None},
        {"user_id": 2, "event_type": "purchase", "timestamp": "2024-01-15", "amount": 100.0},
    ])
    result = transform_events(raw)

    user1 = result[result.user_id == 1].iloc[0]
    assert user1.daily_revenue == 80.0
    assert user1.event_count == 3

    user2 = result[result.user_id == 2].iloc[0]
    assert user2.daily_revenue == 100.0

def test_handles_null_amounts():
    raw = pd.DataFrame([
        {"user_id": 1, "event_type": "click", "timestamp": "2024-01-15", "amount": None},
    ])
    result = transform_events(raw)
    assert result.iloc[0].daily_revenue == 0.0  # Null amounts → 0

def test_handles_duplicate_records():
    raw = pd.DataFrame([
        {"user_id": 1, "event_type": "purchase", "timestamp": "2024-01-15 10:00", "amount": 50.0},
        {"user_id": 1, "event_type": "purchase", "timestamp": "2024-01-15 10:00", "amount": 50.0},
    ])
    result = transform_events(raw)
    assert result.iloc[0].daily_revenue == 50.0  # Deduped, not double-counted
```

## 3. Data Quality Assertions

```python
def test_no_data_loss():
    """Every input user_id appears in output."""
    raw = make_raw_events(n=1000)
    result = transform_events(raw)
    assert set(raw.user_id.unique()) == set(result.user_id.unique())

def test_referential_integrity():
    """All user_ids in output exist in users table."""
    result = transform_events(raw_events)
    valid_ids = set(users_df.user_id)
    orphans = set(result.user_id) - valid_ids
    assert len(orphans) == 0, f"Orphaned user_ids: {orphans}"

def test_idempotency():
    """Running pipeline twice produces identical results."""
    raw = make_raw_events(n=100)
    result1 = transform_events(raw)
    result2 = transform_events(raw)
    pd.testing.assert_frame_equal(result1, result2)

def test_completeness():
    """No dates are missing in the output range."""
    result = generate_daily_report(start='2024-01-01', end='2024-01-31')
    dates = result.date.unique()
    expected = pd.date_range('2024-01-01', '2024-01-31')
    missing = set(expected) - set(dates)
    assert len(missing) == 0, f"Missing dates: {missing}"
```

## 4. Great Expectations Integration

```python
import great_expectations as gx

def validate_output(df):
    context = gx.get_context()
    validator = context.sources.pandas_default.read_dataframe(df)

    validator.expect_column_values_to_not_be_null("user_id")
    validator.expect_column_values_to_be_between("daily_revenue", 0, 1_000_000)
    validator.expect_column_values_to_be_unique("user_id")  # One row per user per day
    validator.expect_table_row_count_to_be_between(1, 1_000_000)

    results = validator.validate()
    assert results.success, f"Data quality check failed: {results}"
```'''
    ),
    (
        "thinking/testing-chaos-testing",
        "We want to make our distributed system more resilient. I've heard of chaos engineering but how do we actually start without bringing down production?",
        r'''<think>
Chaos engineering principles:
1. Start small (one service, staging environment)
2. Define steady state (what does "working" look like?)
3. Inject ONE failure at a time
4. Have a kill switch
5. Minimize blast radius
6. Automate gradually

Start in staging/dev, not production. Use tools like toxiproxy, chaos-monkey, or pumba.
</think>

Start in **staging**, with **one failure type at a time**, and always have a kill switch.

## Phase 1: Game Days (Manual, Low Risk)

```
1. Pick ONE failure scenario: "What if Redis is down?"
2. Define steady state: "Orders still process, just slower"
3. Inject the failure: Stop Redis in staging
4. Observe: Does the circuit breaker activate? Do orders queue?
5. Document findings and fix gaps
```

## Phase 2: Automated Fault Injection in Tests

```python
# Use toxiproxy to simulate network failures
import toxiproxy

@pytest.fixture
def flaky_redis():
    """Redis that drops 50% of connections."""
    proxy = toxiproxy.create(
        name="redis",
        listen="localhost:16379",
        upstream="localhost:6379",
    )
    proxy.add_toxic("timeout", type="timeout",
                    attributes={"timeout": 1000},
                    toxicity=0.5)
    yield proxy
    proxy.destroy()

def test_service_degrades_gracefully_with_flaky_redis(flaky_redis, client):
    """Service should return data (possibly stale) even with Redis issues."""
    response = client.get('/api/products')
    assert response.status_code == 200  # Doesn't crash
    # May serve from fallback/DB instead of cache

def test_circuit_breaker_opens_after_failures(flaky_redis, client):
    """After N failures, circuit breaker opens and returns cached data."""
    for _ in range(10):
        client.get('/api/products')

    # Circuit should be open now — subsequent calls should be fast (cached/fallback)
    import time
    start = time.perf_counter()
    response = client.get('/api/products')
    elapsed = time.perf_counter() - start

    assert response.status_code == 200
    assert elapsed < 0.1  # Fast because circuit breaker returns cached
```

## Phase 3: Continuous Chaos in Staging

```python
# Chaos scenarios to rotate through
CHAOS_SCENARIOS = [
    {"type": "kill_pod", "target": "order-service", "duration": "30s"},
    {"type": "network_delay", "target": "payment-service", "latency": "500ms"},
    {"type": "disk_full", "target": "db-service", "percentage": 95},
    {"type": "cpu_stress", "target": "api-gateway", "load": 80},
    {"type": "dns_failure", "target": "external-api", "duration": "60s"},
]

# Run one scenario per day in staging
def run_daily_chaos():
    scenario = random.choice(CHAOS_SCENARIOS)
    inject_failure(scenario)
    time.sleep(scenario['duration'])
    verify_steady_state()  # System recovered?
    restore(scenario)
```

## Chaos Testing Maturity Model

| Level | What | Where |
|-------|------|-------|
| 1. Manual game days | Kill a service, observe | Staging |
| 2. Automated tests | Toxiproxy in CI | CI/Staging |
| 3. Scheduled chaos | Daily random failures | Staging |
| 4. Production chaos | Controlled blast radius | Production (canary) |

**Rules**:
- Always have a kill switch (stop experiment instantly)
- Always define steady state BEFORE the experiment
- Start with the least destructive failure type
- Never inject chaos without monitoring dashboards open'''
    ),
    (
        "thinking/testing-testing-strategy-summary",
        "Give me a complete testing strategy for a typical web application with a Python/Django backend and React frontend. We have 3 developers and limited time.",
        r'''<think>
For a small team, the strategy needs to maximize bug-catching with minimum maintenance. Let me be practical and opinionated about what gives the best ROI.
</think>

## The Pragmatic Testing Strategy for Small Teams

### Test Pyramid (Adjusted for 3 Developers)

```
            ╱  3 E2E  ╲            ← Critical user journeys only
           ╱  20 API   ╲           ← One per endpoint
          ╱  100 Unit    ╲         ← Business logic + edge cases
```

### What to Test (Prioritized)

```
MUST TEST (day 1):
├── Payment processing          ← Money
├── Authentication/authorization ← Security
├── Core business logic         ← Revenue
└── Data transformations        ← Correctness

SHOULD TEST (week 1):
├── API endpoint contracts      ← Integration
├── Database queries            ← Correctness
├── Error handling paths        ← Reliability
└── Input validation            ← Security

NICE TO HAVE (when stable):
├── Edge cases                  ← Robustness
├── Performance benchmarks      ← Speed
└── E2E critical paths          ← User experience
```

### Backend (Django) Setup

```python
# conftest.py
import pytest

@pytest.fixture(autouse=True)
def enable_db_access(db):
    """All tests get database access with transaction rollback."""
    pass

@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()

@pytest.fixture
def authenticated_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client

@pytest.fixture
def user():
    return User.objects.create_user(
        email='test@example.com', password='testpass123'
    )
```

```python
# Test structure
tests/
├── unit/
│   ├── test_pricing.py          # Pure business logic
│   ├── test_validators.py       # Input validation
│   └── test_permissions.py      # Authorization rules
├── integration/
│   ├── test_api_orders.py       # API endpoints
│   ├── test_api_auth.py         # Auth endpoints
│   └── test_queries.py          # Complex DB queries
├── security/
│   ├── test_auth.py             # Token security
│   └── test_injection.py        # SQL/XSS prevention
└── conftest.py
```

### CI Pipeline

```yaml
# .github/workflows/test.yml
test:
  runs-on: ubuntu-latest
  services:
    postgres:
      image: postgres:16
      env: { POSTGRES_DB: test, POSTGRES_PASSWORD: test }
      ports: ["5432:5432"]
  steps:
    - run: pip install -r requirements.txt
    - run: pytest tests/ -x --tb=short -q
      # -x: stop on first failure (fast feedback)
    - run: pytest tests/ --cov=src --cov-fail-under=80
    - run: bandit -r src/          # Security linter
    - run: pip-audit               # Dependency vulnerabilities
```

### What NOT to Do

```
❌ Don't test Django internals (ORM, admin, auth middleware)
❌ Don't test third-party libraries
❌ Don't aim for 100% coverage
❌ Don't write E2E tests for form validation
❌ Don't mock everything — use real DB with rollback
❌ Don't write tests after the fact for stable code (focus on new code)
```

### Testing Cadence

```
Every PR:       Unit + Integration tests (< 3 min)
Daily:          Full suite + security scan
Pre-release:    3 E2E tests + load test baseline
Monthly:        Dependency audit + mutation testing on critical paths
```

**For 3 developers**: ~120 tests total, < 3 min CI, catching 90% of bugs before production. Add more tests as you hit bugs — each production bug becomes a test.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
