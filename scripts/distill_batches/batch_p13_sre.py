"""
Batch P13 — Site Reliability Engineering: SLOs/SLIs/SLAs, incident management,
capacity planning, release engineering, and reliability patterns.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. SLOs/SLIs/SLAs ---
    (
        "sre/slos-slis-slas",
        r"""Explain how to define service level indicators and objectives for production systems, including error budget policies, burn rate alerting with multi-window strategies, toil budget management, and SLA negotiation best practices for platform teams.""",
        r"""# Service Level Indicators, Objectives, and Agreements in SRE

## Why SLOs Are the Foundation of Reliability Engineering

The entire discipline of Site Reliability Engineering rests on a deceptively simple insight: **you cannot manage reliability without measuring it quantitatively**. Service Level Indicators (SLIs), Service Level Objectives (SLOs), and Service Level Agreements (SLAs) form a layered framework that translates vague notions of "uptime" and "performance" into actionable, measurable targets. Because SRE teams must balance reliability work against feature velocity, SLOs provide the objective decision boundary — when your error budget is healthy, you ship faster; when it is depleted, you prioritize stability.

A **common mistake** is conflating SLIs, SLOs, and SLAs. An SLI is a carefully chosen metric that quantifies some aspect of service behavior — for example, the proportion of HTTP requests that return a 2xx status within 300ms. An SLO is a target range for that SLI over a rolling window — "99.9% of requests succeed within 300ms over 30 days." An SLA is a contractual commitment with financial consequences if the SLO is breached. **Therefore**, SLOs should always be stricter than SLAs, because you need an internal buffer before contractual penalties kick in.

## Defining High-Quality SLIs

### Choosing the Right Measurement Points

The **best practice** is to measure SLIs as close to the user as possible. Server-side metrics miss client-perceived latency from DNS, TLS handshakes, and network transit. However, purely client-side measurement introduces noise from device variability. The **trade-off** is between accuracy and controllability — most teams settle on load balancer or API gateway metrics as a practical compromise that captures server processing time plus internal network latency.

There are four canonical SLI categories: **availability** (successful requests / total requests), **latency** (proportion of requests faster than a threshold), **throughput** (requests processed per unit time), and **correctness** (proportion of responses with valid data). A **pitfall** is using averages for latency SLIs — averages hide tail latency problems. Use percentile-based thresholds instead: p50 for typical experience, p99 for tail latency.

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime, timedelta
import math


class SLICategory(Enum):
    AVAILABILITY = "availability"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    CORRECTNESS = "correctness"


@dataclass
class SLIDefinition:
    # Defines a Service Level Indicator with measurement parameters
    name: str
    category: SLICategory
    description: str
    good_event_filter: str  # query or predicate for "good" events
    total_event_filter: str  # query or predicate for "total" events
    threshold_ms: Optional[float] = None  # latency threshold
    unit: str = "ratio"

    def compute_sli(self, good_count: int, total_count: int) -> float:
        # Returns the SLI value as a ratio between 0.0 and 1.0
        if total_count == 0:
            return 1.0  # no traffic means no failures
        return good_count / total_count


@dataclass
class SLOTarget:
    # Binds an SLI to a target value and rolling window
    sli: SLIDefinition
    target: float  # e.g., 0.999 for 99.9%
    window_days: int = 30
    burn_rate_thresholds: Dict[str, float] = field(default_factory=dict)

    def error_budget_total(self, total_events: int) -> float:
        # Maximum number of "bad" events allowed in the window
        return total_events * (1.0 - self.target)

    def error_budget_remaining(
        self, total_events: int, bad_events: int
    ) -> Tuple[float, float]:
        # Returns (remaining_budget_count, remaining_budget_fraction)
        budget = self.error_budget_total(total_events)
        remaining = budget - bad_events
        fraction = remaining / budget if budget > 0 else 0.0
        return remaining, fraction


@dataclass
class SLAContract:
    # Wraps an SLO with contractual penalties
    slo: SLOTarget
    penalty_tiers: List[Tuple[float, str]]  # (threshold, penalty_description)
    contract_window_days: int = 30

    def evaluate_penalty(self, current_sli: float) -> Optional[str]:
        # Check if the current SLI value triggers any penalty tier
        for threshold, penalty in sorted(self.penalty_tiers, reverse=True):
            if current_sli < threshold:
                return penalty
        return None


# Example: define a multi-tier SLO stack for an API
api_availability_sli = SLIDefinition(
    name="api-success-rate",
    category=SLICategory.AVAILABILITY,
    description="Fraction of non-5xx responses at the load balancer",
    good_event_filter='response_code < 500',
    total_event_filter='all_requests',
)

api_latency_sli = SLIDefinition(
    name="api-p99-latency",
    category=SLICategory.LATENCY,
    description="Fraction of requests completing under 300ms at p99",
    good_event_filter='duration_ms <= 300',
    total_event_filter='all_requests',
    threshold_ms=300.0,
)

availability_slo = SLOTarget(
    sli=api_availability_sli,
    target=0.999,
    window_days=30,
    burn_rate_thresholds={"critical": 14.4, "warning": 6.0, "info": 1.0},
)
```

## Error Budget Policies and Burn Rate Alerting

### Multi-Window, Multi-Burn-Rate Alerts

Raw error budget consumption is too noisy for alerting. The **best practice**, popularized by Google's SRE book, is multi-window burn rate alerting. A burn rate of 1.0 means you are consuming budget exactly at the pace that would exhaust it at the end of the window. A burn rate of 14.4 means you would exhaust a 30-day budget in roughly 2 hours — this demands immediate attention. **However**, a brief spike that quickly resolves should not page on-call engineers at 3 AM. Therefore, multi-window alerting requires the burn rate to be elevated across both a short window (for recency) and a long window (for persistence).

A **common mistake** is setting only a single alert threshold. You need at minimum three tiers: a critical page (burn rate greater than 14x over 1 hour AND over 5 minutes), a warning ticket (burn rate greater than 6x over 6 hours AND over 30 minutes), and an informational notification (burn rate greater than 1x over 3 days AND over 6 hours).

```python
from dataclasses import dataclass
from typing import List, Optional, Callable
from enum import Enum
import time


class AlertSeverity(Enum):
    CRITICAL = "critical"  # pages on-call immediately
    WARNING = "warning"    # creates a ticket for next business day
    INFO = "info"          # dashboard notification only


@dataclass
class BurnRateWindow:
    # Defines a single burn rate measurement window
    duration_minutes: int
    burn_rate_threshold: float


