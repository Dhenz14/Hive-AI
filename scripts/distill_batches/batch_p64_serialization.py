"""Tooling — serialization formats, Protocol Buffers, and data interchange."""

PAIRS = [
    (
        "serialization/protobuf",
        "Show Protocol Buffers patterns: message definitions, gRPC services, evolution rules, and Python usage.",
        '''Protocol Buffers and gRPC patterns:

```protobuf
// --- Proto3 message definitions ---
// user.proto

syntax = "proto3";
package myapp.v1;

import "google/protobuf/timestamp.proto";
import "google/protobuf/field_mask.proto";
import "google/protobuf/wrappers.proto";

option python_package = "myapp.proto.v1";


// Enums
enum UserStatus {
  USER_STATUS_UNSPECIFIED = 0;  // Always have zero value
  USER_STATUS_ACTIVE = 1;
  USER_STATUS_SUSPENDED = 2;
  USER_STATUS_DELETED = 3;
}

// Messages
message User {
  string id = 1;
  string email = 2;
  string name = 3;
  UserStatus status = 4;
  google.protobuf.Timestamp created_at = 5;
  google.protobuf.Timestamp updated_at = 6;

  // Nested message
  Address address = 7;

  // Repeated field (list)
  repeated string tags = 8;

  // Map field
  map<string, string> metadata = 9;

  // Optional wrapper for nullable primitives
  google.protobuf.Int32Value age = 10;

  // Oneof for mutually exclusive fields
  oneof contact {
    string phone = 11;
    string slack_id = 12;
  }
}

message Address {
  string street = 1;
  string city = 2;
  string state = 3;
  string zip_code = 4;
  string country = 5;
}


// --- gRPC service definition ---

message GetUserRequest {
  string id = 1;
}

message ListUsersRequest {
  int32 page_size = 1;
  string page_token = 2;  // Cursor for pagination
  string filter = 3;       // e.g., "status=active"
}

message ListUsersResponse {
  repeated User users = 1;
  string next_page_token = 2;
  int32 total_count = 3;
}

message CreateUserRequest {
  User user = 1;
}

message UpdateUserRequest {
  User user = 1;
  google.protobuf.FieldMask update_mask = 2;  // Which fields to update
}

message DeleteUserRequest {
  string id = 1;
}

service UserService {
  // Unary RPCs
  rpc GetUser(GetUserRequest) returns (User);
  rpc ListUsers(ListUsersRequest) returns (ListUsersResponse);
  rpc CreateUser(CreateUserRequest) returns (User);
  rpc UpdateUser(UpdateUserRequest) returns (User);
  rpc DeleteUser(DeleteUserRequest) returns (google.protobuf.Empty);

  // Server streaming
  rpc WatchUsers(ListUsersRequest) returns (stream User);

  // Client streaming
  rpc BatchCreateUsers(stream CreateUserRequest) returns (ListUsersResponse);
}
```

```python
# --- Python gRPC server ---

import grpc
from concurrent import futures
from myapp.proto.v1 import user_pb2, user_pb2_grpc
from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf import field_mask_pb2
import time


class UserServicer(user_pb2_grpc.UserServiceServicer):

    def __init__(self, db):
        self.db = db

    def GetUser(self, request, context):
        user = self.db.get_user(request.id)
        if not user:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"User {request.id} not found")
            return user_pb2.User()

        return self._to_proto(user)

    def ListUsers(self, request, context):
        page_size = min(request.page_size or 20, 100)
        users, next_token, total = self.db.list_users(
            page_size=page_size,
            page_token=request.page_token,
            filter_str=request.filter,
        )
        return user_pb2.ListUsersResponse(
            users=[self._to_proto(u) for u in users],
            next_page_token=next_token,
            total_count=total,
        )

    def UpdateUser(self, request, context):
        # Use FieldMask to apply partial updates
        paths = request.update_mask.paths
        updates = {}
        for path in paths:
            if hasattr(request.user, path):
                updates[path] = getattr(request.user, path)

        updated = self.db.update_user(request.user.id, updates)
        return self._to_proto(updated)

    def WatchUsers(self, request, context):
        """Server streaming: push updates to client."""
        for event in self.db.watch_changes():
            if context.is_active():
                yield self._to_proto(event.user)
            else:
                break

    def _to_proto(self, user_dict):
        ts = Timestamp()
        ts.FromDatetime(user_dict["created_at"])
        return user_pb2.User(
            id=user_dict["id"],
            email=user_dict["email"],
            name=user_dict["name"],
            status=user_dict["status"],
            created_at=ts,
        )


def serve():
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_receive_message_length", 10 * 1024 * 1024),
        ],
    )
    user_pb2_grpc.add_UserServiceServicer_to_server(
        UserServicer(db), server
    )
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()
```

Protobuf/gRPC patterns:
1. **Zero-value enums** — always have `_UNSPECIFIED = 0` as default
2. **FieldMask** — specify which fields to update in PATCH operations
3. **Page tokens** — opaque cursor strings for stateless pagination
4. **`oneof`** — mutually exclusive fields (phone OR slack_id)
5. **Server streaming** — `returns (stream T)` for real-time event feeds'''
    ),
    (
        "serialization/file-formats",
        "Show data file format patterns: Parquet, Avro, MessagePack, and TOML/YAML parsing.",
        '''Data file format patterns:

```python
import json
import struct
from pathlib import Path


# --- Parquet (columnar, analytics-optimized) ---

import pyarrow as pa
import pyarrow.parquet as pq


def write_parquet(data: list[dict], path: str,
                  partition_cols: list[str] = None):
    """Write data to partitioned Parquet files."""
    table = pa.Table.from_pylist(data)

    if partition_cols:
        pq.write_to_dataset(
            table, root_path=path,
            partition_cols=partition_cols,
            use_dictionary=True,
            compression="snappy",
        )
    else:
        pq.write_table(
            table, path,
            compression="snappy",
            row_group_size=100_000,
        )


def read_parquet_filtered(path: str, filters: list = None,
                          columns: list[str] = None) -> list[dict]:
    """Read Parquet with predicate pushdown."""
    table = pq.read_table(
        path,
        columns=columns,  # Column pruning
        filters=filters,   # Predicate pushdown
        # e.g., filters=[("age", ">", 18), ("status", "=", "active")]
    )
    return table.to_pylist()


# Schema inspection
def inspect_parquet(path: str):
    metadata = pq.read_metadata(path)
    schema = pq.read_schema(path)
    print(f"Rows: {metadata.num_rows}")
    print(f"Row groups: {metadata.num_row_groups}")
    print(f"Schema:\\n{schema}")


# --- MessagePack (binary JSON, faster + smaller) ---

import msgpack


def msgpack_encode(data) -> bytes:
    """Encode to MessagePack (compact binary)."""
    return msgpack.packb(data, use_bin_type=True)

def msgpack_decode(data: bytes):
    """Decode MessagePack."""
    return msgpack.unpackb(data, raw=False)


# Streaming large files
def msgpack_stream_write(records: list[dict], path: str):
    with open(path, "wb") as f:
        packer = msgpack.Packer(use_bin_type=True)
        for record in records:
            f.write(packer.pack(record))

def msgpack_stream_read(path: str):
    with open(path, "rb") as f:
        unpacker = msgpack.Unpacker(f, raw=False)
        for record in unpacker:
            yield record


# --- TOML parsing ---

import tomllib  # Python 3.11+ (or tomli for older)


def load_config(path: str = "pyproject.toml") -> dict:
    """Load TOML configuration."""
    with open(path, "rb") as f:
        config = tomllib.load(f)
    return config


# pyproject.toml example:
# [tool.myapp]
# name = "myapp"
# version = "1.0.0"
# debug = false
#
# [tool.myapp.database]
# host = "localhost"
# port = 5432
# name = "mydb"
#
# [tool.myapp.features]
# dark_mode = true
# beta = ["user1", "user2"]


# --- YAML with safe loading ---

import yaml


def load_yaml(path: str) -> dict:
    """Load YAML with safe loader (no arbitrary code execution)."""
    with open(path) as f:
        return yaml.safe_load(f)

def dump_yaml(data: dict, path: str):
    """Write YAML with readable formatting."""
    with open(path, "w") as f:
        yaml.dump(data, f,
                  default_flow_style=False,
                  sort_keys=False,
                  allow_unicode=True)


# --- CSV with type coercion ---

import csv
from io import StringIO


def read_csv_typed(path: str, types: dict = None) -> list[dict]:
    """Read CSV with automatic type coercion."""
    type_map = types or {}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            typed_row = {}
            for key, value in row.items():
                if key in type_map:
                    typed_row[key] = type_map[key](value) if value else None
                else:
                    typed_row[key] = value
            rows.append(typed_row)

    return rows

# read_csv_typed("data.csv", types={"age": int, "score": float, "active": bool})
```

File format patterns:
1. **Parquet** — columnar format with predicate pushdown and column pruning
2. **MessagePack** — binary JSON alternative (30-50% smaller, 2-5x faster)
3. **TOML** — `tomllib` (stdlib 3.11+) for config files
4. **YAML** — always use `safe_load()` to prevent code execution
5. **CSV typing** — explicit type map to coerce string values'''
    ),
]
"""
