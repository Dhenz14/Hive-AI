"""GraphQL — schema design, resolvers, dataloaders, subscriptions, and federation."""

PAIRS = [
    (
        "graphql/schema-design",
        "Show GraphQL schema design patterns: types, interfaces, enums, input types, and pagination with Strawberry.",
        '''GraphQL schema design with Strawberry (Python):

```python
import strawberry
from strawberry.types import Info
from strawberry.scalars import JSON
from strawberry.permission import BasePermission
from typing import Optional, Annotated
from datetime import datetime
from enum import Enum


# --- Enums ---

@strawberry.enum
class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

@strawberry.enum
class SortDirection(Enum):
    ASC = "asc"
    DESC = "desc"


# --- Types ---

@strawberry.type
class User:
    id: strawberry.ID
    email: str
    name: str
    created_at: datetime

    @strawberry.field
    async def orders(
        self,
        info: Info,
        status: Optional[OrderStatus] = None,
        first: int = 10,
        after: Optional[str] = None,
    ) -> "OrderConnection":
        """Lazy-loaded with cursor pagination."""
        loader = info.context["order_loader"]
        return await loader.load_for_user(self.id, status, first, after)

    @strawberry.field
    async def order_count(self, info: Info) -> int:
        return await info.context["order_repo"].count_by_user(self.id)


@strawberry.type
class Product:
    id: strawberry.ID
    name: str
    price: float
    category: str
    in_stock: bool

    @strawberry.field
    async def reviews(self, info: Info, limit: int = 5) -> list["Review"]:
        loader = info.context["review_loader"]
        return await loader.load(self.id)


@strawberry.type
class Order:
    id: strawberry.ID
    status: OrderStatus
    total: float
    created_at: datetime

    @strawberry.field
    async def user(self, info: Info) -> User:
        return await info.context["user_loader"].load(self.user_id)

    @strawberry.field
    async def items(self, info: Info) -> list["OrderItem"]:
        return await info.context["order_item_loader"].load(self.id)

@strawberry.type
class OrderItem:
    product_id: strawberry.ID
    product_name: str
    quantity: int
    unit_price: float

@strawberry.type
class Review:
    id: strawberry.ID
    rating: int
    comment: str
    author: str
    created_at: datetime


# --- Cursor-based pagination ---

@strawberry.type
class PageInfo:
    has_next_page: bool
    has_previous_page: bool
    start_cursor: Optional[str] = None
    end_cursor: Optional[str] = None

@strawberry.type
class OrderEdge:
    cursor: str
    node: Order

@strawberry.type
class OrderConnection:
    edges: list[OrderEdge]
    page_info: PageInfo
    total_count: int


# --- Input types ---

@strawberry.input
class CreateOrderInput:
    items: list["OrderItemInput"]
    shipping_address: "AddressInput"
    notes: Optional[str] = None

@strawberry.input
class OrderItemInput:
    product_id: strawberry.ID
    quantity: int

@strawberry.input
class AddressInput:
    street: str
    city: str
    state: str
    zip_code: str

@strawberry.input
class ProductFilterInput:
    category: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    in_stock: Optional[bool] = None
    search: Optional[str] = None


# --- Permissions ---

class IsAuthenticated(BasePermission):
    message = "User is not authenticated"

    async def has_permission(self, source, info: Info, **kwargs) -> bool:
        return info.context.get("user") is not None

class IsAdmin(BasePermission):
    message = "Admin access required"

    async def has_permission(self, source, info: Info, **kwargs) -> bool:
        user = info.context.get("user")
        return user and user.role == "admin"


# --- Query ---

@strawberry.type
class Query:
    @strawberry.field
    async def me(self, info: Info) -> Optional[User]:
        user = info.context.get("user")
        if not user:
            return None
        return await info.context["user_repo"].find_by_id(user.id)

    @strawberry.field
    async def products(
        self,
        info: Info,
        filter: Optional[ProductFilterInput] = None,
        sort_by: str = "name",
        sort_dir: SortDirection = SortDirection.ASC,
        first: int = 20,
        after: Optional[str] = None,
    ) -> list[Product]:
        return await info.context["product_repo"].search(
            filter=filter, sort_by=sort_by, sort_dir=sort_dir,
            limit=first, cursor=after,
        )

    @strawberry.field(permission_classes=[IsAuthenticated])
    async def order(self, info: Info, id: strawberry.ID) -> Optional[Order]:
        return await info.context["order_repo"].find_by_id(id)


# --- Mutation ---

@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsAuthenticated])
    async def create_order(self, info: Info, input: CreateOrderInput) -> Order:
        user = info.context["user"]
        return await info.context["order_service"].create(user.id, input)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def update_product_price(
        self, info: Info, product_id: strawberry.ID, price: float
    ) -> Product:
        return await info.context["product_repo"].update_price(product_id, price)


schema = strawberry.Schema(query=Query, mutation=Mutation)
```

GraphQL schema patterns:
1. **Relay-style pagination** — cursor-based with `Connection`, `Edge`, `PageInfo`
2. **Input types** — separate types for mutations (never reuse output types)
3. **Lazy loading** — resolve nested fields with DataLoaders to avoid N+1
4. **Permission classes** — declarative auth on fields and mutations
5. **Enums** — type-safe filter and status values'''
    ),
    (
        "graphql/dataloaders",
        "Show GraphQL DataLoader patterns: batching, caching, and N+1 query prevention.",
        '''DataLoader patterns for efficient GraphQL resolution:

```python
from strawberry.dataloader import DataLoader
from typing import Optional
from collections import defaultdict


# --- Basic DataLoader ---

async def load_users(keys: list[str]) -> list[Optional[dict]]:
    """Batch load users by IDs."""
    users = await db.users.find({"_id": {"$in": keys}})
    user_map = {u["_id"]: u for u in users}
    # MUST return in same order as keys, with None for missing
    return [user_map.get(key) for key in keys]

user_loader = DataLoader(load_fn=load_users)

# Even if called 50 times in one request, only 1 DB query
# user1 = await user_loader.load("user_1")
# user2 = await user_loader.load("user_2")


# --- One-to-many DataLoader ---

async def load_order_items(order_ids: list[str]) -> list[list[dict]]:
    """Batch load items for multiple orders."""
    all_items = await db.order_items.find(
        {"order_id": {"$in": order_ids}}
    )

    # Group by order_id
    items_by_order = defaultdict(list)
    for item in all_items:
        items_by_order[item["order_id"]].append(item)

    # Return in same order as keys
    return [items_by_order.get(oid, []) for oid in order_ids]

order_item_loader = DataLoader(load_fn=load_order_items)


# --- Filtered DataLoader ---

class OrderLoader:
    """DataLoader with filter support."""

    def __init__(self, db):
        self.db = db
        self._cache: dict = {}

    async def load_for_user(
        self, user_id: str,
        status: Optional[str] = None,
        first: int = 10,
        after: Optional[str] = None,
    ):
        query = {"user_id": user_id}
        if status:
            query["status"] = status

        # Build cursor pagination
        if after:
            query["_id"] = {"$gt": after}

        orders = await self.db.orders.find(query).sort(
            "_id", -1
        ).limit(first + 1).to_list()

        has_next = len(orders) > first
        orders = orders[:first]

        return OrderConnection(
            edges=[
                OrderEdge(cursor=str(o["_id"]), node=Order.from_dict(o))
                for o in orders
            ],
            page_info=PageInfo(
                has_next_page=has_next,
                has_previous_page=after is not None,
                start_cursor=str(orders[0]["_id"]) if orders else None,
                end_cursor=str(orders[-1]["_id"]) if orders else None,
            ),
            total_count=await self.db.orders.count_documents(
                {"user_id": user_id}
            ),
        )


# --- Context factory with DataLoaders ---

async def get_context(request):
    """Create per-request context with fresh DataLoaders."""
    # DataLoaders are per-request (cache is request-scoped)
    return {
        "user": await get_current_user(request),
        "user_loader": DataLoader(load_fn=load_users),
        "order_item_loader": DataLoader(load_fn=load_order_items),
        "review_loader": DataLoader(load_fn=load_reviews),
        "order_loader": OrderLoader(db),
        "user_repo": UserRepository(db),
        "order_repo": OrderRepository(db),
        "product_repo": ProductRepository(db),
        "order_service": OrderService(db),
    }


# --- Nested DataLoader pattern ---

async def load_reviews(product_ids: list[str]) -> list[list[dict]]:
    """Load reviews with author info pre-loaded."""
    all_reviews = await db.reviews.find(
        {"product_id": {"$in": product_ids}}
    ).sort("created_at", -1).limit(50).to_list()

    # Pre-fetch all unique author IDs
    author_ids = list({r["author_id"] for r in all_reviews})
    authors = await db.users.find({"_id": {"$in": author_ids}})
    author_map = {a["_id"]: a["name"] for a in authors}

    # Enrich reviews with author names
    for review in all_reviews:
        review["author"] = author_map.get(review["author_id"], "Unknown")

    # Group by product
    by_product = defaultdict(list)
    for review in all_reviews:
        by_product[review["product_id"]].append(review)

    return [by_product.get(pid, []) for pid in product_ids]
```

DataLoader patterns:
1. **Batch + cache** — collect individual loads, execute as single batch query
2. **Return order** — results MUST match input key order (use None for missing)
3. **Per-request scope** — create new DataLoaders per request (prevent stale cache)
4. **One-to-many** — group results by parent key using `defaultdict`
5. **Pre-fetch related** — load nested data in the batch function itself'''
    ),
    (
        "graphql/subscriptions",
        "Show GraphQL subscription patterns: real-time updates, filtering, and connection management.",
        '''GraphQL subscriptions for real-time updates:

```python
import strawberry
from strawberry.types import Info
from strawberry.subscriptions import Subscription
import asyncio
from typing import AsyncGenerator, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import json


# --- PubSub system ---

class PubSub:
    """Simple in-memory pub/sub for GraphQL subscriptions."""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def publish(self, channel: str, message: dict):
        for queue in self._subscribers.get(channel, []):
            await queue.put(message)

    async def subscribe(self, channel: str) -> AsyncGenerator[dict, None]:
        queue = asyncio.Queue()
        self._subscribers[channel].append(queue)
        try:
            while True:
                message = await queue.get()
                yield message
        finally:
            self._subscribers[channel].remove(queue)


pubsub = PubSub()


# --- Subscription types ---

@strawberry.type
class OrderUpdate:
    order_id: strawberry.ID
    status: str
    message: str
    updated_at: str

@strawberry.type
class ChatMessage:
    id: strawberry.ID
    room_id: str
    sender_id: str
    sender_name: str
    content: str
    sent_at: str

@strawberry.type
class Notification:
    id: strawberry.ID
    type: str
    title: str
    body: str
    data: strawberry.scalars.JSON


# --- Subscriptions ---

@strawberry.type
class Subscription:
    @strawberry.subscription
    async def order_updates(
        self, info: Info, order_id: strawberry.ID
    ) -> AsyncGenerator[OrderUpdate, None]:
        """Subscribe to updates for a specific order."""
        user = info.context.get("user")
        if not user:
            raise PermissionError("Authentication required")

        # Verify user owns this order
        order = await info.context["order_repo"].find_by_id(order_id)
        if not order or order.user_id != user.id:
            raise PermissionError("Not your order")

        async for message in pubsub.subscribe(f"order:{order_id}"):
            yield OrderUpdate(**message)

    @strawberry.subscription
    async def chat_messages(
        self, info: Info, room_id: str
    ) -> AsyncGenerator[ChatMessage, None]:
        """Subscribe to messages in a chat room."""
        user = info.context.get("user")
        if not user:
            raise PermissionError("Authentication required")

        async for message in pubsub.subscribe(f"chat:{room_id}"):
            yield ChatMessage(**message)

    @strawberry.subscription
    async def notifications(
        self, info: Info,
        types: Optional[list[str]] = None,
    ) -> AsyncGenerator[Notification, None]:
        """Subscribe to user notifications with optional type filter."""
        user = info.context.get("user")
        if not user:
            raise PermissionError("Authentication required")

        async for message in pubsub.subscribe(f"user:{user.id}:notifications"):
            if types and message.get("type") not in types:
                continue
            yield Notification(**message)


# --- Publishing events (from mutations/services) ---

class OrderService:
    async def update_status(self, order_id: str, new_status: str):
        order = await self.repo.update_status(order_id, new_status)

        # Publish to subscribers
        await pubsub.publish(f"order:{order_id}", {
            "order_id": order_id,
            "status": new_status,
            "message": f"Order {new_status}",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        return order

class ChatService:
    async def send_message(self, room_id: str, sender_id: str,
                           content: str):
        message = await self.repo.create({
            "room_id": room_id,
            "sender_id": sender_id,
            "content": content,
        })

        sender = await self.user_repo.find_by_id(sender_id)
        await pubsub.publish(f"chat:{room_id}", {
            "id": str(message["_id"]),
            "room_id": room_id,
            "sender_id": sender_id,
            "sender_name": sender["name"],
            "content": content,
            "sent_at": message["created_at"].isoformat(),
        })

        return message


# --- Schema with subscriptions ---

schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
)
```

Subscription patterns:
1. **PubSub** — decouple publishers from subscribers
2. **Channel naming** — `entity:id` convention for targeted updates
3. **Auth in subscriptions** — validate user permissions on subscribe
4. **Client-side filtering** — let clients filter by type/criteria
5. **Cleanup** — remove subscriber queues when connection closes'''
    ),
]
"""
