"""
Real-world project help training pairs - CI/CD setup for real projects
"""

pairs = [
    {
        "instruction": r'''I have a Python FastAPI project on GitHub. I want to set up CI that runs tests and linting on every PR, and CD that deploys to a staging server on merge to main. We deploy to a $20 VPS running Docker. What's the simplest GitHub Actions setup?''',
        "output": r'''<think>
Simple CI/CD for a small team. GitHub Actions for CI, SSH deploy for CD. No Kubernetes, no Terraform -- just Docker on a VPS.
</think>

Here's a complete setup with two workflows:

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: testpass
          POSTGRES_DB: testdb
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt -r requirements-dev.txt

      - name: Lint
        run: |
          ruff check .
          ruff format --check .

      - name: Type check
        run: mypy app/ --ignore-missing-imports

      - name: Test
        env:
          DATABASE_URL: postgresql://postgres:testpass@localhost:5432/testdb
        run: pytest --tb=short -q
```

```yaml
# .github/workflows/deploy.yml
name: Deploy to Staging

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.STAGING_HOST }}
          username: deploy
          key: ${{ secrets.STAGING_SSH_KEY }}
          script: |
            cd /opt/myapp
            git pull origin main
            docker compose build --no-cache app
            docker compose up -d app
            docker compose exec -T app alembic upgrade head
            echo "Deployed at $(date)"
```

Set up the secrets in GitHub repo settings:
- `STAGING_HOST` -- your VPS IP
- `STAGING_SSH_KEY` -- SSH private key for the deploy user

On your VPS, set up the deploy user:

```bash
# On the VPS
useradd -m deploy
mkdir -p /home/deploy/.ssh
# Add the public key to authorized_keys
echo "ssh-ed25519 AAAA... deploy-key" >> /home/deploy/.ssh/authorized_keys
usermod -aG docker deploy
```

Your docker-compose.yml on the server:

```yaml
services:
  app:
    build: .
    env_file: .env
    ports:
      - "8000:8000"
    restart: unless-stopped
  db:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
    env_file: .env
    restart: unless-stopped
volumes:
  pgdata:
```

This gives you: PR checks (lint + type check + tests) and auto-deploy on merge to main. Total setup time: about 1 hour.'''
    },
    {
        "instruction": r'''We have a monorepo with a Python backend, React frontend, and shared protobuf definitions. Changes to one part shouldn't trigger CI for the other parts. How do I set up GitHub Actions to only run relevant checks?''',
        "output": r'''Use path filters in your workflow triggers. GitHub Actions supports this natively.

```yaml
# .github/workflows/backend.yml
name: Backend CI

on:
  pull_request:
    paths:
      - "backend/**"
      - "proto/**"          # backend depends on protobufs
      - "requirements*.txt"
      - ".github/workflows/backend.yml"

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: backend/requirements*.txt

      - name: Generate protobuf code
        run: |
          pip install grpcio-tools
          python -m grpc_tools.protoc -I../proto --python_out=./app/proto --grpc_python_out=./app/proto ../proto/*.proto

      - name: Install and test
        run: |
          pip install -r requirements.txt -r requirements-dev.txt
          pytest --tb=short
```

```yaml
# .github/workflows/frontend.yml
name: Frontend CI

on:
  pull_request:
    paths:
      - "frontend/**"
      - "proto/**"           # frontend also depends on protobufs
      - ".github/workflows/frontend.yml"

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm test -- --watchAll=false
```

```yaml
# .github/workflows/proto.yml
name: Protobuf Validation

on:
  pull_request:
    paths:
      - "proto/**"

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate protobuf files
        run: |
          pip install grpcio-tools
          python -m grpc_tools.protoc -I proto --python_out=/tmp proto/*.proto
          echo "Protobuf compilation successful"
```

For the deploy workflow, detect what changed and deploy only affected services:

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      backend: ${{ steps.filter.outputs.backend }}
      frontend: ${{ steps.filter.outputs.frontend }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            backend:
              - 'backend/**'
              - 'proto/**'
            frontend:
              - 'frontend/**'

  deploy-backend:
    needs: detect-changes
    if: needs.detect-changes.outputs.backend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy backend
        run: echo "Deploy backend here"

  deploy-frontend:
    needs: detect-changes
    if: needs.detect-changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy frontend
        run: echo "Deploy frontend here"
```

This way, a backend-only PR only runs backend tests (saving CI minutes), and a deploy only rebuilds the changed service.'''
    },
    {
        "instruction": r'''I want to set up a proper deployment pipeline with staging and production environments. Currently we just push to main and pray. We use AWS (ECS Fargate) and have a Django app. What's a good branching and deploy strategy?''',
        "output": r'''<think>
They need a staging/production pipeline with ECS Fargate. The simplest reliable approach: main branch = staging, release tags = production. No develop branch, no release branches -- keep it simple.
</think>

Use this model: main branch auto-deploys to staging, git tags deploy to production.

Branch strategy:

```
feature/xyz  -->  PR to main  -->  merge to main  -->  auto-deploy to staging
                                                            |
                                                   manual QA on staging
                                                            |
                                                   git tag v1.2.3  -->  deploy to production
```

GitHub Actions workflow:

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]
    tags: ["v*"]

env:
  AWS_REGION: us-east-1
  ECR_REPO: 123456789.dkr.ecr.us-east-1.amazonaws.com/myapp

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      image_tag: ${{ steps.meta.outputs.tag }}

    steps:
      - uses: actions/checkout@v4

      - name: Determine environment
        id: meta
        run: |
          if [[ "$GITHUB_REF" == refs/tags/v* ]]; then
            echo "env=production" >> $GITHUB_OUTPUT
            echo "tag=${GITHUB_REF#refs/tags/}" >> $GITHUB_OUTPUT
          else
            echo "env=staging" >> $GITHUB_OUTPUT
            echo "tag=staging-${GITHUB_SHA::8}" >> $GITHUB_OUTPUT
          fi

      - name: Configure AWS
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push
        run: |
          docker build -t $ECR_REPO:${{ steps.meta.outputs.tag }} .
          docker push $ECR_REPO:${{ steps.meta.outputs.tag }}

  deploy-staging:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Deploy to ECS staging
        run: |
          aws ecs update-service \
            --cluster staging \
            --service myapp \
            --force-new-deployment \
            --task-definition myapp-staging

  deploy-production:
    needs: build
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    environment: production  # requires manual approval in GitHub settings
    steps:
      - name: Deploy to ECS production
        run: |
          aws ecs update-service \
            --cluster production \
            --service myapp \
            --force-new-deployment \
            --task-definition myapp-production

      - name: Run migrations
        run: |
          aws ecs run-task \
            --cluster production \
            --task-definition myapp-migrate \
            --launch-type FARGATE
```

Set up the `production` environment in GitHub Settings -> Environments with required reviewers. This adds a manual approval step before production deploys.

Release process:

```bash
# After QA passes on staging:
git tag -a v1.2.3 -m "Release: add billing feature, fix order bug"
git push origin v1.2.3
# GitHub Actions deploys to production (after approval)
```

Add a rollback script for emergencies:

```bash
#!/bin/bash
# rollback.sh -- deploy the previous image
PREV_TAG=$1
aws ecs update-service \
    --cluster production \
    --service myapp \
    --force-new-deployment \
    --task-definition "myapp-production:${PREV_TAG}"
```

This gives you automated staging deploys, controlled production releases, and easy rollbacks.'''
    },
    {
        "instruction": r'''Our CI pipeline takes 25 minutes to run. Most of that is running the full test suite (18 minutes). We have 1200 tests. Can I speed this up without just throwing money at bigger runners?''',
        "output": r'''Yes. There are several strategies, ordered by effort vs impact:

1. Parallelize tests across multiple jobs (biggest win, moderate effort):

```yaml
jobs:
  test:
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -r requirements.txt

      - name: Run test shard
        run: |
          pytest --splits 4 --group ${{ matrix.shard }} \
            --splitting-algorithm least_duration
```

Install `pytest-split`: it divides tests into equal-duration groups based on previous timing data. 4 shards = ~4.5 min instead of 18.

Generate the timing file:

```bash
pytest --store-durations
# Creates .test_durations file, commit it to the repo
```

2. Cache aggressively (easy, saves 2-3 minutes):

```yaml
      - uses: actions/setup-python@v5
        with:
          cache: pip

      # Cache the database setup if you use fixtures
      - uses: actions/cache@v4
        with:
          path: .pytest_cache
          key: pytest-${{ hashFiles('tests/**') }}
```

3. Run only affected tests on PRs (moderate effort, big win for small changes):

```yaml
      - name: Find changed files
        id: changes
        run: |
          FILES=$(git diff --name-only origin/main...HEAD | grep '\.py$' | tr '\n' ' ')
          echo "files=$FILES" >> $GITHUB_OUTPUT

      - name: Run affected tests
        run: |
          # Use pytest-testmon for dependency tracking
          pytest --testmon
```

`pytest-testmon` tracks which tests depend on which source files and only runs affected tests. A 1-file change might run 30 tests instead of 1200.

4. Speed up the test database (often overlooked):

```python
# conftest.py
import django
from django.conf import settings

# Use in-memory SQLite for tests if possible
if "test" in sys.argv:
    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }

# Or if you need Postgres, use unlogged tables
@pytest.fixture(scope="session")
def django_db_setup(django_db_blocker):
    settings.DATABASES["default"]["OPTIONS"] = {
        "options": "-c synchronous_commit=off"
    }
```

5. Skip slow tests on PRs, run full suite on main:

```yaml
      - name: Run tests
        run: |
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            pytest -m "not slow" --tb=short
          else
            pytest --tb=short
          fi
```

```python
# Mark slow tests
@pytest.mark.slow
def test_full_data_import():
    # This test takes 30 seconds
    ...
```

Combining sharding + caching + PR-only affected tests typically takes a 25-minute pipeline down to 4-6 minutes.'''
    },
    {
        "instruction": r'''We have a Node.js project and I want to add automated dependency security scanning to our CI. We also want to block PRs that introduce known vulnerabilities. What's the best setup?''',
        "output": r'''Use multiple layers: npm audit in CI, GitHub Dependabot for auto-updates, and a dedicated scanning tool for deeper analysis.

Layer 1: npm audit in your CI workflow (immediate):

```yaml
# .github/workflows/security.yml
name: Security Scan

on:
  pull_request:
  schedule:
    - cron: "0 8 * * 1"  # Weekly Monday scan

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20

      - run: npm ci

      - name: Check for vulnerabilities
        run: |
          # Fail on high and critical only (moderate would block too much)
          npm audit --audit-level=high
```

Layer 2: Dependabot configuration:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: npm
    directory: "/"
    schedule:
      interval: weekly
    open-pull-requests-limit: 10
    reviewers:
      - "your-team"
    labels:
      - "dependencies"
    # Group minor/patch updates to reduce PR noise
    groups:
      production-deps:
        dependency-type: production
        update-types:
          - "minor"
          - "patch"
      dev-deps:
        dependency-type: development
        update-types:
          - "minor"
          - "patch"
```

Layer 3: License and deeper scanning with a dedicated action:

```yaml
  license-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci

      - name: Check licenses
        run: |
          npx license-checker --failOn "GPL-3.0;AGPL-3.0" --summary
```

Layer 4: Block PRs with a required status check. In GitHub repo Settings -> Branches -> Branch protection rules:
- Require status checks: `audit` must pass
- This prevents merging PRs that introduce high/critical vulnerabilities

Handling false positives -- sometimes npm audit flags things in devDependencies that aren't actually exploitable:

```json
// .npmrc
audit-level=high

// package.json -- document accepted risks
// "auditExceptions": documented in a separate file
```

```bash
# Create an allowlist for known false positives
# .audit-allowlist
# CVE-2024-XXXXX - devDependency only, not exploitable in our context
# Reviewed by: @developer on 2024-03-01
```

```yaml
      - name: Audit with allowlist
        run: |
          npm audit --json > audit.json || true
          # Filter out allowed advisories
          node scripts/filter-audit.js audit.json .audit-allowlist
```

This gives you: automated PR blocking for real vulnerabilities, auto-PR creation for updates, weekly full scans, and a process for handling false positives.'''
    },
]
