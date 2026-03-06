"""Phase 2E: Advanced Reasoning — Causal & Counterfactual Analysis (Part 9)"""

PAIRS = [
    (
        "thinking/causal-intermittent-test-failures",
        "Our CI pipeline has tests that pass locally but fail randomly in CI — maybe 1 in 5 runs. The failures are always different tests. We added retries but the problem is getting worse. What's causing this?",
        r'''<think>
Intermittent CI test failures — different tests each time. Let me think through the causal chain.

**Key observations:**
1. Pass locally, fail in CI → environmental difference
2. Different tests fail each run → not a specific bug, systemic issue
3. 1 in 5 runs → timing/resource-dependent
4. Getting WORSE → the root cause is accumulating

**Causal hypotheses:**

**Hypothesis 1: Test interdependence (shared state)**
Tests modify shared state (database, files, global variables) and clean up poorly. Test order varies → different contamination → different failures.
- Evidence for: "different tests each time" matches this perfectly
- Counterfactual: if tests ran in the same order every time, same tests would fail
- Fix: ensure test isolation

**Hypothesis 2: Resource constraints in CI**
CI runners have less CPU/RAM than developer machines. Tests that depend on timing (timeouts, race conditions) fail under resource pressure.
- Evidence for: "pass locally, fail in CI" matches
- But: wouldn't explain "getting worse" unless CI resources are shrinking
- Fix: increase CI resources, remove timing dependencies

**Hypothesis 3: Test suite growing → parallelism → contention**
As more tests are added, CI runs more in parallel. Parallel tests compete for shared resources (database, ports, temp files).
- Evidence for: "getting worse" matches perfectly (more tests = more contention)
- Evidence for: "different tests each time" (race conditions are non-deterministic)
- This is the most likely primary cause.

**Hypothesis 4: Flakey third-party dependencies**
Tests call external APIs that are occasionally slow/down.
- Evidence against: "different tests each time" (unless many tests use external APIs)
- Fix: mock external dependencies

**Most likely: Hypothesis 3 (parallel test contention) combined with Hypothesis 1 (shared state)**

"Getting worse" is the key diagnostic clue. It means the root cause SCALES with the test suite. Parallel test contention + poor test isolation explains all symptoms.

**Adding retries masks the problem and makes it worse:**
- Retries that pass are still covering up shared-state corruption
- Retries add load to the CI runner, making resource contention worse
- Retries normalize flakiness → team stops investigating root causes
</think>

The key diagnostic clue is **"getting worse"** — this tells us the root cause scales with your test suite.

## Causal Chain Analysis

```
Root cause: Tests share mutable state + parallel execution

  More tests added over time
  → More parallel execution in CI
  → More contention for shared resources (DB, ports, temp files)
  → Random test failures depending on timing
  → Team adds retries instead of fixing
  → Retries add more load → more contention → more failures
  → Vicious cycle: "getting worse"
```

## Why "Different Tests Each Time"

```
If the same test always failed → it's a specific bug.
If DIFFERENT tests fail randomly → it's shared state contamination.

Test A runs first:     creates user "alice@test.com"
Test B runs next:      creates user "alice@test.com" → duplicate key error!
Test A runs after B:   expects 1 user in DB → finds 2 → assertion fails

The FAILURE depends on EXECUTION ORDER.
Parallel execution = random order = random failures.
```

## Why "Pass Locally, Fail in CI"

```
LOCAL:
  - Often runs tests sequentially (or fewer in parallel)
  - More CPU/RAM → faster execution → timing-dependent tests pass
  - Fresh database each run (maybe)

CI:
  - Parallel execution: 4-8 workers sharing one database
  - Limited CPU/RAM → slower execution → timeouts trigger
  - Shared resources across test workers
  - Container overhead adds latency
```

## Fix 1: Ensure Test Isolation (The Core Fix)

```python
# ❌ SHARED STATE: all tests use the same database
# Tests create/modify data that other tests don't expect

# ✅ FIXED: each test gets a clean state

# Option A: Transaction rollback (fastest)
import pytest

@pytest.fixture(autouse=True)
def db_transaction(db_session):
    """Every test runs inside a transaction that gets rolled back."""
    db_session.begin_nested()  # Savepoint
    yield db_session
    db_session.rollback()      # Undo everything this test did

# Option B: Database reset per test (slower but thorough)
@pytest.fixture(autouse=True)
def clean_database(db):
    yield
    # Truncate all tables after each test
    for table in reversed(db.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()

# Option C: Unique data per test (no cleanup needed)
import uuid

def test_create_user(db):
    # Use unique data so tests never collide
    email = f"test-{uuid.uuid4()}@example.com"
    user = create_user(email=email)
    assert user.email == email
```

## Fix 2: Eliminate Resource Contention

```python
# ❌ SHARED PORT: multiple test workers try to use port 5432
# Test worker 1: connects to localhost:5432
# Test worker 2: connects to localhost:5432
# → Connection pool exhaustion → random timeouts

# ✅ FIXED: per-worker database (pytest-xdist pattern)
# conftest.py
@pytest.fixture(scope="session")
def db_url(worker_id):
    """Each pytest-xdist worker gets its own database."""
    if worker_id == "master":
        return "postgresql://localhost/test_db"
    else:
        db_name = f"test_db_{worker_id}"
        create_database(db_name)
        return f"postgresql://localhost/{db_name}"

# ❌ TEMP FILES: tests write to same temp directory
# Test A writes /tmp/output.json
# Test B writes /tmp/output.json → overwrites A's file

# ✅ FIXED: use pytest's tmp_path fixture
def test_export(tmp_path):
    output_file = tmp_path / "output.json"  # Unique per test
    export_data(output_file)
    assert output_file.read_text() == '{"status": "ok"}'
```

## Fix 3: Remove Timing Dependencies

```python
# ❌ FLAKY: test depends on timing
def test_cache_expiry():
    cache.set("key", "value", ttl=1)
    time.sleep(1.1)          # On slow CI: might not be enough
    assert cache.get("key") is None  # Flaky!

# ✅ FIXED: control time explicitly
from unittest.mock import patch
from freezegun import freeze_time

def test_cache_expiry():
    with freeze_time("2024-01-01 12:00:00"):
        cache.set("key", "value", ttl=60)

    with freeze_time("2024-01-01 12:01:01"):  # Exactly 61 seconds later
        assert cache.get("key") is None  # Deterministic!
```

## Fix 4: Stop Using Retries (They Make It Worse)

```
RETRIES ARE A BANDAID:

  Without retries:
    Flaky test fails → developer sees failure → investigates → fixes root cause

  With retries:
    Flaky test fails → retry → passes → nobody notices
    → More flaky tests accumulate → CI takes 3x longer
    → Eventually retries fail too → "CI is broken, just re-run it"
    → Nobody trusts CI → bugs ship to production

REMOVE RETRIES. FIX THE ROOT CAUSES.
Track flakiness explicitly instead:

  # In CI config:
  # --count-flaky flag: mark tests that pass on retry as "flaky"
  # Dashboard shows: "42 flaky tests this week, up from 35 last week"
  # Assign flaky test fixes as regular maintenance work
```

## Diagnostic Checklist

```bash
# 1. Run tests sequentially — do they still fail?
pytest --forked -p no:randomly    # No parallelism, no randomization
# If this passes → problem is parallelism/ordering

# 2. Run tests in random order — which fail?
pytest -p randomly --randomly-seed=12345    # Reproducible random order

# 3. Find shared state violations
pytest --randomly-dont-shuffle-module    # Shuffle between modules, not within
# If inter-module tests fail → modules contaminate each other

# 4. Check for resource contention
# Monitor during CI run: database connections, open files, memory usage
```'''
    ),
    (
        "thinking/causal-slow-docker-builds",
        "Our Docker builds went from 2 minutes to 15 minutes over the past few months. Nobody changed the Dockerfile. What's causing the slowdown?",
        r'''<think>
Docker build slowdown without Dockerfile changes. Let me think about what ELSE could have changed.

**Causal analysis — what changed if the Dockerfile didn't?**

1. **Dependencies grew**: `npm install` or `pip install` takes longer because package.json/requirements.txt has more dependencies. The Dockerfile didn't change but the files it COPIES changed.

2. **Cache invalidation**: Docker layer caching breaks when earlier layers change. If code changes invalidate the dependency installation layer, everything after rebuilds.

3. **Build context size**: more files in the project = more data sent to Docker daemon before build starts. Large node_modules, data files, logs getting sent as context.

4. **Base image changes**: `FROM node:18` now pulls a larger/different image than 3 months ago.

5. **Docker system resource issues**: Docker disk space filling up, daemon needs pruning.

Let me think about which is most likely...

"Nobody changed the Dockerfile" + "gradual slowdown over months" = most likely:
- Dependencies grew (gradual, scales with time)
- Build context grew (more files added to project)
- Cache invalidation pattern changed (code structure changed)

Let me also think about Dockerfile anti-patterns that cause slow builds even when they "look fine":

**Layer ordering**: If COPY . . comes before RUN npm install, every code change invalidates the npm install cache. This is the #1 cause of slow Docker builds.

If their Dockerfile has:
```
COPY . .
RUN npm install
```
vs the correct:
```
COPY package*.json .
RUN npm install
COPY . .
```

The first version reinstalls ALL dependencies on EVERY code change.
The second only reinstalls when package.json changes.

This wouldn't explain "gradual slowdown" though, unless they've always had this pattern and the dependency list grew.

Actually, thinking more carefully: "nobody changed the Dockerfile" + "gradual increase from 2→15 minutes" strongly suggests:
1. Dependency count grew (more packages to install each build)
2. Build context grew (more files to transfer)
3. Both compound over months as the project grows
</think>

"Nobody changed the Dockerfile" doesn't mean nothing changed. Let me trace what DID change.

## Most Likely Cause: Dependencies Grew

```dockerfile
# Your Dockerfile probably has:
COPY package.json package-lock.json ./
RUN npm install      # ← THIS takes longer now

# 3 months ago: 50 dependencies, 200MB node_modules, 45 seconds
# Today: 120 dependencies, 600MB node_modules, 8 minutes
# Nobody changed the Dockerfile — they changed package.json
```

```bash
# VERIFY: check how dependencies grew
git log --oneline --all -- package.json | head -20
# Count the number of dependency additions over time

git show HEAD~100:package.json | jq '.dependencies | length'  # 3 months ago
git show HEAD:package.json | jq '.dependencies | length'       # now
```

## Second Likely Cause: Build Context Bloat

```bash
# Before Docker builds, it sends ALL files in . to the daemon
# Check how much data is being sent:
docker build . 2>&1 | head -5
# "Sending build context to Docker daemon  2.3GB"
#                                           ^^^^ THIS is the problem

# The project grew: data files, logs, test fixtures, build artifacts
# All getting sent to Docker even though they're not used

# FIX: add a .dockerignore file
```

```
# .dockerignore (like .gitignore but for Docker)
node_modules/          # Don't send 600MB of packages (they'll be npm installed anyway)
.git/                  # Don't send git history
dist/                  # Don't send build output
*.log                  # No log files
test/                  # No test files in production image
coverage/              # No coverage reports
.env                   # No secrets!
data/                  # No data files
*.md                   # No documentation
```

```bash
# Before .dockerignore: "Sending build context to Docker daemon 2.3GB"  (45 seconds)
# After .dockerignore:  "Sending build context to Docker daemon 12MB"   (0.5 seconds)
```

## Third Cause: Bad Layer Ordering (Cache Invalidation)

```dockerfile
# ❌ SLOW: every code change reinstalls ALL dependencies
FROM node:18-alpine
WORKDIR /app
COPY . .                    # ← Code changes invalidate this layer
RUN npm ci                  # ← Must reinstall EVERY time (cache busted)
RUN npm run build

# ANY change to ANY file = npm install runs again = 8 minutes


# ✅ FAST: only reinstall dependencies when package.json changes
FROM node:18-alpine
WORKDIR /app
COPY package.json package-lock.json ./   # ← Only these two files
RUN npm ci                               # ← Cached unless package.json changed!
COPY . .                                 # ← Code changes only affect this layer
RUN npm run build                        # ← And this layer

# Code change without dependency change:
#   npm ci: CACHED (seconds)
#   COPY + build: runs (30 seconds)
# Total: 30 seconds instead of 8 minutes
```

## Diagnostic Script

```bash
# Run this to find your bottleneck:

echo "=== Build context size ==="
du -sh . --exclude=.git
# If > 100MB, you need a .dockerignore

echo "=== .dockerignore exists? ==="
cat .dockerignore 2>/dev/null || echo "NO .dockerignore! This is a problem."

echo "=== Dependency count ==="
cat package.json | python3 -c "
import json, sys
pkg = json.load(sys.stdin)
deps = len(pkg.get('dependencies', {}))
devdeps = len(pkg.get('devDependencies', {}))
print(f'Dependencies: {deps}, DevDependencies: {devdeps}, Total: {deps+devdeps}')
"

echo "=== Docker layer timing ==="
DOCKER_BUILDKIT=1 docker build --progress=plain . 2>&1 | grep -E '^\#[0-9]+ (DONE|CACHED)'
# Shows which layers are cached and how long each takes

echo "=== Docker disk usage ==="
docker system df
# If "Build cache" is > 10GB, run: docker builder prune
```

## Complete Fix

```dockerfile
# Optimized Dockerfile with proper layer caching

FROM node:18-alpine AS base
WORKDIR /app

# Layer 1: System dependencies (rarely changes)
RUN apk add --no-cache dumb-init

# Layer 2: Package files only (changes when dependencies change)
COPY package.json package-lock.json ./

# Layer 3: Install dependencies (CACHED when package.json unchanged)
RUN npm ci --only=production

# Layer 4: Copy source code (changes on every commit)
COPY src/ ./src/
COPY tsconfig.json ./

# Layer 5: Build (only runs if code or deps changed)
RUN npm run build

# Layer 6: Production image (multi-stage — smaller final image)
FROM node:18-alpine
WORKDIR /app
RUN apk add --no-cache dumb-init
COPY --from=base /app/node_modules ./node_modules
COPY --from=base /app/dist ./dist
COPY package.json ./

USER node
ENTRYPOINT ["dumb-init", "node", "dist/index.js"]
```

```
Expected improvement:
  Before: 15 minutes (every build)
  After (code change only): 30-60 seconds (deps cached)
  After (dep change): 3-5 minutes (deps reinstall, but smaller context)
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
