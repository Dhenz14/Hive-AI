"""Advanced GraphQL — federation, subscriptions, dataloaders, schema design."""

PAIRS = [
    (
        "architecture/graphql-federation",
        "Show GraphQL federation: composing multiple subgraphs, entity references, and federated schema design.",
        '''GraphQL Federation — composing microservice schemas:

```python
# Strawberry GraphQL with federation (Python)
import strawberry
from strawberry.federation import Schema
from typing import Optional


# ---- User Subgraph ----
@strawberry.federation.type(keys=["id"])
class User:
    id: strawberry.ID
    name: str
    email: str

    @classmethod
    def resolve_reference(cls, id: strawberry.ID) -> "User":
        """Called when another subgraph references a User by ID."""
        return user_service.get_user(str(id))


@strawberry.type
class UserQuery:
    @strawberry.field
    def user(self, id: strawberry.ID) -> Optional[User]:
        return user_service.get_user(str(id))

    @strawberry.field
    def users(self, limit: int = 10) -> list[User]:
        return user_service.list_users(limit)


# ---- Order Subgraph (extends User) ----
@strawberry.federation.type(keys=["id"])
class Order:
    id: strawberry.ID
    total: float
    status: str
    user_id: strawberry.ID

    @strawberry.field
    def user(self) -> User:
        """Resolved by the gateway via federation."""
        return User(id=self.user_id, name="", email="")


@strawberry.federation.type(keys=["id"], extend=True)
class UserExtension:
    """Extend User type from another subgraph."""
    id: strawberry.ID = strawberry.federation.field(external=True)

    @strawberry.field
    def orders(self) -> list[Order]:
        return order_service.get_user_orders(str(self.id))


@strawberry.type
class OrderQuery:
    @strawberry.field
    def order(self, id: strawberry.ID) -> Optional[Order]:
        return order_service.get_order(str(id))


# Schema composition
user_schema = Schema(query=UserQuery, enable_federation_2=True)
order_schema = Schema(query=OrderQuery, types=[UserExtension],
                       enable_federation_2=True)


# ---- DataLoader for N+1 prevention ----
from strawberry.dataloader import DataLoader


async def load_users(ids: list[str]) -> list[User]:
    """Batch-load users — called once per batch, not per item."""
    users = await user_service.get_users_batch(ids)
    user_map = {u.id: u for u in users}
    return [user_map.get(id) for id in ids]


user_loader = DataLoader(load_fn=load_users)


# ---- Subscription ----
@strawberry.type
class Subscription:
    @strawberry.subscription
    async def order_updates(self, user_id: strawberry.ID):
        """Real-time order status updates via WebSocket."""
        async for event in event_stream(f"orders:{user_id}"):
            yield Order(
                id=event["order_id"],
                total=event["total"],
                status=event["status"],
                user_id=user_id,
            )
```

Key patterns:
1. **Federation keys** — `@key(fields: "id")` lets gateway resolve entities across subgraphs
2. **Entity references** — one subgraph extends another's type; gateway stitches them together
3. **DataLoader** — batch and cache DB calls within a request; eliminates N+1 queries
4. **Subscriptions** — real-time updates over WebSocket; async generator yields events
5. **Schema composition** — each team owns their subgraph; gateway composes the supergraph'''
    ),
    (
        "architecture/graphql-security",
        "Show GraphQL security: query complexity limits, depth limiting, rate limiting, and persisted queries.",
        '''GraphQL security hardening:

```python
import hashlib
import time
from dataclasses import dataclass
from typing import Optional, Any
from graphql import parse, DocumentNode


@dataclass
class QueryComplexity:
    """Calculate and limit query complexity."""
    max_complexity: int = 1000
    max_depth: int = 10

    def calculate_complexity(self, document: DocumentNode,
                              variables: dict = None) -> int:
        """Estimate query cost before execution."""
        return self._walk_selections(
            document.definitions[0].selection_set.selections, depth=0
        )

    def _walk_selections(self, selections, depth: int) -> int:
        if depth > self.max_depth:
            raise QueryTooDeep(f"Query depth {depth} exceeds max {self.max_depth}")

        complexity = 0
        for sel in selections:
            # Each field costs 1
            field_cost = 1

            # List fields multiply by expected items
            if hasattr(sel, "arguments"):
                for arg in sel.arguments:
                    if arg.name.value in ("first", "limit", "last"):
                        field_cost *= int(arg.value.value)

            complexity += field_cost
            if sel.selection_set:
                complexity += self._walk_selections(
                    sel.selection_set.selections, depth + 1
                ) * field_cost

        return complexity

    def validate(self, query: str, variables: dict = None) -> dict:
        document = parse(query)
        complexity = self.calculate_complexity(document, variables)
        depth = self._max_depth(document.definitions[0].selection_set.selections)

        return {
            "complexity": complexity,
            "depth": depth,
            "allowed": complexity <= self.max_complexity and depth <= self.max_depth,
        }

    def _max_depth(self, selections, current: int = 0) -> int:
        if not selections:
            return current
        return max(
            self._max_depth(sel.selection_set.selections if sel.selection_set else [], current + 1)
            for sel in selections
        )


class PersistedQueries:
    """Only allow pre-approved queries in production."""

    def __init__(self):
        self.allowed: dict[str, str] = {}  # hash -> query

    def register(self, query: str) -> str:
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        self.allowed[query_hash] = query
        return query_hash

    def resolve(self, query_hash: str) -> Optional[str]:
        return self.allowed.get(query_hash)

    def middleware(self, request: dict) -> dict:
        """Replace hash with actual query; reject unknown queries."""
        if "extensions" in request:
            pq = request["extensions"].get("persistedQuery", {})
            query_hash = pq.get("sha256Hash")
            if query_hash:
                query = self.resolve(query_hash)
                if query is None:
                    raise PersistedQueryNotFound(query_hash)
                request["query"] = query
            elif not request.get("query"):
                raise ValueError("Query or persisted query hash required")
        return request


class QueryTooDeep(Exception):
    pass


class PersistedQueryNotFound(Exception):
    pass
```

Key patterns:
1. **Complexity analysis** — estimate cost before execution; reject expensive queries
2. **Depth limiting** — prevent deeply nested queries that cause N+1 explosions
3. **List multiplier** — `users(first: 100) { posts(first: 50) }` = 100 × 50 = 5000 cost
4. **Persisted queries** — whitelist approved queries by hash; block arbitrary queries in production
5. **Pre-execution validation** — check complexity/depth before running; fail fast on abuse'''
    ),
]
