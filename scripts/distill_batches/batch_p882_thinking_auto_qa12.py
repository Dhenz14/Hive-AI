"""Phase 4F: Self-Improvement — Quality Assurance (Part 12)

Quality checklists for monitoring/observability recommendations —
ensuring advice on monitoring, logging, and alerting is practical,
actionable, and appropriately scoped.
"""

PAIRS = [
    (
        "thinking/auto-qa-monitoring-strategy",
        r'''What quality checks should I apply when recommending a monitoring strategy? How do I ensure my observability advice is practical rather than overwhelming?''',
        r'''<think>
Monitoring advice frequently suffers from two extremes: either "just add logging" (too vague) or "implement full OpenTelemetry with distributed tracing, custom metrics, structured logging, and a Grafana dashboard for every service" (too complex for most teams).

The quality check must ensure monitoring recommendations:
1. Match the team's operational maturity
2. Focus on what actually needs monitoring
3. Provide actionable alerts, not noise
4. Are implementable with reasonable effort
</think>

**Monitoring Strategy Quality Checklist**

**Step 1: Assess operational maturity**
```
□ LEVEL 1 — No monitoring:
  Recommend: Basic health checks + error alerting
  Don't recommend: Distributed tracing, custom dashboards
  First step: "Can you tell when your app is down?"

□ LEVEL 2 — Basic monitoring exists:
  Recommend: Structured logging + key business metrics
  Don't recommend: Complex observability stack
  Next step: "Can you tell WHY your app had issues?"

□ LEVEL 3 — Good monitoring:
  Recommend: Distributed tracing + SLO-based alerting
  Appropriate: Custom dashboards, anomaly detection
  Next step: "Can you proactively prevent issues?"

□ LEVEL 4 — Mature observability:
  Recommend: Optimization, cost management, advanced analysis
  Appropriate: AIOps, chaos engineering, SLO-driven development
  Next step: "Can you optimize your reliability investment?"

Match recommendations to the current level.
Don't recommend Level 4 practices to a Level 1 team.
```

**Step 2: The three pillars check**
```
Good monitoring covers three pillars. Check that advice
addresses the appropriate pillars for the team's maturity:

PILLAR 1 — LOGS:
  □ Structured logging? (JSON, not free-text)
    Structured: {"level":"error","msg":"query failed","table":"users","duration_ms":5000}
    Unstructured: "ERROR: query failed for users table, took 5s"
    Structured logs are searchable and aggregatable.

  □ Appropriate log levels?
    ERROR: Something failed that needs attention
    WARN: Something unexpected but handled
    INFO: Significant business events
    DEBUG: Detailed flow information (off in production)

  □ Retention policy?
    How long are logs kept? (30 days is typical)
    Where are they stored? (local files rot; use a log aggregator)

PILLAR 2 — METRICS:
  □ Key metrics identified?
    RED metrics for services: Rate, Errors, Duration
    USE metrics for resources: Utilization, Saturation, Errors
    Business metrics: Signups, orders, revenue per hour

  □ Appropriate granularity?
    Too fine (per-request metrics) → expensive, noisy
    Too coarse (daily averages) → hides problems
    Good default: 1-minute resolution for operational metrics

PILLAR 3 — TRACES:
  □ Needed for this architecture?
    Monolith → traces are less critical (logs often suffice)
    Microservices → traces are essential for debugging
    Only recommend tracing when the architecture justifies it.
```

**Step 3: Alerting quality**
```
□ ACTIONABLE ALERTS ONLY:
  Every alert should have a clear action:
  "Error rate > 5% for 5 minutes → check error logs,
   identify failing endpoint, check recent deployments"

  If the response to an alert is "look at it and hope
  it resolves" → the alert is not actionable.

□ APPROPRIATE THRESHOLDS:
  Too sensitive → alert fatigue (team ignores all alerts)
  Too lenient → miss real problems

  Good approach: Start lenient, tighten based on data.
  Example: Start with "error rate > 10%" and tighten to 5%
  after a month of baseline data.

□ APPROPRIATE URGENCY:
  Page (wake someone up): Service is DOWN, data is at risk
  Notify (next business day): Degraded performance, disk filling
  Log (review weekly): Non-urgent anomalies, capacity trends

  Rule: If an alert pages someone and they can't do anything
  about it until morning → it should be a notification, not a page.

□ ALERT FATIGUE PREVENTION:
  □ No duplicate alerts for the same issue
  □ Alerts auto-resolve when the condition clears
  □ No alerts for expected events (deployments, maintenance)
  □ Track alert-to-action ratio (if < 50%, alerts are too noisy)
```

**Step 4: Dashboard design**
```
□ ONE OVERVIEW DASHBOARD:
  Shows system health at a glance.
  Anyone should understand it without training.
  Contains: Service status, error rate, request rate, latency

□ SERVICE-SPECIFIC DASHBOARDS:
  Deep dive into individual services.
  Used for debugging, not routine monitoring.
  Contains: Detailed metrics for that service only

□ BUSINESS METRICS DASHBOARD:
  Non-technical stakeholders can understand.
  Contains: Revenue, signups, active users, conversion rate

□ ANTI-PATTERNS:
  - Dashboard with 50 panels (information overload)
  - Dashboard that requires scrolling (most important info not visible)
  - Dashboard with no context (what are normal values?)
  - Dashboard that nobody looks at (delete it)
```

**Step 5: Implementation practicality**
```
□ COST-APPROPRIATE:
  Monitoring should not cost more than the service it monitors.
  Cloud monitoring costs scale with data volume.
  Log only what you'll actually use.

□ TEAM CAN OPERATE:
  Can the team set up and maintain the recommended tools?
  Self-hosted Prometheus + Grafana needs operational expertise.
  Managed services (Datadog, New Relic) cost more but need less ops.

□ INCREMENTAL ADOPTION:
  Can they start with basics and add more over time?
  Don't recommend a full observability stack on day one.
  Start: Health checks + error alerts
  Then: Structured logging + key metrics
  Then: Dashboards + SLOs
  Then: Tracing + advanced analysis
```

**The meta-principle:** The purpose of monitoring is to answer two questions: "Is everything working?" and "If not, why?" Everything in a monitoring strategy should serve one of these questions. If a metric, log, or dashboard doesn't help answer either question, it's noise. Start with the minimum monitoring that answers "is it working?" and add detail only as needed to answer "why isn't it working?"'''
    ),
    (
        "thinking/auto-qa-monitoring-logging",
        r'''What quality checks should I apply when advising on logging practices? How do I ensure logging advice is practical and leads to useful logs?''',
        r'''<think>
Logging advice frequently falls into the trap of either "log everything" (expensive, noisy, hard to search) or "just add some print statements" (insufficient for debugging). Good logging is structured, purposeful, and searchable. The quality check should ensure logging advice produces logs that are actually useful when debugging production issues.
</think>

**Logging Quality Checklist**

**What to log**
```
□ LOG BUSINESS EVENTS:
  User signed up, order placed, payment processed
  These are the events you'll need when investigating
  business-impacting issues.

□ LOG ERRORS WITH CONTEXT:
  Not just the error, but the context needed to reproduce:
  BAD:  logger.error("Query failed")
  GOOD: logger.error("Query failed", extra={
      "query": "SELECT * FROM users WHERE id = %s",
      "params": [user_id],
      "duration_ms": 5200,
      "error": str(e),
  })

□ LOG INTEGRATION BOUNDARIES:
  When calling external services, log:
  - What was requested (sanitized — no secrets)
  - What was returned (status code, timing)
  - What failed (error details)

□ LOG STATE TRANSITIONS:
  When important objects change state:
  "Order #123 transitioned from 'pending' to 'paid'"
  These are critical for debugging business logic issues.

□ DON'T LOG:
  - Sensitive data (passwords, tokens, PII without masking)
  - High-frequency routine operations (every cache hit)
  - Full request/response bodies in production (too much data)
  - Debug-level logs in production (unless temporarily enabled)
```

**How to log**
```
□ STRUCTURED FORMAT:
  Use JSON or key-value structured logging.
  Structured logs are searchable, filterable, and aggregatable.

  BAD (free text):
    "2025-01-15 10:30:00 ERROR Failed to process order 123 for user 456"

  GOOD (structured):
    {
      "timestamp": "2025-01-15T10:30:00Z",
      "level": "error",
      "message": "Failed to process order",
      "order_id": 123,
      "user_id": 456,
      "error": "insufficient_funds",
      "amount": 99.99
    }

□ CONSISTENT FIELDS:
  Use the same field names across all services:
  - request_id (for tracing a request across logs)
  - user_id (who was affected)
  - duration_ms (how long operations took)
  - error (what went wrong)

□ CORRELATION IDS:
  Include a request ID in every log line.
  This lets you trace a single request across all log entries.
  Pass the request ID between services for distributed tracing.

□ APPROPRIATE LOG LEVELS:
  ERROR: Something failed, needs investigation
  WARN: Something unexpected, handled gracefully
  INFO: Normal business operations (start, complete)
  DEBUG: Detailed technical information (off in production)

  If everything is ERROR, nothing is ERROR.
  If everything is INFO, the logs are too noisy.
```

**Where to send logs**
```
□ NOT JUST LOCAL FILES:
  Local log files are lost when the container restarts.
  Send logs to a centralized system:
  - ELK stack (Elasticsearch + Logstash + Kibana)
  - Managed: Datadog, Splunk, CloudWatch, Loki

□ RETENTION APPROPRIATE:
  Hot storage (searchable): 7-30 days
  Cold storage (archived): 90-365 days
  Compliance storage: As required by regulation

□ COST MANAGEMENT:
  Log volume directly impacts cost.
  High volume → Sample or aggregate instead of logging everything.
  Example: Log 10% of successful requests, 100% of errors.
```

**Log anti-patterns**
```
□ LOGGING SECRETS:
  Never log passwords, API keys, tokens, or session IDs.
  Use redaction: "Authorization: Bearer ****"

□ LOGGING TOO MUCH:
  If you log every database query at INFO level,
  your log volume will be enormous and expensive.
  Use DEBUG for high-frequency operations.

□ INCONSISTENT FORMAT:
  If some logs are JSON and others are free text,
  searching and parsing becomes painful.
  Standardize the format across all services.

□ NO CONTEXT:
  "Error occurred" tells you nothing.
  Always include: what, where, when, who, and why.

□ LOG AND FORGET:
  Logs exist to be READ. If nobody reads the logs,
  they serve no purpose. Set up alerts for error logs.
```

**The meta-principle:** Logs are for answering the question "what happened?" after something goes wrong. Every log entry should contribute to answering that question. If a log entry wouldn't help you debug a production issue, it shouldn't be there. If a log entry would help but is missing context, it's incomplete. Log the right things, in the right format, at the right level.'''
    ),
    (
        "thinking/auto-qa-monitoring-alerting",
        r'''What quality checks should I apply when advising on alerting rules? How do I help teams create alerts that catch real problems without causing alert fatigue?''',
        r'''<think>
Alerting is the most critical and most abused part of monitoring. Bad alerting creates alert fatigue — the team ignores all alerts because most are noise. Good alerting pages you only for problems that require human intervention, and tells you exactly what to do.

The key tension is: too few alerts means you miss problems, too many alerts means you ignore all of them. The quality check must ensure alerts are actionable, appropriately urgent, and well-tuned.
</think>

**Alerting Quality Checklist**

**Alert design principles**
```
□ EVERY ALERT HAS A RUNBOOK:
  When the alert fires, what should the responder do?
  Include:
  1. What the alert means
  2. What to check first
  3. Common causes and fixes
  4. Escalation path if the fix isn't obvious

  If you can't write a runbook for an alert,
  the alert is probably not well-defined.

□ EVERY ALERT IS ACTIONABLE:
  The responder can DO something when the alert fires.

  Actionable: "Error rate > 5% → check recent deployments,
  roll back if necessary"
  Not actionable: "CPU is at 70%" → so what? Is that bad?
  Not actionable: "Disk will be full in 30 days" → at 3 AM?

□ APPROPRIATE URGENCY:
  PAGE (immediate response needed):
  - Service is completely down
  - Data loss is occurring
  - Security breach detected
  - Error rate > threshold for > 5 minutes

  TICKET (next business day):
  - Performance degraded but functional
  - Disk approaching capacity (days/weeks away)
  - Certificate expiring in > 7 days
  - Elevated but not critical error rate

  LOG ONLY (review in weekly meeting):
  - Unusual traffic patterns
  - Non-critical dependency slowness
  - Capacity trends
```

**Alert threshold tuning**
```
□ BASELINE FIRST:
  Before setting thresholds, understand normal behavior:
  - What is the normal error rate? (baseline)
  - What is the normal response time? (p50, p95, p99)
  - What is the normal request volume? (by hour, by day)

  Alert on DEVIATION from normal, not arbitrary numbers.

□ MULTIPLE CONDITIONS:
  Avoid single-metric alerts. Combine signals:

  BAD:  Alert when CPU > 80%
  (Could be a normal traffic spike)

  GOOD: Alert when CPU > 80% AND response time p95 > 2s
  AND error rate > 2% for > 5 minutes
  (Multiple signals confirm a real problem)

□ TIME WINDOWS:
  Don't alert on instantaneous spikes:
  BAD:  Alert when error rate > 5% (any single data point)
  GOOD: Alert when error rate > 5% for > 5 minutes
  (Sustained problems are real; spikes are often transient)

□ HYSTERESIS:
  Don't alert and resolve repeatedly for borderline values:
  Alert at: error rate > 5% for 5 minutes
  Resolve at: error rate < 3% for 5 minutes
  (Different thresholds prevent flapping)
```

**Alert management**
```
□ ALERT OWNERSHIP:
  Every alert has a team or person responsible for responding.
  Unowned alerts get ignored.

□ REGULAR REVIEW:
  Monthly: Review all alerts that fired
  - Which alerts led to action? (keep these)
  - Which alerts were ignored? (tune or delete)
  - Which incidents were missed? (add new alerts)

□ ALERT FATIGUE METRICS:
  Track:
  - Alerts per day/week (should be < 5 pages per week)
  - Alert-to-action ratio (should be > 50%)
  - Time to acknowledge (increasing = fatigue)
  - Duplicate alerts per incident (should be 1)

□ SILENCING AND MAINTENANCE:
  During planned maintenance, silence affected alerts.
  After deployments, temporarily raise thresholds.
  Never permanently silence an alert — fix or delete it.
```

**SLO-based alerting**
```
The most effective alerting model is based on Service Level
Objectives (SLOs):

DEFINE YOUR SLO:
  "99.9% of requests complete successfully within 500ms"

DEFINE YOUR ERROR BUDGET:
  0.1% of requests can fail = ~43 minutes of downtime per month

ALERT WHEN BURNING ERROR BUDGET TOO FAST:
  "At current error rate, we will exhaust our monthly error
   budget in 4 hours" → PAGE

  "At current error rate, we will exhaust our monthly error
   budget in 3 days" → TICKET

  "Error budget consumption is normal" → NO ALERT

This approach:
  - Alerts on business impact, not technical metrics
  - Naturally prioritizes by severity
  - Allows controlled degradation within budget
  - Reduces noise from non-impactful issues
```

**The meta-principle:** An alert should only fire when a human needs to take action. Every alert that fires without resulting in action is training the team to ignore alerts. Invest time in tuning alerts, writing runbooks, and reviewing alert effectiveness. The goal is not to alert on everything — it is to alert on the right things at the right urgency level.'''
    ),
    (
        "thinking/auto-qa-monitoring-incident-response",
        r'''What quality checks should I apply when advising on monitoring for incident detection and response? How do I help teams detect incidents faster?''',
        r'''<think>
Incident detection through monitoring is about reducing the time between "something breaks" and "we know something is broken." The two key metrics are:
- MTTD (Mean Time to Detect): How long until we notice the problem?
- MTTR (Mean Time to Resolve): How long until we fix it?

Good monitoring minimizes MTTD. Good runbooks and procedures minimize MTTR. The quality check should ensure monitoring advice reduces both.
</think>

**Incident Detection and Response Monitoring Checklist**

**Detection speed**
```
□ SYNTHETIC MONITORING:
  Don't wait for users to report problems.
  Run automated checks that simulate user actions:
  - Health check endpoint: /health (every 30 seconds)
  - Core flow check: Login, view data, submit form (every 5 min)
  - External availability: Check from multiple regions

  Synthetic checks detect outages before users do.

□ REAL USER MONITORING (RUM):
  Measure actual user experience:
  - Page load time
  - Error rate from client perspective
  - Core Web Vitals (LCP, FID, CLS)

  Synthetic tests can pass while real users are affected
  (CDN issues, specific browser bugs, geographic problems).

□ ANOMALY DETECTION:
  Alert on significant deviations from normal:
  - Traffic drops > 30% from expected (possible outage)
  - Error rate doubles from baseline
  - Response time increases > 50% from normal

  This catches problems that fixed thresholds miss.
```

**Incident classification**
```
□ SEVERITY LEVELS:
  Define clear severity levels before incidents happen:

  SEV 1 — Critical: Service is down, data loss, security breach
    Response: Immediate, all hands, incident commander
    Communication: Status page update within 15 minutes

  SEV 2 — Major: Significant degradation, major feature broken
    Response: Within 30 minutes, primary on-call
    Communication: Status page update within 1 hour

  SEV 3 — Minor: Partial degradation, non-critical feature broken
    Response: Next business day
    Communication: Internal notification

  SEV 4 — Low: Cosmetic issues, minor inconveniences
    Response: Normal prioritization
    Communication: Bug tracker

□ AUTO-CLASSIFICATION:
  Map monitoring signals to severity levels:
  - Service completely down → SEV 1
  - Error rate > 10% for > 5 min → SEV 2
  - Error rate > 5% for > 15 min → SEV 3
  - Error rate > 2% for > 1 hour → SEV 4
```

**During-incident monitoring**
```
□ INCIDENT DASHBOARD:
  A single dashboard for active incidents showing:
  - Current error rate and trend
  - Affected services
  - Recent deployments
  - Recent configuration changes
  - Key dependency status

  This dashboard should be the first thing opened
  when an incident is declared.

□ TIMELINE TRACKING:
  During the incident, track:
  - When was the problem first detected?
  - When was the incident declared?
  - What changes were made during investigation?
  - When was the problem resolved?

  This timeline feeds post-incident review.

□ BLAST RADIUS ASSESSMENT:
  How many users are affected?
  Which features are broken?
  Is the impact growing or stable?

  Monitoring should answer these questions quickly:
  - Affected users: Track unique users hitting errors
  - Affected features: Map errors to product features
  - Impact trend: Is the error rate growing or stable?
```

**Post-incident monitoring**
```
□ POST-INCIDENT REVIEW:
  After every SEV 1 and SEV 2 incident, review:
  - What monitoring detected the issue?
  - What monitoring SHOULD have detected it earlier?
  - Were the alerts actionable?
  - Was the runbook helpful?

□ MONITORING IMPROVEMENTS:
  Every incident should result in monitoring improvements:
  - New alerts for the failure mode (if missing)
  - Better runbooks for the response (if unclear)
  - Faster detection for this category (if too slow)
  - Corrected thresholds (if existing alerts didn't fire)

□ RECURRENCE PREVENTION:
  Add specific monitoring for the root cause:
  "This outage was caused by database connection exhaustion.
   Add an alert for connections > 80% of pool size."
```

**The meta-principle:** The purpose of incident monitoring is to minimize the time between "something breaks" and "we've fixed it." Every minute of undetected downtime is a minute of user impact. Invest in detection speed (synthetic monitoring, anomaly detection) and response speed (clear severity levels, actionable runbooks, pre-built dashboards). The best incident is one detected by monitoring before any user notices.'''
    ),
    (
        "thinking/auto-qa-monitoring-cost-management",
        r'''What quality checks should I apply when advising on monitoring costs? How do I help teams balance observability coverage with monitoring expenses?''',
        r'''<think>
Monitoring costs can spiral out of control, especially with cloud-based observability platforms that charge by data volume. Teams often end up paying more for monitoring than for the infrastructure being monitored. The quality check should ensure monitoring advice considers cost as a first-class constraint.

Key cost drivers:
1. Log volume (biggest cost for most teams)
2. Metric cardinality (number of unique time series)
3. Trace sampling rate
4. Retention duration
5. Number of alerting rules and dashboards
</think>

**Monitoring Cost Management Checklist**

**Understanding cost drivers**
```
□ LOG VOLUME:
  The #1 monitoring cost for most teams.
  Calculate: Bytes per log entry x entries per second x 86,400

  Cost reduction strategies:
  - Log sampling: Log 10% of successful requests, 100% of errors
  - Log level management: DEBUG off in production
  - Reduce log verbosity: Log events, not narration
  - Drop noise: Filter out health check logs, bot traffic

  BAD: Logging every HTTP request at INFO with full headers
  GOOD: Logging errors and slow requests; sampling normal requests

□ METRIC CARDINALITY:
  Number of unique label combinations creates "cardinality explosion."
  BAD: Metric with labels {user_id, endpoint, status_code}
    1M users x 50 endpoints x 5 status codes = 250M time series

  GOOD: Metric with labels {endpoint, status_code}
    50 endpoints x 5 status codes = 250 time series

  Rule: Never use high-cardinality values (user IDs, request IDs,
  IP addresses) as metric labels. Use logs for high-cardinality data.

□ TRACE SAMPLING:
  Full tracing (100% of requests) is expensive.
  Sample intelligently:
  - 100% of errors (always capture failures)
  - 100% of slow requests (> p95 latency)
  - 1-10% of normal requests (enough for baseline)
  - 100% of specific debug sessions (temporary)
```

**Cost-appropriate monitoring tiers**
```
TIER 1 — Free/minimal cost:
  - Application health checks (built into most frameworks)
  - Error logging to files or CloudWatch
  - Basic uptime monitoring (free tier of Uptime Robot, etc.)
  - Built-in cloud provider metrics (CPU, memory, disk)
  Appropriate for: Side projects, internal tools, prototypes

TIER 2 — Moderate cost ($50-500/month):
  - Structured logging with retention (Loki, CloudWatch)
  - Application metrics (Prometheus + Grafana, free self-hosted)
  - Alerting (PagerDuty free tier, or self-hosted)
  - Basic dashboards
  Appropriate for: Small production applications, startups

TIER 3 — Significant cost ($500-5000/month):
  - Managed monitoring platform (Datadog, New Relic)
  - Full logging with 30-day retention
  - Application and infrastructure metrics
  - Distributed tracing
  - Custom dashboards and alerting
  Appropriate for: Medium production applications, growing teams

TIER 4 — Enterprise cost ($5000+/month):
  - Full observability stack with extended retention
  - AIOps and anomaly detection
  - Custom integrations
  - Compliance and audit logging
  Appropriate for: Large-scale production systems
```

**Cost optimization strategies**
```
□ RIGHT-SIZE RETENTION:
  Do you need 90 days of log retention?
  Most debugging happens within 7 days of an incident.
  Reduce hot storage retention; archive to cold storage.

□ AGGREGATE BEFORE STORING:
  Instead of storing every data point:
  - Aggregate to 1-minute resolution for recent data
  - Aggregate to 5-minute resolution for older data
  - Aggregate to 1-hour resolution for historical data

□ DROP UNUSED DATA:
  Audit monthly:
  - Which dashboards are viewed? (delete unused ones)
  - Which logs are queried? (stop collecting unqueried logs)
  - Which metrics are used in alerts? (drop unused metrics)

  If nobody looks at a metric, stop collecting it.

□ COMPARE MANAGED VS SELF-HOSTED:
  Managed (Datadog): ~$15/host/month + data costs
  Self-hosted (Prometheus+Grafana+Loki): Free software,
    but need engineering time to operate

  Small teams: Managed is usually cheaper (no ops overhead)
  Large teams: Self-hosted may be cheaper (amortized ops cost)
```

**The meta-principle:** Monitoring should cost proportionally less than the service it monitors. If monitoring costs are growing faster than the service's value, something is wrong. Log what you'll actually use, sample what you don't need completely, and regularly audit what you're paying for versus what you're using. The cheapest monitoring is the monitoring you don't need because your system is well-designed.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
