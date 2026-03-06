"""Phase 2G: Advanced Reasoning — Abstraction Laddering (Part 3/5)
Move between concrete instances, patterns, principles, and policies:
N+1 query to data access strategy, security incident to threat model,
code smell to design principle, outage to reliability engineering."""

PAIRS = [
    (
        "thinking/abstraction-n1query-to-datastrategy",
        "My Django view is making 100+ database queries to render a single page. I think it's an N+1 query problem. How do I fix it?",
        r'''<think>
Let me climb the abstraction ladder from this specific N+1 bug to a general data access strategy.

CONCRETE LEVEL (the specific bug):
```python
# views.py
def order_list(request):
    orders = Order.objects.all()  # 1 query
    for order in orders:
        print(order.customer.name)     # N queries (1 per order)
        for item in order.items.all(): # N more queries
            print(item.product.name)   # N*M more queries!
    # Total: 1 + N + N + N*M queries
    # With 100 orders and 5 items each: 1 + 100 + 100 + 500 = 701 queries!
```

The fix is straightforward: use select_related/prefetch_related.

PATTERN LEVEL (what are the recurring causes?):
N+1 queries appear whenever:
1. ORM lazy-loads relationships (the default in Django, SQLAlchemy)
2. Code iterates over a collection and accesses related objects
3. Each access triggers a separate SQL query

The pattern: eager loading vs lazy loading.
- Lazy loading: load related data only when accessed (simple but dangerous in loops)
- Eager loading: load related data upfront in the initial query (more complex but efficient)

This isn't just an N+1 fix — it's about having a DATA ACCESS STRATEGY.

PRINCIPLE LEVEL (the underlying principle):
"The number of database queries should be proportional to the number of TYPES of data, not the number of ROWS."

Rendering a page with orders, customers, items, and products should be 3-4 queries regardless of whether there are 10 or 10,000 orders.

This connects to a broader principle: "Minimize round trips to external systems."
Each DB query is a network round trip (~1-5ms). 100 queries = 100-500ms of just network overhead.

POLICY LEVEL (organizational rule):
"Every Django view must use Django Debug Toolbar in development to monitor query count. Any page exceeding 10 queries requires review. N+1 patterns must be caught in code review."
</think>

100+ queries for one page is a classic N+1 problem. Let me fix it and then show you how to prevent it permanently.

**The concrete fix:**

```python
# BEFORE: 701 queries (N+1 pattern)
def order_list(request):
    orders = Order.objects.all()
    # Template accesses: order.customer.name, order.items, item.product

# AFTER: 3 queries (eager loading)
def order_list(request):
    orders = (
        Order.objects
        .select_related('customer')           # JOIN: 1 query for orders+customers
        .prefetch_related(                     # 1 query for items
            Prefetch('items',
                queryset=OrderItem.objects.select_related('product')  # +1 for products
            )
        )
    )
    # Total: 3 queries regardless of how many orders exist
```

**When to use which:**

```python
# select_related: ForeignKey / OneToOne (uses SQL JOIN)
# → One query, but wider rows
Order.objects.select_related('customer')
# SQL: SELECT orders.*, customers.* FROM orders JOIN customers ...

# prefetch_related: ManyToMany / reverse ForeignKey (separate query + Python join)
# → Two queries, assembled in Python
Order.objects.prefetch_related('items')
# SQL 1: SELECT * FROM orders
# SQL 2: SELECT * FROM order_items WHERE order_id IN (1, 2, 3, ...)
# Python: attaches items to their respective orders
```

**Pattern: every view should declare its data needs upfront**

```python
# Create a "query plan" for each view — document what data it needs

# BAD: implicit data access (triggers lazy loads anywhere in template)
def order_detail(request, pk):
    order = Order.objects.get(pk=pk)
    return render(request, 'order_detail.html', {'order': order})

# GOOD: explicit data access (all queries happen here, not in template)
def order_detail(request, pk):
    order = (
        Order.objects
        .select_related('customer', 'shipping_address')
        .prefetch_related(
            'items__product',
            'status_history',
        )
        .get(pk=pk)
    )
    return render(request, 'order_detail.html', {'order': order})
```

**Principle: queries should scale with data types, not row count**

```
Page shows: orders + customers + items + products

WRONG scaling: queries = 1 + N_orders + N_orders + N_items
  10 orders:   ~50 queries
  100 orders:  ~700 queries
  1000 orders: ~7000 queries

RIGHT scaling: queries = 4 (constant)
  10 orders:   4 queries
  100 orders:  4 queries
  1000 orders: 4 queries
```

**Policy: catch N+1 before production**

```python
# settings.py (development)
INSTALLED_APPS += ['debug_toolbar']
# Django Debug Toolbar shows exact query count per page

# Or: use nplusone package to auto-detect
INSTALLED_APPS += ['nplusone.ext.django']
NPLUSONE_RAISE = True  # Crash on N+1 in development!

# In tests: assert query count
from django.test.utils import override_settings

def test_order_list_queries(self):
    create_test_orders(50)
    with self.assertNumQueries(3):  # FAIL if more than 3 queries
        response = self.client.get('/orders/')
```

Add Django Debug Toolbar today, set `assertNumQueries` in your tests, and add `nplusone` to crash on N+1 patterns in development. You'll never ship 700-query pages again.'''
    ),
    (
        "thinking/abstraction-incident-to-threatmodel",
        "We just had a security incident — an attacker used a leaked API key from a public GitHub repo to access our production database. How do we prevent this from happening again?",
        r'''<think>
Let me climb the abstraction ladder from this specific incident to a comprehensive security approach.

CONCRETE LEVEL (the specific incident):
- Developer committed an API key to a public GitHub repo
- Attacker found it (probably via GitHub search or automated scanning)
- API key had database access → attacker accessed production data

Immediate fixes:
1. Rotate the compromised API key
2. Audit what data was accessed
3. Remove the key from git history (git filter-branch or BFG)
4. Revoke the developer's key and issue new one with least privilege

PATTERN LEVEL (what class of vulnerability is this?):
This is a "secret exposure" incident. The pattern:
1. Secrets (API keys, passwords, tokens) mixed with code
2. Code pushed to a place attackers can access
3. No detection mechanism for exposed secrets
4. Secrets have excessive privileges (DB access via an API key?)

Similar incidents:
- .env file committed to git
- AWS keys in Docker images pushed to public registry
- Database passwords in config files committed to repo
- Slack webhook URLs in public repos

The common thread: secrets leak through code distribution channels.

PRINCIPLE LEVEL (the underlying security principles):
1. "Secrets and code must travel through different channels"
   - Code goes through git/CI → can be public
   - Secrets go through secret management → always private
   - They meet at runtime, not at rest

2. "Defense in depth" — multiple layers of protection
   - Even if a secret leaks, the damage should be limited
   - API keys should have minimal permissions (least privilege)
   - Network controls should restrict where keys can be used from
   - Monitoring should detect unusual access patterns

3. "Assume breach" — plan for secrets being compromised
   - Secrets should be rotatable without downtime
   - Access logs should exist to determine blast radius
   - Incident response process should be documented

POLICY LEVEL (organizational security policy):
1. "No secrets in code repositories — enforced by pre-commit hooks and CI scanning"
2. "All secrets managed through [Vault/AWS Secrets Manager/etc.]"
3. "All API keys must have minimum necessary permissions and expire within 90 days"
4. "Secrets rotation must be possible without service downtime"
5. "All data access must be logged and monitored for anomalies"
</think>

This incident reveals a systemic issue, not just a one-time mistake. Let me walk from the immediate fix up to a proper security posture.

**Immediate (today):**

```bash
# 1. Rotate the compromised key NOW
# Every second the old key is active, attacker has access

# 2. Audit what was accessed
# Check database access logs during the exposure window
SELECT usename, client_addr, query_start, query
FROM pg_stat_activity
WHERE usename = 'api_user';
# Also check: pg_stat_user_tables for unusual read counts

# 3. Remove from git history (not just a new commit)
# BFG is faster and simpler than git filter-branch
bfg --replace-text passwords.txt repo.git
# Or: git filter-repo (newer tool)
git filter-repo --invert-paths --path config/secrets.py
```

**Short-term fix — prevent secret commits:**

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
        # Scans for API keys, passwords, tokens in staged files
        # Blocks commit if found

  - repo: https://github.com/zricethezav/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
```

```bash
# Also add to CI pipeline — catches anything pre-commit missed
# .github/workflows/security.yml
- name: Scan for secrets
  uses: gitleaks/gitleaks-action@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Pattern fix — separate secrets from code entirely:**

```python
# WRONG: secrets in code (any of these)
DB_PASSWORD = "super_secret"           # Hardcoded
DB_PASSWORD = os.environ["DB_PASS"]    # Slightly better, but .env gets committed

# RIGHT: secrets from a secrets manager
import boto3

def get_secret(name: str) -> str:
    """Fetch secret from AWS Secrets Manager at runtime."""
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=name)
    return response['SecretString']

# Or for simpler setups: environment variables set by deployment platform
# (Kubernetes secrets, Docker secrets, Heroku config vars)
# NEVER in .env files that could be committed
```

```yaml
# Kubernetes: secrets mounted as environment variables
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
type: Opaque
data:
  DB_PASSWORD: c3VwZXJfc2VjcmV0  # base64 encoded
  API_KEY: YWJjMTIz

---
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - name: app
          envFrom:
            - secretRef:
                name: app-secrets
```

**Principle: defense in depth (assume the secret WILL leak)**

```python
# 1. Least privilege — API key should only access what it needs
# DON'T: one key with full database access
# DO: separate keys per service, read-only where possible

# PostgreSQL: create restricted roles
"""
CREATE ROLE api_readonly;
GRANT CONNECT ON DATABASE myapp TO api_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO api_readonly;
-- This role can't DELETE, UPDATE, or DROP anything
"""

# 2. Network restrictions — key only works from your servers
# AWS: IAM policy with source IP condition
# Database: pg_hba.conf restricts which IPs can connect

# 3. Monitoring — detect unusual access
"""
-- Alert on: unusual query patterns, bulk data export, new source IPs
CREATE EXTENSION pg_audit;
-- Logs all queries for compliance/forensics
"""

# 4. Key rotation — change keys regularly without downtime
# If using AWS Secrets Manager: automatic rotation every 90 days
# Your app reads the secret at startup and refreshes periodically
```

**Policy: make it impossible, not just difficult**

```
1. Pre-commit hooks block secrets locally
2. CI pipeline scans for secrets (catches hook bypass)
3. GitHub secret scanning alerts (catches pushes to public repos)
4. No long-lived credentials — use short-lived tokens (AWS STS, OAuth)
5. All API keys must be:
   - Stored in secrets manager (not .env, not config files)
   - Scoped to minimum permissions
   - Rotatable without code changes
   - Logged when used
6. Quarterly secret rotation (automated)
```

The incident happened because secrets and code were in the same channel (git). Fix it by keeping them in completely separate systems that only meet at runtime.'''
    ),
    (
        "thinking/abstraction-codesmell-to-principle",
        "I keep finding god classes in our codebase — classes with 2000+ lines that do everything. How do I convince my team this is a problem and how do we fix it?",
        r'''<think>
Abstraction ladder for god classes:

CONCRETE LEVEL (what a god class looks like):
```python
class OrderManager:
    # 2000+ lines, does EVERYTHING related to orders:
    def create_order(self, ...)
    def validate_order(self, ...)
    def calculate_total(self, ...)
    def apply_discount(self, ...)
    def calculate_tax(self, ...)
    def process_payment(self, ...)
    def send_confirmation_email(self, ...)
    def update_inventory(self, ...)
    def generate_invoice(self, ...)
    def handle_refund(self, ...)
    def export_to_csv(self, ...)
    def sync_to_warehouse(self, ...)
    # ... 50 more methods
```

PATTERN LEVEL (why god classes emerge and what problems they cause):
God classes emerge because:
1. It's the "obvious" place to add new order-related code
2. No clear extraction point — everything seems related
3. Incremental growth — each method is small, the class grew over years

Problems they cause:
1. Merge conflicts — everyone touches this file
2. Hard to test — need to set up the entire class to test one method
3. Hard to understand — 2000 lines, can't hold in your head
4. Hidden dependencies — calculate_tax() secretly depends on process_payment() state
5. Can't reuse — want just the tax calculation? You get all 2000 lines

PRINCIPLE LEVEL (what design principles are violated):
1. Single Responsibility Principle (SRP): A class should have one reason to change
   - OrderManager changes when: pricing changes, tax rules change, email templates change, inventory logic changes, warehouse integration changes...
   - Each of those is a different "reason to change" = different responsibility

2. Interface Segregation: Clients shouldn't depend on methods they don't use
   - The email system only needs send_confirmation_email()
   - But it depends on the entire OrderManager class

3. Open/Closed: Classes should be open for extension, closed for modification
   - Adding a new discount type? Modify OrderManager. Adding a new payment method? Modify OrderManager.
   - Everything requires modifying this one class.

The key principle: "A class should be about one CONCEPT, not one ENTITY."
OrderManager is about the entity "Order" but spans many concepts: pricing, payment, notification, inventory, export.

POLICY LEVEL:
"No class may exceed 300 lines. Classes exceeding 200 lines must be reviewed for extraction opportunities. Code review checklist includes SRP assessment."
</think>

God classes are the most common architectural debt. Let me help you make the case and the fix, climbing from concrete symptoms to principles.

**Make the case with symptoms, not theory:**

```
Show your team these concrete problems (they'll recognize them):

1. "How many merge conflicts did we have in order_manager.py last month?"
   → Everyone edits it → constant conflicts → wasted time

2. "How long does it take to write a unit test for calculate_tax()?"
   → Need to mock payment processor, email service, inventory...
   → Tests are fragile and slow

3. "A bug in export_to_csv() caused payments to fail. How?"
   → Shared state between unrelated methods
   → Change in one area breaks another

4. "How long does it take a new developer to understand OrderManager?"
   → 2000 lines → days, not hours
```

**The extraction recipe (do it incrementally, not all at once):**

```python
# BEFORE: God class
class OrderManager:
    def create_order(self, data): ...
    def validate_order(self, data): ...
    def calculate_subtotal(self, items): ...
    def apply_discount(self, order, code): ...
    def calculate_tax(self, order): ...
    def calculate_total(self, order): ...
    def process_payment(self, order, card): ...
    def handle_refund(self, order): ...
    def send_confirmation(self, order): ...
    def send_shipping_update(self, order): ...
    def update_inventory(self, order): ...
    def generate_invoice(self, order): ...
    def export_orders_csv(self, filters): ...

# AFTER: Cohesive classes, each with one reason to change
class PricingService:
    """Changes when: pricing rules, discounts, or tax logic changes."""
    def calculate_subtotal(self, items): ...
    def apply_discount(self, order, code): ...
    def calculate_tax(self, order): ...
    def calculate_total(self, order): ...

class PaymentService:
    """Changes when: payment processing or refund logic changes."""
    def process_payment(self, order, card): ...
    def handle_refund(self, order): ...

class NotificationService:
    """Changes when: email templates or notification channels change."""
    def send_confirmation(self, order): ...
    def send_shipping_update(self, order): ...

class InventoryService:
    """Changes when: inventory tracking logic changes."""
    def reserve_stock(self, items): ...
    def release_stock(self, items): ...

class OrderService:
    """Orchestrates the workflow — delegates to specialists."""
    def __init__(self, pricing, payment, notifications, inventory):
        self.pricing = pricing
        self.payment = payment
        self.notifications = notifications
        self.inventory = inventory

    def create_order(self, data):
        order = Order(**data)
        order.total = self.pricing.calculate_total(order)
        self.inventory.reserve_stock(order.items)
        self.payment.process_payment(order, data['card'])
        self.notifications.send_confirmation(order)
        return order
```

**How to extract without breaking everything:**

```python
# Step 1: Extract method group into new class (keep calling from old class)
class PricingService:
    def calculate_total(self, order):
        # Move the exact code from OrderManager.calculate_total
        ...

class OrderManager:
    def __init__(self):
        self.pricing = PricingService()  # Delegate

    def calculate_total(self, order):
        return self.pricing.calculate_total(order)  # Forward call
    # All existing callers still work — they still call OrderManager

# Step 2: Update callers one by one to use PricingService directly
# Step 3: Remove the forwarding method from OrderManager
# Step 4: Repeat for next group of methods
```

**Principle: "one reason to change"**

```
Ask for each method: "When does this change?"

calculate_tax()       → tax rules change       → PricingService
send_confirmation()   → email template changes  → NotificationService
process_payment()     → payment logic changes   → PaymentService
export_to_csv()       → report format changes   → ReportingService

If two methods change for the SAME reason → same class
If two methods change for DIFFERENT reasons → different classes
```

**Policy: prevent regrowth**

```python
# pyproject.toml — enforce with tooling
[tool.ruff]
max-complexity = 10  # Cyclomatic complexity per function

# Custom check (in CI):
# "Flag any class with more than 300 lines"
find . -name "*.py" -exec awk '/^class /{name=$0; count=0} {count++} /^class |^[^ ]/{if(count>300) print FILENAME": "name" ("count" lines)"}' {} \;

# Code review checklist:
# □ Does this class have more than one reason to change?
# □ Can this new method be added to an existing smaller class?
# □ Would a new developer understand this class in < 30 minutes?
```

Extract one service per sprint. Start with the group of methods that has the most merge conflicts — that's where the team pain is highest. Don't try to refactor the whole god class at once.'''
    ),
    (
        "thinking/abstraction-outage-to-reliability",
        "We've had 3 outages in the past month — all different root causes. One was a bad deploy, one was a database issue, one was a memory leak. How do we get more reliable?",
        r'''<think>
Abstraction ladder for reliability:

CONCRETE LEVEL (the three outages):
1. Bad deploy: pushed broken code, no rollback plan
2. Database issue: disk full, queries started failing
3. Memory leak: OOM kill after 3 days of uptime

These look unrelated at the concrete level. But...

PATTERN LEVEL (common failure patterns):
Looking at these three, I see patterns:

Pattern A: No safety nets for changes
- Bad deploy → no canary, no automated rollback, no health checks
- If the deploy had been to 10% of instances first, impact would have been limited

Pattern B: No capacity monitoring/alerting
- Disk full → nobody noticed disk growing until it was 100%
- If there was an alert at 80%, team could have acted before outage

Pattern C: No graceful degradation
- Memory leak → app just died (OOM kill)
- If the app had been recycled periodically, or if there were memory limits with graceful restart, it would have survived

Common thread: all three are lack of OBSERVABILITY and AUTOMATION.
- No one saw the problems coming
- No automated response when problems occurred

PRINCIPLE LEVEL (the principles of reliability engineering):
1. "Detect before customers do" (observability)
   - Monitor the 4 golden signals: latency, traffic, errors, saturation
   - Alert on leading indicators (disk at 80%), not trailing (disk full)

2. "Limit blast radius" (failure isolation)
   - Canary deploys (test on 10% before 100%)
   - Circuit breakers (don't let one failure cascade)
   - Resource limits (memory caps, request timeouts)

3. "Recover automatically" (self-healing)
   - Automated rollback on health check failure
   - Auto-restart on crash (systemd, Kubernetes)
   - Auto-scaling on load increase

4. "Learn from failure" (continuous improvement)
   - Blameless postmortems after every incident
   - Track action items to completion
   - Measure MTTR (mean time to recovery) over time

POLICY LEVEL:
"SLO: 99.9% uptime (allows 43 min downtime/month). All deployments use canary rollout. All infrastructure has capacity alerts at 80%. MTTR must be < 30 minutes. Postmortem within 48 hours of any P0/P1 incident."
</think>

Three outages with different root causes actually share common patterns. Let me show you the systematic fix.

**The pattern across all three outages:**

```
Outage 1 (bad deploy):
  Root cause:     No canary deployment
  Missing:        Detect ← deploy health check
  Missing:        Recover ← automated rollback

Outage 2 (disk full):
  Root cause:     No capacity monitoring
  Missing:        Detect ← disk usage alert at 80%
  Missing:        Prevent ← log rotation, data retention

Outage 3 (memory leak):
  Root cause:     No resource limits
  Missing:        Detect ← memory usage alert
  Missing:        Recover ← auto-restart, worker recycling

Common gap: no detection, no automated recovery.
```

**Layer 1: Observability (detect before customers do)**

```yaml
# Monitor the 4 Golden Signals for every service:

# 1. Latency — are requests getting slower?
- alert: HighP99Latency
  expr: histogram_quantile(0.99, http_request_duration_seconds) > 1
  for: 5m
  labels: { severity: warning }

# 2. Traffic — unexpected drop or spike?
- alert: TrafficDrop
  expr: rate(http_requests_total[5m]) < 0.5 * rate(http_requests_total[5m] offset 1h)
  for: 10m
  labels: { severity: critical }

# 3. Error rate — are requests failing?
- alert: HighErrorRate
  expr: rate(http_responses_total{status=~"5.."}[5m]) / rate(http_responses_total[5m]) > 0.01
  for: 5m
  labels: { severity: critical }

# 4. Saturation — are you running out of resources?
- alert: DiskSpaceWarning
  expr: disk_used_percent > 80
  labels: { severity: warning }
- alert: DiskSpaceCritical
  expr: disk_used_percent > 90
  labels: { severity: critical }
- alert: MemoryHigh
  expr: container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.85
  labels: { severity: warning }
```

**Layer 2: Deployment safety (prevent bad deploys)**

```yaml
# Progressive rollout — test before going to 100%
# Kubernetes rolling update with health checks:
apiVersion: apps/v1
kind: Deployment
spec:
  strategy:
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0  # Never have fewer than current pods
  template:
    spec:
      containers:
        - name: app
          # Health checks — Kubernetes auto-rolls back if these fail
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
          resources:
            limits:
              memory: "512Mi"  # OOM protection — prevents memory leak outage
              cpu: "500m"
```

```bash
# If not using Kubernetes — simple deploy script with auto-rollback
deploy() {
    git rev-parse HEAD > .previous_version
    git pull origin main
    pip install -r requirements.txt
    python manage.py migrate --noinput
    systemctl restart myapp

    sleep 10  # Wait for startup

    if ! curl -sf http://localhost:8000/health > /dev/null; then
        echo "HEALTH CHECK FAILED — rolling back"
        git checkout $(cat .previous_version)
        pip install -r requirements.txt
        systemctl restart myapp
        exit 1
    fi
}
```

**Layer 3: Self-healing (recover automatically)**

```python
# Worker recycling — prevents memory leak from becoming outage
# gunicorn.conf.py
max_requests = 10000        # Restart worker after 10K requests
max_requests_jitter = 1000  # Stagger restarts
timeout = 30                # Kill stuck workers
```

```yaml
# Kubernetes: auto-restart on crash
# (This is default behavior — containers restart automatically)
# Plus: auto-scale on load
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

```bash
# Log rotation — prevents disk full
# /etc/logrotate.d/myapp
/var/log/myapp/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

**Layer 4: Learn from failure (postmortems)**

```markdown
After EVERY outage, write a postmortem with:

1. Timeline (when did we detect, engage, diagnose, fix?)
2. Root cause (not "human error" — what systemic issue allowed this?)
3. Action items with OWNERS and DEADLINES
4. What detection would have caught this earlier?

Track MTTR over months — it should trend down:
  Month 1: 4 hours average
  Month 3: 1 hour average
  Month 6: 15 minutes average
```

**Priority order for your situation:**

```
This week:
  1. Add disk/memory/CPU alerts at 80% thresholds (prevents outage 2 & 3)
  2. Add /health endpoint + deploy health check (prevents outage 1)

This month:
  3. Add error rate and latency monitoring
  4. Set up worker recycling (max_requests)
  5. Write postmortem template and process

This quarter:
  6. Progressive/canary deployments
  7. Auto-scaling
  8. Chaos engineering (intentionally test failure modes)
```

The goal isn't zero outages — it's fast detection and fast recovery. The pattern: detect at 80% capacity (not 100%), roll out changes gradually, auto-recover from crashes, and learn from every incident.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
