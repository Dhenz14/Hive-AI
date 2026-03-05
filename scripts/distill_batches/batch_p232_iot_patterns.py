"""IoT programming patterns — MQTT pub/sub, device shadows, OTA updates, edge processing, time-series ingestion, device authentication."""

PAIRS = [
    (
        "iot/mqtt-pubsub",
        "Implement a production MQTT pub/sub system with topic hierarchies, QoS levels, retained messages, last-will-and-testament, and automatic reconnection with exponential backoff for IoT device fleets.",
        '''Production MQTT pub/sub system for IoT device fleets:

```python
# mqtt_fleet.py — MQTT fleet manager with QoS, LWT, retained messages, reconnection
import asyncio
import json
import ssl
import time
import logging
import hashlib
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Awaitable, Protocol
from contextlib import asynccontextmanager
from collections import defaultdict

import aiomqtt
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class QoS(IntEnum):
    AT_MOST_ONCE = 0   # Fire-and-forget telemetry
    AT_LEAST_ONCE = 1  # Commands and alerts
    EXACTLY_ONCE = 2   # Provisioning and OTA triggers


class TopicScheme:
    """Hierarchical topic structure for device fleet management.

    Pattern: {org}/{site}/{device_type}/{device_id}/{channel}
    Example: acme/factory-1/sensor/temp-042/telemetry
    """
    @staticmethod
    def telemetry(org: str, site: str, dtype: str, did: str) -> str:
        return f"{org}/{site}/{dtype}/{did}/telemetry"

    @staticmethod
    def command(org: str, site: str, dtype: str, did: str) -> str:
        return f"{org}/{site}/{dtype}/{did}/command"

    @staticmethod
    def status(org: str, site: str, dtype: str, did: str) -> str:
        return f"{org}/{site}/{dtype}/{did}/status"

    @staticmethod
    def ota(org: str, site: str, dtype: str, did: str) -> str:
        return f"{org}/{site}/{dtype}/{did}/ota"

    @staticmethod
    def wildcard_site(org: str, site: str) -> str:
        return f"{org}/{site}/+/+/telemetry"

    @staticmethod
    def wildcard_all(org: str) -> str:
        return f"{org}/#"


@dataclass
class MQTTConfig:
    broker_host: str
    broker_port: int = 8883
    client_id: str = ""
    username: str | None = None
    password: str | None = None
    keepalive: int = 60
    clean_session: bool = True
    ca_cert: str = "/etc/ssl/certs/mqtt-ca.pem"
    client_cert: str | None = None
    client_key: str | None = None
    reconnect_base: float = 1.0
    reconnect_max: float = 120.0
    lwt_topic: str | None = None
    lwt_payload: str = '{"status":"offline","ts":0}'
    lwt_qos: QoS = QoS.AT_LEAST_ONCE
    lwt_retain: bool = True


MessageHandler = Callable[[aiomqtt.Message], Awaitable[None]]


class FleetMQTTClient:
    """Production MQTT client with fleet-scale features."""

    def __init__(self, config: MQTTConfig):
        self.config = config
        self._subscriptions: dict[str, list[tuple[QoS, MessageHandler]]] = defaultdict(list)
        self._reconnect_delay = config.reconnect_base
        self._connected = asyncio.Event()
        self._shutdown = asyncio.Event()
        self._message_count = 0
        self._error_count = 0

    def _build_tls_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context(cafile=self.config.ca_cert)
        if self.config.client_cert and self.config.client_key:
            ctx.load_cert_chain(self.config.client_cert, self.config.client_key)
        ctx.check_hostname = True
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        return ctx

    def subscribe(self, topic: str, qos: QoS = QoS.AT_LEAST_ONCE):
        """Decorator to register a message handler for a topic pattern."""
        def decorator(func: MessageHandler) -> MessageHandler:
            self._subscriptions[topic].append((qos, func))
            return func
        return decorator

    async def publish(
        self,
        client: aiomqtt.Client,
        topic: str,
        payload: dict[str, Any],
        qos: QoS = QoS.AT_LEAST_ONCE,
        retain: bool = False,
    ):
        message = json.dumps({**payload, "_ts": time.time()})
        await client.publish(topic, message.encode(), qos=qos.value, retain=retain)
        self._message_count += 1

    async def _dispatch(self, message: aiomqtt.Message):
        topic = str(message.topic)
        for pattern, handlers in self._subscriptions.items():
            if aiomqtt.Topic(topic).matches(pattern):
                for _qos, handler in handlers:
                    try:
                        await handler(message)
                    except Exception:
                        self._error_count += 1
                        logger.exception(f"Handler error on {topic}")

    async def run(self):
        """Main loop with automatic reconnection and exponential backoff."""
        tls_ctx = self._build_tls_context()

        while not self._shutdown.is_set():
            try:
                async with aiomqtt.Client(
                    hostname=self.config.broker_host,
                    port=self.config.broker_port,
                    identifier=self.config.client_id,
                    username=self.config.username,
                    password=self.config.password,
                    keepalive=self.config.keepalive,
                    clean_session=self.config.clean_session,
                    tls_context=tls_ctx,
                    will=aiomqtt.Will(
                        topic=self.config.lwt_topic or f"devices/{self.config.client_id}/status",
                        payload=self.config.lwt_payload.encode(),
                        qos=self.config.lwt_qos.value,
                        retain=self.config.lwt_retain,
                    ) if self.config.lwt_topic else None,
                ) as client:
                    self._connected.set()
                    self._reconnect_delay = self.config.reconnect_base
                    logger.info(f"Connected to {self.config.broker_host}")

                    # Publish online status as retained message
                    await client.publish(
                        f"devices/{self.config.client_id}/status",
                        json.dumps({"status": "online", "ts": time.time()}).encode(),
                        qos=QoS.AT_LEAST_ONCE.value,
                        retain=True,
                    )

                    # Subscribe to all registered topics
                    for topic, handlers in self._subscriptions.items():
                        max_qos = max(h[0] for h in handlers)
                        await client.subscribe(topic, qos=max_qos.value)
                        logger.info(f"Subscribed: {topic} (QoS {max_qos})")

                    # Message dispatch loop
                    async for message in client.messages:
                        await self._dispatch(message)

            except aiomqtt.MqttError as e:
                self._connected.clear()
                logger.warning(f"Disconnected: {e}. Reconnecting in {self._reconnect_delay:.1f}s")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    self.config.reconnect_max,
                )
            except asyncio.CancelledError:
                logger.info("MQTT client shutting down")
                break

    async def stop(self):
        self._shutdown.set()


# Usage example
async def main():
    config = MQTTConfig(
        broker_host="mqtt.example.com",
        client_id="gateway-east-01",
        lwt_topic="devices/gateway-east-01/status",
    )
    fleet = FleetMQTTClient(config)

    @fleet.subscribe("acme/factory-1/+/+/telemetry", QoS.AT_MOST_ONCE)
    async def on_telemetry(msg: aiomqtt.Message):
        data = json.loads(msg.payload)
        logger.info(f"Telemetry from {msg.topic}: {data}")

    @fleet.subscribe("acme/factory-1/+/+/status", QoS.AT_LEAST_ONCE)
    async def on_status(msg: aiomqtt.Message):
        data = json.loads(msg.payload)
        logger.info(f"Status from {msg.topic}: {data}")

    await fleet.run()
```

Key patterns and design decisions:

| Pattern | Purpose | QoS Level |
|---|---|---|
| Hierarchical topics | `org/site/type/id/channel` enables wildcard subscriptions | N/A |
| Retained messages | Device status persists so new subscribers get last known state | QoS 1 |
| Last Will and Testament | Broker publishes offline status when connection drops ungracefully | QoS 1 |
| QoS 0 for telemetry | High-frequency sensor data where occasional loss is acceptable | 0 |
| QoS 1 for commands | Commands must be delivered at least once | 1 |
| QoS 2 for provisioning | Provisioning and OTA triggers must be exactly once | 2 |
| Exponential backoff | Prevents thundering herd on broker restart | N/A |

Critical considerations:
- Always use TLS 1.2+ with mutual TLS (mTLS) for production IoT
- Topic hierarchies should mirror physical topology for efficient wildcard filtering
- Retained messages on status topics let new dashboard connections see current fleet state
- Clean session = False with persistent client IDs enables offline message queuing
- Keep payload sizes small (< 4KB) for constrained devices on cellular networks
'''
    ),
    (
        "iot/device-shadow",
        "Implement a device shadow (digital twin) pattern that synchronizes desired and reported state between cloud and device, with conflict resolution, versioning, and delta computation.",
        '''Device shadow (digital twin) pattern with state synchronization and conflict resolution:

```python
# device_shadow.py — AWS IoT-style device shadow with versioning and deltas
import json
import time
import hashlib
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from copy import deepcopy
from collections.abc import Mapping

import redis.asyncio as redis
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ShadowState(BaseModel):
    """Represents the desired/reported state document."""
    desired: dict[str, Any] = Field(default_factory=dict)
    reported: dict[str, Any] = Field(default_factory=dict)
    delta: dict[str, Any] = Field(default_factory=dict)
    version: int = 0
    timestamp: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConflictResolution(Enum):
    DESIRED_WINS = "desired_wins"       # Cloud overrides device
    REPORTED_WINS = "reported_wins"     # Device overrides cloud
    LATEST_WINS = "latest_wins"         # Most recent timestamp wins
    MERGE = "merge"                     # Deep merge both sides


def compute_delta(desired: dict, reported: dict) -> dict:
    """Compute difference between desired and reported state.

    Returns fields in desired that differ from reported, enabling
    the device to know exactly what needs to change.
    """
    delta = {}
    for key, desired_val in desired.items():
        if key not in reported:
            delta[key] = desired_val
        elif isinstance(desired_val, dict) and isinstance(reported.get(key), dict):
            nested = compute_delta(desired_val, reported[key])
            if nested:
                delta[key] = nested
        elif desired_val != reported.get(key):
            delta[key] = desired_val
    return delta


def deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base, overlay wins on conflicts."""
    result = deepcopy(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class DeviceShadowManager:
    """Manages device shadows with Redis-backed persistence and pub/sub notifications."""

    def __init__(
        self,
        redis_client: redis.Redis,
        conflict_policy: ConflictResolution = ConflictResolution.DESIRED_WINS,
    ):
        self.redis = redis_client
        self.conflict_policy = conflict_policy
        self._listeners: dict[str, list[Callable]] = {}

    def _shadow_key(self, device_id: str) -> str:
        return f"shadow:{device_id}"

    async def get_shadow(self, device_id: str) -> ShadowState:
        raw = await self.redis.get(self._shadow_key(device_id))
        if raw is None:
            return ShadowState()
        return ShadowState.model_validate_json(raw)

    async def update_desired(
        self,
        device_id: str,
        desired_update: dict[str, Any],
        client_token: str | None = None,
    ) -> ShadowState:
        """Cloud-side: update desired state and compute delta for device."""
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(self._shadow_key(device_id))
                    shadow = await self.get_shadow(device_id)

                    # Optimistic concurrency: version must match
                    new_desired = deep_merge(shadow.desired, desired_update)
                    shadow.desired = new_desired
                    shadow.delta = compute_delta(shadow.desired, shadow.reported)
                    shadow.version += 1
                    shadow.timestamp = time.time()
                    shadow.metadata["last_desired_update"] = {
                        "client_token": client_token,
                        "timestamp": shadow.timestamp,
                    }

                    pipe.multi()
                    await pipe.set(
                        self._shadow_key(device_id),
                        shadow.model_dump_json(),
                    )
                    await pipe.publish(
                        f"shadow:{device_id}:delta",
                        json.dumps(shadow.delta),
                    )
                    await pipe.execute()

                    logger.info(f"Shadow {device_id} desired updated v{shadow.version}")
                    return shadow

                except redis.WatchError:
                    logger.warning(f"Concurrent update on {device_id}, retrying")
                    continue

    async def update_reported(
        self,
        device_id: str,
        reported_update: dict[str, Any],
        version: int | None = None,
    ) -> ShadowState:
        """Device-side: report current state after applying changes."""
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(self._shadow_key(device_id))
                    shadow = await self.get_shadow(device_id)

                    # Version check for conflict detection
                    if version is not None and version < shadow.version:
                        shadow = self._resolve_conflict(
                            shadow, reported_update
                        )
                    else:
                        shadow.reported = deep_merge(
                            shadow.reported, reported_update
                        )

                    shadow.delta = compute_delta(shadow.desired, shadow.reported)
                    shadow.version += 1
                    shadow.timestamp = time.time()

                    pipe.multi()
                    await pipe.set(
                        self._shadow_key(device_id),
                        shadow.model_dump_json(),
                    )
                    # Notify if delta is empty (device fully synchronized)
                    if not shadow.delta:
                        await pipe.publish(
                            f"shadow:{device_id}:synced",
                            json.dumps({"version": shadow.version}),
                        )
                    await pipe.execute()

                    logger.info(
                        f"Shadow {device_id} reported updated v{shadow.version}, "
                        f"delta={'empty' if not shadow.delta else shadow.delta}"
                    )
                    return shadow

                except redis.WatchError:
                    continue

    def _resolve_conflict(
        self, shadow: ShadowState, reported: dict
    ) -> ShadowState:
        match self.conflict_policy:
            case ConflictResolution.DESIRED_WINS:
                shadow.reported = deep_merge(shadow.reported, reported)
            case ConflictResolution.REPORTED_WINS:
                shadow.reported = deep_merge(shadow.reported, reported)
                shadow.desired = deep_merge(shadow.desired, reported)
            case ConflictResolution.MERGE:
                shadow.reported = deep_merge(shadow.reported, reported)
            case ConflictResolution.LATEST_WINS:
                shadow.reported = deep_merge(shadow.reported, reported)
        return shadow

    async def delete_shadow(self, device_id: str) -> bool:
        result = await self.redis.delete(self._shadow_key(device_id))
        return result > 0

    async def listen_deltas(self, device_id: str, callback: Callable):
        """Subscribe to delta notifications for a specific device."""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(f"shadow:{device_id}:delta")
        async for message in pubsub.listen():
            if message["type"] == "message":
                delta = json.loads(message["data"])
                await callback(device_id, delta)
```

Shadow lifecycle flow:

```
Cloud sets desired          Device reads delta          Device reports
  state change         -->   and applies changes   -->   new state
       |                          |                         |
  v1: desired={temp:72}     delta={temp:72}           reported={temp:72}
       |                          |                         |
  shadow.delta computed     device acts on delta      delta becomes empty
       |                          |                         |
  publishes delta event     subscribes via MQTT       publishes synced event
```

| Operation | Initiator | State Updated | Delta Recomputed |
|---|---|---|---|
| update_desired | Cloud/App | desired | Yes |
| update_reported | Device | reported | Yes |
| get_shadow | Any | None | No |
| delete_shadow | Cloud/Admin | All cleared | N/A |

Conflict resolution strategies:
- **DESIRED_WINS**: Cloud always overrides device (strict command-and-control)
- **REPORTED_WINS**: Device state is ground truth (autonomous devices)
- **LATEST_WINS**: Most recent timestamp prevails (collaborative)
- **MERGE**: Deep merge both sides, desired still drives delta computation

Key patterns:
- Optimistic concurrency with Redis WATCH/MULTI for atomic updates
- Version numbers prevent lost updates from stale device state
- Delta computation tells device exactly what to change (bandwidth efficient)
- Pub/Sub notifications push deltas to connected devices instantly
- Retained MQTT messages ensure offline devices get latest delta on reconnect
'''
    ),
    (
        "iot/ota-updates",
        "Build an OTA (over-the-air) firmware update system with chunked transfers, integrity verification, rollback support, fleet staged rollout, and update status tracking.",
        '''OTA firmware update system with chunked delivery, verification, rollback, and staged rollout:

```python
# ota_manager.py — OTA update system for IoT device fleets
import asyncio
import hashlib
import json
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field
import httpx
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class UpdateStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    INSTALLING = "installing"
    REBOOTING = "rebooting"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class RolloutStrategy(str, Enum):
    IMMEDIATE = "immediate"           # All devices at once
    CANARY = "canary"                 # 1% -> 10% -> 100% with gates
    LINEAR = "linear"                 # Gradual % increase over time
    BLUE_GREEN = "blue_green"         # Swap between two firmware slots


class FirmwareManifest(BaseModel):
    """Firmware release manifest with integrity metadata."""
    firmware_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    version: str                      # Semantic version
    target_hardware: str              # Hardware model identifier
    min_battery_pct: int = 30         # Minimum battery to start update
    file_url: str                     # CDN URL for firmware binary
    file_size_bytes: int
    sha256_hash: str                  # Full file integrity hash
    chunk_size: int = 64 * 1024       # 64KB chunks for constrained devices
    chunk_hashes: list[str] = Field(default_factory=list)  # Per-chunk SHA256
    release_notes: str = ""
    created_at: float = Field(default_factory=time.time)
    rollback_version: str | None = None   # Version to rollback to on failure


class DeviceUpdateState(BaseModel):
    device_id: str
    firmware_id: str
    status: UpdateStatus = UpdateStatus.PENDING
    progress_pct: float = 0.0
    chunks_received: int = 0
    total_chunks: int = 0
    current_version: str = ""
    target_version: str = ""
    started_at: float | None = None
    completed_at: float | None = None
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3


class RolloutConfig(BaseModel):
    rollout_id: str = Field(default_factory=lambda: uuid4().hex[:8])
    firmware_id: str
    strategy: RolloutStrategy = RolloutStrategy.CANARY
    canary_stages: list[float] = Field(default_factory=lambda: [0.01, 0.1, 0.5, 1.0])
    current_stage: int = 0
    success_threshold: float = 0.98   # 98% success rate to advance
    stage_duration_minutes: int = 60  # Minimum time per stage
    max_failure_pct: float = 0.05     # Auto-halt if >5% fail
    target_devices: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)


class OTAUpdateManager:
    """Server-side OTA manager for fleet firmware updates."""

    def __init__(self, redis_client: redis.Redis, cdn_base_url: str):
        self.redis = redis_client
        self.cdn_base = cdn_base_url

    async def create_firmware_manifest(
        self, firmware_path: Path, version: str, hardware: str,
        chunk_size: int = 64 * 1024,
    ) -> FirmwareManifest:
        """Generate manifest with per-chunk integrity hashes."""
        data = firmware_path.read_bytes()
        full_hash = hashlib.sha256(data).hexdigest()

        chunk_hashes = []
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i + chunk_size]
            chunk_hashes.append(hashlib.sha256(chunk).hexdigest())

        manifest = FirmwareManifest(
            version=version,
            target_hardware=hardware,
            file_url=f"{self.cdn_base}/firmware/{version}/{firmware_path.name}",
            file_size_bytes=len(data),
            sha256_hash=full_hash,
            chunk_size=chunk_size,
            chunk_hashes=chunk_hashes,
        )

        await self.redis.set(
            f"firmware:{manifest.firmware_id}",
            manifest.model_dump_json(),
            ex=86400 * 90,  # 90 day TTL
        )
        return manifest

    async def start_rollout(
        self,
        firmware_id: str,
        device_ids: list[str],
        strategy: RolloutStrategy = RolloutStrategy.CANARY,
    ) -> RolloutConfig:
        rollout = RolloutConfig(
            firmware_id=firmware_id,
            strategy=strategy,
            target_devices=device_ids,
        )
        await self.redis.set(
            f"rollout:{rollout.rollout_id}",
            rollout.model_dump_json(),
        )

        # Start first stage
        await self._advance_rollout(rollout)
        return rollout

    async def _advance_rollout(self, rollout: RolloutConfig):
        """Push firmware to the next batch of devices based on strategy."""
        if rollout.current_stage >= len(rollout.canary_stages):
            logger.info(f"Rollout {rollout.rollout_id} complete")
            return

        target_pct = rollout.canary_stages[rollout.current_stage]
        batch_size = int(len(rollout.target_devices) * target_pct)
        batch = rollout.target_devices[:batch_size]

        manifest_raw = await self.redis.get(f"firmware:{rollout.firmware_id}")
        manifest = FirmwareManifest.model_validate_json(manifest_raw)

        for device_id in batch:
            state_key = f"ota:{rollout.rollout_id}:{device_id}"
            existing = await self.redis.get(state_key)
            if existing:
                continue  # Already started

            state = DeviceUpdateState(
                device_id=device_id,
                firmware_id=rollout.firmware_id,
                total_chunks=len(manifest.chunk_hashes),
                target_version=manifest.version,
            )
            await self.redis.set(state_key, state.model_dump_json())

            # Notify device via MQTT or push channel
            await self.redis.publish(
                f"device:{device_id}:ota",
                manifest.model_dump_json(),
            )

        logger.info(
            f"Rollout {rollout.rollout_id} stage {rollout.current_stage}: "
            f"{len(batch)}/{len(rollout.target_devices)} devices ({target_pct*100:.0f}%)"
        )

    async def report_progress(
        self,
        rollout_id: str,
        device_id: str,
        status: UpdateStatus,
        chunks_received: int = 0,
        error: str = "",
    ) -> DeviceUpdateState:
        """Device reports its OTA progress; triggers rollout gates."""
        state_key = f"ota:{rollout_id}:{device_id}"
        raw = await self.redis.get(state_key)
        state = DeviceUpdateState.model_validate_json(raw)

        state.status = status
        state.chunks_received = chunks_received
        if state.total_chunks > 0:
            state.progress_pct = (chunks_received / state.total_chunks) * 100

        if status == UpdateStatus.DOWNLOADING and state.started_at is None:
            state.started_at = time.time()
        elif status in (UpdateStatus.SUCCESS, UpdateStatus.FAILED, UpdateStatus.ROLLED_BACK):
            state.completed_at = time.time()
        if error:
            state.error_message = error

        await self.redis.set(state_key, state.model_dump_json())

        # Check if we should advance or halt rollout
        if status in (UpdateStatus.SUCCESS, UpdateStatus.FAILED):
            await self._check_rollout_gates(rollout_id)

        return state

    async def _check_rollout_gates(self, rollout_id: str):
        """Evaluate success/failure rates and advance or halt rollout."""
        raw = await self.redis.get(f"rollout:{rollout_id}")
        rollout = RolloutConfig.model_validate_json(raw)

        target_pct = rollout.canary_stages[rollout.current_stage]
        batch_size = int(len(rollout.target_devices) * target_pct)
        batch = rollout.target_devices[:batch_size]

        success = failed = completed = 0
        for did in batch:
            state_raw = await self.redis.get(f"ota:{rollout_id}:{did}")
            if not state_raw:
                continue
            state = DeviceUpdateState.model_validate_json(state_raw)
            if state.status == UpdateStatus.SUCCESS:
                success += 1
                completed += 1
            elif state.status in (UpdateStatus.FAILED, UpdateStatus.ROLLED_BACK):
                failed += 1
                completed += 1

        if completed < batch_size:
            return  # Not all devices have reported yet

        failure_rate = failed / max(completed, 1)
        if failure_rate > rollout.max_failure_pct:
            logger.error(
                f"Rollout {rollout_id} HALTED: {failure_rate:.1%} failure rate "
                f"exceeds {rollout.max_failure_pct:.1%} threshold"
            )
            return

        success_rate = success / max(completed, 1)
        if success_rate >= rollout.success_threshold:
            rollout.current_stage += 1
            await self.redis.set(f"rollout:{rollout_id}", rollout.model_dump_json())
            await self._advance_rollout(rollout)
```

```python
# ota_device_agent.py — Device-side OTA agent with chunk verification and rollback
import asyncio
import hashlib
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class DeviceOTAAgent:
    """Runs on the device; downloads firmware in chunks with verification."""

    def __init__(self, device_id: str, firmware_dir: Path, active_slot: str = "A"):
        self.device_id = device_id
        self.firmware_dir = firmware_dir
        self.active_slot = active_slot  # A/B partition scheme

    @property
    def inactive_slot(self) -> str:
        return "B" if self.active_slot == "A" else "A"

    async def apply_update(self, manifest: dict, report_callback) -> bool:
        """Download, verify, install firmware with A/B rollback."""
        target_path = self.firmware_dir / f"slot_{self.inactive_slot}.bin"
        chunk_size = manifest["chunk_size"]
        chunk_hashes = manifest["chunk_hashes"]
        total_chunks = len(chunk_hashes)

        await report_callback("downloading", chunks_received=0)

        async with httpx.AsyncClient(timeout=30) as client:
            with open(target_path, "wb") as f:
                for i, expected_hash in enumerate(chunk_hashes):
                    start = i * chunk_size
                    end = start + chunk_size - 1
                    for attempt in range(3):
                        resp = await client.get(
                            manifest["file_url"],
                            headers={"Range": f"bytes={start}-{end}"},
                        )
                        chunk = resp.content
                        actual_hash = hashlib.sha256(chunk).hexdigest()

                        if actual_hash == expected_hash:
                            f.write(chunk)
                            await report_callback("downloading", chunks_received=i + 1)
                            break
                        else:
                            logger.warning(
                                f"Chunk {i} hash mismatch (attempt {attempt+1})"
                            )
                    else:
                        await report_callback("failed", error=f"Chunk {i} integrity failure")
                        return False

        # Verify full file hash
        await report_callback("verifying", chunks_received=total_chunks)
        full_hash = hashlib.sha256(target_path.read_bytes()).hexdigest()
        if full_hash != manifest["sha256_hash"]:
            await report_callback("failed", error="Full file hash mismatch")
            return False

        # Swap active partition
        await report_callback("installing", chunks_received=total_chunks)
        self.active_slot = self.inactive_slot
        await report_callback("rebooting", chunks_received=total_chunks)

        # In real device: write bootloader flag and reboot
        # If new firmware fails health check, bootloader reverts to old slot
        return True
```

Staged rollout flow:

```
Stage 0: 1% canary   --> Monitor success rate --> Gate: 98%+ pass?
Stage 1: 10% early   --> Monitor success rate --> Gate: 98%+ pass?
Stage 2: 50% main    --> Monitor success rate --> Gate: 98%+ pass?
Stage 3: 100% fleet  --> Complete
         |
    Auto-halt if failure rate > 5% at any stage
```

Key OTA patterns:
- A/B partition scheme enables instant rollback to known-good firmware
- Per-chunk SHA256 verification catches corrupted downloads early
- HTTP Range requests enable resumable downloads on unreliable networks
- Canary rollout with automatic gates prevents fleet-wide bricking
- Minimum battery check prevents update failures from power loss
'''
    ),
    (
        "iot/edge-processing",
        "Implement an edge data processing pipeline that filters, aggregates, and compresses sensor data locally before sending to cloud, with configurable rules, local buffering, and store-and-forward for intermittent connectivity.",
        '''Edge data processing pipeline with local aggregation, compression, and store-and-forward:

```python
# edge_pipeline.py — Edge processing pipeline for IoT sensor data
import asyncio
import gzip
import json
import time
import logging
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from statistics import mean, median, stdev

import httpx

logger = logging.getLogger(__name__)


class AggregationType(str, Enum):
    MEAN = "mean"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"
    SUM = "sum"
    COUNT = "count"
    LAST = "last"
    PERCENTILE_95 = "p95"
    STDDEV = "stddev"


@dataclass
class FilterRule:
    """Rule to filter out sensor readings before aggregation."""
    field: str
    operator: str    # gt, lt, gte, lte, eq, neq, between, change_pct
    value: Any
    upper: Any = None  # For 'between' operator

    def matches(self, reading: dict) -> bool:
        val = reading.get(self.field)
        if val is None:
            return False
        match self.operator:
            case "gt":   return val > self.value
            case "lt":   return val < self.value
            case "gte":  return val >= self.value
            case "lte":  return val <= self.value
            case "eq":   return val == self.value
            case "neq":  return val != self.value
            case "between": return self.value <= val <= self.upper
            case _: return True


@dataclass
class AggregationWindow:
    """Tumbling window that collects values and emits aggregate."""
    duration_seconds: float
    aggregation: AggregationType
    values: list[float] = field(default_factory=list)
    window_start: float = 0.0

    def is_expired(self, now: float) -> bool:
        return now - self.window_start >= self.duration_seconds

    def add(self, value: float, now: float):
        if self.window_start == 0.0:
            self.window_start = now
        self.values.append(value)

    def compute(self) -> float | None:
        if not self.values:
            return None
        match self.aggregation:
            case AggregationType.MEAN:    return mean(self.values)
            case AggregationType.MEDIAN:  return median(self.values)
            case AggregationType.MIN:     return min(self.values)
            case AggregationType.MAX:     return max(self.values)
            case AggregationType.SUM:     return sum(self.values)
            case AggregationType.COUNT:   return len(self.values)
            case AggregationType.LAST:    return self.values[-1]
            case AggregationType.STDDEV:
                return stdev(self.values) if len(self.values) > 1 else 0.0
            case AggregationType.PERCENTILE_95:
                sorted_vals = sorted(self.values)
                idx = int(len(sorted_vals) * 0.95)
                return sorted_vals[min(idx, len(sorted_vals) - 1)]

    def reset(self, now: float):
        self.values = []
        self.window_start = now


@dataclass
class DeadBandFilter:
    """Suppress values that haven't changed significantly."""
    field: str
    threshold_pct: float = 1.0     # Minimum % change to emit
    threshold_abs: float = 0.0     # Minimum absolute change to emit
    last_emitted: float | None = None

    def should_emit(self, value: float) -> bool:
        if self.last_emitted is None:
            self.last_emitted = value
            return True
        abs_change = abs(value - self.last_emitted)
        pct_change = (abs_change / abs(self.last_emitted)) * 100 if self.last_emitted != 0 else 100
        if abs_change >= self.threshold_abs or pct_change >= self.threshold_pct:
            self.last_emitted = value
            return True
        return False


class StoreAndForwardBuffer:
    """SQLite-backed buffer for offline resilience."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload BLOB NOT NULL,
                created_at REAL NOT NULL,
                attempts INTEGER DEFAULT 0,
                last_attempt REAL DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_outbox_created
            ON outbox(created_at)
        """)
        self._conn.commit()

    def enqueue(self, payload: bytes):
        self._conn.execute(
            "INSERT INTO outbox (payload, created_at) VALUES (?, ?)",
            (payload, time.time()),
        )
        self._conn.commit()

    def peek_batch(self, batch_size: int = 100) -> list[tuple[int, bytes]]:
        cursor = self._conn.execute(
            "SELECT id, payload FROM outbox ORDER BY created_at LIMIT ?",
            (batch_size,),
        )
        return cursor.fetchall()

    def acknowledge(self, ids: list[int]):
        placeholders = ",".join("?" for _ in ids)
        self._conn.execute(
            f"DELETE FROM outbox WHERE id IN ({placeholders})", ids
        )
        self._conn.commit()

    def queue_depth(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM outbox").fetchone()
        return row[0]

    def prune_old(self, max_age_hours: int = 72):
        cutoff = time.time() - (max_age_hours * 3600)
        self._conn.execute("DELETE FROM outbox WHERE created_at < ?", (cutoff,))
        self._conn.commit()


class EdgePipeline:
    """Configurable edge processing pipeline: filter -> deadband -> aggregate -> compress -> send."""

    def __init__(
        self,
        device_id: str,
        cloud_endpoint: str,
        buffer_path: Path = Path("/var/lib/edge/outbox.db"),
        flush_interval: float = 30.0,
    ):
        self.device_id = device_id
        self.cloud_endpoint = cloud_endpoint
        self.flush_interval = flush_interval
        self.buffer = StoreAndForwardBuffer(buffer_path)
        self._filters: dict[str, list[FilterRule]] = defaultdict(list)
        self._deadbands: dict[str, DeadBandFilter] = {}
        self._windows: dict[str, AggregationWindow] = {}
        self._pending: list[dict] = []
        self._online = True
        self._stats = {"ingested": 0, "filtered": 0, "emitted": 0, "compressed_bytes": 0}

    def add_filter(self, sensor: str, rule: FilterRule):
        self._filters[sensor].append(rule)

    def add_deadband(self, sensor: str, threshold_pct: float = 1.0, threshold_abs: float = 0.0):
        self._deadbands[sensor] = DeadBandFilter(
            field=sensor, threshold_pct=threshold_pct, threshold_abs=threshold_abs
        )

    def add_aggregation(
        self, sensor: str, window_seconds: float, agg_type: AggregationType
    ):
        self._windows[sensor] = AggregationWindow(
            duration_seconds=window_seconds, aggregation=agg_type
        )

    async def ingest(self, sensor: str, value: float, metadata: dict | None = None):
        """Process a single sensor reading through the pipeline."""
        self._stats["ingested"] += 1
        now = time.time()
        reading = {"sensor": sensor, "value": value, "ts": now, **(metadata or {})}

        # Stage 1: Filter
        for rule in self._filters.get(sensor, []):
            if not rule.matches(reading):
                self._stats["filtered"] += 1
                return

        # Stage 2: Dead band
        if sensor in self._deadbands:
            if not self._deadbands[sensor].should_emit(value):
                self._stats["filtered"] += 1
                return

        # Stage 3: Aggregate
        if sensor in self._windows:
            window = self._windows[sensor]
            window.add(value, now)
            if window.is_expired(now):
                agg_value = window.compute()
                window.reset(now)
                if agg_value is not None:
                    self._pending.append({
                        "sensor": sensor,
                        "value": round(agg_value, 4),
                        "ts": now,
                        "agg": window.aggregation.value,
                        "window_s": window.duration_seconds,
                        "samples": len(window.values),
                    })
                    self._stats["emitted"] += 1
        else:
            self._pending.append(reading)
            self._stats["emitted"] += 1

    async def flush(self):
        """Compress and send or buffer pending data."""
        if not self._pending:
            return

        batch = {
            "device_id": self.device_id,
            "readings": self._pending,
            "batch_ts": time.time(),
            "count": len(self._pending),
        }
        compressed = gzip.compress(json.dumps(batch).encode(), compresslevel=6)
        self._stats["compressed_bytes"] += len(compressed)
        self._pending = []

        if self._online:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        self.cloud_endpoint,
                        content=compressed,
                        headers={
                            "Content-Type": "application/json",
                            "Content-Encoding": "gzip",
                            "X-Device-ID": self.device_id,
                        },
                    )
                    resp.raise_for_status()
                    # Also drain buffered messages
                    await self._drain_buffer()
            except (httpx.HTTPError, httpx.ConnectError):
                logger.warning("Cloud unreachable, buffering locally")
                self._online = False
                self.buffer.enqueue(compressed)
        else:
            self.buffer.enqueue(compressed)

    async def _drain_buffer(self):
        """Send buffered messages from offline period."""
        batch = self.buffer.peek_batch(50)
        if not batch:
            return
        sent_ids = []
        async with httpx.AsyncClient(timeout=10) as client:
            for row_id, payload in batch:
                try:
                    resp = await client.post(
                        self.cloud_endpoint,
                        content=payload,
                        headers={
                            "Content-Type": "application/json",
                            "Content-Encoding": "gzip",
                            "X-Device-ID": self.device_id,
                        },
                    )
                    resp.raise_for_status()
                    sent_ids.append(row_id)
                except httpx.HTTPError:
                    break
        if sent_ids:
            self.buffer.acknowledge(sent_ids)
            logger.info(f"Drained {len(sent_ids)} buffered messages")

    async def run(self):
        """Background flush loop."""
        while True:
            await asyncio.sleep(self.flush_interval)
            await self.flush()
```

Pipeline stages and data reduction:

| Stage | Purpose | Typical Reduction |
|---|---|---|
| Filter rules | Remove out-of-range / invalid readings | 5-15% |
| Dead band | Suppress unchanged values | 40-80% |
| Aggregation | Window-based mean/min/max/p95 | 90-99% |
| Compression | Gzip batch payloads | 70-85% size |

Key edge processing patterns:
- Dead band filtering is the single biggest bandwidth saver for slowly-changing sensors
- Tumbling windows aggregate high-frequency data (1000 Hz -> 1 point/30s)
- SQLite store-and-forward survives power cycles and network outages
- Gzip compression at level 6 balances CPU (constrained) with ratio
- Batch flush intervals trade latency for efficiency (30s default)
- Buffer pruning prevents disk exhaustion on prolonged offline periods
'''
    ),
    (
        "iot/timeseries-ingestion",
        "Design a time-series data ingestion pipeline for IoT that handles millions of data points per second using TimescaleDB, with automatic partitioning, continuous aggregates, retention policies, and downsampling.",
        '''High-throughput time-series ingestion pipeline with TimescaleDB:

```python
# timeseries_ingestion.py — IoT time-series pipeline with TimescaleDB
import asyncio
import json
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from contextlib import asynccontextmanager

import asyncpg
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SensorReading(BaseModel):
    device_id: str
    sensor_type: str
    value: float
    ts: datetime
    metadata: dict[str, Any] | None = None


class TimeseriesDB:
    """TimescaleDB manager with hypertables, continuous aggregates, and retention."""

    def __init__(self, dsn: str, pool_size: int = 20):
        self.dsn = dsn
        self.pool_size = pool_size
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(self.dsn, min_size=5, max_size=self.pool_size)
        await self._initialize_schema()

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def _initialize_schema(self):
        async with self.pool.acquire() as conn:
            # Enable TimescaleDB extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

            # Raw readings hypertable — partitioned by time
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    ts          TIMESTAMPTZ     NOT NULL,
                    device_id   TEXT            NOT NULL,
                    sensor_type TEXT            NOT NULL,
                    value       DOUBLE PRECISION NOT NULL,
                    metadata    JSONB
                );
            """)

            # Convert to hypertable with 1-day chunks
            # Use if_not_exists to make idempotent
            await conn.execute("""
                SELECT create_hypertable(
                    'sensor_readings', 'ts',
                    chunk_time_interval => INTERVAL '1 day',
                    if_not_exists => TRUE
                );
            """)

            # Composite index for common query patterns
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_readings_device_ts
                ON sensor_readings (device_id, ts DESC);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_readings_type_ts
                ON sensor_readings (sensor_type, ts DESC);
            """)

            # Continuous aggregate: 1-minute rollups (materialized automatically)
            await conn.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_readings_1m
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('1 minute', ts) AS bucket,
                    device_id,
                    sensor_type,
                    AVG(value)    AS avg_value,
                    MIN(value)    AS min_value,
                    MAX(value)    AS max_value,
                    COUNT(*)      AS sample_count,
                    STDDEV(value) AS stddev_value,
                    last(value, ts) AS last_value
                FROM sensor_readings
                GROUP BY bucket, device_id, sensor_type
                WITH NO DATA;
            """)

            # Continuous aggregate: 1-hour rollups
            await conn.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_readings_1h
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('1 hour', ts) AS bucket,
                    device_id,
                    sensor_type,
                    AVG(value)    AS avg_value,
                    MIN(value)    AS min_value,
                    MAX(value)    AS max_value,
                    COUNT(*)      AS sample_count,
                    STDDEV(value) AS stddev_value
                FROM sensor_readings
                GROUP BY bucket, device_id, sensor_type
                WITH NO DATA;
            """)

            # Continuous aggregate: 1-day rollups
            await conn.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_readings_1d
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('1 day', ts) AS bucket,
                    device_id,
                    sensor_type,
                    AVG(value)    AS avg_value,
                    MIN(value)    AS min_value,
                    MAX(value)    AS max_value,
                    COUNT(*)      AS sample_count
                FROM sensor_readings
                GROUP BY bucket, device_id, sensor_type
                WITH NO DATA;
            """)

            # Refresh policies for continuous aggregates
            await conn.execute("""
                SELECT add_continuous_aggregate_policy('sensor_readings_1m',
                    start_offset => INTERVAL '3 hours',
                    end_offset   => INTERVAL '1 minute',
                    schedule_interval => INTERVAL '1 minute',
                    if_not_exists => TRUE
                );
            """)
            await conn.execute("""
                SELECT add_continuous_aggregate_policy('sensor_readings_1h',
                    start_offset => INTERVAL '3 days',
                    end_offset   => INTERVAL '1 hour',
                    schedule_interval => INTERVAL '30 minutes',
                    if_not_exists => TRUE
                );
            """)
            await conn.execute("""
                SELECT add_continuous_aggregate_policy('sensor_readings_1d',
                    start_offset => INTERVAL '30 days',
                    end_offset   => INTERVAL '1 day',
                    schedule_interval => INTERVAL '1 hour',
                    if_not_exists => TRUE
                );
            """)

            # Retention policies: raw=7 days, 1m=30 days, 1h=1 year, 1d=forever
            await conn.execute("""
                SELECT add_retention_policy('sensor_readings',
                    drop_after => INTERVAL '7 days',
                    if_not_exists => TRUE
                );
            """)
            await conn.execute("""
                SELECT add_retention_policy('sensor_readings_1m',
                    drop_after => INTERVAL '30 days',
                    if_not_exists => TRUE
                );
            """)
            await conn.execute("""
                SELECT add_retention_policy('sensor_readings_1h',
                    drop_after => INTERVAL '365 days',
                    if_not_exists => TRUE
                );
            """)

            # Enable compression on raw data after 2 days
            await conn.execute("""
                ALTER TABLE sensor_readings SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'device_id, sensor_type',
                    timescaledb.compress_orderby = 'ts DESC'
                );
            """)
            await conn.execute("""
                SELECT add_compression_policy('sensor_readings',
                    compress_after => INTERVAL '2 days',
                    if_not_exists => TRUE
                );
            """)


class BatchIngester:
    """High-throughput batch ingestion using COPY protocol."""

    def __init__(self, db: TimeseriesDB, batch_size: int = 5000, flush_interval: float = 1.0):
        self.db = db
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._buffer: list[SensorReading] = []
        self._lock = asyncio.Lock()
        self._stats = {"ingested": 0, "batches": 0, "errors": 0}

    async def ingest(self, reading: SensorReading):
        async with self._lock:
            self._buffer.append(reading)
            if len(self._buffer) >= self.batch_size:
                await self._flush()

    async def ingest_batch(self, readings: list[SensorReading]):
        async with self._lock:
            self._buffer.extend(readings)
            while len(self._buffer) >= self.batch_size:
                await self._flush()

    async def _flush(self):
        if not self._buffer:
            return
        batch = self._buffer[:self.batch_size]
        self._buffer = self._buffer[self.batch_size:]

        try:
            async with self.db.pool.acquire() as conn:
                # Use COPY for maximum throughput (10-100x faster than INSERT)
                records = [
                    (r.ts, r.device_id, r.sensor_type, r.value,
                     json.dumps(r.metadata) if r.metadata else None)
                    for r in batch
                ]
                await conn.copy_records_to_table(
                    "sensor_readings",
                    records=records,
                    columns=["ts", "device_id", "sensor_type", "value", "metadata"],
                )
            self._stats["ingested"] += len(batch)
            self._stats["batches"] += 1
        except Exception:
            self._stats["errors"] += 1
            # Re-queue failed batch
            self._buffer = batch + self._buffer
            logger.exception(f"Batch insert failed, {len(batch)} records re-queued")

    async def run_flusher(self):
        """Background timer-based flush for low-throughput periods."""
        while True:
            await asyncio.sleep(self.flush_interval)
            async with self._lock:
                if self._buffer:
                    await self._flush()


class TimeseriesQuery:
    """Query interface with automatic resolution selection."""

    def __init__(self, db: TimeseriesDB):
        self.db = db

    async def query_auto_resolution(
        self,
        device_id: str,
        sensor_type: str,
        start: datetime,
        end: datetime,
        max_points: int = 1000,
    ) -> list[dict]:
        """Automatically select the best resolution table based on time range."""
        duration = end - start
        if duration <= timedelta(hours=6):
            table = "sensor_readings"      # Raw data
            time_col = "ts"
            value_col = "value"
        elif duration <= timedelta(days=7):
            table = "sensor_readings_1m"   # 1-minute aggregates
            time_col = "bucket"
            value_col = "avg_value"
        elif duration <= timedelta(days=90):
            table = "sensor_readings_1h"   # 1-hour aggregates
            time_col = "bucket"
            value_col = "avg_value"
        else:
            table = "sensor_readings_1d"   # 1-day aggregates
            time_col = "bucket"
            value_col = "avg_value"

        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT {time_col} AS ts, {value_col} AS value
                FROM {table}
                WHERE device_id = $1
                  AND sensor_type = $2
                  AND {time_col} BETWEEN $3 AND $4
                ORDER BY {time_col}
                LIMIT $5
            """, device_id, sensor_type, start, end, max_points)

        return [{"ts": row["ts"].isoformat(), "value": row["value"]} for row in rows]
```

Data lifecycle and retention tiers:

| Tier | Table | Resolution | Retention | Compression |
|---|---|---|---|---|
| Raw | sensor_readings | Full rate | 7 days | After 2 days |
| 1-minute | sensor_readings_1m | 1 min avg/min/max | 30 days | N/A |
| 1-hour | sensor_readings_1h | 1 hour avg/min/max | 1 year | N/A |
| 1-day | sensor_readings_1d | 1 day avg/min/max | Forever | N/A |

Key time-series patterns:
- COPY protocol is 10-100x faster than row-by-row INSERT for bulk ingestion
- Chunk-based hypertables enable parallel queries and efficient retention drops
- Continuous aggregates are materialized views refreshed automatically by TimescaleDB
- Segment-by compression groups data by device_id for efficient per-device queries
- Auto-resolution query selects the right table based on requested time range
- Buffer + timer flush handles both high-throughput bursts and low-activity periods
'''
    ),
    (
        "iot/device-authentication",
        "Implement IoT device authentication using X.509 certificates with a device provisioning flow, certificate rotation, and a device registry that tracks certificate lifecycle and revocation.",
        '''IoT device authentication with X.509 certificates, provisioning, rotation, and revocation:

```python
# device_auth.py — X.509 device authentication and certificate lifecycle
import asyncio
import hashlib
import json
import time
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, NoEncryption, BestAvailableEncryption
)
from pydantic import BaseModel, Field
import asyncpg

logger = logging.getLogger(__name__)


class CertificateStatus(str, Enum):
    ACTIVE = "active"
    PENDING_ROTATION = "pending_rotation"
    REVOKED = "revoked"
    EXPIRED = "expired"


class DeviceRegistration(BaseModel):
    device_id: str
    hardware_model: str
    firmware_version: str
    certificate_fingerprint: str
    certificate_status: CertificateStatus = CertificateStatus.ACTIVE
    certificate_not_before: datetime
    certificate_not_after: datetime
    provisioned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime | None = None
    rotation_requested_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CertificateAuthority:
    """Lightweight CA for IoT device certificate management."""

    def __init__(
        self,
        ca_key_path: Path,
        ca_cert_path: Path,
        cert_validity_days: int = 365,
    ):
        self.cert_validity_days = cert_validity_days
        self._ca_key = self._load_private_key(ca_key_path)
        self._ca_cert = self._load_certificate(ca_cert_path)

    @staticmethod
    def _load_private_key(path: Path) -> ec.EllipticCurvePrivateKey:
        return serialization.load_pem_private_key(
            path.read_bytes(), password=None
        )

    @staticmethod
    def _load_certificate(path: Path) -> x509.Certificate:
        return x509.load_pem_x509_certificate(path.read_bytes())

    def generate_device_certificate(
        self, device_id: str, hardware_model: str
    ) -> tuple[bytes, bytes, str]:
        """Generate EC P-256 key pair and signed device certificate.

        Returns: (private_key_pem, certificate_pem, fingerprint)
        """
        # Generate device key pair (ECDSA P-256 — optimal for constrained devices)
        device_key = ec.generate_private_key(ec.SECP256R1())

        now = datetime.now(timezone.utc)
        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, device_id),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "IoT Fleet"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, hardware_model),
        ])

        cert_builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self._ca_cert.subject)
            .public_key(device_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=self.cert_validity_days))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=False,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
                ]),
                critical=False,
            )
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.UniformResourceIdentifier(f"urn:iot:device:{device_id}"),
                ]),
                critical=False,
            )
        )

        cert = cert_builder.sign(self._ca_key, hashes.SHA256())

        key_pem = device_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        )
        cert_pem = cert.public_bytes(Encoding.PEM)
        fingerprint = hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest()

        return key_pem, cert_pem, fingerprint

    def verify_device_certificate(self, cert_pem: bytes) -> tuple[bool, str, str]:
        """Verify a device certificate against the CA.

        Returns: (is_valid, device_id, fingerprint)
        """
        try:
            cert = x509.load_pem_x509_certificate(cert_pem)

            # Verify signature chain
            self._ca_cert.public_key().verify(
                cert.signature,
                cert.tbs_certificate_bytes,
                ec.ECDSA(hashes.SHA256()),
            )

            # Check expiration
            now = datetime.now(timezone.utc)
            if now < cert.not_valid_before_utc or now > cert.not_valid_after_utc:
                return False, "", ""

            device_id = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
            fingerprint = hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest()

            return True, device_id, fingerprint

        except Exception as e:
            logger.warning(f"Certificate verification failed: {e}")
            return False, "", ""


class DeviceRegistry:
    """Database-backed device registry with certificate lifecycle management."""

    def __init__(self, pool: asyncpg.Pool, ca: CertificateAuthority):
        self.pool = pool
        self.ca = ca

    async def initialize(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    device_id               TEXT PRIMARY KEY,
                    hardware_model          TEXT NOT NULL,
                    firmware_version        TEXT NOT NULL DEFAULT '0.0.0',
                    cert_fingerprint        TEXT UNIQUE NOT NULL,
                    cert_status             TEXT NOT NULL DEFAULT 'active',
                    cert_not_before         TIMESTAMPTZ NOT NULL,
                    cert_not_after          TIMESTAMPTZ NOT NULL,
                    prev_cert_fingerprint   TEXT,
                    provisioned_at          TIMESTAMPTZ DEFAULT NOW(),
                    last_seen               TIMESTAMPTZ,
                    metadata                JSONB DEFAULT '{}'
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS revoked_certs (
                    fingerprint   TEXT PRIMARY KEY,
                    device_id     TEXT NOT NULL,
                    revoked_at    TIMESTAMPTZ DEFAULT NOW(),
                    reason        TEXT
                );
            """)

    async def provision_device(
        self, device_id: str, hardware_model: str
    ) -> tuple[bytes, bytes]:
        """Provision a new device: generate certs and register."""
        key_pem, cert_pem, fingerprint = self.ca.generate_device_certificate(
            device_id, hardware_model
        )
        cert = x509.load_pem_x509_certificate(cert_pem)

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO devices (device_id, hardware_model, cert_fingerprint,
                                     cert_not_before, cert_not_after)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (device_id) DO UPDATE SET
                    cert_fingerprint = EXCLUDED.cert_fingerprint,
                    cert_not_before = EXCLUDED.cert_not_before,
                    cert_not_after = EXCLUDED.cert_not_after,
                    cert_status = 'active'
            """, device_id, hardware_model, fingerprint,
                cert.not_valid_before_utc, cert.not_valid_after_utc)

        logger.info(f"Provisioned device {device_id} with cert {fingerprint[:16]}...")
        return key_pem, cert_pem

    async def authenticate(self, cert_pem: bytes) -> DeviceRegistration | None:
        """Authenticate a device by its TLS client certificate."""
        is_valid, device_id, fingerprint = self.ca.verify_device_certificate(cert_pem)
        if not is_valid:
            return None

        async with self.pool.acquire() as conn:
            # Check if certificate is revoked
            revoked = await conn.fetchrow(
                "SELECT 1 FROM revoked_certs WHERE fingerprint = $1", fingerprint
            )
            if revoked:
                logger.warning(f"Revoked cert used by device {device_id}")
                return None

            # Verify device is registered with this cert
            row = await conn.fetchrow(
                "SELECT * FROM devices WHERE device_id = $1 AND cert_fingerprint = $2",
                device_id, fingerprint,
            )
            if not row:
                return None

            # Update last seen
            await conn.execute(
                "UPDATE devices SET last_seen = NOW() WHERE device_id = $1",
                device_id,
            )

        return DeviceRegistration(
            device_id=row["device_id"],
            hardware_model=row["hardware_model"],
            firmware_version=row["firmware_version"],
            certificate_fingerprint=row["cert_fingerprint"],
            certificate_status=CertificateStatus(row["cert_status"]),
            certificate_not_before=row["cert_not_before"],
            certificate_not_after=row["cert_not_after"],
        )

    async def rotate_certificate(self, device_id: str) -> tuple[bytes, bytes]:
        """Issue new certificate and revoke old one."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM devices WHERE device_id = $1", device_id
            )
            if not row:
                raise ValueError(f"Device {device_id} not found")

            old_fingerprint = row["cert_fingerprint"]

            # Generate new certificate
            key_pem, cert_pem, new_fp = self.ca.generate_device_certificate(
                device_id, row["hardware_model"]
            )
            cert = x509.load_pem_x509_certificate(cert_pem)

            # Atomic swap: update device, revoke old cert
            async with conn.transaction():
                await conn.execute("""
                    UPDATE devices SET
                        cert_fingerprint = $1,
                        cert_not_before = $2,
                        cert_not_after = $3,
                        prev_cert_fingerprint = $4,
                        cert_status = 'active'
                    WHERE device_id = $5
                """, new_fp, cert.not_valid_before_utc,
                    cert.not_valid_after_utc, old_fingerprint, device_id)

                await conn.execute("""
                    INSERT INTO revoked_certs (fingerprint, device_id, reason)
                    VALUES ($1, $2, 'rotation')
                """, old_fingerprint, device_id)

        logger.info(f"Rotated cert for {device_id}: {old_fingerprint[:16]} -> {new_fp[:16]}")
        return key_pem, cert_pem

    async def get_expiring_devices(self, days_ahead: int = 30) -> list[str]:
        """Find devices with certificates expiring within N days."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT device_id FROM devices
                WHERE cert_status = 'active'
                  AND cert_not_after < NOW() + INTERVAL '1 day' * $1
                ORDER BY cert_not_after
            """, days_ahead)
        return [row["device_id"] for row in rows]
```

Certificate lifecycle:

```
Provisioning          Normal Operation         Rotation              Revocation
  |                       |                      |                      |
  Generate EC P-256   mTLS handshake on      Generate new cert      Add old cert to
  key pair            every connection        for device             revoked_certs table
  |                       |                      |                      |
  Sign with CA        Verify chain +          Atomic DB swap:        Reject future
  private key         check revocation        old -> revoked,        connections with
  |                   list                    new -> active          this cert
  Register in DB          |                      |
                      Update last_seen        Device installs new
                                              cert on next connect
```

Key security patterns:
- ECDSA P-256 keys are optimal for constrained IoT devices (small key, fast verify)
- mTLS ensures both broker and device are authenticated (not just one side)
- Certificate fingerprint (SHA-256 of DER) is the primary lookup key
- Revocation list check on every connection prevents use of compromised certs
- prev_cert_fingerprint field enables grace period during rotation
- Automatic expiry scanning enables proactive fleet-wide rotation
'''
    ),
]
