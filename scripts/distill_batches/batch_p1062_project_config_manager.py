PAIRS = [
    ("projects/config-manager", r'''<think>
A config manager needs to load from multiple sources (env vars, files, defaults)
and merge them in a predictable order. I should support YAML and TOML formats,
with environment variable overrides and validation.
</think>
Build a config manager that loads from env vars, YAML/TOML files, and defaults with hierarchical merging.''', r'''import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Type
from copy import deepcopy


class ConfigSource:
    """Base class for configuration sources."""
    def load(self) -> dict:
        raise NotImplementedError


class EnvVarSource(ConfigSource):
    """Loads config from environment variables with prefix."""
    def __init__(self, prefix: str = "APP_", separator: str = "__"):
        self._prefix = prefix
        self._separator = separator

    def load(self) -> dict:
        result = {}
        for key, value in os.environ.items():
            if not key.startswith(self._prefix):
                continue
            config_key = key[len(self._prefix):].lower()
            parts = config_key.split(self._separator.lower())
            self._set_nested(result, parts, self._parse_value(value))
        return result

    def _set_nested(self, d: dict, keys: List[str], value: Any) -> None:
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value

    def _parse_value(self, value: str) -> Any:
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value


class YAMLSource(ConfigSource):
    """Loads config from a YAML file."""
    def __init__(self, filepath: str, required: bool = True):
        self._filepath = Path(filepath)
        self._required = required

    def load(self) -> dict:
        if not self._filepath.exists():
            if self._required:
                raise FileNotFoundError(f"Config file not found: {self._filepath}")
            return {}
        try:
            import yaml
            with open(self._filepath) as f:
                data = yaml.safe_load(f)
            return data or {}
        except ImportError:
            raise ImportError("PyYAML is required: pip install pyyaml")


class TOMLSource(ConfigSource):
    """Loads config from a TOML file."""
    def __init__(self, filepath: str, required: bool = True):
        self._filepath = Path(filepath)
        self._required = required

    def load(self) -> dict:
        if not self._filepath.exists():
            if self._required:
                raise FileNotFoundError(f"Config file not found: {self._filepath}")
            return {}
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        with open(self._filepath, "rb") as f:
            return tomllib.load(f)


class JSONSource(ConfigSource):
    """Loads config from a JSON file."""
    def __init__(self, filepath: str, required: bool = True):
        self._filepath = Path(filepath)
        self._required = required

    def load(self) -> dict:
        if not self._filepath.exists():
            if self._required:
                raise FileNotFoundError(f"Config file not found: {self._filepath}")
            return {}
        with open(self._filepath) as f:
            return json.load(f)


class DictSource(ConfigSource):
    """Loads config from a plain dictionary (for defaults)."""
    def __init__(self, data: dict):
        self._data = data

    def load(self) -> dict:
        return deepcopy(self._data)


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries. Override values take precedence."""
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class ConfigManager:
    """Manages configuration from multiple sources with hierarchical merging."""

    def __init__(self):
        self._sources: List[ConfigSource] = []
        self._config: dict = {}
        self._frozen = False

    def add_source(self, source: ConfigSource) -> "ConfigManager":
        """Add a configuration source (later sources override earlier ones)."""
        self._sources.append(source)
        return self

    def load(self) -> dict:
        """Load and merge all configuration sources."""
        merged = {}
        for source in self._sources:
            data = source.load()
            merged = deep_merge(merged, data)
        self._config = merged
        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value using dot-notation (e.g., 'database.host')."""
        parts = key.split(".")
        value = self._config
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """Set a config value using dot-notation."""
        if self._frozen:
            raise RuntimeError("Configuration is frozen")
        parts = key.split(".")
        d = self._config
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value

    def freeze(self) -> None:
        """Prevent further modifications."""
        self._frozen = True

    def to_dict(self) -> dict:
        return deepcopy(self._config)

    def __getitem__(self, key: str) -> Any:
        value = self.get(key)
        if value is None:
            raise KeyError(f"Config key not found: {key}")
        return value


# Usage:
# config = ConfigManager()
# config.add_source(DictSource({"database": {"host": "localhost", "port": 5432}}))
# config.add_source(YAMLSource("config.yaml", required=False))
# config.add_source(EnvVarSource(prefix="MYAPP_"))
# config.load()
# db_host = config.get("database.host")
'''),
    ("projects/config-manager", r'''Implement configuration validation with type checking, required fields, and custom validators.''', r'''from typing import Any, Callable, Dict, List, Optional, Set, Type, Union


class ValidationError:
    """A single validation error."""
    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class ConfigSchema:
    """Defines the expected structure and types for configuration."""

    def __init__(self):
        self._fields: Dict[str, dict] = {}
        self._validators: List[Callable] = []

    def field(
        self,
        path: str,
        field_type: Type = str,
        required: bool = False,
        default: Any = None,
        choices: Optional[list] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        pattern: Optional[str] = None,
        description: str = "",
        validator: Optional[Callable] = None,
    ) -> "ConfigSchema":
        """Define a configuration field."""
        self._fields[path] = {
            "type": field_type,
            "required": required,
            "default": default,
            "choices": choices,
            "min_value": min_value,
            "max_value": max_value,
            "pattern": pattern,
            "description": description,
            "validator": validator,
        }
        return self

    def add_validator(self, validator: Callable) -> "ConfigSchema":
        """Add a cross-field validator."""
        self._validators.append(validator)
        return self

    def validate(self, config: dict) -> List[ValidationError]:
        """Validate a configuration dictionary against this schema."""
        errors = []

        for path, field_def in self._fields.items():
            value = self._get_value(config, path)

            # Check required
            if value is None:
                if field_def["required"]:
                    errors.append(ValidationError(path, "Required field is missing"))
                continue

            # Check type
            expected_type = field_def["type"]
            if expected_type is not None and not isinstance(value, expected_type):
                errors.append(ValidationError(
                    path,
                    f"Expected type {expected_type.__name__}, got {type(value).__name__}"
                ))
                continue

            # Check choices
            if field_def["choices"] is not None and value not in field_def["choices"]:
                errors.append(ValidationError(
                    path,
                    f"Value must be one of {field_def['choices']}, got {value}"
                ))

            # Check numeric bounds
            if field_def["min_value"] is not None and isinstance(value, (int, float)):
                if value < field_def["min_value"]:
                    errors.append(ValidationError(
                        path, f"Value {value} is below minimum {field_def['min_value']}"
                    ))

            if field_def["max_value"] is not None and isinstance(value, (int, float)):
                if value > field_def["max_value"]:
                    errors.append(ValidationError(
                        path, f"Value {value} exceeds maximum {field_def['max_value']}"
                    ))

            # Check pattern
            if field_def["pattern"] is not None and isinstance(value, str):
                import re
                if not re.match(field_def["pattern"], value):
                    errors.append(ValidationError(
                        path, f"Value does not match pattern {field_def['pattern']}"
                    ))

            # Custom field validator
            if field_def["validator"]:
                try:
                    result = field_def["validator"](value)
                    if result is False:
                        errors.append(ValidationError(path, "Custom validation failed"))
                    elif isinstance(result, str):
                        errors.append(ValidationError(path, result))
                except Exception as e:
                    errors.append(ValidationError(path, f"Validator error: {e}"))

        # Run cross-field validators
        for validator in self._validators:
            try:
                result = validator(config)
                if isinstance(result, list):
                    errors.extend(result)
                elif isinstance(result, str):
                    errors.append(ValidationError("", result))
            except Exception as e:
                errors.append(ValidationError("", f"Cross-field validator error: {e}"))

        return errors

    def apply_defaults(self, config: dict) -> dict:
        """Apply default values for missing fields."""
        from copy import deepcopy
        result = deepcopy(config)
        for path, field_def in self._fields.items():
            if field_def["default"] is not None:
                value = self._get_value(result, path)
                if value is None:
                    self._set_value(result, path, field_def["default"])
        return result

    def _get_value(self, config: dict, path: str) -> Any:
        parts = path.split(".")
        value = config
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value

    def _set_value(self, config: dict, path: str, value: Any) -> None:
        parts = path.split(".")
        d = config
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value

    def get_documentation(self) -> List[dict]:
        """Generate documentation for all config fields."""
        docs = []
        for path, field_def in self._fields.items():
            docs.append({
                "path": path,
                "type": field_def["type"].__name__ if field_def["type"] else "any",
                "required": field_def["required"],
                "default": field_def["default"],
                "choices": field_def["choices"],
                "description": field_def["description"],
            })
        return docs
'''),
    ("projects/config-manager", r'''Implement secrets management with encrypted storage and environment-based secret injection.''', r'''import base64
import hashlib
import json
import os
import secrets as secrets_module
from pathlib import Path
from typing import Any, Dict, Optional


class SecretValue:
    """Wraps a secret value to prevent accidental logging/printing."""

    def __init__(self, value: str):
        self._value = value

    def get(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "SecretValue(***)"

    def __str__(self) -> str:
        return "***"

    def __eq__(self, other) -> bool:
        if isinstance(other, SecretValue):
            return secrets_module.compare_digest(self._value, other._value)
        return False


class SimpleEncryptor:
    """Simple XOR-based encryption for local secret storage.

    NOTE: For production use, replace with a proper encryption library
    like cryptography.fernet or use a secrets manager service.
    """

    def __init__(self, key: str):
        self._key = hashlib.sha256(key.encode()).digest()

    def encrypt(self, plaintext: str) -> str:
        data = plaintext.encode("utf-8")
        key_stream = self._key * ((len(data) // len(self._key)) + 1)
        encrypted = bytes(a ^ b for a, b in zip(data, key_stream))
        return base64.b64encode(encrypted).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        encrypted = base64.b64decode(ciphertext)
        key_stream = self._key * ((len(encrypted) // len(self._key)) + 1)
        decrypted = bytes(a ^ b for a, b in zip(encrypted, key_stream))
        return decrypted.decode("utf-8")


class SecretsManager:
    """Manages application secrets with encrypted file storage."""

    def __init__(
        self,
        secrets_file: str = ".secrets.enc",
        master_key: Optional[str] = None,
    ):
        self._filepath = Path(secrets_file)
        self._master_key = master_key or os.environ.get("APP_MASTER_KEY", "")
        if not self._master_key:
            self._master_key = secrets_module.token_hex(32)

        self._encryptor = SimpleEncryptor(self._master_key)
        self._secrets: Dict[str, str] = {}
        self._env_prefix = "SECRET_"

    def load(self) -> None:
        """Load secrets from encrypted file and environment variables."""
        # Load from encrypted file
        if self._filepath.exists():
            with open(self._filepath, "r") as f:
                encrypted_data = f.read().strip()
            try:
                decrypted = self._encryptor.decrypt(encrypted_data)
                self._secrets = json.loads(decrypted)
            except Exception as e:
                raise ValueError(f"Failed to decrypt secrets file: {e}")

        # Override with environment variables
        for key, value in os.environ.items():
            if key.startswith(self._env_prefix):
                secret_name = key[len(self._env_prefix):].lower()
                self._secrets[secret_name] = value

    def save(self) -> None:
        """Save secrets to encrypted file."""
        plaintext = json.dumps(self._secrets)
        encrypted = self._encryptor.encrypt(plaintext)
        with open(self._filepath, "w") as f:
            f.write(encrypted)
        # Set restrictive permissions
        os.chmod(self._filepath, 0o600)

    def get(self, name: str) -> Optional[SecretValue]:
        """Get a secret by name."""
        value = self._secrets.get(name)
        if value is None:
            return None
        return SecretValue(value)

    def set(self, name: str, value: str) -> None:
        """Set a secret."""
        self._secrets[name] = value

    def delete(self, name: str) -> bool:
        """Delete a secret."""
        return self._secrets.pop(name, None) is not None

    def list_names(self) -> list:
        """List all secret names (not values)."""
        return sorted(self._secrets.keys())

    def has(self, name: str) -> bool:
        return name in self._secrets

    def inject_into_config(self, config: dict, mappings: Dict[str, str]) -> dict:
        """Inject secrets into a config dict based on mappings.

        Args:
            config: The configuration dictionary
            mappings: Maps config paths to secret names
                      e.g., {"database.password": "db_password"}
        """
        from copy import deepcopy
        result = deepcopy(config)

        for config_path, secret_name in mappings.items():
            secret = self.get(secret_name)
            if secret is None:
                continue

            parts = config_path.split(".")
            d = result
            for part in parts[:-1]:
                d = d.setdefault(part, {})
            d[parts[-1]] = secret.get()

        return result

    def rotate(self, name: str, new_value: str) -> Optional[str]:
        """Rotate a secret, returning the old value."""
        old_value = self._secrets.get(name)
        self._secrets[name] = new_value
        self.save()
        return old_value

    def generate(self, name: str, length: int = 32) -> SecretValue:
        """Generate and store a random secret."""
        value = secrets_module.token_urlsafe(length)
        self._secrets[name] = value
        return SecretValue(value)
'''),
    ("projects/config-manager", r'''Implement hierarchical configuration with environment-specific overrides and feature flags.''', r'''import os
from typing import Any, Callable, Dict, List, Optional
from copy import deepcopy


class Environment:
    """Standard environment names."""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class HierarchicalConfig:
    """Configuration with environment-specific overrides.

    Supports a base config with per-environment overrides layered on top.
    """

    def __init__(self, base_config: dict):
        self._base = deepcopy(base_config)
        self._env_overrides: Dict[str, dict] = {}
        self._current_env: str = os.environ.get("APP_ENV", Environment.DEVELOPMENT)

    def set_environment(self, env: str) -> None:
        self._current_env = env

    def add_environment_override(self, env: str, overrides: dict) -> None:
        """Add configuration overrides for a specific environment."""
        self._env_overrides[env] = deepcopy(overrides)

    def get_config(self, env: Optional[str] = None) -> dict:
        """Get the merged config for an environment."""
        target_env = env or self._current_env
        result = deepcopy(self._base)

        overrides = self._env_overrides.get(target_env, {})
        return self._deep_merge(result, overrides)

    def get(self, key: str, default: Any = None, env: Optional[str] = None) -> Any:
        config = self.get_config(env)
        parts = key.split(".")
        value = config
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    def _deep_merge(self, base: dict, override: dict) -> dict:
        result = deepcopy(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result


class FeatureFlags:
    """Simple feature flag system backed by configuration."""

    def __init__(self):
        self._flags: Dict[str, dict] = {}
        self._overrides: Dict[str, bool] = {}

    def define(
        self,
        name: str,
        default: bool = False,
        description: str = "",
        environments: Optional[Dict[str, bool]] = None,
        rollout_percentage: float = 100.0,
    ) -> None:
        """Define a feature flag."""
        self._flags[name] = {
            "default": default,
            "description": description,
            "environments": environments or {},
            "rollout_percentage": rollout_percentage,
        }

    def is_enabled(
        self,
        name: str,
        environment: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        """Check if a feature flag is enabled."""
        # Check overrides first
        if name in self._overrides:
            return self._overrides[name]

        flag = self._flags.get(name)
        if flag is None:
            return False

        # Check environment-specific setting
        env = environment or os.environ.get("APP_ENV", "development")
        if env in flag["environments"]:
            return flag["environments"][env]

        # Check rollout percentage
        if user_id and flag["rollout_percentage"] < 100.0:
            import hashlib
            hash_val = int(hashlib.md5(f"{name}:{user_id}".encode()).hexdigest(), 16)
            bucket = hash_val % 100
            return bucket < flag["rollout_percentage"]

        return flag["default"]

    def override(self, name: str, enabled: bool) -> None:
        """Set a temporary override for a flag."""
        self._overrides[name] = enabled

    def clear_override(self, name: str) -> None:
        """Remove a flag override."""
        self._overrides.pop(name, None)

    def list_flags(self) -> List[dict]:
        """List all defined feature flags."""
        return [
            {
                "name": name,
                "default": info["default"],
                "description": info["description"],
                "rollout_percentage": info["rollout_percentage"],
                "overridden": name in self._overrides,
            }
            for name, info in self._flags.items()
        ]

    def load_from_config(self, config: dict) -> None:
        """Load feature flags from a configuration dictionary."""
        flags = config.get("feature_flags", {})
        for name, settings in flags.items():
            self.define(
                name=name,
                default=settings.get("enabled", False),
                description=settings.get("description", ""),
                environments=settings.get("environments", {}),
                rollout_percentage=settings.get("rollout_percentage", 100.0),
            )


# Usage:
# config = HierarchicalConfig({
#     "database": {"host": "localhost", "port": 5432},
#     "logging": {"level": "INFO"},
# })
# config.add_environment_override("production", {
#     "database": {"host": "db.prod.internal"},
#     "logging": {"level": "WARNING"},
# })
# config.set_environment("production")
# db_host = config.get("database.host")  # -> "db.prod.internal"
'''),
    ("projects/config-manager", r'''<think>
Configuration hot-reloading is useful for production systems where
you want to change settings without restarting. I need a file watcher
that detects changes and notifies registered callbacks.
</think>
Implement configuration hot-reload with file watching and change notification.''', r'''import json
import os
import threading
import time
import logging
import hashlib
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """Watches configuration files for changes and triggers reloads."""

    def __init__(self, poll_interval: float = 2.0):
        self._poll_interval = poll_interval
        self._watched_files: Dict[str, str] = {}  # filepath -> content hash
        self._callbacks: List[Callable] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def watch(self, filepath: str) -> None:
        """Add a file to watch."""
        path = Path(filepath)
        if path.exists():
            self._watched_files[str(path)] = self._hash_file(str(path))

    def on_change(self, callback: Callable) -> None:
        """Register a callback for config changes."""
        self._callbacks.append(callback)

    def start(self) -> None:
        """Start watching in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info("Config watcher started")

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def _hash_file(self, filepath: str) -> str:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def _watch_loop(self) -> None:
        while self._running:
            for filepath, old_hash in list(self._watched_files.items()):
                if not os.path.exists(filepath):
                    continue
                new_hash = self._hash_file(filepath)
                if new_hash != old_hash:
                    self._watched_files[filepath] = new_hash
                    logger.info(f"Config file changed: {filepath}")
                    self._notify_callbacks(filepath)
            time.sleep(self._poll_interval)

    def _notify_callbacks(self, filepath: str) -> None:
        for callback in self._callbacks:
            try:
                callback(filepath)
            except Exception as e:
                logger.error(f"Config change callback error: {e}")


class ReloadableConfig:
    """Configuration that automatically reloads when files change."""

    def __init__(self, config_manager):
        self._manager = config_manager
        self._watcher = ConfigWatcher()
        self._change_listeners: List[Callable] = []
        self._previous_config: dict = {}
        self._lock = threading.Lock()

    def enable_reload(self, filepaths: List[str]) -> None:
        """Enable auto-reload for the given config files."""
        for filepath in filepaths:
            self._watcher.watch(filepath)

        self._watcher.on_change(self._handle_file_change)
        self._previous_config = self._manager.to_dict()
        self._watcher.start()

    def disable_reload(self) -> None:
        """Disable auto-reload."""
        self._watcher.stop()

    def on_change(self, callback: Callable) -> None:
        """Register a listener for config changes.

        Callback receives (changed_keys, old_config, new_config).
        """
        self._change_listeners.append(callback)

    def _handle_file_change(self, filepath: str) -> None:
        """Handle a config file change."""
        with self._lock:
            old_config = self._previous_config

            try:
                new_config = self._manager.load()
            except Exception as e:
                logger.error(f"Failed to reload config: {e}")
                return

            # Detect what changed
            changed_keys = self._diff_configs(old_config, new_config)
            if not changed_keys:
                return

            self._previous_config = new_config
            logger.info(f"Config reloaded. Changed keys: {changed_keys}")

            # Notify listeners
            for listener in self._change_listeners:
                try:
                    listener(changed_keys, old_config, new_config)
                except Exception as e:
                    logger.error(f"Config change listener error: {e}")

    def _diff_configs(self, old: dict, new: dict, prefix: str = "") -> List[str]:
        """Find keys that differ between two configs."""
        changed = []
        all_keys = set(list(old.keys()) + list(new.keys()))

        for key in all_keys:
            full_key = f"{prefix}.{key}" if prefix else key
            old_val = old.get(key)
            new_val = new.get(key)

            if old_val != new_val:
                if isinstance(old_val, dict) and isinstance(new_val, dict):
                    changed.extend(self._diff_configs(old_val, new_val, full_key))
                else:
                    changed.append(full_key)

        return changed

    def get(self, key: str, default: Any = None) -> Any:
        """Thread-safe config access."""
        with self._lock:
            return self._manager.get(key, default)


class ConfigTemplate:
    """Generates config file templates from schema definitions."""

    @staticmethod
    def generate_yaml(schema, include_descriptions: bool = True) -> str:
        """Generate a YAML template from a config schema."""
        lines = ["# Application Configuration", ""]
        docs = schema.get_documentation()

        current_sections = []
        for doc in docs:
            parts = doc["path"].split(".")
            # Handle section headers
            for i, part in enumerate(parts[:-1]):
                if i >= len(current_sections) or current_sections[i] != part:
                    indent = "  " * i
                    lines.append(f"{indent}{part}:")
                    current_sections = parts[:i + 1]

            # Write field
            indent = "  " * (len(parts) - 1)
            field_name = parts[-1]

            if include_descriptions and doc["description"]:
                lines.append(f"{indent}# {doc['description']}")

            default = doc["default"]
            required = doc["required"]

            if default is not None:
                lines.append(f"{indent}{field_name}: {default}")
            elif required:
                lines.append(f"{indent}{field_name}:  # REQUIRED")
            else:
                lines.append(f"{indent}# {field_name}:")

        return "\n".join(lines) + "\n"

    @staticmethod
    def generate_env(schema, prefix: str = "APP_") -> str:
        """Generate a .env template from a config schema."""
        lines = ["# Environment Variables", ""]
        docs = schema.get_documentation()

        for doc in docs:
            env_key = prefix + doc["path"].replace(".", "__").upper()
            if doc["description"]:
                lines.append(f"# {doc['description']}")
            if doc["default"] is not None:
                lines.append(f"# {env_key}={doc['default']}")
            elif doc["required"]:
                lines.append(f"{env_key}=  # REQUIRED")
            else:
                lines.append(f"# {env_key}=")
            lines.append("")

        return "\n".join(lines)
'''),
]
