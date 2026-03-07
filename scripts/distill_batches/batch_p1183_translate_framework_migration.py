"""Code translation pairs: Between frameworks (Express to FastAPI, React class to hooks, etc.)."""

PAIRS = [
    (
        "code-translation/framework-migration",
        r'''Migrate this Express.js REST API to FastAPI (Python):

const express = require("express");
const app = express();
app.use(express.json());

let todos = [];
let nextId = 1;

app.get("/todos", (req, res) => {
  const { status, limit } = req.query;
  let result = todos;
  if (status) result = result.filter(t => t.status === status);
  if (limit) result = result.slice(0, parseInt(limit));
  res.json(result);
});

app.get("/todos/:id", (req, res) => {
  const todo = todos.find(t => t.id === parseInt(req.params.id));
  if (!todo) return res.status(404).json({ error: "Not found" });
  res.json(todo);
});

app.post("/todos", (req, res) => {
  const { title, description } = req.body;
  if (!title) return res.status(400).json({ error: "title required" });
  const todo = { id: nextId++, title, description: description || "", status: "pending" };
  todos.push(todo);
  res.status(201).json(todo);
});

app.put("/todos/:id", (req, res) => {
  const todo = todos.find(t => t.id === parseInt(req.params.id));
  if (!todo) return res.status(404).json({ error: "Not found" });
  Object.assign(todo, req.body);
  res.json(todo);
});

app.delete("/todos/:id", (req, res) => {
  const idx = todos.findIndex(t => t.id === parseInt(req.params.id));
  if (idx === -1) return res.status(404).json({ error: "Not found" });
  todos.splice(idx, 1);
  res.status(204).end();
});

app.listen(3000);''',
        r'''<think>
Express.js to FastAPI migration. Several structural differences:

1. Express uses callback-based route handlers; FastAPI uses async functions with type annotations and automatic validation.

2. Express req.query is untyped strings; FastAPI uses Query() with types and validation.

3. Express req.params.id is a string (need parseInt); FastAPI path params get auto-converted via type hints.

4. Express req.body is parsed by middleware; FastAPI uses Pydantic models for request body validation.

5. Express manual error responses with res.status().json(); FastAPI raises HTTPException.

6. Express has no built-in request validation; FastAPI validates automatically from Pydantic models and type hints.

The biggest win in this migration is the automatic validation and OpenAPI docs that FastAPI gives you for free. I should use Pydantic models for the request/response bodies.

One thing to note: Express's Object.assign for partial updates maps to Pydantic's model with Optional fields and model.dict(exclude_unset=True).
</think>

```python
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI()

class TodoCreate(BaseModel):
    title: str
    description: str = ""

class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class Todo(BaseModel):
    id: int
    title: str
    description: str
    status: str

todos: list = []
next_id = 1

@app.get("/todos", response_model=List[Todo])
def list_todos(
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1),
):
    result = todos
    if status:
        result = [t for t in result if t["status"] == status]
    if limit:
        result = result[:limit]
    return result

@app.get("/todos/{todo_id}", response_model=Todo)
def get_todo(todo_id: int):
    todo = next((t for t in todos if t["id"] == todo_id), None)
    if not todo:
        raise HTTPException(status_code=404, detail="Not found")
    return todo

@app.post("/todos", response_model=Todo, status_code=201)
def create_todo(body: TodoCreate):
    global next_id
    todo = {
        "id": next_id,
        "title": body.title,
        "description": body.description,
        "status": "pending",
    }
    next_id += 1
    todos.append(todo)
    return todo

@app.put("/todos/{todo_id}", response_model=Todo)
def update_todo(todo_id: int, body: TodoUpdate):
    todo = next((t for t in todos if t["id"] == todo_id), None)
    if not todo:
        raise HTTPException(status_code=404, detail="Not found")
    updates = body.dict(exclude_unset=True)
    todo.update(updates)
    return todo

@app.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int):
    global todos
    before = len(todos)
    todos = [t for t in todos if t["id"] != todo_id]
    if len(todos) == before:
        raise HTTPException(status_code=404, detail="Not found")

# Run with: uvicorn module_name:app --port 3000
```

Key migration notes:

- `req.query.status` (string) -> `Query(None)` with type annotation -- FastAPI auto-validates types
- `req.params.id` with `parseInt` -> `todo_id: int` in path -- auto-converted and validated
- `req.body` parsed by middleware -> Pydantic `BaseModel` with automatic JSON validation and error messages
- `res.status(404).json({error})` -> `raise HTTPException(404, detail=...)`
- `Object.assign(todo, req.body)` -> `body.dict(exclude_unset=True)` for partial updates
- FastAPI auto-generates OpenAPI docs at /docs -- Express needs swagger-jsdoc or similar''',
    ),
    (
        "code-translation/framework-migration",
        r'''Migrate this jQuery AJAX code to modern fetch API:

$(document).ready(function() {
  // Load users on page load
  $.ajax({
    url: "/api/users",
    method: "GET",
    dataType: "json",
    success: function(users) {
      users.forEach(function(user) {
        $("#user-list").append(
          "<li data-id='" + user.id + "'>" + user.name + "</li>"
        );
      });
    },
    error: function(xhr, status, error) {
      $("#error").text("Failed to load users: " + error);
    }
  });

  // Submit new user form
  $("#user-form").on("submit", function(e) {
    e.preventDefault();
    var formData = $(this).serialize();
    $.ajax({
      url: "/api/users",
      method: "POST",
      data: formData,
      dataType: "json",
      beforeSend: function() {
        $("#submit-btn").prop("disabled", true).text("Saving...");
      },
      success: function(user) {
        $("#user-list").append(
          "<li data-id='" + user.id + "'>" + user.name + "</li>"
        );
        $("#user-form")[0].reset();
      },
      error: function(xhr) {
        var msg = xhr.responseJSON ? xhr.responseJSON.error : "Unknown error";
        alert("Failed: " + msg);
      },
      complete: function() {
        $("#submit-btn").prop("disabled", false).text("Save");
      }
    });
  });
});''',
        r'''```javascript
document.addEventListener("DOMContentLoaded", async function () {
  const userList = document.getElementById("user-list");
  const errorDiv = document.getElementById("error");

  // Load users on page load
  try {
    const resp = await fetch("/api/users");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const users = await resp.json();
    users.forEach(function (user) {
      const li = document.createElement("li");
      li.dataset.id = user.id;
      li.textContent = user.name;
      userList.appendChild(li);
    });
  } catch (err) {
    errorDiv.textContent = "Failed to load users: " + err.message;
  }

  // Submit new user form
  const form = document.getElementById("user-form");
  const submitBtn = document.getElementById("submit-btn");

  form.addEventListener("submit", async function (e) {
    e.preventDefault();

    // beforeSend equivalent
    submitBtn.disabled = true;
    submitBtn.textContent = "Saving...";

    try {
      const formData = new FormData(form);
      const body = Object.fromEntries(formData.entries());

      const resp = await fetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(function () {
          return {};
        });
        throw new Error(data.error || "Unknown error");
      }

      const user = await resp.json();
      const li = document.createElement("li");
      li.dataset.id = user.id;
      li.textContent = user.name;
      userList.appendChild(li);
      form.reset();
    } catch (err) {
      alert("Failed: " + err.message);
    } finally {
      // complete equivalent
      submitBtn.disabled = false;
      submitBtn.textContent = "Save";
    }
  });
});
```

Key migration notes:

- `$(document).ready(fn)` -> `document.addEventListener("DOMContentLoaded", fn)`
- `$.ajax({url, method, success, error})` -> `fetch(url, opts)` with async/await and try/catch
- `success` callback -> code after `await resp.json()`; `error` callback -> `catch` block
- `beforeSend` -> code before the fetch call; `complete` -> `finally` block
- `$(this).serialize()` -> `new FormData(form)` + `Object.fromEntries()` for JSON body
- `$("#user-list").append("<li>...")` (HTML string) -> `document.createElement("li")` (safer, no XSS risk from user.name)
- `xhr.responseJSON` -> `await resp.json()` with `.catch()` fallback for non-JSON error responses
- fetch does not reject on HTTP errors (unlike jQuery), so you must check `resp.ok` manually''',
    ),
    (
        "code-translation/framework-migration",
        r'''Migrate this Flask app with Jinja2 templates to a FastAPI + HTMX approach:

from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///tasks.db"
db = SQLAlchemy(app)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    done = db.Column(db.Boolean, default=False)

@app.route("/")
def index():
    tasks = Task.query.all()
    return render_template("index.html", tasks=tasks)

@app.route("/add", methods=["POST"])
def add_task():
    title = request.form["title"]
    task = Task(title=title)
    db.session.add(task)
    db.session.commit()
    return redirect(url_for("index"))

@app.route("/toggle/<int:task_id>", methods=["POST"])
def toggle_task(task_id):
    task = Task.query.get_or_404(task_id)
    task.done = not task.done
    db.session.commit()
    return redirect(url_for("index"))

@app.route("/delete/<int:task_id>", methods=["POST"])
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for("index"))''',
        r'''```python
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base

# Database setup
engine = create_engine("sqlite:///tasks.db")
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    done = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Full page load
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    db = SessionLocal()
    tasks = db.query(Task).all()
    db.close()
    return templates.TemplateResponse(
        "index.html", {"request": request, "tasks": tasks}
    )

# HTMX: return just the new task row (partial HTML)
@app.post("/add", response_class=HTMLResponse)
def add_task(request: Request, title: str = Form(...)):
    db = SessionLocal()
    task = Task(title=title)
    db.add(task)
    db.commit()
    db.refresh(task)
    db.close()
    # Return only the new task fragment -- HTMX swaps it in
    return templates.TemplateResponse(
        "partials/task_row.html",
        {"request": request, "task": task},
    )

# HTMX: return updated task row
@app.post("/toggle/{task_id}", response_class=HTMLResponse)
def toggle_task(request: Request, task_id: int):
    db = SessionLocal()
    task = db.query(Task).get(task_id)
    if not task:
        db.close()
        raise HTTPException(404)
    task.done = not task.done
    db.commit()
    db.refresh(task)
    db.close()
    return templates.TemplateResponse(
        "partials/task_row.html",
        {"request": request, "task": task},
    )

# HTMX: return empty (element gets removed)
@app.delete("/delete/{task_id}", response_class=HTMLResponse)
def delete_task(task_id: int):
    db = SessionLocal()
    task = db.query(Task).get(task_id)
    if not task:
        db.close()
        raise HTTPException(404)
    db.delete(task)
    db.commit()
    db.close()
    return HTMLResponse("")
```

```html
<!-- templates/partials/task_row.html -->
<!-- Each task is a self-contained HTMX fragment -->
<!--
<li id="task-{{ task.id }}">
  <span>{{ task.title }}</span>
  <button hx-post="/toggle/{{ task.id }}"
          hx-target="#task-{{ task.id }}"
          hx-swap="outerHTML">
    Toggle
  </button>
  <button hx-delete="/delete/{{ task.id }}"
          hx-target="#task-{{ task.id }}"
          hx-swap="outerHTML">
    Delete
  </button>
</li>
-->
```

Key migration notes:

- Flask `redirect(url_for("index"))` full page reload -> HTMX partial HTML responses (only the changed fragment)
- `flask_sqlalchemy` magic -> explicit SQLAlchemy with `sessionmaker` (FastAPI has no built-in ORM integration)
- `request.form["title"]` -> `title: str = Form(...)` with auto-validation
- `Task.query.get_or_404()` -> manual query + `HTTPException(404)`
- Flask POST returns redirect (302); HTMX returns HTML fragment that gets swapped into the DOM
- DELETE uses HTTP DELETE method instead of POST (more RESTful, enabled by HTMX)''',
    ),
    (
        "code-translation/framework-migration",
        r'''Migrate this Mocha/Chai test suite to Jest:

const chai = require("chai");
const chaiHttp = require("chai-http");
const sinon = require("sinon");
const { expect } = chai;
chai.use(chaiHttp);
const app = require("../app");
const User = require("../models/User");

describe("User API", function() {
  beforeEach(function() {
    this.sandbox = sinon.createSandbox();
  });

  afterEach(function() {
    this.sandbox.restore();
  });

  describe("GET /users", function() {
    it("should return all users", function(done) {
      const mockUsers = [{ id: 1, name: "Alice" }, { id: 2, name: "Bob" }];
      this.sandbox.stub(User, "findAll").resolves(mockUsers);

      chai.request(app)
        .get("/users")
        .end(function(err, res) {
          expect(res).to.have.status(200);
          expect(res.body).to.be.an("array").with.lengthOf(2);
          expect(res.body[0]).to.have.property("name", "Alice");
          done();
        });
    });

    it("should handle errors", function(done) {
      this.sandbox.stub(User, "findAll").rejects(new Error("DB down"));

      chai.request(app)
        .get("/users")
        .end(function(err, res) {
          expect(res).to.have.status(500);
          expect(res.body).to.have.property("error");
          done();
        });
    });
  });

  describe("POST /users", function() {
    it("should create a user", function(done) {
      const newUser = { id: 3, name: "Carol", email: "carol@test.com" };
      this.sandbox.stub(User, "create").resolves(newUser);

      chai.request(app)
        .post("/users")
        .send({ name: "Carol", email: "carol@test.com" })
        .end(function(err, res) {
          expect(res).to.have.status(201);
          expect(res.body.name).to.equal("Carol");
          done();
        });
    });
  });
});''',
        r'''```javascript
const request = require("supertest");
const app = require("../app");
const User = require("../models/User");

// Jest has built-in mocking -- no sinon needed
jest.mock("../models/User");

describe("User API", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("GET /users", () => {
    it("should return all users", async () => {
      const mockUsers = [
        { id: 1, name: "Alice" },
        { id: 2, name: "Bob" },
      ];
      User.findAll.mockResolvedValue(mockUsers);

      const res = await request(app).get("/users");

      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(2);
      expect(res.body[0]).toHaveProperty("name", "Alice");
    });

    it("should handle errors", async () => {
      User.findAll.mockRejectedValue(new Error("DB down"));

      const res = await request(app).get("/users");

      expect(res.status).toBe(500);
      expect(res.body).toHaveProperty("error");
    });
  });

  describe("POST /users", () => {
    it("should create a user", async () => {
      const newUser = {
        id: 3, name: "Carol", email: "carol@test.com",
      };
      User.create.mockResolvedValue(newUser);

      const res = await request(app)
        .post("/users")
        .send({ name: "Carol", email: "carol@test.com" });

      expect(res.status).toBe(201);
      expect(res.body.name).toBe("Carol");
    });
  });
});
```

Key migration notes:

- `sinon.createSandbox()` + `sandbox.stub()` -> `jest.mock()` + `.mockResolvedValue()` (Jest has built-in mocking)
- `sandbox.restore()` -> `jest.restoreAllMocks()` in afterEach
- `chai-http` -> `supertest` (standard HTTP testing library for Jest)
- Callback-based `done()` pattern -> `async/await` (Jest supports both, but async is cleaner)
- Chai assertions: `expect(x).to.have.status(200)` -> Jest: `expect(x.status).toBe(200)`
- `to.be.an("array").with.lengthOf(2)` -> `toHaveLength(2)`
- `to.have.property("name", "Alice")` -> `toHaveProperty("name", "Alice")` (same concept, different syntax)
- `function()` callbacks -> arrow functions (Jest does not use `this` context like Mocha)
- `sinon.stub(obj, "method").resolves(val)` -> `obj.method.mockResolvedValue(val)`''',
    ),
    (
        "code-translation/framework-migration",
        r'''Migrate this SQLAlchemy 1.x query style to SQLAlchemy 2.0:

from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    posts = relationship("Post", back_populates="author")

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    author_id = Column(Integer, ForeignKey("users.id"))
    author = relationship("User", back_populates="posts")

engine = create_engine("sqlite:///app.db")
Session = sessionmaker(bind=engine)
session = Session()

# Legacy query style
users = session.query(User).filter(User.name == "Alice").all()
user = session.query(User).filter_by(name="Alice").first()
post_count = session.query(Post).filter(Post.author_id == 1).count()
results = session.query(User.name, Post.title).join(Post).all()

# Legacy bulk update
session.query(User).filter(User.name == "old").update({"name": "new"})
session.commit()''',
        r'''<think>
SQLAlchemy 1.x to 2.0 migration. This is a common real-world migration. Key changes:

1. `declarative_base()` from `sqlalchemy.ext.declarative` -> `DeclarativeBase` class from `sqlalchemy.orm` or `registry.generate_base()`

2. `Column(Integer)` -> `mapped_column(Integer)` with `Mapped[]` type annotations

3. `session.query(Model)` (legacy) -> `select(Model)` with `session.execute()` (2.0 style)

4. `session.query(Model).filter()` -> `session.execute(select(Model).where())`

5. `.all()` returns list of Model instances in 1.x -> `.scalars().all()` in 2.0 (execute returns Row objects, scalars extracts the first column)

6. `relationship()` -> `relationship()` still works but add `Mapped[]` annotation

7. `sessionmaker(bind=engine)` still works but 2.0 recommends `Session(engine)` or `sessionmaker(engine)`

This is important because SQLAlchemy 2.0 deprecated the 1.x query API and it will be removed in a future version.
</think>

```python
from sqlalchemy import create_engine, ForeignKey, select, update, func
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column,
    relationship, Session,
)
from typing import List, Optional

# 2.0 style: class-based DeclarativeBase
class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[Optional[str]]
    posts: Mapped[List["Post"]] = relationship(back_populates="author")

class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[Optional[str]]
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    author: Mapped["User"] = relationship(back_populates="posts")

engine = create_engine("sqlite:///app.db")

# 2.0 query style using select() + session.execute()
with Session(engine) as session:
    # session.query(User).filter(...).all()
    # becomes:
    stmt = select(User).where(User.name == "Alice")
    users = session.scalars(stmt).all()

    # session.query(User).filter_by(name="Alice").first()
    # becomes:
    user = session.scalars(
        select(User).where(User.name == "Alice")
    ).first()

    # session.query(Post).filter(...).count()
    # becomes:
    post_count = session.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_id == 1
        )
    )

    # session.query(User.name, Post.title).join(Post).all()
    # becomes:
    stmt = select(User.name, Post.title).join(Post)
    results = session.execute(stmt).all()
    # results is list of Row tuples, not model instances

    # Bulk update
    session.execute(
        update(User).where(User.name == "old").values(name="new")
    )
    session.commit()
```

Key migration notes:

- `declarative_base()` function -> `DeclarativeBase` class you subclass
- `Column(Integer)` -> `Mapped[int] = mapped_column()` with Python type annotations
- `relationship("Post")` -> `Mapped[List["Post"]] = relationship()` with type annotation
- `session.query(Model).filter().all()` -> `session.scalars(select(Model).where()).all()`
- `.first()` -> `session.scalars(stmt).first()`
- `.count()` -> `session.scalar(select(func.count()).select_from(Model).where())`
- `session.query(...).update({})` -> `session.execute(update(Model).where().values())`
- `Session(engine)` as context manager replaces manual `session.close()`
- `session.execute()` returns `Result` with `Row` objects; use `.scalars()` to get model instances directly''',
    ),
]
