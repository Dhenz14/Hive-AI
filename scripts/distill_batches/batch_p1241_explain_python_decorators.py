"""
Code explanation training pairs - Python decorators, metaclasses, descriptors
"""

pairs = [
    {
        "instruction": r'''Explain what this decorator does:

```python
import functools
import time

def retry(max_attempts=3, delay=1, exceptions=(Exception,)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        time.sleep(delay * attempt)
            raise last_exception
        return wrapper
    return decorator
```''',
        "output": r'''This is a retry decorator with configurable behavior. It wraps a function so that if it raises certain exceptions, it automatically retries before giving up.

**The three-layer structure:**

1. `retry(...)` is the outermost function -- it accepts configuration parameters and returns the actual decorator. This pattern is needed because `@retry(max_attempts=5)` first calls `retry()` with the config, and the returned `decorator` is then applied to the target function.

2. `decorator(func)` receives the function being decorated.

3. `wrapper(*args, **kwargs)` is what actually runs when you call the decorated function.

**Retry logic:**

- It loops up to `max_attempts` times, calling the original function each time.
- If the function succeeds (returns without raising), the result is returned immediately -- no further retries.
- If it raises an exception that matches the `exceptions` tuple, the exception is stored and the loop continues after sleeping.
- The sleep uses linear backoff: `delay * attempt`. So with default settings, it waits 1s after the first failure, 2s after the second.
- After exhausting all attempts, it re-raises the last exception.

**`functools.wraps` note:** This copies the original function's `__name__`, `__doc__`, and other attributes onto the wrapper. Without it, introspection and debugging tools would show "wrapper" instead of the real function name.

**Subtle behavior:** The `exceptions` parameter defaults to `(Exception,)`, catching almost everything. But `KeyboardInterrupt` and `SystemExit` derive from `BaseException`, not `Exception`, so those will not be retried -- which is the correct behavior.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain a descriptor protocol implementation. This is a cached property descriptor, similar to what functools.cached_property does.
</think>

What is this class doing? I see it used as a decorator on methods.

```python
class cached_property:
    def __init__(self, func):
        self.func = func
        self.attrname = None
        self.__doc__ = func.__doc__

    def __set_name__(self, owner, name):
        self.attrname = name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        if self.attrname is None:
            raise TypeError("cached_property requires __set_name__")
        val = instance.__dict__.get(self.attrname)
        if val is None:
            val = self.func(instance)
            instance.__dict__[self.attrname] = val
        return val
```''',
        "output": r'''<think>
This is a descriptor that implements cached/lazy property access. I should explain the descriptor protocol, __set_name__, and the caching mechanism via the instance dict.
</think>

This is a descriptor class that implements a cached property -- a property that computes its value once and then caches it on the instance.

**How the descriptor protocol works here:**

1. **`__init__`**: When you write `@cached_property` above a method, Python calls `cached_property(func)`, storing the original method.

2. **`__set_name__`**: Called automatically by Python when the class is created. It tells the descriptor what attribute name it was assigned to (e.g., if you write `x = cached_property(func)`, `attrname` becomes `"x"`). This was added in Python 3.6.

3. **`__get__`**: Called every time the attribute is accessed on an instance. This is the core of the descriptor protocol.

**The caching trick:**

When `__get__` fires, it checks `instance.__dict__` for the cached value. If not found, it calls the original function and stores the result directly in the instance's `__dict__`. The next time the attribute is accessed, Python finds it in the instance dict and returns it directly -- the descriptor's `__get__` is never called again because instance attributes shadow data descriptors that only define `__get__` (non-data descriptors).

**The `if instance is None` guard:** When accessed on the class itself (e.g., `MyClass.prop`), `instance` is None. Returning `self` lets you introspect the descriptor object.

**Limitation:** If the computed value is actually `None`, this implementation will recompute it every time because `dict.get` returns `None` for missing keys. A sentinel value like `_MISSING = object()` would fix this.'''
    },
    {
        "instruction": r'''Walk me through this metaclass:

```python
class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]

class Database(metaclass=SingletonMeta):
    def __init__(self, url):
        self.url = url
        self.connection = self._connect()

    def _connect(self):
        print(f"Connecting to {self.url}")
        return True
```''',
        "output": r'''This implements the Singleton pattern using a metaclass -- ensuring only one instance of `Database` ever exists.

**How metaclasses work:**

A metaclass is the "class of a class." When you write `class Database(metaclass=SingletonMeta)`, `Database` itself becomes an instance of `SingletonMeta`. So when you call `Database("postgres://...")`, Python calls `SingletonMeta.__call__` -- not the normal object creation path.

**The `__call__` override:**

Normally, calling a class triggers `type.__call__`, which runs `__new__` to create the instance, then `__init__` to initialize it. `SingletonMeta.__call__` intercepts this:

1. Checks if this class already has an instance in the `_instances` dict.
2. If not, calls `super().__call__(*args, **kwargs)` which runs the normal `__new__` + `__init__` chain and stores the result.
3. If yes, returns the existing instance -- skipping both `__new__` and `__init__`.

**Important consequence:** The second call to `Database("mysql://...")` returns the first instance with the postgres URL. The `__init__` does NOT run again, so the URL is never updated. This surprises people who expect re-initialization.

**Why a metaclass instead of `__new__`?** Overriding `__new__` on `Database` itself would still call `__init__` on the existing instance every time, which could have side effects (like reconnecting). The metaclass approach skips `__init__` entirely on subsequent calls.

**Thread safety note:** This is not thread-safe. Two threads could both pass the `if cls not in` check simultaneously, creating two instances. A lock around the check-and-store would fix that.'''
    },
    {
        "instruction": r'''What does this decorator pattern do?

```python
def validate_types(**type_hints):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            for param_name, expected_type in type_hints.items():
                if param_name in bound.arguments:
                    value = bound.arguments[param_name]
                    if not isinstance(value, expected_type):
                        raise TypeError(
                            f"{param_name} must be {expected_type.__name__}, "
                            f"got {type(value).__name__}"
                        )
            return func(*args, **kwargs)
        return wrapper
    return decorator

@validate_types(name=str, age=int)
def create_user(name, age, role="member"):
    return {"name": name, "age": age, "role": role}
```''',
        "output": r'''This is a runtime type-checking decorator. It validates function arguments against specified types before the function runs.

**How it works:**

1. `@validate_types(name=str, age=int)` passes the type constraints as keyword arguments and returns the actual decorator.

2. When `create_user("Alice", 25)` is called, the wrapper fires and uses `inspect.signature` to match positional and keyword arguments to parameter names.

3. `sig.bind(*args, **kwargs)` maps the actual call arguments to parameter names -- so it figures out that arg 0 is `name` and arg 1 is `age`, regardless of whether they were passed positionally or as keywords.

4. `apply_defaults()` fills in default values (like `role="member"`) so they can also be validated if type hints are provided for them.

5. For each parameter that has a type constraint in `type_hints`, it checks `isinstance(value, expected_type)`. If the check fails, it raises a `TypeError` with a clear message.

6. If all checks pass, the original function runs normally.

**Design choices:**

- Only parameters listed in `type_hints` are checked -- `role` is unchecked here since it was not included.
- Using `isinstance` means subclasses are accepted (a `bool` would pass an `int` check since `bool` inherits from `int`).
- The validation happens at call time, not at import time -- so there is a small performance cost on every call.

**Compared to Python type hints:** This does actual runtime enforcement. Normal `def foo(x: int)` annotations are ignored at runtime and only used by static checkers like mypy.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain a class decorator that adds methods to a class. This is similar to dataclasses.
</think>

Explain what this class decorator does:

```python
def auto_repr(*fields):
    def decorator(cls):
        def __repr__(self):
            field_strs = []
            for f in fields:
                field_strs.append(f"{f}={getattr(self, f)!r}")
            return f"{cls.__name__}({', '.join(field_strs)})"

        def __eq__(self, other):
            if not isinstance(other, cls):
                return NotImplemented
            return all(
                getattr(self, f) == getattr(other, f)
                for f in fields
            )

        def __hash__(self):
            return hash(tuple(getattr(self, f) for f in fields))

        cls.__repr__ = __repr__
        cls.__eq__ = __eq__
        cls.__hash__ = __hash__
        return cls
    return decorator
```''',
        "output": r'''<think>
This is a class decorator that auto-generates __repr__, __eq__, and __hash__ based on specified fields. Similar to what @dataclass does but more manually controlled.
</think>

This class decorator auto-generates three dunder methods based on a list of field names. It is a simplified version of what `@dataclasses.dataclass` does.

**What it adds to the class:**

1. **`__repr__`**: Produces output like `User(name='Alice', age=30)`. Uses `!r` formatting to add quotes around strings and properly represent other types. The `cls.__name__` is captured from the closure, so subclasses would still show the original class name -- a subtle bug.

2. **`__eq__`**: Compares two instances by checking if all specified fields are equal. Returns `NotImplemented` if the other object is a different type, which tells Python to try the other object's `__eq__` instead of returning `False`. This is the correct protocol.

3. **`__hash__`**: Computes a hash from a tuple of the field values, making instances usable as dictionary keys and in sets. This is important because Python makes a class unhashable when you define `__eq__` without `__hash__`.

**Usage would look like:**
```
@auto_repr('name', 'age')
class User:
    def __init__(self, name, age):
        self.name = name
        self.age = age
```

**Limitation:** The fields are specified as strings and accessed via `getattr` at runtime. If you mistype a field name, you get an `AttributeError` at call time, not at class definition time. Dataclasses avoid this by inspecting annotations at class creation.'''
    },
]
