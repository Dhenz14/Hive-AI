"""Platform engineering and Internal Developer Platforms."""

PAIRS = [
    (
        "platform-engineering/idp-backstage-architecture",
        "Design an Internal Developer Platform (IDP) architecture using Backstage, including plugin system, catalog ingestion, and integration with CI/CD and cloud providers.",
        '''Internal Developer Platform architecture with Backstage:

```yaml
# --- Backstage app-config.yaml ---

app:
  title: Acme Developer Portal
  baseUrl: https://portal.acme.dev

organization:
  name: Acme Corp

backend:
  baseUrl: https://portal-api.acme.dev
  listen:
    port: 7007
  database:
    client: pg
    connection:
      host: ${POSTGRES_HOST}
      port: ${POSTGRES_PORT}
      user: ${POSTGRES_USER}
      password: ${POSTGRES_PASSWORD}

catalog:
  # Auto-discover from GitHub org
  providers:
    github:
      acmeOrg:
        organization: acme-corp
        catalogPath: /catalog-info.yaml
        filters:
          branch: main
          repository: ".*"
        schedule:
          frequency: { minutes: 30 }
          timeout: { minutes: 3 }

    # Import from existing CMDB
    microsoftGraphOrg:
      default:
        tenantId: ${AZURE_TENANT_ID}
        clientId: ${AZURE_CLIENT_ID}
        clientSecret: ${AZURE_CLIENT_SECRET}
        userFilter: accountEnabled eq true
        groupFilter: displayName eq 'Engineering'
        schedule:
          frequency: { hours: 1 }
          timeout: { minutes: 10 }

  # Static locations for bootstrap
  locations:
    - type: file
      target: ../../catalog-entities/all-systems.yaml
    - type: url
      target: https://github.com/acme-corp/platform/blob/main/templates/all-templates.yaml

integrations:
  github:
    - host: github.com
      token: ${GITHUB_TOKEN}

auth:
  environment: production
  providers:
    github:
      production:
        clientId: ${AUTH_GITHUB_CLIENT_ID}
        clientSecret: ${AUTH_GITHUB_CLIENT_SECRET}

kubernetes:
  serviceLocatorMethod:
    type: multiTenant
  clusterLocatorMethods:
    - type: config
      clusters:
        - url: https://k8s-prod.acme.dev
          name: production
          authProvider: serviceAccount
          serviceAccountToken: ${K8S_PROD_TOKEN}
        - url: https://k8s-staging.acme.dev
          name: staging
          authProvider: serviceAccount
          serviceAccountToken: ${K8S_STAGING_TOKEN}

techdocs:
  builder: external
  generator:
    runIn: local
  publisher:
    type: awsS3
    awsS3:
      bucketName: acme-techdocs
      region: us-east-1
```

```typescript
// --- Custom Backstage plugin: scaffolder action for infra provisioning ---

import { createTemplateAction } from '@backstage/plugin-scaffolder-node';
import { Config } from '@backstage/config';
import { Logger } from 'winston';

interface ProvisionInput {
  serviceName: string;
  team: string;
  environment: 'dev' | 'staging' | 'production';
  tier: 'critical' | 'standard' | 'batch';
  resources: {
    cpu: string;
    memory: string;
    replicas: number;
  };
  database?: {
    engine: 'postgres' | 'mysql' | 'redis';
    size: string;
  };
}

export const createProvisionInfraAction = (options: {
  config: Config;
  logger: Logger;
}) => {
  return createTemplateAction<ProvisionInput>({
    id: 'acme:infra:provision',
    description: 'Provisions cloud infrastructure via Terraform',
    schema: {
      input: {
        required: ['serviceName', 'team', 'environment', 'tier', 'resources'],
        type: 'object',
        properties: {
          serviceName: {
            type: 'string',
            pattern: '^[a-z][a-z0-9-]{2,40}$',
            description: 'Service name (lowercase, hyphens allowed)',
          },
          team: { type: 'string' },
          environment: {
            type: 'string',
            enum: ['dev', 'staging', 'production'],
          },
          tier: {
            type: 'string',
            enum: ['critical', 'standard', 'batch'],
          },
          resources: {
            type: 'object',
            properties: {
              cpu: { type: 'string' },
              memory: { type: 'string' },
              replicas: { type: 'number', minimum: 1, maximum: 50 },
            },
          },
          database: {
            type: 'object',
            properties: {
              engine: { type: 'string', enum: ['postgres', 'mysql', 'redis'] },
              size: { type: 'string' },
            },
          },
        },
      },
    },
    async handler(ctx) {
      const { serviceName, team, environment, tier, resources, database } =
        ctx.input;
      const logger = options.logger.child({ action: 'provision-infra' });

      logger.info(`Provisioning infra for ${serviceName} in ${environment}`);

      // 1. Generate Terraform workspace
      const tfWorkspace = `${serviceName}-${environment}`;
      const tfVars = {
        service_name: serviceName,
        team,
        environment,
        tier,
        cpu_request: resources.cpu,
        memory_request: resources.memory,
        replica_count: resources.replicas,
        ...(database && {
          db_engine: database.engine,
          db_instance_class: mapSizeToInstanceClass(database.size),
        }),
      };

      // 2. Trigger Terraform via Atlantis / Terraform Cloud
      const terraformCloudApi = options.config.getString(
        'acme.terraformCloud.apiUrl',
      );
      const tfToken = options.config.getString(
        'acme.terraformCloud.token',
      );

      const runResponse = await fetch(
        `${terraformCloudApi}/runs`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${tfToken}`,
            'Content-Type': 'application/vnd.api+json',
          },
          body: JSON.stringify({
            data: {
              type: 'runs',
              attributes: {
                'is-destroy': false,
                message: `Backstage: provision ${serviceName}`,
              },
              relationships: {
                workspace: {
                  data: { type: 'workspaces', id: tfWorkspace },
                },
              },
            },
          }),
        },
      );

      if (!runResponse.ok) {
        throw new Error(
          `Terraform Cloud run failed: ${runResponse.statusText}`,
        );
      }

      const runData = await runResponse.json();
      const runId = runData.data.id;

      // 3. Register outputs in catalog
      ctx.output('terraformRunId', runId);
      ctx.output('infraWorkspace', tfWorkspace);
      ctx.output('provisionedAt', new Date().toISOString());

      logger.info(`Terraform run ${runId} created for ${tfWorkspace}`);
    },
  });
};

function mapSizeToInstanceClass(size: string): string {
  const sizeMap: Record<string, string> = {
    small: 'db.t3.micro',
    medium: 'db.t3.medium',
    large: 'db.r6g.large',
    xlarge: 'db.r6g.xlarge',
  };
  return sizeMap[size] ?? 'db.t3.small';
}
```

```yaml
# --- catalog-info.yaml (per-service registration) ---

apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: payment-service
  description: Handles payment processing and settlement
  annotations:
    backstage.io/techdocs-ref: dir:.
    github.com/project-slug: acme-corp/payment-service
    backstage.io/kubernetes-id: payment-service
    pagerduty.com/service-id: P12345X
    sonarqube.org/project-key: acme_payment-service
    sentry.io/project-slug: payment-service
    argocd/app-name: payment-service-prod
  tags:
    - python
    - payments
    - pci
  links:
    - url: https://grafana.acme.dev/d/payments
      title: Grafana Dashboard
    - url: https://runbook.acme.dev/payment-service
      title: Runbook
spec:
  type: service
  lifecycle: production
  owner: team-payments
  system: payment-platform
  providesApis:
    - payment-api
  consumesApis:
    - fraud-detection-api
    - notification-api
  dependsOn:
    - resource:payment-db
    - resource:payment-cache

---
apiVersion: backstage.io/v1alpha1
kind: API
metadata:
  name: payment-api
  description: REST API for payment processing
spec:
  type: openapi
  lifecycle: production
  owner: team-payments
  system: payment-platform
  definition:
    $text: ./openapi.yaml

---
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: payment-db
  description: Payment PostgreSQL database
spec:
  type: database
  owner: team-payments
  system: payment-platform

---
apiVersion: backstage.io/v1alpha1
kind: System
metadata:
  name: payment-platform
  description: End-to-end payment processing
spec:
  owner: team-payments
  domain: fintech
```

```python
# --- Backstage catalog sync script (reconcile CMDB -> Backstage) ---

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
import yaml

logger = logging.getLogger(__name__)


@dataclass
class CatalogEntity:
    """Represents a Backstage catalog entity."""

    kind: str
    name: str
    namespace: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)
    spec: dict[str, Any] = field(default_factory=dict)

    def to_yaml(self) -> str:
        entity = {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": self.kind,
            "metadata": {"name": self.name, **self.metadata},
            "spec": self.spec,
        }
        return yaml.dump(entity, default_flow_style=False)


@dataclass
class CatalogSyncer:
    """Syncs entities from CMDB into Backstage catalog."""

    backstage_url: str
    backstage_token: str
    cmdb_url: str
    cmdb_token: str
    dry_run: bool = False
    _client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> CatalogSyncer:
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client:
            await self._client.aclose()

    async def fetch_cmdb_services(self) -> list[dict[str, Any]]:
        """Fetch all services from the existing CMDB."""
        assert self._client is not None
        resp = await self._client.get(
            f"{self.cmdb_url}/api/v1/services",
            headers={"Authorization": f"Bearer {self.cmdb_token}"},
        )
        resp.raise_for_status()
        return resp.json()["services"]

    def cmdb_to_catalog_entity(
        self, svc: dict[str, Any]
    ) -> CatalogEntity:
        """Map CMDB service record to Backstage entity."""
        tier_to_lifecycle = {
            "tier-0": "production",
            "tier-1": "production",
            "tier-2": "production",
            "tier-3": "experimental",
        }
        return CatalogEntity(
            kind="Component",
            name=svc["slug"],
            metadata={
                "description": svc.get("description", ""),
                "annotations": {
                    "cmdb.acme.dev/id": str(svc["id"]),
                    "backstage.io/managed-by-origin-location": (
                        f"url:https://cmdb.acme.dev/services/{svc['id']}"
                    ),
                },
                "tags": svc.get("tags", []),
            },
            spec={
                "type": "service",
                "lifecycle": tier_to_lifecycle.get(
                    svc.get("tier", "tier-2"), "production"
                ),
                "owner": svc.get("owning_team", "unknown"),
                "system": svc.get("system", "default"),
            },
        )

    async def upsert_entity(self, entity: CatalogEntity) -> None:
        """Register or update entity in Backstage catalog."""
        assert self._client is not None
        if self.dry_run:
            logger.info(f"[DRY RUN] Would upsert: {entity.kind}/{entity.name}")
            return

        location_target = (
            f"https://cmdb.acme.dev/backstage/{entity.name}/catalog-info.yaml"
        )
        resp = await self._client.post(
            f"{self.backstage_url}/api/catalog/locations",
            json={"type": "url", "target": location_target},
            headers={"Authorization": f"Bearer {self.backstage_token}"},
        )
        if resp.status_code == 409:
            logger.info(f"Entity already registered: {entity.name}")
        elif resp.is_success:
            logger.info(f"Registered entity: {entity.name}")
        else:
            logger.error(
                f"Failed to register {entity.name}: {resp.status_code}"
            )

    async def sync_all(self) -> dict[str, int]:
        """Full sync: CMDB -> Backstage catalog."""
        services = await self.fetch_cmdb_services()
        stats = {"total": len(services), "synced": 0, "errors": 0}

        tasks = []
        for svc in services:
            entity = self.cmdb_to_catalog_entity(svc)
            tasks.append(self.upsert_entity(entity))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                stats["errors"] += 1
                logger.error(f"Sync error: {r}")
            else:
                stats["synced"] += 1

        logger.info(f"Sync complete: {stats}")
        return stats


async def main() -> None:
    async with CatalogSyncer(
        backstage_url="https://portal-api.acme.dev",
        backstage_token="<token>",
        cmdb_url="https://cmdb.acme.dev",
        cmdb_token="<token>",
        dry_run=True,
    ) as syncer:
        await syncer.sync_all()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```

| IDP Component | Backstage Plugin / Tool | Purpose |
|---|---|---|
| Service Catalog | @backstage/plugin-catalog | Discover and own services |
| TechDocs | @backstage/plugin-techdocs | Docs-as-code, MkDocs rendering |
| Scaffolder | @backstage/plugin-scaffolder | Golden path templates |
| Kubernetes | @backstage/plugin-kubernetes | Workload visibility |
| CI/CD | @backstage/plugin-github-actions | Pipeline status |
| Cost tracking | backstage-plugin-cost-insights | Cloud spend per team |
| API docs | @backstage/plugin-api-docs | OpenAPI / gRPC docs |
| Search | @backstage/plugin-search | Unified search across catalog |

Key patterns:

1. **Everything-as-Code catalog** — every service, API, resource, and team is described in catalog-info.yaml checked into its own repo
2. **Provider-based ingestion** — use GitHub/GitLab discovery providers plus custom providers for CMDB sync
3. **Plugin architecture** — extend Backstage with frontend and backend plugins; keep core minimal
4. **Scaffolder actions** — custom actions integrate Terraform, ArgoCD, and cloud APIs into golden-path templates
5. **Entity relationships** — model dependencies (consumesApi, dependsOn) for impact analysis and change management
6. **Auth + RBAC** — integrate with SSO (GitHub, Okta, Azure AD) and use permission framework for fine-grained access
'''
    ),
    (
        "platform-engineering/developer-portal-service-catalog",
        "Build a developer portal with a service catalog that tracks ownership, dependencies, health status, and documentation for all services in the organization.",
        '''Developer portal with service catalog implementation:

```python
# --- Service catalog data model and API ---

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    Session,
    sessionmaker,
)


class Base(DeclarativeBase):
    pass


# --- Enums ---

class Lifecycle(str, enum.Enum):
    EXPERIMENTAL = "experimental"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"
    END_OF_LIFE = "end_of_life"


class HealthStatus(str, enum.Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OUTAGE = "outage"
    UNKNOWN = "unknown"


class Tier(str, enum.Enum):
    CRITICAL = "critical"       # Tier 0 — revenue-impacting
    STANDARD = "standard"       # Tier 1 — customer-facing
    INTERNAL = "internal"       # Tier 2 — internal tools
    BATCH = "batch"             # Tier 3 — async/batch jobs


# --- Association tables ---

service_dependencies = Table(
    "service_dependencies",
    Base.metadata,
    Column("upstream_id", Integer, ForeignKey("services.id"), primary_key=True),
    Column("downstream_id", Integer, ForeignKey("services.id"), primary_key=True),
)


# --- ORM Models ---

class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    slack_channel: Mapped[Optional[str]] = mapped_column(String(80))
    pagerduty_id: Mapped[Optional[str]] = mapped_column(String(40))
    services: Mapped[list[Service]] = relationship(back_populates="team")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    repo_url: Mapped[Optional[str]] = mapped_column(String(500))
    docs_url: Mapped[Optional[str]] = mapped_column(String(500))
    dashboard_url: Mapped[Optional[str]] = mapped_column(String(500))

    lifecycle: Mapped[Lifecycle] = mapped_column(
        SAEnum(Lifecycle), default=Lifecycle.EXPERIMENTAL
    )
    tier: Mapped[Tier] = mapped_column(SAEnum(Tier), default=Tier.INTERNAL)
    health_status: Mapped[HealthStatus] = mapped_column(
        SAEnum(HealthStatus), default=HealthStatus.UNKNOWN
    )

    language: Mapped[Optional[str]] = mapped_column(String(40))
    framework: Mapped[Optional[str]] = mapped_column(String(80))

    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    team: Mapped[Team] = relationship(back_populates="services")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Self-referential many-to-many for dependency graph
    upstream_deps: Mapped[list[Service]] = relationship(
        secondary=service_dependencies,
        primaryjoin=id == service_dependencies.c.downstream_id,
        secondaryjoin=id == service_dependencies.c.upstream_id,
        backref="downstream_deps",
    )

    scorecards: Mapped[list[Scorecard]] = relationship(back_populates="service")


class Scorecard(Base):
    """Tracks maturity/readiness scores for each service."""
    __tablename__ = "scorecards"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    service: Mapped[Service] = relationship(back_populates="scorecards")

    has_runbook: Mapped[bool] = mapped_column(default=False)
    has_slo: Mapped[bool] = mapped_column(default=False)
    has_owner: Mapped[bool] = mapped_column(default=True)
    has_ci_cd: Mapped[bool] = mapped_column(default=False)
    has_monitoring: Mapped[bool] = mapped_column(default=False)
    has_load_tests: Mapped[bool] = mapped_column(default=False)
    pii_classified: Mapped[bool] = mapped_column(default=False)
    disaster_recovery_tested: Mapped[bool] = mapped_column(default=False)

    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    @property
    def score(self) -> float:
        checks = [
            self.has_runbook,
            self.has_slo,
            self.has_owner,
            self.has_ci_cd,
            self.has_monitoring,
            self.has_load_tests,
            self.pii_classified,
            self.disaster_recovery_tested,
        ]
        return sum(checks) / len(checks) * 100
```

```python
# --- FastAPI service catalog endpoints ---

from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel as PydanticBase

app = FastAPI(title="Service Catalog API", version="2.0.0")


class ServiceResponse(PydanticBase):
    slug: str
    name: str
    description: str | None
    lifecycle: str
    tier: str
    health_status: str
    team_slug: str
    repo_url: str | None
    docs_url: str | None
    upstream_deps: list[str]
    scorecard_pct: float | None


class ServiceListResponse(PydanticBase):
    services: list[ServiceResponse]
    total: int
    page: int
    page_size: int


@app.get("/api/v1/services", response_model=ServiceListResponse)
def list_services(
    team: str | None = Query(None, description="Filter by team slug"),
    lifecycle: str | None = Query(None, description="Filter by lifecycle"),
    tier: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ServiceListResponse:
    query = db.query(Service)

    if team:
        query = query.join(Team).filter(Team.slug == team)
    if lifecycle:
        query = query.filter(Service.lifecycle == lifecycle)
    if tier:
        query = query.filter(Service.tier == tier)

    total = query.count()
    services = (
        query.order_by(Service.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ServiceListResponse(
        services=[_to_response(s) for s in services],
        total=total,
        page=page,
        page_size=page_size,
    )


@app.get("/api/v1/services/{slug}", response_model=ServiceResponse)
def get_service(slug: str, db: Session = Depends(get_db)) -> ServiceResponse:
    service = db.query(Service).filter(Service.slug == slug).first()
    if not service:
        raise HTTPException(status_code=404, detail=f"Service '{slug}' not found")
    return _to_response(service)


@app.get("/api/v1/services/{slug}/dependency-graph")
def get_dependency_graph(slug: str, depth: int = Query(3, ge=1, le=10), db: Session = Depends(get_db)):
    """Returns the transitive dependency graph for a service."""
    root = db.query(Service).filter(Service.slug == slug).first()
    if not root:
        raise HTTPException(status_code=404, detail="Service not found")

    visited: set[str] = set()
    edges: list[dict[str, str]] = []

    def walk(svc: Service, current_depth: int) -> None:
        if svc.slug in visited or current_depth > depth:
            return
        visited.add(svc.slug)
        for upstream in svc.upstream_deps:
            edges.append({"from": svc.slug, "to": upstream.slug})
            walk(upstream, current_depth + 1)

    walk(root, 0)
    return {"root": slug, "nodes": list(visited), "edges": edges}


@app.post("/api/v1/services/{slug}/health")
def update_health(
    slug: str,
    status: HealthStatus,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    service = db.query(Service).filter(Service.slug == slug).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    service.health_status = status
    db.commit()
    return {"slug": slug, "health_status": status.value}


def _to_response(svc: Service) -> ServiceResponse:
    latest_score = svc.scorecards[-1].score if svc.scorecards else None
    return ServiceResponse(
        slug=svc.slug,
        name=svc.name,
        description=svc.description,
        lifecycle=svc.lifecycle.value,
        tier=svc.tier.value,
        health_status=svc.health_status.value,
        team_slug=svc.team.slug,
        repo_url=svc.repo_url,
        docs_url=svc.docs_url,
        upstream_deps=[d.slug for d in svc.upstream_deps],
        scorecard_pct=latest_score,
    )
```

```python
# --- Scorecard evaluator (runs nightly via cron) ---

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ScorecardEvaluator:
    """Evaluates service maturity scorecards by checking external systems."""

    github_token: str
    pagerduty_token: str
    grafana_url: str
    grafana_token: str

    async def evaluate(self, service: Service, db: Session) -> Scorecard:
        checks = await self._run_checks(service)
        scorecard = Scorecard(
            service_id=service.id,
            has_runbook=checks["runbook"],
            has_slo=checks["slo"],
            has_owner=service.team_id is not None,
            has_ci_cd=checks["ci_cd"],
            has_monitoring=checks["monitoring"],
            has_load_tests=checks["load_tests"],
            pii_classified=checks["pii"],
            disaster_recovery_tested=checks["dr"],
        )
        db.add(scorecard)
        db.commit()
        logger.info(
            f"Scorecard for {service.slug}: {scorecard.score:.0f}%"
        )
        return scorecard

    async def _run_checks(self, svc: Service) -> dict[str, bool]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            return {
                "runbook": await self._check_runbook(client, svc),
                "slo": await self._check_slo(client, svc),
                "ci_cd": await self._check_ci(client, svc),
                "monitoring": await self._check_monitoring(client, svc),
                "load_tests": await self._check_load_tests(client, svc),
                "pii": await self._check_pii_classification(client, svc),
                "dr": await self._check_dr(client, svc),
            }

    async def _check_runbook(
        self, client: httpx.AsyncClient, svc: Service
    ) -> bool:
        """Check if a runbook directory exists in the service repo."""
        if not svc.repo_url:
            return False
        owner_repo = svc.repo_url.rstrip("/").split("github.com/")[-1]
        resp = await client.get(
            f"https://api.github.com/repos/{owner_repo}/contents/runbook",
            headers={"Authorization": f"token {self.github_token}"},
        )
        return resp.status_code == 200

    async def _check_slo(
        self, client: httpx.AsyncClient, svc: Service
    ) -> bool:
        """Check if SLO dashboard exists in Grafana."""
        resp = await client.get(
            f"{self.grafana_url}/api/search",
            params={"query": f"SLO {svc.slug}"},
            headers={"Authorization": f"Bearer {self.grafana_token}"},
        )
        return resp.status_code == 200 and len(resp.json()) > 0

    async def _check_ci(
        self, client: httpx.AsyncClient, svc: Service
    ) -> bool:
        """Check if CI workflows exist."""
        if not svc.repo_url:
            return False
        owner_repo = svc.repo_url.rstrip("/").split("github.com/")[-1]
        resp = await client.get(
            f"https://api.github.com/repos/{owner_repo}/actions/workflows",
            headers={"Authorization": f"token {self.github_token}"},
        )
        return resp.status_code == 200 and resp.json().get("total_count", 0) > 0

    async def _check_monitoring(
        self, client: httpx.AsyncClient, svc: Service
    ) -> bool:
        resp = await client.get(
            f"{self.grafana_url}/api/search",
            params={"query": svc.slug, "type": "dash-db"},
            headers={"Authorization": f"Bearer {self.grafana_token}"},
        )
        return resp.status_code == 200 and len(resp.json()) > 0

    async def _check_load_tests(
        self, client: httpx.AsyncClient, svc: Service
    ) -> bool:
        if not svc.repo_url:
            return False
        owner_repo = svc.repo_url.rstrip("/").split("github.com/")[-1]
        resp = await client.get(
            f"https://api.github.com/repos/{owner_repo}/contents/tests/load",
            headers={"Authorization": f"token {self.github_token}"},
        )
        return resp.status_code == 200

    async def _check_pii_classification(
        self, client: httpx.AsyncClient, svc: Service
    ) -> bool:
        if not svc.repo_url:
            return False
        owner_repo = svc.repo_url.rstrip("/").split("github.com/")[-1]
        resp = await client.get(
            f"https://api.github.com/repos/{owner_repo}/contents/data-classification.yaml",
            headers={"Authorization": f"token {self.github_token}"},
        )
        return resp.status_code == 200

    async def _check_dr(
        self, client: httpx.AsyncClient, svc: Service
    ) -> bool:
        if not svc.repo_url:
            return False
        owner_repo = svc.repo_url.rstrip("/").split("github.com/")[-1]
        resp = await client.get(
            f"https://api.github.com/repos/{owner_repo}/contents/dr-runbook.md",
            headers={"Authorization": f"token {self.github_token}"},
        )
        return resp.status_code == 200
```

| Catalog Feature | Purpose | Data Source |
|---|---|---|
| Ownership tracking | Who owns what service | catalog-info.yaml / CMDB |
| Dependency graph | Impact analysis, blast radius | Service declarations |
| Health status | Live operational state | Health check endpoints |
| Scorecard | Maturity / production readiness | Automated evaluator |
| Documentation | Searchable docs per service | TechDocs / repo READMEs |
| API specifications | Machine-readable API contracts | OpenAPI / gRPC definitions |
| Change history | Audit trail of service changes | Git commits + deploy events |

Key patterns:

1. **Ownership is mandatory** — every service must have a team owner; orphan services trigger alerts
2. **Dependency graph** — model upstream/downstream relationships for blast-radius analysis during incidents
3. **Automated scorecards** — nightly evaluation against production-readiness criteria drives maturity improvements
4. **Tiered SLAs** — critical (Tier 0) services have stricter scorecard requirements than internal tools
5. **Lifecycle management** — track services from experimental through production to end-of-life
6. **Self-service updates** — teams update catalog-info.yaml in their repos; catalog syncs automatically
'''
    ),
    (
        "platform-engineering/self-service-infrastructure",
        "Implement self-service infrastructure provisioning that lets developers request databases, queues, caches, and Kubernetes namespaces through a portal with approval workflows.",
        '''Self-service infrastructure provisioning system:

```python
# --- Infrastructure request models and workflow engine ---

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class ResourceType(str, enum.Enum):
    POSTGRES_DB = "postgres"
    MYSQL_DB = "mysql"
    REDIS_CACHE = "redis"
    RABBITMQ = "rabbitmq"
    SQS_QUEUE = "sqs"
    S3_BUCKET = "s3"
    K8S_NAMESPACE = "k8s-namespace"


class Environment(str, enum.Enum):
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


class RequestStatus(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROVISIONING = "provisioning"
    PROVISIONED = "provisioned"
    FAILED = "failed"
    DECOMMISSIONED = "decommissioned"


class ResourceSize(str, enum.Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    XLARGE = "xlarge"


class InfraRequest(BaseModel):
    """A developer request for infrastructure resources."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    resource_type: ResourceType
    environment: Environment
    size: ResourceSize
    name: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9-]{2,40}$",
        description="Resource name (lowercase, hyphens allowed)",
    )
    team: str
    requester: str
    justification: str = Field(..., min_length=10)
    ttl_days: Optional[int] = Field(
        None, description="Auto-delete after N days (dev/staging only)"
    )
    config: dict[str, Any] = Field(default_factory=dict)

    status: RequestStatus = RequestStatus.PENDING_APPROVAL
    approver: Optional[str] = None
    approved_at: Optional[datetime] = None
    provisioned_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    terraform_run_id: Optional[str] = None
    outputs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ttl_days")
    @classmethod
    def ttl_only_for_non_prod(cls, v: int | None, info: Any) -> int | None:
        env = info.data.get("environment")
        if v is not None and env == Environment.PRODUCTION:
            raise ValueError("TTL auto-delete not allowed for production")
        return v


# --- Approval policies ---

class ApprovalPolicy:
    """Determines whether a request needs manual approval."""

    # Production always needs approval
    # Large resources need approval
    # Dev/staging small/medium are auto-approved

    AUTO_APPROVE_MATRIX: dict[
        tuple[Environment, ResourceSize], bool
    ] = {
        (Environment.DEV, ResourceSize.SMALL): True,
        (Environment.DEV, ResourceSize.MEDIUM): True,
        (Environment.DEV, ResourceSize.LARGE): False,
        (Environment.DEV, ResourceSize.XLARGE): False,
        (Environment.STAGING, ResourceSize.SMALL): True,
        (Environment.STAGING, ResourceSize.MEDIUM): True,
        (Environment.STAGING, ResourceSize.LARGE): False,
        (Environment.STAGING, ResourceSize.XLARGE): False,
        (Environment.PRODUCTION, ResourceSize.SMALL): False,
        (Environment.PRODUCTION, ResourceSize.MEDIUM): False,
        (Environment.PRODUCTION, ResourceSize.LARGE): False,
        (Environment.PRODUCTION, ResourceSize.XLARGE): False,
    }

    COST_THRESHOLDS: dict[ResourceSize, float] = {
        ResourceSize.SMALL: 50.0,
        ResourceSize.MEDIUM: 200.0,
        ResourceSize.LARGE: 800.0,
        ResourceSize.XLARGE: 2500.0,
    }

    @classmethod
    def can_auto_approve(cls, request: InfraRequest) -> bool:
        return cls.AUTO_APPROVE_MATRIX.get(
            (request.environment, request.size), False
        )

    @classmethod
    def estimated_monthly_cost(cls, request: InfraRequest) -> float:
        return cls.COST_THRESHOLDS.get(request.size, 0.0)
```

```python
# --- Provisioning engine with Terraform integration ---

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class Provisioner(ABC):
    """Abstract provisioner interface."""

    @abstractmethod
    async def provision(self, request: InfraRequest) -> dict[str, Any]:
        ...

    @abstractmethod
    async def deprovision(self, request: InfraRequest) -> None:
        ...

    @abstractmethod
    async def status(self, request: InfraRequest) -> str:
        ...


@dataclass
class TerraformCloudProvisioner(Provisioner):
    """Provisions infrastructure via Terraform Cloud."""

    api_url: str
    token: str
    organization: str

    RESOURCE_TO_MODULE: dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.RESOURCE_TO_MODULE = {
            "postgres": "modules/aws-rds-postgres",
            "mysql": "modules/aws-rds-mysql",
            "redis": "modules/aws-elasticache-redis",
            "rabbitmq": "modules/aws-mq-rabbitmq",
            "sqs": "modules/aws-sqs",
            "s3": "modules/aws-s3",
            "k8s-namespace": "modules/k8s-namespace",
        }

    async def provision(self, request: InfraRequest) -> dict[str, Any]:
        workspace = await self._ensure_workspace(request)
        variables = self._build_variables(request)
        await self._set_variables(workspace["id"], variables)
        run = await self._create_run(workspace["id"], request)

        request.terraform_run_id = run["id"]
        logger.info(
            f"Terraform run {run['id']} started for {request.name}"
        )

        return {
            "workspace_id": workspace["id"],
            "run_id": run["id"],
            "workspace_name": workspace["attributes"]["name"],
        }

    async def deprovision(self, request: InfraRequest) -> None:
        workspace_name = f"{request.name}-{request.environment.value}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            ws_resp = await client.get(
                f"{self.api_url}/organizations/{self.organization}"
                f"/workspaces/{workspace_name}",
                headers=self._headers(),
            )
            ws_resp.raise_for_status()
            ws_id = ws_resp.json()["data"]["id"]

            destroy_resp = await client.post(
                f"{self.api_url}/runs",
                headers=self._headers(),
                json={
                    "data": {
                        "type": "runs",
                        "attributes": {
                            "is-destroy": True,
                            "message": f"Deprovision {request.name}",
                        },
                        "relationships": {
                            "workspace": {
                                "data": {"type": "workspaces", "id": ws_id}
                            }
                        },
                    }
                },
            )
            destroy_resp.raise_for_status()
            logger.info(f"Destroy run created for {request.name}")

    async def status(self, request: InfraRequest) -> str:
        if not request.terraform_run_id:
            return "no_run"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.api_url}/runs/{request.terraform_run_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()["data"]["attributes"]["status"]

    def _build_variables(self, request: InfraRequest) -> dict[str, Any]:
        size_map = {
            "postgres": {
                "small": {"instance_class": "db.t3.micro", "storage_gb": 20},
                "medium": {"instance_class": "db.t3.medium", "storage_gb": 100},
                "large": {"instance_class": "db.r6g.large", "storage_gb": 500},
                "xlarge": {"instance_class": "db.r6g.xlarge", "storage_gb": 1000},
            },
            "redis": {
                "small": {"node_type": "cache.t3.micro", "num_nodes": 1},
                "medium": {"node_type": "cache.t3.medium", "num_nodes": 2},
                "large": {"node_type": "cache.r6g.large", "num_nodes": 3},
                "xlarge": {"node_type": "cache.r6g.xlarge", "num_nodes": 3},
            },
        }
        base_vars = {
            "resource_name": request.name,
            "environment": request.environment.value,
            "team": request.team,
            "tags": json.dumps({
                "team": request.team,
                "environment": request.environment.value,
                "managed-by": "self-service-portal",
                "request-id": request.id,
            }),
        }
        resource_vars = size_map.get(
            request.resource_type.value, {}
        ).get(request.size.value, {})
        return {**base_vars, **resource_vars, **request.config}

    async def _ensure_workspace(
        self, request: InfraRequest
    ) -> dict[str, Any]:
        workspace_name = f"{request.name}-{request.environment.value}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.api_url}/organizations/{self.organization}/workspaces",
                headers=self._headers(),
                json={
                    "data": {
                        "type": "workspaces",
                        "attributes": {
                            "name": workspace_name,
                            "auto-apply": request.environment != Environment.PRODUCTION,
                            "working-directory": self.RESOURCE_TO_MODULE.get(
                                request.resource_type.value, ""
                            ),
                        },
                    }
                },
            )
            if resp.status_code == 422:
                get_resp = await client.get(
                    f"{self.api_url}/organizations/{self.organization}"
                    f"/workspaces/{workspace_name}",
                    headers=self._headers(),
                )
                get_resp.raise_for_status()
                return get_resp.json()["data"]
            resp.raise_for_status()
            return resp.json()["data"]

    async def _set_variables(
        self, workspace_id: str, variables: dict[str, Any]
    ) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for key, value in variables.items():
                await client.post(
                    f"{self.api_url}/workspaces/{workspace_id}/vars",
                    headers=self._headers(),
                    json={
                        "data": {
                            "type": "vars",
                            "attributes": {
                                "key": key,
                                "value": str(value),
                                "category": "terraform",
                                "hcl": isinstance(value, (dict, list)),
                            },
                        }
                    },
                )

    async def _create_run(
        self, workspace_id: str, request: InfraRequest
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.api_url}/runs",
                headers=self._headers(),
                json={
                    "data": {
                        "type": "runs",
                        "attributes": {
                            "message": (
                                f"Self-service: {request.resource_type.value} "
                                f"for {request.team} ({request.requester})"
                            ),
                        },
                        "relationships": {
                            "workspace": {
                                "data": {"type": "workspaces", "id": workspace_id}
                            }
                        },
                    }
                },
            )
            resp.raise_for_status()
            return resp.json()["data"]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/vnd.api+json",
        }
```

```hcl
# --- Terraform module: AWS RDS PostgreSQL (self-service) ---

variable "resource_name" {
  type        = string
  description = "Name of the database instance"
}

variable "environment" {
  type        = string
  description = "dev, staging, or production"
}

variable "team" {
  type        = string
  description = "Owning team"
}

variable "instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "storage_gb" {
  type    = number
  default = 20
}

variable "tags" {
  type    = string
  default = "{}"
}

locals {
  common_tags = merge(
    jsondecode(var.tags),
    {
      Name        = var.resource_name
      Environment = var.environment
      Team        = var.team
      ManagedBy   = "self-service-portal"
    }
  )
  is_prod = var.environment == "production"
}

resource "aws_db_instance" "this" {
  identifier     = "${var.resource_name}-${var.environment}"
  engine         = "postgres"
  engine_version = "15.4"
  instance_class = var.instance_class

  allocated_storage     = var.storage_gb
  max_allocated_storage = var.storage_gb * 2
  storage_encrypted     = true
  storage_type          = "gp3"

  db_name  = replace(var.resource_name, "-", "_")
  username = "app_admin"
  password = random_password.db_password.result

  multi_az               = local.is_prod
  deletion_protection    = local.is_prod
  skip_final_snapshot    = !local.is_prod
  backup_retention_period = local.is_prod ? 30 : 7

  vpc_security_group_ids = [aws_security_group.db.id]
  db_subnet_group_name   = aws_db_subnet_group.this.name

  performance_insights_enabled = local.is_prod

  tags = local.common_tags
}

resource "random_password" "db_password" {
  length  = 32
  special = true
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name = "${var.resource_name}-${var.environment}-db-creds"
  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    host     = aws_db_instance.this.address
    port     = aws_db_instance.this.port
    database = aws_db_instance.this.db_name
    username = aws_db_instance.this.username
    password = random_password.db_password.result
    url      = "postgresql://${aws_db_instance.this.username}:${random_password.db_password.result}@${aws_db_instance.this.address}:${aws_db_instance.this.port}/${aws_db_instance.this.db_name}"
  })
}

output "db_endpoint" {
  value = aws_db_instance.this.address
}

output "db_port" {
  value = aws_db_instance.this.port
}

output "secret_arn" {
  value = aws_secretsmanager_secret.db_credentials.arn
}
```

| Resource Type | Auto-approve (Dev) | Auto-approve (Staging) | Requires Approval (Prod) | Estimated Cost Range |
|---|---|---|---|---|
| PostgreSQL (small) | Yes | Yes | Always | $15-50/mo |
| PostgreSQL (large) | No | No | Always | $200-800/mo |
| Redis (small) | Yes | Yes | Always | $10-30/mo |
| S3 Bucket | Yes | Yes | Always | Pay per use |
| K8s Namespace | Yes | Yes | Always | Free (shared cluster) |
| RabbitMQ | No | No | Always | $50-300/mo |

Key patterns:

1. **Policy-driven approval** — auto-approve low-risk requests (dev small/medium), require human approval for production and large resources
2. **Terraform-backed provisioning** — every resource maps to a Terraform module ensuring consistency and drift detection
3. **Cost estimation** — show estimated monthly costs before approval to prevent budget surprises
4. **TTL for non-production** — auto-delete dev/staging resources after TTL expires to avoid sprawl
5. **Secrets management** — credentials are stored in Secrets Manager, never exposed in portal UI
6. **Tagging enforcement** — every provisioned resource gets mandatory tags for cost attribution and ownership
'''
    ),
    (
        "platform-engineering/golden-paths-scaffolding",
        "Create golden path templates and scaffolding for new services, including project generators, CI/CD pipelines, observability setup, and deployment manifests.",
        '''Golden path templates and scaffolding system:

```yaml
# --- Backstage software template: new Python microservice ---

apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
  name: python-microservice
  title: Python Microservice (Golden Path)
  description: |
    Creates a new Python microservice with FastAPI, Docker, CI/CD,
    Kubernetes manifests, monitoring, and documentation.
  tags:
    - python
    - fastapi
    - recommended
  annotations:
    backstage.io/techdocs-ref: dir:.
spec:
  owner: team-platform
  type: service

  parameters:
    - title: Service Details
      required: [name, description, owner]
      properties:
        name:
          title: Service Name
          type: string
          pattern: '^[a-z][a-z0-9-]{2,40}$'
          ui:autofocus: true
        description:
          title: Description
          type: string
          minLength: 10
        owner:
          title: Owner Team
          type: string
          ui:field: OwnerPicker
          ui:options:
            allowedKinds: [Group]

    - title: Technical Options
      properties:
        python_version:
          title: Python Version
          type: string
          enum: ['3.11', '3.12', '3.13']
          default: '3.12'
        database:
          title: Database
          type: string
          enum: ['none', 'postgres', 'mysql']
          default: 'none'
        cache:
          title: Cache
          type: string
          enum: ['none', 'redis']
          default: 'none'
        message_queue:
          title: Message Queue
          type: string
          enum: ['none', 'rabbitmq', 'sqs']
          default: 'none'
        tier:
          title: Service Tier
          type: string
          enum: ['critical', 'standard', 'internal', 'batch']
          default: 'standard'

    - title: Repository
      required: [repoUrl]
      properties:
        repoUrl:
          title: Repository Location
          type: string
          ui:field: RepoUrlPicker
          ui:options:
            allowedHosts: ['github.com']
            allowedOwners: ['acme-corp']

  steps:
    - id: fetch-skeleton
      name: Fetch project skeleton
      action: fetch:template
      input:
        url: ./skeleton
        values:
          name: ${{ parameters.name }}
          description: ${{ parameters.description }}
          owner: ${{ parameters.owner }}
          python_version: ${{ parameters.python_version }}
          database: ${{ parameters.database }}
          cache: ${{ parameters.cache }}
          tier: ${{ parameters.tier }}

    - id: create-repo
      name: Create GitHub repository
      action: publish:github
      input:
        allowedHosts: ['github.com']
        repoUrl: ${{ parameters.repoUrl }}
        description: ${{ parameters.description }}
        defaultBranch: main
        protectDefaultBranch: true
        requireCodeOwnerReviews: true
        repoVisibility: internal

    - id: provision-infra
      name: Provision infrastructure
      action: acme:infra:provision
      input:
        serviceName: ${{ parameters.name }}
        team: ${{ parameters.owner }}
        environment: dev
        tier: ${{ parameters.tier }}
        resources:
          cpu: "250m"
          memory: "512Mi"
          replicas: 1
        database:
          ${{ if parameters.database !== 'none' }}:
            engine: ${{ parameters.database }}
            size: small

    - id: register-catalog
      name: Register in service catalog
      action: catalog:register
      input:
        repoContentsUrl: ${{ steps['create-repo'].output.repoContentsUrl }}
        catalogInfoPath: /catalog-info.yaml

    - id: setup-argocd
      name: Create ArgoCD application
      action: argocd:create-app
      input:
        appName: ${{ parameters.name }}-dev
        repoUrl: ${{ steps['create-repo'].output.remoteUrl }}
        path: deploy/k8s/overlays/dev
        cluster: dev-cluster
        namespace: ${{ parameters.name }}

  output:
    links:
      - title: Repository
        url: ${{ steps['create-repo'].output.remoteUrl }}
      - title: Open in Catalog
        icon: catalog
        entityRef: ${{ steps['register-catalog'].output.entityRef }}
      - title: ArgoCD App
        url: https://argocd.acme.dev/applications/${{ parameters.name }}-dev
```

```python
# --- Cookiecutter-style template engine for golden paths ---

from __future__ import annotations

import os
import shutil
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2
import yaml

logger = logging.getLogger(__name__)


@dataclass
class TemplateConfig:
    """Configuration for a golden-path template."""

    name: str
    description: str
    variables: dict[str, Any]
    conditional_files: dict[str, str] = field(default_factory=dict)
    # e.g., {"database/migrations/": "database != 'none'"}


@dataclass
class GoldenPathGenerator:
    """Generates project scaffolding from golden-path templates."""

    templates_dir: Path
    output_dir: Path
    _env: jinja2.Environment | None = None

    def __post_init__(self) -> None:
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.templates_dir)),
            keep_trailing_newline=True,
            undefined=jinja2.StrictUndefined,
        )

    def generate(
        self,
        template_name: str,
        variables: dict[str, Any],
    ) -> Path:
        """Generate a new project from a template."""
        template_dir = self.templates_dir / template_name / "skeleton"
        if not template_dir.exists():
            raise FileNotFoundError(
                f"Template skeleton not found: {template_dir}"
            )

        # Load template config
        config_path = self.templates_dir / template_name / "template.yaml"
        config = self._load_config(config_path)

        # Merge defaults with provided variables
        merged_vars = {**config.variables, **variables}
        project_dir = self.output_dir / merged_vars["name"]

        if project_dir.exists():
            raise FileExistsError(f"Project directory already exists: {project_dir}")

        logger.info(f"Generating project: {merged_vars['name']}")

        # Walk template and render files
        for root, dirs, files in os.walk(template_dir):
            rel_root = Path(root).relative_to(template_dir)

            # Check conditional directory inclusion
            skip_dir = False
            for cond_path, condition in config.conditional_files.items():
                if str(rel_root).startswith(cond_path):
                    if not self._evaluate_condition(condition, merged_vars):
                        skip_dir = True
                        break
            if skip_dir:
                continue

            # Create directory
            target_dir = project_dir / self._render_path(
                str(rel_root), merged_vars
            )
            target_dir.mkdir(parents=True, exist_ok=True)

            for filename in files:
                src_path = Path(root) / filename
                rendered_filename = self._render_path(filename, merged_vars)
                target_path = target_dir / rendered_filename

                if filename.endswith(('.j2', '.jinja2')):
                    # Render Jinja2 template
                    target_path = target_path.with_suffix('')
                    content = self._render_template(src_path, merged_vars)
                    target_path.write_text(content, encoding="utf-8")
                else:
                    # Copy as-is
                    shutil.copy2(src_path, target_path)

                logger.debug(f"  Created: {target_path.relative_to(project_dir)}")

        # Post-generation hooks
        self._run_post_hooks(project_dir, merged_vars)

        logger.info(f"Project generated at: {project_dir}")
        return project_dir

    def _load_config(self, path: Path) -> TemplateConfig:
        with open(path) as f:
            data = yaml.safe_load(f)
        return TemplateConfig(
            name=data["name"],
            description=data.get("description", ""),
            variables=data.get("variables", {}),
            conditional_files=data.get("conditional_files", {}),
        )

    def _render_path(self, path: str, variables: dict[str, Any]) -> str:
        """Render variable substitutions in file/directory names."""
        result = path
        for key, value in variables.items():
            result = result.replace(f"{{{{ {key} }}}}", str(value))
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result

    def _render_template(
        self, template_path: Path, variables: dict[str, Any]
    ) -> str:
        """Render a Jinja2 template file."""
        assert self._env is not None
        with open(template_path) as f:
            template = self._env.from_string(f.read())
        return template.render(**variables)

    def _evaluate_condition(
        self, condition: str, variables: dict[str, Any]
    ) -> bool:
        """Evaluate a simple condition expression."""
        # Simple evaluation: "database != 'none'"
        try:
            return bool(eval(condition, {"__builtins__": {}}, variables))  # noqa: S307
        except Exception:
            logger.warning(f"Failed to evaluate condition: {condition}")
            return True

    def _run_post_hooks(
        self, project_dir: Path, variables: dict[str, Any]
    ) -> None:
        """Run post-generation hooks (git init, dependency install, etc.)."""
        import subprocess

        hooks = [
            ["git", "init"],
            ["git", "add", "."],
            ["git", "commit", "-m", "Initial scaffold from golden path"],
        ]
        for cmd in hooks:
            try:
                subprocess.run(
                    cmd, cwd=project_dir, check=True, capture_output=True
                )
                logger.info(f"  Hook: {' '.join(cmd)}")
            except subprocess.CalledProcessError as e:
                logger.warning(f"  Hook failed: {' '.join(cmd)} - {e}")
```

```yaml
# --- Generated project structure (skeleton) ---

# skeleton/
# +-- catalog-info.yaml.j2
# +-- Dockerfile.j2
# +-- pyproject.toml.j2
# +-- src/
# |   +-- {{ name }}/
# |       +-- __init__.py
# |       +-- app.py.j2
# |       +-- config.py.j2
# |       +-- health.py
# +-- tests/
# |   +-- conftest.py.j2
# |   +-- test_health.py
# +-- deploy/
# |   +-- k8s/
# |       +-- base/
# |       |   +-- deployment.yaml.j2
# |       |   +-- service.yaml.j2
# |       |   +-- kustomization.yaml.j2
# |       +-- overlays/
# |           +-- dev/
# |           |   +-- kustomization.yaml.j2
# |           +-- staging/
# |           |   +-- kustomization.yaml.j2
# |           +-- production/
# |               +-- kustomization.yaml.j2
# +-- .github/
# |   +-- workflows/
# |       +-- ci.yaml.j2
# |       +-- deploy.yaml.j2
# +-- docs/
#     +-- index.md.j2
#     +-- adr/
#         +-- 0001-initial-architecture.md.j2

# --- Example: Dockerfile.j2 ---
# syntax=docker/dockerfile:1

FROM python:{{ python_version }}-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

FROM base AS builder
RUN pip install --no-cache-dir uv
COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml

FROM base AS runtime
COPY --from=builder /usr/local/lib/python{{ python_version }}/site-packages \
     /usr/local/lib/python{{ python_version }}/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src/ ./src/

RUN groupadd -r app && useradd -r -g app app
USER app

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"]

CMD ["uvicorn", "{{ name }}.app:app", "--host", "0.0.0.0", "--port", "8080"]

# --- Example: .github/workflows/ci.yaml.j2 ---
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '{{ python_version }}'
      - run: pip install uv && uv pip install --system -e ".[dev]"
      - run: pytest --cov={{ name }} --cov-report=xml
      - uses: codecov/codecov-action@v4

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '{{ python_version }}'
      - run: pip install ruff mypy
      - run: ruff check src/ tests/
      - run: mypy src/

  build:
    needs: [test, lint]
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: {% raw %}${{ github.actor }}{% endraw %}
          password: {% raw %}${{ secrets.GITHUB_TOKEN }}{% endraw %}
      - uses: docker/build-push-action@v5
        with:
          push: {% raw %}${{ github.ref == 'refs/heads/main' }}{% endraw %}
          tags: ghcr.io/acme-corp/{{ name }}:{% raw %}${{ github.sha }}{% endraw %}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

| Golden Path Component | What It Provides | Why It Matters |
|---|---|---|
| Project skeleton | Standardized directory layout | Consistency across all services |
| Dockerfile | Multi-stage build, non-root user | Security + small images |
| CI pipeline | Test, lint, build, push | Automated quality gates |
| K8s manifests | Kustomize overlays per env | GitOps-ready deployment |
| catalog-info.yaml | Backstage registration | Discoverability + ownership |
| Health endpoints | /health, /ready | K8s probe integration |
| Observability | Structured logging, metrics | Day-1 monitoring |
| Documentation | ADR template, docs/ dir | Knowledge preservation |

Key patterns:

1. **Opinionated defaults** — golden paths make the right thing easy, not mandatory; teams can customize after scaffolding
2. **Template versioning** — version templates so existing services can track upstream improvements
3. **Conditional sections** — include database migrations, cache config, or queue consumers only when those options are selected
4. **Multi-environment from day one** — Kustomize overlays for dev/staging/prod prevent "works on my machine" issues
5. **Automated catalog registration** — new services appear in Backstage immediately after scaffolding
6. **Post-generation hooks** — git init, dependency install, and initial commit happen automatically
'''
    ),
    (
        "platform-engineering/platform-metrics-devex",
        "Design a platform metrics and developer experience measurement system that tracks DORA metrics, developer satisfaction, and platform adoption to drive continuous improvement.",
        '''Platform metrics and developer experience measurement system:

```python
# --- DORA metrics collector ---

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class ChangeFailureType(str, Enum):
    ROLLBACK = "rollback"
    HOTFIX = "hotfix"
    INCIDENT = "incident"
    FIX_FORWARD = "fix_forward"


@dataclass
class DeploymentEvent:
    """A single deployment event."""

    service: str
    team: str
    environment: str
    commit_sha: str
    deployed_at: datetime
    lead_time_seconds: float  # Time from first commit to deploy
    is_failure: bool = False
    failure_type: Optional[ChangeFailureType] = None
    recovery_time_seconds: Optional[float] = None


@dataclass
class DORAMetrics:
    """DORA four key metrics for a team/service."""

    team: str
    period_start: datetime
    period_end: datetime

    # Deployment Frequency
    total_deployments: int = 0
    deployments_per_day: float = 0.0

    # Lead Time for Changes
    median_lead_time_hours: float = 0.0
    p95_lead_time_hours: float = 0.0

    # Change Failure Rate
    total_failures: int = 0
    change_failure_rate_pct: float = 0.0

    # Mean Time to Recovery
    median_mttr_hours: float = 0.0
    p95_mttr_hours: float = 0.0

    @property
    def deployment_frequency_rating(self) -> str:
        if self.deployments_per_day >= 1.0:
            return "Elite"
        elif self.deployments_per_day >= 1 / 7:
            return "High"
        elif self.deployments_per_day >= 1 / 30:
            return "Medium"
        return "Low"

    @property
    def lead_time_rating(self) -> str:
        if self.median_lead_time_hours < 24:
            return "Elite"
        elif self.median_lead_time_hours < 168:  # 1 week
            return "High"
        elif self.median_lead_time_hours < 720:  # 1 month
            return "Medium"
        return "Low"

    @property
    def change_failure_rating(self) -> str:
        if self.change_failure_rate_pct <= 5:
            return "Elite"
        elif self.change_failure_rate_pct <= 10:
            return "High"
        elif self.change_failure_rate_pct <= 15:
            return "Medium"
        return "Low"

    @property
    def mttr_rating(self) -> str:
        if self.median_mttr_hours < 1:
            return "Elite"
        elif self.median_mttr_hours < 24:
            return "High"
        elif self.median_mttr_hours < 168:  # 1 week
            return "Medium"
        return "Low"

    @property
    def overall_rating(self) -> str:
        ratings = [
            self.deployment_frequency_rating,
            self.lead_time_rating,
            self.change_failure_rating,
            self.mttr_rating,
        ]
        rating_scores = {"Elite": 4, "High": 3, "Medium": 2, "Low": 1}
        avg = sum(rating_scores[r] for r in ratings) / len(ratings)
        if avg >= 3.5:
            return "Elite"
        elif avg >= 2.5:
            return "High"
        elif avg >= 1.5:
            return "Medium"
        return "Low"


@dataclass
class DORACollector:
    """Collects and computes DORA metrics from CI/CD and incident data."""

    github_token: str
    github_org: str
    incident_api_url: str
    incident_api_token: str

    async def compute_metrics(
        self,
        team: str,
        services: list[str],
        period_days: int = 30,
    ) -> DORAMetrics:
        period_end = datetime.utcnow()
        period_start = period_end - timedelta(days=period_days)

        events = await self._collect_deployment_events(
            services, period_start, period_end
        )
        incidents = await self._collect_incidents(
            services, period_start, period_end
        )

        # Mark failure deployments
        for event in events:
            for incident in incidents:
                if (
                    event.service == incident.get("service")
                    and abs(
                        (event.deployed_at - incident["started_at"]).total_seconds()
                    )
                    < 3600
                ):
                    event.is_failure = True
                    event.failure_type = ChangeFailureType.INCIDENT
                    if incident.get("resolved_at"):
                        event.recovery_time_seconds = (
                            incident["resolved_at"] - incident["started_at"]
                        ).total_seconds()

        # Compute metrics
        total_days = (period_end - period_start).days or 1
        lead_times = sorted(
            e.lead_time_seconds / 3600 for e in events
        )
        failure_events = [e for e in events if e.is_failure]
        recovery_times = sorted(
            e.recovery_time_seconds / 3600
            for e in failure_events
            if e.recovery_time_seconds
        )

        return DORAMetrics(
            team=team,
            period_start=period_start,
            period_end=period_end,
            total_deployments=len(events),
            deployments_per_day=len(events) / total_days,
            median_lead_time_hours=(
                lead_times[len(lead_times) // 2] if lead_times else 0
            ),
            p95_lead_time_hours=(
                lead_times[int(len(lead_times) * 0.95)] if lead_times else 0
            ),
            total_failures=len(failure_events),
            change_failure_rate_pct=(
                len(failure_events) / len(events) * 100 if events else 0
            ),
            median_mttr_hours=(
                recovery_times[len(recovery_times) // 2]
                if recovery_times
                else 0
            ),
            p95_mttr_hours=(
                recovery_times[int(len(recovery_times) * 0.95)]
                if recovery_times
                else 0
            ),
        )

    async def _collect_deployment_events(
        self,
        services: list[str],
        start: datetime,
        end: datetime,
    ) -> list[DeploymentEvent]:
        events: list[DeploymentEvent] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for service in services:
                resp = await client.get(
                    f"https://api.github.com/repos/{self.github_org}"
                    f"/{service}/actions/runs",
                    headers={
                        "Authorization": f"token {self.github_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    params={
                        "branch": "main",
                        "status": "completed",
                        "created": f">={start.isoformat()}",
                        "per_page": 100,
                    },
                )
                if resp.status_code != 200:
                    continue
                for run in resp.json().get("workflow_runs", []):
                    if run["name"] in ("Deploy", "CD", "Release"):
                        created = datetime.fromisoformat(
                            run["created_at"].replace("Z", "+00:00")
                        )
                        events.append(
                            DeploymentEvent(
                                service=service,
                                team="",
                                environment="production",
                                commit_sha=run["head_sha"],
                                deployed_at=created,
                                lead_time_seconds=(
                                    created - datetime.fromisoformat(
                                        run.get("head_commit", {})
                                        .get("timestamp", created.isoformat())
                                        .replace("Z", "+00:00")
                                    )
                                ).total_seconds(),
                            )
                        )
        return events

    async def _collect_incidents(
        self,
        services: list[str],
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.incident_api_url}/api/v1/incidents",
                headers={
                    "Authorization": f"Bearer {self.incident_api_token}"
                },
                params={
                    "services": ",".join(services),
                    "since": start.isoformat(),
                    "until": end.isoformat(),
                },
            )
            if resp.status_code != 200:
                return []
            return resp.json().get("incidents", [])
```

```python
# --- Developer Experience survey and metrics dashboard ---

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DevExSurveyResponse(BaseModel):
    """Developer experience survey response."""

    respondent_team: str
    submitted_at: datetime = Field(default_factory=datetime.utcnow)

    # Scale 1-5 (Strongly Disagree to Strongly Agree)
    easy_to_deploy: int = Field(..., ge=1, le=5)
    easy_to_create_service: int = Field(..., ge=1, le=5)
    docs_are_helpful: int = Field(..., ge=1, le=5)
    ci_cd_is_fast: int = Field(..., ge=1, le=5)
    monitoring_is_sufficient: int = Field(..., ge=1, le=5)
    can_find_service_info: int = Field(..., ge=1, le=5)
    platform_team_responsive: int = Field(..., ge=1, le=5)
    would_recommend_platform: int = Field(..., ge=1, le=10)  # NPS scale

    # Free-text
    biggest_pain_point: str = ""
    feature_request: str = ""


@dataclass
class DevExMetrics:
    """Aggregated developer experience metrics."""

    period: str
    total_responses: int = 0

    # Survey averages (1-5)
    avg_ease_of_deploy: float = 0.0
    avg_ease_of_create: float = 0.0
    avg_docs_quality: float = 0.0
    avg_ci_speed: float = 0.0
    avg_monitoring: float = 0.0
    avg_discoverability: float = 0.0
    avg_support_responsiveness: float = 0.0
    nps_score: float = 0.0  # -100 to +100

    # Operational metrics (automated)
    avg_pr_to_deploy_minutes: float = 0.0
    avg_ci_pipeline_minutes: float = 0.0
    pct_golden_path_adoption: float = 0.0
    pct_services_with_scorecard_above_80: float = 0.0
    avg_onboarding_days: float = 0.0
    self_service_requests_per_month: int = 0
    support_tickets_per_month: int = 0
    platform_api_error_rate_pct: float = 0.0


@dataclass
class PlatformDashboard:
    """Computes and renders platform metrics dashboard data."""

    dora_collector: DORACollector
    catalog_api_url: str
    survey_responses: list[DevExSurveyResponse] = field(default_factory=list)

    def compute_devex_metrics(
        self, responses: list[DevExSurveyResponse], period: str
    ) -> DevExMetrics:
        if not responses:
            return DevExMetrics(period=period)

        n = len(responses)
        promoters = sum(1 for r in responses if r.would_recommend_platform >= 9)
        detractors = sum(1 for r in responses if r.would_recommend_platform <= 6)

        return DevExMetrics(
            period=period,
            total_responses=n,
            avg_ease_of_deploy=sum(r.easy_to_deploy for r in responses) / n,
            avg_ease_of_create=sum(r.easy_to_create_service for r in responses) / n,
            avg_docs_quality=sum(r.docs_are_helpful for r in responses) / n,
            avg_ci_speed=sum(r.ci_cd_is_fast for r in responses) / n,
            avg_monitoring=sum(r.monitoring_is_sufficient for r in responses) / n,
            avg_discoverability=sum(r.can_find_service_info for r in responses) / n,
            avg_support_responsiveness=sum(
                r.platform_team_responsive for r in responses
            ) / n,
            nps_score=(promoters - detractors) / n * 100,
        )

    def generate_report(
        self, dora: DORAMetrics, devex: DevExMetrics
    ) -> dict[str, Any]:
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "dora": {
                "deployment_frequency": {
                    "value": f"{dora.deployments_per_day:.2f}/day",
                    "rating": dora.deployment_frequency_rating,
                },
                "lead_time": {
                    "value": f"{dora.median_lead_time_hours:.1f}h",
                    "rating": dora.lead_time_rating,
                },
                "change_failure_rate": {
                    "value": f"{dora.change_failure_rate_pct:.1f}%",
                    "rating": dora.change_failure_rating,
                },
                "mttr": {
                    "value": f"{dora.median_mttr_hours:.1f}h",
                    "rating": dora.mttr_rating,
                },
                "overall": dora.overall_rating,
            },
            "developer_experience": {
                "nps": devex.nps_score,
                "satisfaction_scores": {
                    "deploy_ease": devex.avg_ease_of_deploy,
                    "service_creation": devex.avg_ease_of_create,
                    "documentation": devex.avg_docs_quality,
                    "ci_speed": devex.avg_ci_speed,
                    "monitoring": devex.avg_monitoring,
                    "discoverability": devex.avg_discoverability,
                    "support": devex.avg_support_responsiveness,
                },
                "survey_responses": devex.total_responses,
            },
            "platform_adoption": {
                "golden_path_pct": devex.pct_golden_path_adoption,
                "scorecard_above_80_pct": devex.pct_services_with_scorecard_above_80,
                "self_service_requests": devex.self_service_requests_per_month,
                "support_tickets": devex.support_tickets_per_month,
            },
        }
```

```yaml
# --- Grafana dashboard for platform metrics (provisioned) ---

apiVersion: 1
providers:
  - name: Platform Engineering
    folder: Platform
    type: file
    options:
      path: /var/lib/grafana/dashboards/platform

# --- platform-overview.json (simplified) ---
# Dashboard panels:
#
# Row 1: DORA Metrics
#   - Deployment Frequency (timeseries, per team)
#   - Lead Time for Changes (timeseries, p50/p95)
#   - Change Failure Rate (gauge, 0-100%)
#   - MTTR (timeseries, p50/p95)
#
# Row 2: Developer Experience
#   - NPS Score (stat panel, -100 to +100)
#   - Satisfaction by Category (bar chart)
#   - Survey Response Rate (stat panel)
#   - Pain Points Word Cloud (text panel)
#
# Row 3: Platform Adoption
#   - Golden Path Adoption % (gauge)
#   - Self-Service vs Tickets (timeseries)
#   - Scorecard Distribution (histogram)
#   - New Services Created (counter)

# --- PromQL queries for automated DORA collection ---
# Deployment frequency:
#   sum(increase(deploy_total{env="production"}[7d])) by (team)
#
# Lead time (from CI timestamps):
#   histogram_quantile(0.50, rate(deploy_lead_time_seconds_bucket[7d]))
#
# Change failure rate:
#   sum(increase(deploy_failure_total[30d])) /
#   sum(increase(deploy_total[30d])) * 100
#
# MTTR:
#   histogram_quantile(0.50, rate(incident_recovery_seconds_bucket[30d]))

# --- Alert rules for platform health ---
groups:
  - name: platform_health
    interval: 5m
    rules:
      - alert: HighChangeFailureRate
        expr: >
          sum(increase(deploy_failure_total{env="production"}[7d]))
          / sum(increase(deploy_total{env="production"}[7d]))
          > 0.15
        for: 1h
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Change failure rate above 15% over past 7 days"

      - alert: SlowLeadTime
        expr: >
          histogram_quantile(0.95,
            rate(deploy_lead_time_seconds_bucket[7d])
          ) > 604800
        for: 2h
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "p95 lead time exceeds 7 days"

      - alert: LowGoldenPathAdoption
        expr: >
          golden_path_adoption_ratio < 0.5
        for: 24h
        labels:
          severity: info
          team: platform
        annotations:
          summary: "Golden path adoption below 50%"
```

| Metric Category | Metric | Elite | High | Medium | Low |
|---|---|---|---|---|---|
| DORA | Deploy Frequency | Multiple/day | Weekly | Monthly | < Monthly |
| DORA | Lead Time | < 1 day | < 1 week | < 1 month | > 1 month |
| DORA | Change Failure Rate | < 5% | < 10% | < 15% | > 15% |
| DORA | MTTR | < 1 hour | < 1 day | < 1 week | > 1 week |
| DevEx | NPS | > 50 | > 20 | > 0 | < 0 |
| DevEx | Satisfaction (avg) | > 4.5 | > 3.5 | > 2.5 | < 2.5 |
| Adoption | Golden Path % | > 80% | > 60% | > 40% | < 40% |
| Adoption | Self-service ratio | > 90% | > 70% | > 50% | < 50% |

Key patterns:

1. **DORA metrics as north star** — deployment frequency, lead time, change failure rate, and MTTR are the four key metrics that correlate with high-performing teams
2. **Automated collection** — pull DORA data from CI/CD systems, incident management, and Git; avoid manual reporting
3. **Developer experience surveys** — quarterly NPS-style surveys measure subjective satisfaction alongside objective metrics
4. **Platform adoption tracking** — measure golden path usage, self-service ratio, and scorecard compliance as indicators of platform value
5. **Team-level dashboards** — show metrics per team to enable comparison without shaming; focus on trends not absolutes
6. **Alert on regressions** — alert when DORA metrics degrade (e.g., change failure rate exceeds 15%) to trigger platform improvements
'''
    ),
]
"""
