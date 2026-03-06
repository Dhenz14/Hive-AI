"""Thinking-trace pairs: GraphQL debugging."""

PAIRS = [
    (
        "thinking/debugging",
        r'''My GraphQL API has severe N+1 query performance issues. When I query a list of users with their posts, each user triggers a separate database query for their posts. DataLoader is supposed to fix this but it is not working. Here is my setup:

import strawberry
from strawberry.dataloader import DataLoader

@strawberry.type
class Post:
    id: int
    title: str
    user_id: int

@strawberry.type
class User:
    id: int
    name: str

    @strawberry.field
    async def posts(self) -> list[Post]:
        # This runs once per user -- N+1 problem!
        rows = await db.fetch("SELECT * FROM posts WHERE user_id = $1", self.id)
        return [Post(**row) for row in rows]

@strawberry.type
class Query:
    @strawberry.field
    async def users(self) -> list[User]:
        rows = await db.fetch("SELECT * FROM users")
        return [User(**row) for row in rows]

# Query: { users { id name posts { title } } }
# With 100 users, this makes 101 database queries!''',
        r'''<think>
The user has 100 users and 101 database queries. The posts resolver runs once per user, each making its own SELECT. Could this be fixed by just using a JOIN in the initial users query? Hmm, that would work for this specific case, but GraphQL's strength is that clients choose which fields to request -- if a client does not ask for posts, you should not fetch them. So preloading with a JOIN is wasteful when posts are not requested.

Wait, I see that DataLoader is imported at the top but never actually used anywhere. The posts field directly queries the database with a per-user WHERE clause. That is the core issue -- DataLoader exists to solve exactly this problem by batching, but importing it does nothing if you do not wire it into the resolver.

I initially considered whether caching alone would help, but no -- each user has a different user_id, so there is nothing to cache. DataLoader's real value is batching: it collects all .load() calls within a single event loop tick and calls the batch function once with all collected keys. So instead of 100 individual SELECTs, you get one SELECT ... WHERE user_id IN (...) query.

One thing I need to be careful about: DataLoader must be created per-request, not shared globally. Since DataLoader caches results per instance, a globally shared one would serve stale data from previous requests. Also, the batch function must return results in the exact same order as the input keys -- if the database returns rows in a different order, the wrong posts get assigned to the wrong users.
</think>

The `posts` resolver queries the database directly for each user instead of using a DataLoader. Here is how to fix the N+1 problem properly:

```python
import strawberry
from strawberry.dataloader import DataLoader
from strawberry.types import Info
from collections import defaultdict
from typing import Optional
import asyncio

# ============================================================
# STEP 1: Create batch loading functions
# ============================================================

async def batch_load_posts(user_ids: list[int]) -> list[list["Post"]]:
    """Load posts for multiple users in ONE query."""
    # Single query for ALL user_ids
    placeholders = ", ".join(f"${i+1}" for i in range(len(user_ids)))
    rows = await db.fetch(
        f"SELECT * FROM posts WHERE user_id IN ({placeholders}) ORDER BY user_id",
        *user_ids,
    )

    # Group posts by user_id
    posts_by_user = defaultdict(list)
    for row in rows:
        posts_by_user[row["user_id"]].append(Post(
            id=row["id"],
            title=row["title"],
            user_id=row["user_id"],
        ))

    # CRITICAL: Return results in the SAME ORDER as user_ids
    # DataLoader requires 1:1 mapping between input keys and results
    return [posts_by_user.get(uid, []) for uid in user_ids]


async def batch_load_users(user_ids: list[int]) -> list[Optional["User"]]:
    """Load users by ID in one query."""
    placeholders = ", ".join(f"${i+1}" for i in range(len(user_ids)))
    rows = await db.fetch(
        f"SELECT * FROM users WHERE id IN ({placeholders})",
        *user_ids,
    )

    users_by_id = {row["id"]: User(id=row["id"], name=row["name"]) for row in rows}
    # Must return in same order as input, with None for missing IDs
    return [users_by_id.get(uid) for uid in user_ids]


# ============================================================
# STEP 2: Create DataLoader context per request
# ============================================================

class GraphQLContext:
    """Per-request context containing DataLoaders."""

    def __init__(self):
        # Each DataLoader must be created per-request
        # to ensure proper batching within a single query
        self.posts_loader = DataLoader(load_fn=batch_load_posts)
        self.users_loader = DataLoader(load_fn=batch_load_users)


async def get_context() -> GraphQLContext:
    """Create fresh context for each GraphQL request."""
    return GraphQLContext()


# ============================================================
# STEP 3: Use DataLoader in resolvers
# ============================================================

@strawberry.type
class Post:
    id: int
    title: str
    user_id: int

    @strawberry.field
    async def author(self, info: Info) -> Optional["User"]:
        # Uses DataLoader -- batched automatically
        return await info.context.users_loader.load(self.user_id)


@strawberry.type
class User:
    id: int
    name: str

    @strawberry.field
    async def posts(self, info: Info) -> list[Post]:
        # Uses DataLoader instead of direct DB query
        # All user.posts calls in one query are batched into ONE DB query
        return await info.context.posts_loader.load(self.id)


@strawberry.type
class Query:
    @strawberry.field
    async def users(self) -> list[User]:
        rows = await db.fetch("SELECT * FROM users")
        return [User(id=row["id"], name=row["name"]) for row in rows]

    @strawberry.field
    async def user(self, id: int, info: Info) -> Optional[User]:
        return await info.context.users_loader.load(id)


# ============================================================
# STEP 4: Wire up with your framework
# ============================================================

schema = strawberry.Schema(query=Query)

# With FastAPI:
from strawberry.fastapi import GraphQLRouter

graphql_app = GraphQLRouter(
    schema,
    context_getter=get_context,  # Creates fresh loaders per request
)

# ============================================================
# RESULT:
# ============================================================
# Before: { users { posts { title } } } with 100 users
#   -> 1 query for users + 100 queries for posts = 101 queries
#
# After (with DataLoader):
#   -> 1 query for users + 1 batched query for ALL posts = 2 queries
#
# DataLoader collects all .load(id) calls within one event loop tick
# and calls batch_load_posts once with all collected IDs.

# ============================================================
# COMMON DATALOADER MISTAKES
# ============================================================

# MISTAKE 1: Sharing DataLoader across requests (stale cache)
# DataLoader caches results per instance. If shared globally,
# request 2 gets cached results from request 1.
# FIX: Always create DataLoader per-request in context_getter.

# MISTAKE 2: Not returning results in input order
# DataLoader expects results[i] to correspond to keys[i].
# If you return results in a different order, data gets mixed up.

# MISTAKE 3: Using DataLoader for mutations
# DataLoader is for reads. Do not batch mutations.
```

**Key points:**
1. DataLoader collects all `.load()` calls in one event loop tick and batches them
2. The batch function MUST return results in the same order as the input keys
3. Create a new DataLoader instance per request (never share globally)
4. This reduces N+1 to exactly 2 queries regardless of result set size''',
    ),
    (
        "thinking/debugging",
        r'''My GraphQL subscription is leaking memory. Over time the server memory grows and eventually crashes. I suspect it is related to clients not properly disconnecting. Here is my subscription setup:

import strawberry
from strawberry.subscriptions import Subscription
import asyncio

active_subscriptions = {}

@strawberry.type
class Subscription:
    @strawberry.subscription
    async def notifications(self, user_id: str) -> AsyncGenerator[str, None]:
        queue = asyncio.Queue()
        active_subscriptions[user_id] = queue

        try:
            while True:
                message = await queue.get()
                yield message
        except Exception:
            pass

# After running for a few hours, memory usage is 4GB+''',
        r'''<think>
Memory growing to 4GB+ over a few hours with subscriptions. Let me trace through the code to find where memory is leaking.

My first thought was that the queue itself is accumulating messages without bound, but actually the queue.get() is called in a tight loop, so messages should be consumed as fast as they arrive. Unless... the client disconnects. When a client disconnects, the async generator should raise GeneratorExit or CancelledError. But look at the exception handler: "except Exception: pass". That swallows the exception silently, and since CancelledError inherits from BaseException (not Exception) in Python 3.9+... hmm, wait, actually in Python 3.8 and earlier CancelledError inherits from Exception. So depending on the Python version, this might or might not catch disconnections.

But even if the exception is caught, the critical problem is what happens after: the while True loop just continues, and the entry in active_subscriptions is never removed. The queue stays allocated, and if messages keep being published to that user_id, they pile up in the queue with nobody consuming them. That is the memory leak.

Actually, there is another problem I almost missed: active_subscriptions[user_id] = queue overwrites any previous queue for the same user_id. So if a user reconnects, the old queue is orphaned -- it is no longer referenced by the dict, but the old coroutine is still blocked on queue.get() forever since there is no timeout. These zombie coroutines and their queues accumulate indefinitely.

The fix needs a finally block that always removes the subscription entry on exit, a timeout on queue.get() to detect dead connections via keepalives, bounded queue size to prevent unbounded growth, and proper handling of CancelledError/GeneratorExit without swallowing them.
</think>

The memory leak comes from multiple issues: the subscription dictionary never cleans up, disconnection exceptions are swallowed, and queues accumulate messages for dead clients.

```python
import strawberry
from strawberry.subscriptions import Subscription
import asyncio
import logging
import time
from typing import AsyncGenerator
from weakref import WeakValueDictionary
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ============================================================
# PROBLEM ANALYSIS
# ============================================================
# 1. active_subscriptions[user_id] = queue -- never deleted
# 2. except Exception: pass -- swallows CancelledError/GeneratorExit
# 3. Queue grows unbounded if client disconnects but entry remains
# 4. No timeout means zombie subscriptions live forever

# ============================================================
# FIX: Subscription manager with proper lifecycle
# ============================================================

@dataclass
class SubscriptionEntry:
    queue: asyncio.Queue
    created_at: float = field(default_factory=time.time)
    last_message_at: float = field(default_factory=time.time)
    message_count: int = 0


class SubscriptionManager:
    """Manages subscription lifecycle with cleanup."""

    def __init__(self, max_queue_size: int = 100, idle_timeout: float = 300):
        self._subscriptions: dict[str, list[SubscriptionEntry]] = {}
        self._max_queue_size = max_queue_size
        self._idle_timeout = idle_timeout
        self._cleanup_task = None

    async def start(self):
        """Start the background cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """Stop the manager and clean up all subscriptions."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        self._subscriptions.clear()
        logger.info("Subscription manager stopped")

    def subscribe(self, user_id: str) -> SubscriptionEntry:
        """Register a new subscription."""
        entry = SubscriptionEntry(
            queue=asyncio.Queue(maxsize=self._max_queue_size),
        )
        if user_id not in self._subscriptions:
            self._subscriptions[user_id] = []
        self._subscriptions[user_id].append(entry)
        logger.info(
            "New subscription for %s (total: %d)",
            user_id, self.total_count,
        )
        return entry

    def unsubscribe(self, user_id: str, entry: SubscriptionEntry):
        """Remove a subscription entry."""
        if user_id in self._subscriptions:
            try:
                self._subscriptions[user_id].remove(entry)
            except ValueError:
                pass
            if not self._subscriptions[user_id]:
                del self._subscriptions[user_id]
        logger.info(
            "Removed subscription for %s (total: %d)",
            user_id, self.total_count,
        )

    async def publish(self, user_id: str, message: str):
        """Send a message to all subscriptions for a user."""
        entries = self._subscriptions.get(user_id, [])
        for entry in entries:
            try:
                entry.queue.put_nowait(message)
                entry.last_message_at = time.time()
                entry.message_count += 1
            except asyncio.QueueFull:
                logger.warning(
                    "Queue full for %s, dropping message", user_id
                )

    async def broadcast(self, message: str):
        """Send a message to ALL subscribers."""
        for user_id in list(self._subscriptions.keys()):
            await self.publish(user_id, message)

    @property
    def total_count(self) -> int:
        return sum(len(v) for v in self._subscriptions.values())

    async def _cleanup_loop(self):
        """Periodically remove stale subscriptions."""
        while True:
            try:
                await asyncio.sleep(60)
                now = time.time()
                stale = []
                for user_id, entries in self._subscriptions.items():
                    for entry in entries:
                        if now - entry.last_message_at > self._idle_timeout:
                            stale.append((user_id, entry))

                for user_id, entry in stale:
                    logger.info("Cleaning stale subscription for %s", user_id)
                    self.unsubscribe(user_id, entry)

                logger.info("Active subscriptions: %d", self.total_count)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Cleanup error: %s", e)


# Global manager instance
sub_manager = SubscriptionManager(max_queue_size=100, idle_timeout=300)


# ============================================================
# FIXED SUBSCRIPTION RESOLVER
# ============================================================

@strawberry.type
class Subscription:
    @strawberry.subscription
    async def notifications(
        self, user_id: str
    ) -> AsyncGenerator[str, None]:
        entry = sub_manager.subscribe(user_id)
        try:
            while True:
                try:
                    # Timeout prevents zombie subscriptions
                    message = await asyncio.wait_for(
                        entry.queue.get(),
                        timeout=30.0,
                    )
                    yield message
                except asyncio.TimeoutError:
                    # Send keepalive to detect dead connections
                    yield '{"type": "keepalive"}'
        except (asyncio.CancelledError, GeneratorExit):
            # Client disconnected -- this is normal
            logger.info("Client %s disconnected", user_id)
        except Exception as e:
            logger.error("Subscription error for %s: %s", user_id, e)
        finally:
            # ALWAYS clean up, regardless of how we exit
            sub_manager.unsubscribe(user_id, entry)


# ============================================================
# WIRE UP LIFECYCLE
# ============================================================

# With FastAPI lifespan:
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    await sub_manager.start()
    yield
    await sub_manager.stop()

app = FastAPI(lifespan=lifespan)
```

**Root causes fixed:**
1. `finally` block ensures cleanup even on disconnect
2. Bounded queue prevents unbounded memory growth
3. Background cleanup task removes stale subscriptions
4. Timeout on `queue.get()` detects dead connections via keepalives
5. Never swallow `CancelledError` or `GeneratorExit` silently''',
    ),
    (
        "thinking/debugging",
        r'''I am using schema stitching to combine two GraphQL schemas but getting field name conflicts and type collisions. Schema A has a "User" type and Schema B also has a "User" type with different fields. Queries fail with "Error: Type User was defined more than once." How do I resolve this?''',
        r'''<think>
Two schemas both define a "User" type with different fields, causing "Type User was defined more than once." Let me think about the best way to resolve this.

My first instinct was to simply rename one of them -- AuthUser and ProfileUser. But that feels wrong because they represent the same entity, just with different facets. Clients would have to know which "User" type to use for which query, breaking the abstraction.

Could I just merge the fields into a single User type manually? That would work for a monolith, but if these are separate microservices, it creates tight coupling -- every time one service adds a field, I need to update the merged type.

Actually, this is exactly the problem GraphQL Federation was designed to solve. With federation, each service defines its own slice of the User type using @key directives, and the gateway merges them transparently. Schema A owns id/email/role and Schema B extends User with displayName/avatarUrl/bio. The gateway resolves references across services automatically.

Hmm, but federation requires an Apollo-compatible gateway and adds operational complexity. For simpler setups, I considered type renaming with namespace prefixes as a middle ground -- it avoids collisions without the federation overhead, though it does expose implementation details to clients. Let me present all the approaches so the user can choose based on their architecture.
</think>

Type name conflicts in schema stitching require either renaming, merging, or using proper federation. Here are the approaches:

```python
# ============================================================
# THE PROBLEM: Two schemas with conflicting "User" type
# ============================================================

# Schema A (Auth Service):
SCHEMA_A = """
type User {
    id: ID!
    email: String!
    role: String!
}

type Query {
    me: User
    userById(id: ID!): User
}
"""

# Schema B (Profile Service):
SCHEMA_B = """
type User {
    id: ID!
    displayName: String!
    avatarUrl: String!
    bio: String
}

type Query {
    profile(userId: ID!): User
}
"""

# Stitching these fails: "Type User was defined more than once"

# ============================================================
# SOLUTION 1: Type merging (combine into single User type)
# ============================================================

# Using graphql-tools or ariadne-style approach:
# Merge fields from both User types into one

MERGED_SCHEMA = """
type User {
    id: ID!
    # From Schema A (auth)
    email: String!
    role: String!
    # From Schema B (profile)
    displayName: String!
    avatarUrl: String!
    bio: String
}

type Query {
    me: User
    userById(id: ID!): User
    profile(userId: ID!): User
}
"""

# Python implementation with Strawberry:
import strawberry
from typing import Optional

@strawberry.type
class User:
    """Merged User type combining auth and profile data."""
    id: strawberry.ID
    # Auth fields
    email: str
    role: str
    # Profile fields
    display_name: str
    avatar_url: Optional[str]
    bio: Optional[str]

@strawberry.type
class Query:
    @strawberry.field
    async def me(self, info) -> User:
        # Fetch from both services and merge
        auth_data = await auth_client.get_current_user(info)
        profile_data = await profile_client.get_profile(auth_data["id"])
        return User(
            id=auth_data["id"],
            email=auth_data["email"],
            role=auth_data["role"],
            display_name=profile_data.get("displayName", ""),
            avatar_url=profile_data.get("avatarUrl"),
            bio=profile_data.get("bio"),
        )

# ============================================================
# SOLUTION 2: Namespace with type renaming
# ============================================================

# Rename conflicting types by adding a prefix

SCHEMA_A_NAMESPACED = """
type AuthUser {
    id: ID!
    email: String!
    role: String!
}

type Query {
    me: AuthUser
    authUserById(id: ID!): AuthUser
}
"""

SCHEMA_B_NAMESPACED = """
type ProfileUser {
    id: ID!
    displayName: String!
    avatarUrl: String!
    bio: String
}

type Query {
    profile(userId: ID!): ProfileUser
}
"""

# In Python with transforms:
@strawberry.type
class AuthUser:
    id: strawberry.ID
    email: str
    role: str

@strawberry.type
class ProfileUser:
    id: strawberry.ID
    display_name: str
    avatar_url: Optional[str]
    bio: Optional[str]

# ============================================================
# SOLUTION 3: GraphQL Federation (best for microservices)
# ============================================================

# Schema A defines the base User entity
SCHEMA_A_FEDERATED = """
type User @key(fields: "id") {
    id: ID!
    email: String!
    role: String!
}

type Query {
    me: User
}
"""

# Schema B extends the User entity with additional fields
SCHEMA_B_FEDERATED = """
extend type User @key(fields: "id") {
    id: ID! @external
    displayName: String!
    avatarUrl: String!
    bio: String
}

type Query {
    profile(userId: ID!): User
}
"""

# Python implementation with Strawberry Federation:

@strawberry.federation.type(keys=["id"])
class User:
    id: strawberry.ID
    email: str = strawberry.federation.field(shareable=True)
    role: str

    @classmethod
    async def resolve_reference(cls, id: strawberry.ID, info) -> "User":
        """Called by the gateway to resolve this entity."""
        data = await auth_service.get_user(id)
        return User(id=id, email=data["email"], role=data["role"])

# In the profile service:
@strawberry.federation.type(keys=["id"], extend=True)
class User:
    id: strawberry.ID = strawberry.federation.field(external=True)
    display_name: str
    avatar_url: Optional[str]
    bio: Optional[str]

    @classmethod
    async def resolve_reference(cls, id: strawberry.ID, info) -> "User":
        data = await profile_service.get_profile(id)
        return User(
            id=id,
            display_name=data["displayName"],
            avatar_url=data.get("avatarUrl"),
            bio=data.get("bio"),
        )

# The federation gateway merges these automatically:
# Query { me { id email role displayName avatarUrl bio } }
# Gateway calls Schema A for id/email/role,
# then Schema B's resolve_reference for displayName/avatarUrl/bio

# ============================================================
# SOLUTION 4: Schema delegation (manual stitching)
# ============================================================

@strawberry.type
class CombinedUser:
    """Wrapper that delegates to both services."""
    id: strawberry.ID

    @strawberry.field
    async def auth(self, info) -> AuthUser:
        return await info.context.auth_loader.load(self.id)

    @strawberry.field
    async def profile(self, info) -> ProfileUser:
        return await info.context.profile_loader.load(self.id)

# Query: { users { id auth { email role } profile { displayName } } }
# Each sub-object comes from its respective service
```

**Recommendation:** For microservices, use **GraphQL Federation** (Solution 3). It handles type conflicts by design, with each service owning its fields and the gateway merging them transparently. For monoliths, type merging (Solution 1) is simpler.''',
    ),
    (
        "thinking/debugging",
        r'''My GraphQL schema has circular type references and I am getting "Cannot access 'UserType' before initialization" errors in Python. Here is my setup:

# types/user.py
from types.post import PostType

@strawberry.type
class UserType:
    id: int
    name: str
    posts: list[PostType]

# types/post.py
from types.user import UserType

@strawberry.type
class PostType:
    id: int
    title: str
    author: UserType

# ImportError: cannot import name 'PostType' from partially initialized module''',
        r'''<think>
The error says "Cannot access 'UserType' before initialization" -- this is a circular import. user.py imports PostType from post.py, and post.py imports UserType from user.py. When Python starts loading user.py, it hits the import of PostType, which triggers loading post.py, which tries to import UserType from the partially-loaded user.py. Since UserType is not defined yet at that point, the import fails.

I initially considered whether rearranging the import order could fix this -- maybe import PostType after defining UserType? But that does not work because the class definition uses PostType in its type annotations, so it needs to be available at class definition time.

Wait, actually -- Python type annotations can use forward references as strings. If I write posts: list["PostType"] instead of posts: list[PostType], Python does not evaluate the string at class definition time. Combined with TYPE_CHECKING to keep the import only for static type checkers, the circular dependency breaks.

But for Strawberry specifically, there is a cleaner approach: strawberry.lazy() provides lazy type resolution designed exactly for this. It tells Strawberry to defer resolving the type reference until the schema is built, by which point both modules are fully loaded. The alternative of putting both types in the same file is the simplest solution but does not scale well as the schema grows. I should present multiple options since the best choice depends on project size.
</think>

This is a circular import problem, not a GraphQL-specific issue. Python cannot import two modules that depend on each other at import time. Here are the solutions:

```python
# ============================================================
# SOLUTION 1: Use strawberry.lazy for lazy type resolution
# ============================================================

# types/user.py
import strawberry
from typing import TYPE_CHECKING, Annotated

@strawberry.type
class UserType:
    id: int
    name: str

    @strawberry.field
    async def posts(self) -> list[Annotated["PostType", strawberry.lazy("types.post")]]:
        """Lazy reference avoids circular import."""
        from types.post import PostType
        rows = await db.fetch("SELECT * FROM posts WHERE user_id = $1", self.id)
        return [PostType(id=r["id"], title=r["title"]) for r in rows]


# types/post.py
import strawberry
from typing import TYPE_CHECKING, Annotated, Optional

@strawberry.type
class PostType:
    id: int
    title: str

    @strawberry.field
    async def author(self) -> Annotated["UserType", strawberry.lazy("types.user")]:
        """Lazy reference avoids circular import."""
        from types.user import UserType
        row = await db.fetchrow("SELECT * FROM users WHERE id = $1", self.author_id)
        return UserType(id=row["id"], name=row["name"])


# ============================================================
# SOLUTION 2: Use typing.TYPE_CHECKING with forward references
# ============================================================

# types/user.py
from __future__ import annotations  # Makes all annotations strings
import strawberry
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types.post import PostType  # Only imported for type checking

@strawberry.type
class UserType:
    id: int
    name: str

    @strawberry.field
    async def posts(self) -> list["PostType"]:
        # Import at runtime, inside the function
        from types.post import PostType
        rows = await db.fetch("SELECT * FROM posts WHERE user_id = $1", self.id)
        return [PostType(id=r["id"], title=r["title"]) for r in rows]


# types/post.py
from __future__ import annotations
import strawberry
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types.user import UserType

@strawberry.type
class PostType:
    id: int
    title: str

    @strawberry.field
    async def author(self) -> "UserType":
        from types.user import UserType
        row = await db.fetchrow("SELECT * FROM users WHERE id = $1", self.author_id)
        return UserType(id=row["id"], name=row["name"])


# ============================================================
# SOLUTION 3: Put all types in one module (simplest)
# ============================================================

# types/all.py
import strawberry
from typing import Optional

@strawberry.type
class UserType:
    id: int
    name: str

    @strawberry.field
    async def posts(self) -> list["PostType"]:
        rows = await db.fetch(
            "SELECT * FROM posts WHERE user_id = $1", self.id
        )
        return [PostType(id=r["id"], title=r["title"]) for r in rows]


@strawberry.type
class PostType:
    id: int
    title: str

    @strawberry.field
    async def author(self) -> "UserType":
        row = await db.fetchrow(
            "SELECT * FROM users WHERE id = $1", self.author_id
        )
        return UserType(id=row["id"], name=row["name"])

# In the same module, forward references ("PostType" as string)
# are resolved after both classes are defined.


# ============================================================
# SOLUTION 4: Interface pattern (decouple the types)
# ============================================================

# types/interfaces.py (no circular deps)
import strawberry

@strawberry.interface
class HasAuthor:
    @strawberry.field
    async def author_id(self) -> int:
        ...

@strawberry.interface
class HasPosts:
    @strawberry.field
    async def post_ids(self) -> list[int]:
        ...

# types/user.py
from types.interfaces import HasPosts

@strawberry.type
class UserType(HasPosts):
    id: int
    name: str
    _post_ids: strawberry.Private[list[int]]

    @strawberry.field
    async def post_ids(self) -> list[int]:
        return self._post_ids

# types/post.py
from types.interfaces import HasAuthor

@strawberry.type
class PostType(HasAuthor):
    id: int
    title: str
    _author_id: strawberry.Private[int]

    @strawberry.field
    async def author_id(self) -> int:
        return self._author_id

# Then resolve the full objects in a top-level resolver or DataLoader
```

**Best practice:** Use `strawberry.lazy()` (Solution 1) for Strawberry projects. It is the officially supported approach for circular type references. For other GraphQL libraries, use `TYPE_CHECKING` with runtime imports inside resolver functions (Solution 2).''',
    ),
    (
        "thinking/debugging",
        r'''My GraphQL API is returning generic "Internal Server Error" messages to clients instead of useful error information. But I also do not want to leak sensitive internal details. How do I design proper error handling that is useful for clients but safe?

Currently when a resolver throws an exception, clients see:
{
  "errors": [{"message": "Internal Server Error"}],
  "data": null
}''',
        r'''<think>
The client gets "Internal Server Error" for everything, which is secure but useless for debugging. My first thought was to just expose all error messages -- but that would leak stack traces, SQL queries, and internal service names, which is a security risk.

Could I use HTTP status codes instead? Hmm, GraphQL always returns 200 with errors in the response body, so HTTP status codes are not the right mechanism here. The GraphQL spec uses the "errors" array with optional "extensions" for structured error metadata.

Wait, the real insight is that there are two categories of errors: business errors (not found, validation failed, permission denied) that are safe and useful to expose, and unexpected errors (database connection failed, null pointer, etc.) that should be masked. I considered using a single error format for both, but actually the masking strategy should differ. Business errors need the actual message and a machine-readable code. Internal errors need a generic message plus a reference ID that support can use to look up the full details in server logs.

So the approach is: create an AppError base class for intentional business errors. In the error formatter, check if the original exception is an AppError -- if yes, expose its message and code. If no, generate a unique reference ID, log the full traceback server-side, and return a generic message with the reference. This gives clients actionable information for expected errors while keeping internal details private.
</think>

You need a layered error handling strategy: expose business errors to clients while masking unexpected internal errors. Here is how:

```python
import strawberry
from strawberry.types import Info
from enum import Enum
import logging
import traceback
import uuid

logger = logging.getLogger(__name__)

# ============================================================
# STEP 1: Define custom error types (safe to expose)
# ============================================================

class AppError(Exception):
    """Base class for errors safe to expose to clients."""

    def __init__(self, message: str, code: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"{resource} not found",
            code="NOT_FOUND",
            status_code=404,
        )
        self.resource = resource
        self.resource_id = resource_id


class ValidationError(AppError):
    def __init__(self, field: str, message: str):
        super().__init__(
            message=f"Validation error on '{field}': {message}",
            code="VALIDATION_ERROR",
            status_code=400,
        )
        self.field = field


class PermissionError(AppError):
    def __init__(self, action: str):
        super().__init__(
            message=f"You do not have permission to {action}",
            code="FORBIDDEN",
            status_code=403,
        )


class RateLimitError(AppError):
    def __init__(self, retry_after: int = 60):
        super().__init__(
            message="Rate limit exceeded",
            code="RATE_LIMITED",
            status_code=429,
        )
        self.retry_after = retry_after


# ============================================================
# STEP 2: Custom error formatter (the key piece)
# ============================================================

from strawberry.extensions import SchemaExtension
from graphql import GraphQLError

def format_error(error: GraphQLError) -> dict:
    """Format errors for client consumption."""
    original = error.original_error

    if isinstance(original, AppError):
        # Business error -- safe to expose with details
        formatted = {
            "message": original.message,
            "extensions": {
                "code": original.code,
                "status_code": original.status_code,
            },
        }
        # Add error-specific fields
        if isinstance(original, NotFoundError):
            formatted["extensions"]["resource"] = original.resource
        elif isinstance(original, ValidationError):
            formatted["extensions"]["field"] = original.field
        elif isinstance(original, RateLimitError):
            formatted["extensions"]["retry_after"] = original.retry_after

        if error.path:
            formatted["path"] = error.path

        return formatted

    else:
        # Unexpected error -- mask details, log internally
        error_id = str(uuid.uuid4())[:8]

        logger.error(
            "Unhandled error [%s]: %s\n%s",
            error_id,
            str(original or error),
            traceback.format_exc(),
        )

        return {
            "message": "An internal error occurred. Reference: " + error_id,
            "extensions": {
                "code": "INTERNAL_ERROR",
                "reference": error_id,
            },
            "path": error.path,
        }


# ============================================================
# STEP 3: Apply error formatter to schema
# ============================================================

class ErrorLoggingExtension(SchemaExtension):
    """Log all errors with context."""

    async def on_execute(self):
        yield
        result = self.execution_context.result
        if result and result.errors:
            for error in result.errors:
                if not isinstance(error.original_error, AppError):
                    logger.error(
                        "GraphQL error in %s: %s",
                        self.execution_context.query,
                        error,
                    )


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[ErrorLoggingExtension],
)

# Override the default error formatter
# In FastAPI with Strawberry:
from strawberry.fastapi import GraphQLRouter

graphql_app = GraphQLRouter(
    schema,
    # Custom process_result to format errors
)

# ============================================================
# STEP 4: Use errors in resolvers
# ============================================================

@strawberry.type
class Query:
    @strawberry.field
    async def user(self, id: int, info: Info) -> "UserType":
        user = await db.get_user(id)
        if not user:
            raise NotFoundError("User", str(id))

        current_user = info.context.get("current_user")
        if not current_user:
            raise PermissionError("view user profiles")

        return UserType(**user)


@strawberry.type
class Mutation:
    @strawberry.field
    async def update_profile(
        self, name: str, info: Info
    ) -> "UserType":
        if len(name) < 2:
            raise ValidationError("name", "Must be at least 2 characters")
        if len(name) > 100:
            raise ValidationError("name", "Must be at most 100 characters")

        # This might throw an unexpected DB error --
        # it will be masked with a reference ID
        user = await db.update_user(info.context["user_id"], name=name)
        return UserType(**user)
```

**Error response examples:**

Business error (exposed): `{"errors": [{"message": "User not found", "extensions": {"code": "NOT_FOUND", "resource": "User"}}]}`

Internal error (masked): `{"errors": [{"message": "An internal error occurred. Reference: a1b2c3d4", "extensions": {"code": "INTERNAL_ERROR", "reference": "a1b2c3d4"}}]}`

Clients get actionable information for business errors and a reference ID for internal errors that support can look up in server logs.''',
    ),
]