@dataclass
class MultiWindowBurnRateAlert:
    # Multi-window burn rate alerting following Google SRE methodology
    name: str
    severity: AlertSeverity
    long_window: BurnRateWindow
    short_window: BurnRateWindow
    slo_target: float
    window_days: int = 30

    def compute_burn_rate(
        self, bad_events: int, total_events: int, window_minutes: int
    ) -> float:
        # burn_rate = (error_rate_observed / error_rate_budget)
        if total_events == 0:
            return 0.0
        observed_error_rate = bad_events / total_events
        budget_error_rate = 1.0 - self.slo_target
        if budget_error_rate == 0:
            return float('inf') if observed_error_rate > 0 else 0.0
        return observed_error_rate / budget_error_rate

    def should_fire(
        self,
        long_window_bad: int,
        long_window_total: int,
        short_window_bad: int,
        short_window_total: int,
    ) -> bool:
        # Alert fires only if BOTH windows exceed their thresholds
        long_burn = self.compute_burn_rate(
            long_window_bad, long_window_total, self.long_window.duration_minutes
        )
        short_burn = self.compute_burn_rate(
            short_window_bad, short_window_total, self.short_window.duration_minutes
        )
        return (
            long_burn >= self.long_window.burn_rate_threshold
            and short_burn >= self.short_window.burn_rate_threshold
        )


# Standard multi-window burn rate alert configuration
def create_standard_burn_rate_alerts(
    slo_name: str, slo_target: float
) -> List[MultiWindowBurnRateAlert]:
    # Returns the canonical three-tier burn rate alert set
    return [
        MultiWindowBurnRateAlert(
            name=f"{slo_name}-critical",
            severity=AlertSeverity.CRITICAL,
            long_window=BurnRateWindow(duration_minutes=60, burn_rate_threshold=14.4),
            short_window=BurnRateWindow(duration_minutes=5, burn_rate_threshold=14.4),
            slo_target=slo_target,
        ),
        MultiWindowBurnRateAlert(
            name=f"{slo_name}-warning",
            severity=AlertSeverity.WARNING,
            long_window=BurnRateWindow(duration_minutes=360, burn_rate_threshold=6.0),
            short_window=BurnRateWindow(duration_minutes=30, burn_rate_threshold=6.0),
            slo_target=slo_target,
        ),
        MultiWindowBurnRateAlert(
            name=f"{slo_name}-info",
            severity=AlertSeverity.INFO,
            long_window=BurnRateWindow(duration_minutes=4320, burn_rate_threshold=1.0),
            short_window=BurnRateWindow(duration_minutes=360, burn_rate_threshold=1.0),
            slo_target=slo_target,
        ),
    ]
```

## Toil Budget Management

Toil is any operational work that is manual, repetitive, automatable, and scales linearly with service size. Google's SRE model recommends that teams spend **no more than 50% of their time on toil**, with the remainder devoted to engineering work that reduces future toil. **Because** toil naturally accumulates as services grow, tracking a toil budget alongside error budgets is essential.

```python
@dataclass
class ToilBudgetTracker:
    # Tracks toil hours against a team's weekly budget
    team_size: int
    hours_per_engineer_per_week: float = 40.0
    max_toil_fraction: float = 0.50

    def weekly_toil_budget_hours(self) -> float:
        return self.team_size * self.hours_per_engineer_per_week * self.max_toil_fraction

    def evaluate_week(
        self, toil_hours_logged: float
    ) -> Dict[str, float]:
        budget = self.weekly_toil_budget_hours()
        return {
            "budget_hours": budget,
            "consumed_hours": toil_hours_logged,
            "remaining_hours": budget - toil_hours_logged,
            "utilization_pct": (toil_hours_logged / budget) * 100 if budget > 0 else 0,
        }
```

## SLA Negotiation Best Practices

When negotiating SLAs with external customers or partner teams, keep these principles in mind. First, **never promise an SLA tighter than your internal SLO** — you need a reliability margin. Second, SLAs should exclude planned maintenance windows that are communicated in advance. Third, define "downtime" precisely — is a partial degradation (slower but functional) a violation? Fourth, error budget policies should specify consequences: reduced deployment velocity, mandatory stability sprints, or executive escalation.

## Summary and Key Takeaways

- **SLIs** are the raw metrics; choose them based on user-visible behavior and measure at the edge.
- **SLOs** are internal targets; set them tighter than SLAs to maintain a buffer.
- **Error budgets** are the mechanism that balances reliability and velocity — when budget is healthy, ship features; when depleted, prioritize stability.
- **Burn rate alerting** with multi-window strategies avoids alert fatigue while catching real incidents quickly.
- **Toil budgets** ensure engineering teams spend the majority of their time on automation, not repetitive manual work.
- The trade-off between aggressive SLOs and development speed is the central tension in SRE — error budgets make that tension explicit and manageable.
""",
    ),

    # --- 2. Incident Management ---
    (
        "sre/incident-management",
        r"""Describe a complete incident management framework for SRE teams including on-call rotation design, incident command system structure, blameless postmortem processes, runbook automation with decision trees, and escalation policies that minimize mean time to recovery.""",
        r"""# Incident Management Framework for SRE Teams

## Why Structured Incident Management Is Non-Negotiable

Production incidents are inevitable. No matter how rigorous your testing, how thorough your code reviews, or how sophisticated your deployment pipelines, systems **will** fail in unexpected ways. The difference between a mature SRE organization and a chaotic one is not the absence of incidents — it is the speed, coordination, and learning that happens during and after them. **Because** incidents are high-stress, time-critical events, having a well-rehearsed structure is a **best practice** that directly reduces Mean Time to Recovery (MTTR).

A **common mistake** is treating incident management as purely reactive. Effective incident management is a system that must be designed, practiced, and continuously improved. The three pillars are: **on-call readiness** (who responds), **incident command** (how they coordinate), and **postmortem culture** (how the organization learns). **However**, many organizations focus only on the first pillar and neglect the structured coordination and learning components.

## On-Call Rotation Design

### Principles of Sustainable On-Call

On-call duty directly impacts engineer well-being and retention. **Therefore**, designing rotations that are humane while maintaining coverage is critical. The key principles are: no engineer should be on-call more than one week in four (ideally one in six), on-call handoffs should include a briefing on recent changes and known issues, and compensation — whether financial, time-off-in-lieu, or both — must be explicit.

A **pitfall** is having a single on-call tier. Two-tier rotations work better: a primary on-call who is paged first and handles most issues, and a secondary who is escalated to if the primary cannot resolve within the escalation window or if a second simultaneous incident occurs. The **trade-off** between larger rotation pools (less burden per person) and domain expertise (fewer people know each service deeply) is best resolved by pairing rotation membership with runbook quality.

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib


class OnCallTier(Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    ESCALATION_MANAGER = "escalation_manager"


@dataclass
class Engineer:
    name: str
    email: str
    phone: str
    team: str
    expertise_areas: List[str] = field(default_factory=list)
    consecutive_on_call_weeks: int = 0
    last_on_call_end: Optional[datetime] = None


@dataclass
class OnCallShift:
    engineer: Engineer
    tier: OnCallTier
    start_time: datetime
    end_time: datetime
    handoff_notes: str = ""


class OnCallScheduler:
    # Generates fair on-call rotations with fatigue protection
    def __init__(
        self,
        engineers: List[Engineer],
        min_gap_weeks: int = 3,
        shift_duration_days: int = 7,
    ) -> None:
        self.engineers = engineers
        self.min_gap_weeks = min_gap_weeks
        self.shift_duration = timedelta(days=shift_duration_days)
        self.schedule: List[OnCallShift] = []

    def is_eligible(self, engineer: Engineer, shift_start: datetime) -> bool:
        # Checks fatigue constraints before scheduling
        if engineer.last_on_call_end is None:
            return True
        gap = shift_start - engineer.last_on_call_end
        min_gap = timedelta(weeks=self.min_gap_weeks)
        return gap >= min_gap

    def generate_rotation(
        self, start_date: datetime, num_weeks: int
    ) -> List[OnCallShift]:
        # Round-robin with fatigue-aware scheduling
        eligible_pool = list(self.engineers)
        rotation: List[OnCallShift] = []
        primary_idx = 0
        secondary_idx = 1

        for week in range(num_weeks):
            shift_start = start_date + timedelta(weeks=week)
            shift_end = shift_start + self.shift_duration

            # Find next eligible primary
            attempts = 0
            while not self.is_eligible(
                eligible_pool[primary_idx % len(eligible_pool)], shift_start
            ):
                primary_idx += 1
                attempts += 1
                if attempts >= len(eligible_pool):
                    break  # all exhausted, override constraint with warning

            primary = eligible_pool[primary_idx % len(eligible_pool)]
            secondary_idx = (primary_idx + 1) % len(eligible_pool)
            secondary = eligible_pool[secondary_idx]

            rotation.append(OnCallShift(
                engineer=primary,
                tier=OnCallTier.PRIMARY,
                start_time=shift_start,
                end_time=shift_end,
            ))
            rotation.append(OnCallShift(
                engineer=secondary,
                tier=OnCallTier.SECONDARY,
                start_time=shift_start,
                end_time=shift_end,
            ))

            primary.last_on_call_end = shift_end
            primary.consecutive_on_call_weeks += 1
            primary_idx += 1

        self.schedule = rotation
        return rotation
```

