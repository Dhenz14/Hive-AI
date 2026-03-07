"""Code translation pairs: OOP class-based to functional style."""

PAIRS = [
    (
        "code-translation/class-to-functional",
        r'''Refactor this Python class-based state machine to a functional style:

class OrderStateMachine:
    TRANSITIONS = {
        "pending":    ["confirmed", "cancelled"],
        "confirmed":  ["shipped", "cancelled"],
        "shipped":    ["delivered", "returned"],
        "delivered":  ["returned"],
        "cancelled":  [],
        "returned":   [],
    }

    def __init__(self, order_id):
        self.order_id = order_id
        self.state = "pending"
        self.history = []

    def transition(self, new_state):
        if new_state not in self.TRANSITIONS.get(self.state, []):
            raise ValueError(f"Cannot go from {self.state} to {new_state}")
        self.history.append(self.state)
        self.state = new_state

    def can_transition(self, new_state):
        return new_state in self.TRANSITIONS.get(self.state, [])''',
        r'''<think>
Converting a stateful class to functional style. The key principle: instead of mutating `self.state`, return a new state record. Functions operate on data, not on objects.

In functional style:
- The state machine config (TRANSITIONS) becomes a plain dict/constant
- The order state becomes an immutable data record (namedtuple or dict)
- transition() becomes a pure function that takes old state and returns new state
- No self, no mutation

I should use a namedtuple or frozen dataclass for immutability. Actually for pure functional, I'll use plain tuples/dicts and standalone functions.

One interesting choice: history. In OOP we append to a list (mutation). In functional style, we create a new tuple with the old state appended. This naturally gives us an immutable audit trail.
</think>

```python
from typing import NamedTuple, Tuple

# Immutable state record
class OrderState(NamedTuple):
    order_id: str
    state: str
    history: Tuple[str, ...]

# Pure data -- no class needed
TRANSITIONS = {
    "pending":    ("confirmed", "cancelled"),
    "confirmed":  ("shipped", "cancelled"),
    "shipped":    ("delivered", "returned"),
    "delivered":  ("returned",),
    "cancelled":  (),
    "returned":   (),
}

# Pure functions operating on data

def create_order(order_id: str) -> OrderState:
    return OrderState(order_id=order_id, state="pending", history=())

def can_transition(order: OrderState, new_state: str) -> bool:
    return new_state in TRANSITIONS.get(order.state, ())

def transition(order: OrderState, new_state: str) -> OrderState:
    if not can_transition(order, new_state):
        raise ValueError(
            f"Cannot go from {order.state} to {new_state}"
        )
    # Return NEW state -- no mutation
    return OrderState(
        order_id=order.order_id,
        state=new_state,
        history=order.history + (order.state,),
    )

# Usage -- each call returns a new immutable value
order = create_order("ORD-001")
order = transition(order, "confirmed")
order = transition(order, "shipped")
order = transition(order, "delivered")
# order.history == ("pending", "confirmed", "shipped")
# order.state == "delivered"
```

What changed:

- `class OrderStateMachine` with mutable `self.state` -> `NamedTuple` (immutable) + pure functions
- `self.history.append(state)` mutation -> `history + (state,)` creates a new tuple
- `self.transition(new_state)` method -> `transition(order, new_state)` standalone function returning new state
- TRANSITIONS stays the same -- it was already pure data
- Every function is referentially transparent: same inputs always produce same outputs, no side effects''',
    ),
    (
        "code-translation/class-to-functional",
        r'''Convert this JavaScript class-based React component to functional style with hooks:

class UserProfile extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      user: null,
      loading: true,
      error: null,
    };
  }

  componentDidMount() {
    this.fetchUser();
  }

  componentDidUpdate(prevProps) {
    if (prevProps.userId !== this.props.userId) {
      this.fetchUser();
    }
  }

  async fetchUser() {
    this.setState({ loading: true, error: null });
    try {
      const res = await fetch(`/api/users/${this.props.userId}`);
      if (!res.ok) throw new Error("Failed to fetch");
      const user = await res.json();
      this.setState({ user, loading: false });
    } catch (err) {
      this.setState({ error: err.message, loading: false });
    }
  }

  render() {
    const { user, loading, error } = this.state;
    if (loading) return <div>Loading...</div>;
    if (error) return <div>Error: {error}</div>;
    return (
      <div>
        <h1>{user.name}</h1>
        <p>{user.email}</p>
      </div>
    );
  }
}''',
        r'''```jsx
function UserProfile({ userId }) {
  const [user, setUser] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    let cancelled = false;

    async function fetchUser() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/users/" + userId);
        if (!res.ok) throw new Error("Failed to fetch");
        const data = await res.json();
        if (!cancelled) {
          setUser(data);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
          setLoading(false);
        }
      }
    }

    fetchUser();

    // Cleanup: prevent state updates on unmounted component
    return () => { cancelled = true; };
  }, [userId]);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  return (
    <div>
      <h1>{user.name}</h1>
      <p>{user.email}</p>
    </div>
  );
}
```

What changed:

- `class extends React.Component` -> plain function
- `constructor` with `this.state = {...}` -> three `useState` calls (one per state variable)
- `componentDidMount` + `componentDidUpdate` -> single `useEffect` with `[userId]` dependency array
- `this.setState({...})` -> individual setter functions (`setUser`, `setLoading`)
- `this.props.userId` -> destructured `{ userId }` parameter
- Added cleanup function returning `() => { cancelled = true }` to prevent state updates after unmount -- the class version had this bug
- No `this` keyword anywhere -- closures capture variables naturally
- The `[userId]` dependency array replaces the manual `prevProps.userId !== this.props.userId` check''',
    ),
    (
        "code-translation/class-to-functional",
        r'''Refactor this Python class-based builder pattern to a functional pipeline:

class QueryBuilder:
    def __init__(self, table):
        self.table = table
        self.conditions = []
        self.order = None
        self.limit_val = None
        self.columns = ["*"]

    def select(self, *cols):
        self.columns = list(cols)
        return self

    def where(self, condition):
        self.conditions.append(condition)
        return self

    def order_by(self, column, desc=False):
        self.order = f"{column} {'DESC' if desc else 'ASC'}"
        return self

    def limit(self, n):
        self.limit_val = n
        return self

    def build(self):
        sql = f"SELECT {', '.join(self.columns)} FROM {self.table}"
        if self.conditions:
            sql += " WHERE " + " AND ".join(self.conditions)
        if self.order:
            sql += f" ORDER BY {self.order}"
        if self.limit_val:
            sql += f" LIMIT {self.limit_val}"
        return sql

# Usage: QueryBuilder("users").select("name","email").where("age > 18").order_by("name").limit(10).build()''',
        r'''<think>
The builder pattern is inherently about accumulating state through method chaining. In functional style, there are a few approaches:

1. Pipe/compose functions that transform an immutable config dict
2. Use reduce with a list of transform functions
3. Use a namedtuple/frozen dataclass and return new instances

I think option 1 is cleanest -- a query config dict that gets passed through a pipeline of functions, each returning a new dict.

The method chaining `QueryBuilder().select().where().build()` becomes a function pipeline. In Python there's no built-in pipe operator, but I can use functools.reduce or just sequential function calls.

Actually, the most Pythonic functional approach would be a single `build_query` function that takes keyword arguments. But that loses composability. Let me do the pipeline approach with closures that return transform functions, then a compose/pipe utility.
</think>

```python
from typing import NamedTuple, Tuple, Optional, Callable

# Immutable query config
class Query(NamedTuple):
    table: str
    columns: Tuple[str, ...] = ("*",)
    conditions: Tuple[str, ...] = ()
    order: Optional[str] = None
    limit_val: Optional[int] = None

# Each function returns a NEW Query -- no mutation

def select(*cols):
    # Returns a transform function
    def apply(q: Query) -> Query:
        return q._replace(columns=cols)
    return apply

def where(condition: str):
    def apply(q: Query) -> Query:
        return q._replace(conditions=q.conditions + (condition,))
    return apply

def order_by(column: str, desc: bool = False):
    def apply(q: Query) -> Query:
        direction = "DESC" if desc else "ASC"
        return q._replace(order=column + " " + direction)
    return apply

def limit(n: int):
    def apply(q: Query) -> Query:
        return q._replace(limit_val=n)
    return apply

def pipe(query: Query, *transforms: Callable) -> Query:
    result = query
    for fn in transforms:
        result = fn(result)
    return result

def build(q: Query) -> str:
    sql = "SELECT " + ", ".join(q.columns) + " FROM " + q.table
    if q.conditions:
        sql += " WHERE " + " AND ".join(q.conditions)
    if q.order:
        sql += " ORDER BY " + q.order
    if q.limit_val is not None:
        sql += " LIMIT " + str(q.limit_val)
    return sql

# Usage:
query = pipe(
    Query("users"),
    select("name", "email"),
    where("age > 18"),
    order_by("name"),
    limit(10),
)
sql = build(query)
# SELECT name, email FROM users WHERE age > 18 ORDER BY name ASC LIMIT 10
```

What changed:

- Mutable class with `self.conditions.append()` -> immutable `NamedTuple` with `_replace()` creating new instances
- Method chaining (`obj.select().where()`) -> `pipe(data, fn1, fn2, ...)` function composition
- Builder methods -> factory functions returning transform closures
- `build()` method -> standalone pure function taking a Query value
- Each transform is a reusable, composable unit: `where("active = true")` can be stored and applied to any query''',
    ),
    (
        "code-translation/class-to-functional",
        r'''Convert this TypeScript class-based service layer to functional style:

class UserService {
  private db: Database;
  private cache: Cache;
  private logger: Logger;

  constructor(db: Database, cache: Cache, logger: Logger) {
    this.db = db;
    this.cache = cache;
    this.logger = logger;
  }

  async getUser(id: string): Promise<User | null> {
    const cached = await this.cache.get(`user:${id}`);
    if (cached) return cached as User;

    const user = await this.db.query("SELECT * FROM users WHERE id = $1", [id]);
    if (user) {
      await this.cache.set(`user:${id}`, user, 300);
    }
    this.logger.info(`Fetched user ${id}`);
    return user;
  }

  async createUser(data: CreateUserDTO): Promise<User> {
    const user = await this.db.query(
      "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING *",
      [data.name, data.email]
    );
    this.logger.info(`Created user ${user.id}`);
    return user;
  }
}''',
        r'''```typescript
// Dependencies passed as a context object instead of class fields
interface Deps {
  db: Database;
  cache: Cache;
  logger: Logger;
}

// Pure functions that take dependencies explicitly

async function getUser(
  deps: Deps,
  id: string
): Promise<User | null> {
  const cached = await deps.cache.get("user:" + id);
  if (cached) return cached as User;

  const user = await deps.db.query(
    "SELECT * FROM users WHERE id = $1", [id]
  );
  if (user) {
    await deps.cache.set("user:" + id, user, 300);
  }
  deps.logger.info("Fetched user " + id);
  return user;
}

async function createUser(
  deps: Deps,
  data: CreateUserDTO
): Promise<User> {
  const user = await deps.db.query(
    "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING *",
    [data.name, data.email]
  );
  deps.logger.info("Created user " + user.id);
  return user;
}

// Option A: use directly with explicit deps
// const user = await getUser(deps, "123");

// Option B: create a bound module (partial application)
function createUserService(deps: Deps) {
  return {
    getUser: (id: string) => getUser(deps, id),
    createUser: (data: CreateUserDTO) => createUser(deps, data),
  };
}

// const userService = createUserService({ db, cache, logger });
// const user = await userService.getUser("123");
```

What changed:

- Class with private fields -> `Deps` interface passed as first argument (dependency injection via parameters instead of constructor)
- `this.db`, `this.cache` -> `deps.db`, `deps.cache` (explicit dependency, no hidden state)
- Methods -> standalone exported functions, easier to test (just pass mock deps)
- Constructor -> `createUserService()` factory using partial application for convenience
- No `new` keyword, no `this` -- functions are stateless
- Each function is independently importable and testable without instantiating a class
- The `Deps` object acts like a "reader monad" -- a functional pattern for injecting environment/config''',
    ),
    (
        "code-translation/class-to-functional",
        r'''Refactor this Python class-based observer pattern to functional style:

class EventBus:
    def __init__(self):
        self._subscribers = {}

    def subscribe(self, event, callback):
        if event not in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(callback)

    def unsubscribe(self, event, callback):
        if event in self._subscribers:
            self._subscribers[event].remove(callback)

    def publish(self, event, data=None):
        for callback in self._subscribers.get(event, []):
            callback(data)

bus = EventBus()
bus.subscribe("user:login", lambda data: print(f"User logged in: {data}"))
bus.subscribe("user:login", lambda data: log_to_file(data))
bus.publish("user:login", {"user_id": 42})''',
        r'''```python
from typing import Callable, Any, Tuple

# Immutable subscriber state as a tuple of (event, callback) pairs
Subscribers = Tuple[Tuple[str, Callable], ...]

def create_bus() -> Subscribers:
    return ()

def subscribe(
    subs: Subscribers, event: str, callback: Callable
) -> Subscribers:
    # Return new tuple with added subscriber -- no mutation
    return subs + ((event, callback),)

def unsubscribe(
    subs: Subscribers, event: str, callback: Callable
) -> Subscribers:
    return tuple(
        (e, cb) for e, cb in subs if not (e == event and cb is callback)
    )

def publish(
    subs: Subscribers, event: str, data: Any = None
) -> None:
    for e, cb in subs:
        if e == event:
            cb(data)

def log_to_file(data):
    pass  # placeholder

# Usage -- thread the state through each call
bus = create_bus()
bus = subscribe(bus, "user:login", lambda d: print("Logged in: " + str(d)))
bus = subscribe(bus, "user:login", log_to_file)
publish(bus, "user:login", {"user_id": 42})

# Unsubscribe returns a new bus without that callback
bus = unsubscribe(bus, "user:login", log_to_file)
publish(bus, "user:login", {"user_id": 99})
```

What changed:

- `class EventBus` with mutable dict -> immutable tuple of `(event, callback)` pairs
- `self._subscribers[event].append(cb)` -> return `subs + ((event, cb),)` new tuple
- `.remove(callback)` mutation -> filter comprehension returning new tuple
- Object method calls `bus.subscribe(...)` -> function calls `subscribe(bus, ...)`
- State must be explicitly threaded: `bus = subscribe(bus, ...)`. This makes state changes visible -- you can see exactly when and how the subscriber list changes
- No `self`, no `__init__`, no mutable collections
- Trade-off: the tuple approach is O(n) for publish (scans all subscribers). The class version using a dict was O(k) where k = subscribers for that event. For production, use a frozen dict mapping events to tuples of callbacks''',
    ),
]
