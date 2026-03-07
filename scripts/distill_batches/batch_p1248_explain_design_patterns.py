"""
Code explanation training pairs - Design pattern implementations (strategy, observer, factory)
"""

pairs = [
    {
        "instruction": r'''Walk me through this Python code. What pattern is this?

```python
from abc import ABC, abstractmethod

class PaymentStrategy(ABC):
    @abstractmethod
    def pay(self, amount: float) -> dict:
        pass

class CreditCardPayment(PaymentStrategy):
    def __init__(self, card_number: str, cvv: str):
        self.card_number = card_number
        self.cvv = cvv

    def pay(self, amount: float) -> dict:
        return {"method": "credit_card", "last4": self.card_number[-4:], "amount": amount}

class PayPalPayment(PaymentStrategy):
    def __init__(self, email: str):
        self.email = email

    def pay(self, amount: float) -> dict:
        return {"method": "paypal", "email": self.email, "amount": amount}

class Checkout:
    def __init__(self, strategy: PaymentStrategy):
        self._strategy = strategy

    def set_strategy(self, strategy: PaymentStrategy):
        self._strategy = strategy

    def process(self, amount: float) -> dict:
        return self._strategy.pay(amount)
```''',
        "output": r'''This is the Strategy pattern -- it lets you swap algorithms (in this case, payment methods) at runtime without changing the code that uses them.

**The components:**

1. **`PaymentStrategy` (abstract base class):** Defines the interface that all payment methods must follow -- a `pay` method that takes an amount and returns a dict. The `@abstractmethod` decorator means you cannot instantiate `PaymentStrategy` directly; you must subclass it.

2. **Concrete strategies (`CreditCardPayment`, `PayPalPayment`):** Each implements `pay` differently. Credit card returns the last 4 digits; PayPal returns the email. New payment methods (crypto, bank transfer) can be added without modifying existing code.

3. **`Checkout` (the context):** Holds a reference to a strategy and delegates payment processing to it. It does not know or care which concrete strategy it is using -- it just calls `pay()`.

**Why this pattern is useful:**

Without Strategy, you would end up with if/else chains or switch statements inside `process()`:
```
if method == "credit_card": ...
elif method == "paypal": ...
```
Every new payment method requires modifying `Checkout`. With Strategy, you add a new class and pass it in -- `Checkout` never changes. This follows the Open/Closed Principle.

**`set_strategy` enables runtime swapping:** A user could start with credit card, then switch to PayPal mid-session without creating a new Checkout instance.

**Python alternative:** In Python, you could also pass a plain function instead of a strategy object, since functions are first-class. The class-based approach is better when strategies need configuration state (like card numbers or emails).'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain an Observer pattern implementation in JavaScript. Let me trace through the event system.
</think>

Explain this JavaScript code:

```javascript
class EventEmitter {
  constructor() {
    this._listeners = new Map();
  }

  on(event, callback) {
    if (!this._listeners.has(event)) {
      this._listeners.set(event, new Set());
    }
    this._listeners.get(event).add(callback);
    return () => this.off(event, callback);
  }

  off(event, callback) {
    const listeners = this._listeners.get(event);
    if (listeners) {
      listeners.delete(callback);
      if (listeners.size === 0) this._listeners.delete(event);
    }
  }

  emit(event, ...args) {
    const listeners = this._listeners.get(event);
    if (!listeners) return;
    for (const callback of listeners) {
      callback(...args);
    }
  }

  once(event, callback) {
    const wrapper = (...args) => {
      this.off(event, wrapper);
      callback(...args);
    };
    return this.on(event, wrapper);
  }
}
```''',
        "output": r'''<think>
This is the Observer pattern implemented as a pub/sub event emitter. I should explain the subscription management, the cleanup pattern, and the once() implementation.
</think>

This is the Observer pattern implemented as an event emitter / pub-sub system. Components can subscribe to named events and get notified when those events fire.

**`on(event, callback)` -- subscribe:**

Adds a callback to the Set of listeners for the given event. Using a Set (instead of an Array) automatically prevents duplicate registrations of the same callback. Returns an unsubscribe function -- a nice API touch that eliminates the need to keep references to callbacks for later removal.

**`off(event, callback)` -- unsubscribe:**

Removes a specific callback. If no listeners remain for that event, cleans up the Map entry entirely. This prevents memory leaks from accumulating empty Sets.

**`emit(event, ...args)` -- notify:**

Calls every registered callback for the event, passing along any arguments. The callbacks execute synchronously and in insertion order (Sets maintain insertion order in JS).

**`once(event, callback)` -- one-time listener:**

Wraps the callback in a function that unsubscribes itself before calling the original callback. The key subtlety: it calls `this.off(event, wrapper)`, not `this.off(event, callback)`. The wrapper is what was registered, so the wrapper is what must be removed.

**Design decisions worth noting:**

- No error handling in emit. If a callback throws, subsequent callbacks for the same event will not run. Node.js EventEmitter has the same behavior.
- No async support. If a callback returns a Promise, it is not awaited.
- Callbacks are called with the emitter's context, not bound to anything specific. If a callback uses `this`, it could behave unexpectedly unless arrow functions or `.bind()` are used.
- The unsubscribe function returned by `on` creates a closure, which is cleaner than requiring callers to call `off` manually.'''
    },
    {
        "instruction": r'''What pattern is this and how does it work?

```python
class Builder:
    def __init__(self):
        self._config = {}

    def host(self, host):
        self._config['host'] = host
        return self

    def port(self, port):
        self._config['port'] = port
        return self

    def database(self, db):
        self._config['database'] = db
        return self

    def credentials(self, user, password):
        self._config['user'] = user
        self._config['password'] = password
        return self

    def pool_size(self, size):
        if size < 1 or size > 100:
            raise ValueError("Pool size must be between 1 and 100")
        self._config['pool_size'] = size
        return self

    def build(self):
        required = ['host', 'database', 'user', 'password']
        missing = [k for k in required if k not in self._config]
        if missing:
            raise ValueError(f"Missing required config: {missing}")
        self._config.setdefault('port', 5432)
        self._config.setdefault('pool_size', 10)
        return DatabaseConnection(**self._config)

# Usage:
conn = (Builder()
    .host("localhost")
    .port(5432)
    .database("myapp")
    .credentials("admin", "secret")
    .build())
```''',
        "output": r'''This is the Builder pattern -- it constructs a complex object step by step, with validation and sensible defaults.

**How it works:**

Each method (`.host()`, `.port()`, etc.) stores a value in the internal `_config` dict and returns `self`. Returning `self` enables method chaining -- the fluent API style where you can write `.host(...).port(...).database(...)` on a single expression.

**The `build()` method:**

This is where the real work happens:
1. Validates that all required fields are present. If you forgot to call `.credentials()`, it raises a clear error listing what is missing.
2. Sets defaults for optional fields using `setdefault` -- port defaults to 5432 (PostgreSQL) and pool_size to 10.
3. Unpacks the config dict into the `DatabaseConnection` constructor using `**self._config`.

**`pool_size` validates eagerly** -- the error is raised when you call `.pool_size(200)`, not deferred to `build()`. This gives immediate feedback at the point of misconfiguration.

**Why use Builder instead of just passing arguments to a constructor?**

1. Readability: named method calls are clearer than positional arguments, especially with many parameters.
2. Validation: the builder can enforce constraints before the object is created.
3. Optional parameters: you only call the methods you need; the rest get defaults.
4. Immutability: the final `DatabaseConnection` can be immutable since all configuration happens before construction.

**Python alternative:** For simpler cases, keyword arguments with defaults achieve the same goal. Builders shine when there are complex validation rules, interdependent parameters, or when the construction process has multiple steps.'''
    },
    {
        "instruction": r'''Explain this code -- what is the pattern and how does it work?

```python
from __future__ import annotations
from typing import Dict, Type

class Animal:
    _registry: Dict[str, Type[Animal]] = {}

    def __init_subclass__(cls, animal_type: str = "", **kwargs):
        super().__init_subclass__(**kwargs)
        if animal_type:
            Animal._registry[animal_type] = cls

    @classmethod
    def create(cls, animal_type: str, name: str) -> Animal:
        if animal_type not in cls._registry:
            raise ValueError(f"Unknown animal type: {animal_type}")
        return cls._registry[animal_type](name)

class Dog(Animal, animal_type="dog"):
    def __init__(self, name):
        self.name = name
    def speak(self):
        return f"{self.name} says Woof!"

class Cat(Animal, animal_type="cat"):
    def __init__(self, name):
        self.name = name
    def speak(self):
        return f"{self.name} says Meow!"
```''',
        "output": r'''This is the Factory pattern with auto-registration -- subclasses register themselves simply by being defined, and the base class creates instances by type name.

**`__init_subclass__` -- the auto-registration hook:**

This special method is called automatically whenever a class inherits from `Animal`. The `animal_type` keyword argument is captured from the class definition line: `class Dog(Animal, animal_type="dog")` passes `"dog"` to `__init_subclass__`.

When `animal_type` is non-empty, the subclass is stored in `_registry` with that type string as the key. This means defining the class IS the registration -- no separate registration step needed.

**`create` -- the factory method:**

Looks up the type string in the registry and calls the corresponding class constructor. The caller does not need to know about `Dog` or `Cat` -- they just say `Animal.create("dog", "Buddy")`.

**Why this is powerful:**

1. New animal types can be added in separate files. As long as the file is imported (so the class definition runs), the type is automatically available.
2. The factory method provides a single entry point for object creation, which is useful for deserialization: `Animal.create(data["type"], data["name"])`.
3. No if/else chain to maintain -- adding a new type never requires modifying existing code.

**The `super().__init_subclass__(**kwargs)` call** is important for cooperative multiple inheritance. It forwards any unrecognized keyword arguments up the MRO chain.

**Edge case:** If two subclasses register with the same `animal_type` string, the second one silently overwrites the first. Adding a duplicate check would make this more robust.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain a middleware/chain of responsibility pattern implementation.
</think>

Walk me through this middleware system:

```python
class Middleware:
    def __init__(self):
        self._middlewares = []

    def use(self, fn):
        self._middlewares.append(fn)
        return self

    def execute(self, context):
        index = -1

        def dispatch(i):
            nonlocal index
            if i <= index:
                raise RuntimeError("next() called multiple times")
            index = i
            if i >= len(self._middlewares):
                return
            fn = self._middlewares[i]
            fn(context, lambda: dispatch(i + 1))

        dispatch(0)
        return context
```''',
        "output": r'''<think>
This is a middleware pipeline similar to Express.js or Koa. I should explain the dispatch mechanism and the next() function pattern.
</think>

This is a middleware pipeline -- the Chain of Responsibility pattern commonly seen in web frameworks like Express.js and Koa.

**How it works:**

Each middleware is a function that receives a `context` and a `next` function. The middleware can:
1. Modify the context before calling `next()` (pre-processing).
2. Call `next()` to pass control to the next middleware.
3. Modify the context after `next()` returns (post-processing).
4. NOT call `next()` to short-circuit the chain (e.g., for auth rejection).

**The `dispatch` function:**

This is the engine of the pipeline. `dispatch(i)` runs the i-th middleware and provides it with `lambda: dispatch(i + 1)` as the `next` callback. When the middleware calls `next()`, it triggers `dispatch(i + 1)`, which runs the next middleware, and so on.

**The `index` guard:**

The `nonlocal index` and `if i <= index` check prevent a middleware from calling `next()` more than once. Without this, double-calling next would re-execute all downstream middleware, causing unpredictable behavior.

**Execution flow example:**

With three middlewares [A, B, C]:
1. dispatch(0) calls A with next = dispatch(1)
2. A does pre-work, calls next()
3. dispatch(1) calls B with next = dispatch(2)
4. B calls next()
5. dispatch(2) calls C with next = dispatch(3)
6. C calls next() -- dispatch(3) returns immediately (past end of list)
7. C finishes, returns to B
8. B does post-work, returns to A
9. A does post-work

This creates an "onion" execution model -- each middleware wraps around the next one, with code before `next()` running on the way in and code after running on the way out.'''
    },
]
