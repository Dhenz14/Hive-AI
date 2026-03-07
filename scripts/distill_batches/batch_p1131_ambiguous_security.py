"""
Ambiguous request handling pairs - vague security requests
"""

pairs = [
    {
        "instruction": r'''Add security to my app.''',
        "output": r'''<think>
"Add security" is one of the vaguest requests possible. Security could mean authentication, authorization, input validation, HTTPS, CSRF protection, rate limiting, encryption at rest, SQL injection prevention, XSS prevention, secrets management... I don't even know what kind of app this is. Web app? Mobile API? Desktop? What framework? What's the threat model?
</think>

Security is a broad topic, so let me ask a few things first:

1. **What kind of app?** Web app, REST API, mobile backend? What framework (Express, Django, FastAPI, etc.)?
2. **What security do you have now?** Any authentication? HTTPS? Input validation?
3. **What's driving this?** A specific vulnerability, a compliance requirement, or just general hardening?

Here's a practical security baseline assuming a typical web API. These cover the most common attack vectors:

```python
# Assuming FastAPI -- adapt to your framework

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
import secrets

app = FastAPI()

# 1. HTTPS redirect -- never serve over plain HTTP
app.add_middleware(HTTPSRedirectMiddleware)

# 2. CORS -- restrict which origins can call your API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourapp.com"],  # NOT "*" in production
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# 3. Security headers
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response

# 4. Input validation with Pydantic (prevents injection)
from pydantic import BaseModel, EmailStr, constr

class CreateUser(BaseModel):
    email: EmailStr
    username: constr(min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9_]+$')
    password: constr(min_length=8)

# 5. Password hashing -- never store plaintext
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

The priority order for most apps: authentication -> input validation -> HTTPS -> CORS -> security headers -> rate limiting. Tell me your stack and current state, and I'll tailor the recommendations.'''
    },
    {
        "instruction": r'''Is this secure enough? [shows a login endpoint]

@app.post("/login")
def login(username: str, password: str):
    user = db.query(f"SELECT * FROM users WHERE username='{username}'")
    if user and user.password == password:
        token = str(user.id)
        return {"token": token}
    return {"error": "invalid credentials"}''',
        "output": r'''<think>
This code has multiple critical security vulnerabilities that I can identify immediately: SQL injection via string formatting, plaintext password comparison (no hashing), predictable token (just the user ID), no rate limiting. I should point these out clearly. But I should also ask about context -- what framework, what's the token used for, is there middleware I'm not seeing?
</think>

To give complete advice, I'd want to know: What framework is this (FastAPI, Flask)? Is there any middleware or auth layer not shown here?

That said, I can already see several critical vulnerabilities in this code. Let me walk through them:

**Issues found (in severity order):**
1. **SQL Injection** -- the f-string query lets attackers log in as anyone or dump your database
2. **Plaintext passwords** -- comparing raw passwords means you're storing them unhashed
3. **Predictable tokens** -- using `str(user.id)` means anyone can forge tokens by guessing IDs
4. **No rate limiting** -- vulnerable to brute-force attacks

Here's a secure version:

```python
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from pydantic import BaseModel
from fastapi import HTTPException
from sqlalchemy import select

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = "your-secret-key-from-env-variable"  # use os.environ in production
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 30

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/login")
def login(credentials: LoginRequest):
    # Fix 1: Parameterized query -- prevents SQL injection
    stmt = select(User).where(User.username == credentials.username)
    user = db.execute(stmt).scalar_one_or_none()

    # Fix 2: Hash comparison -- never compare plaintext
    if not user or not pwd_context.verify(credentials.password, user.hashed_password):
        # Same error for both cases -- don't reveal which failed
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Fix 3: Signed JWT token -- can't be forged without the secret
    token_data = {
        "sub": str(user.id),
        "exp": datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES),
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

    return {"access_token": token, "token_type": "bearer"}
```

You'll also need to hash passwords at registration time: `hashed = pwd_context.hash(plain_password)`. And add rate limiting (e.g., 5 attempts per minute per IP) to prevent brute-force attacks.'''
    },
    {
        "instruction": r'''We need to pass a security audit. What do we need to do?''',
        "output": r'''<think>
"Pass a security audit" -- which audit? SOC 2? PCI DSS? HIPAA? ISO 27001? A penetration test? A client's vendor security questionnaire? Each has wildly different requirements. Without knowing the audit type, the tech stack, and current security posture, I can only give generic guidance. I should ask about the specific audit framework.
</think>

The answer depends heavily on a few things:

1. **What type of audit?** SOC 2 Type II, PCI DSS, HIPAA, ISO 27001, or a client's custom security questionnaire?
2. **What's the timeline?** Weeks or months? Some frameworks (SOC 2 Type II) require months of evidence collection.
3. **What do you have in place today?** Any existing security controls, access management, logging?

Here's a practical checklist covering what most audits look for, regardless of framework:

```text
== INFRASTRUCTURE ==
[ ] All traffic over HTTPS/TLS 1.2+
[ ] Firewall rules -- only necessary ports exposed
[ ] Secrets in environment variables or a vault (not in code)
[ ] Regular patching schedule for OS and dependencies
[ ] Backups tested and encrypted

== APPLICATION ==
[ ] Authentication with MFA option
[ ] Role-based access control (RBAC)
[ ] Input validation on all user inputs
[ ] Parameterized queries (no SQL injection)
[ ] Rate limiting on auth endpoints
[ ] Session timeout and token expiration

== LOGGING & MONITORING ==
[ ] Centralized logging (who did what, when)
[ ] Failed login attempt alerts
[ ] Error tracking (Sentry or similar)
[ ] Uptime monitoring

== ACCESS CONTROL ==
[ ] Principle of least privilege for all accounts
[ ] No shared credentials
[ ] SSH key-based auth (no password SSH)
[ ] Production access restricted and logged

== PROCESSES ==
[ ] Code review required before merge
[ ] Dependency vulnerability scanning (Dependabot, Snyk)
[ ] Incident response plan documented
[ ] Data retention and deletion policy
```

```python
# Quick win: add audit logging to your app
import logging
from datetime import datetime

audit_logger = logging.getLogger("audit")
handler = logging.FileHandler("audit.log")
handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
audit_logger.addHandler(handler)
audit_logger.setLevel(logging.INFO)

def log_action(user_id: str, action: str, resource: str, detail: str = ""):
    audit_logger.info(f"user={user_id} action={action} resource={resource} detail={detail}")

# Usage: log_action("user_42", "DELETE", "invoice/123", "deleted by admin request")
```

Tell me which audit framework you're targeting, and I'll prioritize the checklist for you.'''
    },
    {
        "instruction": r'''Protect the API from attacks.''',
        "output": r'''<think>
"Protect from attacks" -- which attacks? DDoS, SQL injection, XSS, brute force, credential stuffing, CSRF, man-in-the-middle, API abuse? Each requires different mitigations. I don't know the framework, whether this is public-facing, what data it handles, or what protections exist already. I'll ask but also provide the highest-impact defenses.
</think>

A couple questions to prioritize the right protections:

1. **What framework/language?** (Express, Django, FastAPI, Spring, etc.)
2. **Is this a public API or internal?** Public APIs face very different threats than internal microservices.
3. **Any existing protections?** Authentication, WAF, rate limiting?

Here's a defense-in-depth approach covering the most common API attacks. Assuming a Python/FastAPI app, but the concepts apply everywhere:

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
import re

app = FastAPI()
limiter = Limiter(key_func=get_remote_address)

# 1. Rate limiting -- stops brute force and credential stuffing
@app.post("/api/login")
@limiter.limit("5/minute")
async def login(request: Request):
    pass  # your login logic

@app.get("/api/data")
@limiter.limit("60/minute")
async def get_data(request: Request):
    pass  # your endpoint logic

# 2. CORS -- prevent unauthorized origins from calling your API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# 3. Input sanitization middleware
@app.middleware("http")
async def validate_content_type(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type:
            raise HTTPException(status_code=415, detail="Unsupported media type")
    response = await call_next(request)
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response

# 4. Request size limits -- prevent payload-based DoS
from fastapi import Body

@app.post("/api/upload")
async def upload(data: bytes = Body(..., max_length=10_000_000)):  # 10MB max
    pass
```

```text
Protection priority for public APIs:
1. Rate limiting (stops brute force, scraping, DoS)
2. Input validation (stops injection attacks)
3. Authentication + authorization (stops unauthorized access)
4. HTTPS everywhere (stops MITM)
5. CORS restrictions (stops cross-origin abuse)
6. Request size limits (stops payload DoS)
7. Logging + alerting (detect attacks in progress)
```

Tell me your stack and whether the API is public, and I'll customize further.'''
    },
    {
        "instruction": r'''We need to handle authentication. Set it up.''',
        "output": r'''<think>
"Handle authentication" -- there are so many approaches. Session-based? JWT? OAuth2? SSO with an identity provider? API keys for service-to-service? Do they need registration, password reset, email verification? Do they want to use a third-party service like Auth0/Firebase Auth, or build it themselves? I need to know the stack and requirements before writing code.
</think>

Authentication is a big decision with several approaches. Before I set anything up:

1. **What's your stack?** (Framework, database, frontend type)
2. **Who are the users?** End users with email/password? Third-party developers with API keys? Internal employees with SSO?
3. **Build or buy?** Are you open to services like Auth0/Clerk/Firebase Auth, or do you want to own the auth layer?

Here's a solid JWT-based auth setup assuming you want to build it yourself with FastAPI and PostgreSQL -- the most common choice for APIs:

```python
# auth.py -- core authentication module
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import os

SECRET_KEY = os.environ["JWT_SECRET_KEY"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await get_user_by_id(int(user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# routes.py -- login and registration endpoints
@app.post("/auth/register")
async def register(email: str, password: str):
    existing = await get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(password)
    user = await create_user(email=email, hashed_password=hashed)
    return {"id": user.id, "email": user.email}

@app.post("/auth/login")
async def login(email: str, password: str):
    user = await get_user_by_email(email)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer"}

# Protected route example
@app.get("/api/profile")
async def get_profile(current_user = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email}
```

This gives you registration, login, and token-based route protection. You'll still need to decide on: password reset flow, email verification, refresh tokens, and whether to add OAuth providers (Google, GitHub login). Let me know your priorities.'''
    },
]
