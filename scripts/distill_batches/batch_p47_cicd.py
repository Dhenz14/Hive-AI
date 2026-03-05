"""CI/CD — GitHub Actions, deployment strategies, and pipeline patterns."""

PAIRS = [
    (
        "devops/github-actions",
        "Show GitHub Actions patterns: reusable workflows, matrix builds, caching, and deployment pipelines.",
        '''GitHub Actions CI/CD patterns:

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read
  pull-requests: write

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements*.txt') }}

      - run: pip install ruff mypy
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy src/ --ignore-missing-imports

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
      fail-fast: false

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7
        ports: ["6379:6379"]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Cache dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ matrix.python-version }}-${{ hashFiles('requirements*.txt') }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt -r requirements-test.txt

      - name: Run tests
        run: pytest --cov=src --cov-report=xml -n auto
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379

      - name: Upload coverage
        if: matrix.python-version == '3.12'
        uses: codecov/codecov-action@v4
        with:
          files: coverage.xml

  build:
    needs: [lint, test]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read

    outputs:
      image_tag: ${{ steps.meta.outputs.tags }}

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-arn: arn:aws:iam::123456789:role/github-actions
          aws-region: us-east-1

      - name: Login to ECR
        id: ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Docker meta
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ steps.ecr.outputs.registry }}/myapp
          tags: |
            type=sha,prefix=
            type=raw,value=latest

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy-staging:
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Deploy to ECS
        uses: aws-actions/amazon-ecs-deploy-task-definition@v1
        with:
          task-definition: task-def-staging.json
          service: myapp-staging
          cluster: staging
          wait-for-service-stability: true

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://myapp.example.com
    steps:
      - name: Deploy to ECS
        uses: aws-actions/amazon-ecs-deploy-task-definition@v1
        with:
          task-definition: task-def-prod.json
          service: myapp-prod
          cluster: production
          wait-for-service-stability: true


# --- Reusable workflow ---
# .github/workflows/deploy.yml
name: Deploy

on:
  workflow_call:
    inputs:
      environment:
        required: true
        type: string
      image_tag:
        required: true
        type: string
    secrets:
      AWS_ROLE_ARN:
        required: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
      - run: |
          aws ecs update-service \
            --cluster ${{ inputs.environment }} \
            --service myapp \
            --force-new-deployment
```

GitHub Actions patterns:
1. **Concurrency** — cancel in-progress runs for same branch
2. **Matrix strategy** — test across Python versions in parallel
3. **Service containers** — Postgres/Redis for integration tests
4. **OIDC authentication** — no long-lived AWS credentials
5. **Reusable workflows** — `workflow_call` for DRY deployment logic'''
    ),
    (
        "devops/deployment-strategies",
        "Show deployment strategies: blue-green, canary, rolling updates, and feature flags.",
        '''Deployment strategy patterns:

```python
# --- Blue-Green deployment controller ---

import boto3
from typing import Literal

class BlueGreenDeployer:
    """Blue-green deployment via ALB target group switching."""

    def __init__(self, region: str = "us-east-1"):
        self.elbv2 = boto3.client("elbv2", region_name=region)
        self.ecs = boto3.client("ecs", region_name=region)

    def deploy(self, listener_arn: str, blue_tg: str, green_tg: str,
               cluster: str, service: str, new_image: str):
        """
        1. Update inactive target group with new version
        2. Wait for health checks
        3. Switch traffic
        """
        # Determine which is active
        rules = self.elbv2.describe_rules(ListenerArn=listener_arn)
        active_tg = rules["Rules"][0]["Actions"][0]["TargetGroupArn"]

        inactive_tg = green_tg if active_tg == blue_tg else blue_tg

        # Deploy to inactive
        self._update_service(cluster, service, new_image, inactive_tg)
        self._wait_healthy(inactive_tg)

        # Switch traffic atomically
        self.elbv2.modify_rule(
            RuleArn=rules["Rules"][0]["RuleArn"],
            Actions=[{
                "Type": "forward",
                "TargetGroupArn": inactive_tg,
            }],
        )

        return {"previous": active_tg, "current": inactive_tg}

    def rollback(self, listener_arn: str, previous_tg: str):
        """Instant rollback by switching back."""
        rules = self.elbv2.describe_rules(ListenerArn=listener_arn)
        self.elbv2.modify_rule(
            RuleArn=rules["Rules"][0]["RuleArn"],
            Actions=[{"Type": "forward", "TargetGroupArn": previous_tg}],
        )


# --- Canary deployment with gradual rollout ---

class CanaryDeployer:
    """Gradually shift traffic from old to new version."""

    STAGES = [
        {"canary_percent": 5, "duration_minutes": 5},
        {"canary_percent": 25, "duration_minutes": 10},
        {"canary_percent": 50, "duration_minutes": 10},
        {"canary_percent": 100, "duration_minutes": 0},
    ]

    def __init__(self):
        self.elbv2 = boto3.client("elbv2")
        self.cloudwatch = boto3.client("cloudwatch")

    def deploy(self, listener_arn: str, stable_tg: str, canary_tg: str):
        for stage in self.STAGES:
            pct = stage["canary_percent"]

            # Shift traffic
            self._set_weights(listener_arn, stable_tg, canary_tg, pct)
            print(f"Canary at {pct}%")

            if stage["duration_minutes"] > 0:
                # Monitor error rate during bake time
                healthy = self._monitor(
                    canary_tg,
                    duration_minutes=stage["duration_minutes"],
                    error_threshold=1.0,
                )
                if not healthy:
                    print("Canary unhealthy — rolling back")
                    self._set_weights(listener_arn, stable_tg, canary_tg, 0)
                    return False

        print("Canary promotion complete")
        return True

    def _set_weights(self, listener_arn, stable_tg, canary_tg, canary_pct):
        self.elbv2.modify_rule(
            RuleArn=self._get_rule_arn(listener_arn),
            Actions=[{
                "Type": "forward",
                "ForwardConfig": {
                    "TargetGroups": [
                        {"TargetGroupArn": stable_tg, "Weight": 100 - canary_pct},
                        {"TargetGroupArn": canary_tg, "Weight": canary_pct},
                    ],
                },
            }],
        )

    def _monitor(self, target_group, duration_minutes, error_threshold) -> bool:
        """Check error rate stays below threshold during bake period."""
        import time
        end_time = time.time() + duration_minutes * 60
        while time.time() < end_time:
            error_rate = self._get_error_rate(target_group)
            if error_rate > error_threshold:
                return False
            time.sleep(30)
        return True


# --- Feature flag deployment ---

class FeatureFlags:
    """Runtime feature flags for gradual rollout."""

    def __init__(self, redis_client):
        self.redis = redis_client

    def is_enabled(self, flag: str, user_id: str = None) -> bool:
        config = self.redis.hgetall(f"flag:{flag}")
        if not config:
            return False

        strategy = config.get(b"strategy", b"boolean").decode()

        if strategy == "boolean":
            return config.get(b"enabled") == b"true"

        elif strategy == "percentage":
            pct = int(config.get(b"percentage", b"0"))
            if user_id:
                # Consistent hashing: same user always gets same result
                import hashlib
                hash_val = int(hashlib.md5(
                    f"{flag}:{user_id}".encode()
                ).hexdigest(), 16)
                return (hash_val % 100) < pct
            return False

        elif strategy == "allowlist":
            allowed = config.get(b"users", b"").decode().split(",")
            return user_id in allowed

        return False

    def set_flag(self, flag: str, strategy: str, **kwargs):
        data = {"strategy": strategy, **{k: str(v) for k, v in kwargs.items()}}
        self.redis.hset(f"flag:{flag}", mapping=data)


# Usage:
# flags.set_flag("new_checkout", "percentage", percentage=10)
# if flags.is_enabled("new_checkout", user_id=current_user.id):
#     return render_new_checkout()
# else:
#     return render_old_checkout()
```

Deployment strategies:
1. **Blue-green** — instant switch, instant rollback (needs 2x resources)
2. **Canary** — gradual traffic shift with health monitoring (safest)
3. **Rolling** — replace instances one by one (default for k8s/ECS)
4. **Feature flags** — deploy code first, enable feature later (decouples deploy from release)
5. **Always have rollback** — never deploy without a tested rollback path'''
    ),
]
"""
