"""
Anti-pattern training pairs - Architecture anti-patterns
Topics: god objects, circular deps, premature abstraction, wrong patterns, over-engineering
"""

pairs = [
    {
        "instruction": r'''Our codebase has a Utils class that everyone imports. It keeps growing:

```python
class Utils:
    @staticmethod
    def format_date(dt): ...
    @staticmethod
    def send_email(to, body): ...
    @staticmethod
    def validate_credit_card(number): ...
    @staticmethod
    def resize_image(img, width, height): ...
    @staticmethod
    def calculate_tax(amount, state): ...
    @staticmethod
    def parse_csv(filepath): ...
    @staticmethod
    def encrypt_password(password): ...
    @staticmethod
    def generate_invoice_pdf(order): ...
    @staticmethod
    def geocode_address(address): ...
    @staticmethod
    def sanitize_html(text): ...
    # ... 50 more methods
```

It's convenient because you just import Utils and everything is there.''',
        "output": r'''<think>
God object / utility class anti-pattern. This class has no cohesion -- it groups unrelated functionality (dates, email, images, taxes, crypto, PDFs, geocoding) into one dumping ground. It grows forever, creates a dependency bottleneck, and makes it impossible to understand what any part of the system actually needs. The "convenience" argument is the trap.
</think>

This is called a "God Object" or "junk drawer" class. It has zero cohesion -- credit card validation, image resizing, and geocoding have nothing in common.

**Why it hurts:**
- **Every module depends on Utils.** A change to `resize_image` could break `validate_credit_card` tests because they share the same import.
- **It only grows.** Nobody creates a new module when Utils already exists -- they just add another method. In a year it is 200 methods.
- **Unclear dependencies.** When a module imports Utils, you cannot tell which of the 50 methods it actually uses. Does the payment module really need image resizing?
- **Cannot be decomposed later.** With 50 callers importing `Utils.format_date`, renaming is a massive effort.

**The fix -- split by domain:**

```python
# dates.py
def format_date(dt): ...

# email.py
def send_email(to, body): ...

# payments/validation.py
def validate_credit_card(number): ...

# images.py
def resize_image(img, width, height): ...

# tax.py
def calculate_tax(amount, state): ...
```

Now each module imports only what it needs:

```python
# Before -- opaque dependency
from utils import Utils
Utils.send_email(to, body)

# After -- clear dependency
from email_service import send_email
send_email(to, body)
```

**The test for cohesion:** Can you describe what the class does in one sentence without using "and"? "Formats dates AND sends email AND validates credit cards AND resizes images" is a red flag. Each module should have one reason to exist.'''
    },
    {
        "instruction": r'''My project structure has these imports and it works fine:

```python
# models/user.py
from services.auth import hash_password

class User:
    def set_password(self, raw):
        self.password_hash = hash_password(raw)

# services/auth.py
from models.user import User

def authenticate(username, password):
    user = User.query.filter_by(username=username).first()
    return verify(user.password_hash, password)

# services/notifications.py
from models.user import User
from services.auth import get_current_user

def notify_all():
    user = get_current_user()
    ...
```''',
        "output": r'''<think>
Circular dependency: models.user imports from services.auth, and services.auth imports from models.user. This works in Python only by accident (due to import timing), but it creates fragile code that breaks with reorganization, prevents clear layering, and makes the dependency graph unmaintainable. The fix is to break the cycle by separating concerns -- models should not depend on services.
</think>

You have a circular dependency: `models.user` imports from `services.auth`, and `services.auth` imports from `models.user`. This works in Python only because of import timing -- if you change the import order or refactor, it will break with an `ImportError` or `AttributeError`.

**Why circular deps are harmful:**
- **Fragile imports.** Moving code between files or changing import style (from relative to absolute) causes mysterious failures.
- **No clear layering.** Models depend on services, which depend on models. There is no "bottom" of the stack -- you cannot understand either module in isolation.
- **Testing requires loading everything.** You cannot test `User` without loading the auth service, which loads `User` again.

**The fix -- enforce one-way dependencies:**

```
models --> (nothing, or other models)
services --> models (never the reverse)
```

Remove the dependency from `models.user` on `services.auth`:

```python
# models/user.py -- NO service imports
class User:
    def set_password(self, raw, hasher):
        """Accept hasher as a parameter instead of importing it."""
        self.password_hash = hasher(raw)

# services/auth.py -- imports models (one direction)
from models.user import User

def hash_password(raw):
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt())

def create_user(username, raw_password):
    user = User(username=username)
    user.set_password(raw_password, hash_password)
    return user

def authenticate(username, password):
    user = User.query.filter_by(username=username).first()
    return verify(user.password_hash, password)
```

Now models are self-contained. Services depend on models, but never the reverse. The dependency graph is a tree, not a tangle.'''
    },
    {
        "instruction": r'''I want to make my code flexible for the future, so I'm adding abstractions early:

```python
class IDataSource(ABC):
    @abstractmethod
    def fetch(self): pass

class IDataTransformer(ABC):
    @abstractmethod
    def transform(self, data): pass

class IDataSink(ABC):
    @abstractmethod
    def write(self, data): pass

class CSVDataSource(IDataSource):
    def fetch(self):
        return pd.read_csv("data.csv")

class PassthroughTransformer(IDataTransformer):
    def transform(self, data):
        return data  # no-op for now

class PrintSink(IDataSink):
    def write(self, data):
        print(data)

class DataPipeline:
    def __init__(self, source: IDataSource, transformer: IDataTransformer, sink: IDataSink):
        self.source = source
        self.transformer = transformer
        self.sink = sink

    def run(self):
        data = self.source.fetch()
        transformed = self.transformer.transform(data)
        self.sink.write(transformed)
```

I only have one data source right now, but this way I'm prepared for more.''',
        "output": r'''<think>
Premature abstraction. The user created 3 abstract base classes, 3 concrete implementations (one of which is a no-op), and a pipeline class -- all for reading a CSV and printing it. They have one data source and are "preparing" for more. This is speculative generality -- building flexibility for requirements that may never come. The code is 10x more complex than needed for zero current benefit.
</think>

You wrote 7 classes to read a CSV and print it. Here is what you actually need right now:

```python
import pandas as pd

data = pd.read_csv("data.csv")
print(data)
```

That is two lines versus seven classes, three abstract interfaces, and a `PassthroughTransformer` that literally does nothing.

**Why premature abstraction hurts:**
- **You are guessing future requirements.** When you do need a second data source, it probably will not fit the `IDataSource.fetch()` interface. Maybe it needs authentication, pagination, or streaming. Your abstraction will need to change anyway.
- **More code to read and maintain.** Every developer must understand the class hierarchy to follow a two-line operation.
- **Wrong abstractions are worse than no abstractions.** Once other code depends on `IDataSource`, changing it is a breaking change. You have locked yourself into a guess.

**The Rule of Three:** Don't abstract until you have three concrete cases. With one case, just write the code directly. With two, look for patterns. With three, you have enough information to design a good abstraction.

**When you actually get a second source:**

```python
# Now you have a reason to abstract
def run_pipeline(fetch_fn, transform_fn=None):
    data = fetch_fn()
    if transform_fn:
        data = transform_fn(data)
    return data

# Simple functions, no class hierarchy needed
run_pipeline(lambda: pd.read_csv("data.csv"))
run_pipeline(lambda: fetch_from_api("/data"), clean_data)
```

Functions are often sufficient. You don't need an abstract class hierarchy for everything.'''
    },
    {
        "instruction": r'''I used the Singleton pattern for my database connection, logger, and config in my Flask app:

```python
class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.conn = psycopg2.connect(DATABASE_URL)
        return cls._instance

class Logger:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.setup_handlers()
        return cls._instance

class Config:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.load_from_env()
        return cls._instance
```''',
        "output": r'''<think>
Singleton anti-pattern (or at least misuse). In Python, singletons are rarely needed -- modules are already singletons. These singletons create global mutable state, make testing extremely difficult (can't substitute a test database), create hidden dependencies, and are not thread-safe as written. Flask already has patterns for this (app context, config). The user is applying a design pattern where simpler Python idioms work better.
</think>

The Singleton pattern is almost never the right choice in Python. You have three problems here.

**Problem 1: Hidden global state.** Any function can call `Database()` and get the shared instance. You cannot tell from a function's signature that it uses the database -- the dependency is invisible.

**Problem 2: Testing is painful.** You cannot swap in a test database:

```python
def test_create_user():
    # This ALWAYS uses the production database
    # because Database() returns the singleton
    service = UserService()
    service.create_user("test")  # writes to prod DB!
```

**Problem 3: Not thread-safe.** Two threads calling `Database()` simultaneously can both see `_instance is None` and create two connections. You would need locks, which adds complexity.

**The fix -- just use modules and dependency injection:**

```python
# database.py -- module-level is already a singleton
import psycopg2
from config import DATABASE_URL

def create_connection():
    return psycopg2.connect(DATABASE_URL)

# app.py -- Flask has built-in patterns for this
from flask import Flask, g

app = Flask(__name__)

def get_db():
    if 'db' not in g:
        g.db = create_connection()
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# services.py -- explicit dependencies
class UserService:
    def __init__(self, db_conn):
        self.db = db_conn  # injected, testable

# test
def test_create_user():
    test_db = create_test_connection()
    service = UserService(test_db)  # easy to test
```

Python modules are already singletons (imported once, cached in `sys.modules`). You do not need a class to achieve "only one instance." For config, use `app.config`. For logging, use `logging.getLogger()` (already a singleton internally).'''
    },
    {
        "instruction": r'''I'm building a simple todo app for a hackathon. Here's my architecture:

```
todo-app/
  src/
    domain/
      entities/
        TodoItem.ts
        TodoList.ts
      value-objects/
        Priority.ts
        DueDate.ts
      repositories/
        ITodoRepository.ts
      services/
        TodoDomainService.ts
    application/
      use-cases/
        CreateTodo.ts
        CompleteTodo.ts
        DeleteTodo.ts
        ListTodos.ts
      dto/
        CreateTodoDTO.ts
        TodoResponseDTO.ts
      mappers/
        TodoMapper.ts
    infrastructure/
      persistence/
        InMemoryTodoRepository.ts
      web/
        TodoController.ts
        TodoRouter.ts
    shared/
      Result.ts
      Guard.ts
      UniqueID.ts
```

I'm following Clean Architecture / DDD. Is this the right approach?''',
        "output": r'''<think>
Massive over-engineering for a hackathon todo app. The user has 20+ files across 4 layers for what could be a single file with a list and a few routes. Clean Architecture and DDD have their place, but applying them to a todo app (especially at a hackathon where speed matters) is the wrong pattern for the context. The abstraction layers add zero value when you have one entity and CRUD operations.
</think>

For a hackathon todo app, this is extreme over-engineering. You have 20+ files, 4 architectural layers, DTOs, mappers, value objects, and a domain service -- for a list of strings with checkboxes.

**What this architecture is designed for:** Large teams working on complex business domains over years, where the cost of the abstraction pays off through independent deployability and team autonomy.

**What you are building:** A todo app at a hackathon, where you need to ship in hours.

**A todo app needs one file:**

```typescript
import express from 'express';

const app = express();
app.use(express.json());

interface Todo {
    id: number;
    text: string;
    done: boolean;
}

let todos: Todo[] = [];
let nextId = 1;

app.get('/todos', (req, res) => res.json(todos));

app.post('/todos', (req, res) => {
    const todo = { id: nextId++, text: req.body.text, done: false };
    todos.push(todo);
    res.status(201).json(todo);
});

app.patch('/todos/:id', (req, res) => {
    const todo = todos.find(t => t.id === Number(req.params.id));
    if (!todo) return res.status(404).end();
    todo.done = req.body.done ?? todo.done;
    res.json(todo);
});

app.delete('/todos/:id', (req, res) => {
    todos = todos.filter(t => t.id !== Number(req.params.id));
    res.status(204).end();
});

app.listen(3000);
```

**When to add architecture:** When you feel pain. When the single file gets hard to navigate (500+ lines), extract modules. When you need a real database, add a repository. When business logic gets complex, add a service layer. Let complexity drive architecture, not the other way around.

**Architecture is not free.** Every layer adds files to navigate, mappings to maintain, and indirection to debug. Only add it when the benefit exceeds the cost.'''
    },
]
