"""Code translation pairs: JavaScript/Node.js to Python equivalents."""

PAIRS = [
    (
        "code-translation/javascript-to-python",
        r'''Convert this Express.js middleware chain to Python:

const express = require("express");
const app = express();

function authMiddleware(req, res, next) {
  const token = req.headers.authorization?.split(" ")[1];
  if (!token) {
    return res.status(401).json({ error: "No token" });
  }
  try {
    req.user = jwt.verify(token, process.env.SECRET);
    next();
  } catch (e) {
    res.status(403).json({ error: "Invalid token" });
  }
}

function roleCheck(role) {
  return (req, res, next) => {
    if (req.user.role !== role) {
      return res.status(403).json({ error: "Forbidden" });
    }
    next();
  };
}

app.get("/admin", authMiddleware, roleCheck("admin"), (req, res) => {
  res.json({ message: `Hello ${req.user.name}` });
});

app.listen(3000);''',
        r'''<think>
Express middleware chain to Python -- the most natural target is FastAPI with its dependency injection system, since that's the modern Python equivalent.

Key differences to handle:

1. Express middleware uses (req, res, next) pattern with mutation. FastAPI uses dependency injection via Depends(). Very different paradigm.

2. Express's req.user mutation pattern -- in FastAPI, dependencies return values that get injected as function parameters. No mutation needed.

3. roleCheck is a factory function returning middleware. In FastAPI, I'll make a dependency factory that returns a Depends-compatible callable.

4. Error responses: Express uses res.status().json(). FastAPI raises HTTPException.

5. Optional chaining ?. -- Python uses getattr or dict.get or explicit checks.

6. process.env.SECRET -> os.environ["SECRET"] or via pydantic Settings.

Let me think about the role check factory. In Express it returns a middleware function. In FastAPI I can make a function that returns a dependency. Something like:

def require_role(role):
    def checker(user = Depends(get_current_user)):
        if user.role != role:
            raise HTTPException(403)
        return user
    return checker

That's clean and idiomatic.
</think>

```python
import os
import jwt
from fastapi import FastAPI, Depends, HTTPException, Header
from typing import Optional

app = FastAPI()

def get_current_user(authorization: Optional[str] = Header(None)):
    # Mirrors authMiddleware
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, os.environ["SECRET"], algorithms=["HS256"])
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Invalid token")

def require_role(role: str):
    # Mirrors roleCheck factory -- returns a dependency
    def checker(user: dict = Depends(get_current_user)):
        if user.get("role") != role:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return checker

@app.get("/admin")
def admin_endpoint(user: dict = Depends(require_role("admin"))):
    return {"message": f"Hello {user['name']}"}

# Run with: uvicorn module_name:app --port 3000
```

Key translation notes:

- Express middleware chain `(mw1, mw2, handler)` becomes FastAPI's `Depends()` injection chain
- `req.user = ...` mutation becomes a return value from the dependency
- `res.status(401).json(...)` becomes `raise HTTPException(status_code=401, ...)`
- Factory middleware `roleCheck(role)` becomes a dependency factory `require_role(role)` that returns a Depends-compatible function
- Optional chaining `?.` becomes explicit None checks''',
    ),
    (
        "code-translation/javascript-to-python",
        r'''Translate this JavaScript Promise chain and error handling to Python:

function fetchUserData(userId) {
  return fetch(`https://api.example.com/users/${userId}`)
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then(user => {
      return fetch(`https://api.example.com/posts?author=${user.id}`)
        .then(res => res.json())
        .then(posts => ({ ...user, posts }));
    })
    .catch(err => {
      console.error("Failed:", err.message);
      return null;
    });
}

async function main() {
  const users = await Promise.all([
    fetchUserData(1),
    fetchUserData(2),
    fetchUserData(3),
  ]);
  const valid = users.filter(u => u !== null);
  console.log(`Got ${valid.length} users`);
}''',
        r'''```python
import asyncio
import aiohttp

async def fetch_user_data(session, user_id):
    try:
        async with session.get(
            f"https://api.example.com/users/{user_id}"
        ) as resp:
            if resp.status >= 400:
                raise Exception(f"HTTP {resp.status}")
            user = await resp.json()

        async with session.get(
            f"https://api.example.com/posts?author={user['id']}"
        ) as resp:
            posts = await resp.json()
            return {**user, "posts": posts}

    except Exception as err:
        print(f"Failed: {err}")
        return None

async def main():
    async with aiohttp.ClientSession() as session:
        users = await asyncio.gather(
            fetch_user_data(session, 1),
            fetch_user_data(session, 2),
            fetch_user_data(session, 3),
        )
    valid = [u for u in users if u is not None]
    print(f"Got {len(valid)} users")

asyncio.run(main())
```

Translation notes:

- `Promise.all([...])` maps directly to `asyncio.gather(...)`
- `.then()` chains become sequential `await` calls -- Python's async/await is generally cleaner than chained .then()
- `{ ...user, posts }` spread becomes `{**user, "posts": posts}` dict merge
- `fetch()` becomes `aiohttp` -- Python has no built-in fetch. We pass a shared session for connection pooling
- `.filter(u => u !== null)` becomes a list comprehension `[u for u in users if u is not None]`
- JS `res.ok` (status 200-299) becomes an explicit `resp.status >= 400` check''',
    ),
    (
        "code-translation/javascript-to-python",
        r'''Convert this Node.js EventEmitter pattern to Python:

const EventEmitter = require("events");

class OrderSystem extends EventEmitter {
  constructor() {
    super();
    this.orders = new Map();
  }

  placeOrder(item, quantity) {
    const id = Date.now().toString(36);
    const order = { id, item, quantity, status: "pending" };
    this.orders.set(id, order);
    this.emit("order:placed", order);
    return id;
  }

  fulfillOrder(id) {
    const order = this.orders.get(id);
    if (!order) throw new Error("Order not found");
    order.status = "fulfilled";
    this.emit("order:fulfilled", order);
  }
}

const system = new OrderSystem();
system.on("order:placed", (order) => {
  console.log(`New order: ${order.item} x${order.quantity}`);
});
system.on("order:fulfilled", (order) => {
  console.log(`Fulfilled: ${order.id}`);
});

const id = system.placeOrder("Widget", 5);
system.fulfillOrder(id);''',
        r'''<think>
Node's EventEmitter pattern to Python. There are a few approaches:

1. Use the `pyee` library (EventEmitter port for Python) -- but that's an external dependency
2. Roll our own simple event system -- closest to the spirit of translation
3. Use Python's built-in options -- there is no built-in EventEmitter in Python

I'll implement a simple EventEmitter mixin/base class since it shows the translation clearly and the implementation is small.

Key differences:
- JS Map -> Python dict
- Date.now().toString(36) -> I'll use uuid or time-based id
- Arrow function callbacks -> regular functions or lambdas
- The on/emit pattern maps well to a dict of lists of callables

Actually, Python does have a lightweight option: I could use signals (like blinker library) or just callbacks. But implementing a simple EventEmitter class is most instructive.
</think>

```python
import time
from collections import defaultdict
from typing import Any, Callable

class EventEmitter:
    def __init__(self):
        self._listeners = defaultdict(list)

    def on(self, event: str, callback: Callable):
        self._listeners[event].append(callback)

    def emit(self, event: str, *args: Any):
        for callback in self._listeners.get(event, []):
            callback(*args)

class OrderSystem(EventEmitter):
    def __init__(self):
        super().__init__()
        self.orders = {}

    def place_order(self, item: str, quantity: int) -> str:
        order_id = format(int(time.time() * 1000), "x")
        order = {
            "id": order_id,
            "item": item,
            "quantity": quantity,
            "status": "pending",
        }
        self.orders[order_id] = order
        self.emit("order:placed", order)
        return order_id

    def fulfill_order(self, order_id: str):
        order = self.orders.get(order_id)
        if not order:
            raise KeyError("Order not found")
        order["status"] = "fulfilled"
        self.emit("order:fulfilled", order)

system = OrderSystem()

system.on("order:placed", lambda order: print(
    f"New order: {order['item']} x{order['quantity']}"
))
system.on("order:fulfilled", lambda order: print(
    f"Fulfilled: {order['id']}"
))

oid = system.place_order("Widget", 5)
system.fulfill_order(oid)
```

Key differences:

- Python has no built-in EventEmitter, so we implement one with `defaultdict(list)` to store listeners
- `Date.now().toString(36)` (base-36 timestamp) becomes `format(int(time.time() * 1000), "x")` (hex timestamp)
- JS `Map` becomes a plain Python `dict` -- Python dicts are ordered since 3.7 and cover most Map use cases
- JS `throw new Error(...)` becomes `raise KeyError(...)` with a more specific exception type
- Arrow callbacks become lambdas or named functions''',
    ),
    (
        "code-translation/javascript-to-python",
        r'''Translate this JavaScript array processing with method chaining to Python:

const data = [
  { name: "Alice", dept: "eng", salary: 95000 },
  { name: "Bob", dept: "eng", salary: 110000 },
  { name: "Carol", dept: "sales", salary: 85000 },
  { name: "Dave", dept: "eng", salary: 120000 },
  { name: "Eve", dept: "sales", salary: 92000 },
  { name: "Frank", dept: "hr", salary: 78000 },
];

const result = data
  .filter(e => e.salary > 80000)
  .map(e => ({ ...e, bonus: e.salary * 0.1 }))
  .sort((a, b) => b.salary - a.salary)
  .reduce((groups, e) => {
    (groups[e.dept] = groups[e.dept] || []).push(e);
    return groups;
  }, {});

console.log(JSON.stringify(result, null, 2));''',
        r'''```python
from itertools import groupby
from operator import itemgetter
import json

data = [
    {"name": "Alice", "dept": "eng", "salary": 95000},
    {"name": "Bob", "dept": "eng", "salary": 110000},
    {"name": "Carol", "dept": "sales", "salary": 85000},
    {"name": "Dave", "dept": "eng", "salary": 120000},
    {"name": "Eve", "dept": "sales", "salary": 92000},
    {"name": "Frank", "dept": "hr", "salary": 78000},
]

# Filter salary > 80000
filtered = [e for e in data if e["salary"] > 80000]

# Add bonus field
with_bonus = [{**e, "bonus": e["salary"] * 0.1} for e in filtered]

# Sort by salary descending
sorted_data = sorted(with_bonus, key=itemgetter("salary"), reverse=True)

# Group by department
result = {}
for emp in sorted_data:
    result.setdefault(emp["dept"], []).append(emp)

print(json.dumps(result, indent=2))
```

Translation notes:

- JS method chaining (`.filter().map().sort().reduce()`) has no direct Python equivalent -- Python uses separate expressions for each step
- `.filter(fn)` -> list comprehension with `if` clause
- `.map(fn)` -> list comprehension with transformation
- `.sort((a,b) => b.salary - a.salary)` -> `sorted(..., key=itemgetter("salary"), reverse=True)`. Python uses a key function instead of a comparator
- `.reduce()` for grouping -> a simple loop with `dict.setdefault()`. Python's `itertools.groupby` requires pre-sorted data on the group key, so a manual loop is simpler here
- `{ ...e, bonus: ... }` spread -> `{**e, "bonus": ...}` dict unpacking
- `JSON.stringify(x, null, 2)` -> `json.dumps(x, indent=2)`''',
    ),
    (
        "code-translation/javascript-to-python",
        r'''Convert this JavaScript class with private fields and getters to Python:

class BankAccount {
  #balance;
  #transactions;
  #owner;

  constructor(owner, initialBalance = 0) {
    this.#owner = owner;
    this.#balance = initialBalance;
    this.#transactions = [];
  }

  get balance() { return this.#balance; }
  get owner() { return this.#owner; }

  deposit(amount) {
    if (amount <= 0) throw new RangeError("Amount must be positive");
    this.#balance += amount;
    this.#transactions.push({ type: "deposit", amount, date: new Date() });
  }

  withdraw(amount) {
    if (amount <= 0) throw new RangeError("Amount must be positive");
    if (amount > this.#balance) throw new RangeError("Insufficient funds");
    this.#balance -= amount;
    this.#transactions.push({ type: "withdrawal", amount, date: new Date() });
  }

  getStatement() {
    return this.#transactions.map(t =>
      `${t.date.toISOString().slice(0,10)} ${t.type}: $${t.amount}`
    ).join("\n");
  }
}''',
        r'''<think>
JavaScript private fields (#) to Python. Python doesn't have true private fields -- convention is underscore prefix. There's name mangling with double underscore (__var) but that's not truly private either, just harder to access accidentally.

Key mapping decisions:

1. JS `#field` -> Python `_field` (single underscore convention) or `__field` (name mangling). I'll use single underscore since that's more Pythonic -- double underscore is rarely used in practice.

2. JS `get balance()` getter -> Python `@property` decorator. Direct equivalent.

3. `new Date()` -> `datetime.now()`

4. `RangeError` -> `ValueError` in Python (closest built-in equivalent)

5. `.map(...).join("\n")` -> `"\n".join(...)` with a list comprehension or generator

6. `toISOString().slice(0,10)` to get YYYY-MM-DD -> `strftime("%Y-%m-%d")` or `.isoformat()[:10]`
</think>

```python
from datetime import datetime

class BankAccount:
    def __init__(self, owner: str, initial_balance: float = 0):
        self._owner = owner
        self._balance = initial_balance
        self._transactions = []

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def owner(self) -> str:
        return self._owner

    def deposit(self, amount: float):
        if amount <= 0:
            raise ValueError("Amount must be positive")
        self._balance += amount
        self._transactions.append({
            "type": "deposit",
            "amount": amount,
            "date": datetime.now(),
        })

    def withdraw(self, amount: float):
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if amount > self._balance:
            raise ValueError("Insufficient funds")
        self._balance -= amount
        self._transactions.append({
            "type": "withdrawal",
            "amount": amount,
            "date": datetime.now(),
        })

    def get_statement(self) -> str:
        lines = [
            f"{t['date'].strftime('%Y-%m-%d')} {t['type']}: ${t['amount']}"
            for t in self._transactions
        ]
        return "\n".join(lines)
```

Translation notes:

- JS `#privateField` -> Python `_field` convention. Python has no true private fields; `_` signals "internal use" by convention
- JS `get prop()` -> Python `@property` decorator -- functionally identical
- `RangeError` -> `ValueError` (Python's closest built-in for "value out of acceptable range")
- `.map().join()` -> list comprehension inside `"\n".join(...)`
- `new Date()` -> `datetime.now()`
- `toISOString().slice(0,10)` -> `strftime("%Y-%m-%d")`''',
    ),
]
