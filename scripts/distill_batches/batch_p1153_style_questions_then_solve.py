"""
Response variety training pairs - Clarify then solve
Opens by identifying key factors/questions, then provides a default solution with stated assumptions.
"""

pairs = [
    {
        "instruction": r'''Build me an authentication system for my web app.''',
        "output": r'''Before diving in, a couple things to consider:

1. What's your stack? (I'll assume Python/FastAPI)
2. Do you need OAuth/social login, or just email+password?
3. SPA (token-based) or server-rendered (session-based)?

Assuming FastAPI + email/password + JWT for a SPA frontend:

```python
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr

app = FastAPI()
SECRET_KEY = "your-secret-from-env"
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# In production, use a real database
fake_db = {}

def create_access_token(data: dict, expires: timedelta = timedelta(minutes=30)):
    payload = {**data, "exp": datetime.utcnow() + expires}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email or email not in fake_db:
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return fake_db[email]

@app.post("/register")
async def register(email: str, password: str):
    if email in fake_db:
        raise HTTPException(400, "Email already registered")
    fake_db[email] = {"email": email, "hashed_pw": pwd_context.hash(password)}
    return {"message": "User created"}

@app.post("/token")
async def login(form: OAuth2PasswordRequestForm = Depends()):
    user = fake_db.get(form.username)
    if not user or not pwd_context.verify(form.password, user["hashed_pw"]):
        raise HTTPException(401, "Incorrect credentials")
    return {"access_token": create_access_token({"sub": form.username})}

@app.get("/me")
async def whoami(user: dict = Depends(get_current_user)):
    return {"email": user["email"]}
```

Install with: `pip install fastapi passlib[bcrypt] python-jose[cryptography]`

If you need refresh tokens later, add a second longer-lived token in an httpOnly cookie. For OAuth, look into `authlib`.'''
    },
    {
        "instruction": r'''Set up logging for my application.''',
        "output": r'''This depends on a few factors:

1. What language? (I'll assume Python)
2. Where do logs go -- stdout, files, or a log aggregation service?
3. Single process or distributed?

Assuming Python, structured JSON to stdout (good for containers):

```python
import logging
import json
import sys
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_data"):
            entry.update(record.extra_data)
        return json.dumps(entry)

def setup_logging(level="INFO"):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.setLevel(getattr(logging, level))
    root.handlers = [handler]
    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)

setup_logging()
logger = logging.getLogger(__name__)

# Usage
logger.info("Server starting on port 8000")
logger.warning("Cache miss rate high", extra={
    "extra_data": {"miss_rate": 0.45, "threshold": 0.3}
})
```

For file logging, add a `RotatingFileHandler`. For Docker/Kubernetes, stdout is the right choice -- the orchestrator captures it and you ship to Datadog or CloudWatch from there.'''
    },
    {
        "instruction": r'''Help me set up a database schema for my app.''',
        "output": r'''Before diving in, a couple things to consider:

1. What kind of app? (I'll assume SaaS with users and teams)
2. What database? (PostgreSQL)
3. Multi-tenancy? (Simple team-based scoping)

Here's a practical schema:

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    plan VARCHAR(20) DEFAULT 'free',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE team_members (
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) DEFAULT 'member'
        CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
    PRIMARY KEY (team_id, user_id)
);

CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    name VARCHAR(200) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_team_members_user ON team_members(user_id);
CREATE INDEX idx_projects_team ON projects(team_id);
CREATE INDEX idx_projects_active ON projects(team_id, status)
    WHERE status = 'active';
```

Key decisions: UUIDs over serial IDs (safe to expose in URLs), `TIMESTAMPTZ` not `TIMESTAMP` (always store timezone info), composite primary key on `team_members` (prevents duplicate memberships), partial index on active projects (smaller and faster for the most common query pattern).

Adapt the `projects` table to whatever your core entity is.'''
    },
    {
        "instruction": r'''I need to add file uploads to my web app.''',
        "output": r'''This depends on a few factors:

1. How large are the files? (Under 10MB can go through your server; larger should go direct-to-storage)
2. What file types? (Images may need thumbnails; docs might need virus scanning)
3. Where to store them? (S3, GCS, local disk?)

Assuming mixed files up to 50MB, stored in S3, Python/FastAPI backend:

```python
import boto3
import uuid
from fastapi import FastAPI, UploadFile, HTTPException

app = FastAPI()
s3 = boto3.client('s3')
BUCKET = 'my-app-uploads'
ALLOWED = {'image/jpeg', 'image/png', 'application/pdf', 'text/csv'}

# Simple upload (good for < 10MB)
@app.post("/upload")
async def upload_file(file: UploadFile):
    if file.content_type not in ALLOWED:
        raise HTTPException(400, "File type not allowed")
    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(400, "File too large")

    file_id = str(uuid.uuid4())
    ext = file.filename.rsplit('.', 1)[-1] if '.' in file.filename else 'bin'
    key = f"uploads/{file_id}.{ext}"
    s3.put_object(Bucket=BUCKET, Key=key, Body=contents,
                  ContentType=file.content_type)
    return {"file_id": file_id, "url": f"https://{BUCKET}.s3.amazonaws.com/{key}"}

# Presigned URL (better for large files -- client uploads directly to S3)
@app.post("/upload/presign")
async def presign(filename: str, content_type: str):
    if content_type not in ALLOWED:
        raise HTTPException(400, "File type not allowed")
    file_id = str(uuid.uuid4())
    ext = filename.rsplit('.', 1)[-1] if '.' in filename else 'bin'
    key = f"uploads/{file_id}.{ext}"
    url = s3.generate_presigned_url('put_object', Params={
        'Bucket': BUCKET, 'Key': key, 'ContentType': content_type,
    }, ExpiresIn=300)
    return {"upload_url": url, "file_id": file_id}
```

Frontend for presigned uploads:

```javascript
async function uploadFile(file) {
    const { upload_url, file_id } = await fetch('/upload/presign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file.name, content_type: file.type }),
    }).then(r => r.json());

    await fetch(upload_url, { method: 'PUT', body: file,
        headers: { 'Content-Type': file.type } });
    return file_id;
}
```

Use the simple upload for small files; presigned URLs for large ones to keep your server out of the data path.'''
    },
    {
        "instruction": r'''Add caching to my API to improve performance.''',
        "output": r'''Before diving in, a couple things to consider:

1. What are you caching -- query results, computed responses, or full HTTP responses?
2. How stale can data be? (Seconds, minutes, hours?)
3. Single server or multiple? (In-memory works for one; Redis needed for shared)

Assuming FastAPI, caching JSON responses, 1-5 min staleness OK, single server:

```python
import hashlib
import time
from functools import wraps

class MemoryCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        entry = self.store.get(key)
        if entry and time.monotonic() <= entry["expires"]:
            return entry["value"]
        if entry:
            del self.store[key]
        return None

    def set(self, key, value, ttl=60):
        self.store[key] = {"value": value, "expires": time.monotonic() + ttl}

    def invalidate(self, prefix):
        for k in [k for k in self.store if k.startswith(prefix)]:
            del self.store[k]

cache = MemoryCache()

def cached_route(ttl=60, prefix=""):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            raw_key = f"{prefix}:{func.__name__}:{args}:{kwargs}"
            key = hashlib.md5(raw_key.encode()).hexdigest()
            hit = cache.get(key)
            if hit is not None:
                return hit
            result = await func(*args, **kwargs)
            cache.set(key, result, ttl)
            return result
        return wrapper
    return decorator

# Usage
from fastapi import FastAPI
app = FastAPI()

@app.get("/products")
@cached_route(ttl=300, prefix="products")
async def list_products(category: str = None):
    return await db.fetch_all("SELECT * FROM products WHERE category=$1", category)

@app.put("/products/{pid}")
async def update_product(pid: int, data: dict):
    await db.execute("UPDATE products SET name=$1 WHERE id=$2", data["name"], pid)
    cache.invalidate("products:")
    return {"status": "updated"}
```

Cache reads, invalidate on writes. TTL is your safety net -- even if you miss an invalidation, data self-corrects. When you outgrow in-memory (multiple servers), swap `MemoryCache` for Redis with the same interface.'''
    },
]
