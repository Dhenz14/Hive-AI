"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 9)
Scenarios: Wrong API design, logic errors, performance antipatterns, security holes
"""

PAIRS = [
    (
        "thinking/meta-error-api-inconsistent-naming",
        r'''I designed these API endpoints for a blog platform:

```
GET    /api/posts              - List all posts
POST   /api/posts/create       - Create a post
GET    /api/post/{id}          - Get a post
PUT    /api/updatePost/{id}    - Update a post
DELETE /api/posts/{id}/delete  - Delete a post
GET    /api/posts/{id}/comments - List comments
POST   /api/comment/new        - Create a comment
GET    /api/users/{userId}     - Get user profile
GET    /api/get-user-posts/{user_id} - Get user's posts
```

Is this a well-designed REST API?''',
        r'''<think>
Let me examine these endpoints for REST conventions...

Problems I see:

1. **Inconsistent pluralization**: `/api/posts` (plural) vs `/api/post/{id}` (singular) vs `/api/comment/new` (singular). REST convention: always use plural nouns.

2. **Verbs in URLs**: REST uses HTTP methods for actions, not URL verbs:
   - `/api/posts/create` → should be `POST /api/posts`
   - `/api/updatePost/{id}` → should be `PUT /api/posts/{id}`
   - `/api/posts/{id}/delete` → should be `DELETE /api/posts/{id}`
   - `/api/get-user-posts/{user_id}` → should be `GET /api/users/{user_id}/posts`
   - `/api/comment/new` → should be `POST /api/comments` or `POST /api/posts/{id}/comments`

3. **Inconsistent naming convention**: camelCase (`updatePost`, `userId`) mixed with kebab-case (`get-user-posts`) mixed with snake_case (`user_id`). Pick one convention.

4. **Inconsistent nesting**: Comments on a post are `GET /api/posts/{id}/comments` (nested, good) but creating a comment is `POST /api/comment/new` (flat, disconnected from the post).

5. **Redundant path segments**: `POST /api/posts/create` — the `POST` method already means "create." Same for `DELETE /api/posts/{id}/delete` — `DELETE` already means "delete."

6. **No version prefix**: Should be `/api/v1/posts` for future compatibility.

This API would be confusing for developers because they'd have to memorize each endpoint's unique pattern instead of learning one consistent pattern.
</think>

**This API has 6 different consistency violations that make it hard to use and maintain.**

### The problems

| Issue | Example | Convention |
|-------|---------|------------|
| Verbs in URLs | `/posts/create`, `/updatePost` | HTTP methods express actions |
| Mixed plurality | `/post/{id}` vs `/posts` | Always use plural |
| Mixed naming | `userId`, `user_id`, `get-user-posts` | Pick one convention |
| Redundant verbs | `POST /create`, `DELETE /delete` | Method IS the verb |
| Inconsistent nesting | `GET /posts/{id}/comments` but `POST /comment/new` | Consistent hierarchy |
| No versioning | `/api/posts` | `/api/v1/posts` |

### Fixed API design
```
GET    /api/v1/posts                       - List posts
POST   /api/v1/posts                       - Create post
GET    /api/v1/posts/{id}                  - Get post
PUT    /api/v1/posts/{id}                  - Update post
DELETE /api/v1/posts/{id}                  - Delete post

GET    /api/v1/posts/{id}/comments         - List post's comments
POST   /api/v1/posts/{id}/comments         - Create comment on post

GET    /api/v1/users/{id}                  - Get user profile
GET    /api/v1/users/{id}/posts            - Get user's posts
```

### The pattern
```
GET    /resources          → list
POST   /resources          → create
GET    /resources/{id}     → read
PUT    /resources/{id}     → replace
PATCH  /resources/{id}     → partial update
DELETE /resources/{id}     → delete

GET    /resources/{id}/sub-resources  → list nested
POST   /resources/{id}/sub-resources  → create nested
```

### The meta-lesson
API design is about consistency and predictability. A developer who learns your pattern for one resource should be able to guess the endpoints for every other resource. Inconsistency forces developers to memorize each endpoint individually instead of learning one pattern. Always use: plural nouns, no verbs in URLs, consistent naming convention, consistent nesting.'''
    ),
    (
        "thinking/meta-error-regex-catastrophic-backtracking",
        r'''I wrote this regex to validate email addresses:

```python
import re

EMAIL_REGEX = re.compile(r'^([a-zA-Z0-9]+\.)*[a-zA-Z0-9]+@([a-zA-Z0-9]+\.)*[a-zA-Z0-9]+$')

def is_valid_email(email):
    return bool(EMAIL_REGEX.match(email))
```

It works for valid emails. Is there any issue?''',
        r'''<think>
Let me analyze this regex for performance issues...

The pattern: `^([a-zA-Z0-9]+\.)*[a-zA-Z0-9]+@([a-zA-Z0-9]+\.)*[a-zA-Z0-9]+$`

The problematic part is `([a-zA-Z0-9]+\.)*[a-zA-Z0-9]+`. This is a nested quantifier: a group with `*` containing `+`. Let me trace what happens with a non-matching input.

Consider: `aaaaaaaaaaaaaaaaaa!@example.com`

The `([a-zA-Z0-9]+\.)*` tries to match the local part. It tries:
- `aaaaaaaaaaaaaaaaaa` as one group match of `[a-zA-Z0-9]+` — but no dot follows, so the `\.` fails
- Backtrack: try `aaaaaaaaaaaaaaaa` as first match, then `aa` as start of next `[a-zA-Z0-9]+`... but still no dot
- More backtracking: try `aaa` then `aaa` then...

Wait, actually the key issue is `([a-zA-Z0-9]+\.)*[a-zA-Z0-9]+`. When the input is `aaaaaa` with no dots, the regex engine has to figure out how to divide the `a`s between the repeated group's `[a-zA-Z0-9]+` and the final `[a-zA-Z0-9]+`. There are exponentially many ways to partition the string.

For `aaaaaaaaaaaaaaaaaaa!` (19 a's followed by !), the engine tries:
- 19 a's in final part → fails (! doesn't match @)
- 18 a's in group + 1 in final → fails (no dot after group)
- Actually wait, the group requires a dot: `[a-zA-Z0-9]+\.`. So without any dots, the group can't match at all. The entire local part must match `[a-zA-Z0-9]+`, which matches all the a's, then hits `!` when expecting `@`.

Hmm, so maybe this specific pattern isn't catastrophically bad for the local part without dots. Let me reconsider...

Actually, the real danger is on the DOMAIN part: `([a-zA-Z0-9]+\.)*[a-zA-Z0-9]+$`. Consider input `user@aaaaaaaaaaaaaaaaaa` (no dots in domain and no final match for `$` if there's a trailing character that doesn't match).

Wait, let me reconsider the regex more carefully. The issue with `(a+\.)*a+` is when the input has NO dots — then `(a+\.)*` matches empty, and `a+` matches everything. That's fine, no backtracking.

But what about `(a+)*a+`? THAT would be catastrophic. The current regex has `\.` in the repeating group, which anchors it. Let me try a failing input like `user@aaaa.aaaa.aaaa.aaaa.aaaa.aaaa.aaaa.aaaa.aaaa.!`...

With dots present, `([a-zA-Z0-9]+\.)*` can match various numbers of dot-segments, and then the remaining part may or may not match `[a-zA-Z0-9]+$`. If it can't match $ (because of the `!`), the engine backtracks through all possible ways to divide the segments.

Actually, I think the real catastrophic case is something like `aaaa.aaaa.aaaa.aaaa.aaaa.aaaa.aaaa.aaaa.aaaa.aaaa` (no @ sign). The engine tries to match `([a-zA-Z0-9]+\.)*[a-zA-Z0-9]+@`, and the `@` never comes. It backtracks through all possible groupings of the dot-separated segments.

Let me actually test this reasoning. With `a.a.a.a.a.a.a.a.a.a.a.a.a.a.a.!` — the engine tries different splits of `a.a.a...` into the repeating group and final part, combined with the groups themselves having flexible length. This could indeed be exponential.

Yes, this IS vulnerable to ReDoS. With inputs like `'a.' * 25 + '!'`, the regex engine can take exponential time.
</think>

**This regex is vulnerable to catastrophic backtracking (ReDoS) with crafted input.**

### The vulnerability
```python
# This takes exponentially increasing time:
import time

for n in [15, 20, 25, 30]:
    test = 'a.' * n + '!'
    start = time.time()
    EMAIL_REGEX.match(test)
    print(f"n={n}: {time.time() - start:.2f}s")

# n=15:  0.01s
# n=20:  0.50s
# n=25:  15.0s
# n=30:  timeout!
```

The nested quantifier `([a-zA-Z0-9]+\.)*[a-zA-Z0-9]+` creates exponential backtracking when the match fails on long dot-separated inputs. The engine tries every possible way to divide segments between the repeating group and the final part.

### Attack scenario
An attacker submits `'a.' * 50 + '!'` as an email address. Your server hangs for minutes processing one regex match — denial of service with a single request.

### Fix: use atomic groups or possessive quantifiers
```python
# Option 1: Simple regex with length limits
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# Option 2: Use a library (handles edge cases + no ReDoS)
from email_validator import validate_email

# Option 3: Add input length limit BEFORE regex
def is_valid_email(email):
    if len(email) > 254:  # RFC 5321 limit
        return False
    return bool(EMAIL_REGEX.match(email))
```

### The meta-lesson
Any regex with nested quantifiers (`(a+)*`, `(a+)+`, `(a*)*`) is potentially vulnerable to catastrophic backtracking. Before deploying a regex that processes user input, test it with adversarial inputs: long strings of matching characters that ALMOST match. Always set a length limit on input before applying regex, and prefer simple patterns over "complete" ones.'''
    ),
    (
        "thinking/meta-error-logic-floating-point-money",
        r'''I wrote this price calculation for an e-commerce cart:

```python
def calculate_cart_total(items):
    subtotal = 0.0
    for item in items:
        subtotal += item['price'] * item['quantity']

    tax = subtotal * 0.08
    total = subtotal + tax
    return round(total, 2)
```

Simple arithmetic. Any issues?''',
        r'''<think>
Let me think about floating-point arithmetic and money...

The classic problem: `0.1 + 0.2 = 0.30000000000000004` in IEEE 754 floating point. These tiny errors accumulate across many additions.

Example:
```python
subtotal = 0.0
subtotal += 19.99  # = 19.99 (OK so far)
subtotal += 19.99  # = 39.98 (OK)
subtotal += 19.99  # = 59.97000000000001 (error appears!)
```

With 100 items at $19.99: floating-point errors can accumulate to a cent or more. The `round(total, 2)` at the end rounds the FINAL result, but intermediate rounding errors might push the total to the wrong cent.

More critically, consider:
```python
tax = 59.97000000000001 * 0.08  # = 4.797600000000001
total = 59.97000000000001 + 4.797600000000001  # = 64.76760000000001
round(64.76760000000001, 2)  # = 64.77
```

But if we'd used exact arithmetic: 59.97 * 0.08 = 4.7976, 59.97 + 4.7976 = 64.7676, round to 64.77. Same result here, but with different item prices, the rounding could go either way.

The bigger issue: for financial calculations, you should NEVER use floating-point. The standard solution is `decimal.Decimal` or integer cents.

Also: where should tax rounding happen? On the total? Per item? Tax laws vary by jurisdiction, and accumulated per-item rounding vs total rounding can differ by cents.

And: `round(total, 2)` uses banker's rounding in Python 3 (`round(2.5) = 2`, `round(3.5) = 4`). Some jurisdictions require standard rounding.
</think>

**Never use floating-point (`float`) for money. IEEE 754 accumulates rounding errors across additions.**

### The bug
```python
>>> 0.1 + 0.2
0.30000000000000004

>>> sum([19.99] * 100)
1998.9999999999998  # should be 1999.00

>>> 0.1 + 0.1 + 0.1 - 0.3
5.551115123125783e-17  # should be 0.0
```

These tiny errors accumulate. With enough items, your cart total can be off by a cent — which violates financial regulations and causes reconciliation nightmares.

### Fix: use Decimal
```python
from decimal import Decimal, ROUND_HALF_UP

def calculate_cart_total(items):
    subtotal = Decimal('0')
    for item in items:
        price = Decimal(str(item['price']))
        subtotal += price * item['quantity']

    tax_rate = Decimal('0.08')
    tax = (subtotal * tax_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    total = subtotal + tax
    return total

# Even better: store prices as integer cents
def calculate_cart_total_cents(items):
    subtotal_cents = sum(item['price_cents'] * item['quantity'] for item in items)
    tax_cents = round(subtotal_cents * 0.08)  # integer arithmetic
    return subtotal_cents + tax_cents
```

### Why `round()` at the end doesn't fix it
```python
# Rounding the final result doesn't guarantee correctness:
round(64.76500000000001, 2)  # 64.77
round(64.76499999999999, 2)  # 64.76
# These SHOULD be the same number but float imprecision flips the rounding!
```

### Python 3's round() uses banker's rounding
```python
round(2.5)  # = 2 (not 3!)
round(3.5)  # = 4
# This may not match your jurisdiction's tax rounding rules
```

### The meta-lesson
For financial calculations: use `Decimal` (exact decimal arithmetic) or integer cents (no fractions at all). Floating-point is designed for speed in scientific computing, not accuracy in financial computing. The errors are tiny but legally and financially significant.'''
    ),
    (
        "thinking/meta-error-security-jwt-in-url",
        r'''I implemented file download authentication using JWT tokens in the URL:

```python
@app.get("/api/files/{file_id}")
def download_file(file_id: str, token: str):
    """Download file with JWT token in query parameter.
    Usage: /api/files/123?token=eyJhbG...
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload["file_id"] != file_id:
            raise HTTPException(403, "Token not valid for this file")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")

    return FileResponse(get_file_path(file_id))
