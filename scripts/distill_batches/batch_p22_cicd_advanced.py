"""Advanced CI/CD patterns — GitHub Actions, pipeline design, artifact management, deployment automation."""

PAIRS = [
    (
        "devops/github-actions-advanced",
        "Show advanced GitHub Actions patterns: reusable workflows, matrix strategies, caching, conditional jobs, and secrets management.",
        '''Advanced GitHub Actions patterns for production CI/CD:

```yaml
# .github/workflows/ci.yml
name: CI Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true  # Cancel stale PR runs

permissions:
  contents: read
  packages: write
  id-token: write  # For OIDC

jobs:
  changes:
    runs-on: ubuntu-latest
    outputs:
      backend: ${{ steps.filter.outputs.backend }}
      frontend: ${{ steps.filter.outputs.frontend }}
      infra: ${{ steps.filter.outputs.infra }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            backend:
              - 'src/api/**'
              - 'requirements*.txt'
            frontend:
              - 'src/web/**'
              - 'package*.json'
            infra:
              - 'terraform/**'
              - 'Dockerfile*'

  test-backend:
    needs: changes
    if: needs.changes.outputs.backend == 'true'
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
        database: [postgres, sqlite]
        exclude:
          - python-version: "3.11"
            database: sqlite  # Only test sqlite on latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: testpass
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports: ["5432:5432"]
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ matrix.python-version }}-${{ hashFiles('requirements*.txt') }}
          restore-keys: pip-${{ matrix.python-version }}-

      - name: Install dependencies
        run: |
          pip install -r requirements.txt -r requirements-dev.txt

      - name: Run tests
        env:
          DATABASE_URL: ${{ matrix.database == 'postgres'
            && 'postgresql://postgres:testpass@localhost:5432/test'
            || 'sqlite:///test.db' }}
        run: |
          pytest tests/ -v --cov=src --cov-report=xml \\
            --junitxml=results-${{ matrix.python-version }}.xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
          flags: backend-py${{ matrix.python-version }}

  test-frontend:
    needs: changes
    if: needs.changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: src/web/package-lock.json
      - run: cd src/web && npm ci
      - run: cd src/web && npm run lint
      - run: cd src/web && npm run test -- --coverage
      - run: cd src/web && npm run build

  deploy:
    needs: [test-backend, test-frontend]
    if: |
      always() &&
      github.ref == 'refs/heads/main' &&
      !contains(needs.*.result, 'failure')
    uses: ./.github/workflows/deploy-reusable.yml
    with:
      environment: production
      image-tag: ${{ github.sha }}
    secrets: inherit

# .github/workflows/deploy-reusable.yml
name: Reusable Deploy

on:
  workflow_call:
    inputs:
      environment:
        required: true
        type: string
      image-tag:
        required: true
        type: string
    secrets:
      AWS_ROLE_ARN:
        required: false  # Inherited

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      - name: Login to ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.ECR_REGISTRY }}/app:${{ inputs.image-tag }}
            ${{ env.ECR_REGISTRY }}/app:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Deploy to ECS
        run: |
          aws ecs update-service \\
            --cluster prod \\
            --service app \\
            --force-new-deployment
```

Key patterns:
- **Path filtering** — only run jobs for changed code
- **Matrix + exclude** — test combinations without waste
- **Concurrency groups** — cancel stale runs
- **Reusable workflows** — DRY deployment logic
- **OIDC auth** — no long-lived AWS keys
- **Docker layer caching** — `type=gha` uses Actions cache'''
    ),
    (
        "devops/pipeline-design-patterns",
        "Explain CI/CD pipeline design patterns: trunk-based development, environment promotion, rollback strategies, and feature flags integration.",
        '''Pipeline architecture patterns for safe, fast deployments:

```python
# Pipeline orchestrator pattern
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import subprocess
import sys

class Stage(Enum):
    BUILD = "build"
    TEST = "test"
    SECURITY_SCAN = "security_scan"
    STAGING = "staging"
    CANARY = "canary"
    PRODUCTION = "production"

@dataclass
class PipelineConfig:
    """Environment promotion pipeline configuration."""
    stages: list[Stage]
    require_approval: set[Stage] = field(default_factory=lambda: {Stage.PRODUCTION})
    rollback_on_failure: set[Stage] = field(default_factory=lambda: {
        Stage.CANARY, Stage.PRODUCTION
    })
    health_check_timeout: int = 300  # seconds
    canary_percentage: int = 5
    canary_duration: int = 600  # seconds

class DeploymentPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.current_stage: Optional[Stage] = None
        self.previous_version: Optional[str] = None

    def run(self, version: str, commit_sha: str):
        for stage in self.config.stages:
            self.current_stage = stage
            print(f"[Pipeline] Starting {stage.value}...")

            try:
                if stage in self.config.require_approval:
                    if not self._get_approval(stage, version):
                        print(f"[Pipeline] Deployment to {stage.value} cancelled")
                        return False

                success = self._execute_stage(stage, version, commit_sha)

                if not success:
                    if stage in self.config.rollback_on_failure:
                        self._rollback(stage)
                    return False

            except Exception as e:
                print(f"[Pipeline] {stage.value} failed: {e}")
                if stage in self.config.rollback_on_failure:
                    self._rollback(stage)
                return False

        return True

    def _execute_stage(self, stage: Stage, version: str, sha: str) -> bool:
        handlers = {
            Stage.BUILD: self._build,
            Stage.TEST: self._test,
            Stage.SECURITY_SCAN: self._security_scan,
            Stage.STAGING: self._deploy_staging,
            Stage.CANARY: self._deploy_canary,
            Stage.PRODUCTION: self._deploy_production,
        }
        return handlers[stage](version, sha)

    def _deploy_canary(self, version: str, sha: str) -> bool:
        """Progressive canary deployment."""
        self.previous_version = self._get_current_version()

        # Deploy to canary percentage
        self._update_deployment(version, weight=self.config.canary_percentage)

        # Monitor for anomalies
        import time
        check_interval = 60
        elapsed = 0
        while elapsed < self.config.canary_duration:
            metrics = self._get_canary_metrics()
            if metrics["error_rate"] > 0.01:
                print(f"Canary error rate {metrics['error_rate']:.2%} > 1%")
                return False
            if metrics["p99_latency"] > metrics["baseline_p99"] * 1.5:
                print(f"Canary latency regression detected")
                return False
            time.sleep(check_interval)
            elapsed += check_interval

        return True

    def _rollback(self, stage: Stage):
        if self.previous_version:
            print(f"[Rollback] Reverting {stage.value} to {self.previous_version}")
            self._update_deployment(self.previous_version, weight=100)

# --- Feature flag integration ---

class FeatureFlagDeployment:
    """Deploy behind feature flags for safe rollouts."""

    def __init__(self, flag_client):
        self.flags = flag_client

    def progressive_rollout(self, feature: str, stages: list[dict]):
        """
        stages = [
            {"percentage": 1, "duration": 3600, "metric_threshold": 0.01},
            {"percentage": 10, "duration": 3600, "metric_threshold": 0.01},
            {"percentage": 50, "duration": 1800, "metric_threshold": 0.02},
            {"percentage": 100, "duration": 0, "metric_threshold": 0.05},
        ]
        """
        for stage in stages:
            pct = stage["percentage"]
            print(f"Rolling out {feature} to {pct}%")
            self.flags.update_rule(feature, percentage=pct)

            if stage["duration"] > 0:
                success = self._monitor(
                    feature, stage["duration"], stage["metric_threshold"]
                )
                if not success:
                    print(f"Rollout failed at {pct}%, rolling back")
                    self.flags.update_rule(feature, percentage=0)
                    return False

        print(f"Feature {feature} fully rolled out")
        return True

    def _monitor(self, feature: str, duration: int, threshold: float) -> bool:
        import time
        start = time.time()
        while time.time() - start < duration:
            error_rate = self._get_feature_error_rate(feature)
            if error_rate > threshold:
                return False
            time.sleep(30)
        return True

# --- Trunk-based development pipeline ---

# Branch strategy:
# main (trunk) → always deployable
#   ├── feature/short-lived (max 2 days)
#   └── release/v1.2 (cut from main, cherry-pick fixes)
#
# Pipeline flow:
# PR → lint + unit tests + security scan (fast, <5min)
# Merge to main → full test suite + build + deploy staging
# Staging health check passes → canary → production
# Rollback if canary metrics degrade
```

Key principles:
1. **Fail fast** — lint and unit tests run first (<5 min)
2. **Environment promotion** — staging → canary → production
3. **Automatic rollback** — metrics-driven, not manual
4. **Feature flags** — decouple deployment from release
5. **Short-lived branches** — merge to trunk within 1-2 days'''
    ),
    (
        "devops/artifact-management",
        "Explain artifact management patterns: container registries, package versioning, reproducible builds, and supply chain security with SLSA.",
        '''Artifact management ensures reproducible, secure, and traceable builds:

```python
# Build metadata and provenance tracking
import hashlib
import json
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

@dataclass
class BuildProvenance:
    """SLSA-inspired build provenance metadata."""
    builder_id: str
    build_type: str
    source_repo: str
    source_ref: str
    source_digest: str  # Git commit SHA
    build_timestamp: str
    artifact_digest: str  # SHA256 of artifact
    dependencies: list[dict]  # Pinned dependency versions
    build_config: dict  # Reproducibility parameters

    def to_slsa_statement(self) -> dict:
        return {
            "_type": "https://in-toto.io/Statement/v0.1",
            "predicateType": "https://slsa.dev/provenance/v1",
            "subject": [{"digest": {"sha256": self.artifact_digest}}],
            "predicate": {
                "buildDefinition": {
                    "buildType": self.build_type,
                    "externalParameters": {
                        "source": {
                            "uri": self.source_repo,
                            "digest": {"gitCommit": self.source_digest},
                        },
                    },
                },
                "runDetails": {
                    "builder": {"id": self.builder_id},
                    "metadata": {
                        "buildStartedOn": self.build_timestamp,
                    },
                },
            },
        }

def create_build_provenance(artifact_path: str) -> BuildProvenance:
    """Generate provenance for a build artifact."""

    # Get source info
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    repo = subprocess.check_output(
        ["git", "remote", "get-url", "origin"], text=True
    ).strip()

    # Hash the artifact
    sha256 = hashlib.sha256()
    with open(artifact_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)

    # Capture pinned dependencies
    deps = subprocess.check_output(
        ["pip", "freeze"], text=True
    ).strip().split("\\n")
    dep_list = []
    for dep in deps:
        if "==" in dep:
            name, ver = dep.split("==", 1)
            dep_list.append({"name": name, "version": ver})

    return BuildProvenance(
        builder_id="github-actions/v1",
        build_type="python-package",
        source_repo=repo,
        source_ref="refs/heads/main",
        source_digest=commit,
        build_timestamp=datetime.now(timezone.utc).isoformat(),
        artifact_digest=sha256.hexdigest(),
        dependencies=dep_list,
        build_config={
            "python_version": "3.12",
            "build_tool": "hatchling",
            "reproducible": True,
        },
    )

# --- Semantic versioning automation ---

class VersionManager:
    """Automated versioning from conventional commits."""

    def __init__(self, current: str):
        parts = current.split(".")
        self.major = int(parts[0])
        self.minor = int(parts[1])
        self.patch = int(parts[2])

    def bump_from_commits(self, commits: list[str]) -> str:
        """Determine version bump from conventional commit messages."""
        has_breaking = any(
            "BREAKING CHANGE" in c or "!:" in c for c in commits
        )
        has_feat = any(c.startswith("feat") for c in commits)
        has_fix = any(c.startswith("fix") for c in commits)

        if has_breaking:
            self.major += 1
            self.minor = 0
            self.patch = 0
        elif has_feat:
            self.minor += 1
            self.patch = 0
        elif has_fix:
            self.patch += 1

        return f"{self.major}.{self.minor}.{self.patch}"

# --- Container image best practices ---
# Dockerfile with reproducibility and security

DOCKERFILE = """
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
# Pin base image by digest for reproducibility
# FROM python:3.12-slim@sha256:abc123...

# Security: non-root user
RUN groupadd -r app && useradd -r -g app -d /app app
WORKDIR /app

# Dependencies (cached layer)
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \\
    pip install --no-deps -r requirements.txt

# Application code
COPY --chown=app:app src/ ./src/

# Security: drop all capabilities, read-only FS
USER app
ENV PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=3s \\
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

ENTRYPOINT ["python", "-m", "src.main"]
"""

# --- Image signing and verification ---
# Using cosign (Sigstore)
SIGNING_COMMANDS = """
# Sign image after push
cosign sign --yes $ECR_REGISTRY/app:$TAG

# Verify before deploy
cosign verify $ECR_REGISTRY/app:$TAG \\
    --certificate-identity=builder@ci.example.com \\
    --certificate-oidc-issuer=https://token.actions.githubusercontent.com

# Attach SBOM
syft $ECR_REGISTRY/app:$TAG -o spdx-json > sbom.json
cosign attach sbom --sbom sbom.json $ECR_REGISTRY/app:$TAG

# Attach provenance
cosign attest --predicate provenance.json --type slsaprovenance $ECR_REGISTRY/app:$TAG
"""
```

SLSA levels:
- **L1**: Documentation of build process
- **L2**: Hosted build service (GitHub Actions)
- **L3**: Hardened build platform, provenance verification
- **L4**: Two-party review, hermetic builds'''
    ),
    (
        "devops/database-migrations-cicd",
        "Show how to safely integrate database migrations into CI/CD pipelines with zero-downtime deployment strategies.",
        '''Safe database migrations in automated pipelines:

```python
# migration_runner.py — CI/CD-aware migration orchestrator
import subprocess
import time
import sys
from dataclasses import dataclass
from enum import Enum

class MigrationStrategy(Enum):
    EXPAND_CONTRACT = "expand_contract"
    BLUE_GREEN = "blue_green"
    SHADOW = "shadow"

@dataclass
class MigrationPlan:
    forward_sql: str
    backward_sql: str
    strategy: MigrationStrategy
    requires_backfill: bool = False
    estimated_rows: int = 0
    safe_for_online: bool = True

# --- Expand-and-contract pattern ---

RENAME_COLUMN_MIGRATIONS = {
    "step1_expand": """
        -- Phase 1: Add new column (deploy with old + new code)
        ALTER TABLE users ADD COLUMN full_name VARCHAR(255);

        -- Backfill in batches (non-blocking)
        -- DO NOT: UPDATE users SET full_name = name; (locks table)
    """,

    "step1_backfill": """
        -- Batch backfill script (run as background job)
        DO $$
        DECLARE
            batch_size INT := 1000;
            last_id BIGINT := 0;
            rows_updated INT;
        BEGIN
            LOOP
                UPDATE users
                SET full_name = name
                WHERE id > last_id
                  AND id <= last_id + batch_size
                  AND full_name IS NULL;

                GET DIAGNOSTICS rows_updated = ROW_COUNT;
                EXIT WHEN rows_updated = 0;

                last_id := last_id + batch_size;
                PERFORM pg_sleep(0.1);  -- Rate limit
                RAISE NOTICE 'Updated through id %', last_id;
            END LOOP;
        END $$;
    """,

    "step2_sync": """
        -- Phase 2: Trigger to keep columns in sync during transition
        CREATE OR REPLACE FUNCTION sync_user_name()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'INSERT' OR NEW.name IS DISTINCT FROM OLD.name THEN
                NEW.full_name := NEW.name;
            END IF;
            IF NEW.full_name IS DISTINCT FROM OLD.full_name THEN
                NEW.name := NEW.full_name;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER user_name_sync
            BEFORE INSERT OR UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION sync_user_name();
    """,

    "step3_contract": """
        -- Phase 3: After all code uses full_name (separate deploy)
        DROP TRIGGER user_name_sync ON users;
        DROP FUNCTION sync_user_name();
        ALTER TABLE users DROP COLUMN name;
    """,
}

# --- Safe migration checker ---

class MigrationSafetyChecker:
    """Validates migrations won't cause downtime."""

    DANGEROUS_PATTERNS = [
        ("ALTER TABLE .+ ADD COLUMN .+ NOT NULL(?! DEFAULT)",
         "Adding NOT NULL column without DEFAULT locks table"),
        ("ALTER TABLE .+ ALTER COLUMN .+ TYPE",
         "Changing column type requires ACCESS EXCLUSIVE lock"),
        ("CREATE INDEX (?!CONCURRENTLY)",
         "CREATE INDEX without CONCURRENTLY locks writes"),
        ("ALTER TABLE .+ RENAME COLUMN",
         "Renaming column breaks running application code"),
        ("DROP COLUMN",
         "Dropping column breaks running application code"),
        ("LOCK TABLE",
         "Explicit table lock detected"),
    ]

    def check(self, sql: str) -> list[str]:
        import re
        warnings = []
        for pattern, message in self.DANGEROUS_PATTERNS:
            if re.search(pattern, sql, re.IGNORECASE):
                warnings.append(f"WARNING: {message}")
        return warnings

# --- CI/CD pipeline integration ---

def run_migration_pipeline(env: str, dry_run: bool = True):
    """Run migrations as part of deployment pipeline."""
    checker = MigrationSafetyChecker()

    # 1. Get pending migrations
    pending = get_pending_migrations(env)
    if not pending:
        print("No pending migrations")
        return True

    # 2. Safety check all migrations
    for migration in pending:
        warnings = checker.check(migration.forward_sql)
        if warnings:
            print(f"Migration {migration} has safety warnings:")
            for w in warnings:
                print(f"  {w}")
            if env == "production":
                print("BLOCKED: Fix warnings before production deploy")
                return False

    # 3. Take pre-migration snapshot
    if env == "production" and not dry_run:
        snapshot_id = create_db_snapshot(env)
        print(f"Created snapshot: {snapshot_id}")

    # 4. Run migrations
    if dry_run:
        print("DRY RUN — would execute:")
        for m in pending:
            print(f"  {m}")
        return True

    for migration in pending:
        print(f"Applying: {migration}")
        try:
            apply_migration(migration, env)
        except Exception as e:
            print(f"Migration failed: {e}")
            if env == "production":
                print("Attempting rollback...")
                rollback_migration(migration, env)
            return False

    # 5. Verify schema
    if not verify_schema(env):
        print("Schema verification failed!")
        return False

    print(f"All {len(pending)} migrations applied successfully")
    return True

# --- Alembic integration example ---

ALEMBIC_CI_COMMANDS = """
# In CI pipeline:

# 1. Check for pending migrations
alembic check || echo "Pending migrations detected"

# 2. Dry-run migration
alembic upgrade head --sql > migration.sql
# Review migration.sql for safety

# 3. Run migration safety checker
python -c "
from migration_runner import MigrationSafetyChecker
checker = MigrationSafetyChecker()
sql = open('migration.sql').read()
warnings = checker.check(sql)
if warnings:
    for w in warnings: print(w)
    exit(1)
"

# 4. Apply migrations (with timeout)
timeout 300 alembic upgrade head

# 5. Verify
alembic current
python -c "from app.models import *; print('Schema OK')"
"""
```

Pipeline order for zero-downtime:
1. **Run expand migration** (add columns, create indexes concurrently)
2. **Deploy new app code** (reads both old + new columns)
3. **Run backfill** (populate new columns from old data)
4. **Deploy code using only new columns**
5. **Run contract migration** (drop old columns, triggers)

Each step is a separate deployment — never combine schema + code changes.'''
    ),
]
