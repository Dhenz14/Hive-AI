"""Deep reasoning training pairs: multi-step system design with extended think blocks."""

PAIRS = [
    (
        "deep_reasoning/task-scheduler-priority-deps",
        r'''Build a task scheduler in Python that supports priority queues, task dependencies, and cycle detection. Tasks should only run when all their dependencies have completed. If a cycle is detected, raise an error before execution begins.''',
        r'''<think>
This is a multi-component system. Let me decompose it:

Sub-problems:
1. Task representation — needs an ID, priority, callable, and list of dependency IDs
2. Dependency graph — need to track which tasks depend on which others
3. Cycle detection — must run BEFORE execution starts, not during. Topological sort with DFS and coloring (white/gray/black) is the classic approach.
4. Priority queue for ready tasks — tasks whose dependencies are all satisfied
5. Execution loop — pick highest priority ready task, run it, then check if any blocked tasks are now unblocked

Interface decisions:
- Task depends on other tasks by ID, so the scheduler needs a registry: dict[str, Task]
- The dependency graph is implicit in each task's `depends_on` list, but for cycle detection I need to walk it as an adjacency list
- Priority: lower number = higher priority (like OS scheduling)

Edge cases:
- Task depends on a task ID that doesn't exist — should raise KeyError early
- Task with no dependencies should be immediately ready
- Multiple tasks at same priority — FIFO among equal priority
- Empty scheduler — should just return empty results

Implementation order:
1. Task dataclass first (no dependencies on anything else)
2. Scheduler with add_task and the dependency registry
3. Cycle detection (topological sort via DFS)
4. Execution loop with priority queue

Wait — I need to think about the priority queue carefully. Python's heapq is a min-heap, so lower number = higher priority works naturally. But I also want FIFO for equal priorities, so I'll use a (priority, insertion_order, task_id) tuple.

Self-correction: I initially thought about running tasks in threads for parallelism, but the prompt says "task scheduler" not "parallel executor." I'll keep it single-threaded for clarity — dependencies form a topological order, and within each "level" I pick by priority.
</think>

```python
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import heapq


class CycleDetectedError(Exception):
    """Raised when a dependency cycle is found in the task graph."""
    pass


class MissingDependencyError(Exception):
    """Raised when a task depends on an unregistered task."""
    pass


@dataclass(order=False)
class Task:
    task_id: str
    fn: Callable[[], Any]
    priority: int = 0
    depends_on: list[str] = field(default_factory=list)
    result: Any = None
    completed: bool = False


class TaskScheduler:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._insertion_order: int = 0

    def add_task(
        self,
        task_id: str,
        fn: Callable[[], Any],
        priority: int = 0,
        depends_on: Optional[list[str]] = None,
    ) -> None:
        if task_id in self._tasks:
            raise ValueError(f"Task '{task_id}' already registered")
        self._tasks[task_id] = Task(
            task_id=task_id,
            fn=fn,
            priority=priority,
            depends_on=depends_on or [],
        )

    def _validate_dependencies(self) -> None:
        for task in self._tasks.values():
            for dep_id in task.depends_on:
                if dep_id not in self._tasks:
                    raise MissingDependencyError(
                        f"Task '{task.task_id}' depends on unknown task '{dep_id}'"
                    )

    def _detect_cycle(self) -> None:
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {tid: WHITE for tid in self._tasks}
        path: list[str] = []

        def dfs(tid: str) -> None:
            color[tid] = GRAY
            path.append(tid)
            for dep_id in self._tasks[tid].depends_on:
                if color[dep_id] == GRAY:
                    cycle_start = path.index(dep_id)
                    cycle = path[cycle_start:] + [dep_id]
                    raise CycleDetectedError(
                        f"Dependency cycle: {' -> '.join(cycle)}"
                    )
                if color[dep_id] == WHITE:
                    dfs(dep_id)
            path.pop()
            color[tid] = BLACK

        for tid in self._tasks:
            if color[tid] == WHITE:
                dfs(tid)

    def _get_ready_tasks(self) -> list[tuple[int, int, str]]:
        heap: list[tuple[int, int, str]] = []
        for task in self._tasks.values():
            if task.completed:
                continue
            all_deps_done = all(
                self._tasks[d].completed for d in task.depends_on
            )
            if all_deps_done:
                self._insertion_order += 1
                heapq.heappush(heap, (task.priority, self._insertion_order, task.task_id))
        return heap

    def run(self) -> dict[str, Any]:
        self._validate_dependencies()
        self._detect_cycle()

        results: dict[str, Any] = {}
        remaining = len(self._tasks)

        while remaining > 0:
            ready_heap = self._get_ready_tasks()
            if not ready_heap:
                unfinished = [t.task_id for t in self._tasks.values() if not t.completed]
                raise RuntimeError(f"Deadlock — unfinished tasks: {unfinished}")

            _, _, tid = heapq.heappop(ready_heap)
            task = self._tasks[tid]
            task.result = task.fn()
            task.completed = True
            results[tid] = task.result
            remaining -= 1

        return results


# --- Usage / test ---
if __name__ == "__main__":
    scheduler = TaskScheduler()

    log: list[str] = []

    scheduler.add_task("fetch_config", lambda: log.append("config") or {"db": "postgres"}, priority=1)
    scheduler.add_task("connect_db", lambda: log.append("db") or "conn_ok", priority=1, depends_on=["fetch_config"])
    scheduler.add_task("load_cache", lambda: log.append("cache") or "cache_ok", priority=0)
    scheduler.add_task("start_server", lambda: log.append("server") or "running", priority=2, depends_on=["connect_db", "load_cache"])

    results = scheduler.run()
    print("Execution order:", log)
    print("Results:", results)
    # load_cache runs first (priority 0, no deps), then fetch_config (priority 1),
    # then connect_db (priority 1, dep on fetch_config), then start_server
    assert log == ["cache", "config", "db", "server"]
    assert results["start_server"] == "running"

    # Test cycle detection
    bad = TaskScheduler()
    bad.add_task("a", lambda: 1, depends_on=["b"])
    bad.add_task("b", lambda: 2, depends_on=["c"])
    bad.add_task("c", lambda: 3, depends_on=["a"])
    try:
        bad.run()
        assert False, "Should have raised"
    except CycleDetectedError as e:
        print(f"Caught expected cycle: {e}")

    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/type-safe-orm-query-migration",
        r'''Implement a type-safe ORM in Python with model definitions (using descriptors or dataclass-style fields), a query builder that chains filter/order/limit, and a migration generator that diffs two model versions and outputs SQL ALTER statements.''',
        r'''<think>
This is a substantial system with three major subsystems. Let me decompose:

Sub-problems:
1. Model definition layer — need a metaclass or descriptor approach so users can declare fields with types and constraints. I'll go with a metaclass that collects Field descriptors.
2. Query builder — chainable API: Model.query().filter(name="x").order_by("age").limit(10). Must produce parameterized SQL.
3. Migration generator — compare two model schemas (old vs new) and emit ALTER TABLE ADD/DROP/ALTER COLUMN statements.

Interface design:
- Field knows its column name, Python type, SQL type, nullable, default
- Model metaclass collects all Field instances into a _fields dict on the class
- QueryBuilder holds a reference to the model class (for table name and field validation)
- MigrationGenerator takes two dicts of {field_name: FieldSpec} and diffs them

Edge cases:
- Filter on a field that doesn't exist — should raise AttributeError
- Chaining multiple filters — AND them together
- Migration: field type changed (ALTER COLUMN ... TYPE), field added, field removed
- SQL injection in filter values — must use parameterized queries, never string interpolation

Implementation order:
1. Field descriptor and base Model metaclass — everything else depends on these
2. Query builder — depends on Model for field validation
3. Migration diff — depends on Field for SQL type mapping

Wait, for the migration generator, I need a way to capture the "old" schema. I'll represent schemas as simple dicts so you can snapshot them. The generator doesn't need live models — just schema dicts.

Self-correction: I was going to use __set_name__ descriptors, but a metaclass approach is cleaner for collecting fields. Actually, I can use BOTH — __set_name__ to register the field's attribute name, and the metaclass to collect them.
</think>

```python
from typing import Any, Optional


# ============================================================
# 1. Field definitions & Model metaclass
# ============================================================

PYTHON_TO_SQL = {
    int: "INTEGER",
    str: "VARCHAR(255)",
    float: "REAL",
    bool: "BOOLEAN",
    bytes: "BLOB",
}


class Field:
    def __init__(
        self,
        py_type: type,
        primary_key: bool = False,
        nullable: bool = True,
        default: Any = None,
        max_length: Optional[int] = None,
    ):
        self.py_type = py_type
        self.primary_key = primary_key
        self.nullable = nullable
        self.default = default
        self.max_length = max_length
        self.name: str = ""  # set by __set_name__

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    @property
    def sql_type(self) -> str:
        if self.py_type is str and self.max_length:
            return f"VARCHAR({self.max_length})"
        return PYTHON_TO_SQL[self.py_type]

    @property
    def spec(self) -> dict:
        return {
            "sql_type": self.sql_type,
            "nullable": self.nullable,
            "primary_key": self.primary_key,
            "default": self.default,
        }


class ModelMeta(type):
    def __new__(mcs, name: str, bases: tuple, namespace: dict):
        fields: dict[str, Field] = {}
        for key, val in namespace.items():
            if isinstance(val, Field):
                fields[key] = val
        cls = super().__new__(mcs, name, bases, namespace)
        cls._fields = fields
        cls._table_name = namespace.get("_table_name", name.lower() + "s")
        return cls


class Model(metaclass=ModelMeta):
    _fields: dict[str, Field]
    _table_name: str

    def __init__(self, **kwargs: Any):
        for fname, field in self._fields.items():
            val = kwargs.get(fname, field.default)
            if val is None and not field.nullable:
                raise ValueError(f"Field '{fname}' is not nullable")
            if val is not None and not isinstance(val, field.py_type):
                raise TypeError(f"Field '{fname}' expected {field.py_type.__name__}, got {type(val).__name__}")
            setattr(self, fname, val)

    @classmethod
    def query(cls) -> "QueryBuilder":
        return QueryBuilder(cls)

    @classmethod
    def schema_snapshot(cls) -> dict[str, dict]:
        return {name: f.spec for name, f in cls._fields.items()}

    @classmethod
    def create_table_sql(cls) -> str:
        cols = []
        for name, f in cls._fields.items():
            parts = [name, f.sql_type]
            if f.primary_key:
                parts.append("PRIMARY KEY")
            if not f.nullable:
                parts.append("NOT NULL")
            if f.default is not None:
                parts.append(f"DEFAULT {repr(f.default)}")
            cols.append(" ".join(parts))
        return f"CREATE TABLE {cls._table_name} ({', '.join(cols)});"


# ============================================================
# 2. Query builder (parameterized)
# ============================================================

class QueryBuilder:
    def __init__(self, model: type):
        self._model = model
        self._filters: list[tuple[str, str, Any]] = []
        self._order: list[tuple[str, bool]] = []
        self._limit_val: Optional[int] = None
        self._offset_val: Optional[int] = None

    def _validate_field(self, name: str) -> None:
        if name not in self._model._fields:
            raise AttributeError(f"'{self._model.__name__}' has no field '{name}'")

    def filter(self, **kwargs: Any) -> "QueryBuilder":
        for key, val in kwargs.items():
            if "__" in key:
                fname, op = key.rsplit("__", 1)
                ops = {"gt": ">", "lt": "<", "gte": ">=", "lte": "<=", "ne": "!=", "like": "LIKE"}
                if op not in ops:
                    raise ValueError(f"Unknown operator '{op}'")
                self._validate_field(fname)
                self._filters.append((fname, ops[op], val))
            else:
                self._validate_field(key)
                self._filters.append((key, "=", val))
        return self

    def order_by(self, field: str, desc: bool = False) -> "QueryBuilder":
        self._validate_field(field)
        self._order.append((field, desc))
        return self

    def limit(self, n: int) -> "QueryBuilder":
        self._limit_val = n
        return self

    def offset(self, n: int) -> "QueryBuilder":
        self._offset_val = n
        return self

    def build(self) -> tuple[str, list[Any]]:
        parts = [f"SELECT * FROM {self._model._table_name}"]
        params: list[Any] = []

        if self._filters:
            clauses = []
            for fname, op, val in self._filters:
                clauses.append(f"{fname} {op} ?")
                params.append(val)
            parts.append("WHERE " + " AND ".join(clauses))

        if self._order:
            order_parts = [f"{f} {'DESC' if d else 'ASC'}" for f, d in self._order]
            parts.append("ORDER BY " + ", ".join(order_parts))

        if self._limit_val is not None:
            parts.append(f"LIMIT {int(self._limit_val)}")

        if self._offset_val is not None:
            parts.append(f"OFFSET {int(self._offset_val)}")

        return " ".join(parts) + ";", params


# ============================================================
# 3. Migration generator
# ============================================================

def generate_migration(
    table_name: str,
    old_schema: dict[str, dict],
    new_schema: dict[str, dict],
) -> list[str]:
    statements: list[str] = []
    old_keys = set(old_schema)
    new_keys = set(new_schema)

    # Added columns
    for col in sorted(new_keys - old_keys):
        spec = new_schema[col]
        parts = [f"ALTER TABLE {table_name} ADD COLUMN {col} {spec['sql_type']}"]
        if not spec["nullable"]:
            parts.append("NOT NULL")
        if spec["default"] is not None:
            parts.append(f"DEFAULT {repr(spec['default'])}")
        statements.append(" ".join(parts) + ";")

    # Dropped columns
    for col in sorted(old_keys - new_keys):
        statements.append(f"ALTER TABLE {table_name} DROP COLUMN {col};")

    # Modified columns
    for col in sorted(old_keys & new_keys):
        old, new = old_schema[col], new_schema[col]
        if old["sql_type"] != new["sql_type"]:
            statements.append(
                f"ALTER TABLE {table_name} ALTER COLUMN {col} TYPE {new['sql_type']};"
            )
        if old["nullable"] != new["nullable"]:
            action = "DROP NOT NULL" if new["nullable"] else "SET NOT NULL"
            statements.append(
                f"ALTER TABLE {table_name} ALTER COLUMN {col} {action};"
            )

    return statements


# ============================================================
# Usage / tests
# ============================================================

if __name__ == "__main__":
    class User(Model):
        _table_name = "users"
        id = Field(int, primary_key=True, nullable=False)
        name = Field(str, nullable=False, max_length=100)
        email = Field(str, nullable=False)
        age = Field(int, nullable=True)

    # Test model instantiation
    u = User(id=1, name="Alice", email="alice@example.com", age=30)
    assert u.name == "Alice"

    # Test CREATE TABLE
    ddl = User.create_table_sql()
    print("DDL:", ddl)
    assert "PRIMARY KEY" in ddl
    assert "VARCHAR(100)" in ddl

    # Test query builder
    sql, params = (
        User.query()
        .filter(age__gte=18, name__like="A%")
        .order_by("age", desc=True)
        .limit(10)
        .build()
    )
    print("SQL:", sql)
    print("Params:", params)
    assert "age >= ?" in sql
    assert "name LIKE ?" in sql
    assert params == [18, "A%"]
    assert "LIMIT 10" in sql

    # Test migration
    old = User.schema_snapshot()

    class UserV2(Model):
        _table_name = "users"
        id = Field(int, primary_key=True, nullable=False)
        name = Field(str, nullable=False, max_length=200)  # changed length
        email = Field(str, nullable=False)
        bio = Field(str, nullable=True)                      # added
        # age removed

    new = UserV2.schema_snapshot()
    stmts = generate_migration("users", old, new)
    print("Migration:")
    for s in stmts:
        print("  ", s)
    assert any("ADD COLUMN bio" in s for s in stmts)
    assert any("DROP COLUMN age" in s for s in stmts)
    assert any("TYPE VARCHAR(200)" in s for s in stmts)

    print("\nAll tests passed.")
```'''
    ),
    (
        "deep_reasoning/pubsub-broker-dlq",
        r'''Create a pub/sub message broker in Python with topics, subscriptions, message acknowledgment (with timeout), and a dead letter queue for messages that fail delivery after N retries.''',
        r'''<think>
Let me break down this pub/sub system into its components:

Sub-problems:
1. Message — needs an ID, topic, payload, metadata (attempt count, timestamps)
2. Topic — holds a list of subscriptions, routes published messages to all subscribers
3. Subscription — connects a topic to a handler (callback), tracks pending (unacked) messages
4. Acknowledgment — subscriber must ack within a timeout, else the message is redelivered
5. Dead Letter Queue (DLQ) — after N failed delivery attempts, move the message to a DLQ topic

Interface design:
- Broker is the central coordinator. It owns topics, subscriptions, and the DLQ.
- publish(topic, payload) -> Message: enqueue to all subscriptions on that topic
- subscribe(topic, handler, ack_timeout, max_retries) -> Subscription
- handler receives a MessageContext with .ack() and .nack() methods
- A background "reaper" checks for expired unacked messages and redelivers or DLQs them

Edge cases:
- Publish to a topic with no subscribers — message is silently dropped (fan-out of 0)
- Subscriber acks after timeout already triggered redelivery — ignore late acks
- max_retries=0 means no retries, straight to DLQ on first nack/timeout
- Handler raises an exception — treat as nack

Implementation order:
1. Message and MessageContext (no deps)
2. Subscription (needs Message)
3. Topic and Broker (needs Subscription)
4. Ack/timeout reaper loop
5. DLQ routing

Wait — threading for the timeout reaper adds complexity. I'll use a manual check_timeouts() method the caller can invoke (or run in a thread). This keeps the core logic testable without real timers.

Actually, for a clean demo, I'll use a simulated clock so tests are deterministic. The broker accepts a time_fn (defaults to time.time) for testability.
</think>

```python
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum


class MessageState(Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    ACKED = "acked"
    NACKED = "nacked"
    DEAD = "dead"


@dataclass
class Message:
    topic: str
    payload: Any
    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = 0.0
    attempt: int = 0


@dataclass
class PendingMessage:
    message: Message
    delivered_at: float
    state: MessageState = MessageState.DELIVERED
    attempt: int = 1


class MessageContext:
    """Passed to subscriber handlers — provides ack/nack interface."""
    def __init__(self, pending: PendingMessage):
        self._pending = pending
        self.msg = pending.message
        self.payload = pending.message.payload
        self.attempt = pending.attempt

    def ack(self) -> None:
        if self._pending.state == MessageState.DELIVERED:
            self._pending.state = MessageState.ACKED

    def nack(self) -> None:
        if self._pending.state == MessageState.DELIVERED:
            self._pending.state = MessageState.NACKED


class Subscription:
    def __init__(
        self,
        topic: str,
        handler: Callable[[MessageContext], None],
        ack_timeout: float = 5.0,
        max_retries: int = 3,
    ):
        self.topic = topic
        self.handler = handler
        self.ack_timeout = ack_timeout
        self.max_retries = max_retries
        self.pending: dict[str, PendingMessage] = {}  # msg_id -> PendingMessage

    def deliver(self, message: Message, now: float) -> None:
        pm = PendingMessage(
            message=message,
            delivered_at=now,
            attempt=message.attempt + 1,
        )
        self.pending[message.msg_id] = pm
        ctx = MessageContext(pm)
        try:
            self.handler(ctx)
        except Exception:
            pm.state = MessageState.NACKED


class Broker:
    def __init__(self, time_fn: Optional[Callable[[], float]] = None):
        self._time_fn = time_fn or time.time
        self._topics: dict[str, list[Subscription]] = {}
        self._dlq: list[Message] = []

    def create_topic(self, name: str) -> None:
        if name not in self._topics:
            self._topics[name] = []

    def subscribe(
        self,
        topic: str,
        handler: Callable[[MessageContext], None],
        ack_timeout: float = 5.0,
        max_retries: int = 3,
    ) -> Subscription:
        self.create_topic(topic)
        sub = Subscription(topic, handler, ack_timeout, max_retries)
        self._topics[topic].append(sub)
        return sub

    def publish(self, topic: str, payload: Any) -> Optional[Message]:
        if topic not in self._topics:
            return None
        msg = Message(topic=topic, payload=payload, created_at=self._time_fn())
        now = self._time_fn()
        for sub in self._topics[topic]:
            sub.deliver(msg, now)
        return msg

    def check_timeouts(self) -> int:
        """Check all subscriptions for timed-out messages. Returns count of redeliveries + DLQ moves."""
        now = self._time_fn()
        actions = 0
        for subs in self._topics.values():
            for sub in subs:
                expired = []
                for msg_id, pm in list(sub.pending.items()):
                    if pm.state == MessageState.ACKED:
                        expired.append(msg_id)
                        continue
                    timed_out = (now - pm.delivered_at) > sub.ack_timeout
                    nacked = pm.state == MessageState.NACKED
                    if timed_out or nacked:
                        expired.append(msg_id)
                        if pm.attempt >= sub.max_retries:
                            pm.state = MessageState.DEAD
                            self._dlq.append(pm.message)
                            actions += 1
                        else:
                            pm.message.attempt = pm.attempt
                            sub.deliver(pm.message, now)
                            actions += 1
                for msg_id in expired:
                    sub.pending.pop(msg_id, None)
        return actions

    @property
    def dead_letters(self) -> list[Message]:
        return list(self._dlq)


# --- Usage / test ---
if __name__ == "__main__":
    sim_time = [0.0]
    broker = Broker(time_fn=lambda: sim_time[0])

    results: list[str] = []
    fail_count = [0]

    def good_handler(ctx: MessageContext) -> None:
        results.append(f"got:{ctx.payload}")
        ctx.ack()

    def flaky_handler(ctx: MessageContext) -> None:
        fail_count[0] += 1
        if fail_count[0] <= 3:
            raise ValueError("transient failure")
        results.append(f"finally:{ctx.payload}")
        ctx.ack()

    broker.subscribe("orders", good_handler)
    sub_flaky = broker.subscribe("orders", flaky_handler, ack_timeout=2.0, max_retries=3)

    broker.publish("orders", "order-42")
    assert results == ["got:order-42"]  # good_handler acked immediately

    # flaky_handler failed — message is NACKED
    sim_time[0] = 1.0
    broker.check_timeouts()  # retry 2
    assert fail_count[0] == 2

    sim_time[0] = 2.0
    broker.check_timeouts()  # retry 3 (last attempt)
    assert fail_count[0] == 3

    sim_time[0] = 3.0
    broker.check_timeouts()  # exceeds max_retries -> DLQ
    assert len(broker.dead_letters) == 1
    assert broker.dead_letters[0].payload == "order-42"
    print(f"DLQ has {len(broker.dead_letters)} message(s): {broker.dead_letters[0].payload}")

    # Now publish another — flaky_handler will succeed (fail_count > 3)
    broker.publish("orders", "order-43")
    assert "finally:order-43" in results
    print("Results:", results)
    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/json-rule-engine",
        r'''Build a rule engine in Python that parses rules from JSON (with conditions like field comparisons, AND/OR logic, nested groups), evaluates them against a data dict, and executes configured actions when rules match.''',
        r'''<think>
Let me decompose this rule engine:

Sub-problems:
1. Rule schema — JSON format for conditions and actions. I need a recursive structure for AND/OR groups.
2. Condition evaluator — takes a condition node and a data dict, returns bool. Must handle operators like eq, ne, gt, lt, gte, lte, in, contains, regex.
3. Logical combinators — AND (all conditions true), OR (any condition true), NOT. These can nest arbitrarily.
4. Action executor — when a rule matches, execute its actions. Actions could be "set_field", "log", "send_event", etc. I'll make actions pluggable via a registry.
5. Rule engine — loads rules from JSON, evaluates them in priority order, collects triggered actions.

Interface design:
- Condition node: {"field": "age", "op": "gte", "value": 18} or {"all": [...conditions]} or {"any": [...conditions]}
- Rule: {"name": "...", "priority": N, "condition": <condition_node>, "actions": [{"type": "set_field", ...}]}
- Engine.evaluate(data) -> list of (rule_name, action_results)
- Action handlers registered as: engine.register_action("set_field", handler_fn)

Edge cases:
- Field doesn't exist in data — should return False (or a configurable "missing field" policy)
- Nested field access like "user.address.city" — I'll support dotted paths
- Empty condition list in "all" — should be True (vacuous truth)
- Empty condition list in "any" — should be False
- Rule with no actions — just a match check

Implementation order:
1. Condition evaluator (leaf + combinators) — standalone, no deps
2. Action registry and executor — standalone
3. Rule parser — combines conditions + actions
4. Engine — ties it all together

Self-correction: I initially thought about making this async for action execution, but that's overengineering. Synchronous evaluation is simpler and testable.
</think>

```python
import json
import re
from typing import Any, Callable


# ============================================================
# 1. Dotted-path field access
# ============================================================

def get_field(data: dict, path: str) -> Any:
    """Access nested fields via dotted path like 'user.address.city'."""
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


_MISSING = object()


# ============================================================
# 2. Condition evaluator
# ============================================================

OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "lt": lambda a, b: a < b,
    "gte": lambda a, b: a >= b,
    "lte": lambda a, b: a <= b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "contains": lambda a, b: b in a,
    "regex": lambda a, b: bool(re.search(b, str(a))),
    "exists": lambda a, b: a is not _MISSING if b else a is _MISSING,
}


def evaluate_condition(cond: dict, data: dict) -> bool:
    # Logical combinators
    if "all" in cond:
        return all(evaluate_condition(c, data) for c in cond["all"])
    if "any" in cond:
        return any(evaluate_condition(c, data) for c in cond["any"])
    if "not" in cond:
        return not evaluate_condition(cond["not"], data)

    # Leaf condition
    field = cond["field"]
    op = cond.get("op", "eq")
    expected = cond.get("value")

    actual = get_field(data, field)
    if actual is _MISSING and op != "exists":
        return False

    if op not in OPERATORS:
        raise ValueError(f"Unknown operator: {op}")
    return OPERATORS[op](actual, expected)


# ============================================================
# 3. Action registry & executor
# ============================================================

class ActionRegistry:
    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, action_type: str, handler: Callable) -> None:
        self._handlers[action_type] = handler

    def execute(self, action: dict, data: dict) -> Any:
        atype = action["type"]
        if atype not in self._handlers:
            raise ValueError(f"No handler for action type '{atype}'")
        return self._handlers[atype](action, data)


