"""Documentation generation training pairs: architecture decision records and system overviews."""

pairs = [
    {
        "instruction": r'''Write an Architecture Decision Record (ADR) for this decision. Context: we are building an e-commerce platform and chose to use event sourcing for the order management service instead of traditional CRUD with a relational database.''',
        "output": r'''<think>
An ADR should follow a standard template: Title, Status, Context, Decision, Consequences. I need to explain why event sourcing was chosen over CRUD for orders specifically, what tradeoffs were accepted, and what follows from this decision. The key arguments for event sourcing in orders: full audit trail, ability to reconstruct state at any point, support for complex workflows (returns, partial shipments). Arguments against: increased complexity, eventual consistency, steeper learning curve.
</think>

# ADR-007: Use Event Sourcing for Order Management

**Status:** Accepted

**Date:** 2024-09-15

## Context

The order management service handles the full lifecycle of customer orders: creation, payment, fulfillment, shipping, returns, and refunds. Orders go through many state transitions, and business stakeholders need:

- A complete audit trail of every change to every order
- The ability to answer questions like "what did this order look like at 2pm yesterday?"
- Support for complex workflows (partial shipments, split payments, retroactive discounts)

We evaluated two approaches:

1. **Traditional CRUD** with a PostgreSQL orders table and a separate audit_log table
2. **Event sourcing** where order state is derived from an append-only stream of domain events

## Decision

We will use event sourcing for the order management service. Order state is rebuilt by replaying events (OrderCreated, PaymentReceived, ItemShipped, etc.) from an append-only event store. Read-side projections will be maintained for query performance.

The event store will use PostgreSQL with an append-only events table. We will not introduce a dedicated event store product (e.g., EventStoreDB) at this stage to limit operational complexity.

## Consequences

**Positive:**

- Full audit trail is built-in -- no separate audit logging needed
- Temporal queries ("state at time T") are straightforward
- Domain events can be published to other services for integration (notifications, analytics)
- Complex workflows are modeled naturally as event sequences

**Negative:**

- Higher implementation complexity compared to CRUD
- Developers must learn event sourcing patterns (projections, snapshots, idempotent handlers)
- Eventual consistency between the event store and read-side projections
- Schema evolution of events requires careful versioning (upcasting)

**Mitigations:**

- Snapshot every 100 events to keep replay times bounded
- Use a shared library for event serialization and versioning
- Comprehensive integration tests for projection consistency'''
    },
    {
        "instruction": r'''Write a system architecture overview document for this microservices setup:

Services:
- api-gateway (Node.js, Express) - routes requests, rate limiting, auth
- user-service (Python, FastAPI) - user accounts, profiles, auth tokens
- product-service (Go) - product catalog, inventory, pricing
- order-service (Python, FastAPI) - order management, checkout
- notification-service (Node.js) - email, SMS, push notifications
- payment-service (Go) - payment processing, refunds

Infrastructure:
- PostgreSQL (user-service, order-service)
- MongoDB (product-service)
- Redis (api-gateway caching, session store)
- RabbitMQ (async messaging between services)
- S3 (product images, user uploads)
- Kubernetes on AWS EKS
- GitHub Actions CI/CD''',
        "output": r'''# System Architecture Overview

## 1. High-Level Architecture

The platform follows a microservices architecture with six independently deployable services communicating via synchronous HTTP/REST and asynchronous message queues. All services run on Kubernetes (AWS EKS) behind an API gateway.

```
Clients (Web/Mobile)
       |
   API Gateway (Node.js)
       |
  +---------+---------+---------+
  |         |         |         |
Users    Products   Orders   Payments
(Python)  (Go)     (Python)   (Go)
  |         |         |         |
  +----+----+    +----+----+   |
       |         |         |   |
   PostgreSQL  MongoDB  RabbitMQ
                           |
                    Notifications
                      (Node.js)
```

## 2. Service Descriptions

**API Gateway** -- Entry point for all client requests. Handles JWT validation, rate limiting (token bucket via Redis), request routing, and response caching for product catalog reads.

**User Service** -- Manages registration, authentication (JWT issuance), profile CRUD, and password resets. Owns the users PostgreSQL database.

**Product Service** -- Product catalog with full-text search, inventory tracking, and dynamic pricing. Uses MongoDB for flexible product schemas and nested attributes.

**Order Service** -- Orchestrates the checkout flow. Validates inventory (sync call to product-service), initiates payment (sync call to payment-service), and publishes order events to RabbitMQ.

**Payment Service** -- Integrates with external payment providers. Handles charges, refunds, and webhook callbacks. Publishes payment outcome events to RabbitMQ.

**Notification Service** -- Consumes events from RabbitMQ and sends emails (via SES), SMS (via Twilio), and push notifications (via FCM). No synchronous API -- fully event-driven.

## 3. Communication Patterns

- **Synchronous:** REST/HTTP between api-gateway and backend services; order-service calls payment-service and product-service directly during checkout.
- **Asynchronous:** RabbitMQ for event-driven flows (order.created, payment.completed, shipment.updated). Notification-service consumes all notification-worthy events.

## 4. Data Stores

| Store      | Owner(s)                  | Purpose                     |
|------------|---------------------------|-----------------------------|
| PostgreSQL | user-service, order-service | Transactional data         |
| MongoDB    | product-service           | Flexible product catalog    |
| Redis      | api-gateway               | Response cache, sessions    |
| S3         | product-service           | Product images, user uploads|

## 5. Deployment

All services are containerized and deployed to AWS EKS via GitHub Actions. Each service has its own Helm chart, CI pipeline, and independent release cycle.'''
    },
    {
        "instruction": r'''Write an ADR for choosing WebSocket over Server-Sent Events (SSE) for a real-time collaborative document editor.''',
        "output": r'''# ADR-012: WebSocket for Real-Time Collaboration Transport

**Status:** Accepted

**Date:** 2024-11-02

## Context

Our collaborative document editor requires real-time communication between clients and the server. Users editing the same document must see each other's changes within 100ms. The editor uses Operational Transformation (OT) for conflict resolution.

Two transport protocols were evaluated:

1. **Server-Sent Events (SSE)** -- server-to-client streaming over HTTP/1.1. Client-to-server communication uses regular HTTP POST requests.
2. **WebSocket** -- full-duplex bidirectional communication over a single persistent TCP connection.

Key requirements:

- Sub-100ms latency for operation propagation
- Bidirectional: clients send operations AND receive operations from other users
- Cursor position and selection broadcasting
- Connection state awareness (detect disconnects quickly)

## Decision

We will use WebSocket (via the ws library on Node.js, native WebSocket API on the client).

**Rationale:**

- **Bidirectional:** OT requires frequent client-to-server messages (every keystroke). SSE would need a separate POST channel for upstream, adding latency and complexity.
- **Latency:** WebSocket avoids HTTP request overhead for each operation. With SSE + POST, each upstream message incurs TCP/TLS handshake cost (unless using HTTP/2 with connection reuse, which adds infrastructure complexity).
- **Connection management:** WebSocket has built-in ping/pong frames for connection health checks. SSE relies on reconnection timeouts, which are slower to detect dead connections.
- **Cursor streaming:** Broadcasting cursor positions generates high-frequency small messages. WebSocket frames have lower overhead (2-6 bytes) compared to SSE event framing.

## Consequences

**Positive:**

- Single connection handles both upstream and downstream
- Lower per-message overhead for high-frequency updates
- Native ping/pong for connection health monitoring

**Negative:**

- WebSocket connections are not cacheable by CDNs or HTTP proxies
- Load balancers need sticky sessions or WebSocket-aware routing
- Reconnection logic must be implemented manually (SSE has built-in auto-reconnect)
- Cannot use standard HTTP middleware (auth, logging) -- must handle in the WebSocket handshake

**Mitigations:**

- Use an ALB with WebSocket support on AWS
- Implement exponential backoff reconnection with jitter on the client
- Authenticate during the WebSocket upgrade handshake via a short-lived token in the query string'''
    },
    {
        "instruction": r'''Write a brief architecture overview for this monolithic Django application that is being considered for decomposition into services. Include which parts are good candidates for extraction.

# Django apps in the project:
# accounts/ - user auth, profiles, teams, permissions (35 models)
# billing/ - subscriptions, invoices, payment processing (18 models)
# projects/ - project management, tasks, kanban boards (22 models)
# documents/ - document storage, versioning, sharing (12 models)
# analytics/ - usage tracking, report generation, dashboards (8 models)
# notifications/ - email, in-app, webhook notifications (6 models)
# integrations/ - Slack, GitHub, Jira connectors (15 models)
# api/ - REST API layer (DRF), used by SPA frontend and mobile app

# Pain points:
# - Deployments take 45 min due to full test suite
# - billing/ changes require careful testing of accounts/ and projects/
# - analytics/ report generation blocks web workers for minutes
# - integrations/ third-party API calls cause timeout cascading
# - Database has 116 models in one PostgreSQL instance''',
        "output": r'''<think>
I need to analyze this monolith for service extraction candidates. The pain points reveal which boundaries are causing problems:

1. analytics/ -- long-running reports blocking web workers -- classic candidate for extraction with async processing
2. integrations/ -- third-party API calls causing cascading timeouts -- should be isolated
3. notifications/ -- low coupling, clear bounded context, event-driven by nature
4. billing/ -- tightly coupled to accounts/ and projects/ -- harder to extract

The accounts/ and projects/ apps are likely the core domain and tightly coupled. Extracting them early would be risky. Better candidates are the "leaf" services that consume events but do not have deep joins into core tables.
</think>

# Architecture Overview: ProjectHub Monolith

## Current State

ProjectHub is a Django 4.x monolith serving a React SPA and mobile apps via a Django REST Framework API. All 8 Django apps share a single PostgreSQL database with 116 models.

### App Dependency Map

```
accounts/ <--+-- projects/ <--+-- documents/
    |        |                 |
    +--------+-- billing/      +-- analytics/
    |
    +-- notifications/ (reads from all apps)
    +-- integrations/ (reads from projects/, accounts/)
    +-- api/ (thin layer over all apps)
```

### Pain Points

- **Deployment:** 45-min test suite; any change deploys everything
- **Cascading timeouts:** integrations/ makes sync calls to third-party APIs
- **Worker starvation:** analytics/ blocks web workers with heavy queries
- **Coupling:** billing/ has deep FKs into accounts/ and projects/

## Extraction Candidates

**1. Notifications (LOW risk)** -- 6 models, event-driven, minimal dependencies. Extract as a queue consumer.

**2. Analytics (MEDIUM risk)** -- 8 read-only models. Move to async worker with read replica. Removes long queries from web workers.

**3. Integrations (MEDIUM risk)** -- 15 models, self-contained. Isolates third-party latency behind async messaging.

**4. Billing (HIGH risk -- defer)** -- Deep FKs across core apps. Keep in monolith until domain boundaries stabilize.'''
    },
    {
        "instruction": r'''Write a data flow architecture document for this ETL pipeline:

# Airflow DAG
# 1. extract_from_postgres - reads from 5 source tables in OLTP database
# 2. extract_from_s3 - pulls CSV files from partner data drops
# 3. validate_schemas - runs Great Expectations checks on raw data
# 4. transform_dimensions - builds dimension tables (users, products, regions)
# 5. transform_facts - builds fact tables (orders, page_views, revenue)
# 6. load_to_warehouse - bulk loads into Snowflake via COPY INTO
# 7. run_dbt_models - runs dbt for downstream aggregation tables
# 8. update_dashboards - triggers Looker cache refresh
# 9. notify_stakeholders - sends Slack summary with row counts and warnings

# Schedule: daily at 2am UTC
# SLA: must complete by 6am UTC
# Data volume: ~50M rows/day across all sources''',
        "output": r'''# ETL Pipeline -- Data Flow Architecture

## Overview

A daily batch ETL pipeline orchestrated by Apache Airflow that extracts data from operational systems, validates and transforms it, and loads it into a Snowflake data warehouse for analytics.

**Schedule:** Daily at 02:00 UTC | **SLA:** Complete by 06:00 UTC | **Volume:** ~50M rows/day

## Pipeline Stages

```
[OLTP PostgreSQL] ---+
                     +--> [Validate] --> [Transform] --> [Snowflake] --> [dbt] --> [Looker]
[S3 Partner CSVs] ---+
                                                                                    |
                                                                              [Slack Alert]
```

### Stage 1: Extract (parallel)

Two extract tasks run in parallel:

- **extract_from_postgres** -- Reads from 5 source tables in the OLTP database using incremental extraction (WHERE updated_at > last_run_timestamp). Outputs Parquet files to a staging S3 bucket.
- **extract_from_s3** -- Pulls CSV files from partner data drop locations. Files are moved to a processed/ prefix after pickup to prevent reprocessing.

### Stage 2: Validate

- **validate_schemas** -- Runs Great Expectations validation suites on all raw data. Checks include: schema conformance, null rates, value ranges, referential integrity between sources. Failures produce warnings (soft) or block the pipeline (hard) depending on severity.

### Stage 3: Transform (sequential)

- **transform_dimensions** -- SCD Type 2 dimension tables (users, products, regions) with deduplication and surrogate keys.
- **transform_facts** -- Fact tables (orders, page_views, revenue) joining raw data with dimension keys. Applies currency conversion, tax, and session attribution.

### Stage 4: Load

- **load_to_warehouse** -- Bulk loads into Snowflake staging via COPY INTO, then atomically swaps staging with production tables.

### Stage 5: Post-Load

- **run_dbt_models** -- Builds aggregation tables (daily summaries, cohorts, funnels) with incremental materialization.
- **update_dashboards** -- Triggers Looker cache refresh.
- **notify_stakeholders** -- Slack summary with row counts, warnings, and SLA status.

## Failure Handling

- Schema validation failures on partner data: pipeline continues with warnings, affected rows quarantined
- Source database unavailable: task retries 3 times with 10-minute backoff
- Snowflake load failure: rolls back staging swap, alerts on-call via PagerDuty
- SLA breach (not complete by 06:00 UTC): automatic escalation to data engineering on-call'''
    },
]
