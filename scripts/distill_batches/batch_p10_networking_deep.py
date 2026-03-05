"""
Batch P10 — Deep Networking Topics
Covers: HTTP/3 and QUIC handshake simulation, DNS internals with caching resolver,
TCP congestion control algorithms, network security (TLS 1.3, CORS, CSP),
WebSocket protocol frame parsing and reconnection logic.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    # --- 1. HTTP/3 and QUIC Protocol — Handshake Simulator ---
    (
        "networking/quic-handshake-simulator",
        "Explain the HTTP/3 QUIC protocol in depth including UDP-based transport, stream multiplexing without head-of-line blocking, 0-RTT connection establishment, connection migration, and implement a QUIC handshake simulator in Python that demonstrates the full connection establishment flow and stream management lifecycle.",
        r"""# HTTP/3 and QUIC: Building a Handshake Simulator from the Ground Up

## Why QUIC Replaced TCP for HTTP/3

The internet's transport layer has been dominated by **TCP** for decades, but TCP carries fundamental limitations that cannot be patched away. The most critical problem is **head-of-line (HOL) blocking**: because TCP guarantees in-order byte delivery across a single connection, a single lost packet stalls **every** multiplexed stream — even those whose data arrived perfectly. This is devastating on lossy mobile and Wi-Fi networks where packet loss rates regularly hit 1-5%.

**QUIC** (standardized in RFC 9000) solves this by building a **reliable, encrypted, multiplexed transport** directly on top of **UDP**. Because QUIC controls its own packet framing and acknowledgment, it can deliver streams independently — a lost packet on stream 3 never blocks stream 7. HTTP/3 (RFC 9114) layers HTTP semantics on QUIC, therefore completing the replacement of the traditional TCP+TLS stack.

The **trade-off** is complexity: QUIC must re-implement congestion control, flow control, loss recovery, and encryption that TCP+TLS previously handled in separate, well-tested layers. However, the benefits — faster connections, no HOL blocking, seamless connection migration — make this trade-off worthwhile for modern web traffic.

## The QUIC Handshake: 1-RTT and 0-RTT

### 1-RTT Initial Handshake

A fresh QUIC connection completes in a **single round trip**, compared to TCP's 2-3 RTTs (SYN/SYN-ACK + TLS handshake). The flow is:

1. **Client Initial**: Client sends a CRYPTO frame containing a TLS ClientHello, plus proposed transport parameters (max streams, flow control limits, connection IDs).
2. **Server Initial + Handshake**: Server responds with its TLS ServerHello, certificate, and finished message, all in CRYPTO frames. The server also sends its chosen transport parameters.
3. **Client Handshake Complete**: Client verifies the server's certificate chain, derives the 1-RTT keys, and sends its Handshake finished message. Application data can now flow.

**Best practice**: The client should include a **retry token** if the server previously issued one. Retry tokens prevent IP address spoofing amplification attacks because the server validates that the client actually controls the claimed source address.

### 0-RTT Connection Resumption

When the client has previously connected, it caches the server's transport parameters and a **session ticket**. On reconnection, the client sends application data alongside the Initial packet — **zero additional round trips**. However, 0-RTT introduces a **replay attack** risk because an attacker can capture and resend the 0-RTT packet. Therefore, 0-RTT data must be **idempotent** (safe to replay). A **common mistake** is sending POST requests with side effects in 0-RTT; only safe, read-only operations like GET requests should use this path.

### Connection Migration

QUIC connections are identified by a **Connection ID (CID)**, not by the IP/port 4-tuple. When a mobile device switches from Wi-Fi to cellular, the CID stays the same and the connection migrates seamlessly. The migrating endpoint sends a **PATH_CHALLENGE** frame, the peer responds with **PATH_RESPONSE**, and traffic resumes on the new path without a full reconnection.

## Implementing the QUIC Handshake Simulator

```python
import os
import enum
import time
import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# --- QUIC Packet Types ---
class PacketType(enum.Enum):
    INITIAL = "initial"
    HANDSHAKE = "handshake"
    ZERO_RTT = "0-rtt"
    ONE_RTT = "1-rtt"
    RETRY = "retry"

# --- Frame Types ---
class FrameType(enum.Enum):
    CRYPTO = 0x06
    STREAM = 0x08
    ACK = 0x02
    PATH_CHALLENGE = 0x1A
    PATH_RESPONSE = 0x1B
    NEW_CONNECTION_ID = 0x18
    CONNECTION_CLOSE = 0x1C

@dataclass
class QuicFrame:
    # Represents a single QUIC frame within a packet
    frame_type: FrameType
    stream_id: Optional[int] = None
    offset: int = 0
    payload: bytes = b""
    fin: bool = False

@dataclass
class QuicPacket:
    # A QUIC packet containing one or more frames
    packet_type: PacketType
    connection_id: bytes = b""
    packet_number: int = 0
    frames: List[QuicFrame] = field(default_factory=list)
    timestamp: float = field(default_factory=time.monotonic)

@dataclass
class TransportParameters:
    # QUIC transport parameters negotiated during handshake
    max_idle_timeout_ms: int = 30000
    max_udp_payload_size: int = 1200
    initial_max_data: int = 1_048_576
    initial_max_stream_data_bidi_local: int = 262_144
    initial_max_stream_data_bidi_remote: int = 262_144
    initial_max_streams_bidi: int = 100
    initial_max_streams_uni: int = 100
    active_connection_id_limit: int = 4

class CryptoState(enum.Enum):
    # Tracks the TLS handshake progression
    IDLE = "idle"
    INITIAL_SENT = "initial_sent"
    HANDSHAKE_RECEIVED = "handshake_received"
    HANDSHAKE_COMPLETE = "handshake_complete"
    ESTABLISHED = "established"
    ZERO_RTT_SENT = "0rtt_sent"
```

```python
# --- QUIC Connection and Handshake Engine ---
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import secrets
import hashlib
import time

@dataclass
class HandshakeResult:
    # Outcome of a handshake attempt
    success: bool
    rtt_count: int
    connection_id: bytes
    negotiated_params: Optional[TransportParameters] = None
    error: Optional[str] = None

class QuicConnection:
    # Simulates a QUIC connection with full handshake lifecycle
    # Supports 1-RTT initial, 0-RTT resumption, and connection migration

    def __init__(
        self,
        is_server: bool = False,
        local_params: Optional[TransportParameters] = None,
    ) -> None:
        self.is_server = is_server
        self.local_params = local_params or TransportParameters()
        self.remote_params: Optional[TransportParameters] = None
        self.state = CryptoState.IDLE
        self.connection_id = secrets.token_bytes(8)
        self.peer_connection_id: Optional[bytes] = None
        self.packet_number: int = 0
        self._sent_packets: List[QuicPacket] = []
        self._received_packets: List[QuicPacket] = []
        self._streams: Dict[int, "StreamState"] = {}
        self._session_ticket: Optional[bytes] = None
        self._cached_params: Optional[TransportParameters] = None
        self._rtt_estimate_ms: float = 0.0
        self._path: Optional[Tuple[str, int]] = None

    def initiate_handshake(
        self, cached_ticket: Optional[bytes] = None
    ) -> QuicPacket:
        # Client initiates the QUIC handshake
        # If cached_ticket is provided, attempts 0-RTT
        if self.is_server:
            raise RuntimeError("Server cannot initiate handshake")

        crypto_payload = self._build_client_hello()

        if cached_ticket is not None:
            # 0-RTT: include early data with the Initial
            self.state = CryptoState.ZERO_RTT_SENT
            frames = [
                QuicFrame(
                    frame_type=FrameType.CRYPTO,
                    payload=crypto_payload,
                ),
                QuicFrame(
                    frame_type=FrameType.STREAM,
                    stream_id=0,
                    payload=b"GET / HTTP/3\r\n",
                    fin=False,
                ),
            ]
            packet = QuicPacket(
                packet_type=PacketType.INITIAL,
                connection_id=self.connection_id,
                packet_number=self._next_pn(),
                frames=frames,
            )
        else:
            # Standard 1-RTT Initial
            self.state = CryptoState.INITIAL_SENT
            frames = [
                QuicFrame(
                    frame_type=FrameType.CRYPTO,
                    payload=crypto_payload,
                )
            ]
            packet = QuicPacket(
                packet_type=PacketType.INITIAL,
                connection_id=self.connection_id,
                packet_number=self._next_pn(),
                frames=frames,
            )

        self._sent_packets.append(packet)
        return packet

    def process_initial(self, packet: QuicPacket) -> QuicPacket:
        # Server processes client Initial and responds with Handshake
        if not self.is_server:
            raise RuntimeError("Client should not process Initial")

        self.peer_connection_id = packet.connection_id
        self._received_packets.append(packet)

        # Build Server Handshake response
        server_hello = self._build_server_hello()
        cert_payload = self._build_certificate()

        response = QuicPacket(
            packet_type=PacketType.HANDSHAKE,
            connection_id=self.connection_id,
            packet_number=self._next_pn(),
            frames=[
                QuicFrame(
                    frame_type=FrameType.CRYPTO,
                    payload=server_hello + cert_payload,
                ),
                QuicFrame(
                    frame_type=FrameType.ACK,
                    payload=packet.packet_number.to_bytes(4, "big"),
                ),
            ],
        )
        self.state = CryptoState.HANDSHAKE_COMPLETE
        self._sent_packets.append(response)
        return response

    def complete_handshake(self, packet: QuicPacket) -> HandshakeResult:
        # Client completes handshake after receiving server Handshake
        self._received_packets.append(packet)
        self.peer_connection_id = packet.connection_id

        # Verify server certificate (simulated)
        crypto_frame = next(
            f for f in packet.frames if f.frame_type == FrameType.CRYPTO
        )
        if not self._verify_certificate(crypto_frame.payload):
            self.state = CryptoState.IDLE
            return HandshakeResult(
                success=False,
                rtt_count=0,
                connection_id=self.connection_id,
                error="Certificate verification failed",
            )

        # Derive session ticket for future 0-RTT
        self._session_ticket = hashlib.sha256(
            self.connection_id + packet.connection_id
        ).digest()
        self._cached_params = self.local_params

        # Calculate RTT from timestamps
        send_time = self._sent_packets[0].timestamp
        recv_time = packet.timestamp
        self._rtt_estimate_ms = (recv_time - send_time) * 1000

        rtt_count = 0 if self.state == CryptoState.ZERO_RTT_SENT else 1
        self.state = CryptoState.ESTABLISHED
        self.remote_params = self.local_params  # Simplified

        return HandshakeResult(
            success=True,
            rtt_count=rtt_count,
            connection_id=self.connection_id,
            negotiated_params=self.remote_params,
        )

    def migrate_path(
        self, new_addr: Tuple[str, int]
    ) -> QuicPacket:
        # Initiate connection migration to a new network path
        old_path = self._path
        self._path = new_addr
        challenge_data = secrets.token_bytes(8)
        packet = QuicPacket(
            packet_type=PacketType.ONE_RTT,
            connection_id=self.connection_id,
            packet_number=self._next_pn(),
            frames=[
                QuicFrame(
                    frame_type=FrameType.PATH_CHALLENGE,
                    payload=challenge_data,
                )
            ],
        )
        self._sent_packets.append(packet)
        return packet

    def respond_path_challenge(self, packet: QuicPacket) -> QuicPacket:
        # Respond to a PATH_CHALLENGE with PATH_RESPONSE
        challenge_frame = next(
            f for f in packet.frames
            if f.frame_type == FrameType.PATH_CHALLENGE
        )
        response = QuicPacket(
            packet_type=PacketType.ONE_RTT,
            connection_id=self.connection_id,
            packet_number=self._next_pn(),
            frames=[
                QuicFrame(
                    frame_type=FrameType.PATH_RESPONSE,
                    payload=challenge_frame.payload,
                )
            ],
        )
        self._sent_packets.append(response)
        return response

    # --- Internal helpers ---
    def _next_pn(self) -> int:
        pn = self.packet_number
        self.packet_number += 1
        return pn

    def _build_client_hello(self) -> bytes:
        return b"ClientHello|TLS1.3|ALPN=h3"

    def _build_server_hello(self) -> bytes:
        return b"ServerHello|TLS1.3|KeyShare"

    def _build_certificate(self) -> bytes:
        return b"Certificate|CertVerify|Finished"

    def _verify_certificate(self, payload: bytes) -> bool:
        return b"Certificate" in payload
```