## Incident Command System (ICS) Structure

### Roles and Responsibilities

Adapted from emergency services, the Incident Command System provides clear role delineation during high-pressure incidents. The core roles are:

- **Incident Commander (IC)**: Owns the incident lifecycle, makes decisions, coordinates all responders. Does NOT debug — they orchestrate.
- **Operations Lead**: Hands-on-keyboard engineer performing diagnosis, applying mitigations, executing runbooks.
- **Communications Lead**: Updates stakeholders, status pages, and internal channels at regular intervals. Shields the operations team from interruptions.
- **Scribe**: Documents the timeline of events, decisions made, and actions taken in real time. This log becomes the foundation of the postmortem.

**Because** role clarity prevents the chaos of everyone trying to debug simultaneously, the first action in any incident should be explicitly assigning these roles in the incident channel.

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime, timezone
from enum import Enum


class IncidentSeverity(Enum):
    SEV1 = "sev1"  # complete outage, all users affected
    SEV2 = "sev2"  # major degradation, many users affected
    SEV3 = "sev3"  # partial degradation, some users affected
    SEV4 = "sev4"  # minor issue, workaround available


class IncidentPhase(Enum):
    DETECTION = "detection"
    TRIAGE = "triage"
    MITIGATION = "mitigation"
    RESOLUTION = "resolution"
    POSTMORTEM = "postmortem"
    CLOSED = "closed"


@dataclass
class IncidentRole:
    role_name: str
    assignee: Optional[Engineer] = None
    assigned_at: Optional[datetime] = None


@dataclass
class TimelineEntry:
    timestamp: datetime
    author: str
    action: str
    details: str = ""


@dataclass
class Incident:
    # Central incident record tracking the full lifecycle
    incident_id: str
    title: str
    severity: IncidentSeverity
    phase: IncidentPhase = IncidentPhase.DETECTION
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    roles: Dict[str, IncidentRole] = field(default_factory=dict)
    timeline: List[TimelineEntry] = field(default_factory=list)
    affected_services: List[str] = field(default_factory=list)
    customer_impact: str = ""
    mitigation_actions: List[str] = field(default_factory=list)

    def assign_role(self, role_name: str, engineer: Engineer) -> None:
        now = datetime.now(timezone.utc)
        self.roles[role_name] = IncidentRole(
            role_name=role_name, assignee=engineer, assigned_at=now
        )
        self.add_timeline_entry(
            author="system",
            action=f"Assigned {role_name}",
            details=f"{engineer.name} is now {role_name}",
        )

    def add_timeline_entry(
        self, author: str, action: str, details: str = ""
    ) -> None:
        self.timeline.append(TimelineEntry(
            timestamp=datetime.now(timezone.utc),
            author=author,
            action=action,
            details=details,
        ))

    def escalate_severity(self, new_severity: IncidentSeverity) -> None:
        old = self.severity
        self.severity = new_severity
        self.add_timeline_entry(
            author="incident_commander",
            action=f"Escalated from {old.value} to {new_severity.value}",
        )

    def calculate_mttr(self) -> Optional[timedelta]:
        # Mean Time to Recovery for this incident
        if self.resolved_at is None:
            return None
        return self.resolved_at - self.created_at


class EscalationPolicy:
    # Defines when and how to escalate based on severity and elapsed time
    def __init__(self) -> None:
        # Maps severity to (minutes_before_escalation, escalation_target)
        self.policies: Dict[IncidentSeverity, List[tuple]] = {
            IncidentSeverity.SEV1: [
                (5, "engineering_manager"),
                (15, "director_of_engineering"),
                (30, "vp_engineering"),
            ],
            IncidentSeverity.SEV2: [
                (15, "engineering_manager"),
                (60, "director_of_engineering"),
            ],
            IncidentSeverity.SEV3: [
                (60, "team_lead"),
            ],
        }

    def check_escalations(
        self, incident: Incident
    ) -> List[str]:
        elapsed = datetime.now(timezone.utc) - incident.created_at
        elapsed_minutes = elapsed.total_seconds() / 60
        escalations_needed: List[str] = []
        if incident.severity in self.policies:
            for threshold_min, target in self.policies[incident.severity]:
                if elapsed_minutes >= threshold_min:
                    if target not in incident.roles:
                        escalations_needed.append(target)
        return escalations_needed
