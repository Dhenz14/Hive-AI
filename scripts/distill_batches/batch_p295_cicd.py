"""CI/CD patterns — GitHub Actions, pipeline design, deployment strategies."""

PAIRS = [
    (
        "devops/github-actions",
        "Show GitHub Actions CI/CD: matrix builds, caching, reusable workflows, and deployment with environments.",
        '''GitHub Actions CI/CD pipeline:

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true  # Cancel outdated PR runs

permissions:
  contents: read
  packages: write
  deployments: write

jobs:
  lint-and-type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install ruff mypy
      - run: ruff check src/
      - run: mypy src/ --strict

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
        os: [ubuntu-latest, macos-latest]
      fail-fast: false
    services:
      postgres:
        image: postgres:16
        env:
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
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ runner.os }}-${{ matrix.python-version }}-${{ hashFiles('**/pyproject.toml') }}
      - run: pip install -e ".[test]"
      - run: pytest --cov=src --cov-report=xml -n auto
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/postgres
      - uses: codecov/codecov-action@v4
        with:
          file: coverage.xml

  build-and-push:
    needs: [lint-and-type-check, test]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    outputs:
      image-tag: ${{ steps.meta.outputs.tags }}
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=sha
            type=ref,event=branch
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy-staging:
    needs: build-and-push
    runs-on: ubuntu-latest
    environment:
      name: staging
      url: https://staging.example.com
    steps:
      - run: |
          kubectl set image deployment/api-server \
            api=ghcr.io/${{ github.repository }}:sha-${{ github.sha }}
          kubectl rollout status deployment/api-server --timeout=5m

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://api.example.com
    steps:
      - run: |
          kubectl set image deployment/api-server \
            api=ghcr.io/${{ github.repository }}:sha-${{ github.sha }}
          kubectl rollout status deployment/api-server --timeout=5m
```

Key patterns:
1. **Matrix builds** — test across Python versions and OSes; fail-fast=false for full picture
2. **Concurrency control** — cancel outdated PR runs; save CI minutes
3. **Service containers** — spin up Postgres alongside tests; realistic integration testing
4. **Build cache** — GHA cache for Docker layers; pip cache for dependencies
5. **Environment gates** — staging deploys automatically; production requires manual approval'''
    ),
    (
        "devops/deployment-strategies",
        "Show deployment strategies: blue-green, canary, rolling, and A/B deployments with traffic shifting.",
        '''Deployment strategies:

```python
from dataclasses import dataclass
from enum import Enum


class Strategy(Enum):
    ROLLING = "rolling"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"


@dataclass
class DeploymentConfig:
    strategy: Strategy
    replicas: int
    health_check_url: str
    rollback_on_error: bool = True


class BlueGreenDeploy:
    """Blue-Green: two identical environments, instant switch.

    - Blue = current production
    - Green = new version
    - Switch traffic atomically via load balancer
    - Instant rollback: switch back to blue
    """

    async def deploy(self, new_version: str):
        # 1. Deploy new version to green environment
        green = await self.provision_environment("green", new_version)

        # 2. Run smoke tests against green
        if not await self.run_smoke_tests(green.url):
            await self.teardown(green)
            raise DeployError("Smoke tests failed on green")

        # 3. Switch traffic atomically
        await self.switch_traffic(from_env="blue", to_env="green")

        # 4. Keep blue running for quick rollback
        # After confidence period, teardown blue
        await self.schedule_teardown("blue", delay_minutes=30)


class CanaryDeploy:
    """Canary: gradually shift traffic to new version.

    5% → 25% → 50% → 100% with metrics checks between stages.
    Automatic rollback if error rate increases.
    """

    def __init__(self):
        self.stages = [5, 25, 50, 100]  # Traffic percentages
        self.stage_duration_minutes = 10
        self.error_threshold = 0.01  # 1% error rate

    async def deploy(self, new_version: str):
        # Deploy canary pods (small fraction)
        await self.create_canary(new_version, replicas=1)

        for pct in self.stages:
            # Shift traffic
            await self.set_traffic_split(canary_pct=pct)

            # Monitor for stage duration
            metrics = await self.monitor(
                duration_minutes=self.stage_duration_minutes
            )

            # Check error rate
            if metrics["error_rate"] > self.error_threshold:
                await self.rollback()
                raise DeployError(
                    f"Canary failed at {pct}%: "
                    f"error_rate={metrics['error_rate']:.3f}"
                )

            # Check latency regression
            if metrics["p99_latency_ms"] > metrics["baseline_p99"] * 1.5:
                await self.rollback()
                raise DeployError(f"Latency regression at {pct}%")

        # Full rollout successful
        await self.promote_canary()


class DeployError(Exception):
    pass
```

Key patterns:
1. **Blue-green** — instant cutover; zero downtime; instant rollback; requires 2x resources
2. **Canary** — gradual traffic shift; automatic rollback on metrics degradation
3. **Rolling** — replace pods one-by-one; no extra infrastructure needed; slower rollback
4. **Metrics gates** — error rate and latency checks between canary stages
5. **Confidence period** — keep old environment alive for quick rollback window'''
    ),
]
"""
