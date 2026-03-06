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
Let me look at this class hierarchy. Animal at the top, Dog/Cat/Bird inheriting from it, then ServiceDog from Dog, and GuideDog/TherapyDog/PoliceDog from ServiceDog. That's 4 levels deep already.

My first instinct is that this inheritance is too deep, but let me think about whether each level actually adds meaningful behavior... Animal defines the basics (name, species, sound). Dog adds breed and tricks. ServiceDog adds handler and certifications. GuideDog adds route_knowledge. Each level does add something, but the deeper levels feel forced -- is a GuideDog really a fundamentally different type from a ServiceDog? The difference is mostly in configuration (service_type='guide', route_knowledge) rather than behavior.

The bigger issue is the string-typed behavior in the base class. eat() switches on self.diet being 'herbivore', 'carnivore', or 'omnivore'. This is a code smell -- you could refactor to polymorphism. But wait, would I really create a HerbivoreAnimal subclass? That crosses the inheritance dimension (species vs diet), creating a combinatorial explosion. So actually, string-based switching is reasonable here. However, there's no else clause -- if diet is anything unexpected, eat() returns None silently. Same with describe_habitat().

Looking at the constructor chain... GuideDog.__init__ calls super().__init__ with handler, which calls ServiceDog.__init__ with breed, which calls Dog.__init__ with name/breed/is_trained, which calls Animal.__init__ with 5 params. To create a GuideDog, you need to understand the entire chain. That's a lot of mental overhead.

I think the real problem is that "service capability" should be composition, not inheritance. A dog might stop being a service dog. A service dog might change handlers. These are roles, not identities. A ServiceCapability object composed into Dog would be much more flexible.

AnimalShelter has three nearly identical find methods -- find_by_species, find_by_diet, find_by_habitat. That's a DRY violation. Could be a single method: `find_by(attr, value)` or even better, a generic filter with keyword args.

