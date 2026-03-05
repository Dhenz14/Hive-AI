"""Configuration management — feature flags, environment config, and Vault patterns."""

PAIRS = [
    (
        "devops/feature-flags",
        "Show feature flag patterns: gradual rollout, A/B testing, and flag lifecycle management.",
        '''Feature flag patterns:

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import hashlib
import json
import time
import logging

logger = logging.getLogger(__name__)


class FlagState(Enum):
    OFF = "off"
    ON = "on"
    PERCENTAGE = "percentage"
    TARGETED = "targeted"


@dataclass
class FeatureFlag:
    name: str
    state: FlagState = FlagState.OFF
    percentage: int = 0                # For gradual rollout (0-100)
    allowed_users: set[str] = field(default_factory=set)
    allowed_groups: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class FeatureFlagService:
    """Feature flag evaluation engine."""

    def __init__(self):
        self._flags: dict[str, FeatureFlag] = {}
        self._overrides: dict[str, dict[str, bool]] = {}  # user -> flag -> value

    def register(self, flag: FeatureFlag):
        self._flags[flag.name] = flag

    def is_enabled(
        self,
        flag_name: str,
        user_id: str | None = None,
        user_groups: set[str] | None = None,
        default: bool = False,
    ) -> bool:
        """Evaluate feature flag for a user."""
        flag = self._flags.get(flag_name)
        if not flag:
            logger.warning("Unknown flag: %s", flag_name)
            return default

        # Check user-level override first
        if user_id and user_id in self._overrides:
            override = self._overrides[user_id].get(flag_name)
            if override is not None:
                return override

        match flag.state:
            case FlagState.OFF:
                return False

            case FlagState.ON:
                return True

            case FlagState.TARGETED:
                # Check user allowlist
                if user_id and user_id in flag.allowed_users:
                    return True
                # Check group allowlist
                if user_groups and flag.allowed_groups & user_groups:
                    return True
                return False

            case FlagState.PERCENTAGE:
                if not user_id:
                    return False
                # Deterministic hash — same user always gets same result
                hash_input = f"{flag_name}:{user_id}".encode()
                hash_val = int(hashlib.sha256(hash_input).hexdigest()[:8], 16)
                return (hash_val % 100) < flag.percentage

    def set_override(self, user_id: str, flag_name: str, value: bool):
        """Set per-user override (for testing/support)."""
        self._overrides.setdefault(user_id, {})[flag_name] = value

    def get_all_flags(self, user_id: str | None = None) -> dict[str, bool]:
        """Get all flag states for a user (for frontend bootstrap)."""
        return {
            name: self.is_enabled(name, user_id)
            for name in self._flags
        }


# --- Usage ---

flags = FeatureFlagService()

# Register flags
flags.register(FeatureFlag(
    name="new_checkout",
    state=FlagState.PERCENTAGE,
    percentage=25,  # 25% of users
))

flags.register(FeatureFlag(
    name="dark_mode",
    state=FlagState.TARGETED,
    allowed_groups={"beta_testers"},
))

flags.register(FeatureFlag(
    name="legacy_api",
    state=FlagState.ON,
))


# In application code
async def checkout(user_id: str, cart: dict):
    if flags.is_enabled("new_checkout", user_id):
        return await new_checkout_flow(cart)
    return await legacy_checkout_flow(cart)


# API endpoint to bootstrap flags for frontend
# GET /api/flags?user_id=abc
# Returns: {"new_checkout": true, "dark_mode": false, "legacy_api": true}


# --- Flag lifecycle ---

# 1. Create flag (OFF by default)
# 2. Enable for developers/QA (TARGETED)
# 3. Enable for beta users (TARGETED with groups)
# 4. Gradual rollout (PERCENTAGE: 5% → 25% → 50% → 100%)
# 5. Fully enabled (ON)
# 6. Remove flag from code
# 7. Delete flag definition


# --- A/B test variant ---

@dataclass
class Experiment:
    name: str
    variants: dict[str, int]  # variant_name -> weight

    def assign_variant(self, user_id: str) -> str:
        hash_input = f"{self.name}:{user_id}".encode()
        hash_val = int(hashlib.sha256(hash_input).hexdigest()[:8], 16) % 100

        cumulative = 0
        for variant, weight in self.variants.items():
            cumulative += weight
            if hash_val < cumulative:
                return variant
        return list(self.variants.keys())[-1]

# experiment = Experiment("checkout_button", {"blue": 50, "green": 50})
# variant = experiment.assign_variant("user-123")  # Deterministic
```

Feature flag patterns:
1. **Deterministic hashing** — same user always sees same flag state
2. **Percentage rollout** — gradual increase from 5% → 25% → 50% → 100%
3. **Targeted flags** — enable for specific users or groups (beta testers)
4. **User overrides** — support team can toggle flags for specific users
5. **Flag lifecycle** — OFF → TARGETED → PERCENTAGE → ON → remove from code'''
    ),
    (
        "devops/vault-secrets",
        "Show HashiCorp Vault patterns: secret engines, dynamic credentials, and transit encryption.",
        '''HashiCorp Vault patterns:

```python
import hvac
import os
from functools import lru_cache
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


# --- Vault client setup ---

def create_vault_client() -> hvac.Client:
    """Create authenticated Vault client."""
    client = hvac.Client(
        url=os.environ.get("VAULT_ADDR", "https://vault.example.com:8200"),
    )

    # Auth method 1: Token (simple, for dev)
    token = os.environ.get("VAULT_TOKEN")
    if token:
        client.token = token
        return client

    # Auth method 2: AppRole (for services)
    role_id = os.environ.get("VAULT_ROLE_ID")
    secret_id = os.environ.get("VAULT_SECRET_ID")
    if role_id and secret_id:
        client.auth.approle.login(role_id=role_id, secret_id=secret_id)
        return client

    # Auth method 3: Kubernetes (for pods)
    jwt_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    if os.path.exists(jwt_path):
        with open(jwt_path) as f:
            jwt = f.read()
        client.auth.kubernetes.login(role="myapp", jwt=jwt)
        return client

    raise RuntimeError("No Vault authentication method available")


# --- KV secrets engine (static secrets) ---

class SecretManager:
    def __init__(self, client: hvac.Client, mount_point: str = "secret"):
        self.client = client
        self.mount_point = mount_point
        self._cache: dict[str, dict] = {}

    def get_secret(self, path: str) -> dict:
        """Read secret from KV v2 engine."""
        if path in self._cache:
            return self._cache[path]

        response = self.client.secrets.kv.v2.read_secret_version(
            path=path, mount_point=self.mount_point,
        )
        data = response["data"]["data"]
        self._cache[path] = data
        return data

    def set_secret(self, path: str, data: dict):
        """Write secret to KV v2 engine."""
        self.client.secrets.kv.v2.create_or_update_secret(
            path=path, secret=data, mount_point=self.mount_point,
        )
        self._cache.pop(path, None)

    def get_field(self, path: str, field: str) -> str:
        """Get single field from a secret."""
        data = self.get_secret(path)
        if field not in data:
            raise KeyError(f"Field '{field}' not found in secret '{path}'")
        return data[field]


# --- Dynamic database credentials ---

class DynamicCredentials:
    """Get short-lived database credentials from Vault."""

    def __init__(self, client: hvac.Client):
        self.client = client

    @contextmanager
    def database_creds(self, role: str = "myapp-readonly"):
        """Get temporary database credentials, auto-revoke on exit."""
        response = self.client.secrets.database.generate_credentials(
            name=role,
        )
        creds = response["data"]
        lease_id = response["lease_id"]

        logger.info(
            "Got dynamic DB creds (lease: %s, ttl: %ss)",
            lease_id, response["lease_duration"],
        )

        try:
            yield {
                "username": creds["username"],
                "password": creds["password"],
            }
        finally:
            # Revoke credentials when done
            self.client.sys.revoke_lease(lease_id)
            logger.info("Revoked lease: %s", lease_id)


# Usage:
# with dynamic.database_creds("myapp-readwrite") as creds:
#     conn = psycopg2.connect(
#         host="db.example.com",
#         user=creds["username"],
#         password=creds["password"],
#     )
#     # ... use connection ...
# # Credentials auto-revoked here


# --- Transit encryption (Vault encrypts, app never sees key) ---

class TransitEncryption:
    """Encrypt/decrypt using Vault's Transit engine."""

    def __init__(self, client: hvac.Client, key_name: str = "myapp"):
        self.client = client
        self.key_name = key_name

    def encrypt(self, plaintext: str) -> str:
        """Encrypt data — app never handles encryption key."""
        import base64
        encoded = base64.b64encode(plaintext.encode()).decode()
        response = self.client.secrets.transit.encrypt_data(
            name=self.key_name, plaintext=encoded,
        )
        return response["data"]["ciphertext"]  # "vault:v1:..."

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt data."""
        import base64
        response = self.client.secrets.transit.decrypt_data(
            name=self.key_name, ciphertext=ciphertext,
        )
        return base64.b64decode(response["data"]["plaintext"]).decode()

    def rotate_key(self):
        """Rotate encryption key — old ciphertext still decryptable."""
        self.client.secrets.transit.rotate_encryption_key(
            name=self.key_name,
        )

    def rewrap(self, ciphertext: str) -> str:
        """Re-encrypt with latest key version (no plaintext exposure)."""
        response = self.client.secrets.transit.rewrap_data(
            name=self.key_name, ciphertext=ciphertext,
        )
        return response["data"]["ciphertext"]
```

Vault patterns:
1. **AppRole auth** — role_id + secret_id for service authentication
2. **KV v2 engine** — versioned static secrets with metadata
3. **Dynamic credentials** — short-lived DB creds, auto-revoked after use
4. **Transit encryption** — Vault holds keys, app sends data to encrypt/decrypt
5. **Key rotation** — rotate keys without re-encrypting; `rewrap` updates ciphertext'''
    ),
]