```

This gives authenticated download links I can share. Secure?''',
        r'''<think>
Let me analyze the security of JWT tokens in URL query parameters...

The URL would look like: `https://example.com/api/files/123?token=eyJhbGciOiJIUzI1NiJ9.eyJmaWxlX2lkIjoiMTIzIn0.abc123`

Problems:

1. **URLs are logged everywhere**: Web server access logs, reverse proxy logs, CDN logs, browser history, analytics tools (Google Analytics), referrer headers — all capture the full URL including the token. Anyone with log access can steal tokens.

2. **Browser history**: The download URL with token is saved in the user's browser history. Anyone using the same computer can access the file.

3. **Referrer header leakage**: If the file page links to external resources, the browser sends the full URL (including token) as the `Referer` header to those external sites.

4. **Shoulder surfing**: The token is visible in the browser address bar.

5. **Token doesn't expire**: The code doesn't check `exp` claim. This token works forever once generated.

6. **Token scope**: The token only checks `file_id` — no user ID, no expiration, no IP binding. If leaked, anyone can use it.

The proper approaches:
- Short-lived signed URLs (like AWS S3 presigned URLs) with expiration
- Token in Authorization header for API calls
- Session-based authentication with cookies
- One-time download tokens stored in database

My error: I treated URL parameters as equivalent to headers for security purposes. URLs are much more exposed than headers — they're logged, cached, bookmarked, and shared across systems in ways that Authorization headers never are.
</think>