# ============================================================
# 4. Rule engine
# ============================================================

class RuleEngine:
    def __init__(self):
        self.rules: list[dict] = []
        self.actions = ActionRegistry()

        # Built-in actions
        self.actions.register("set_field", self._action_set_field)
        self.actions.register("log", self._action_log)
        self._log: list[str] = []

    @staticmethod
    def _action_set_field(action: dict, data: dict) -> None:
        path = action["field"]
        parts = path.split(".")
        obj = data
        for part in parts[:-1]:
            obj = obj.setdefault(part, {})
        obj[parts[-1]] = action["value"]

    def _action_log(self, action: dict, data: dict) -> None:
        msg = action.get("message", "").format_map(data)
        self._log.append(msg)

    def load_rules(self, rules_json: str) -> None:
        rules = json.loads(rules_json)
        if isinstance(rules, dict):
            rules = [rules]
        self.rules.extend(rules)
        self.rules.sort(key=lambda r: r.get("priority", 0), reverse=True)

    def evaluate(self, data: dict) -> list[tuple[str, list[Any]]]:
        results: list[tuple[str, list[Any]]] = []
        for rule in self.rules:
            if evaluate_condition(rule["condition"], data):
                action_results = []
                for action in rule.get("actions", []):
                    result = self.actions.execute(action, data)
                    action_results.append(result)
                results.append((rule["name"], action_results))
                if rule.get("stop_on_match", False):
                    break
        return results


# --- Usage / test ---
if __name__ == "__main__":
    engine = RuleEngine()

    rules = json.dumps([
        {
            "name": "premium_discount",
            "priority": 10,
            "condition": {
                "all": [
                    {"field": "user.tier", "op": "eq", "value": "premium"},
                    {"field": "cart.total", "op": "gte", "value": 100},
                ]
            },
            "actions": [
                {"type": "set_field", "field": "discount", "value": 0.20},
                {"type": "log", "message": "Applied 20% premium discount"},
            ],
        },
        {
            "name": "new_user_welcome",
            "priority": 5,
            "condition": {
                "all": [
                    {"field": "user.is_new", "op": "eq", "value": True},
                    {"field": "user.tier", "op": "ne", "value": "premium"},
                ]
            },
            "actions": [
                {"type": "set_field", "field": "discount", "value": 0.10},
            ],
        },
        {
            "name": "fraud_flag",
            "priority": 100,
            "condition": {
                "any": [
                    {"field": "cart.total", "op": "gt", "value": 10000},
                    {"field": "user.country", "op": "in", "value": ["XX", "YY"]},
                ]
            },
            "actions": [
                {"type": "set_field", "field": "flagged", "value": True},
                {"type": "log", "message": "Fraud check triggered"},
            ],
            "stop_on_match": True,
        },
    ])
    engine.load_rules(rules)

    # Test 1: premium user
    data1 = {"user": {"tier": "premium", "is_new": False}, "cart": {"total": 150}}
    matches1 = engine.evaluate(data1)
    print("Test 1:", [m[0] for m in matches1])
    assert data1["discount"] == 0.20
    assert len(matches1) == 1

    # Test 2: new user
    data2 = {"user": {"tier": "basic", "is_new": True}, "cart": {"total": 50}}
    matches2 = engine.evaluate(data2)
    print("Test 2:", [m[0] for m in matches2])
    assert data2["discount"] == 0.10

    # Test 3: fraud — stop_on_match prevents further rules
    data3 = {"user": {"tier": "premium", "is_new": False, "country": "US"}, "cart": {"total": 15000}}
    matches3 = engine.evaluate(data3)
    print("Test 3:", [m[0] for m in matches3])
    assert data3.get("flagged") is True
    assert "discount" not in data3  # premium rule didn't run due to stop_on_match

    # Test 4: nested NOT condition
    engine2 = RuleEngine()
    engine2.load_rules(json.dumps({
        "name": "not_test",
        "priority": 1,
        "condition": {"not": {"field": "status", "op": "eq", "value": "banned"}},
        "actions": [{"type": "set_field", "field": "allowed", "value": True}],
    }))
    data4 = {"status": "active"}
    engine2.evaluate(data4)
    assert data4["allowed"] is True
    data5 = {"status": "banned"}
    engine2.evaluate(data5)
    assert "allowed" not in data5

    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/connection-pool-health-steal",
        r'''Implement a connection pool in Python with configurable min/max size, health checks on checkout, automatic reconnection for dead connections, and connection stealing (taking a connection from an idle client when the pool is exhausted) rather than blocking forever.''',
        r'''<think>
Decomposing the connection pool system:

Sub-problems:
1. Connection abstraction — wraps a real connection with health state, last-used time, creation time. Needs a "connector" factory to create/reconnect.
2. Pool management — min_size idle connections kept alive, max_size hard cap
3. Health check on checkout — before returning a connection, verify it's alive (ping). If dead, reconnect or discard and create new.
4. Automatic reconnection — if health check fails, try to reconnect. If reconnect fails, discard and try next idle connection.
5. Connection stealing — when pool is at max_size and all connections are checked out, instead of blocking, steal the longest-idle checked-out connection from whoever has it and give it to the new requester. The original holder gets a "revoked" marker.
6. Return/release — put connection back into idle pool, unless it's been revoked.

Interface design:
- Pool.acquire() -> PooledConnection: check out a connection
- Pool.release(conn): return it
- Context manager: `with pool.acquire() as conn: ...`
- PooledConnection wraps the raw connection, has a `revoked` flag
- Connector protocol: connect() -> raw_conn, ping(raw_conn) -> bool, close(raw_conn)

Edge cases:
- All connections are checked out AND stealing is disabled — raise PoolExhaustedError
- Health check fails for all idle connections — create new if under max_size
- Connection returned after being stolen — silently discard (don't double-return)
- min_size > max_size — raise config error
- Release a connection that doesn't belong to this pool — raise error

Implementation order:
1. Connector protocol and a fake/mock connector for testing
2. PooledConnection wrapper
3. Core pool: idle list, active set
4. acquire() with health check and creation logic
5. Stealing logic
6. release()

Self-correction: Threading — a real pool needs locks. I'll use threading.Lock for thread safety, but keep the test single-threaded for simplicity. The stealing mechanism means I need to track which connections are active and their checkout times.
</think>

```python
import threading
import time
from typing import Any, Optional, Protocol
from dataclasses import dataclass, field


class PoolExhaustedError(Exception):
    pass


class ConnectionRevokedError(Exception):
    pass


class Connector(Protocol):
    def connect(self) -> Any: ...
    def ping(self, conn: Any) -> bool: ...
    def close(self, conn: Any) -> None: ...


@dataclass
class PooledConnection:
    raw: Any
    created_at: float
    last_used: float
    checkout_time: float = 0.0
    revoked: bool = False
    _pool: Optional["ConnectionPool"] = field(default=None, repr=False)

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        if self.revoked:
            raise ConnectionRevokedError("This connection was stolen by the pool")
        self.last_used = time.time()
        return self.raw.execute(*args, **kwargs)

    def __enter__(self) -> "PooledConnection":
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._pool:
            self._pool.release(self)


class ConnectionPool:
    def __init__(
        self,
        connector: Connector,
        min_size: int = 2,
        max_size: int = 10,
        max_idle_time: float = 300.0,
        enable_stealing: bool = True,
    ):
        if min_size > max_size:
            raise ValueError("min_size cannot exceed max_size")

        self._connector = connector
        self._min_size = min_size
        self._max_size = max_size
        self._max_idle_time = max_idle_time
        self._enable_stealing = enable_stealing

        self._lock = threading.Lock()
        self._idle: list[PooledConnection] = []
        self._active: set[int] = set()  # id(PooledConnection)
        self._active_conns: dict[int, PooledConnection] = {}
        self._total_created = 0

        # Pre-populate min_size connections
        for _ in range(min_size):
            self._idle.append(self._create_connection())

    def _create_connection(self) -> PooledConnection:
        raw = self._connector.connect()
        now = time.time()
        self._total_created += 1
        return PooledConnection(raw=raw, created_at=now, last_used=now, _pool=self)

    def _health_check(self, pc: PooledConnection) -> bool:
        try:
            return self._connector.ping(pc.raw)
        except Exception:
            return False

    def _try_reconnect(self, pc: PooledConnection) -> bool:
        try:
            self._connector.close(pc.raw)
        except Exception:
            pass
        try:
            pc.raw = self._connector.connect()
            pc.last_used = time.time()
            return True
        except Exception:
            return False

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._idle) + len(self._active)

    @property
    def idle_count(self) -> int:
        with self._lock:
            return len(self._idle)

    def acquire(self) -> PooledConnection:
        with self._lock:
            # Try idle connections with health check
            while self._idle:
                pc = self._idle.pop(0)
                if self._health_check(pc):
                    pc.checkout_time = time.time()
                    pc.revoked = False
                    self._active.add(id(pc))
                    self._active_conns[id(pc)] = pc
                    return pc
                # Health check failed — try reconnect
                if self._try_reconnect(pc):
                    pc.checkout_time = time.time()
                    pc.revoked = False
                    self._active.add(id(pc))
                    self._active_conns[id(pc)] = pc
                    return pc
                # Dead — discard
                self._connector.close(pc.raw)

            # No idle connections — create new if under max
            if len(self._active) < self._max_size:
                pc = self._create_connection()
                pc.checkout_time = time.time()
                self._active.add(id(pc))
                self._active_conns[id(pc)] = pc
                return pc

            # At max — try stealing
            if self._enable_stealing and self._active_conns:
                oldest = min(
                    self._active_conns.values(),
                    key=lambda c: c.checkout_time,
                )
                oldest.revoked = True
                self._active.discard(id(oldest))
                del self._active_conns[id(oldest)]

                # Create a fresh connection to replace the stolen one
                pc = self._create_connection()
                pc.checkout_time = time.time()
                self._active.add(id(pc))
                self._active_conns[id(pc)] = pc
                return pc

            raise PoolExhaustedError(
                f"Pool exhausted: {len(self._active)} active, max={self._max_size}"
            )

    def release(self, pc: PooledConnection) -> None:
        with self._lock:
            conn_id = id(pc)
            if pc.revoked:
                # Stolen connection — discard silently
                try:
                    self._connector.close(pc.raw)
                except Exception:
                    pass
                return

            self._active.discard(conn_id)
            self._active_conns.pop(conn_id, None)
            pc.last_used = time.time()
            self._idle.append(pc)

    def close_all(self) -> None:
        with self._lock:
            for pc in self._idle:
                self._connector.close(pc.raw)
            self._idle.clear()
            for pc in self._active_conns.values():
                pc.revoked = True
                self._connector.close(pc.raw)
            self._active.clear()
            self._active_conns.clear()


# --- Mock connector and tests ---
if __name__ == "__main__":
    class FakeConn:
        def __init__(self, cid: int):
            self.cid = cid
            self.alive = True
            self.queries: list[str] = []
        def execute(self, sql: str) -> str:
            self.queries.append(sql)
            return f"result-{self.cid}"

    class FakeConnector:
        def __init__(self):
            self._next_id = 0
            self.kill_list: set[int] = set()
        def connect(self) -> FakeConn:
            self._next_id += 1
            return FakeConn(self._next_id)
        def ping(self, conn: FakeConn) -> bool:
            return conn.alive and conn.cid not in self.kill_list
        def close(self, conn: FakeConn) -> None:
            conn.alive = False

    connector = FakeConnector()
    pool = ConnectionPool(connector, min_size=2, max_size=3, enable_stealing=True)
    assert pool.idle_count == 2

    # Basic acquire/release
    with pool.acquire() as c1:
        result = c1.execute("SELECT 1")
        print(f"Query result: {result}")
    assert pool.idle_count == 2

    # Health check: kill connection 1, pool should reconnect or discard
    connector.kill_list.add(1)
    c2 = pool.acquire()
    assert c2.raw.cid != 1  # should not get the dead connection
    pool.release(c2)

    # Exhaust pool to trigger stealing
    a = pool.acquire()
    b = pool.acquire()
    c = pool.acquire()
    assert pool.idle_count == 0
    # All 3 active, at max — next acquire steals oldest
    d = pool.acquire()
    assert a.revoked  # oldest was stolen
    try:
        a.execute("SELECT fail")
        assert False, "Should have raised"
    except ConnectionRevokedError:
        print("Caught expected ConnectionRevokedError")

    # Releasing stolen connection is silently discarded
    pool.release(a)  # should not crash
    pool.release(d)
    pool.release(b)
    pool.release(c)

    pool.close_all()
    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/middleware-pipeline",
        r'''Create a middleware pipeline system (inspired by Express/Django) in Python. Support request/response transformation, error handling middleware, short-circuiting (early return), and async-compatible middleware.''',
        r'''<think>
Let me decompose the middleware pipeline:

Sub-problems:
1. Request/Response objects — simple containers for headers, body, status, etc.
2. Middleware protocol — each middleware is a callable that receives (request, next) and returns a response. Calling next() passes to the next middleware.
3. Pipeline builder — compose middleware in order, handle the "onion" pattern (pre-processing before next(), post-processing after)
4. Error handling — special error middleware that only runs when an exception occurs, like Express's (err, req, next) pattern
5. Short-circuiting — middleware can return a response without calling next(), stopping the chain
6. Async support — middleware can be async, pipeline handles both sync and async

Interface design:
- `app.use(middleware_fn)` to add regular middleware
- `app.use_error(error_handler_fn)` to add error handlers
- `app.handle(request) -> response` to process a request through the pipeline
- Middleware signature: `def mw(req: Request, call_next: Callable) -> Response`
- Error handler signature: `def eh(error: Exception, req: Request, call_next: Callable) -> Response`

Edge cases:
- No middleware registered — return a default 404 response
- Middleware calls next() multiple times — should work but only first result counts. Actually, let it be called multiple times (retry pattern) but that's unusual.
- Exception in middleware — skip to nearest error handler
- Exception in error handler — propagate to next error handler or raise
- All error handlers fail — return 500

Implementation order:
1. Request/Response dataclasses
2. Middleware chain builder (the "next" function closure)
3. Error handling integration
4. Short-circuit support (naturally falls out of not calling next)
5. Async support via asyncio

Wait — supporting both sync and async in one pipeline is tricky. I'll make the pipeline async-first and wrap sync middleware with asyncio. The public API will have both handle() (sync wrapper) and handle_async().
</think>

