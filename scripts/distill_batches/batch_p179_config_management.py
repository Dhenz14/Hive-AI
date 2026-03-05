"""Configuration and secrets management — 12-factor config, Vault integration, secrets rotation, feature flags."""

PAIRS = [
    (
        "backend/twelve-factor-config-pydantic",
        "Show 12-factor app configuration with Pydantic Settings: environment variables, validation, nested config, and multi-environment support.",
        '''12-factor configuration with Pydantic Settings:

```python
from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import (
    Field,
    SecretStr,
    field_validator,
    model_validator,
    AnyHttpUrl,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── Environment enum ──────────────────────────────────────────────

class Environment(str, Enum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


# ── Nested settings groups ────────────────────────────────────────

class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "localhost"
    port: int = 5432
    name: str = "myapp"
    user: str = "postgres"
    password: SecretStr = SecretStr("")
    pool_min: int = Field(default=2, ge=1)
    pool_max: int = Field(default=10, ge=1, le=200)
    pool_timeout: int = Field(default=30, ge=5)
    ssl_mode: str = "prefer"
    statement_timeout_ms: int = 30000

    @property
    def async_dsn(self) -> str:
        pwd = self.password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.user}:{pwd}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @property
    def sync_dsn(self) -> str:
        pwd = self.password.get_secret_value()
        return (
            f"postgresql://{self.user}:{pwd}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    url: str = "redis://localhost:6379/0"
    max_connections: int = 20
    socket_timeout: float = 5.0
    ssl: bool = False


class CORSSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORS_")

    origins: list[str] = Field(default=["http://localhost:3000"])
    allow_credentials: bool = True
    allow_methods: list[str] = Field(default=["*"])
    allow_headers: list[str] = Field(default=["*"])
    max_age: int = 3600


class LoggingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: str = "INFO"
    format: str = "json"  # "json" or "text"
    include_timestamp: bool = True
    include_request_id: bool = True


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_")

    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    issuer: str = "myapp"
    audience: str = "myapp-api"


# ── Main application settings ─────────────────────────────────────

class AppSettings(BaseSettings):
    """Root application configuration.

    12-factor compliant: all config from environment variables.

    Loading priority (highest first):
      1. Environment variables
      2. .env file (local dev only)
      3. Default values
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    # Core
    name: str = "MyApp"
    version: str = "1.0.0"
    environment: Environment = Environment.LOCAL
    debug: bool = False
    base_url: str = "http://localhost:8000"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = Field(default=1, ge=1)
    trusted_proxies: list[str] = Field(default=["127.0.0.1"])

    # Nested configs
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    cors: CORSSettings = Field(default_factory=CORSSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    auth: AuthSettings | None = None

    # Feature toggles
    enable_metrics: bool = True
    enable_docs: bool = True
    enable_profiling: bool = False

    @model_validator(mode="after")
    def validate_production(self) -> AppSettings:
        if self.environment == Environment.PRODUCTION:
            errors: list[str] = []
            if self.debug:
                errors.append("debug must be False in production")
            if self.workers < 2:
                errors.append("workers must be >= 2 in production")
            if self.enable_profiling:
                errors.append("profiling must be disabled in production")
            if self.enable_docs:
                object.__setattr__(self, "enable_docs", False)
            if self.db.ssl_mode == "disable":
                errors.append("DB SSL must not be disabled in production")
            if errors:
                raise ValueError(
                    f"Production validation failed: {'; '.join(errors)}"
                )
        return self
```

```python
# ── Settings singleton with dependency injection ──────────────────

@lru_cache
def get_settings() -> AppSettings:
    """Load settings once, cache for app lifetime."""
    return AppSettings()


# ── FastAPI integration ───────────────────────────────────────────

from fastapi import Depends, FastAPI


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create FastAPI app with settings-driven configuration."""
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.name,
        version=settings.version,
        debug=settings.debug,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
    )

    # CORS
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.origins,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=settings.cors.allow_methods,
        allow_headers=settings.cors.allow_headers,
        max_age=settings.cors.max_age,
    )

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "version": settings.version,
            "environment": settings.environment.value,
        }

    @app.get("/config")
    async def show_config(
        s: AppSettings = Depends(get_settings),
    ):
        """Show non-sensitive config (never expose secrets)."""
        return {
            "name": s.name,
            "version": s.version,
            "environment": s.environment.value,
            "debug": s.debug,
            "workers": s.workers,
            "db_host": s.db.host,
            "db_name": s.db.name,
            "redis_url": s.redis.url,
            "features": {
                "metrics": s.enable_metrics,
                "docs": s.enable_docs,
                "profiling": s.enable_profiling,
            },
        }

    return app


# ── Testing with overridden settings ──────────────────────────────

import pytest


@pytest.fixture
def test_settings(monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    """Override settings for testing."""
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("APP_DEBUG", "true")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_NAME", "test_myapp")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-key")

    get_settings.cache_clear()
    settings = AppSettings()
    return settings


@pytest.fixture
def test_app(test_settings: AppSettings) -> FastAPI:
    return create_app(test_settings)


# ── .env file template ───────────────────────────────────────────

ENV_TEMPLATE = """
# .env (local development only — never commit to git!)
APP_ENVIRONMENT=local
APP_DEBUG=true
APP_PORT=8000

DB_HOST=localhost
DB_PORT=5432
DB_NAME=myapp_dev
DB_USER=postgres
DB_PASSWORD=localdev

REDIS_URL=redis://localhost:6379/0

AUTH_JWT_SECRET=dev-secret-change-in-prod

CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]

LOG_LEVEL=DEBUG
LOG_FORMAT=text
"""
```

```python
# ── Multi-environment configuration factory ───────────────────────

from typing import TypeVar

T = TypeVar("T", bound=BaseSettings)


class ConfigFactory:
    """Load different configs per environment."""

    ENV_FILES: dict[Environment, str] = {
        Environment.LOCAL: ".env",
        Environment.DEVELOPMENT: ".env.development",
        Environment.STAGING: ".env.staging",
        Environment.PRODUCTION: ".env.production",
        Environment.TEST: ".env.test",
    }

    @classmethod
    def create(cls, env: Environment | None = None) -> AppSettings:
        """Create settings for the specified environment."""
        if env is None:
            env_str = os.getenv("APP_ENVIRONMENT", "local")
            env = Environment(env_str)

        env_file = cls.ENV_FILES.get(env, ".env")
        if not Path(env_file).exists():
            env_file = ".env"

        # Temporarily set env_file
        os.environ["APP_ENVIRONMENT"] = env.value
        settings = AppSettings(_env_file=env_file)
        return settings

    @classmethod
    def create_for_testing(cls) -> AppSettings:
        """Minimal config for unit tests."""
        os.environ.update({
            "APP_ENVIRONMENT": "test",
            "APP_DEBUG": "true",
            "DB_HOST": "localhost",
            "DB_NAME": "test_db",
            "DB_PASSWORD": "test",
            "AUTH_JWT_SECRET": "test-secret",
        })
        return AppSettings()


# ── Validation example output ─────────────────────────────────────

def validate_config() -> None:
    """Validate configuration at startup."""
    try:
        settings = get_settings()
        print(f"Config loaded for: {settings.environment.value}")
        print(f"  Database: {settings.db.host}:{settings.db.port}/{settings.db.name}")
        print(f"  Redis: {settings.redis.url}")
        print(f"  Workers: {settings.workers}")
        print(f"  Debug: {settings.debug}")
    except Exception as e:
        print(f"Configuration error: {e}")
        raise SystemExit(1)
```

| Principle | Implementation | Why |
|---|---|---|
| Config from env vars | `SettingsConfigDict(env_prefix=...)` | 12-factor: env-based config |
| Secrets as env vars | `SecretStr` fields | Never log secrets |
| Validate at startup | `@model_validator` | Fail fast on bad config |
| Nested grouping | `DatabaseSettings`, `RedisSettings` | Organized, prefixed env vars |
| Defaults per env | `ConfigFactory.create()` | Different .env per environment |
| Cache singleton | `@lru_cache` on `get_settings()` | Read env once per process |

Key patterns:
1. Use `SecretStr` for all passwords and keys -- prevents accidental logging.
2. `env_nested_delimiter="__"` maps `APP__DB__HOST` to `settings.db.host`.
3. Production validator catches insecure defaults before they reach prod.
4. `@lru_cache` ensures settings are read once; clear in tests with `cache_clear()`.
5. Never commit `.env` files to git -- use `.env.example` as a template.
6. Show non-sensitive config at `/config` endpoint for debugging; never expose secrets.'''
    ),
    (
        "backend/vault-integration",
        "Show HashiCorp Vault integration for secrets management: dynamic database credentials, KV secrets engine, transit encryption, and AppRole auth.",
        '''HashiCorp Vault integration for secrets management:

```python
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import hvac

logger = logging.getLogger(__name__)


# ── Vault client wrapper ─────────────────────────────────────────

class VaultClient:
    """HashiCorp Vault client with AppRole authentication."""

    def __init__(
        self,
        vault_addr: str | None = None,
        role_id: str | None = None,
        secret_id: str | None = None,
        namespace: str | None = None,
    ) -> None:
        self._addr = vault_addr or os.getenv("VAULT_ADDR", "http://localhost:8200")
        self._role_id = role_id or os.getenv("VAULT_ROLE_ID", "")
        self._secret_id = secret_id or os.getenv("VAULT_SECRET_ID", "")
        self._namespace = namespace or os.getenv("VAULT_NAMESPACE")
        self._client: hvac.Client | None = None
        self._token_expiry: float = 0

    def _get_client(self) -> hvac.Client:
        """Get authenticated Vault client, re-authenticating if needed."""
        if self._client and time.time() < self._token_expiry:
            return self._client

        client = hvac.Client(url=self._addr, namespace=self._namespace)

        # Authenticate with AppRole
        if self._role_id and self._secret_id:
            auth_result = client.auth.approle.login(
                role_id=self._role_id,
                secret_id=self._secret_id,
            )
            self._token_expiry = time.time() + auth_result["auth"]["lease_duration"] - 60
            logger.info("Authenticated with Vault via AppRole")
        elif os.getenv("VAULT_TOKEN"):
            client.token = os.getenv("VAULT_TOKEN")
            self._token_expiry = time.time() + 3600
        else:
            raise RuntimeError("No Vault authentication method configured")

        if not client.is_authenticated():
            raise RuntimeError("Vault authentication failed")

        self._client = client
        return client


    # ── KV Secrets Engine (v2) ────────────────────────────────

    def read_secret(
        self,
        path: str,
        mount_point: str = "secret",
    ) -> dict[str, Any]:
        """Read a secret from KV v2 engine."""
        client = self._get_client()
        response = client.secrets.kv.v2.read_secret_version(
            path=path,
            mount_point=mount_point,
        )
        return response["data"]["data"]

    def write_secret(
        self,
        path: str,
        data: dict[str, Any],
        mount_point: str = "secret",
    ) -> None:
        """Write a secret to KV v2 engine."""
        client = self._get_client()
        client.secrets.kv.v2.create_or_update_secret(
            path=path,
            secret=data,
            mount_point=mount_point,
        )

    def list_secrets(
        self,
        path: str,
        mount_point: str = "secret",
    ) -> list[str]:
        """List secret keys at a path."""
        client = self._get_client()
        response = client.secrets.kv.v2.list_secrets(
            path=path,
            mount_point=mount_point,
        )
        return response["data"]["keys"]


    # ── Dynamic Database Credentials ──────────────────────────

    def get_database_credentials(
        self,
        role: str = "myapp-readwrite",
        mount_point: str = "database",
    ) -> DatabaseCredentials:
        """Get dynamic database credentials from Vault.

        Vault creates a temporary user with a limited TTL.
        The credentials are automatically revoked after expiry.
        """
        client = self._get_client()
        response = client.secrets.database.generate_credentials(
            name=role,
            mount_point=mount_point,
        )
        data = response["data"]
        lease = response["lease_duration"]

        creds = DatabaseCredentials(
            username=data["username"],
            password=data["password"],
            lease_id=response["lease_id"],
            lease_duration=lease,
            expires_at=time.time() + lease,
        )
        logger.info(
            f"Got dynamic DB credentials: {creds.username} "
            f"(TTL: {lease}s)"
        )
        return creds

    def renew_lease(self, lease_id: str, increment: int = 3600) -> int:
        """Renew a Vault lease."""
        client = self._get_client()
        response = client.sys.renew_lease(
            lease_id=lease_id,
            increment=increment,
        )
        return response["lease_duration"]


    # ── Transit Secrets Engine (encryption as a service) ──────

    def encrypt(
        self,
        plaintext: str,
        key_name: str = "myapp-key",
        mount_point: str = "transit",
    ) -> str:
        """Encrypt data using Vault Transit engine."""
        import base64
        client = self._get_client()
        response = client.secrets.transit.encrypt_data(
            name=key_name,
            plaintext=base64.b64encode(plaintext.encode()).decode(),
            mount_point=mount_point,
        )
        return response["data"]["ciphertext"]

    def decrypt(
        self,
        ciphertext: str,
        key_name: str = "myapp-key",
        mount_point: str = "transit",
    ) -> str:
        """Decrypt data using Vault Transit engine."""
        import base64
        client = self._get_client()
        response = client.secrets.transit.decrypt_data(
            name=key_name,
            ciphertext=ciphertext,
            mount_point=mount_point,
        )
        return base64.b64decode(response["data"]["plaintext"]).decode()


@dataclass
class DatabaseCredentials:
    username: str
    password: str
    lease_id: str
    lease_duration: int
    expires_at: float

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at - 60  # 60s buffer
```

```python
# ── Credential manager with auto-renewal ──────────────────────────

class CredentialManager:
    """Manages dynamic credentials with automatic renewal."""

    def __init__(self, vault: VaultClient) -> None:
        self._vault = vault
        self._db_creds: DatabaseCredentials | None = None
        self._renewal_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start credential management."""
        self._db_creds = self._vault.get_database_credentials()
        self._renewal_task = asyncio.create_task(self._renewal_loop())

    async def _renewal_loop(self) -> None:
        """Renew credentials before they expire."""
        while True:
            if not self._db_creds:
                await asyncio.sleep(10)
                continue

            # Renew at 2/3 of lease duration
            sleep_time = self._db_creds.lease_duration * 2 / 3
            await asyncio.sleep(sleep_time)

            try:
                new_duration = self._vault.renew_lease(
                    self._db_creds.lease_id,
                    increment=self._db_creds.lease_duration,
                )
                self._db_creds.expires_at = time.time() + new_duration
                logger.info(
                    f"Renewed DB credentials: {self._db_creds.username} "
                    f"(TTL: {new_duration}s)"
                )
            except Exception as e:
                logger.error(f"Lease renewal failed: {e}")
                # Get fresh credentials
                try:
                    self._db_creds = self._vault.get_database_credentials()
                except Exception as e2:
                    logger.critical(f"Failed to get new credentials: {e2}")

    @property
    def database_dsn(self) -> str:
        if not self._db_creds:
            raise RuntimeError("Credentials not initialized")
        return (
            f"postgresql+asyncpg://{self._db_creds.username}:"
            f"{self._db_creds.password}@db.internal:5432/myapp"
        )

    async def stop(self) -> None:
        if self._renewal_task:
            self._renewal_task.cancel()


# ── Pydantic Settings with Vault source ───────────────────────────

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
)


class VaultSettingsSource(PydanticBaseSettingsSource):
    """Load settings from Vault KV engine."""

    def __init__(
        self,
        settings_cls: type[BaseSettings],
        vault_path: str = "myapp/config",
    ) -> None:
        super().__init__(settings_cls)
        self._vault_path = vault_path
        self._data: dict[str, Any] = {}

    def get_field_value(
        self, field: Any, field_name: str
    ) -> tuple[Any, str, bool]:
        val = self._data.get(field_name)
        return val, field_name, val is not None

    def __call__(self) -> dict[str, Any]:
        if not self._data:
            try:
                vault = VaultClient()
                self._data = vault.read_secret(self._vault_path)
            except Exception as e:
                logger.warning(f"Vault unavailable: {e}")
        return self._data
```

```python
# ── Vault setup commands (Terraform/CLI) ──────────────────────────

VAULT_SETUP = """
# Enable KV v2 secrets engine
vault secrets enable -path=secret kv-v2

# Store application secrets
vault kv put secret/myapp/config \\
    db_password="prod-db-password" \\
    jwt_secret="prod-jwt-secret-key" \\
    api_key="prod-api-key"

# Enable database secrets engine
vault secrets enable database

# Configure PostgreSQL connection
vault write database/config/myapp-postgres \\
    plugin_name=postgresql-database-plugin \\
    allowed_roles="myapp-readwrite,myapp-readonly" \\
    connection_url="postgresql://{{username}}:{{password}}@db.internal:5432/myapp" \\
    username="vault_admin" \\
    password="vault_admin_password"

# Create read-write role (credentials valid for 1 hour)
vault write database/roles/myapp-readwrite \\
    db_name=myapp-postgres \\
    creation_statements="CREATE ROLE \\"{{name}}\\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT ALL ON ALL TABLES IN SCHEMA public TO \\"{{name}}\\";" \\
    revocation_statements="REVOKE ALL ON ALL TABLES IN SCHEMA public FROM \\"{{name}}\\"; DROP ROLE IF EXISTS \\"{{name}}\\";" \\
    default_ttl="1h" \\
    max_ttl="24h"

# Create read-only role
vault write database/roles/myapp-readonly \\
    db_name=myapp-postgres \\
    creation_statements="CREATE ROLE \\"{{name}}\\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO \\"{{name}}\\";" \\
    default_ttl="1h" \\
    max_ttl="24h"

# Enable Transit encryption
vault secrets enable transit
vault write -f transit/keys/myapp-key

# Enable AppRole auth
vault auth enable approle
vault write auth/approle/role/myapp \\
    token_ttl=1h \\
    token_max_ttl=4h \\
    secret_id_ttl=720h \\
    token_policies="myapp-policy"

# Policy for the application
vault policy write myapp-policy - <<POLICY
path "secret/data/myapp/*" {
  capabilities = ["read"]
}
path "database/creds/myapp-readwrite" {
  capabilities = ["read"]
}
path "database/creds/myapp-readonly" {
  capabilities = ["read"]
}
path "transit/encrypt/myapp-key" {
  capabilities = ["update"]
}
path "transit/decrypt/myapp-key" {
  capabilities = ["update"]
}
path "sys/leases/renew" {
  capabilities = ["update"]
}
POLICY
"""
```

| Vault Engine | Purpose | Use Case |
|---|---|---|
| KV v2 | Static key-value secrets | API keys, config values |
| Database | Dynamic database credentials | Short-lived DB users |
| Transit | Encryption as a service | Encrypt PII at rest |
| PKI | Dynamic TLS certificates | Service-to-service mTLS |
| AWS | Dynamic AWS credentials | Temporary IAM roles |
| AppRole | Machine authentication | Service identity |

Key patterns:
1. **AppRole auth** for machine-to-machine; never hardcode Vault tokens.
2. **Dynamic DB credentials** with 1-hour TTL -- auto-created, auto-revoked.
3. **Lease renewal** at 2/3 of TTL prevents credential expiry during operation.
4. **Transit engine** encrypts data without exposing the encryption key to the app.
5. Use **least-privilege policies** -- each service gets only the paths it needs.
6. `VaultSettingsSource` integrates Vault with Pydantic Settings loading chain.'''
    ),
    (
        "backend/secrets-rotation-zero-downtime",
        "Show secrets rotation and zero-downtime key rollover: dual-key acceptance, graceful rotation, database credential rotation, and JWT key rotation.",
        '''Secrets rotation and zero-downtime key rollover:

```python
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)


# ── Key manager with dual-key support ─────────────────────────────

@dataclass
class KeyVersion:
    """A single key version with metadata."""
    key_id: str
    key_value: str
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    status: str = "active"  # active, rotated, expired


class KeyManager:
    """Manages encryption/signing keys with zero-downtime rotation.

    During rotation, both old and new keys are accepted.
    Only the newest key is used for signing/encrypting.
    """

    def __init__(self, key_name: str) -> None:
        self._key_name = key_name
        self._versions: list[KeyVersion] = []
        self._active_key: KeyVersion | None = None

    @property
    def current_key(self) -> KeyVersion:
        """Get the current active key (for signing/encrypting)."""
        if not self._active_key:
            raise RuntimeError(f"No active key for {self._key_name}")
        return self._active_key

    @property
    def all_valid_keys(self) -> list[KeyVersion]:
        """All keys that should be accepted (for verification/decryption)."""
        now = time.time()
        return [
            k for k in self._versions
            if k.status in ("active", "rotated")
            and (k.expires_at is None or k.expires_at > now)
        ]

    def add_key(
        self,
        key_value: str | None = None,
        grace_period_hours: int = 24,
    ) -> KeyVersion:
        """Add a new key version and rotate the previous one."""
        new_key = KeyVersion(
            key_id=f"{self._key_name}-{len(self._versions) + 1}",
            key_value=key_value or secrets.token_hex(32),
        )

        # Mark previous active key as rotated (still valid for verification)
        if self._active_key:
            self._active_key.status = "rotated"
            self._active_key.expires_at = (
                time.time() + grace_period_hours * 3600
            )
            logger.info(
                f"Key {self._active_key.key_id} rotated, "
                f"grace period: {grace_period_hours}h"
            )

        self._versions.append(new_key)
        self._active_key = new_key
        logger.info(f"New key activated: {new_key.key_id}")
        return new_key

    def verify_with_any_key(
        self,
        payload: bytes,
        signature: str,
    ) -> tuple[bool, str]:
        """Try to verify signature with any valid key.
        Returns (valid, key_id) tuple."""
        for key in self.all_valid_keys:
            expected = hmac.new(
                key.key_value.encode(),
                payload,
                hashlib.sha256,
            ).hexdigest()
            if hmac.compare_digest(expected, signature):
                return True, key.key_id
        return False, ""

    def sign(self, payload: bytes) -> tuple[str, str]:
        """Sign with the current active key.
        Returns (signature, key_id)."""
        key = self.current_key
        sig = hmac.new(
            key.key_value.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return sig, key.key_id

    def cleanup_expired(self) -> int:
        """Remove expired key versions."""
        now = time.time()
        before = len(self._versions)
        self._versions = [
            k for k in self._versions
            if k.status == "active"
            or (k.expires_at is not None and k.expires_at > now)
        ]
        removed = before - len(self._versions)
        if removed:
            logger.info(f"Cleaned up {removed} expired keys")
        return removed
```

```python
# ── JWT key rotation ──────────────────────────────────────────────

import jwt


class JWTKeyRotator:
    """JWT signing with automatic key rotation.

    Uses JWKS (JSON Web Key Set) for public key distribution.
    During rotation, tokens signed with old keys are still valid
    until their natural expiry.
    """

    def __init__(self) -> None:
        self._key_manager = KeyManager("jwt-signing")

    def initialize(self, initial_secret: str) -> None:
        self._key_manager.add_key(initial_secret)

    def rotate(self, grace_period_hours: int = 48) -> str:
        """Rotate JWT signing key with grace period."""
        new_key = self._key_manager.add_key(
            grace_period_hours=grace_period_hours
        )
        return new_key.key_id

    def create_token(
        self,
        payload: dict[str, Any],
        expires_in: timedelta = timedelta(hours=1),
    ) -> str:
        """Create JWT with current key."""
        key = self._key_manager.current_key
        now = datetime.now(timezone.utc)

        token_payload = {
            **payload,
            "iat": now,
            "exp": now + expires_in,
            "kid": key.key_id,  # key ID in header
        }

        return jwt.encode(
            token_payload,
            key.key_value,
            algorithm="HS256",
            headers={"kid": key.key_id},
        )

    def verify_token(self, token: str) -> dict[str, Any]:
        """Verify JWT, trying all valid keys."""
        # Try to get kid from header first
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid", "")
        except jwt.InvalidTokenError:
            kid = ""

        # Try matching key first, then all valid keys
        keys_to_try = self._key_manager.all_valid_keys
        if kid:
            matching = [k for k in keys_to_try if k.key_id == kid]
            keys_to_try = matching + [k for k in keys_to_try if k.key_id != kid]

        last_error: Exception | None = None
        for key in keys_to_try:
            try:
                return jwt.decode(
                    token,
                    key.key_value,
                    algorithms=["HS256"],
                )
            except jwt.InvalidSignatureError:
                continue
            except jwt.ExpiredSignatureError as e:
                last_error = e
                break  # token expired, don't try other keys
            except jwt.InvalidTokenError as e:
                last_error = e
                continue

        if last_error:
            raise last_error
        raise jwt.InvalidSignatureError("No valid key found for token")


# ── Database credential rotation ──────────────────────────────────

class DatabaseCredentialRotator:
    """Rotate database credentials with zero downtime.

    Strategy: create new user, update app, drop old user.
    During transition, both credentials work.
    """

    def __init__(self, admin_dsn: str) -> None:
        self._admin_dsn = admin_dsn

    async def rotate(
        self,
        app_user: str,
        new_password: str | None = None,
    ) -> dict[str, str]:
        """Rotate database user password.

        1. Create new temporary user with same permissions
        2. App switches to new user
        3. Drop old user or change its password

        Alternative (simpler): ALTER USER ... PASSWORD ...
        requires connection pool drain.
        """
        new_password = new_password or secrets.token_urlsafe(32)

        import asyncpg
        conn = await asyncpg.connect(self._admin_dsn)
        try:
            # Strategy 1: Simple password change
            # (requires connection pool reconnection)
            await conn.execute(
                f"ALTER USER {app_user} WITH PASSWORD $1",
                new_password,
            )

            logger.info(f"Rotated password for user {app_user}")
            return {"username": app_user, "password": new_password}

        finally:
            await conn.close()

    async def rotate_with_dual_user(
        self,
        current_user: str,
        new_user: str | None = None,
    ) -> dict[str, str]:
        """Rotate by creating a new user (zero-downtime).

        1. Create new_user with same grants
        2. App switches connections to new_user
        3. After drain period, drop current_user
        """
        new_user = new_user or f"{current_user}_v{int(time.time()) % 10000}"
        new_password = secrets.token_urlsafe(32)

        import asyncpg
        conn = await asyncpg.connect(self._admin_dsn)
        try:
            # Create new user
            await conn.execute(
                f"CREATE USER {new_user} WITH PASSWORD $1",
                new_password,
            )

            # Copy grants from current user
            grants = await conn.fetch("""
                SELECT table_schema, table_name, privilege_type
                FROM information_schema.role_table_grants
                WHERE grantee = $1
            """, current_user)

            for grant in grants:
                schema = grant["table_schema"]
                table = grant["table_name"]
                priv = grant["privilege_type"]
                await conn.execute(
                    f"GRANT {priv} ON {schema}.{table} TO {new_user}"
                )

            logger.info(
                f"Created new DB user {new_user} with "
                f"{len(grants)} grants copied from {current_user}"
            )

            return {"username": new_user, "password": new_password}

        finally:
            await conn.close()
```

```python
# ── Automated rotation scheduler ──────────────────────────────────

class RotationScheduler:
    """Schedules and executes secret rotations."""

    def __init__(self) -> None:
        self._jwt_rotator = JWTKeyRotator()
        self._rotations: list[dict[str, Any]] = []

    async def run(self) -> None:
        """Main rotation loop."""
        while True:
            for rotation in self._rotations:
                if self._should_rotate(rotation):
                    await self._execute_rotation(rotation)
            await asyncio.sleep(3600)  # check every hour

    def schedule(
        self,
        name: str,
        interval_days: int,
        rotation_fn: Any,
        grace_period_hours: int = 24,
    ) -> None:
        self._rotations.append({
            "name": name,
            "interval_days": interval_days,
            "rotation_fn": rotation_fn,
            "grace_period_hours": grace_period_hours,
            "last_rotation": 0.0,
        })

    def _should_rotate(self, rotation: dict) -> bool:
        elapsed = time.time() - rotation["last_rotation"]
        return elapsed >= rotation["interval_days"] * 86400

    async def _execute_rotation(self, rotation: dict) -> None:
        try:
            logger.info(f"Starting rotation: {rotation['name']}")
            await rotation["rotation_fn"]()
            rotation["last_rotation"] = time.time()
            logger.info(f"Rotation completed: {rotation['name']}")
        except Exception as e:
            logger.error(
                f"Rotation failed for {rotation['name']}: {e}"
            )


# ── FastAPI integration ───────────────────────────────────────────

from fastapi import FastAPI, Depends, HTTPException

app = FastAPI()

jwt_rotator = JWTKeyRotator()
jwt_rotator.initialize("initial-secret-key")


@app.post("/auth/login")
async def login(username: str, password: str):
    # Validate credentials...
    token = jwt_rotator.create_token(
        {"sub": username, "role": "user"},
        expires_in=timedelta(hours=8),
    )
    return {"access_token": token, "token_type": "bearer"}


@app.get("/protected")
async def protected(token: str):
    try:
        payload = jwt_rotator.verify_token(token)
        return {"user": payload["sub"]}
    except Exception:
        raise HTTPException(401, "Invalid token")


@app.post("/admin/rotate-jwt-key")
async def rotate_jwt_key():
    """Rotate JWT signing key (admin only)."""
    new_kid = jwt_rotator.rotate(grace_period_hours=48)
    return {"new_key_id": new_kid, "grace_period": "48h"}
```

| Secret Type | Rotation Interval | Grace Period | Method |
|---|---|---|---|
| JWT signing key | 30-90 days | 48 hours (> max token TTL) | Dual-key acceptance |
| API keys | 90 days | 7 days | Old key valid during grace |
| DB password | 7-30 days | Connection pool drain time | ALTER USER or dual-user |
| TLS certificates | 30-90 days | Hours (via cert chain) | New cert before old expires |
| Webhook secrets | 90 days | 7 days | Accept both during overlap |
| Encryption keys | 365 days | Indefinite (for decryption) | Encrypt with new, decrypt with any |

Key patterns:
1. **Dual-key acceptance**: during rotation, accept both old and new keys for verification.
2. JWT grace period must exceed the **maximum token TTL** to avoid breaking valid tokens.
3. `kid` (key ID) in JWT header allows direct key lookup without trying all keys.
4. Database rotation via **dual-user** avoids connection pool disruption.
5. **Cleanup expired keys** periodically to prevent unbounded key list growth.
6. Never rotate all secrets simultaneously -- stagger rotations to isolate failures.'''
    ),
    (
        "backend/feature-flags-patterns",
        "Show feature flag patterns with LaunchDarkly/Unleash-style SDKs: flag evaluation, targeting rules, gradual rollouts, and A/B testing.",
        '''Feature flag patterns with targeting, rollouts, and A/B testing:

```python
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ── Flag definitions ──────────────────────────────────────────────

class FlagType(str, Enum):
    BOOLEAN = "boolean"
    STRING = "string"
    NUMBER = "number"
    JSON = "json"


class RolloutStrategy(str, Enum):
    ALL = "all"                    # on for everyone
    NONE = "none"                  # off for everyone
    PERCENTAGE = "percentage"      # gradual rollout
    USER_LIST = "user_list"        # specific users
    ATTRIBUTE = "attribute"        # based on user attributes
    RING = "ring"                  # deployment rings


@dataclass
class TargetingRule:
    """A rule for targeting specific users/segments."""
    attribute: str               # e.g., "country", "plan", "email"
    operator: str                # eq, neq, contains, in, gt, lt
    values: list[Any]            # values to match
    variation: int = 0           # which variation to serve


@dataclass
class FlagConfig:
    """Complete feature flag configuration."""
    key: str
    flag_type: FlagType = FlagType.BOOLEAN
    enabled: bool = True
    default_variation: int = 0
    variations: list[Any] = field(default_factory=lambda: [False, True])
    targeting_rules: list[TargetingRule] = field(default_factory=list)
    rollout_percentage: float = 0.0  # 0-100
    rollout_stickiness: str = "user_id"  # attribute for consistent hashing
    description: str = ""
    tags: list[str] = field(default_factory=list)


# ── User context ──────────────────────────────────────────────────

@dataclass
class UserContext:
    """User attributes for flag evaluation."""
    user_id: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "user_id":
            return self.user_id
        return self.attributes.get(key, default)


# ── Flag evaluator ────────────────────────────────────────────────

class FlagEvaluator:
    """Evaluates feature flags against user context."""

    def evaluate(
        self,
        flag: FlagConfig,
        user: UserContext,
    ) -> tuple[Any, str]:
        """Evaluate a flag for a user.
        Returns (variation_value, reason)."""

        # Flag disabled globally
        if not flag.enabled:
            return flag.variations[flag.default_variation], "flag_disabled"

        # Check targeting rules (first match wins)
        for rule in flag.targeting_rules:
            if self._matches_rule(rule, user):
                return flag.variations[rule.variation], f"rule:{rule.attribute}"

        # Percentage rollout
        if flag.rollout_percentage > 0:
            if self._in_rollout(
                flag.key,
                user.get(flag.rollout_stickiness, user.user_id),
                flag.rollout_percentage,
            ):
                # Return the "on" variation (typically index 1)
                on_variation = min(1, len(flag.variations) - 1)
                return flag.variations[on_variation], "percentage_rollout"

        # Default
        return flag.variations[flag.default_variation], "default"

    def _matches_rule(
        self, rule: TargetingRule, user: UserContext
    ) -> bool:
        """Check if user matches a targeting rule."""
        user_value = user.get(rule.attribute)
        if user_value is None:
            return False

        op = rule.operator
        values = rule.values

        if op == "eq":
            return user_value == values[0]
        elif op == "neq":
            return user_value != values[0]
        elif op == "in":
            return user_value in values
        elif op == "not_in":
            return user_value not in values
        elif op == "contains":
            return any(v in str(user_value) for v in values)
        elif op == "starts_with":
            return str(user_value).startswith(values[0])
        elif op == "ends_with":
            return str(user_value).endswith(values[0])
        elif op == "gt":
            return float(user_value) > float(values[0])
        elif op == "lt":
            return float(user_value) < float(values[0])
        elif op == "gte":
            return float(user_value) >= float(values[0])
        elif op == "lte":
            return float(user_value) <= float(values[0])
        elif op == "semver_gt":
            from packaging.version import Version
            return Version(str(user_value)) > Version(str(values[0]))

        return False

    def _in_rollout(
        self,
        flag_key: str,
        stickiness_value: str,
        percentage: float,
    ) -> bool:
        """Deterministic percentage rollout using consistent hashing.
        Same user always gets the same result for the same flag."""
        hash_input = f"{flag_key}:{stickiness_value}"
        hash_value = int(
            hashlib.md5(hash_input.encode()).hexdigest()[:8], 16
        )
        bucket = (hash_value % 10000) / 100.0  # 0.00 - 99.99
        return bucket < percentage
```

```python
# ── Feature flag service (in-memory + sync from backend) ──────────

import asyncio
from typing import Callable


class FeatureFlagService:
    """Feature flag service with local evaluation and remote sync."""

    def __init__(self) -> None:
        self._flags: dict[str, FlagConfig] = {}
        self._evaluator = FlagEvaluator()
        self._listeners: list[Callable[[str, FlagConfig], None]] = []
        self._sync_task: asyncio.Task | None = None

    def register_flags(self, flags: list[FlagConfig]) -> None:
        """Register flag configurations."""
        for flag in flags:
            self._flags[flag.key] = flag

    def get_flag(
        self,
        key: str,
        user: UserContext,
        default: Any = None,
    ) -> Any:
        """Evaluate a feature flag for a user."""
        flag = self._flags.get(key)
        if not flag:
            logger.warning(f"Unknown flag: {key}")
            return default

        value, reason = self._evaluator.evaluate(flag, user)
        logger.debug(
            f"Flag {key} = {value} for user {user.user_id} ({reason})"
        )
        return value

    def is_enabled(self, key: str, user: UserContext) -> bool:
        """Shorthand for boolean flags."""
        return bool(self.get_flag(key, user, default=False))

    def get_variant(
        self, key: str, user: UserContext, default: str = "control"
    ) -> str:
        """Get A/B test variant."""
        return str(self.get_flag(key, user, default=default))

    def on_flag_changed(
        self, callback: Callable[[str, FlagConfig], None]
    ) -> None:
        self._listeners.append(callback)

    def update_flag(self, key: str, updates: dict[str, Any]) -> None:
        """Update a flag configuration."""
        flag = self._flags.get(key)
        if not flag:
            return
        for attr, value in updates.items():
            setattr(flag, attr, value)
        for listener in self._listeners:
            try:
                listener(key, flag)
            except Exception as e:
                logger.error(f"Listener error: {e}")

    async def start_sync(
        self,
        fetch_fn: Callable[[], list[FlagConfig]],
        interval: float = 30.0,
    ) -> None:
        """Periodically sync flags from a remote source."""
        async def _sync_loop() -> None:
            while True:
                try:
                    remote_flags = fetch_fn()
                    for flag in remote_flags:
                        old = self._flags.get(flag.key)
                        self._flags[flag.key] = flag
                        if old and old != flag:
                            for listener in self._listeners:
                                listener(flag.key, flag)
                except Exception as e:
                    logger.error(f"Flag sync error: {e}")
                await asyncio.sleep(interval)

        self._sync_task = asyncio.create_task(_sync_loop())


# ── Predefined flag configurations ────────────────────────────────

DEFAULT_FLAGS = [
    FlagConfig(
        key="new_checkout_flow",
        description="New checkout UI with improved UX",
        enabled=True,
        rollout_percentage=25.0,  # 25% of users
        targeting_rules=[
            # Always on for internal users
            TargetingRule(
                attribute="email",
                operator="ends_with",
                values=["@mycompany.com"],
                variation=1,
            ),
            # Always on for beta testers
            TargetingRule(
                attribute="plan",
                operator="eq",
                values=["beta"],
                variation=1,
            ),
        ],
    ),
    FlagConfig(
        key="dark_mode",
        flag_type=FlagType.BOOLEAN,
        enabled=True,
        rollout_percentage=100.0,  # fully rolled out
    ),
    FlagConfig(
        key="pricing_experiment",
        flag_type=FlagType.STRING,
        enabled=True,
        variations=["control", "variant_a", "variant_b"],
        rollout_percentage=100.0,
        description="A/B/C test for pricing page",
    ),
    FlagConfig(
        key="api_rate_limit",
        flag_type=FlagType.NUMBER,
        enabled=True,
        variations=[100, 200, 500, 1000],
        default_variation=0,
        targeting_rules=[
            TargetingRule(attribute="plan", operator="eq", values=["pro"], variation=2),
            TargetingRule(attribute="plan", operator="eq", values=["enterprise"], variation=3),
        ],
    ),
]
```

```python
# ── FastAPI middleware integration ────────────────────────────────

from fastapi import FastAPI, Request, Depends


app = FastAPI()
flag_service = FeatureFlagService()
flag_service.register_flags(DEFAULT_FLAGS)


def get_user_context(request: Request) -> UserContext:
    """Extract user context from request."""
    return UserContext(
        user_id=request.headers.get("x-user-id", "anonymous"),
        attributes={
            "email": request.headers.get("x-user-email", ""),
            "plan": request.headers.get("x-user-plan", "free"),
            "country": request.headers.get("x-user-country", ""),
            "app_version": request.headers.get("x-app-version", ""),
        },
    )


@app.get("/checkout")
async def checkout(
    user: UserContext = Depends(get_user_context),
):
    """Route to different checkout based on feature flag."""
    if flag_service.is_enabled("new_checkout_flow", user):
        return {"checkout": "v2", "features": ["express_pay", "saved_addresses"]}
    return {"checkout": "v1"}


@app.get("/pricing")
async def pricing(
    user: UserContext = Depends(get_user_context),
):
    """A/B test on pricing page."""
    variant = flag_service.get_variant("pricing_experiment", user)
    pricing_data = {
        "control": {"basic": 9.99, "pro": 29.99},
        "variant_a": {"basic": 7.99, "pro": 24.99},
        "variant_b": {"basic": 12.99, "pro": 34.99},
    }
    return {
        "variant": variant,
        "prices": pricing_data.get(variant, pricing_data["control"]),
    }


@app.get("/api/flags")
async def list_flags(
    user: UserContext = Depends(get_user_context),
):
    """Return all flag values for this user (for client-side SDKs)."""
    flags: dict[str, Any] = {}
    for key, flag in flag_service._flags.items():
        value, reason = flag_service._evaluator.evaluate(flag, user)
        flags[key] = {
            "value": value,
            "reason": reason,
        }
    return {"flags": flags}


@app.post("/admin/flags/{key}/rollout")
async def update_rollout(key: str, percentage: float):
    """Gradually increase rollout percentage."""
    flag_service.update_flag(key, {"rollout_percentage": percentage})
    return {"key": key, "rollout_percentage": percentage}
```

| Rollout Strategy | How It Works | Use Case |
|---|---|---|
| Percentage | Consistent hash of user_id + flag_key | Gradual feature rollout |
| User list | Match specific user IDs | Beta testers, internal users |
| Attribute targeting | Match user properties | Plan-based features |
| Ring-based | Internal -> beta -> GA | Enterprise deployments |
| Time-based | Enable at a specific time | Scheduled launches |

| Evaluation Order | Priority | Example |
|---|---|---|
| Flag disabled | Highest | `enabled: false` -> always default |
| Targeting rules | High | Email ends with @company.com |
| Percentage rollout | Medium | 25% of users |
| Default variation | Lowest | Fallback value |

Key patterns:
1. **Consistent hashing** (MD5 of flag_key + user_id) ensures the same user always gets the same variation.
2. **Targeting rules** take precedence over percentage rollout -- useful for internal testing.
3. First matching rule wins -- order rules from most specific to least specific.
4. **`/api/flags` endpoint** returns all evaluated flags for client-side SDKs.
5. Gradual rollout: increase percentage over time (5% -> 25% -> 50% -> 100%).
6. Always provide a **default value** -- handle unknown flags gracefully.'''
    ),
]
"""
