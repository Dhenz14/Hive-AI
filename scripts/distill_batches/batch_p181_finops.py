"""FinOps — cloud cost optimization."""

PAIRS = [
    (
        "finops/cloud-cost-monitoring-attribution",
        "Build a cloud cost monitoring and attribution system that tracks spend by team, service, and environment with anomaly detection and budget alerts.",
        '''Cloud cost monitoring and attribution system:

```python
# --- Cost data ingestion and attribution engine ---

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

import boto3
import httpx

logger = logging.getLogger(__name__)


class CloudProvider(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"


class CostGranularity(str, Enum):
    DAILY = "DAILY"
    MONTHLY = "MONTHLY"
    HOURLY = "HOURLY"


@dataclass
class CostRecord:
    """Single cost record attributed to a team/service."""

    date: date
    provider: CloudProvider
    account_id: str
    service: str          # AWS service name (EC2, RDS, etc.)
    team: str
    application: str
    environment: str
    region: str
    cost_usd: Decimal
    usage_quantity: float
    usage_unit: str
    resource_id: Optional[str] = None


@dataclass
class AWSCostCollector:
    """Collects cost data from AWS Cost Explorer."""

    session: boto3.Session
    tag_key_team: str = "Team"
    tag_key_app: str = "Application"
    tag_key_env: str = "Environment"

    def collect(
        self,
        start_date: date,
        end_date: date,
        granularity: CostGranularity = CostGranularity.DAILY,
    ) -> list[CostRecord]:
        client = self.session.client("ce")
        records: list[CostRecord] = []

        response = client.get_cost_and_usage(
            TimePeriod={
                "Start": start_date.isoformat(),
                "End": end_date.isoformat(),
            },
            Granularity=granularity.value,
            Metrics=["UnblendedCost", "UsageQuantity"],
            GroupBy=[
                {"Type": "DIMENSION", "Key": "SERVICE"},
                {"Type": "DIMENSION", "Key": "REGION"},
                {"Type": "TAG", "Key": self.tag_key_team},
            ],
        )

        for period in response["ResultsByTime"]:
            period_date = date.fromisoformat(period["TimePeriod"]["Start"])
            for group in period["Groups"]:
                keys = group["Keys"]
                cost = Decimal(
                    group["Metrics"]["UnblendedCost"]["Amount"]
                )
                usage = float(
                    group["Metrics"]["UsageQuantity"]["Amount"]
                )

                if cost <= 0:
                    continue

                # Parse group keys
                aws_service = keys[0]
                region = keys[1] if len(keys) > 1 else "global"
                team_tag = keys[2].replace(f"{self.tag_key_team}$", "") if len(keys) > 2 else "untagged"

                records.append(
                    CostRecord(
                        date=period_date,
                        provider=CloudProvider.AWS,
                        account_id=self._get_account_id(),
                        service=aws_service,
                        team=team_tag or "untagged",
                        application="unknown",
                        environment="unknown",
                        region=region,
                        cost_usd=cost,
                        usage_quantity=usage,
                        usage_unit=group["Metrics"]["UsageQuantity"].get(
                            "Unit", "count"
                        ),
                    )
                )

        logger.info(
            f"Collected {len(records)} cost records "
            f"from {start_date} to {end_date}"
        )
        return records

    def _get_account_id(self) -> str:
        sts = self.session.client("sts")
        return sts.get_caller_identity()["Account"]

    def get_untagged_resources(self) -> list[dict[str, Any]]:
        """Find resources missing cost-attribution tags."""
        client = self.session.client("resourcegroupstaggingapi")
        untagged: list[dict[str, Any]] = []

        paginator = client.get_paginator("get_resources")
        for page in paginator.paginate(
            TagFilters=[
                {"Key": self.tag_key_team, "Values": []},
            ],
            ExcludeCompliantResources=False,
        ):
            for resource in page["ResourceTagMappingList"]:
                tag_keys = [t["Key"] for t in resource.get("Tags", [])]
                if self.tag_key_team not in tag_keys:
                    untagged.append({
                        "arn": resource["ResourceARN"],
                        "missing_tags": [
                            t for t in [self.tag_key_team, self.tag_key_app, self.tag_key_env]
                            if t not in tag_keys
                        ],
                    })

        logger.info(f"Found {len(untagged)} untagged resources")
        return untagged
```

```python
# --- Cost anomaly detection and budget alerts ---

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any


@dataclass
class CostAnomaly:
    """Detected cost anomaly."""

    team: str
    service: str
    date: date
    actual_cost: Decimal
    expected_cost: Decimal
    deviation_pct: float
    severity: str  # "warning" | "critical"
    details: str


@dataclass
class BudgetAlert:
    """Budget threshold alert."""

    team: str
    budget_name: str
    period: str
    budget_amount: Decimal
    actual_amount: Decimal
    forecasted_amount: Decimal
    pct_used: float
    alert_threshold_pct: float
    status: str  # "ok" | "warning" | "exceeded"


@dataclass
class CostAnalyzer:
    """Analyzes cost data for anomalies and budget adherence."""

    lookback_days: int = 30
    anomaly_std_threshold: float = 2.0
    warning_threshold_pct: float = 80.0
    critical_threshold_pct: float = 100.0

    def detect_anomalies(
        self,
        records: list[CostRecord],
        current_date: date,
    ) -> list[CostAnomaly]:
        """Detect cost anomalies using statistical analysis."""
        anomalies: list[CostAnomaly] = []

        # Group records by (team, service)
        groups: dict[tuple[str, str], list[CostRecord]] = {}
        for r in records:
            key = (r.team, r.service)
            groups.setdefault(key, []).append(r)

        lookback_start = current_date - timedelta(days=self.lookback_days)

        for (team, service), group_records in groups.items():
            # Separate historical and current
            historical = [
                r for r in group_records
                if lookback_start <= r.date < current_date
            ]
            current = [
                r for r in group_records if r.date == current_date
            ]

            if not historical or not current:
                continue

            # Compute baseline statistics
            daily_costs = [float(r.cost_usd) for r in historical]
            mean_cost = statistics.mean(daily_costs)
            if len(daily_costs) < 3:
                continue
            std_cost = statistics.stdev(daily_costs)

            # Check current day
            current_total = sum(float(r.cost_usd) for r in current)
            if std_cost > 0:
                z_score = (current_total - mean_cost) / std_cost
            else:
                z_score = 0 if current_total == mean_cost else 10

            if abs(z_score) > self.anomaly_std_threshold:
                deviation_pct = (
                    (current_total - mean_cost) / mean_cost * 100
                    if mean_cost > 0
                    else 0
                )
                severity = (
                    "critical"
                    if abs(z_score) > self.anomaly_std_threshold * 1.5
                    else "warning"
                )
                anomalies.append(
                    CostAnomaly(
                        team=team,
                        service=service,
                        date=current_date,
                        actual_cost=Decimal(str(round(current_total, 2))),
                        expected_cost=Decimal(str(round(mean_cost, 2))),
                        deviation_pct=round(deviation_pct, 1),
                        severity=severity,
                        details=(
                            f"Cost ${current_total:.2f} is "
                            f"{abs(z_score):.1f} std devs from "
                            f"mean ${mean_cost:.2f} "
                            f"(30-day baseline, std=${std_cost:.2f})"
                        ),
                    )
                )

        return sorted(
            anomalies, key=lambda a: abs(a.deviation_pct), reverse=True
        )

    def check_budgets(
        self,
        budgets: list[dict[str, Any]],
        records: list[CostRecord],
        current_date: date,
    ) -> list[BudgetAlert]:
        """Check spend against budget thresholds."""
        alerts: list[BudgetAlert] = []

        for budget in budgets:
            team = budget["team"]
            period = budget["period"]  # "monthly" or "quarterly"
            budget_amount = Decimal(str(budget["amount"]))

            # Filter records for this team and period
            if period == "monthly":
                period_start = current_date.replace(day=1)
                days_in_period = 30
            else:
                quarter_month = ((current_date.month - 1) // 3) * 3 + 1
                period_start = current_date.replace(
                    month=quarter_month, day=1
                )
                days_in_period = 90

            team_records = [
                r for r in records
                if r.team == team and r.date >= period_start
            ]
            actual = sum(r.cost_usd for r in team_records)
            days_elapsed = max((current_date - period_start).days, 1)
            daily_rate = actual / days_elapsed
            forecasted = daily_rate * days_in_period
            pct_used = float(actual / budget_amount * 100) if budget_amount else 0

            if pct_used >= self.critical_threshold_pct:
                status = "exceeded"
            elif pct_used >= self.warning_threshold_pct:
                status = "warning"
            else:
                status = "ok"

            alerts.append(
                BudgetAlert(
                    team=team,
                    budget_name=budget.get("name", f"{team}-{period}"),
                    period=period,
                    budget_amount=budget_amount,
                    actual_amount=actual,
                    forecasted_amount=Decimal(str(round(float(forecasted), 2))),
                    pct_used=round(pct_used, 1),
                    alert_threshold_pct=(
                        self.critical_threshold_pct
                        if status == "exceeded"
                        else self.warning_threshold_pct
                    ),
                    status=status,
                )
            )

        return [a for a in alerts if a.status != "ok"]
```

```python
# --- Slack notification and reporting ---

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

import httpx


@dataclass
class CostReporter:
    """Sends cost reports and alerts to Slack and dashboards."""

    slack_webhook_url: str

    async def send_daily_report(
        self,
        team: str,
        daily_cost: Decimal,
        mtd_cost: Decimal,
        budget: Decimal,
        top_services: list[tuple[str, Decimal]],
        anomalies: list[CostAnomaly],
    ) -> None:
        pct_used = float(mtd_cost / budget * 100) if budget else 0
        color = (
            "#dc3545" if pct_used > 100
            else "#ffc107" if pct_used > 80
            else "#28a745"
        )

        service_lines = "\n".join(
            f"  {svc}: ${cost:.2f}"
            for svc, cost in top_services[:5]
        )
        anomaly_lines = "\n".join(
            f"  :warning: {a.service}: ${a.actual_cost} "
            f"({a.deviation_pct:+.1f}% vs expected ${a.expected_cost})"
            for a in anomalies[:3]
        )

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f":money_with_wings: Daily Cost Report: {team}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Today:* ${daily_cost:.2f}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*MTD:* ${mtd_cost:.2f}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Budget:* ${budget:.2f}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Used:* {pct_used:.1f}%",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Top Services:*\n```{service_lines}```",
                },
            },
        ]

        if anomaly_lines:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Anomalies Detected:*\n```{anomaly_lines}```",
                },
            })

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                self.slack_webhook_url,
                json={
                    "attachments": [
                        {
                            "color": color,
                            "blocks": blocks,
                        }
                    ]
                },
            )


@dataclass
class ShowbackReport:
    """Generates showback/chargeback reports per team."""

    def generate_monthly_report(
        self,
        records: list[CostRecord],
        team: str,
    ) -> dict:
        team_records = [r for r in records if r.team == team]
        total = sum(r.cost_usd for r in team_records)

        # By service
        by_service: dict[str, Decimal] = {}
        for r in team_records:
            by_service[r.service] = by_service.get(
                r.service, Decimal("0")
            ) + r.cost_usd

        # By environment
        by_env: dict[str, Decimal] = {}
        for r in team_records:
            by_env[r.environment] = by_env.get(
                r.environment, Decimal("0")
            ) + r.cost_usd

        # By region
        by_region: dict[str, Decimal] = {}
        for r in team_records:
            by_region[r.region] = by_region.get(
                r.region, Decimal("0")
            ) + r.cost_usd

        return {
            "team": team,
            "total_cost_usd": float(total),
            "by_service": {
                k: float(v)
                for k, v in sorted(
                    by_service.items(), key=lambda x: x[1], reverse=True
                )
            },
            "by_environment": {k: float(v) for k, v in by_env.items()},
            "by_region": {k: float(v) for k, v in by_region.items()},
            "top_resources": self._top_resources(team_records, n=10),
        }

    def _top_resources(
        self, records: list[CostRecord], n: int = 10
    ) -> list[dict]:
        by_resource: dict[str, Decimal] = {}
        for r in records:
            if r.resource_id:
                by_resource[r.resource_id] = by_resource.get(
                    r.resource_id, Decimal("0")
                ) + r.cost_usd

        top = sorted(by_resource.items(), key=lambda x: x[1], reverse=True)[:n]
        return [
            {"resource_id": rid, "cost_usd": float(cost)}
            for rid, cost in top
        ]
```

| FinOps Capability | Tool / Approach | Key Metric |
|---|---|---|
| Cost visibility | AWS Cost Explorer + CUR | Total spend, daily burn |
| Attribution | Tag-based grouping | % tagged resources |
| Anomaly detection | Statistical z-score | False positive rate |
| Budget management | Monthly/quarterly budgets | % budget consumed |
| Showback | Team cost reports | Cost per service |
| Chargeback | Shared cost allocation | Unit cost per request |
| Forecasting | Linear extrapolation | Forecast accuracy |
| Optimization | Right-sizing recommendations | Savings realized |

Key patterns:

1. **Tag everything** — mandatory tags (Team, Application, Environment) on all resources enable cost attribution; untagged resources go to a shared "untagged" bucket for follow-up
2. **Anomaly detection** — use z-score analysis against 30-day baselines to catch cost spikes within hours, not at end of month
3. **Budget alerts at 80%** — warn teams when they hit 80% of monthly budget so they can take action before exceeding it
4. **Showback before chargeback** — start with visibility reports (showback) to build trust before enforcing cost accountability (chargeback)
5. **Daily cost reporting** — Slack/email digests with top services and anomalies keep cost awareness in daily workflows
6. **Untagged resource hunting** — automated scanning for untagged resources with periodic compliance reports to drive 95%+ tagging coverage
'''
    ),
    (
        "finops/right-sizing-compute",
        "Implement a compute right-sizing system that analyzes CPU, memory, and GPU utilization to recommend optimal instance types and container resource limits.",
        '''Compute right-sizing analysis and recommendation engine:

```python
# --- Resource utilization collector and analyzer ---

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import boto3

logger = logging.getLogger(__name__)


class ResourceType(str, Enum):
    EC2 = "ec2"
    RDS = "rds"
    K8S_POD = "k8s_pod"
    LAMBDA = "lambda"


class RecommendationType(str, Enum):
    DOWNSIZE = "downsize"
    UPSIZE = "upsize"
    TERMINATE = "terminate"
    CHANGE_FAMILY = "change_family"
    SPOT = "convert_to_spot"
    GRAVITON = "migrate_to_graviton"


@dataclass
class UtilizationMetrics:
    """Resource utilization over a time period."""

    resource_id: str
    resource_type: ResourceType
    instance_type: str
    team: str
    environment: str

    # CPU metrics (0-100%)
    cpu_avg: float = 0.0
    cpu_p50: float = 0.0
    cpu_p95: float = 0.0
    cpu_max: float = 0.0

    # Memory metrics (0-100%)
    memory_avg: float = 0.0
    memory_p95: float = 0.0
    memory_max: float = 0.0

    # Network (bytes/sec)
    network_in_avg: float = 0.0
    network_out_avg: float = 0.0

    # Cost
    current_hourly_cost: float = 0.0
    period_days: int = 14


@dataclass
class RightSizeRecommendation:
    """A right-sizing recommendation."""

    resource_id: str
    resource_type: ResourceType
    team: str
    current_type: str
    recommended_type: str
    recommendation: RecommendationType
    current_monthly_cost: float
    projected_monthly_cost: float
    monthly_savings: float
    savings_pct: float
    confidence: str  # "high" | "medium" | "low"
    rationale: str
    risk_notes: str


@dataclass
class EC2RightSizer:
    """Analyzes EC2 instances for right-sizing opportunities."""

    session: boto3.Session
    lookback_days: int = 14
    downsize_cpu_threshold: float = 30.0   # avg CPU < 30% -> downsize
    downsize_mem_threshold: float = 40.0   # avg mem < 40% -> downsize
    idle_cpu_threshold: float = 5.0         # avg CPU < 5%  -> terminate
    upsize_cpu_threshold: float = 80.0      # p95 CPU > 80% -> upsize

    # Instance type pricing (simplified, us-east-1 on-demand)
    INSTANCE_PRICING: dict[str, float] = field(default_factory=lambda: {
        "t3.micro": 0.0104,
        "t3.small": 0.0208,
        "t3.medium": 0.0416,
        "t3.large": 0.0832,
        "t3.xlarge": 0.1664,
        "m6i.large": 0.096,
        "m6i.xlarge": 0.192,
        "m6i.2xlarge": 0.384,
        "m6g.large": 0.077,       # Graviton — cheaper
        "m6g.xlarge": 0.154,
        "m6g.2xlarge": 0.308,
        "r6i.large": 0.126,
        "r6i.xlarge": 0.252,
        "r6g.large": 0.1008,      # Graviton
        "r6g.xlarge": 0.2016,
        "c6i.large": 0.085,
        "c6i.xlarge": 0.170,
        "c6g.large": 0.068,       # Graviton
        "c6g.xlarge": 0.136,
    })

    DOWNSIZE_MAP: dict[str, str] = field(default_factory=lambda: {
        "t3.xlarge": "t3.large",
        "t3.large": "t3.medium",
        "t3.medium": "t3.small",
        "t3.small": "t3.micro",
        "m6i.2xlarge": "m6i.xlarge",
        "m6i.xlarge": "m6i.large",
        "r6i.xlarge": "r6i.large",
        "c6i.xlarge": "c6i.large",
    })

    GRAVITON_MAP: dict[str, str] = field(default_factory=lambda: {
        "m6i.large": "m6g.large",
        "m6i.xlarge": "m6g.xlarge",
        "m6i.2xlarge": "m6g.2xlarge",
        "r6i.large": "r6g.large",
        "r6i.xlarge": "r6g.xlarge",
        "c6i.large": "c6g.large",
        "c6i.xlarge": "c6g.xlarge",
    })

    def collect_utilization(self) -> list[UtilizationMetrics]:
        """Collect CPU/memory utilization from CloudWatch."""
        ec2 = self.session.client("ec2")
        cw = self.session.client("cloudwatch")
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=self.lookback_days)

        instances = ec2.describe_instances(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        )

        metrics_list: list[UtilizationMetrics] = []
        for reservation in instances["Reservations"]:
            for inst in reservation["Instances"]:
                instance_id = inst["InstanceId"]
                instance_type = inst["InstanceType"]

                tags = {
                    t["Key"]: t["Value"]
                    for t in inst.get("Tags", [])
                }

                # Get CPU utilization
                cpu_stats = cw.get_metric_statistics(
                    Namespace="AWS/EC2",
                    MetricName="CPUUtilization",
                    Dimensions=[
                        {"Name": "InstanceId", "Value": instance_id}
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,
                    Statistics=["Average", "Maximum"],
                    ExtendedStatistics=["p50", "p95"],
                )

                cpu_points = cpu_stats.get("Datapoints", [])
                if not cpu_points:
                    continue

                cpu_avgs = [p["Average"] for p in cpu_points]
                cpu_maxes = [p["Maximum"] for p in cpu_points]

                metrics_list.append(
                    UtilizationMetrics(
                        resource_id=instance_id,
                        resource_type=ResourceType.EC2,
                        instance_type=instance_type,
                        team=tags.get("Team", "untagged"),
                        environment=tags.get("Environment", "unknown"),
                        cpu_avg=sum(cpu_avgs) / len(cpu_avgs),
                        cpu_p50=sorted(cpu_avgs)[len(cpu_avgs) // 2],
                        cpu_p95=sorted(cpu_avgs)[int(len(cpu_avgs) * 0.95)],
                        cpu_max=max(cpu_maxes),
                        current_hourly_cost=self.INSTANCE_PRICING.get(
                            instance_type, 0
                        ),
                        period_days=self.lookback_days,
                    )
                )

        logger.info(
            f"Collected utilization for {len(metrics_list)} EC2 instances"
        )
        return metrics_list

    def generate_recommendations(
        self, metrics: list[UtilizationMetrics]
    ) -> list[RightSizeRecommendation]:
        """Generate right-sizing recommendations based on utilization."""
        recommendations: list[RightSizeRecommendation] = []

        for m in metrics:
            current_monthly = m.current_hourly_cost * 730  # ~730 hours/month

            # Check for idle instances
            if m.cpu_avg < self.idle_cpu_threshold:
                recommendations.append(
                    RightSizeRecommendation(
                        resource_id=m.resource_id,
                        resource_type=m.resource_type,
                        team=m.team,
                        current_type=m.instance_type,
                        recommended_type="terminate",
                        recommendation=RecommendationType.TERMINATE,
                        current_monthly_cost=current_monthly,
                        projected_monthly_cost=0,
                        monthly_savings=current_monthly,
                        savings_pct=100.0,
                        confidence="high",
                        rationale=(
                            f"CPU avg {m.cpu_avg:.1f}% over "
                            f"{m.period_days} days — likely idle"
                        ),
                        risk_notes="Verify no scheduled jobs before terminating",
                    )
                )
                continue

            # Check for downsize opportunity
            if (
                m.cpu_avg < self.downsize_cpu_threshold
                and m.cpu_p95 < 60
            ):
                smaller = self.DOWNSIZE_MAP.get(m.instance_type)
                if smaller:
                    new_cost = self.INSTANCE_PRICING.get(smaller, 0) * 730
                    savings = current_monthly - new_cost
                    recommendations.append(
                        RightSizeRecommendation(
                            resource_id=m.resource_id,
                            resource_type=m.resource_type,
                            team=m.team,
                            current_type=m.instance_type,
                            recommended_type=smaller,
                            recommendation=RecommendationType.DOWNSIZE,
                            current_monthly_cost=current_monthly,
                            projected_monthly_cost=new_cost,
                            monthly_savings=savings,
                            savings_pct=savings / current_monthly * 100,
                            confidence="high" if m.cpu_p95 < 40 else "medium",
                            rationale=(
                                f"CPU avg {m.cpu_avg:.1f}%, p95 {m.cpu_p95:.1f}% "
                                f"— safe to downsize"
                            ),
                            risk_notes="Monitor after resize for 48h",
                        )
                    )

            # Check Graviton migration opportunity
            graviton = self.GRAVITON_MAP.get(m.instance_type)
            if graviton:
                new_cost = self.INSTANCE_PRICING.get(graviton, 0) * 730
                savings = current_monthly - new_cost
                recommendations.append(
                    RightSizeRecommendation(
                        resource_id=m.resource_id,
                        resource_type=m.resource_type,
                        team=m.team,
                        current_type=m.instance_type,
                        recommended_type=graviton,
                        recommendation=RecommendationType.GRAVITON,
                        current_monthly_cost=current_monthly,
                        projected_monthly_cost=new_cost,
                        monthly_savings=savings,
                        savings_pct=savings / current_monthly * 100,
                        confidence="medium",
                        rationale=(
                            f"Graviton ({graviton}) offers ~20% cost savings "
                            f"with comparable performance"
                        ),
                        risk_notes=(
                            "Ensure application is ARM-compatible; "
                            "test thoroughly before migration"
                        ),
                    )
                )

        # Sort by savings potential
        return sorted(
            recommendations, key=lambda r: r.monthly_savings, reverse=True
        )
```

```python
# --- Kubernetes pod right-sizing analyzer ---

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kubernetes import client, config


@dataclass
class K8sRightSizer:
    """Analyzes Kubernetes pod resource requests vs actual usage."""

    prometheus_url: str
    lookback_hours: int = 168  # 7 days

    def get_over_provisioned_pods(self) -> list[dict[str, Any]]:
        """Find pods where requests >> actual usage."""
        import httpx

        # Query Prometheus for actual CPU usage vs requests
        cpu_query = (
            'sum by (namespace, pod, container) ('
            '  rate(container_cpu_usage_seconds_total{container!=""}[5m])'
            ')'
            ' / '
            'sum by (namespace, pod, container) ('
            '  kube_pod_container_resource_requests{resource="cpu"}'
            ')'
        )
        mem_query = (
            'sum by (namespace, pod, container) ('
            '  container_memory_working_set_bytes{container!=""}'
            ')'
            ' / '
            'sum by (namespace, pod, container) ('
            '  kube_pod_container_resource_requests{resource="memory"}'
            ')'
        )

        results = []
        with httpx.Client(timeout=30.0) as http:
            for metric_name, query in [("cpu", cpu_query), ("memory", mem_query)]:
                resp = http.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={"query": query},
                )
                resp.raise_for_status()
                for result in resp.json()["data"]["result"]:
                    ratio = float(result["value"][1])
                    if ratio < 0.3:  # Using less than 30% of requested
                        results.append({
                            "namespace": result["metric"]["namespace"],
                            "pod": result["metric"]["pod"],
                            "container": result["metric"]["container"],
                            "metric": metric_name,
                            "usage_to_request_ratio": round(ratio, 3),
                            "recommendation": (
                                f"Reduce {metric_name} request by "
                                f"{(1 - ratio) * 100:.0f}%"
                            ),
                        })

        return results

    def generate_vpa_recommendations(self) -> list[dict[str, Any]]:
        """Generate VPA-style recommendations for all deployments."""
        import httpx

        recommendations = []
        with httpx.Client(timeout=30.0) as http:
            # Get p95 CPU usage over 7 days
            cpu_resp = http.get(
                f"{self.prometheus_url}/api/v1/query",
                params={
                    "query": (
                        'quantile_over_time(0.95, '
                        '  rate(container_cpu_usage_seconds_total'
                        '    {container!=""}[5m])'
                        f'[{self.lookback_hours}h:]'
                        ') by (namespace, container)'
                    )
                },
            )
            # Get p95 memory usage
            mem_resp = http.get(
                f"{self.prometheus_url}/api/v1/query",
                params={
                    "query": (
                        'quantile_over_time(0.95, '
                        '  container_memory_working_set_bytes'
                        '    {container!=""}'
                        f'[{self.lookback_hours}h:]'
                        ') by (namespace, container)'
                    )
                },
            )

            cpu_data = {
                (r["metric"]["namespace"], r["metric"]["container"]):
                float(r["value"][1])
                for r in cpu_resp.json()["data"]["result"]
            }
            mem_data = {
                (r["metric"]["namespace"], r["metric"]["container"]):
                float(r["value"][1])
                for r in mem_resp.json()["data"]["result"]
            }

            for key in cpu_data:
                ns, container = key
                cpu_p95 = cpu_data.get(key, 0)
                mem_p95 = mem_data.get(key, 0)

                # Add 20% headroom to p95
                recommended_cpu = f"{int(cpu_p95 * 1.2 * 1000)}m"
                recommended_mem = f"{int(mem_p95 * 1.2 / 1024 / 1024)}Mi"

                recommendations.append({
                    "namespace": ns,
                    "container": container,
                    "recommended_cpu_request": recommended_cpu,
                    "recommended_memory_request": recommended_mem,
                    "cpu_p95_cores": round(cpu_p95, 3),
                    "memory_p95_bytes": int(mem_p95),
                })

        return recommendations
```

| Right-Sizing Strategy | When to Apply | Typical Savings | Risk Level |
|---|---|---|---|
| Terminate idle | CPU avg < 5% for 14+ days | 100% | Medium — verify no cron jobs |
| Downsize instance | CPU avg < 30%, p95 < 60% | 30-50% | Low — easily reversible |
| Graviton migration | x86 workloads, compatible apps | 15-20% | Medium — needs testing |
| Spot instances | Stateless, fault-tolerant | 60-90% | High — interruption risk |
| Reduce K8s requests | Usage < 30% of request | 0 (frees capacity) | Low — VPA automates this |
| Savings Plans | Stable baseline workloads | 20-40% | Low — 1-3 year commitment |
| Reserved Instances | Known long-running instances | 30-60% | Medium — 1 year minimum |

Key patterns:

1. **14-day lookback minimum** — analyze at least 2 weeks of utilization data to account for weekly patterns and batch jobs
2. **p95 not max** — use p95 percentile for sizing decisions, not maximum; occasional spikes should not drive instance size
3. **Graviton-first** — ARM instances (Graviton, Ampere) offer 20%+ savings with comparable performance for most workloads
4. **VPA for Kubernetes** — use Vertical Pod Autoscaler in recommendation mode to continuously tune pod resource requests
5. **Automate implementation** — right-sizing recommendations without automated execution become stale; use IaC to apply changes
6. **Safety margins** — add 20% headroom above p95 usage for recommended sizes to handle organic growth
'''
    ),
    (
        "finops/spot-preemptible-strategies",
        "Design spot/preemptible instance strategies for production workloads, including fallback mechanisms, interruption handling, and cost-aware autoscaling.",
        '''Spot and preemptible instance strategies:

```python
# --- Spot instance management with interruption handling ---

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import boto3
import httpx

logger = logging.getLogger(__name__)


class SpotStrategy(str, Enum):
    LOWEST_PRICE = "lowest-price"
    CAPACITY_OPTIMIZED = "capacity-optimized"
    PRICE_CAPACITY_OPTIMIZED = "price-capacity-optimized"


@dataclass
class SpotConfig:
    """Configuration for spot instance fleet."""

    base_on_demand_count: int = 1  # Minimum on-demand for stability
    spot_percentage: int = 80      # Target % of fleet on spot
    instance_types: list[str] = field(default_factory=lambda: [
        "m6i.xlarge", "m6a.xlarge", "m5.xlarge", "m5a.xlarge",
        "m6g.xlarge", "m7g.xlarge",  # Graviton variants
    ])
    strategy: SpotStrategy = SpotStrategy.PRICE_CAPACITY_OPTIMIZED
    max_price_pct_of_on_demand: int = 70  # Max 70% of on-demand price
    availability_zones: list[str] = field(default_factory=lambda: [
        "us-east-1a", "us-east-1b", "us-east-1c",
    ])


@dataclass
class SpotInterruptionHandler:
    """Handles EC2 spot instance interruption notices."""

    metadata_url: str = "http://169.254.169.254/latest/meta-data"
    shutdown_callbacks: list[Callable[[], None]] = field(default_factory=list)
    _running: bool = True

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to execute before instance termination."""
        self.shutdown_callbacks.append(callback)

    def start_monitoring(self) -> None:
        """Poll for spot interruption notice (2-minute warning)."""
        logger.info("Starting spot interruption monitor")
        while self._running:
            try:
                with httpx.Client(timeout=2.0) as client:
                    # Check for interruption notice
                    resp = client.get(
                        f"{self.metadata_url}/spot/instance-action",
                        headers={
                            "X-aws-ec2-metadata-token": self._get_imds_token(
                                client
                            )
                        },
                    )
                    if resp.status_code == 200:
                        action = resp.json()
                        logger.warning(
                            f"Spot interruption notice received: "
                            f"action={action['action']}, "
                            f"time={action['time']}"
                        )
                        self._handle_interruption(action)
                        return
            except httpx.ConnectError:
                pass  # Not on EC2 or IMDS unavailable
            except Exception as e:
                logger.error(f"Error checking spot interruption: {e}")

            time.sleep(5)  # Check every 5 seconds

    def _get_imds_token(self, client: httpx.Client) -> str:
        resp = client.put(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"},
        )
        return resp.text

    def _handle_interruption(self, action: dict[str, Any]) -> None:
        """Execute graceful shutdown sequence."""
        logger.warning("Executing graceful shutdown callbacks...")

        for callback in self.shutdown_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Shutdown callback failed: {e}")

        logger.warning("All shutdown callbacks executed")

    def stop(self) -> None:
        self._running = False


@dataclass
class SpotFleetManager:
    """Manages mixed on-demand/spot fleet with fallback."""

    session: boto3.Session
    config: SpotConfig

    def create_fleet(
        self,
        launch_template_id: str,
        desired_capacity: int,
        tags: dict[str, str],
    ) -> str:
        """Create an EC2 Fleet with mixed on-demand/spot instances."""
        ec2 = self.session.client("ec2")

        on_demand_count = max(
            self.config.base_on_demand_count,
            int(desired_capacity * (100 - self.config.spot_percentage) / 100),
        )
        spot_count = desired_capacity - on_demand_count

        overrides = [
            {
                "InstanceType": itype,
                "AvailabilityZone": az,
            }
            for itype in self.config.instance_types
            for az in self.config.availability_zones
        ]

        response = ec2.create_fleet(
            Type="maintain",
            SpotOptions={
                "AllocationStrategy": self.config.strategy.value,
                "InstanceInterruptionBehavior": "terminate",
                "MaintenanceStrategies": {
                    "CapacityRebalance": {
                        "ReplacementStrategy": "launch-before-terminate",
                        "TerminationDelay": 120,  # 2 min to drain
                    }
                },
            },
            OnDemandOptions={
                "AllocationStrategy": "lowest-price",
            },
            LaunchTemplateConfigs=[
                {
                    "LaunchTemplateSpecification": {
                        "LaunchTemplateId": launch_template_id,
                        "Version": "$Latest",
                    },
                    "Overrides": overrides,
                }
            ],
            TargetCapacitySpecification={
                "TotalTargetCapacity": desired_capacity,
                "OnDemandTargetCapacity": on_demand_count,
                "SpotTargetCapacity": spot_count,
                "DefaultTargetCapacityType": "spot",
            },
            TagSpecifications=[
                {
                    "ResourceType": "fleet",
                    "Tags": [
                        {"Key": k, "Value": v}
                        for k, v in tags.items()
                    ],
                }
            ],
        )

        fleet_id = response["FleetId"]
        logger.info(
            f"Created fleet {fleet_id}: "
            f"{on_demand_count} on-demand + {spot_count} spot"
        )
        return fleet_id
```

```yaml
# --- Kubernetes Karpenter provisioner for spot-aware autoscaling ---

apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: spot-general
spec:
  template:
    metadata:
      labels:
        capacity-type: spot
        workload-type: general
    spec:
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot"]
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64", "arm64"]
        - key: karpenter.k8s.aws/instance-family
          operator: In
          values: ["m6i", "m6a", "m6g", "m7g", "c6i", "c6g"]
        - key: karpenter.k8s.aws/instance-size
          operator: In
          values: ["large", "xlarge", "2xlarge"]
      nodeClassRef:
        name: default

  # Scale down unused nodes after 30 seconds
  disruption:
    consolidationPolicy: WhenUnderutilized
    consolidateAfter: 30s
    # Expire nodes after 7 days for security patching
    expireAfter: 168h

  limits:
    cpu: 200        # Max 200 vCPUs in this pool
    memory: 400Gi

  weight: 100  # Prefer spot over on-demand

---
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: on-demand-baseline
spec:
  template:
    metadata:
      labels:
        capacity-type: on-demand
        workload-type: critical
    spec:
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
        - key: karpenter.k8s.aws/instance-family
          operator: In
          values: ["m6i", "m6g"]
        - key: karpenter.k8s.aws/instance-size
          operator: In
          values: ["large", "xlarge"]
      nodeClassRef:
        name: default
      # Taint so only critical workloads schedule here
      taints:
        - key: capacity-type
          value: on-demand
          effect: NoSchedule

  limits:
    cpu: 50
    memory: 100Gi

  weight: 10  # Less preferred than spot

---
# Pod spec that tolerates on-demand taint (critical services)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  template:
    spec:
      tolerations:
        - key: capacity-type
          value: on-demand
          effect: NoSchedule
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: capacity-type
                    operator: In
                    values: ["on-demand"]
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: payment-service
```

```python
# --- Spot price analyzer and savings calculator ---

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import boto3


@dataclass
class SpotPriceAnalyzer:
    """Analyzes spot pricing history for optimal instance selection."""

    session: boto3.Session

    def get_price_history(
        self,
        instance_types: list[str],
        availability_zones: list[str],
        days: int = 7,
    ) -> dict[str, dict[str, list[float]]]:
        """Get spot price history grouped by instance type and AZ."""
        ec2 = self.session.client("ec2")
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        prices: dict[str, dict[str, list[float]]] = {}

        paginator = ec2.get_paginator("describe_spot_price_history")
        for page in paginator.paginate(
            InstanceTypes=instance_types,
            AvailabilityZones=availability_zones,
            StartTime=start_time,
            EndTime=end_time,
            ProductDescriptions=["Linux/UNIX"],
        ):
            for record in page["SpotPriceHistory"]:
                itype = record["InstanceType"]
                az = record["AvailabilityZone"]
                price = float(record["SpotPrice"])

                prices.setdefault(itype, {}).setdefault(az, []).append(price)

        return prices

    def recommend_instances(
        self,
        instance_types: list[str],
        availability_zones: list[str],
        count: int = 3,
    ) -> list[dict[str, Any]]:
        """Recommend best instance type + AZ combinations for spot."""
        history = self.get_price_history(instance_types, availability_zones)

        scored: list[dict[str, Any]] = []
        for itype, az_prices in history.items():
            for az, prices in az_prices.items():
                if not prices:
                    continue
                avg_price = sum(prices) / len(prices)
                price_stability = (
                    1 - (max(prices) - min(prices)) / avg_price
                    if avg_price > 0
                    else 0
                )
                scored.append({
                    "instance_type": itype,
                    "availability_zone": az,
                    "avg_spot_price": round(avg_price, 4),
                    "min_price": round(min(prices), 4),
                    "max_price": round(max(prices), 4),
                    "price_stability": round(price_stability, 3),
                    "score": round(
                        price_stability * (1 / avg_price if avg_price else 0),
                        3,
                    ),
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:count]

    def calculate_savings(
        self,
        instance_type: str,
        on_demand_price: float,
        hours_per_month: int = 730,
        instance_count: int = 10,
    ) -> dict[str, float]:
        """Calculate projected spot savings vs on-demand."""
        history = self.get_price_history(
            [instance_type],
            ["us-east-1a", "us-east-1b", "us-east-1c"],
        )
        all_prices = [
            p
            for az_prices in history.get(instance_type, {}).values()
            for p in az_prices
        ]

        if not all_prices:
            return {"error": "No spot price data available"}

        avg_spot = sum(all_prices) / len(all_prices)
        monthly_on_demand = on_demand_price * hours_per_month * instance_count
        monthly_spot = avg_spot * hours_per_month * instance_count
        savings = monthly_on_demand - monthly_spot

        return {
            "on_demand_hourly": on_demand_price,
            "spot_avg_hourly": round(avg_spot, 4),
            "discount_pct": round((1 - avg_spot / on_demand_price) * 100, 1),
            "monthly_on_demand": round(monthly_on_demand, 2),
            "monthly_spot": round(monthly_spot, 2),
            "monthly_savings": round(savings, 2),
            "annual_savings": round(savings * 12, 2),
        }
```

| Strategy | Best For | Savings | Interruption Risk | Complexity |
|---|---|---|---|---|
| Spot-only fleet | Batch, CI/CD, dev | 60-90% | High | Low |
| Mixed on-demand + spot | Production stateless | 40-60% | Medium | Medium |
| Karpenter spot pools | K8s workloads | 50-70% | Medium | Low |
| Capacity-optimized alloc | Large fleets | 50-70% | Lower | Low |
| Diversified instances | All spot workloads | 40-60% | Lower | Medium |
| Savings Plans + spot | Hybrid approach | 50-80% | Varies | High |

Key patterns:

1. **Diversify instance types** — use 6+ instance types across 3+ AZs to reduce interruption probability; capacity-optimized allocation picks the deepest pools
2. **On-demand baseline** — maintain minimum on-demand capacity for critical services; spot supplements for elasticity and cost savings
3. **Graceful interruption handling** — monitor IMDS for 2-minute warning; drain connections, checkpoint state, and deregister from load balancer
4. **Capacity rebalance** — use "launch-before-terminate" strategy to proactively replace at-risk instances before actual interruption
5. **Karpenter over Cluster Autoscaler** — Karpenter's spot-aware scheduling picks optimal instance types dynamically, reducing interruptions vs static ASGs
6. **Taint critical workloads** — taint on-demand nodes and tolerate only critical services (payments, auth) to ensure they never run on spot
'''
    ),
    (
        "finops/resource-tagging-showback-chargeback",
        "Implement a comprehensive resource tagging strategy with showback/chargeback reporting that drives accountability for cloud costs across engineering teams.",
        '''Resource tagging and showback/chargeback system:

```python
# --- Tag policy enforcement engine ---

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import boto3

logger = logging.getLogger(__name__)


class TagComplianceLevel(str, Enum):
    COMPLIANT = "compliant"
    PARTIAL = "partial"
    NON_COMPLIANT = "non_compliant"


class TagAction(str, Enum):
    WARN = "warn"
    AUTO_TAG = "auto_tag"
    BLOCK = "block"
    NOTIFY_OWNER = "notify_owner"


@dataclass
class TagPolicy:
    """Defines required tags and validation rules."""

    REQUIRED_TAGS: dict[str, dict[str, Any]] = field(default_factory=lambda: {
        "Team": {
            "required": True,
            "pattern": r"^team-[a-z][a-z0-9-]{2,30}$",
            "description": "Owning team (e.g., team-payments)",
            "auto_detect": "iam_user_tag",
        },
        "Application": {
            "required": True,
            "pattern": r"^[a-z][a-z0-9-]{2,40}$",
            "description": "Application/service name",
        },
        "Environment": {
            "required": True,
            "allowed_values": ["dev", "staging", "production", "sandbox"],
            "description": "Deployment environment",
        },
        "CostCenter": {
            "required": True,
            "pattern": r"^CC-\d{4,6}$",
            "description": "Finance cost center code",
            "auto_detect": "team_mapping",
        },
        "ManagedBy": {
            "required": False,
            "allowed_values": ["terraform", "pulumi", "cloudformation", "manual"],
            "default": "manual",
        },
        "DataClassification": {
            "required": False,
            "allowed_values": ["public", "internal", "confidential", "restricted"],
            "default": "internal",
        },
    })

    TEAM_TO_COST_CENTER: dict[str, str] = field(default_factory=lambda: {
        "team-payments": "CC-1001",
        "team-platform": "CC-1002",
        "team-search": "CC-1003",
        "team-mobile": "CC-1004",
        "team-data": "CC-2001",
        "team-ml": "CC-2002",
    })

    def validate_tags(
        self, tags: dict[str, str]
    ) -> tuple[TagComplianceLevel, list[str]]:
        """Validate tags against policy, return compliance level and issues."""
        issues: list[str] = []
        required_present = 0
        required_total = 0

        for tag_key, rules in self.REQUIRED_TAGS.items():
            if rules.get("required"):
                required_total += 1

            value = tags.get(tag_key)

            if value is None:
                if rules.get("required"):
                    issues.append(f"Missing required tag: {tag_key}")
                continue

            required_present += 1

            # Validate pattern
            if "pattern" in rules:
                if not re.match(rules["pattern"], value):
                    issues.append(
                        f"Tag '{tag_key}' value '{value}' "
                        f"does not match pattern: {rules['pattern']}"
                    )

            # Validate allowed values
            if "allowed_values" in rules:
                if value not in rules["allowed_values"]:
                    issues.append(
                        f"Tag '{tag_key}' value '{value}' "
                        f"not in allowed values: {rules['allowed_values']}"
                    )

        if not issues:
            return TagComplianceLevel.COMPLIANT, []
        elif required_present >= required_total // 2:
            return TagComplianceLevel.PARTIAL, issues
        else:
            return TagComplianceLevel.NON_COMPLIANT, issues

    def suggest_auto_tags(
        self,
        existing_tags: dict[str, str],
        creator_arn: Optional[str] = None,
    ) -> dict[str, str]:
        """Suggest tags that can be auto-applied."""
        suggestions: dict[str, str] = {}

        # Auto-detect team from IAM user
        if "Team" not in existing_tags and creator_arn:
            team = self._extract_team_from_arn(creator_arn)
            if team:
                suggestions["Team"] = team

        # Auto-detect cost center from team
        team = existing_tags.get("Team") or suggestions.get("Team")
        if team and "CostCenter" not in existing_tags:
            cc = self.TEAM_TO_COST_CENTER.get(team)
            if cc:
                suggestions["CostCenter"] = cc

        # Apply defaults
        for tag_key, rules in self.REQUIRED_TAGS.items():
            if tag_key not in existing_tags and "default" in rules:
                suggestions[tag_key] = rules["default"]

        return suggestions

    def _extract_team_from_arn(self, arn: str) -> Optional[str]:
        """Extract team from IAM role/user naming convention."""
        # e.g., arn:aws:iam::123456:role/team-payments-deploy
        parts = arn.split("/")
        if len(parts) >= 2:
            role_name = parts[-1]
            for team in self.TEAM_TO_COST_CENTER:
                if role_name.startswith(team):
                    return team
        return None


@dataclass
class TagEnforcer:
    """Enforces tag policies across AWS accounts."""

    session: boto3.Session
    policy: TagPolicy
    dry_run: bool = False

    def scan_account(self) -> dict[str, Any]:
        """Scan entire account for tag compliance."""
        client = self.session.client("resourcegroupstaggingapi")
        stats = {
            "total_resources": 0,
            "compliant": 0,
            "partial": 0,
            "non_compliant": 0,
            "violations": [],
        }

        paginator = client.get_paginator("get_resources")
        for page in paginator.paginate():
            for resource in page["ResourceTagMappingList"]:
                stats["total_resources"] += 1
                tags = {
                    t["Key"]: t["Value"]
                    for t in resource.get("Tags", [])
                }
                level, issues = self.policy.validate_tags(tags)

                if level == TagComplianceLevel.COMPLIANT:
                    stats["compliant"] += 1
                elif level == TagComplianceLevel.PARTIAL:
                    stats["partial"] += 1
                    stats["violations"].append({
                        "arn": resource["ResourceARN"],
                        "level": level.value,
                        "issues": issues,
                    })
                else:
                    stats["non_compliant"] += 1
                    stats["violations"].append({
                        "arn": resource["ResourceARN"],
                        "level": level.value,
                        "issues": issues,
                    })

        stats["compliance_pct"] = round(
            stats["compliant"] / max(stats["total_resources"], 1) * 100, 1
        )
        logger.info(
            f"Tag scan complete: {stats['compliance_pct']}% compliant "
            f"({stats['compliant']}/{stats['total_resources']})"
        )
        return stats

    def auto_remediate(
        self, violations: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Auto-tag resources where possible."""
        client = self.session.client("resourcegroupstaggingapi")
        results = {"tagged": 0, "skipped": 0, "errors": 0}

        for violation in violations:
            arn = violation["arn"]
            current_tags = self._get_tags(arn)
            suggestions = self.policy.suggest_auto_tags(current_tags)

            if not suggestions:
                results["skipped"] += 1
                continue

            if self.dry_run:
                logger.info(
                    f"[DRY RUN] Would tag {arn}: {suggestions}"
                )
                results["tagged"] += 1
                continue

            try:
                client.tag_resources(
                    ResourceARNList=[arn],
                    Tags=suggestions,
                )
                results["tagged"] += 1
                logger.info(f"Auto-tagged {arn}: {suggestions}")
            except Exception as e:
                results["errors"] += 1
                logger.error(f"Failed to tag {arn}: {e}")

        return results

    def _get_tags(self, arn: str) -> dict[str, str]:
        client = self.session.client("resourcegroupstaggingapi")
        resp = client.get_resources(
            ResourceARNList=[arn],
        )
        for resource in resp.get("ResourceTagMappingList", []):
            return {
                t["Key"]: t["Value"]
                for t in resource.get("Tags", [])
            }
        return {}
```

```python
# --- Showback/chargeback report generator ---

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass
class ChargebackConfig:
    """Configuration for cost allocation rules."""

    # Shared costs allocation method
    shared_cost_split: str = "proportional"  # "even" | "proportional" | "custom"

    # Shared services to allocate across teams
    shared_services: list[str] = field(default_factory=lambda: [
        "AWS CloudTrail",
        "AWS Config",
        "Amazon GuardDuty",
        "AWS WAF",
        "Amazon Route 53",
        "AWS Key Management Service",
    ])

    # Custom allocation weights (for "custom" split)
    custom_weights: dict[str, float] = field(default_factory=dict)

    # Discount sharing — distribute RI/SP savings proportionally
    share_discounts: bool = True


@dataclass
class ShowbackChargebackEngine:
    """Generates showback and chargeback reports."""

    config: ChargebackConfig = field(default_factory=ChargebackConfig)

    def generate_chargeback(
        self,
        records: list[CostRecord],
        period_start: date,
        period_end: date,
    ) -> dict[str, Any]:
        """Generate full chargeback report with shared cost allocation."""
        # Separate direct and shared costs
        direct_costs: dict[str, Decimal] = {}
        shared_costs: Decimal = Decimal("0")
        untagged_costs: Decimal = Decimal("0")

        for r in records:
            if r.service in self.config.shared_services:
                shared_costs += r.cost_usd
            elif r.team == "untagged":
                untagged_costs += r.cost_usd
            else:
                direct_costs[r.team] = (
                    direct_costs.get(r.team, Decimal("0")) + r.cost_usd
                )

        total_direct = sum(direct_costs.values())
        teams = list(direct_costs.keys())

        # Allocate shared costs
        shared_allocation = self._allocate_shared(
            teams, direct_costs, shared_costs
        )

        # Allocate untagged costs (split evenly as penalty)
        untagged_per_team = (
            untagged_costs / len(teams) if teams else Decimal("0")
        )

        # Build team reports
        team_reports: list[dict[str, Any]] = []
        grand_total = Decimal("0")
        for team in sorted(teams):
            direct = direct_costs.get(team, Decimal("0"))
            shared = shared_allocation.get(team, Decimal("0"))
            untagged_share = untagged_per_team
            team_total = direct + shared + untagged_share
            grand_total += team_total

            team_reports.append({
                "team": team,
                "direct_costs": float(direct),
                "shared_costs": float(shared),
                "untagged_allocation": float(untagged_share),
                "total": float(team_total),
                "pct_of_total": 0.0,  # Filled in below
            })

        # Calculate percentages
        for report in team_reports:
            report["pct_of_total"] = round(
                report["total"] / float(grand_total) * 100
                if grand_total > 0
                else 0,
                1,
            )

        return {
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
            },
            "summary": {
                "total_cost": float(total_direct + shared_costs + untagged_costs),
                "direct_costs": float(total_direct),
                "shared_costs": float(shared_costs),
                "untagged_costs": float(untagged_costs),
                "num_teams": len(teams),
            },
            "teams": sorted(
                team_reports, key=lambda t: t["total"], reverse=True
            ),
        }

    def _allocate_shared(
        self,
        teams: list[str],
        direct_costs: dict[str, Decimal],
        shared_total: Decimal,
    ) -> dict[str, Decimal]:
        """Allocate shared costs to teams."""
        allocation: dict[str, Decimal] = {}

        if self.config.shared_cost_split == "even":
            per_team = shared_total / len(teams) if teams else Decimal("0")
            for team in teams:
                allocation[team] = per_team

        elif self.config.shared_cost_split == "proportional":
            total_direct = sum(direct_costs.values())
            for team in teams:
                ratio = (
                    direct_costs.get(team, Decimal("0")) / total_direct
                    if total_direct > 0
                    else Decimal("0")
                )
                allocation[team] = shared_total * ratio

        elif self.config.shared_cost_split == "custom":
            for team in teams:
                weight = Decimal(
                    str(self.config.custom_weights.get(team, 0))
                )
                allocation[team] = shared_total * weight

        return allocation

    def to_csv(self, report: dict[str, Any]) -> str:
        """Export chargeback report to CSV."""
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "Team", "Direct Costs ($)", "Shared Costs ($)",
            "Untagged Allocation ($)", "Total ($)", "% of Total",
        ])

        for team in report["teams"]:
            writer.writerow([
                team["team"],
                f"{team['direct_costs']:.2f}",
                f"{team['shared_costs']:.2f}",
                f"{team['untagged_allocation']:.2f}",
                f"{team['total']:.2f}",
                f"{team['pct_of_total']:.1f}%",
            ])

        writer.writerow([])
        writer.writerow(["Summary"])
        for key, value in report["summary"].items():
            writer.writerow([key, value])

        return output.getvalue()
```

```hcl
# --- AWS Organizations tag policy (enforced at org level) ---

resource "aws_organizations_policy" "tag_policy" {
  name        = "mandatory-cost-tags"
  description = "Enforce mandatory cost attribution tags"
  type        = "TAG_POLICY"

  content = jsonencode({
    tags = {
      Team = {
        tag_key = {
          "@@assign" = "Team"
        }
        tag_value = {
          "@@assign" = [
            "team-payments",
            "team-platform",
            "team-search",
            "team-mobile",
            "team-data",
            "team-ml"
          ]
        }
        enforced_for = {
          "@@assign" = [
            "ec2:instance",
            "ec2:volume",
            "rds:db",
            "s3:bucket",
            "elasticache:cluster",
            "lambda:function"
          ]
        }
      }
      Environment = {
        tag_key = {
          "@@assign" = "Environment"
        }
        tag_value = {
          "@@assign" = [
            "dev",
            "staging",
            "production",
            "sandbox"
          ]
        }
        enforced_for = {
          "@@assign" = [
            "ec2:instance",
            "rds:db",
            "s3:bucket"
          ]
        }
      }
      CostCenter = {
        tag_key = {
          "@@assign" = "CostCenter"
        }
      }
    }
  })
}

resource "aws_organizations_policy_attachment" "tag_policy" {
  policy_id = aws_organizations_policy.tag_policy.id
  target_id = var.engineering_ou_id
}

# --- AWS Config rule for tag compliance ---

resource "aws_config_config_rule" "required_tags" {
  name = "required-cost-tags"

  source {
    owner             = "AWS"
    source_identifier = "REQUIRED_TAGS"
  }

  input_parameters = jsonencode({
    tag1Key   = "Team"
    tag2Key   = "Application"
    tag3Key   = "Environment"
    tag4Key   = "CostCenter"
  })

  scope {
    compliance_resource_types = [
      "AWS::EC2::Instance",
      "AWS::RDS::DBInstance",
      "AWS::S3::Bucket",
      "AWS::ElastiCache::CacheCluster",
      "AWS::Lambda::Function",
    ]
  }
}
```

| Allocation Method | Description | Best For | Fairness |
|---|---|---|---|
| Direct attribution | Costs go to tagged team | Team-owned resources | High |
| Proportional shared | Split by team\'s direct spend ratio | Shared infra (VPC, DNS) | Medium |
| Even split | Equal share across all teams | Small shared costs | Low |
| Custom weights | Finance-defined allocation | Cross-BU cost sharing | High |
| Usage-based | Per-request/per-GB allocation | Shared platforms | High |
| Untagged penalty | Evenly split untagged costs | Incentivize tagging | Medium |

Key patterns:

1. **Mandatory tags via org policy** — enforce Team, Application, Environment, CostCenter at the AWS Organizations level so untaggable resources cannot be created
2. **Showback first, chargeback later** — start with visibility and team reports for 2-3 months before enforcing cost accountability to build trust
3. **Shared cost allocation** — allocate VPC, DNS, security tools proportionally based on each team\'s direct spend
4. **Untagged cost penalty** — distribute untagged costs evenly across teams to incentivize tagging compliance
5. **Auto-tagging remediation** — automatically tag resources using IAM context (role name, SSO user) when manual tags are missing
6. **Config rule compliance** — use AWS Config rules to continuously monitor tag compliance with automated reporting
'''
    ),
]