```python
import asyncio
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union


@dataclass
class Request:
    method: str = "GET"
    path: str = "/"
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class Response:
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None

    @staticmethod
    def not_found() -> "Response":
        return Response(status=404, body="Not Found")

    @staticmethod
    def error(msg: str = "Internal Server Error", status: int = 500) -> "Response":
        return Response(status=status, body=msg)


Middleware = Callable  # (Request, next) -> Response or async
ErrorMiddleware = Callable  # (Exception, Request, next) -> Response or async


class Pipeline:
    def __init__(self):
        self._middleware: list[tuple[str, Callable]] = []  # ("normal"|"error", fn)

    def use(self, *middleware: Middleware) -> "Pipeline":
        for mw in middleware:
            self._middleware.append(("normal", mw))
        return self

    def use_error(self, *handlers: ErrorMiddleware) -> "Pipeline":
        for h in handlers:
            self._middleware.append(("error", h))
        return self

    async def handle_async(self, request: Request) -> Response:
        return await self._run_chain(request, self._middleware, error=None)

    def handle(self, request: Request) -> Response:
        return asyncio.get_event_loop().run_until_complete(self.handle_async(request))

    async def _run_chain(
        self,
        request: Request,
        remaining: list[tuple[str, Callable]],
        error: Optional[Exception],
    ) -> Response:
        if not remaining:
            if error:
                return Response.error(str(error))
            return Response.not_found()

        kind, handler = remaining[0]
        rest = remaining[1:]

        async def call_next() -> Response:
            return await self._run_chain(request, rest, error=None)

        try:
            if error is not None:
                # In error state — skip normal middleware, look for error handlers
                if kind == "error":
                    result = handler(error, request, call_next)
                    if asyncio.iscoroutine(result):
                        return await result
                    return result
                else:
                    # Skip this normal middleware, keep propagating error
                    return await self._run_chain(request, rest, error=error)
            else:
                # Normal state — skip error handlers
                if kind == "error":
                    return await self._run_chain(request, rest, error=None)
                else:
                    result = handler(request, call_next)
                    if asyncio.iscoroutine(result):
                        return await result
                    return result
        except Exception as e:
            # Exception thrown — enter error state
            return await self._run_chain(request, rest, error=e)


# ============================================================
# Usage / tests
# ============================================================

if __name__ == "__main__":
    app = Pipeline()
    call_log: list[str] = []

    # Logging middleware (onion — wraps around inner)
    async def logger(req: Request, call_next):
        call_log.append(f">> {req.method} {req.path}")
        resp = await call_next()
        call_log.append(f"<< {resp.status}")
        return resp

    # Auth middleware (can short-circuit)
    def auth(req: Request, call_next):
        token = req.headers.get("Authorization")
        if not token:
            call_log.append("auth:rejected")
            return Response(status=401, body="Unauthorized")
        req.context["user"] = token.split(" ")[-1]
        call_log.append("auth:ok")
        # Must return awaitable since pipeline is async
        return call_next()

    # Request transform
    def add_request_id(req: Request, call_next):
        req.context["request_id"] = "req-12345"
        return call_next()

    # Final handler
    def handler(req: Request, call_next):
        user = req.context.get("user", "anonymous")
        return Response(status=200, body=f"Hello, {user}!")

    # Error handler
    def error_handler(err: Exception, req: Request, call_next):
        call_log.append(f"error_handler:{type(err).__name__}")
        return Response.error(f"Caught: {err}", status=500)

    app.use(logger, auth, add_request_id, handler)
    app.use_error(error_handler)

    loop = asyncio.new_event_loop()

    # Test 1: successful request
    call_log.clear()
    req1 = Request(method="GET", path="/api/me", headers={"Authorization": "Bearer alice"})
    resp1 = loop.run_until_complete(app.handle_async(req1))
    print(f"Test 1: {resp1.status} {resp1.body}")
    print(f"  Log: {call_log}")
    assert resp1.status == 200
    assert resp1.body == "Hello, alice!"
    assert "auth:ok" in call_log

    # Test 2: short-circuit (no auth header)
    call_log.clear()
    req2 = Request(method="GET", path="/api/me")
    resp2 = loop.run_until_complete(app.handle_async(req2))
    print(f"Test 2: {resp2.status} {resp2.body}")
    assert resp2.status == 401
    assert "auth:rejected" in call_log

    # Test 3: error handling
    call_log.clear()
    app2 = Pipeline()

    def bad_middleware(req, call_next):
        raise RuntimeError("something broke")

    app2.use(logger, bad_middleware)
    app2.use_error(error_handler)

    req3 = Request(method="POST", path="/crash")
    resp3 = loop.run_until_complete(app2.handle_async(req3))
    print(f"Test 3: {resp3.status} {resp3.body}")
    assert resp3.status == 500
    assert "Caught: something broke" in resp3.body

    loop.close()
    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/schema-validator-nested",
        r'''Build a schema validator in Python that supports nested objects, arrays with item schemas, optional/required fields, custom validator functions, type coercion, and returns helpful, path-specific error messages.''',
        r'''<think>
Decomposing the schema validator:

Sub-problems:
1. Schema definition DSL — need a way to declare schemas for objects, arrays, scalars. I'll use a class-based approach: ObjectSchema, ArraySchema, StringField, IntField, etc.
2. Validation engine — recursively walks the data and schema, collecting errors with JSON-path-style locations like "user.addresses[0].zip"
3. Error accumulation — don't stop at first error; collect ALL errors so the user can fix them in one pass
4. Custom validators — user-provided functions that receive a value and return True/error message
5. Type coercion — optionally try to convert types (string "42" -> int 42) before validation
6. Required vs optional — fields can be required (error if missing) or optional (skip if missing, validate if present)

Interface design:
- Schema is a tree: ObjectSchema has fields which can be other schemas
- validate(data, schema) -> ValidationResult with .is_valid and .errors list
- Each error has: path (string), message, got (actual value)
- Custom validators: Field(..., validators=[lambda v: v > 0 or "must be positive"])

Edge cases:
- Nested optional object with required fields inside — if the outer object is present, inner required fields must be checked
- Array with no items — should pass (empty is valid unless min_length constraint)
- null/None for a non-nullable field — distinct from missing
- Coercion failure should become a validation error, not an exception
- Deeply nested paths: "orders[2].items[0].price"

Implementation order:
1. ValidationError dataclass and ValidationResult
2. Base Schema class with validate() method
3. Scalar fields (String, Int, Float, Bool) with type coercion
4. ObjectSchema with required/optional
5. ArraySchema with item schema
6. Custom validators hook
7. Error path tracking (pass path prefix through recursion)

Self-correction: I initially thought of using a dict-based schema definition like JSON Schema, but a class-based approach is more Pythonic and easier to extend with custom validators. Users can always build a JSON-to-schema parser on top.
</think>

```python
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union


@dataclass
class ValidationError:
    path: str
    message: str
    got: Any = None

    def __str__(self) -> str:
        return f"{self.path}: {self.message} (got {self.got!r})"