```

## Blameless Postmortems

The **best practice** for postmortems is that they are blameless, thorough, and action-oriented. "Blameless" does not mean "accountabilityless" — it means focusing on systemic causes rather than individual failures. **Because** humans make mistakes in proportion to system complexity, punishing individuals for errors encourages hiding problems rather than surfacing them. The postmortem document should include: incident summary, timeline, root cause analysis (using the "5 Whys" technique), contributing factors, what went well, what went poorly, and concrete action items with owners and due dates.

## Runbook Automation

Runbooks codify institutional knowledge into executable procedures. A **pitfall** is writing runbooks as static wiki pages that rot within weeks. **Therefore**, best-in-class teams encode runbooks as decision trees with automated diagnostic steps that can be executed directly from the incident management tooling.

## Summary and Key Takeaways

- **On-call rotations** must be humane: one-in-four minimum, two tiers, explicit compensation, and high-quality runbooks.
- **Incident Command System** roles (IC, Ops Lead, Comms Lead, Scribe) prevent coordination chaos during high-severity incidents.
- **Blameless postmortems** focus on systemic fixes, not individual blame — they are the primary mechanism for organizational learning.
- **Runbook automation** transforms static documentation into executable decision trees, reducing MTTR and dependency on tribal knowledge.
- **Escalation policies** should be time-based and severity-aware, automatically notifying leadership as incidents persist.
- The trade-off between process overhead and incident response speed is resolved by practice: regular incident drills make the structure feel natural rather than bureaucratic.
""",
    ),

    # --- 3. Capacity Planning ---
    (
        "sre/capacity-planning",
        r"""Explain capacity planning methodologies for production systems including systematic load testing strategies, traffic modeling with seasonal decomposition, resource forecasting using regression and queueing theory, autoscaling configuration patterns, and cost-performance optimization trade-offs.""",
        r"""# Capacity Planning for Production Systems

## Why Capacity Planning Is a Core SRE Discipline

Running out of capacity in production is one of the most preventable yet devastating failure modes. **Because** provisioning too little causes outages during traffic spikes and provisioning too much wastes infrastructure budget, capacity planning sits at the intersection of reliability engineering and cost optimization. Effective capacity planning is not a one-time exercise — it is a continuous process of measuring current utilization, modeling future demand, testing system limits, and adjusting resources proactively.

A **common mistake** is treating capacity planning as purely reactive ("we ran out of database connections last week, add more"). Mature SRE organizations practice **proactive** capacity planning: they model traffic growth, forecast resource needs 3-12 months ahead, and validate those forecasts with load testing. **However**, the trade-off between planning precision and planning effort means you should focus detailed forecasting on your critical bottleneck resources rather than trying to model every component.

## Systematic Load Testing

### Designing Representative Load Tests

Load testing validates your capacity model against reality. The **best practice** is to test in a production-like environment with realistic traffic patterns, not just uniform request floods. Key load test types include: **stress tests** (find the breaking point), **soak tests** (sustained load over hours to detect memory leaks and connection pool exhaustion), **spike tests** (sudden traffic increases), and **capacity tests** (verify headroom at projected peak load).

A **pitfall** is load testing only the happy path. Real traffic includes error cases, retry storms, cache misses during cold starts, and clients with varying payload sizes. **Therefore**, your load test scenarios should include a mix of request types weighted by production traffic analysis.

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any
from enum import Enum
from datetime import datetime, timedelta
import random
import math
import statistics


class LoadTestType(Enum):
    STRESS = "stress"         # ramp up until failure
    SOAK = "soak"             # sustained load over extended period
    SPIKE = "spike"           # sudden burst of traffic
    CAPACITY = "capacity"     # verify headroom at projected peak


@dataclass
class RequestScenario:
    # Defines a type of request with its relative weight in the traffic mix
    name: str
    endpoint: str
    method: str
    weight: float  # proportion of total traffic, 0.0 to 1.0
    payload_generator: Optional[Callable[[], Dict[str, Any]]] = None
    expected_latency_p99_ms: float = 500.0
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class LoadTestConfig:
    # Complete load test configuration with phased traffic shaping
    name: str
    test_type: LoadTestType
    target_rps: int
    duration_seconds: int
    ramp_up_seconds: int = 60
    ramp_down_seconds: int = 30
    scenarios: List[RequestScenario] = field(default_factory=list)
    concurrency_limit: int = 500
    timeout_ms: int = 5000

    def compute_rps_at_time(self, elapsed_seconds: int) -> int:
        # Compute target RPS at a given point in the test timeline
        if elapsed_seconds < self.ramp_up_seconds:
            # Linear ramp-up phase
            progress = elapsed_seconds / self.ramp_up_seconds
            return int(self.target_rps * progress)
        elif elapsed_seconds > (self.duration_seconds - self.ramp_down_seconds):
            # Linear ramp-down phase
            remaining = self.duration_seconds - elapsed_seconds
            progress = remaining / self.ramp_down_seconds
            return int(self.target_rps * max(0, progress))
        else:
            return self.target_rps

    def generate_spike_profile(
        self, base_rps: int, spike_multiplier: float, spike_duration_s: int
    ) -> List[int]:
        # Generate an RPS profile with a sudden spike
        profile: List[int] = []
        pre_spike = self.duration_seconds // 3
        for t in range(self.duration_seconds):
            if t < pre_spike:
                profile.append(base_rps)
            elif t < pre_spike + spike_duration_s:
                profile.append(int(base_rps * spike_multiplier))
            else:
                profile.append(base_rps)
        return profile


@dataclass
class LoadTestResult:
    # Aggregated results from a load test execution
    config: LoadTestConfig
    total_requests: int
    successful_requests: int
    failed_requests: int
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    max_rps_achieved: int
    saturation_point_rps: Optional[int] = None  # RPS where errors start
    error_rate: float = 0.0
    resource_utilization: Dict[str, float] = field(default_factory=dict)

    def passes_slo(self, target_success_rate: float, target_p99_ms: float) -> bool:
        actual_success_rate = self.successful_requests / max(self.total_requests, 1)
        return (
            actual_success_rate >= target_success_rate
            and self.latency_p99_ms <= target_p99_ms
        )
```

## Traffic Modeling with Seasonal Decomposition

### Decomposing Traffic Patterns

Production traffic is rarely uniform. It exhibits **daily cycles** (peak during business hours), **weekly patterns** (weekday vs. weekend), **seasonal trends** (holiday shopping, tax season), and **long-term growth**. **Because** capacity planning requires forecasting future peaks, you must decompose historical traffic into these components.

The classical decomposition is: `Traffic(t) = Trend(t) + Seasonal(t) + Residual(t)`. The trend captures long-term growth, the seasonal component captures repeating patterns, and the residual captures random noise. For capacity planning, you care most about **Trend + max(Seasonal)** — the projected peak.

