"""Contract testing with Pact — consumer-driven contracts, provider verification, broker integration, and comparison with integration testing."""

PAIRS = [
    (
        "testing/consumer-driven-contracts",
        "Show how to write consumer-driven contract tests using Pact in Python, including defining interactions and generating pacts.",
        '''Consumer-driven contract testing with Pact in Python:

```python
# --- test_order_consumer.py --- Consumer side: order service calls user service ---

from __future__ import annotations

import pytest
import requests
from typing import Any
from dataclasses import dataclass

import atexit
from pact import Consumer, Provider, Like, EachLike, Term, Format


# --- Data models ---

@dataclass
class User:
    id: int
    name: str
    email: str
    tier: str  # "free", "pro", "enterprise"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> User:
        return cls(
            id=data["id"],
            name=data["name"],
            email=data["email"],
            tier=data["tier"],
        )


# --- API Client (the code under test) ---

class UserServiceClient:
    """Client for the User Service API — this is the consumer."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def get_user(self, user_id: int) -> User:
        """Fetch a user by ID."""
        resp = requests.get(f"{self.base_url}/api/users/{user_id}", timeout=10)
        resp.raise_for_status()
        return User.from_dict(resp.json())

    def list_users(self, tier: str | None = None) -> list[User]:
        """List users, optionally filtered by tier."""
        params = {}
        if tier:
            params["tier"] = tier
        resp = requests.get(
            f"{self.base_url}/api/users",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        return [User.from_dict(u) for u in resp.json()["users"]]

    def create_user(self, name: str, email: str, tier: str = "free") -> User:
        """Create a new user."""
        resp = requests.post(
            f"{self.base_url}/api/users",
            json={"name": name, "email": email, "tier": tier},
            timeout=10,
        )
        resp.raise_for_status()
        return User.from_dict(resp.json())


# --- Pact setup ---

PACT_MOCK_HOST = "localhost"
PACT_MOCK_PORT = 1234

pact = Consumer("OrderService").has_pact_with(
    Provider("UserService"),
    host_name=PACT_MOCK_HOST,
    port=PACT_MOCK_PORT,
    pact_dir="./pacts",           # where pact JSON files are written
    log_dir="./pact_logs",
)

pact.start_service()
atexit.register(pact.stop_service)


# --- Tests ---

class TestUserServiceConsumer:
    """Consumer contract tests — define what OrderService expects from UserService."""

    def test_get_user_by_id(self):
        """Verify: GET /api/users/{id} returns a user object."""
        expected_user = {
            "id": 42,
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "tier": "pro",
        }

        (
            pact
            .given("user 42 exists")                    # Provider state
            .upon_receiving("a request for user 42")    # Interaction name
            .with_request("GET", "/api/users/42")
            .will_respond_with(
                200,
                headers={"Content-Type": "application/json"},
                body=Like(expected_user),  # Like = match structure, not exact values
            )
        )

        with pact:
            client = UserServiceClient(f"http://{PACT_MOCK_HOST}:{PACT_MOCK_PORT}")
            user = client.get_user(42)

            assert user.id == 42
            assert user.name == "Alice Johnson"
            assert user.tier == "pro"

    def test_get_nonexistent_user(self):
        """Verify: GET /api/users/{id} returns 404 for missing user."""
        (
            pact
            .given("user 999 does not exist")
            .upon_receiving("a request for nonexistent user 999")
            .with_request("GET", "/api/users/999")
            .will_respond_with(
                404,
                headers={"Content-Type": "application/json"},
                body={"error": Like("User not found")},
            )
        )

        with pact:
            client = UserServiceClient(f"http://{PACT_MOCK_HOST}:{PACT_MOCK_PORT}")
            with pytest.raises(requests.HTTPError) as exc_info:
                client.get_user(999)
            assert exc_info.value.response.status_code == 404

    def test_list_users_by_tier(self):
        """Verify: GET /api/users?tier=pro returns a filtered list."""
        (
            pact
            .given("users with tier pro exist")
            .upon_receiving("a request to list pro users")
            .with_request(
                "GET",
                "/api/users",
                query={"tier": ["pro"]},
            )
            .will_respond_with(
                200,
                headers={"Content-Type": "application/json"},
                body={
                    "users": EachLike({   # EachLike = array with 1+ items matching shape
                        "id": Like(1),
                        "name": Like("Alice"),
                        "email": Term(
                            r".+@.+\\..+",     # regex for email format
                            "alice@example.com"  # example value
                        ),
                        "tier": "pro",          # exact match — must always be "pro"
                    }),
                },
            )
        )

        with pact:
            client = UserServiceClient(f"http://{PACT_MOCK_HOST}:{PACT_MOCK_PORT}")
            users = client.list_users(tier="pro")

            assert len(users) >= 1
            assert all(u.tier == "pro" for u in users)

    def test_create_user(self):
        """Verify: POST /api/users creates and returns a user."""
        (
            pact
            .given("the user service is available")
            .upon_receiving("a request to create a user")
            .with_request(
                "POST",
                "/api/users",
                headers={"Content-Type": "application/json"},
                body={
                    "name": "Bob Smith",
                    "email": "bob@example.com",
                    "tier": "free",
                },
            )
            .will_respond_with(
                201,
                headers={"Content-Type": "application/json"},
                body={
                    "id": Like(1),             # any integer
                    "name": "Bob Smith",        # exact match
                    "email": "bob@example.com",
                    "tier": "free",
                },
            )
        )

        with pact:
            client = UserServiceClient(f"http://{PACT_MOCK_HOST}:{PACT_MOCK_PORT}")
            user = client.create_user("Bob Smith", "bob@example.com")

            assert user.name == "Bob Smith"
            assert user.tier == "free"
```

```python
# --- Pact matchers reference ---

from pact import Like, EachLike, Term, Format

# Like(value) — match by type, not exact value
Like(42)                    # any integer
Like("hello")               # any string
Like({"key": "val"})        # object with same structure

# EachLike(value, minimum=1) — array with items matching shape
EachLike({"id": Like(1), "name": Like("n")})         # array of objects
EachLike(Like(1), minimum=3)                          # array of 3+ integers

# Term(regex, generate) — match by regex, use generate for examples
Term(r"^\\d{4}-\\d{2}-\\d{2}$", "2024-01-15")        # date format
Term(r"^[A-Z]{3}$", "USD")                            # currency code

# Format helpers
Format().iso_8601_datetime()   # ISO 8601 datetime
Format().uuid()                # UUID v4
Format().ip_address()          # IPv4 address
Format().ipv6_address()        # IPv6 address
Format().hex()                 # hexadecimal string

# Nested matchers — combine for complex structures
body = {
    "order": Like({
        "id": Format().uuid(),
        "created_at": Format().iso_8601_datetime(),
        "total": Like(99.99),
        "currency": Term(r"^[A-Z]{3}$", "USD"),
        "items": EachLike({
            "sku": Like("SKU-001"),
            "quantity": Like(1),
            "price": Like(9.99),
        }, minimum=1),
    }),
}
```

```json
// --- Generated pact file: pacts/orderservice-userservice.json ---
// This is auto-generated by the consumer tests — DO NOT edit manually
{
  "consumer": { "name": "OrderService" },
  "provider": { "name": "UserService" },
  "interactions": [
    {
      "description": "a request for user 42",
      "providerState": "user 42 exists",
      "request": {
        "method": "GET",
        "path": "/api/users/42"
      },
      "response": {
        "status": 200,
        "headers": { "Content-Type": "application/json" },
        "body": {
          "id": 42,
          "name": "Alice Johnson",
          "email": "alice@example.com",
          "tier": "pro"
        },
        "matchingRules": {
          "body": {
            "$": { "matchers": [{ "match": "type" }] }
          }
        }
      }
    }
  ],
  "metadata": {
    "pactSpecification": { "version": "2.0.0" }
  }
}
```

| Matcher | Syntax | Matches |
|---------|--------|---------|
| `Like` | `Like(42)` | Same type (int), any value |
| `EachLike` | `EachLike({...})` | Array with 1+ items of same shape |
| `Term` | `Term(regex, example)` | String matching regex |
| `Format().uuid()` | Auto-regex | UUID v4 format |
| `Format().iso_8601_datetime()` | Auto-regex | ISO 8601 datetime |

Key patterns:
1. Consumer defines the contract — only specify fields and shapes the consumer actually uses
2. Use `Like()` for flexible type matching, exact values only for enums/constants
3. Use `Term()` with regex for format-sensitive fields (dates, emails, IDs)
4. Provider states (`given(...)`) let you set up test fixtures on the provider side
5. Generated pact files are the contract artifact — publish to Pact Broker for verification'''
    ),
    (
        "testing/provider-verification",
        "Show how to verify Pact contracts on the provider side, including provider state setup and running verification.",
        '''Pact provider verification — proving the provider honors consumer contracts:

```python
# --- test_user_provider.py --- Provider-side verification ---

from __future__ import annotations

import pytest
import subprocess
import os
from typing import Generator
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pact import Verifier


# --- The actual provider application ---

from user_service.app import create_app
from user_service.models import User, Base
from user_service.database import get_db


# --- Test database setup ---

TEST_DATABASE_URL = "sqlite:///test_pact.db"
engine = create_engine(TEST_DATABASE_URL)
TestSession = sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def setup_database():
    """Create fresh tables for each test."""
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


# --- Provider state handlers ---
# These set up the database state required by each consumer interaction

PROVIDER_STATE_HANDLERS = {}


def provider_state(state_name: str):
    """Decorator to register a provider state handler."""
    def decorator(func):
        PROVIDER_STATE_HANDLERS[state_name] = func
        return func
    return decorator


@provider_state("user 42 exists")
def state_user_42_exists(db: Session) -> None:
    """Insert user 42 into the test database."""
    user = User(id=42, name="Alice Johnson", email="alice@example.com", tier="pro")
    db.add(user)
    db.commit()


@provider_state("user 999 does not exist")
def state_user_999_missing(db: Session) -> None:
    """Ensure user 999 does not exist — no setup needed."""
    pass


@provider_state("users with tier pro exist")
def state_pro_users_exist(db: Session) -> None:
    """Insert multiple pro-tier users."""
    users = [
        User(id=1, name="Alice", email="alice@example.com", tier="pro"),
        User(id=2, name="Charlie", email="charlie@example.com", tier="pro"),
    ]
    db.add_all(users)
    db.commit()


@provider_state("the user service is available")
def state_service_available(db: Session) -> None:
    """No specific setup — service is running."""
    pass


# --- Provider state middleware ---

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def create_provider_state_app(main_app: FastAPI, db_session: Session) -> FastAPI:
    """Wrap the main app with a provider state setup endpoint.

    Pact Verifier calls POST /_pact/provider-states before each interaction.
    """
    @main_app.post("/_pact/provider-states")
    async def setup_provider_state(request: Request):
        body = await request.json()
        state = body.get("state") or body.get("consumer", {}).get("state", "")

        handler = PROVIDER_STATE_HANDLERS.get(state)
        if handler:
            handler(db_session)
            return JSONResponse({"status": "ok", "state": state})
        else:
            return JSONResponse(
                {"status": "error", "message": f"Unknown state: {state}"},
                status_code=400,
            )

    return main_app
```

```python
# --- verify_pacts.py --- Run verification against pact files ---

import os
import pytest
from pact import Verifier


def test_verify_pacts_from_broker():
    """Verify all consumer pacts registered in the Pact Broker."""
    verifier = Verifier(
        provider="UserService",
        provider_base_url="http://localhost:8000",
    )

    # Option 1: Verify from Pact Broker (recommended for CI)
    success, logs = verifier.verify_with_broker(
        broker_url=os.environ.get("PACT_BROKER_URL", "http://localhost:9292"),
        broker_username=os.environ.get("PACT_BROKER_USERNAME", ""),
        broker_password=os.environ.get("PACT_BROKER_PASSWORD", ""),
        publish_version=os.environ.get("GIT_COMMIT", "dev"),
        publish_verification_results=True,
        provider_states_setup_url="http://localhost:8000/_pact/provider-states",
        enable_pending=True,       # new contracts don't break the build
        include_wip_pacts_since="2024-01-01",  # include work-in-progress
        consumer_version_selectors=[
            {"mainBranch": True},               # verify main branch contracts
            {"deployedOrReleased": True},        # verify deployed contracts
        ],
    )

    assert success == 0, f"Pact verification failed:\\n{logs}"


def test_verify_pacts_from_file():
    """Verify from local pact files (for local development)."""
    verifier = Verifier(
        provider="UserService",
        provider_base_url="http://localhost:8000",
    )

    success, logs = verifier.verify_pacts(
        "./pacts/orderservice-userservice.json",
        provider_states_setup_url="http://localhost:8000/_pact/provider-states",
    )

    assert success == 0, f"Pact verification failed:\\n{logs}"


# --- conftest.py --- Start the provider app for verification ---

import pytest
import uvicorn
import threading
from user_service.app import create_app
from user_service.database import get_db


@pytest.fixture(scope="session", autouse=True)
def start_provider():
    """Start the provider app in a background thread for verification."""
    app = create_app()

    # Override DB dependency for test database
    def get_test_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = get_test_db

    # Add provider state endpoint
    create_provider_state_app(app, TestSession())

    server = uvicorn.Server(
        uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    import time
    time.sleep(2)  # wait for server to start

    yield

    server.should_exit = True
```

```bash
# --- CLI verification (alternative to Python) ---

# Verify from local pact file
pact-verifier \
  --provider-base-url http://localhost:8000 \
  --provider "UserService" \
  --pact-url ./pacts/orderservice-userservice.json \
  --provider-states-setup-url http://localhost:8000/_pact/provider-states

# Verify from Pact Broker
pact-verifier \
  --provider-base-url http://localhost:8000 \
  --provider "UserService" \
  --pact-broker-url http://pact-broker:9292 \
  --provider-app-version $(git rev-parse --short HEAD) \
  --publish-verification-results \
  --enable-pending \
  --consumer-version-selectors '{"mainBranch": true}' \
  --provider-states-setup-url http://localhost:8000/_pact/provider-states

# Docker-based verification
docker run --rm --network host \
  pactfoundation/pact-cli:latest \
  pact-provider-verifier \
  --provider-base-url http://localhost:8000 \
  --pact-broker-url http://pact-broker:9292 \
  --provider "UserService"
```

| Verification Option | Purpose | When to use |
|--------------------|---------|-------------|
| `verify_pacts(file)` | Verify from local JSON | Local dev, pre-commit |
| `verify_with_broker()` | Verify from Pact Broker | CI/CD pipelines |
| `enable_pending` | New contracts are warnings, not failures | Avoid blocking provider CI |
| `include_wip_pacts_since` | Include in-progress consumer contracts | Catch issues early |
| `consumer_version_selectors` | Filter which consumer versions to verify | Deploy safety (can-i-deploy) |
| `publish_verification_results` | Report results back to broker | Required for can-i-deploy |

Key patterns:
1. Provider state handlers set up database fixtures that match consumer interaction preconditions
2. Expose a `/_pact/provider-states` endpoint for the Verifier to call before each interaction
3. Use `enable_pending=True` so new consumer contracts do not immediately break the provider build
4. Publish verification results to the broker — this enables `can-i-deploy` safety checks
5. Verify against `deployedOrReleased` selectors to ensure compatibility with production consumers'''
    ),
    (
        "testing/pact-broker-ci",
        "Show how to integrate Pact with a CI/CD pipeline using the Pact Broker, can-i-deploy checks, and webhook triggers.",
        '''Pact Broker and CI/CD integration for contract testing workflows:

```python
# --- pact_broker.py --- Pact Broker API client ---

from __future__ import annotations

import os
import requests
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class PactBrokerClient:
    """Client for Pact Broker API operations."""
    base_url: str
    username: str = ""
    password: str = ""
    token: str = ""  # for Pactflow (hosted broker)

    @property
    def _auth(self) -> Optional[tuple[str, str]]:
        if self.username:
            return (self.username, self.password)
        return None

    @property
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def publish_pact(
        self,
        consumer: str,
        provider: str,
        version: str,
        pact_file: str,
        branch: str = "main",
        tags: list[str] | None = None,
    ) -> dict:
        """Publish a pact file to the broker."""
        with open(pact_file, "r") as f:
            pact_content = f.read()

        # Publish pact
        url = f"{self.base_url}/pacts/provider/{provider}/consumer/{consumer}/version/{version}"
        resp = requests.put(
            url,
            data=pact_content,
            headers={"Content-Type": "application/json"},
            auth=self._auth,
        )
        resp.raise_for_status()
        logger.info(f"Published pact: {consumer} -> {provider} v{version}")

        # Tag the version
        if tags:
            for tag in tags:
                self._tag_version(consumer, version, tag)

        # Record branch (Pact Broker 2.86+)
        if branch:
            self._record_branch(consumer, version, branch)

        return resp.json()

    def can_i_deploy(
        self,
        pacticipant: str,
        version: str,
        to_environment: str = "production",
    ) -> tuple[bool, str]:
        """Check if a version can be safely deployed.

        Returns (can_deploy, reason).
        """
        url = (
            f"{self.base_url}/can-i-deploy"
            f"?pacticipant={pacticipant}"
            f"&version={version}"
            f"&to=production"
        )
        resp = requests.get(url, headers=self._headers, auth=self._auth)
        data = resp.json()

        can_deploy = data.get("summary", {}).get("deployable", False)
        reason = data.get("summary", {}).get("reason", "unknown")

        logger.info(
            f"can-i-deploy {pacticipant}@{version} -> {to_environment}: "
            f"{'YES' if can_deploy else 'NO'} ({reason})"
        )
        return can_deploy, reason

    def record_deployment(
        self,
        pacticipant: str,
        version: str,
        environment: str = "production",
    ) -> dict:
        """Record that a version has been deployed to an environment."""
        url = (
            f"{self.base_url}/pacticipants/{pacticipant}"
            f"/versions/{version}/deployed-to/{environment}"
        )
        resp = requests.post(url, headers=self._headers, auth=self._auth)
        resp.raise_for_status()
        logger.info(f"Recorded deployment: {pacticipant}@{version} -> {environment}")
        return resp.json()

    def _tag_version(self, pacticipant: str, version: str, tag: str) -> None:
        url = f"{self.base_url}/pacticipants/{pacticipant}/versions/{version}/tags/{tag}"
        requests.put(url, headers=self._headers, auth=self._auth).raise_for_status()

    def _record_branch(self, pacticipant: str, version: str, branch: str) -> None:
        url = (
            f"{self.base_url}/pacticipants/{pacticipant}"
            f"/versions/{version}/branch/{branch}"
        )
        requests.put(url, headers=self._headers, auth=self._auth).raise_for_status()
```

```yaml
# --- .github/workflows/consumer-ci.yml --- Consumer CI pipeline ---

name: Consumer CI (Order Service)

on:
  push:
    branches: [main, "feature/*"]
  pull_request:
    branches: [main]

env:
  PACT_BROKER_URL: ${{ secrets.PACT_BROKER_URL }}
  PACT_BROKER_TOKEN: ${{ secrets.PACT_BROKER_TOKEN }}

jobs:
  test-and-publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements.txt pact-python

      # Step 1: Run consumer contract tests (generates pact files)
      - name: Run consumer contract tests
        run: pytest tests/contract/ -v

      # Step 2: Publish pacts to broker
      - name: Publish pacts to Pact Broker
        run: |
          pact-broker publish ./pacts \
            --consumer-app-version ${{ github.sha }} \
            --branch ${{ github.ref_name }} \
            --broker-base-url $PACT_BROKER_URL \
            --broker-token $PACT_BROKER_TOKEN

      # Step 3: Can-I-Deploy check (blocks merge if contracts are broken)
      - name: Can I Deploy?
        run: |
          pact-broker can-i-deploy \
            --pacticipant OrderService \
            --version ${{ github.sha }} \
            --to-environment production \
            --broker-base-url $PACT_BROKER_URL \
            --broker-token $PACT_BROKER_TOKEN \
            --retry-while-unknown 30 \
            --retry-interval 10

  deploy:
    needs: test-and-publish
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to production
        run: echo "Deploying..."

      # Step 4: Record deployment in broker
      - name: Record deployment
        run: |
          pact-broker record-deployment \
            --pacticipant OrderService \
            --version ${{ github.sha }} \
            --environment production \
            --broker-base-url $PACT_BROKER_URL \
            --broker-token $PACT_BROKER_TOKEN

---
# --- .github/workflows/provider-ci.yml --- Provider CI pipeline ---

name: Provider CI (User Service)

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  # Webhook trigger: broker notifies when new consumer pact is published
  repository_dispatch:
    types: [pact_changed]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements.txt pact-python

      - name: Start provider service
        run: |
          uvicorn user_service.app:app --port 8000 &
          sleep 3

      # Verify all consumer contracts from the broker
      - name: Verify pacts
        run: |
          pact-verifier \
            --provider-base-url http://localhost:8000 \
            --provider UserService \
            --pact-broker-url $PACT_BROKER_URL \
            --provider-app-version ${{ github.sha }} \
            --provider-version-branch ${{ github.ref_name }} \
            --publish-verification-results \
            --enable-pending \
            --consumer-version-selectors '{"mainBranch": true, "deployedOrReleased": true}' \
            --provider-states-setup-url http://localhost:8000/_pact/provider-states

      # Can-I-Deploy check for the provider
      - name: Can I Deploy?
        run: |
          pact-broker can-i-deploy \
            --pacticipant UserService \
            --version ${{ github.sha }} \
            --to-environment production \
            --broker-base-url $PACT_BROKER_URL \
            --broker-token $PACT_BROKER_TOKEN
```

```yaml
# --- docker-compose.pact-broker.yml --- Self-hosted Pact Broker ---

version: "3.9"
services:
  pact-broker:
    image: pactfoundation/pact-broker:latest
    ports:
      - "9292:9292"
    environment:
      PACT_BROKER_DATABASE_URL: "postgres://pact:pact@postgres/pact"
      PACT_BROKER_BASIC_AUTH_USERNAME: admin
      PACT_BROKER_BASIC_AUTH_PASSWORD: admin
      PACT_BROKER_LOG_LEVEL: INFO
      PACT_BROKER_ALLOW_PUBLIC_READ: "true"
      # Webhook: notify provider CI when consumer publishes new pact
      PACT_BROKER_WEBHOOK_SCHEME_WHITELIST: "https"
      PACT_BROKER_WEBHOOK_HOST_WHITELIST: "api.github.com"
    depends_on:
      - postgres

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: pact
      POSTGRES_PASSWORD: pact
      POSTGRES_DB: pact
    volumes:
      - pact_db:/var/lib/postgresql/data

volumes:
  pact_db:

# --- Webhook configuration (via broker API) ---
# curl -X POST http://localhost:9292/webhooks \
#   -H "Content-Type: application/json" \
#   -d '{
#     "events": [{"name": "contract_content_changed"}],
#     "request": {
#       "method": "POST",
#       "url": "https://api.github.com/repos/OWNER/REPO/dispatches",
#       "headers": {
#         "Authorization": "Bearer $TOKEN",
#         "Accept": "application/vnd.github.v3+json"
#       },
#       "body": {
#         "event_type": "pact_changed",
#         "client_payload": {
#           "consumer": "${pactbroker.consumerName}",
#           "provider": "${pactbroker.providerName}"
#         }
#       }
#     }
#   }'
```

| CI Step | Consumer | Provider |
|---------|----------|----------|
| 1. Test | Run contract tests, generate pacts | Start app with test DB |
| 2. Publish | Publish pacts to broker | Verify pacts from broker |
| 3. Check | `can-i-deploy` before merge | `can-i-deploy` before merge |
| 4. Deploy | Deploy, then `record-deployment` | Deploy, then `record-deployment` |
| 5. Notify | N/A | Webhook triggers on new pacts |

Key patterns:
1. Consumers publish pacts with the git SHA as version and branch name for selector matching
2. Providers verify with `enable_pending=True` so new contracts do not immediately break the build
3. Both sides run `can-i-deploy` before deploying — this is the deployment safety gate
4. After successful deployment, call `record-deployment` to update the broker
5. Use webhooks to trigger provider verification when a consumer publishes a new pact'''
    ),
    (
        "testing/contract-vs-integration",
        "Compare contract testing with integration testing — when to use each, trade-offs, and how they complement each other.",
        '''Contract testing vs integration testing — trade-offs and complementary strategies:

```python
# --- integration_test.py --- Traditional integration test ---
# Requires BOTH services running + database + network

import pytest
import requests
import time
from testcontainers.postgres import PostgresContainer
from testcontainers.compose import DockerCompose


class TestOrderUserIntegration:
    """Integration test: actual Order Service calls actual User Service."""

    @pytest.fixture(scope="class")
    def services(self):
        """Start all services with Docker Compose."""
        compose = DockerCompose(
            filepath=".",
            compose_file_name="docker-compose.test.yml",
        )
        compose.start()
        compose.wait_for("http://localhost:8000/health")
        compose.wait_for("http://localhost:8001/health")
        yield compose
        compose.stop()

    def test_create_order_with_valid_user(self, services):
        """Full round-trip: create user, then create order referencing that user."""
        # Step 1: Create user in User Service
        user_resp = requests.post(
            "http://localhost:8001/api/users",
            json={"name": "Alice", "email": "alice@test.com", "tier": "pro"},
        )
        assert user_resp.status_code == 201
        user_id = user_resp.json()["id"]

        # Step 2: Create order in Order Service (which calls User Service)
        order_resp = requests.post(
            "http://localhost:8000/api/orders",
            json={"user_id": user_id, "items": [{"sku": "ITEM-1", "qty": 2}]},
        )
        assert order_resp.status_code == 201
        assert order_resp.json()["user"]["name"] == "Alice"

    def test_create_order_with_missing_user(self, services):
        """Order creation fails gracefully when user doesn't exist."""
        order_resp = requests.post(
            "http://localhost:8000/api/orders",
            json={"user_id": 99999, "items": [{"sku": "ITEM-1", "qty": 1}]},
        )
        assert order_resp.status_code == 422
        assert "user not found" in order_resp.json()["detail"].lower()


# --- contract_test.py --- Equivalent contract test ---
# Requires ONLY the consumer code + Pact mock — no real services

class TestOrderUserContract:
    """Contract test: Order Service defines expectations, verified separately."""

    def test_get_user_for_order(self):
        """Only tests the consumer's expectations of the provider API shape."""
        (
            pact
            .given("user 42 exists")
            .upon_receiving("order service requests user 42")
            .with_request("GET", "/api/users/42")
            .will_respond_with(
                200,
                body=Like({
                    "id": 42,
                    "name": Like("Alice"),
                    "email": Like("alice@test.com"),
                    "tier": Like("pro"),
                }),
            )
        )

        with pact:
            # Test ONLY the client code — no real HTTP calls
            client = UserServiceClient(f"http://localhost:{PACT_MOCK_PORT}")
            user = client.get_user(42)
            assert user.id == 42
            assert isinstance(user.name, str)
```

```python
# --- testing_strategy.py --- When to use each approach ---

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TestType(Enum):
    CONTRACT = "contract"
    INTEGRATION = "integration"
    E2E = "e2e"


@dataclass
class TestingDecision:
    """Decision framework for choosing test types."""
    scenario: str
    recommended: TestType
    reason: str
    alternative: Optional[TestType] = None


TESTING_DECISIONS = [
    # Contract testing wins
    TestingDecision(
        scenario="Verify API shape/schema between services",
        recommended=TestType.CONTRACT,
        reason="Fast, isolated, catches schema drift without running both services",
    ),
    TestingDecision(
        scenario="Microservices owned by different teams",
        recommended=TestType.CONTRACT,
        reason="Teams can develop independently; contract is the shared agreement",
    ),
    TestingDecision(
        scenario="CI pipeline needs to be fast (<5 min)",
        recommended=TestType.CONTRACT,
        reason="No containers, databases, or network — runs in seconds",
    ),
    TestingDecision(
        scenario="Testing backward compatibility of API changes",
        recommended=TestType.CONTRACT,
        reason="can-i-deploy tells you if changes break any consumer",
    ),

    # Integration testing wins
    TestingDecision(
        scenario="Testing database queries and transactions",
        recommended=TestType.INTEGRATION,
        reason="Need real database to verify SQL, indexes, constraints",
    ),
    TestingDecision(
        scenario="Testing message queue behavior (ordering, retry)",
        recommended=TestType.INTEGRATION,
        reason="Need real broker for delivery semantics, DLQ behavior",
    ),
    TestingDecision(
        scenario="Testing cross-service business logic flows",
        recommended=TestType.INTEGRATION,
        reason="Contract tests don't verify business logic correctness",
        alternative=TestType.E2E,
    ),
    TestingDecision(
        scenario="Testing third-party API integrations",
        recommended=TestType.INTEGRATION,
        reason="Can't define contracts for APIs you don't control",
    ),

    # Use both
    TestingDecision(
        scenario="Microservice API with complex business flows",
        recommended=TestType.CONTRACT,
        reason="Contracts for shape, integration for critical business paths",
        alternative=TestType.INTEGRATION,
    ),
]


# --- Test pyramid with contracts ---

TEST_PYRAMID = """
Testing Pyramid with Contract Tests:

            /\\
           /  \\        E2E Tests (few)
          / E2E\\       - Critical user journeys only
         /------\\      - Slow, flaky, expensive
        /        \\
       / Integr.  \\   Integration Tests (some)
      /   Tests    \\  - Real databases, queues
     /--------------\\  - Cross-service business logic
    /                \\
   /  Contract Tests  \\ Contract Tests (many)
  /    (API shape)     \\ - Fast, isolated
 /----------------------\\ - Schema compatibility
/                        \\
/     Unit Tests          \\ Unit Tests (most)
/  (business logic)        \\ - Fastest, most stable
/----------------------------\\
"""
```

```python
# --- combined_strategy.py --- Using both together ---

import pytest
from typing import Callable


class TestOrderWorkflow:
    """Layered testing strategy for the order workflow."""

    # Layer 1: Unit test — pure business logic, no I/O
    def test_calculate_order_total(self):
        """Unit test: verify pricing math."""
        items = [
            {"sku": "A", "price": 10.00, "quantity": 2},
            {"sku": "B", "price": 25.00, "quantity": 1},
        ]
        total = calculate_total(items, discount_pct=10)
        assert total == 40.50  # (20 + 25) * 0.9

    # Layer 2: Contract test — verify API shape between services
    def test_order_service_expects_user_shape(self):
        """Contract: order service expects {id, name, email, tier} from user service."""
        # Runs in <1 second, no real services needed
        # Pact generates contract file for provider to verify
        pass  # (see Pact consumer test above)

    # Layer 3: Integration test — verify real cross-service behavior
    @pytest.mark.integration
    def test_order_applies_user_discount(self, services):
        """Integration: verify pro users get 20% discount (real services)."""
        # Requires both services + database — runs in ~30 seconds
        user = create_test_user(tier="pro")
        order = create_order(user_id=user["id"], items=[{"sku": "A", "qty": 1}])
        assert order["discount_applied"] == 20

    # Layer 4: E2E test — verify critical user journey
    @pytest.mark.e2e
    def test_checkout_flow_end_to_end(self, browser):
        """E2E: full checkout from browsing to payment confirmation."""
        # Requires full stack + browser — runs in ~2 minutes
        pass


def calculate_total(items: list[dict], discount_pct: float = 0) -> float:
    """Pure function — easily unit tested."""
    subtotal = sum(i["price"] * i["quantity"] for i in items)
    return round(subtotal * (1 - discount_pct / 100), 2)


# --- pytest markers for test layers ---
# pytest.ini:
# [pytest]
# markers =
#     unit: Unit tests (no I/O)
#     contract: Pact contract tests
#     integration: Integration tests (real services)
#     e2e: End-to-end tests (browser)
#
# Run by layer:
# pytest -m unit           # fast: ~5 seconds
# pytest -m contract       # fast: ~10 seconds
# pytest -m integration    # slow: ~2 minutes
# pytest -m e2e            # slowest: ~10 minutes
```

| Aspect | Contract Testing | Integration Testing |
|--------|-----------------|-------------------|
| Speed | Seconds (no real services) | Minutes (containers, DBs) |
| Isolation | Consumer and provider test independently | Services must run together |
| Flakiness | Very low (deterministic mocks) | Higher (network, timing, state) |
| What it catches | Schema/shape mismatches | Business logic bugs, data issues |
| What it misses | Business logic correctness | Cannot run without both services |
| Setup cost | Low (Pact library only) | High (Docker Compose, test DBs) |
| Team autonomy | High (teams develop independently) | Low (need access to all services) |
| CI pipeline | Runs in every commit (<30s) | Nightly or pre-deploy (minutes) |
| Third-party APIs | Not suitable (can't define their contract) | Use sandbox/mock servers |
| Deployment safety | `can-i-deploy` gates deployment | Manual verification |

Key patterns:
1. Contract tests replace integration tests for API shape verification, not business logic
2. Use both: contracts in every PR (fast feedback), integration tests nightly (deep verification)
3. Contract tests work best for services your organization owns and controls
4. Run unit > contract > integration > E2E in the CI pipeline, failing fast at each layer
5. `can-i-deploy` is the unique superpower of contract testing — automated deployment safety'''
    ),
]