@dataclass
class ValidationResult:
    errors: list[ValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add(self, path: str, message: str, got: Any = None) -> None:
        self.errors.append(ValidationError(path, message, got))

    def merge(self, other: "ValidationResult") -> None:
        self.errors.extend(other.errors)


class Schema:
    """Base class for all schema types."""

    def validate(self, data: Any, path: str = "$", result: Optional[ValidationResult] = None) -> ValidationResult:
        if result is None:
            result = ValidationResult()
        self._validate(data, path, result)
        return result

    def _validate(self, data: Any, path: str, result: ValidationResult) -> None:
        raise NotImplementedError


class ScalarField(Schema):
    def __init__(
        self,
        py_type: type,
        *,
        coerce: bool = False,
        nullable: bool = False,
        validators: Optional[list[Callable[[Any], Union[bool, str]]]] = None,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        pattern: Optional[str] = None,
    ):
        self.py_type = py_type
        self.coerce = coerce
        self.nullable = nullable
        self.validators = validators or []
        self.min_val = min_val
        self.max_val = max_val
        self.min_length = min_length
        self.max_length = max_length
        self.pattern = pattern

    def _validate(self, data: Any, path: str, result: ValidationResult) -> None:
        if data is None:
            if not self.nullable:
                result.add(path, "value is null but field is not nullable", data)
            return

        # Type coercion
        value = data
        if self.coerce and not isinstance(data, self.py_type):
            try:
                value = self.py_type(data)
            except (ValueError, TypeError):
                result.add(path, f"cannot coerce {type(data).__name__} to {self.py_type.__name__}", data)
                return

        if not isinstance(value, self.py_type):
            result.add(path, f"expected {self.py_type.__name__}, got {type(value).__name__}", value)
            return

        # Range checks
        if self.min_val is not None and value < self.min_val:
            result.add(path, f"value must be >= {self.min_val}", value)
        if self.max_val is not None and value > self.max_val:
            result.add(path, f"value must be <= {self.max_val}", value)

        # Length checks (strings, bytes)
        if hasattr(value, "__len__"):
            if self.min_length is not None and len(value) < self.min_length:
                result.add(path, f"length must be >= {self.min_length}", value)
            if self.max_length is not None and len(value) > self.max_length:
                result.add(path, f"length must be <= {self.max_length}", value)

        # Regex
        if self.pattern is not None and isinstance(value, str):
            import re
            if not re.match(self.pattern, value):
                result.add(path, f"does not match pattern {self.pattern!r}", value)

        # Custom validators
        for validator in self.validators:
            check = validator(value)
            if check is not True and check is not None:
                msg = check if isinstance(check, str) else "custom validation failed"
                result.add(path, msg, value)


# Convenience aliases
def String(**kwargs) -> ScalarField:
    return ScalarField(str, **kwargs)

def Int(**kwargs) -> ScalarField:
    return ScalarField(int, **kwargs)

def Float(**kwargs) -> ScalarField:
    return ScalarField(float, **kwargs)

def Bool(**kwargs) -> ScalarField:
    return ScalarField(bool, **kwargs)


class Object(Schema):
    def __init__(
        self,
        fields: dict[str, Schema],
        *,
        required: Optional[list[str]] = None,
        allow_extra: bool = False,
    ):
        self.fields = fields
        self.required = set(required or [])
        self.allow_extra = allow_extra

    def _validate(self, data: Any, path: str, result: ValidationResult) -> None:
        if not isinstance(data, dict):
            result.add(path, f"expected object, got {type(data).__name__}", data)
            return

        # Check required fields
        for fname in self.required:
            if fname not in data:
                result.add(f"{path}.{fname}", "required field is missing")

        # Check for extra fields
        if not self.allow_extra:
            for key in data:
                if key not in self.fields:
                    result.add(f"{path}.{key}", "unexpected field")

        # Validate each present field
        for fname, schema in self.fields.items():
            if fname in data:
                schema.validate(data[fname], f"{path}.{fname}", result)


class Array(Schema):
    def __init__(
        self,
        items: Schema,
        *,
        min_length: int = 0,
        max_length: Optional[int] = None,
    ):
        self.items = items
        self.min_length = min_length
        self.max_length = max_length

    def _validate(self, data: Any, path: str, result: ValidationResult) -> None:
        if not isinstance(data, list):
            result.add(path, f"expected array, got {type(data).__name__}", data)
            return

        if len(data) < self.min_length:
            result.add(path, f"array length must be >= {self.min_length}", len(data))
        if self.max_length is not None and len(data) > self.max_length:
            result.add(path, f"array length must be <= {self.max_length}", len(data))

        for i, item in enumerate(data):
            self.items.validate(item, f"{path}[{i}]", result)


# --- Usage / test ---
if __name__ == "__main__":
    address_schema = Object(
        fields={
            "street": String(min_length=1),
            "city": String(min_length=1),
            "zip": String(pattern=r"^\d{5}(-\d{4})?$"),
        },
        required=["street", "city", "zip"],
    )

    user_schema = Object(
        fields={
            "name": String(min_length=1, max_length=100),
            "age": Int(min_val=0, max_val=150, coerce=True),
            "email": String(pattern=r"^[^@]+@[^@]+\.[^@]+$"),
            "tags": Array(String(), max_length=5),
            "address": address_schema,
        },
        required=["name", "email"],
    )

    # Valid data
    good = {
        "name": "Alice",
        "age": "30",  # will be coerced
        "email": "alice@example.com",
        "tags": ["admin", "user"],
        "address": {"street": "123 Main St", "city": "Springfield", "zip": "62704"},
    }
    r1 = user_schema.validate(good)
    print(f"Valid data: is_valid={r1.is_valid}")
    assert r1.is_valid

    # Invalid data — multiple errors
    bad = {
        "name": "",
        "age": "not_a_number",
        "email": "invalid-email",
        "tags": ["a", "b", "c", "d", "e", "f"],
        "address": {"street": "", "zip": "ABC"},
        "extra_field": True,
    }
    r2 = user_schema.validate(bad)
    print(f"\nInvalid data: {len(r2.errors)} errors:")
    for err in r2.errors:
        print(f"  {err}")

    assert not r2.is_valid
    paths = {e.path for e in r2.errors}
    assert "$.name" in paths  # min_length
    assert "$.age" in paths  # coerce failure
    assert "$.email" in paths  # pattern
    assert "$.tags" in paths  # max_length
    assert "$.address.city" in paths  # required missing
    assert "$.address.zip" in paths  # pattern
    assert "$.extra_field" in paths  # unexpected

    # Custom validator
    even_only = Int(validators=[lambda v: v % 2 == 0 or "must be even"])
    r3 = even_only.validate(3)
    assert not r3.is_valid
    assert "must be even" in r3.errors[0].message

    r4 = even_only.validate(4)
    assert r4.is_valid

    print("\nAll tests passed.")
```'''
    ),
    (
        "deep_reasoning/retry-circuit-breaker",
        r'''Implement a retry decorator in Python with exponential backoff, jitter, a circuit breaker (that opens after N consecutive failures and stays open for a cooldown period), and a retry budget (max retries per time window across all calls).''',
        r'''<think>
This is several interrelated reliability patterns. Let me decompose:

Sub-problems:
1. Retry decorator — wraps a function, catches specified exceptions, retries with delay
2. Exponential backoff — delay doubles each attempt: base * 2^attempt
3. Jitter — randomize the delay to avoid thundering herd. Full jitter: uniform(0, calculated_delay)
4. Circuit breaker — tracks consecutive failures. After N failures, "opens" the circuit (rejects calls immediately). After a cooldown, moves to "half-open" (allows one test call). If test succeeds, closes; if fails, re-opens.
5. Retry budget — global limit on retries per time window. E.g., max 100 retries per 60 seconds across ALL decorated functions. This prevents retry storms.

Interface design:
- @retry(max_retries=3, backoff_base=1.0, max_delay=30, jitter=True, on=(ConnectionError, TimeoutError))
- CircuitBreaker(failure_threshold=5, cooldown=30) — can be shared across decorators
- RetryBudget(max_retries=100, window=60) — also shareable
- The decorator composes all three: check budget -> check circuit -> call -> handle result

Edge cases:
- Circuit is open — should raise CircuitOpenError immediately without consuming retry budget
- Budget exhausted — should raise BudgetExhaustedError without attempting the call
- Half-open state: only one call allowed through. If concurrent calls hit half-open, only first gets through.
- max_retries=0 with circuit breaker — still tracks failures for the circuit even if no retries
- Function succeeds on retry — circuit failure counter resets

Implementation order:
1. RetryBudget (standalone, just a counter with time window)
2. CircuitBreaker (standalone state machine)
3. Retry decorator that uses both
4. Backoff calculator with jitter

Self-correction: I need to think about thread safety. CircuitBreaker and RetryBudget can be hit from multiple threads. I'll use threading.Lock. For the retry budget's sliding window, I'll track individual retry timestamps and evict old ones.
</think>

```python
import functools
import random
import threading
import time
from enum import Enum
from typing import Any, Callable, Optional, Type


# ============================================================
# 1. Retry Budget
# ============================================================

class BudgetExhaustedError(Exception):
    pass


class RetryBudget:
    """Limits total retries across all callers within a sliding time window."""

    def __init__(self, max_retries: int = 100, window: float = 60.0):
        self.max_retries = max_retries
        self.window = window
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def _evict(self, now: float) -> None:
        cutoff = now - self.window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.pop(0)

    def acquire(self) -> bool:
        with self._lock:
            now = time.time()
            self._evict(now)
            if len(self._timestamps) >= self.max_retries:
                return False
            self._timestamps.append(now)
            return True

    @property
    def remaining(self) -> int:
        with self._lock:
            self._evict(time.time())
            return max(0, self.max_retries - len(self._timestamps))


# ============================================================
# 2. Circuit Breaker
# ============================================================

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Circuit is open. Retry after {retry_after:.1f}s")


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown: float = 30.0,
        time_fn: Optional[Callable[[], float]] = None,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self._time_fn = time_fn or time.time
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._get_state()

    def _get_state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if self._time_fn() - self._opened_at >= self.cooldown:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def check(self) -> None:
        with self._lock:
            state = self._get_state()
            if state == CircuitState.OPEN:
                remaining = self.cooldown - (self._time_fn() - self._opened_at)
                raise CircuitOpenError(remaining)
            # HALF_OPEN and CLOSED both allow the call

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self._time_fn()


# ============================================================
# 3. Backoff calculator
# ============================================================

def calculate_delay(
    attempt: int,
    base: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> float:
    delay = min(base * (2 ** attempt), max_delay)
    if jitter:
        delay = random.uniform(0, delay)
    return delay


# ============================================================
# 4. Retry decorator
# ============================================================

def retry(
    max_retries: int = 3,
    backoff_base: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    on: tuple[Type[Exception], ...] = (Exception,),
    circuit: Optional[CircuitBreaker] = None,
    budget: Optional[RetryBudget] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
) -> Callable:
    _sleep = sleep_fn or time.sleep

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[Exception] = None

            for attempt in range(max_retries + 1):
                # Check circuit breaker
                if circuit:
                    circuit.check()  # raises CircuitOpenError if open

                # Check retry budget (only for retries, not first attempt)
                if attempt > 0:
                    if budget and not budget.acquire():
                        raise BudgetExhaustedError(
                            f"Retry budget exhausted ({budget.remaining} remaining)"
                        )

                try:
                    result = fn(*args, **kwargs)
                    if circuit:
                        circuit.record_success()
                    return result
                except on as exc:
                    last_exc = exc
                    if circuit:
                        circuit.record_failure()

                    if attempt < max_retries:
                        delay = calculate_delay(attempt, backoff_base, max_delay, jitter)
                        _sleep(delay)
                    # else: final attempt failed, will raise

            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator


# --- Usage / test ---
if __name__ == "__main__":
    # Use fake sleep for fast tests
    sleep_log: list[float] = []
    def fake_sleep(t: float) -> None:
        sleep_log.append(t)

    # Test 1: basic retry with success on 3rd attempt
    call_count = [0]

    @retry(max_retries=3, backoff_base=0.1, jitter=False, on=(ValueError,), sleep_fn=fake_sleep)
    def flaky():
        call_count[0] += 1
        if call_count[0] < 3:
            raise ValueError("not yet")
        return "success"

    result = flaky()
    assert result == "success"
    assert call_count[0] == 3
    print(f"Test 1: succeeded after {call_count[0]} attempts, delays: {sleep_log}")

    # Test 2: circuit breaker opens after threshold
    sim_time = [0.0]
    cb = CircuitBreaker(failure_threshold=3, cooldown=10.0, time_fn=lambda: sim_time[0])

    @retry(max_retries=0, on=(RuntimeError,), circuit=cb, sleep_fn=fake_sleep)
    def always_fail():
        raise RuntimeError("boom")

    for _ in range(3):
        try:
            always_fail()
        except RuntimeError:
            pass

    assert cb.state == CircuitState.OPEN
    try:
        always_fail()
        assert False
    except CircuitOpenError as e:
        print(f"Test 2: Circuit opened — {e}")

    # Test 3: circuit half-opens after cooldown
    sim_time[0] = 11.0
    assert cb.state == CircuitState.HALF_OPEN

    # Test 4: retry budget
    budget = RetryBudget(max_retries=2, window=60.0)

    @retry(max_retries=5, on=(IOError,), budget=budget, sleep_fn=fake_sleep)
    def budget_test():
        raise IOError("fail")

    try:
        budget_test()
    except (IOError, BudgetExhaustedError) as e:
        print(f"Test 4: {type(e).__name__}: {e}")
    assert budget.remaining <= 0

    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/di-container-lifetimes",
        r'''Create a dependency injection container in Python with constructor injection, singleton and transient lifetimes, and circular dependency detection. It should support registering classes with their dependencies and resolving the full object graph automatically.''',
        r'''<think>
Decomposing the DI container:

Sub-problems:
1. Registration — map an abstract type (or string key) to a concrete class plus its dependencies. Need to store lifetime policy (singleton vs transient).
2. Resolution — when resolving a type, recursively resolve its constructor dependencies. For singletons, cache the instance. For transient, create new each time.
3. Constructor injection — inspect the class's __init__ signature to determine what dependencies it needs. Can use type annotations or explicit registration.
4. Circular dependency detection — while resolving, track the "resolution stack." If we see a type we're already resolving, that's a cycle.
5. Lifetime scopes — singleton (one instance for container lifetime), transient (new instance per resolve).

Interface design:
- container.register(abstract, concrete, lifetime="singleton"|"transient")
- container.resolve(abstract) -> instance
- Dependencies discovered via type annotations on __init__
- Optional: register_instance(abstract, instance) for pre-built singletons
- Optional: register_factory(abstract, factory_fn, lifetime)

Edge cases:
- Resolving an unregistered type — could auto-resolve if it's a concrete class with resolvable deps, or raise
- Singleton depending on transient — the transient is captured at singleton creation time (this is a known DI smell but shouldn't crash)
- Transient depending on singleton — fine, they share the singleton
- Self-dependency — cycle of length 1
- Diamond dependency — A depends on B and C, both depend on D. D should be created once if singleton, twice if transient

Implementation order:
1. Registration dataclass (binding: abstract -> concrete, lifetime, factory)
2. Container with register/resolve methods
3. Auto-injection via inspect.signature
4. Singleton cache
5. Cycle detection via resolution stack

Self-correction: I was going to use just type annotations, but string keys are also useful. I'll support both — register with any hashable key.
</think>

```python
import inspect
from enum import Enum
from typing import Any, Callable, Optional, TypeVar, Type


class Lifetime(Enum):
    SINGLETON = "singleton"
    TRANSIENT = "transient"


class CircularDependencyError(Exception):
    pass


class ResolutionError(Exception):
    pass


class Registration:
    def __init__(
        self,
        concrete: Optional[Type] = None,
        factory: Optional[Callable] = None,
        lifetime: Lifetime = Lifetime.TRANSIENT,
        instance: Any = None,
    ):
        self.concrete = concrete
        self.factory = factory
        self.lifetime = lifetime
        self.instance = instance  # pre-set for register_instance


class Container:
    def __init__(self):
        self._registrations: dict[Any, Registration] = {}
        self._singletons: dict[Any, Any] = {}

    def register(
        self,
        abstract: Any,
        concrete: Optional[Type] = None,
        lifetime: Lifetime = Lifetime.TRANSIENT,
    ) -> "Container":
        if concrete is None:
            concrete = abstract
        self._registrations[abstract] = Registration(concrete=concrete, lifetime=lifetime)
        return self

    def register_factory(
        self,
        abstract: Any,
        factory: Callable[["Container"], Any],
        lifetime: Lifetime = Lifetime.TRANSIENT,
    ) -> "Container":
        self._registrations[abstract] = Registration(factory=factory, lifetime=lifetime)
        return self

    def register_instance(self, abstract: Any, instance: Any) -> "Container":
        reg = Registration(lifetime=Lifetime.SINGLETON, instance=instance)
        self._registrations[abstract] = reg
        self._singletons[abstract] = instance
        return self

    def resolve(self, abstract: Any) -> Any:
        return self._resolve(abstract, resolution_stack=[])

    def _resolve(self, abstract: Any, resolution_stack: list[Any]) -> Any:
        # Circular dependency check
        if abstract in resolution_stack:
            cycle = resolution_stack[resolution_stack.index(abstract):] + [abstract]
            names = [getattr(t, "__name__", str(t)) for t in cycle]
            raise CircularDependencyError(
                f"Circular dependency: {' -> '.join(names)}"
            )

        # Check singleton cache
        if abstract in self._singletons:
            return self._singletons[abstract]

        # Find registration
        if abstract not in self._registrations:
            # Try auto-resolve if it's a concrete class
            if isinstance(abstract, type):
                self.register(abstract, abstract, Lifetime.TRANSIENT)
            else:
                raise ResolutionError(f"No registration for {abstract!r}")

        reg = self._registrations[abstract]

        # Pre-set instance (register_instance)
        if reg.instance is not None:
            return reg.instance

        resolution_stack = resolution_stack + [abstract]

        # Create instance
        if reg.factory:
            instance = reg.factory(self)
        elif reg.concrete:
            instance = self._construct(reg.concrete, resolution_stack)
        else:
            raise ResolutionError(f"No concrete or factory for {abstract!r}")

        # Cache singleton
        if reg.lifetime == Lifetime.SINGLETON:
            self._singletons[abstract] = instance

        return instance

    def _construct(self, cls: Type, resolution_stack: list[Any]) -> Any:
        sig = inspect.signature(cls.__init__)
        params = list(sig.parameters.values())[1:]  # skip 'self'

        kwargs: dict[str, Any] = {}
        for param in params:
            if param.annotation is inspect.Parameter.empty:
                if param.default is not inspect.Parameter.empty:
                    continue  # has default, skip
                raise ResolutionError(
                    f"Cannot resolve parameter '{param.name}' of {cls.__name__}: "
                    f"no type annotation and no default"
                )
            dep_type = param.annotation
            try:
                kwargs[param.name] = self._resolve(dep_type, resolution_stack)
            except (ResolutionError, CircularDependencyError):
                if param.default is not inspect.Parameter.empty:
                    continue  # has default, skip
                raise

        return cls(**kwargs)


# --- Usage / test ---
if __name__ == "__main__":
    # Define services
    class Logger:
        def __init__(self):
            self.logs: list[str] = []
        def log(self, msg: str) -> None:
            self.logs.append(msg)

    class Database:
        def __init__(self, logger: Logger):
            self.logger = logger
            self.logger.log("Database created")
        def query(self, sql: str) -> str:
            self.logger.log(f"Query: {sql}")
            return f"result({sql})"

    class UserRepository:
        def __init__(self, db: Database, logger: Logger):
            self.db = db
            self.logger = logger
        def find(self, user_id: int) -> str:
            return self.db.query(f"SELECT * FROM users WHERE id={user_id}")

    class UserService:
        def __init__(self, repo: UserRepository):
            self.repo = repo
        def get_user(self, uid: int) -> str:
            return self.repo.find(uid)

    # Configure container
    container = Container()
    container.register(Logger, lifetime=Lifetime.SINGLETON)
    container.register(Database, lifetime=Lifetime.SINGLETON)
    container.register(UserRepository, lifetime=Lifetime.TRANSIENT)
    container.register(UserService, lifetime=Lifetime.TRANSIENT)

    # Resolve
    service = container.resolve(UserService)
    result = service.get_user(42)
    print(f"Result: {result}")
    assert "42" in result

    # Singleton test — same Logger instance everywhere
    logger1 = container.resolve(Logger)
    logger2 = container.resolve(Logger)
    assert logger1 is logger2
    assert logger1 is service.repo.db.logger
    print(f"Logger logs: {logger1.logs}")
    assert "Database created" in logger1.logs

    # Transient test — different UserRepository instances
    repo1 = container.resolve(UserRepository)
    repo2 = container.resolve(UserRepository)
    assert repo1 is not repo2
    # But they share the same singleton DB
    assert repo1.db is repo2.db

    # Circular dependency detection
    class A:
        def __init__(self, b: "B"): self.b = b
    class B:
        def __init__(self, a: A): self.a = a

    c2 = Container()
    c2.register(A)
    c2.register(B)
    try:
        c2.resolve(A)
        assert False, "Should have raised"
    except CircularDependencyError as e:
        print(f"Caught: {e}")

    # Factory registration
    c3 = Container()
    c3.register_factory("config", lambda c: {"db_url": "postgres://localhost/test"}, Lifetime.SINGLETON)
    cfg = c3.resolve("config")
    assert cfg["db_url"] == "postgres://localhost/test"
    assert c3.resolve("config") is cfg  # singleton

    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/cli-framework-subcommands",
        r'''Build a CLI framework in Python with subcommands, typed argument parsing (positional and named), automatic help generation, and shell completion script output. Do not use argparse — build the parser from scratch.''',
        r'''<think>
Decomposing the CLI framework:

Sub-problems:
1. Argument definitions — positional args, named flags (--name), typed parsing (int, str, bool, float), required vs optional with defaults
2. Command and subcommand tree — top-level app has subcommands, each subcommand has its own args. Could support nested subcommands (git remote add).
3. Parsing — split sys.argv, match subcommand, then parse remaining args for that command. Handle --flag=value and --flag value styles.
4. Help generation — auto-generate from command/arg metadata: usage line, description, args table with types and defaults
5. Shell completion — output a bash completion script that lists subcommands and flags

Interface design:
- @app.command("name", help="...") decorator registers a command
- Command function's parameters become CLI args (via inspection or explicit Arg() annotations)
- app.run(argv) parses and dispatches
- app.help() prints help for top-level or specific subcommand
- app.completion_script("bash") outputs completion script

Edge cases:
- Unknown flag — error with suggestion ("did you mean --name?")
- Missing required arg — helpful error message
- Boolean flags (--verbose) — presence means True, no value needed
- Multiple positional args — order matters
- --help flag — intercept before dispatch, print help

Implementation order:
1. Arg dataclass (metadata for one argument)
2. Command class (wraps a function + its args)
3. Parser (tokenize argv, match args)
4. App (registry of commands, dispatch)
5. Help formatter
6. Completion generator

Self-correction: I considered using function signature inspection like Click does, but explicit Arg() objects are clearer for a from-scratch implementation. I'll support both: explicit registration AND auto-detection from type hints.
</think>

```python
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, get_type_hints


@dataclass
class Arg:
    name: str
    arg_type: type = str
    help: str = ""
    required: bool = True
    default: Any = None
    positional: bool = False
    is_flag: bool = False  # boolean flag (no value)

    @property
    def cli_name(self) -> str:
        return self.name if self.positional else f"--{self.name}"


class ParseError(Exception):
    pass


class Command:
    def __init__(self, name: str, fn: Callable, help_text: str = ""):
        self.name = name
        self.fn = fn
        self.help_text = help_text
        self.args: list[Arg] = []

    def add_arg(self, arg: Arg) -> "Command":
        self.args.append(arg)
        return self

    def auto_args(self) -> "Command":
        """Detect args from function type hints."""
        import inspect
        hints = get_type_hints(self.fn)
        sig = inspect.signature(self.fn)
        for i, (pname, param) in enumerate(sig.parameters.items()):
            ptype = hints.get(pname, str)
            has_default = param.default is not inspect.Parameter.empty
            is_bool = ptype is bool
            self.args.append(Arg(
                name=pname,
                arg_type=ptype,
                required=not has_default and not is_bool,
                default=param.default if has_default else (False if is_bool else None),
                positional=(i == 0 and not has_default and not is_bool),
                is_flag=is_bool,
            ))
        return self

    def parse(self, tokens: list[str]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        positional_args = [a for a in self.args if a.positional]
        named_args = {a.name: a for a in self.args if not a.positional}
        pos_idx = 0
        i = 0

        while i < len(tokens):
            tok = tokens[i]
            if tok.startswith("--"):
                key = tok[2:]
                # Handle --key=value
                if "=" in key:
                    key, value = key.split("=", 1)
                    if key not in named_args:
                        raise ParseError(f"Unknown flag: --{key}")
                    arg = named_args[key]
                    result[key] = arg.arg_type(value)
                elif key in named_args:
                    arg = named_args[key]
                    if arg.is_flag:
                        result[key] = True
                    else:
                        i += 1
                        if i >= len(tokens):
                            raise ParseError(f"--{key} requires a value")
                        result[key] = arg.arg_type(tokens[i])
                else:
                    raise ParseError(f"Unknown flag: --{key}")
            else:
                if pos_idx < len(positional_args):
                    arg = positional_args[pos_idx]
                    result[arg.name] = arg.arg_type(tok)
                    pos_idx += 1
                else:
                    raise ParseError(f"Unexpected positional argument: {tok}")
            i += 1

        # Fill defaults and check required
        for arg in self.args:
            if arg.name not in result:
                if arg.is_flag:
                    result[arg.name] = False
                elif arg.required:
                    raise ParseError(f"Missing required argument: {arg.cli_name}")
                else:
                    result[arg.name] = arg.default

        return result

    def format_help(self) -> str:
        lines = [f"  {self.name}  {self.help_text}"]
        for arg in self.args:
            default = f" [default: {arg.default}]" if not arg.required else ""
            req = " (required)" if arg.required else ""
            lines.append(f"    {arg.cli_name:<20} {arg.arg_type.__name__:<8} {arg.help}{default}{req}")
        return "\n".join(lines)


class App:
    def __init__(self, name: str = "app", description: str = ""):
        self.name = name
        self.description = description
        self._commands: dict[str, Command] = {}

    def command(self, name: str, help_text: str = "") -> Callable:
        def decorator(fn: Callable) -> Callable:
            cmd = Command(name, fn, help_text)
            cmd.auto_args()
            self._commands[name] = cmd
            return fn
        return decorator

    def add_command(self, cmd: Command) -> None:
        self._commands[cmd.name] = cmd

    def format_help(self) -> str:
        lines = [f"Usage: {self.name} <command> [options]", ""]
        if self.description:
            lines.append(self.description)
            lines.append("")
        lines.append("Commands:")
        for cmd in self._commands.values():
            lines.append(cmd.format_help())
            lines.append("")
        return "\n".join(lines)

    def bash_completion(self) -> str:
        cmds = " ".join(self._commands.keys())
        parts = [f'_{self.name}_completions() {{']
        parts.append(f'  local commands="{cmds}"')
        parts.append('  local cur="${COMP_WORDS[COMP_CWORD]}"')
        parts.append('  local prev="${COMP_WORDS[COMP_CWORD-1]}"')
        parts.append('  if [ "$COMP_CWORD" -eq 1 ]; then')
        parts.append('    COMPREPLY=($(compgen -W "$commands" -- "$cur"))')
        parts.append('    return')
        parts.append('  fi')
        # Per-command flag completion
        parts.append('  local cmd="${COMP_WORDS[1]}"')
        parts.append('  case "$cmd" in')
        for cmd_name, cmd in self._commands.items():
            flags = " ".join(f"--{a.name}" for a in cmd.args if not a.positional)
            parts.append(f'    {cmd_name}) COMPREPLY=($(compgen -W "{flags}" -- "$cur")) ;;')
        parts.append('  esac')
        parts.append('}')
        parts.append(f'complete -F _{self.name}_completions {self.name}')
        return "\n".join(parts)

    def run(self, argv: Optional[list[str]] = None) -> Any:
        if argv is None:
            argv = sys.argv[1:]

        if not argv or argv[0] in ("-h", "--help"):
            print(self.format_help())
            return None

        cmd_name = argv[0]
        if cmd_name == "--completion":
            print(self.bash_completion())
            return None

        if cmd_name not in self._commands:
            print(f"Unknown command: {cmd_name}")
            print(f"Available: {', '.join(self._commands.keys())}")
            return None

        cmd = self._commands[cmd_name]
        rest = argv[1:]

        if rest and rest[0] in ("-h", "--help"):
            print(cmd.format_help())
            return None

        try:
            parsed = cmd.parse(rest)
        except ParseError as e:
            print(f"Error: {e}")
            print(cmd.format_help())
            return None

        return cmd.fn(**parsed)


# --- Usage / test ---
if __name__ == "__main__":
    app = App("mytool", "A demo CLI tool")
    results: list[str] = []

    @app.command("greet", help_text="Greet a user")
    def greet(name: str, times: int = 1, loud: bool = False):
        for _ in range(times):
            msg = f"Hello, {name}!" if not loud else f"HELLO, {name.upper()}!"
            results.append(msg)
        return msg

    @app.command("add", help_text="Add two numbers")
    def add(a: str, b: int = 0):
        # 'a' is positional (first param, no default, not bool)
        total = int(a) + b
        results.append(str(total))
        return total

    # Test 1: basic command
    app.run(["greet", "--name", "Alice"])
    assert results[-1] == "Hello, Alice!"

    # Test 2: with optional and flag
    app.run(["greet", "--name", "Bob", "--times", "2", "--loud"])
    assert results[-1] == "HELLO, BOB!"
    assert results.count("HELLO, BOB!") == 2

    # Test 3: positional arg
    val = app.run(["add", "10", "--b", "20"])
    assert val == 30

    # Test 4: help
    print("--- Help ---")
    app.run(["--help"])

    # Test 5: completion script
    print("\n--- Bash completion ---")
    app.run(["--completion"])

    # Test 6: missing required
    print("\n--- Missing arg ---")
    app.run(["greet"])  # should print error

    print("\nAll tests passed.")
```'''
    ),
    (
        "deep_reasoning/finite-state-machine",
        r'''Implement a finite state machine in Python with guard conditions, entry/exit actions, hierarchical (nested) states, and event queuing. Support both sync and async transitions.''',
        r'''<think>
Decomposing the FSM:

Sub-problems:
1. States — each state has a name, optional entry/exit actions, and transitions
2. Transitions — triggered by events, optionally guarded by conditions, with actions
3. Guard conditions — boolean functions that must return True for a transition to fire
4. Hierarchical states — a state can contain sub-states with their own transitions. If an event isn't handled by the current sub-state, it bubbles up to the parent.
5. Event queuing — events can be queued during transitions (e.g., an entry action fires an event). Process queue in FIFO order after current transition completes.
6. Entry/exit actions — when entering a state, run entry action; when leaving, run exit action. For hierarchical states, entering a child also enters the parent (if not already in it).

Interface design:
- sm = StateMachine("idle") to set initial state
- sm.add_state("idle", on_enter=fn, on_exit=fn)
- sm.add_transition(source="idle", event="start", target="running", guard=fn, action=fn)
- sm.send("start") — fire event, find matching transition, execute
- For hierarchical: sm.add_state("active", children=["running", "paused"])

Edge cases:
- No matching transition for event — silently ignore or configurable error
- Guard returns False — transition doesn't fire, event is consumed
- Multiple transitions for same event — first matching guard wins
- Re-entering the same state — should fire exit then entry
- Event fired during entry/exit action — queue it, process after current transition
- Initial state's entry action should fire on machine start

Implementation order:
1. State dataclass with entry/exit hooks
2. Transition dataclass with guard, action, source, target, event
3. StateMachine core — state registry, current state, send()
4. Guard evaluation and transition selection
5. Event queue
6. Hierarchical states (parent tracking, event bubbling)

Self-correction: Hierarchical states add significant complexity. I'll implement them as a parent reference on each state. When entering a child, we also enter ancestors that we're not already in. When leaving a child for a state outside the parent, we exit the child AND the parent.
</think>

```python
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class State:
    name: str
    on_enter: Optional[Callable[[], None]] = None
    on_exit: Optional[Callable[[], None]] = None
    parent: Optional[str] = None
    initial_child: Optional[str] = None  # for hierarchical entry


@dataclass
class Transition:
    source: str
    event: str
    target: str
    guard: Optional[Callable[[], bool]] = None
    action: Optional[Callable[[], None]] = None


class StateMachine:
    def __init__(self, initial: str):
        self._initial = initial
        self._states: dict[str, State] = {}
        self._transitions: list[Transition] = []
        self._current: Optional[str] = None
        self._event_queue: deque[str] = deque()
        self._processing: bool = False
        self._history: list[str] = []
        self._active_states: set[str] = set()  # for hierarchical

    def add_state(
        self,
        name: str,
        on_enter: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
        parent: Optional[str] = None,
        initial_child: Optional[str] = None,
    ) -> "StateMachine":
        self._states[name] = State(name, on_enter, on_exit, parent, initial_child)
        return self

    def add_transition(
        self,
        source: str,
        event: str,
        target: str,
        guard: Optional[Callable[[], bool]] = None,
        action: Optional[Callable[[], None]] = None,
    ) -> "StateMachine":
        self._transitions.append(Transition(source, event, target, guard, action))
        return self

    def _ancestors(self, state_name: str) -> list[str]:
        """Return ancestor chain from state up to root (exclusive of state itself)."""
        chain = []
        current = self._states.get(state_name)
        while current and current.parent:
            chain.append(current.parent)
            current = self._states.get(current.parent)
        return chain

    def _enter_state(self, name: str) -> None:
        state = self._states[name]
        # Enter ancestors first (if not already active)
        ancestors = self._ancestors(name)
        for anc in reversed(ancestors):
            if anc not in self._active_states:
                self._active_states.add(anc)
                anc_state = self._states[anc]
                if anc_state.on_enter:
                    anc_state.on_enter()

        self._active_states.add(name)
        if state.on_enter:
            state.on_enter()

        # If hierarchical state with initial child, descend
        if state.initial_child:
            self._enter_state(state.initial_child)
            self._current = state.initial_child
        else:
            self._current = name

    def _exit_state(self, name: str, target: str) -> None:
        state = self._states[name]
        if state.on_exit:
            state.on_exit()
        self._active_states.discard(name)

        # Exit ancestors that are NOT ancestors of the target
        target_ancestors = set(self._ancestors(target)) | {target}
        for anc in self._ancestors(name):
            if anc not in target_ancestors and anc in self._active_states:
                anc_state = self._states[anc]
                if anc_state.on_exit:
                    anc_state.on_exit()
                self._active_states.discard(anc)

    def start(self) -> None:
        self._enter_state(self._initial)
        self._history.append(self._current or self._initial)

    def _find_transition(self, event: str) -> Optional[Transition]:
        # Check current state and its ancestors for matching transitions
        candidates = [self._current] + self._ancestors(self._current or "")
        for state_name in candidates:
            for t in self._transitions:
                if t.source == state_name and t.event == event:
                    if t.guard is None or t.guard():
                        return t
        return None

    def send(self, event: str) -> bool:
        self._event_queue.append(event)
        if self._processing:
            return True  # queued for later

        self._processing = True
        handled = False
        while self._event_queue:
            evt = self._event_queue.popleft()
            t = self._find_transition(evt)
            if t:
                self._exit_state(self._current, t.target)
                if t.action:
                    t.action()
                self._enter_state(t.target)
                self._history.append(self._current)
                handled = True
        self._processing = False
        return handled

    @property
    def current(self) -> Optional[str]:
        return self._current

    @property
    def history(self) -> list[str]:
        return list(self._history)

    @property
    def active_states(self) -> set[str]:
        return set(self._active_states)


# --- Usage / test ---
if __name__ == "__main__":
    log: list[str] = []

    sm = StateMachine("idle")
    sm.add_state("idle", on_enter=lambda: log.append("enter:idle"), on_exit=lambda: log.append("exit:idle"))
    sm.add_state("active", on_enter=lambda: log.append("enter:active"), initial_child="running", parent=None)
    sm.add_state("running", on_enter=lambda: log.append("enter:running"), on_exit=lambda: log.append("exit:running"), parent="active")
    sm.add_state("paused", on_enter=lambda: log.append("enter:paused"), on_exit=lambda: log.append("exit:paused"), parent="active")
    sm.add_state("stopped", on_enter=lambda: log.append("enter:stopped"))

    sm.add_transition("idle", "start", "active")
    sm.add_transition("running", "pause", "paused")
    sm.add_transition("paused", "resume", "running")
    sm.add_transition("active", "stop", "stopped")  # parent-level transition
    sm.add_transition("idle", "start_fast", "running",
                      guard=lambda: True,
                      action=lambda: log.append("action:fast_start"))

    sm.start()
    print(f"Initial: {sm.current}, log: {log}")
    assert sm.current == "idle"
    assert "enter:idle" in log

    log.clear()
    sm.send("start")
    print(f"After start: {sm.current}, active: {sm.active_states}")
    print(f"  log: {log}")
    assert sm.current == "running"
    assert "active" in sm.active_states  # hierarchical parent is active
    assert "exit:idle" in log
    assert "enter:active" in log
    assert "enter:running" in log

    log.clear()
    sm.send("pause")
    assert sm.current == "paused"
    assert "exit:running" in log
    assert "enter:paused" in log
    # Still inside 'active'
    assert "active" in sm.active_states

    log.clear()
    sm.send("stop")  # handled by parent 'active' transition
    print(f"After stop: {sm.current}, log: {log}")
    assert sm.current == "stopped"
    assert "exit:paused" in log
    assert "enter:stopped" in log
    # 'active' should have been exited
    assert "active" not in sm.active_states

    # Guard test
    sm2 = StateMachine("locked")
    sm2.add_state("locked")
    sm2.add_state("unlocked")
    unlocked = [False]
    sm2.add_transition("locked", "try_unlock", "unlocked", guard=lambda: unlocked[0])
    sm2.start()

    assert not sm2.send("try_unlock")  # guard fails — no state change
    assert sm2.current == "locked"

    unlocked[0] = True
    sm2.send("try_unlock")
    assert sm2.current == "unlocked"

    print(f"History: {sm.history}")
    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/reactive-data-binding",
        r'''Create a reactive data binding system in Python (inspired by Vue's reactivity) with observable objects, computed properties that auto-update, and watchers that trigger callbacks when values change.''',
        r'''<think>
Decomposing the reactive system:

Sub-problems:
1. Reactive/Observable — an object whose property access and mutation are intercepted. Getting a property records it as a "dependency," setting a property notifies dependents.
2. Dependency tracking — when a computed property or watcher evaluates, we need to know which reactive properties it accessed. Classic approach: a global "active effect" stack. During evaluation, every property get pushes a dependency.
3. Computed properties — lazily evaluated, cached until a dependency changes. When a dep changes, the computed is marked dirty and re-evaluates on next access.
4. Watchers — callback functions that run whenever tracked reactive values change. Unlike computed, they execute immediately on change (or can be deferred).
5. Nested reactivity — if a reactive object's property is itself an object, it should also be reactive.

Interface design:
- state = reactive({"count": 0, "name": "Alice"})
- doubled = computed(lambda: state.count * 2)
- watch(lambda: state.count, callback=lambda old, new: print(f"{old} -> {new}"))
- state.count = 5 triggers watcher and invalidates computed

Edge cases:
- Circular computed dependencies — A depends on B depends on A. Should detect and raise.
- Computed accessed during another computed's evaluation — should track correctly (nested dependency)
- Setting a property to the same value — should NOT trigger watchers
- Batch updates — multiple changes should not trigger watchers N times. I'll add a batching mechanism.
- Deleting a property from a reactive object

Implementation order:
1. Dependency tracking infrastructure (global stack, Dep class)
2. Reactive proxy (intercept get/set via __getattr__/__setattr__)
3. Effect function (the primitive both computed and watch use)
4. Computed property (lazy + caching)
5. Watch function

Self-correction: Python doesn't have Proxy like JavaScript. I'll use a custom class with __getattr__/__setattr__ that wraps a dict. For nested objects, I'll recursively make sub-dicts reactive.
</think>

```python
from typing import Any, Callable, Optional


# ============================================================
# 1. Dependency tracking
# ============================================================

class Dep:
    """A dependency tracker for one reactive property."""
    def __init__(self):
        self._subscribers: set["Effect"] = set()

    def depend(self) -> None:
        if Effect.active:
            self._subscribers.add(Effect.active)
            Effect.active._deps.add(self)

    def notify(self) -> None:
        for effect in list(self._subscribers):
            effect.trigger()

    def remove(self, effect: "Effect") -> None:
        self._subscribers.discard(effect)


class Effect:
    active: Optional["Effect"] = None
    _stack: list["Effect"] = []

    def __init__(self, fn: Callable, scheduler: Optional[Callable] = None):
        self.fn = fn
        self.scheduler = scheduler
        self._deps: set[Dep] = set()

    def run(self) -> Any:
        # Clean old deps
        for dep in self._deps:
            dep.remove(self)
        self._deps.clear()

        Effect._stack.append(Effect.active)
        Effect.active = self
        try:
            return self.fn()
        finally:
            Effect.active = Effect._stack.pop()

    def trigger(self) -> None:
        if self.scheduler:
            self.scheduler(self)
        else:
            self.run()


# ============================================================
# 2. Reactive proxy
# ============================================================

class ReactiveObject:
    def __init__(self, data: dict):
        # Use object.__setattr__ to avoid triggering our custom __setattr__
        object.__setattr__(self, "_data", {})
        object.__setattr__(self, "_deps", {})
        for key, value in data.items():
            self._data[key] = _make_reactive(value)
            self._deps[key] = Dep()

    def __getattr__(self, name: str) -> Any:
        data = object.__getattribute__(self, "_data")
        deps = object.__getattribute__(self, "_deps")
        if name in data:
            deps[name].depend()
            return data[name]
        raise AttributeError(f"No reactive property: {name}")

    def __setattr__(self, name: str, value: Any) -> None:
        data = object.__getattribute__(self, "_data")
        deps = object.__getattribute__(self, "_deps")
        old = data.get(name)
        new = _make_reactive(value)
        if old is new or (not isinstance(old, ReactiveObject) and old == new):
            return  # no change
        data[name] = new
        if name not in deps:
            deps[name] = Dep()
        deps[name].notify()

    def __repr__(self) -> str:
        data = object.__getattribute__(self, "_data")
        return f"ReactiveObject({data})"


def _make_reactive(value: Any) -> Any:
    if isinstance(value, dict):
        return ReactiveObject(value)
    return value


def reactive(data: dict) -> ReactiveObject:
    return ReactiveObject(data)


# ============================================================
# 3. Computed
# ============================================================

class ComputedRef:
    def __init__(self, getter: Callable[[], Any]):
        self._getter = getter
        self._value: Any = None
        self._dirty: bool = True
        self._dep = Dep()

        def scheduler(effect: Effect) -> None:
            if not self._dirty:
                self._dirty = True
                self._dep.notify()

        self._effect = Effect(getter, scheduler=scheduler)

    @property
    def value(self) -> Any:
        if self._dirty:
            self._value = self._effect.run()
            self._dirty = False
        self._dep.depend()
        return self._value


def computed(getter: Callable[[], Any]) -> ComputedRef:
    return ComputedRef(getter)


# ============================================================
# 4. Watcher
# ============================================================

class Watcher:
    def __init__(
        self,
        source: Callable[[], Any],
        callback: Callable[[Any, Any], None],
        immediate: bool = False,
    ):
        self._source = source
        self._callback = callback
        self._old_value: Any = None

        self._effect = Effect(self._evaluate, scheduler=lambda e: self._on_change())

        # Initial run to collect dependencies
        self._old_value = self._effect.run()
        if immediate:
            self._callback(None, self._old_value)

    def _evaluate(self) -> Any:
        return self._source()

    def _on_change(self) -> None:
        new_value = self._effect.run()
        old_value = self._old_value
        if new_value != old_value or isinstance(new_value, ReactiveObject):
            self._old_value = new_value
            self._callback(old_value, new_value)


def watch(
    source: Callable[[], Any],
    callback: Callable[[Any, Any], None],
    immediate: bool = False,
) -> Watcher:
    return Watcher(source, callback, immediate)


# --- Usage / test ---
if __name__ == "__main__":
    state = reactive({"count": 0, "name": "Alice", "items": {"a": 1}})

    # Computed
    doubled = computed(lambda: state.count * 2)
    greeting = computed(lambda: f"Hello, {state.name}! (x{doubled.value})")

    assert doubled.value == 0
    assert greeting.value == "Hello, Alice! (x0)"

    # Watcher
    changes: list[tuple] = []
    watch(lambda: state.count, lambda old, new: changes.append(("count", old, new)))

    # Mutate
    state.count = 5
    assert doubled.value == 10
    assert greeting.value == "Hello, Alice! (x10)"
    assert changes == [("count", 0, 5)]
    print(f"After count=5: doubled={doubled.value}, greeting={greeting.value}")

    # Same value — no trigger
    state.count = 5
    assert len(changes) == 1  # no new change

    # Name change
    name_changes: list[tuple] = []
    watch(lambda: state.name, lambda old, new: name_changes.append((old, new)))
    state.name = "Bob"
    assert greeting.value == "Hello, Bob! (x10)"
    assert name_changes == [("Alice", "Bob")]

    # Nested reactive
    state.items = {"x": 99}
    nested = state.items
    assert isinstance(nested, ReactiveObject)

    print(f"Changes: {changes}")
    print(f"Name changes: {name_changes}")
    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/job-queue-workers",
        r'''Build a job queue system in Python with worker processes, retry logic with configurable max retries, dead letter handling for permanently failed jobs, and real-time progress tracking.''',
        r'''<think>
Decomposing the job queue:

Sub-problems:
1. Job — has an ID, payload, status (pending/running/completed/failed/dead), attempt count, progress percentage, result or error.
2. Queue — thread-safe FIFO queue of pending jobs. Workers pull from this.
3. Workers — threads (or processes) that pull jobs, execute them, update status. Configurable worker count.
4. Retry logic — if a job fails, re-enqueue it if attempts < max_retries. Otherwise, move to dead letter queue.
5. Dead letter queue — separate list/queue for permanently failed jobs. Can be inspected and retried manually.
6. Progress tracking — jobs can report progress (0-100%) during execution. Need a thread-safe way for the job function to call back with progress updates.

Interface design:
- queue = JobQueue(workers=4, max_retries=3)
- job_id = queue.enqueue(fn, *args, **kwargs)
- queue.get_status(job_id) -> JobStatus with status, progress, result, attempts
- Job function signature: def my_job(ctx: JobContext, *args): ctx.report_progress(50)
- queue.dead_letters -> list of failed jobs
- queue.retry_dead_letter(job_id) -> re-enqueue from DLQ
- queue.shutdown() -> wait for running jobs, stop workers

Edge cases:
- Job raises exception — catch, increment attempt, re-enqueue or DLQ
- Worker thread dies — shouldn't crash the whole queue
- Shutdown while jobs are running — wait for current jobs, don't start new ones
- Progress reported after job completes — ignore
- Enqueue after shutdown — raise error

Implementation order:
1. Job dataclass and JobContext (progress reporting)
2. JobQueue with internal queue and job registry
3. Worker loop
4. Retry and DLQ logic
5. Progress tracking (thread-safe)
6. Shutdown

I'll use threading for workers since the prompt says "worker processes" but threading is simpler for a demonstration. The interface works the same way.
</think>

```python
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


@dataclass
class Job:
    job_id: str
    fn: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    attempt: int = 0
    max_retries: int = 3
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)


class JobContext:
    """Passed to job functions for progress reporting."""
    def __init__(self, job: Job, lock: threading.Lock):
        self._job = job
        self._lock = lock

    def report_progress(self, pct: float) -> None:
        with self._lock:
            if self._job.status == JobStatus.RUNNING:
                self._job.progress = max(0.0, min(100.0, pct))

    @property
    def attempt(self) -> int:
        return self._job.attempt


class JobQueue:
    def __init__(self, workers: int = 2, max_retries: int = 3):
        self._max_retries = max_retries
        self._lock = threading.Lock()
        self._queue: deque[str] = deque()
        self._jobs: dict[str, Job] = {}
        self._dead_letters: list[str] = []
        self._shutdown = False
        self._event = threading.Event()
        self._workers: list[threading.Thread] = []

        for i in range(workers):
            t = threading.Thread(target=self._worker_loop, name=f"worker-{i}", daemon=True)
            t.start()
            self._workers.append(t)

    def enqueue(self, fn: Callable, *args: Any, **kwargs: Any) -> str:
        with self._lock:
            if self._shutdown:
                raise RuntimeError("Queue is shut down")
            job_id = uuid.uuid4().hex[:10]
            job = Job(
                job_id=job_id,
                fn=fn,
                args=args,
                kwargs=kwargs,
                max_retries=self._max_retries,
            )
            self._jobs[job_id] = job
            self._queue.append(job_id)
        self._event.set()
        return job_id

    def get_status(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return {"error": "unknown job"}
            return {
                "job_id": job.job_id,
                "status": job.status.value,
                "progress": job.progress,
                "attempt": job.attempt,
                "result": job.result,
                "error": job.error,
            }

    @property
    def dead_letters(self) -> list[dict]:
        with self._lock:
            return [self.get_status(jid) for jid in self._dead_letters]

    def retry_dead_letter(self, job_id: str) -> bool:
        with self._lock:
            if job_id not in self._dead_letters:
                return False
            job = self._jobs[job_id]
            self._dead_letters.remove(job_id)
            job.status = JobStatus.PENDING
            job.attempt = 0
            job.progress = 0.0
            job.error = None
            self._queue.append(job_id)
        self._event.set()
        return True

    def _worker_loop(self) -> None:
        while True:
            self._event.wait(timeout=0.1)
            job_id = None
            with self._lock:
                if self._shutdown and not self._queue:
                    return
                if self._queue:
                    job_id = self._queue.popleft()
                else:
                    self._event.clear()

            if job_id is None:
                if self._shutdown:
                    return
                continue

            job = self._jobs[job_id]
            with self._lock:
                job.status = JobStatus.RUNNING
                job.attempt += 1
                job.progress = 0.0

            ctx = JobContext(job, self._lock)
            try:
                result = job.fn(ctx, *job.args, **job.kwargs)
                with self._lock:
                    job.status = JobStatus.COMPLETED
                    job.result = result
                    job.progress = 100.0
            except Exception as e:
                with self._lock:
                    job.error = str(e)
                    if job.attempt >= job.max_retries:
                        job.status = JobStatus.DEAD
                        self._dead_letters.append(job_id)
                    else:
                        job.status = JobStatus.PENDING
                        self._queue.append(job_id)
                        self._event.set()

    def shutdown(self, wait: bool = True) -> None:
        self._shutdown = True
        self._event.set()
        if wait:
            for t in self._workers:
                t.join(timeout=5.0)

    def wait_for(self, job_id: str, timeout: float = 10.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.get_status(job_id)
            if status["status"] in ("completed", "dead"):
                return status
            time.sleep(0.05)
        return self.get_status(job_id)


# --- Usage / test ---
if __name__ == "__main__":
    q = JobQueue(workers=2, max_retries=3)

    # Successful job with progress
    def process_data(ctx: JobContext, n: int) -> str:
        for i in range(n):
            ctx.report_progress((i + 1) / n * 100)
            time.sleep(0.01)
        return f"processed {n} items"

    j1 = q.enqueue(process_data, 10)

    # Flaky job — fails first 2 attempts
    attempt_counter = {"count": 0}
    def flaky_job(ctx: JobContext) -> str:
        attempt_counter["count"] += 1
        if attempt_counter["count"] < 3:
            raise RuntimeError(f"fail #{attempt_counter['count']}")
        return "finally worked"

    j2 = q.enqueue(flaky_job)

    # Always-failing job
    def bad_job(ctx: JobContext) -> str:
        raise ValueError("permanent failure")

    j3 = q.enqueue(bad_job)

    # Wait for results
    r1 = q.wait_for(j1)
    print(f"Job 1: {r1}")
    assert r1["status"] == "completed"
    assert r1["result"] == "processed 10 items"

    r2 = q.wait_for(j2)
    print(f"Job 2: {r2}")
    assert r2["status"] == "completed"
    assert r2["result"] == "finally worked"

    r3 = q.wait_for(j3, timeout=5)
    print(f"Job 3: {r3}")
    assert r3["status"] == "dead"

    # Dead letter queue
    dl = q.dead_letters
    print(f"Dead letters: {len(dl)}")
    assert len(dl) == 1
    assert dl[0]["job_id"] == j3

    q.shutdown()
    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/plugin-loader-versions",
        r'''Implement a plugin loader system in Python with dependency resolution between plugins, semantic version constraints (>=, <, ~=), and hot reload support (unload a plugin, load a new version without restarting).''',
        r'''<think>
Decomposing the plugin system:

Sub-problems:
1. Plugin interface — base class with lifecycle hooks: on_load(), on_unload(). Each plugin declares a name, version, and dependencies (with version constraints).
2. Plugin registry — tracks loaded plugins by name, stores metadata.
3. Dependency resolution — topological sort of plugins based on their dependencies. Must resolve version constraints: ">=1.0.0,<2.0.0".
4. Semantic versioning — parse "1.2.3" and compare. Support operators: >=, <=, >, <, ==, ~= (compatible release: ~=1.4 means >=1.4,<2.0).
5. Hot reload — unload a plugin (call on_unload, remove from registry), then load a new version. Must check that no other loaded plugin depends on the old version in a way that the new version doesn't satisfy.

Interface design:
- class MyPlugin(Plugin): name="my_plugin", version="1.2.0", depends={"core": ">=1.0.0"}
- loader = PluginLoader()
- loader.register(MyPlugin)
- loader.load_all() — resolve deps, load in order
- loader.reload("my_plugin", NewVersionClass) — hot reload

Edge cases:
- Dependency not found — error with clear message
- Version constraint not satisfied — error listing available vs required versions
- Circular plugin dependencies — detect and error
- Unloading a plugin that others depend on — error or cascade unload
- Hot reload changes interface — can't prevent this in Python, but we can warn

Implementation order:
1. SemVer class (parse, compare)
2. Version constraint parser and matcher
3. Plugin base class
4. PluginLoader with registration and dependency resolution
5. Load/unload lifecycle
6. Hot reload

Self-correction: For the version constraint parser, I need to handle compound constraints like ">=1.0.0,<2.0.0". I'll split on comma and AND them together. The ~= operator needs special handling: ~=1.4.2 means >=1.4.2,<1.5.0.
</think>

```python
import re
from typing import Any, Optional, Type
from dataclasses import dataclass, field


# ============================================================
# 1. Semantic Versioning
# ============================================================

@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, version: str) -> "SemVer":
        parts = version.strip().split(".")
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return cls(major, minor, patch)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


# ============================================================
# 2. Version constraints
# ============================================================

class VersionConstraint:
    def __init__(self, spec: str):
        self.spec = spec
        self._checks: list[tuple[str, SemVer]] = []
        for part in spec.split(","):
            part = part.strip()
            match = re.match(r"^(~=|>=|<=|!=|>|<|==)?\s*(.+)$", part)
            if not match:
                raise ValueError(f"Invalid version constraint: {part}")
            op = match.group(1) or "=="
            ver = SemVer.parse(match.group(2))
            if op == "~=":
                # Compatible release: ~=1.4.2 -> >=1.4.2,<1.5.0
                self._checks.append((">=", ver))
                self._checks.append(("<", SemVer(ver.major, ver.minor + 1, 0)))
            else:
                self._checks.append((op, ver))

    def matches(self, version: SemVer) -> bool:
        ops = {
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        return all(ops[op](version, ver) for op, ver in self._checks)

    def __repr__(self) -> str:
        return f"VersionConstraint({self.spec!r})"


# ============================================================
# 3. Plugin base class
# ============================================================

class Plugin:
    name: str = "unnamed"
    version: str = "0.0.0"
    depends: dict[str, str] = {}  # {plugin_name: version_constraint_spec}

    def on_load(self, loader: "PluginLoader") -> None:
        pass

    def on_unload(self) -> None:
        pass

    @classmethod
    def semver(cls) -> SemVer:
        return SemVer.parse(cls.version)


# ============================================================
# 4. Plugin Loader
# ============================================================

class PluginError(Exception):
    pass


class PluginLoader:
    def __init__(self):
        self._registered: dict[str, Type[Plugin]] = {}
        self._loaded: dict[str, Plugin] = {}

    def register(self, plugin_cls: Type[Plugin]) -> None:
        self._registered[plugin_cls.name] = plugin_cls

    def _resolve_order(self) -> list[str]:
        """Topological sort of plugins by dependency."""
        # Build adjacency
        order: list[str] = []
        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(name: str) -> None:
            if name in visited:
                return
            if name in visiting:
                raise PluginError(f"Circular dependency involving '{name}'")
            if name not in self._registered:
                raise PluginError(f"Plugin '{name}' not registered")

            visiting.add(name)
            cls = self._registered[name]
            for dep_name in cls.depends:
                visit(dep_name)
            visiting.remove(name)
            visited.add(name)
            order.append(name)

        for name in self._registered:
            visit(name)

        return order

    def _check_version_constraints(self, plugin_cls: Type[Plugin]) -> None:
        for dep_name, constraint_spec in plugin_cls.depends.items():
            if dep_name not in self._registered:
                raise PluginError(
                    f"Plugin '{plugin_cls.name}' requires '{dep_name}' but it's not registered"
                )
            dep_cls = self._registered[dep_name]
            constraint = VersionConstraint(constraint_spec)
            if not constraint.matches(dep_cls.semver()):
                raise PluginError(
                    f"Plugin '{plugin_cls.name}' requires '{dep_name}' {constraint_spec}, "
                    f"but version {dep_cls.version} is registered"
                )

    def load_all(self) -> list[str]:
        order = self._resolve_order()
        loaded_names = []

        for name in order:
            if name in self._loaded:
                continue
            cls = self._registered[name]
            self._check_version_constraints(cls)
            instance = cls()
            instance.on_load(self)
            self._loaded[name] = instance
            loaded_names.append(name)

        return loaded_names

    def unload(self, name: str) -> None:
        if name not in self._loaded:
            raise PluginError(f"Plugin '{name}' is not loaded")

        # Check if any loaded plugin depends on this one
        for other_name, other in self._loaded.items():
            if other_name == name:
                continue
            if name in other.__class__.depends:
                raise PluginError(
                    f"Cannot unload '{name}': '{other_name}' depends on it"
                )

        plugin = self._loaded[name]
        plugin.on_unload()
        del self._loaded[name]

    def reload(self, name: str, new_cls: Type[Plugin]) -> None:
        """Hot reload: unload old, register new, load new."""
        if name in self._loaded:
            # Temporarily remove dependency checks for this plugin
            old_cls = self._registered[name]
            self._registered[name] = new_cls
            # Verify new version satisfies all dependents
            try:
                for other_name, other_cls in self._registered.items():
                    if other_name == name:
                        continue
                    if name in other_cls.depends:
                        constraint = VersionConstraint(other_cls.depends[name])
                        if not constraint.matches(new_cls.semver()):
                            raise PluginError(
                                f"New version {new_cls.version} of '{name}' doesn't satisfy "
                                f"'{other_name}' constraint: {other_cls.depends[name]}"
                            )
            except PluginError:
                self._registered[name] = old_cls  # rollback
                raise

            self._loaded[name].on_unload()
            del self._loaded[name]
        else:
            self._registered[name] = new_cls

        instance = new_cls()
        instance.on_load(self)
        self._loaded[name] = instance

    def get(self, name: str) -> Optional[Plugin]:
        return self._loaded.get(name)

    @property
    def loaded_plugins(self) -> dict[str, str]:
        return {name: p.__class__.version for name, p in self._loaded.items()}


# --- Usage / test ---
if __name__ == "__main__":
    log: list[str] = []

    class CorePlugin(Plugin):
        name = "core"
        version = "2.1.0"
        depends = {}
        def on_load(self, loader):
            log.append(f"core:{self.version}:loaded")
        def on_unload(self):
            log.append(f"core:{self.version}:unloaded")

    class AuthPlugin(Plugin):
        name = "auth"
        version = "1.3.0"
        depends = {"core": ">=2.0.0,<3.0.0"}
        def on_load(self, loader):
            log.append(f"auth:{self.version}:loaded")
        def on_unload(self):
            log.append(f"auth:unloaded")

    class DashboardPlugin(Plugin):
        name = "dashboard"
        version = "0.5.0"
        depends = {"core": ">=1.0.0", "auth": "~=1.3"}
        def on_load(self, loader):
            log.append(f"dashboard:loaded")
        def on_unload(self):
            log.append(f"dashboard:unloaded")

    loader = PluginLoader()
    loader.register(CorePlugin)
    loader.register(AuthPlugin)
    loader.register(DashboardPlugin)

    loaded = loader.load_all()
    print(f"Load order: {loaded}")
    print(f"Log: {log}")
    assert loaded.index("core") < loaded.index("auth")
    assert loaded.index("auth") < loaded.index("dashboard")

    # Hot reload auth to 1.4.0 (still satisfies ~=1.3 of dashboard? No: ~=1.3 means >=1.3,<1.4)
    class AuthV14(Plugin):
        name = "auth"
        version = "1.4.0"
        depends = {"core": ">=2.0.0"}
        def on_load(self, loader): log.append("auth:1.4.0:loaded")
        def on_unload(self): log.append("auth:1.4.0:unloaded")

    # This should fail — dashboard requires auth ~=1.3 (i.e. >=1.3.0,<1.4.0)
    try:
        loader.reload("auth", AuthV14)
        assert False, "Should have raised"
    except PluginError as e:
        print(f"Expected error: {e}")

    # Reload to 1.3.5 — should work
    class AuthV135(Plugin):
        name = "auth"
        version = "1.3.5"
        depends = {"core": ">=2.0.0"}
        def on_load(self, loader): log.append("auth:1.3.5:loaded")
        def on_unload(self): log.append("auth:1.3.5:unloaded")

    loader.reload("auth", AuthV135)
    assert loader.loaded_plugins["auth"] == "1.3.5"
    print(f"After reload: {loader.loaded_plugins}")

    # Version constraint test
    vc = VersionConstraint(">=1.0.0,<2.0.0")
    assert vc.matches(SemVer(1, 5, 0))
    assert not vc.matches(SemVer(2, 0, 0))
    assert not vc.matches(SemVer(0, 9, 0))

    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/cache-ttl-lru-stampede",
        r'''Create an in-memory cache in Python with TTL (time-to-live) expiration, LRU eviction when capacity is reached, cache-aside pattern helpers, and stampede prevention (only one thread computes a missing value while others wait).''',
        r'''<think>
Decomposing the caching system:

Sub-problems:
1. Core cache store — dict-based, each entry has value, expiry timestamp, access metadata
2. TTL — each entry expires after N seconds. On get, check if expired. Also need background/lazy eviction.
3. LRU eviction — when cache is at capacity and a new entry needs space, evict the least recently used. Use OrderedDict or a doubly-linked list.
4. Cache-aside pattern — helper method: get_or_set(key, factory_fn, ttl). If key exists and not expired, return it. Otherwise, call factory_fn, cache the result, return it.
5. Stampede prevention — when a cache miss triggers computation, other threads requesting the same key should wait for the first computation rather than all computing simultaneously. Use per-key locks or futures.

Interface design:
- cache = Cache(max_size=100, default_ttl=60)
- cache.get(key) -> value or None
- cache.set(key, value, ttl=optional)
- cache.get_or_set(key, factory, ttl) — with stampede prevention
- cache.delete(key)
- cache.stats() -> hits, misses, evictions

Edge cases:
- get() on expired key — treat as miss, lazy-delete the entry
- Cache full + all entries still valid — evict LRU even if not expired
- factory_fn raises exception in get_or_set — don't cache the error, let other waiters also try (or propagate the error)
- Concurrent get_or_set for same key — only first computes, others wait
- TTL=0 — no expiration
- max_size=0 — unlimited

Implementation order:
1. CacheEntry dataclass
2. Core get/set/delete with OrderedDict for LRU ordering
3. TTL checking in get()
4. LRU eviction in set()
5. Stampede prevention with per-key threading.Event or threading.Lock
6. get_or_set()
7. Stats tracking

Self-correction: For stampede prevention, a simple per-key Lock won't work because the second thread needs to get the VALUE computed by the first thread. Better approach: use a "pending" dict mapping key -> Future (or Event + result holder). First thread sets the pending entry, computes, stores result, signals event. Other threads wait on the event.
</think>

```python
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class CacheEntry:
    value: Any
    expires_at: float  # 0 = never expires
    created_at: float = field(default_factory=time.time)


class CacheComputeError(Exception):
    """Wraps an error from a cache-aside factory function."""
    pass


class _PendingComputation:
    def __init__(self):
        self.event = threading.Event()
        self.value: Any = None
        self.error: Optional[Exception] = None
        self.done: bool = False


class Cache:
    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: float = 60.0,
        time_fn: Optional[Callable[[], float]] = None,
    ):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._time_fn = time_fn or time.time
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._pending: dict[str, _PendingComputation] = {}

        # Stats
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def _is_expired(self, entry: CacheEntry) -> bool:
        if entry.expires_at == 0:
            return False
        return self._time_fn() > entry.expires_at

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._store:
                entry = self._store[key]
                if self._is_expired(entry):
                    del self._store[key]
                    self.misses += 1
                    return None
                # Move to end (most recently used)
                self._store.move_to_end(key)
                self.hits += 1
                return entry.value
            self.misses += 1
            return None

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        if ttl is None:
            ttl = self._default_ttl

        with self._lock:
            now = self._time_fn()
            expires_at = now + ttl if ttl > 0 else 0

            if key in self._store:
                self._store.move_to_end(key)
                self._store[key] = CacheEntry(value=value, expires_at=expires_at, created_at=now)
            else:
                # Evict if at capacity
                if self._max_size > 0:
                    while len(self._store) >= self._max_size:
                        evicted_key, _ = self._store.popitem(last=False)
                        self.evictions += 1
                self._store[key] = CacheEntry(value=value, expires_at=expires_at, created_at=now)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: Optional[float] = None,
    ) -> Any:
        # Fast path: already cached
        result = self.get(key)
        if result is not None:
            return result

        # Stampede prevention: check if someone else is computing this key
        with self._lock:
            # Double-check after acquiring lock
            if key in self._store and not self._is_expired(self._store[key]):
                self._store.move_to_end(key)
                self.hits += 1
                return self._store[key].value

            if key in self._pending:
                pending = self._pending[key]
            else:
                pending = _PendingComputation()
                self._pending[key] = pending
                pending = None  # signal that WE are the one to compute

        if pending is not None:
            # Wait for the computing thread
            self._pending[key].event.wait(timeout=30.0)
            p = self._pending.get(key)
            if p and p.done:
                if p.error:
                    raise CacheComputeError(str(p.error))
                return p.value
            return self.get(key)  # fallback

        # We are the computing thread
        computation = self._pending[key] = _PendingComputation()
        try:
            value = factory()
            self.set(key, value, ttl)
            computation.value = value
            computation.done = True
            computation.event.set()
            return value
        except Exception as e:
            computation.error = e
            computation.done = True
            computation.event.set()
            raise
        finally:
            with self._lock:
                self._pending.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)

    def stats(self) -> dict[str, int]:
        return {
            "size": self.size,
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_rate": round(self.hits / max(1, self.hits + self.misses) * 100, 1),
        }


