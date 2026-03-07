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

Starting with the deployment strategy. deploy-production runs automatically after deploy-staging. Could there be environment protection rules configured outside the YAML? Possibly, but there is no `environment:` key in the job definition, so GitHub Environments are not used. This means any push to main that passes tests goes straight to production with no human review or staging validation. That is extremely risky.

Both staging and production use the same deployment pattern: docker stop, docker rm, docker run. Wait, this creates a window where no container is running. For production, that means user-facing downtime on every single deploy. I initially thought the "|| true" on docker stop might indicate awareness of this issue, but actually it just prevents the step from failing if the container does not exist.

Security issues: secrets are passed via -e flags in the SSH command. I considered whether this is acceptable since it is within an SSH session, but actually the -e values are visible in process listings (ps aux) on the remote server and in docker inspect output. Also, the secrets appear in the SSH command string, which means they could end up in shell history on the remote host.

Caching is completely absent. Both test and lint jobs install all Python dependencies from scratch on every run. Could the jobs share a cache? Yes -- setup-python@v4 supports a cache option, and actions/cache could share pip packages. No Docker layer caching either, so the Docker build runs from scratch every time, potentially adding 5-15 minutes per build.

Reliability concerns: no concurrency control means two rapid pushes to main trigger parallel pipeline runs. Hmm, what happens when two deploys run simultaneously? They race to stop and start containers, creating unpredictable states. No timeout on jobs either -- a hung test suite consumes runner minutes until the 6-hour default limit.

No health check after deployment. If the new container crashes on startup, nobody knows until users report it. No rollback mechanism either. Old action versions (checkout@v3, setup-python@v4) should be updated. No test result reporting, no coverage, no security scanning.
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

The matrix produces 3 OS x 5 Python versions x 3 databases = 45 combinations. Could all these be necessary for thorough testing? Hmm, let me think about which combinations actually make sense. macOS and Windows cannot run Docker service containers (postgres, mysql). So 2 OS x 5 Python x 2 DB = 20 of those 45 jobs are guaranteed to fail because the database services will not start. That is already broken.

But wait, even for the Ubuntu jobs, both postgres AND mysql services are started for every combination, even when testing with sqlite. That is wasted resources. And the DATABASE_URL is hardcoded to postgresql://... regardless of the matrix.database value! The mysql and sqlite matrix entries are effectively testing against postgres. The matrix variable has no effect at all. This means the entire matrix is an illusion -- only the OS and Python version dimensions actually vary.

fail-fast: false compounds the waste. All 45 jobs run to completion even if the first one fails immediately. With macOS runners costing 10x and Windows runners 2x the price, this is burning through CI credits.

Trigger configuration: push on branches: ["*"] triggers the pipeline on every push to every branch. Combined with pull_request, a push to a PR branch fires the pipeline TWICE -- once for the push event and once for the PR event. That is 90 jobs per commit on a PR branch.

Coverage upload runs 45 times using the deprecated codecov pip package. I considered whether multiple uploads might merge correctly, but actually each upload can overwrite or conflict with the others. Should use the official codecov GitHub Action with per-job flags.

Python 3.8 reached EOL in October 2024 -- testing against it wastes CI minutes on an unsupported version. No dependency caching, no job timeouts. The bandit security scan outputs to a JSON file that is never uploaded as an artifact, so the report vanishes when the job ends.
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

Security is extremely concerning here. _docker_login passes the password via -p flag on the command line. Could Docker handle this securely? Actually no -- Docker explicitly warns against this because the password is visible in process listings (ps aux) and shell history. I considered whether subprocess might hide it, but shell=True means the entire command string, including the password, is passed to /bin/sh.

secrets.json is loaded from a file. If this file is in the repo, all secrets are in version control. Even if it is not committed, it is a plaintext file on disk with no mentioned permissions restrictions. And _update_env_file makes it worse by writing ALL secrets to a .env file in plaintext that persists indefinitely on the deployment target.

Wait, it gets worse. run_migrations passes DATABASE_URL as a command-line argument in an SSH command string: f'ssh {host} "DATABASE_URL={db_url} ..."'. This URL contains credentials, and it is visible in process listings on both the local and remote machines, in shell history, and potentially in SSH audit logs. create_backup has the same issue with pg_dump {db_url}.

