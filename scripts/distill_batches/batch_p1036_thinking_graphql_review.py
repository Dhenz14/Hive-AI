r"""Thinking-trace pairs: GraphQL code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this GraphQL code and identify issues:

```python
import strawberry
from strawberry.types import Info
from typing import List, Optional
from dataclasses import dataclass

@strawberry.type
class User:
    id: int
    name: str
    email: str
    posts: List['Post']

    @strawberry.field
    def posts(self, info: Info) -> List['Post']:
        return db.query("SELECT * FROM posts WHERE user_id = %s", [self.id])

@strawberry.type
class Post:
    id: int
    title: str
    body: str
    author: 'User'
    comments: List['Comment']

    @strawberry.field
    def author(self, info: Info) -> 'User':
        return db.query("SELECT * FROM users WHERE id = %s", [self.author_id])

    @strawberry.field
    def comments(self, info: Info) -> List['Comment']:
        return db.query("SELECT * FROM comments WHERE post_id = %s", [self.id])

@strawberry.type
class Comment:
    id: int
    body: str
    author: 'User'

    @strawberry.field
    def author(self, info: Info) -> 'User':
        return db.query("SELECT * FROM users WHERE id = %s", [self.author_id])

@strawberry.type
class Query:
    @strawberry.field
    def users(self, info: Info) -> List[User]:
        return db.query("SELECT * FROM users")

    @strawberry.field
    def posts(self, info: Info, limit: int = 100) -> List[Post]:
        return db.query("SELECT * FROM posts ORDER BY created_at DESC LIMIT %s", [limit])

    @strawberry.field
    def search(self, info: Info, query: str) -> List[Post]:
        return db.query(f"SELECT * FROM posts WHERE title LIKE '%{query}%'")

@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_post(self, info: Info, title: str, body: str) -> Post:
        user = info.context.get('user')
        return db.execute("INSERT INTO posts (title, body, user_id) VALUES (%s, %s, %s) RETURNING *",
                         [title, body, user['id']])

    @strawberry.mutation
    def delete_post(self, info: Info, post_id: int) -> bool:
        db.execute("DELETE FROM posts WHERE id = %s", [post_id])
        return True

schema = strawberry.Schema(query=Query, mutation=Mutation)
```''', r'''<think>
Let me review this GraphQL schema implementation.

1. N+1 query problem:
- This is the classic GraphQL N+1 issue. If a client queries `users { posts { author { name } } }`:
  - 1 query for all users
  - N queries for each user's posts
  - For each post, 1 query for the author
  - For each post, 1 query for comments
- With 10 users having 10 posts each, that is 1 + 10 + 100 + 100 = 211 queries.
- Need DataLoader to batch database requests.

2. SQL injection in search:
- `f"SELECT * FROM posts WHERE title LIKE '%{query}%'"` uses f-string interpolation. An attacker can inject SQL via the search query.

3. No authentication:
- create_post reads user from context but does not check if it exists. If unauthenticated, info.context.get('user') returns None, and user['id'] crashes.
- delete_post has no auth at all. Anyone can delete any post.

4. No authorization:
- delete_post does not check if the user owns the post.

5. No query depth limiting:
- The schema allows circular references: User -> posts -> author -> posts -> author -> ... An attacker can craft a deeply nested query that consumes exponential resources.

6. No query complexity analysis:
- `posts(limit: 100)` defaults to 100 posts. Each post resolves author and comments. With nested fields, this can trigger thousands of database queries.

7. Limit validation:
- The limit parameter has no maximum bound. A client can request limit=1000000.

8. Email exposure:
- The User type exposes email to anyone who queries it. Should have field-level authorization.

Let me write the review.
</think>

## Code Review: GraphQL Schema

### CRITICAL - N+1 Query Problem

**NP1: Every resolver executes individual database queries (Severity: CRITICAL)**
A query like `{ users { posts { comments { author { name } } } } }` with 10 users, 10 posts each, 5 comments each triggers:
- 1 query for users
- 10 queries for posts (one per user)
- 100 queries for comments (one per post)
- 500 queries for comment authors (one per comment)
Total: 611 database queries for one GraphQL request.

Fix with DataLoader to batch queries:
```python
from strawberry.dataloader import DataLoader

async def load_posts_by_user(user_ids: List[int]) -> List[List[Post]]:
    posts = await db.query("SELECT * FROM posts WHERE user_id = ANY($1)", [user_ids])
    grouped = {uid: [] for uid in user_ids}
    for post in posts:
        grouped[post.user_id].append(post)
    return [grouped[uid] for uid in user_ids]

# In context setup:
context = {"post_loader": DataLoader(load_fn=load_posts_by_user)}
```

### CRITICAL - SQL Injection

**SQL1: String interpolation in search query (Severity: CRITICAL)**
```python
f"SELECT * FROM posts WHERE title LIKE '%{query}%'"
```
User input is interpolated directly into SQL. Attack: `query = "'; DROP TABLE posts; --"`. Use parameterized queries:
```python
db.query("SELECT * FROM posts WHERE title LIKE %s", [f"%{query}%"])
```

### HIGH - No Authentication or Authorization

**AUTH1: create_post crashes without auth (Severity: HIGH)**
```python
user = info.context.get('user')
return db.execute("...", [title, body, user['id']])
```
If no user is in context (unauthenticated request), `user['id']` raises TypeError. Check authentication first.

**AUTH2: delete_post has no ownership check (Severity: HIGH)**
Any user can delete any post. Verify ownership:
```python
post = db.query("SELECT * FROM posts WHERE id = %s", [post_id])
if post.user_id != user['id']:
    raise PermissionError("Not your post")
```

### HIGH - No Query Depth/Complexity Limits

**QL1: Circular references enable resource exhaustion (Severity: HIGH)**
User -> posts -> author -> posts -> author creates infinite nesting. An attacker can craft a query with depth 100+, causing exponential database load. Add depth limiting:
```python
from strawberry.extensions import QueryDepthLimiter
schema = strawberry.Schema(
    query=Query,
    extensions=[QueryDepthLimiter(max_depth=10)],
)
```

### MEDIUM - Unbounded Limit

**UL1: No maximum on posts limit (Severity: MEDIUM)**
`limit: int = 100` accepts any integer. A client can request `limit: 999999`. Add a cap:
```python
@strawberry.field
def posts(self, info: Info, limit: int = 20) -> List[Post]:
    capped = min(limit, 100)
    return db.query("SELECT * FROM posts LIMIT %s", [capped])
```

### MEDIUM - Email Exposed to All Queries

**PII1: User email visible without authorization (Severity: MEDIUM)**
Any client querying `{ users { email } }` sees all email addresses. Add field-level authorization or remove email from the public schema.'''),

    ("thinking/code-review", r'''Review this GraphQL code and identify issues:

```javascript
const { ApolloServer, gql } = require('apollo-server');
const { PubSub, withFilter } = require('graphql-subscriptions');

const pubsub = new PubSub();

const typeDefs = gql`
  type Query {
    messages(channel: String!): [Message!]!
    user(id: ID!): User
    search(text: String!): [SearchResult!]!
  }

  type Mutation {
    sendMessage(channel: String!, text: String!): Message!
    updateProfile(input: ProfileInput!): User!
    deleteMessage(id: ID!): Boolean!
  }

  type Subscription {
    messageSent(channel: String!): Message!
    userPresence: PresenceEvent!
  }

  type Message {
    id: ID!
    text: String!
    author: User!
    channel: String!
    createdAt: String!
  }

  type User {
    id: ID!
    name: String!
    email: String!
    messages: [Message!]!
  }

  type PresenceEvent {
    userId: ID!
    status: String!
    timestamp: String!
  }

  union SearchResult = Message | User

  input ProfileInput {
    name: String
    email: String
    password: String
  }
`;

const resolvers = {
  Query: {
    messages: (_, { channel }) => {
      return db.messages.findMany({ where: { channel }, take: 1000 });
    },
    user: (_, { id }) => db.users.findUnique({ where: { id } }),
    search: (_, { text }) => {
      const messages = db.messages.findMany({
        where: { text: { contains: text } },
      });
      const users = db.users.findMany({
        where: { name: { contains: text } },
      });
      return [...messages, ...users];
    },
  },
  Mutation: {
    sendMessage: async (_, { channel, text }, context) => {
      const message = await db.messages.create({
        data: { channel, text, authorId: context.user.id },
      });
      pubsub.publish('MESSAGE_SENT', { messageSent: message });
      return message;
    },
    updateProfile: (_, { input }, context) => {
      return db.users.update({
        where: { id: context.user.id },
        data: input,
      });
    },
    deleteMessage: async (_, { id }) => {
      await db.messages.delete({ where: { id } });
      return true;
    },
  },
  Subscription: {
    messageSent: {
      subscribe: withFilter(
        () => pubsub.asyncIterator('MESSAGE_SENT'),
        (payload, variables) => {
          return payload.messageSent.channel === variables.channel;
        }
      ),
    },
    userPresence: {
      subscribe: () => pubsub.asyncIterator('USER_PRESENCE'),
    },
  },
  SearchResult: {
    __resolveType(obj) {
      if (obj.text) return 'Message';
      if (obj.name) return 'User';
      return null;
    },
  },
  User: {
    messages: (parent) => {
      return db.messages.findMany({ where: { authorId: parent.id } });
    },
  },
};

const server = new ApolloServer({
  typeDefs,
  resolvers,
  context: ({ req }) => {
    const token = req.headers.authorization;
    const user = token ? verifyToken(token) : null;
    return { user };
  },
});
```''', r'''<think>
Let me review this GraphQL chat application.

1. N+1 on User.messages:
- The User resolver for messages fires a query per user. If a search returns 50 users and the client requests their messages, 50 additional queries fire.

2. Authentication issues:
- sendMessage accesses context.user.id without checking if user exists. An unauthenticated request crashes.
- deleteMessage has no auth at all -- anyone can delete any message.
- updateProfile passes `input` directly to db.users.update. The input includes `password` field. If password is included, it is stored as-is (not hashed).
- userPresence subscription has no auth -- anyone can monitor presence.

3. In-memory PubSub:
- PubSub from graphql-subscriptions is in-memory only. It does not work across multiple server instances. In production with load balancing, subscriptions only work on the server instance that published the event.

4. messages query returns 1000:
- `take: 1000` is a very high default. No pagination parameters exposed to the client.

5. SearchResult type resolution:
- __resolveType checks for `obj.text` to identify Message and `obj.name` for User. But if a Message has a name field or a User has a text field, the resolution is wrong. Use a discriminator field or check the model type.

6. search resolver:
- Runs two separate queries (messages and users) and combines results. These could run in parallel with Promise.all but are currently sequential (no await, but the Prisma calls might be async).
- No limit on search results.
- No __typename or type information in the combined results.

7. Subscription filtering:
- messageSent filter compares channel names, which is correct. But the payload contains the full message including author data, which might be a privacy concern for channel-specific subscriptions.

8. ProfileInput includes password:
- Passing password through GraphQL mutation as a plain field. The password appears in logs, query introspection, and potentially in error messages.

Let me write the review.
</think>

## Code Review: GraphQL Chat Application

### CRITICAL - No Auth on Destructive Operations

**AUTH1: deleteMessage has no authentication (Severity: CRITICAL)**
```javascript
deleteMessage: async (_, { id }) => {
  await db.messages.delete({ where: { id } });
```
Anyone can delete any message. No user check, no ownership verification. Add auth:
```javascript
deleteMessage: async (_, { id }, context) => {
  if (!context.user) throw new AuthenticationError('Must be logged in');
  const msg = await db.messages.findUnique({ where: { id } });
  if (msg.authorId !== context.user.id) throw new ForbiddenError('Not your message');
  await db.messages.delete({ where: { id } });
  return true;
}
```

**AUTH2: sendMessage crashes without auth (Severity: HIGH)**
`context.user.id` throws TypeError when user is null. Check first:
```javascript
if (!context.user) throw new AuthenticationError('Login required');
```

### CRITICAL - Password Stored Unhashed

**PW1: updateProfile passes password directly to database (Severity: CRITICAL)**
```javascript
updateProfile: (_, { input }, context) => {
  return db.users.update({ where: { id: context.user.id }, data: input });
}
```
If `input` contains `password: "newpass123"`, it is stored as plain text. Hash before saving:
```javascript
if (input.password) {
  input.password = await bcrypt.hash(input.password, 12);
}
```
Also, password changes should require the current password for verification.

### HIGH - In-Memory PubSub

**PS1: PubSub does not scale across instances (Severity: HIGH)**
```javascript
const pubsub = new PubSub();
```
The default PubSub is in-memory. With multiple server instances (load balancing, horizontal scaling), subscriptions only receive events from the same instance. Use Redis-based PubSub:
```javascript
const { RedisPubSub } = require('graphql-redis-subscriptions');
const pubsub = new RedisPubSub({ connection: { host: 'redis-host' } });
```

### HIGH - N+1 on User.messages

**NP1: Per-user message query (Severity: HIGH)**
```javascript
messages: (parent) => {
  return db.messages.findMany({ where: { authorId: parent.id } });
}
```
For a search returning 50 users, this fires 50 queries. Use a DataLoader to batch:
```javascript
const messageLoader = new DataLoader(async (userIds) => {
  const messages = await db.messages.findMany({ where: { authorId: { in: userIds } } });
  return userIds.map(id => messages.filter(m => m.authorId === id));
});
```

### MEDIUM - SearchResult Type Resolution Fragile

**SR1: Field-based type detection is unreliable (Severity: MEDIUM)**
```javascript
__resolveType(obj) {
  if (obj.text) return 'Message';
  if (obj.name) return 'User';
}
```
If a Message happens to have a `name` property or a User has `text`, the resolution is wrong. Use explicit typing:
```javascript
// In search resolver:
return [
  ...messages.map(m => ({ ...m, __typename: 'Message' })),
  ...users.map(u => ({ ...u, __typename: 'User' })),
];
```

### MEDIUM - No Pagination on Messages

**PG1: Messages returns up to 1000 (Severity: MEDIUM)**
`take: 1000` is excessive. Add pagination parameters:
```graphql
messages(channel: String!, cursor: ID, limit: Int = 50): MessageConnection!
```

### LOW - Password in Schema

**PS2: Password field visible in GraphQL introspection (Severity: LOW)**
The `ProfileInput` type with `password: String` is visible through schema introspection. While this is not a direct vulnerability, it advertises the password field. Consider a separate `changePassword` mutation with dedicated input types.'''),

    ("thinking/code-review", r'''Review this GraphQL code and identify issues:

```python
import strawberry
from strawberry.types import Info
from strawberry.permission import BasePermission
from typing import List, Optional
from datetime import datetime

class IsAuthenticated(BasePermission):
    message = "Not authenticated"

    def has_permission(self, source, info: Info, **kwargs) -> bool:
        return info.context.get("user") is not None

@strawberry.type
class Product:
    id: int
    name: str
    price: float
    description: str

@strawberry.input
class ProductInput:
    name: str
    price: float
    description: str

@strawberry.type
class CartItem:
    product: Product
    quantity: int

@strawberry.type
class Order:
    id: int
    items: List[CartItem]
    total: float
    status: str
    created_at: datetime

@strawberry.type
class Query:
    @strawberry.field
    def products(
        self, info: Info,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> List[Product]:
        filters = {}
        if category: filters['category'] = category
        if min_price: filters['price__gte'] = min_price
        if max_price: filters['price__lte'] = max_price
        return Product.objects.filter(**filters)

    @strawberry.field
    def product(self, info: Info, id: int) -> Optional[Product]:
        return Product.objects.get(id=id)

    @strawberry.field(permission_classes=[IsAuthenticated])
    def my_orders(self, info: Info) -> List[Order]:
        user = info.context['user']
        return Order.objects.filter(user_id=user.id).prefetch_related('items__product')

    @strawberry.field(permission_classes=[IsAuthenticated])
    def order(self, info: Info, id: int) -> Optional[Order]:
        return Order.objects.get(id=id)

@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsAuthenticated])
    def add_to_cart(self, info: Info, product_id: int, quantity: int) -> List[CartItem]:
        user = info.context['user']
        cart = get_or_create_cart(user.id)
        cart.add_item(product_id, quantity)
        return cart.items

    @strawberry.mutation(permission_classes=[IsAuthenticated])
    def place_order(self, info: Info) -> Order:
        user = info.context['user']
        cart = get_cart(user.id)
        order = create_order_from_cart(cart, user)
        send_confirmation_email(user.email, order)
        notify_warehouse(order)
        return order

    @strawberry.mutation(permission_classes=[IsAuthenticated])
    def cancel_order(self, info: Info, order_id: int) -> Order:
        order = Order.objects.get(id=order_id)
        order.status = 'cancelled'
        order.save()
        process_refund(order)
        return order
```''', r'''<think>
Let me review this GraphQL e-commerce code.

1. Authorization issues:
- order resolver: any authenticated user can view ANY order by ID. No ownership check. A user can access other users' order details.
- cancel_order: any authenticated user can cancel ANY order. No ownership check.

2. Caching opportunity missed:
- products query fetches from the database on every request. Product data changes infrequently and could be cached.

3. Side effects in mutation:
- place_order does create_order, send_confirmation_email, AND notify_warehouse synchronously. If email sending fails, does the order still go through? If warehouse notification fails, the order is placed but warehouse is not notified. These should be async/queued.

4. cancel_order does refund synchronously:
- If process_refund fails after status is set to 'cancelled', the order is cancelled without a refund. Should be transactional.

5. Falsy filter check:
- `if min_price:` evaluates to False when min_price is 0. A user filtering for free products (min_price=0) has the filter silently ignored. Should be `if min_price is not None:`.

6. product resolver:
- `Product.objects.get(id=id)` raises DoesNotExist if the product is not found. Should handle this and return None (since the return type is Optional[Product]).

7. Cart operations:
- add_to_cart does not validate that the product exists or has sufficient stock.
- No quantity validation (negative quantities?).

8. No pagination:
- products returns all matching products. my_orders returns all orders. No pagination.

Let me write the review.
</think>

## Code Review: GraphQL E-Commerce Schema

### CRITICAL - Authorization Bypass

**AZ1: Any user can view any order (Severity: CRITICAL)**
```python
@strawberry.field(permission_classes=[IsAuthenticated])
def order(self, info: Info, id: int) -> Optional[Order]:
    return Order.objects.get(id=id)
```
IsAuthenticated only checks if a user is logged in, not if they own the order. User A can query User B's orders by guessing IDs. Add ownership check:
```python
order = Order.objects.get(id=id)
if order.user_id != info.context['user'].id:
    raise PermissionError("Access denied")
return order
```

**AZ2: Any user can cancel any order (Severity: CRITICAL)**
Same issue in `cancel_order`. A malicious user can cancel other users' orders and trigger refunds.

### HIGH - Synchronous Side Effects in Mutations

**SE1: place_order blocks on email and warehouse (Severity: HIGH)**
```python
order = create_order_from_cart(cart, user)
send_confirmation_email(user.email, order)
notify_warehouse(order)
```
If `send_confirmation_email` fails, does the response fail even though the order was created? If `notify_warehouse` is slow, the client waits. These should be async tasks:
```python
order = create_order_from_cart(cart, user)
# Queue background tasks
queue.enqueue(send_confirmation_email, user.email, order.id)
queue.enqueue(notify_warehouse, order.id)
return order
```

**SE2: cancel_order not transactional (Severity: HIGH)**
```python
order.status = 'cancelled'
order.save()
process_refund(order)
```
If `process_refund` fails after save, the order is cancelled without a refund. Wrap in a transaction:
```python
with transaction.atomic():
    order.status = 'cancelled'
    order.save()
    process_refund(order)
```

### MEDIUM - Falsy Filter Bug

**FB1: min_price=0 silently ignored (Severity: MEDIUM)**
```python
if min_price: filters['price__gte'] = min_price
```
`if min_price:` is False when min_price is 0. Filtering for free products does not work. Use `if min_price is not None:`.

### MEDIUM - DoesNotExist Not Handled

**DE1: product() crashes on invalid ID (Severity: MEDIUM)**
`Product.objects.get(id=id)` raises DoesNotExist for invalid IDs. The return type is Optional[Product], implying None should be returned. Use:
```python
try:
    return Product.objects.get(id=id)
except Product.DoesNotExist:
    return None
```

### MEDIUM - No Input Validation

**IV1: Quantity not validated (Severity: MEDIUM)**
`add_to_cart` accepts any quantity including 0, negative numbers, or extremely large values. Validate:
```python
if quantity <= 0:
    raise ValueError("Quantity must be positive")
if quantity > 100:
    raise ValueError("Maximum quantity exceeded")
```

### MEDIUM - No Pagination

**PG1: Unbounded list queries (Severity: MEDIUM)**
`products` and `my_orders` return all matching results. A user with 10,000 orders or a product catalog with 100,000 items would produce massive responses. Add connection-based pagination.

### LOW - No Caching

**CA1: Product queries hit database every time (Severity: LOW)**
Product data changes infrequently. Cache product queries with a short TTL to reduce database load.'''),

    ("thinking/code-review", r'''Review this GraphQL code and identify issues:

```javascript
const { ApolloServer } = require('@apollo/server');
const { makeExecutableSchema } = require('@graphql-tools/schema');
const depthLimit = require('graphql-depth-limit');
const costAnalysis = require('graphql-cost-analysis');

const typeDefs = `
  type Query {
    analytics(dateRange: DateRangeInput!): Analytics!
    report(type: ReportType!, filters: ReportFilters): Report!
  }

  input DateRangeInput {
    start: String!
    end: String!
  }

  enum ReportType {
    SALES
    INVENTORY
    USERS
    PERFORMANCE
  }

  input ReportFilters {
    categories: [String!]
    minAmount: Float
    maxAmount: Float
    status: String
  }

  type Analytics {
    totalRevenue: Float!
    orderCount: Int!
    averageOrderValue: Float!
    topProducts: [ProductStat!]!
    revenueByDay: [DailyRevenue!]!
    conversionRate: Float!
    userGrowth: [GrowthPoint!]!
  }

  type ProductStat {
    product: Product!
    sold: Int!
    revenue: Float!
  }

  type DailyRevenue {
    date: String!
    revenue: Float!
    orders: Int!
  }

  type GrowthPoint {
    date: String!
    newUsers: Int!
    totalUsers: Int!
  }

  type Report {
    id: ID!
    type: ReportType!
    data: JSON!
    generatedAt: String!
    downloadUrl: String
  }

  scalar JSON
`;

const resolvers = {
  Query: {
    analytics: async (_, { dateRange }) => {
      const { start, end } = dateRange;
      const revenue = await db.query(
        `SELECT SUM(total) FROM orders WHERE created_at BETWEEN '${start}' AND '${end}'`
      );
      const orderCount = await db.query(
        `SELECT COUNT(*) FROM orders WHERE created_at BETWEEN '${start}' AND '${end}'`
      );
      const topProducts = await db.query(
        `SELECT product_id, SUM(quantity) as sold, SUM(price * quantity) as revenue
         FROM order_items oi JOIN orders o ON oi.order_id = o.id
         WHERE o.created_at BETWEEN '${start}' AND '${end}'
         GROUP BY product_id ORDER BY revenue DESC LIMIT 10`
      );
      const dailyRevenue = await db.query(
        `SELECT DATE(created_at) as date, SUM(total) as revenue, COUNT(*) as orders
         FROM orders WHERE created_at BETWEEN '${start}' AND '${end}'
         GROUP BY DATE(created_at)`
      );
      const conversionRate = await db.query(
        `SELECT (SELECT COUNT(*) FROM orders WHERE created_at BETWEEN '${start}' AND '${end}')::float
         / NULLIF((SELECT COUNT(*) FROM sessions WHERE created_at BETWEEN '${start}' AND '${end}'), 0)`
      );
      const userGrowth = await db.query(
        `SELECT DATE(created_at) as date, COUNT(*) as new_users,
         SUM(COUNT(*)) OVER (ORDER BY DATE(created_at)) as total_users
         FROM users WHERE created_at BETWEEN '${start}' AND '${end}'
         GROUP BY DATE(created_at)`
      );

      return {
        totalRevenue: revenue[0].sum,
        orderCount: orderCount[0].count,
        averageOrderValue: revenue[0].sum / orderCount[0].count,
        topProducts,
        revenueByDay: dailyRevenue,
        conversionRate: conversionRate[0].result,
        userGrowth,
      };
    },
    report: async (_, { type, filters }) => {
      const data = await generateReport(type, filters);
      return {
        id: generateId(),
        type,
        data,
        generatedAt: new Date().toISOString(),
      };
    },
  },
};

const server = new ApolloServer({
  schema: makeExecutableSchema({ typeDefs, resolvers }),
  validationRules: [depthLimit(10)],
  plugins: [costAnalysis({ maximumCost: 1000 })],
});
```''', r'''<think>
Let me review this GraphQL analytics code.

1. SQL injection -- critical:
- Every single query uses string interpolation with `start` and `end` values: `BETWEEN '${start}' AND '${end}'`. These come directly from user input (DateRangeInput). An attacker can inject SQL via the date parameters.
- This is the same vulnerability repeated 6 times.

2. All queries run sequentially:
- The analytics resolver runs 6 database queries sequentially with individual awaits. These are independent queries that could run in parallel with Promise.all, cutting response time significantly.

3. Date validation:
- DateRangeInput uses String! for dates. No validation that the strings are valid dates. Client can send "not-a-date" or "'; DROP TABLE orders; --".

4. Division by zero:
- `averageOrderValue: revenue[0].sum / orderCount[0].count` -- if count is 0, this divides by zero (NaN in JavaScript, but still wrong).

5. No authentication:
- Analytics data is accessible to anyone. No auth check on any resolver.

6. No caching:
- Analytics queries hit the database every time. These aggregation queries can be very expensive on large tables. Should cache results.

7. Report generation:
- The report resolver generates reports synchronously. For large reports, this blocks the response. Should be async with polling.
- JSON scalar type is used for report data, losing all type safety.

8. Good practices:
- depthLimit and costAnalysis plugins are good security measures.

Let me write the review.
</think>

## Code Review: GraphQL Analytics Schema

### CRITICAL - SQL Injection in All Queries

**SQL1: String interpolation in 6 database queries (Severity: CRITICAL)**
```javascript
`SELECT SUM(total) FROM orders WHERE created_at BETWEEN '${start}' AND '${end}'`
```
The `start` and `end` parameters from the client are interpolated directly into SQL. Attack payload:
```graphql
query {
  analytics(dateRange: { start: "2024-01-01", end: "'; DROP TABLE orders; --" }) { ... }
}
```

This vulnerability appears in ALL 6 queries. Use parameterized queries:
```javascript
const revenue = await db.query(
  'SELECT SUM(total) FROM orders WHERE created_at BETWEEN $1 AND $2',
  [start, end]
);
```

### HIGH - Sequential Queries Kill Performance

**SQ1: Six independent queries run sequentially (Severity: HIGH)**
Each query awaits before starting the next. For date ranges spanning months, these aggregation queries can each take seconds. Total response time is the sum.

Run in parallel:
```javascript
const [revenue, orderCount, topProducts, dailyRevenue, conversionRate, userGrowth] =
  await Promise.all([
    db.query('SELECT SUM(total) FROM orders WHERE ...', [start, end]),
    db.query('SELECT COUNT(*) FROM orders WHERE ...', [start, end]),
    db.query('SELECT product_id, ... WHERE ... GROUP BY ...', [start, end]),
    db.query('SELECT DATE(created_at), ... GROUP BY ...', [start, end]),
    db.query('SELECT ... / NULLIF(...)', [start, end]),
    db.query('SELECT DATE(created_at), ... GROUP BY ...', [start, end]),
  ]);
```

### HIGH - No Authentication

**AUTH1: Analytics accessible to anyone (Severity: HIGH)**
Revenue data, order counts, conversion rates, and user growth are exposed without authentication. Add authorization middleware.

### MEDIUM - No Date Validation

**DV1: Dates are unvalidated strings (Severity: MEDIUM)**
```graphql
input DateRangeInput {
  start: String!
  end: String!
}
```
No validation that strings are valid dates, or that start < end. Use a custom Date scalar or validate in the resolver:
```javascript
const startDate = new Date(start);
const endDate = new Date(end);
if (isNaN(startDate) || isNaN(endDate)) throw new UserInputError('Invalid date');
if (startDate > endDate) throw new UserInputError('start must be before end');
```

### MEDIUM - Division by Zero

**DZ1: Average order value when no orders (Severity: MEDIUM)**
```javascript
averageOrderValue: revenue[0].sum / orderCount[0].count,
```
When count is 0, this produces NaN (or Infinity). Guard:
```javascript
averageOrderValue: orderCount[0].count > 0
  ? revenue[0].sum / orderCount[0].count
  : 0,
```

### MEDIUM - No Caching

**NC1: Expensive aggregations on every request (Severity: MEDIUM)**
Analytics queries aggregate over potentially millions of rows. The same date range produces the same results. Cache with the date range as key and a reasonable TTL (5-15 minutes).

### Good Practices

- `depthLimit(10)` prevents deeply nested queries
- `costAnalysis({ maximumCost: 1000 })` limits query complexity
These are excellent security measures that many GraphQL APIs lack.'''),

    ("thinking/code-review", r'''Review this GraphQL code and identify issues:

```typescript
import { ApolloClient, InMemoryCache, gql, useQuery, useMutation, useSubscription } from '@apollo/client';
import { WebSocketLink } from '@apollo/client/link/ws';
import { split, HttpLink, from } from '@apollo/client';
import { getMainDefinition } from '@apollo/client/utilities';
import { onError } from '@apollo/client/link/error';
import { RetryLink } from '@apollo/client/link/retry';

const httpLink = new HttpLink({
  uri: '/graphql',
  credentials: 'include',
});

const wsLink = new WebSocketLink({
  uri: `ws://${window.location.host}/graphql`,
  options: {
    reconnect: true,
    connectionParams: {
      authToken: localStorage.getItem('token'),
    },
  },
});

const errorLink = onError(({ graphQLErrors, networkError }) => {
  if (graphQLErrors) {
    graphQLErrors.forEach(({ message, locations, path }) => {
      console.log(`GraphQL error: ${message}`);
      if (message.includes('not authenticated')) {
        localStorage.removeItem('token');
        window.location.href = '/login';
      }
    });
  }
  if (networkError) {
    console.log(`Network error: ${networkError}`);
  }
});

const retryLink = new RetryLink({
  delay: { initial: 300, max: 3000, jitter: true },
  attempts: { max: 5, retryIf: (error) => !!error },
});

const splitLink = split(
  ({ query }) => {
    const definition = getMainDefinition(query);
    return definition.kind === 'OperationDefinition' && definition.operation === 'subscription';
  },
  wsLink,
  from([retryLink, errorLink, httpLink]),
);

const cache = new InMemoryCache({
  typePolicies: {
    Query: {
      fields: {
        notifications: {
          merge(existing = [], incoming) {
            return [...existing, ...incoming];
          },
        },
        tasks: {
          merge(existing, incoming) {
            return incoming;
          },
        },
      },
    },
  },
});

const client = new ApolloClient({ link: splitLink, cache });

const GET_TASKS = gql`
  query GetTasks($projectId: ID!, $status: String) {
    project(id: $projectId) {
      id
      name
      tasks(status: $status) {
        id
        title
        description
        status
        assignee {
          id
          name
          email
          avatar
        }
        comments {
          id
          text
          author { id name }
          createdAt
        }
        attachments {
          id
          filename
          url
          size
        }
        createdAt
        updatedAt
      }
    }
  }
`;

const UPDATE_TASK = gql`
  mutation UpdateTask($id: ID!, $input: TaskInput!) {
    updateTask(id: $id, input: $input) {
      id
      title
      status
    }
  }
`;

const TASK_UPDATED = gql`
  subscription OnTaskUpdated($projectId: ID!) {
    taskUpdated(projectId: $projectId) {
      id
      title
      status
      assignee { id name }
    }
  }
`;

function TaskBoard({ projectId }) {
  const { data, loading, error, refetch } = useQuery(GET_TASKS, {
    variables: { projectId },
    pollInterval: 30000,
  });

  const [updateTask] = useMutation(UPDATE_TASK);

  useSubscription(TASK_UPDATED, {
    variables: { projectId },
    onData: ({ data: subData }) => {
      refetch();
    },
  });

  const handleStatusChange = async (taskId, newStatus) => {
    await updateTask({
      variables: { id: taskId, input: { status: newStatus } },
    });
  };

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;

  const tasks = data.project.tasks;
  const columns = {
    TODO: tasks.filter(t => t.status === 'TODO'),
    IN_PROGRESS: tasks.filter(t => t.status === 'IN_PROGRESS'),
    DONE: tasks.filter(t => t.status === 'DONE'),
  };

  return (
    <div className="board">
      {Object.entries(columns).map(([status, statusTasks]) => (
        <div key={status} className="column">
          <h2>{status} ({statusTasks.length})</h2>
          {statusTasks.map(task => (
            <TaskCard
              key={task.id}
              task={task}
              onStatusChange={(s) => handleStatusChange(task.id, s)}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
```''', r'''<think>
Let me analyze this Apollo Client GraphQL setup and task board component.

1. WebSocket link security:
- `ws://` is used instead of `wss://`. Unencrypted WebSocket exposes auth tokens and all subscription data to network interception.
- connectionParams reads localStorage.getItem('token') at module initialization time, not when the connection is established. If the user logs in after the module loads, the WebSocket uses the stale (null) token.

2. Error link:
- On auth error, it does `window.location.href = '/login'`. This is a hard redirect that loses all in-memory state. In a SPA, this should use the router.
- The auth detection is fragile: `message.includes('not authenticated')`. If the server changes the error message, auth errors are no longer caught.
- graphQLErrors are logged with console.log, not console.error.

3. Retry link:
- `retryIf: (error) => !!error` retries on ALL errors, including auth errors (401) and validation errors (400). Retrying auth errors 5 times is pointless and delays the redirect.
- The retry link is before errorLink in the chain. If a request fails with a network error, it is retried 5 times, THEN the error link handles it. But if the first attempt gets a GraphQL error, does the retry link kick in? The retryIf checks for network errors, not GraphQL errors. So actually, retrying only happens on network errors, which is reasonable. But the condition `!!error` is too broad.

4. Cache merge policies:
- notifications merge appends incoming to existing: [...existing, ...incoming]. This means refetching notifications duplicates them. If the server returns notifications [A, B, C] and then [A, B, C, D], the cache has [A, B, C, A, B, C, D]. Should use keyArgs or merge with deduplication.
- tasks merge replaces entirely, which is correct but means any local optimistic updates are lost.

5. GET_TASKS over-fetching:
- The query fetches comments (with author), attachments, and full assignee data for every task. On a board view, you only need task title, status, and maybe assignee name. Comments and attachments are detail-level data that should be fetched when a task is opened.
- For a project with 100 tasks, each with 10 comments and 5 attachments, this is a massive payload.

6. Redundant data fetching:
- TaskBoard uses both pollInterval (30 seconds) AND a subscription that calls refetch() on every task update. This means:
  a) The subscription fires on every task update, triggering a full refetch.
  b) The poll interval also refetches every 30 seconds.
  This is redundant. The subscription should update the cache directly instead of triggering a full refetch. And the poll interval is unnecessary if the subscription is active.

7. UPDATE_TASK returns only id, title, status. But the task in the cache also has assignee, comments, etc. Apollo will merge the partial result, but fields not returned remain stale. If another user changed the assignee, the local cache still shows the old assignee until the next full refetch.

8. handleStatusChange does not use optimistic updates. The UI waits for the server round-trip before showing the status change, which feels sluggish for a drag-and-drop board.

9. No error handling in handleStatusChange. If the mutation fails, the error is silently swallowed.

Let me write the review.
</think>

## Code Review: Apollo Client GraphQL Task Board

### CRITICAL - Unencrypted WebSocket

**WS1: ws:// exposes auth tokens (Severity: CRITICAL)**
```typescript
uri: `ws://${window.location.host}/graphql`,
```
Unencrypted WebSocket traffic exposes the auth token in `connectionParams` and all subscription data to network interception (MITM attacks). Use `wss://`:
```typescript
uri: `wss://${window.location.host}/graphql`,
```

### HIGH - Stale WebSocket Auth Token

**TK1: Token read at module load time (Severity: HIGH)**
```typescript
connectionParams: {
  authToken: localStorage.getItem('token'),
},
```
`localStorage.getItem('token')` is evaluated once when the module loads. If the user logs in after the page loads, the WebSocket connection uses the old (null) token. Use a function:
```typescript
connectionParams: () => ({
  authToken: localStorage.getItem('token'),
}),
```

### HIGH - Subscription Triggers Full Refetch

**RF1: Refetch on every subscription event (Severity: HIGH)**
```typescript
onData: ({ data: subData }) => {
  refetch();
},
```
Every task update triggers a full query refetch, negating the benefit of subscriptions. The subscription already returns the updated task data. Update the cache directly:
```typescript
onData: ({ data: subData, client }) => {
  const updatedTask = subData.data.taskUpdated;
  client.cache.modify({
    id: client.cache.identify({ __typename: 'Task', id: updatedTask.id }),
    fields: {
      status: () => updatedTask.status,
      title: () => updatedTask.title,
    },
  });
},
```
Also remove `pollInterval: 30000` since the subscription provides real-time updates.

### HIGH - Massive Over-Fetching

**OF1: Board query fetches comments and attachments (Severity: HIGH)**
```graphql
tasks {
  id title description status
  assignee { id name email avatar }
  comments { id text author { id name } createdAt }
  attachments { id filename url size }
  createdAt updatedAt
}
```
A board view only needs task title, status, and assignee name. For 100 tasks with 10 comments each, this transfers orders of magnitude more data than needed. Split into a lightweight board query and a detailed task query:
```graphql
query GetBoardTasks($projectId: ID!) {
  project(id: $projectId) {
    tasks { id title status assignee { id name } }
  }
}
```
Fetch comments and attachments on demand when the user opens a task.

### MEDIUM - Notification Cache Duplicates

**NC1: Merge appends without deduplication (Severity: MEDIUM)**
```typescript
notifications: {
  merge(existing = [], incoming) {
    return [...existing, ...incoming];
  },
},
```
Refetching notifications appends duplicates. Use keyArgs and deduplicate by ID:
```typescript
notifications: {
  keyArgs: false,
  merge(existing = [], incoming, { readField }) {
    const existingIds = new Set(existing.map(ref => readField('id', ref)));
    const merged = [...existing];
    for (const item of incoming) {
      if (!existingIds.has(readField('id', item))) {
        merged.push(item);
      }
    }
    return merged;
  },
},
```

### MEDIUM - Retry on All Errors

**RT1: Auth errors retried 5 times (Severity: MEDIUM)**
```typescript
retryIf: (error) => !!error
```
This retries on all network errors including 401 (Unauthorized). Five retries on auth errors delays the login redirect by several seconds. Check the status:
```typescript
retryIf: (error) => {
  return !!error && (!error.statusCode || error.statusCode >= 500);
}
```

### MEDIUM - No Optimistic Update on Status Change

**OU1: UI waits for server round-trip (Severity: MEDIUM)**
`handleStatusChange` awaits the mutation without optimistic response. For a drag-and-drop board, the card snaps back to its original column until the server responds. Add optimistic response:
```typescript
await updateTask({
  variables: { id: taskId, input: { status: newStatus } },
  optimisticResponse: {
    updateTask: { __typename: 'Task', id: taskId, title: task.title, status: newStatus },
  },
});
```

### MEDIUM - No Error Handling on Mutation

**EH1: Status change errors silently swallowed (Severity: MEDIUM)**
`handleStatusChange` has no try/catch. If the mutation fails, the user sees no feedback. Add error handling and notify the user.

### LOW - Fragile Auth Error Detection

**AE1: String matching for auth errors (Severity: LOW)**
`message.includes('not authenticated')` breaks if the server changes the error message. Use error codes or extensions:
```typescript
if (extensions?.code === 'UNAUTHENTICATED') { ... }
```'''),
]
