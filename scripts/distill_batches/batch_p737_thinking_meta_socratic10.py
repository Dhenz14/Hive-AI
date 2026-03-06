"""Phase 3C: Metacognition — Socratic Self-Questioning (Part 10)"""

PAIRS = [
    (
        "thinking/meta-socratic-silent-failure-cron",
        r'''I set up a cron job to run our daily report generator:

```bash
0 6 * * * cd /app && python generate_report.py
```

The script runs daily at 6 AM. Simple and reliable, right?''',
        r'''<think>
Q: Could this fail silently?

Q: Where does the output go?
A: Nowhere. Cron captures stdout/stderr and emails it to the user — but most servers don't have a local mail agent configured. If the script crashes, the error vanishes.

Q: What if the script fails?
A: No one knows until someone asks "where's today's report?" hours later.

Q: What if the script takes too long?
A: If yesterday's run is still going at 6 AM, a new instance starts. Now two copies run simultaneously — potential data corruption, duplicate reports, resource exhaustion.

Q: What if the server reboots?
A: Cron is persistent (survives reboots). But if the server is down at 6 AM, the job is SKIPPED. Cron doesn't run missed jobs.

Q: What environment does cron use?
A: Cron runs with a minimal environment — no PATH, no virtualenv, no environment variables from .bashrc. `python` might not resolve, or it might use the wrong Python. `requests` import might fail because virtualenv isn't activated.

Q: What if there's a problem with the report data?
A: The script generates a report but there's no validation that the report is correct or complete.

Multiple silent failure modes.
</think>

**Multiple silent failure modes.** Here's what goes wrong:

**Issue 1: No output capture → errors vanish**
```bash
# Fix: redirect output to log file
0 6 * * * cd /app && /app/venv/bin/python generate_report.py >> /var/log/reports.log 2>&1
```

**Issue 2: No failure notification**
```bash
# Fix: alert on failure
0 6 * * * cd /app && /app/venv/bin/python generate_report.py 2>&1 || curl -X POST https://hooks.slack.com/... -d '{"text":"Report generation FAILED"}'
```

**Issue 3: Wrong environment (most common cron issue)**
```bash
# BAD: cron has minimal PATH, no virtualenv
0 6 * * * python generate_report.py

# GOOD: absolute paths everywhere
0 6 * * * cd /app && /app/venv/bin/python generate_report.py
```

**Issue 4: Overlapping runs**
```bash
# Fix: use flock to prevent concurrent execution
0 6 * * * flock -n /tmp/report.lock /app/venv/bin/python /app/generate_report.py
```

**Issue 5: Missed runs (server down at 6 AM)**
```bash
# Cron does NOT run missed jobs. Use anacron for catch-up:
# Or add a startup check in the application
```

**Better approach — wrapper script:**
```bash
#!/bin/bash
# run_report.sh
set -euo pipefail
cd /app
source /app/venv/bin/activate

flock -n /tmp/report.lock python generate_report.py \
    >> /var/log/reports.log 2>&1

if [ $? -ne 0 ]; then
    curl -s -X POST "$SLACK_WEBHOOK" \
        -d '{"text":"Daily report generation FAILED. Check /var/log/reports.log"}'
fi
```

```bash
# crontab
0 6 * * * /app/run_report.sh
```

**For production, consider a proper scheduler:**
- Celery Beat (Python ecosystem)
- Airflow (complex data pipelines)
- systemd timers (better logging than cron)'''
    ),
    (
        "thinking/meta-socratic-anchored-kubernetes",
        r'''I'm deploying my Django app (single service, PostgreSQL, Redis) for a startup with 100 daily users. I want to set up Kubernetes for deployment. Should I?''',
        r'''<think>
Q: Am I anchored on Kubernetes because it's the "industry standard"?

Q: What does Kubernetes actually provide?
A: Container orchestration, auto-scaling, self-healing, service discovery, rolling deployments, config management. These are for running MANY services at SCALE.

Q: What do I have?
A: ONE Django service, PostgreSQL, Redis. 100 daily users. This is a single-server application.

Q: What does K8s cost for this setup?
A:
  - Learning curve: weeks to months to do K8s properly
  - Cluster management: 3 nodes minimum for HA (even managed K8s like EKS/GKE)
  - Infrastructure cost: K8s control plane + 3 nodes ≈ $150-300/month minimum
  - Operational overhead: YAML manifests, Helm charts, ingress controllers, cert-manager, monitoring

Q: What's the cheapest alternative?
A: A single $10/month VPS with Docker Compose:
  ```yaml
  services:
    web:
      build: .
      ports: ["80:8000"]
    db:
      image: postgres:16
    redis:
      image: redis:7
  ```
  Total monthly cost: $10. Time to deploy: 1 hour.

Q: When would K8s be justified?
A: - Multiple services needing independent scaling
   - Auto-scaling based on traffic (thousands of users, variable load)
   - Team of 5+ DevOps engineers
   - Multiple environments (dev, staging, prod) with complex configs
   - Compliance requiring high availability

Q: At 100 users/day, what matters more than K8s?
A: Product-market fit, user acquisition, feature development. Infrastructure should be boring and invisible.
</think>

**No. Kubernetes for 100 daily users is like hiring a fleet of trucks to deliver one pizza.**

**What Kubernetes costs you:**

| Concern | Kubernetes | Single VPS |
|---------|-----------|------------|
| Monthly cost | $150-300+ (3 nodes) | $10-20 |
| Setup time | Days-weeks | 1 hour |
| Learning curve | Months | Minimal |
| YAML to maintain | Hundreds of lines | 30 lines |
| Debugging | Complex (pods, nodes, ingress) | `docker logs web` |

**What you actually need:**

```yaml
# docker-compose.yml — your entire infrastructure
services:
  web:
    build: .
    command: gunicorn myapp.wsgi -w 4 -b 0.0.0.0:8000
    env_file: .env
    depends_on: [db, redis]

  db:
    image: postgres:16
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: myapp

  redis:
    image: redis:7-alpine

  caddy:
    image: caddy:2
    ports: ["80:80", "443:443"]
    volumes: [./Caddyfile:/etc/caddy/Caddyfile]

volumes:
  pgdata:
```

```
# Caddyfile — automatic HTTPS
myapp.com {
    reverse_proxy web:8000
}
```

**Deploy:**
```bash
ssh myserver "cd /app && git pull && docker compose up -d --build"
```

**Scaling path:**
1. **100 users**: Single VPS + Docker Compose ($10/mo)
2. **10,000 users**: Bigger VPS or managed DB ($50-100/mo)
3. **100,000 users**: Multiple servers + load balancer ($200-500/mo)
4. **1,000,000+ users**: NOW consider Kubernetes

Don't build infrastructure for 1M users when you have 100. Build the product.'''
    ),
    (
        "thinking/meta-socratic-testing-integration-mock",
        r'''Should I mock the database in my tests or use a real test database? Here's what I'm debating:

```python
# Option A: Mock everything
def test_create_user(mocker):
    mock_db = mocker.patch('app.db.session')
    create_user('Alice', 'alice@test.com')
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()

# Option B: Real test database
def test_create_user(test_db):
    create_user('Alice', 'alice@test.com')
    user = User.query.filter_by(email='alice@test.com').first()
    assert user is not None
    assert user.name == 'Alice'
```

Which is better?''',
        r'''<think>
Q: Am I testing what matters? Let me think about what each approach actually verifies.

Q: What does the mock test prove?
A: That `db.session.add()` and `db.session.commit()` are called. But NOT:
  - That the User object was created correctly
  - That the data was actually inserted
  - That database constraints work (unique email, NOT NULL)
  - That the SQL generated by the ORM is correct
  - That the function works at all

Q: What does the real DB test prove?
A: That calling create_user actually creates a user with the correct data in the database. This tests the BEHAVIOR, not the implementation.

Q: What if I change the implementation?
A: Mock test: If I refactor create_user to use `bulk_insert_mappings` instead of `session.add()`, the mock test FAILS even though the code works perfectly. I'm testing HOW, not WHAT.

Real DB test: If I refactor the implementation, the test still passes because it checks the RESULT, not the method calls.

Q: Are there performance concerns with real DB tests?
A: Yes, but manageable:
  - Use SQLite in-memory for speed (:memory:)
  - Or use PostgreSQL with transaction rollback per test
  - Faster than people think: 100 tests with real DB ≈ 5 seconds

Q: When ARE mocks appropriate?
A: For external services you don't control:
  - HTTP APIs (don't hit real Stripe in tests)
  - Email services (don't send real emails)
  - Third-party webhooks
  NOT for your own database — that's part of your system.

Q: What's the best approach?
A: Real DB for your own data layer, mocks for external services.
</think>

**Use the real test database (Option B).** It tests behavior, not implementation details.

**Why Option A (mocking) is worse:**
```python
# This "test" passes but proves nothing about correctness:
mock_db.add.assert_called_once()
# ✅ add() was called — but was the User object correct? Unknown.
# ✅ commit() was called — but did the data actually persist? Unknown.

# Worse: this test BREAKS on correct refactoring:
# Refactor create_user to use bulk_insert_mappings → test fails
# even though the code works perfectly
```

**Why Option B (real DB) is better:**
```python
# This test proves the function WORKS:
user = User.query.filter_by(email='alice@test.com').first()
assert user is not None       # User actually exists
assert user.name == 'Alice'   # With correct data

# Bonus: catches real issues:
# - Unique constraint violations
# - NOT NULL violations
# - Wrong column types
# - ORM mapping errors
```

**Performance trick — transaction rollback:**
```python
@pytest.fixture
def test_db(app):
    with app.app_context():
        db.create_all()
        yield db
        db.session.rollback()  # Instant cleanup, no data persists
        db.drop_all()
```

**When to mock vs real:**

| Layer | Approach |
|-------|----------|
| Your database | Real test DB |
| Your code | Real code |
| External APIs (Stripe, SendGrid) | Mock |
| File system | Usually real (tmpdir fixture) |
| Time/dates | Mock (freeze_time) |
| Network calls | Mock (responses library) |

**Rule**: Mock at system boundaries (external services), not at internal boundaries (your own database).'''
    ),
    (
        "thinking/meta-socratic-coupling-hardcoded-urls",
        r'''In my React app, I call API endpoints directly in components:

```jsx
function UserProfile({ userId }) {
    const [user, setUser] = useState(null);

    useEffect(() => {
        fetch(`https://api.myapp.com/v1/users/${userId}`)
            .then(res => res.json())
            .then(data => setUser(data));
    }, [userId]);

    const handleDelete = () => {
        fetch(`https://api.myapp.com/v1/users/${userId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
    };

    return <div>{user?.name}</div>;
}
```

This is in 30+ components. Is there an issue?''',
        r'''<think>
Q: Am I introducing tight coupling? Let me check.

Q: What's hardcoded across 30+ components?
A:
  1. Base URL: `https://api.myapp.com` — can't switch between local/staging/prod
  2. API version: `/v1/` — upgrading to v2 requires changing 30+ files
  3. Auth header logic: `localStorage.getItem('token')` — repeated everywhere
  4. Error handling: none — what if the fetch fails?
  5. Response parsing: `.then(res => res.json())` — no status code check

Q: What happens when the API URL changes?
A: Find and replace across 30+ files. Miss one → broken component in production.

Q: What happens when auth changes (cookies instead of localStorage)?
A: Change auth header logic in 30+ files.

Q: What about error handling?
A: No error handling in any of the 30+ components. Token expired? Network error? 500 response? Silent failure in every component.

Q: What's the fix?
A: Centralized API client. Define the base URL, auth, and error handling once.

This is textbook tight coupling — 30+ components directly depend on URL structure, auth mechanism, and error handling.
</think>

**Yes.** You have the same URL, auth logic, and (missing) error handling hardcoded 30+ times. Any change requires updating every component.

**Problems:**
- **Base URL**: Can't switch environments (local/staging/prod)
- **Auth header**: `localStorage.getItem('token')` repeated 30+ times
- **Error handling**: None — expired tokens, network errors are silent
- **API version**: `/v1/` hardcoded everywhere

**Fix: Centralized API client**

```javascript
// api/client.js
const API_BASE = process.env.REACT_APP_API_URL || 'https://api.myapp.com/v1';

async function apiClient(endpoint, options = {}) {
    const token = localStorage.getItem('token');

    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...(token && { 'Authorization': `Bearer ${token}` }),
            ...options.headers,
        },
    });

    if (response.status === 401) {
        // Token expired — redirect to login
        localStorage.removeItem('token');
        window.location.href = '/login';
        return;
    }

    if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
    }

    return response.json();
}

// api/users.js
export const getUser = (id) => apiClient(`/users/${id}`);
export const deleteUser = (id) => apiClient(`/users/${id}`, { method: 'DELETE' });
```

```jsx
// Component — clean and simple
import { getUser, deleteUser } from '../api/users';

function UserProfile({ userId }) {
    const [user, setUser] = useState(null);

    useEffect(() => {
        getUser(userId).then(setUser).catch(console.error);
    }, [userId]);

    const handleDelete = () => deleteUser(userId);

    return <div>{user?.name}</div>;
}
```

**What this centralizes:**
| Concern | Before (30+ files) | After (1 file) |
|---------|-------------------|--------------||
| Base URL | Hardcoded everywhere | `API_BASE` config |
| Auth header | Repeated | Automatic |
| Error handling | None | Centralized (401 redirect) |
| API version | `/v1/` in every URL | One place |
| Switching auth method | 30+ file changes | 1 file change |'''
    ),
    (
        "thinking/meta-socratic-not-considering-i18n",
        r'''I'm building a SaaS app targeting international users. I'm handling user-facing strings like this:

```python
def get_error_message(error_code):
    messages = {
        'INVALID_EMAIL': 'Please enter a valid email address',
        'PASSWORD_TOO_SHORT': 'Password must be at least 8 characters',
        'USER_NOT_FOUND': 'No account found with that email',
        'PAYMENT_FAILED': 'Your payment could not be processed. Please try again.',
        'LIMIT_EXCEEDED': f'You have exceeded your limit of {PLAN_LIMIT} items',
    }
    return messages.get(error_code, 'An unexpected error occurred')
```

Clean and simple. Anything I'm not considering?''',
        r'''<think>
Q: What am I not considering?

Q: The app targets "international users" — are all messages in English?
A: Yes. Every string is hardcoded in English. International users who don't speak English can't use the app effectively.

Q: Is adding i18n later hard?
A: Yes, very. Extracting strings from across the entire codebase is tedious. It's much easier to use a translation framework from the start, even if you only have English initially.

Q: What about the f-string with PLAN_LIMIT?
A: `f'You have exceeded your limit of {PLAN_LIMIT} items'` — in other languages, the number might go in a different position. String interpolation needs to support variable placement: "Вы превысили лимит в {limit} элементов" vs "{limit} items exceeded."

Q: What about pluralization?
A: "8 characters" in English, but many languages have different plural forms for 1, 2-4, 5-20, etc. Russian has 3 plural forms. Arabic has 6. Simple string interpolation can't handle this.

Q: What about text direction?
A: Arabic and Hebrew are right-to-left. This affects the entire UI layout, not just strings.

Q: What about number and date formatting?
A: "1,000.50" in English = "1.000,50" in German = "1 000,50" in French. Dates: MM/DD/YYYY (US) vs DD/MM/YYYY (Europe).

Q: Is the string approach even the right pattern?
A: Error codes should go to the client, which handles display and translation. The backend should return error CODES, not messages. This separates concerns and enables client-side i18n.

Multiple internationalization blind spots.
</think>

**For an international SaaS, hardcoded English strings will be a major problem.** Here's what you're not considering:

**Issue 1: Backend shouldn't return display strings**
```python
# BAD: Backend returns English text
return {'error': 'Please enter a valid email address'}

# GOOD: Backend returns error code, client handles display
return {'error': {'code': 'INVALID_EMAIL', 'params': {}}}
# Client translates based on user's locale
```

**Issue 2: Set up i18n framework early** (even with just English)
```python
# Flask-Babel approach:
from flask_babel import gettext as _

messages = {
    'INVALID_EMAIL': _('Please enter a valid email address'),
    'PASSWORD_TOO_SHORT': _('Password must be at least %(min)d characters',
                            min=8),
    'LIMIT_EXCEEDED': _('You have exceeded your limit of %(limit)d items',
                        limit=PLAN_LIMIT),
}
```

**Issue 3: Pluralization varies by language**
```python
# English: "1 item", "2 items" (2 forms)
# Russian: "1 элемент", "2 элемента", "5 элементов" (3 forms)
# Arabic: 6 plural forms

# Use ngettext for plurals:
from flask_babel import ngettext
msg = ngettext('%(num)d item', '%(num)d items', count, num=count)
```

**Issue 4: Number and date formatting**
```python
# "1,000.50" (English) vs "1.000,50" (German)
from babel.numbers import format_currency
format_currency(1000.50, 'USD', locale='de_DE')  # "1.000,50 $"
```

**Recommended approach for international SaaS:**
1. Return error CODES from backend, not strings
2. Client-side translation with react-i18next or similar
3. Use ICU message format for complex interpolation
4. Set up extraction pipeline early (even with just English)
5. Store user's preferred locale in their profile

The cost of adding i18n later to an app with hardcoded strings across 100 files is enormous. Set up the framework now.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