shell=True is used everywhere with f-string interpolation. I initially thought this was just bad practice, but actually it is command injection. If any config value (hostname, registry name, image tag) contains shell metacharacters like ; or $(), arbitrary commands can be executed. Should use the list form of subprocess.run without shell=True.

Reliability issues: rollback calls _restart_service but does not restore the .env file to its previous state. Hmm, so if the new deployment changed environment variables, rolling back the image while keeping the new env vars could cause incompatibilities. create_backup runs pg_dump but never verifies the output -- a failed dump could produce a 0-byte file. The date-based naming (backup_YYYYMMDD.sql) means a second backup on the same day overwrites the first.

No deployment locking -- two simultaneous deploys to the same environment race each other. No deployment history tracking. _notify_slack silently swallows failures. Environment parameter is not validated, so an invalid environment produces a confusing KeyError.
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

The caching strategy has a fundamental flaw. The install job creates a cache of node_modules, and lint/test/build jobs restore it. Could this work reliably? GitHub Actions cache is best-effort -- if the cache is evicted, corrupted, or the dependent job runs on a different runner, the cache restore fails. But wait, the lint/test/build jobs have NO npm install fallback. If the cache miss occurs, node_modules does not exist, and the jobs fail with "command not found" errors. This is a ticking time bomb.

Even when the cache works, using npm install instead of npm ci is problematic. I initially thought they were equivalent, but actually npm install can modify package-lock.json and does not guarantee deterministic installs. npm ci deletes node_modules and does a clean install from the lock file. With npm install, the cache could contain stale or extra packages.

Wait, Jest runs twice in the test job: npx jest --coverage --ci followed by npx jest --coverage --ci --reporters=default. The second run adds --reporters=default, which is already the default behavior. This doubles test execution time for literally zero benefit. The two runs could be combined into one.

Coverage report is generated and copied to coverage-report/ but never uploaded as an artifact. Hmm, I thought the "Save coverage report" step might be followed by an upload step, but no -- the files disappear when the runner is destroyed. All that coverage data is lost.

The e2e job downloads the build artifact but then runs npm install from scratch with no cache restore. This is slow. And npx playwright install downloads browser binaries (~500MB) on every run with no caching, adding 2-3 minutes.

The install job itself is an unnecessary abstraction. It does nothing except checkout, setup node, and run npm install to populate a cache. That is a full job setup overhead (~30 seconds) for zero productive work. The lint and test jobs should handle their own cache and install.

actions/cache@v3 and upload-artifact@v3 are outdated -- v4 is current. No cancel-in-progress for the same PR, no job timeouts, no test result reporting.
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

First the positives: using GHCR with GITHUB_TOKEN avoids external credentials, permissions are properly scoped per job, and environments are used for staging and production. Auto-generated release notes are a nice touch.

Now the issues. deploy-production uses needs.validate-tag.outputs.version in the curl command. But wait -- validate-tag is NOT listed in deploy-production's needs array, only deploy-staging is. In GitHub Actions, job outputs are only accessible from jobs explicitly listed in needs. Hmm, could it inherit through the chain? No -- GitHub Actions requires direct needs references. This means the version will be empty, and the deployment sends an image tag with no version. This is a critical bug.

No test job in the pipeline. I initially assumed tests would be run before tagging, but there is no guarantee. If someone tags a commit directly on main without going through a PR, untested code goes straight to production. Should add a test job that build-and-push depends on.

build-and-push always pushes the :latest tag. Could this be intentional for convenience? The problem is that if tags are pushed out of order (e.g., v1.2.1 hotfix after v2.0.0 was released), :latest incorrectly points to the older version. Pre-releases also overwrite :latest, which defeats the purpose of pre-releases.

create-release has prerelease: false hardcoded. Tags like v1.0.0-beta.1 or v2.0.0-rc.1 should be marked as pre-releases but will be published as full releases. Should detect the hyphen in the version string.

deploy-production's verification is fragile: sleep 30 followed by a single health check. I considered whether 30 seconds is enough -- it might be too much or too little depending on the deployment. And the health check only verifies HTTP 200, not which version is running. The old version could still be serving and pass the check.

The curl deployment commands have no response code checking (no -f flag), no timeout, and no retry logic. A 500 error from the webhook is silently ignored.

create-release and deploy-staging run in parallel since both need validate-tag and build-and-push. This means the GitHub release is published before staging is verified. validate-tag itself only strips the "v" prefix with no semver validation -- "vFOO" would be accepted.
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
