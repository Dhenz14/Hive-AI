"""Phase 2A: Advanced Reasoning — Backtracking & Dead-End Recovery (Part 12)"""

PAIRS = [
    (
        "thinking/backtrack-string-validation-to-parser",
        "I'm validating user input with a massive chain of if/else statements and regex patterns. It's 300 lines long and keeps growing. Every new validation rule adds more complexity. How do I clean this up?",
        r'''<think>
Massive validation chain — let me think about approaches.

**First approach: refactor the if/else into separate validator functions**
```python
def validate_email(value): ...
def validate_phone(value): ...
def validate_age(value): ...

validators = [validate_email, validate_phone, validate_age]
errors = [v(data) for v in validators if not v(data)]
```

This is better — modular, each validator is testable. But...

Wait, this is still ad-hoc. Every field needs a custom function. For 50 fields, that's 50 functions. And they're all doing similar things: check type, check length, check pattern, check range.

**Let me backtrack. What if I use a schema-based approach?**

Instead of writing code for each validation rule, DECLARE the rules as data:

```python
schema = {
    "email": {"type": "string", "format": "email", "required": True},
    "age": {"type": "integer", "min": 13, "max": 120},
    "phone": {"type": "string", "pattern": r"^\+?[\d\s-]+$"},
}
```

Now the validation engine interprets the schema. Adding a rule = adding data, not code.

This is the right approach. Libraries like Pydantic, marshmallow, cerberus, JSON Schema already do this. Don't write validation engines from scratch.

The key insight: the 300-line if/else chain is trying to be a validation engine written imperatively. Replace it with a declarative schema and a library that already handles the engine.
</think>

My first thought was to split the if/else into functions. But then I backtracked to a better approach: **declarative schema validation**.

## Why Separate Functions Aren't Enough

```python
# First attempt: extract validators (better, but still ad-hoc)
def validate_email(data):
    if not data.get("email"):
        return "Email is required"
    if not re.match(r'^[\w.-]+@[\w.-]+\.\w+$', data["email"]):
        return "Invalid email format"
    if len(data["email"]) > 255:
        return "Email too long"

def validate_age(data):
    if "age" in data:
        if not isinstance(data["age"], int):
            return "Age must be a number"
        if data["age"] < 13:
            return "Must be at least 13"
        if data["age"] > 120:
            return "Invalid age"

# 50 fields = 50 functions = still 300+ lines
# Each function repeats the same patterns: check type, check length, check range
# Adding a new field = writing a new function = more code
```

## The Right Approach: Declarative Schema

```python
# Instead of writing HOW to validate, declare WHAT is valid
from pydantic import BaseModel, Field, EmailStr
from typing import Optional

class UserRegistration(BaseModel):
    email: EmailStr                                    # Valid email format
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    age: int = Field(ge=13, le=120)                    # 13 ≤ age ≤ 120
    phone: Optional[str] = Field(None, pattern=r'^\+?[\d\s-]{7,15}$')
    bio: Optional[str] = Field(None, max_length=500)
    website: Optional[str] = None

# Usage — Pydantic validates automatically:
try:
    user = UserRegistration(**request_data)
except ValidationError as e:
    return {"errors": e.errors()}, 422

# Adding a new field: ONE LINE instead of a new function
# username: str = Field(min_length=3, max_length=30, pattern=r'^[a-zA-Z0-9_]+$')
```

## Before vs After

```python
# ❌ BEFORE: 300 lines of imperative validation
def validate_registration(data):
    errors = []
    if not data.get("email"):
        errors.append("Email is required")
    elif not re.match(r'^[\w.-]+@[\w.-]+\.\w+$', data["email"]):
        errors.append("Invalid email format")
    elif len(data["email"]) > 255:
        errors.append("Email too long")

    if not data.get("password"):
        errors.append("Password is required")
    elif len(data["password"]) < 8:
        errors.append("Password must be at least 8 characters")
    elif len(data["password"]) > 128:
        errors.append("Password too long")

    if not data.get("name"):
        errors.append("Name is required")
    elif len(data["name"]) > 100:
        errors.append("Name too long")

    if "age" in data:
        try:
            age = int(data["age"])
            if age < 13:
                errors.append("Must be at least 13")
            elif age > 120:
                errors.append("Invalid age")
        except (ValueError, TypeError):
            errors.append("Age must be a number")
    # ... 250 more lines for remaining fields ...
    return errors


# ✅ AFTER: 15 lines of declarative schema
class UserRegistration(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    age: int = Field(ge=13, le=120)
    phone: Optional[str] = Field(None, pattern=r'^\+?[\d\s-]{7,15}$')
    bio: Optional[str] = Field(None, max_length=500)

# Same validation, 95% less code.
# Adding a field: 1 line. Testing: automatic. Documentation: auto-generated.
```

## Custom Validators When Needed

```python
from pydantic import BaseModel, field_validator

class UserRegistration(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    username: str = Field(min_length=3, max_length=30)

    @field_validator('password')
    @classmethod
    def password_strength(cls, v):
        if not re.search(r'[A-Z]', v):
            raise ValueError('Must contain uppercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Must contain a digit')
        return v

    @field_validator('username')
    @classmethod
    def username_available(cls, v):
        if v.lower() in RESERVED_USERNAMES:
            raise ValueError('Username is reserved')
        return v
```

The key insight: your 300-line if/else chain was an ad-hoc validation engine written imperatively. Replace it with a declarative schema and let a library handle the engine.'''
    ),
    (
        "thinking/backtrack-manual-deploy-script-to-ci-cd",
        "Our deployment is a 45-line bash script that SSHs into the server, pulls the latest code, runs migrations, and restarts the service. It works but only I know how to run it. How do I make this more reliable?",
        r'''<think>
Manual deploy script → more reliable deployment. Let me think about the progression.

**Current state:** A bash script that one person runs manually.
Problems:
- Bus factor of 1 (only one person can deploy)
- No audit trail (who deployed what, when?)
- No rollback mechanism
- SSH credentials on one laptop
- Script might fail partway (migration succeeded, restart failed — now what?)
- No testing before deploy

**First approach: document the script and teach the team**
This is the most obvious — just share the knowledge.
But it doesn't fix: partial failures, no rollback, no audit trail.

**Second approach: wrap in a CI/CD pipeline**
The deploy script can be the FIRST step in CI/CD. Don't rewrite it — wrap it.

Git push → CI runs tests → CI runs the deploy script → notification

This gives:
- Anyone can deploy (push to main or click a button)
- Tests run before deploy (catches bugs)
- Audit trail (git log + CI logs)
- Still uses the working script

But doesn't fix: partial failures, rollback.

**Third approach: containerized deployment**
Build a Docker image in CI, push to registry, deploy the image (not the code).
This eliminates: SSH, git pull on server, dependency issues.
Adds: reliable rollback (just deploy the previous image).

This is the right direction but might be too much change at once.

**Practical path:**
1. First: put the script in CI/CD (quick win, big improvement)
2. Next: add health checks and rollback
3. Later: containerize for full reliability
</think>

Let me trace the progression from your current script to reliable deployment. Each step is independently valuable — you don't need to jump to the end.

## Step 1: Put Your Script in CI/CD (Quick Win)

```yaml
# .github/workflows/deploy.yml
# Takes your EXISTING script and runs it from CI instead of your laptop

name: Deploy
on:
  push:
    branches: [main]
  # Or manual trigger:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: pytest  # Tests BEFORE deploying

  deploy:
    needs: test  # Only deploy if tests pass
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to production
        env:
          SSH_KEY: ${{ secrets.DEPLOY_SSH_KEY }}
        run: |
          mkdir -p ~/.ssh
          echo "$SSH_KEY" > ~/.ssh/deploy_key
          chmod 600 ~/.ssh/deploy_key
          # Your existing script, but SSH key is from GitHub Secrets
          ssh -i ~/.ssh/deploy_key user@server << 'DEPLOY'
            cd /app
            git pull origin main
            pip install -r requirements.txt
            python manage.py migrate
            sudo systemctl restart myapp
          DEPLOY
```

```
What this gives you IMMEDIATELY:
  ✓ Anyone can deploy (push to main or click "Run workflow")
  ✓ Tests run before deploy (catches bugs before production)
  ✓ Audit trail (GitHub Actions logs: who deployed, when, what)
  ✓ SSH key in GitHub Secrets (not on your laptop)
  ✓ No SSH access needed for team members to deploy

What's still missing:
  ✗ Partial failure handling (migration passes, restart fails)
  ✗ Rollback mechanism
  ✗ Health check after deploy
```

## Step 2: Add Health Checks and Rollback

```yaml
      - name: Deploy with health check
        run: |
          ssh -i ~/.ssh/deploy_key user@server << 'DEPLOY'
            cd /app

            # Save current version for rollback
            CURRENT_COMMIT=$(git rev-parse HEAD)

            # Pull new code
            git pull origin main || { echo "Git pull failed"; exit 1; }

            # Install dependencies
            pip install -r requirements.txt || {
              echo "Pip install failed, rolling back"
              git checkout $CURRENT_COMMIT
              exit 1
            }

            # Run migrations
            python manage.py migrate || {
              echo "Migration failed, rolling back"
              git checkout $CURRENT_COMMIT
              pip install -r requirements.txt
              exit 1
            }

            # Restart with health check
            sudo systemctl restart myapp
            sleep 5

            # Health check — verify the app is responding
            for i in 1 2 3 4 5; do
              if curl -sf http://localhost:8080/health > /dev/null; then
                echo "Health check passed!"
                exit 0
              fi
              sleep 2
            done

            # Health check failed — rollback!
            echo "Health check FAILED, rolling back"
            git checkout $CURRENT_COMMIT
            pip install -r requirements.txt
            python manage.py migrate  # Reverse migration if possible
            sudo systemctl restart myapp
            exit 1
          DEPLOY

      - name: Notify on failure
        if: failure()
        run: |
          curl -X POST "${{ secrets.SLACK_WEBHOOK }}" \
            -H 'Content-Type: application/json' \
            -d '{"text": "⚠️ Deploy FAILED. Check GitHub Actions."}'
```

## Step 3: Containerize (When Ready)

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["gunicorn", "myapp.wsgi:app", "--bind", "0.0.0.0:8080"]
```

```yaml
# CI builds and pushes Docker image
  deploy:
    steps:
      - name: Build and push Docker image
        run: |
          docker build -t myapp:${{ github.sha }} .
          docker tag myapp:${{ github.sha }} registry.example.com/myapp:latest
          docker push registry.example.com/myapp:${{ github.sha }}

      - name: Deploy new image
        run: |
          ssh user@server << DEPLOY
            docker pull registry.example.com/myapp:${{ github.sha }}
            docker stop myapp-old || true
            docker rename myapp myapp-old || true
            docker run -d --name myapp -p 8080:8080 \
              --env-file /etc/myapp/env \
              registry.example.com/myapp:${{ github.sha }}

            # Health check
            sleep 5
            if curl -sf http://localhost:8080/health; then
              docker rm myapp-old || true
              echo "Deploy successful!"
            else
              # INSTANT ROLLBACK: just start the old container
              docker stop myapp
              docker rename myapp-old myapp
              docker start myapp
              echo "Deploy FAILED, rolled back"
              exit 1
            fi
          DEPLOY
```

```
ROLLBACK WITH CONTAINERS:
  docker stop myapp
  docker run registry.example.com/myapp:PREVIOUS_SHA
  Done. 5 seconds. No git pull, no pip install, no migrations.

This is why containers are the end goal:
  Code + dependencies + runtime = one immutable artifact.
  Deploy = swap the artifact. Rollback = swap back.
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
