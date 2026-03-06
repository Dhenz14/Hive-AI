r"""Thinking-trace pairs: CI/CD pipeline code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this GitHub Actions workflow and identify issues:

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: pip install -r requirements-dev.txt
      - run: pytest

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: pip install -r requirements-dev.txt
      - run: flake8 src/
      - run: black --check src/
      - run: mypy src/

  build:
    runs-on: ubuntu-latest
    needs: [test, lint]
    steps:
      - uses: actions/checkout@v3
      - run: docker build -t myapp:${{ github.sha }} .
      - run: echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin
        env:
          DOCKER_USERNAME: ${{ secrets.DOCKER_USERNAME }}
          DOCKER_PASSWORD: ${{ secrets.DOCKER_PASSWORD }}
      - run: docker push myapp:${{ github.sha }}

  deploy-staging:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - uses: actions/checkout@v3
      - run: |
          ssh deploy@staging.example.com "
            docker pull myapp:${{ github.sha }}
            docker stop myapp || true
            docker rm myapp || true
            docker run -d --name myapp -p 80:8000 \
              -e DATABASE_URL=${{ secrets.STAGING_DB_URL }} \
              -e SECRET_KEY=${{ secrets.STAGING_SECRET }} \
              myapp:${{ github.sha }}
          "

  deploy-production:
    runs-on: ubuntu-latest
    needs: deploy-staging
    steps:
      - uses: actions/checkout@v3
      - run: |
          ssh deploy@prod.example.com "
            docker pull myapp:${{ github.sha }}
            docker stop myapp || true
            docker rm myapp || true
            docker run -d --name myapp -p 80:8000 \
              -e DATABASE_URL=${{ secrets.PROD_DB_URL }} \
              -e SECRET_KEY=${{ secrets.PROD_SECRET }} \
              myapp:${{ github.sha }}
          "
```''', r'''<think>
Let me analyze this GitHub Actions workflow for security, reliability, caching, and deployment issues.

Security issues:
- Secrets passed via -e flags in docker run commands are visible in process listings and docker inspect
- SSH to production servers directly from CI with no key management shown
- No environment protection rules on production deployment
- docker login before push is fine, but the image is pushed to what appears to be Docker Hub without an org/namespace prefix
- Secrets in deploy commands could be logged if the SSH command fails

Caching:
- No pip caching - installs all dependencies from scratch on every run
- No Docker layer caching - builds from scratch every time
- requirements.txt installed twice (test and lint jobs) with no caching between them
- No setup-python cache option used

Deployment:
- deploy-production runs automatically after deploy-staging with no manual approval gate
- Both staging and production use identical deployment strategy (stop, rm, run) - this causes downtime
- No health check after deployment
- No rollback mechanism if deployment fails
- No smoke tests between staging and production
- Single container deployment (docker run) instead of orchestration - no zero-downtime deployment

Reliability:
- No timeout on jobs
- No concurrency control - multiple pushes to main could trigger simultaneous deployments
- deploy-staging deploys on every push to main, even PRs that just got merged
- No artifact passing between build and deploy - the deploy jobs pull the image independently

Missing:
- No dependency caching
- No test result reporting
- No code coverage
- No security scanning (Snyk, Trivy, etc.)
- No container image scanning
- No notification on failure
- ubuntu-latest is mutable
- Old action versions (v3, v4 instead of v5)
</think>

## Code Review: GitHub Actions CI/CD Pipeline

### CRITICAL - No Manual Approval for Production Deployment
`deploy-production` runs automatically after `deploy-staging` with no approval gate. Any push to main that passes tests goes straight to production without human review or staging validation.

**Fix:** Use GitHub Environments with required reviewers:
```yaml
deploy-production:
    runs-on: ubuntu-latest
    needs: deploy-staging
    environment:
        name: production
        url: https://myapp.example.com
```
Then configure the `production` environment in repo settings to require approvals.

### CRITICAL - Downtime During Deployment
Both staging and production deployments use `docker stop && docker rm && docker run`. This creates a window where no container is serving traffic. For production, this means user-facing downtime on every deploy.

**Fix:** Use a zero-downtime strategy such as blue-green deployment, or use Docker Swarm/Kubernetes with rolling updates.

### HIGH - No Dependency Caching
Both `test` and `lint` jobs install all Python dependencies from scratch. This wastes time and bandwidth on every run.

**Fix:**
```yaml
- uses: actions/setup-python@v5
  with:
      python-version: "3.11"
      cache: "pip"
```

### HIGH - No Docker Build Cache
The Docker build runs without any layer caching, rebuilding everything from scratch each time. This can add 5-15 minutes per build.

**Fix:**
```yaml
- uses: docker/build-push-action@v5
  with:
      context: .
      push: true
      tags: myapp:${{ github.sha }}
      cache-from: type=gha
      cache-to: type=gha,mode=max
```

### HIGH - No Post-Deployment Health Check
After deployment, there is no verification that the new container is actually healthy and serving requests. A crash-on-startup would go unnoticed until users report it.

**Fix:** Add a health check step after docker run:
```yaml
- run: |
    for i in $(seq 1 30); do
        if curl -sf http://staging.example.com/health; then
            echo "Health check passed"
            exit 0
        fi
        sleep 2
    done
    echo "Health check failed"
    exit 1
```

### HIGH - Secrets Exposed via Docker Run
Passing secrets through `-e DATABASE_URL=${{ secrets.PROD_DB_URL }}` in an SSH command means the secret values are in the SSH command string, potentially logged by the shell history on the remote server and visible in `docker inspect`.

**Fix:** Use Docker secrets, a .env file deployed separately, or a secrets manager that the container reads at startup.

### MEDIUM - No Concurrency Control
Multiple pushes to main trigger parallel pipeline runs. Two simultaneous deployments will race to stop/start containers, causing unpredictable states.

**Fix:**
```yaml
concurrency:
    group: deploy-${{ github.ref }}
    cancel-in-progress: false
```

### MEDIUM - No Rollback Mechanism
If a deployment fails or the new version has bugs, there is no automated rollback. The previous image tag is not recorded.

### MEDIUM - Outdated Action Versions
Using `actions/checkout@v3` and `actions/setup-python@v4` instead of current versions. Older versions may have security vulnerabilities and miss performance improvements.

### LOW - No Test Reporting or Coverage
pytest runs but results are not uploaded as artifacts or reported on the PR. No coverage thresholds are enforced.'''),

    ("thinking/code-review", r'''Review this CI/CD configuration with matrix builds and identify issues:

```yaml
name: Matrix CI

on:
  push:
    branches: ["*"]
  pull_request:

jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ["3.8", "3.9", "3.10", "3.11", "3.12"]
        database: [postgres, mysql, sqlite]
      fail-fast: false

    runs-on: ${{ matrix.os }}

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
      mysql:
        image: mysql:8
        env:
          MYSQL_ROOT_PASSWORD: test
          MYSQL_DATABASE: test
        ports:
          - 3306:3306

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - run: pip install -r requirements.txt
      - run: pip install -r requirements-test.txt

      - name: Run tests
        env:
          DATABASE_TYPE: ${{ matrix.database }}
          DATABASE_URL: postgresql://postgres:test@localhost:5432/postgres
        run: pytest tests/ -v --tb=short

      - name: Upload coverage
        run: |
          pip install codecov
          codecov --token=${{ secrets.CODECOV_TOKEN }}

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install safety bandit
      - run: safety check -r requirements.txt
      - run: bandit -r src/ -f json -o bandit-report.json
```''', r'''<think>
Let me analyze this matrix CI configuration for efficiency, correctness, and waste.

Matrix explosion:
- 3 OS x 5 Python versions x 3 databases = 45 combinations
- This is massively wasteful. Not all combinations are meaningful.
- macOS and Windows runners are more expensive (10x and 2x respectively)
- fail-fast: false means all 45 jobs run to completion even if the first one fails

Service container issues:
- Both postgres AND mysql services are started for every matrix combination, even when testing with sqlite
- Services are only available on ubuntu runners, not macOS or Windows. The postgres and mysql jobs on macOS and Windows will fail.
- DATABASE_URL is hardcoded to postgresql regardless of the matrix.database value
- The mysql service is started but DATABASE_URL never points to it

Coverage upload:
- Runs 45 times, uploading potentially conflicting coverage reports
- Uses pip install codecov (deprecated CLI) instead of the codecov GitHub Action
- CODECOV_TOKEN exposed as environment variable

Trigger issues:
- push on all branches ("*") means every push to every branch triggers 45 jobs
- Combined with PR trigger, a push to a PR branch triggers the matrix TWICE (once for push, once for PR)

Security scan:
- safety check uses the free database which is outdated
- bandit output goes to a JSON file but is never uploaded as an artifact
- No failure threshold on bandit

Other:
- No caching for pip dependencies
- Python 3.8 is EOL (October 2024)
- No timeout on jobs
</think>

## Code Review: Matrix CI Configuration

### CRITICAL - 45-Job Matrix Is Wasteful and Broken
The matrix produces 3 OS x 5 Python x 3 DB = 45 job combinations. This is excessive and fundamentally broken because:
1. Docker service containers (postgres, mysql) only work on Linux runners. All macOS and Windows jobs that need postgres/mysql will fail.
2. Both postgres AND mysql services start for every job, even sqlite tests.
3. Total: 30 of 45 jobs are guaranteed to fail or waste resources.

**Fix:** Use `include`/`exclude` to define meaningful combinations:
```yaml
strategy:
    matrix:
        include:
            - os: ubuntu-latest
              python-version: "3.12"
              database: postgres
            - os: ubuntu-latest
              python-version: "3.12"
              database: mysql
            - os: ubuntu-latest
              python-version: "3.12"
              database: sqlite
            - os: ubuntu-latest
              python-version: "3.9"
              database: postgres
            - os: macos-latest
              python-version: "3.12"
              database: sqlite
            - os: windows-latest
              python-version: "3.12"
              database: sqlite
```

### CRITICAL - DATABASE_URL Ignores Matrix Variable
`DATABASE_URL` is hardcoded to `postgresql://...` regardless of `matrix.database`. When `database: mysql` or `database: sqlite`, the tests still connect to PostgreSQL. The matrix variable has no effect.

**Fix:** Set DATABASE_URL conditionally:
```yaml
env:
    DATABASE_URL: ${{ matrix.database == 'postgres' && 'postgresql://postgres:test@localhost:5432/postgres' || matrix.database == 'mysql' && 'mysql://root:test@localhost:3306/test' || 'sqlite:///test.db' }}
```

### HIGH - Double Triggering on PR Branches
`push: branches: ["*"]` combined with `pull_request` means any push to a PR branch triggers the pipeline twice: once for the push event and once for the PR event. This doubles resource usage.

**Fix:** Only trigger on main for push, and use PR events for branches:
```yaml
on:
    push:
        branches: [main]
    pull_request:
```

### HIGH - Coverage Uploaded 45 Times
Every matrix job uploads coverage independently using the deprecated `codecov` pip package. This produces conflicting reports and wastes time.

**Fix:** Use the official codecov action, upload per-job with flags, and merge:
```yaml
- uses: codecov/codecov-action@v4
  with:
      flags: ${{ matrix.os }}-py${{ matrix.python-version }}-${{ matrix.database }}
      token: ${{ secrets.CODECOV_TOKEN }}
```

### MEDIUM - Python 3.8 Is End-of-Life
Python 3.8 reached EOL in October 2024. Testing against it wastes CI minutes on an unsupported version. Remove it unless you have users who explicitly require it.

### MEDIUM - No Dependency Caching
45 jobs each install all pip dependencies from scratch. Even reduced to 6-8 jobs, caching saves significant time.

### MEDIUM - Security Scan Results Not Captured
`bandit -r src/ -f json -o bandit-report.json` writes to a file that is never uploaded as an artifact. The report is lost when the job completes.

**Fix:**
```yaml
- uses: actions/upload-artifact@v4
  with:
      name: bandit-report
      path: bandit-report.json
```

### LOW - No Job Timeouts
No `timeout-minutes` specified. A hung test suite will consume runner minutes for the default 6-hour limit.

**Fix:** Add `timeout-minutes: 15` to each job.'''),

    ("thinking/code-review", r'''Review this deployment script with secrets management and identify issues:

```python
import os
import subprocess
import yaml
import json
import base64
import requests

class Deployer:
    def __init__(self):
        self.config = self._load_config()
        self.secrets = self._load_secrets()

    def _load_config(self):
        with open("deploy-config.yaml") as f:
            return yaml.safe_load(f)

    def _load_secrets(self):
        secrets_file = os.environ.get("SECRETS_FILE", "secrets.json")
        with open(secrets_file) as f:
            return json.load(f)

    def deploy(self, environment):
        env_config = self.config["environments"][environment]
        env_secrets = self.secrets[environment]

        image = f"{env_config['registry']}/{env_config['image']}:{env_config['tag']}"

        self._docker_login(env_config["registry"], env_secrets)
        self._pull_image(image)
        self._update_env_file(environment, env_secrets)
        self._restart_service(env_config, image)
        self._notify_slack(environment, env_config["tag"])

    def _docker_login(self, registry, secrets):
        subprocess.run(
            f"docker login {registry} -u {secrets['docker_user']} "
            f"-p {secrets['docker_password']}",
            shell=True, check=True
        )

    def _pull_image(self, image):
        subprocess.run(f"docker pull {image}", shell=True, check=True)

    def _update_env_file(self, environment, secrets):
        env_content = ""
        for key, value in secrets.items():
            env_content += f"{key.upper()}={value}\n"

        with open(f"/opt/myapp/{environment}/.env", "w") as f:
            f.write(env_content)

    def _restart_service(self, config, image):
        host = config["host"]
        subprocess.run(
            f"ssh {host} 'cd /opt/myapp && docker-compose down && "
            f"IMAGE={image} docker-compose up -d'",
            shell=True, check=True
        )

    def _notify_slack(self, environment, tag):
        webhook_url = self.secrets.get("slack_webhook")
        if webhook_url:
            requests.post(webhook_url, json={
                "text": f"Deployed {tag} to {environment}"
            })

    def rollback(self, environment, tag):
        env_config = self.config["environments"][environment].copy()
        env_config["tag"] = tag
        image = f"{env_config['registry']}/{env_config['image']}:{tag}"
        self._restart_service(env_config, image)

    def run_migrations(self, environment):
        env_config = self.config["environments"][environment]
        host = env_config["host"]
        db_url = self.secrets[environment]["database_url"]
        subprocess.run(
            f'ssh {host} "DATABASE_URL={db_url} docker-compose exec web '
            f'python manage.py migrate"',
            shell=True, check=True
        )

    def create_backup(self, environment):
        env_config = self.config["environments"][environment]
        host = env_config["host"]
        db_url = self.secrets[environment]["database_url"]

        subprocess.run(
            f'ssh {host} "pg_dump {db_url} > /backups/backup_$(date +%Y%m%d).sql"',
            shell=True, check=True
        )

    def verify_deployment(self, environment):
        env_config = self.config["environments"][environment]
        url = f"https://{env_config['domain']}/health"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"Health check failed: {response.status_code}")
            return False
        return True
```''', r'''<think>
Let me analyze this deployment script for security, reliability, and design issues.

Security - this is extremely concerning:

1. _docker_login passes password via -p flag on command line. This is visible in process listings (ps aux) and shell history. Docker warns against this.

2. secrets.json loaded from file - if this file is in the repo, all secrets are in version control. Even if not, it is a plaintext file on disk.

3. _update_env_file writes all secrets to a .env file on disk in plaintext. This file persists after deployment.

4. run_migrations passes DATABASE_URL (containing credentials) as a command-line argument via SSH. This is visible in process listings on both the local and remote machines.

5. create_backup passes the full database URL (with credentials) as a command argument.

6. shell=True everywhere with f-strings - command injection if any config values contain shell metacharacters.

7. _docker_login credentials visible in CI logs if the step fails and prints the command.

Reliability:
- No error handling beyond check=True
- rollback does not restore the .env file to previous values
- No backup verification (create_backup just runs pg_dump, never checks if the file is valid)
- verify_deployment only checks HTTP 200, not response body
- No timeout on SSH commands
- _notify_slack silently ignores failures

Design:
- environment parameter not validated - could key-error on invalid environment
- No locking mechanism - two deploys to the same environment simultaneously will conflict
- No deployment history tracking
- create_backup uses date-based naming which overwrites if run twice in one day
- rollback does not re-run migrations (downgrade) - schema could be incompatible

YAML loading:
- yaml.safe_load is used (good, not yaml.load)
- But no schema validation on the loaded config
</think>

## Code Review: Deployment Script with Secrets Management

### CRITICAL - Credentials Exposed via Command Line
`_docker_login` passes the password via `-p` flag, which is visible in process listings (`ps aux`), shell history, and CI logs. Similarly, `run_migrations` and `create_backup` pass `DATABASE_URL` (containing credentials) as command-line arguments through SSH.

**Fix for docker login:**
```python
def _docker_login(self, registry, secrets):
    subprocess.run(
        ["docker", "login", registry, "-u", secrets["docker_user"],
         "--password-stdin"],
        input=secrets["docker_password"].encode(),
        check=True
    )
```

**Fix for database URL:** Write credentials to a temporary file on the remote host or use environment variables via SSH:
```python
subprocess.run(
    ["ssh", host, f"export DATABASE_URL='{db_url}' && docker-compose exec web python manage.py migrate"],
    check=True
)
```

### CRITICAL - Plaintext Secrets Written to Disk
`_update_env_file` writes all secrets (database passwords, API keys, etc.) to a `.env` file on the deployment target. This file persists indefinitely, is readable by any user with file access, and may be backed up unencrypted.

**Fix:** Use a proper secrets manager (HashiCorp Vault, AWS Secrets Manager, Docker secrets) instead of .env files. If .env is unavoidable, set restrictive permissions:
```python
os.chmod(env_path, 0o600)
```

### CRITICAL - Command Injection via shell=True
All subprocess calls use `shell=True` with f-string interpolation. If any config value (host, registry, image name) contains shell metacharacters, arbitrary commands can be executed.

**Fix:** Use list form without shell:
```python
subprocess.run(["docker", "pull", image], check=True)
subprocess.run(["ssh", host, command_string], check=True)
```

### HIGH - No Deployment Locking
Two simultaneous deployments to the same environment will race, potentially leaving the environment in an inconsistent state (e.g., one deployment pulls a new image while the other is mid-restart).

**Fix:** Implement a file-based or distributed lock:
```python
import fcntl

def deploy(self, environment):
    lock_file = f"/tmp/deploy-{environment}.lock"
    with open(lock_file, "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f"Deployment to {environment} already in progress")
        # ... deploy logic
```

### HIGH - Rollback Does Not Restore Secrets
`rollback` calls `_restart_service` but does not restore the `.env` file to its previous state. If the new deployment changed environment variables, rolling back the image but keeping new env vars may cause incompatibilities.

### MEDIUM - No Backup Verification
`create_backup` runs `pg_dump` but never verifies the backup was successful (non-empty file, valid SQL). A failed pg_dump could produce a 0-byte file that looks like a successful backup.

### MEDIUM - Slack Notification Silently Fails
`_notify_slack` catches no exceptions and does not check the response status. A failed notification gives the false impression that the team was informed.

### MEDIUM - Date-Based Backup Name Collision
`backup_$(date +%Y%m%d).sql` overwrites if run twice in the same day. Use a timestamp with time: `%Y%m%d_%H%M%S`.

### LOW - No Configuration Validation
The loaded YAML config and JSON secrets are used directly without schema validation. A missing key produces a confusing KeyError instead of a clear configuration error message.'''),

    ("thinking/code-review", r'''Review this GitHub Actions workflow with caching and artifacts:

```yaml
name: Build and Test

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  install:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 18

      - name: Cache node_modules
        uses: actions/cache@v3
        with:
          path: node_modules
          key: node-modules-${{ hashFiles('package-lock.json') }}

      - run: npm install

  lint:
    needs: install
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 18

      - name: Restore node_modules cache
        uses: actions/cache@v3
        with:
          path: node_modules
          key: node-modules-${{ hashFiles('package-lock.json') }}

      - run: npx eslint src/
      - run: npx prettier --check src/

  test:
    needs: install
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 18

      - name: Restore node_modules cache
        uses: actions/cache@v3
        with:
          path: node_modules
          key: node-modules-${{ hashFiles('package-lock.json') }}

      - run: npx jest --coverage --ci
      - run: npx jest --coverage --ci --reporters=default

      - name: Save coverage report
        run: |
          mkdir -p coverage-report
          cp coverage/lcov.info coverage-report/
          cp -r coverage/lcov-report coverage-report/

  build:
    needs: [lint, test]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 18

      - name: Restore node_modules cache
        uses: actions/cache@v3
        with:
          path: node_modules
          key: node-modules-${{ hashFiles('package-lock.json') }}

      - run: npm run build
      - run: ls -la dist/

      - name: Upload build artifact
        uses: actions/upload-artifact@v3
        with:
          name: build-output
          path: dist/

  e2e:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 18

      - name: Download build
        uses: actions/download-artifact@v3
        with:
          name: build-output
          path: dist/

      - run: npm install
      - run: npx playwright install
      - run: npx playwright test
```''', r'''<think>
Let me analyze this workflow for caching strategy, artifact management, and efficiency issues.

Caching problems:
1. The cache key uses only package-lock.json hash, but caches node_modules. Using `npm install` instead of `npm ci` means the cache could contain stale packages. `npm ci` deletes node_modules and does a clean install from the lock file.

2. Cache is used across separate jobs (install, lint, test, build) but cache is not guaranteed to be available in dependent jobs. GitHub Actions cache is best-effort - if cache eviction happens or the cache was created on a different runner, the dependent jobs will fail because node_modules won't exist and no `npm install` fallback is in the lint/test/build jobs.

3. The install job creates the cache, but lint/test/build only restore it. If the cache restore fails (miss), those jobs have no npm install step and will fail with "command not found" errors.

4. actions/cache@v3 is outdated - v4 is current.

Artifact issues:
1. actions/upload-artifact@v3 and download-artifact@v3 are outdated (v4 is current and has breaking changes in how artifacts work).
2. Coverage report is generated but never uploaded as an artifact - it is saved to a local directory that disappears when the job ends.

Test execution:
1. Jest is run twice in the test job: `npx jest --coverage --ci` and then `npx jest --coverage --ci --reporters=default`. This doubles test execution time for no reason (the --reporters flag just changes the output format, which could be combined).

E2E job issues:
1. Downloads the build artifact but does a full `npm install` from scratch (no cache restore). This is slow and installs all dependencies including dev deps.
2. `npx playwright install` downloads browser binaries with no caching. This can take 2-3 minutes.
3. No Playwright browser caching.

Workflow structure:
- 5 sequential jobs (install -> lint/test -> build -> e2e) means the pipeline is mostly serial despite some parallelism between lint and test.
- Each job checks out code and sets up Node independently.
- The install job does nothing except create a cache - this is an unnecessary job.

Missing:
- No cancel-in-progress for the same PR
- No timeout on jobs
- No test result reporting to PR
- No coverage threshold enforcement
</think>

## Code Review: GitHub Actions Build and Test Workflow

### CRITICAL - Cache Miss Causes Job Failures
The `lint`, `test`, and `build` jobs rely entirely on the cache from the `install` job but have no `npm install` fallback. GitHub Actions cache is best-effort. If the cache is evicted, corrupted, or unavailable (different runner), these jobs will fail because `node_modules` will not exist.

**Fix:** Always include an install step after cache restore:
```yaml
- name: Restore cache
  uses: actions/cache@v4
  id: cache
  with:
      path: node_modules
      key: node-modules-${{ hashFiles('package-lock.json') }}

- name: Install dependencies
  if: steps.cache.outputs.cache-hit != 'true'
  run: npm ci
```

### HIGH - npm install Instead of npm ci
`npm install` can modify `package-lock.json` and may not produce deterministic installs. In CI, always use `npm ci` which does a clean install from the lock file and fails if the lock file is out of sync.

### HIGH - Jest Runs Twice
The test job runs Jest twice:
```yaml
- run: npx jest --coverage --ci
- run: npx jest --coverage --ci --reporters=default
```
The second run adds `--reporters=default` which is already the default behavior. This doubles test execution time with no benefit.

**Fix:** Run once with all desired reporters:
```yaml
- run: npx jest --coverage --ci --reporters=default --reporters=jest-junit
```

### HIGH - Coverage Report Never Uploaded
Coverage files are copied to `coverage-report/` but never uploaded as an artifact. When the job ends, the runner is destroyed and the coverage data is lost.

**Fix:**
```yaml
- uses: actions/upload-artifact@v4
  with:
      name: coverage-report
      path: coverage/lcov-report/
```

### MEDIUM - Unnecessary Install Job
The `install` job exists solely to populate the cache. This adds a full job setup overhead (checkout, node setup, ~30 seconds) just to run `npm install`. Merge it into the first dependent jobs.

**Fix:** Remove the `install` job. Run `lint` and `test` in parallel, each with their own cache restore and conditional install.

### MEDIUM - E2E Job Has No Browser Caching
`npx playwright install` downloads browser binaries (~500MB) on every run. This adds 2-3 minutes of download time.

**Fix:**
```yaml
- name: Cache Playwright browsers
  uses: actions/cache@v4
  with:
      path: ~/.cache/ms-playwright
      key: playwright-${{ hashFiles('package-lock.json') }}

- run: npx playwright install --with-deps
```

### MEDIUM - Outdated Action Versions
Using `actions/cache@v3`, `actions/upload-artifact@v3`, and `actions/download-artifact@v3`. Version 4 of these actions has significant improvements and breaking changes. The artifact v3 actions will be deprecated.

### LOW - No Concurrency Control
Multiple pushes to the same PR trigger parallel workflow runs. Add concurrency to cancel previous runs:
```yaml
concurrency:
    group: ${{ github.workflow }}-${{ github.event.pull_request.number }}
    cancel-in-progress: true
```

### LOW - No Job Timeouts
No `timeout-minutes` on any job. A hung Playwright test or build could run for hours.'''),

    ("thinking/code-review", r'''Review this CI/CD pipeline configuration and identify issues:

```yaml
name: Release Pipeline

on:
  push:
    tags:
      - "v*"

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  validate-tag:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.version.outputs.value }}
    steps:
      - id: version
        run: echo "value=${GITHUB_REF#refs/tags/v}" >> $GITHUB_OUTPUT

  build-and-push:
    needs: validate-tag
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ needs.validate-tag.outputs.version }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest

  create-release:
    needs: [validate-tag, build-and-push]
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: softprops/action-gh-release@v1
        with:
          generate_release_notes: true
          draft: false
          prerelease: false

  deploy-staging:
    needs: [validate-tag, build-and-push]
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - run: |
          curl -X POST "${{ secrets.DEPLOY_WEBHOOK_URL }}/deploy" \
            -H "Authorization: Bearer ${{ secrets.DEPLOY_TOKEN }}" \
            -H "Content-Type: application/json" \
            -d '{"image": "${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ needs.validate-tag.outputs.version }}", "environment": "staging"}'

  deploy-production:
    needs: [deploy-staging]
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - run: |
          curl -X POST "${{ secrets.DEPLOY_WEBHOOK_URL }}/deploy" \
            -H "Authorization: Bearer ${{ secrets.DEPLOY_TOKEN }}" \
            -H "Content-Type: application/json" \
            -d '{"image": "${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ needs.validate-tag.outputs.version }}", "environment": "production"}'

      - name: Verify deployment
        run: |
          sleep 30
          curl -sf https://myapp.example.com/health
```''', r'''<think>
Let me analyze this release pipeline for security, reliability, and design issues.

Positive aspects:
- Uses GHCR (GitHub Container Registry) with GITHUB_TOKEN - no external credentials needed
- Proper permissions scoping per job
- Uses environments for staging and production
- Semantic versioning from tags
- Auto-generated release notes

Issues:

1. validate-tag does minimal validation - just strips the "v" prefix. Does not validate that the tag follows semver. A tag like "vFOO" would be accepted.

2. build-and-push always pushes :latest tag. This means any release (including patches and pre-releases) overwrites :latest. Also, if tags are not pushed in order (e.g., v1.1.0 after v2.0.0 was released), :latest could point to an older version.

3. create-release has prerelease: false hardcoded. Tags like v1.0.0-beta.1 or v2.0.0-rc.1 should be marked as prerelease but will not be.

4. deploy-staging and deploy-production use curl to a webhook API. The curl commands:
   - No response code checking (no -f flag or response validation)
   - No timeout specified for the HTTP request
   - No retry on transient failure
   - deploy-production calls the SAME webhook URL as staging - only the JSON body differs. If the webhook URL rotates, both break.

5. deploy-production verification:
   - sleep 30 is a magic number - fragile timing assumption
   - Single curl to /health is insufficient - should retry
   - No verification of which VERSION is running (the health check might pass with the old version still serving)

6. deploy-production uses needs: [deploy-staging] but does NOT reference validate-tag. It inherits the version from validate-tag through the needs chain, but the version output is only accessible if deploy-production lists validate-tag in its needs. Wait - it does use needs.validate-tag.outputs.version in the curl command but validate-tag is not in its needs array! This will fail with an empty version.

7. No test job - the pipeline goes straight from build to deploy with no test verification.

8. No rollback if production deployment fails.

9. create-release and deploy-staging run in parallel (both need validate-tag and build-and-push). The release is created before staging deployment is verified.

10. softprops/action-gh-release@v1 - should use v2.
</think>

## Code Review: Release Pipeline

### CRITICAL - deploy-production Cannot Access Version Output
`deploy-production` uses `${{ needs.validate-tag.outputs.version }}` but `validate-tag` is not listed in its `needs` array. Only `deploy-staging` is listed. Job outputs are only accessible from jobs listed in `needs`. The version will be empty, deploying an untagged or invalid image.

**Fix:**
```yaml
deploy-production:
    needs: [deploy-staging, validate-tag]
```

### CRITICAL - No Test Job in Release Pipeline
The pipeline goes directly from build to deploy with no test execution. A tagged release is assumed to be tested, but if someone tags a commit that was never tested (e.g., direct push to main), broken code goes to production.

**Fix:** Add a test job that build-and-push depends on:
```yaml
test:
    runs-on: ubuntu-latest
    steps:
        - uses: actions/checkout@v4
        - run: npm ci && npm test
build-and-push:
    needs: [validate-tag, test]
```

### HIGH - :latest Tag Always Overwritten
Every release pushes the `:latest` tag, including patch releases and potential out-of-order tag pushes. If v1.2.1 is tagged after v2.0.0, `:latest` will incorrectly point to v1.2.1.

**Fix:** Only push `:latest` for the highest version, or remove `:latest` tagging entirely and use explicit version tags:
```yaml
tags: |
    ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ needs.validate-tag.outputs.version }}
```

### HIGH - No Deployment Response Validation
The curl deployment commands do not check the HTTP response code or body. A 500 error from the webhook is silently ignored, and the pipeline reports success.

**Fix:**
```yaml
- run: |
    RESPONSE=$(curl -sf -w "\n%{http_code}" -X POST ...)
    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    if [ "$HTTP_CODE" != "200" ]; then
        echo "Deployment failed with HTTP $HTTP_CODE"
        exit 1
    fi
```

### HIGH - Sleep-Based Deployment Verification
`sleep 30` followed by a single health check is fragile. The deployment may take more or less than 30 seconds, and a single check does not verify the correct version is running.

**Fix:** Poll with a version check:
```yaml
- name: Verify deployment
  run: |
      for i in $(seq 1 30); do
          VERSION=$(curl -sf https://myapp.example.com/health | jq -r '.version')
          if [ "$VERSION" = "${{ needs.validate-tag.outputs.version }}" ]; then
              echo "Deployment verified: $VERSION"
              exit 0
          fi
          sleep 5
      done
      echo "Deployment verification timed out"
      exit 1
```

### MEDIUM - Prerelease Tags Not Detected
`prerelease: false` is hardcoded. Tags like `v1.0.0-beta.1` or `v2.0.0-rc.1` will create full releases instead of pre-releases.

**Fix:** Detect pre-release from the tag:
```yaml
prerelease: ${{ contains(needs.validate-tag.outputs.version, '-') }}
```

### MEDIUM - No Tag Format Validation
`validate-tag` only strips the "v" prefix. Tags like `vBROKEN`, `v..1`, or `v1.0.0; echo hacked` are accepted without validation.

**Fix:** Add semver validation:
```bash
VERSION="${GITHUB_REF#refs/tags/v}"
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+'; then
    echo "Invalid version: $VERSION"
    exit 1
fi
```

### MEDIUM - Release Created Before Staging Verification
`create-release` runs in parallel with `deploy-staging`. The GitHub release (visible to users) is published before the code is verified in staging.

### LOW - Outdated Action Version
`softprops/action-gh-release@v1` should be updated to `@v2`.'''),
]
