"""Documentation generation training pairs: API reference docs from code."""

pairs = [
    {
        "instruction": r'''Generate API reference documentation for these Flask endpoints:

@app.route("/api/v1/projects", methods=["GET"])
@require_auth
def list_projects():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    status = request.args.get("status", None)
    sort = request.args.get("sort", "created_at")

    query = Project.query.filter_by(owner_id=g.user.id)
    if status:
        query = query.filter_by(status=status)
    query = query.order_by(getattr(Project, sort).desc())

    result = query.paginate(page=page, per_page=per_page)
    return jsonify({
        "projects": [p.to_dict() for p in result.items],
        "total": result.total,
        "page": result.page,
        "pages": result.pages
    })


@app.route("/api/v1/projects", methods=["POST"])
@require_auth
def create_project():
    data = request.get_json()
    if not data or not data.get("name"):
        abort(400, description="name is required")

    project = Project(
        name=data["name"],
        description=data.get("description", ""),
        owner_id=g.user.id
    )
    db.session.add(project)
    db.session.commit()
    return jsonify(project.to_dict()), 201


@app.route("/api/v1/projects/<int:project_id>", methods=["DELETE"])
@require_auth
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.owner_id != g.user.id:
        abort(403, description="not authorized")
    db.session.delete(project)
    db.session.commit()
    return "", 204''',
        "output": r'''<think>
I need to generate clean API reference docs from these Flask endpoints. I should cover:
- HTTP method and path
- Authentication requirements (all have @require_auth)
- Query parameters with types and defaults
- Request body schema
- Response format with status codes
- Error responses

I will use a standard REST API documentation format with clear sections for each endpoint.
</think>

# Projects API

All endpoints require authentication via the `Authorization` header.

---

## List Projects

```
GET /api/v1/projects
```

Returns a paginated list of projects owned by the authenticated user.

**Query Parameters**

| Parameter  | Type   | Default      | Description                          |
|------------|--------|--------------|--------------------------------------|
| page       | int    | 1            | Page number (1-indexed)              |
| per_page   | int    | 20           | Results per page                     |
| status     | string | (none)       | Filter by status (e.g., "active")    |
| sort       | string | "created_at" | Field to sort by (descending order)  |

**Response** `200 OK`

```json
{
    "projects": [{"id": 1, "name": "...", "status": "..."}],
    "total": 42,
    "page": 1,
    "pages": 3
}
```

---

## Create Project

```
POST /api/v1/projects
```

**Request Body** (JSON)

| Field       | Type   | Required | Description              |
|-------------|--------|----------|--------------------------|
| name        | string | yes      | Project name             |
| description | string | no       | Project description      |

**Response** `201 Created`

Returns the created project object.

**Errors**

- `400 Bad Request` -- request body missing or `name` not provided.

---

## Delete Project

```
DELETE /api/v1/projects/{project_id}
```

**Path Parameters**

| Parameter  | Type | Description         |
|------------|------|---------------------|
| project_id | int  | ID of the project   |

**Response** `204 No Content`

Empty response body on success.

**Errors**

- `403 Forbidden` -- authenticated user does not own the project.
- `404 Not Found` -- project with the given ID does not exist.'''
    },
    {
        "instruction": r'''Write API documentation for this FastAPI router:

router = APIRouter(prefix="/api/search", tags=["search"])

@router.get("/")
async def search(
    q: str = Query(..., min_length=1, max_length=200),
    category: Optional[str] = Query(None, regex="^[a-z_]+$"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    sort_by: str = Query("relevance", regex="^(relevance|date|popularity)$"),
):
    results = await search_service.search(
        query=q, category=category, offset=(page - 1) * limit,
        limit=limit, sort=sort_by
    )
    return {
        "query": q,
        "results": results.items,
        "total_hits": results.total,
        "page": page,
        "has_more": (page * limit) < results.total,
    }

@router.get("/suggest")
async def suggest(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(5, ge=1, le=20),
):
    suggestions = await search_service.autocomplete(q, limit=limit)
    return {"suggestions": suggestions}''',
        "output": r'''# Search API Reference

Base path: `/api/search`

---

## Full-Text Search

```
GET /api/search/
```

Performs a full-text search across indexed content and returns paginated results.

**Query Parameters**

| Parameter | Type   | Required | Constraints                          | Default     | Description                |
|-----------|--------|----------|--------------------------------------|-------------|----------------------------|
| q         | string | yes      | 1-200 characters                     | --          | Search query string        |
| category  | string | no       | lowercase letters and underscores    | null        | Filter by content category |
| page      | int    | no       | >= 1                                 | 1           | Page number                |
| limit     | int    | no       | 1-100                                | 10          | Results per page           |
| sort_by   | string | no       | "relevance", "date", or "popularity" | "relevance" | Sort order for results     |

**Success Response** `200 OK`

```json
{
    "query": "search terms",
    "results": [
        {"id": "...", "title": "...", "snippet": "..."}
    ],
    "total_hits": 142,
    "page": 1,
    "has_more": true
}
```

**Error Responses**

- `422 Unprocessable Entity` -- validation failure (e.g., query too long, invalid sort_by value)

---

## Autocomplete Suggestions

```
GET /api/search/suggest
```

Returns autocomplete suggestions as the user types.

**Query Parameters**

| Parameter | Type   | Required | Constraints    | Default | Description            |
|-----------|--------|----------|----------------|---------|------------------------|
| q         | string | yes      | 2-100 chars    | --      | Partial query string   |
| limit     | int    | no       | 1-20           | 5       | Max suggestions to return |

**Success Response** `200 OK`

```json
{
    "suggestions": ["python tutorial", "python async", "python dataclass"]
}
```'''
    },
    {
        "instruction": r'''Document the request and response formats for this Express.js middleware and endpoint:

// auth middleware
const authenticate = async (req, res, next) => {
  const token = req.headers.authorization?.replace('Bearer ', '');
  if (!token) return res.status(401).json({ error: 'Token required' });

  try {
    const payload = jwt.verify(token, process.env.JWT_SECRET);
    req.user = await User.findById(payload.sub);
    if (!req.user) return res.status(401).json({ error: 'User not found' });
    next();
  } catch (err) {
    return res.status(401).json({ error: 'Invalid token' });
  }
};

// file upload endpoint
router.post('/files/upload',
  authenticate,
  upload.single('file'),
  async (req, res) => {
    if (!req.file) return res.status(400).json({ error: 'No file provided' });
    if (req.file.size > 10 * 1024 * 1024) {
      return res.status(413).json({ error: 'File exceeds 10MB limit' });
    }

    const record = await FileRecord.create({
      filename: req.file.originalname,
      mimetype: req.file.mimetype,
      size: req.file.size,
      path: req.file.path,
      uploadedBy: req.user._id,
    });

    res.status(201).json({
      id: record._id,
      filename: record.filename,
      mimetype: record.mimetype,
      size: record.size,
      uploadedAt: record.createdAt,
    });
  }
);''',
        "output": r'''<think>
I need to document this Express.js file upload endpoint. Key things:
- Authentication via Bearer token (middleware)
- Multipart form upload using multer (upload.single)
- File size limit of 10MB
- Request is multipart/form-data, not JSON
- Response includes the created file record

I should document the auth header requirement, the multipart form field name, size limits, and all possible error responses.
</think>

# File Upload API

## Authentication

All requests must include a valid JWT Bearer token.

```
Authorization: Bearer <jwt_token>
```

The token payload must contain a `sub` claim with a valid user ID. Returns `401 Unauthorized` if the token is missing, expired, or the user no longer exists.

---

## Upload File

```
POST /files/upload
```

Upload a single file. The request must use `multipart/form-data` encoding.

**Request Headers**

| Header        | Value                        | Required |
|---------------|------------------------------|----------|
| Authorization | Bearer {token}               | yes      |
| Content-Type  | multipart/form-data          | yes      |

**Form Fields**

| Field | Type | Required | Description                    |
|-------|------|----------|--------------------------------|
| file  | file | yes      | The file to upload (max 10MB)  |

**Example (curl)**

```bash
curl -X POST https://api.example.com/files/upload \
  -H "Authorization: Bearer eyJhbG..." \
  -F "file=@report.pdf"
```

**Success Response** `201 Created`

```json
{
    "id": "64a7f2...",
    "filename": "report.pdf",
    "mimetype": "application/pdf",
    "size": 245760,
    "uploadedAt": "2024-07-15T10:30:00.000Z"
}
```

**Error Responses**

| Status | Body                              | Cause                          |
|--------|-----------------------------------|--------------------------------|
| 400    | {"error": "No file provided"}     | Missing file in form data      |
| 401    | {"error": "Token required"}       | No Authorization header        |
| 401    | {"error": "Invalid token"}        | Expired or malformed JWT       |
| 401    | {"error": "User not found"}       | Token references deleted user  |
| 413    | {"error": "File exceeds 10MB..."}  | File larger than 10MB          |'''
    },
    {
        "instruction": r'''Write API docs for this gRPC service definition:

service OrderService {
  rpc CreateOrder(CreateOrderRequest) returns (Order);
  rpc GetOrder(GetOrderRequest) returns (Order);
  rpc ListOrders(ListOrdersRequest) returns (ListOrdersResponse);
  rpc CancelOrder(CancelOrderRequest) returns (CancelOrderResponse);
  rpc StreamOrderUpdates(StreamOrderRequest) returns (stream OrderUpdate);
}

message CreateOrderRequest {
  string product_id = 1;
  int32 quantity = 2;
  string shipping_address = 3;
  PaymentMethod payment = 4;
}

message Order {
  string id = 1;
  string product_id = 2;
  int32 quantity = 3;
  string status = 4;
  double total_price = 5;
  google.protobuf.Timestamp created_at = 6;
}

message ListOrdersRequest {
  int32 page_size = 1;
  string page_token = 2;
  string status_filter = 3;
}

message ListOrdersResponse {
  repeated Order orders = 1;
  string next_page_token = 2;
  int32 total_count = 3;
}''',
        "output": r'''# OrderService -- gRPC API Reference

## Service Overview

The OrderService provides order lifecycle management including creation, retrieval, cancellation, and real-time status streaming.

---

## Methods

### CreateOrder

Creates a new order for the specified product.

- **Request:** `CreateOrderRequest`
- **Response:** `Order`
- **Errors:** `INVALID_ARGUMENT` if required fields are missing; `NOT_FOUND` if product_id is invalid.

| Field            | Type          | Number | Description                    |
|------------------|---------------|--------|--------------------------------|
| product_id       | string        | 1      | ID of the product to order     |
| quantity         | int32         | 2      | Number of units (must be > 0)  |
| shipping_address | string        | 3      | Full shipping address          |
| payment          | PaymentMethod | 4      | Payment method details         |

### GetOrder

Retrieves a single order by ID.

- **Request:** `GetOrderRequest` (contains order `id` field)
- **Response:** `Order`
- **Errors:** `NOT_FOUND` if the order does not exist; `PERMISSION_DENIED` if the caller does not own the order.

### ListOrders

Returns a paginated list of orders. Accepts `page_size` (default 20), `page_token` (from previous response), and `status_filter`. Response includes `orders` list, `next_page_token`, and `total_count`.

### CancelOrder

Cancels a pending or processing order. Returns `FAILED_PRECONDITION` if already shipped.

### StreamOrderUpdates

Server-streaming RPC that pushes real-time status changes. The stream stays open until the order reaches a terminal state or the client disconnects.

### Order (common response type)

| Field       | Type      | Number | Description               |
|-------------|-----------|--------|---------------------------|
| id          | string    | 1      | Unique order identifier   |
| product_id  | string    | 2      | Ordered product ID        |
| quantity    | int32     | 3      | Quantity ordered           |
| status      | string    | 4      | Current status            |
| total_price | double    | 5      | Total price in USD        |
| created_at  | Timestamp | 6      | When the order was placed |'''
    },
    {
        "instruction": r'''Generate API reference documentation for this Python SDK client class:

class StorageClient:
    def __init__(self, api_key, region="us-east-1", timeout=30):
        self.session = requests.Session()
        self.session.headers["X-API-Key"] = api_key
        self.base_url = f"https://storage.{region}.example.com/v2"
        self.timeout = timeout

    def upload(self, bucket, key, data, content_type="application/octet-stream", metadata=None):
        headers = {"Content-Type": content_type}
        if metadata:
            for k, v in metadata.items():
                headers[f"X-Meta-{k}"] = str(v)
        resp = self.session.put(
            f"{self.base_url}/buckets/{bucket}/objects/{key}",
            data=data, headers=headers, timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    def download(self, bucket, key):
        resp = self.session.get(
            f"{self.base_url}/buckets/{bucket}/objects/{key}",
            timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.content

    def delete(self, bucket, key):
        resp = self.session.delete(
            f"{self.base_url}/buckets/{bucket}/objects/{key}",
            timeout=self.timeout
        )
        resp.raise_for_status()

    def list_objects(self, bucket, prefix="", max_keys=1000, continuation_token=None):
        params = {"prefix": prefix, "max_keys": max_keys}
        if continuation_token:
            params["continuation_token"] = continuation_token
        resp = self.session.get(
            f"{self.base_url}/buckets/{bucket}/objects",
            params=params, timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()''',
        "output": r'''# StorageClient SDK Reference

```python
client = StorageClient(api_key, region="us-east-1", timeout=30)
```

| Parameter | Type | Default     | Description                          |
|-----------|------|-------------|--------------------------------------|
| api_key   | str  | (required)  | API key for authentication           |
| region    | str  | "us-east-1" | Deployment region (affects base URL) |
| timeout   | int  | 30          | Request timeout in seconds           |

---

### upload(bucket, key, data, content_type, metadata)

Upload an object to a bucket. Overwrites existing objects at the same key.

```python
result = client.upload("my-bucket", "reports/q4.pdf", pdf_bytes,
                       content_type="application/pdf",
                       metadata={"author": "alice"})
```

| Parameter    | Type         | Default                    | Description                     |
|--------------|--------------|----------------------------|---------------------------------|
| bucket       | str          | (required)                 | Target bucket name              |
| key          | str          | (required)                 | Object key (path within bucket) |
| data         | bytes or str | (required)                 | Object content                  |
| content_type | str          | "application/octet-stream" | MIME type of the object         |
| metadata     | dict / None  | None                       | Custom metadata key-value pairs |

**Returns:** dict with upload confirmation. **Raises:** `requests.HTTPError`.

---

### download(bucket, key)

Download an object. Returns `bytes`. Raises `HTTPError` (404 if missing).

### delete(bucket, key)

Delete an object. Returns None. Raises `HTTPError` (404 if missing).

### list_objects(bucket, prefix, max_keys, continuation_token)

List objects with optional prefix filtering and pagination.

```python
result = client.list_objects("my-bucket", prefix="reports/", max_keys=50)
next_page = client.list_objects("my-bucket", prefix="reports/",
                                continuation_token=result["next_token"])
```

| Parameter          | Type       | Default | Description                          |
|--------------------|------------|---------|--------------------------------------|
| prefix             | str        | ""      | Filter keys starting with this value |
| max_keys           | int        | 1000    | Maximum number of keys to return     |
| continuation_token | str / None | None    | Pagination token from prior response |

**Returns:** dict with "objects" list, "next_token", and "is_truncated" flag.'''
    },
]
