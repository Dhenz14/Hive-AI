"""API patterns — GraphQL, tRPC, and real-time APIs."""

PAIRS = [
    (
        "api/graphql-patterns",
        "Show GraphQL patterns: schema design, resolvers, DataLoader, subscriptions, and error handling.",
        '''GraphQL patterns with Strawberry (Python):

```python
import strawberry
from strawberry.types import Info
from strawberry.scalars import JSON
from strawberry.dataloader import DataLoader
from typing import Optional
import asyncio


# --- Schema definition ---

@strawberry.type
class User:
    id: strawberry.ID
    name: str
    email: str
    avatar_url: Optional[str] = None

    @strawberry.field
    async def orders(self, info: Info) -> list["Order"]:
        """Resolved lazily — only fetched if requested."""
        loader = info.context["order_loader"]
        return await loader.load(self.id)

    @strawberry.field
    async def order_count(self, info: Info) -> int:
        orders = await self.orders(info)
        return len(orders)


@strawberry.type
class Order:
    id: strawberry.ID
    user_id: strawberry.ID
    total: float
    status: str
    items: list["OrderItem"]


@strawberry.type
class OrderItem:
    product_id: str
    name: str
    quantity: int
    price: float


# --- Input types ---

@strawberry.input
class CreateUserInput:
    name: str
    email: str
    password: str


@strawberry.input
class UpdateUserInput:
    name: Optional[str] = None
    email: Optional[str] = None


@strawberry.input
class OrderFilterInput:
    status: Optional[str] = None
    min_total: Optional[float] = None
    max_total: Optional[float] = None


# --- Pagination ---

@strawberry.type
class UserConnection:
    items: list[User]
    total: int
    has_next: bool
    cursor: Optional[str] = None


# --- Query resolvers ---

@strawberry.type
class Query:
    @strawberry.field
    async def user(self, id: strawberry.ID, info: Info) -> Optional[User]:
        db = info.context["db"]
        row = await db.fetchone("SELECT * FROM users WHERE id = $1", id)
        return User(**dict(row)) if row else None

    @strawberry.field
    async def users(
        self,
        info: Info,
        limit: int = 20,
        cursor: Optional[str] = None,
        search: Optional[str] = None,
    ) -> UserConnection:
        db = info.context["db"]
        query = "SELECT * FROM users"
        params = []

        if search:
            query += " WHERE name ILIKE $1"
            params.append(f"%{search}%")

        if cursor:
            query += " AND id > $" + str(len(params) + 1)
            params.append(cursor)

        query += f" ORDER BY id LIMIT {limit + 1}"
        rows = await db.fetch(query, *params)

        has_next = len(rows) > limit
        items = [User(**dict(r)) for r in rows[:limit]]

        return UserConnection(
            items=items,
            total=await db.fetchval("SELECT COUNT(*) FROM users"),
            has_next=has_next,
            cursor=items[-1].id if items else None,
        )


# --- Mutation resolvers ---

@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_user(self, input: CreateUserInput, info: Info) -> User:
        db = info.context["db"]
        row = await db.fetchone(
            "INSERT INTO users (name, email, password_hash) "
            "VALUES ($1, $2, $3) RETURNING *",
            input.name, input.email, hash_password(input.password),
        )
        return User(**dict(row))

    @strawberry.mutation
    async def update_user(
        self, id: strawberry.ID, input: UpdateUserInput, info: Info,
    ) -> User:
        db = info.context["db"]
        updates = {k: v for k, v in strawberry.asdict(input).items() if v is not None}
        if not updates:
            raise ValueError("No fields to update")
        # ... build and execute update query ...


# --- DataLoader (N+1 prevention) ---

async def load_orders_batch(user_ids: list[str]) -> list[list[Order]]:
    """Batch-load orders for multiple users in single query."""
    rows = await db.fetch(
        "SELECT * FROM orders WHERE user_id = ANY($1)",
        user_ids,
    )

    # Group by user_id
    orders_by_user: dict[str, list[Order]] = {uid: [] for uid in user_ids}
    for row in rows:
        order = Order(**dict(row))
        orders_by_user[row["user_id"]].append(order)

    # Return in same order as input
    return [orders_by_user[uid] for uid in user_ids]


# Context setup:
# async def get_context():
#     return {
#         "db": database_pool,
#         "order_loader": DataLoader(load_fn=load_orders_batch),
#     }


# --- Subscriptions (real-time) ---

@strawberry.type
class Subscription:
    @strawberry.subscription
    async def order_updates(
        self, user_id: strawberry.ID,
    ) -> asyncio.AsyncGenerator[Order, None]:
        """Stream order updates in real-time."""
        async for event in subscribe_to_channel(f"orders:{user_id}"):
            yield Order(**event)


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
)
```

GraphQL patterns:
1. **DataLoader** — batch N+1 queries into single `WHERE id = ANY($1)` query
2. **Cursor pagination** — `UserConnection` with `has_next` + `cursor`
3. **Lazy field resolution** — `orders` field only queries DB if client requests it
4. **Input types** — separate types for create vs update (partial updates)
5. **Subscriptions** — async generators for real-time data streaming'''
    ),
    (
        "api/trpc-patterns",
        "Show tRPC patterns: type-safe APIs, routers, middleware, and React Query integration.",
        '''tRPC type-safe API patterns:

```typescript
// --- Server: Router definition ---

// server/trpc.ts
import { initTRPC, TRPCError } from '@trpc/server';
import { z } from 'zod';
import type { Context } from './context';

const t = initTRPC.context<Context>().create();

// Middleware
const isAuthed = t.middleware(({ ctx, next }) => {
  if (!ctx.user) {
    throw new TRPCError({ code: 'UNAUTHORIZED' });
  }
  return next({ ctx: { ...ctx, user: ctx.user } });
});

export const router = t.router;
export const publicProcedure = t.procedure;
export const protectedProcedure = t.procedure.use(isAuthed);


// --- Router with procedures ---

// server/routers/users.ts
import { router, publicProcedure, protectedProcedure } from '../trpc';
import { z } from 'zod';

export const userRouter = router({
  // Query (GET)
  getById: publicProcedure
    .input(z.object({ id: z.string().uuid() }))
    .query(async ({ input, ctx }) => {
      const user = await ctx.db.users.findUnique({
        where: { id: input.id },
      });
      if (!user) {
        throw new TRPCError({
          code: 'NOT_FOUND',
          message: `User ${input.id} not found`,
        });
      }
      return user;
    }),

  // List with pagination
  list: publicProcedure
    .input(z.object({
      cursor: z.string().optional(),
      limit: z.number().min(1).max(100).default(20),
      search: z.string().optional(),
    }))
    .query(async ({ input, ctx }) => {
      const items = await ctx.db.users.findMany({
        take: input.limit + 1,
        cursor: input.cursor ? { id: input.cursor } : undefined,
        where: input.search
          ? { name: { contains: input.search } }
          : undefined,
        orderBy: { createdAt: 'desc' },
      });

      let nextCursor: string | undefined;
      if (items.length > input.limit) {
        const next = items.pop();
        nextCursor = next!.id;
      }

      return { items, nextCursor };
    }),

  // Mutation (POST)
  create: protectedProcedure
    .input(z.object({
      name: z.string().min(1).max(100),
      email: z.string().email(),
    }))
    .mutation(async ({ input, ctx }) => {
      return ctx.db.users.create({
        data: { ...input, createdBy: ctx.user.id },
      });
    }),

  // Update
  update: protectedProcedure
    .input(z.object({
      id: z.string().uuid(),
      name: z.string().min(1).max(100).optional(),
      email: z.string().email().optional(),
    }))
    .mutation(async ({ input, ctx }) => {
      const { id, ...data } = input;
      return ctx.db.users.update({ where: { id }, data });
    }),
});


// --- App router ---

// server/routers/index.ts
import { router } from '../trpc';
import { userRouter } from './users';
import { orderRouter } from './orders';

export const appRouter = router({
  users: userRouter,
  orders: orderRouter,
});

export type AppRouter = typeof appRouter;


// --- Client: React integration ---

// utils/trpc.ts
import { createTRPCReact } from '@trpc/react-query';
import type { AppRouter } from '../server/routers';

export const trpc = createTRPCReact<AppRouter>();


// --- Client usage in components ---

// components/UserList.tsx
import { trpc } from '../utils/trpc';

function UserList() {
  // Fully typed — autocomplete for input and output
  const { data, isLoading, fetchNextPage, hasNextPage } =
    trpc.users.list.useInfiniteQuery(
      { limit: 20 },
      { getNextPageParam: (lastPage) => lastPage.nextCursor },
    );

  const createUser = trpc.users.create.useMutation({
    onSuccess: () => {
      // Invalidate cache to refetch list
      utils.users.list.invalidate();
    },
  });

  if (isLoading) return <div>Loading...</div>;

  return (
    <div>
      {data?.pages.flatMap(page =>
        page.items.map(user => (
          <div key={user.id}>{user.name}</div>
        ))
      )}

      {hasNextPage && (
        <button onClick={() => fetchNextPage()}>Load More</button>
      )}

      <button onClick={() => createUser.mutate({
        name: 'Alice',
        email: 'alice@example.com',
      })}>
        Add User
      </button>
    </div>
  );
}


// --- Optimistic updates ---

const utils = trpc.useUtils();

const deleteMutation = trpc.users.delete.useMutation({
  onMutate: async (input) => {
    await utils.users.list.cancel();
    const previous = utils.users.list.getData();

    // Optimistically remove from cache
    utils.users.list.setData(undefined, (old) =>
      old ? { ...old, items: old.items.filter(u => u.id !== input.id) } : old
    );

    return { previous };
  },
  onError: (err, input, context) => {
    // Rollback on error
    if (context?.previous) {
      utils.users.list.setData(undefined, context.previous);
    }
  },
  onSettled: () => {
    utils.users.list.invalidate();
  },
});
```

tRPC patterns:
1. **`AppRouter` type export** — single type shares server types with client
2. **Zod validation** — `.input(z.object(...))` validates at runtime, infers types
3. **Middleware chain** — `isAuthed` middleware adds typed `ctx.user`
4. **`useInfiniteQuery`** — cursor-based infinite scroll with type safety
5. **Optimistic updates** — update UI immediately, rollback on server error'''
    ),
    (
        "api/websocket-patterns",
        "Show WebSocket patterns: connection management, rooms, heartbeats, and reconnection.",
        '''WebSocket patterns:

```python
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
app = FastAPI()


# --- Connection manager ---

@dataclass
class Connection:
    websocket: WebSocket
    user_id: str
    rooms: set[str] = field(default_factory=set)
    connected_at: float = field(default_factory=time.time)
    last_ping: float = field(default_factory=time.time)


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, Connection] = {}  # user_id -> Connection
        self._rooms: dict[str, set[str]] = {}          # room -> set of user_ids

    async def connect(self, websocket: WebSocket, user_id: str) -> Connection:
        await websocket.accept()
        conn = Connection(websocket=websocket, user_id=user_id)
        self._connections[user_id] = conn
        logger.info("Connected: %s (total: %d)", user_id, len(self._connections))
        return conn

    def disconnect(self, user_id: str):
        conn = self._connections.pop(user_id, None)
        if conn:
            for room in conn.rooms:
                self._rooms.get(room, set()).discard(user_id)
            logger.info("Disconnected: %s", user_id)

    async def send(self, user_id: str, data: dict):
        """Send message to specific user."""
        conn = self._connections.get(user_id)
        if conn:
            try:
                await conn.websocket.send_json(data)
            except Exception:
                self.disconnect(user_id)

    async def broadcast(self, data: dict, exclude: str | None = None):
        """Send message to all connected users."""
        disconnected = []
        for uid, conn in self._connections.items():
            if uid == exclude:
                continue
            try:
                await conn.websocket.send_json(data)
            except Exception:
                disconnected.append(uid)
        for uid in disconnected:
            self.disconnect(uid)

    async def send_to_room(self, room: str, data: dict,
                           exclude: str | None = None):
        """Send message to all users in a room."""
        for uid in self._rooms.get(room, set()):
            if uid != exclude:
                await self.send(uid, data)

    def join_room(self, user_id: str, room: str):
        self._rooms.setdefault(room, set()).add(user_id)
        conn = self._connections.get(user_id)
        if conn:
            conn.rooms.add(room)

    def leave_room(self, user_id: str, room: str):
        self._rooms.get(room, set()).discard(user_id)
        conn = self._connections.get(user_id)
        if conn:
            conn.rooms.discard(room)

    @property
    def online_users(self) -> list[str]:
        return list(self._connections.keys())


manager = ConnectionManager()


# --- WebSocket endpoint ---

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    conn = await manager.connect(websocket, user_id)

    # Start heartbeat task
    heartbeat = asyncio.create_task(send_heartbeat(conn))

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)

            match message.get("type"):
                case "ping":
                    conn.last_ping = time.time()
                    await websocket.send_json({"type": "pong"})

                case "join_room":
                    room = message["room"]
                    manager.join_room(user_id, room)
                    await manager.send_to_room(room, {
                        "type": "user_joined",
                        "user_id": user_id,
                        "room": room,
                    })

                case "leave_room":
                    room = message["room"]
                    manager.leave_room(user_id, room)

                case "message":
                    room = message.get("room")
                    if room:
                        await manager.send_to_room(room, {
                            "type": "message",
                            "user_id": user_id,
                            "content": message["content"],
                            "room": room,
                            "timestamp": time.time(),
                        }, exclude=user_id)

                case _:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {message.get('type')}",
                    })

    except WebSocketDisconnect:
        pass
    finally:
        heartbeat.cancel()
        manager.disconnect(user_id)
        await manager.broadcast({
            "type": "user_left", "user_id": user_id,
        })


async def send_heartbeat(conn: Connection, interval: float = 30.0):
    """Send periodic heartbeat, disconnect if no pong."""
    while True:
        await asyncio.sleep(interval)
        if time.time() - conn.last_ping > interval * 3:
            logger.warning("Client %s heartbeat timeout", conn.user_id)
            await conn.websocket.close()
            break
        await conn.websocket.send_json({"type": "ping"})
```

```javascript
// --- Client: auto-reconnecting WebSocket ---

class ReconnectingWebSocket {
  constructor(url, options = {}) {
    this.url = url;
    this.maxRetries = options.maxRetries ?? 10;
    this.baseDelay = options.baseDelay ?? 1000;
    this.handlers = new Map();
    this.retries = 0;
    this.connect();
  }

  connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.retries = 0;
      this.startHeartbeat();
      this.emit('connected');
    };

    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'pong') return;
      this.emit(msg.type, msg);
    };

    this.ws.onclose = () => {
      this.stopHeartbeat();
      if (this.retries < this.maxRetries) {
        const delay = this.baseDelay * Math.pow(2, this.retries);
        setTimeout(() => this.connect(), delay + Math.random() * 1000);
        this.retries++;
      }
    };
  }

  send(type, data = {}) {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, ...data }));
    }
  }

  on(event, handler) {
    if (!this.handlers.has(event)) this.handlers.set(event, new Set());
    this.handlers.get(event).add(handler);
    return () => this.handlers.get(event)?.delete(handler);
  }

  emit(event, data) {
    this.handlers.get(event)?.forEach(fn => fn(data));
  }

  startHeartbeat() {
    this.heartbeat = setInterval(() => this.send('ping'), 25000);
  }

  stopHeartbeat() {
    clearInterval(this.heartbeat);
  }
}
```

WebSocket patterns:
1. **Connection manager** — track connected users, rooms, broadcast
2. **Room-based messaging** — join/leave rooms, send to room members
3. **Heartbeat** — detect dead connections via ping/pong timeout
4. **Auto-reconnect** — exponential backoff with jitter on disconnect
5. **Pattern matching** — `match message["type"]` for clean message routing'''
    ),
]