Also missing: no __repr__ or __str__ (printing an Animal gives you `<Animal object at 0x...>`), no __eq__ (can't compare animals meaningfully), no way to remove animals from the shelter, and no input validation anywhere.

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
OK, let me work through these classes. There's a Shape hierarchy with Drawable protocol, Observer pattern, and a factory. Let me start with what catches my eye first.

Square inherits from Rectangle. This is the textbook Liskov Substitution Principle violation, but let me verify it actually causes problems here... A Square sets both width and height in __init__. But width and height are just regular attributes on Rectangle. So:
```python
sq = Square(5)
sq.width = 10  # sets width to 10, but height stays 5
```
Now the "square" has different width and height. The Square.side property setter tries to keep them in sync, but nothing prevents direct attribute access. So any code that takes a Rectangle and sets width independently will break a Square's invariant. Classic LSP.

Now the typing setup is interesting but confusing. Drawable is a Protocol (structural typing), Shape is an ABC (nominal typing). Shape happens to implement the Drawable protocol. Canvas.add_shape type-hints for Shape but does an isinstance check against Drawable at runtime. These are different checks -- the type hint says "must inherit from Shape" but the runtime check says "must have draw() and get_area() methods". A class that implements Drawable but doesn't inherit from Shape would fail the type hint but pass the runtime check. Inconsistent.

Also, runtime_checkable Protocol only verifies method existence, not signatures. A class with `draw(self, color)` (different signature) would pass the Drawable check. That's a known limitation but still a gotcha.

The Observer pattern is partially implemented and that bothers me. Circle notifies observers when radius changes via the @radius.setter. But Rectangle.width and Rectangle.height are plain attributes -- no setter, no notification. So observers watching a Rectangle get notified of... nothing? If you resize a rectangle, observers are never told. That's really inconsistent behavior.

Also, _observers is a list with no removal method. Once you subscribe, you can never unsubscribe. In a long-running application, that's a memory leak -- every observer is kept alive by the reference in the list.

Hardcoded pi=3.14159 instead of math.pi is a minor but real precision loss.

ShapeFactory uses a class-level _registry dict. That's global mutable state -- in tests, registrations leak between test cases. And there's no validation that the registered class actually IS a Shape subclass. You could register `int` as a "shape" and get a confusing error later when someone tries to use it.

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
Let me go through these utility classes one at a time. Starting with the Singleton metaclass...

The Singleton pattern stores instances in a class-level _instances dict, keyed by class. First call creates the instance, subsequent calls return the cached one. But here's a subtle and nasty bug: __init__ is only called on the first instantiation. So `DatabaseConnection('host1', 5432, 'db1')` creates and caches the instance. Then `DatabaseConnection('host2', 5433, 'db2')` returns the FIRST instance, silently ignoring 'host2', 5433, and 'db2'. The caller thinks they have a connection to host2, but they're actually using host1. This is a classic Singleton trap that leads to incredibly hard-to-debug issues.

And it's not thread-safe. Two threads can both check `cls not in cls._instances`, both see True, both create instances, and one overwrites the other. So much for "Singleton."

Looking at DatabaseConnection itself -- being a Singleton means you can never connect to two databases simultaneously. execute() always calls fetchall(), which fails for INSERT/UPDATE/DELETE statements that return no rows. connect() creates a new connection but doesn't close the existing one -- connection leak. And there's no close() method at all.

CachedProperty... hmm, this is a manual reimplementation of functools.cached_property which has existed since Python 3.8. The manual version works but stores the cache as a regular attribute (f"_cached_{self.func.__name__}"), which could confuse serialization or show up in vars(). It's also not thread-safe -- two threads can both see the attribute missing and both call the function. And there's no way to invalidate the cache.

ConfigManager uses a class-level _config dict -- global mutable state, can't have multiple configurations. The dot-notation get is clever: `config.get('database.host')` walks the nested dict. But if any intermediate key doesn't exist, it returns the default. You can't distinguish between "key doesn't exist" and "key exists with value None." Not thread-safe either -- load() and get() can race.

EventEmitter has several edge cases. emit() calls handlers sequentially -- if one raises, the rest don't run. off() with an unregistered handler raises ValueError from list.remove(). off() without a handler tries to del the event key, but raises KeyError if the event doesn't exist. These error cases should be handled gracefully.

Validator.validate() returns None on success and a dict on failure. Inconsistent return type. Callers have to do `if result is not None` instead of just checking `if result`. Should return an empty dict on success for consistency. And rule functions receive None for missing fields -- every rule has to handle None even if it's checking string length or format.

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
This is a ticket system built with dataclasses. Let me look at the data model first, then the operations.

Starting with the User dataclass -- `roles: list = field(default_factory=list)` is correct for mutable defaults. Good. But `metadata: dict = field(default_factory=dict)` means every User gets a fresh empty dict, which is fine but raises the question: what goes in metadata? If it's arbitrary key-value pairs, it's a schema smell.

For Ticket, I see `reporter: User = None`. The type hint says User but the default is None -- so the actual type is Optional[User], but that's not declared. More importantly, `created_at` and `updated_at` use `field(default_factory=datetime.now)`. That's local time, not UTC. If this system runs across servers in different timezones, timestamps are inconsistent and uncomparable.

The ID generation bothers me. `id=len(self.tickets) + 1` in TicketBoard's create_ticket. What happens if ticket #3 is deleted and then a new ticket is created? len(self.tickets) is back to, say, 4 after the deletion, so the new ticket gets id=5. Wait, actually if there were 5 tickets and #3 was deleted, len is 4, new id is 5. But what if #5 already exists? Then we have a collision. Actually... looking more carefully, there's no delete method. But the same logic applies to comments: `id=len(self.comments) + 1`. IDs should be monotonically increasing, not based on current count.

add_comment has a side effect that concerns me: it calls notify_user() for every watcher. That's I/O happening inside what looks like a simple data operation. This makes the method hard to test (you need to mock the notification system) and impossible to use in contexts where notifications aren't desired (data migration, batch processing). Should be decoupled via events or a separate notification step.

The serialization methods (to_dict, to_json) manually list fields. If someone adds a field to the Ticket dataclass, they have to remember to update both to_dict and to_json. Use dataclasses.asdict() instead. Also, to_json uses str(self.created_at) which produces Python's default datetime string representation, not ISO 8601. And description is omitted from to_json -- is that intentional or a bug? Hard to tell.

Dataclass equality is based on ALL fields by default. So two Tickets with the same id but different comments are not equal. For domain objects, equality should typically be based on the identity field (id) alone. Similarly, find_by_assignee compares User objects, but if the User has been modified since assignment (role added, metadata changed), the comparison fails even though it's the "same" user.

get_stats iterates the entire ticket list 4 times (once per priority level via find_by_priority). Could be done in a single pass with a Counter.

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
Let me trace through this plugin system. There's a PluginMeta metaclass, a Plugin base class, a PluginManager, and a plugin_hook decorator.

First question: is the metaclass necessary? PluginMeta.__new__ just adds the class to a registry dict. This could be done with __init_subclass__, which was added in Python 3.6 specifically to reduce metaclass usage:
```python
class Plugin:
    _registry = {}
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        Plugin._registry[cls.__name__] = cls
```
Metaclasses should be reserved for cases where __init_subclass__ isn't sufficient, like modifying the class creation process itself. Using a metaclass here adds complexity and can conflict with other metaclasses if a plugin needs multiple inheritance.

Now I notice something concerning about the Plugin base class. `dependencies: list = []` is a class-level mutable default. All Plugin subclasses that don't override it share the SAME list object. If any plugin does `self.dependencies.append('something')`, every plugin sees that change. CachePlugin defines its own `dependencies = ['auth']`, so it gets a fresh list. But any plugin that relies on the default shares the base class's empty list. This is a classic Python mutable-default-at-class-level bug.

The registry is also problematic. It's a global dict keyed by class name. If two plugins in different modules happen to have the same class name, one silently overwrites the other. No warning, no error -- just lost functionality.

Let me look at the PluginManager's load_all method. It loads plugins from the registry using class name as key but stores them in self.plugins using plugin.name as key. These can differ -- CachePlugin's class name is "CachePlugin" but its name attribute is "cache". The dependency check uses plugin.name, so dependencies must reference the name attribute. This naming mismatch is confusing and error-prone.

Wait, there's a more fundamental problem. load_all iterates the registry in arbitrary order (dict iteration order). If CachePlugin depends on AuthPlugin, but CachePlugin happens to be loaded first, the dependency check fails because AuthPlugin isn't in self.plugins yet. There's no topological sort. And if there are circular dependencies, there's no detection -- it would just silently fail or give confusing results.

The plugin_hook decorator creates a new PluginManager and calls load_all on EVERY function invocation. That means every decorated function call initializes all plugins from scratch. This is wildly inefficient and means plugins can't maintain state between calls -- the CachePlugin's dict-based cache is recreated empty every time, making it completely useless.

unload_all tears down in forward load order, but teardown should typically happen in reverse order so dependencies are torn down last. If CachePlugin depends on AuthPlugin, tearing down AuthPlugin before CachePlugin could leave CachePlugin in a broken state during its own teardown.

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
