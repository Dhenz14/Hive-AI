r"""Thinking-trace pairs: Python OOP code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this Python code and identify issues:

```python
class Animal:
    def __init__(self, name, species, sound, diet, habitat):
        self.name = name
        self.species = species
        self.sound = sound
        self.diet = diet
        self.habitat = habitat

    def speak(self):
        return f"{self.name} says {self.sound}"

    def eat(self):
        if self.diet == 'herbivore':
            return f"{self.name} eats plants"
        elif self.diet == 'carnivore':
            return f"{self.name} eats meat"
        elif self.diet == 'omnivore':
            return f"{self.name} eats everything"

    def describe_habitat(self):
        if self.habitat == 'forest':
            return f"{self.name} lives in the forest"
        elif self.habitat == 'ocean':
            return f"{self.name} lives in the ocean"
        elif self.habitat == 'desert':
            return f"{self.name} lives in the desert"
        elif self.habitat == 'arctic':
            return f"{self.name} lives in the arctic"

class Dog(Animal):
    def __init__(self, name, breed, is_trained):
        super().__init__(name, 'canine', 'woof', 'omnivore', 'domestic')
        self.breed = breed
        self.is_trained = is_trained
        self.tricks = []

    def learn_trick(self, trick):
        self.tricks.append(trick)

    def perform_tricks(self):
        return [f"{self.name} performs {t}" for t in self.tricks]

class Cat(Animal):
    def __init__(self, name, breed, is_indoor):
        super().__init__(name, 'feline', 'meow', 'carnivore', 'domestic')
        self.breed = breed
        self.is_indoor = is_indoor

class ServiceDog(Dog):
    def __init__(self, name, breed, service_type, handler):
        super().__init__(name, breed, True)
        self.service_type = service_type
        self.handler = handler
        self.certifications = []

class GuideDog(ServiceDog):
    def __init__(self, name, breed, handler, route_knowledge):
        super().__init__(name, breed, 'guide', handler)
        self.route_knowledge = route_knowledge

class TherapyDog(ServiceDog):
    def __init__(self, name, breed, handler, therapy_type):
        super().__init__(name, breed, 'therapy', handler)
        self.therapy_type = therapy_type

class PoliceDog(ServiceDog):
    def __init__(self, name, breed, handler, specialization):
        super().__init__(name, breed, 'police', handler)
        self.specialization = specialization

class AnimalShelter:
    def __init__(self):
        self.animals = []

    def add_animal(self, animal):
        self.animals.append(animal)

    def find_by_species(self, species):
        return [a for a in self.animals if a.species == species]

    def find_by_diet(self, diet):
        return [a for a in self.animals if a.diet == diet]

    def find_by_habitat(self, habitat):
        return [a for a in self.animals if a.habitat == habitat]

    def get_all_sounds(self):
        return {a.name: a.speak() for a in self.animals}
```''', r'''<think>
Let me review this Python OOP code for design issues.

1. Deep inheritance hierarchy:
- Animal -> Dog -> ServiceDog -> GuideDog/TherapyDog/PoliceDog
- This is 4 levels deep. The deeper the hierarchy, the harder it is to understand and modify. Changes to Animal ripple through everything. The inheritance represents "is-a" relationships that are increasingly tenuous -- a GuideDog is not meaningfully different from a ServiceDog in terms of behavior.

2. String-typed behavior (diet and habitat):
- eat() and describe_habitat() use string comparisons to determine behavior. This is the "replace conditional with polymorphism" smell. Adding a new diet type requires modifying the eat() method.
- However, creating a subclass for each diet type would be overengineering. The real issue is that these methods return None for unrecognized values (no else clause).

3. Constructor parameter explosion:
- Animal.__init__ takes 5 parameters. Each subclass adds more. GuideDog's effective parameter chain is (name, breed, handler, route_knowledge, is_trained=True, species='canine', sound='woof', diet='omnivore', habitat='domestic', service_type='guide'). This is hard to trace.

4. Composition vs inheritance:
- ServiceDog should use composition instead of inheritance. A "service capability" is a behavior/role, not an identity. A dog might stop being a service dog. Using composition:
```python
class ServiceCapability:
    def __init__(self, service_type, handler, certifications=None):
        self.service_type = service_type
        self.handler = handler
        self.certifications = certifications or []
```

5. AnimalShelter:
- Has three nearly identical find methods (find_by_species, find_by_diet, find_by_habitat). This violates DRY. Could use a generic filter method.
- Linear search through the list for every query.

6. Missing functionality:
- No __repr__ or __str__ methods.
- No equality comparison (__eq__).
- AnimalShelter has no way to remove animals.
- No validation on any inputs.

Let me structure the review.
</think>

## Code Review: Python OOP Animal Hierarchy

### HIGH - Deep Inheritance Hierarchy

**IH1: Four-level inheritance chain (Severity: HIGH)**
`Animal -> Dog -> ServiceDog -> GuideDog` is four levels deep. Each level adds tight coupling and makes the code harder to understand. The distinctions between GuideDog, TherapyDog, and PoliceDog are minimal -- they each add one attribute. This does not justify separate classes.

The subclasses at the bottom level differ only in one attribute value. They could be represented as ServiceDog instances with different configuration:
```python
guide_dog = ServiceDog(name="Rex", breed="Lab", service_type="guide",
                       handler=handler, metadata={"route_knowledge": routes})
```

### HIGH - Composition Over Inheritance

**CI1: Service capability should be composed, not inherited (Severity: HIGH)**
"Being a service dog" is a role, not an identity. A dog might gain or lose this role over time. Inheritance makes it permanent. Use composition:
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ServiceRole:
    service_type: str
    handler: str
    certifications: list

class Dog(Animal):
    def __init__(self, name, breed, is_trained=False):
        super().__init__(name, 'canine', 'woof', 'omnivore', 'domestic')
        self.breed = breed
        self.is_trained = is_trained
        self.tricks = []
        self.service_role: Optional[ServiceRole] = None

    def assign_service_role(self, service_type, handler):
        self.service_role = ServiceRole(service_type, handler, [])
        self.is_trained = True
```

### MEDIUM - Conditional Logic

**CL1: String-based dispatch in eat() and describe_habitat() (Severity: MEDIUM)**
These methods use if/elif chains on string values. Adding a new diet or habitat requires modifying the method. More importantly, unrecognized values return None silently:
```python
animal = Animal("X", "alien", "beep", "photosynthesis", "space")
animal.eat()  # returns None
```
Add an else clause or use enums:
```python
from enum import Enum

class Diet(Enum):
    HERBIVORE = 'herbivore'
    CARNIVORE = 'carnivore'
    OMNIVORE = 'omnivore'

DIET_DESCRIPTIONS = {
    Diet.HERBIVORE: 'eats plants',
    Diet.CARNIVORE: 'eats meat',
    Diet.OMNIVORE: 'eats everything',
}

def eat(self):
    desc = DIET_DESCRIPTIONS.get(self.diet)
    if desc is None:
        raise ValueError(f"Unknown diet: {self.diet}")
    return f"{self.name} {desc}"
```

### MEDIUM - DRY Violation in AnimalShelter

**DRY1: Repetitive filter methods (Severity: MEDIUM)**
`find_by_species`, `find_by_diet`, `find_by_habitat` are nearly identical. Use a generic filter:
```python
class AnimalShelter:
    def find_by(self, **criteria):
        return [
            a for a in self.animals
            if all(getattr(a, k) == v for k, v in criteria.items())
        ]

    # Usage: shelter.find_by(species='canine', diet='omnivore')
```

### LOW - Missing Features

**MF1: No __repr__ or __str__**
Printing any animal shows `<Animal object at 0x...>`. Add meaningful representations.

**MF2: No removal from shelter**
AnimalShelter has `add_animal` but no way to remove an animal (adoption, transfer, etc.).

**MF3: No input validation**
No validation on any constructor parameter. Empty names, negative values, or None are silently accepted.'''),

    ("thinking/code-review", r'''Review this Python code and identify issues:

```python
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

@runtime_checkable
class Drawable(Protocol):
    def draw(self) -> str: ...
    def get_area(self) -> float: ...

class Shape(ABC):
    def __init__(self, color: str = 'black'):
        self.color = color
        self._observers = []

    @abstractmethod
    def area(self) -> float: ...

    @abstractmethod
    def perimeter(self) -> float: ...

    def draw(self) -> str:
        return f"Drawing {self.__class__.__name__} in {self.color}"

    def get_area(self) -> float:
        return self.area()

    def add_observer(self, observer):
        self._observers.append(observer)

    def notify_observers(self):
        for obs in self._observers:
            obs.update(self)

class Circle(Shape):
    def __init__(self, radius: float, color: str = 'black'):
        super().__init__(color)
        self._radius = radius

    @property
    def radius(self):
        return self._radius

    @radius.setter
    def radius(self, value):
        self._radius = value
        self.notify_observers()

    def area(self) -> float:
        return 3.14159 * self._radius ** 2

    def perimeter(self) -> float:
        return 2 * 3.14159 * self._radius

class Rectangle(Shape):
    def __init__(self, width: float, height: float, color: str = 'black'):
        super().__init__(color)
        self.width = width
        self.height = height

    def area(self) -> float:
        return self.width * self.height

    def perimeter(self) -> float:
        return 2 * (self.width + self.height)

class Square(Rectangle):
    def __init__(self, side: float, color: str = 'black'):
        super().__init__(side, side, color)

    @property
    def side(self):
        return self.width

    @side.setter
    def side(self, value):
        self.width = value
        self.height = value

class Canvas:
    def __init__(self):
        self.shapes = []

    def add_shape(self, shape: Shape):
        if not isinstance(shape, Drawable):
            raise TypeError(f"{shape} is not Drawable")
        self.shapes.append(shape)

    def total_area(self) -> float:
        return sum(s.get_area() for s in self.shapes)

    def draw_all(self) -> list:
        return [s.draw() for s in self.shapes]

class ShapeFactory:
    _registry = {}

    @classmethod
    def register(cls, name: str, shape_class):
        cls._registry[name] = shape_class

    @classmethod
    def create(cls, name: str, **kwargs) -> Shape:
        if name not in cls._registry:
            raise ValueError(f"Unknown shape: {name}")
        return cls._registry[name](**kwargs)

ShapeFactory.register('circle', Circle)
ShapeFactory.register('rectangle', Rectangle)
ShapeFactory.register('square', Square)
```''', r'''<think>
Let me review this Python code for OOP design issues.

1. Liskov Substitution Principle violation:
- Square inherits from Rectangle. This is the classic LSP violation. A Square with width/height can have them set independently:
```python
sq = Square(5)
sq.width = 10  # Now width=10, height=5 -- it's no longer a square
```
- The side setter attempts to fix this by keeping width and height in sync, but setting width or height directly bypasses the setter and breaks the invariant.

2. Protocol vs ABC redundancy:
- Drawable is defined as a Protocol, and Shape is an ABC. Shape implements the Drawable protocol. But Canvas checks isinstance(shape, Drawable) using the runtime_checkable Protocol. This is confusing -- why not just check isinstance(shape, Shape)?
- runtime_checkable Protocol only checks method existence, not signatures. A class with draw() and get_area() methods that return different types would pass the check.

3. Observer pattern issues:
- _observers is a mutable list shared via reference. If someone does shape1._observers = shape2._observers, they share the same list.
- No way to remove observers. Once added, they cannot be unsubscribed.
- Only Circle.radius uses the observer pattern (notifies on set). Rectangle.width and Rectangle.height are plain attributes with no notification. Changing a rectangle's width does not notify observers -- inconsistent behavior.
- The observer pattern here is partially implemented and adds complexity without clear benefit.

4. Hardcoded pi:
- 3.14159 instead of math.pi. Loses precision and is not maintainable.

5. ShapeFactory:
- Uses a class variable _registry shared across all instances and subclasses. This is a global mutable state. In testing, registrations from one test can leak into another.
- No way to unregister shapes.
- No validation that registered classes are actually Shape subclasses.

6. Canvas:
- add_shape accepts Shape type hint but checks Drawable protocol at runtime. The type hint and runtime check are inconsistent.
- shapes list has no duplicate prevention.

Let me write the structured review.
</think>

## Code Review: Python OOP Shape System

### HIGH - Liskov Substitution Violation

**LSP1: Square extends Rectangle (Severity: HIGH)**
This is the classic LSP violation. Square inherits `width` and `height` as independent attributes from Rectangle. Direct assignment bypasses the side setter:
```python
sq = Square(5)
sq.width = 10  # width=10, height=5, no longer a square
```
The `side` property setter syncs both, but `width` and `height` setters do not. Any code that treats a Square as a Rectangle and modifies `width` alone breaks the square invariant.

Fix: Do not inherit Square from Rectangle. Make them siblings:
```python
class Square(Shape):
    def __init__(self, side: float, color: str = 'black'):
        super().__init__(color)
        self._side = side

    def area(self) -> float:
        return self._side ** 2

    def perimeter(self) -> float:
        return 4 * self._side
```

### HIGH - Inconsistent Observer Pattern

**OBS1: Notification only works on Circle (Severity: HIGH)**
`Circle.radius` is a property that calls `notify_observers()` on change. But `Rectangle.width` and `Rectangle.height` are plain attributes -- changing them does NOT notify observers. This is a trap for anyone who relies on the observer pattern for shape changes.

Either implement property-based notification on all mutable shapes, or remove the observer pattern entirely if it is not needed consistently.

**OBS2: No unsubscribe mechanism (Severity: MEDIUM)**
`add_observer` adds to the list, but there is no `remove_observer`. This leads to memory leaks (observers cannot be garbage collected) and unwanted notifications.

### MEDIUM - Protocol/ABC Redundancy

**PA1: Confusing Drawable Protocol alongside Shape ABC (Severity: MEDIUM)**
`Drawable` (Protocol) and `Shape` (ABC) define overlapping interfaces. Canvas type-hints `Shape` but runtime-checks `Drawable`. This is confusing:
- If only Shape subclasses are expected, just check `isinstance(shape, Shape)`
- If any Drawable is accepted, the type hint should be `Drawable`, not `Shape`
- `runtime_checkable` Protocol only checks method names exist, not that signatures match

Pick one approach. If you control all shape classes, use ABC. If you need structural typing for third-party classes, use Protocol.

### MEDIUM - Factory Design

**FD1: Global mutable registry (Severity: MEDIUM)**
`ShapeFactory._registry` is a class-level dict shared globally. Tests that register mock shapes leak state into other tests. No cleanup mechanism exists.

**FD2: No type validation on registration (Severity: LOW)**
```python
ShapeFactory.register('triangle', str)  # No error
ShapeFactory.create('triangle', x=1)  # Fails at runtime
```
Validate that the registered class is a Shape subclass:
```python
@classmethod
def register(cls, name: str, shape_class: type):
    if not issubclass(shape_class, Shape):
        raise TypeError(f"{shape_class} is not a Shape subclass")
    cls._registry[name] = shape_class
```

### LOW - Precision

**PR1: Hardcoded pi value (Severity: LOW)**
```python
return 3.14159 * self._radius ** 2
```
Use `math.pi` for full floating-point precision. The hardcoded value introduces rounding errors in calculations.

### LOW - Input Validation

**IV1: No validation on dimensions (Severity: LOW)**
Negative or zero radius, width, height are silently accepted. A circle with radius -5 has a positive area (25 * pi). Add validation:
```python
@radius.setter
def radius(self, value):
    if value <= 0:
        raise ValueError("Radius must be positive")
    self._radius = value
```'''),

    ("thinking/code-review", r'''Review this Python code and identify issues:

```python
class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

class DatabaseConnection(metaclass=Singleton):
    def __init__(self, host, port, database):
        self.host = host
        self.port = port
        self.database = database
        self.connection = None

    def connect(self):
        import psycopg2
        self.connection = psycopg2.connect(
            host=self.host, port=self.port, dbname=self.database
        )
        return self.connection

    def execute(self, query, params=None):
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()

class CachedProperty:
    def __init__(self, func):
        self.func = func
        self.attr_name = f'_cached_{func.__name__}'

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if not hasattr(obj, self.attr_name):
            setattr(obj, self.attr_name, self.func(obj))
        return getattr(obj, self.attr_name)

class ConfigManager:
    _config = {}

    @classmethod
    def load(cls, path):
        import json
        with open(path) as f:
            cls._config = json.load(f)

    @classmethod
    def get(cls, key, default=None):
        keys = key.split('.')
        value = cls._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value

class EventEmitter:
    def __init__(self):
        self._handlers = {}

    def on(self, event, handler):
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)

    def emit(self, event, *args, **kwargs):
        if event in self._handlers:
            for handler in self._handlers[event]:
                handler(*args, **kwargs)

    def off(self, event, handler=None):
        if handler is None:
            del self._handlers[event]
        else:
            self._handlers[event].remove(handler)

class Validator:
    def __init__(self):
        self.rules = {}

    def add_rule(self, field, rule_func, message):
        if field not in self.rules:
            self.rules[field] = []
        self.rules[field].append((rule_func, message))

    def validate(self, data):
        errors = {}
        for field, rules in self.rules.items():
            value = data.get(field)
            for rule_func, message in rules:
                if not rule_func(value):
                    if field not in errors:
                        errors[field] = []
                    errors[field].append(message)
        return errors if errors else None
```''', r'''<think>
Let me review these Python utility classes for design issues, edge cases, and anti-patterns.

1. Singleton metaclass:
- The Singleton metaclass is a well-known anti-pattern in modern Python. It creates global state, makes testing extremely difficult, and hides dependencies.
- The __init__ is only called on first instantiation. Subsequent calls return the cached instance BUT __init__ is NOT called again. So `DatabaseConnection('host1', 5432, 'db1')` followed by `DatabaseConnection('host2', 5433, 'db2')` returns the first instance with host1, silently ignoring the new parameters. This is a nasty, hard-to-debug issue.
- Thread safety: _instances dict is not protected. Two threads can both check `cls not in cls._instances` simultaneously and both create instances.

2. DatabaseConnection:
- Being a Singleton means it cannot be used with multiple databases.
- execute() calls fetchall() which fails for INSERT/UPDATE/DELETE queries that return no rows.
- No connection pooling, no context manager for transactions, no error handling.
- connect() creates a new connection but does not close an existing one.
- No close() method at all.

3. CachedProperty:
- This is a manual implementation of functools.cached_property which exists since Python 3.8. The manual implementation stores the cache as a separate attribute, which can be seen with hasattr/getattr and might confuse serialization.
- Not thread-safe. Two threads can call the func simultaneously and set the value twice.
- No invalidation mechanism.

4. ConfigManager:
- Uses class-level _config dict -- global mutable state. Cannot have multiple configurations simultaneously.
- Not thread-safe. load() and get() can race.
- The dot-notation get works but returns default for any intermediate None, which makes it impossible to distinguish between a key that does not exist and a key with value None.

5. EventEmitter:
- emit() calls handlers sequentially. If one handler raises, the remaining handlers are not called.
- off() with a handler that is not registered raises ValueError from list.remove.
- off() without handler deletes the event key, but del raises KeyError if event does not exist.
- No async support.
- No way to add one-time handlers.

6. Validator:
- validate() returns None on success, dict on failure. Inconsistent return type -- callers need to check for None explicitly. Better to return empty dict.
- rule_func receives None for missing fields. This means every rule must handle None, even if the rule is about string length or format.
- No short-circuit option -- all rules run even after a field fails the first check.

Let me structure the review.
</think>

## Code Review: Python Utility Classes

### HIGH - Singleton Anti-Pattern

**SA1: Silent parameter ignoring (Severity: HIGH)**
```python
db1 = DatabaseConnection('host1', 5432, 'db1')
db2 = DatabaseConnection('host2', 5433, 'db2')
db1 is db2  # True -- db2 has host1's config!
```
After first instantiation, `__init__` is never called again. All subsequent constructor calls with different parameters silently return the original instance. This is a very common and hard-to-debug issue.

**SA2: Untestable global state (Severity: HIGH)**
The Singleton metaclass shares state across all tests. You cannot create a fresh DatabaseConnection in tests without monkeypatching `Singleton._instances`. This pattern should be replaced with dependency injection:
```python
# Instead of Singleton, use a factory or DI container
def get_db_connection(config):
    return DatabaseConnection(config.host, config.port, config.database)
```

**SA3: Not thread-safe (Severity: MEDIUM)**
`_instances` dict is accessed without locking. Two threads can both evaluate `cls not in cls._instances` as True and both create instances.

### HIGH - DatabaseConnection

**DB1: execute() always calls fetchall() (Severity: HIGH)**
`cursor.fetchall()` fails for INSERT, UPDATE, DELETE, and DDL statements that do not return rows. Need to differentiate query types or provide separate methods:
```python
def execute(self, query, params=None):
    cursor = self.connection.cursor()
    cursor.execute(query, params)
    if cursor.description:  # has result set
        return cursor.fetchall()
    self.connection.commit()
    return cursor.rowcount
```

**DB2: No connection lifecycle management (Severity: HIGH)**
No `close()` method, no context manager, no connection pooling. The connection leaks when the object is garbage collected. No reconnection logic if the connection drops.

### MEDIUM - CachedProperty Reinvention

**CP1: Manual reimplementation of stdlib (Severity: MEDIUM)**
`functools.cached_property` exists since Python 3.8 and is thread-safe (using per-instance locking). This manual implementation stores values in separate attributes (`_cached_xxx`), which pollutes the object namespace and can confuse serialization or `__dict__` inspection. Use the stdlib version.

### MEDIUM - ConfigManager Global State

**CM1: Class-level _config prevents multiple configs (Severity: MEDIUM)**
One process can only have one configuration. This prevents having separate test and production configs simultaneously. Make it instance-based:
```python
class ConfigManager:
    def __init__(self, path=None):
        self._config = {}
        if path:
            self.load(path)
```

**CM2: None ambiguity in get() (Severity: LOW)**
`get('key.subkey')` returns `default` for both missing keys and keys with value `None`. Use a sentinel:
```python
_MISSING = object()
# ... check against _MISSING instead of None
```

### MEDIUM - EventEmitter Error Handling

**EE1: Exception in handler stops remaining handlers (Severity: MEDIUM)**
If one handler raises, subsequent handlers for the same event are never called. Wrap each handler call:
```python
def emit(self, event, *args, **kwargs):
    for handler in self._handlers.get(event, []):
        try:
            handler(*args, **kwargs)
        except Exception:
            logging.exception(f"Handler error for event {event}")
```

**EE2: off() raises on missing event/handler (Severity: MEDIUM)**
`del self._handlers[event]` raises KeyError if event was never registered. `list.remove(handler)` raises ValueError if handler is not found. Add defensive checks.

### LOW - Validator Return Type

**VR1: Inconsistent return type (Severity: LOW)**
`validate()` returns `dict` on failure and `None` on success. This forces callers to check for None. Return an empty dict on success for consistent typing:
```python
return errors  # always a dict, empty means valid
```'''),

    ("thinking/code-review", r'''Review this Python code and identify issues:

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
import json

class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class User:
    id: int
    name: str
    email: str
    roles: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'roles': self.roles,
            'metadata': self.metadata,
        }

@dataclass
class Ticket:
    id: int
    title: str
    description: str
    priority: Priority
    assignee: Optional[User] = None
    reporter: User = None
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    comments: List['Comment'] = field(default_factory=list)
    watchers: List[User] = field(default_factory=list)

    def assign(self, user: User):
        self.assignee = user
        self.updated_at = datetime.now()

    def add_comment(self, user: User, text: str):
        comment = Comment(
            id=len(self.comments) + 1,
            author=user,
            text=text,
        )
        self.comments.append(comment)
        self.updated_at = datetime.now()
        for watcher in self.watchers:
            notify_user(watcher, f"New comment on {self.title}")

    def escalate(self):
        priorities = list(Priority)
        idx = priorities.index(self.priority)
        if idx < len(priorities) - 1:
            self.priority = priorities[idx + 1]
        self.updated_at = datetime.now()

    def to_json(self) -> str:
        return json.dumps({
            'id': self.id,
            'title': self.title,
            'priority': self.priority.value,
            'assignee': self.assignee.to_dict() if self.assignee else None,
            'reporter': self.reporter.to_dict() if self.reporter else None,
            'tags': self.tags,
            'created_at': str(self.created_at),
            'comments': [c.to_dict() for c in self.comments],
        })

@dataclass
class Comment:
    id: int
    author: User
    text: str
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'author': self.author.to_dict(),
            'text': self.text,
            'created_at': str(self.created_at),
        }

class TicketBoard:
    def __init__(self):
        self.tickets: List[Ticket] = []

    def create_ticket(self, **kwargs) -> Ticket:
        ticket = Ticket(id=len(self.tickets) + 1, **kwargs)
        self.tickets.append(ticket)
        return ticket

    def find_by_priority(self, priority: Priority) -> List[Ticket]:
        return [t for t in self.tickets if t.priority == priority]

    def find_by_assignee(self, user: User) -> List[Ticket]:
        return [t for t in self.tickets if t.assignee == user]

    def get_stats(self) -> dict:
        stats = {}
        for p in Priority:
            stats[p.name] = len(self.find_by_priority(p))
        return stats
```''', r'''<think>
Let me review this dataclass-based ticket system.

1. Default value issues:
- `reporter: User = None` -- this is a mutable default without using field(default_factory=...). Actually, None is immutable so this is fine technically, but the type hint says User (not Optional[User]), so the type is wrong.
- created_at and updated_at use `field(default_factory=datetime.now)`. This uses local time, not UTC. Different servers in different timezones create inconsistent timestamps.

2. ID generation:
- `id=len(self.tickets) + 1` in TicketBoard and `id=len(self.comments) + 1` in add_comment. If tickets are deleted, IDs can collide. The IDs are not globally unique. This is a fragile pattern.

3. Notification side effect in add_comment:
- `notify_user(watcher, ...)` is called inside add_comment. This is a side effect that makes the method hard to test and impossible to use without the notification system being available. Should be decoupled via an event system.

4. Serialization issues:
- Manual to_dict() and to_json() methods duplicate the dataclass field list. If a field is added, all serialization methods must be updated. Use dataclasses.asdict() or a proper serialization library.
- to_json uses str(self.created_at) which produces a non-standard datetime format.
- description is omitted from to_json -- is this intentional?

5. Equality and comparison:
- Dataclasses auto-generate __eq__ based on all fields. Two Tickets with the same id but different comments are not equal. This might be unexpected. For domain objects, equality is usually based on id alone.
- User equality compares all fields including mutable roles and metadata. Two User objects with the same id but different roles are not equal.

6. find_by_assignee uses equality:
- `t.assignee == user` uses dataclass equality. If the User object has been modified since assignment (e.g., a role was added), the comparison may fail even though it's the same user.

7. get_stats:
- Calls find_by_priority for each priority, iterating the entire list 4 times. Could be done in a single pass.

8. Missing features:
- No validation (empty title, None reporter)
- No immutability on fields that should not change (id, created_at)
- Ticket watchers can contain duplicates

Let me structure the review.
</think>

## Code Review: Dataclass Ticket System

### HIGH - Type Annotation Error

**TA1: reporter default is None but type is User (Severity: HIGH)**
```python
reporter: User = None
```
The type says `User` but the default is `None`. This should be `Optional[User] = None`. Static type checkers (mypy, pyright) will flag this. More importantly, code like `self.reporter.to_dict()` will crash if reporter is None.

### HIGH - Identity vs Equality

**IE1: Dataclass equality based on all fields (Severity: HIGH)**
Dataclasses auto-generate `__eq__` comparing all fields. For domain objects like User and Ticket, identity should be based on `id` alone:
```python
@dataclass
class User:
    id: int
    name: str
    # ...

    def __eq__(self, other):
        if not isinstance(other, User):
            return NotImplemented
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)
```

Without this, `find_by_assignee` fails if the User object has been modified since assignment (e.g., a role was added), because the modified User no longer equals the stored assignee.

### HIGH - Fragile ID Generation

**ID1: Sequential IDs based on list length (Severity: HIGH)**
```python
id=len(self.tickets) + 1  # in TicketBoard
id=len(self.comments) + 1  # in add_comment
```
If a ticket or comment is removed, the next insert reuses a previous ID. With concurrent access, two calls to create_ticket can produce the same ID. Use UUID or an auto-incrementing counter:
```python
import itertools
_counter = itertools.count(1)

id=next(_counter)
```

### MEDIUM - Side Effects in Domain Logic

**SE1: Notification in add_comment (Severity: MEDIUM)**
```python
def add_comment(self, user, text):
    # ...
    for watcher in self.watchers:
        notify_user(watcher, ...)
```
This couples comment creation to the notification system. Testing add_comment requires mocking notify_user. If the notification service is slow, adding a comment is slow. Decouple via events or callbacks:
```python
def add_comment(self, user, text):
    comment = Comment(...)
    self.comments.append(comment)
    self.updated_at = datetime.now()
    return comment  # caller handles notification
```

### MEDIUM - Serialization

**SR1: Manual to_dict/to_json duplicates field lists (Severity: MEDIUM)**
Adding a field to the dataclass requires updating to_dict and to_json manually. Use `dataclasses.asdict()`:
```python
from dataclasses import asdict

def to_dict(self):
    return asdict(self)
```
Note: asdict recursively converts nested dataclasses. Customize with a custom encoder if needed.

**SR2: Missing description in to_json (Severity: MEDIUM)**
`Ticket.to_json()` omits the `description` field. This may be a bug.

### MEDIUM - Timestamp Issues

**TS1: Local time instead of UTC (Severity: MEDIUM)**
`datetime.now()` uses the server's local timezone. Different servers produce inconsistent timestamps. Use `datetime.utcnow()` or `datetime.now(timezone.utc)`.

### LOW - Performance

**P1: get_stats iterates list 4 times (Severity: LOW)**
```python
for p in Priority:
    stats[p.name] = len(self.find_by_priority(p))
```
Four complete iterations. Single pass:
```python
from collections import Counter
stats = Counter(t.priority.name for t in self.tickets)
```

### LOW - Duplicate Watchers

**DW1: No dedup on watchers list (Severity: LOW)**
`watchers: List[User]` allows the same user to be added multiple times, receiving duplicate notifications. Use a set (requires __hash__ on User).'''),

    ("thinking/code-review", r'''Review this Python code and identify issues:

```python
import logging
from typing import Any, Callable, Dict, Type
from functools import wraps

class PluginMeta(type):
    registry: Dict[str, Type] = {}

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        if name != 'Plugin':
            mcs.registry[name] = cls
        return cls

class Plugin(metaclass=PluginMeta):
    name: str = ''
    version: str = '0.0.0'
    dependencies: list = []

    def setup(self):
        pass

    def teardown(self):
        pass

    def execute(self, *args, **kwargs):
        raise NotImplementedError

class AuthPlugin(Plugin):
    name = 'auth'
    version = '1.0.0'

    def execute(self, request):
        token = request.get('token')
        if not token:
            return {'error': 'no token'}
        return {'user_id': decode_token(token)}

class CachePlugin(Plugin):
    name = 'cache'
    version = '1.0.0'
    dependencies = ['auth']

    def __init__(self):
        self.cache = {}

    def execute(self, key, value=None):
        if value is not None:
            self.cache[key] = value
        return self.cache.get(key)

class LogPlugin(Plugin):
    name = 'log'
    version = '1.0.0'

    def execute(self, message, level='info'):
        getattr(logging, level)(message)

class PluginManager:
    def __init__(self):
        self.plugins = {}
        self.load_order = []

    def load_all(self):
        for name, cls in PluginMeta.registry.items():
            plugin = cls()
            self.plugins[plugin.name] = plugin

        for plugin in self.plugins.values():
            for dep in plugin.dependencies:
                if dep not in self.plugins:
                    raise RuntimeError(f"Missing dependency: {dep}")

        for plugin in self.plugins.values():
            plugin.setup()
            self.load_order.append(plugin.name)

    def get(self, name):
        return self.plugins[name]

    def execute(self, name, *args, **kwargs):
        return self.plugins[name].execute(*args, **kwargs)

    def unload_all(self):
        for name in self.load_order:
            self.plugins[name].teardown()
        self.plugins.clear()
        self.load_order.clear()

def plugin_hook(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        manager = PluginManager()
        manager.load_all()
        kwargs['plugins'] = manager
        try:
            result = func(*args, **kwargs)
        finally:
            manager.unload_all()
        return result
    return wrapper
```''', r'''<think>
Let me review this plugin system for metaclass usage, design issues, and correctness.

1. Metaclass overuse:
- PluginMeta metaclass is used purely for auto-registration. This is a common overuse of metaclasses. The same could be achieved with __init_subclass__:
```python
class Plugin:
    _registry = {}
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        Plugin._registry[cls.__name__] = cls
```
- Metaclasses add complexity and can conflict with other metaclasses.

2. Mutable class-level default:
- `dependencies: list = []` is a mutable class-level default. All Plugin subclasses that do not override dependencies share the same list object. If one modifies it (e.g., self.dependencies.append('x')), all plugins see the change. CachePlugin overrides it with a new list, so it's fine for CachePlugin, but other plugins that don't override will share the base Plugin's list.

3. Global registry:
- PluginMeta.registry is a class-level dict shared globally. In testing, importing any module that defines a Plugin subclass adds it to the registry. There is no way to isolate or reset the registry between tests.
- If two plugins have the same class name but different module paths, one overwrites the other in the registry.

4. Plugin loading:
- load_all loads plugins from registry using class name as key but stores them using plugin.name attribute. These can be different (class name "CachePlugin" vs name "cache"). The dependency check uses plugin.name, so dependencies must use the name attribute, not the class name. This is confusing.
- Dependency ordering is not enforced. Plugins are loaded in arbitrary dict iteration order. If CachePlugin depends on AuthPlugin, AuthPlugin's setup() should run first, but there is no topological sort.
- Circular dependencies are not detected -- they would cause infinite loops if ordering were enforced.

5. plugin_hook decorator:
- Creates a new PluginManager and loads all plugins on EVERY function call. This is extremely wasteful -- plugin initialization is repeated for every decorated function invocation.
- The manager is not shared between functions, so plugins cannot maintain state across calls.

6. Unload order:
- unload_all teardowns in load_order (forward order), but typically teardown should be in reverse order (dependencies torn down last).

7. CachePlugin:
- Uses a plain dict as cache. No TTL, no size limit, no thread safety. Memory grows unbounded.
- The cache is per-instance, but plugin_hook creates a new instance per call, so the cache is always empty.

Let me write the review.
</think>

## Code Review: Python Plugin System

### HIGH - Metaclass Overuse

**MC1: Metaclass used only for auto-registration (Severity: HIGH)**
`PluginMeta` exists solely to register subclasses. This is a common metaclass overuse. Since Python 3.6, `__init_subclass__` achieves the same result without metaclass complexity or potential conflicts:
```python
class Plugin:
    _registry: dict = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__name__ != 'Plugin':
            Plugin._registry[cls.__name__] = cls
```
Metaclasses should be reserved for cases that truly need to customize class creation (modifying the namespace, intercepting attribute definitions, etc.).

### HIGH - No Dependency Ordering

**DO1: Plugins loaded in arbitrary order (Severity: HIGH)**
`load_all` iterates `PluginMeta.registry.items()` (arbitrary order) and calls `setup()` on each plugin. CachePlugin declares a dependency on AuthPlugin, but there is no guarantee AuthPlugin.setup() runs first. If setup() has initialization that depends on another plugin being ready, this fails silently.

Fix with topological sort:
```python
def _resolve_load_order(self):
    # Build dependency graph and topologically sort
    visited = set()
    order = []
    def visit(name):
        if name in visited:
            return
        visited.add(name)
        plugin = self.plugins[name]
        for dep in plugin.dependencies:
            visit(dep)
        order.append(name)
    for name in self.plugins:
        visit(name)
    return order
```

### HIGH - Mutable Class-Level Default

**MD1: Shared mutable dependencies list (Severity: HIGH)**
```python
class Plugin(metaclass=PluginMeta):
    dependencies: list = []
```
All subclasses that do not explicitly override `dependencies` share the same list object. Appending to `self.dependencies` in one plugin modifies all of them. Use a tuple or override in each subclass:
```python
dependencies: tuple = ()
```

### MEDIUM - Global Registry Problems

**GR1: Global registry leaks across tests (Severity: MEDIUM)**
`PluginMeta.registry` is populated at class definition time (import time). There is no way to reset it between tests. Importing a module with a Plugin subclass permanently adds it to the registry.

**GR2: Class name collision (Severity: MEDIUM)**
Registry keys are class names, not fully qualified names. Two modules defining `class CachePlugin(Plugin)` collide, with the second overwriting the first silently.

### MEDIUM - plugin_hook Performance

**PH1: Plugins reloaded on every function call (Severity: MEDIUM)**
```python
@plugin_hook
def my_function(plugins=None):
    plugins.get('cache').execute('key')
```
Every invocation of `my_function` creates a new PluginManager, instantiates all plugins, and runs all setup methods. This is wasteful and prevents plugins from maintaining state across calls. The CachePlugin's cache is always empty because it is recreated each time.

### MEDIUM - Teardown Order

**TO1: Teardown in wrong order (Severity: MEDIUM)**
`unload_all` teardowns in forward load order. Dependencies should be torn down in reverse order -- dependents first, then their dependencies:
```python
def unload_all(self):
    for name in reversed(self.load_order):
        self.plugins[name].teardown()
```

### LOW - Name Confusion

**NC1: Registry uses class name, plugins dict uses name attribute (Severity: LOW)**
Registry key: `"CachePlugin"`. Plugins dict key: `"cache"`. Dependencies reference: `"auth"`. Three different naming schemes for the same concept. Pick one and use it consistently.'''),
]