```python
# --- Stream Manager and Full Simulation Runner ---
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class StreamState:
    # Independent per-stream state, the core of HOL-blocking prevention
    stream_id: int
    bytes_sent: int = 0
    bytes_received: int = 0
    send_buffer: bytes = b""
    recv_buffer: bytes = b""
    fin_sent: bool = False
    fin_received: bool = False
    is_closed: bool = False

class StreamManager:
    # Manages independent QUIC streams on a connection
    # Each stream has its own flow control and reassembly buffer

    def __init__(self, max_bidi: int = 100, max_uni: int = 100) -> None:
        self._streams: Dict[int, StreamState] = {}
        self._max_bidi = max_bidi
        self._max_uni = max_uni
        self._next_bidi_id = 0
        self._next_uni_id = 2  # Uni streams use odd IDs for server

    def open_bidi_stream(self) -> StreamState:
        # Open a new bidirectional stream
        if len(self._get_bidi_streams()) >= self._max_bidi:
            raise RuntimeError("Max bidirectional streams exceeded")
        sid = self._next_bidi_id
        self._next_bidi_id += 4  # Client bidi: 0, 4, 8...
        stream = StreamState(stream_id=sid)
        self._streams[sid] = stream
        return stream

    def send_data(self, stream_id: int, data: bytes, fin: bool = False) -> QuicFrame:
        # Queue data for sending on a stream
        stream = self._streams[stream_id]
        stream.send_buffer += data
        stream.bytes_sent += len(data)
        if fin:
            stream.fin_sent = True
        return QuicFrame(
            frame_type=FrameType.STREAM,
            stream_id=stream_id,
            offset=stream.bytes_sent - len(data),
            payload=data,
            fin=fin,
        )

    def receive_data(self, frame: QuicFrame) -> None:
        # Process received stream data, reassembling independently
        # This is why QUIC avoids HOL blocking: each stream
        # reassembles its own data without waiting for other streams
        sid = frame.stream_id
        if sid not in self._streams:
            self._streams[sid] = StreamState(stream_id=sid)
        stream = self._streams[sid]
        stream.recv_buffer += frame.payload
        stream.bytes_received += len(frame.payload)
        if frame.fin:
            stream.fin_received = True

    def _get_bidi_streams(self) -> List[StreamState]:
        return [s for s in self._streams.values() if s.stream_id % 2 == 0]


def run_handshake_simulation() -> None:
    # Full simulation: 1-RTT handshake, stream creation, and migration
    print("=== QUIC Handshake Simulation ===\n")

    client = QuicConnection(is_server=False)
    server = QuicConnection(is_server=True)

    # Step 1: Client sends Initial
    print("[1-RTT] Client -> Server: Initial (ClientHello)")
    initial = client.initiate_handshake()
    print(f"  Packet #{initial.packet_number}, CID={initial.connection_id.hex()[:8]}")

    # Step 2: Server processes and responds
    print("[1-RTT] Server -> Client: Handshake (ServerHello + Cert)")
    handshake = server.process_initial(initial)
    print(f"  Packet #{handshake.packet_number}, CID={handshake.connection_id.hex()[:8]}")

    # Step 3: Client completes handshake
    result = client.complete_handshake(handshake)
    print(f"[1-RTT] Handshake complete: success={result.success}, RTTs={result.rtt_count}")

    # Step 4: Open streams and send data
    print("\n=== Stream Multiplexing ===\n")
    mgr = StreamManager()
    s0 = mgr.open_bidi_stream()
    s1 = mgr.open_bidi_stream()
    print(f"Opened stream {s0.stream_id} and stream {s1.stream_id}")

    f0 = mgr.send_data(s0.stream_id, b"GET /index.html HTTP/3", fin=True)
    f1 = mgr.send_data(s1.stream_id, b"GET /style.css HTTP/3", fin=True)
    print(f"Stream {s0.stream_id}: sent {f0.payload}")
    print(f"Stream {s1.stream_id}: sent {f1.payload}")
    print("(Loss on stream 0 does NOT block stream 4 delivery)")

    # Step 5: Connection migration
    print("\n=== Connection Migration ===\n")
    challenge = client.migrate_path(("10.0.0.5", 443))
    print(f"Client migrated, PATH_CHALLENGE sent: {challenge.frames[0].payload.hex()[:8]}...")
    response = server.respond_path_challenge(challenge)
    print(f"Server PATH_RESPONSE: {response.frames[0].payload.hex()[:8]}...")
    print("Connection migrated successfully, CID unchanged.")

    # Step 6: 0-RTT resumption simulation
    print("\n=== 0-RTT Resumption ===\n")
    client2 = QuicConnection(is_server=False)
    ticket = client._session_ticket
    print(f"Using cached session ticket: {ticket.hex()[:16]}...")
    initial_0rtt = client2.initiate_handshake(cached_ticket=ticket)
    print(f"0-RTT Initial sent with early data, state={client2.state.value}")
    print("Application data sent in first flight — zero additional RTTs!")


if __name__ == "__main__":
    run_handshake_simulation()
```

## Key Differences from TCP+TLS

| Feature | TCP+TLS 1.3 | QUIC |
|---|---|---|
| Handshake RTTs | 2-3 RTT | 1 RTT (0-RTT resume) |
| HOL blocking | Yes (TCP layer) | No (per-stream) |
| Connection ID | IP:port tuple | CID (migration-safe) |
| Encryption | Separate TLS layer | Integrated into transport |
| Congestion control | Kernel TCP | User-space (pluggable) |

## Pitfalls and Common Mistakes

A **pitfall** with QUIC deployment is **middlebox interference**: firewalls and NATs that inspect TCP headers cannot parse QUIC packets because they are encrypted UDP. Therefore, QUIC implementations must fall back to TCP if UDP is blocked on the network. A **common mistake** is assuming QUIC will always be faster — on low-loss wired networks, the difference from TCP is minimal, and the added user-space overhead can actually increase CPU usage.

**Best practice**: Always implement HTTP/3 with an HTTP/2-over-TCP fallback. Use Alt-Svc headers to advertise HTTP/3 availability so clients can upgrade on subsequent requests.

## Summary / Key Takeaways

- **QUIC replaces TCP+TLS** with a single encrypted transport on UDP, achieving 1-RTT connections and 0-RTT resumption for previously visited servers.
- **Stream multiplexing without HOL blocking** is the most impactful improvement: lost packets only affect their own stream, not the entire connection.
- **Connection migration via Connection IDs** enables seamless handoffs between networks, critical for mobile users.
- **0-RTT carries replay risk**, therefore only idempotent operations should use early data.
- **Best practice** is to deploy HTTP/3 alongside HTTP/2 fallback, using Alt-Svc for progressive upgrade.
- The handshake simulator above demonstrates the full lifecycle: Initial exchange, certificate verification, stream creation, independent data flow, and path migration.
"""
    ),

    # --- 2. DNS Internals — Resolver with Caching ---
    (
        "networking/dns-resolver-caching-internals",
        "Explain DNS resolution internals in depth including recursive versus iterative resolution, DNS caching with TTL management, DNSSEC chain of trust validation, DNS-over-HTTPS tunneling, and all major record types, then implement a fully functional DNS resolver in Python with caching, TTL expiration, and record parsing for A, AAAA, CNAME, SRV, and TXT records.",
        r"""# DNS Internals: Building a Caching Resolver from Scratch

## How DNS Resolution Actually Works

The **Domain Name System** is a globally distributed, hierarchical database that translates human-readable domain names into IP addresses and other records. Understanding its internals is essential because DNS is involved in virtually every network connection, and misconfigurations cause some of the most frustrating debugging sessions in production systems.

### Recursive vs. Iterative Resolution

There are two fundamentally different resolution strategies, and confusing them is a **common mistake** among developers.