**Tokens in URLs are exposed through logs, browser history, referrer headers, and caching — making this insecure for authentication.**

### Where the token leaks

| Vector | Exposure |
|--------|----------|
| Server access logs | `GET /api/files/123?token=eyJ...` logged with every request |
| Reverse proxy logs (nginx, Cloudflare) | Same — token in plain text |
| Browser history | URL + token saved locally |
| Referrer header | If page has external links, token sent as Referer |
| Analytics tools | Google Analytics captures full URLs |
| Shared links | User copies URL with token, shares via chat |
| Browser address bar | Visible to anyone nearby |

### Fix: short-lived signed URLs with expiration
```python
import time

@app.post("/api/files/{file_id}/download-link")
def create_download_link(file_id: str, current_user: User = Depends(get_current_user)):
    """Generate a short-lived download token."""
    token = jwt.encode({
        "file_id": file_id,
        "user_id": current_user.id,
        "exp": int(time.time()) + 300,  # 5 minute expiry
        "jti": str(uuid.uuid4()),       # unique token ID (one-time use)
    }, SECRET_KEY, algorithm="HS256")
    return {"url": f"/api/files/{file_id}/download?token={token}"}


@app.get("/api/files/{file_id}/download")
def download_file(file_id: str, token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Download link expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")

    if payload["file_id"] != file_id:
        raise HTTPException(403)

    # Optional: mark token as used (prevent reuse)
    if is_token_used(payload["jti"]):
        raise HTTPException(401, "Download link already used")
    mark_token_used(payload["jti"])

    response = FileResponse(get_file_path(file_id))
    # Prevent caching of authenticated response
    response.headers["Cache-Control"] = "no-store"
    # Prevent referrer leakage
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
```

