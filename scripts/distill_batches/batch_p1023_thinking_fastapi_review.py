r"""Thinking-trace pairs: FastAPI code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this FastAPI code and identify issues:

```python
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import hashlib

app = FastAPI()

class UserCreate(BaseModel):
    username: str
    password: str
    email: str
    age: Optional[int]

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    password: str

def get_db():
    db = SessionLocal()
    return db

@app.post("/users", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    hashed = hashlib.md5(user.password.encode()).hexdigest()
    db_user = User(
        username=user.username,
        password=hashed,
        email=user.email,
        age=user.age
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404)
    return user

@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return users

@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    db.delete(user)
    db.commit()
    return {"status": "deleted"}

@app.put("/users/{user_id}")
def update_user(user_id: int, user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    db_user.username = user.username
    db_user.password = hashlib.md5(user.password.encode()).hexdigest()
    db_user.email = user.email
    db.commit()
    return db_user
```''', r'''<think>
Let me review this FastAPI application systematically, checking for security issues, design problems, resource management, and best practices.

1. Security issues:
- UserResponse includes the password field -- this leaks hashed passwords in API responses
- Using MD5 for password hashing -- MD5 is cryptographically broken and too fast for password hashing
- No authentication on any endpoints -- anyone can delete or update users
- No input validation on email format or password strength

2. Resource management:
- get_db() never closes the session -- it creates a SessionLocal() but has no try/finally or yield pattern. This leaks database connections on every request.

3. Error handling:
- delete_user does not check if user exists before calling db.delete(user) -- will crash with AttributeError if user is None
- update_user similarly does not check if db_user is None
- HTTPException(status_code=404) has no detail message

4. API design:
- list_users returns untyped response (no response_model), inconsistent with other endpoints
- list_users has no pagination -- will load entire user table into memory
- UserCreate is reused for update, but maybe not all fields should be required for update

5. Pydantic model design:
- UserResponse should use model_config with from_attributes=True (or orm_mode in v1) to work with SQLAlchemy models
- No separate UserUpdate model with optional fields

Let me compile a structured review.
</think>

## Code Review: FastAPI User CRUD Application

### CRITICAL - Security

**S1: Password leaked in API response (Severity: CRITICAL)**
`UserResponse` includes the `password` field. Every GET and POST response sends the hashed password to the client. Remove `password` from the response model immediately.

**S2: MD5 used for password hashing (Severity: CRITICAL)**
MD5 is cryptographically broken and far too fast for password hashing, making brute-force attacks trivial. Use `bcrypt` or `passlib` with argon2/bcrypt schemes instead.

**S3: No authentication or authorization (Severity: HIGH)**
All endpoints including DELETE and PUT are completely unprotected. Any anonymous user can delete or modify accounts.

### HIGH - Resource Leak

**R1: Database session never closed (Severity: HIGH)**
The `get_db` dependency creates a session but never closes it. This leaks one database connection per request, eventually exhausting the connection pool.

Fix:
```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### HIGH - Runtime Errors

**E1: delete_user crashes on missing user (Severity: HIGH)**
No existence check before `db.delete(user)`. If user is None, this raises `AttributeError: 'NoneType' object has no attribute...`.

**E2: update_user crashes on missing user (Severity: HIGH)**
Same problem -- attribute assignment on None when user not found.

### MEDIUM - API Design

**D1: No pagination on list_users**
`db.query(User).all()` loads every user into memory. Add `skip` and `limit` query parameters.

**D2: No response_model on list_users**
Inconsistent with other endpoints and may leak fields.

**D3: Missing detail in HTTPException**
`HTTPException(status_code=404)` should include `detail="User not found"`.

### LOW - Model Design

**M1: No orm_mode / from_attributes**
UserResponse will fail to serialize SQLAlchemy model objects without proper Pydantic configuration.

**M2: No UserUpdate model**
PUT endpoint forces all fields to be provided. Create a separate model with optional fields for partial updates (or use PATCH).

### Refactored Code

```python
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from passlib.hash import bcrypt

app = FastAPI()

class UserCreate(BaseModel):
    username: str
    password: str
    email: EmailStr
    age: Optional[int] = None

class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    email: Optional[EmailStr] = None
    age: Optional[int] = None

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    hashed = bcrypt.hash(user.password)
    db_user = User(
        username=user.username,
        password=hashed,
        email=user.email,
        age=user.age,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user
```'''),

    ("thinking/code-review", r'''Review this FastAPI code and identify issues:

```python
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import time
import json
import logging

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

request_counts = {}

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    current_time = time.time()
    if client_ip not in request_counts:
        request_counts[client_ip] = []
    request_counts[client_ip].append(current_time)
    # Keep only last 60 seconds
    request_counts[client_ip] = [
        t for t in request_counts[client_ip] if current_time - t < 60
    ]
    if len(request_counts[client_ip]) > 100:
        return Response(content="Rate limited", status_code=429)
    response = await call_next(request)
    return response

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    body = await request.body()
    logging.info(f"Request: {request.method} {request.url} Body: {body}")
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logging.info(f"Response: {response.status_code} Duration: {duration}")
    return response

@app.middleware("http")
async def error_handling_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        return Response(
            content=json.dumps({"error": str(e)}),
            status_code=500,
            media_type="application/json"
        )

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/data")
async def process_data(request: Request):
    data = await request.json()
    result = heavy_computation(data)
    return {"result": result}

def heavy_computation(data):
    time.sleep(2)
    return sum(data.get("values", []))
```''', r'''<think>
Let me review this FastAPI middleware and endpoint code carefully.

1. CORS configuration:
- allow_origins=["*"] with allow_credentials=True is invalid per the CORS spec. Browsers will reject this combination. You must specify exact origins when credentials are allowed.

2. Rate limiting middleware:
- Uses a plain dict (request_counts) -- this is not thread-safe for concurrent async requests and will not work across multiple workers/processes
- Memory leak: the dict grows unbounded since old IPs are never removed, only their timestamps are pruned
- The list comprehension filter runs on every request, which is O(n) per client

3. Logging middleware:
- await request.body() consumes the request body. This can cause issues because subsequent middleware or the endpoint may not be able to read the body again (depends on Starlette version)
- Logging raw request bodies may leak sensitive data (passwords, tokens, PII)
- Using f-strings in logging bypasses lazy formatting

4. Error handling middleware:
- In FastAPI/Starlette, exceptions raised in endpoints are typically caught by exception handlers, not middleware after call_next. The call_next function catches exceptions internally in newer versions, so this middleware may never catch anything useful.
- str(e) may leak internal details to the client

5. Middleware ordering:
- Middleware executes in reverse registration order in Starlette. The error_handling_middleware is registered last, so it runs first (outermost). Rate limiting is first registered, so it runs last (innermost). This means rate limiting happens after error handling, which is the wrong order.

6. Endpoint issues:
- process_data uses time.sleep(2) which blocks the async event loop. Should use asyncio.sleep or run_in_executor for blocking operations.
- process_data takes raw Request instead of a Pydantic model -- loses validation
- No error handling if data is not valid JSON

Let me structure the review.
</think>

## Code Review: FastAPI Middleware Stack

### CRITICAL - Security

**S1: Invalid CORS configuration (Severity: CRITICAL)**
`allow_origins=["*"]` with `allow_credentials=True` violates the CORS specification. Browsers will reject credentialed requests when the origin is a wildcard. You must list specific allowed origins when credentials are enabled.

**S2: Sensitive data in logs (Severity: HIGH)**
The logging middleware dumps the full request body including passwords, tokens, and PII. This creates compliance violations (GDPR, HIPAA) and security risks if logs are compromised.

### CRITICAL - Concurrency

**C1: Blocking call in async endpoint (Severity: CRITICAL)**
`time.sleep(2)` in `heavy_computation` blocks the entire async event loop, stalling ALL concurrent requests. Use `await asyncio.sleep()` for simulation or `await run_in_executor(None, heavy_computation, data)` for real CPU work.

**C2: Thread-unsafe rate limiter (Severity: HIGH)**
`request_counts` is a plain dict shared across async coroutines. With concurrent requests, race conditions can corrupt the dict. This also fails entirely with multiple Uvicorn workers since each process has its own dict. Use Redis or a proper rate-limiting library.

### HIGH - Memory and Performance

**M1: Unbounded memory growth in rate limiter**
Old IP keys are never evicted from `request_counts`. Over time this dict grows without bound. Only timestamps are pruned, not the keys themselves.

### HIGH - Middleware Issues

**MW1: Request body consumed in logging middleware**
`await request.body()` reads and consumes the body stream. Depending on the Starlette version, downstream middleware or the endpoint handler may receive an empty body, causing failures on POST/PUT requests.

**MW2: Middleware execution order is wrong**
Starlette executes middleware in reverse registration order. The error handler (registered last) runs outermost, meaning rate limiting runs innermost -- after the request has already been processed through logging and error handling. Rate limiting should be the outermost middleware.

**MW3: Error handling middleware is ineffective**
In modern Starlette, `call_next` does not propagate exceptions. Endpoint exceptions are converted to 500 responses before reaching middleware. Use FastAPI exception handlers instead.

### MEDIUM - Design

**D1: Raw Request instead of Pydantic model**
`process_data` manually parses JSON from Request, losing automatic validation, documentation, and type safety. Use a Pydantic model parameter instead.

### Refactored Middleware Example

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://myapp.example.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# Use a proper rate limiter like slowapi
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)
```'''),

    ("thinking/code-review", r'''Review this FastAPI code and identify issues:

```python
from fastapi import FastAPI, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import asyncio
import aiohttp

app = FastAPI()

class OrderItem(BaseModel):
    product_id: int
    quantity: int
    price: float

class Order(BaseModel):
    customer_id: int
    items: List[OrderItem]
    discount_code: Optional[str]

class OrderResponse(BaseModel):
    order_id: int
    total: float
    status: str

orders_db = []
order_counter = 0

async def get_current_user():
    return {"user_id": 1, "role": "admin"}

@app.post("/orders", response_model=OrderResponse)
async def create_order(order: Order, background_tasks: BackgroundTasks,
                       user=Depends(get_current_user)):
    global order_counter
    order_counter += 1

    total = 0
    for item in order.items:
        total += item.quantity * item.price

    if order.discount_code:
        if order.discount_code == "SAVE10":
            total = total * 0.9
        elif order.discount_code == "SAVE20":
            total = total * 0.8

    order_record = {
        "order_id": order_counter,
        "customer_id": order.customer_id,
        "items": order.items,
        "total": total,
        "status": "pending",
        "created_at": str(datetime.now()),
    }
    orders_db.append(order_record)

    background_tasks.add_task(process_payment, order_counter, total)
    background_tasks.add_task(send_confirmation_email, order.customer_id)
    background_tasks.add_task(notify_warehouse, order_record)

    return OrderResponse(order_id=order_counter, total=total, status="pending")

async def process_payment(order_id: int, amount: float):
    async with aiohttp.ClientSession() as session:
        await session.post("http://payment-service/charge",
                          json={"order_id": order_id, "amount": amount})
    for o in orders_db:
        if o["order_id"] == order_id:
            o["status"] = "paid"

async def send_confirmation_email(customer_id: int):
    async with aiohttp.ClientSession() as session:
        await session.post("http://email-service/send",
                          json={"customer_id": customer_id, "template": "order_confirm"})

async def notify_warehouse(order: dict):
    async with aiohttp.ClientSession() as session:
        await session.post("http://warehouse-service/fulfill",
                          json=order)

@app.get("/orders/{order_id}")
async def get_order(order_id: int):
    for o in orders_db:
        if o["order_id"] == order_id:
            return o
    return {"error": "not found"}
```''', r'''<think>
Let me review this order management FastAPI application.

1. Concurrency / Race conditions:
- `global order_counter` with `order_counter += 1` is not atomic. Under concurrent requests, two orders could get the same ID. This is a classic race condition in async code.
- `orders_db` (a list) is shared mutable state with no locking. Concurrent appends and iteration can lead to data corruption.

2. Background task issues:
- process_payment is a critical operation that determines if the order is valid, but it is run as a background task. The user gets a "pending" response, but if payment fails, there is no rollback mechanism.
- The background tasks have no error handling. If payment fails, the order stays "pending" forever.
- Creating a new aiohttp.ClientSession per call is wasteful -- should reuse a session.

3. Authentication:
- get_current_user always returns a hardcoded admin user. This is presumably a placeholder, but the endpoint does not verify that user.user_id matches order.customer_id.

4. Business logic:
- Discount codes are hardcoded with string comparisons. Should be in a database or configuration.
- No validation that item prices are positive or that quantities are > 0
- No validation on discount_code -- invalid codes are silently ignored rather than returning an error
- Price is supplied by the client, which is a security issue. Prices should come from the server/database.

5. API design:
- get_order returns {"error": "not found"} with status 200 instead of raising HTTPException(404). The client gets a success status code for a failed lookup.
- No authentication on get_order -- any user can view any order

6. Data storage:
- Using an in-memory list means all data is lost on restart and does not scale to multiple workers

7. Timestamp:
- str(datetime.now()) produces a non-standard format. Use datetime.utcnow().isoformat() or timezone-aware timestamps.

Let me structure this.
</think>

## Code Review: FastAPI Order Management

### CRITICAL - Race Conditions

**RC1: Non-atomic order counter (Severity: CRITICAL)**
`global order_counter; order_counter += 1` is not atomic in async Python. Two concurrent requests can read the same value, producing duplicate order IDs. Use a database sequence, UUID, or an asyncio.Lock at minimum.

**RC2: Shared mutable list without synchronization (Severity: HIGH)**
`orders_db` is appended to and iterated over concurrently with no locking. This can cause lost writes or iteration errors under load.

### CRITICAL - Security

**S1: Client-supplied prices (Severity: CRITICAL)**
`item.price` comes from the request body. A malicious client can set any price. Prices must be fetched from the server-side product catalog based on `product_id`.

**S2: No input validation on quantities (Severity: HIGH)**
Nothing prevents `quantity: -5` or `price: -100`, which would result in negative totals. Add `Field(gt=0)` constraints to the Pydantic model.

**S3: Fake authentication (Severity: HIGH)**
`get_current_user` always returns a hardcoded admin. Any user can create orders for any customer_id. Real auth is needed, and customer_id should come from the authenticated user.

### HIGH - Business Logic

**B1: Critical payment in background task (Severity: HIGH)**
Payment processing runs as a fire-and-forget background task. If it fails, the order remains "pending" with no retry, no notification, no rollback. Payment should either be synchronous or use a proper task queue with retry logic and dead-letter handling.

**B2: No error handling in background tasks**
All three background tasks make HTTP calls with no try/except. A network error crashes the background task silently.

**B3: Hardcoded discount codes**
Discount logic uses string literals. This cannot be maintained or audited. Store discount codes in a database with validation rules.

**B4: Invalid discount codes silently ignored**
If a user passes `discount_code: "INVALID"`, it is silently ignored. The user expects a discount but pays full price. Return a 400 error for unrecognized codes.

### MEDIUM - API Design

**D1: get_order returns 200 on not found**
Returning `{"error": "not found"}` with HTTP 200 breaks REST conventions. Use `raise HTTPException(status_code=404, detail="Order not found")`.

**D2: No authorization on get_order**
Any user can view any order by ID. Add ownership checks.

### LOW - Performance and Data

**P1: New aiohttp session per background task**
Creating a `ClientSession` per call is expensive. Use a shared application-scoped session via FastAPI lifespan events.

**P2: In-memory storage**
Data is lost on restart and not shared across workers. Use a database.

**P3: Non-standard timestamp**
`str(datetime.now())` is not ISO 8601 and uses local time. Use `datetime.utcnow().isoformat()` or timezone-aware datetimes.'''),

    ("thinking/code-review", r'''Review this FastAPI code and identify issues:

```python
from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum
import os

app = FastAPI()

DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY = os.environ["SECRET_KEY"]
API_KEY = "sk-hardcoded-key-12345"

class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"

class ProductFilter(BaseModel):
    category: Optional[str]
    min_price: Optional[float]
    max_price: Optional[float]
    in_stock: Optional[bool]

class Product(BaseModel):
    id: int
    name: str
    price: float
    category: str
    stock: int

def verify_api_key(api_key: str = Query(...)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key

@app.get("/products", response_model=List[Product])
async def list_products(
    skip: int = 0,
    limit: int = Query(default=100, le=10000),
    sort_by: str = "name",
    sort_order: SortOrder = SortOrder.asc,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    api_key: str = Depends(verify_api_key),
):
    query = f"SELECT * FROM products WHERE 1=1"
    if category:
        query += f" AND category = '{category}'"
    if min_price is not None:
        query += f" AND price >= {min_price}"
    if max_price is not None:
        query += f" AND price <= {max_price}"
    query += f" ORDER BY {sort_by} {sort_order.value}"
    query += f" LIMIT {limit} OFFSET {skip}"

    results = await db.fetch_all(query)
    return results

@app.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: int, api_key: str = Depends(verify_api_key)):
    query = f"SELECT * FROM products WHERE id = {product_id}"
    result = await db.fetch_one(query)
    if not result:
        raise HTTPException(status_code=404)
    return result

@app.post("/products", response_model=Product)
async def create_product(product: Product, api_key: str = Depends(verify_api_key)):
    query = f"""INSERT INTO products (name, price, category, stock)
                VALUES ('{product.name}', {product.price}, '{product.category}', {product.stock})
                RETURNING *"""
    result = await db.fetch_one(query)
    return result

@app.delete("/products/{product_id}")
async def delete_product(product_id: int, api_key: str = Depends(verify_api_key)):
    query = f"DELETE FROM products WHERE id = {product_id}"
    await db.execute(query)
    return {"deleted": True}
```''', r'''<think>
Let me analyze this product API code carefully.

1. SQL Injection -- the most critical issue:
- Every single query uses f-string interpolation to build SQL. This is textbook SQL injection vulnerability.
- `category = '{category}'` -- a user can pass `'; DROP TABLE products; --` as the category
- `sort_by` is user-supplied and directly interpolated into ORDER BY -- allows arbitrary SQL
- The INSERT statement interpolates product.name and product.category directly
- Even product_id in get_product and delete_product, while typed as int by FastAPI, the pattern is still dangerous

2. Security:
- API_KEY is hardcoded as a string literal in source code. This will be committed to version control.
- API key is passed as a query parameter, which means it appears in server logs, browser history, and referrer headers. Should use an Authorization header.
- DATABASE_URL and SECRET_KEY use os.environ[] which crashes at import time if not set. Should use a settings class or provide defaults.
- No distinction between read and write permissions -- same API key for everything

3. Authentication:
- verify_api_key compares with == which is vulnerable to timing attacks. Use secrets.compare_digest.
- 401 is returned without WWW-Authenticate header

4. API design:
- limit can be up to 10000, which is very high for a default max. This can cause memory issues.
- sort_by accepts any string, no validation against actual column names
- delete_product returns {"deleted": True} even if no row was actually deleted (the product might not exist)
- create_product uses Product model which includes `id`, but the id should be server-generated. Need a separate CreateProduct model.

5. Configuration:
- os.environ["DATABASE_URL"] will crash at module import if not set
- db object is used but never defined in the code

Let me structure the review.
</think>

## Code Review: FastAPI Product API

### CRITICAL - SQL Injection (Multiple)

**SQL1: String interpolation in all queries (Severity: CRITICAL)**
Every query in this file uses f-string formatting to insert user-supplied values directly into SQL strings. This is the most dangerous vulnerability possible in a web application.

Example attack on list_products:
```
GET /products?category=' OR 1=1; DROP TABLE products; --
```

This affects: `list_products`, `get_product`, `create_product`, `delete_product`.

**SQL2: Unvalidated ORDER BY column (Severity: CRITICAL)**
`sort_by` is a free-form string interpolated into `ORDER BY {sort_by}`. An attacker can inject arbitrary SQL. Validate against an allowlist of column names.

Fix: Use parameterized queries for all data values, and an enum/allowlist for sort columns:
```python
ALLOWED_SORT_COLUMNS = {"name", "price", "category", "stock"}
if sort_by not in ALLOWED_SORT_COLUMNS:
    raise HTTPException(400, "Invalid sort column")
query = "SELECT * FROM products WHERE category = $1"
results = await db.fetch_all(query, [category])
```

### CRITICAL - Secrets Management

**SEC1: Hardcoded API key (Severity: CRITICAL)**
`API_KEY = "sk-hardcoded-key-12345"` is in source code, which gets committed to version control. Use environment variables or a secrets manager.

**SEC2: API key in query parameter (Severity: HIGH)**
Query parameters appear in server access logs, browser history, proxy logs, and Referrer headers. Use the `Authorization` header with `Security` dependency instead.

**SEC3: Timing-vulnerable comparison (Severity: MEDIUM)**
`api_key != API_KEY` using `!=` is vulnerable to timing attacks. Use `secrets.compare_digest()`.

### HIGH - Configuration

**CFG1: Crash on missing environment variables**
`os.environ["DATABASE_URL"]` at module level crashes the application at import time if the variable is not set. Use Pydantic Settings with defaults or fail gracefully.

**CFG2: Undefined db object**
The `db` variable is used everywhere but never defined. The application will crash on every request.

### MEDIUM - API Design

**D1: Product model reused for creation**
`Product` includes `id`, but the client should not supply an ID for creation. Create a separate `ProductCreate` model without the `id` field.

**D2: delete_product always returns success**
Returns `{"deleted": True}` even if the product ID does not exist. Check the affected row count and return 404 if zero.

**D3: Excessive limit ceiling**
`le=10000` allows fetching 10,000 products in one request. Cap at a reasonable number like 100 and require explicit pagination.

### Refactored Query Example

```python
from databases import Database
import secrets

@app.get("/products", response_model=List[Product])
async def list_products(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    sort_by: str = Query(default="name"),
    api_key: str = Depends(verify_api_key),
):
    if sort_by not in ALLOWED_SORT_COLUMNS:
        raise HTTPException(400, detail="Invalid sort column")
    query = f"SELECT * FROM products ORDER BY {sort_by} LIMIT :limit OFFSET :skip"
    return await db.fetch_all(query, {"limit": limit, "skip": skip})
```'''),

    ("thinking/code-review", r'''Review this FastAPI code and identify issues:

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from typing import Dict, List
import asyncio
import json

app = FastAPI()

connected_clients: Dict[str, WebSocket] = {}
chat_history: List[dict] = []

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket)
    connected_clients[client_id] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            chat_history.append(message)
            await manager.broadcast(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        del connected_clients[client_id]

@app.get("/history")
async def get_history():
    return chat_history

@app.get("/stream")
async def stream_data():
    async def generate():
        for i in range(1000000):
            yield f"data: {json.dumps({'count': i})}\n\n"
            await asyncio.sleep(0.01)
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/clients")
async def get_clients():
    return {
        "count": len(connected_clients),
        "clients": list(connected_clients.keys())
    }

@app.post("/send/{client_id}")
async def send_to_client(client_id: str, message: dict):
    ws = connected_clients[client_id]
    await ws.send_text(json.dumps(message))
    return {"sent": True}

@app.on_event("startup")
async def startup():
    print("Server started")

@app.on_event("shutdown")
async def shutdown():
    for ws in manager.active_connections:
        await ws.close()
```''', r'''<think>
Let me review this WebSocket chat application.

1. Data structure issues:
- connected_clients and manager.active_connections store overlapping data. A client is tracked in both places, but they can get out of sync.
- chat_history grows without bound -- unbounded memory usage
- connected_clients is a global dict, not part of the ConnectionManager

2. Concurrency issues:
- broadcast() iterates over self.active_connections while sending. If a connection drops during broadcast, calling send_text on a closed WebSocket will raise an exception, which stops the broadcast to remaining clients.
- self.active_connections.remove(websocket) in disconnect() -- if called concurrently, list mutation during iteration could cause issues
- connected_clients[client_id] = websocket -- if two connections use the same client_id, the first one is silently overwritten and leaked

3. Error handling:
- json.loads(data) has no try/except. Malformed JSON from a client crashes the handler.
- send_to_client does connected_clients[client_id] with no existence check -- KeyError becomes 500.
- broadcast does not handle individual send failures

4. Security:
- No authentication on WebSocket connections or HTTP endpoints
- No rate limiting -- a client can spam messages
- No message size limits -- a client can send huge payloads
- No validation of message content
- The /clients endpoint exposes connected user IDs to anyone

5. API design:
- on_event("startup") and on_event("shutdown") are deprecated in favor of lifespan context manager
- stream_data generates 1 million events with no way to stop -- the client must disconnect
- No heartbeat/ping-pong to detect dead connections

6. Memory:
- chat_history is unbounded
- No cleanup of stale entries in connected_clients if disconnect fails

Let me write the structured review.
</think>

## Code Review: FastAPI WebSocket Chat Application

### HIGH - Concurrency and State Issues

**C1: Duplicate client tracking (Severity: HIGH)**
Clients are tracked in both `connected_clients` (dict) and `manager.active_connections` (list). These can get out of sync. For example, if disconnect raises during `self.active_connections.remove()`, the client remains in `connected_clients`. Consolidate into a single data structure inside ConnectionManager.

**C2: Client ID collision (Severity: HIGH)**
If two connections use the same `client_id`, the second silently overwrites the first in `connected_clients`. The original WebSocket is leaked (never cleaned up) and remains in `manager.active_connections`.

**C3: Broadcast failure stops delivery (Severity: HIGH)**
`broadcast()` awaits each `send_text` sequentially. If one connection has been closed but not yet cleaned up, the exception stops the loop and remaining clients never receive the message. Wrap each send in try/except or use `asyncio.gather` with `return_exceptions=True`:

```python
async def broadcast(self, message: str):
    tasks = []
    for conn in self.active_connections.copy():
        tasks.append(self._safe_send(conn, message))
    await asyncio.gather(*tasks)

async def _safe_send(self, ws: WebSocket, message: str):
    try:
        await ws.send_text(message)
    except Exception:
        self.disconnect(ws)
```

### HIGH - Error Handling

**E1: Unhandled JSON parse error (Severity: HIGH)**
`json.loads(data)` has no try/except. A client sending malformed JSON crashes the WebSocket handler, disconnecting that client without proper cleanup.

**E2: KeyError in send_to_client (Severity: MEDIUM)**
`connected_clients[client_id]` raises KeyError (returns 500) if the client is not connected. Check existence first and return 404.

### HIGH - Memory

**M1: Unbounded chat_history (Severity: HIGH)**
`chat_history.append(message)` grows forever. With active users, this will consume all available memory. Use a fixed-size deque or store in a database.

**M2: Unbounded stream endpoint (Severity: MEDIUM)**
`stream_data` generates 1,000,000 events (~2.7 hours at 10ms intervals). No cancellation mechanism, no client acknowledgment, no backpressure handling.

### MEDIUM - Security

**SEC1: No authentication**
WebSocket connections and all HTTP endpoints are open to anyone. Implement token-based auth on the WebSocket handshake.

**SEC2: No message size limits**
A client can send arbitrarily large messages, consuming server memory. Set `max_size` on the WebSocket or validate payload length.

**SEC3: Client list exposed**
`/clients` leaks connected user IDs to any caller. This should require authentication at minimum.

**SEC4: No input validation**
Messages are broadcast as-is with no content validation or sanitization. Malicious payloads (XSS content, huge messages) are relayed to all clients.

### LOW - Deprecation

**DEP1: on_event is deprecated**
`@app.on_event("startup")` and `shutdown` are deprecated. Use the lifespan context manager:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Server started")
    yield
    for ws in manager.active_connections:
        await ws.close()

app = FastAPI(lifespan=lifespan)
```

### Missing Features

- No heartbeat/ping-pong to detect dead connections
- No reconnection guidance for clients
- No message ordering or delivery guarantees
- No room/channel concept for message scoping'''),
]