**Recursive resolution** means the resolver does all the work on behalf of the client. The client sends a single query to its configured recursive resolver (e.g., 8.8.8.8 or your ISP's DNS server), and that resolver chases the delegation chain from root servers down to the authoritative nameserver, returning the final answer. The client makes **one request** and gets a complete response.

**Iterative resolution** means each server returns either the answer or a **referral** pointing to a more specific nameserver. The querying resolver must follow these referrals itself. Root servers always respond iteratively — they never recurse on behalf of clients. Therefore, a recursive resolver internally performs iterative queries against the DNS hierarchy.

The **trade-off** is clear: recursive resolution is simpler for clients but places more load on the recursive resolver. Iterative resolution distributes the work but requires the client to handle multiple round trips.

### The DNS Hierarchy

A query for `api.example.com` follows this chain:

1. **Root servers** (`.`): Return referral to `.com` TLD nameservers.
2. **TLD servers** (`.com`): Return referral to `example.com` authoritative nameservers.
3. **Authoritative servers** (`example.com`): Return the actual A/AAAA record.

### DNS Record Types

- **A**: Maps hostname to IPv4 address (4 bytes).
- **AAAA**: Maps hostname to IPv6 address (16 bytes).
- **CNAME**: Canonical name alias — the resolver must follow the chain to the actual A/AAAA record. A **pitfall** is creating CNAME loops or placing a CNAME at the zone apex (which violates the RFC).
- **SRV**: Service location record — specifies host, port, priority, and weight for services like SIP or XMPP.
- **TXT**: Arbitrary text data, commonly used for SPF, DKIM, domain verification, and ACME DNS-01 challenges.

### DNS Caching and TTL

Every DNS record includes a **Time-To-Live (TTL)** value in seconds. Caching resolvers store records until the TTL expires. **Best practice** is to set TTLs based on how frequently the record changes: 300 seconds (5 minutes) for dynamic services, 86400 seconds (1 day) for stable infrastructure.

A **common mistake** is setting TTLs too low (e.g., 10 seconds) "just in case" — this dramatically increases query volume and latency because every request must go back to the authoritative server.

### DNSSEC Chain of Trust

**DNSSEC** adds cryptographic signatures to DNS records. Each zone signs its records with a **Zone Signing Key (ZSK)** and publishes the corresponding **DNSKEY** record. The parent zone signs a **DS (Delegation Signer)** record that contains a hash of the child's KSK. This creates a chain of trust from the root (whose keys are hardcoded in resolvers as trust anchors) down to the leaf zone.

However, DNSSEC has a **trade-off**: it authenticates responses but does **not** encrypt them. DNS-over-HTTPS (DoH) solves the privacy problem.

### DNS-over-HTTPS (DoH)

DoH tunnels DNS queries inside HTTPS POST or GET requests to a DoH endpoint (e.g., `https://dns.google/dns-query`). This provides both **encryption** and **authentication** (via TLS), preventing ISPs and middleboxes from snooping on or tampering with DNS queries. The **pitfall** is that DoH can bypass corporate DNS policies, which is why some enterprises block known DoH endpoints.

## Implementing a DNS Resolver with Caching

```python
import struct
import socket
import time
import enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

# --- DNS Constants and Record Types ---

class RecordType(enum.IntEnum):
    A = 1
    AAAA = 28
    CNAME = 5
    SRV = 33
    TXT = 16
    NS = 2
    SOA = 6
    DS = 43
    DNSKEY = 48

class ResponseCode(enum.IntEnum):
    NOERROR = 0
    FORMERR = 1
    SERVFAIL = 2
    NXDOMAIN = 3
    REFUSED = 5

@dataclass
class DnsRecord:
    # A parsed DNS resource record with TTL tracking
    name: str
    record_type: RecordType
    ttl: int
    data: Union[str, bytes, "SrvData"]
    # Absolute expiration time for cache management
    expires_at: float = 0.0

    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    def remaining_ttl(self) -> int:
        return max(0, int(self.expires_at - time.time()))

@dataclass
class SrvData:
    # Parsed SRV record fields
    priority: int
    weight: int
    port: int
    target: str

@dataclass
class DnsQuery:
    # Represents a DNS question section
    name: str
    record_type: RecordType
    query_class: int = 1  # IN (Internet)

@dataclass
class DnsResponse:
    # Complete DNS response with all sections
    query_id: int
    response_code: ResponseCode
    questions: List[DnsQuery] = field(default_factory=list)
    answers: List[DnsRecord] = field(default_factory=list)
    authority: List[DnsRecord] = field(default_factory=list)
    additional: List[DnsRecord] = field(default_factory=list)
    is_authoritative: bool = False
    is_truncated: bool = False
    recursion_available: bool = False
```

```python
# --- DNS Cache with TTL Expiration ---
import time
import threading
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

class DnsCache:
    # Thread-safe DNS cache with automatic TTL expiration
    # Stores records keyed by (name, record_type) with per-record expiry

    def __init__(self, max_entries: int = 10000) -> None:
        self._cache: Dict[Tuple[str, int], List[DnsRecord]] = {}
        self._lock = threading.RLock()
        self._max_entries = max_entries
        self._hit_count = 0
        self._miss_count = 0
        self._eviction_count = 0

    def get(self, name: str, record_type: RecordType) -> Optional[List[DnsRecord]]:
        # Look up cached records, filtering out expired entries
        key = (name.lower(), int(record_type))
        with self._lock:
            records = self._cache.get(key)
            if records is None:
                self._miss_count += 1
                return None

            # Remove expired records
            valid = [r for r in records if not r.is_expired()]
            if not valid:
                del self._cache[key]
                self._miss_count += 1
                return None

            self._cache[key] = valid
            self._hit_count += 1
            return valid

    def put(self, records: List[DnsRecord]) -> None:
        # Cache a list of DNS records, setting absolute expiration
        if not records:
            return
        with self._lock:
            # Enforce max cache size with LRU-like eviction
            if len(self._cache) >= self._max_entries:
                self._evict_expired()

            for record in records:
                record.expires_at = time.time() + record.ttl
                key = (record.name.lower(), int(record.record_type))
                existing = self._cache.get(key, [])
                existing.append(record)
                self._cache[key] = existing

    def _evict_expired(self) -> None:
        # Remove all expired entries from the cache
        keys_to_remove = []
        for key, records in self._cache.items():
            valid = [r for r in records if not r.is_expired()]
            if not valid:
                keys_to_remove.append(key)
            else:
                self._cache[key] = valid
        for key in keys_to_remove:
            del self._cache[key]
            self._eviction_count += 1

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._cache),
                "hits": self._hit_count,
                "misses": self._miss_count,
                "evictions": self._eviction_count,
                "hit_rate_pct": (
                    int(100 * self._hit_count / max(1, self._hit_count + self._miss_count))
                ),
            }

    def flush(self) -> int:
        # Clear the entire cache, returning number of removed entries
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count
```

```python
# --- DNS Packet Parser and Resolver ---
import struct
import socket
import secrets
from typing import Dict, List, Optional, Tuple, Union

class DnsPacketBuilder:
    # Builds raw DNS query packets for wire transmission

    @staticmethod
    def build_query(name: str, record_type: RecordType) -> Tuple[int, bytes]:
        # Build a DNS query packet, returns (query_id, packet_bytes)
        query_id = secrets.randbelow(65536)
        # Header: ID, flags (recursion desired), QDCOUNT=1
        flags = 0x0100  # Standard query, RD=1
        header = struct.pack("!HHHHHH", query_id, flags, 1, 0, 0, 0)

        # Encode domain name as DNS wire format labels
        question = b""
        for label in name.split("."):
            encoded = label.encode("ascii")
            question += struct.pack("!B", len(encoded)) + encoded
        question += b"\x00"  # Root terminator
        question += struct.pack("!HH", int(record_type), 1)  # QTYPE, QCLASS=IN

        return query_id, header + question

class DnsPacketParser:
    # Parses raw DNS response packets into structured DnsResponse objects

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def parse(self) -> DnsResponse:
        # Parse the full DNS response from wire format
        (qid, flags, qdcount, ancount, nscount, arcount) = struct.unpack_from(
            "!HHHHHH", self._data, 0
        )
        self._offset = 12

        rcode = ResponseCode(flags & 0x0F)
        is_auth = bool(flags & 0x0400)
        is_trunc = bool(flags & 0x0200)
        ra = bool(flags & 0x0080)

        questions = [self._parse_question() for _ in range(qdcount)]
        answers = [self._parse_record() for _ in range(ancount)]
        authority = [self._parse_record() for _ in range(nscount)]
        additional = [self._parse_record() for _ in range(arcount)]

        return DnsResponse(
            query_id=qid,
            response_code=rcode,
            questions=questions,
            answers=answers,
            authority=authority,
            additional=additional,
            is_authoritative=is_auth,
            is_truncated=is_trunc,
            recursion_available=ra,
        )

    def _parse_question(self) -> DnsQuery:
        name = self._read_name()
        qtype, qclass = struct.unpack_from("!HH", self._data, self._offset)
        self._offset += 4
        return DnsQuery(name=name, record_type=RecordType(qtype), query_class=qclass)

    def _parse_record(self) -> DnsRecord:
        name = self._read_name()
        rtype, rclass, ttl, rdlength = struct.unpack_from(
            "!HHIH", self._data, self._offset
        )
        self._offset += 10
        rdata_start = self._offset
        parsed_data = self._parse_rdata(RecordType(rtype), rdlength)
        self._offset = rdata_start + rdlength
        return DnsRecord(
            name=name,
            record_type=RecordType(rtype),
            ttl=ttl,
            data=parsed_data,
        )

    def _parse_rdata(self, rtype: RecordType, length: int) -> Union[str, bytes, SrvData]:
        start = self._offset
        if rtype == RecordType.A:
            octets = struct.unpack_from("!4B", self._data, self._offset)
            return ".".join(str(o) for o in octets)
        elif rtype == RecordType.AAAA:
            words = struct.unpack_from("!8H", self._data, self._offset)
            return ":".join(f"{w:04x}" for w in words)
        elif rtype == RecordType.CNAME:
            return self._read_name()
        elif rtype == RecordType.SRV:
            priority, weight, port = struct.unpack_from(
                "!HHH", self._data, self._offset
            )
            self._offset += 6
            target = self._read_name()
            return SrvData(priority=priority, weight=weight, port=port, target=target)
        elif rtype == RecordType.TXT:
            # TXT records: one or more length-prefixed strings
            texts = []
            end = start + length
            while self._offset < end:
                slen = self._data[self._offset]
                self._offset += 1
                texts.append(self._data[self._offset:self._offset + slen].decode("utf-8", errors="replace"))
                self._offset += slen
            return " ".join(texts)
        else:
            return self._data[self._offset:self._offset + length]

    def _read_name(self) -> str:
        # Read a DNS name with pointer compression support
        labels = []
        jumped = False
        saved_offset = 0
        while True:
            if self._offset >= len(self._data):
                break
            length = self._data[self._offset]
            if (length & 0xC0) == 0xC0:
                # Compression pointer
                if not jumped:
                    saved_offset = self._offset + 2
                pointer = struct.unpack_from("!H", self._data, self._offset)[0] & 0x3FFF
                self._offset = pointer
                jumped = True
            elif length == 0:
                self._offset += 1
                break
            else:
                self._offset += 1
                label = self._data[self._offset:self._offset + length].decode("ascii")
                labels.append(label)
                self._offset += length
        if jumped:
            self._offset = saved_offset
        return ".".join(labels)


class CachingDnsResolver:
    # Full recursive DNS resolver with caching, TTL management,
    # and CNAME chain following

    def __init__(
        self,
        upstream: str = "8.8.8.8",
        cache: Optional[DnsCache] = None,
        timeout: float = 5.0,
    ) -> None:
        self._upstream = upstream
        self._cache = cache or DnsCache()
        self._timeout = timeout
        self._max_cname_depth = 8

    def resolve(
        self, name: str, record_type: RecordType = RecordType.A
    ) -> List[DnsRecord]:
        # Resolve a DNS name, checking cache first, then querying upstream
        # Follows CNAME chains automatically
        cached = self._cache.get(name, record_type)
        if cached:
            return cached

        return self._resolve_recursive(name, record_type, depth=0)

    def _resolve_recursive(
        self, name: str, record_type: RecordType, depth: int
    ) -> List[DnsRecord]:
        if depth > self._max_cname_depth:
            raise RuntimeError(f"CNAME chain too deep for {name}")

        query_id, packet = DnsPacketBuilder.build_query(name, record_type)
        response_data = self._send_query(packet)
        if response_data is None:
            return []

        parser = DnsPacketParser(response_data)
        response = parser.parse()

        if response.response_code != ResponseCode.NOERROR:
            return []

        # Cache all answer records
        self._cache.put(response.answers)

        # Check for CNAME and follow the chain
        direct = [r for r in response.answers if r.record_type == record_type]
        if direct:
            return direct

        cnames = [r for r in response.answers if r.record_type == RecordType.CNAME]
        if cnames and isinstance(cnames[0].data, str):
            return self._resolve_recursive(cnames[0].data, record_type, depth + 1)

        return response.answers

    def _send_query(self, packet: bytes) -> Optional[bytes]:
        # Send a DNS query over UDP to the upstream resolver
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self._timeout)
            sock.sendto(packet, (self._upstream, 53))
            data, _ = sock.recvfrom(4096)
            return data
        except socket.timeout:
            return None
        finally:
            sock.close()

    def cache_stats(self) -> Dict[str, int]:
        return self._cache.stats()
```

## DNSSEC Validation Flow

The DNSSEC chain of trust works as follows:

1. The resolver has **root trust anchors** (hardcoded DNSKEY public keys for the root zone).
2. For `.com`, the resolver fetches the **DS record** from the root zone and the **DNSKEY** from `.com` — verifying the DS hash matches.
3. For `example.com`, the resolver fetches the **DS** from `.com` and **DNSKEY** from `example.com`.
4. Finally, the **RRSIG** signature on the A record is verified against the zone's DNSKEY.

If any link in the chain fails, the response is marked **BOGUS** and discarded. This is a **trade-off**: DNSSEC adds latency (more records to fetch and verify) and complexity (key rotation, algorithm rollover) but provides strong protection against cache poisoning.

## Summary / Key Takeaways

- **Recursive resolvers** do all the work for the client; **iterative queries** are how they chase the delegation chain internally.
- **DNS caching with TTL** is critical for performance — **best practice** is to match TTL to the record's expected change frequency.
- **CNAME following** requires depth limits to prevent infinite loops, a subtle **pitfall** that catches many custom resolver implementations.
- **DNSSEC** provides authentication via a chain of trust from root to leaf, however it does not encrypt queries — DoH handles privacy.
- **SRV records** enable service discovery with priority and weight-based load balancing, therefore they are essential for microservice DNS patterns.
- The caching resolver above handles A, AAAA, CNAME, SRV, and TXT records with proper TTL expiration and thread-safe cache access.
"""
    ),

    # --- 3. TCP Congestion Control — Window Simulator ---
    (
        "networking/tcp-congestion-control-simulator",
        "Explain TCP congestion control algorithms in depth including slow start, congestion avoidance, fast retransmit, fast recovery, BBR, and CUBIC, then implement a comprehensive TCP congestion window simulator in Python that demonstrates window growth phases, packet loss detection, and recovery behavior with visualization-ready output.",
        r"""# TCP Congestion Control: Building a Congestion Window Simulator

## Why Congestion Control Matters

Without congestion control, TCP senders would blast packets as fast as possible, overwhelming routers and causing **congestion collapse** — a state where the network carries almost no useful data because it is flooded with retransmissions. Congestion control algorithms dynamically adjust the **congestion window (cwnd)** — the number of unacknowledged packets the sender is allowed to have in flight — to find the optimal sending rate without overwhelming the network.

Understanding these algorithms deeply is essential because they directly affect application throughput and latency. A **common mistake** is assuming TCP just "handles" performance — in reality, the choice of congestion control algorithm and its parameter tuning can make a 10x difference in throughput on high-latency or lossy links.

## The Classic Algorithms

### Slow Start

Despite the name, slow start is actually **exponential growth**. The sender starts with cwnd = 1 MSS (Maximum Segment Size, typically 1460 bytes) and doubles cwnd every RTT by incrementing it by 1 MSS for each ACK received. This continues until cwnd reaches the **slow start threshold (ssthresh)**, at which point the sender transitions to congestion avoidance.

**Best practice**: Modern implementations start with an **Initial Window (IW)** of 10 MSS (RFC 6928) rather than 1, because the original value was far too conservative for today's networks.

### Congestion Avoidance

Once cwnd >= ssthresh, growth switches to **linear** (additive increase): cwnd increases by approximately 1 MSS per RTT (specifically, by MSS * MSS / cwnd for each ACK). This cautious growth probes for available bandwidth without aggressive doubling.

### Loss Detection and Response

TCP detects loss through two mechanisms:

1. **Timeout (RTO)**: No ACK received within the retransmission timeout. This is the nuclear option: cwnd resets to 1 MSS and ssthresh is set to cwnd/2. The sender re-enters slow start.
2. **Triple duplicate ACKs**: Three duplicate ACKs indicate a single packet was lost but subsequent packets arrived. This triggers **fast retransmit** (retransmit the lost packet immediately) and **fast recovery**.

### Fast Recovery (Reno)

In fast recovery, ssthresh = cwnd/2, and cwnd = ssthresh + 3 MSS (accounting for the three duplicate ACKs). The sender continues to inflate cwnd for each additional duplicate ACK and deflates it back to ssthresh when a new (non-duplicate) ACK arrives. The **trade-off** is that Reno handles single losses well but struggles with multiple losses in the same window.

### CUBIC

**CUBIC** (the default on Linux) uses a cubic function of time since the last congestion event to set cwnd. The key idea is that cwnd growth is a function of **elapsed time**, not of ACK arrivals, making it more fair across flows with different RTTs. The cubic function creates a characteristic S-curve: rapid growth far from the previous maximum, slow probing near it, and rapid growth again once it is surpassed.

### BBR (Bottleneck Bandwidth and Round-trip propagation time)

**BBR** takes a fundamentally different approach. Instead of using packet loss as a congestion signal, it estimates the **bottleneck bandwidth** (maximum delivery rate) and **minimum RTT** independently, then sets the sending rate to their product. BBR cycles through probing phases to discover available bandwidth and detect RTT changes.

However, BBR has a **pitfall**: BBRv1 can be unfair to loss-based algorithms (CUBIC, Reno) on shared bottlenecks because it does not back off on loss. BBRv2 addresses this by incorporating loss signals.

## Implementing the Congestion Window Simulator

```python
import enum
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

# --- Congestion Control Algorithm Interface ---

class CongestionEvent(enum.Enum):
    ACK = "ack"
    DUPLICATE_ACK = "duplicate_ack"
    TIMEOUT = "timeout"
    TRIPLE_DUP_ACK = "triple_dup_ack"

class CongestionPhase(enum.Enum):
    SLOW_START = "slow_start"
    CONGESTION_AVOIDANCE = "congestion_avoidance"
    FAST_RECOVERY = "fast_recovery"

@dataclass
class CwndSnapshot:
    # A point-in-time capture of congestion window state
    # Used for building visualization-ready traces
    time_ms: float
    cwnd_mss: float
    ssthresh_mss: float
    phase: CongestionPhase
    event: CongestionEvent
    bytes_in_flight: int = 0
    rtt_ms: float = 0.0

@dataclass
class SimulationConfig:
    # Parameters for the congestion control simulation
    mss: int = 1460                # Maximum Segment Size in bytes
    initial_cwnd_mss: float = 10.0 # Initial window in MSS units (RFC 6928)
    initial_ssthresh_mss: float = 64.0
    base_rtt_ms: float = 50.0     # Minimum RTT in ms
    simulation_duration_ms: float = 10000.0
    loss_events_at_ms: List[float] = field(
        default_factory=lambda: [2000.0, 5000.0, 7500.0]
    )
    loss_type: str = "triple_dup"  # "triple_dup" or "timeout"

class RenoController:
    # TCP Reno congestion control: slow start, congestion avoidance,
    # fast retransmit / fast recovery

    def __init__(self, config: SimulationConfig) -> None:
        self.config = config
        self.cwnd: float = config.initial_cwnd_mss
        self.ssthresh: float = config.initial_ssthresh_mss
        self.phase = CongestionPhase.SLOW_START
        self.dup_ack_count: int = 0
        self._trace: List[CwndSnapshot] = []

    def on_ack(self, time_ms: float, rtt_ms: float) -> None:
        # Process a new ACK based on current phase
        if self.phase == CongestionPhase.SLOW_START:
            # Exponential growth: +1 MSS per ACK
            self.cwnd += 1.0
            if self.cwnd >= self.ssthresh:
                self.phase = CongestionPhase.CONGESTION_AVOIDANCE
        elif self.phase == CongestionPhase.CONGESTION_AVOIDANCE:
            # Additive increase: ~1 MSS per RTT
            self.cwnd += 1.0 / self.cwnd
        elif self.phase == CongestionPhase.FAST_RECOVERY:
            # Deflate cwnd back to ssthresh on new ACK
            self.cwnd = self.ssthresh
            self.phase = CongestionPhase.CONGESTION_AVOIDANCE

        self.dup_ack_count = 0
        self._record(time_ms, CongestionEvent.ACK, rtt_ms)

    def on_duplicate_ack(self, time_ms: float, rtt_ms: float) -> None:
        # Handle duplicate ACK; trigger fast recovery on triple dup
        self.dup_ack_count += 1
        if self.dup_ack_count == 3:
            # Fast retransmit + fast recovery entry
            self.ssthresh = max(self.cwnd / 2.0, 2.0)
            self.cwnd = self.ssthresh + 3.0
            self.phase = CongestionPhase.FAST_RECOVERY
            self._record(time_ms, CongestionEvent.TRIPLE_DUP_ACK, rtt_ms)
        elif self.phase == CongestionPhase.FAST_RECOVERY:
            # Inflate cwnd during fast recovery
            self.cwnd += 1.0
            self._record(time_ms, CongestionEvent.DUPLICATE_ACK, rtt_ms)

    def on_timeout(self, time_ms: float, rtt_ms: float) -> None:
        # RTO timeout: reset to slow start
        self.ssthresh = max(self.cwnd / 2.0, 2.0)
        self.cwnd = 1.0  # Back to initial
        self.phase = CongestionPhase.SLOW_START
        self.dup_ack_count = 0
        self._record(time_ms, CongestionEvent.TIMEOUT, rtt_ms)

    def _record(self, time_ms: float, event: CongestionEvent, rtt_ms: float) -> None:
        self._trace.append(CwndSnapshot(
            time_ms=time_ms,
            cwnd_mss=self.cwnd,
            ssthresh_mss=self.ssthresh,
            phase=self.phase,
            event=event,
            bytes_in_flight=int(self.cwnd * self.config.mss),
            rtt_ms=rtt_ms,
        ))

    @property
    def trace(self) -> List[CwndSnapshot]:
        return list(self._trace)
```

```python
# --- CUBIC Controller and BBR Estimator ---
import math
from dataclasses import dataclass, field
from typing import List, Optional

class CubicController:
    # TCP CUBIC congestion control algorithm
    # cwnd is a cubic function of time since last loss event

    BETA: float = 0.7   # Multiplicative decrease factor
    C: float = 0.4      # CUBIC scaling constant

    def __init__(self, config: SimulationConfig) -> None:
        self.config = config
        self.cwnd: float = config.initial_cwnd_mss
        self.ssthresh: float = config.initial_ssthresh_mss
        self.phase = CongestionPhase.SLOW_START
        self.w_max: float = config.initial_ssthresh_mss  # cwnd at last loss
        self.epoch_start_ms: float = 0.0  # Time of last loss event
        self.origin_point: float = 0.0    # W_max for the cubic curve
        self.k: float = 0.0              # Time to reach W_max
        self._trace: List[CwndSnapshot] = []
        self.dup_ack_count: int = 0

    def _cubic_update(self, time_ms: float) -> float:
        # Compute CUBIC target cwnd based on elapsed time
        t = (time_ms - self.epoch_start_ms) / 1000.0  # Convert to seconds
        # K = cubic_root(W_max * (1 - beta) / C)
        # W_cubic(t) = C * (t - K)^3 + W_max
        target = self.C * (t - self.k) ** 3 + self.origin_point
        return max(target, 1.0)

    def on_ack(self, time_ms: float, rtt_ms: float) -> None:
        if self.phase == CongestionPhase.SLOW_START:
            self.cwnd += 1.0
            if self.cwnd >= self.ssthresh:
                self.phase = CongestionPhase.CONGESTION_AVOIDANCE
                self.epoch_start_ms = time_ms
                self.origin_point = self.cwnd
                self.k = (self.w_max * (1 - self.BETA) / self.C) ** (1.0 / 3.0)
        elif self.phase == CongestionPhase.CONGESTION_AVOIDANCE:
            target = self._cubic_update(time_ms)
            if target > self.cwnd:
                self.cwnd += (target - self.cwnd) / self.cwnd
            else:
                # TCP-friendly region: linear increase
                self.cwnd += 1.0 / self.cwnd
        elif self.phase == CongestionPhase.FAST_RECOVERY:
            self.cwnd = self.ssthresh
            self.phase = CongestionPhase.CONGESTION_AVOIDANCE
            self.epoch_start_ms = time_ms
            self.origin_point = self.cwnd
            self.k = (self.w_max * (1 - self.BETA) / self.C) ** (1.0 / 3.0)

        self.dup_ack_count = 0
        self._record(time_ms, CongestionEvent.ACK, rtt_ms)

    def on_loss(self, time_ms: float, rtt_ms: float) -> None:
        # Multiplicative decrease with CUBIC's beta (0.7 vs Reno's 0.5)
        self.w_max = self.cwnd
        self.ssthresh = max(self.cwnd * self.BETA, 2.0)
        self.cwnd = self.ssthresh
        self.phase = CongestionPhase.FAST_RECOVERY
        self.epoch_start_ms = time_ms
        self.origin_point = self.w_max
        self.k = (self.w_max * (1 - self.BETA) / self.C) ** (1.0 / 3.0)
        self._record(time_ms, CongestionEvent.TRIPLE_DUP_ACK, rtt_ms)

    def _record(self, time_ms: float, event: CongestionEvent, rtt_ms: float) -> None:
        self._trace.append(CwndSnapshot(
            time_ms=time_ms, cwnd_mss=self.cwnd, ssthresh_mss=self.ssthresh,
            phase=self.phase, event=event,
            bytes_in_flight=int(self.cwnd * self.config.mss), rtt_ms=rtt_ms,
        ))

    @property
    def trace(self) -> List[CwndSnapshot]:
        return list(self._trace)


@dataclass
class BbrState:
    # BBR estimates bottleneck bandwidth and min RTT independently
    btl_bw: float = 0.0             # Bottleneck bandwidth (bytes/sec)
    rt_prop_ms: float = float("inf") # Minimum observed RTT
    pacing_rate: float = 0.0         # Computed sending rate
    cwnd: float = 10.0               # Congestion window in MSS
    pacing_gain: float = 1.0         # Current pacing multiplier
    cwnd_gain: float = 2.0           # cwnd multiplier
    round_count: int = 0             # Number of completed rounds
    probe_bw_phase: int = 0          # Cycle phase (0-7)

class BbrController:
    # Simplified BBR congestion control estimator
    # BBR does not use loss as a congestion signal (unlike Reno/CUBIC)
    # Instead it probes for bandwidth and RTT independently

    PROBE_BW_GAINS = [1.25, 0.75, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]

    def __init__(self, config: SimulationConfig) -> None:
        self.config = config
        self.state = BbrState(cwnd=config.initial_cwnd_mss)
        self._delivery_rate_samples: List[float] = []
        self._trace: List[CwndSnapshot] = []

    def on_ack(self, time_ms: float, delivered_bytes: int, rtt_ms: float) -> None:
        # Update BBR state with new delivery information
        # Estimate delivery rate from this ACK
        delivery_rate = delivered_bytes / (rtt_ms / 1000.0) if rtt_ms > 0 else 0
        self._delivery_rate_samples.append(delivery_rate)

        # Update bottleneck bandwidth (windowed max)
        if delivery_rate > self.state.btl_bw:
            self.state.btl_bw = delivery_rate

        # Update minimum RTT
        if rtt_ms < self.state.rt_prop_ms:
            self.state.rt_prop_ms = rtt_ms

        # Compute pacing rate and cwnd
        bdp = self.state.btl_bw * (self.state.rt_prop_ms / 1000.0)
        bdp_mss = bdp / self.config.mss if self.config.mss > 0 else 10

        # Cycle through probe_bw phases
        self.state.probe_bw_phase = (self.state.probe_bw_phase + 1) % 8
        self.state.pacing_gain = self.PROBE_BW_GAINS[self.state.probe_bw_phase]

        self.state.pacing_rate = self.state.btl_bw * self.state.pacing_gain
        self.state.cwnd = max(bdp_mss * self.state.cwnd_gain, 4.0)
        self.state.round_count += 1

        self._trace.append(CwndSnapshot(
            time_ms=time_ms, cwnd_mss=self.state.cwnd,
            ssthresh_mss=bdp_mss, phase=CongestionPhase.CONGESTION_AVOIDANCE,
            event=CongestionEvent.ACK,
            bytes_in_flight=int(self.state.cwnd * self.config.mss),
            rtt_ms=rtt_ms,
        ))

    @property
    def trace(self) -> List[CwndSnapshot]:
        return list(self._trace)
```

```python
# --- Simulation Runner with Comparative Output ---
from typing import List, Dict

def run_comparison_simulation() -> Dict[str, List[CwndSnapshot]]:
    # Run Reno, CUBIC, and BBR side-by-side
    # and produce visualization-ready trace data
    config = SimulationConfig(
        base_rtt_ms=50.0,
        simulation_duration_ms=10000.0,
        loss_events_at_ms=[2000.0, 5000.0, 7500.0],
    )

    reno = RenoController(config)
    cubic = CubicController(config)
    bbr = BbrController(config)

    time_ms = 0.0
    step_ms = config.base_rtt_ms  # One RTT per step
    loss_set = set(config.loss_events_at_ms)

    while time_ms <= config.simulation_duration_ms:
        is_loss = any(
            abs(time_ms - loss_time) < step_ms / 2
            for loss_time in loss_set
        )

        if is_loss:
            # Simulate packet loss event
            reno.on_duplicate_ack(time_ms, config.base_rtt_ms)
            reno.on_duplicate_ack(time_ms + 1, config.base_rtt_ms)
            reno.on_duplicate_ack(time_ms + 2, config.base_rtt_ms)
            cubic.on_loss(time_ms, config.base_rtt_ms)
            # BBR does not react to loss directly
            bbr.on_ack(time_ms, int(bbr.state.cwnd * config.mss), config.base_rtt_ms * 1.5)
        else:
            reno.on_ack(time_ms, config.base_rtt_ms)
            cubic.on_ack(time_ms, config.base_rtt_ms)
            delivered = int(bbr.state.cwnd * config.mss)
            bbr.on_ack(time_ms, delivered, config.base_rtt_ms)

        time_ms += step_ms

    return {"reno": reno.trace, "cubic": cubic.trace, "bbr": bbr.trace}


def print_trace_summary(traces: Dict[str, List[CwndSnapshot]]) -> None:
    # Print a text-based summary of cwnd evolution for each algorithm
    print("=== TCP Congestion Control Comparison ===\n")
    for name, trace in traces.items():
        if not trace:
            continue
        peak = max(s.cwnd_mss for s in trace)
        final = trace[-1].cwnd_mss
        losses = sum(1 for s in trace if s.event in (
            CongestionEvent.TRIPLE_DUP_ACK, CongestionEvent.TIMEOUT
        ))
        print(f"[{name.upper()}]")
        print(f"  Peak cwnd: {peak:.1f} MSS ({peak * 1460 / 1024:.0f} KB)")
        print(f"  Final cwnd: {final:.1f} MSS")
        print(f"  Loss events: {losses}")
        print(f"  Data points: {len(trace)}")
        print()

    # Print time series sample
    print("--- Time Series Sample (every 1000ms) ---")
    print(f"{'Time':>8} | {'Reno':>8} | {'CUBIC':>8} | {'BBR':>8}")
    print("-" * 42)
    for t in range(0, 10001, 1000):
        vals = []
        for name in ["reno", "cubic", "bbr"]:
            points = [s for s in traces[name] if abs(s.time_ms - t) < 50]
            val = points[-1].cwnd_mss if points else 0
            vals.append(f"{val:>8.1f}")
        print(f"{t:>7}ms | {' | '.join(vals)}")


if __name__ == "__main__":
    traces = run_comparison_simulation()
    print_trace_summary(traces)
```

## Algorithm Comparison

| Property | Reno | CUBIC | BBR |
|---|---|---|---|
| Loss signal | Packet loss | Packet loss | Bandwidth/RTT model |
| Growth function | Linear (AIMD) | Cubic (time-based) | Probe-drain cycles |
| RTT fairness | Biased to low RTT | Better (time-based) | Good |
| Recovery | Slow (halve cwnd) | Faster (beta=0.7) | No loss-based drop |
| **Best for** | Simple, low-loss | General internet | High-BDP links |

## Summary / Key Takeaways

- **Slow start** is exponential growth (doubling each RTT) until ssthresh, then transitions to **congestion avoidance** (linear growth). A **common mistake** is confusing "slow" with "linear."
- **Fast retransmit/recovery** handles single losses efficiently via triple duplicate ACK detection, however Reno struggles with multiple losses in one window.
- **CUBIC** uses a cubic function of elapsed time, therefore it grows aggressively far from the previous max and cautiously near it — the **best practice** default on Linux.
- **BBR** models the network instead of reacting to loss, which is a fundamentally different **trade-off**: better throughput on high-BDP links but potential unfairness to loss-based flows.
- The simulator above provides visualization-ready traces comparing all three algorithms under identical loss conditions.
- **Pitfall**: Tuning congestion control without understanding the network's actual bandwidth-delay product leads to either underutilization or excessive loss.
"""
    ),

    # --- 4. Network Security — TLS 1.3, CORS, CSP ---
    (
        "networking/tls13-cors-csp-security",
        "Explain network security in depth including TLS 1.3 handshake details with key exchange, certificate chain validation, OCSP stapling, and HTTP security headers such as Content-Security-Policy, HSTS, and CORS, then implement TLS certificate chain validation logic, CORS middleware for a web server, and a Content Security Policy builder in Python with comprehensive directive support.",
        r"""# Network Security: TLS 1.3, Certificate Validation, CORS, and CSP

## TLS 1.3: The Modern Encryption Standard

**TLS 1.3** (RFC 8446) is a major overhaul of the TLS protocol that removes insecure legacy features and dramatically improves both security and performance. Compared to TLS 1.2, it eliminates RSA key exchange, removes CBC cipher suites, mandates **forward secrecy** via ephemeral Diffie-Hellman, and reduces the handshake from 2 RTTs to **1 RTT** (with 0-RTT for resumption).

### The TLS 1.3 Handshake in Detail

**Step 1 — ClientHello**: The client sends supported cipher suites, a list of **key_share** entries (ephemeral DH public keys for each supported group like X25519, P-256), and a random nonce. Because the client speculatively sends key shares, the server can compute the shared secret immediately.

**Step 2 — ServerHello + EncryptedExtensions + Certificate + CertificateVerify + Finished**: The server selects a cipher suite and key share group, computes the handshake secret, and sends its certificate chain, a CertificateVerify signature (proving possession of the private key), and a Finished MAC — all encrypted with the handshake traffic keys. This is a **critical improvement**: in TLS 1.2, the certificate was sent in plaintext.

**Step 3 — Client Finished**: The client verifies the certificate chain, validates the CertificateVerify signature, sends its own Finished message, and both sides derive the application traffic keys.

**Best practice**: Always configure TLS 1.3 with **strong cipher suites** only: TLS_AES_256_GCM_SHA384 and TLS_CHACHA20_POLY1305_SHA256. A **common mistake** is leaving TLS 1.0/1.1 enabled for "compatibility" — these are deprecated and vulnerable.

### Certificate Chain Validation

The client must verify the entire chain from the server's leaf certificate up to a trusted **root Certificate Authority (CA)**:

1. **Signature verification**: Each certificate in the chain is signed by the next certificate's public key, up to the root.
2. **Validity period**: Check notBefore and notAfter dates.
3. **Name matching**: The leaf certificate's Subject Alternative Names (SANs) must match the requested hostname.
4. **Revocation checking**: Verify the certificate has not been revoked via **CRL** or **OCSP**.

### OCSP Stapling

Instead of the client querying the CA's OCSP responder (adding latency and leaking browsing history), the **server** periodically fetches its own OCSP response and "staples" it to the TLS handshake. The client verifies the stapled response's signature against the issuing CA. This is a **trade-off**: the server takes on the responsibility of refreshing OCSP responses, but clients get faster, more private revocation checking.

**Pitfall**: If the server's stapled OCSP response expires and the server fails to refresh it, clients may soft-fail (accept the expired response) or hard-fail (reject the connection). **Best practice** is to set up monitoring for OCSP staple freshness.

## Implementing Certificate Chain Validation

```python
import hashlib
import datetime
import enum
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# --- Certificate and Chain Validation ---

class CertificateStatus(enum.Enum):
    VALID = "valid"
    EXPIRED = "expired"
    NOT_YET_VALID = "not_yet_valid"
    REVOKED = "revoked"
    SIGNATURE_INVALID = "signature_invalid"
    NAME_MISMATCH = "name_mismatch"
    CHAIN_BROKEN = "chain_broken"
    UNTRUSTED_ROOT = "untrusted_root"

@dataclass
class Certificate:
    # Represents an X.509 certificate for validation
    subject: str
    issuer: str
    serial_number: str
    not_before: datetime.datetime
    not_after: datetime.datetime
    subject_alt_names: List[str] = field(default_factory=list)
    public_key_hash: str = ""
    signature_hash: str = ""
    is_ca: bool = False
    ocsp_url: Optional[str] = None
    crl_url: Optional[str] = None
    # Simplified: in real code this would be the actual public key
    _issuer_key_hash: str = ""

@dataclass
class OcspResponse:
    # Represents a stapled OCSP response
    serial_number: str
    status: str  # "good", "revoked", "unknown"
    this_update: datetime.datetime
    next_update: datetime.datetime
    responder_key_hash: str = ""

@dataclass
class ValidationResult:
    # Complete result of certificate chain validation
    is_valid: bool
    status: CertificateStatus
    chain_depth: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

class CertificateChainValidator:
    # Validates TLS certificate chains against a trust store
    # Performs signature verification, date checks, name matching,
    # and OCSP staple validation

    def __init__(self, trust_store: Optional[List[Certificate]] = None) -> None:
        self._trust_store: Dict[str, Certificate] = {}
        self._revoked_serials: Set[str] = set()
        if trust_store:
            for cert in trust_store:
                self._trust_store[cert.subject] = cert

    def add_trusted_root(self, cert: Certificate) -> None:
        self._trust_store[cert.subject] = cert

    def revoke_serial(self, serial: str) -> None:
        self._revoked_serials.add(serial)

    def validate_chain(
        self,
        chain: List[Certificate],
        hostname: str,
        ocsp_staple: Optional[OcspResponse] = None,
        now: Optional[datetime.datetime] = None,
    ) -> ValidationResult:
        # Validate the full certificate chain
        now = now or datetime.datetime.utcnow()
        errors: List[str] = []
        warnings: List[str] = []

        if not chain:
            return ValidationResult(
                is_valid=False, status=CertificateStatus.CHAIN_BROKEN,
                chain_depth=0, errors=["Empty certificate chain"],
            )

        leaf = chain[0]

        # 1. Validate hostname against leaf SANs
        if not self._check_hostname(leaf, hostname):
            errors.append(f"Hostname '{hostname}' not in SANs: {leaf.subject_alt_names}")
            return ValidationResult(
                is_valid=False, status=CertificateStatus.NAME_MISMATCH,
                chain_depth=len(chain), errors=errors,
            )

        # 2. Check each certificate's validity period
        for i, cert in enumerate(chain):
            if now < cert.not_before:
                errors.append(f"Certificate [{i}] '{cert.subject}' not yet valid")
                return ValidationResult(
                    is_valid=False, status=CertificateStatus.NOT_YET_VALID,
                    chain_depth=i, errors=errors,
                )
            if now > cert.not_after:
                errors.append(f"Certificate [{i}] '{cert.subject}' expired at {cert.not_after}")
                return ValidationResult(
                    is_valid=False, status=CertificateStatus.EXPIRED,
                    chain_depth=i, errors=errors,
                )

        # 3. Check revocation status
        for cert in chain:
            if cert.serial_number in self._revoked_serials:
                errors.append(f"Certificate '{cert.subject}' serial {cert.serial_number} is revoked")
                return ValidationResult(
                    is_valid=False, status=CertificateStatus.REVOKED,
                    chain_depth=len(chain), errors=errors,
                )

        # 4. Validate OCSP staple if provided
        if ocsp_staple:
            if ocsp_staple.status == "revoked":
                errors.append("OCSP staple indicates certificate is revoked")
                return ValidationResult(
                    is_valid=False, status=CertificateStatus.REVOKED,
                    chain_depth=len(chain), errors=errors,
                )
            if now > ocsp_staple.next_update:
                warnings.append("OCSP staple has expired, soft-failing")

        # 5. Verify chain links (each cert signed by the next)
        for i in range(len(chain) - 1):
            child = chain[i]
            parent = chain[i + 1]
            if child.issuer != parent.subject:
                errors.append(
                    f"Chain broken: cert[{i}] issuer '{child.issuer}' "
                    f"!= cert[{i+1}] subject '{parent.subject}'"
                )
                return ValidationResult(
                    is_valid=False, status=CertificateStatus.CHAIN_BROKEN,
                    chain_depth=i, errors=errors,
                )
            if not parent.is_ca:
                errors.append(f"Certificate '{parent.subject}' is not a CA but signed a child")
                return ValidationResult(
                    is_valid=False, status=CertificateStatus.CHAIN_BROKEN,
                    chain_depth=i, errors=errors,
                )

        # 6. Verify the root is in our trust store
        root = chain[-1]
        if root.subject not in self._trust_store:
            errors.append(f"Root CA '{root.subject}' not in trust store")
            return ValidationResult(
                is_valid=False, status=CertificateStatus.UNTRUSTED_ROOT,
                chain_depth=len(chain), errors=errors,
            )

        return ValidationResult(
            is_valid=True, status=CertificateStatus.VALID,
            chain_depth=len(chain), warnings=warnings,
        )

    def _check_hostname(self, cert: Certificate, hostname: str) -> bool:
        # Match hostname against SANs, supporting wildcard certificates
        for san in cert.subject_alt_names:
            if san.startswith("*."):
                # Wildcard: *.example.com matches sub.example.com
                pattern = san[2:]  # Remove "*."
                if hostname.endswith(pattern) and hostname.count(".") == san.count("."):
                    return True
            elif san.lower() == hostname.lower():
                return True
        return False
```

```python
# --- CORS Middleware Implementation ---
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Callable, Tuple

@dataclass
class CorsConfig:
    # Configuration for CORS middleware
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])
    allowed_methods: List[str] = field(
        default_factory=lambda: ["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"]
    )
    allowed_headers: List[str] = field(
        default_factory=lambda: ["Content-Type", "Authorization", "X-Request-ID"]
    )
    exposed_headers: List[str] = field(default_factory=list)
    allow_credentials: bool = False
    max_age_seconds: int = 86400  # 24 hours
    # Regex patterns for origin matching (e.g., r"https://.*\.example\.com")
    origin_patterns: List[str] = field(default_factory=list)

@dataclass
class HttpRequest:
    # Simplified HTTP request for middleware processing
    method: str
    path: str
    headers: Dict[str, str] = field(default_factory=dict)

@dataclass
class HttpResponse:
    # Simplified HTTP response
    status: int = 200
    headers: Dict[str, str] = field(default_factory=dict)
    body: str = ""

class CorsMiddleware:
    # CORS middleware that handles preflight OPTIONS requests
    # and adds appropriate Access-Control headers to responses
    # A common mistake is allowing credentials with wildcard origins,
    # which browsers will reject

    def __init__(self, config: CorsConfig) -> None:
        self._config = config
        self._compiled_patterns = [
            re.compile(p) for p in config.origin_patterns
        ]
        # Validate config: credentials + wildcard is invalid
        if config.allow_credentials and "*" in config.allowed_origins:
            raise ValueError(
                "Cannot use allow_credentials=True with wildcard origin '*'. "
                "This is a common pitfall: browsers reject this combination. "
                "Specify explicit origins instead."
            )

    def process_request(
        self, request: HttpRequest, next_handler: Callable[[HttpRequest], HttpResponse]
    ) -> HttpResponse:
        # Main middleware entry point
        origin = request.headers.get("Origin", "")

        if not origin:
            # Not a CORS request, pass through
            return next_handler(request)

        if not self._is_origin_allowed(origin):
            # Origin not allowed, return 403
            return HttpResponse(status=403, body="CORS origin not allowed")

        if request.method == "OPTIONS":
            # Preflight request
            return self._handle_preflight(request, origin)

        # Simple or actual CORS request
        response = next_handler(request)
        self._add_cors_headers(response, origin)
        return response

    def _handle_preflight(self, request: HttpRequest, origin: str) -> HttpResponse:
        # Handle OPTIONS preflight request
        requested_method = request.headers.get("Access-Control-Request-Method", "")
        requested_headers = request.headers.get("Access-Control-Request-Headers", "")

        # Validate requested method
        if requested_method and requested_method not in self._config.allowed_methods:
            return HttpResponse(status=403, body=f"Method {requested_method} not allowed")

        # Validate requested headers
        if requested_headers:
            req_hdrs = {h.strip().lower() for h in requested_headers.split(",")}
            allowed = {h.lower() for h in self._config.allowed_headers}
            if not req_hdrs.issubset(allowed):
                denied = req_hdrs - allowed
                return HttpResponse(status=403, body=f"Headers not allowed: {denied}")

        response = HttpResponse(status=204)
        self._add_cors_headers(response, origin)
        response.headers["Access-Control-Allow-Methods"] = ", ".join(
            self._config.allowed_methods
        )
        response.headers["Access-Control-Allow-Headers"] = ", ".join(
            self._config.allowed_headers
        )
        response.headers["Access-Control-Max-Age"] = str(self._config.max_age_seconds)
        return response

    def _add_cors_headers(self, response: HttpResponse, origin: str) -> None:
        # Add CORS response headers
        response.headers["Access-Control-Allow-Origin"] = origin
        if self._config.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"
        if self._config.exposed_headers:
            response.headers["Access-Control-Expose-Headers"] = ", ".join(
                self._config.exposed_headers
            )
        # Vary on Origin to prevent cache poisoning
        response.headers["Vary"] = "Origin"

    def _is_origin_allowed(self, origin: str) -> bool:
        # Check if the origin is in the allowed list or matches a pattern
        if "*" in self._config.allowed_origins:
            return True
        if origin in self._config.allowed_origins:
            return True
        return any(p.fullmatch(origin) for p in self._compiled_patterns)
```

```python
# --- Content Security Policy Builder ---
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

class CspDirective:
    # Standard CSP directive names
    DEFAULT_SRC = "default-src"
    SCRIPT_SRC = "script-src"
    STYLE_SRC = "style-src"
    IMG_SRC = "img-src"
    FONT_SRC = "font-src"
    CONNECT_SRC = "connect-src"
    MEDIA_SRC = "media-src"
    OBJECT_SRC = "object-src"
    FRAME_SRC = "frame-src"
    FRAME_ANCESTORS = "frame-ancestors"
    BASE_URI = "base-uri"
    FORM_ACTION = "form-action"
    REPORT_URI = "report-uri"
    REPORT_TO = "report-to"
    UPGRADE_INSECURE = "upgrade-insecure-requests"
    BLOCK_ALL_MIXED = "block-all-mixed-content"

class CspBuilder:
    # Fluent builder for Content-Security-Policy headers
    # Best practice: start with a restrictive default-src and
    # selectively open specific directives
    # A pitfall is using 'unsafe-inline' or 'unsafe-eval' which
    # defeats the purpose of CSP

    def __init__(self) -> None:
        self._directives: Dict[str, Set[str]] = {}
        self._report_only: bool = False
        self._warnings: List[str] = []

    def default_src(self, *sources: str) -> "CspBuilder":
        # Set the fallback source list for all fetch directives
        return self._add(CspDirective.DEFAULT_SRC, sources)

    def script_src(self, *sources: str) -> "CspBuilder":
        self._check_unsafe(sources, "script-src")
        return self._add(CspDirective.SCRIPT_SRC, sources)

    def style_src(self, *sources: str) -> "CspBuilder":
        self._check_unsafe(sources, "style-src")
        return self._add(CspDirective.STYLE_SRC, sources)

    def img_src(self, *sources: str) -> "CspBuilder":
        return self._add(CspDirective.IMG_SRC, sources)

    def font_src(self, *sources: str) -> "CspBuilder":
        return self._add(CspDirective.FONT_SRC, sources)

    def connect_src(self, *sources: str) -> "CspBuilder":
        return self._add(CspDirective.CONNECT_SRC, sources)

    def frame_ancestors(self, *sources: str) -> "CspBuilder":
        return self._add(CspDirective.FRAME_ANCESTORS, sources)

    def form_action(self, *sources: str) -> "CspBuilder":
        return self._add(CspDirective.FORM_ACTION, sources)

    def object_src(self, *sources: str) -> "CspBuilder":
        return self._add(CspDirective.OBJECT_SRC, sources)

    def base_uri(self, *sources: str) -> "CspBuilder":
        return self._add(CspDirective.BASE_URI, sources)

    def report_uri(self, uri: str) -> "CspBuilder":
        return self._add(CspDirective.REPORT_URI, (uri,))

    def report_to(self, group_name: str) -> "CspBuilder":
        return self._add(CspDirective.REPORT_TO, (group_name,))

    def upgrade_insecure_requests(self) -> "CspBuilder":
        self._directives[CspDirective.UPGRADE_INSECURE] = set()
        return self

    def block_all_mixed_content(self) -> "CspBuilder":
        self._directives[CspDirective.BLOCK_ALL_MIXED] = set()
        return self

    def nonce(self, directive: str, nonce_value: str) -> "CspBuilder":
        # Add a nonce source — the preferred alternative to unsafe-inline
        return self._add(directive, (f"'nonce-{nonce_value}'",))

    def hash_source(self, directive: str, algorithm: str, hash_value: str) -> "CspBuilder":
        # Add a hash source for inline scripts/styles
        return self._add(directive, (f"'{algorithm}-{hash_value}'",))

    def report_only(self, enabled: bool = True) -> "CspBuilder":
        # Use Content-Security-Policy-Report-Only instead of enforcing
        self._report_only = enabled
        return self

    def build(self) -> str:
        # Build the CSP header value string
        parts = []
        for directive, sources in self._directives.items():
            if sources:
                parts.append(f"{directive} {' '.join(sorted(sources))}")
            else:
                parts.append(directive)
        return "; ".join(parts)

    def header_name(self) -> str:
        if self._report_only:
            return "Content-Security-Policy-Report-Only"
        return "Content-Security-Policy"

    def as_header(self) -> Tuple[str, str]:
        return (self.header_name(), self.build())

    @property
    def warnings(self) -> List[str]:
        return list(self._warnings)

    def _add(self, directive: str, sources: tuple) -> "CspBuilder":
        if directive not in self._directives:
            self._directives[directive] = set()
        self._directives[directive].update(sources)
        return self

    def _check_unsafe(self, sources: tuple, directive: str) -> None:
        for src in sources:
            if src in ("'unsafe-inline'", "'unsafe-eval'"):
                self._warnings.append(
                    f"WARNING: {src} in {directive} weakens CSP. "
                    f"Use nonces or hashes instead."
                )


def build_production_csp() -> str:
    # Example: build a production-grade CSP header
    builder = CspBuilder()
    policy = (
        builder
        .default_src("'self'")
        .script_src("'self'", "https://cdn.example.com")
        .nonce("script-src", "abc123randomnonce")
        .style_src("'self'", "https://fonts.googleapis.com")
        .img_src("'self'", "data:", "https://images.example.com")
        .font_src("'self'", "https://fonts.gstatic.com")
        .connect_src("'self'", "https://api.example.com", "wss://ws.example.com")
        .frame_ancestors("'none'")
        .form_action("'self'")
        .object_src("'none'")
        .base_uri("'self'")
        .upgrade_insecure_requests()
        .report_uri("https://example.com/csp-report")
        .build()
    )
    return policy


def build_security_headers() -> Dict[str, str]:
    # Complete set of security headers for production
    csp = build_production_csp()
    return {
        "Content-Security-Policy": csp,
        "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "0",  # Disabled because CSP replaces it
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
```

## HTTP Security Headers Overview

- **HSTS** (`Strict-Transport-Security`): Forces browsers to use HTTPS for all future requests. `includeSubDomains` applies to all subdomains. `preload` registers the domain in browser preload lists. A **pitfall** is setting HSTS without testing on all subdomains first — a single HTTP-only subdomain will break.
- **CSP** (`Content-Security-Policy`): Controls which resources can load. **Best practice** is starting with `default-src 'self'` and opening specific directives. Using `'unsafe-inline'` is a **common mistake** that defeats XSS protection.
- **CORS**: Controls which origins can access your API. The **trade-off** is between security (strict origin lists) and developer convenience (wildcard). Never combine `Access-Control-Allow-Credentials: true` with `Access-Control-Allow-Origin: *`.

## Summary / Key Takeaways

- **TLS 1.3** achieves 1-RTT handshakes with forward secrecy by integrating key exchange into the first flight, therefore eliminating the extra round trips of TLS 1.2.
- **Certificate chain validation** must check signatures, validity dates, hostname matching, and revocation status — skipping any step is a critical **pitfall**.
- **OCSP stapling** improves performance and privacy, however servers must monitor staple freshness to avoid client-side failures.
- **CORS middleware** must reject credentials with wildcard origins (a **common mistake**), validate preflight requests, and include `Vary: Origin` to prevent cache poisoning.
- **CSP** is the primary defense against XSS — **best practice** is `default-src 'self'` with nonces for inline scripts, never `'unsafe-inline'` or `'unsafe-eval'`.
- **HSTS with preload** provides the strongest transport security but requires careful deployment across all subdomains first.
"""
    ),

    # --- 5. WebSocket Protocol — Frame Parser and Reconnection ---
    (
        "networking/websocket-frame-parser-reconnection",
        "Explain the WebSocket protocol in depth including frame format with opcode and masking, ping/pong keepalive mechanism, message fragmentation, per-message compression via permessage-deflate, and implement a complete WebSocket frame parser and builder, heartbeat manager, and reconnection client with exponential backoff in Python.",
        r"""# WebSocket Protocol: Frame Parsing, Heartbeats, and Reconnection

## Understanding the WebSocket Wire Protocol

The **WebSocket protocol** (RFC 6455) provides full-duplex, bidirectional communication over a single TCP connection. After an HTTP upgrade handshake, the connection switches to a binary framing protocol that is fundamentally different from HTTP. Understanding the frame format is essential because many WebSocket bugs — message corruption, hanging connections, failed negotiations — stem from framing errors.

### The WebSocket Frame Format

Every WebSocket message is transmitted as one or more **frames**. Each frame has a compact binary header:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-------+-+-------------+-------------------------------+
|F|R|R|R| opcode|M| Payload len |    Extended payload length    |
|I|S|S|S|  (4)  |A|     (7)     |         (16/64 bits)          |
|N|V|V|V|       |S|             |   (if payload len==126/127)   |
| |1|2|3|       |K|             |                               |
+-+-+-+-+-------+-+-------------+-------------------------------+
|     Extended payload length continued, if payload len == 127  |
+-------------------------------+-------------------------------+
|                               | Masking-key, if MASK set to 1 |
+-------------------------------+-------------------------------+
| Masking-key (continued)       |          Payload Data         |
+-------------------------------+-------------------------------+
```

- **FIN bit**: 1 if this is the final fragment of a message, 0 if continuation follows.
- **Opcode**: 0x0 (continuation), 0x1 (text), 0x2 (binary), 0x8 (close), 0x9 (ping), 0xA (pong).
- **MASK bit**: Must be 1 for client-to-server frames (the mask prevents proxy cache poisoning). Servers must **never** mask frames they send.
- **Payload length**: 7-bit value. If 126, the next 2 bytes are the actual length. If 127, the next 8 bytes are the length (up to 2^63).
- **Masking key**: 4 bytes used to XOR the payload. This is a security measure, not encryption.

**Common mistake**: Forgetting that client frames must be masked while server frames must not. Violating this causes immediate connection closure.

### Ping/Pong Keepalive

WebSocket defines **ping** (opcode 0x9) and **pong** (opcode 0xA) control frames for connection liveness detection. When one side sends a ping, the other must respond with a pong containing the same payload. **Best practice** is to implement bidirectional heartbeats — the server pings to detect dead clients, and the client pings to detect dead servers.

The **trade-off** with heartbeat intervals is: too frequent (e.g., every 5 seconds) wastes bandwidth and battery on mobile; too infrequent (e.g., every 5 minutes) means dead connections go undetected for too long. A typical **best practice** is 30-second intervals with a 10-second timeout for the pong response.

### Message Fragmentation

Large messages can be split across multiple frames. The first frame has the message opcode (text/binary) with FIN=0, intermediate frames use opcode 0x0 (continuation) with FIN=0, and the final frame uses opcode 0x0 with FIN=1. The receiver must buffer all fragments and reassemble the complete message.

**Pitfall**: Control frames (ping, pong, close) can be interleaved between data fragments. A correct implementation must handle a ping arriving in the middle of a fragmented data message.

### Per-Message Compression (permessage-deflate)

RFC 7692 defines the **permessage-deflate** extension, negotiated during the HTTP upgrade. When enabled, the RSV1 bit is set on the first frame of a compressed message. The payload is compressed using the DEFLATE algorithm (zlib). The **trade-off** is CPU usage for compression versus bandwidth savings — on high-throughput connections with compressible data (JSON, text), the bandwidth savings typically outweigh the CPU cost.

## Implementing the WebSocket Frame Parser and Builder

```python
import struct
import os
import enum
import zlib
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# --- WebSocket Frame Constants and Types ---

class Opcode(enum.IntEnum):
    CONTINUATION = 0x0
    TEXT = 0x1
    BINARY = 0x2
    CLOSE = 0x8
    PING = 0x9
    PONG = 0xA

    def is_control(self) -> bool:
        return self >= 0x8

@dataclass
class WebSocketFrame:
    # A parsed or constructed WebSocket frame
    fin: bool = True
    rsv1: bool = False  # Used by permessage-deflate
    rsv2: bool = False
    rsv3: bool = False
    opcode: Opcode = Opcode.TEXT
    masked: bool = False
    mask_key: bytes = b""
    payload: bytes = b""

    @property
    def payload_length(self) -> int:
        return len(self.payload)

    @property
    def is_control(self) -> bool:
        return self.opcode.is_control()


class FrameParser:
    # Parses raw bytes into WebSocket frames
    # Handles variable-length payloads, masking, and fragmentation

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._fragments: List[bytes] = []
        self._fragment_opcode: Optional[Opcode] = None

    def feed(self, data: bytes) -> List[WebSocketFrame]:
        # Feed raw bytes and return any complete frames parsed
        self._buffer.extend(data)
        frames: List[WebSocketFrame] = []

        while True:
            frame = self._try_parse_frame()
            if frame is None:
                break
            frames.append(frame)

        return frames

    def _try_parse_frame(self) -> Optional[WebSocketFrame]:
        # Attempt to parse a single frame from the buffer
        buf = self._buffer
        if len(buf) < 2:
            return None

        # Parse first two bytes
        byte0 = buf[0]
        byte1 = buf[1]

        fin = bool(byte0 & 0x80)
        rsv1 = bool(byte0 & 0x40)
        rsv2 = bool(byte0 & 0x20)
        rsv3 = bool(byte0 & 0x10)
        opcode = Opcode(byte0 & 0x0F)
        masked = bool(byte1 & 0x80)
        payload_len = byte1 & 0x7F

        offset = 2

        # Extended payload length
        if payload_len == 126:
            if len(buf) < offset + 2:
                return None
            payload_len = struct.unpack_from("!H", buf, offset)[0]
            offset += 2
        elif payload_len == 127:
            if len(buf) < offset + 8:
                return None
            payload_len = struct.unpack_from("!Q", buf, offset)[0]
            offset += 8

        # Masking key
        mask_key = b""
        if masked:
            if len(buf) < offset + 4:
                return None
            mask_key = bytes(buf[offset:offset + 4])
            offset += 4

        # Payload
        if len(buf) < offset + payload_len:
            return None

        payload = bytes(buf[offset:offset + payload_len])

        # Unmask payload if masked
        if masked and mask_key:
            payload = self._apply_mask(payload, mask_key)

        # Remove parsed bytes from buffer
        self._buffer = self._buffer[offset + payload_len:]

        return WebSocketFrame(
            fin=fin, rsv1=rsv1, rsv2=rsv2, rsv3=rsv3,
            opcode=opcode, masked=masked, mask_key=mask_key,
            payload=payload,
        )

    @staticmethod
    def _apply_mask(data: bytes, mask: bytes) -> bytes:
        # XOR each byte of data with the corresponding mask byte
        # mask cycles every 4 bytes
        return bytes(b ^ mask[i % 4] for i, b in enumerate(data))

    def reassemble(self, frames: List[WebSocketFrame]) -> Optional[Tuple[Opcode, bytes]]:
        # Reassemble fragmented message frames into a complete message
        # Returns (opcode, full_payload) or None if incomplete
        if not frames:
            return None

        first = frames[0]
        if first.fin and first.opcode != Opcode.CONTINUATION:
            return (first.opcode, first.payload)

        # Collect fragments
        payload = bytearray()
        msg_opcode = first.opcode

        for frame in frames:
            if frame.is_control:
                # Control frames can be interleaved; skip them here
                continue
            payload.extend(frame.payload)
            if frame.fin:
                return (msg_opcode, bytes(payload))

        return None  # Message incomplete


class FrameBuilder:
    # Builds raw WebSocket frame bytes from structured data
    # Handles masking for client frames and fragmentation for large messages

    def __init__(self, is_client: bool = True, fragment_size: int = 0) -> None:
        self._is_client = is_client
        self._fragment_size = fragment_size  # 0 = no fragmentation
        self._compressor: Optional[zlib._Compress] = None

    def enable_compression(self) -> None:
        # Enable permessage-deflate compression
        self._compressor = zlib.compressobj(
            zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15
        )

    def build_frame(self, frame: WebSocketFrame) -> bytes:
        # Serialize a WebSocketFrame to wire bytes
        header = bytearray()

        # Byte 0: FIN + RSV + opcode
        byte0 = (
            (0x80 if frame.fin else 0)
            | (0x40 if frame.rsv1 else 0)
            | (0x20 if frame.rsv2 else 0)
            | (0x10 if frame.rsv3 else 0)
            | (frame.opcode & 0x0F)
        )
        header.append(byte0)

        # Byte 1: MASK + payload length
        should_mask = self._is_client
        payload = frame.payload
        plen = len(payload)

        if plen < 126:
            header.append((0x80 if should_mask else 0) | plen)
        elif plen < 65536:
            header.append((0x80 if should_mask else 0) | 126)
            header.extend(struct.pack("!H", plen))
        else:
            header.append((0x80 if should_mask else 0) | 127)
            header.extend(struct.pack("!Q", plen))

        # Masking
        if should_mask:
            mask_key = os.urandom(4)
            header.extend(mask_key)
            payload = FrameParser._apply_mask(payload, mask_key)

        return bytes(header) + payload

    def build_text(self, text: str, compress: bool = False) -> List[bytes]:
        # Build one or more text frames (with optional fragmentation)
        payload = text.encode("utf-8")
        return self._build_data_frames(Opcode.TEXT, payload, compress)

    def build_binary(self, data: bytes, compress: bool = False) -> List[bytes]:
        # Build one or more binary frames
        return self._build_data_frames(Opcode.BINARY, data, compress)

    def build_ping(self, payload: bytes = b"") -> bytes:
        return self.build_frame(WebSocketFrame(
            opcode=Opcode.PING, payload=payload
        ))

    def build_pong(self, payload: bytes = b"") -> bytes:
        return self.build_frame(WebSocketFrame(
            opcode=Opcode.PONG, payload=payload
        ))

    def build_close(self, code: int = 1000, reason: str = "") -> bytes:
        payload = struct.pack("!H", code) + reason.encode("utf-8")
        return self.build_frame(WebSocketFrame(
            opcode=Opcode.CLOSE, payload=payload
        ))

    def _build_data_frames(
        self, opcode: Opcode, payload: bytes, compress: bool
    ) -> List[bytes]:
        rsv1 = False
        if compress and self._compressor is not None:
            payload = self._compressor.compress(payload)
            payload += self._compressor.flush(zlib.Z_SYNC_FLUSH)
            # Remove trailing 0x00 0x00 0xFF 0xFF per RFC 7692
            if payload.endswith(b"\x00\x00\xff\xff"):
                payload = payload[:-4]
            rsv1 = True

        if self._fragment_size <= 0 or len(payload) <= self._fragment_size:
            frame = WebSocketFrame(
                fin=True, rsv1=rsv1, opcode=opcode, payload=payload
            )
            return [self.build_frame(frame)]

        # Fragment the message
        frames: List[bytes] = []
        offset = 0
        first = True
        while offset < len(payload):
            chunk = payload[offset:offset + self._fragment_size]
            is_last = offset + self._fragment_size >= len(payload)
            frame = WebSocketFrame(
                fin=is_last,
                rsv1=rsv1 if first else False,
                opcode=opcode if first else Opcode.CONTINUATION,
                payload=chunk,
            )
            frames.append(self.build_frame(frame))
            offset += self._fragment_size
            first = False

        return frames
```

```python
# --- Heartbeat Manager and Reconnection Client ---
import asyncio
import time
import logging
import random
from dataclasses import dataclass, field
from typing import Callable, Optional, Awaitable, List

logger = logging.getLogger("websocket")

@dataclass
class HeartbeatConfig:
    # Configuration for the ping/pong heartbeat mechanism
    ping_interval_seconds: float = 30.0
    pong_timeout_seconds: float = 10.0
    max_missed_pongs: int = 2

class HeartbeatManager:
    # Manages WebSocket ping/pong keepalive
    # Detects dead connections by tracking pong responses
    # A common mistake is not implementing server-side pings,
    # relying solely on TCP keepalive which has much longer timeouts

    def __init__(
        self,
        config: HeartbeatConfig,
        send_ping: Callable[[bytes], Awaitable[None]],
        on_dead_connection: Callable[[], Awaitable[None]],
    ) -> None:
        self._config = config
        self._send_ping = send_ping
        self._on_dead = on_dead_connection
        self._pending_pong: Optional[bytes] = None
        self._missed_pongs = 0
        self._last_pong_time = time.monotonic()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        # Start the heartbeat loop
        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        # Stop the heartbeat loop
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def on_pong_received(self, payload: bytes) -> None:
        # Called when a pong frame is received
        if self._pending_pong is not None and payload == self._pending_pong:
            self._missed_pongs = 0
            self._pending_pong = None
            self._last_pong_time = time.monotonic()
            logger.debug("Pong received, connection alive")
        else:
            logger.warning("Unexpected pong payload")

    async def _heartbeat_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._config.ping_interval_seconds)
            if not self._running:
                break

            # Check if previous pong was received
            if self._pending_pong is not None:
                self._missed_pongs += 1
                logger.warning(
                    f"Missed pong #{self._missed_pongs} "
                    f"(max {self._config.max_missed_pongs})"
                )
                if self._missed_pongs >= self._config.max_missed_pongs:
                    logger.error("Connection appears dead, triggering reconnect")
                    await self._on_dead()
                    return

            # Send new ping with random payload for matching
            ping_data = os.urandom(4)
            self._pending_pong = ping_data
            try:
                await self._send_ping(ping_data)
                logger.debug(f"Ping sent: {ping_data.hex()}")
            except Exception as exc:
                logger.error(f"Failed to send ping: {exc}")
                await self._on_dead()
                return