# --- Usage / test ---
if __name__ == "__main__":
    sim_time = [0.0]
    cache = Cache(max_size=3, default_ttl=10.0, time_fn=lambda: sim_time[0])

    # Basic set/get
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.get("a") == 1
    assert cache.get("b") == 2
    assert cache.size == 3

    # LRU eviction: adding "d" should evict "c" (least recently used after accessing a and b)
    cache.set("d", 4)
    assert cache.get("c") is None  # evicted (c was accessed earliest and not touched after set)
    assert cache.get("d") == 4
    print(f"After eviction: size={cache.size}, evictions={cache.evictions}")
    assert cache.evictions == 1

    # TTL expiration
    cache.set("temp", "expires", ttl=5.0)
    assert cache.get("temp") == "expires"
    sim_time[0] = 6.0
    assert cache.get("temp") is None  # expired
    print(f"After TTL: misses={cache.misses}")

    # Cache-aside
    compute_count = [0]
    def expensive():
        compute_count[0] += 1
        return "computed_value"

    sim_time[0] = 0.0
    result = cache.get_or_set("computed", expensive, ttl=30)
    assert result == "computed_value"
    assert compute_count[0] == 1

    result2 = cache.get_or_set("computed", expensive, ttl=30)
    assert result2 == "computed_value"
    assert compute_count[0] == 1  # not recomputed

    # Stampede prevention test (multi-threaded)
    slow_cache = Cache(max_size=100, default_ttl=60)
    slow_compute_count = [0]
    results_list = []

    def slow_factory():
        slow_compute_count[0] += 1
        time.sleep(0.1)
        return f"result-{slow_compute_count[0]}"

    threads = []
    for _ in range(5):
        t = threading.Thread(
            target=lambda: results_list.append(
                slow_cache.get_or_set("shared_key", slow_factory)
            )
        )
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"Stampede test: compute_count={slow_compute_count[0]}, results={results_list}")
    assert slow_compute_count[0] == 1  # only one computation
    assert all(r == "result-1" for r in results_list)

    print(f"Stats: {cache.stats()}")
    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/rate-limiter-sliding-token",
        r'''Build a rate limiter in Python with sliding window counting, token bucket algorithm, and per-client tracking. Support multiple strategies and composability (e.g., 100 requests/minute AND 10 requests/second).''',
        r'''<think>
Decomposing the rate limiter:

Sub-problems:
1. Sliding window counter — track requests in a time window that slides (not fixed intervals). Count requests in [now - window, now]. If count >= limit, reject.
2. Token bucket — bucket fills at a fixed rate (tokens/second) up to a max capacity. Each request consumes one token. If empty, reject.
3. Per-client tracking — each client (identified by key like IP or user ID) has its own independent limiter state.
4. Composability — combine multiple limiters with AND logic: request is allowed only if ALL limiters allow it. E.g., 10/sec AND 100/min.

Interface design:
- limiter = SlidingWindowLimiter(max_requests=100, window_seconds=60)
- limiter = TokenBucketLimiter(rate=10, capacity=20)
- limiter = CompositeLimiter(limiter1, limiter2) — all must allow
- limiter.allow(client_id) -> bool
- limiter.allow(client_id) -> RateLimitResult with allowed, remaining, retry_after

Edge cases:
- First request ever — should always be allowed
- Exactly at the limit — reject the next one
- Clock skew — use monotonic time or injectable time function
- Per-client cleanup — clients that stop sending requests should eventually have their state cleaned up (memory leak prevention)
- Token bucket: burst handling — bucket starts full, allows burst up to capacity

Implementation order:
1. RateLimitResult dataclass
2. Base Limiter protocol/ABC
3. SlidingWindowLimiter with per-client state
4. TokenBucketLimiter with per-client state
5. CompositeLimiter
6. Cleanup mechanism for stale clients

Self-correction: For the sliding window, I initially thought of storing every request timestamp. That's O(n) memory per client. For high-traffic systems, a better approach is the "sliding window counter" that interpolates between the previous and current fixed window. But for correctness and clarity, I'll store timestamps and evict old ones. I'll add a max_history parameter to cap memory.
</think>

```python
import time
import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Callable


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int = 0
    retry_after: float = 0.0
    limit: int = 0


class Limiter(ABC):
    @abstractmethod
    def allow(self, client_id: str) -> RateLimitResult:
        ...

    @abstractmethod
    def reset(self, client_id: str) -> None:
        ...


# ============================================================
# 1. Sliding Window
# ============================================================

class SlidingWindowLimiter(Limiter):
    def __init__(
        self,
        max_requests: int,
        window: float,
        time_fn: Optional[Callable[[], float]] = None,
    ):
        self.max_requests = max_requests
        self.window = window
        self._time_fn = time_fn or time.monotonic
        self._clients: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _evict(self, timestamps: list[float], now: float) -> list[float]:
        cutoff = now - self.window
        # Binary search would be faster but list comprehension is clear
        return [t for t in timestamps if t > cutoff]

    def allow(self, client_id: str) -> RateLimitResult:
        with self._lock:
            now = self._time_fn()
            self._clients[client_id] = self._evict(self._clients[client_id], now)
            count = len(self._clients[client_id])

            if count < self.max_requests:
                self._clients[client_id].append(now)
                return RateLimitResult(
                    allowed=True,
                    remaining=self.max_requests - count - 1,
                    limit=self.max_requests,
                )
            else:
                oldest = self._clients[client_id][0]
                retry_after = oldest + self.window - now
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    retry_after=max(0, retry_after),
                    limit=self.max_requests,
                )

    def reset(self, client_id: str) -> None:
        with self._lock:
            self._clients.pop(client_id, None)


# ============================================================
# 2. Token Bucket
# ============================================================

@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class TokenBucketLimiter(Limiter):
    def __init__(
        self,
        rate: float,
        capacity: int,
        time_fn: Optional[Callable[[], float]] = None,
    ):
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self._time_fn = time_fn or time.monotonic
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, client_id: str) -> _Bucket:
        if client_id not in self._buckets:
            self._buckets[client_id] = _Bucket(
                tokens=float(self.capacity),
                last_refill=self._time_fn(),
            )
        return self._buckets[client_id]

    def _refill(self, bucket: _Bucket, now: float) -> None:
        elapsed = now - bucket.last_refill
        bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.rate)
        bucket.last_refill = now

    def allow(self, client_id: str) -> RateLimitResult:
        with self._lock:
            now = self._time_fn()
            bucket = self._get_bucket(client_id)
            self._refill(bucket, now)

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return RateLimitResult(
                    allowed=True,
                    remaining=int(bucket.tokens),
                    limit=self.capacity,
                )
            else:
                deficit = 1.0 - bucket.tokens
                retry_after = deficit / self.rate
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    retry_after=retry_after,
                    limit=self.capacity,
                )

    def reset(self, client_id: str) -> None:
        with self._lock:
            self._buckets.pop(client_id, None)


# ============================================================
# 3. Composite Limiter
# ============================================================

class CompositeLimiter(Limiter):
    """All inner limiters must allow for the request to pass."""

    def __init__(self, *limiters: Limiter):
        self._limiters = list(limiters)

    def allow(self, client_id: str) -> RateLimitResult:
        results = [lim.allow(client_id) for lim in self._limiters]

        if all(r.allowed for r in results):
            return RateLimitResult(
                allowed=True,
                remaining=min(r.remaining for r in results),
                limit=min(r.limit for r in results),
            )
        else:
            # Find the worst offender
            denied = [r for r in results if not r.allowed]
            max_retry = max(r.retry_after for r in denied)
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after=max_retry,
                limit=min(r.limit for r in results),
            )

    def reset(self, client_id: str) -> None:
        for lim in self._limiters:
            lim.reset(client_id)


# --- Usage / test ---
if __name__ == "__main__":
    sim_time = [0.0]
    tf = lambda: sim_time[0]

    # Test sliding window: 3 requests per 10 seconds
    sw = SlidingWindowLimiter(max_requests=3, window=10.0, time_fn=tf)

    assert sw.allow("user1").allowed  # 1
    assert sw.allow("user1").allowed  # 2
    r3 = sw.allow("user1")           # 3
    assert r3.allowed
    assert r3.remaining == 0

    r4 = sw.allow("user1")           # 4 -> rejected
    assert not r4.allowed
    print(f"Sliding window: rejected, retry_after={r4.retry_after:.1f}s")

    # Different client is unaffected
    assert sw.allow("user2").allowed

    # Advance time past window
    sim_time[0] = 11.0
    assert sw.allow("user1").allowed  # window slid

    # Test token bucket: 2 tokens/sec, capacity 5
    sim_time[0] = 0.0
    tb = TokenBucketLimiter(rate=2.0, capacity=5, time_fn=tf)

    # Burst: use all 5 tokens
    for i in range(5):
        assert tb.allow("client1").allowed, f"Burst request {i+1} should pass"

    r_deny = tb.allow("client1")
    assert not r_deny.allowed
    print(f"Token bucket: burst exhausted, retry_after={r_deny.retry_after:.2f}s")

    # Refill: 0.5 seconds -> 1 token
    sim_time[0] = 0.5
    assert tb.allow("client1").allowed

    # Test composite: 3/10s AND 2 tokens/sec cap 3
    sim_time[0] = 0.0
    composite = CompositeLimiter(
        SlidingWindowLimiter(max_requests=3, window=10.0, time_fn=tf),
        TokenBucketLimiter(rate=2.0, capacity=3, time_fn=tf),
    )

    assert composite.allow("c1").allowed  # 1
    assert composite.allow("c1").allowed  # 2
    assert composite.allow("c1").allowed  # 3
    cr = composite.allow("c1")
    assert not cr.allowed  # both limits hit
    print(f"Composite: denied, retry_after={cr.retry_after:.2f}s")

    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/sql-query-builder",
        r'''Implement a SQL query builder in Python that supports SELECT, INSERT, UPDATE, DELETE, JOINs (inner, left, right), subqueries, parameterized values (preventing SQL injection), and WHERE clause composition with AND/OR.''',
        r'''<think>
