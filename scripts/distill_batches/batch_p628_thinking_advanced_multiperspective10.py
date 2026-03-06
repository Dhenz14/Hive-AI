"""Phase 2D: Advanced Reasoning — Multi-Perspective Analysis (Part 10)"""

PAIRS = [
    (
        "thinking/multiperspective-microservices-communication",
        "Our microservices communicate via synchronous HTTP calls. Some people want to switch to message queues (RabbitMQ/Kafka). Others say HTTP is simpler. How do I decide?",
        r'''<think>
Sync HTTP vs async messaging between microservices. Let me think through perspectives.

**HTTP (synchronous) advocate:**
- Simple: request/response is intuitive
- Easy to debug (HTTP status codes, request/response logging)
- Immediate feedback (caller knows if it worked)
- No infrastructure overhead (no message broker to maintain)
- OpenAPI/Swagger for documentation

**Message queue (async) advocate:**
- Decoupling: services don't need to know about each other
- Resilience: if consumer is down, messages queue up and process later
- Scalability: add more consumers to handle load
- Temporal decoupling: producer and consumer don't need to be up simultaneously
- Event-driven architecture enables event sourcing, CQRS

**The nuanced view:**
It's not either/or. Different communication patterns suit different needs:
- Query (need data now) → sync HTTP
- Command (do something, need confirmation) → sync HTTP or async with reply
- Event (something happened, react to it) → async messaging
- Long-running process → definitely async

The question isn't "HTTP or queues?" but "which interactions need synchronous response and which don't?"
</think>

This isn't an either/or decision. Let me break down when each approach is right.

## The Two Perspectives

### HTTP Advocates

```
STRENGTHS:
  ✓ Simple mental model: send request, get response
  ✓ Immediate feedback: "order created" or "error: invalid data"
  ✓ Easy to debug: HTTP status codes, request/response pairs, curl
  ✓ No extra infrastructure: no broker to deploy, monitor, maintain
  ✓ Mature tooling: OpenAPI, Postman, API gateways

WEAKNESSES:
  ✗ Tight coupling: caller must know callee's address
  ✗ Cascading failures: if downstream is slow, upstream blocks
  ✗ No buffer: if downstream is down, request fails immediately
  ✗ Synchronous blocking: thread/connection held during call
```

### Message Queue Advocates

```
STRENGTHS:
  ✓ Decoupled: producer doesn't know (or care) about consumers
  ✓ Resilient: if consumer is down, messages wait in queue
  ✓ Scalable: add consumers to handle more throughput
  ✓ Temporal decoupling: producer and consumer run at their own pace
  ✓ Fan-out: one event, many consumers (order created → email, analytics, shipping)

WEAKNESSES:
  ✗ Complexity: broker is another thing to deploy and monitor
  ✗ No immediate response: "did it work?" requires callbacks or polling
  ✗ Debugging: messages in queues are harder to trace than HTTP calls
  ✗ Eventual consistency: consumer might process the message seconds later
  ✗ Message ordering, exactly-once delivery, dead letters — all need handling
```

## Decision Framework: Match the Pattern

```
INTERACTION TYPE              BEST FIT          EXAMPLE
────────────────────────────────────────────────────────────
"Give me data now"            HTTP (sync)       GET /users/42
(query, needs response)

"Do this, tell me if it       HTTP (sync)       POST /orders
worked" (command, needs ack)                    → 201 Created

"This happened, react"        Queue (async)     "order.created" event
(event, no response needed)                     → email, analytics, shipping

"Process this eventually"     Queue (async)     Image resizing, PDF generation
(background work)                               report generation

"Call 3 services, combine     HTTP (sync) +     API gateway calls user, order,
results" (aggregation)        parallel           payment services in parallel

"This happened, many care"    Queue (async)     "user.registered" →
(fan-out to many consumers)   pub/sub            welcome email, CRM sync,
                                                 analytics, onboarding
```

## Practical Architecture: Use Both

```
              ┌──────────┐
  Browser ──→ │ API GW   │ ──HTTP──→ Order Service ──→ DB
              └──────────┘        │
                                  │ publishes event
                                  ▼
                          ┌──── Message Queue ────┐
                          │  "order.created"       │
                          └───┬────┬────┬─────────┘
                              │    │    │
                              ▼    ▼    ▼
                          Email  Shipping  Analytics
                          Service Service  Service

  SYNCHRONOUS (HTTP):
    Browser → API → Order Service → "201 Created"
    User gets immediate confirmation.

  ASYNCHRONOUS (Queue):
    Order Service → publishes "order.created" event
    Email Service → sends confirmation email (seconds later)
    Shipping Service → creates shipping label (seconds later)
    Analytics Service → records metrics (seconds later)
    None of these need to happen for the user's request to succeed.
```

```python
# Order Service: synchronous API + async events
@app.post("/orders")
async def create_order(data: OrderRequest):
    # Synchronous: validate and create order
    order = await order_repository.create(data)

    # Asynchronous: publish event for downstream services
    await message_bus.publish("order.created", {
        "order_id": order.id,
        "user_id": order.user_id,
        "total": order.total,
        "items": order.items,
    })

    # Return immediately — user doesn't wait for email/shipping
    return {"id": order.id, "status": "created"}


# Email Service: async consumer
@message_bus.subscribe("order.created")
async def handle_order_created(event):
    user = await user_service.get_user(event["user_id"])  # HTTP call OK here
    await send_confirmation_email(user.email, event)
```

## The Key Question

```
For each service-to-service interaction, ask:

  "Does the CALLER need the result to continue?"

  YES → synchronous HTTP
    "Show me this user's profile" → need the data to render the page
    "Create this order" → need the order ID to redirect the user

  NO → asynchronous messaging
    "Send a confirmation email" → user doesn't wait for email
    "Update analytics" → doesn't affect the user's request
    "Generate a PDF report" → user can come back later

Most services need BOTH:
  - HTTP for the request/response API
  - Events for side effects and notifications
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
