PAIRS = [
    ("projects/orm-layer", r'''<think>
Building an ORM layer requires a model definition system with field types,
constraints, and table mapping. I will implement a metaclass-based approach
similar to SQLAlchemy's declarative style but simpler.
</think>
Build an ORM layer: implement model definitions with field types, constraints, and table mapping.''', r'''from typing import Any, Dict, List, Optional, Type
from enum import Enum


class FieldType(Enum):
    INTEGER = "INTEGER"
    TEXT = "TEXT"
    REAL = "REAL"
    BOOLEAN = "BOOLEAN"
    TIMESTAMP = "TIMESTAMP"
    BLOB = "BLOB"


class Field:
    """Describes a database column."""

    def __init__(
        self,
        field_type: FieldType,
        primary_key: bool = False,
        nullable: bool = True,
        unique: bool = False,
        default: Any = None,
        max_length: Optional[int] = None,
        auto_increment: bool = False,
        index: bool = False,
    ):
        self.field_type = field_type
        self.primary_key = primary_key
        self.nullable = nullable
        self.unique = unique
        self.default = default
        self.max_length = max_length
        self.auto_increment = auto_increment
        self.index = index
        self.name: str = ""  # Set by metaclass
        self.column_name: str = ""  # Set by metaclass

    def to_sql(self) -> str:
        """Generate SQL column definition."""
        parts = [self.column_name]

        if self.field_type == FieldType.TEXT and self.max_length:
            parts.append(f"VARCHAR({self.max_length})")
        else:
            parts.append(self.field_type.value)

        if self.primary_key:
            parts.append("PRIMARY KEY")
        if self.auto_increment:
            parts.append("AUTOINCREMENT")
        if not self.nullable and not self.primary_key:
            parts.append("NOT NULL")
        if self.unique and not self.primary_key:
            parts.append("UNIQUE")
        if self.default is not None:
            if isinstance(self.default, str):
                parts.append(f"DEFAULT '{self.default}'")
            elif isinstance(self.default, bool):
                parts.append(f"DEFAULT {1 if self.default else 0}")
            else:
                parts.append(f"DEFAULT {self.default}")

        return " ".join(parts)

    def validate(self, value: Any) -> Any:
        """Validate and coerce a value for this field."""
        if value is None:
            if not self.nullable and self.default is None:
                raise ValueError(f"Field '{self.name}' cannot be null")
            return self.default

        if self.field_type == FieldType.INTEGER:
            return int(value)
        elif self.field_type == FieldType.REAL:
            return float(value)
        elif self.field_type == FieldType.BOOLEAN:
            return bool(value)
        elif self.field_type == FieldType.TEXT:
            value = str(value)
            if self.max_length and len(value) > self.max_length:
                raise ValueError(
                    f"Field '{self.name}' exceeds max length {self.max_length}"
                )
            return value
        return value


# Convenience constructors
def IntegerField(**kwargs) -> Field:
    return Field(FieldType.INTEGER, **kwargs)

def TextField(**kwargs) -> Field:
    return Field(FieldType.TEXT, **kwargs)

def FloatField(**kwargs) -> Field:
    return Field(FieldType.REAL, **kwargs)

def BooleanField(**kwargs) -> Field:
    return Field(FieldType.BOOLEAN, **kwargs)

def TimestampField(**kwargs) -> Field:
    return Field(FieldType.TIMESTAMP, **kwargs)


class ModelMeta(type):
    """Metaclass that collects field definitions from model classes."""

    def __new__(mcs, name: str, bases: tuple, namespace: dict):
        fields = {}
        for key, value in list(namespace.items()):
            if isinstance(value, Field):
                value.name = key
                value.column_name = key
                fields[key] = value

        namespace["_fields"] = fields
        namespace["_table_name"] = namespace.get(
            "_table_name", name.lower() + "s"
        )

        cls = super().__new__(mcs, name, bases, namespace)
        return cls


class Model(metaclass=ModelMeta):
    """Base model class for ORM entities."""

    _fields: Dict[str, Field] = {}
    _table_name: str = ""

    def __init__(self, **kwargs):
        for field_name, field_def in self._fields.items():
            value = kwargs.get(field_name)
            validated = field_def.validate(value)
            setattr(self, field_name, validated)

    @classmethod
    def create_table_sql(cls) -> str:
        """Generate CREATE TABLE SQL statement."""
        columns = [f.to_sql() for f in cls._fields.values()]
        return f"CREATE TABLE IF NOT EXISTS {cls._table_name} (\n  " + ",\n  ".join(columns) + "\n)"

    def to_dict(self) -> dict:
        """Convert model instance to dictionary."""
        return {name: getattr(self, name) for name in self._fields}


# Example usage:
class User(Model):
    _table_name = "users"
    id = IntegerField(primary_key=True, auto_increment=True)
    username = TextField(max_length=50, unique=True, nullable=False)
    email = TextField(max_length=255, unique=True, nullable=False)
    is_active = BooleanField(default=True)
    created_at = TimestampField(default="CURRENT_TIMESTAMP")
'''),
    ("projects/orm-layer", r'''Implement a query builder for the ORM that supports select, where, join, order by, and limit clauses with parameterized queries.''', r'''from typing import Any, Dict, List, Optional, Tuple, Type


class QueryBuilder:
    """Fluent query builder that generates parameterized SQL."""

    def __init__(self, model_class=None, table: Optional[str] = None):
        self._table = table or (model_class._table_name if model_class else "")
        self._model_class = model_class
        self._select_columns: List[str] = []
        self._where_clauses: List[str] = []
        self._params: List[Any] = []
        self._joins: List[str] = []
        self._order_by: List[str] = []
        self._group_by: List[str] = []
        self._having: List[str] = []
        self._limit_val: Optional[int] = None
        self._offset_val: Optional[int] = None
        self._distinct = False

    def select(self, *columns: str) -> "QueryBuilder":
        """Specify columns to select."""
        self._select_columns.extend(columns)
        return self

    def distinct(self) -> "QueryBuilder":
        """Add DISTINCT to the query."""
        self._distinct = True
        return self

    def where(self, condition: str, *params: Any) -> "QueryBuilder":
        """Add a WHERE condition with parameters."""
        self._where_clauses.append(condition)
        self._params.extend(params)
        return self

    def where_eq(self, column: str, value: Any) -> "QueryBuilder":
        """Add a column = value condition."""
        self._where_clauses.append(f"{column} = ?")
        self._params.append(value)
        return self

    def where_in(self, column: str, values: List[Any]) -> "QueryBuilder":
        """Add a column IN (...) condition."""
        placeholders = ", ".join(["?"] * len(values))
        self._where_clauses.append(f"{column} IN ({placeholders})")
        self._params.extend(values)
        return self

    def where_like(self, column: str, pattern: str) -> "QueryBuilder":
        """Add a LIKE condition."""
        self._where_clauses.append(f"{column} LIKE ?")
        self._params.append(pattern)
        return self

    def where_between(self, column: str, low: Any, high: Any) -> "QueryBuilder":
        """Add a BETWEEN condition."""
        self._where_clauses.append(f"{column} BETWEEN ? AND ?")
        self._params.extend([low, high])
        return self

    def where_null(self, column: str) -> "QueryBuilder":
        """Add IS NULL condition."""
        self._where_clauses.append(f"{column} IS NULL")
        return self

    def where_not_null(self, column: str) -> "QueryBuilder":
        """Add IS NOT NULL condition."""
        self._where_clauses.append(f"{column} IS NOT NULL")
        return self

    def join(self, table: str, on: str, join_type: str = "INNER") -> "QueryBuilder":
        """Add a JOIN clause."""
        self._joins.append(f"{join_type} JOIN {table} ON {on}")
        return self

    def left_join(self, table: str, on: str) -> "QueryBuilder":
        return self.join(table, on, "LEFT")

    def right_join(self, table: str, on: str) -> "QueryBuilder":
        return self.join(table, on, "RIGHT")

    def order_by(self, column: str, direction: str = "ASC") -> "QueryBuilder":
        """Add ORDER BY clause."""
        direction = direction.upper()
        if direction not in ("ASC", "DESC"):
            raise ValueError("Direction must be ASC or DESC")
        self._order_by.append(f"{column} {direction}")
        return self

    def group_by(self, *columns: str) -> "QueryBuilder":
        """Add GROUP BY clause."""
        self._group_by.extend(columns)
        return self

    def having(self, condition: str, *params: Any) -> "QueryBuilder":
        """Add HAVING clause."""
        self._having.append(condition)
        self._params.extend(params)
        return self

    def limit(self, count: int) -> "QueryBuilder":
        """Set LIMIT."""
        self._limit_val = count
        return self

    def offset(self, count: int) -> "QueryBuilder":
        """Set OFFSET."""
        self._offset_val = count
        return self

    def build(self) -> Tuple[str, List[Any]]:
        """Build the final SQL query and parameters."""
        columns = ", ".join(self._select_columns) if self._select_columns else "*"
        distinct = "DISTINCT " if self._distinct else ""
        sql = f"SELECT {distinct}{columns} FROM {self._table}"

        for join_clause in self._joins:
            sql += f" {join_clause}"

        if self._where_clauses:
            sql += " WHERE " + " AND ".join(self._where_clauses)

        if self._group_by:
            sql += " GROUP BY " + ", ".join(self._group_by)

        if self._having:
            sql += " HAVING " + " AND ".join(self._having)

        if self._order_by:
            sql += " ORDER BY " + ", ".join(self._order_by)

        if self._limit_val is not None:
            sql += f" LIMIT {self._limit_val}"

        if self._offset_val is not None:
            sql += f" OFFSET {self._offset_val}"

        return sql, list(self._params)

    def build_count(self) -> Tuple[str, List[Any]]:
        """Build a COUNT query."""
        sql = f"SELECT COUNT(*) FROM {self._table}"
        for join_clause in self._joins:
            sql += f" {join_clause}"
        if self._where_clauses:
            sql += " WHERE " + " AND ".join(self._where_clauses)
        return sql, list(self._params)


# Usage example:
# query, params = (
#     QueryBuilder(table="users")
#     .select("users.id", "users.username", "orders.total")
#     .join("orders", "orders.user_id = users.id")
#     .where_eq("users.is_active", True)
#     .where_like("users.username", "%admin%")
#     .order_by("users.created_at", "DESC")
#     .limit(20)
#     .offset(0)
#     .build()
# )
'''),
    ("projects/orm-layer", r'''<think>
Database migrations are essential for schema evolution. I need a system
that tracks applied migrations, supports up/down operations, and
generates migration files from model diffs.
</think>
Implement a database migration system with schema versioning, up/down operations, and migration tracking.''', r'''import os
import time
import sqlite3
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class Migration:
    """Represents a single database migration."""
    version: str
    name: str
    up_sql: str
    down_sql: str
    created_at: float

    @property
    def filename(self) -> str:
        return f"{self.version}_{self.name}.py"


class MigrationRegistry:
    """Stores and orders migrations."""

    def __init__(self):
        self._migrations: Dict[str, Migration] = {}

    def register(self, version: str, name: str, up_sql: str, down_sql: str) -> None:
        self._migrations[version] = Migration(
            version=version,
            name=name,
            up_sql=up_sql,
            down_sql=down_sql,
            created_at=time.time(),
        )

    def get_ordered(self) -> List[Migration]:
        return sorted(self._migrations.values(), key=lambda m: m.version)

    def get(self, version: str) -> Optional[Migration]:
        return self._migrations.get(version)


class MigrationManager:
    """Manages database schema migrations."""

    TRACKING_TABLE = "_migrations"

    def __init__(self, db_path: str, migrations_dir: str = "migrations"):
        self._db_path = db_path
        self._migrations_dir = Path(migrations_dir)
        self._registry = MigrationRegistry()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_tracking_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TRACKING_TABLE} (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at REAL NOT NULL,
                checksum TEXT
            )
        """)

    def get_applied_versions(self) -> List[str]:
        """Get list of applied migration versions."""
        conn = self._get_connection()
        self._ensure_tracking_table(conn)
        rows = conn.execute(
            f"SELECT version FROM {self.TRACKING_TABLE} ORDER BY version"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    def get_pending(self) -> List[Migration]:
        """Get migrations that have not been applied yet."""
        applied = set(self.get_applied_versions())
        all_migrations = self._registry.get_ordered()
        return [m for m in all_migrations if m.version not in applied]

    def migrate_up(self, target: Optional[str] = None, dry_run: bool = False) -> List[str]:
        """Apply pending migrations up to the target version."""
        pending = self.get_pending()
        if target:
            pending = [m for m in pending if m.version <= target]

        if not pending:
            return []

        applied = []
        conn = self._get_connection()
        self._ensure_tracking_table(conn)

        for migration in pending:
            if dry_run:
                print(f"[DRY RUN] Would apply: {migration.version} - {migration.name}")
                print(f"  SQL: {migration.up_sql[:200]}...")
                applied.append(migration.version)
                continue

            try:
                conn.executescript(migration.up_sql)
                conn.execute(
                    f"INSERT INTO {self.TRACKING_TABLE} (version, name, applied_at) VALUES (?, ?, ?)",
                    (migration.version, migration.name, time.time()),
                )
                conn.commit()
                applied.append(migration.version)
                print(f"Applied: {migration.version} - {migration.name}")
            except Exception as e:
                conn.rollback()
                print(f"Failed at {migration.version}: {e}")
                break

        conn.close()
        return applied

    def migrate_down(self, steps: int = 1, dry_run: bool = False) -> List[str]:
        """Roll back the last N applied migrations."""
        applied = self.get_applied_versions()
        if not applied:
            return []

        to_rollback = list(reversed(applied[-steps:]))
        rolled_back = []
        conn = self._get_connection()

        for version in to_rollback:
            migration = self._registry.get(version)
            if not migration:
                print(f"Warning: Migration {version} not found in registry")
                continue

            if dry_run:
                print(f"[DRY RUN] Would rollback: {version} - {migration.name}")
                rolled_back.append(version)
                continue

            try:
                conn.executescript(migration.down_sql)
                conn.execute(
                    f"DELETE FROM {self.TRACKING_TABLE} WHERE version = ?",
                    (version,),
                )
                conn.commit()
                rolled_back.append(version)
                print(f"Rolled back: {version} - {migration.name}")
            except Exception as e:
                conn.rollback()
                print(f"Rollback failed at {version}: {e}")
                break

        conn.close()
        return rolled_back

    def create_migration(self, name: str) -> str:
        """Generate a new migration file."""
        timestamp = time.strftime("%Y%m%d%H%M%S")
        version = timestamp
        self._migrations_dir.mkdir(parents=True, exist_ok=True)

        content = f"""# Migration: {version}_{name}
# Generated at {time.strftime("%Y-%m-%d %H:%M:%S")}

UP = \"\"\"
-- Write your forward migration SQL here
\"\"\"

DOWN = \"\"\"
-- Write your rollback SQL here
\"\"\"
"""
        filepath = self._migrations_dir / f"{version}_{name}.py"
        with open(filepath, "w") as f:
            f.write(content)

        return str(filepath)

    def status(self) -> List[dict]:
        """Get the status of all migrations."""
        applied = set(self.get_applied_versions())
        result = []
        for m in self._registry.get_ordered():
            result.append({
                "version": m.version,
                "name": m.name,
                "applied": m.version in applied,
            })
        return result
'''),
    ("projects/orm-layer", r'''Implement model relationships (one-to-many, many-to-many) and eager/lazy loading for the ORM.''', r'''from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING


class Relationship:
    """Base class for model relationships."""

    def __init__(
        self,
        target_model: str,
        foreign_key: Optional[str] = None,
        back_ref: Optional[str] = None,
        lazy: bool = True,
    ):
        self.target_model = target_model
        self.foreign_key = foreign_key
        self.back_ref = back_ref
        self.lazy = lazy
        self.name: str = ""  # Set during model registration
        self.owner_model: str = ""

    def resolve_target(self, registry: dict):
        """Resolve the target model class from the registry."""
        return registry.get(self.target_model)


class HasMany(Relationship):
    """One-to-many relationship."""

    def __init__(self, target_model: str, foreign_key: str, **kwargs):
        super().__init__(target_model, foreign_key=foreign_key, **kwargs)

    def build_query(self, owner_id: Any) -> tuple:
        """Build query to fetch related records."""
        sql = f"SELECT * FROM {{table}} WHERE {self.foreign_key} = ?"
        return sql, [owner_id]


class BelongsTo(Relationship):
    """Inverse of one-to-many."""

    def __init__(self, target_model: str, foreign_key: str, **kwargs):
        super().__init__(target_model, foreign_key=foreign_key, **kwargs)

    def build_query(self, foreign_key_value: Any) -> tuple:
        """Build query to fetch the parent record."""
        sql = "SELECT * FROM {table} WHERE id = ?"
        return sql, [foreign_key_value]


class ManyToMany(Relationship):
    """Many-to-many relationship through a join table."""

    def __init__(
        self,
        target_model: str,
        join_table: str,
        local_key: str = "id",
        foreign_key: str = "id",
        join_local: Optional[str] = None,
        join_foreign: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(target_model, **kwargs)
        self.join_table = join_table
        self.local_key = local_key
        self.foreign_key_col = foreign_key
        self.join_local = join_local
        self.join_foreign = join_foreign

    def build_query(self, owner_id: Any) -> tuple:
        """Build query to fetch related records through join table."""
        jl = self.join_local or f"{self.owner_model.lower()}_id"
        jf = self.join_foreign or f"{self.target_model.lower()}_id"
        sql = (
            f"SELECT t.* FROM {{table}} t "
            f"INNER JOIN {self.join_table} j ON j.{jf} = t.{self.foreign_key_col} "
            f"WHERE j.{jl} = ?"
        )
        return sql, [owner_id]


class RelationshipLoader:
    """Handles loading of related models with eager/lazy strategies."""

    def __init__(self, connection, model_registry: dict):
        self._conn = connection
        self._registry = model_registry

    def load_related(self, instance, relationship: Relationship) -> Any:
        """Load related model(s) for an instance."""
        target_cls = relationship.resolve_target(self._registry)
        if not target_cls:
            raise ValueError(f"Model '{relationship.target_model}' not found in registry")

        if isinstance(relationship, HasMany):
            return self._load_has_many(instance, relationship, target_cls)
        elif isinstance(relationship, BelongsTo):
            return self._load_belongs_to(instance, relationship, target_cls)
        elif isinstance(relationship, ManyToMany):
            return self._load_many_to_many(instance, relationship, target_cls)

    def _load_has_many(self, instance, rel: HasMany, target_cls) -> List:
        """Load a one-to-many relationship."""
        owner_id = getattr(instance, "id")
        sql_template, params = rel.build_query(owner_id)
        sql = sql_template.format(table=target_cls._table_name)
        cursor = self._conn.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            data = dict(zip(columns, row))
            results.append(target_cls(**data))
        return results

    def _load_belongs_to(self, instance, rel: BelongsTo, target_cls) -> Optional[Any]:
        """Load a belongs-to relationship."""
        fk_value = getattr(instance, rel.foreign_key, None)
        if fk_value is None:
            return None
        sql_template, params = rel.build_query(fk_value)
        sql = sql_template.format(table=target_cls._table_name)
        cursor = self._conn.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()
        if row:
            return target_cls(**dict(zip(columns, row)))
        return None

    def _load_many_to_many(self, instance, rel: ManyToMany, target_cls) -> List:
        """Load a many-to-many relationship."""
        owner_id = getattr(instance, rel.local_key)
        sql_template, params = rel.build_query(owner_id)
        sql = sql_template.format(table=target_cls._table_name)
        cursor = self._conn.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            data = dict(zip(columns, row))
            results.append(target_cls(**data))
        return results

    def eager_load(self, instances: List, *relationship_names: str) -> List:
        """Eager load relationships for a list of instances to avoid N+1 queries."""
        if not instances:
            return instances

        model_cls = type(instances[0])
        for rel_name in relationship_names:
            rel = getattr(model_cls, rel_name, None)
            if not isinstance(rel, Relationship):
                continue

            # Batch load: collect all IDs and do a single query
            if isinstance(rel, HasMany):
                ids = [getattr(inst, "id") for inst in instances]
                target_cls = rel.resolve_target(self._registry)
                placeholders = ", ".join(["?"] * len(ids))
                sql = f"SELECT * FROM {target_cls._table_name} WHERE {rel.foreign_key} IN ({placeholders})"
                cursor = self._conn.execute(sql, ids)
                columns = [desc[0] for desc in cursor.description]

                # Group results by foreign key
                grouped: Dict[Any, List] = {}
                for row in cursor.fetchall():
                    data = dict(zip(columns, row))
                    fk_val = data[rel.foreign_key]
                    grouped.setdefault(fk_val, []).append(target_cls(**data))

                for inst in instances:
                    setattr(inst, f"_{rel_name}_cache", grouped.get(getattr(inst, "id"), []))

        return instances
'''),
    ("projects/orm-layer", r'''Implement connection pooling for the ORM with configurable pool size, health checks, and connection recycling.''', r'''import sqlite3
import threading
import time
import logging
import queue
from typing import Any, Optional
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PooledConnection:
    """Wraps a database connection with pool metadata."""
    connection: sqlite3.Connection
    created_at: float
    last_used: float
    use_count: int = 0
    in_use: bool = False

    def is_expired(self, max_age: float) -> bool:
        return (time.time() - self.created_at) > max_age

    def is_idle_too_long(self, max_idle: float) -> bool:
        return (time.time() - self.last_used) > max_idle


class ConnectionPool:
    """Thread-safe connection pool with health checks and recycling.

    Features:
    - Configurable min/max pool size
    - Connection health checking before checkout
    - Automatic connection recycling based on age
    - Idle connection cleanup
    - Overflow connections for burst traffic
    """

    def __init__(
        self,
        database: str,
        min_size: int = 2,
        max_size: int = 10,
        max_overflow: int = 5,
        max_age: float = 3600.0,
        max_idle: float = 600.0,
        checkout_timeout: float = 30.0,
    ):
        self._database = database
        self._min_size = min_size
        self._max_size = max_size
        self._max_overflow = max_overflow
        self._max_age = max_age
        self._max_idle = max_idle
        self._checkout_timeout = checkout_timeout

        self._pool: queue.Queue = queue.Queue(maxsize=max_size)
        self._lock = threading.Lock()
        self._size = 0
        self._overflow_count = 0
        self._total_checkouts = 0
        self._total_checkins = 0
        self._closed = False

        # Pre-populate with minimum connections
        for _ in range(min_size):
            conn = self._create_connection()
            self._pool.put(conn)

    def _create_connection(self) -> PooledConnection:
        """Create a new database connection."""
        conn = sqlite3.connect(self._database, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row

        with self._lock:
            self._size += 1

        now = time.time()
        return PooledConnection(
            connection=conn,
            created_at=now,
            last_used=now,
        )

    def _validate_connection(self, pooled: PooledConnection) -> bool:
        """Check if a connection is still valid."""
        try:
            pooled.connection.execute("SELECT 1")
            return True
        except Exception:
            return False

    def checkout(self) -> PooledConnection:
        """Get a connection from the pool."""
        if self._closed:
            raise RuntimeError("Connection pool is closed")

        # Try to get from pool
        try:
            pooled = self._pool.get(timeout=0.1)
        except queue.Empty:
            pooled = None

        if pooled:
            # Check health and age
            if pooled.is_expired(self._max_age) or not self._validate_connection(pooled):
                self._destroy_connection(pooled)
                pooled = self._create_connection()
        else:
            # Pool empty - create new if under limits
            with self._lock:
                total = self._size + self._overflow_count
                if total < self._max_size + self._max_overflow:
                    if self._size < self._max_size:
                        pooled = self._create_connection()
                    else:
                        self._overflow_count += 1
                        pooled = self._create_connection()

            if pooled is None:
                # Wait for a connection to be returned
                try:
                    pooled = self._pool.get(timeout=self._checkout_timeout)
                except queue.Empty:
                    raise TimeoutError("Could not get connection from pool within timeout")

        pooled.in_use = True
        pooled.last_used = time.time()
        pooled.use_count += 1

        with self._lock:
            self._total_checkouts += 1

        return pooled

    def checkin(self, pooled: PooledConnection) -> None:
        """Return a connection to the pool."""
        pooled.in_use = False
        pooled.last_used = time.time()

        with self._lock:
            self._total_checkins += 1

        if pooled.is_expired(self._max_age):
            self._destroy_connection(pooled)
            return

        try:
            self._pool.put_nowait(pooled)
        except queue.Full:
            self._destroy_connection(pooled)

    def _destroy_connection(self, pooled: PooledConnection) -> None:
        """Close and discard a connection."""
        try:
            pooled.connection.close()
        except Exception:
            pass
        with self._lock:
            self._size -= 1

    @contextmanager
    def connection(self):
        """Context manager for checkout/checkin."""
        pooled = self.checkout()
        try:
            yield pooled.connection
        except Exception:
            # Rollback on error
            try:
                pooled.connection.rollback()
            except Exception:
                pass
            raise
        finally:
            self.checkin(pooled)

    def cleanup_idle(self) -> int:
        """Remove idle connections that exceed max_idle time."""
        removed = 0
        temp = []
        while not self._pool.empty():
            try:
                pooled = self._pool.get_nowait()
                if pooled.is_idle_too_long(self._max_idle) and self._size > self._min_size:
                    self._destroy_connection(pooled)
                    removed += 1
                else:
                    temp.append(pooled)
            except queue.Empty:
                break

        for p in temp:
            try:
                self._pool.put_nowait(p)
            except queue.Full:
                self._destroy_connection(p)
        return removed

    def close(self) -> None:
        """Close all connections and shut down the pool."""
        self._closed = True
        while not self._pool.empty():
            try:
                pooled = self._pool.get_nowait()
                self._destroy_connection(pooled)
            except queue.Empty:
                break

    def stats(self) -> dict:
        """Get pool statistics."""
        return {
            "size": self._size,
            "available": self._pool.qsize(),
            "overflow": self._overflow_count,
            "total_checkouts": self._total_checkouts,
            "total_checkins": self._total_checkins,
            "max_size": self._max_size,
        }
'''),
]