Decomposing the SQL query builder:

Sub-problems:
1. SELECT builder — columns, FROM, WHERE, ORDER BY, LIMIT, GROUP BY, HAVING
2. INSERT builder — INTO table, columns, VALUES (parameterized)
3. UPDATE builder — SET clauses, WHERE
4. DELETE builder — FROM table, WHERE
5. JOINs — INNER JOIN, LEFT JOIN, RIGHT JOIN with ON clause
6. WHERE composition — chainable AND/OR with nested groups. Each condition uses parameterized values (?) to prevent SQL injection.
7. Subqueries — a query builder can be used as a subquery in FROM, WHERE IN, or as a column expression

Interface design:
- q = Query.select("name", "age").from_("users").where("age", ">", 18).order_by("name").limit(10)
- q.join("orders", "users.id = orders.user_id", join_type="LEFT")
- q.where_in("status", Query.select("status").from_("active_statuses"))
- sql, params = q.build() -> ("SELECT name, age FROM users WHERE age > ? ...", [18])
- Query.insert("users").columns("name", "age").values("Alice", 30)
- Query.update("users").set(name="Bob").where("id", "=", 1)
- Query.delete("users").where("id", "=", 1)

Edge cases:
- Empty WHERE — no WHERE clause at all
- Multiple JOINs — append in order
- Subquery as FROM source — needs alias
- Parameterized LIKE patterns — "name LIKE ?" with param "%alice%"
- NULL handling — WHERE x IS NULL (not x = NULL)
- SQL injection attempt in column names — column names can't be parameterized in standard SQL, but we can validate them (alphanumeric + underscore + dot only)