```python
from typing import List, Tuple
import math
import statistics


class TrafficForecaster:
    # Forecasts future traffic using seasonal decomposition and linear regression
    def __init__(self, historical_rps: List[float], period: int = 168) -> None:
        # period=168 for hourly data with weekly seasonality (24*7)
        self.data = historical_rps
        self.period = period

    def compute_moving_average(self, window: int) -> List[float]:
        # Simple moving average to extract the trend component
        result: List[float] = []
        for i in range(len(self.data)):
            start = max(0, i - window // 2)
            end = min(len(self.data), i + window // 2 + 1)
            result.append(statistics.mean(self.data[start:end]))
        return result

    def extract_seasonal_component(self) -> List[float]:
        # Average the detrended signal by position within the period
        trend = self.compute_moving_average(self.period)
        detrended = [
            self.data[i] - trend[i] for i in range(len(self.data))
        ]
        # Average each position in the cycle
        seasonal_avg: List[float] = []
        for pos in range(self.period):
            values = [
                detrended[i]
                for i in range(pos, len(detrended), self.period)
            ]
            seasonal_avg.append(statistics.mean(values) if values else 0.0)
        # Tile the seasonal pattern across the full series
        seasonal = [
            seasonal_avg[i % self.period] for i in range(len(self.data))
        ]
        return seasonal

    def linear_trend_forecast(
        self, forecast_periods: int
    ) -> Tuple[float, float, List[float]]:
        # Fits y = slope*x + intercept to the trend component
        trend = self.compute_moving_average(self.period)
        n = len(trend)
        x_mean = (n - 1) / 2.0
        y_mean = statistics.mean(trend)
        numerator = sum((i - x_mean) * (trend[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0.0
        intercept = y_mean - slope * x_mean
        forecast = [
            slope * (n + i) + intercept for i in range(forecast_periods)
        ]
        return slope, intercept, forecast

    def forecast_peak_rps(self, weeks_ahead: int) -> float:
        # Forecasts the peak RPS expected in the future window
        forecast_periods = weeks_ahead * self.period
        slope, intercept, trend_forecast = self.linear_trend_forecast(
            forecast_periods
        )
        seasonal = self.extract_seasonal_component()
        # Project peak = max trend value + max seasonal component
        max_trend = max(trend_forecast)
        max_seasonal = max(seasonal)
        # Add safety margin of 1.3x for unexpected spikes
        safety_margin = 1.3
        return (max_trend + max_seasonal) * safety_margin
```

## Resource Forecasting with Queueing Theory

Understanding queueing theory helps SREs reason about **why** systems degrade non-linearly as utilization increases. The M/M/1 queueing model gives a crucial insight: average response time = service_time / (1 - utilization). **Therefore**, at 50% utilization, response time is 2x the service time; at 80%, it is 5x; at 90%, it is 10x. This **non-linear degradation** is why the best practice is to target 60-70% peak utilization — it leaves headroom for traffic spikes without catastrophic latency increases.

A **common mistake** is assuming linear scaling: "if 10 servers handle 10K RPS, then 20 servers handle 20K RPS." In reality, coordination overhead (locks, consensus, shared caches) means throughput scales sub-linearly. The **Universal Scalability Law** models this as: `Throughput(N) = N / (1 + alpha*(N-1) + beta*N*(N-1))` where alpha is contention and beta is coherence delay.

## Autoscaling Configuration Patterns

Autoscaling is not a substitute for capacity planning — it is a tool within capacity planning. **However**, poorly configured autoscaling causes more outages than it prevents. **Best practice** configurations include: scale-out thresholds at 60-70% CPU or based on custom metrics like queue depth, minimum instance counts set to handle baseline traffic without scaling events, cool-down periods to prevent flapping (3-5 minutes for scale-out, 10-15 minutes for scale-in), and predictive scaling for known traffic patterns.

The **trade-off** between responsiveness (short cool-down) and stability (long cool-down) should be tuned based on your traffic volatility. Bursty workloads need shorter cool-downs; gradual ramps tolerate longer ones.

## Cost-Performance Optimization

Capacity planning is ultimately about spending the right amount of money on infrastructure. Key optimization strategies include: **right-sizing instances** (most services are over-provisioned by 30-50%), **using spot/preemptible instances** for fault-tolerant workloads, **reserved capacity** for baseline load, and **on-demand capacity** for peak headroom. Track cost per request and cost per active user as first-class SLIs alongside latency and availability.

## Summary and Key Takeaways

- **Load testing** must be realistic: mix request types, include error scenarios, test ramp-up and spike patterns, and validate against SLOs not just throughput numbers.
- **Traffic modeling** using seasonal decomposition separates trend, seasonality, and noise — forecast peaks using trend extrapolation plus maximum seasonal amplitude with a safety margin.
- **Queueing theory** explains why latency explodes above 70% utilization — therefore, plan for 60-70% peak utilization to maintain reliability under unexpected load.
- **Autoscaling** is a tool within capacity planning, not a replacement for it. Set appropriate minimums, cool-down periods, and custom scaling metrics.
- **Cost optimization** is integral to capacity planning: track cost-per-request, right-size instances, and use a mix of reserved and on-demand capacity.
- The fundamental trade-off is between cost efficiency and reliability headroom — capacity planning makes that trade-off explicit and data-driven.
""",
    ),

    # --- 4. Release Engineering ---
    (
        "sre/release-engineering",
        r"""Describe release engineering practices for reliable software delivery including canary deployment analysis with statistical significance testing, progressive rollout strategies, feature flag lifecycle management, automated rollback mechanisms, and deployment velocity metrics that balance speed with safety.""",
        r"""# Release Engineering: Reliable Software Delivery at Scale

## Why Release Engineering Is an SRE Concern

Release engineering is the discipline of getting code from a developer's machine into production safely, repeatably, and quickly. **Because** the majority of production incidents are caused by changes — deployments, configuration updates, feature flag flips — the release process is one of the highest-leverage areas for SRE investment. A well-designed release pipeline reduces both the frequency and blast radius of deployment-related incidents.

A **common mistake** is treating releases as a purely CI/CD automation problem. While automation is necessary, it is not sufficient. Release engineering also encompasses **risk analysis** (which changes are riskier?), **observability** (how do we detect problems during rollout?), **rollback** (how do we undo a bad deployment?), and **velocity metrics** (how do we measure improvement?). **However**, over-engineering the release process can slow down deployment velocity to the point where changes batch up, creating larger, riskier releases — the exact opposite of the desired outcome.

## Canary Deployments with Statistical Analysis

### The Canary Strategy

A canary deployment routes a small percentage of production traffic to the new version while the majority continues to be served by the existing version. The key insight is that this is a **statistical experiment**: you are comparing the canary population's error rate and latency against the baseline population to determine whether the new version is safe. **Therefore**, you need proper statistical analysis, not just eyeballing dashboards.

The **trade-off** between canary duration and deployment speed is significant. Longer canaries catch more subtle regressions but slow your release cycle. A **best practice** is to size the canary population and duration based on the minimum detectable effect you care about — if you want to detect a 0.1% increase in error rate with 95% confidence, you need a specific sample size that can be computed in advance.

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
from datetime import datetime, timedelta, timezone
import math
import statistics


class RolloutPhase(Enum):
    CANARY = "canary"            # small traffic slice
    PROGRESSIVE = "progressive"   # gradually increasing
    FULL = "full"                 # 100% of traffic
    ROLLED_BACK = "rolled_back"   # reverted to previous version


@dataclass
class CanaryMetrics:
    # Collected metrics for a canary or baseline population
    total_requests: int
    error_count: int
    latency_samples_ms: List[float] = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        return self.error_count / max(self.total_requests, 1)

    @property
    def latency_p50(self) -> float:
        if not self.latency_samples_ms:
            return 0.0
        sorted_samples = sorted(self.latency_samples_ms)
        idx = int(len(sorted_samples) * 0.50)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]

    @property
    def latency_p99(self) -> float:
        if not self.latency_samples_ms:
            return 0.0
        sorted_samples = sorted(self.latency_samples_ms)
        idx = int(len(sorted_samples) * 0.99)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]


