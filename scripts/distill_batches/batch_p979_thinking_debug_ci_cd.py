PAIRS = [
    ("thinking/debugging", r'''Our GitHub Actions workflow is leaking secrets into the build logs. Even though we use `${{ secrets.API_KEY }}`, the actual secret value appears in the output:

```yaml
name: Deploy
on: push

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure API
        run: |
          echo "Setting up API configuration..."
          echo "API_KEY=${{ secrets.API_KEY }}" >> .env
          echo "DATABASE_URL=${{ secrets.DATABASE_URL }}" >> .env
          cat .env  # Debugging -- shows the actual values!

      - name: Debug environment
        run: |
          echo "Config contents:"
          cat .env
          echo "Checking API connectivity..."
          curl -v "https://api.example.com/health?key=${{ secrets.API_KEY }}"
          # The -v flag prints the full URL including the secret!

      - name: Build
        run: |
          docker build --build-arg API_KEY=${{ secrets.API_KEY }} -t myapp .
          # docker build output shows: --build-arg API_KEY=sk-live-abc123...
```

GitHub says it masks secrets in logs, but we can see the actual values in multiple places.''', r'''<think>
GitHub Actions DOES mask secrets in logs, but only when the secret appears as an exact match of the stored secret value. There are several ways secrets can leak through the masking:

1. `cat .env` -- GitHub masks the secret value in log output, BUT if the secret is embedded in a longer string like `API_KEY=sk-live-abc123`, the masking might not catch partial matches depending on the format.

2. `curl -v` -- The verbose flag prints the full URL. If the secret is in a URL query parameter, it might get URL-encoded differently, which bypasses the exact-match masking.

3. `docker build --build-arg` -- Docker prints build arguments in the build log. The secret appears as part of the `--build-arg` output.

4. The biggest issue: `cat .env` directly prints the file contents. GitHub's masking should catch the exact secret value, but if the secret contains special characters that get escaped differently, the masking fails.

Actually, let me reconsider. GitHub Actions masks secrets in log output by replacing the exact string with `***`. This works for most cases. But there are known bypass scenarios:
- Base64 encoding of the secret
- URL encoding
- The secret broken across multiple lines
- The secret appearing in structured output (JSON) with escaping
- Multi-line secrets where only each line is masked, not the whole value

The real issues here are:
1. Writing secrets to a file and then `cat`-ing the file (the `cat` output might be masked, but the file persists as an artifact)
2. Using `curl -v` which outputs the URL (URL-encoded differently)
3. Docker build args appearing in the image layers and build cache
</think>

GitHub Actions masks secrets in log output by exact-match replacement, but there are multiple ways secrets bypass this masking. Your workflow has several distinct leak vectors.

**Leak 1: `cat .env` prints secrets (masking may fail)**

GitHub masks the exact secret string, but if the secret contains special characters, shell escaping or concatenation can produce a string that does not exactly match:

```yaml
# BAD: cat prints the file, and the secret might bypass masking
- run: |
    echo "API_KEY=${{ secrets.API_KEY }}" >> .env
    cat .env  # REMOVE THIS -- even if masked, it is risky

# GOOD: write secrets without printing
- run: |
    echo "API_KEY=${{ secrets.API_KEY }}" >> .env
    echo ".env file created ($(wc -l < .env) lines)"
```

**Leak 2: `curl -v` prints the full URL including query parameters:**

```yaml
# BAD: -v prints the entire request including the URL with the secret
- run: curl -v "https://api.example.com/health?key=${{ secrets.API_KEY }}"
# Output: > GET /health?key=sk-live-abc123 HTTP/2

# GOOD: use headers instead of query parameters, and remove -v
- run: |
    curl -s -o /dev/null -w "%{http_code}" \
      -H "Authorization: Bearer ${{ secrets.API_KEY }}" \
      "https://api.example.com/health"
```

**Leak 3: Docker build args appear in image layers:**

```yaml
# BAD: build args are visible in image history and build output
- run: docker build --build-arg API_KEY=${{ secrets.API_KEY }} -t myapp .
# Anyone with image access: docker history myapp
# Shows: ARG API_KEY=sk-live-abc123

# GOOD: use Docker secrets (BuildKit)
- run: |
    echo "${{ secrets.API_KEY }}" > /tmp/api_key
    DOCKER_BUILDKIT=1 docker build \
      --secret id=api_key,src=/tmp/api_key \
      -t myapp .
    rm /tmp/api_key
```

And in the Dockerfile:

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Mount secret at build time -- never stored in a layer
RUN --mount=type=secret,id=api_key \
    cat /run/secrets/api_key > /dev/null && \
    echo "Secret verified"

# For runtime, use environment variables passed at container start
# NOT baked into the image
```

**Leak 4: Secrets in error messages and tracebacks:**

```yaml
# BAD: if curl fails, the error message includes the URL
- run: |
    set -e
    curl "https://api.example.com/data?key=${{ secrets.API_KEY }}" || true
    # Error: curl: (6) Could not resolve host...
    # The full URL with the secret appears in the error

# GOOD: use environment variables so secrets are not in the command line
- run: |
    curl -s -f \
      -H "X-API-Key: ${API_KEY}" \
      "https://api.example.com/data" \
      2>/dev/null || echo "API check failed"
  env:
    API_KEY: ${{ secrets.API_KEY }}
```

**Comprehensive secure workflow:**

```yaml
name: Deploy
on: push

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure API
        run: |
          # Write secrets to .env without echoing
          {
            echo "API_KEY=${API_KEY}"
            echo "DATABASE_URL=${DATABASE_URL}"
          } > .env
          chmod 600 .env
          echo ".env configured with $(wc -l < .env) variables"
        env:
          API_KEY: ${{ secrets.API_KEY }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}

      - name: Health check
        run: |
          status=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "Authorization: Bearer ${API_KEY}" \
            "https://api.example.com/health")
          echo "API health check: HTTP ${status}"
        env:
          API_KEY: ${{ secrets.API_KEY }}

      - name: Build
        run: |
          echo "${API_KEY}" > /tmp/secret_api_key
          DOCKER_BUILDKIT=1 docker build \
            --secret id=api_key,src=/tmp/secret_api_key \
            -t myapp .
          rm -f /tmp/secret_api_key
        env:
          API_KEY: ${{ secrets.API_KEY }}
```

**Prevention tips:**
- NEVER use `cat`, `echo`, `printenv`, or `env` to display files or variables containing secrets
- NEVER use `curl -v` with secrets in URLs -- use headers and suppress verbose output
- NEVER use `docker build --build-arg` for secrets -- use BuildKit `--secret` mount
- Use the `env:` block to pass secrets as environment variables, not inline `${{ secrets.* }}`
- Add `set +x` before sections handling secrets (disables command echoing in bash)
- Use `add-mask` for dynamically generated secrets: `echo "::add-mask::${DYNAMIC_SECRET}"`
- Review build logs in a PR before merging to verify no secrets are exposed'''),

    ("thinking/debugging", r'''Our GitHub Actions matrix build is failing on one specific combination, but we cannot reproduce it locally. The matrix:

```yaml
name: Test Matrix
on: [push, pull_request]

jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ["3.9", "3.10", "3.11", "3.12"]
      fail-fast: false

    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        run: pytest tests/ -v
```

Results:
```
ubuntu-latest  / 3.9  -- PASS
ubuntu-latest  / 3.10 -- PASS
ubuntu-latest  / 3.11 -- PASS
ubuntu-latest  / 3.12 -- PASS
macos-latest   / 3.9  -- PASS
macos-latest   / 3.10 -- PASS
macos-latest   / 3.11 -- PASS
macos-latest   / 3.12 -- PASS
windows-latest / 3.9  -- PASS
windows-latest / 3.10 -- FAIL  <-- Only this combination!
windows-latest / 3.11 -- PASS
windows-latest / 3.12 -- PASS
```

The failing test:
```
FAILED tests/test_paths.py::test_config_loading - AssertionError:
  Expected: /home/user/.config/myapp/settings.json
  Got:      C:\Users\runneradmin\.config\myapp\settings.json
```

But wait -- windows/3.11 and windows/3.12 PASS. Why does only windows/3.10 fail?''', r'''<think>
The test expects a Unix-style path but gets a Windows path. That makes sense on Windows. But the mystery is why it only fails on Windows 3.10, not Windows 3.11 or 3.12.

Let me think about what could cause a path handling difference between Python versions on the same OS.

Possible explanations:
1. The code uses `pathlib.Path` differently across versions
2. There is a version-specific behavior in `os.path` or `pathlib`
3. The test fixture or setup differs by Python version
4. There is a dependency that installs differently on Python 3.10 vs 3.11+ on Windows

Actually, the most likely explanation: the test has a conditional check for the platform, but the condition has a bug. Or the code being tested uses `pathlib.PurePosixPath` vs `pathlib.Path` differently.

Wait, another possibility: in Python 3.12, `pathlib.Path` had some changes. Or the code uses a library like `platformdirs` that changed behavior across versions.

Actually, the simplest explanation: the code might be using `pathlib.PurePosixPath` on 3.11+ but `pathlib.Path` on 3.10 due to a version check in the code or a dependency. Or a dependency like `platformdirs` or `appdirs` that changed the config directory location.

Let me think more carefully. The expected path uses `/home/user/.config/` which is a Unix XDG path. The actual path uses `C:\Users\runneradmin\.config\`. On Windows, the standard config directory would be `C:\Users\runneradmin\AppData\Roaming\` or similar, NOT `.config`.

So the code is using a `.config` directory on both platforms, but the test hardcodes a Unix-style path. The question is why 3.11 and 3.12 pass on Windows.

Most likely: a dependency changed behavior between 3.10 and 3.11. For example, `platformdirs` might have changed the default on Windows, or the test mocking setup changed.

Actually, I think the real answer might be simpler: the test uses a mock or fixture that returns different values based on Python version. Or the application code has a `sys.version_info` check that branches differently.

For the purpose of this training example, I will focus on the general debugging approach for matrix-specific failures and the specific path handling issue.
</think>

A matrix failure on exactly one OS + Python version combination usually points to a version-specific behavior in a dependency or the standard library. Let me walk through the debugging approach.

**Step 1: Isolate what is different about windows/3.10**

The test expects `/home/user/.config/myapp/settings.json` but gets a Windows path. The fact that windows/3.11 and 3.12 PASS means something changed between 3.10 and 3.11 that affects path handling.

**Step 2: Check dependency versions across matrix runs**

```yaml
- name: Debug dependency versions
  run: |
    pip freeze | grep -i "platformdirs\|appdirs\|pathlib"
    python -c "import sys; print(f'Python: {sys.version}')"
    python -c "import platformdirs; print(f'platformdirs: {platformdirs.__version__}')"
```

**Most likely cause: A dependency resolves to different versions on Python 3.10 vs 3.11+**

```
# Python 3.10 on Windows:
platformdirs==3.11.0  # Uses ~/.config on all platforms

# Python 3.11+ on Windows:
platformdirs==4.1.0   # Uses AppData/Roaming on Windows
```

Some packages have version pins like `platformdirs>=3.0; python_version<"3.11"` that cause different versions to install.

**Step 3: Check the actual test and fix it:**

```python
# BAD: Hardcoded Unix path in test
def test_config_loading():
    config_path = get_config_path()
    assert config_path == "/home/user/.config/myapp/settings.json"

# GOOD: Platform-aware test
import sys
from pathlib import Path

def test_config_loading():
    config_path = get_config_path()
    # Normalize to Path for cross-platform comparison
    result = Path(config_path)

    if sys.platform == "win32":
        assert result.name == "settings.json"
        assert "myapp" in result.parts
    else:
        assert result == Path.home() / ".config" / "myapp" / "settings.json"
```

**Step 4: Pin dependencies to ensure consistent matrix runs:**

```
# requirements.txt -- pin exact versions
platformdirs==4.1.0
# Or use a constraint to ensure the same version everywhere:
platformdirs>=4.0,<5.0
```

**Step 5: Add debugging steps to your matrix workflow:**

```yaml
- name: Debug matrix-specific info
  run: |
    python -c "
    import sys, platform, os
    print(f'Python: {sys.version}')
    print(f'Platform: {platform.platform()}')
    print(f'OS: {os.name}')
    print(f'Path sep: {os.sep}')
    print(f'Home: {os.path.expanduser(\"~\")}')
    "

- name: Freeze dependencies for comparison
  run: pip freeze > deps-${{ matrix.os }}-${{ matrix.python-version }}.txt

- uses: actions/upload-artifact@v4
  with:
    name: deps-${{ matrix.os }}-${{ matrix.python-version }}
    path: deps-*.txt
```

**Common causes of matrix-specific failures:**

```python
# 1. Path separator differences
path = "config" + "/" + "file.json"     # Fails on Windows
path = os.path.join("config", "file.json")  # Correct

# 2. Case sensitivity
open("Config.json")  # Works on Windows/macOS, fails on Linux

# 3. Line endings
assert content == "line1\nline2"  # Fails on Windows (\r\n)
assert content.strip() == "line1\nline2".strip()  # Safer

# 4. Temp directory differences
import tempfile
print(tempfile.gettempdir())
# Linux:   /tmp
# macOS:   /var/folders/xx/...
# Windows: C:\Users\...\AppData\Local\Temp
```

**Prevention tips:**
- Use `pathlib.Path` everywhere instead of string concatenation for paths
- Never hardcode platform-specific paths in tests
- Pin dependency versions in requirements.txt to avoid version drift across matrix cells
- Use `os.sep`, `os.linesep`, `pathlib.Path` for cross-platform compatibility
- Add a `pip freeze` artifact upload to compare dependency versions across matrix runs
- Use `fail-fast: false` in matrix strategy to see ALL failures, not just the first one
- Test with `tox` locally to reproduce different Python version behaviors'''),

    ("thinking/debugging", r'''Our CI build cache is corrupt and builds are failing with mysterious errors. We are using GitHub Actions cache for pip and node_modules:

```yaml
- name: Cache pip packages
  uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: pip-${{ runner.os }}-${{ hashFiles('requirements.txt') }}

- name: Cache node_modules
  uses: actions/cache@v4
  with:
    path: node_modules
    key: node-${{ runner.os }}-${{ hashFiles('package-lock.json') }}

- name: Install Python deps
  run: pip install -r requirements.txt

- name: Install Node deps
  run: npm ci

- name: Run tests
  run: pytest tests/ && npm test
```

Build errors:
```
Step "Install Python deps":
  ERROR: Could not install packages due to an OSError:
  [Errno 28] No space left on device

Step "Install Node deps":
  npm ERR! EINTEGRITY sha512-abc123... integrity checksum failed

Step "Run tests":
  ModuleNotFoundError: No module named 'new_dependency'
  (we added new_dependency to requirements.txt last week)
```

Three different errors, all seemingly unrelated. But they all started happening around the same time.''', r'''<think>
Three errors all starting around the same time point to a common root cause: the cache.

1. "No space left on device" -- the pip cache grew too large and the runner disk is full
2. "EINTEGRITY checksum failed" -- the node_modules cache is corrupt (cached node_modules do not match the current package-lock.json checksums)
3. "No module named 'new_dependency'" -- the pip cache key has not changed because requirements.txt hash is the same as when the cache was created, BUT the actual contents changed (maybe the file was modified and then the hash collided, OR the cache restores old packages that do not include the new dependency)

Wait, #3 is interesting. If they added `new_dependency` to requirements.txt, the hash of requirements.txt would change, so the cache key would change. Unless... the cache key matches a restore-keys prefix.

Actually, let me reconsider. The pip cache caches the pip download cache (`~/.cache/pip`), not the installed packages. So even with a cached pip, `pip install -r requirements.txt` should still install new packages. The issue might be that the disk is full (error #1) which prevents pip from installing the new dependency.

So the root cause chain is:
1. The pip download cache (`~/.cache/pip`) grows unbounded because old cached packages are never evicted
2. The cache fills the runner disk
3. Disk full prevents pip from installing new packages (which looks like ModuleNotFoundError)
4. The node_modules cache may be corrupt because a previous run ran out of disk during cache save

The fix: bust the caches and add better cache key strategies.
</think>

Three seemingly unrelated errors starting at the same time points to a **common root cause: corrupted or bloated CI cache**. Here is the cascade:

1. **Pip cache grew unbounded** -- old package downloads accumulated because the cache key never changes when you only add new packages (the hash might match a partial restore)
2. **Disk full from bloated cache** -- prevents new package installation, causing `ModuleNotFoundError`
3. **Node cache corruption** -- a previous run's cache save was interrupted by disk full, leaving corrupt data

**Immediate fix: Bust ALL caches by changing the cache key:**

```yaml
- name: Cache pip packages
  uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: pip-v2-${{ runner.os }}-${{ hashFiles('requirements.txt') }}
    #     ^^^ bump this version to bust the cache

- name: Cache node_modules
  uses: actions/cache@v4
  with:
    path: node_modules
    key: node-v2-${{ runner.os }}-${{ hashFiles('package-lock.json') }}
```

Or delete caches via the GitHub API:

```bash
# List all caches for the repo
gh cache list

# Delete specific caches
gh cache delete pip-ubuntu-latest-abc123
gh cache delete node-ubuntu-latest-def456

# Or delete ALL caches
gh cache list --json id -q '.[].id' | xargs -I {} gh cache delete {}
```

**Long-term fix: Better cache strategy with restore-keys:**

```yaml
- name: Cache pip packages
  uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: pip-${{ runner.os }}-${{ hashFiles('requirements.txt') }}-${{ github.run_id }}
    restore-keys: |
      pip-${{ runner.os }}-${{ hashFiles('requirements.txt') }}-
      pip-${{ runner.os }}-
    # run_id ensures cache is always saved fresh
    # restore-keys allow fallback to older caches

- name: Install Python deps
  run: |
    pip install -r requirements.txt
    # Clean old cached downloads to prevent bloat
    pip cache purge || true
```

**Fix the node_modules caching -- do NOT cache node_modules directly:**

```yaml
# BAD: caching node_modules directly causes integrity issues
- uses: actions/cache@v4
  with:
    path: node_modules
    key: node-${{ runner.os }}-${{ hashFiles('package-lock.json') }}

# GOOD: cache the npm global cache, let npm ci rebuild node_modules
- uses: actions/cache@v4
  with:
    path: ~/.npm
    key: npm-${{ runner.os }}-${{ hashFiles('package-lock.json') }}
    restore-keys: |
      npm-${{ runner.os }}-

- run: npm ci
  # npm ci always does a clean install from package-lock.json
  # but uses the cached downloads from ~/.npm
```

**Add disk space monitoring:**

```yaml
- name: Check disk space before build
  run: |
    df -h /
    echo "---"
    du -sh ~/.cache/pip 2>/dev/null || echo "No pip cache"
    du -sh node_modules 2>/dev/null || echo "No node_modules"

- name: Check disk space after build
  if: always()
  run: df -h /
```

**Add cache size limits:**

```yaml
- name: Cleanup pip cache if too large
  run: |
    CACHE_SIZE=$(du -sm ~/.cache/pip 2>/dev/null | cut -f1 || echo 0)
    echo "Pip cache size: ${CACHE_SIZE}MB"
    if [ "${CACHE_SIZE}" -gt 1000 ]; then
      echo "Cache too large, purging..."
      pip cache purge
    fi
```

**Complete robust caching setup:**

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip  # Built-in pip caching -- handles everything!

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm  # Built-in npm caching -- handles everything!

      # The setup actions handle caching correctly:
      # - Cache pip download directory (not installed packages)
      # - Cache npm global cache (not node_modules)
      # - Automatic key based on lock files
      # - No manual cache action needed!

      - run: pip install -r requirements.txt
      - run: npm ci
      - run: pytest tests/ && npm test
```

**Prevention tips:**
- Use `actions/setup-python` and `actions/setup-node` built-in caching instead of manual `actions/cache`
- NEVER cache `node_modules` directly -- cache `~/.npm` and let `npm ci` rebuild
- Include a version prefix in cache keys (`v2-`) so you can bust caches easily
- Monitor cache sizes and add alerts if they exceed thresholds
- Use `npm ci` (not `npm install`) which does clean installs from the lock file
- Periodically bump cache version prefixes to prevent unbounded growth
- GitHub has a 10GB cache limit per repository -- old caches are evicted LRU'''),

    ("thinking/debugging", r'''Our CI has flaky parallel test jobs that occasionally fail with a database conflict. We have 4 parallel test shards that all use the same test database:

```yaml
jobs:
  test:
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - name: Run test shard
        run: |
          pytest tests/ -v \
            --splits 4 \
            --group ${{ matrix.shard }} \
            --splitting-algorithm least_duration
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_db
```

Intermittent failures:
```
Shard 2: FAILED test_user_creation
  psycopg2.errors.UniqueViolation: duplicate key value violates unique
  constraint "users_email_key"
  DETAIL: Key (email)=(test@example.com) already exists.

Shard 3: FAILED test_order_processing
  AssertionError: Expected 1 order, found 3
  (other shards created orders in the shared database)

Shard 1: FAILED test_cleanup
  psycopg2.errors.DeadlockDetected: deadlock detected
  DETAIL: Process 142 waits for ShareLock on transaction 5234;
  blocked by process 156.
```

The tests pass when run sequentially but fail randomly in parallel CI.''', r'''<think>
The problem is clear: all 4 parallel test shards share the same database and interfere with each other. Each shard creates test data that conflicts with other shards (unique constraint violations, unexpected row counts, deadlocks).

Wait, actually looking more carefully at the YAML: each matrix job runs its own `services` block, which means each shard gets its OWN PostgreSQL container. They should be isolated. Unless... the GitHub Actions services are shared across matrix jobs somehow? No, each matrix job runs in its own runner with its own services.

Hmm, but then why the conflicts? Let me re-read...

Actually, each matrix job gets its own runner and its own services container. So each shard should have its own isolated PostgreSQL. The parallel shards should NOT share a database.

Unless the tests are connecting to an EXTERNAL database, not the local services one. Or the DATABASE_URL points to a shared external database. But the YAML shows `localhost:5432` which would be the job-local service.

Wait, maybe I am overthinking this. The user says they have parallel test shards using the same database. Perhaps the `services` block is NOT in the matrix job but in a separate job, or they are using a remote database. Let me take the scenario at face value: 4 parallel shards sharing one database, which causes conflicts.

The fix is to use per-shard isolated databases.
</think>

Parallel test shards sharing a single database is a recipe for flaky tests. Each shard creates, modifies, and deletes data that other shards depend on, causing unique violations, wrong counts, and deadlocks.

**Root cause analysis:**

```
Shard 1: INSERT INTO users (email) VALUES ('test@example.com')
Shard 2: INSERT INTO users (email) VALUES ('test@example.com')  -- CONFLICT!
Shard 3: SELECT COUNT(*) FROM orders WHERE user_id=1  -- Sees other shards' data!
Shard 1: DELETE FROM orders WHERE user_id=1  -- Deadlock with Shard 3's SELECT
```

**Fix 1: Use per-shard databases (recommended):**

```yaml
jobs:
  test:
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - name: Create isolated database for this shard
        run: |
          PGPASSWORD=test psql -h localhost -U test -d test_db -c \
            "CREATE DATABASE test_shard_${{ matrix.shard }};"
        env:
          PGPASSWORD: test

      - name: Run test shard
        run: |
          pytest tests/ -v \
            --splits 4 \
            --group ${{ matrix.shard }} \
            --splitting-algorithm least_duration
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_shard_${{ matrix.shard }}
```

**Fix 2: Use transactions that roll back after each test:**

```python
# conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture(autouse=True)
def db_session(request):
    """Each test runs in a transaction that is rolled back after the test."""
    engine = create_engine(os.environ["DATABASE_URL"])
    connection = engine.connect()
    transaction = connection.begin()

    Session = sessionmaker(bind=connection)
    session = Session()

    # Patch the application's session to use this transactional one
    request.cls.session = session if request.cls else None

    yield session

    session.close()
    transaction.rollback()  # Undo ALL changes from this test
    connection.close()
```

**Fix 3: Use unique test data per shard:**

```python
# conftest.py
import os

SHARD_ID = os.environ.get("TEST_SHARD", "0")

@pytest.fixture
def unique_email():
    """Generate a shard-unique email for tests."""
    import uuid
    return f"test-{SHARD_ID}-{uuid.uuid4().hex[:8]}@example.com"

@pytest.fixture
def unique_user(db_session, unique_email):
    """Create a user with a guaranteed unique email."""
    user = User(email=unique_email, name=f"Test User (shard {SHARD_ID})")
    db_session.add(user)
    db_session.commit()
    return user

# In tests:
def test_user_creation(unique_email, db_session):
    user = User(email=unique_email, name="Test")  # No conflicts!
    db_session.add(user)
    db_session.commit()
    assert User.query.filter_by(email=unique_email).count() == 1
```

**Fix 4: Use schema-based isolation:**

```python
# Each shard uses a separate PostgreSQL schema
SHARD_ID = os.environ.get("TEST_SHARD", "1")

@pytest.fixture(scope="session", autouse=True)
def setup_shard_schema(db_engine):
    schema_name = f"shard_{SHARD_ID}"
    with db_engine.connect() as conn:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
        conn.execute(f"SET search_path TO {schema_name}")
        # Run migrations in this schema
        create_all_tables(conn)
    yield
    with db_engine.connect() as conn:
        conn.execute(f"DROP SCHEMA {schema_name} CASCADE")
```

**Updated CI workflow with proper isolation:**

```yaml
jobs:
  test:
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
      fail-fast: false
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Create shard database
        run: |
          PGPASSWORD=test psql -h localhost -U test -d test_db \
            -c "CREATE DATABASE test_shard_${{ matrix.shard }};"

      - name: Run migrations
        run: alembic upgrade head
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_shard_${{ matrix.shard }}

      - name: Run test shard
        run: |
          pytest tests/ -v \
            --splits 4 \
            --group ${{ matrix.shard }} \
            --splitting-algorithm least_duration \
            --junitxml=results-shard-${{ matrix.shard }}.xml
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_shard_${{ matrix.shard }}
          TEST_SHARD: ${{ matrix.shard }}

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: test-results-shard-${{ matrix.shard }}
          path: results-shard-*.xml
```

**Prevention tips:**
- NEVER share a database between parallel test jobs without isolation
- Use per-shard databases, schemas, or transaction rollback for isolation
- Generate unique test data (UUIDs, shard-prefixed IDs) instead of hardcoded values
- Add health checks to database services so tests do not start before the DB is ready
- Use `fail-fast: false` so you see all shard failures, not just the first one
- Add test result artifacts for post-failure analysis across shards'''),

    ("thinking/debugging", r'''Our deployment gate in GitHub Actions is timing out. The workflow waits for manual approval before deploying to production, but the approval step times out after 6 hours even though reviewers respond within minutes:

```yaml
name: Production Deploy
on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t myapp:${{ github.sha }} .
      - run: docker push registry.example.com/myapp:${{ github.sha }}

  staging-deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - run: kubectl set image deployment/myapp myapp=registry.example.com/myapp:${{ github.sha }}
      - run: kubectl rollout status deployment/myapp --timeout=300s

  staging-test:
    needs: staging-deploy
    runs-on: ubuntu-latest
    steps:
      - run: |
          for i in $(seq 1 10); do
            curl -sf https://staging.example.com/health && break
            sleep 30
          done
      - run: pytest tests/integration/ --base-url=https://staging.example.com

  production-approval:
    needs: staging-test
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://app.example.com
    steps:
      - run: echo "Approved for production deployment"

  production-deploy:
    needs: production-approval
    runs-on: ubuntu-latest
    steps:
      - run: kubectl set image deployment/myapp myapp=registry.example.com/myapp:${{ github.sha }}
      - run: |
          kubectl rollout status deployment/myapp --timeout=600s
          echo "Production deploy complete!"
```

Error:
```
production-approval: This job was cancelled because "production"
has a wait timer. The wait timer has expired.
```

We configured the "production" environment with "Required reviewers" and a "Wait timer" of 360 minutes. Reviewers approved within 10 minutes, but the job still timed out.''', r'''<think>
The "Wait timer" in GitHub environment protection rules is NOT a timeout -- it is a DELAY. It means the deployment must wait for the specified time AFTER approval before it can proceed. Setting it to 360 minutes (6 hours) means that even after approval, the job waits 6 hours before running.

The user likely confused "Wait timer" with "Approval timeout." They wanted a 6-hour window for reviewers to respond, but instead they set a 6-hour mandatory delay after approval.

The "Wait timer" is intended for use cases like: "After approval, wait 2 hours before deploying" (to deploy during off-peak hours, or to give time for a cooldown period).

The workflow timeout (default 6 hours / 360 minutes) is what limits how long the entire job can wait. If the wait timer exceeds the workflow timeout, the job times out.

The fix: remove or reduce the wait timer and use only the required reviewers protection rule. If they want a timeout for the approval window, that is controlled by the workflow-level `timeout-minutes`.
</think>

The "Wait timer" in GitHub environment protection rules is NOT an approval timeout -- it is a **mandatory delay AFTER approval**. Setting it to 360 minutes means: "After the reviewer approves, wait 6 hours before the job starts." This is the opposite of what you intended.

**What is actually happening:**

```
1. staging-test completes
2. production-approval job starts
3. GitHub sends review request to approvers
4. Reviewer approves within 10 minutes
5. Wait timer starts: 360 minutes of mandatory waiting AFTER approval
6. The GitHub Actions workflow timeout (default: 360 minutes) expires
7. Job is cancelled -- "wait timer has expired"
```

**The environment protection rules explained:**

```
"Required reviewers":
  - Blocks the job until a reviewer approves
  - No built-in timeout -- waits until the workflow timeout

"Wait timer" (0-43200 minutes):
  - ADDITIONAL delay AFTER approval before the job can run
  - NOT a timeout for getting approval
  - Use case: deploy at a specific time, cooldown periods

"Deployment branches":
  - Restricts which branches can deploy to this environment
```

**Fix: Remove the wait timer, keep only required reviewers:**

Go to: Repository Settings -> Environments -> production

```
Required reviewers: [x] Enable
  Reviewers: @team-leads, @devops
  (approval gates the deployment)

Wait timer: 0 minutes   <-- Set to 0!
  (or remove entirely -- you do not want a post-approval delay)
```

**If you want a timeout for the approval window (not a delay after approval):**

```yaml
production-approval:
    needs: staging-test
    runs-on: ubuntu-latest
    timeout-minutes: 360  # Job-level timeout: cancel if no approval in 6 hours
    environment:
      name: production
      url: https://app.example.com
    steps:
      - run: echo "Approved for production deployment"
```

**If you want to deploy only during business hours:**

```yaml
production-approval:
    needs: staging-test
    runs-on: ubuntu-latest
    environment:
      name: production
    steps:
      - name: Check deployment window
        run: |
          HOUR=$(TZ=America/New_York date +%H)
          DAY=$(TZ=America/New_York date +%u)
          if [ "$DAY" -gt 5 ]; then
            echo "ERROR: No weekend deployments"
            exit 1
          fi
          if [ "$HOUR" -lt 9 ] || [ "$HOUR" -gt 16 ]; then
            echo "ERROR: Deploy only between 9 AM and 4 PM ET"
            exit 1
          fi
          echo "Within deployment window, proceeding..."
```

**Complete production-safe deployment workflow:**

```yaml
name: Production Deploy
on:
  push:
    branches: [main]

concurrency:
  group: production-deploy
  cancel-in-progress: false  # Never cancel an in-progress deploy

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      image-tag: ${{ github.sha }}
    steps:
      - uses: actions/checkout@v4
      - run: |
          docker build -t registry.example.com/myapp:${{ github.sha }} .
          docker push registry.example.com/myapp:${{ github.sha }}

  staging-deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - run: |
          kubectl set image deployment/myapp \
            myapp=registry.example.com/myapp:${{ needs.build.outputs.image-tag }}
          kubectl rollout status deployment/myapp --timeout=300s

  staging-test:
    needs: staging-deploy
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - run: pytest tests/integration/ --base-url=https://staging.example.com

  production-gate:
    needs: staging-test
    runs-on: ubuntu-latest
    timeout-minutes: 480  # 8 hours for approval
    environment:
      name: production      # Required reviewers configured here (NO wait timer!)
      url: https://app.example.com
    steps:
      - run: echo "Deployment approved at $(date -u)"

  production-deploy:
    needs: [build, production-gate]
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - run: |
          kubectl set image deployment/myapp \
            myapp=registry.example.com/myapp:${{ needs.build.outputs.image-tag }}
          kubectl rollout status deployment/myapp --timeout=600s

      - name: Verify deployment
        run: |
          sleep 10
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://app.example.com/health)
          if [ "$STATUS" != "200" ]; then
            echo "Health check failed! Rolling back..."
            kubectl rollout undo deployment/myapp
            exit 1
          fi
          echo "Production deployment verified successfully"
```

**Prevention tips:**
- "Wait timer" is a post-approval DELAY, not an approval timeout -- set it to 0 unless you need a cooldown
- Use `timeout-minutes` on the job for approval window limits
- Use `concurrency` groups to prevent overlapping production deployments
- Add a health check after deployment with automatic rollback on failure
- Use `cancel-in-progress: false` for production deploys to prevent accidental cancellation
- Document your environment protection rules in the repo README so the team understands the gates'''),
]
