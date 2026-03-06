"""Phase 2D: Advanced Reasoning — Multi-Perspective Analysis (Part 7/8)"""

PAIRS = [
    (
        "thinking/multiperspective-technical-debt-payoff",
        "We have significant technical debt — a legacy ORM wrapper, three different authentication mechanisms, and duplicated business logic across services. Leadership wants a roadmap for paying it down while still shipping features. How do we prioritize?",
        r'''<think>
Technical debt prioritization — let me analyze from multiple perspectives.

**Developer perspective:**
Want to fix everything at once. "Just give us 3 months to rewrite." But this rarely works because:
- Business can't stop for 3 months
- Rewrites take longer than estimated (2-3x)
- New bugs introduced during rewrite
- Context lost during the rewrite ("why was this edge case handled this way?")

**Product/business perspective:**
Every sprint spent on tech debt = features not shipped. They want to see ROI:
- "How does fixing auth save us money?"
- "Will cleaning up the ORM make us ship faster?"
- They need metrics, not feelings.

**Engineering manager perspective:**
Need a framework that's defensible to leadership:
- Quantify the cost of the debt (developer time wasted, incidents caused)
- Show the payback period (invest X weeks, save Y hours per sprint)
- Integrate debt paydown INTO feature work, not separate from it

**Customer perspective:**
Tech debt is invisible until it causes:
- Bugs (inconsistent auth = security incidents)
- Slow features (duplicated logic = implement everything twice)
- Outages (legacy ORM = fragile queries)

**The prioritization framework:**
Score each debt item on:
1. PAIN: How much time/incidents does this cause per sprint?
2. RISK: What's the probability of a catastrophic failure?
3. COUPLING: How much other work is blocked or slowed by this?
4. EFFORT: How many developer-weeks to fix?
5. ROI = (PAIN + RISK + COUPLING) / EFFORT

Fix the highest ROI items first.
</think>

Here's a framework that leadership can buy into because it's ROI-driven, not feeling-driven.

## Step 1: Quantify Each Debt Item

| Debt Item | Pain (hrs/sprint wasted) | Risk (incident probability) | Coupling (features blocked) | Fix Effort (weeks) |
|-----------|------------------------|-----------------------------|----------------------------|-------------------|
| 3 auth mechanisms | 8 hrs (debugging which auth, edge cases) | HIGH (security inconsistency) | Every new endpoint touches auth | 6 weeks |
| Legacy ORM wrapper | 4 hrs (working around bugs) | MEDIUM (fragile queries) | New models harder to add | 8 weeks |
| Duplicated business logic | 12 hrs (change in 3 places) | HIGH (logic divergence = data bugs) | Every business rule change | 4 weeks |

## Step 2: Calculate ROI

```
ROI = (Pain per sprint × sprints per year + Risk cost) / Fix effort

Duplicated business logic:
  Pain: 12 hrs/sprint × 26 sprints = 312 hrs/year = ~8 developer-weeks
  Risk: 2 data bugs/year × 20 hrs incident response = 40 hrs
  Fix effort: 4 weeks
  ROI: (8 + 1) / 4 = 2.25x payback in first year ← FIX FIRST

3 auth mechanisms:
  Pain: 8 hrs/sprint × 26 sprints = 208 hrs/year = ~5 developer-weeks
  Risk: 1 security incident/year × 80 hrs response = 80 hrs = 2 weeks
  Fix effort: 6 weeks
  ROI: (5 + 2) / 6 = 1.17x payback ← FIX SECOND

Legacy ORM:
  Pain: 4 hrs/sprint × 26 = 104 hrs = ~2.6 weeks
  Risk: moderate
  Fix effort: 8 weeks
  ROI: ~0.4x payback ← LOW PRIORITY (or incremental)
```

## Step 3: The "20% Rule" Roadmap

Don't ask for dedicated debt sprints. Instead:

```markdown
## Technical Debt Paydown Policy

- 20% of each sprint is allocated to tech debt (non-negotiable)
- 5-person team × 2-week sprint = 10 person-days × 20% = 2 person-days/sprint
- That's ~52 person-days/year = 10 developer-weeks of debt paydown

### Quarter 1: Fix Duplicated Business Logic (highest ROI)
Sprint 1-2: Identify all duplicated logic, create shared service layer
Sprint 3-4: Migrate Service A to shared layer
Sprint 5-6: Migrate Services B and C, delete duplicates

### Quarter 2: Unify Authentication (high risk)
Sprint 7-8: Design unified auth, implement for new endpoints
Sprint 9-10: Migrate existing endpoints to unified auth
Sprint 11-12: Remove legacy auth mechanisms, security audit

### Quarter 3-4: ORM Modernization (incremental)
No big rewrite. When touching any code that uses the legacy ORM:
- Refactor that specific query to use the modern ORM
- "Boy Scout Rule": leave the code better than you found it
- Over 6 months, most active code migrates naturally
```

## How to Present This to Leadership

```markdown
## Technical Debt Investment Proposal

### The Problem (in business terms)
Our team wastes 24 developer-hours per sprint on technical debt:
- 12 hrs changing duplicated business logic in 3 places
- 8 hrs debugging authentication edge cases
- 4 hrs working around ORM limitations

That's $125,000/year in wasted developer time.

### The Proposal
Invest 20% of sprint capacity (2 developer-days/sprint) in
targeted debt reduction.

### Expected ROI
- Q1: Fix duplicated logic → save 12 hrs/sprint → $62K/year savings
- Q2: Unify auth → save 8 hrs/sprint → $42K/year savings
- Q3: Eliminate #1 source of data bugs (currently ~2/quarter)

### What We're NOT Doing
- No "stop the world" rewrite (features keep shipping)
- No new infrastructure (no new tools or services to maintain)
- No speculative refactoring (only fixing measured pain points)

### Success Metrics
- Developer hours lost to tech debt: 24/sprint → <8/sprint by Q3
- Data consistency bugs: 2/quarter → 0/quarter by Q2
- Auth-related incidents: 1/quarter → 0 by Q3
```

The key: frame tech debt as a business cost with measurable ROI, not a developer preference. Leadership approves investments that show returns.'''
    ),
    (
        "thinking/multiperspective-database-choice",
        "We're building a new feature that needs to store user activity events — clicks, page views, API calls, etc. Expected volume is 50 million events per day. Someone wants PostgreSQL, another wants MongoDB, a third suggests ClickHouse. How do we decide?",
        r'''<think>
Event storage at 50M events/day. Let me analyze each option from multiple perspectives.

**Scale perspective:**
50M events/day = ~580 events/second average, with peaks probably 3-5x = ~2000 events/second.
This is moderate scale. All three databases can handle this with proper setup.

**Write pattern perspective:**
Events are:
- Append-only (no updates)
- Time-ordered
- Potentially varying schema (different event types have different fields)
- High volume, individual events are small

This favors write-optimized databases.

**Query pattern perspective:**
What do they want to DO with these events?
- Dashboard aggregations? ("How many page views today?" "What's the top API endpoint?")
- User journey analysis? ("Show me everything user X did yesterday")
- Real-time alerting? ("Alert if error rate > 5% in last 5 minutes")
- Ad-hoc analysis? ("Which features are most used by enterprise customers?")

This is the KEY differentiator between the databases.

**PostgreSQL perspective:**
Pros:
- Team likely knows it
- ACID transactions (overkill for events)
- Rich query language
- Good for moderate scale

Cons:
- Not designed for analytical queries on large datasets
- 50M rows/day = 18B rows/year — PostgreSQL will struggle with aggregations
- Table bloat, VACUUM issues at this scale
- Need partitioning, which adds complexity

Confidence: 30% — works for now but will be painful at scale.

**MongoDB perspective:**
Pros:
- Flexible schema (good for varying event types)
- Easy to get started
- Sharding for horizontal scale
- TTL indexes for automatic data expiration

Cons:
- Aggregation pipeline is complex for analytical queries
- Memory-hungry
- Not great for time-series data specifically
- No columnar storage → slow full-table scans

Confidence: 40% — reasonable but not ideal for analytics.

**ClickHouse perspective:**
Pros:
- Designed for exactly this use case (analytics on event data)
- Columnar storage → insanely fast aggregations
- Compression → 50M events/day stored very efficiently
- Handles billions of rows without breaking a sweat
- SQL interface (familiar)

Cons:
- Not great for point queries ("get event by ID")
- No true UPDATE/DELETE (eventually consistent)
- Smaller ecosystem, fewer developers know it
- Operational complexity (MergeTree, replication)

Confidence: 75% — this is what ClickHouse was built for.

**But wait — what about a simpler option?**
For 50M events/day, TimescaleDB (PostgreSQL extension) might give them the best of both worlds: PostgreSQL compatibility + time-series optimizations.

Confidence in TimescaleDB: 70% — strong contender if they want to stay in PostgreSQL ecosystem.
</think>

The answer depends on what you DO with the events after storing them. Here's the analysis:

## Decision Matrix

| Factor | PostgreSQL | MongoDB | ClickHouse | TimescaleDB |
|--------|-----------|---------|------------|-------------|
| Write speed (50M/day) | Adequate | Good | Excellent | Good |
| Analytical queries | Slow at scale | Moderate | Excellent | Good |
| Point queries (single event) | Excellent | Good | Poor | Good |
| Team familiarity | Likely high | Moderate | Likely low | High (it's PG) |
| Schema flexibility | Moderate (JSONB) | Excellent | Good | Moderate |
| Storage efficiency | Poor (row-based) | Moderate | Excellent (columnar) | Good |
| Operational complexity | Low | Moderate | High | Low |

## My Recommendation by Use Case

### If primary use is dashboards/analytics (75% confident → ClickHouse)

```sql
-- ClickHouse: query 1 billion events in < 1 second
-- "How many page views per hour, by country, last 30 days?"

CREATE TABLE events (
    event_type String,
    user_id UInt64,
    timestamp DateTime,
    properties String,  -- JSON
    country LowCardinality(String),
    device LowCardinality(String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (event_type, timestamp);

-- This query scans 1.5 billion rows in 200ms:
SELECT
    toStartOfHour(timestamp) AS hour,
    country,
    count() AS views
FROM events
WHERE event_type = 'page_view'
  AND timestamp >= now() - INTERVAL 30 DAY
GROUP BY hour, country
ORDER BY hour DESC;
```

**Why ClickHouse:** Columnar storage means aggregation queries only read the columns they need. Scanning 1B rows takes seconds, not minutes.

### If primary use is user journey analysis + general-purpose (70% confident → TimescaleDB)

```sql
-- TimescaleDB: PostgreSQL + time-series superpowers
-- "Show me everything user 12345 did yesterday"

CREATE TABLE events (
    timestamp    TIMESTAMPTZ NOT NULL,
    event_type   TEXT,
    user_id      BIGINT,
    properties   JSONB,
    ip_address   INET
);

-- Convert to hypertable (automatic partitioning by time)
SELECT create_hypertable('events', 'timestamp',
    chunk_time_interval => INTERVAL '1 day');

-- Create indexes for common access patterns
CREATE INDEX idx_events_user ON events (user_id, timestamp DESC);

-- Point query: fast (indexed)
SELECT * FROM events
WHERE user_id = 12345 AND timestamp >= '2024-01-15'
ORDER BY timestamp;

-- Analytical query: good (not ClickHouse-fast, but acceptable)
SELECT time_bucket('1 hour', timestamp) AS hour,
       event_type,
       count(*)
FROM events
WHERE timestamp >= now() - INTERVAL '7 days'
GROUP BY hour, event_type;

-- Automatic data retention (delete events older than 90 days)
SELECT add_retention_policy('events', INTERVAL '90 days');

-- Automatic compression (shrink old data 10-20x)
SELECT add_compression_policy('events', INTERVAL '7 days');
```

**Why TimescaleDB:** It's PostgreSQL — your team already knows it, your existing tools work, and you get time-series optimizations (automatic partitioning, compression, retention) without a new database.

### If schema varies wildly per event type (40% confident → MongoDB)

MongoDB is only better if:
- Event types have radically different structures
- You need to query deeply nested fields efficiently
- Your team already knows MongoDB well

For most event use cases, PostgreSQL's JSONB handles schema flexibility well enough.

## What I'd Avoid (90% Confident)

**Don't use raw PostgreSQL without TimescaleDB or partitioning:**
- 50M rows/day = 18B rows/year
- Unpartitioned PostgreSQL will grind to a halt on aggregations
- VACUUM becomes a serious operational burden

```sql
-- ❌ Raw PostgreSQL at 18B rows: this query takes 30+ minutes
SELECT count(*) FROM events
WHERE event_type = 'page_view' AND timestamp > now() - interval '30 days';

-- ✅ TimescaleDB at 18B rows: same query in 2-5 seconds
-- (hypertable + chunk exclusion + compression)
```

## The Pragmatic Path

```
Start simple, upgrade when needed:

1. TODAY: TimescaleDB (PostgreSQL + time-series extension)
   - Zero new infrastructure if you already use PostgreSQL
   - Handles 50M events/day comfortably
   - Your team already knows SQL

2. LATER (if analytics become primary use case):
   - Add ClickHouse as a read replica for analytics
   - Keep TimescaleDB for real-time queries and writes
   - Sync via Kafka or CDC (change data capture)

3. AVOID premature optimization:
   - Don't start with ClickHouse unless analytics is your core product
   - Don't use MongoDB unless your schema is truly unstructured
```'''
    ),
    (
        "thinking/multiperspective-remote-team-velocity",
        "Our remote development team's velocity has dropped 30% over the last two quarters. We've tried standup meetings and sprint retrospectives but nothing has changed. What's going on?",
        r'''<think>
Remote team velocity drop — this is rarely a technical problem. Let me analyze from multiple perspectives.

**Individual developer perspective:**
What's happening in their day:
- Meeting overload ("I have no uninterrupted time to code")
- Context switching between Slack, email, tickets, code reviews
- Unclear priorities ("what should I actually be working on?")
- Burnout/motivation decline (remote isolation)
- Tool friction (slow CI, bad dev environment, flaky tests)

**Team dynamics perspective:**
- Knowledge silos (one person knows each area, blockers when they're busy)
- Unclear ownership (tickets sit because nobody knows who should do them)
- PR review bottleneck (code sits for days waiting for review)
- Async communication failures (misunderstandings, waiting for answers across time zones)

**Process perspective:**
- Too many meetings (standups, retros, planning, 1:1s, all-hands = 5-10 hrs/week)
- Sprint planning disconnect (stories too large, not well-defined)
- Work not visible (hard to see blockers and dependencies)
- Technical debt accumulation making everything slower

**Management perspective:**
- "Velocity dropped" — but is this measurement accurate? Story point inflation earlier?
- New team members who haven't ramped up?
- Changed product direction causing more unknowns?
- More complex features now that the easy wins are done?

**The 30% drop is a symptom, not the diagnosis.**
I need to identify which of these is the ACTUAL cause. The most common causes I've seen:
1. Meeting overload (most common in remote teams)
2. Unclear priorities / too much WIP
3. Technical friction (slow tests, bad CI)
4. Burnout

Let me provide a diagnostic approach.
</think>

A 30% velocity drop in a remote team is almost never a single problem — it's usually 3-4 compounding issues. Here's a diagnostic approach:

## Step 1: Measure Where Time Actually Goes (1 Week)

Ask each developer to track their time for ONE week (not permanently):

```markdown
## Time Audit Template (per developer, per day)

| Activity | Hours |
|----------|-------|
| Writing code | ? |
| Reading/understanding code | ? |
| Code reviews (reviewing others) | ? |
| Waiting for reviews (blocked) | ? |
| Meetings (standups, planning, retros, 1:1s) | ? |
| Slack/email communication | ? |
| Debugging CI/environment issues | ? |
| Context switching between tasks | ? |
| Unclear requirements / waiting for answers | ? |
```

## The Usual Findings

Most remote teams discover something like this:

```
EXPECTED time distribution:     ACTUAL time distribution:
  Coding:           60%           Coding:           25%
  Code review:      10%           Meetings:         25%
  Meetings:         10%           Slack/email:       20%
  Communication:    10%           Code review:       10%
  Other:            10%           Waiting/blocked:   10%
                                  CI/env issues:     10%

The 30% velocity drop = developers spending
25% of their time coding instead of 60%.
```

## The Top 4 Causes (and Fixes)

### Cause 1: Meeting Overload (Most Common)

```
Typical remote team meeting load:
  Daily standup:           15 min × 5 = 1.25 hrs/week
  Sprint planning:         2 hrs/2 weeks = 1 hr/week
  Sprint retro:            1 hr/2 weeks = 0.5 hr/week
  Backlog grooming:        1 hr/week
  1:1 with manager:        0.5 hr/week
  Team sync:               1 hr/week
  All-hands:               0.5 hr/week
  Ad-hoc discussions:      2-3 hrs/week
  Total: 8-10 hrs/week = 20-25% of time

But worse: each meeting fragments a coding block.
A 30-minute meeting in the middle of a morning
destroys a 4-hour focus block → net loss is 2+ hours.
```

**Fix:**
```markdown
## Meeting Hygiene Rules

1. Meeting-free blocks: Tue/Thu mornings are NO MEETINGS (8am-12pm)
2. Async standups: Post in Slack by 9am instead of synchronous meeting
   "Yesterday: finished auth migration. Today: starting API tests. Blocked: none"
3. 25-minute meetings (not 30): gives 5 min buffer between meetings
4. Default to async: "Could this have been a Slack message?" If yes, cancel.
5. Maximum 3 meetings per developer per day (enforced by calendar audit)
```

### Cause 2: Too Much Work In Progress (WIP)

```
Developer has 5 tickets "in progress":
  - Ticket A: waiting for design feedback
  - Ticket B: waiting for PR review
  - Ticket C: blocked by another team
  - Ticket D: actually working on this
  - Ticket E: started yesterday, context-switching to A when unblocked

Each context switch = 20-30 minutes to get back "in the zone"
5 switches/day × 25 min = 2+ hours LOST to context switching
```

**Fix: WIP limits**
```markdown
## WIP Policy
- Maximum 2 tickets "in progress" per developer
- If blocked, DON'T start a new ticket. Instead:
  - Unblock yourself (ping reviewer, ask question)
  - Help review someone else's PR
  - Only start new work as last resort
```

### Cause 3: Technical Friction

```
Common friction points:
  CI takes 45 minutes → developers wait instead of iterate
  Flaky tests → rerun CI 2-3 times per PR
  Dev environment setup → new features take 2 hours to test locally
  Dependency conflicts → "works on my machine"
```

**Fix: Measure and fix the dev loop**
```bash
# Track these metrics:
# Time from commit → CI result: should be < 10 minutes
# Number of CI reruns per PR: should be < 1.2
# Time from PR opened → first review: should be < 4 hours
# Time from PR opened → merged: should be < 1 day
```

### Cause 4: Burnout / Disengagement

```
Remote work warning signs:
  - Camera off in all meetings (not always burnout, but worth noting)
  - Shorter and shorter commit messages
  - Less participation in code reviews
  - Working odd hours (compensating for low productivity)
  - No informal team interaction
```

**Fix:**
```markdown
## Remote Team Health
- Weekly optional social time (30 min, no work topics)
- Pair programming sessions (combat isolation)
- Explicit "core hours" (no expectation of response outside 10am-4pm)
- Regular 1:1s focused on wellbeing, not just task status
```

## The Action Plan

```
Week 1:    Time audit — everyone tracks their time
Week 2:    Analyze results, identify top 2-3 causes
Week 3-4:  Implement fixes for top cause
Week 5-6:  Implement fixes for second cause
Week 7-8:  Measure velocity again, compare

Expected outcome: 15-25% velocity improvement within 2 months
by recovering time lost to meetings, context switching, and friction.
```

The uncomfortable truth: standups and retros don't fix velocity because they're ABOUT process, not the process itself. The fixes are structural — fewer meetings, WIP limits, faster CI, and addressing burnout.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