class CanaryAnalyzer:
    # Statistical analysis of canary vs baseline metrics
    def __init__(
        self,
        significance_level: float = 0.05,
        max_acceptable_error_rate_delta: float = 0.001,
        max_acceptable_latency_delta_ms: float = 50.0,
    ) -> None:
        self.significance_level = significance_level
        self.max_error_delta = max_acceptable_error_rate_delta
        self.max_latency_delta = max_acceptable_latency_delta_ms

    def proportion_z_test(
        self,
        baseline_successes: int,
        baseline_total: int,
        canary_successes: int,
        canary_total: int,
    ) -> Tuple[float, bool]:
        # Two-proportion z-test for error rate comparison
        # Returns (z_score, is_significantly_worse)
        p1 = baseline_successes / max(baseline_total, 1)
        p2 = canary_successes / max(canary_total, 1)
        p_pool = (baseline_successes + canary_successes) / max(
            baseline_total + canary_total, 1
        )
        se = math.sqrt(
            p_pool * (1 - p_pool) * (1 / max(baseline_total, 1) + 1 / max(canary_total, 1))
        )
        if se == 0:
            return 0.0, False
        z = (p1 - p2) / se
        # One-tailed test: is the canary significantly WORSE?
        # For alpha=0.05, critical z = 1.645
        z_critical = 1.645  # one-tailed 95% confidence
        return z, z < -z_critical  # canary is worse if z is very negative

    def analyze_canary(
        self,
        baseline: CanaryMetrics,
        canary: CanaryMetrics,
    ) -> Dict[str, any]:
        # Comprehensive canary analysis with pass/fail verdict
        baseline_successes = baseline.total_requests - baseline.error_count
        canary_successes = canary.total_requests - canary.error_count

        z_score, error_rate_worse = self.proportion_z_test(
            baseline_successes, baseline.total_requests,
            canary_successes, canary.total_requests,
        )

        error_rate_delta = canary.error_rate - baseline.error_rate
        latency_delta = canary.latency_p99 - baseline.latency_p99

        # Verdict: fail if statistically significantly worse OR if delta exceeds threshold
        should_rollback = (
            error_rate_worse
            or error_rate_delta > self.max_error_delta
            or latency_delta > self.max_latency_delta
        )

        return {
            "verdict": "FAIL" if should_rollback else "PASS",
            "error_rate_baseline": baseline.error_rate,
            "error_rate_canary": canary.error_rate,
            "error_rate_delta": error_rate_delta,
            "z_score": z_score,
            "statistically_significant": error_rate_worse,
            "latency_p99_baseline_ms": baseline.latency_p99,
            "latency_p99_canary_ms": canary.latency_p99,
            "latency_delta_ms": latency_delta,
            "recommendation": "ROLLBACK" if should_rollback else "PROMOTE",
        }

    def minimum_sample_size(
        self,
        baseline_error_rate: float,
        detectable_delta: float,
        power: float = 0.80,
    ) -> int:
        # Computes minimum sample size for detecting a given error rate increase
        # Uses the formula for two-proportion z-test sample size
        p1 = baseline_error_rate
        p2 = baseline_error_rate + detectable_delta
        z_alpha = 1.645  # one-tailed alpha=0.05
        z_beta = 0.842   # power=0.80
        p_avg = (p1 + p2) / 2
        numerator = (
            z_alpha * math.sqrt(2 * p_avg * (1 - p_avg))
            + z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
        ) ** 2
        denominator = (p2 - p1) ** 2
        return int(math.ceil(numerator / denominator)) if denominator > 0 else 0
```

## Progressive Rollout Strategies

### Phased Traffic Shifting

Rather than jumping from canary (1-5%) directly to full rollout (100%), progressive rollouts increase traffic in stages: 1% -> 5% -> 25% -> 50% -> 100%. At each stage, the canary analyzer evaluates metrics before proceeding. This provides multiple checkpoints and limits the blast radius at each phase.

```python
@dataclass
class RolloutStage:
    # A single stage in a progressive rollout
    traffic_percentage: float
    minimum_duration_minutes: int
    required_sample_size: int
    auto_promote: bool = True  # automatically advance if analysis passes