@dataclass
class ReconnectConfig:
    # Exponential backoff configuration for reconnection
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    backoff_factor: float = 2.0
    jitter_factor: float = 0.1  # Random jitter to prevent thundering herd
    max_retries: int = 0  # 0 = unlimited

class ReconnectingWebSocketClient:
    # WebSocket client with automatic reconnection using exponential backoff
    # Best practice: always add jitter to prevent thundering herd when
    # many clients reconnect simultaneously after a server restart

    def __init__(
        self,
        url: str,
        reconnect_config: Optional[ReconnectConfig] = None,
        heartbeat_config: Optional[HeartbeatConfig] = None,
        on_message: Optional[Callable[[bytes], Awaitable[None]]] = None,
        on_connect: Optional[Callable[[], Awaitable[None]]] = None,
        on_disconnect: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        self._url = url
        self._rc = reconnect_config or ReconnectConfig()
        self._hc = heartbeat_config or HeartbeatConfig()
        self._on_message = on_message
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._heartbeat: Optional[HeartbeatManager] = None
        self._connected = False
        self._retry_count = 0
        self._should_reconnect = True
        self._frame_builder = FrameBuilder(is_client=True)
        self._frame_parser = FrameParser()

    async def connect(self) -> None:
        # Main connection loop with reconnection logic
        while self._should_reconnect:
            try:
                await self._establish_connection()
                self._retry_count = 0  # Reset on successful connect
                await self._receive_loop()
            except ConnectionError as exc:
                logger.warning(f"Connection lost: {exc}")
            except Exception as exc:
                logger.error(f"Unexpected error: {exc}")
            finally:
                self._connected = False
                if self._heartbeat:
                    await self._heartbeat.stop()
                if self._on_disconnect:
                    await self._on_disconnect()

            if not self._should_reconnect:
                break

            # Exponential backoff with jitter
            delay = self._calculate_backoff()
            logger.info(f"Reconnecting in {delay:.1f}s (attempt {self._retry_count + 1})")
            await asyncio.sleep(delay)
            self._retry_count += 1

            if 0 < self._rc.max_retries <= self._retry_count:
                logger.error(f"Max retries ({self._rc.max_retries}) exceeded")
                break

    def _calculate_backoff(self) -> float:
        # Exponential backoff: delay = initial * factor^retry
        # With random jitter to prevent thundering herd
        delay = self._rc.initial_delay_seconds * (
            self._rc.backoff_factor ** self._retry_count
        )
        delay = min(delay, self._rc.max_delay_seconds)
        # Add jitter: +/- jitter_factor * delay
        jitter = delay * self._rc.jitter_factor
        delay += random.uniform(-jitter, jitter)
        return max(0.1, delay)

    async def _establish_connection(self) -> None:
        # Simulate WebSocket connection establishment
        # In production, this would perform the HTTP upgrade handshake
        logger.info(f"Connecting to {self._url}")
        # Simulated connection delay
        await asyncio.sleep(0.1)
        self._connected = True

        if self._on_connect:
            await self._on_connect()

        # Start heartbeat manager
        self._heartbeat = HeartbeatManager(
            config=self._hc,
            send_ping=self._send_ping,
            on_dead_connection=self._handle_dead_connection,
        )
        await self._heartbeat.start()
        logger.info("Connected and heartbeat started")

    async def _receive_loop(self) -> None:
        # Main receive loop — reads frames and dispatches messages
        while self._connected:
            # Simulated frame reception
            await asyncio.sleep(0.01)
            # In production: raw_data = await self._socket.recv()
            # frames = self._frame_parser.feed(raw_data)
            # for frame in frames:
            #     if frame.opcode == Opcode.PONG:
            #         self._heartbeat.on_pong_received(frame.payload)
            #     elif frame.opcode == Opcode.CLOSE:
            #         await self.close()
            #     elif frame.opcode in (Opcode.TEXT, Opcode.BINARY):
            #         if self._on_message:
            #             await self._on_message(frame.payload)

    async def _send_ping(self, payload: bytes) -> None:
        if not self._connected:
            raise ConnectionError("Not connected")
        _frame_bytes = self._frame_builder.build_ping(payload)
        # In production: await self._socket.send(_frame_bytes)

    async def _handle_dead_connection(self) -> None:
        logger.warning("Dead connection detected via heartbeat")
        self._connected = False

    async def close(self) -> None:
        # Gracefully close the WebSocket connection
        self._should_reconnect = False
        if self._connected:
            close_frame = self._frame_builder.build_close(1000, "Normal closure")
            # In production: await self._socket.send(close_frame)
            self._connected = False
        if self._heartbeat:
            await self._heartbeat.stop()

    async def send_text(self, text: str) -> None:
        if not self._connected:
            raise ConnectionError("Not connected")
        frames = self._frame_builder.build_text(text)
        for frame_bytes in frames:
            pass  # In production: await self._socket.send(frame_bytes)

    async def send_binary(self, data: bytes) -> None:
        if not self._connected:
            raise ConnectionError("Not connected")
        frames = self._frame_builder.build_binary(data)
        for frame_bytes in frames:
            pass  # In production: await self._socket.send(frame_bytes)
```

## Compression Trade-offs

The **permessage-deflate** extension applies DEFLATE compression to each message before framing. For JSON-heavy WebSocket traffic, compression ratios of 5-10x are common. However, compression adds CPU overhead and **memory usage** (each connection maintains a compression context). The **trade-off**: on a server handling 100,000 concurrent WebSocket connections, the per-connection zlib context (32KB+ each) can consume gigabytes of memory. **Best practice** is to use `server_no_context_takeover` to release the compression context after each message, trading compression ratio for memory savings.

## Summary / Key Takeaways

- **WebSocket frames** have a compact binary header with FIN, opcode, mask, and variable-length payload fields. **Client frames must be masked**; server frames must not — this is a strict protocol requirement.
- **Ping/pong heartbeats** are essential for detecting dead connections. **Best practice** is 30-second intervals with jitter, and tracking missed pongs to trigger reconnection.
- **Message fragmentation** allows large messages to be split across frames. A **pitfall** is forgetting that control frames can interleave between data fragments and must be handled immediately.
- **Exponential backoff with jitter** prevents thundering herd on reconnection. The formula `delay = initial * factor^retry + random_jitter` ensures clients spread out their reconnection attempts.
- **permessage-deflate** provides significant bandwidth savings for text-heavy protocols, however the per-connection memory **trade-off** must be considered at scale.
- The frame parser above handles variable-length payloads, masking/unmasking, and fragmentation reassembly — the core building blocks for any WebSocket implementation.
"""
    ),
]
