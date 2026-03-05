"""GraphQL — schema design, resolvers, DataLoader, subscriptions, federation."""

PAIRS = [
    (
        "graphql/schema-design",
        "Show GraphQL schema design best practices: type design, pagination, error handling, and schema evolution with practical examples.",
        '''GraphQL schema design for production APIs:

```graphql
# --- Type definitions ---

type Query {
  """Get user by ID"""
  user(id: ID!): User
  """Search users with pagination"""
  users(filter: UserFilter, pagination: PaginationInput): UserConnection!
  """Get current authenticated user"""
  me: User!
}

type Mutation {
  createUser(input: CreateUserInput!): CreateUserPayload!
  updateUser(id: ID!, input: UpdateUserInput!): UpdateUserPayload!
  deleteUser(id: ID!): DeleteUserPayload!
}

# --- Input/Payload pattern (never return raw types from mutations) ---

input CreateUserInput {
  name: String!
  email: String!
  role: UserRole = MEMBER
}

type CreateUserPayload {
  user: User
  errors: [UserError!]!
}

type UserError {
  field: String
  message: String!
  code: ErrorCode!
}

enum ErrorCode {
  VALIDATION_ERROR
  NOT_FOUND
  ALREADY_EXISTS
  UNAUTHORIZED
}

# --- Cursor-based pagination (Relay spec) ---

input PaginationInput {
  first: Int
  after: String
  last: Int
  before: String
}

type UserConnection {
  edges: [UserEdge!]!
  pageInfo: PageInfo!
  totalCount: Int!
}

type UserEdge {
  node: User!
  cursor: String!
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
}

# --- Interface + Union for polymorphism ---

interface Node {
  id: ID!
}

interface Timestamped {
  createdAt: DateTime!
  updatedAt: DateTime!
}

type User implements Node & Timestamped {
  id: ID!
  name: String!
  email: String!
  role: UserRole!
  orders(first: Int = 10, after: String): OrderConnection!
  createdAt: DateTime!
  updatedAt: DateTime!
}

union SearchResult = User | Product | Order

type Query {
  search(query: String!, types: [SearchType!]): [SearchResult!]!
}

# --- Subscriptions ---

type Subscription {
  orderStatusChanged(orderId: ID!): Order!
  newMessage(channelId: ID!): Message!
}
```

```python
# --- Python resolvers (Strawberry) ---

import strawberry
from strawberry.types import Info
from dataclasses import dataclass

@strawberry.type
class User:
    id: strawberry.ID
    name: str
    email: str

    @strawberry.field
    async def orders(
        self,
        info: Info,
        first: int = 10,
        after: str | None = None,
    ) -> "OrderConnection":
        # Use DataLoader to avoid N+1
        loader = info.context["order_loader"]
        orders = await loader.load(self.id)
        return paginate(orders, first=first, after=after)

@strawberry.type
class CreateUserPayload:
    user: User | None = None
    errors: list["UserError"] = strawberry.field(default_factory=list)

@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_user(self, input: CreateUserInput) -> CreateUserPayload:
        # Validate
        errors = validate_user_input(input)
        if errors:
            return CreateUserPayload(errors=errors)

        # Create
        user = await db.create_user(name=input.name, email=input.email)
        return CreateUserPayload(user=user)

# --- DataLoader (batch N+1 queries) ---

from strawberry.dataloader import DataLoader

async def load_orders_batch(user_ids: list[str]) -> list[list[Order]]:
    """Batch load orders for multiple users in ONE query."""
    all_orders = await db.query(
        "SELECT * FROM orders WHERE user_id = ANY($1)",
        user_ids,
    )
    # Group by user_id
    grouped = {}
    for order in all_orders:
        grouped.setdefault(order.user_id, []).append(order)
    return [grouped.get(uid, []) for uid in user_ids]

# Context factory
async def get_context():
    return {
        "order_loader": DataLoader(load_fn=load_orders_batch),
        "user_loader": DataLoader(load_fn=load_users_batch),
    }
```

Schema design rules:
1. **Mutations return payloads** — include errors field, never throw
2. **Cursor pagination** — scalable, works with real-time data
3. **Input types** — separate from output types for flexibility
4. **Interfaces** — shared fields (Node for global IDs, Timestamped)
5. **DataLoader everywhere** — prevent N+1 queries
6. **Nullable by default** — non-null only for guaranteed fields'''
    ),
    (
        "graphql/federation",
        "Explain GraphQL federation for microservices: subgraph design, entity resolution, and schema composition with Apollo Federation.",
        '''GraphQL Federation splits a graph across microservices:

```graphql
# --- User subgraph (user-service) ---
# schema.graphql

extend schema @link(url: "https://specs.apollo.dev/federation/v2.0",
                    import: ["@key", "@shareable"])

type User @key(fields: "id") {
  id: ID!
  name: String!
  email: String!
  role: UserRole!
  createdAt: DateTime!
}

type Query {
  user(id: ID!): User
  me: User!
}

type Mutation {
  createUser(input: CreateUserInput!): CreateUserPayload!
}

# --- Order subgraph (order-service) ---
# schema.graphql

extend schema @link(url: "https://specs.apollo.dev/federation/v2.0",
                    import: ["@key", "@external", "@requires"])

type Order @key(fields: "id") {
  id: ID!
  status: OrderStatus!
  items: [OrderItem!]!
  total: Float!
  createdAt: DateTime!
  # Reference to User from user-service
  user: User!
}

# Extend User type from user-service
type User @key(fields: "id") {
  id: ID!
  # Add orders field to User (resolved by this subgraph)
  orders(first: Int = 10, after: String): OrderConnection!
}

type Query {
  order(id: ID!): Order
  ordersByStatus(status: OrderStatus!): [Order!]!
}

# --- Product subgraph (product-service) ---

type Product @key(fields: "sku") {
  sku: String!
  name: String!
  price: Float!
  inStock: Boolean!
}

# Extend OrderItem to include product details
type OrderItem {
  product: Product!
  quantity: Int!
  lineTotal: Float!
}
```

```python
# --- Subgraph resolver (order-service) ---

import strawberry
from strawberry.federation import Schema

@strawberry.federation.type(keys=["id"])
class Order:
    id: strawberry.ID
    status: str
    total: float

    @classmethod
    async def resolve_reference(cls, info, id: strawberry.ID):
        """Called by gateway when another service references this order."""
        order = await db.get_order(id)
        return cls(id=order.id, status=order.status, total=order.total)

@strawberry.federation.type(keys=["id"])
class User:
    id: strawberry.ID

    @strawberry.field
    async def orders(self, info, first: int = 10) -> list[Order]:
        """Extend User with orders (resolved here, not in user-service)."""
        orders = await db.get_user_orders(self.id, limit=first)
        return [Order(id=o.id, status=o.status, total=o.total) for o in orders]

    @classmethod
    async def resolve_reference(cls, info, id: strawberry.ID):
        """Stub — we only need the ID to resolve orders."""
        return cls(id=id)

schema = Schema(query=Query, mutation=Mutation, enable_federation_2=True)

# --- Gateway (Apollo Router / Apollo Gateway) ---

# router.yaml (Apollo Router configuration)
ROUTER_CONFIG = """
supergraph:
  listen: 0.0.0.0:4000

subgraphs:
  users:
    routing_url: http://user-service:4001/graphql
  orders:
    routing_url: http://order-service:4002/graphql
  products:
    routing_url: http://product-service:4003/graphql

# Query planning: gateway decomposes client query into subgraph queries
# Client query:
#   query { user(id: "123") { name orders { id total } } }
#
# Gateway plan:
#   1. user-service: { user(id: "123") { id name } }
#   2. order-service: { _entities(representations: [{__typename: "User", id: "123"}]) { orders { id total } } }
#   3. Merge results
"""
```

Federation principles:
- **Entity ownership** — one subgraph owns each entity's core fields
- **Entity extension** — other subgraphs add fields via `@key` + `resolve_reference`
- **Gateway composition** — schema composed at gateway, transparent to clients
- **Independent deployment** — each subgraph deploys independently
- **Shared types** — `@shareable` for types multiple subgraphs define'''
    ),
]