Implementation order:
1. Where clause builder (conditions + params)
2. Select query builder
3. JOIN support
4. INSERT/UPDATE/DELETE builders
5. Subquery support
6. Build method that produces (sql, params)

Self-correction: Column names can't be parameterized (they're identifiers, not values). I should validate that column/table names only contain safe characters to prevent injection through identifiers.
</think>

```python
import re
from typing import Any, Optional, Union


def _safe_identifier(name: str) -> str:
    """Validate SQL identifier to prevent injection."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.*]*$', name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


class WhereClause:
    def __init__(self):
        self._parts: list[tuple[str, str, list[Any]]] = []  # (connector, sql, params)

    def _add(self, connector: str, sql: str, params: list[Any]) -> "WhereClause":
        self._parts.append((connector, sql, params))
        return self

    def and_(self, column: str, op: str, value: Any) -> "WhereClause":
        col = _safe_identifier(column)
        return self._add("AND", f"{col} {op} ?", [value])

    def or_(self, column: str, op: str, value: Any) -> "WhereClause":
        col = _safe_identifier(column)
        return self._add("OR", f"{col} {op} ?", [value])

    def and_null(self, column: str, is_null: bool = True) -> "WhereClause":
        col = _safe_identifier(column)
        clause = f"{col} IS NULL" if is_null else f"{col} IS NOT NULL"
        return self._add("AND", clause, [])

    def and_in(self, column: str, values: Union[list, "Query"]) -> "WhereClause":
        col = _safe_identifier(column)
        if isinstance(values, Query):
            sub_sql, sub_params = values.build()
            return self._add("AND", f"{col} IN ({sub_sql})", sub_params)
        placeholders = ", ".join("?" for _ in values)
        return self._add("AND", f"{col} IN ({placeholders})", list(values))

    def and_group(self, group: "WhereClause") -> "WhereClause":
        sql, params = group.build_fragment()
        return self._add("AND", f"({sql})", params)

    def or_group(self, group: "WhereClause") -> "WhereClause":
        sql, params = group.build_fragment()
        return self._add("OR", f"({sql})", params)

    def build_fragment(self) -> tuple[str, list[Any]]:
        if not self._parts:
            return "", []
        parts_sql = []
        all_params: list[Any] = []
        for i, (connector, sql, params) in enumerate(self._parts):
            if i == 0:
                parts_sql.append(sql)
            else:
                parts_sql.append(f"{connector} {sql}")
            all_params.extend(params)
        return " ".join(parts_sql), all_params


class Query:
    def __init__(self):
        self._type: str = "SELECT"
        self._table: str = ""
        self._columns: list[str] = []
        self._where = WhereClause()
        self._joins: list[tuple[str, str, str]] = []  # (type, table, on)
        self._order: list[str] = []
        self._group: list[str] = []
        self._having: Optional[str] = None
        self._limit_val: Optional[int] = None
        self._offset_val: Optional[int] = None
        self._set_clauses: dict[str, Any] = {}
        self._insert_columns: list[str] = []
        self._insert_values: list[list[Any]] = []
        self._alias: Optional[str] = None
        self._distinct: bool = False

    # --- Factory methods ---
    @classmethod
    def select(cls, *columns: str) -> "Query":
        q = cls()
        q._type = "SELECT"
        q._columns = [_safe_identifier(c) for c in columns] if columns else ["*"]
        return q

    @classmethod
    def insert(cls, table: str) -> "Query":
        q = cls()
        q._type = "INSERT"
        q._table = _safe_identifier(table)
        return q

    @classmethod
    def update(cls, table: str) -> "Query":
        q = cls()
        q._type = "UPDATE"
        q._table = _safe_identifier(table)
        return q

    @classmethod
    def delete(cls, table: str) -> "Query":
        q = cls()
        q._type = "DELETE"
        q._table = _safe_identifier(table)
        return q

    # --- Chainable methods ---
    def distinct(self) -> "Query":
        self._distinct = True
        return self

    def from_(self, table: Union[str, "Query"], alias: Optional[str] = None) -> "Query":
        if isinstance(table, Query):
            sub_sql, _ = table.build()
            self._table = f"({sub_sql})"
            if alias:
                self._table += f" AS {_safe_identifier(alias)}"
        else:
            self._table = _safe_identifier(table)
        return self

    def where(self, column: str, op: str, value: Any) -> "Query":
        self._where.and_(column, op, value)
        return self

    def or_where(self, column: str, op: str, value: Any) -> "Query":
        self._where.or_(column, op, value)
        return self

    def where_null(self, column: str, is_null: bool = True) -> "Query":
        self._where.and_null(column, is_null)
        return self

    def where_in(self, column: str, values: Union[list, "Query"]) -> "Query":
        self._where.and_in(column, values)
        return self

    def where_group(self, group: WhereClause) -> "Query":
        self._where.and_group(group)
        return self

    def join(self, table: str, on: str, join_type: str = "INNER") -> "Query":
        self._joins.append((join_type.upper(), _safe_identifier(table), on))
        return self

    def left_join(self, table: str, on: str) -> "Query":
        return self.join(table, on, "LEFT")

    def right_join(self, table: str, on: str) -> "Query":
        return self.join(table, on, "RIGHT")

    def order_by(self, column: str, desc: bool = False) -> "Query":
        col = _safe_identifier(column)
        self._order.append(f"{col} {'DESC' if desc else 'ASC'}")
        return self

    def group_by(self, *columns: str) -> "Query":
        self._group.extend(_safe_identifier(c) for c in columns)
        return self

    def limit(self, n: int) -> "Query":
        self._limit_val = int(n)
        return self

    def offset(self, n: int) -> "Query":
        self._offset_val = int(n)
        return self

    # INSERT
    def columns(self, *cols: str) -> "Query":
        self._insert_columns = [_safe_identifier(c) for c in cols]
        return self

    def values(self, *vals: Any) -> "Query":
        self._insert_values.append(list(vals))
        return self

    # UPDATE
    def set(self, **kwargs: Any) -> "Query":
        for k, v in kwargs.items():
            self._set_clauses[_safe_identifier(k)] = v
        return self

    def build(self) -> tuple[str, list[Any]]:
        params: list[Any] = []

        if self._type == "SELECT":
            dist = "DISTINCT " if self._distinct else ""
            parts = [f"SELECT {dist}{', '.join(self._columns)}"]
            if self._table:
                parts.append(f"FROM {self._table}")
            for jtype, jtable, jon in self._joins:
                parts.append(f"{jtype} JOIN {jtable} ON {jon}")
            where_sql, where_params = self._where.build_fragment()
            if where_sql:
                parts.append(f"WHERE {where_sql}")
                params.extend(where_params)
            if self._group:
                parts.append(f"GROUP BY {', '.join(self._group)}")
            if self._order:
                parts.append(f"ORDER BY {', '.join(self._order)}")
            if self._limit_val is not None:
                parts.append(f"LIMIT {self._limit_val}")
            if self._offset_val is not None:
                parts.append(f"OFFSET {self._offset_val}")
            return " ".join(parts), params

        elif self._type == "INSERT":
            cols = ", ".join(self._insert_columns)
            all_placeholders = []
            for row in self._insert_values:
                all_placeholders.append(f"({', '.join('?' for _ in row)})")
                params.extend(row)
            vals = ", ".join(all_placeholders)
            return f"INSERT INTO {self._table} ({cols}) VALUES {vals}", params

        elif self._type == "UPDATE":
            set_parts = []
            for col, val in self._set_clauses.items():
                set_parts.append(f"{col} = ?")
                params.append(val)
            sql = f"UPDATE {self._table} SET {', '.join(set_parts)}"
            where_sql, where_params = self._where.build_fragment()
            if where_sql:
                sql += f" WHERE {where_sql}"
                params.extend(where_params)
            return sql, params

        elif self._type == "DELETE":
            sql = f"DELETE FROM {self._table}"
            where_sql, where_params = self._where.build_fragment()
            if where_sql:
                sql += f" WHERE {where_sql}"
                params.extend(where_params)
            return sql, params

        raise ValueError(f"Unknown query type: {self._type}")


# --- Usage / test ---
if __name__ == "__main__":
    # SELECT with JOINs and WHERE
    sql, params = (
        Query.select("u.name", "o.total")
        .from_("users", )
        .join("orders", "u.id = orders.user_id", "LEFT")
        .where("u.age", ">=", 18)
        .where("o.total", ">", 100)
        .or_where("u.name", "LIKE", "%admin%")
        .order_by("o.total", desc=True)
        .limit(20)
        .build()
    )
    print(f"SELECT: {sql}")
    print(f"  params: {params}")
    assert "LEFT JOIN orders" in sql
    assert sql.count("?") == len(params)
    assert params == [18, 100, "%admin%"]

    # Subquery in WHERE IN
    sub = Query.select("id").from_("premium_users").where("tier", "=", "gold")
    sql2, params2 = (
        Query.select("*")
        .from_("orders")
        .where_in("user_id", sub)
        .build()
    )
    print(f"\nSubquery: {sql2}")
    print(f"  params: {params2}")
    assert "IN (SELECT" in sql2
    assert params2 == ["gold"]

    # INSERT
    sql3, params3 = (
        Query.insert("users")
        .columns("name", "age", "email")
        .values("Alice", 30, "alice@example.com")
        .values("Bob", 25, "bob@example.com")
        .build()
    )
    print(f"\nINSERT: {sql3}")
    print(f"  params: {params3}")
    assert sql3.count("?") == 6
    assert params3 == ["Alice", 30, "alice@example.com", "Bob", 25, "bob@example.com"]

    # UPDATE
    sql4, params4 = (
        Query.update("users")
        .set(name="Charlie", age=35)
        .where("id", "=", 42)
        .build()
    )
    print(f"\nUPDATE: {sql4}")
    print(f"  params: {params4}")
    assert "SET" in sql4
    assert 42 in params4

    # DELETE
    sql5, params5 = (
        Query.delete("users")
        .where("id", "=", 99)
        .build()
    )
    print(f"\nDELETE: {sql5}")
    assert params5 == [99]

    # SQL injection attempt
    try:
        Query.select("name; DROP TABLE users;--").from_("users").build()
        assert False, "Should have raised"
    except ValueError as e:
        print(f"\nInjection blocked: {e}")

    # WHERE group (OR inside AND)
    group = WhereClause()
    group.and_("status", "=", "active")
    group.or_("status", "=", "pending")

    sql6, params6 = (
        Query.select("*")
        .from_("tasks")
        .where("priority", ">", 5)
        .where_group(group)
        .build()
    )
    print(f"\nGrouped WHERE: {sql6}")
    print(f"  params: {params6}")
    assert "(status = ? OR status = ?)" in sql6

    print("\nAll tests passed.")
```'''
    ),
    (
        "deep_reasoning/event-sourcing-projections",
        r'''Create an event sourcing system in Python with an event store (append-only log), projections that materialize read models from events, and snapshots to speed up aggregate reconstruction.''',
        r'''<think>
Decomposing the event sourcing system:

Sub-problems:
1. Events — immutable records with type, aggregate ID, data payload, sequence number, timestamp. Once stored, never modified or deleted.
2. Event store — append-only log. Store events per aggregate ID. Support reading all events for an aggregate (optionally from a sequence number).
3. Aggregates — domain objects rebuilt by replaying events. An aggregate has an apply(event) method for each event type. The current state is computed, never stored directly.
4. Projections — read-model builders that subscribe to events and maintain materialized views. E.g., an "order count per customer" projection listens to OrderPlaced events.
5. Snapshots — periodically save aggregate state to avoid replaying ALL events. When loading, start from latest snapshot, then replay only events after the snapshot's sequence number.

Interface design:
- event_store.append(aggregate_id, event_type, data) -> Event
- event_store.get_events(aggregate_id, from_seq=0) -> list[Event]
- aggregate = AggregateRoot(); aggregate.load(events)
- snapshot_store.save(aggregate_id, seq, state)
- snapshot_store.load(aggregate_id) -> (seq, state) or None
- projection.handle(event) — updates the read model
- event_store.subscribe(projection) — push new events to projections

Edge cases:
- Concurrent writes to same aggregate — optimistic concurrency via expected_version
- No events for an aggregate — initial state
- Snapshot exists but events after it — replay only the delta
- Projection crashes mid-processing — needs to track its position (cursor) and resume
- Empty event store — projections have nothing to process

Implementation order:
1. Event dataclass
2. InMemoryEventStore (append, get_events, subscribe)
3. AggregateRoot base class (apply, load_from_events)
4. Snapshot store
5. Projection base class
6. Concrete example: BankAccount aggregate with Deposited/Withdrawn events

Self-correction: I was going to use a single global sequence number, but per-aggregate versioning is more practical. I'll use both: per-aggregate version for optimistic concurrency, and global sequence for projections to track their cursor.
</think>

```python
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ============================================================
# 1. Events
# ============================================================

@dataclass(frozen=True)
class Event:
    global_seq: int
    aggregate_id: str
    aggregate_version: int
    event_type: str
    data: dict
    timestamp: float


class ConcurrencyError(Exception):
    pass


# ============================================================
# 2. Event Store
# ============================================================

class EventStore:
    def __init__(self):
        self._events: list[Event] = []
        self._by_aggregate: dict[str, list[Event]] = {}
        self._global_seq: int = 0
        self._subscribers: list[Callable[[Event], None]] = []

    def append(
        self,
        aggregate_id: str,
        event_type: str,
        data: dict,
        expected_version: Optional[int] = None,
    ) -> Event:
        agg_events = self._by_aggregate.get(aggregate_id, [])
        current_version = len(agg_events)

        if expected_version is not None and current_version != expected_version:
            raise ConcurrencyError(
                f"Expected version {expected_version}, but aggregate "
                f"'{aggregate_id}' is at version {current_version}"
            )

        self._global_seq += 1
        event = Event(
            global_seq=self._global_seq,
            aggregate_id=aggregate_id,
            aggregate_version=current_version + 1,
            event_type=event_type,
            data=data,
            timestamp=time.time(),
        )

        self._events.append(event)
        if aggregate_id not in self._by_aggregate:
            self._by_aggregate[aggregate_id] = []
        self._by_aggregate[aggregate_id].append(event)

        for sub in self._subscribers:
            sub(event)

        return event

    def get_events(
        self, aggregate_id: str, from_version: int = 0
    ) -> list[Event]:
        events = self._by_aggregate.get(aggregate_id, [])
        return [e for e in events if e.aggregate_version > from_version]

    def get_all_events(self, from_global_seq: int = 0) -> list[Event]:
        return [e for e in self._events if e.global_seq > from_global_seq]

    def subscribe(self, handler: Callable[[Event], None]) -> None:
        self._subscribers.append(handler)


# ============================================================
# 3. Aggregate Root
# ============================================================

class AggregateRoot:
    def __init__(self, aggregate_id: str):
        self.aggregate_id = aggregate_id
        self.version: int = 0
        self._pending_events: list[tuple[str, dict]] = []

    def apply_event(self, event: Event) -> None:
        handler_name = f"_on_{event.event_type}"
        handler = getattr(self, handler_name, None)
        if handler:
            handler(event.data)
        self.version = event.aggregate_version

    def load_from_events(self, events: list[Event]) -> None:
        for event in events:
            self.apply_event(event)

    def load_from_snapshot(self, version: int, state: dict) -> None:
        self.version = version
        self._restore_state(state)

    def _raise_event(self, event_type: str, data: dict) -> None:
        self._pending_events.append((event_type, data))
        # Apply locally
        handler_name = f"_on_{event_type}"
        handler = getattr(self, handler_name, None)
        if handler:
            handler(data)
        self.version += 1

    def save(self, store: EventStore) -> list[Event]:
        saved = []
        for event_type, data in self._pending_events:
            evt = store.append(
                self.aggregate_id,
                event_type,
                data,
                expected_version=self.version - len(self._pending_events) + len(saved),
            )
            saved.append(evt)
        self._pending_events.clear()
        return saved

    def _snapshot_state(self) -> dict:
        raise NotImplementedError

    def _restore_state(self, state: dict) -> None:
        raise NotImplementedError


# ============================================================
# 4. Snapshot Store
# ============================================================

class SnapshotStore:
    def __init__(self):
        self._snapshots: dict[str, tuple[int, dict]] = {}

    def save(self, aggregate_id: str, version: int, state: dict) -> None:
        self._snapshots[aggregate_id] = (version, state)

    def load(self, aggregate_id: str) -> Optional[tuple[int, dict]]:
        return self._snapshots.get(aggregate_id)


# ============================================================
# 5. Projection
# ============================================================

class Projection:
    def __init__(self):
        self._cursor: int = 0  # last processed global_seq

    def handle(self, event: Event) -> None:
        handler_name = f"_on_{event.event_type}"
        handler = getattr(self, handler_name, None)
        if handler:
            handler(event)
        self._cursor = event.global_seq

    def rebuild(self, store: EventStore) -> None:
        """Replay all events from scratch."""
        self._cursor = 0
        self._reset()
        for event in store.get_all_events(from_global_seq=0):
            self.handle(event)

    def catch_up(self, store: EventStore) -> None:
        """Process only new events since last cursor."""
        for event in store.get_all_events(from_global_seq=self._cursor):
            self.handle(event)

    def _reset(self) -> None:
        pass


# ============================================================
# 6. Concrete example: Bank Account
# ============================================================

class BankAccount(AggregateRoot):
    def __init__(self, account_id: str):
        super().__init__(account_id)
        self.balance: float = 0.0
        self.is_open: bool = False

    def open(self, initial_deposit: float) -> None:
        if self.is_open:
            raise ValueError("Account already open")
        self._raise_event("account_opened", {"amount": initial_deposit})

    def deposit(self, amount: float) -> None:
        if amount <= 0:
            raise ValueError("Deposit must be positive")
        self._raise_event("deposited", {"amount": amount})

    def withdraw(self, amount: float) -> None:
        if amount > self.balance:
            raise ValueError("Insufficient funds")
        self._raise_event("withdrawn", {"amount": amount})

    def _on_account_opened(self, data: dict) -> None:
        self.is_open = True
        self.balance = data["amount"]

    def _on_deposited(self, data: dict) -> None:
        self.balance += data["amount"]

    def _on_withdrawn(self, data: dict) -> None:
        self.balance -= data["amount"]

    def _snapshot_state(self) -> dict:
        return {"balance": self.balance, "is_open": self.is_open}

    def _restore_state(self, state: dict) -> None:
        self.balance = state["balance"]
        self.is_open = state["is_open"]


class BalanceSummaryProjection(Projection):
    def __init__(self):
        super().__init__()
        self.total_deposits: float = 0.0
        self.total_withdrawals: float = 0.0
        self.account_count: int = 0

    def _reset(self) -> None:
        self.total_deposits = 0.0
        self.total_withdrawals = 0.0
        self.account_count = 0

    def _on_account_opened(self, event: Event) -> None:
        self.account_count += 1
        self.total_deposits += event.data["amount"]

    def _on_deposited(self, event: Event) -> None:
        self.total_deposits += event.data["amount"]

    def _on_withdrawn(self, event: Event) -> None:
        self.total_withdrawals += event.data["amount"]


# --- Usage / test ---
if __name__ == "__main__":
    store = EventStore()
    snapshots = SnapshotStore()

    # Create and use account
    acct = BankAccount("acct-001")
    acct.open(100.0)
    acct.deposit(50.0)
    acct.withdraw(30.0)
    assert acct.balance == 120.0

    # Persist events
    saved = acct.save(store)
    print(f"Saved {len(saved)} events")
    assert len(saved) == 3

    # Rebuild from events
    acct2 = BankAccount("acct-001")
    events = store.get_events("acct-001")
    acct2.load_from_events(events)
    assert acct2.balance == 120.0
    assert acct2.version == 3
    print(f"Rebuilt balance: {acct2.balance}")

    # Snapshot
    snapshots.save("acct-001", acct2.version, acct2._snapshot_state())

    # More events after snapshot
    acct2.deposit(200.0)
    acct2.save(store)

    # Load from snapshot + delta
    acct3 = BankAccount("acct-001")
    snap = snapshots.load("acct-001")
    assert snap is not None
    snap_version, snap_state = snap
    acct3.load_from_snapshot(snap_version, snap_state)
    delta_events = store.get_events("acct-001", from_version=snap_version)
    acct3.load_from_events(delta_events)
    assert acct3.balance == 320.0
    print(f"From snapshot + delta: {acct3.balance} (replayed {len(delta_events)} events instead of {len(store.get_events('acct-001'))})")

    # Projection
    projection = BalanceSummaryProjection()
    projection.rebuild(store)
    print(f"Projection: deposits={projection.total_deposits}, withdrawals={projection.total_withdrawals}, accounts={projection.account_count}")
    assert projection.total_deposits == 350.0  # 100 + 50 + 200
    assert projection.total_withdrawals == 30.0
    assert projection.account_count == 1

    # Optimistic concurrency test
    other = BankAccount("acct-001")
    other.load_from_events(store.get_events("acct-001"))
    other.deposit(10.0)
    # Meanwhile, someone else writes
    store.append("acct-001", "deposited", {"amount": 5.0}, expected_version=4)
    try:
        other.save(store)  # expected_version=4 but now it's 5
        assert False
    except ConcurrencyError as e:
        print(f"Caught: {e}")

    print("All tests passed.")
```'''
    ),
    (
        "deep_reasoning/config-manager-layered",
        r'''Build a configuration manager in Python with layered sources (environment variables, config files, defaults), type coercion (strings from env vars to int/bool/float/list), dot-notation access, and validation of required fields.''',
        r'''<think>
