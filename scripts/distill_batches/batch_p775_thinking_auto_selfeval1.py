"""Phase 4B: Self-Improvement — Self-Evaluation (Part 1)

The model learns to evaluate its own outputs for quality, correctness, and completeness.
"""

PAIRS = [
    (
        "thinking/auto-selfeval-check-own-code-bugs",
        r'''I just generated this Python code to solve FizzBuzz. Before I present it to the user, let me evaluate it for correctness:

```python
def fizzbuzz(n):
    for i in range(n):
        if i % 3 == 0 and i % 5 == 0:
            print("FizzBuzz")
        elif i % 3 == 0:
            print("Fizz")
        elif i % 5 == 0:
            print("Buzz")
        else:
            print(i)
```

Is this correct?''',
        r'''<think>
Let me evaluate my own output by tracing through it:

**Correctness check — trace with small inputs:**
- i=0: 0%3==0 AND 0%5==0 → "FizzBuzz" — Wait, 0 is divisible by everything. Most FizzBuzz implementations start at 1, not 0. This is a bug.
- i=1: prints 1 ✓
- i=2: prints 2 ✓
- i=3: 3%3==0 → "Fizz" ✓
- i=5: 5%5==0 → "Buzz" ✓
- i=15: 15%3==0 AND 15%5==0 → "FizzBuzz" ✓

**Issues found:**
1. `range(n)` starts at 0 — FizzBuzz traditionally goes from 1 to n inclusive. Should be `range(1, n+1)`.
2. At i=0, prints "FizzBuzz" which is wrong — 0 shouldn't be in the output at all.
3. Returns None (uses print, not return) — fine if the spec says "print", but less reusable.

**Quality check:**
- Logic order: checks 3 AND 5 first (correct, avoids printing just "Fizz" or "Buzz" for multiples of 15) ✓
- Uses elif chain (efficient, only one check needed per number) ✓
- No unnecessary variables ✓

**Verdict:** Has a bug — off-by-one on the range. Fix before presenting.
</think>

**Found a bug: `range(n)` starts at 0, should start at 1.**

**Self-evaluation results:**
| Check | Status | Issue |
|-------|--------|-------|
| Logic order (15 before 3 and 5) | ✅ Pass | Correct priority |
| Range boundaries | ❌ Fail | Starts at 0, should be 1 to n |
| Output at i=0 | ❌ Fail | Prints "FizzBuzz" for 0 |
| Core fizz/buzz logic | ✅ Pass | Modulo checks are correct |
| Performance | ✅ Pass | O(n), single pass |

**Corrected version:**
```python
def fizzbuzz(n):
    for i in range(1, n + 1):  # Start at 1, include n
        if i % 3 == 0 and i % 5 == 0:
            print("FizzBuzz")
        elif i % 3 == 0:
            print("Fizz")
        elif i % 5 == 0:
            print("Buzz")
        else:
            print(i)
```

**Self-evaluation process used:**
1. Traced execution with boundary values (0, 1, 3, 5, 15)
2. Checked against the problem specification
3. Identified the off-by-one error before presenting to user'''
    ),
    (
        "thinking/auto-selfeval-check-own-explanation",
        r'''I just generated this explanation of Python's GIL. Let me evaluate it before presenting:

"The GIL (Global Interpreter Lock) is a mutex that protects Python objects from concurrent access. It means Python can't use multiple CPU cores, so multi-threading is useless in Python. You should always use multiprocessing instead of threading."

Is this explanation accurate and complete?''',
        r'''<think>
Let me self-evaluate this explanation for accuracy:

**Claim 1: "GIL is a mutex that protects Python objects from concurrent access"**
Partially correct. The GIL protects the reference counting mechanism in CPython specifically. It's not about "Python objects" in general — it's about the interpreter state and reference counts. Other Python implementations (Jython, PyPy-STM) may not have a GIL.

**Claim 2: "Python can't use multiple CPU cores"**
Misleading. CPython threads can't use multiple cores for CPU-bound PYTHON code. But:
- C extensions can release the GIL (NumPy, pandas operations DO use multiple cores)
- multiprocessing uses multiple cores
- Python 3.12+ has per-interpreter GILs, 3.13+ has experimental free-threading

**Claim 3: "Multi-threading is useless in Python"**
WRONG. Threading is excellent for I/O-bound work: network requests, file I/O, database queries. The GIL is released during I/O operations, so threads run truly concurrently for I/O.

**Claim 4: "You should always use multiprocessing instead of threading"**
WRONG. Multiprocessing has high overhead (process creation, IPC, memory). For I/O-bound work, threading or asyncio is better. Multiprocessing is only better for CPU-bound work.

**Missing information:**
- The GIL is a CPython implementation detail, not a Python language feature
- asyncio as an alternative for I/O concurrency
- Python 3.13 free-threading (no-GIL) mode

**Verdict:** This explanation has significant inaccuracies. The blanket statements about threading being "useless" and "always use multiprocessing" are wrong. Needs major revision.
</think>

**Self-evaluation: This explanation has significant inaccuracies. Rating: 3/10.**

| Claim | Accurate? | Issue |
|-------|-----------|-------|
| "GIL is a mutex protecting objects" | Partially | Protects reference counting in CPython specifically |
| "Can't use multiple CPU cores" | Misleading | Only for CPU-bound Python code; C extensions can |
| "Threading is useless" | **Wrong** | Threading is great for I/O-bound work |
| "Always use multiprocessing" | **Wrong** | Multiprocessing has high overhead, bad for I/O |

**Corrected explanation:**
"The GIL (Global Interpreter Lock) is a mutex in CPython that prevents multiple threads from executing Python bytecode simultaneously. This means CPU-bound Python code can't benefit from multi-threading. However, threading IS useful for I/O-bound work (network requests, file I/O, database queries) because the GIL is released during I/O operations. For CPU-bound work, use multiprocessing or C extensions (NumPy, etc.) which release the GIL. Note: Python 3.13+ has an experimental free-threading mode that removes the GIL entirely."

**Self-evaluation checklist applied:**
1. ✅ Check each factual claim individually
2. ✅ Look for absolute statements ("always", "never", "useless") — usually wrong
3. ✅ Check for missing important context
4. ✅ Verify against known edge cases and exceptions'''
    ),
    (
        "thinking/auto-selfeval-check-own-security-advice",
        r'''I just generated this security advice for a user asking about password storage. Let me evaluate it:

"To store passwords securely:
1. Use SHA-256 to hash the password
2. Add a salt — concatenate a random string before hashing
3. Store the salt alongside the hash in the database
4. To verify: hash(salt + password) == stored_hash"

Is this advice correct and complete?''',
        r'''<think>
Let me self-evaluate this security advice:

**Claim 1: "Use SHA-256 to hash the password"**
WRONG for passwords. SHA-256 is a fast hash — designed to be computed quickly. For passwords, you want a SLOW hash (bcrypt, argon2, scrypt) that's resistant to brute-force attacks. SHA-256 can be computed billions of times per second on a GPU. bcrypt is intentionally slow.

**Claim 2: "Add a salt — concatenate a random string before hashing"**
Partially correct concept. Salting is necessary to prevent rainbow table attacks. But:
- "Concatenate" is vague — the order matters (salt + password vs password + salt)
- The salt generation method isn't specified (must be cryptographically random)
- The salt length isn't specified (should be at least 16 bytes)
- More importantly: dedicated password hashing functions (bcrypt, argon2) handle salting automatically

**Claim 3: "Store the salt alongside the hash"**
Correct concept. The salt is not secret.

**Claim 4: "hash(salt + password) == stored_hash"**
Correct concept for verification, but:
- Must use constant-time comparison to prevent timing attacks
- With bcrypt/argon2, this is handled by the library's verify function

**Critical missing information:**
- Should recommend bcrypt, argon2id, or scrypt — NOT SHA-256
- Should recommend using a library function, not rolling your own
- No mention of work factor / cost parameter
- No mention of timing-safe comparison

**Verdict:** This advice would lead to insecure password storage. SHA-256 is the wrong algorithm for passwords. Must revise.
</think>

**Self-evaluation: This advice is INSECURE. Rating: 2/10.**

**Critical error: SHA-256 is wrong for passwords.**

| Recommendation | Correct? | Issue |
|---------------|----------|-------|
| Use SHA-256 | **Wrong** | Too fast; use bcrypt/argon2 |
| Add a salt | Partially | Right concept, but bcrypt does this automatically |
| Store salt with hash | Correct | Salt is not secret |
| Verify by re-hashing | Partially | Must use constant-time comparison |

**Why SHA-256 is dangerous for passwords:**
```
SHA-256: ~10 billion hashes/second on modern GPU
bcrypt:  ~30,000 hashes/second on same GPU

An 8-char password brute-force:
SHA-256: hours
bcrypt:  centuries
```

**Corrected advice:**
```python
# Use bcrypt (or argon2id) — handles salting automatically
import bcrypt

# Hash a password
password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))

# Verify a password (constant-time comparison built in)
is_valid = bcrypt.checkpw(password.encode(), stored_hash)
```

**Self-evaluation lessons learned:**
1. SHA-256 is a general-purpose hash, not a password hash — this is a common misconception I should catch
2. When giving security advice, I should recommend specific libraries, not DIY approaches
3. I should flag when advice could lead to vulnerabilities if followed'''
    ),
    (
        "thinking/auto-selfeval-check-own-architecture",
        r'''I just recommended this architecture to a user building a todo app:

"For your todo app, I recommend:
- React frontend with Redux for state management
- Node.js backend with Express
- PostgreSQL database
- Redis for caching
- RabbitMQ for async task processing
- Docker + Kubernetes for deployment
- Elasticsearch for search
- GraphQL API layer"

Should I present this recommendation as-is?''',
        r'''<think>
Let me self-evaluate this architecture recommendation:

**Context check:** This is a TODO APP. One of the simplest possible applications. Let me evaluate each component against the actual requirements:

1. **React** — Reasonable for a frontend, though even this might be overkill. A todo app could be vanilla HTML + JS.

2. **Redux** — Massive overkill. A todo app has trivial state (a list of items). Redux adds boilerplate and complexity for state management that's needed at scale. React's built-in useState or useContext is sufficient.

3. **Node.js + Express** — Reasonable as a backend, though any framework works.

4. **PostgreSQL** — Reasonable, though SQLite would be simpler and sufficient for a todo app.

5. **Redis for caching** — For what? A todo app with a few hundred items doesn't need caching. This adds operational complexity for zero benefit.

6. **RabbitMQ** — For what async tasks? Sending todo reminder emails? Way overkill. A simple cron job or setTimeout would suffice.

7. **Docker + Kubernetes** — Kubernetes for a todo app is like renting a cruise ship to cross a puddle. A single server or even a static deployment (Vercel, Netlify) would work.

8. **Elasticsearch** — For searching... a list of todos? A SQL LIKE query or simple in-memory filter handles this trivially.

9. **GraphQL** — For a CRUD todo API with maybe 3 endpoints? REST is simpler and perfectly adequate.

**Verdict:** This is massively over-engineered. I'm recommending enterprise architecture for a simple CRUD app. This would take weeks to set up instead of hours, and the user would spend more time on infrastructure than on the actual todo features.
</think>

**Self-evaluation: OVER-ENGINEERED. Do not present this. Rating: 2/10.**

**This is enterprise architecture for a todo app.** Every component except the core (frontend + backend + database) is unnecessary.

| Component | Needed for a todo app? | Why not |
|-----------|----------------------|---------|
| React | Maybe | Vanilla JS works fine for a todo list |
| Redux | No | useState/useContext handles todo state trivially |
| PostgreSQL | Maybe | SQLite is simpler and sufficient |
| Redis | No | Nothing to cache with a few hundred items |
| RabbitMQ | No | No async tasks to process |
| Kubernetes | No | Single server or static hosting is fine |
| Elasticsearch | No | SQL LIKE or array.filter() works |
| GraphQL | No | 3 REST endpoints are simpler |

**Corrected recommendation:**
"For a todo app, keep it simple:
- **Frontend:** React (or even vanilla JS) with useState
- **Backend:** Express or FastAPI, 3-4 REST endpoints
- **Database:** SQLite (or PostgreSQL if you plan to scale later)
- **Deployment:** Vercel, Railway, or a single server

You can build this in a weekend. Add complexity only when you hit specific problems that require it."

**Self-evaluation lesson:** Match architecture to actual requirements. Recommending Kubernetes for a todo app signals that I'm optimizing for resume keywords, not for the user's needs.'''
    ),
    (
        "thinking/auto-selfeval-check-own-completeness",
        r'''I just generated this answer to "How do I handle file uploads in Flask?" Let me evaluate it:

```python
@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    file.save(f'uploads/{file.filename}')
    return 'Uploaded!'
```

"Here's how to handle file uploads in Flask. Save the file to an uploads directory using file.save()."

Is this answer complete and safe to present?''',
        r'''<think>
Let me self-evaluate this answer for completeness and safety:

**Correctness:** The basic mechanism works — `request.files['file']` and `file.save()` are correct Flask APIs. ✓

**Security issues I'm NOT warning about:**
1. Path traversal: `file.filename` could be `../../etc/passwd` — need `secure_filename()`
2. No file type validation — user could upload malicious executables
3. No file size limit — DoS vector
4. No authentication — anyone can upload

**Completeness issues:**
1. No error handling — what if no file is in the request?
2. No `enctype="multipart/form-data"` mentioned for the HTML form
3. No mention of creating the uploads directory
4. No file size configuration
5. No content-type validation
6. Filename collisions not handled

**Quality issues:**
1. The response 'Uploaded!' is a plain string, not JSON — inconsistent with modern API practices
2. No return of the file URL or metadata
3. No mention of where the file is accessible after upload

**Verdict:** This answer is dangerously incomplete. The code has a path traversal vulnerability, and the explanation doesn't mention any of the critical considerations for file uploads. Needs major expansion.
</think>

**Self-evaluation: INCOMPLETE AND INSECURE. Rating: 2/10.**

**What's missing:**
| Issue | Severity | Status |
|-------|----------|--------|
| Path traversal vulnerability | Critical | Not mentioned |
| No file type validation | High | Not mentioned |
| No file size limit | Medium | Not mentioned |
| No error handling | Medium | Not mentioned |
| No form configuration | Low | Not mentioned |

**Corrected answer I should present instead:**

```python
import os
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    filename = secure_filename(file.filename)  # Prevents path traversal
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    return jsonify({"filename": filename}), 201
```

**Self-evaluation process:** Before presenting any file upload code, check: (1) secure_filename, (2) file type validation, (3) size limits, (4) error handling. These are non-negotiable for file uploads.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
