PAIRS = [
    ("projects/plugin-system", r'''Build a plugin system with automatic plugin discovery from a directory, metadata parsing, and lifecycle management.''', r'''import importlib
import importlib.util
import inspect
import logging
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


@dataclass
class PluginMetadata:
    """Metadata describing a plugin."""
    name: str
    version: str
    author: str = ""
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    min_host_version: Optional[str] = None
    tags: List[str] = field(default_factory=list)


class PluginBase(ABC):
    """Abstract base class for all plugins."""

    metadata: PluginMetadata

    @abstractmethod
    def activate(self) -> None:
        """Called when the plugin is activated."""
        pass

    @abstractmethod
    def deactivate(self) -> None:
        """Called when the plugin is deactivated."""
        pass

    def on_config_change(self, config: dict) -> None:
        """Called when configuration changes."""
        pass


class PluginState:
    DISCOVERED = "discovered"
    LOADED = "loaded"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ERROR = "error"


@dataclass
class PluginEntry:
    """Internal record of a discovered plugin."""
    metadata: PluginMetadata
    module_path: str
    plugin_class: Optional[Type[PluginBase]] = None
    instance: Optional[PluginBase] = None
    state: str = PluginState.DISCOVERED
    error: Optional[str] = None


class PluginDiscovery:
    """Discovers plugins from a directory structure."""

    def __init__(self, plugin_dirs: Optional[List[str]] = None):
        self._dirs = [Path(d) for d in (plugin_dirs or ["plugins"])]

    def discover(self) -> List[PluginEntry]:
        """Scan plugin directories and return discovered plugins."""
        entries = []
        for plugin_dir in self._dirs:
            if not plugin_dir.exists():
                logger.warning(f"Plugin directory not found: {plugin_dir}")
                continue

            for item in plugin_dir.iterdir():
                if item.is_dir() and (item / "__init__.py").exists():
                    entry = self._load_plugin_package(item)
                    if entry:
                        entries.append(entry)
                elif item.is_file() and item.suffix == ".py" and item.stem != "__init__":
                    entry = self._load_plugin_module(item)
                    if entry:
                        entries.append(entry)

        return entries

    def _load_plugin_module(self, filepath: Path) -> Optional[PluginEntry]:
        """Load a single plugin module."""
        try:
            module_name = f"plugins.{filepath.stem}"
            spec = importlib.util.spec_from_file_location(module_name, str(filepath))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find plugin class
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, PluginBase) and obj is not PluginBase:
                    metadata = getattr(obj, "metadata", None)
                    if not metadata:
                        metadata = PluginMetadata(name=filepath.stem, version="0.0.0")
                    return PluginEntry(
                        metadata=metadata,
                        module_path=str(filepath),
                        plugin_class=obj,
                        state=PluginState.LOADED,
                    )

        except Exception as e:
            logger.error(f"Failed to load plugin from {filepath}: {e}")
            return PluginEntry(
                metadata=PluginMetadata(name=filepath.stem, version="0.0.0"),
                module_path=str(filepath),
                state=PluginState.ERROR,
                error=str(e),
            )

        return None

    def _load_plugin_package(self, dirpath: Path) -> Optional[PluginEntry]:
        """Load a plugin from a package directory."""
        init_file = dirpath / "__init__.py"
        return self._load_plugin_module(init_file)


class PluginManager:
    """Manages the complete plugin lifecycle."""

    def __init__(self, plugin_dirs: Optional[List[str]] = None):
        self._discovery = PluginDiscovery(plugin_dirs)
        self._plugins: Dict[str, PluginEntry] = {}
        self._hooks: Dict[str, List[Callable]] = {}

    def discover_plugins(self) -> List[str]:
        """Discover all available plugins."""
        entries = self._discovery.discover()
        names = []
        for entry in entries:
            self._plugins[entry.metadata.name] = entry
            names.append(entry.metadata.name)
            logger.info(f"Discovered plugin: {entry.metadata.name} v{entry.metadata.version}")
        return names

    def activate_plugin(self, name: str) -> bool:
        """Activate a plugin by name."""
        entry = self._plugins.get(name)
        if not entry or not entry.plugin_class:
            logger.error(f"Plugin '{name}' not found or not loaded")
            return False

        # Check dependencies
        for dep in entry.metadata.dependencies:
            dep_entry = self._plugins.get(dep)
            if not dep_entry or dep_entry.state != PluginState.ACTIVATED:
                logger.error(f"Plugin '{name}' requires '{dep}' to be activated first")
                return False

        try:
            entry.instance = entry.plugin_class()
            entry.instance.activate()
            entry.state = PluginState.ACTIVATED
            logger.info(f"Activated plugin: {name}")
            return True
        except Exception as e:
            entry.state = PluginState.ERROR
            entry.error = str(e)
            logger.error(f"Failed to activate plugin '{name}': {e}")
            return False

    def deactivate_plugin(self, name: str) -> bool:
        """Deactivate a plugin."""
        entry = self._plugins.get(name)
        if not entry or entry.state != PluginState.ACTIVATED:
            return False

        # Check if other plugins depend on this one
        dependents = [
            n for n, e in self._plugins.items()
            if e.state == PluginState.ACTIVATED and name in e.metadata.dependencies
        ]
        if dependents:
            logger.error(f"Cannot deactivate '{name}': required by {dependents}")
            return False

        try:
            entry.instance.deactivate()
            entry.instance = None
            entry.state = PluginState.DEACTIVATED
            logger.info(f"Deactivated plugin: {name}")
            return True
        except Exception as e:
            logger.error(f"Error deactivating '{name}': {e}")
            return False

    def get_plugin(self, name: str) -> Optional[PluginBase]:
        entry = self._plugins.get(name)
        return entry.instance if entry else None

    def list_plugins(self) -> List[dict]:
        return [
            {
                "name": e.metadata.name,
                "version": e.metadata.version,
                "state": e.state,
                "description": e.metadata.description,
            }
            for e in self._plugins.values()
        ]

    def activate_all(self) -> None:
        """Activate all discovered plugins in dependency order."""
        activated = set()
        remaining = set(self._plugins.keys())

        while remaining:
            progress = False
            for name in list(remaining):
                entry = self._plugins[name]
                deps = set(entry.metadata.dependencies)
                if deps.issubset(activated):
                    if self.activate_plugin(name):
                        activated.add(name)
                    remaining.discard(name)
                    progress = True

            if not progress:
                logger.error(f"Cannot resolve dependencies for: {remaining}")
                break
'''),
    ("projects/plugin-system", r'''<think>
Lifecycle hooks allow plugins to respond to application events.
I need an event-based hook system where plugins can register
callbacks for specific lifecycle events. Should support priority ordering.
</think>
Implement lifecycle hooks for the plugin system with priority ordering and async support.''', r'''import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)


class HookPriority:
    HIGHEST = 0
    HIGH = 25
    NORMAL = 50
    LOW = 75
    LOWEST = 100


@dataclass
class HookRegistration:
    """A registered hook callback."""
    name: str
    callback: Callable
    plugin_name: str
    priority: int = HookPriority.NORMAL
    is_async: bool = False


class HookManager:
    """Manages lifecycle hooks with priority ordering."""

    def __init__(self):
        self._hooks: Dict[str, List[HookRegistration]] = {}
        self._disabled_hooks: Set[str] = set()

    def register(
        self,
        hook_name: str,
        callback: Callable,
        plugin_name: str,
        priority: int = HookPriority.NORMAL,
    ) -> None:
        """Register a callback for a hook."""
        is_async = asyncio.iscoroutinefunction(callback)
        reg = HookRegistration(
            name=hook_name,
            callback=callback,
            plugin_name=plugin_name,
            priority=priority,
            is_async=is_async,
        )

        if hook_name not in self._hooks:
            self._hooks[hook_name] = []

        self._hooks[hook_name].append(reg)
        # Sort by priority (lower number = higher priority)
        self._hooks[hook_name].sort(key=lambda r: r.priority)

        logger.debug(f"Registered hook '{hook_name}' for plugin '{plugin_name}'")

    def unregister(self, hook_name: str, plugin_name: str) -> None:
        """Remove all hooks for a plugin on a specific hook name."""
        if hook_name in self._hooks:
            self._hooks[hook_name] = [
                r for r in self._hooks[hook_name]
                if r.plugin_name != plugin_name
            ]

    def unregister_plugin(self, plugin_name: str) -> None:
        """Remove all hooks registered by a plugin."""
        for hook_name in list(self._hooks.keys()):
            self._hooks[hook_name] = [
                r for r in self._hooks[hook_name]
                if r.plugin_name != plugin_name
            ]

    def fire(self, hook_name: str, **kwargs) -> List[Any]:
        """Fire a synchronous hook and collect results."""
        if hook_name in self._disabled_hooks:
            return []

        registrations = self._hooks.get(hook_name, [])
        results = []

        for reg in registrations:
            try:
                if reg.is_async:
                    logger.warning(f"Skipping async hook '{reg.name}' in sync context")
                    continue
                result = reg.callback(**kwargs)
                results.append(result)
            except Exception as e:
                logger.error(
                    f"Hook '{hook_name}' from plugin '{reg.plugin_name}' failed: {e}"
                )

        return results

    async def fire_async(self, hook_name: str, **kwargs) -> List[Any]:
        """Fire a hook asynchronously, supporting both sync and async callbacks."""
        if hook_name in self._disabled_hooks:
            return []

        registrations = self._hooks.get(hook_name, [])
        results = []

        for reg in registrations:
            try:
                if reg.is_async:
                    result = await reg.callback(**kwargs)
                else:
                    result = reg.callback(**kwargs)
                results.append(result)
            except Exception as e:
                logger.error(
                    f"Hook '{hook_name}' from plugin '{reg.plugin_name}' failed: {e}"
                )

        return results

    def fire_filter(self, hook_name: str, value: Any, **kwargs) -> Any:
        """Fire a filter hook that transforms a value through a chain."""
        registrations = self._hooks.get(hook_name, [])

        for reg in registrations:
            try:
                value = reg.callback(value, **kwargs)
            except Exception as e:
                logger.error(f"Filter hook '{hook_name}' from '{reg.plugin_name}' failed: {e}")

        return value

    def disable_hook(self, hook_name: str) -> None:
        self._disabled_hooks.add(hook_name)

    def enable_hook(self, hook_name: str) -> None:
        self._disabled_hooks.discard(hook_name)

    def get_registered_hooks(self) -> Dict[str, List[dict]]:
        """Get information about all registered hooks."""
        return {
            name: [
                {
                    "plugin": r.plugin_name,
                    "priority": r.priority,
                    "is_async": r.is_async,
                }
                for r in regs
            ]
            for name, regs in self._hooks.items()
        }


# Standard lifecycle hooks
class LifecycleHooks:
    """Standard hook names for the plugin lifecycle."""
    APP_STARTUP = "app:startup"
    APP_SHUTDOWN = "app:shutdown"
    PLUGIN_LOADED = "plugin:loaded"
    PLUGIN_ACTIVATED = "plugin:activated"
    PLUGIN_DEACTIVATED = "plugin:deactivated"
    CONFIG_CHANGED = "config:changed"
    REQUEST_BEFORE = "request:before"
    REQUEST_AFTER = "request:after"
    ERROR_OCCURRED = "error:occurred"


def hook(hook_name: str, priority: int = HookPriority.NORMAL):
    """Decorator to mark a method as a hook handler."""
    def decorator(func: Callable) -> Callable:
        func._hook_name = hook_name
        func._hook_priority = priority
        return func
    return decorator


def auto_register_hooks(plugin_instance, hook_manager: HookManager, plugin_name: str) -> None:
    """Automatically register decorated hook methods from a plugin instance."""
    for name in dir(plugin_instance):
        method = getattr(plugin_instance, name, None)
        if callable(method) and hasattr(method, "_hook_name"):
            hook_manager.register(
                hook_name=method._hook_name,
                callback=method,
                plugin_name=plugin_name,
                priority=getattr(method, "_hook_priority", HookPriority.NORMAL),
            )
'''),
    ("projects/plugin-system", r'''Implement dependency injection for the plugin system with a service container and automatic wiring.''', r'''import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, get_type_hints

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ServiceLifetime:
    SINGLETON = "singleton"
    TRANSIENT = "transient"
    SCOPED = "scoped"


class ServiceDescriptor:
    """Describes a service registration."""

    def __init__(
        self,
        service_type: Type,
        implementation: Any = None,
        factory: Optional[Callable] = None,
        lifetime: str = ServiceLifetime.SINGLETON,
    ):
        self.service_type = service_type
        self.implementation = implementation
        self.factory = factory
        self.lifetime = lifetime


class ServiceContainer:
    """Dependency injection container with automatic wiring."""

    def __init__(self):
        self._descriptors: Dict[Type, ServiceDescriptor] = {}
        self._singletons: Dict[Type, Any] = {}
        self._scoped_instances: Dict[Type, Any] = {}

    def register_singleton(self, service_type: Type, implementation: Any = None) -> None:
        """Register a singleton service."""
        self._descriptors[service_type] = ServiceDescriptor(
            service_type=service_type,
            implementation=implementation or service_type,
            lifetime=ServiceLifetime.SINGLETON,
        )

    def register_transient(self, service_type: Type, implementation: Any = None) -> None:
        """Register a transient service (new instance each time)."""
        self._descriptors[service_type] = ServiceDescriptor(
            service_type=service_type,
            implementation=implementation or service_type,
            lifetime=ServiceLifetime.TRANSIENT,
        )

    def register_factory(self, service_type: Type, factory: Callable, lifetime: str = ServiceLifetime.SINGLETON) -> None:
        """Register a service with a factory function."""
        self._descriptors[service_type] = ServiceDescriptor(
            service_type=service_type,
            factory=factory,
            lifetime=lifetime,
        )

    def register_instance(self, service_type: Type, instance: Any) -> None:
        """Register an existing instance as a singleton."""
        self._descriptors[service_type] = ServiceDescriptor(
            service_type=service_type,
            lifetime=ServiceLifetime.SINGLETON,
        )
        self._singletons[service_type] = instance

    def resolve(self, service_type: Type) -> Any:
        """Resolve a service, creating it if necessary."""
        # Check for cached singleton
        if service_type in self._singletons:
            return self._singletons[service_type]

        descriptor = self._descriptors.get(service_type)
        if not descriptor:
            raise KeyError(f"Service '{service_type.__name__}' is not registered")

        instance = self._create_instance(descriptor)

        if descriptor.lifetime == ServiceLifetime.SINGLETON:
            self._singletons[service_type] = instance

        return instance

    def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
        """Create an instance of a service, resolving its dependencies."""
        if descriptor.factory:
            # Use factory function
            deps = self._resolve_dependencies(descriptor.factory)
            return descriptor.factory(**deps)

        impl = descriptor.implementation
        if not inspect.isclass(impl):
            return impl

        deps = self._resolve_dependencies(impl.__init__)
        return impl(**deps)

    def _resolve_dependencies(self, func: Callable) -> Dict[str, Any]:
        """Resolve dependencies from function type hints."""
        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}

        sig = inspect.signature(func)
        resolved = {}

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            param_type = hints.get(param_name)
            if param_type and param_type in self._descriptors:
                resolved[param_name] = self.resolve(param_type)
            elif param.default != inspect.Parameter.empty:
                resolved[param_name] = param.default

        return resolved

    def create_scope(self) -> "ServiceScope":
        """Create a new scope for scoped services."""
        return ServiceScope(self)

    def has(self, service_type: Type) -> bool:
        """Check if a service type is registered."""
        return service_type in self._descriptors

    def get_registrations(self) -> List[dict]:
        """List all registered services."""
        return [
            {
                "type": d.service_type.__name__,
                "lifetime": d.lifetime,
                "has_instance": d.service_type in self._singletons,
            }
            for d in self._descriptors.values()
        ]


class ServiceScope:
    """A scope for scoped service lifetimes."""

    def __init__(self, container: ServiceContainer):
        self._container = container
        self._instances: Dict[Type, Any] = {}

    def resolve(self, service_type: Type) -> Any:
        """Resolve a service within this scope."""
        descriptor = self._container._descriptors.get(service_type)
        if not descriptor:
            raise KeyError(f"Service '{service_type.__name__}' is not registered")

        if descriptor.lifetime == ServiceLifetime.SCOPED:
            if service_type not in self._instances:
                self._instances[service_type] = self._container._create_instance(descriptor)
            return self._instances[service_type]

        return self._container.resolve(service_type)

    def __enter__(self) -> "ServiceScope":
        return self

    def __exit__(self, *args) -> None:
        self._instances.clear()


def inject(func: Callable) -> Callable:
    """Decorator that auto-injects dependencies from the global container."""
    import functools

    @functools.wraps(func)
    def wrapper(*args, _container: Optional[ServiceContainer] = None, **kwargs):
        if _container is None:
            return func(*args, **kwargs)

        hints = get_type_hints(func)
        sig = inspect.signature(func)

        for param_name, param in sig.parameters.items():
            if param_name in kwargs or param_name == "self":
                continue
            param_type = hints.get(param_name)
            if param_type and _container.has(param_type):
                kwargs[param_name] = _container.resolve(param_type)

        return func(*args, **kwargs)

    return wrapper


# Usage:
# container = ServiceContainer()
# container.register_singleton(DatabaseService, PostgresDatabase)
# container.register_transient(UserRepository)
# container.register_factory(CacheService, lambda: RedisCache("localhost"))
#
# repo = container.resolve(UserRepository)  # Auto-wires DatabaseService
'''),
    ("projects/plugin-system", r'''<think>
Plugin sandboxing is important for security. I need to restrict
what plugins can access -- limiting imports, file system access,
and network calls. I will use a restricted execution context.
</think>
Implement plugin sandboxing with restricted imports, resource limits, and permission controls.''', r'''import builtins
import importlib
import logging
import os
import signal
import sys
import types
from typing import Any, Callable, Dict, List, Optional, Set
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Permission:
    """Plugin permission types."""
    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    NETWORK = "network"
    SUBPROCESS = "subprocess"
    SYSTEM = "system"
    IMPORT_ALL = "import:all"


class PermissionSet:
    """Manages granted permissions for a plugin."""

    def __init__(self, permissions: Optional[Set[str]] = None):
        self._permissions = permissions or set()

    def grant(self, permission: str) -> None:
        self._permissions.add(permission)

    def revoke(self, permission: str) -> None:
        self._permissions.discard(permission)

    def has(self, permission: str) -> bool:
        return permission in self._permissions

    def check(self, permission: str) -> None:
        """Raise if permission is not granted."""
        if not self.has(permission):
            raise PermissionError(f"Permission denied: {permission}")


# Default safe modules that plugins can always import
SAFE_MODULES = {
    "json", "math", "datetime", "collections", "itertools",
    "functools", "operator", "string", "re", "typing",
    "dataclasses", "enum", "abc", "copy", "hashlib",
    "base64", "uuid", "time", "textwrap", "decimal",
}

# Modules that require specific permissions
RESTRICTED_MODULES = {
    "os": Permission.SYSTEM,
    "sys": Permission.SYSTEM,
    "subprocess": Permission.SUBPROCESS,
    "shutil": Permission.FILE_WRITE,
    "socket": Permission.NETWORK,
    "http": Permission.NETWORK,
    "urllib": Permission.NETWORK,
    "requests": Permission.NETWORK,
    "aiohttp": Permission.NETWORK,
    "pathlib": Permission.FILE_READ,
}


class RestrictedImporter:
    """Custom import hook that restricts what modules a plugin can import."""

    def __init__(self, permissions: PermissionSet, allowed_extra: Optional[Set[str]] = None):
        self._permissions = permissions
        self._allowed_extra = allowed_extra or set()

    def __call__(self, name: str, *args, **kwargs):
        """Restricted import function."""
        top_level = name.split(".")[0]

        # Always allow safe modules
        if top_level in SAFE_MODULES or top_level in self._allowed_extra:
            return builtins.__import__(name, *args, **kwargs)

        # Check if import:all permission is granted
        if self._permissions.has(Permission.IMPORT_ALL):
            return builtins.__import__(name, *args, **kwargs)

        # Check restricted modules
        required_perm = RESTRICTED_MODULES.get(top_level)
        if required_perm:
            if self._permissions.has(required_perm):
                return builtins.__import__(name, *args, **kwargs)
            raise ImportError(
                f"Plugin does not have permission to import '{name}' "
                f"(requires '{required_perm}')"
            )

        # Deny by default
        raise ImportError(f"Import of '{name}' is not allowed in plugin sandbox")


class ResourceLimits:
    """Enforces resource limits for plugin execution."""

    def __init__(
        self,
        max_memory_mb: int = 100,
        max_cpu_seconds: float = 30.0,
        max_file_size_mb: int = 10,
    ):
        self.max_memory_mb = max_memory_mb
        self.max_cpu_seconds = max_cpu_seconds
        self.max_file_size_mb = max_file_size_mb

    @contextmanager
    def enforce(self):
        """Context manager that enforces resource limits."""
        # Set up timeout
        def timeout_handler(signum, frame):
            raise TimeoutError(
                f"Plugin exceeded CPU time limit of {self.max_cpu_seconds}s"
            )

        old_handler = None
        try:
            # Try to set signal alarm (Unix only)
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(self.max_cpu_seconds))
        except (AttributeError, OSError, ValueError):
            pass  # Windows or non-main thread

        try:
            yield
        finally:
            try:
                signal.alarm(0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)
            except (AttributeError, OSError, ValueError):
                pass


class PluginSandbox:
    """Sandbox for running plugin code with restrictions."""

    def __init__(
        self,
        plugin_name: str,
        permissions: Optional[PermissionSet] = None,
        resource_limits: Optional[ResourceLimits] = None,
    ):
        self._plugin_name = plugin_name
        self._permissions = permissions or PermissionSet()
        self._limits = resource_limits or ResourceLimits()
        self._restricted_importer = RestrictedImporter(self._permissions)

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function within the sandbox."""
        original_import = builtins.__import__

        try:
            builtins.__import__ = self._restricted_importer

            with self._limits.enforce():
                result = func(*args, **kwargs)

            return result
        except PermissionError as e:
            logger.error(f"Plugin '{self._plugin_name}' permission denied: {e}")
            raise
        except TimeoutError as e:
            logger.error(f"Plugin '{self._plugin_name}' timed out: {e}")
            raise
        finally:
            builtins.__import__ = original_import

    @contextmanager
    def context(self):
        """Context manager for sandboxed execution."""
        original_import = builtins.__import__
        try:
            builtins.__import__ = self._restricted_importer
            with self._limits.enforce():
                yield
        finally:
            builtins.__import__ = original_import

    def check_permission(self, permission: str) -> bool:
        """Check if a specific permission is granted."""
        return self._permissions.has(permission)

    def grant_permission(self, permission: str) -> None:
        """Grant an additional permission to this sandbox."""
        self._permissions.grant(permission)
        logger.info(f"Granted '{permission}' to plugin '{self._plugin_name}'")


# Usage:
# permissions = PermissionSet({Permission.FILE_READ, Permission.NETWORK})
# sandbox = PluginSandbox("my-plugin", permissions)
# result = sandbox.execute(plugin.process_data, input_data)
'''),
    ("projects/plugin-system", r'''Implement hot reload support for plugins that allows updating plugin code without restarting the application.''', r'''import hashlib
import importlib
import importlib.util
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class FileWatcher:
    """Watches files for changes using polling."""

    def __init__(self, interval: float = 1.0):
        self._interval = interval
        self._watched: Dict[str, float] = {}  # filepath -> last mtime
        self._callbacks: List[Callable] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def watch(self, filepath: str) -> None:
        """Add a file to watch."""
        path = Path(filepath)
        if path.exists():
            self._watched[str(path)] = path.stat().st_mtime

    def unwatch(self, filepath: str) -> None:
        """Remove a file from the watch list."""
        self._watched.pop(str(Path(filepath)), None)

    def on_change(self, callback: Callable) -> None:
        """Register a callback for file changes."""
        self._callbacks.append(callback)

    def start(self) -> None:
        """Start watching for changes in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def _poll_loop(self) -> None:
        """Polling loop that checks for file changes."""
        while self._running:
            changed = self._check_changes()
            for filepath in changed:
                logger.info(f"File changed: {filepath}")
                for callback in self._callbacks:
                    try:
                        callback(filepath)
                    except Exception as e:
                        logger.error(f"Change callback error: {e}")
            time.sleep(self._interval)

    def _check_changes(self) -> List[str]:
        """Check for changed files."""
        changed = []
        for filepath, last_mtime in list(self._watched.items()):
            path = Path(filepath)
            if not path.exists():
                continue
            current_mtime = path.stat().st_mtime
            if current_mtime != last_mtime:
                self._watched[filepath] = current_mtime
                changed.append(filepath)
        return changed


class HotReloader:
    """Manages hot reloading of plugin modules."""

    def __init__(self, plugin_manager):
        self._plugin_manager = plugin_manager
        self._watcher = FileWatcher(interval=1.0)
        self._module_map: Dict[str, str] = {}  # filepath -> plugin_name
        self._reload_hooks: List[Callable] = []
        self._file_hashes: Dict[str, str] = {}

    def enable(self) -> None:
        """Enable hot reloading for all loaded plugins."""
        for name, entry in self._plugin_manager._plugins.items():
            if entry.module_path:
                self._watch_plugin(name, entry.module_path)

        self._watcher.on_change(self._handle_change)
        self._watcher.start()
        logger.info("Hot reload enabled")

    def disable(self) -> None:
        """Disable hot reloading."""
        self._watcher.stop()
        logger.info("Hot reload disabled")

    def add_reload_hook(self, callback: Callable) -> None:
        """Add a callback that runs after a plugin is reloaded."""
        self._reload_hooks.append(callback)

    def _watch_plugin(self, plugin_name: str, module_path: str) -> None:
        """Start watching a plugin's module file."""
        self._module_map[module_path] = plugin_name
        self._file_hashes[module_path] = self._hash_file(module_path)
        self._watcher.watch(module_path)

        # Also watch any submodules in the same directory
        parent_dir = Path(module_path).parent
        for py_file in parent_dir.glob("*.py"):
            filepath = str(py_file)
            if filepath != module_path:
                self._module_map[filepath] = plugin_name
                self._watcher.watch(filepath)

    def _hash_file(self, filepath: str) -> str:
        """Compute a hash of file contents."""
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def _handle_change(self, filepath: str) -> None:
        """Handle a file change event."""
        # Verify content actually changed (not just mtime)
        new_hash = self._hash_file(filepath)
        old_hash = self._file_hashes.get(filepath)
        if new_hash == old_hash:
            return
        self._file_hashes[filepath] = new_hash

        plugin_name = self._module_map.get(filepath)
        if not plugin_name:
            return

        logger.info(f"Reloading plugin '{plugin_name}' due to file change")
        success = self._reload_plugin(plugin_name)

        if success:
            for hook in self._reload_hooks:
                try:
                    hook(plugin_name)
                except Exception as e:
                    logger.error(f"Reload hook error: {e}")

    def _reload_plugin(self, plugin_name: str) -> bool:
        """Reload a single plugin."""
        entry = self._plugin_manager._plugins.get(plugin_name)
        if not entry:
            return False

        was_active = entry.state == "activated"

        # Deactivate if active
        if was_active:
            self._plugin_manager.deactivate_plugin(plugin_name)

        # Reload the module
        try:
            module_path = entry.module_path
            module_name = Path(module_path).stem

            # Remove from sys.modules to force reimport
            modules_to_remove = [
                key for key in sys.modules
                if key == module_name or key.startswith(f"{module_name}.")
            ]
            for key in modules_to_remove:
                del sys.modules[key]

            # Re-discover the plugin
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find plugin class again
            import inspect
            from .plugin_base import PluginBase
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, PluginBase) and obj is not PluginBase:
                    entry.plugin_class = obj
                    break

            logger.info(f"Plugin '{plugin_name}' reloaded successfully")

            # Re-activate if it was active
            if was_active:
                self._plugin_manager.activate_plugin(plugin_name)

            return True

        except Exception as e:
            logger.error(f"Failed to reload plugin '{plugin_name}': {e}")
            entry.state = "error"
            entry.error = str(e)
            return False

    def force_reload(self, plugin_name: str) -> bool:
        """Force reload a plugin without waiting for file changes."""
        return self._reload_plugin(plugin_name)
'''),
]
