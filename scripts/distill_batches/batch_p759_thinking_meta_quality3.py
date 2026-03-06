"""Phase 3F: Metacognition — Code Quality Judgment (Part 3)

Scenario 3: Rate code security with threat modeling (OWASP top 10).
Scenario 4: Rate code performance with complexity analysis.
"""

PAIRS = [
    (
        "thinking/meta-quality-security-user-profile",
        r'''Rate the security of this user profile endpoint (1-10):

```python
@app.route('/api/profile/<user_id>', methods=['GET', 'PUT'])
def profile(user_id):
    if request.method == 'GET':
        user = db.query(User).get(user_id)
        return jsonify(user.to_dict())

    elif request.method == 'PUT':
        user = db.query(User).get(user_id)
        data = request.json
        for key, value in data.items():
            setattr(user, key, value)
        db.commit()
        return jsonify(user.to_dict())
```''',
        r'''<think>
Let me check against OWASP Top 10 and common vulnerabilities:

1. **Broken Access Control (OWASP #1)**: No authentication check. Any user can read/modify any other user's profile by changing the user_id in the URL. CRITICAL.

2. **Mass Assignment (part of OWASP #1)**: `setattr(user, key, value)` for every key in the request. An attacker can set `is_admin=True`, `role="superuser"`, `password_hash="..."`, or any database column. CRITICAL.

3. **Injection**: Not directly (using ORM), but `user_id` from URL is passed directly to `.get()`. If user_id is expected to be an integer, no validation is done. LOW.

4. **Security Misconfiguration**: `user.to_dict()` might expose sensitive fields (password hash, email, internal IDs). No field filtering. MEDIUM.

5. **No input validation**: The PUT endpoint accepts any JSON without validation. No type checking, no length limits.

6. **No rate limiting**: An attacker could enumerate all user profiles with sequential IDs.

7. **IDOR (Insecure Direct Object Reference)**: user_id is a sequential integer in the URL, easily guessable.

This has at least 2 critical vulnerabilities. Score: 1/10.
</think>

**Security: 1/10 — Two critical vulnerabilities.**

**Critical #1: No authentication/authorization**
Any anonymous user can read or modify ANY user's profile:
```bash
# Read anyone's profile
curl https://api.example.com/api/profile/1
curl https://api.example.com/api/profile/2  # Just increment the ID

# Escalate to admin
curl -X PUT https://api.example.com/api/profile/1 \
  -d '{"is_admin": true}'
```

**Critical #2: Mass assignment via setattr**
```python
for key, value in data.items():
    setattr(user, key, value)  # Attacker controls EVERY field
```
An attacker can set: `is_admin`, `role`, `password_hash`, `email_verified`, `balance` — anything.

**Fixed version:**
```python
from flask_login import login_required, current_user

ALLOWED_FIELDS = {"display_name", "bio", "avatar_url"}

@app.route('/api/profile/<int:user_id>', methods=['GET', 'PUT'])
@login_required
def profile(user_id):
    if current_user.id != user_id and not current_user.is_admin:
        return jsonify({"error": "Forbidden"}), 403

    user = db.query(User).get_or_404(user_id)

    if request.method == 'GET':
        return jsonify(user.to_public_dict())  # Filter sensitive fields

    elif request.method == 'PUT':
        data = request.json
        for key, value in data.items():
            if key in ALLOWED_FIELDS:  # Whitelist fields
                setattr(user, key, value)
        db.commit()
        return jsonify(user.to_public_dict())
```

**OWASP checklist for this endpoint:**
| OWASP | Issue | Severity |
|-------|-------|----------|
| A01 Broken Access Control | No auth, no authz, IDOR | Critical |
| A01 Mass Assignment | setattr on all fields | Critical |
| A04 Insecure Design | Sequential IDs, no field filtering | Medium |
| A07 Missing Auth | No @login_required | Critical |'''
    ),
    (
        "thinking/meta-quality-security-file-upload",
        r'''Rate the security of this file upload endpoint (1-10):

```python
@app.route('/upload', methods=['POST'])
@login_required
def upload():
    file = request.files['file']
    filename = file.filename
    filepath = os.path.join('/uploads', filename)
    file.save(filepath)
    return jsonify({"url": f"/uploads/{filename}"})
```''',
        r'''<think>
Let me check security issues:

1. **Path Traversal**: `filename` comes from the user. If they send `filename = "../../etc/passwd"`, `os.path.join('/uploads', '../../etc/passwd')` = `/etc/passwd`. The attacker can overwrite ANY file on the filesystem. CRITICAL.

2. **No file type validation**: User can upload .py, .php, .sh, .exe — anything. If the uploads directory is served by a web server that executes scripts, this is Remote Code Execution. CRITICAL.

3. **No file size limit**: User can upload a 10GB file, filling the disk. DoS vector. MEDIUM.

4. **Filename collisions**: Two users uploading "photo.jpg" overwrite each other's files.

5. **No content-type validation**: The file extension might not match the actual content. A .jpg could be a PHP script.

6. **Serving user uploads from the same domain**: If uploads are served from the same origin, XSS via uploaded HTML/SVG files.

At least 2 critical vulnerabilities. Score: 2/10 (gets 1 point for having @login_required and 1 for using the ORM-like pattern).
</think>

**Security: 2/10**

**Critical #1: Path traversal → arbitrary file overwrite**
```bash
# Attacker uploads with crafted filename:
curl -F "file=@malware.sh;filename=../../usr/local/bin/startup.sh" /upload
# Overwrites server startup script
```

**Critical #2: No file type restriction → code execution**
If uploads directory is web-accessible and the server executes scripts:
```bash
curl -F "file=@shell.php;filename=shell.php" /upload
curl https://example.com/uploads/shell.php  # Remote code execution
```

**Fixed version:**
```python
import uuid
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "No file"}), 400

    # Check file size
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        return jsonify({"error": "File too large"}), 413

    # Validate extension
    ext = os.path.splitext(secure_filename(file.filename))[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "File type not allowed"}), 400

    # Generate safe filename (no user input in path)
    safe_name = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join('/uploads', safe_name)
    file.save(filepath)

    return jsonify({"url": f"/uploads/{safe_name}"})
```

**Security fixes:**
- `secure_filename()` sanitizes path traversal
- UUID filenames prevent collisions and path manipulation
- Extension allowlist blocks script uploads
- File size limit prevents DoS'''
    ),
    (
        "thinking/meta-quality-security-jwt-implementation",
        r'''Rate the security of this JWT authentication (1-10):

```python
import jwt
import time

SECRET = "mysecretkey123"

def create_token(user_id):
    return jwt.encode({"user_id": user_id, "exp": time.time() + 86400}, SECRET, algorithm="HS256")

def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        return payload["user_id"]
    except jwt.InvalidTokenError:
        return None
```''',
        r'''<think>
Let me evaluate:

1. **Weak secret key**: `"mysecretkey123"` is trivially brute-forceable. HS256 with a weak secret can be cracked in seconds. CRITICAL.

2. **Hardcoded secret**: The key is in source code, likely committed to git. Should be in environment variable. HIGH.

3. **Algorithm is specified (good)**: Using `algorithms=["HS256"]` prevents the "none" algorithm attack. ✓

4. **Expiration is set (good)**: 24-hour expiry. ✓

5. **No token revocation**: Once issued, a token is valid for 24 hours even if the user changes password, is banned, or reports account compromise. MEDIUM.

6. **No issuer/audience claims**: No `iss` or `aud` claims, making the token usable across different services if they share the secret. LOW.

7. **Token in payload**: Only `user_id` and `exp`. No session ID for revocation. No `iat` (issued at) for rotation tracking.

8. **HS256 vs RS256**: HS256 (symmetric) means anyone who can verify tokens can also create them. For microservices, RS256 (asymmetric) is better — only the auth service has the private key.

The weak hardcoded secret is the critical issue. Otherwise the implementation is reasonable. Score: 4/10.
</think>

**Security: 4/10**

**Critical: Weak, hardcoded secret**
```python
SECRET = "mysecretkey123"  # Crackable in seconds with hashcat
```
```bash
hashcat -a 3 -m 16500 jwt_token.txt ?a?a?a?a?a?a?a?a?a?a?a?a?a?a?a
# Cracks "mysecretkey123" in minutes
```

**What's done right:**
- ✅ Algorithm pinned to HS256 (prevents "none" algorithm attack)
- ✅ Expiration set (24 hours)
- ✅ Exception handling for invalid tokens

**What's wrong:**

| Issue | Severity | Fix |
|-------|----------|-----|
| Weak secret | Critical | 256-bit random key |
| Hardcoded secret | High | Environment variable |
| No token revocation | Medium | Token blacklist or short expiry + refresh tokens |
| No iss/aud claims | Low | Add issuer and audience |

**Fixed version:**
```python
import jwt
import os
import time
import secrets

# Strong secret from environment (or generate once and store securely)
SECRET = os.environ["JWT_SECRET"]  # Should be: secrets.token_hex(32)

def create_token(user_id):
    return jwt.encode({
        "user_id": user_id,
        "exp": time.time() + 3600,  # 1 hour, not 24
        "iat": time.time(),
        "iss": "myapp",
    }, SECRET, algorithm="HS256")

def verify_token(token):
    try:
        payload = jwt.decode(
            token, SECRET,
            algorithms=["HS256"],
            issuer="myapp",
        )
        return payload["user_id"]
    except jwt.InvalidTokenError:
        return None
```

**Generate a proper secret:** `python -c "import secrets; print(secrets.token_hex(32))"`'''
    ),
    (
        "thinking/meta-quality-performance-nested-loop",
        r'''Rate the performance of this duplicate finder (1-10):

```python
def find_duplicates(items):
    duplicates = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] == items[j]:
                if items[i] not in duplicates:
                    duplicates.append(items[i])
    return duplicates
```''',
        r'''<think>
Let me analyze complexity:

**Time complexity:**
- Outer loop: O(n)
- Inner loop: O(n) for each outer iteration
- `items[i] not in duplicates`: O(d) where d is the number of duplicates found so far
- Worst case: O(n² × d), which is O(n³) if all items are duplicates

**Space complexity:** O(d) for the duplicates list.

For n=1000: ~500,000 comparisons (manageable)
For n=10,000: ~50,000,000 comparisons (slow)
For n=100,000: ~5,000,000,000 comparisons (unusable)
For n=1,000,000: heat death of universe

The `not in duplicates` check on a list is also O(d), adding to the inefficiency.

**Optimal solution:** O(n) with a Counter or set-based approach.

Score: 2/10 for performance. It works for tiny inputs but is catastrophically slow for anything beyond a few thousand items.
</think>

**Performance: 2/10**

**Complexity: O(n³) worst case**
- Nested loops: O(n²)
- `not in duplicates` (list search): O(d) per check
- If all items are duplicates: O(n² × n) = O(n³)

**Scaling:**
| n | Comparisons | Time |
|---|-------------|------|
| 100 | ~5,000 | Instant |
| 1,000 | ~500,000 | ~50ms |
| 10,000 | ~50M | ~30s |
| 100,000 | ~5B | Hours |

**O(n) solution:**
```python
from collections import Counter

def find_duplicates(items):
    counts = Counter(items)
    return [item for item, count in counts.items() if count > 1]
```

**Or with a set (also O(n)):**
```python
def find_duplicates(items):
    seen = set()
    duplicates = set()
    for item in items:
        if item in seen:
            duplicates.add(item)
        seen.add(item)
    return list(duplicates)
```

Both are O(n) time, O(n) space. The Counter version is more Pythonic.

**Why the original is O(n³):**
1. **O(n²)**: comparing every pair → use a hash set instead
2. **O(n)**: `not in duplicates` on a list → use a set (O(1) lookup)
3. **Combined**: O(n² × n) = O(n³)

Replace list-based "have I seen this?" checks with set-based checks. Sets give O(1) membership testing.'''
    ),
    (
        "thinking/meta-quality-performance-n-plus-one",
        r'''Rate the performance of this API endpoint (1-10):

```python
@app.get("/api/posts")
def list_posts():
    posts = db.query(Post).limit(20).all()
    result = []
    for post in posts:
        author = db.query(User).get(post.author_id)
        comments = db.query(Comment).filter_by(post_id=post.id).all()
        result.append({
            "title": post.title,
            "author": author.name,
            "comment_count": len(comments),
        })
    return jsonify(result)
```''',
        r'''<think>
Classic N+1 query problem.

**Query count:**
- 1 query for posts (20 rows)
- 20 queries for authors (one per post)
- 20 queries for comments (one per post)
- Total: 41 queries for 20 posts

**If limit were 100:** 201 queries.

**Time analysis:**
Each query has network round-trip overhead (~1-5ms local, ~10-50ms remote).
41 queries × 5ms = ~200ms just in network overhead.
41 queries × 50ms (remote DB) = ~2 seconds.

**Additionally:** Fetching ALL comments just to count them (`len(comments)`) loads entire comment objects into memory when a COUNT query would suffice.

**Optimal approach:** 1-3 queries using JOINs or eager loading.

Score: 3/10. Works correctly but has 41 queries where 1-3 would suffice.
</think>

**Performance: 3/10 — Classic N+1 query problem**

**Current: 41 queries for 20 posts**
```
Query 1:  SELECT * FROM posts LIMIT 20
Query 2:  SELECT * FROM users WHERE id = 1    ← per post
Query 3:  SELECT * FROM users WHERE id = 2
...
Query 21: SELECT * FROM users WHERE id = 20
Query 22: SELECT * FROM comments WHERE post_id = 1  ← per post
...
Query 41: SELECT * FROM comments WHERE post_id = 20
```

**Additional waste:** Loading ALL comment objects just to count them.

**Fixed — 1 query with JOINs:**
```python
@app.get("/api/posts")
def list_posts():
    results = db.query(
        Post.title,
        User.name.label("author_name"),
        func.count(Comment.id).label("comment_count")
    ).join(User, Post.author_id == User.id
    ).outerjoin(Comment, Comment.post_id == Post.id
    ).group_by(Post.id, User.name
    ).limit(20).all()

    return jsonify([{
        "title": r.title,
        "author": r.author_name,
        "comment_count": r.comment_count,
    } for r in results])
```

**Or with eager loading (simpler):**
```python
posts = db.query(Post).options(
    joinedload(Post.author),
    subqueryload(Post.comments)
).limit(20).all()
```

**Performance comparison:**
| Approach | Queries | Time (local) | Time (remote DB) |
|----------|---------|-------------|-----------------|
| N+1 (original) | 41 | ~200ms | ~2s |
| Eager loading | 3 | ~15ms | ~150ms |
| Single JOIN | 1 | ~5ms | ~50ms |'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
