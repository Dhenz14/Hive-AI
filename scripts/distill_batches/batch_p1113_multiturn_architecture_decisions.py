"""
Multi-turn conversation training pairs - Architecture Decisions
Design discussions with tradeoffs, pushback, and evolving requirements
"""

pairs = [
    {
        "instruction": r'''[Previous conversation]
User: We are building an e-commerce platform. Should we use microservices architecture from the start? We have a team of 5 developers.

[Current message]
User: Our CTO wants microservices because "that is what Netflix uses." But we have not even launched yet. How do I push back on this?''',
        "output": r'''With 5 developers and no launch yet, microservices would slow you down significantly. Here is a concrete argument:

**Why a monolith first:**

1. **Deployment complexity** -- Microservices need: container orchestration (Kubernetes), service mesh, distributed tracing, centralized logging, API gateway, service discovery. That is months of infrastructure work before writing business logic.

2. **Team size math** -- With 5 people and, say, 6 services, each person owns more than one service. The benefit of microservices (independent team ownership) does not exist.

3. **Boundary uncertainty** -- You do not know your domain boundaries yet. In microservices, getting the boundaries wrong means expensive cross-service refactoring. In a monolith, it is just moving code between modules.

**What to build instead -- a modular monolith:**

```
ecommerce/
    catalog/           # Product listings, categories, search
        models.py
        services.py
        routes.py
    orders/            # Cart, checkout, order processing
        models.py
        services.py
        routes.py
    payments/          # Payment processing, refunds
        models.py
        services.py
        routes.py
    users/             # Auth, profiles, addresses
        models.py
        services.py
        routes.py
    shared/            # Shared utilities, base classes
```

Rules: modules communicate through defined service interfaces, not by reaching into each other's models directly. This gives you clear boundaries that can be extracted into services later if needed.

**When to consider microservices:**
- When one module needs to scale independently (e.g., search gets 100x more traffic than orders)
- When teams grow to 15+ people and need independent deployment
- When different modules need different tech stacks (e.g., search needs Elasticsearch, ML needs Python)

Tell your CTO: "Netflix started as a monolith too. They moved to microservices when they had hundreds of engineers and specific scaling problems. We have neither."'''
    },
    {
        "instruction": r'''[Previous conversation]
User: We are building a social media app with posts, comments, likes, followers, and a feed. Should we use PostgreSQL or MongoDB?
Assistant: For social media with relational data (users follow users, users like posts), PostgreSQL is usually the better starting point. The relationships between entities map naturally to relational tables, and you get ACID transactions, mature tooling, and strong query capabilities. MongoDB can work but you will end up reimplementing relationships manually.

[Current message]
User: OK, PostgreSQL makes sense for most of it. But what about the activity feed? Every user has a personalized feed showing posts from people they follow, sorted by time. I have heard that feeds are hard to do with SQL at scale.''',
        "output": r'''You are right that the feed is the hardest part to scale. There are three main approaches, and the right one depends on your user count:

**Approach 1 -- Fan-out on read (simplest, good to ~100K users):**

Query at read time. No denormalization:

```sql
-- Get feed for user 42: posts from people they follow, newest first
SELECT p.id, p.content, p.created_at, u.username
FROM posts p
JOIN users u ON p.author_id = u.id
WHERE p.author_id IN (
    SELECT followed_id FROM follows WHERE follower_id = 42
)
ORDER BY p.created_at DESC
LIMIT 20 OFFSET 0;
```

With proper indexes this is fast enough for most apps:

```sql
CREATE INDEX idx_posts_author_created ON posts (author_id, created_at DESC);
CREATE INDEX idx_follows_follower ON follows (follower_id, followed_id);
```

**Approach 2 -- Fan-out on write (good to ~10M users):**

When someone posts, push a reference into their followers' feed tables:

```sql
CREATE TABLE feed_entries (
    id BIGSERIAL PRIMARY KEY,
    user_id INT NOT NULL,       -- the feed owner
    post_id INT NOT NULL,       -- the post to show
    created_at TIMESTAMP NOT NULL,
    INDEX idx_feed_user_time (user_id, created_at DESC)
);

-- When user 10 creates a post, insert into all followers' feeds
INSERT INTO feed_entries (user_id, post_id, created_at)
SELECT follower_id, NEW_POST_ID, NOW()
FROM follows
WHERE followed_id = 10;
```

Reading is fast (just query your own feed table) but writing is expensive for users with millions of followers.

**Approach 3 -- Hybrid (what Twitter/Instagram do):**

- Fan-out on write for normal users (< 10K followers)
- Fan-out on read for celebrities (> 10K followers)
- Merge both at read time

**My recommendation:** Start with Approach 1. It is the simplest and works until you have real scale problems. PostgreSQL with proper indexes can handle feeds for 100K+ users on modest hardware. You can always add Redis caching later or move to Approach 2 when you need it. Do not build the Twitter architecture before you have Twitter's problems.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: We decided to split our monolith into 3 services: user service, order service, and product service. Each has its own database.
Assistant: Good separation. Make sure you have clear API contracts between services and a strategy for cross-service data consistency.

User: How should I handle authentication across the services? Right now the monolith uses session-based auth with cookies.

[Current message]
User: Should each service validate the session independently, or should there be a central auth service?''',
        "output": r'''For microservices, move from session-based auth to token-based auth (JWT). Here is the architecture:

**Option 1 -- API Gateway + JWT (recommended):**

```
Client --> API Gateway --> Service A
                      --> Service B
                      --> Service C

1. Client sends credentials to /auth/login
2. User Service validates, returns JWT
3. Client includes JWT in all subsequent requests
4. API Gateway validates JWT, forwards request + user context to services
5. Services trust the gateway (internal network only)
```

```python
# API Gateway middleware (e.g., in Kong, or custom)
# Validates JWT and adds user info to headers
def gateway_auth_middleware(request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"])
        # Forward user info as internal headers
        request.headers["X-User-Id"] = str(payload["user_id"])
        request.headers["X-User-Role"] = payload["role"]
    except jwt.InvalidTokenError:
        return Response(status=401, body={"error": "Invalid token"})

# Individual services -- no JWT validation needed, just read headers
@app.get("/orders")
def list_orders(request):
    user_id = request.headers["X-User-Id"]  # Trusted from gateway
    orders = OrderRepo.get_by_user(user_id)
    return orders
```

**Option 2 -- Each service validates JWT independently:**

```python
# Shared library used by all services
# pip install your-company-auth-lib

from auth_lib import require_auth

@app.get("/orders")
@require_auth(roles=["user", "admin"])
def list_orders(request):
    user_id = request.auth.user_id
    return OrderRepo.get_by_user(user_id)
```

Each service has the public key and validates the JWT itself. No central point of failure, but you need to distribute the public key to all services.

**Key decisions:**

- Use RS256 (asymmetric) not HS256 (symmetric) -- the user service holds the private key, everyone else only needs the public key
- Put minimal data in the JWT: user_id, role, expiry. Do not put email/name -- those change and JWTs are immutable
- Keep JWTs short-lived (15 min) with refresh tokens for new access tokens
- Internal service-to-service calls use a separate mechanism (mutual TLS or service account tokens), not user JWTs

I recommend Option 1 (API Gateway) because it centralizes auth logic, simplifies individual services, and gives you one place to add rate limiting, logging, and CORS.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: Our API is getting slow under load. The product listing endpoint takes 500ms because it queries PostgreSQL with several JOINs every time. We get about 1000 requests per minute to this endpoint and the data only changes a few times per day.
Assistant: With data that rarely changes and high read traffic, caching is the right approach. Redis is the standard choice for API caching.

[Current message]
User: How should I structure the caching? I do not want stale data showing to users when we do update products. And should I cache at the database level, the API level, or both?''',
        "output": r'''Cache at the API level since that is where the bottleneck is. Here is a structured approach:

**Cache-aside pattern with invalidation:**

```python
import redis
import json
import hashlib

redis_client = redis.Redis(host='localhost', port=6379, db=0)
CACHE_TTL = 3600  # 1 hour as safety net

def cache_key(prefix, **params):
    """Generate consistent cache keys from query parameters."""
    param_str = json.dumps(params, sort_keys=True)
    param_hash = hashlib.md5(param_str.encode()).hexdigest()[:12]
    return f"{prefix}:{param_hash}"

# Read path -- check cache first
@app.get("/products")
async def list_products(
    category: str = None,
    page: int = 1,
    per_page: int = 20,
):
    key = cache_key("products:list", category=category, page=page, per_page=per_page)

    # Try cache
    cached = redis_client.get(key)
    if cached:
        return json.loads(cached)

    # Cache miss -- query DB
    result = await query_products(category, page, per_page)

    # Store in cache
    redis_client.setex(key, CACHE_TTL, json.dumps(result))
    return result

# Write path -- invalidate related caches
@app.put("/products/{product_id}")
async def update_product(product_id: int, data: ProductUpdate):
    await save_product(product_id, data)

    # Invalidate all product list caches
    # Use a pattern delete (or cache tags)
    for key in redis_client.scan_iter("products:list:*"):
        redis_client.delete(key)

    # Invalidate the specific product cache
    redis_client.delete(f"products:detail:{product_id}")

    return {"status": "updated"}
```

**Better approach -- cache versioning (avoids scan_iter):**

```python
def get_cache_version(resource_type):
    """Version number incremented on any write."""
    version = redis_client.get(f"version:{resource_type}")
    return version.decode() if version else "0"

def bump_cache_version(resource_type):
    """Increment version to invalidate all caches for this resource."""
    redis_client.incr(f"version:{resource_type}")

def versioned_key(prefix, **params):
    version = get_cache_version(prefix.split(":")[0])
    param_str = json.dumps(params, sort_keys=True)
    param_hash = hashlib.md5(param_str.encode()).hexdigest()[:12]
    return f"{prefix}:v{version}:{param_hash}"

# On product update:
bump_cache_version("products")
# All existing cache keys now have the old version and will miss
```

**Why not cache at the DB level too:**
- PostgreSQL already has its own query cache and buffer pool
- Adding another cache layer (like pgbouncer query cache) adds complexity without much benefit when you are already caching API responses
- One cache layer is easier to reason about and invalidate

Since your data changes "a few times per day," the cache hit rate will be very high. The versioning approach means updates instantly invalidate all stale data without scanning keys.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: When a user places an order in our e-commerce app, we need to: (1) save the order, (2) charge payment, (3) update inventory, (4) send confirmation email, (5) notify the warehouse. Right now all five steps happen synchronously in one API call and it takes 3-4 seconds.
Assistant: That is too slow for a checkout flow. The user should not wait for email sending and warehouse notification. Separate the critical path (save order + charge payment) from the background tasks (email, warehouse notification, inventory).

[Current message]
User: Should I use a message queue like RabbitMQ for the background tasks, or can I just use a task queue like Celery? What is the difference and which one fits better?''',
        "output": r'''Both involve queuing work, but they solve different problems:

**Celery (task queue)** -- "Do this specific job later"
- You define Python functions as tasks and call them asynchronously
- Built-in retry, scheduling, result tracking
- Best for: background jobs triggered by your app (send email, generate report)

**RabbitMQ/Kafka (message queue)** -- "Something happened, whoever cares can react"
- You publish events, multiple consumers can subscribe
- Best for: decoupling services, event-driven architecture

**For your case, Celery is the right fit.** You have one app that needs to offload work. You are not decoupling multiple services (yet). Here is the architecture:

```python
# tasks.py
from celery import Celery

app = Celery('orders', broker='redis://localhost:6379/0')

@app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_order_confirmation(self, order_id, email):
    try:
        order = Order.query.get(order_id)
        send_email(
            to=email,
            subject=f"Order {order.id} confirmed",
            body=render_template("order_confirmation.html", order=order),
        )
    except EmailError as e:
        self.retry(exc=e)

@app.task(bind=True, max_retries=3)
def notify_warehouse(self, order_id):
    try:
        order = Order.query.get(order_id)
        warehouse_api.create_shipment(order)
    except WarehouseAPIError as e:
        self.retry(exc=e)

@app.task
def update_inventory(order_id):
    order = Order.query.get(order_id)
    for item in order.items:
        Product.query.filter_by(id=item.product_id).update(
            {"stock": Product.stock - item.quantity}
        )
    db.session.commit()

# checkout endpoint -- fast critical path
@app.route('/checkout', methods=['POST'])
def checkout():
    order = create_order(request.json)        # ~50ms
    charge = process_payment(order)           # ~500ms

    if charge.status != 'succeeded':
        return jsonify({"error": "Payment failed"}), 402

    # Fire and forget -- these run in background workers
    send_order_confirmation.delay(order.id, order.user.email)
    notify_warehouse.delay(order.id)
    update_inventory.delay(order.id)

    return jsonify({"order_id": order.id, "status": "confirmed"})  # ~600ms total
```

The checkout now takes ~600ms instead of 3-4 seconds. Each background task has independent retry logic. If the email server is down, it retries 3 times with 60-second delays without affecting the order.

**When to switch to RabbitMQ/Kafka:** When you split into microservices and the order service needs to publish an "order_created" event that multiple independent services (email, warehouse, analytics, fraud detection) consume. At that point, events are better than direct task calls because the order service does not need to know about every consumer.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: We are splitting our monolith into microservices. Currently everything shares one PostgreSQL database. Should each service get its own database?
Assistant: Yes, each service should own its data. A shared database creates tight coupling -- if the order service changes the users table schema, it can break the user service. Database-per-service is a core microservices principle.

User: But the order service needs user data (name, email for order confirmation) and product data (prices, stock). How does it get that without accessing those tables directly?

[Current message]
User: I see three options: (1) API calls between services, (2) duplicate the data, (3) shared database views. Which one should I pick?''',
        "output": r'''Each has tradeoffs. Here is when to use each:

**Option 1 -- Synchronous API calls (simplest start):**

```python
# Order Service calls User Service at order time
class OrderService:
    async def create_order(self, user_id, items):
        # Call user service for user info
        user = await http_client.get(f"http://user-service/users/{user_id}")
        if user.status_code != 200:
            raise ServiceUnavailableError("User service down")

        # Call product service for prices
        product_ids = [item["product_id"] for item in items]
        products = await http_client.post(
            "http://product-service/products/batch",
            json={"ids": product_ids}
        )

        order = Order(
            user_id=user_id,
            user_email=user.json()["email"],  # snapshot at order time
            items=self._build_items(items, products.json()),
        )
        db.add(order)
        db.commit()
        return order
```

- Pro: No data duplication, always fresh data
- Con: Order service fails if user service is down (temporal coupling)
- Use when: Services are reliable, latency is acceptable

**Option 2 -- Event-driven data replication (best for resilience):**

```python
# User Service publishes events when users change
@app.post("/users")
def create_user(data):
    user = User.create(data)
    # Publish event to message queue
    publish_event("user.created", {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
    })
    return user

# Order Service subscribes and keeps a local read-only copy
@consumer("user.created")
@consumer("user.updated")
def handle_user_event(event):
    # Store minimal user data needed by order service
    UserSnapshot.upsert(
        user_id=event["user_id"],
        email=event["email"],
        name=event["name"],
    )

# Now order creation is fully local -- no API calls
class OrderService:
    def create_order(self, user_id, items):
        user = UserSnapshot.query.get(user_id)
        # ... create order using local snapshot ...
```

- Pro: Order service works even if user service is down
- Con: Data can be slightly stale (eventual consistency)
- Use when: Availability is critical, slight staleness is OK

**Option 3 -- Shared database views: avoid this.** It couples service deployments and schema changes. It is a shared database with extra steps.

**My recommendation:** Start with Option 1 (API calls) for simplicity. When you hit reliability or latency issues, migrate specific data flows to Option 2 (event replication). You do not need to pick one approach for everything -- use API calls for real-time data and event replication for data that is accessed frequently but changes rarely (like user profiles).'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I need to add real-time notifications to our web app. When something happens (new message, order update, etc.), users should see it immediately without refreshing. Should I use WebSockets or long polling?
Assistant: WebSockets are the modern standard for real-time features. They maintain a persistent connection so the server can push data to clients instantly. Long polling works but is less efficient -- the client repeatedly asks "anything new?" which wastes bandwidth and adds latency.

[Current message]
User: OK, WebSockets it is. But I am worried about scaling. Our app runs on 4 servers behind a load balancer. If a user connects to server 1, but the notification is generated on server 2, how does the notification reach the user?''',
        "output": r'''This is the classic WebSocket scaling problem. The connection is to one server, but events can originate anywhere. The solution is a pub/sub layer between your servers:

**Architecture:**

```
Load Balancer
    |
    +-- Server 1 (has User A's WebSocket)
    +-- Server 2 (has User B's WebSocket)
    +-- Server 3 (has User C's WebSocket)
    +-- Server 4
    |
    All servers subscribe to Redis Pub/Sub
```

**Implementation with Socket.IO + Redis adapter:**

```javascript
// server.js -- works identically on all 4 servers
const { Server } = require('socket.io');
const { createAdapter } = require('@socket.io/redis-adapter');
const { createClient } = require('redis');

const io = new Server(httpServer, {
    cors: { origin: "https://myapp.com" },
});

// Redis adapter -- broadcasts events across all servers
const pubClient = createClient({ url: 'redis://redis-host:6379' });
const subClient = pubClient.duplicate();

Promise.all([pubClient.connect(), subClient.connect()]).then(() => {
    io.adapter(createAdapter(pubClient, subClient));
});

// Handle connections
io.on('connection', (socket) => {
    const userId = socket.handshake.auth.userId;
    // Join a room named after the user ID
    socket.join('user:' + userId);
    console.log('User connected:', userId);
});

// Send notification to a specific user (from ANY server)
function notifyUser(userId, notification) {
    // Redis adapter ensures this reaches the right server
    io.to('user:' + userId).emit('notification', notification);
}

// Example: order service triggers a notification
app.post('/internal/notify', (req, res) => {
    const { userId, type, message } = req.body;
    notifyUser(userId, { type, message, timestamp: Date.now() });
    res.json({ sent: true });
});
```

**How it works:**
1. User A connects to Server 1, joins room "user:123"
2. Server 3 processes an order and calls notifyUser("123", ...)
3. Server 3 publishes to Redis: "emit to room user:123"
4. Server 1 receives from Redis, sees User A in that room, sends the WebSocket message

**Load balancer configuration:**
- Enable sticky sessions so a client reconnects to the same server (reduces reconnection overhead)
- Or let Socket.IO handle reconnection to any server -- the Redis adapter makes it work regardless

**For the load balancer (nginx):**

```
upstream websocket_servers {
    ip_hash;  # Sticky sessions by client IP
    server server1:3000;
    server server2:3000;
    server server3:3000;
    server server4:3000;
}

location /socket.io/ {
    proxy_pass http://websocket_servers;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

This scales horizontally -- add more servers, they all join the same Redis pub/sub. Redis handles the cross-server message routing.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: Our REST API has been in production for a year with many clients. We need to make breaking changes to some endpoints (rename fields, change response structure). How should we handle API versioning?
Assistant: There are three common approaches: URL versioning (/api/v1/), header versioning (Accept: application/vnd.myapi.v1+json), and query parameter versioning (?version=1). URL versioning is the most common and easiest for clients to understand.

User: We chose URL versioning. But now I am not sure how to organize the code. Do I copy the entire v1 codebase into a v2 folder? That seems like a maintenance nightmare.

[Current message]
User: How do I structure the code so v1 and v2 can share logic but have different response formats? I do not want to maintain two copies of the same business logic.''',
        "output": r'''The key is separating business logic from response serialization. The service layer is shared; only the API layer (routes + serializers) differs per version:

```
app/
    services/           # Shared business logic -- version-agnostic
        user_service.py
        order_service.py
    models/             # Database models -- shared
        user.py
        order.py
    api/
        v1/
            routes.py
            serializers.py
        v2/
            routes.py
            serializers.py
```

```python
# services/order_service.py -- shared, no version awareness
class OrderService:
    def get_order(self, order_id):
        order = Order.query.get(order_id)
        if not order:
            raise NotFoundError("Order", order_id)
        return order  # Returns the model object

    def create_order(self, user_id, items):
        # Business logic, validation, etc.
        order = Order(user_id=user_id)
        for item in items:
            order.add_item(item["product_id"], item["quantity"])
        db.session.add(order)
        db.session.commit()
        return order

# api/v1/serializers.py -- v1 response format
def serialize_order_v1(order):
    return {
        "id": order.id,
        "user_id": order.user_id,
        "total": float(order.total),           # v1: flat number
        "status": order.status.value,
        "items": [
            {"product_id": i.product_id, "qty": i.quantity, "price": float(i.price)}
            for i in order.items
        ],
    }

# api/v2/serializers.py -- v2 response format (breaking changes)
def serialize_order_v2(order):
    return {
        "id": order.id,
        "customer": {                           # v2: nested customer object
            "id": order.user_id,
            "name": order.user.name,
        },
        "pricing": {                            # v2: structured pricing
            "subtotal": float(order.subtotal),
            "tax": float(order.tax),
            "total": float(order.total),
            "currency": "USD",
        },
        "status": order.status.value,
        "line_items": [                         # v2: renamed from "items"
            {
                "product_id": i.product_id,
                "quantity": i.quantity,          # v2: "quantity" not "qty"
                "unit_price": float(i.price),
                "line_total": float(i.price * i.quantity),
            }
            for i in order.items
        ],
        "links": {
            "self": f"/api/v2/orders/{order.id}",
        },
    }

# api/v1/routes.py
v1 = Blueprint('v1', __name__, url_prefix='/api/v1')

@v1.route('/orders/<int:order_id>')
def get_order(order_id):
    order = order_service.get_order(order_id)
    return jsonify(serialize_order_v1(order))

# api/v2/routes.py
v2 = Blueprint('v2', __name__, url_prefix='/api/v2')

@v2.route('/orders/<int:order_id>')
def get_order(order_id):
    order = order_service.get_order(order_id)
    return jsonify(serialize_order_v2(order))
```

The service layer and models are shared -- zero duplication of business logic. Only the thin route + serializer layer is versioned. When v1 is eventually deprecated, you just remove the api/v1 directory. The serializer pattern also makes it easy to test: you can unit test serializers independently from routes.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: Our app lets users upload images (profile photos, product images). Right now we save them to the local filesystem on the web server. It works fine with one server.
Assistant: Local filesystem breaks when you add a second server -- a file uploaded to server A will not be available on server B. Move to object storage like S3 or MinIO.

User: Makes sense. Should the upload go through our API server, or should the client upload directly to S3?

[Current message]
User: Our images are user-submitted product photos (2-10 MB each). We get about 500 uploads per day now but expect it to grow to 10,000+ per day. Which upload approach scales better?''',
        "output": r'''At 10,000+ uploads per day, direct-to-S3 (presigned URLs) is clearly better. Here is why and how:

**Through your server (proxy upload):**
```
Client --(10MB)--> Your API --(10MB)--> S3
```
- Your server receives the full file, then re-uploads to S3
- Ties up a server process for the entire transfer duration
- At 10K uploads/day with 5MB average: 50GB/day flowing through your servers
- Scales by adding more server instances (expensive)

**Direct to S3 (presigned URL):**
```
Client --> Your API (get presigned URL, ~50ms)
Client --(10MB)--> S3 directly
Client --> Your API (confirm upload, ~50ms)
```
- Your server only handles two tiny API calls
- S3 handles all the bandwidth (designed for this)
- Scales to millions of uploads with no infrastructure changes

**Implementation:**

```python
import boto3
from uuid import uuid4

s3 = boto3.client('s3')
BUCKET = 'myapp-uploads'
ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
MAX_SIZE = 10 * 1024 * 1024  # 10 MB

@app.post("/uploads/presign")
async def get_upload_url(
    content_type: str,
    user: dict = Depends(get_current_user),
):
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "File type not allowed")

    file_key = f"uploads/{user['id']}/{uuid4().hex}"
    extension = content_type.split('/')[-1]
    file_key += f".{extension}"

    presigned = s3.generate_presigned_post(
        Bucket=BUCKET,
        Key=file_key,
        Conditions=[
            ["content-length-range", 1, MAX_SIZE],
            {"Content-Type": content_type},
        ],
        ExpiresIn=300,  # URL valid for 5 minutes
    )

    return {
        "upload_url": presigned["url"],
        "fields": presigned["fields"],
        "file_key": file_key,
    }

@app.post("/uploads/confirm")
async def confirm_upload(
    file_key: str,
    user: dict = Depends(get_current_user),
):
    # Verify the file actually exists in S3
    try:
        head = s3.head_object(Bucket=BUCKET, Key=file_key)
    except s3.exceptions.ClientError:
        raise HTTPException(400, "File not found in storage")

    # Save reference in database
    upload = Upload(
        user_id=user["id"],
        file_key=file_key,
        size=head["ContentLength"],
        content_type=head["ContentType"],
    )
    db.add(upload)
    db.commit()

    return {"id": upload.id, "url": f"https://{BUCKET}.s3.amazonaws.com/{file_key}"}
```

**Client-side (JavaScript):**

```javascript
async function uploadImage(file) {
    // Step 1: Get presigned URL
    const presign = await fetch('/api/uploads/presign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content_type: file.type }),
    }).then(r => r.json());

    // Step 2: Upload directly to S3
    const formData = new FormData();
    Object.entries(presign.fields).forEach(([k, v]) => formData.append(k, v));
    formData.append('file', file);
    await fetch(presign.upload_url, { method: 'POST', body: formData });

    // Step 3: Confirm with your API
    return fetch('/api/uploads/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_key: presign.file_key }),
    }).then(r => r.json());
}
```

The presigned URL approach also handles security -- the URL expires in 5 minutes, enforces file size limits and content type restrictions, and the file lands in a user-specific prefix in S3.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: We are building a mobile app and a web app that share the same backend. The mobile app needs much less data per screen than the web app. With our REST API, the mobile app over-fetches a lot of data it does not need. Someone on the team suggested GraphQL.
Assistant: That is a common motivation for GraphQL -- the mobile app can request only the fields it needs, reducing bandwidth. But GraphQL adds complexity (schema management, N+1 query prevention, caching is harder). It depends on how severe the over-fetching problem is.

User: The over-fetching is pretty bad. Our /api/orders endpoint returns 40 fields per order, but the mobile app only needs 5 of them. And some screens need data from 3 different endpoints which means 3 round trips.

[Current message]
User: Before we commit to GraphQL, are there simpler solutions? Can we fix the over-fetching in REST without a full rewrite?''',
        "output": r'''Yes, there are REST solutions that fix over-fetching without the complexity of GraphQL. Try these first:

**1. Sparse fieldsets (field selection in REST):**

```python
# Let clients specify which fields they want
@app.get("/orders")
async def list_orders(
    fields: str = None,  # Comma-separated field names
    user: dict = Depends(get_current_user),
):
    orders = await get_user_orders(user["id"])

    if fields:
        allowed = {"id", "status", "total", "created_at", "item_count",
                   "shipping_address", "tracking_number", "customer_name"}
        requested = set(fields.split(",")) & allowed
        orders = [{k: o[k] for k in requested if k in o} for o in orders]

    return {"data": orders}

# Mobile: GET /orders?fields=id,status,total,created_at
# Web:    GET /orders (gets everything)
```

**2. Composite endpoints for mobile:**

Instead of 3 round trips, create a single endpoint that returns what a specific screen needs:

```python
@app.get("/mobile/order-summary/{order_id}")
async def mobile_order_summary(order_id: int):
    """Single endpoint optimized for the mobile order detail screen."""
    order = await get_order(order_id)
    return {
        "order": {
            "id": order.id,
            "status": order.status,
            "total": order.total,
            "created_at": order.created_at,
        },
        "items": [
            {"name": i.product_name, "qty": i.quantity, "price": i.price}
            for i in order.items[:5]  # Mobile only shows first 5
        ],
        "tracking": {
            "carrier": order.tracking_carrier,
            "number": order.tracking_number,
            "url": order.tracking_url,
        },
    }
```

**3. Response profiles via Accept header:**

```python
@app.get("/orders/{order_id}")
async def get_order(order_id: int, request: Request):
    order = await fetch_order(order_id)
    profile = request.headers.get("X-Response-Profile", "full")

    serializers = {
        "full": serialize_order_full,      # All 40 fields
        "summary": serialize_order_summary, # 10 key fields
        "minimal": serialize_order_minimal, # 5 fields for lists
    }

    serializer = serializers.get(profile, serializers["full"])
    return serializer(order)
```

**When to actually use GraphQL:**
- You have 10+ distinct clients (iOS, Android, web, partner APIs) with very different data needs
- Your data is highly interconnected (social graph, nested relationships)
- You have a dedicated team to maintain the GraphQL schema and optimize resolvers

For your case with 2 clients (web + mobile), sparse fieldsets plus a few composite mobile endpoints will solve the over-fetching problem with far less complexity. You can always add GraphQL later if the number of clients and data complexity grows.'''
    },
]