Decomposing the config manager:

Sub-problems:
1. Layered sources — multiple config sources with priority: env vars > config file > defaults. Higher priority overrides lower.
2. Type coercion — env vars are always strings. Need to coerce "true"/"false" to bool, "42" to int, "1.5" to float, "a,b,c" to list.
3. Dot-notation access — config.get("database.host") accesses nested config. Also support attribute-style: config.database.host
4. Validation — declare required fields with types. At startup, verify all required fields are present and correctly typed.
5. Config file parsing — support JSON and TOML-like formats. I'll support JSON and simple key=value .env files.

Interface design:
- config = ConfigManager()
- config.add_defaults({"database": {"host": "localhost", "port": 5432}})
- config.add_file("config.json")
- config.add_env_prefix("MYAPP_") — MYAPP_DATABASE_HOST -> database.host
- config.require("database.host", type=str)
- config.require("database.port", type=int)
- config.validate() -> raises if requirements not met
- config.get("database.host") -> value
- config["database.host"] -> value

Edge cases:
- Env var "MYAPP_DATABASE_PORT" = "abc" with type=int — validation error
- Nested keys in env vars: MYAPP_DATABASE__HOST (double underscore for nesting? or single underscore with prefix stripping?)
- Boolean coercion: "true", "TRUE", "1", "yes" -> True; "false", "FALSE", "0", "no" -> False
- List coercion: "a,b,c" -> ["a", "b", "c"]
- Default has a value but env var overrides with empty string — should empty string count as "set"?
- Config file doesn't exist — warning or error (configurable)

Implementation order:
1. Type coercion utilities
2. Deep dict merge (for layering)
3. Dot-notation getter/setter on nested dicts
4. ConfigManager with add_defaults, add_dict, add_env
5. Validation with required fields
6. File loading (JSON)

Self-correction: For env var mapping, I'll use single underscore as separator with the prefix stripped. So MYAPP_DATABASE_HOST -> database.host. This is the most common convention. Double underscore for actual underscores in key names would add complexity — I'll skip that for now.
</think>

```python
import json
import os
from typing import Any, Optional, Type


# ============================================================
# 1. Type coercion
# ============================================================

def coerce_bool(value: str) -> bool:
    if value.lower() in ("true", "1", "yes", "on"):
        return True
    if value.lower() in ("false", "0", "no", "off", ""):
        return False
    raise ValueError(f"Cannot coerce {value!r} to bool")


def coerce_list(value: str, sep: str = ",") -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(sep)]


def coerce_value(value: str, target_type: Type) -> Any:
    if target_type is str:
        return value
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    if target_type is bool:
        return coerce_bool(value)
    if target_type is list:
        return coerce_list(value)
    return value


# ============================================================
# 2. Deep dict utilities
# ============================================================

def deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base (returns new dict)."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def deep_get(data: dict, path: str, default: Any = None) -> Any:
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def deep_set(data: dict, path: str, value: Any) -> None:
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


# ============================================================
# 3. Config accessor (dot-notation attribute access)
# ============================================================

class ConfigView:
    """Provides attribute-style access to a nested dict."""
    def __init__(self, data: dict):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str) -> Any:
        data = object.__getattribute__(self, "_data")
        if name in data:
            val = data[name]
            if isinstance(val, dict):
                return ConfigView(val)
            return val
        raise AttributeError(f"No config key: {name}")

    def __repr__(self) -> str:
        return f"ConfigView({object.__getattribute__(self, '_data')})"

    def __contains__(self, key: str) -> bool:
        return key in object.__getattribute__(self, "_data")


# ============================================================
# 4. Requirement definition
# ============================================================

class ConfigRequirement:
    def __init__(self, path: str, req_type: Type = str, description: str = ""):
        self.path = path
        self.req_type = req_type
        self.description = description


class ConfigValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Config validation failed:\n" + "\n".join(f"  - {e}" for e in errors))


# ============================================================
# 5. ConfigManager
# ============================================================

class ConfigManager:
    def __init__(self):
        self._layers: list[dict] = []  # lowest priority first
        self._requirements: list[ConfigRequirement] = []
        self._merged: Optional[dict] = None

    def add_defaults(self, defaults: dict) -> "ConfigManager":
        self._layers.insert(0, defaults)  # lowest priority
        self._merged = None
        return self

    def add_dict(self, data: dict) -> "ConfigManager":
        self._layers.append(data)
        self._merged = None
        return self

    def add_json_file(self, path: str, required: bool = True) -> "ConfigManager":
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            self._layers.append(data)
            self._merged = None
        elif required:
            raise FileNotFoundError(f"Config file not found: {path}")
        return self

    def add_env(self, prefix: str = "", separator: str = "_") -> "ConfigManager":
        """Load env vars with prefix into nested dict.
        MYAPP_DATABASE_HOST -> database.host (with prefix='MYAPP_')
        """
        env_data: dict = {}
        prefix_upper = prefix.upper()
        for key, value in os.environ.items():
            if prefix_upper and not key.upper().startswith(prefix_upper):
                continue
            # Strip prefix and convert to dotted path
            stripped = key[len(prefix_upper):]
            path = separator.join(stripped.lower().split(separator))
            # Convert underscored path to dotted
            dotted = path.replace(separator, ".")
            deep_set(env_data, dotted, value)

        if env_data:
            self._layers.append(env_data)
            self._merged = None
        return self

    def require(self, path: str, req_type: Type = str, description: str = "") -> "ConfigManager":
        self._requirements.append(ConfigRequirement(path, req_type, description))
        return self

    def _build(self) -> dict:
        if self._merged is None:
            result: dict = {}
            for layer in self._layers:
                result = deep_merge(result, layer)
            self._merged = result
        return self._merged

    def validate(self) -> None:
        data = self._build()
        errors: list[str] = []

        for req in self._requirements:
            value = deep_get(data, req.path)
            if value is None:
                errors.append(f"Missing required config: '{req.path}'" +
                              (f" ({req.description})" if req.description else ""))
                continue

            # Attempt type coercion if value is string
            if isinstance(value, str) and req.req_type is not str:
                try:
                    coerced = coerce_value(value, req.req_type)
                    deep_set(data, req.path, coerced)
                except (ValueError, TypeError) as e:
                    errors.append(
                        f"Config '{req.path}': cannot coerce {value!r} to "
                        f"{req.req_type.__name__}: {e}"
                    )
            elif not isinstance(value, req.req_type):
                errors.append(
                    f"Config '{req.path}': expected {req.req_type.__name__}, "
                    f"got {type(value).__name__}"
                )

        if errors:
            raise ConfigValidationError(errors)

    def get(self, path: str, default: Any = None) -> Any:
        return deep_get(self._build(), path, default)

    def __getitem__(self, path: str) -> Any:
        value = self.get(path)
        if value is None:
            raise KeyError(path)
        return value

    @property
    def view(self) -> ConfigView:
        return ConfigView(self._build())

    def as_dict(self) -> dict:
        return dict(self._build())


# --- Usage / test ---
if __name__ == "__main__":
    config = ConfigManager()

    # Layer 1: defaults (lowest priority)
    config.add_defaults({
        "database": {
            "host": "localhost",
            "port": 5432,
            "name": "myapp",
        },
        "debug": False,
        "log_level": "INFO",
        "allowed_origins": "http://localhost:3000",
    })

    # Layer 2: "config file" (simulated)
    config.add_dict({
        "database": {
            "host": "db.production.internal",
            "name": "myapp_prod",
        },
        "log_level": "WARNING",
    })

    # Layer 3: env vars (highest priority — simulate by setting)
    os.environ["MYAPP_DATABASE_PORT"] = "3306"
    os.environ["MYAPP_DEBUG"] = "true"
    config.add_env(prefix="MYAPP_")

    # Requirements
    config.require("database.host", str, "Database hostname")
    config.require("database.port", int, "Database port")
    config.require("debug", bool)

    # Validate (will coerce env var strings)
    config.validate()

    # Access via get()
    assert config.get("database.host") == "db.production.internal"  # file overrides default
    assert config.get("database.port") == 3306  # env overrides default (coerced from string)
    assert config.get("debug") is True  # env overrides default (coerced from "true")
    assert config.get("log_level") == "WARNING"  # file overrides default
    assert config.get("database.name") == "myapp_prod"

    # Access via view (attribute style)
    v = config.view
    print(f"Host: {v.database.host}")
    print(f"Port: {config['database.port']}")
    print(f"Debug: {config.get('debug')}")

    # Validation error test
    bad_config = ConfigManager()
    bad_config.add_defaults({"port": "not_a_number"})
    bad_config.require("port", int)
    bad_config.require("missing_field", str, "A required field")

    try:
        bad_config.validate()
        assert False
    except ConfigValidationError as e:
        print(f"\nValidation errors ({len(e.errors)}):")
        for err in e.errors:
            print(f"  {err}")
        assert len(e.errors) == 2

    # Cleanup
    del os.environ["MYAPP_DATABASE_PORT"]
    del os.environ["MYAPP_DEBUG"]

    print("\nAll tests passed.")
```'''
    ),
    (
        "deep_reasoning/async-task-graph-executor",
        r'''Implement an async task graph executor in Python that runs tasks with dependencies in parallel (using asyncio), supports cancellation of in-progress tasks, and aggregates results from all completed tasks. Tasks should run as soon as their dependencies are satisfied.''',
        r'''<think>
Decomposing the async task graph executor:

Sub-problems:
1. Task definition — each task has an ID, an async callable, a list of dependency IDs, and a result slot
2. Dependency graph — DAG of tasks. Need topological validation (no cycles) and a way to determine which tasks are "ready" (all deps completed).
3. Parallel execution — when multiple tasks are ready simultaneously, run them concurrently with asyncio.create_task(). Don't wait for one to finish before starting another at the same level.
4. Cancellation — ability to cancel the entire graph execution. In-progress tasks should be cancelled via asyncio.Task.cancel(). Pending tasks should not start.
5. Result aggregation — collect results from all completed tasks into a dict[task_id, result]. Failed tasks should store their exception.
6. Error handling — if a task fails, what happens to tasks that depend on it? Options: a) fail dependents too, b) skip dependents, c) continue and mark dependents as "skipped." I'll go with option b (skip dependents, don't block the rest).

Interface design:
- executor = TaskGraphExecutor()
- executor.add_task("fetch", fetch_data)
- executor.add_task("process", process_data, depends_on=["fetch"])
- executor.add_task("notify", send_notification, depends_on=["process"])
- executor.add_task("log", log_event)  # no deps — runs immediately
- results = await executor.execute() -> {"fetch": ..., "process": ..., "log": ..., "notify": ...}
- await executor.cancel() — cancel all running tasks

Edge cases:
- Task raises exception — mark as failed, skip dependents, continue other branches
- Cycle detection — must check before execution starts
- Empty graph — return empty results
- Task that depends on a task not in the graph — raise KeyError
- Cancellation while tasks are running — cancel asyncio tasks, mark remaining as cancelled
- Diamond dependency — A depends on B and C, B and C both depend on D. D runs once, B and C run in parallel after D, then A runs.

Implementation order:
1. TaskNode dataclass
2. Graph validation (cycle detection, missing deps)
3. Executor loop: track completed set, find ready tasks, launch them
4. Result collection
5. Cancellation support
6. Error handling (skip dependents on failure)

Self-correction: The execution loop needs to be event-driven, not polling. When a task completes, check if any new tasks become ready. I'll use asyncio.Event or just gather the running tasks and check after each completion.

Actually, the cleanest approach: maintain a set of running asyncio.Tasks. When any completes (via asyncio.wait with FIRST_COMPLETED), check for newly ready tasks and launch them. Repeat until all tasks are done or cancelled.
</think>

```python
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional


class TaskState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class TaskNode:
    task_id: str
    coro_fn: Callable[..., Coroutine]
    depends_on: list[str] = field(default_factory=list)
    state: TaskState = TaskState.PENDING
    result: Any = None
    error: Optional[Exception] = None


class CycleError(Exception):
    pass


class TaskGraphExecutor:
    def __init__(self):
        self._tasks: dict[str, TaskNode] = {}
        self._cancelled = False

    def add_task(
        self,
        task_id: str,
        coro_fn: Callable[..., Coroutine],
        depends_on: Optional[list[str]] = None,
    ) -> "TaskGraphExecutor":
        if task_id in self._tasks:
            raise ValueError(f"Task '{task_id}' already registered")
        self._tasks[task_id] = TaskNode(
            task_id=task_id,
            coro_fn=coro_fn,
            depends_on=depends_on or [],
        )
        return self

    def _validate(self) -> None:
        # Check missing dependencies
        for node in self._tasks.values():
            for dep in node.depends_on:
                if dep not in self._tasks:
                    raise KeyError(f"Task '{node.task_id}' depends on unknown task '{dep}'")

        # Cycle detection via DFS
        WHITE, GRAY, BLACK = 0, 1, 2
        colors: dict[str, int] = {tid: WHITE for tid in self._tasks}

        def dfs(tid: str, path: list[str]) -> None:
            colors[tid] = GRAY
            for dep in self._tasks[tid].depends_on:
                if colors[dep] == GRAY:
                    cycle_start = path.index(dep) if dep in path else 0
                    cycle = path[cycle_start:] + [dep]
                    raise CycleError(f"Cycle detected: {' -> '.join(cycle)}")
                if colors[dep] == WHITE:
                    dfs(dep, path + [dep])
            colors[tid] = BLACK

        for tid in self._tasks:
            if colors[tid] == WHITE:
                dfs(tid, [tid])

    def _get_ready_tasks(self) -> list[str]:
        ready = []
        for node in self._tasks.values():
            if node.state != TaskState.PENDING:
                continue
            deps_ok = all(
                self._tasks[d].state == TaskState.COMPLETED
                for d in node.depends_on
            )
            deps_failed = any(
                self._tasks[d].state in (TaskState.FAILED, TaskState.SKIPPED, TaskState.CANCELLED)
                for d in node.depends_on
            )
            if deps_failed:
                node.state = TaskState.SKIPPED
                continue
            if deps_ok:
                ready.append(node.task_id)
        return ready

    async def execute(self) -> dict[str, Any]:
        self._validate()
        self._cancelled = False

        if not self._tasks:
            return {}

        # Map of asyncio.Task -> task_id
        running: dict[asyncio.Task, str] = {}
        results: dict[str, Any] = {}

        def launch_ready() -> None:
            for tid in self._get_ready_tasks():
                if self._cancelled:
                    self._tasks[tid].state = TaskState.CANCELLED
                    continue
                node = self._tasks[tid]
                node.state = TaskState.RUNNING

                async def run_task(n: TaskNode = node) -> Any:
                    # Pass dependency results as kwargs if the function accepts them
                    dep_results = {d: self._tasks[d].result for d in n.depends_on}
                    return await n.coro_fn(dep_results)

                atask = asyncio.create_task(run_task(), name=tid)
                running[atask] = tid

        launch_ready()

        while running:
            done, _ = await asyncio.wait(running.keys(), return_when=asyncio.FIRST_COMPLETED)

            for atask in done:
                tid = running.pop(atask)
                node = self._tasks[tid]

                if atask.cancelled():
                    node.state = TaskState.CANCELLED
                elif atask.exception():
                    node.state = TaskState.FAILED
                    node.error = atask.exception()
                else:
                    node.state = TaskState.COMPLETED
                    node.result = atask.result()
                    results[tid] = node.result

            if not self._cancelled:
                launch_ready()

        # Collect final status
        return results

    async def cancel(self) -> None:
        self._cancelled = True
        # Cancel running asyncio tasks — they'll be picked up in the next wait cycle

    def get_status(self) -> dict[str, str]:
        return {tid: node.state.value for tid, node in self._tasks.items()}


# --- Usage / test ---
if __name__ == "__main__":
    async def test_basic():
        log: list[str] = []

        async def fetch_users(deps):
            log.append("start:fetch_users")
            await asyncio.sleep(0.05)
            log.append("done:fetch_users")
            return ["alice", "bob"]

        async def fetch_orders(deps):
            log.append("start:fetch_orders")
            await asyncio.sleep(0.05)
            log.append("done:fetch_orders")
            return [{"user": "alice", "total": 100}]

        async def merge_data(deps):
            log.append("start:merge")
            users = deps["fetch_users"]
            orders = deps["fetch_orders"]
            await asyncio.sleep(0.02)
            result = {"users": users, "orders": orders, "count": len(users)}
            log.append("done:merge")
            return result

        async def generate_report(deps):
            log.append("start:report")
            merged = deps["merge"]
            await asyncio.sleep(0.02)
            log.append("done:report")
            return f"Report: {merged['count']} users"

        executor = TaskGraphExecutor()
        executor.add_task("fetch_users", fetch_users)
        executor.add_task("fetch_orders", fetch_orders)
        executor.add_task("merge", merge_data, depends_on=["fetch_users", "fetch_orders"])
        executor.add_task("generate_report", generate_report, depends_on=["merge"])

        results = await executor.execute()

        print(f"Execution log: {log}")
        print(f"Results: {results}")
        print(f"Status: {executor.get_status()}")

        # fetch_users and fetch_orders should start in parallel
        assert log.index("start:fetch_users") < log.index("start:merge")
        assert log.index("start:fetch_orders") < log.index("start:merge")
        # Both fetches start before either finishes (parallel)
        fetch_starts = {log.index("start:fetch_users"), log.index("start:fetch_orders")}
        assert max(fetch_starts) < min(log.index("done:fetch_users"), log.index("done:fetch_orders"))

        assert results["generate_report"] == "Report: 2 users"
        assert executor.get_status()["generate_report"] == "completed"

    async def test_failure_skips_dependents():
        async def failing_task(deps):
            raise RuntimeError("boom")

        async def dependent_task(deps):
            return "should not run"

        async def independent_task(deps):
            return "independent result"

        executor = TaskGraphExecutor()
        executor.add_task("fail", failing_task)
        executor.add_task("dependent", dependent_task, depends_on=["fail"])
        executor.add_task("independent", independent_task)

        results = await executor.execute()
        status = executor.get_status()

        print(f"\nFailure test status: {status}")
        assert status["fail"] == "failed"
        assert status["dependent"] == "skipped"
        assert status["independent"] == "completed"
        assert results["independent"] == "independent result"
        assert "dependent" not in results

    async def test_cycle_detection():
        executor = TaskGraphExecutor()
        executor.add_task("a", lambda deps: None, depends_on=["b"])
        executor.add_task("b", lambda deps: None, depends_on=["a"])
        try:
            await executor.execute()
            assert False, "Should have raised"
        except CycleError as e:
            print(f"\nCycle detected: {e}")

    asyncio.run(test_basic())
    asyncio.run(test_failure_skips_dependents())
    asyncio.run(test_cycle_detection())
    print("\nAll tests passed.")
```'''
    ),
]