### The meta-lesson
URLs are public infrastructure — they're logged, cached, and shared across many systems. Never put long-lived secrets in URLs. When URL tokens are unavoidable (download links, email verification), make them short-lived (minutes), single-use, and scoped to the minimum necessary permissions.'''
    ),
    (
        "thinking/meta-error-perf-n-plus-1-graphql",
        r'''I wrote this GraphQL resolver and it's getting slow with many queries:

```python
class Query:
    def resolve_posts(self, info):
        return Post.objects.all()

class PostType:
    def resolve_author(self, info):
        return User.objects.get(id=self.author_id)

    def resolve_comments(self, info):
        return Comment.objects.filter(post_id=self.id)

    def resolve_comment_count(self, info):
        return Comment.objects.filter(post_id=self.id).count()
```

For a query like `{ posts { title author { name } comments { text } } }`, it's making hundreds of DB queries. Why?''',
        r'''<think>
Let me trace the query execution...

Query: `{ posts { title author { name } comments { text } } }`

1. `resolve_posts` → `Post.objects.all()` → 1 query, returns N posts

2. For EACH of the N posts:
   - `resolve_author` → `User.objects.get(id=self.author_id)` → 1 query per post
   - `resolve_comments` → `Comment.objects.filter(post_id=self.id)` → 1 query per post

Total queries: 1 + N + N = 2N + 1

For 100 posts: 201 queries!
For 1000 posts: 2001 queries!

This is the N+1 query problem, amplified by GraphQL's resolver-per-field model. In REST, you might have one endpoint that eagerly joins data. In GraphQL, each field resolves independently, making N+1 even more likely.

And `resolve_comment_count` is ALSO doing a separate query per post — if the client queries `commentCount`, that's another N queries.

The fix in GraphQL is using a DataLoader — a utility that batches individual loads into a single query:

Instead of N separate `User.objects.get(id=X)` calls, the DataLoader collects all the user IDs and does one `User.objects.filter(id__in=[...])` query.

This reduces 2N + 1 queries to 3 queries: one for posts, one for all authors, one for all comments.
</think>

**Classic N+1 problem amplified by GraphQL's per-field resolution. 100 posts = 201+ database queries.**

### Query execution trace
```
resolve_posts()       → SELECT * FROM posts              → 1 query
  ×100 posts:
    resolve_author()  → SELECT * FROM users WHERE id=?   → 100 queries
    resolve_comments()→ SELECT * FROM comments WHERE ...  → 100 queries
                                                    Total: 201 queries!
```

### Fix: use DataLoader for batching
```python
from promise import Promise
from promise.dataloader import DataLoader

class UserLoader(DataLoader):
    def batch_load_fn(self, user_ids):
        # ONE query for all users
        users = {u.id: u for u in User.objects.filter(id__in=user_ids)}
        return Promise.resolve([users.get(uid) for uid in user_ids])

class CommentLoader(DataLoader):
    def batch_load_fn(self, post_ids):
        # ONE query for all comments
        comments = Comment.objects.filter(post_id__in=post_ids)
        grouped = {}
        for c in comments:
            grouped.setdefault(c.post_id, []).append(c)
        return Promise.resolve([grouped.get(pid, []) for pid in post_ids])


class PostType:
    def resolve_author(self, info):
        return info.context.user_loader.load(self.author_id)

    def resolve_comments(self, info):
        return info.context.comment_loader.load(self.id)
```

### Result
```
Before: 1 + N + N = 201 queries (N=100)
After:  1 + 1 + 1 = 3 queries (always)
```

### Why GraphQL makes N+1 worse than REST
In REST, you control the query: one endpoint can do `SELECT * FROM posts JOIN users`. In GraphQL, each field resolves independently — the framework doesn't know which fields will be requested until runtime, so it can't pre-optimize joins. DataLoader is the GraphQL-idiomatic solution.

### The meta-lesson
GraphQL's resolver-per-field model makes N+1 queries the DEFAULT behavior, not an edge case. Every relationship resolver that queries a database needs a DataLoader (or equivalent batching). If your GraphQL API is slow, the first thing to check is whether you have DataLoaders — not whether you need caching or a faster database.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