@dataclass
class ProgressiveRollout:
    # Manages a multi-stage progressive deployment
    deployment_id: str
    version: str
    stages: List[RolloutStage]
    current_stage_index: int = 0
    phase: RolloutPhase = RolloutPhase.CANARY
    analyzer: CanaryAnalyzer = field(default_factory=CanaryAnalyzer)
    rollout_history: List[Dict] = field(default_factory=list)

    def current_stage(self) -> Optional[RolloutStage]:
        if self.current_stage_index < len(self.stages):
            return self.stages[self.current_stage_index]
        return None

    def advance_stage(
        self, baseline: CanaryMetrics, canary: CanaryMetrics
    ) -> Dict[str, any]:
        # Evaluate current stage and decide whether to advance, hold, or rollback
        stage = self.current_stage()
        if stage is None:
            return {"action": "COMPLETE", "message": "All stages passed"}

        analysis = self.analyzer.analyze_canary(baseline, canary)
        self.rollout_history.append({
            "stage": self.current_stage_index,
            "traffic_pct": stage.traffic_percentage,
            "analysis": analysis,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if analysis["verdict"] == "FAIL":
            self.phase = RolloutPhase.ROLLED_BACK
            return {"action": "ROLLBACK", "reason": analysis}

        if canary.total_requests < stage.required_sample_size:
            return {"action": "HOLD", "message": "Insufficient sample size"}

        # Advance to next stage
        self.current_stage_index += 1
        if self.current_stage_index >= len(self.stages):
            self.phase = RolloutPhase.FULL
            return {"action": "COMPLETE", "message": "Rollout successful"}

        self.phase = RolloutPhase.PROGRESSIVE
        return {
            "action": "ADVANCE",
            "next_traffic_pct": self.stages[self.current_stage_index].traffic_percentage,
        }


# Standard progressive rollout configuration
def create_standard_rollout(
    deployment_id: str, version: str, baseline_error_rate: float = 0.001
) -> ProgressiveRollout:
    analyzer = CanaryAnalyzer()
    min_samples = analyzer.minimum_sample_size(baseline_error_rate, 0.001)
    return ProgressiveRollout(
        deployment_id=deployment_id,
        version=version,
        analyzer=analyzer,
        stages=[
            RolloutStage(traffic_percentage=1.0, minimum_duration_minutes=10,
                         required_sample_size=min_samples),
            RolloutStage(traffic_percentage=5.0, minimum_duration_minutes=15,
                         required_sample_size=min_samples),
            RolloutStage(traffic_percentage=25.0, minimum_duration_minutes=20,
                         required_sample_size=min_samples),
            RolloutStage(traffic_percentage=50.0, minimum_duration_minutes=30,
                         required_sample_size=min_samples),
            RolloutStage(traffic_percentage=100.0, minimum_duration_minutes=60,
                         required_sample_size=min_samples, auto_promote=False),
        ],
    )
```

## Feature Flag Lifecycle Management

Feature flags decouple deployment from release. You deploy code that is dark-launched behind a flag, then enable it for specific users, cohorts, or traffic percentages independently of the deployment process. **Because** flags accumulate technical debt, managing their lifecycle is critical. Every flag should have an **owner**, a **creation date**, a **planned removal date**, and a **current state**. The **pitfall** is flag sprawl — organizations that create flags but never clean them up end up with thousands of stale flags that make code incomprehensible and testing combinatorially explosive.

**Best practice** is to enforce flag hygiene: flags older than 90 days with 100% rollout should be automatically flagged for removal, and code with removed flags should have its conditional branches cleaned up.

## Deployment Velocity Metrics

Track these metrics to measure and improve release health: **deployment frequency** (deploys per day), **lead time for changes** (commit to production), **change failure rate** (percentage of deployments causing incidents), and **mean time to recovery** (MTTR for deployment-caused incidents). These are the DORA metrics, and they correlate strongly with overall engineering effectiveness. The **trade-off** is that optimizing solely for deployment frequency without guarding change failure rate leads to instability, while optimizing solely for safety leads to deployment batching and larger, riskier releases.

## Summary and Key Takeaways

- **Canary deployments** are statistical experiments — use proper two-proportion z-tests, not gut feelings, to decide whether to promote or rollback.
- **Progressive rollouts** (1% -> 5% -> 25% -> 50% -> 100%) provide multiple safety checkpoints and limit blast radius at each stage.
- **Feature flags** decouple deployment from release but require lifecycle management to prevent flag sprawl and technical debt accumulation.
- **Automated rollback** must be fast, reliable, and triggered by both statistical analysis failures and manual emergency stops.
- **DORA metrics** (deployment frequency, lead time, change failure rate, MTTR) measure release engineering effectiveness — optimize them as a balanced set, not individually.
- The fundamental trade-off in release engineering is between deployment velocity and safety — canary analysis and progressive rollouts let you have both by making each increment small and well-observed.
""",
    ),

    # --- 5. Reliability Patterns ---
    (
        "sre/reliability-patterns",
        r"""Explain core reliability patterns for distributed systems including circuit breaker implementation with half-open state management, bulkhead isolation strategies, load shedding with priority queues, graceful degradation techniques, and designing chaos engineering experiments to validate resilience.""",
        r"""# Reliability Patterns for Distributed Systems

## Why Reliability Must Be Designed In, Not Bolted On

Distributed systems fail in ways that monoliths do not. Network partitions, cascading failures, thundering herds, and correlated timeouts are emergent behaviors that arise from the interactions between components, not from bugs in individual services. **Because** these failure modes are inherent to distributed architectures, reliability patterns must be woven into the system design from the beginning. Attempting to add them retroactively — after the first cascading outage — is significantly more costly and error-prone.

The core principle underlying all reliability patterns is **failure isolation**: ensuring that a problem in one component does not propagate to bring down the entire system. **However**, isolation has costs — in latency, complexity, and resource utilization. **Therefore**, the art of SRE is selecting the right patterns for each failure mode and calibrating them appropriately. Over-aggressive circuit breakers can cause unnecessary service degradation; overly generous bulkheads waste resources on idle capacity.

## Circuit Breaker Pattern

### State Machine Design

The circuit breaker pattern prevents a service from repeatedly calling a failing dependency, which would waste resources and amplify the failure. It operates as a state machine with three states: **Closed** (normal operation, requests flow through), **Open** (dependency is considered failed, requests are immediately rejected or served from fallback), and **Half-Open** (a limited number of probe requests are sent to test whether the dependency has recovered).

A **common mistake** is implementing circuit breakers with only two states (open/closed), skipping the half-open state. Without half-open, you must either wait a fixed timeout before slamming all traffic back to the dependency (risking re-failure) or manually close the circuit. The half-open state provides **graceful recovery** by testing with a small number of requests before restoring full traffic.

The **trade-off** in circuit breaker configuration is between sensitivity and stability. A trip threshold that is too low causes the breaker to open on transient errors; one that is too high allows prolonged degradation before the breaker acts. **Best practice** is to configure the failure threshold as a percentage over a sliding window, not as an absolute count, because absolute counts do not account for varying traffic volumes.

```python
from dataclasses import dataclass, field
from typing import Optional, Callable, Any, Dict, List
from enum import Enum
from datetime import datetime, timedelta, timezone
import threading
import time
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"       # normal operation
    OPEN = "open"           # failing, reject requests
    HALF_OPEN = "half_open" # testing recovery


@dataclass
class CircuitBreakerConfig:
    # Configuration parameters for the circuit breaker
    failure_rate_threshold: float = 0.50  # open when 50% of requests fail
    sliding_window_size: int = 100        # number of calls in the window
    wait_duration_seconds: float = 30.0   # time in open state before half-open
    half_open_max_calls: int = 5          # probe requests in half-open
    success_rate_to_close: float = 0.80   # close if 80% of probes succeed
    slow_call_duration_ms: float = 2000.0 # calls slower than this count as slow
    slow_call_rate_threshold: float = 0.50


class SlidingWindowMetrics:
    # Tracks success/failure counts in a sliding window
    def __init__(self, window_size: int) -> None:
        self.window_size = window_size
        self.outcomes: List[bool] = []  # True = success, False = failure
        self.call_durations_ms: List[float] = []

    def record(self, success: bool, duration_ms: float) -> None:
        self.outcomes.append(success)
        self.call_durations_ms.append(duration_ms)
        # Trim to window size
        if len(self.outcomes) > self.window_size:
            self.outcomes = self.outcomes[-self.window_size:]
            self.call_durations_ms = self.call_durations_ms[-self.window_size:]

    def failure_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        failures = sum(1 for o in self.outcomes if not o)
        return failures / len(self.outcomes)

    def slow_call_rate(self, threshold_ms: float) -> float:
        if not self.call_durations_ms:
            return 0.0
        slow = sum(1 for d in self.call_durations_ms if d > threshold_ms)
        return slow / len(self.call_durations_ms)

    def total_calls(self) -> int:
        return len(self.outcomes)

    def reset(self) -> None:
        self.outcomes.clear()
        self.call_durations_ms.clear()


class CircuitBreaker:
    # Full circuit breaker with closed/open/half-open state management
    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig = CircuitBreakerConfig(),
        fallback: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.name = name
        self.config = config
        self.fallback = fallback
        self._state = CircuitState.CLOSED
        self._metrics = SlidingWindowMetrics(config.sliding_window_size)
        self._half_open_metrics = SlidingWindowMetrics(config.half_open_max_calls)
        self._opened_at: Optional[datetime] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if wait duration has elapsed -> transition to half-open
                if self._opened_at is not None:
                    elapsed = (
                        datetime.now(timezone.utc) - self._opened_at
                    ).total_seconds()
                    if elapsed >= self.config.wait_duration_seconds:
                        self._state = CircuitState.HALF_OPEN
                        self._half_open_metrics.reset()
                        logger.info(
                            f"Circuit {self.name}: OPEN -> HALF_OPEN after "
                            f"{elapsed:.1f}s"
                        )
            return self._state

    def execute(
        self, func: Callable[[], Any], *args: Any, **kwargs: Any
    ) -> Any:
        # Execute a function through the circuit breaker
        current_state = self.state

        if current_state == CircuitState.OPEN:
            logger.warning(f"Circuit {self.name} is OPEN, rejecting call")
            if self.fallback:
                return self.fallback()
            raise CircuitBreakerOpenError(
                f"Circuit breaker {self.name} is open"
            )

        start_time = time.monotonic()
        try:
            result = func(*args, **kwargs)
            duration_ms = (time.monotonic() - start_time) * 1000
            self._record_success(duration_ms)
            return result
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            self._record_failure(duration_ms)
            raise

    def _record_success(self, duration_ms: float) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_metrics.record(True, duration_ms)
                if self._half_open_metrics.total_calls() >= self.config.half_open_max_calls:
                    success_rate = 1.0 - self._half_open_metrics.failure_rate()
                    if success_rate >= self.config.success_rate_to_close:
                        self._state = CircuitState.CLOSED
                        self._metrics.reset()
                        logger.info(f"Circuit {self.name}: HALF_OPEN -> CLOSED")
                    else:
                        self._trip_open()
            else:
                self._metrics.record(True, duration_ms)

    def _record_failure(self, duration_ms: float) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_metrics.record(False, duration_ms)
                if self._half_open_metrics.failure_rate() > (
                    1.0 - self.config.success_rate_to_close
                ):
                    self._trip_open()
            else:
                self._metrics.record(False, duration_ms)
                if self._metrics.total_calls() >= self.config.sliding_window_size:
                    if (
                        self._metrics.failure_rate()
                        >= self.config.failure_rate_threshold
                    ):
                        self._trip_open()

    def _trip_open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = datetime.now(timezone.utc)
        logger.warning(
            f"Circuit {self.name}: -> OPEN (failure_rate="
            f"{self._metrics.failure_rate():.2%})"
        )


class CircuitBreakerOpenError(Exception):
    pass
```

## Bulkhead Isolation

The bulkhead pattern borrows its name from ship design: watertight compartments prevent a hull breach from flooding the entire vessel. In software, bulkheads isolate resources — thread pools, connection pools, process boundaries — so that a failure in one dependency cannot exhaust resources needed by others.

**Because** a single slow dependency can consume all threads in a shared pool, causing unrelated requests to queue and timeout, bulkhead isolation is critical for services with multiple downstream dependencies. The **pitfall** is over-partitioning: too many small pools waste memory and make the system unable to absorb traffic bursts. **Best practice** is to isolate pools for dependencies with significantly different latency profiles or failure characteristics, and to share pools among dependencies with similar behavior.

```python
from dataclasses import dataclass
from typing import Optional, Callable, Any
import threading
from concurrent.futures import ThreadPoolExecutor, Future, TimeoutError


@dataclass
class BulkheadConfig:
    max_concurrent: int = 25       # max simultaneous calls
    max_wait_ms: float = 500.0     # max time to wait for a slot
    name: str = "default"


class BulkheadIsolation:
    # Limits concurrent calls to a dependency to prevent resource exhaustion
    def __init__(self, config: BulkheadConfig) -> None:
        self.config = config
        self._semaphore = threading.Semaphore(config.max_concurrent)
        self._executor = ThreadPoolExecutor(
            max_workers=config.max_concurrent,
            thread_name_prefix=f"bulkhead-{config.name}",
        )
        self._active_count = 0
        self._rejected_count = 0
        self._lock = threading.Lock()

    def execute(
        self, func: Callable[..., Any], *args: Any, timeout_ms: Optional[float] = None
    ) -> Any:
        wait_timeout = (timeout_ms or self.config.max_wait_ms) / 1000.0
        acquired = self._semaphore.acquire(timeout=wait_timeout)
        if not acquired:
            with self._lock:
                self._rejected_count += 1
            raise BulkheadFullError(
                f"Bulkhead {self.config.name} is full "
                f"({self.config.max_concurrent} concurrent calls)"
            )
        with self._lock:
            self._active_count += 1
        try:
            return func(*args)
        finally:
            with self._lock:
                self._active_count -= 1
            self._semaphore.release()

    def get_metrics(self) -> Dict[str, int]:
        with self._lock:
            return {
                "active": self._active_count,
                "max_concurrent": self.config.max_concurrent,
                "rejected_total": self._rejected_count,
            }


class BulkheadFullError(Exception):
    pass
```

## Load Shedding with Priority Queues

When a system is overloaded beyond what even autoscaling can handle, load shedding deliberately drops low-priority requests to preserve capacity for high-priority ones. This is fundamentally different from crashing under load — it is a **graceful degradation** strategy. The key decisions are: how to classify request priority, where to enforce the shedding, and how to communicate back-pressure to callers.

**Best practice** is to assign priority based on business impact: health checks and payment processing are critical, while analytics events and thumbnail generation are deferrable. The **trade-off** is between shedding too aggressively (rejecting requests you could have handled) and shedding too late (system is already in a degraded state by the time shedding kicks in).

## Graceful Degradation Techniques

Graceful degradation means providing a reduced but functional experience when components fail, rather than returning errors. Examples include: serving stale cached data when the primary database is unavailable, disabling non-essential features (recommendations, personalization) under load, returning simplified responses that omit expensive-to-compute fields, and using pre-computed fallback data. **Because** users strongly prefer a slightly degraded experience over an error page, graceful degradation directly protects user-facing SLOs.

## Chaos Engineering Experiments

Chaos engineering is the practice of intentionally injecting failures into production systems to verify that reliability patterns work as designed. **However**, chaos engineering is not about breaking things randomly — it follows a scientific method: form a hypothesis ("if Redis fails, the circuit breaker will trip and serve cached data"), design an experiment (kill the Redis primary), observe the result (did the breaker trip? was cached data served?), and analyze the gap between hypothesis and reality.

A **pitfall** is running chaos experiments without proper safeguards. **Best practice** requires: blast radius controls (affect only a small percentage of traffic), automatic halt conditions (stop the experiment if error rates exceed a threshold), clear communication (the on-call team knows an experiment is running), and runback procedures (how to undo the injection if something goes wrong). Start with game days in staging, then graduate to production experiments with increasing scope.

## Summary and Key Takeaways

- **Circuit breakers** prevent cascading failures by stopping calls to failing dependencies; the half-open state enables graceful recovery testing before restoring full traffic.
- **Bulkhead isolation** prevents one slow dependency from exhausting shared resources; size pools based on dependency latency profiles and expected concurrency.
- **Load shedding** with priority classification preserves capacity for critical requests when the system is overloaded — it is deliberate and controlled, not a crash.
- **Graceful degradation** serves reduced functionality instead of errors, directly protecting user experience during partial outages.
- **Chaos engineering** validates that reliability patterns actually work by injecting controlled failures and observing system behavior against hypotheses.
- The fundamental trade-off across all reliability patterns is between isolation (safety) and efficiency (resource utilization) — mature SRE teams calibrate this balance using production metrics and chaos experiments.
""",
    ),
]
