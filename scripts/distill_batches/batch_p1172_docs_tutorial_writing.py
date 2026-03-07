"""Documentation generation training pairs: step-by-step tutorials from working code."""

pairs = [
    {
        "instruction": r'''Write a step-by-step tutorial for building a CLI todo app using this Python code:

import json
import sys
from pathlib import Path

TODO_FILE = Path.home() / ".todos.json"

def load_todos():
    if TODO_FILE.exists():
        return json.loads(TODO_FILE.read_text())
    return []

def save_todos(todos):
    TODO_FILE.write_text(json.dumps(todos, indent=2))

def add_todo(text):
    todos = load_todos()
    todos.append({"text": text, "done": False, "id": len(todos) + 1})
    save_todos(todos)
    print(f"Added: {text}")

def list_todos():
    todos = load_todos()
    if not todos:
        print("No todos yet!")
        return
    for t in todos:
        status = "[x]" if t["done"] else "[ ]"
        print(f"  {t['id']}. {status} {t['text']}")

def complete_todo(todo_id):
    todos = load_todos()
    for t in todos:
        if t["id"] == todo_id:
            t["done"] = True
            save_todos(todos)
            print(f"Completed: {t['text']}")
            return
    print(f"Todo {todo_id} not found")

def main():
    if len(sys.argv) < 2:
        print("Usage: todo <add|list|done> [args]")
        return
    cmd = sys.argv[1]
    if cmd == "add" and len(sys.argv) > 2:
        add_todo(" ".join(sys.argv[2:]))
    elif cmd == "list":
        list_todos()
    elif cmd == "done" and len(sys.argv) > 2:
        complete_todo(int(sys.argv[2]))
    else:
        print("Unknown command")

if __name__ == "__main__":
    main()''',
        "output": r'''<think>
I need to write a tutorial that walks someone through building this todo app step by step. The audience is likely a beginner learning Python. I should break it into logical steps: setup, data storage, core functions, CLI interface, and testing it out. I should explain the choices made (JSON for storage, home directory for file location).
</think>

# Build a CLI Todo App in Python

In this tutorial, you will build a command-line todo list manager in a single Python file. No external libraries needed -- just the standard library.

## What You Will Build

A `todo` command that supports:
- `todo add Buy groceries` -- add a new task
- `todo list` -- show all tasks with status
- `todo done 2` -- mark task #2 as complete

Tasks are saved to a JSON file so they persist between sessions.

## Step 1: Set Up the Project

Create a file called `todo.py`. Start with imports and define where todos will be stored:

```python
import json
import sys
from pathlib import Path

# Store todos in the user's home directory so they are
# accessible from any working directory
TODO_FILE = Path.home() / ".todos.json"
```

## Step 2: Load and Save Functions

Write two helper functions to read and write the JSON file:

```python
def load_todos():
    if TODO_FILE.exists():
        return json.loads(TODO_FILE.read_text())
    return []

def save_todos(todos):
    TODO_FILE.write_text(json.dumps(todos, indent=2))
```

`load_todos` returns an empty list if the file does not exist yet. `save_todos` writes the full list back, pretty-printed with 2-space indent.

## Step 3: Core Functions

Add three functions: `add_todo` appends a new dict with `text`, `done`, and `id` fields. `list_todos` prints each todo with a `[x]` or `[ ]` checkbox. `complete_todo` finds a todo by ID and sets `done = True`.

## Step 4: Wire Up the CLI

Parse command-line arguments in a `main` function:

```python
def main():
    if len(sys.argv) < 2:
        print("Usage: todo <add|list|done> [args]")
        return
    cmd = sys.argv[1]
    if cmd == "add" and len(sys.argv) > 2:
        add_todo(" ".join(sys.argv[2:]))
    elif cmd == "list":
        list_todos()
    elif cmd == "done" and len(sys.argv) > 2:
        complete_todo(int(sys.argv[2]))
    else:
        print("Unknown command")

if __name__ == "__main__":
    main()
```

## Step 7: Try It Out

```bash
python todo.py add Buy milk
python todo.py add Write report
python todo.py list
python todo.py done 1
python todo.py list
```

You should see task 1 marked as complete with `[x]`.'''
    },
    {
        "instruction": r'''Write a tutorial for setting up a REST API with Express.js and TypeScript, based on this working code:

import express from 'express';
import { z } from 'zod';

const app = express();
app.use(express.json());

interface Todo {
  id: number;
  title: string;
  completed: boolean;
}

let todos: Todo[] = [];
let nextId = 1;

const CreateTodoSchema = z.object({
  title: z.string().min(1).max(200),
});

app.get('/todos', (req, res) => {
  res.json(todos);
});

app.post('/todos', (req, res) => {
  const parsed = CreateTodoSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ errors: parsed.error.issues });
  }
  const todo: Todo = { id: nextId++, title: parsed.data.title, completed: false };
  todos.push(todo);
  res.status(201).json(todo);
});

app.patch('/todos/:id', (req, res) => {
  const todo = todos.find(t => t.id === parseInt(req.params.id));
  if (!todo) return res.status(404).json({ error: 'Not found' });
  if (req.body.title) todo.title = req.body.title;
  if (req.body.completed !== undefined) todo.completed = req.body.completed;
  res.json(todo);
});

app.delete('/todos/:id', (req, res) => {
  const index = todos.findIndex(t => t.id === parseInt(req.params.id));
  if (index === -1) return res.status(404).json({ error: 'Not found' });
  todos.splice(index, 1);
  res.status(204).send();
});

app.listen(3000, () => console.log('Server running on port 3000'));''',
        "output": r'''# Tutorial: Build a REST API with Express.js and TypeScript

Learn how to create a typed REST API with input validation using Express and Zod.

## Prerequisites

- Node.js 18 or later
- A terminal and text editor

## Step 1: Initialize the Project

```bash
mkdir todo-api && cd todo-api
npm init -y
npm install express zod
npm install -D typescript @types/express @types/node tsx
npx tsc --init
```

`tsx` lets you run TypeScript files directly without a separate build step.

## Step 2: Create the Server

Create `src/index.ts` and set up the Express app:

```typescript
import express from 'express';
const app = express();
app.use(express.json()); // Parse JSON request bodies
```

## Step 3: Define the Data Model

Define a TypeScript interface for your data and an in-memory store:

```typescript
interface Todo {
  id: number;
  title: string;
  completed: boolean;
}

let todos: Todo[] = [];
let nextId = 1;
```

For a real app, you would replace this with a database. The in-memory approach keeps this tutorial focused on the API layer.

## Step 4: Add Input Validation with Zod

Zod lets you define schemas that validate request data and infer TypeScript types:

```typescript
import { z } from 'zod';

const CreateTodoSchema = z.object({
  title: z.string().min(1).max(200),
});
```

If validation fails, Zod provides structured error messages automatically.

## Step 5: Implement the Endpoints

**GET /todos** -- Return all todos:

```typescript
app.get('/todos', (req, res) => {
  res.json(todos);
});
```

**POST /todos** -- Create a new todo with validation:

```typescript
app.post('/todos', (req, res) => {
  const parsed = CreateTodoSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ errors: parsed.error.issues });
  }
  const todo: Todo = { id: nextId++, title: parsed.data.title, completed: false };
  todos.push(todo);
  res.status(201).json(todo);
});
```

**PATCH /todos/:id** -- Update a todo.

**DELETE /todos/:id** -- Remove a todo, returning 204 No Content on success.

## Step 6: Start the Server

Add this at the bottom of `src/index.ts`:

```typescript
app.listen(3000, () => console.log('Server running on port 3000'));
```

Add a start script to `package.json`:

```json
{ "scripts": { "dev": "tsx watch src/index.ts" } }
```

Run with `npm run dev`. The `watch` flag auto-restarts on file changes.

## Step 7: Test Your API

```bash
curl -X POST http://localhost:3000/todos \
  -H "Content-Type: application/json" \
  -d '{"title": "Learn Express"}'

curl http://localhost:3000/todos
```'''
    },
    {
        "instruction": r'''Write a tutorial for implementing JWT authentication in a Flask app based on this code:

from flask import Flask, request, jsonify, g
from functools import wraps
import jwt
import bcrypt
import datetime
import os

app = Flask(__name__)
SECRET_KEY = os.environ.get("JWT_SECRET", "dev-secret-change-me")
users_db = {}

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id):
    payload = {
        "sub": user_id,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"error": "Token required"}), 401
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            g.user_id = payload["sub"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    if data["username"] in users_db:
        return jsonify({"error": "User exists"}), 409
    users_db[data["username"]] = {
        "password": hash_password(data["password"]),
    }
    return jsonify({"message": "User created"}), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    user = users_db.get(data["username"])
    if not user or not check_password(data["password"], user["password"]):
        return jsonify({"error": "Invalid credentials"}), 401
    token = create_token(data["username"])
    return jsonify({"token": token})

@app.route("/profile", methods=["GET"])
@require_auth
def profile():
    return jsonify({"user_id": g.user_id})''',
        "output": r'''# Tutorial: JWT Authentication in Flask

This tutorial walks through implementing JSON Web Token (JWT) authentication for a Flask API, covering user registration, login, and protecting routes.

## Prerequisites

Install the required packages:

```bash
pip install flask pyjwt bcrypt
```

## How JWT Auth Works

1. User registers with username and password (password is hashed and stored)
2. User logs in -- server verifies credentials and returns a signed JWT
3. Client sends the JWT in the Authorization header on subsequent requests
4. Server verifies the token signature and expiration before processing the request

## Step 1: Password Hashing

Never store plain-text passwords. Use bcrypt -- `gensalt()` generates a random salt, and it is embedded in the hash output so you do not store it separately.

## Step 2: Token Creation

Create a JWT with `sub` (user ID), `iat` (issued at), and `exp` (expiry) claims. PyJWT automatically rejects expired tokens with `ExpiredSignatureError`. Set `JWT_SECRET` to a strong random value in production.

## Step 3: Auth Decorator

The `require_auth` decorator extracts the Bearer token from the Authorization header, decodes it with `jwt.decode()`, and stores the user ID on Flask's `g` object. If the token is missing, expired, or invalid, it returns 401.

## Step 4: Protect Routes

Add `@require_auth` to any route that needs authentication:

```python
@app.route("/profile", methods=["GET"])
@require_auth
def profile():
    return jsonify({"user_id": g.user_id})
```

## Step 5: Test the Flow

```bash
# Register
curl -X POST http://localhost:5000/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'

# Login (save the returned token)
curl -X POST http://localhost:5000/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'

# Access protected route
curl http://localhost:5000/profile \
  -H "Authorization: Bearer <token-from-login>"
```'''
    },
    {
        "instruction": r'''Write a short tutorial explaining how to use this Python context manager for database transactions:

class TransactionManager:
    def __init__(self, connection):
        self.conn = connection
        self.savepoint_id = 0

    def __enter__(self):
        self.conn.execute("BEGIN")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.conn.execute("COMMIT")
        else:
            self.conn.execute("ROLLBACK")
        return False

    def savepoint(self):
        self.savepoint_id += 1
        name = f"sp_{self.savepoint_id}"
        self.conn.execute(f"SAVEPOINT {name}")
        return name

    def release(self, name):
        self.conn.execute(f"RELEASE SAVEPOINT {name}")

    def rollback_to(self, name):
        self.conn.execute(f"ROLLBACK TO SAVEPOINT {name}")''',
        "output": r'''# Using TransactionManager for Safe Database Operations

`TransactionManager` wraps database transactions in a Python context manager. It automatically commits on success and rolls back on error.

## Basic Usage

Wrap your database operations in a `with` block:

```python
conn = get_database_connection()

with TransactionManager(conn) as tx:
    conn.execute("INSERT INTO users (name) VALUES ('Alice')")
    conn.execute("INSERT INTO accounts (user_id, balance) VALUES (1, 100)")
# Both inserts are committed together when the block exits normally
```

If any operation raises an exception, the entire transaction is rolled back:

```python
with TransactionManager(conn) as tx:
    conn.execute("INSERT INTO users (name) VALUES ('Bob')")
    conn.execute("INSERT INTO invalid_table (...)")  # raises an error
# Nothing is committed -- the users insert is also rolled back
```

## Using Savepoints

Savepoints let you roll back part of a transaction without losing everything:

```python
with TransactionManager(conn) as tx:
    conn.execute("INSERT INTO orders (product) VALUES ('Widget')")

    sp = tx.savepoint()
    try:
        conn.execute("UPDATE inventory SET count = count - 1 WHERE product = 'Widget'")
        # Suppose this raises an error
        process_payment()
    except PaymentError:
        # Roll back only the inventory update, keep the order
        tx.rollback_to(sp)
        conn.execute("UPDATE orders SET status = 'payment_failed' WHERE ...")

    # The order insert and status update are committed
```

## When to Use Savepoints

- **Partial failure recovery** -- retry or skip a step without aborting the whole transaction
- **Batch processing** -- insert 1000 rows, skip any that fail, commit the rest
- **Nested operations** -- call a function that might fail without rolling back the caller's work

## Key Behaviors

- `__enter__` sends `BEGIN` to start the transaction
- `__exit__` sends `COMMIT` if no exception occurred, `ROLLBACK` otherwise
- Exceptions are NOT suppressed (the method returns False), so they propagate to your code after the rollback'''
    },
    {
        "instruction": r'''Write a tutorial on implementing a custom Python iterator based on this code:

class ChunkedReader:
    def __init__(self, filepath, chunk_size=1024):
        self.filepath = filepath
        self.chunk_size = chunk_size
        self._file = None

    def __enter__(self):
        self._file = open(self.filepath, "rb")
        return self

    def __exit__(self, *args):
        if self._file:
            self._file.close()

    def __iter__(self):
        return self

    def __next__(self):
        if self._file is None:
            raise RuntimeError("Use as context manager")
        chunk = self._file.read(self.chunk_size)
        if not chunk:
            raise StopIteration
        return chunk

    def read_all(self):
        return b"".join(self)''',
        "output": r'''<think>
This shows a class that is both a context manager and an iterator. It reads a file in fixed-size chunks. I should explain the iterator protocol (__iter__ and __next__), the context manager protocol, and show practical use cases like processing large files without loading them entirely into memory.
</think>

# Tutorial: Custom Iterators in Python

Learn how to build a memory-efficient file reader using Python's iterator protocol.

## The Problem

Reading a large file all at once can exhaust memory:

```python
# Dangerous for large files -- loads everything into RAM
data = open("huge_file.bin", "rb").read()
```

A chunked reader processes the file piece by piece, using only `chunk_size` bytes of memory at a time.

## The Iterator Protocol

Python iterators implement two methods:

- `__iter__()` -- returns the iterator object (usually `self`)
- `__next__()` -- returns the next item, or raises `StopIteration` when done

Any object with these methods works in `for` loops, list comprehensions, and functions like `sum()` or `b"".join()`.

## Building ChunkedReader

```python
class ChunkedReader:
    def __init__(self, filepath, chunk_size=1024):
        self.filepath = filepath
        self.chunk_size = chunk_size
        self._file = None
```

The constructor stores configuration but does not open the file yet. The file is opened in `__enter__` so the context manager controls its lifecycle.

The `__next__` method reads one chunk and raises `StopIteration` when there is nothing left:

```python
def __next__(self):
    chunk = self._file.read(self.chunk_size)
    if not chunk:
        raise StopIteration
    return chunk
```

## Using It

**Process chunks in a for loop:**

```python
with ChunkedReader("large_video.mp4", chunk_size=4096) as reader:
    for chunk in reader:
        hasher.update(chunk)
print(hasher.hexdigest())
```

**Read everything (still uses chunked iteration internally):**

```python
with ChunkedReader("data.bin") as reader:
    all_data = reader.read_all()
```

The `read_all` method uses `b"".join(self)`, which iterates through all chunks via `__next__` and concatenates them.

## Why This Pattern Matters

- **Memory efficiency** -- only one chunk is in memory at a time
- **Composability** -- works with all of Python's iteration tools
- **Resource safety** -- the context manager ensures the file is always closed'''
    },
]
