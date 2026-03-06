"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 27)"""

PAIRS = [
    (
        "thinking/adversarial-mass-assignment",
        "I use request.body directly to create database records: User.create(**request.json). My colleague says this is dangerous. Why?",
        r'''<think>
Mass assignment vulnerability — a very common and dangerous pattern.

**The attack:**
If User model has fields: name, email, password_hash, is_admin, balance
And the API accepts: POST /register { "name": "Dan", "email": "dan@..." }

The developer expects only name and email. But an attacker sends:
POST /register { "name": "Dan", "email": "dan@...", "is_admin": true, "balance": 999999 }

User.create(**request.json) creates the user with is_admin=true and balance=999999 because the request body is passed directly to the model constructor.

This is called "mass assignment" because the attacker can assign values to ANY model field, not just the intended ones.

Famous examples: GitHub had this vulnerability in 2012 — an attacker was able to add their SSH key to any repository by mass-assigning the user_id field.
</think>

This is a **mass assignment** vulnerability. An attacker can set ANY model field, including ones you didn't intend to be settable.

## The Attack

```python
# YOUR CODE:
@app.post("/register")
async def register(request):
    data = await request.json()
    user = User.create(**data)  # Passes ALL fields from request to model
    return {"id": user.id}

# EXPECTED REQUEST:
POST /register
{"name": "Dan", "email": "dan@example.com", "password": "s3cure!"}
# Creates: User(name="Dan", email="dan@example.com", password="s3cure!")
# ✓ Works as intended

# ATTACKER'S REQUEST:
POST /register
{
    "name": "Dan",
    "email": "dan@example.com",
    "password": "s3cure!",
    "is_admin": true,          # ← attacker is now admin
    "balance": 999999,         # ← attacker has $999,999
    "email_verified": true,    # ← bypasses email verification
    "role": "superuser"        # ← highest privileges
}
# Creates: User(name="Dan", ..., is_admin=true, balance=999999, ...)
# Attacker is now an admin with $999,999
```

## The Fix: Whitelist Allowed Fields

```python
# ✅ FIX 1: Explicit field whitelist
@app.post("/register")
async def register(request):
    data = await request.json()

    # Only allow these specific fields
    allowed_fields = {"name", "email", "password"}
    safe_data = {k: v for k, v in data.items() if k in allowed_fields}

    user = User.create(**safe_data)
    return {"id": user.id}
    # is_admin, balance, role → silently ignored


# ✅ FIX 2: Pydantic/dataclass schema (best approach)
from pydantic import BaseModel

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    # Only these 3 fields can be set. Everything else is rejected.

@app.post("/register")
async def register(data: RegisterRequest):
    user = User.create(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        is_admin=False,        # Explicitly set server-side
        balance=0,             # Explicitly set server-side
        email_verified=False,  # Explicitly set server-side
    )
    return {"id": user.id}


# ✅ FIX 3: Django — use serializers with explicit fields
# serializers.py
class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['name', 'email', 'password']  # Only these fields
        extra_kwargs = {'password': {'write_only': True}}

    # is_admin, balance, role are NOT in fields → can't be mass-assigned
```

## Different Frameworks, Same Problem

```python
# Django — ❌ VULNERABLE:
User.objects.create(**request.POST)
# ✅ SAFE:
form = RegisterForm(request.POST)  # Form validates allowed fields

# Flask/SQLAlchemy — ❌ VULNERABLE:
user = User(**request.json)
db.session.add(user)
# ✅ SAFE:
schema = RegisterSchema()
data = schema.load(request.json)  # Marshmallow schema validates fields

# Rails — ❌ VULNERABLE:
User.create(params[:user])
# ✅ SAFE:
User.create(params.require(:user).permit(:name, :email, :password))

# Express/Sequelize — ❌ VULNERABLE:
User.create(req.body)
# ✅ SAFE:
const { name, email, password } = req.body;  // Destructure only allowed fields
User.create({ name, email, password });
```

## The Rule

```
NEVER pass raw user input directly to model constructors.

ALWAYS either:
  1. Whitelist allowed fields explicitly
  2. Use a schema/serializer to validate input
  3. Destructure only the fields you expect

Server-controlled fields (is_admin, role, balance, created_at)
should ALWAYS be set server-side, never from user input.
```'''
    ),
    (
        "thinking/uncertainty-when-to-add-typescript",
        "I have a medium-sized JavaScript project (about 15,000 lines). Should I convert to TypeScript now, or is it too late?",
        r'''<think>
Converting an existing 15K line JS project to TypeScript. Is it too late?

**It's NOT too late.** TypeScript supports gradual adoption — you don't have to convert everything at once.

**Factors to consider:**
1. How long will the project live? If years more → worth it
2. How many developers? More developers → more benefit from types
3. How often do you refactor? Frequently → TypeScript makes it safer
4. How many bugs are type-related? ("undefined is not a function")

**Confidence: 80% yes, convert gradually**

The 20% against:
- Project is in maintenance mode (few changes, winding down)
- Solo developer who knows every line
- The conversion cost is high and deadline pressure is real

**The gradual migration approach:**
1. Add tsconfig with allowJs: true
2. Rename new/modified files to .ts
3. Add types to critical paths first (API boundaries, data models)
4. Convert existing files when you touch them
5. Tighten strictness over time
</think>

**80% confidence: yes, convert gradually.** It's never too late for TypeScript — it's designed for incremental adoption.

## Why It's Not Too Late

```
TypeScript was DESIGNED for gradual adoption:
  - .js and .ts files can coexist in the same project
  - allowJs: true → TypeScript handles both
  - You can convert ONE FILE AT A TIME
  - No big-bang rewrite needed

15,000 lines is medium-sized:
  - Whole conversion: maybe 2-4 weeks of focused effort
  - Gradual conversion: 2-3 months of "convert as you touch"
  - Both are very manageable
```

## The Gradual Migration Plan

```bash
# STEP 1: Add TypeScript (15 minutes)
npm install --save-dev typescript @types/node
npx tsc --init
```

```jsonc
// tsconfig.json — start permissive
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "allowJs": true,         // Allow .js files alongside .ts
    "checkJs": false,        // Don't type-check .js files (yet)
    "strict": false,         // Permissive to start
    "noImplicitAny": false,  // Allow implicit 'any'
    "outDir": "./dist",
    "rootDir": "./src",
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*"]
}
```

```
STEP 2: Convert high-value files FIRST
  Priority order:
  1. Data models / types (define your domain types)
  2. API boundaries (request/response types)
  3. Shared utilities (used everywhere)
  4. Business logic (complex functions with many params)
  5. Glue code (simple files, convert when you touch them)

STEP 3: Convert files as you modify them
  Touching user-service.js for a bug fix?
  → Rename to user-service.ts
  → Add types to the functions you're changing
  → Leave the rest as 'any' for now

STEP 4: Tighten strictness over time
  Month 1: allowJs + no strict      → just .ts for new files
  Month 2: noImplicitAny: true      → must declare types (or 'any')
  Month 3: strictNullChecks: true   → catch null/undefined bugs
  Month 6: strict: true             → full TypeScript strictness
```

## The Immediate Benefits

```
Even with partial TypeScript adoption:

DAY 1 (just tsconfig + rename one file):
  - IDE autocomplete starts working for .ts files
  - Import errors caught at compile time
  - Refactoring tools work (rename symbol across files)

WEEK 1 (data models typed):
  interface User {
    id: number;
    name: string;
    email: string;
    role: 'admin' | 'user';  // Can only be these values
  }
  // Now every file that uses User gets autocomplete and type checking

MONTH 1 (API boundaries typed):
  function createOrder(data: CreateOrderRequest): Promise<Order> {
    // TypeScript ensures you pass the right data
    // IDE shows you what fields are required
    // Compile error if you pass wrong types
  }
```

## When NOT to Convert

```
SKIP TYPESCRIPT IF (the 20%):
  □ Project is being decommissioned (< 6 months of life left)
  □ You're the only developer and know every line by heart
  □ The project is in pure maintenance mode (no new features)
  □ Hard deadline where conversion time can't be justified
  □ The codebase is heavily metaprogrammed (dynamic property access everywhere)

IN THESE CASES:
  Consider adding JSDoc type annotations instead:
  /** @param {string} name @returns {User} */
  function createUser(name) { ... }
  // IDE type checking WITHOUT converting to TypeScript
```

**The conversion pays for itself within 2-3 months** through fewer type-related bugs, better refactoring confidence, and faster onboarding for new developers.'''
    ),
    (
        "thinking/causal-slow-docker-build",
        "Our Docker build takes 15 minutes. Most of that time is spent on 'pip install -r requirements.txt' even when requirements haven't changed. Why?",
        r'''<think>
Docker build slow because pip install runs every time. This is a layer caching issue.

**How Docker layer caching works:**
- Each instruction in Dockerfile creates a layer
- If a layer's inputs haven't changed, Docker uses the cached version
- BUT: if any layer changes, ALL subsequent layers are invalidated

**The problem:**
```dockerfile
COPY . /app                      # Layer 1: copies ALL files
RUN pip install -r requirements.txt  # Layer 2: installs dependencies
```

When ANY file in the project changes (even a .py file):
- Layer 1 is invalidated (COPY . changed)
- Layer 2 is ALSO invalidated (previous layer changed)
- pip install runs from scratch even though requirements.txt didn't change

**The fix:**
Copy requirements.txt FIRST (separate layer), then copy the rest of the code:
```dockerfile
COPY requirements.txt /app/          # Layer 1: only requirements
RUN pip install -r requirements.txt  # Layer 2: cached if requirements unchanged
COPY . /app                          # Layer 3: copies rest of code
```

Now when you change a .py file:
- Layer 1: unchanged (requirements.txt didn't change) → cached
- Layer 2: unchanged (layer 1 didn't change) → cached → pip install SKIPPED
- Layer 3: changed (code changed) → rebuilds this layer only
</think>

Docker invalidates **all layers after a change**. If you copy code before installing dependencies, any code change forces a full reinstall.

## The Problem

```dockerfile
# ❌ SLOW: pip install runs on EVERY build
FROM python:3.11-slim

COPY . /app                          # Copies EVERYTHING (including code)
WORKDIR /app
RUN pip install -r requirements.txt  # Installs dependencies

# Why it's slow:
# You change one line in app.py
# → COPY . /app layer is invalidated (code changed)
# → ALL subsequent layers are invalidated
# → pip install runs from scratch (15 minutes)
# → Even though requirements.txt didn't change!
```

## The Fix: Order Matters

```dockerfile
# ✅ FAST: pip install only runs when requirements change
FROM python:3.11-slim

# Step 1: Copy ONLY requirements first
COPY requirements.txt /app/requirements.txt
WORKDIR /app

# Step 2: Install dependencies (cached if requirements.txt unchanged)
RUN pip install --no-cache-dir -r requirements.txt

# Step 3: Copy the rest of the code
COPY . /app

# Now when you change app.py:
# Step 1: requirements.txt unchanged → CACHED ✓
# Step 2: previous layer unchanged → CACHED ✓ (pip install skipped!)
# Step 3: code changed → rebuilds only this layer (2 seconds)
# Total build time: 5 seconds instead of 15 minutes
```

## How Docker Layer Caching Works

```
DOCKERFILE:              LAYERS:
COPY requirements.txt    [Layer 1] ─── cached if file unchanged
RUN pip install          [Layer 2] ─── cached if Layer 1 unchanged
COPY . /app              [Layer 3] ─── rebuilt when code changes
RUN python setup.py      [Layer 4] ─── rebuilt (Layer 3 changed)

KEY RULE:
  If Layer N changes → Layers N+1, N+2, ... ALL rebuild
  So put RARELY CHANGING things FIRST (dependencies)
  And FREQUENTLY CHANGING things LAST (your code)
```

## More Docker Build Optimizations

```dockerfile
# 1. Use .dockerignore (don't copy unnecessary files)
# .dockerignore
.git
node_modules
__pycache__
*.pyc
.env
venv/
tests/
docs/
# Smaller COPY context = faster builds

# 2. Multi-stage build (smaller final image)
# Stage 1: build dependencies
FROM python:3.11 AS builder
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Stage 2: production image (only the installed packages)
FROM python:3.11-slim
COPY --from=builder /root/.local /root/.local
COPY . /app
WORKDIR /app
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "app.py"]
# Final image: 150MB instead of 1.2GB

# 3. Pin versions in requirements.txt
# requirements.txt
flask==3.0.2         # Not just "flask" (which resolves differently each build)
sqlalchemy==2.0.25
```

## The General Principle

```
ORDER DOCKERFILE INSTRUCTIONS BY CHANGE FREQUENCY:

  RARELY CHANGES:   base image, system packages     → TOP (cached most)
  SOMETIMES CHANGES: dependencies (requirements.txt) → MIDDLE
  FREQUENTLY CHANGES: your application code          → BOTTOM (rebuilt most)

  This maximizes cache hits and minimizes rebuild time.
```'''
    ),
    (
        "thinking/multiperspective-api-versioning",
        "How should we version our API? We're debating between URL versioning (/v1/users), header versioning, and query parameter versioning. What's the best approach?",
        r'''<think>
API versioning strategies. Let me analyze each approach from multiple perspectives.

**URL versioning (/v1/users, /v2/users):**
Pros: explicit, visible, easy to understand, works with all clients
Cons: URL changes, complicates routing, temptation to create too many versions

**Header versioning (Accept: application/vnd.myapi.v2+json):**
Pros: clean URLs, separation of concerns, HTTP-correct
Cons: invisible to humans, harder to test (curl needs extra headers), harder to share links

**Query parameter (/users?version=2):**
Pros: explicit, easy to add
Cons: ugly, optional parameters can be forgotten, caching complications

**The practical analysis:**
Most successful APIs use URL versioning because:
1. It's the most visible and understandable
2. It works with every HTTP client
3. curl, browser, documentation all work naturally
4. Stripe, GitHub, Twitter all use it

The purist argument for headers is technically correct (URL should identify the resource, not the representation) but practically less useful.

**Even better than versioning:** design APIs that don't need versioning (additive changes only, never remove fields, use expand/contract).
</think>

Each approach has advocates. Here's the practical analysis.

## The Three Approaches

```
URL VERSIONING: /v1/users, /v2/users
  Used by: Stripe, GitHub, Twitter, Google

HEADER VERSIONING: Accept: application/vnd.myapi.v2+json
  Used by: GitHub (also supports this), some enterprise APIs

QUERY PARAMETER: /users?version=2
  Used by: AWS (some services), Google (some services)
```

## Perspective Analysis

```
DEVELOPER EXPERIENCE:
  URL:    curl https://api.example.com/v1/users     ← Works immediately
  Header: curl -H "Accept: application/vnd.api.v2+json" https://api.example.com/users
          ← Extra step, easy to forget
  Query:  curl https://api.example.com/users?version=2  ← Works, but messy

  Winner: URL versioning (simplest to use, share, document)

TECHNICAL CORRECTNESS:
  URL:    "The URL should identify the resource, not the version"
          /v1/users and /v2/users are different URLs for the same resource → impure
  Header: Content negotiation is the HTTP-correct way
          Same URL, different representation → clean
  Query:  Parameters should filter/modify the resource, not version it

  Winner: Header versioning (most HTTP-correct)

PRACTICAL CACHING:
  URL:    /v1/users and /v2/users are different URLs → CDN caches naturally
  Header: Same URL, different headers → CDN needs Vary header → complex
  Query:  /users?version=1 → CDN caches different params → works but messy

  Winner: URL versioning (best cache behavior)

DOCUMENTATION:
  URL:    "v1 docs here, v2 docs here" → clear separation
  Header: "Same endpoint, different header values" → confusing
  Query:  "Same endpoint, add ?version=2" → okay but cluttered

  Winner: URL versioning (clearest documentation)
```

## Recommendation: URL Versioning + Additive Design

```python
# URL versioning — the practical choice
# api/v1/users.py
@app.get("/v1/users/{user_id}")
async def get_user_v1(user_id: int):
    user = await db.get_user(user_id)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
    }

# api/v2/users.py (added a year later when breaking changes needed)
@app.get("/v2/users/{user_id}")
async def get_user_v2(user_id: int):
    user = await db.get_user(user_id)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "profile": {             # New nested structure (breaking change)
            "avatar_url": user.avatar_url,
            "bio": user.bio,
        },
        "created_at": user.created_at.isoformat(),  # New field
    }
```

## The Better Answer: Avoid Breaking Changes

```
THE BEST API VERSION IS NO VERSION.

ADDITIVE CHANGES (non-breaking):
  ✓ Add new fields to responses      (old clients ignore them)
  ✓ Add new optional request fields   (old clients don't send them)
  ✓ Add new endpoints                 (old clients don't call them)

BREAKING CHANGES (require new version):
  ✗ Remove a field from response
  ✗ Rename a field
  ✗ Change a field's type (string → object)
  ✗ Make a previously optional field required
  ✗ Change the URL structure

IF YOU DESIGN WITH ADDITIVE-ONLY CHANGES:
  You might never need /v2 at all.
  Stripe has been on /v1 for over 10 years.
  They add fields, never remove them.
  They use API version dates in headers for minor behavior changes.
```

## Practical Guidelines

```
FOR MOST TEAMS:
  1. Start with /v1/ in the URL
  2. Design for additive changes (avoid breaking changes)
  3. Only create /v2/ when you MUST make a breaking change
  4. Support /v1/ for at least 12 months after /v2/ launches
  5. Communicate deprecation clearly to API consumers

VERSIONING POLICY:
  □ New fields → add to existing version (non-breaking)
  □ New endpoints → add to existing version (non-breaking)
  □ Remove/rename fields → new version (breaking)
  □ Change response structure → new version (breaking)
  □ Support previous version for 12+ months
  □ Deprecation notices in response headers
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
