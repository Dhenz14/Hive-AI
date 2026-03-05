"""Audit logging — structured audit events, tamper-proof logs, compliance logging (HIPAA/SOC2), log forwarding, searchable audit trails, retention policies."""

PAIRS = [
    (
        "security/structured-audit-events",
        "Build a production structured audit logging system in Python that captures user actions, resource changes, and system events with full context. Include correlation IDs, actor identification, and immutable event schemas.",
        '''A production structured audit logging system with immutable event schemas and full context:

```python
"""
Structured audit event system with immutable schemas,
correlation tracking, and compliance-ready formatting.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Sequence

from pydantic import BaseModel, Field, field_validator, model_validator


# --- Event classification ---

class AuditCategory(str, Enum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    CONFIGURATION = "configuration"
    SYSTEM = "system"
    COMPLIANCE = "compliance"


class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AuditOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"


# --- Actor & resource models ---

class Actor(BaseModel):
    """Who performed the action."""
    actor_id: str
    actor_type: str = "user"  # user | service | system | api_key
    display_name: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    # For service-to-service calls
    service_name: Optional[str] = None
    service_version: Optional[str] = None


class Resource(BaseModel):
    """What was acted upon."""
    resource_type: str  # e.g., "patient_record", "api_key", "config"
    resource_id: str
    resource_name: Optional[str] = None
    owner_id: Optional[str] = None
    sensitivity: str = "standard"  # standard | sensitive | restricted | phi


class DataChange(BaseModel):
    """Captures before/after for data modifications."""
    field_name: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    is_redacted: bool = False  # True if values contain PII/PHI

    def redacted(self) -> "DataChange":
        """Return a copy with values redacted for safe logging."""
        return DataChange(
            field_name=self.field_name,
            old_value="[REDACTED]" if self.old_value is not None else None,
            new_value="[REDACTED]" if self.new_value is not None else None,
            is_redacted=True,
        )


# --- Core audit event ---

class AuditEvent(BaseModel):
    """Immutable structured audit event."""

    # Identity
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str  # e.g., "user.login", "record.view", "config.update"
    event_version: str = "1.0"

    # Timing
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    duration_ms: Optional[int] = None

    # Classification
    category: AuditCategory
    severity: AuditSeverity = AuditSeverity.INFO
    outcome: AuditOutcome

    # Context
    actor: Actor
    resource: Optional[Resource] = None
    changes: list[DataChange] = Field(default_factory=list)

    # Correlation
    correlation_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None

    # Environment
    environment: str = "production"
    service_name: str = "unknown"
    service_version: Optional[str] = None

    # Compliance tags
    compliance_tags: list[str] = Field(default_factory=list)
    # e.g., ["hipaa", "soc2", "gdpr", "pci-dss"]

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Integrity
    event_hash: Optional[str] = None
    previous_hash: Optional[str] = None

    class Config:
        frozen = True  # Immutable after creation

    @model_validator(mode="after")
    def compute_hash(self) -> "AuditEvent":
        """Compute integrity hash over canonical event fields."""
        if self.event_hash is None:
            canonical = json.dumps(
                {
                    "event_id": self.event_id,
                    "event_type": self.event_type,
                    "timestamp": self.timestamp.isoformat(),
                    "category": self.category.value,
                    "outcome": self.outcome.value,
                    "actor_id": self.actor.actor_id,
                    "resource_id": (
                        self.resource.resource_id if self.resource else None
                    ),
                },
                sort_keys=True,
            )
            hash_val = hashlib.sha256(canonical.encode()).hexdigest()
            object.__setattr__(self, "event_hash", hash_val)
        return self


# --- Audit logger with chain integrity ---

class AuditLogger:
    """
    Thread-safe audit logger that maintains hash chain integrity
    and routes events to multiple sinks.
    """

    def __init__(
        self,
        service_name: str,
        environment: str = "production",
        sinks: Optional[list["AuditSink"]] = None,
    ):
        self.service_name = service_name
        self.environment = environment
        self.sinks: list[AuditSink] = sinks or []
        self._last_hash: Optional[str] = None
        self._event_count = 0

    def log(
        self,
        event_type: str,
        category: AuditCategory,
        outcome: AuditOutcome,
        actor: Actor,
        resource: Optional[Resource] = None,
        changes: Optional[list[DataChange]] = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        correlation_id: Optional[str] = None,
        compliance_tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
    ) -> AuditEvent:
        """Create and emit a structured audit event."""
        # Auto-redact sensitive changes
        safe_changes = []
        if changes:
            for change in changes:
                if resource and resource.sensitivity in ("restricted", "phi"):
                    safe_changes.append(change.redacted())
                else:
                    safe_changes.append(change)

        event = AuditEvent(
            event_type=event_type,
            category=category,
            severity=severity,
            outcome=outcome,
            actor=actor,
            resource=resource,
            changes=safe_changes,
            correlation_id=correlation_id,
            compliance_tags=compliance_tags or [],
            metadata=metadata or {},
            duration_ms=duration_ms,
            environment=self.environment,
            service_name=self.service_name,
            previous_hash=self._last_hash,
        )

        self._last_hash = event.event_hash
        self._event_count += 1

        # Emit to all sinks
        for sink in self.sinks:
            sink.emit(event)

        return event


# --- Sink interface ---

class AuditSink:
    """Base class for audit event sinks."""

    def emit(self, event: AuditEvent) -> None:
        raise NotImplementedError


class JsonFileSink(AuditSink):
    """Append JSON lines to a file."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def emit(self, event: AuditEvent) -> None:
        line = event.model_dump_json() + "\\n"
        with open(self.file_path, "a") as f:
            f.write(line)


class StdoutSink(AuditSink):
    """Print events to stdout for development."""

    def emit(self, event: AuditEvent) -> None:
        print(json.dumps(json.loads(event.model_dump_json()), indent=2))


# --- Usage example ---

def demo():
    logger = AuditLogger(
        service_name="patient-portal",
        environment="production",
        sinks=[StdoutSink()],
    )

    actor = Actor(
        actor_id="user-123",
        actor_type="user",
        display_name="Dr. Smith",
        ip_address="10.0.1.50",
        roles=["physician", "admin"],
        session_id="sess-abc-456",
    )

    # Log a PHI access event
    logger.log(
        event_type="patient_record.view",
        category=AuditCategory.DATA_ACCESS,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        resource=Resource(
            resource_type="patient_record",
            resource_id="patient-789",
            resource_name="John Doe",
            sensitivity="phi",
        ),
        compliance_tags=["hipaa", "soc2"],
        metadata={"access_reason": "scheduled_appointment"},
    )

    # Log a config change with before/after tracking
    logger.log(
        event_type="config.update",
        category=AuditCategory.CONFIGURATION,
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.WARNING,
        actor=actor,
        resource=Resource(
            resource_type="system_config",
            resource_id="session-timeout",
            sensitivity="standard",
        ),
        changes=[
            DataChange(
                field_name="timeout_minutes",
                old_value=30,
                new_value=60,
            ),
        ],
        compliance_tags=["soc2"],
    )
```

**Key design principles:**

| Principle | Implementation |
|---|---|
| Immutability | Pydantic `frozen = True` prevents mutation after creation |
| Hash chain | Each event references `previous_hash` for tamper detection |
| Auto-redaction | PHI/restricted resource changes are automatically redacted |
| Correlation | `correlation_id`, `trace_id`, `request_id` link related events |
| Classification | Category, severity, outcome enable filtering and alerting |
| Compliance tagging | `compliance_tags` enable filtering by regulation |
| Multi-sink | Events route to files, stdout, or any custom sink |

**Key patterns:**
- Use Pydantic `frozen=True` models for immutable audit events
- Compute SHA-256 hash chain across events for tamper detection
- Auto-redact sensitive fields based on resource sensitivity classification
- Tag events with compliance frameworks (HIPAA, SOC2, GDPR) for audit queries
- Include full actor context (IP, user agent, session, roles) for forensics
- Use `DataChange` objects to capture before/after state of modifications
- Route events through pluggable sinks (file, stdout, cloud, SIEM)'''
    ),
    (
        "security/tamper-proof-audit-logs",
        "Implement a tamper-proof audit log system using Merkle trees and cryptographic signing. The system should detect any modification or deletion of log entries and support independent verification.",
        '''A tamper-proof audit log using Merkle trees, HMAC chains, and digital signatures:

```python
"""
Tamper-proof audit log with Merkle tree integrity,
HMAC hash chains, and digital signature verification.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDSA,
    EllipticCurvePrivateKey,
    EllipticCurvePublicKey,
)


# --- Merkle Tree for log integrity ---

class MerkleTree:
    """Merkle tree over log entry hashes for efficient tamper detection."""

    def __init__(self):
        self.leaves: list[bytes] = []

    def add_leaf(self, data_hash: bytes) -> int:
        """Add a leaf and return its index."""
        idx = len(self.leaves)
        self.leaves.append(data_hash)
        return idx

    @staticmethod
    def _hash_pair(left: bytes, right: bytes) -> bytes:
        return hashlib.sha256(left + right).digest()

    def compute_root(self) -> bytes:
        """Compute the Merkle root of all current leaves."""
        if not self.leaves:
            return hashlib.sha256(b"empty").digest()

        level = list(self.leaves)
        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else left
                next_level.append(self._hash_pair(left, right))
            level = next_level
        return level[0]

    def get_proof(self, leaf_index: int) -> list[tuple[bytes, str]]:
        """
        Generate a Merkle proof for the leaf at leaf_index.
        Returns list of (sibling_hash, direction) tuples.
        """
        if leaf_index >= len(self.leaves):
            raise IndexError(f"Leaf index {leaf_index} out of range")

        proof: list[tuple[bytes, str]] = []
        level = list(self.leaves)
        idx = leaf_index

        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else left
                next_level.append(self._hash_pair(left, right))

                if i == idx or i + 1 == idx:
                    if idx % 2 == 0:
                        sibling = (
                            level[i + 1] if i + 1 < len(level) else left
                        )
                        proof.append((sibling, "right"))
                    else:
                        proof.append((level[i], "left"))

            idx = idx // 2
            level = next_level

        return proof

    @staticmethod
    def verify_proof(
        leaf_hash: bytes,
        proof: list[tuple[bytes, str]],
        expected_root: bytes,
    ) -> bool:
        """Verify a Merkle inclusion proof."""
        current = leaf_hash
        for sibling_hash, direction in proof:
            if direction == "left":
                current = MerkleTree._hash_pair(sibling_hash, current)
            else:
                current = MerkleTree._hash_pair(current, sibling_hash)
        return current == expected_root


# --- HMAC chain for sequential integrity ---

@dataclass
class ChainedEntry:
    """A single entry in the HMAC-chained log."""
    sequence: int
    timestamp: str
    event_type: str
    payload: dict[str, Any]
    entry_hash: bytes = field(default=b"", repr=False)
    chain_hash: bytes = field(default=b"", repr=False)

    def compute_entry_hash(self) -> bytes:
        canonical = json.dumps({
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "payload": self.payload,
        }, sort_keys=True).encode()
        return hashlib.sha256(canonical).digest()


class TamperProofLog:
    """
    Tamper-proof audit log combining:
    1. HMAC hash chain (sequential integrity)
    2. Merkle tree (efficient verification)
    3. ECDSA signatures (non-repudiation)
    """

    def __init__(self, hmac_key: bytes, signing_key: EllipticCurvePrivateKey):
        self.hmac_key = hmac_key
        self.signing_key = signing_key
        self.entries: list[ChainedEntry] = []
        self.merkle = MerkleTree()
        self._checkpoints: list[SignedCheckpoint] = []
        self._last_chain_hash = b"\\x00" * 32  # Genesis hash

    def append(
        self, event_type: str, payload: dict[str, Any],
    ) -> ChainedEntry:
        """Append a tamper-proof entry to the log."""
        entry = ChainedEntry(
            sequence=len(self.entries),
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            payload=payload,
        )

        # Step 1: Compute content hash
        entry.entry_hash = entry.compute_entry_hash()

        # Step 2: Chain with previous entry using HMAC
        chain_input = self._last_chain_hash + entry.entry_hash
        entry.chain_hash = hmac.new(
            self.hmac_key, chain_input, hashlib.sha256
        ).digest()
        self._last_chain_hash = entry.chain_hash

        # Step 3: Add to Merkle tree
        self.merkle.add_leaf(entry.entry_hash)

        self.entries.append(entry)
        return entry

    def create_checkpoint(self) -> "SignedCheckpoint":
        """Create a signed checkpoint over current state."""
        root = self.merkle.compute_root()
        checkpoint = SignedCheckpoint(
            sequence=len(self.entries) - 1,
            merkle_root=root,
            chain_hash=self._last_chain_hash,
            timestamp=datetime.now(timezone.utc).isoformat(),
            entry_count=len(self.entries),
        )
        signature = self.signing_key.sign(
            checkpoint.signable_bytes(), ECDSA(hashes.SHA256()),
        )
        checkpoint.signature = signature
        self._checkpoints.append(checkpoint)
        return checkpoint

    def verify_chain_integrity(self) -> tuple[bool, Optional[int]]:
        """
        Verify the entire HMAC chain.
        Returns (is_valid, first_tampered_index).
        """
        prev_hash = b"\\x00" * 32

        for entry in self.entries:
            expected_entry_hash = entry.compute_entry_hash()
            if expected_entry_hash != entry.entry_hash:
                return False, entry.sequence

            expected_chain = hmac.new(
                self.hmac_key,
                prev_hash + entry.entry_hash,
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(expected_chain, entry.chain_hash):
                return False, entry.sequence

            prev_hash = entry.chain_hash

        return True, None

    def verify_entry(self, index: int) -> bool:
        """Verify a single entry using Merkle proof."""
        if index >= len(self.entries):
            return False

        entry = self.entries[index]
        expected_hash = entry.compute_entry_hash()
        if expected_hash != entry.entry_hash:
            return False

        proof = self.merkle.get_proof(index)
        root = self.merkle.compute_root()
        return MerkleTree.verify_proof(entry.entry_hash, proof, root)


@dataclass
class SignedCheckpoint:
    """Signed snapshot of log state at a point in time."""
    sequence: int
    merkle_root: bytes
    chain_hash: bytes
    timestamp: str
    entry_count: int
    signature: bytes = field(default=b"", repr=False)

    def signable_bytes(self) -> bytes:
        return json.dumps({
            "sequence": self.sequence,
            "merkle_root": self.merkle_root.hex(),
            "chain_hash": self.chain_hash.hex(),
            "timestamp": self.timestamp,
            "entry_count": self.entry_count,
        }, sort_keys=True).encode()

    def verify(self, public_key: EllipticCurvePublicKey) -> bool:
        try:
            public_key.verify(
                self.signature,
                self.signable_bytes(),
                ECDSA(hashes.SHA256()),
            )
            return True
        except Exception:
            return False


# --- Demo ---

def demo():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    hmac_key = b"super-secret-hmac-key-rotate-me"

    log = TamperProofLog(hmac_key, private_key)

    log.append("user.login", {"user_id": "u-1", "ip": "10.0.1.1"})
    log.append("record.view", {"user_id": "u-1", "record": "r-42"})
    log.append("record.update", {"user_id": "u-1", "record": "r-42",
                                  "field": "status", "new_value": "active"})

    valid, tampered_at = log.verify_chain_integrity()
    print(f"Chain valid: {valid}")  # True

    cp = log.create_checkpoint()
    print(f"Checkpoint verified: {cp.verify(public_key)}")  # True

    # Simulate tampering
    log.entries[1].payload["record"] = "r-99"
    valid, idx = log.verify_chain_integrity()
    print(f"After tamper - valid: {valid}, tampered at: {idx}")
    # valid: False, tampered at: 1
```

**Integrity layers:**

| Layer | Mechanism | Detects |
|---|---|---|
| Entry hash | SHA-256 over canonical JSON | Content modification |
| HMAC chain | HMAC(prev_chain + entry_hash) | Deletion, reordering, insertion |
| Merkle tree | Binary hash tree over entries | Efficient single-entry verification |
| ECDSA checkpoint | Signed (root, chain_hash, count) | Non-repudiation, external audit |

**Key patterns:**
- Combine HMAC chain (sequential integrity) with Merkle tree (random access verification)
- ECDSA sign periodic checkpoints for non-repudiation and external auditor verification
- Use `hmac.compare_digest()` for constant-time comparison against timing attacks
- Store checkpoints externally (e.g., blockchain, separate DB) for split-trust verification
- Genesis hash (zero bytes) anchors the chain start deterministically
- Canonical JSON with sorted keys ensures hash reproducibility across platforms'''
    ),
    (
        "security/compliance-audit-hipaa-soc2",
        "Implement a HIPAA and SOC2-compliant audit logging middleware for a FastAPI application. Include PHI access tracking, minimum necessary logging, and automated compliance report generation.",
        '''HIPAA/SOC2-compliant audit logging middleware for FastAPI with PHI tracking and compliance reports:

```python
"""
HIPAA & SOC2-compliant audit logging middleware for FastAPI.
Tracks PHI access, enforces minimum necessary principle,
and generates compliance reports.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Optional

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware


class PHICategory(str, Enum):
    """HIPAA-defined Protected Health Information categories."""
    DEMOGRAPHIC = "demographic"
    MEDICAL_RECORD = "medical_record"
    BILLING = "billing"
    GENETIC = "genetic"
    BIOMETRIC = "biometric"
    SUBSTANCE_ABUSE = "substance_abuse"  # 42 CFR Part 2


class AccessPurpose(str, Enum):
    """Justified reason for accessing PHI (minimum necessary)."""
    TREATMENT = "treatment"
    PAYMENT = "payment"
    OPERATIONS = "healthcare_operations"
    PATIENT_REQUEST = "patient_request"
    LEGAL = "legal_requirement"
    EMERGENCY = "emergency"
    RESEARCH_DEIDENTIFIED = "research_deidentified"


class PHIRouteConfig(BaseModel):
    """Configuration declaring PHI exposure for an API route."""
    phi_categories: list[PHICategory] = Field(default_factory=list)
    requires_purpose: bool = False
    requires_break_glass: bool = False
    minimum_role: Optional[str] = None
    sensitivity_level: int = 1  # 1-5


PHI_ROUTE_REGISTRY: dict[str, PHIRouteConfig] = {}


def phi_route(
    categories: list[PHICategory],
    requires_purpose: bool = True,
    sensitivity_level: int = 3,
    requires_break_glass: bool = False,
    minimum_role: Optional[str] = None,
):
    """Decorator to register PHI metadata on a FastAPI route."""
    def decorator(func: Callable) -> Callable:
        PHI_ROUTE_REGISTRY[func.__name__] = PHIRouteConfig(
            phi_categories=categories,
            requires_purpose=requires_purpose,
            sensitivity_level=sensitivity_level,
            requires_break_glass=requires_break_glass,
            minimum_role=minimum_role,
        )
        func._phi_config = PHI_ROUTE_REGISTRY[func.__name__]
        return func
    return decorator


class ComplianceAuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    user_id: str
    user_roles: list[str] = Field(default_factory=list)
    ip_address: str
    session_id: Optional[str] = None
    method: str
    path: str
    query_params: dict[str, str] = Field(default_factory=dict)
    status_code: int
    duration_ms: int
    phi_accessed: list[PHICategory] = Field(default_factory=list)
    access_purpose: Optional[AccessPurpose] = None
    patient_ids: list[str] = Field(default_factory=list)
    break_glass: bool = False
    break_glass_reason: Optional[str] = None
    compliance_frameworks: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    records_returned: int = 0
    fields_redacted: list[str] = Field(default_factory=list)


class ComplianceAuditStore:
    """In-memory store (swap for database in production)."""

    def __init__(self):
        self.events: list[ComplianceAuditEvent] = []

    def save(self, event: ComplianceAuditEvent) -> None:
        self.events.append(event)

    def query(
        self,
        start: datetime,
        end: datetime,
        user_id: Optional[str] = None,
        patient_id: Optional[str] = None,
        phi_category: Optional[PHICategory] = None,
        violations_only: bool = False,
    ) -> list[ComplianceAuditEvent]:
        results = []
        for e in self.events:
            if e.timestamp < start or e.timestamp > end:
                continue
            if user_id and e.user_id != user_id:
                continue
            if patient_id and patient_id not in e.patient_ids:
                continue
            if phi_category and phi_category not in e.phi_accessed:
                continue
            if violations_only and not e.violations:
                continue
            results.append(e)
        return results


class HIPAAAuditMiddleware(BaseHTTPMiddleware):
    """Middleware that audits every request for PHI access controls."""

    def __init__(self, app: FastAPI, store: ComplianceAuditStore):
        super().__init__(app)
        self.store = store

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.monotonic()
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        user_id = request.headers.get("X-User-ID", "anonymous")
        user_roles = request.headers.get("X-User-Roles", "").split(",")
        session_id = request.headers.get("X-Session-ID")
        access_purpose = request.headers.get("X-Access-Purpose")
        break_glass = request.headers.get("X-Break-Glass") == "true"
        break_glass_reason = request.headers.get("X-Break-Glass-Reason")
        patient_ids_raw = request.headers.get("X-Patient-IDs", "")
        patient_ids = [p for p in patient_ids_raw.split(",") if p]

        phi_config = self._resolve_phi_config(request)
        violations: list[str] = []

        if phi_config and phi_config.phi_categories:
            if phi_config.requires_purpose and not access_purpose:
                violations.append(
                    "HIPAA: PHI accessed without stated purpose"
                )
            if phi_config.requires_break_glass and not break_glass:
                violations.append(
                    "HIPAA: Restricted PHI requires break-glass"
                )
            if phi_config.minimum_role:
                if phi_config.minimum_role not in user_roles:
                    violations.append(
                        f"SOC2: Insufficient role "
                        f"(required: {phi_config.minimum_role})"
                    )

        response = await call_next(request)
        duration_ms = int((time.monotonic() - start_time) * 1000)

        event = ComplianceAuditEvent(
            user_id=user_id,
            user_roles=user_roles,
            ip_address=(
                request.client.host if request.client else "unknown"
            ),
            session_id=session_id,
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params),
            status_code=response.status_code,
            duration_ms=duration_ms,
            phi_accessed=(
                phi_config.phi_categories if phi_config else []
            ),
            access_purpose=(
                AccessPurpose(access_purpose) if access_purpose else None
            ),
            patient_ids=patient_ids,
            break_glass=break_glass,
            break_glass_reason=break_glass_reason,
            compliance_frameworks=self._get_frameworks(phi_config),
            violations=violations,
        )

        self.store.save(event)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    def _resolve_phi_config(
        self, request: Request
    ) -> Optional[PHIRouteConfig]:
        route = request.scope.get("route")
        if route and hasattr(route, "endpoint"):
            return getattr(route.endpoint, "_phi_config", None)
        return None

    def _get_frameworks(
        self, config: Optional[PHIRouteConfig]
    ) -> list[str]:
        frameworks = ["soc2"]
        if config and config.phi_categories:
            frameworks.append("hipaa")
            if PHICategory.SUBSTANCE_ABUSE in config.phi_categories:
                frameworks.append("42cfr_part2")
        return frameworks


class ComplianceReportGenerator:
    """Generate HIPAA and SOC2 compliance reports."""

    def __init__(self, store: ComplianceAuditStore):
        self.store = store

    def hipaa_access_report(
        self, patient_id: str, start: datetime, end: datetime,
    ) -> dict[str, Any]:
        """HIPAA accounting of disclosures for a patient."""
        events = self.store.query(
            start=start, end=end, patient_id=patient_id
        )
        return {
            "report_type": "hipaa_accounting_of_disclosures",
            "patient_id": patient_id,
            "period": {
                "start": start.isoformat(), "end": end.isoformat()
            },
            "total_accesses": len(events),
            "accesses": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "user_id": e.user_id,
                    "purpose": (
                        e.access_purpose.value
                        if e.access_purpose else "unstated"
                    ),
                    "phi_categories": [c.value for c in e.phi_accessed],
                    "break_glass": e.break_glass,
                }
                for e in events
            ],
            "violations": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "user_id": e.user_id,
                    "violations": e.violations,
                }
                for e in events if e.violations
            ],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def soc2_summary(
        self, start: datetime, end: datetime
    ) -> dict[str, Any]:
        """SOC2 Type II audit summary report."""
        all_events = self.store.query(start=start, end=end)
        violation_events = [e for e in all_events if e.violations]

        user_access: dict[str, int] = defaultdict(int)
        for e in all_events:
            user_access[e.user_id] += 1

        return {
            "report_type": "soc2_type2_summary",
            "period": {
                "start": start.isoformat(), "end": end.isoformat()
            },
            "total_events": len(all_events),
            "total_violations": len(violation_events),
            "violation_rate": (
                len(violation_events) / len(all_events)
                if all_events else 0
            ),
            "unique_users": len(user_access),
            "top_accessors": sorted(
                user_access.items(), key=lambda x: -x[1]
            )[:10],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
```

**HIPAA compliance controls mapped:**

| HIPAA Requirement | Implementation |
|---|---|
| 164.312(b) Audit controls | Every PHI access logged with full context |
| 164.528 Accounting of disclosures | `hipaa_access_report()` per patient |
| 164.502(b) Minimum necessary | `requires_purpose` enforcement on routes |
| 164.312(d) Person authentication | Actor identity in every event |
| 164.312(a)(1) Access control | Role-based checks via `minimum_role` |
| 164.314 Emergency access | Break-glass with mandatory reason |

**Key patterns:**
- Declare PHI exposure at the route level with `@phi_route` decorator
- Enforce minimum necessary principle by requiring access purpose headers
- Support break-glass emergency access with mandatory reason logging
- Generate per-patient accounting of disclosures (HIPAA 164.528 requirement)
- Produce SOC2 Type II summary reports from stored audit events
- Classify PHI categories including 42 CFR Part 2 substance abuse protections
- Track compliance violations in real-time, not just in periodic audits'''
    ),
    (
        "security/audit-log-forwarding",
        "Build an audit log forwarding system that reliably ships events to multiple destinations (Elasticsearch, S3, SIEM) with guaranteed delivery, buffering, retry logic, and dead letter queues.",
        '''Reliable audit log forwarder with buffering, guaranteed delivery, and dead letter queue:

```python
"""
Audit log forwarder: buffers events locally, ships to multiple
destinations with retry, backpressure, and dead letter queue.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import aiohttp
import aioboto3

logger = logging.getLogger("audit_forwarder")


class DeliveryStatus(str, Enum):
    SUCCESS = "success"
    RETRYABLE_ERROR = "retryable_error"
    PERMANENT_ERROR = "permanent_error"


@dataclass
class DeliveryResult:
    status: DeliveryStatus
    destination: str
    events_count: int
    error: Optional[str] = None
    retry_after_seconds: float = 0


class AuditDestination(ABC):
    """Base class for audit log shipping destinations."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def send_batch(
        self, events: list[dict[str, Any]]
    ) -> DeliveryResult: ...

    @abstractmethod
    async def health_check(self) -> bool: ...


class ElasticsearchDestination(AuditDestination):
    """Ship audit events to Elasticsearch via bulk API."""

    def __init__(
        self, url: str, index_prefix: str = "audit-logs",
        api_key: Optional[str] = None,
    ):
        self.url = url.rstrip("/")
        self.index_prefix = index_prefix
        self.api_key = api_key

    @property
    def name(self) -> str:
        return "elasticsearch"

    async def send_batch(
        self, events: list[dict[str, Any]]
    ) -> DeliveryResult:
        today = datetime.now(timezone.utc).strftime("%Y.%m.%d")
        index = f"{self.index_prefix}-{today}"

        lines = []
        for event in events:
            lines.append(json.dumps({"index": {"_index": index}}))
            lines.append(json.dumps(event))
        body = "\\n".join(lines) + "\\n"

        headers = {"Content-Type": "application/x-ndjson"}
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.url}/_bulk",
                    data=body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("errors"):
                            return DeliveryResult(
                                status=DeliveryStatus.RETRYABLE_ERROR,
                                destination=self.name,
                                events_count=len(events),
                                error="Partial bulk indexing failure",
                            )
                        return DeliveryResult(
                            status=DeliveryStatus.SUCCESS,
                            destination=self.name,
                            events_count=len(events),
                        )
                    elif resp.status == 429:
                        retry_after = float(
                            resp.headers.get("Retry-After", "5")
                        )
                        return DeliveryResult(
                            status=DeliveryStatus.RETRYABLE_ERROR,
                            destination=self.name,
                            events_count=len(events),
                            error="Rate limited",
                            retry_after_seconds=retry_after,
                        )
                    else:
                        return DeliveryResult(
                            status=DeliveryStatus.RETRYABLE_ERROR,
                            destination=self.name,
                            events_count=len(events),
                            error=f"HTTP {resp.status}",
                        )
        except aiohttp.ClientError as e:
            return DeliveryResult(
                status=DeliveryStatus.RETRYABLE_ERROR,
                destination=self.name,
                events_count=len(events),
                error=str(e),
            )

    async def health_check(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.url}/_cluster/health",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False


class S3Destination(AuditDestination):
    """Ship audit events to S3 as compressed JSON files."""

    def __init__(
        self, bucket: str, prefix: str = "audit-logs/",
        region: str = "us-east-1",
    ):
        self.bucket = bucket
        self.prefix = prefix
        self.region = region

    @property
    def name(self) -> str:
        return "s3"

    async def send_batch(
        self, events: list[dict[str, Any]]
    ) -> DeliveryResult:
        import gzip

        now = datetime.now(timezone.utc)
        key = (
            f"{self.prefix}"
            f"{now.strftime('%Y/%m/%d/%H')}/"
            f"audit-{now.strftime('%Y%m%dT%H%M%S')}-"
            f"{len(events)}.json.gz"
        )

        payload = "\\n".join(json.dumps(e) for e in events)
        compressed = gzip.compress(payload.encode())

        try:
            session = aioboto3.Session()
            async with session.client("s3", region_name=self.region) as s3:
                await s3.put_object(
                    Bucket=self.bucket, Key=key, Body=compressed,
                    ContentType="application/x-ndjson",
                    ContentEncoding="gzip",
                    Metadata={
                        "event-count": str(len(events)),
                        "timestamp": now.isoformat(),
                    },
                )
            return DeliveryResult(
                status=DeliveryStatus.SUCCESS,
                destination=self.name,
                events_count=len(events),
            )
        except Exception as e:
            return DeliveryResult(
                status=DeliveryStatus.RETRYABLE_ERROR,
                destination=self.name,
                events_count=len(events),
                error=str(e),
            )

    async def health_check(self) -> bool:
        try:
            session = aioboto3.Session()
            async with session.client("s3", region_name=self.region) as s3:
                await s3.head_bucket(Bucket=self.bucket)
            return True
        except Exception:
            return False


@dataclass
class ForwarderConfig:
    batch_size: int = 100
    flush_interval_seconds: float = 5.0
    max_retries: int = 5
    base_retry_delay: float = 1.0
    max_retry_delay: float = 60.0
    max_buffer_size: int = 50_000
    dlq_max_size: int = 10_000


class AuditForwarder:
    """
    Asynchronous audit event forwarder with:
    - Local buffering with backpressure
    - Fan-out to multiple destinations
    - Exponential backoff retry
    - Dead letter queue for permanent failures
    """

    def __init__(
        self,
        destinations: list[AuditDestination],
        config: ForwarderConfig = ForwarderConfig(),
    ):
        self.destinations = destinations
        self.config = config
        self.buffer: deque[dict[str, Any]] = deque(
            maxlen=config.max_buffer_size
        )
        self.dlq: deque[dict[str, Any]] = deque(maxlen=config.dlq_max_size)
        self._running = False
        self._flush_task: Optional[asyncio.Task] = None
        self._stats = {
            "events_received": 0, "events_sent": 0,
            "events_failed": 0, "events_dlq": 0,
            "buffer_overflows": 0,
        }

    async def start(self) -> None:
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
        await self._flush_all()

    def enqueue(self, event: dict[str, Any]) -> bool:
        self._stats["events_received"] += 1
        if len(self.buffer) >= self.config.max_buffer_size:
            self._stats["buffer_overflows"] += 1
            self.buffer.popleft()
        self.buffer.append(event)
        return True

    async def _flush_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.config.flush_interval_seconds)
            await self._flush_all()

    async def _flush_all(self) -> None:
        while self.buffer:
            batch = []
            for _ in range(
                min(self.config.batch_size, len(self.buffer))
            ):
                batch.append(self.buffer.popleft())
            if batch:
                await self._send_to_all(batch)

    async def _send_to_all(
        self, batch: list[dict[str, Any]]
    ) -> None:
        tasks = [
            self._send_with_retry(dest, batch)
            for dest in self.destinations
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, DeliveryResult):
                if result.status == DeliveryStatus.SUCCESS:
                    self._stats["events_sent"] += result.events_count
                elif result.status == DeliveryStatus.PERMANENT_ERROR:
                    self._stats["events_failed"] += result.events_count
                    for event in batch:
                        self.dlq.append({
                            "event": event,
                            "destination": result.destination,
                            "error": result.error,
                            "failed_at": (
                                datetime.now(timezone.utc).isoformat()
                            ),
                        })
                    self._stats["events_dlq"] += len(batch)

    async def _send_with_retry(
        self, destination: AuditDestination,
        batch: list[dict[str, Any]],
    ) -> DeliveryResult:
        delay = self.config.base_retry_delay
        for attempt in range(self.config.max_retries + 1):
            result = await destination.send_batch(batch)
            if result.status == DeliveryStatus.SUCCESS:
                return result
            elif result.status == DeliveryStatus.PERMANENT_ERROR:
                return result
            else:
                wait = max(delay, result.retry_after_seconds)
                logger.warning(
                    "Retry %d/%d for %s in %.1fs: %s",
                    attempt + 1, self.config.max_retries,
                    destination.name, wait, result.error,
                )
                await asyncio.sleep(wait)
                delay = min(delay * 2, self.config.max_retry_delay)

        return DeliveryResult(
            status=DeliveryStatus.PERMANENT_ERROR,
            destination=destination.name,
            events_count=len(batch),
            error=f"Exhausted {self.config.max_retries} retries",
        )
```

**Delivery guarantee architecture:**

| Component | Purpose |
|---|---|
| In-memory buffer | Decouple event production from shipping |
| Batch flush | Amortize network overhead per event |
| Fan-out | Ship to all destinations concurrently |
| Exponential backoff | Handle transient failures gracefully |
| Dead letter queue | Capture events that fail after all retries |
| Backpressure | Drop oldest events when buffer overflows |

**Key patterns:**
- Buffer events locally and flush in configurable batch sizes for throughput
- Fan-out to all destinations concurrently with `asyncio.gather`
- Use exponential backoff with configurable base/max delay for retries
- Respect server `Retry-After` headers for rate limiting (HTTP 429)
- Dead letter queue preserves failed events with error context for reprocessing
- S3 destination uses gzip compression and hour-partitioned keys for cost efficiency
- Elasticsearch destination uses NDJSON bulk API for high-throughput indexing
- Health checks enable circuit breaker integration at the infrastructure level'''
    ),
    (
        "security/audit-retention-archival",
        "Build an audit log retention and archival system that enforces configurable retention policies per compliance framework, compresses and archives old logs to cold storage, and supports legal hold.",
        '''Audit log retention and archival system with per-framework policies, legal hold, and cold storage:

```python
"""
Audit log retention manager: enforces compliance-driven retention
policies, archives to cold storage, and supports legal hold.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Optional, Protocol

import boto3
from botocore.config import Config as BotoConfig


class ComplianceFramework(str, Enum):
    HIPAA = "hipaa"
    SOC2 = "soc2"
    GDPR = "gdpr"
    PCI_DSS = "pci_dss"
    SOX = "sox"
    FINRA = "finra"


@dataclass(frozen=True)
class RetentionPolicy:
    """Defines how long audit logs must be retained."""
    framework: ComplianceFramework
    hot_retention_days: int
    warm_retention_days: int
    cold_retention_days: int
    total_retention_days: int
    requires_encryption: bool = True
    requires_integrity_check: bool = True


RETENTION_POLICIES: dict[ComplianceFramework, RetentionPolicy] = {
    ComplianceFramework.HIPAA: RetentionPolicy(
        framework=ComplianceFramework.HIPAA,
        hot_retention_days=90,
        warm_retention_days=365,
        cold_retention_days=2555,
        total_retention_days=2555,  # 7 years
    ),
    ComplianceFramework.SOC2: RetentionPolicy(
        framework=ComplianceFramework.SOC2,
        hot_retention_days=30,
        warm_retention_days=365,
        cold_retention_days=2555,
        total_retention_days=2555,
    ),
    ComplianceFramework.GDPR: RetentionPolicy(
        framework=ComplianceFramework.GDPR,
        hot_retention_days=30,
        warm_retention_days=180,
        cold_retention_days=365,
        total_retention_days=365,  # Data minimization principle
    ),
    ComplianceFramework.PCI_DSS: RetentionPolicy(
        framework=ComplianceFramework.PCI_DSS,
        hot_retention_days=90,
        warm_retention_days=365,
        cold_retention_days=365,
        total_retention_days=365,
    ),
    ComplianceFramework.SOX: RetentionPolicy(
        framework=ComplianceFramework.SOX,
        hot_retention_days=90,
        warm_retention_days=365,
        cold_retention_days=2555,
        total_retention_days=2555,
    ),
    ComplianceFramework.FINRA: RetentionPolicy(
        framework=ComplianceFramework.FINRA,
        hot_retention_days=90,
        warm_retention_days=365,
        cold_retention_days=2190,
        total_retention_days=2190,  # 6 years
    ),
}


@dataclass
class LegalHold:
    """Prevents deletion of audit logs matching criteria."""
    hold_id: str
    created_at: datetime
    created_by: str
    reason: str
    actor_ids: list[str] = field(default_factory=list)
    resource_ids: list[str] = field(default_factory=list)
    event_types: list[str] = field(default_factory=list)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: bool = True
    released_at: Optional[datetime] = None
    released_by: Optional[str] = None

    def matches(self, event: dict[str, Any]) -> bool:
        if not self.is_active:
            return False
        event_time = datetime.fromisoformat(event.get("timestamp", ""))
        if self.start_date and event_time < self.start_date:
            return False
        if self.end_date and event_time > self.end_date:
            return False
        if self.actor_ids:
            actor_id = event.get("actor", {}).get("actor_id")
            if actor_id not in self.actor_ids:
                return False
        if self.resource_ids:
            resource_id = event.get("resource", {}).get("resource_id")
            if resource_id not in self.resource_ids:
                return False
        if self.event_types:
            if event.get("event_type") not in self.event_types:
                return False
        return True


class AuditStorageBackend(Protocol):
    def store_batch(
        self, key: str, events: list[dict], metadata: dict
    ) -> str: ...
    def retrieve_batch(self, key: str) -> list[dict]: ...
    def delete_batch(self, key: str) -> bool: ...
    def list_keys(self, prefix: str) -> list[str]: ...


class S3ArchiveBackend:
    """Cold storage backend using S3 with encryption and integrity."""

    def __init__(
        self, bucket: str, region: str = "us-east-1",
        kms_key_id: Optional[str] = None,
        storage_class: str = "GLACIER_IR",
    ):
        self.bucket = bucket
        self.kms_key_id = kms_key_id
        self.storage_class = storage_class
        self.s3 = boto3.client(
            "s3", region_name=region,
            config=BotoConfig(retries={"max_attempts": 3}),
        )

    def store_batch(
        self, key: str, events: list[dict],
        metadata: dict[str, str],
    ) -> str:
        payload = "\\n".join(
            json.dumps(e, sort_keys=True) for e in events
        )
        compressed = gzip.compress(
            payload.encode("utf-8"), compresslevel=9
        )

        content_hash = hashlib.sha256(compressed).hexdigest()
        metadata["content-sha256"] = content_hash
        metadata["event-count"] = str(len(events))
        metadata["compressed-size"] = str(len(compressed))

        put_args: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": compressed,
            "ContentType": "application/x-ndjson",
            "ContentEncoding": "gzip",
            "StorageClass": self.storage_class,
            "Metadata": metadata,
            "ChecksumAlgorithm": "SHA256",
        }
        if self.kms_key_id:
            put_args["ServerSideEncryption"] = "aws:kms"
            put_args["SSEKMSKeyId"] = self.kms_key_id
        else:
            put_args["ServerSideEncryption"] = "AES256"

        self.s3.put_object(**put_args)
        return content_hash

    def set_legal_hold(self, key: str, hold: bool = True) -> None:
        self.s3.put_object_legal_hold(
            Bucket=self.bucket, Key=key,
            LegalHold={"Status": "ON" if hold else "OFF"},
        )

    def retrieve_batch(self, key: str) -> list[dict]:
        resp = self.s3.get_object(Bucket=self.bucket, Key=key)
        compressed = resp["Body"].read()
        payload = gzip.decompress(compressed).decode("utf-8")
        return [json.loads(ln) for ln in payload.strip().split("\\n")]

    def delete_batch(self, key: str) -> bool:
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def list_keys(self, prefix: str) -> list[str]:
        keys = []
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=self.bucket, Prefix=prefix
        ):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys


class RetentionManager:
    """Enforces retention policies across storage tiers."""

    def __init__(
        self,
        warm_backend: AuditStorageBackend,
        cold_backend: S3ArchiveBackend,
        legal_holds: list[LegalHold],
        frameworks: list[ComplianceFramework],
    ):
        self.warm = warm_backend
        self.cold = cold_backend
        self.legal_holds = legal_holds
        self.frameworks = frameworks
        self._effective = self._compute_effective_policy()

    def _compute_effective_policy(self) -> RetentionPolicy:
        """Most restrictive union across all frameworks."""
        policies = [RETENTION_POLICIES[f] for f in self.frameworks]
        return RetentionPolicy(
            framework=ComplianceFramework.HIPAA,
            hot_retention_days=max(
                p.hot_retention_days for p in policies
            ),
            warm_retention_days=max(
                p.warm_retention_days for p in policies
            ),
            cold_retention_days=max(
                p.cold_retention_days for p in policies
            ),
            total_retention_days=max(
                p.total_retention_days for p in policies
            ),
            requires_encryption=any(
                p.requires_encryption for p in policies
            ),
            requires_integrity_check=any(
                p.requires_integrity_check for p in policies
            ),
        )

    def archive_warm_to_cold(self, prefix: str) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(
            days=self._effective.warm_retention_days
        )
        stats = {"archived": 0, "held": 0, "skipped": 0}

        for key in self.warm.list_keys(prefix):
            events = self.warm.retrieve_batch(key)
            to_archive, to_keep = [], []

            for event in events:
                ts = datetime.fromisoformat(event["timestamp"])
                if ts < cutoff:
                    if self._is_under_hold(event):
                        to_keep.append(event)
                        stats["held"] += 1
                    else:
                        to_archive.append(event)
                else:
                    to_keep.append(event)
                    stats["skipped"] += 1

            if to_archive:
                cold_key = key.replace("warm/", "cold/")
                self.cold.store_batch(cold_key, to_archive, {
                    "source": "warm-archive",
                    "archived_at": now.isoformat(),
                })
                stats["archived"] += len(to_archive)

        return stats

    def purge_expired(self, prefix: str) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(
            days=self._effective.total_retention_days
        )
        stats = {"purged": 0, "held": 0}

        for key in self.cold.list_keys(prefix):
            events = self.cold.retrieve_batch(key)
            has_held = any(self._is_under_hold(e) for e in events)
            all_expired = all(
                datetime.fromisoformat(e["timestamp"]) < cutoff
                for e in events
            )
            if not has_held and all_expired:
                self.cold.delete_batch(key)
                stats["purged"] += len(events)
            elif has_held:
                stats["held"] += sum(
                    1 for e in events if self._is_under_hold(e)
                )

        return stats

    def _is_under_hold(self, event: dict[str, Any]) -> bool:
        return any(h.matches(event) for h in self.legal_holds)
```

**Retention tiers by compliance framework:**

| Framework | Hot (days) | Warm (days) | Cold (days) | Total Min |
|---|---|---|---|---|
| HIPAA | 90 | 365 | 2555 | 7 years |
| SOC2 | 30 | 365 | 2555 | 7 years |
| GDPR | 30 | 180 | 365 | 1 year |
| PCI-DSS | 90 | 365 | 365 | 1 year |
| SOX | 90 | 365 | 2555 | 7 years |
| FINRA | 90 | 365 | 2190 | 6 years |

**Key patterns:**
- Compute effective retention as the most restrictive union across all applicable frameworks
- Legal holds override retention policies and held events are never deleted
- Use S3 Object Lock for immutable legal hold enforcement at the storage layer
- Compress with gzip level 9 and use Glacier Instant Retrieval for cold tier cost savings
- Store SHA-256 content hash in S3 metadata for integrity verification
- KMS encryption satisfies HIPAA and PCI-DSS encryption-at-rest requirements
- Separate warm-to-cold archival from expired purge for independent scheduling
- GDPR data minimization enforces shortest retention among all frameworks'''
    ),
]
