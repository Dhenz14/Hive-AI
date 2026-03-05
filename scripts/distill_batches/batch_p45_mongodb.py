"""MongoDB — document modeling, queries, aggregation, indexing, and transactions."""

PAIRS = [
    (
        "mongodb/document-modeling",
        "Show MongoDB document modeling patterns: embedding vs referencing, schema design for common use cases, and polymorphic patterns.",
        '''MongoDB document modeling patterns:

```python
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
from pymongo.collection import Collection
from datetime import datetime, timezone
from bson import ObjectId
from typing import Optional
import re

client = MongoClient("mongodb://localhost:27017")
db = client["myapp"]


# --- Embedded document pattern (1:few, read-together) ---

# User with embedded addresses (always fetched together)
user_doc = {
    "_id": ObjectId(),
    "email": "user@example.com",
    "name": "Alice",
    "created_at": datetime.now(timezone.utc),
    "profile": {
        "bio": "Software engineer",
        "avatar_url": "/avatars/alice.jpg",
        "social": {"github": "alice", "twitter": "@alice"},
    },
    "addresses": [
        {
            "type": "home",
            "street": "123 Main St",
            "city": "Portland",
            "state": "OR",
            "zip": "97201",
            "is_default": True,
        },
        {
            "type": "work",
            "street": "456 Tech Ave",
            "city": "Portland",
            "state": "OR",
            "zip": "97204",
            "is_default": False,
        },
    ],
    "preferences": {
        "theme": "dark",
        "notifications": {"email": True, "push": False},
        "language": "en",
    },
}


# --- Reference pattern (1:many, independent access) ---

# Order references user by ID
order_doc = {
    "_id": ObjectId(),
    "user_id": ObjectId("..."),  # Reference to users collection
    "status": "confirmed",
    "items": [
        {
            "product_id": ObjectId("..."),
            "name": "Widget",          # Denormalized for read perf
            "price": 29.99,
            "quantity": 2,
            "sku": "WDG-001",
        },
    ],
    "totals": {
        "subtotal": 59.98,
        "tax": 5.40,
        "shipping": 5.00,
        "total": 70.38,
    },
    "shipping_address": {              # Snapshot at order time
        "street": "123 Main St",
        "city": "Portland",
        "state": "OR",
        "zip": "97201",
    },
    "created_at": datetime.now(timezone.utc),
    "updated_at": datetime.now(timezone.utc),
}


# --- Polymorphic pattern (different types in one collection) ---

# Events collection with varying shapes
base_event = {
    "type": "page_view",
    "user_id": ObjectId("..."),
    "timestamp": datetime.now(timezone.utc),
    "metadata": {"url": "/products/123", "referrer": "google.com"},
}

purchase_event = {
    "type": "purchase",
    "user_id": ObjectId("..."),
    "timestamp": datetime.now(timezone.utc),
    "metadata": {
        "order_id": ObjectId("..."),
        "amount": 70.38,
        "items_count": 2,
    },
}


# --- Bucket pattern (time-series optimization) ---

# Instead of one doc per measurement, bucket by hour
sensor_bucket = {
    "sensor_id": "temp-001",
    "bucket_start": datetime(2024, 1, 15, 10, 0, 0),
    "bucket_end": datetime(2024, 1, 15, 11, 0, 0),
    "count": 60,
    "measurements": [
        {"ts": datetime(2024, 1, 15, 10, 0, 0), "value": 22.5},
        {"ts": datetime(2024, 1, 15, 10, 1, 0), "value": 22.6},
        # ... up to 60 per bucket
    ],
    "summary": {"min": 22.1, "max": 23.4, "avg": 22.7},
}


# --- Indexes ---

def setup_indexes(db):
    # Single field
    db.users.create_index("email", unique=True)

    # Compound index (query + sort order matters)
    db.orders.create_index([
        ("user_id", ASCENDING),
        ("created_at", DESCENDING),
    ])

    # Text index for search
    db.products.create_index([
        ("name", TEXT),
        ("description", TEXT),
    ], default_language="english")

    # TTL index (auto-delete after 30 days)
    db.sessions.create_index(
        "created_at", expireAfterSeconds=30 * 24 * 3600
    )

    # Partial index (only index active users)
    db.users.create_index(
        "last_login",
        partialFilterExpression={"status": "active"},
    )

    # Wildcard index (dynamic fields)
    db.events.create_index({"metadata.$**": 1})
```

Modeling rules:
1. **Embed** when data is read together and rarely exceeds 16MB doc limit
2. **Reference** when data is accessed independently or grows unbounded
3. **Denormalize** read-heavy fields (copy name/price into order items)
4. **Bucket** time-series data to reduce document count
5. **Index** query patterns, not fields — compound indexes cover multiple queries'''
    ),
    (
        "mongodb/aggregation-pipeline",
        "Show MongoDB aggregation pipeline patterns: match, group, lookup, unwind, faceted search, and window functions.",
        '''MongoDB aggregation pipeline patterns:

```python
from pymongo import MongoClient
from datetime import datetime, timezone, timedelta
from bson import ObjectId

db = MongoClient("mongodb://localhost:27017")["myapp"]


# --- Sales analytics pipeline ---

def get_monthly_revenue(year: int):
    """Revenue by category per month."""
    return list(db.orders.aggregate([
        # Stage 1: Filter by year and completed orders
        {"$match": {
            "status": "completed",
            "created_at": {
                "$gte": datetime(year, 1, 1),
                "$lt": datetime(year + 1, 1, 1),
            },
        }},

        # Stage 2: Unwind order items
        {"$unwind": "$items"},

        # Stage 3: Group by month and category
        {"$group": {
            "_id": {
                "month": {"$month": "$created_at"},
                "category": "$items.category",
            },
            "revenue": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}},
            "order_count": {"$sum": 1},
            "avg_order_value": {"$avg": {"$multiply": ["$items.price", "$items.quantity"]}},
        }},

        # Stage 4: Sort
        {"$sort": {"_id.month": 1, "revenue": -1}},

        # Stage 5: Reshape output
        {"$project": {
            "_id": 0,
            "month": "$_id.month",
            "category": "$_id.category",
            "revenue": {"$round": ["$revenue", 2]},
            "order_count": 1,
            "avg_order_value": {"$round": ["$avg_order_value", 2]},
        }},
    ]))


# --- Lookup (join) with nested pipeline ---

def get_orders_with_user_details(limit: int = 20):
    """Join orders with user info."""
    return list(db.orders.aggregate([
        {"$sort": {"created_at": -1}},
        {"$limit": limit},

        # Left join to users
        {"$lookup": {
            "from": "users",
            "localField": "user_id",
            "foreignField": "_id",
            "as": "user",
            "pipeline": [
                {"$project": {"name": 1, "email": 1, "tier": 1}},
            ],
        }},
        {"$unwind": "$user"},

        # Computed fields
        {"$addFields": {
            "item_count": {"$size": "$items"},
            "is_high_value": {"$gte": ["$totals.total", 100]},
        }},
    ]))


# --- Faceted search (multiple aggregations in parallel) ---

def search_products(query: str, filters: dict, page: int = 1, per_page: int = 20):
    """Search with facets for filtering UI."""
    match_stage = {"$match": {"$text": {"$search": query}}}
    if filters.get("category"):
        match_stage["$match"]["category"] = filters["category"]
    if filters.get("price_min"):
        match_stage["$match"]["price"] = {"$gte": filters["price_min"]}

    return db.products.aggregate([
        match_stage,
        {"$facet": {
            # Results page
            "results": [
                {"$sort": {"score": {"$meta": "textScore"}, "price": 1}},
                {"$skip": (page - 1) * per_page},
                {"$limit": per_page},
                {"$project": {
                    "name": 1, "price": 1, "category": 1,
                    "score": {"$meta": "textScore"},
                }},
            ],

            # Category facet
            "categories": [
                {"$group": {"_id": "$category", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ],

            # Price ranges facet
            "price_ranges": [
                {"$bucket": {
                    "groupBy": "$price",
                    "boundaries": [0, 25, 50, 100, 250, 500, 1000],
                    "default": "1000+",
                    "output": {"count": {"$sum": 1}},
                }},
            ],

            # Total count
            "total": [{"$count": "count"}],
        }},
    ]).next()


# --- Window functions (MongoDB 5.0+) ---

def get_running_totals():
    """Running totals and rankings per category."""
    return list(db.orders.aggregate([
        {"$match": {"status": "completed"}},
        {"$group": {
            "_id": {
                "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "category": "$category",
            },
            "daily_revenue": {"$sum": "$totals.total"},
        }},
        {"$setWindowFields": {
            "partitionBy": "$_id.category",
            "sortBy": {"_id.date": 1},
            "output": {
                "running_total": {
                    "$sum": "$daily_revenue",
                    "window": {"documents": ["unbounded", "current"]},
                },
                "moving_avg_7d": {
                    "$avg": "$daily_revenue",
                    "window": {"range": [-7, "current"], "unit": "day"},
                },
                "rank": {
                    "$rank": {},
                },
            },
        }},
    ]))


# --- Transactions (multi-document ACID) ---

def transfer_funds(from_id: ObjectId, to_id: ObjectId, amount: float):
    """Atomic fund transfer using transactions."""
    with client.start_session() as session:
        with session.start_transaction():
            # Debit source
            result = db.accounts.update_one(
                {"_id": from_id, "balance": {"$gte": amount}},
                {"$inc": {"balance": -amount}},
                session=session,
            )
            if result.modified_count == 0:
                raise ValueError("Insufficient funds")

            # Credit destination
            db.accounts.update_one(
                {"_id": to_id},
                {"$inc": {"balance": amount}},
                session=session,
            )

            # Record transaction
            db.transactions.insert_one({
                "from": from_id,
                "to": to_id,
                "amount": amount,
                "timestamp": datetime.now(timezone.utc),
            }, session=session)
```

Pipeline tips:
1. **$match early** — filter first to reduce documents in later stages
2. **$project early** — drop unneeded fields to reduce memory
3. **$lookup with pipeline** — filter joined docs server-side, not client-side
4. **$facet** — run multiple aggregations in one query for search UIs
5. **Indexes** — aggregation uses indexes only for initial $match and $sort'''
    ),
    (
        "mongodb/crud-patterns",
        "Show MongoDB CRUD patterns with pymongo: bulk operations, change streams, and schema validation.",
        '''MongoDB CRUD and operational patterns:

```python
from pymongo import MongoClient, UpdateOne, InsertOne, ReplaceOne
from pymongo.errors import BulkWriteError, DuplicateKeyError
from datetime import datetime, timezone
from bson import ObjectId
from typing import Optional

client = MongoClient("mongodb://localhost:27017")
db = client["myapp"]


# --- Repository pattern ---

class UserRepository:
    def __init__(self, collection):
        self.col = collection

    def find_by_id(self, user_id: str) -> Optional[dict]:
        return self.col.find_one({"_id": ObjectId(user_id)})

    def find_by_email(self, email: str) -> Optional[dict]:
        return self.col.find_one({"email": email.lower()})

    def search(self, query: str, skip: int = 0, limit: int = 20) -> list:
        cursor = self.col.find(
            {"$text": {"$search": query}},
            {"score": {"$meta": "textScore"}},
        ).sort(
            [("score", {"$meta": "textScore"})]
        ).skip(skip).limit(limit)
        return list(cursor)

    def create(self, data: dict) -> str:
        data["created_at"] = datetime.now(timezone.utc)
        data["updated_at"] = data["created_at"]
        data["email"] = data["email"].lower()
        try:
            result = self.col.insert_one(data)
            return str(result.inserted_id)
        except DuplicateKeyError:
            raise ValueError(f"Email already exists: {data['email']}")

    def update(self, user_id: str, updates: dict) -> bool:
        updates["updated_at"] = datetime.now(timezone.utc)
        result = self.col.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": updates},
        )
        return result.modified_count > 0

    def add_to_set(self, user_id: str, field: str, value) -> bool:
        """Add to array only if not already present."""
        result = self.col.update_one(
            {"_id": ObjectId(user_id)},
            {"$addToSet": {field: value}},
        )
        return result.modified_count > 0

    def increment(self, user_id: str, field: str, amount: int = 1) -> bool:
        result = self.col.update_one(
            {"_id": ObjectId(user_id)},
            {"$inc": {field: amount}},
        )
        return result.modified_count > 0

    def soft_delete(self, user_id: str) -> bool:
        return self.update(user_id, {
            "status": "deleted",
            "deleted_at": datetime.now(timezone.utc),
        })


# --- Bulk operations ---

def bulk_upsert_products(products: list[dict]):
    """Upsert many products efficiently."""
    operations = [
        UpdateOne(
            {"sku": p["sku"]},
            {
                "$set": {**p, "updated_at": datetime.now(timezone.utc)},
                "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
        for p in products
    ]

    try:
        result = db.products.bulk_write(operations, ordered=False)
        return {
            "inserted": result.upserted_count,
            "modified": result.modified_count,
            "errors": 0,
        }
    except BulkWriteError as e:
        return {
            "inserted": e.details.get("nUpserted", 0),
            "modified": e.details.get("nModified", 0),
            "errors": len(e.details.get("writeErrors", [])),
        }


# --- Change streams (real-time) ---

def watch_orders():
    """React to order changes in real-time."""
    pipeline = [
        {"$match": {
            "operationType": {"$in": ["insert", "update"]},
            "fullDocument.status": {"$in": ["confirmed", "shipped"]},
        }},
    ]

    with db.orders.watch(pipeline, full_document="updateLookup") as stream:
        for change in stream:
            op = change["operationType"]
            doc = change["fullDocument"]

            if op == "insert" and doc["status"] == "confirmed":
                send_confirmation_email(doc)
            elif doc["status"] == "shipped":
                send_shipping_notification(doc)


# --- Cursor-based pagination (efficient for large datasets) ---

def paginate_cursor(collection, filter_query: dict,
                    last_id: Optional[str] = None, limit: int = 20):
    """Cursor-based pagination using _id."""
    query = {**filter_query}
    if last_id:
        query["_id"] = {"$gt": ObjectId(last_id)}

    results = list(
        collection.find(query).sort("_id", 1).limit(limit + 1)
    )

    has_next = len(results) > limit
    results = results[:limit]

    return {
        "data": results,
        "next_cursor": str(results[-1]["_id"]) if has_next else None,
        "has_next": has_next,
    }


# --- Schema validation ---

def setup_schema_validation():
    db.create_collection("users", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["email", "name", "created_at"],
            "properties": {
                "email": {
                    "bsonType": "string",
                    "pattern": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
                    "description": "Must be a valid email",
                },
                "name": {
                    "bsonType": "string",
                    "minLength": 1,
                    "maxLength": 100,
                },
                "age": {
                    "bsonType": "int",
                    "minimum": 0,
                    "maximum": 150,
                },
                "status": {
                    "enum": ["active", "inactive", "deleted"],
                },
                "created_at": {"bsonType": "date"},
            },
        },
    })
```

CRUD patterns:
1. **Repository pattern** — encapsulate collection operations with typed methods
2. **Bulk writes** — `ordered=False` for parallel execution, handle partial failures
3. **Change streams** — real-time reactions without polling
4. **Cursor pagination** — use `_id` cursors instead of skip/limit for large datasets
5. **Schema validation** — enforce structure at database level'''
    ),
]
"""
