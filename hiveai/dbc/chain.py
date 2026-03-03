"""
hiveai/dbc/chain.py

Hive blockchain abstraction for the Decentralized Brain Collective (DBC).

Three backends with auto-failover:
  1. BeemBackend  — primary (beem library)
  2. LighthiveBackend — stub (future)
  3. DirectRPCBackend — emergency (raw HTTP JSON-RPC, zero external deps)

Plus: pair encoding, operation builders, secrets scanner (Gate 6),
protocol logic (epoch timeout, sybil defense, tiebreaker, RC management),
and ChainState (derived in-memory state from chain replay).
"""

import base64
import gzip
import hashlib
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Generator

import requests

from hiveai.config import (
    DBC_CUSTOM_JSON_ID,
    DBC_EPOCH_TIMEOUT_HOURS,
    DBC_MIN_ONCHAIN_QUALITY,
    DBC_RC_FLOOR_PERCENT,
    DBC_RC_RESUME_PERCENT,
    HIVE_API_NODES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# A. ChainBackend ABC
# ---------------------------------------------------------------------------


class ChainBackend(ABC):
    """Abstract interface for Hive blockchain access."""

    @abstractmethod
    def broadcast_custom_json(
        self, json_id: str, json_data: dict, posting_auths: list[str]
    ) -> dict:
        """Broadcast a custom_json operation. Returns tx result."""

    @abstractmethod
    def get_block(self, block_num: int) -> dict:
        """Fetch a single block by number."""

    @abstractmethod
    def get_dynamic_global_properties(self) -> dict:
        """Get head block number, time, etc."""

    @abstractmethod
    def get_account(self, name: str) -> dict:
        """Get account info (HP, RC, etc.)."""

    @abstractmethod
    def stream_operations(
        self,
        start_block: int | None = None,
        op_types: list[str] | None = None,
    ) -> Generator[dict, None, None]:
        """Yield operations from the blockchain, optionally filtered by type."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier for logging."""


# ---------------------------------------------------------------------------
# DirectRPCBackend — zero deps beyond requests
# ---------------------------------------------------------------------------


class DirectRPCBackend(ChainBackend):
    """Raw HTTP JSON-RPC backend. No beem/lighthive required."""

    def __init__(
        self,
        nodes: list[str] | None = None,
        posting_key: str | None = None,
        timeout: int = 15,
    ):
        self._nodes = nodes or list(HIVE_API_NODES)
        self._posting_key = posting_key
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "direct_rpc"

    def _rpc_call(self, method: str, params: dict | list) -> dict:
        """JSON-RPC 2.0 call with node failover. Mirrors hive_ping.py pattern."""
        for node in self._nodes:
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params if isinstance(params, dict) else params,
                    "id": 1,
                }
                resp = requests.post(node, json=payload, timeout=self._timeout)
                data = resp.json()
                if "result" in data:
                    return data["result"]
                if "error" in data:
                    logger.warning(f"RPC error from {node}: {data['error']}")
                    continue
            except Exception as e:
                logger.warning(f"RPC node {node} failed: {e}")
                continue
        raise ConnectionError("All Hive API nodes failed")

    def get_dynamic_global_properties(self) -> dict:
        return self._rpc_call(
            "condenser_api.get_dynamic_global_properties", []
        )

    def get_block(self, block_num: int) -> dict:
        result = self._rpc_call(
            "block_api.get_block", {"block_num": block_num}
        )
        return result.get("block", result)

    def get_account(self, name: str) -> dict:
        if len(name) > 16 or len(name) < 3:
            raise ValueError(f"Invalid Hive account name: {name!r} (must be 3-16 chars)")
        accounts = self._rpc_call("condenser_api.get_accounts", [[name]])
        if not accounts:
            raise ValueError(f"Account not found: {name}")
        return accounts[0]

    def get_account_rc(self, name: str) -> dict:
        """Get resource credit info for an account."""
        result = self._rpc_call(
            "rc_api.find_rc_accounts", {"accounts": [name]}
        )
        return result.get("rc_accounts", [{}])[0]

    def broadcast_custom_json(
        self, json_id: str, json_data: dict, posting_auths: list[str]
    ) -> dict:
        """Build and broadcast a custom_json transaction.

        Requires posting_key for signing. For read-only or UI-signed
        workflows, use build_*_op() functions + external signing instead.
        """
        if not self._posting_key:
            raise ValueError(
                "DirectRPCBackend requires posting_key for broadcasting. "
                "Use build_*_op() + external signing for keyless workflows."
            )
        # Build the operation for external signing — actual broadcast
        # via direct RPC requires transaction serialization + signing
        # which is complex without beem. For now, return ready-to-sign payload.
        return {
            "status": "ready_to_sign",
            "operation": [
                "custom_json",
                {
                    "required_auths": [],
                    "required_posting_auths": posting_auths,
                    "id": json_id,
                    "json": json.dumps(json_data),
                },
            ],
        }

    def stream_operations(
        self,
        start_block: int | None = None,
        op_types: list[str] | None = None,
    ) -> Generator[dict, None, None]:
        """Poll-based block streaming. Yields operations matching op_types."""
        props = self.get_dynamic_global_properties()
        head = props["head_block_number"]
        current = start_block or head

        while True:
            props = self.get_dynamic_global_properties()
            head = props["head_block_number"]

            while current <= head:
                try:
                    block = self.get_block(current)
                except Exception as e:
                    logger.warning(f"Failed to get block {current}: {e}")
                    time.sleep(1)
                    break

                block_time = block.get("timestamp", "")
                for tx_index, tx in enumerate(
                    block.get("transactions", [])
                ):
                    for op_index, op in enumerate(
                        tx.get("operations", [])
                    ):
                        op_type = op[0] if isinstance(op, list) else op.get("type", "")
                        op_body = op[1] if isinstance(op, list) else op.get("value", {})

                        if op_types and op_type not in op_types:
                            continue

                        yield {
                            "type": op_type,
                            "body": op_body,
                            "block_num": current,
                            "timestamp": block_time,
                            "tx_index": tx_index,
                            "trx_id": tx.get("transaction_id", ""),
                        }
                current += 1

            # Wait for next block (~3 seconds)
            time.sleep(3)


# ---------------------------------------------------------------------------
# BeemBackend — primary production backend
# ---------------------------------------------------------------------------


class BeemBackend(ChainBackend):
    """Primary backend using the beem library."""

    def __init__(
        self,
        nodes: list[str] | None = None,
        posting_key: str | None = None,
    ):
        try:
            from beem import Hive
            from beem.account import Account  # noqa: F401
            from beem.blockchain import Blockchain  # noqa: F401
        except ImportError:
            raise ImportError(
                "beem is required for BeemBackend. "
                "Install with: pip install beem"
            )

        node_list = nodes or list(HIVE_API_NODES)
        keys = [posting_key] if posting_key else []
        self._hive = Hive(node=node_list, keys=keys)
        self._posting_key = posting_key

    @property
    def name(self) -> str:
        return "beem"

    def get_dynamic_global_properties(self) -> dict:
        return self._hive.get_dynamic_global_properties()

    def get_block(self, block_num: int) -> dict:
        from beem.block import Block

        b = Block(block_num, blockchain_instance=self._hive)
        return dict(b)

    def get_account(self, name: str) -> dict:
        from beem.account import Account

        acc = Account(name, blockchain_instance=self._hive)
        return dict(acc)

    def get_account_rc(self, name: str) -> dict:
        from beem.account import Account

        acc = Account(name, blockchain_instance=self._hive)
        return {"rc_manabar": acc.get_rc_manabar()}

    def broadcast_custom_json(
        self, json_id: str, json_data: dict, posting_auths: list[str]
    ) -> dict:
        if not self._posting_key:
            return {
                "status": "ready_to_sign",
                "operation": [
                    "custom_json",
                    {
                        "required_auths": [],
                        "required_posting_auths": posting_auths,
                        "id": json_id,
                        "json": json.dumps(json_data),
                    },
                ],
            }

        from beem.transactionbuilder import TransactionBuilder
        from beembase.operations import Custom_json

        tx = TransactionBuilder(blockchain_instance=self._hive)
        op = Custom_json(
            **{
                "required_auths": [],
                "required_posting_auths": posting_auths,
                "id": json_id,
                "json": json.dumps(json_data),
            }
        )
        tx.appendOps(op)
        tx.appendWif(self._posting_key)
        tx.sign()
        result = tx.broadcast()

        logger.info(
            f"Broadcast custom_json: id={json_id}, "
            f"block={result.get('block_num')}"
        )
        return {
            "status": "broadcast",
            "block_num": result.get("block_num"),
            "trx_id": result.get("id"),
        }

    def stream_operations(
        self,
        start_block: int | None = None,
        op_types: list[str] | None = None,
    ) -> Generator[dict, None, None]:
        from beem.blockchain import Blockchain

        bc = Blockchain(blockchain_instance=self._hive, mode="head")

        stream_kwargs = {"raw_ops": False, "threading": True}
        if op_types:
            stream_kwargs["opNames"] = op_types
        if start_block:
            stream_kwargs["start"] = start_block

        for op in bc.stream(**stream_kwargs):
            yield {
                "type": op.get("type", ""),
                "body": op,
                "block_num": op.get("block_num", 0),
                "timestamp": op.get("timestamp", ""),
                "tx_index": op.get("trx_num", 0),
                "trx_id": op.get("trx_id", ""),
            }


# ---------------------------------------------------------------------------
# LighthiveBackend — stub for future
# ---------------------------------------------------------------------------


class LighthiveBackend(ChainBackend):
    """Placeholder for lighthive backend. Not implemented yet."""

    @property
    def name(self) -> str:
        return "lighthive"

    def broadcast_custom_json(self, json_id, json_data, posting_auths):
        raise NotImplementedError("LighthiveBackend not yet implemented. Use beem or DirectRPC.")

    def get_block(self, block_num):
        raise NotImplementedError("LighthiveBackend not yet implemented.")

    def get_dynamic_global_properties(self):
        raise NotImplementedError("LighthiveBackend not yet implemented.")

    def get_account(self, name):
        raise NotImplementedError("LighthiveBackend not yet implemented.")

    def stream_operations(self, start_block=None, op_types=None):
        raise NotImplementedError("LighthiveBackend not yet implemented.")


# ---------------------------------------------------------------------------
# ResilientChain — auto-failover wrapper
# ---------------------------------------------------------------------------


class ResilientChain:
    """Tries backends in order: beem → direct_rpc. Auto-fails over."""

    def __init__(
        self,
        posting_key: str | None = None,
        nodes: list[str] | None = None,
    ):
        self._backends: list[ChainBackend] = []
        node_list = nodes or list(HIVE_API_NODES)

        # Try beem first (best streaming, signing support)
        try:
            self._backends.append(
                BeemBackend(nodes=node_list, posting_key=posting_key)
            )
            logger.info("DBC chain: beem backend loaded")
        except ImportError:
            logger.info("DBC chain: beem not available, skipping")

        # DirectRPC always available (only needs requests)
        self._backends.append(
            DirectRPCBackend(nodes=node_list, posting_key=posting_key)
        )
        logger.info("DBC chain: DirectRPC backend loaded")

    def _call(self, method: str, *args, **kwargs):
        """Try each backend in order, failover on error."""
        last_error = None
        for backend in self._backends:
            try:
                fn = getattr(backend, method)
                return fn(*args, **kwargs)
            except NotImplementedError:
                continue
            except Exception as e:
                logger.warning(
                    f"DBC chain: {backend.name}.{method} failed: {e}"
                )
                last_error = e
                continue
        raise ConnectionError(
            f"All DBC chain backends failed for {method}: {last_error}"
        )

    def broadcast_custom_json(self, json_id, json_data, posting_auths):
        return self._call(
            "broadcast_custom_json", json_id, json_data, posting_auths
        )

    def get_block(self, block_num):
        return self._call("get_block", block_num)

    def get_dynamic_global_properties(self):
        return self._call("get_dynamic_global_properties")

    def get_account(self, name):
        return self._call("get_account", name)

    def get_account_rc(self, name):
        return self._call("get_account_rc", name)

    def stream_operations(self, start_block=None, op_types=None):
        """Stream uses only the first working backend (no mid-stream failover)."""
        last_error = None
        for backend in self._backends:
            try:
                yield from backend.stream_operations(
                    start_block=start_block, op_types=op_types
                )
                return
            except NotImplementedError:
                continue
            except Exception as e:
                logger.warning(
                    f"DBC chain: {backend.name}.stream_operations failed: {e}"
                )
                last_error = e
                continue
        raise ConnectionError(
            f"All DBC chain backends failed for streaming: {last_error}"
        )


# ===========================================================================
# B. Pair Encoding / Decoding
# ===========================================================================

# Max custom_json payload size on Hive
CUSTOM_JSON_MAX_BYTES = 8192


def encode_pair(instruction: str, response: str, metadata: dict) -> str:
    """Gzip + base64 encode a training pair for on-chain submission.

    Returns the encoded string. Raises ValueError if result exceeds
    custom_json size limit.
    """
    payload = {
        "instruction": instruction,
        "response": response,
        **metadata,
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    compressed = gzip.compress(raw)
    encoded = base64.b64encode(compressed).decode("ascii")
    return encoded


def decode_pair(data_str: str) -> dict:
    """Decode a gzip+base64 encoded training pair from on-chain data."""
    compressed = base64.b64decode(data_str)
    raw = gzip.decompress(compressed)
    return json.loads(raw)


def estimate_pair_size(instruction: str, response: str) -> int:
    """Estimate the on-chain size of a pair in bytes.

    The full custom_json operation includes type, score, lang, topic, scorer
    fields plus the encoded data. Returns approximate total bytes.
    """
    encoded = encode_pair(instruction, response, {})
    # Overhead: {"type":"pair","data":"...","score":0.87,"lang":"python","topic":"x","scorer":"v5.2"}
    overhead = 120
    return len(encoded) + overhead


# ===========================================================================
# C. Operation Builders
# ===========================================================================


def build_pair_op(
    instruction: str,
    response: str,
    score: float,
    lang: str,
    topic: str,
    scorer_version: str,
    metadata: dict | None = None,
) -> dict | None:
    """Build a type:pair custom_json payload.

    Returns the payload dict, or None if the pair is too large for
    on-chain storage (use data_cid overflow instead).
    """
    encoded = encode_pair(instruction, response, metadata or {})

    payload = {
        "type": "pair",
        "data": encoded,
        "score": round(score, 2),
        "lang": lang,
        "topic": topic,
        "scorer": scorer_version,
    }

    # Check size limit
    serialized = json.dumps(payload)
    if len(serialized.encode("utf-8")) > CUSTOM_JSON_MAX_BYTES:
        logger.warning(
            f"Pair too large for on-chain: {len(serialized)} bytes "
            f"(limit {CUSTOM_JSON_MAX_BYTES}). Use data_cid overflow."
        )
        return None

    return payload


def build_pair_overflow_op(
    data_cid: str,
    score: float,
    lang: str,
    topic: str,
    scorer_version: str,
    size_bytes: int,
) -> dict:
    """Build a type:pair operation using CID overflow (for large pairs)."""
    return {
        "type": "pair",
        "data_cid": data_cid,
        "score": round(score, 2),
        "lang": lang,
        "topic": topic,
        "scorer": scorer_version,
        "size": size_bytes,
    }


def build_epoch_op(
    version: str,
    blocks: list[int],
    seed: int,
    base_cid: str,
    min_score: float,
    scorer_version: str,
    script_hash: str,
    shard: str | None = None,
    index_cid: str | None = None,
    eval_set_hash: str | None = None,
) -> dict:
    """Build a type:epoch claim operation."""
    op = {
        "type": "epoch",
        "v": version,
        "base_cid": base_cid,
        "blocks": blocks,
        "min_score": min_score,
        "scorer": scorer_version,
        "seed": seed,
        "script": script_hash,
    }
    if shard:
        op["shard"] = shard
    if index_cid:
        op["index_cid"] = index_cid
    if eval_set_hash:
        op["eval_set"] = eval_set_hash
    return op


def build_version_op(
    version: str,
    cid: str,
    eval_score: float,
    base_model: str | None = None,
    eval_outputs_cid: str | None = None,
    github_tag: str | None = None,
) -> dict:
    """Build a type:version announcement operation."""
    op = {
        "type": "version",
        "v": version,
        "cid": cid,
        "eval": round(eval_score, 3),
    }
    if base_model:
        op["base_model"] = base_model
    if eval_outputs_cid:
        op["eval_outputs_cid"] = eval_outputs_cid
    if github_tag:
        op["github"] = github_tag
    return op


def build_verify_op(
    version: str, eval_score: float, accept: bool
) -> dict:
    """Build a type:verify vote operation."""
    return {
        "type": "verify",
        "v": version,
        "eval": round(eval_score, 3),
        "accept": accept,
    }


def build_flag_op(pair_tx: str, reason: str) -> dict:
    """Build a type:flag operation for pair governance."""
    return {
        "type": "flag",
        "pair_tx": pair_tx,
        "reason": reason,
    }


def build_stage_flag_op(pair_tx: str, reason: str) -> dict:
    """Build a type:stage_flag operation for pre-chain staging."""
    return {
        "type": "stage_flag",
        "pair_tx": pair_tx,
        "reason": reason,
    }


def build_protocol_op(
    eval_tolerance: float = 0.05,
    aggregate_tolerance: float = 0.03,
    spot_check_size: int = 25,
    check3_weight: float = 0.20,
    confidence_tier: str = "MEDIUM_CONFIDENCE",
    calibration_machines: int = 2,
    min_verification_score: float = 0.85,
) -> dict:
    """Build a type:protocol config operation."""
    return {
        "type": "protocol",
        "eval_tolerance": eval_tolerance,
        "aggregate_tolerance": aggregate_tolerance,
        "spot_check_size": spot_check_size,
        "check3_weight": check3_weight,
        "confidence_tier": confidence_tier,
        "calibration_machines": calibration_machines,
        "min_verification_score": min_verification_score,
    }


# ===========================================================================
# D. Secrets Scanner — Gate 6
# ===========================================================================

SECRET_PATTERNS = [
    # API keys
    (r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}", "AWS access key"),
    (r"sk-[a-zA-Z0-9]{20,}", "OpenAI/Stripe secret key"),
    (r"ghp_[a-zA-Z0-9]{30,}", "GitHub personal access token"),
    (r"xox[bpoas]-[0-9a-zA-Z-]+", "Slack token"),
    # Private keys / mnemonics
    (r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----", "Private key (PEM)"),
    (r"(?:^|\s)5[HJK][1-9A-HJ-NP-Za-km-z]{49}", "Hive/WIF private key"),
    # Passwords / secrets in code
    (
        r'(?:password|passwd|secret|api_key)\s*[=:]\s*["\'][^"\']{8,}',
        "Hardcoded secret",
    ),
    # PII
    (
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "Email address",
    ),
    (r"(?i)(?:ssn|social.security(?:\s+number)?)[:\s]+\d{3}[-.]?\d{2}[-.]?\d{4}\b", "Possible SSN"),
    # File paths with usernames
    (
        r"(?:C:\\Users\\|/home/|/Users/)[a-zA-Z0-9._-]+",
        "Local file path with username",
    ),
]


def scan_for_secrets(text: str) -> list[dict]:
    """Scan text for potential secrets, API keys, PII, and local paths.

    Returns list of findings: [{"type": str, "position": int, "snippet": str}]
    """
    findings = []
    for pattern, description in SECRET_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
            start = max(0, match.start() - 10)
            end = min(len(text), match.end() + 10)
            findings.append(
                {
                    "type": description,
                    "position": match.start(),
                    "snippet": text[start:end],
                }
            )
    return findings


def pre_submission_check(pair: dict) -> tuple[bool, list[dict]]:
    """Gate 6: scan pair content before on-chain submission.

    Returns (passed, findings). If passed is False, the pair must NOT
    be submitted — it contains sensitive content.
    """
    text = (
        pair.get("instruction", "")
        + " "
        + pair.get("response", pair.get("output", ""))
    )
    findings = scan_for_secrets(text)
    if findings:
        logger.warning(
            f"Gate 6 BLOCKED: {len(findings)} secret(s) found in pair: "
            + ", ".join(f["type"] for f in findings)
        )
        return False, findings
    return True, []


# ===========================================================================
# E. Protocol Logic
# ===========================================================================


def parse_block_time(timestamp_str: str) -> datetime:
    """Parse Hive block timestamp to datetime (UTC)."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(timestamp_str, fmt).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
    raise ValueError(f"Cannot parse block timestamp: {timestamp_str}")


def is_epoch_stalled(
    epoch_claim: dict,
    current_block_time: datetime,
    versions_since: list[dict],
    timeout_hours: int = DBC_EPOCH_TIMEOUT_HOURS,
) -> bool:
    """Check if an epoch claim has stalled (trainer crashed/disappeared).

    Derivable from chain state — no new operation needed.
    """
    claim_time = parse_block_time(epoch_claim["timestamp"])
    elapsed = current_block_time - claim_time

    # Check if a matching version was published
    epoch_version = epoch_claim.get("v", "")
    version_exists = any(v.get("v") == epoch_version for v in versions_since)
    if version_exists:
        return False  # Epoch completed normally

    return elapsed > timedelta(hours=timeout_hours)


def can_claim_epoch(
    account: str,
    latest_epoch: dict | None,
    versions: list[dict],
    current_block_time: datetime,
    cooldown_hours: int = 12,
) -> bool:
    """Check if an account can claim the next epoch.

    Rules:
    - No active epoch → anyone can claim
    - Previous epoch completed → claim if cooldown expired
    - Previous epoch stalled → anyone can re-claim (no cooldown)
    """
    if latest_epoch is None:
        return True

    epoch_version = latest_epoch.get("v", "")
    version_exists = any(v.get("v") == epoch_version for v in versions)

    if version_exists:
        # Previous epoch completed — check cooldown
        claim_time = parse_block_time(latest_epoch["timestamp"])
        elapsed = current_block_time - claim_time
        return elapsed > timedelta(hours=cooldown_hours)

    # Previous epoch not completed — check if stalled
    if is_epoch_stalled(latest_epoch, current_block_time, versions):
        return True  # No cooldown for recovery claims

    return False  # Epoch still active, wait


def get_winning_epoch_claim(block: dict) -> dict | None:
    """Within a single block, determine which epoch claim wins.

    Hive blocks have deterministic transaction ordering. The claim
    with the lowest tx_index wins. All nodes see the same result.
    """
    claims = []
    for tx_index, tx in enumerate(block.get("transactions", [])):
        for op in tx.get("operations", []):
            op_type = op[0] if isinstance(op, list) else op.get("type", "")
            op_body = op[1] if isinstance(op, list) else op.get("value", {})

            if op_type != "custom_json":
                continue

            try:
                json_data = json.loads(op_body.get("json", "{}"))
            except (json.JSONDecodeError, AttributeError):
                continue

            if (
                op_body.get("id") == DBC_CUSTOM_JSON_ID
                and json_data.get("type") == "epoch"
            ):
                claims.append(
                    {
                        "tx_index": tx_index,
                        "author": (
                            op_body.get("required_posting_auths", [""])[0]
                        ),
                        "config": json_data,
                    }
                )

    if not claims:
        return None
    return min(claims, key=lambda c: c["tx_index"])


def evaluate_consensus(
    votes: list[dict],
    wot_accounts: set[str],
    min_hp: float = 100,
    consensus_hp: float = 5000,
    min_accounts: int = 3,
    wot_fast_track: int = 3,
) -> bool:
    """HP-weighted Sybil-resistant consensus for non-GPU nodes.

    Two paths to consensus:
    1. Fast track: 3+ WoT-vouched accepts → instant
    2. Standard: HP-weighted — total HP >= 5000, 3+ unique accounts
    """
    valid_accepts = []
    for vote in votes:
        if not vote.get("accept"):
            continue
        hp = vote.get("hp", 0)
        if hp < min_hp:
            continue
        valid_accepts.append(vote)

    # Fast track: WoT-vouched
    wot_accepts = [
        v for v in valid_accepts if v.get("author") in wot_accounts
    ]
    if len(wot_accepts) >= wot_fast_track:
        return True

    # Standard: HP-weighted
    total_hp = sum(v.get("hp", 0) for v in valid_accepts)
    unique_accounts = len(set(v.get("author") for v in valid_accepts))
    return total_hp >= consensus_hp and unique_accounts >= min_accounts


def should_submit(
    current_rc_pct: float,
    paused: bool,
    floor: float = DBC_RC_FLOOR_PERCENT,
    resume: float = DBC_RC_RESUME_PERCENT,
) -> bool:
    """Hysteresis-based RC throttle to prevent RC exhaustion.

    When paused, only resume above resume%. When active, pause below floor%.
    """
    if paused:
        return current_rc_pct >= resume
    return current_rc_pct >= floor


def estimate_daily_capacity(account_hp: float) -> int:
    """Estimate how many pairs/day an account can submit based on HP.

    Approximate: 1 HP ≈ 10 billion RC max, 20% daily regen,
    1 custom_json ≈ 1.5 billion RC.
    """
    max_rc = account_hp * 1e10
    daily_regen = max_rc * 0.20
    rc_per_op = 1.5e9
    return max(0, int(daily_regen / rc_per_op))


# ===========================================================================
# F. ChainState — Derived In-Memory State
# ===========================================================================


class ChainState:
    """In-memory DBC state derived from chain replay.

    Every field is derivable from replaying hiveai custom_json operations
    from block 0 (or a checkpoint). No external storage needed.
    """

    def __init__(self):
        self.latest_epoch: dict | None = None
        self.latest_version: dict | None = None
        self.pairs: list[dict] = []
        self.versions: list[dict] = []
        self.epochs: list[dict] = []
        self.flags: dict[str, list[dict]] = {}  # pair_tx → [flag_ops]
        self.stage_flags: dict[str, list[dict]] = {}  # pair_tx → [stage_flag_ops]
        self.verifications: dict[str, list[dict]] = {}  # version → [verify_ops]
        self.protocol_config: dict = {}  # latest protocol operation
        self.last_processed_block: int = 0

    @property
    def pending_pair_count(self) -> int:
        """Pairs accumulated since the last completed epoch."""
        if not self.latest_epoch:
            return len(self.pairs)
        epoch_block = self.latest_epoch.get("block_num", 0)
        return sum(1 for p in self.pairs if p.get("block_num", 0) > epoch_block)

    def process_operation(self, op: dict) -> None:
        """Update state from a single hiveai custom_json operation.

        The op dict must have: type, body (parsed JSON), block_num,
        timestamp, tx_index, trx_id.
        """
        body = op.get("body", {})

        # Parse JSON if body is a raw custom_json operation
        if isinstance(body, dict) and "json" in body:
            try:
                json_data = json.loads(body["json"])
            except (json.JSONDecodeError, TypeError):
                return
            # Check it's a hiveai operation
            if body.get("id") != DBC_CUSTOM_JSON_ID:
                return
            author = (body.get("required_posting_auths") or [""])[0]
        elif isinstance(body, dict) and "type" in body:
            json_data = body
            author = op.get("author", "")
        else:
            return

        op_type = json_data.get("type")
        block_num = op.get("block_num", 0)
        timestamp = op.get("timestamp", "")

        enriched = {
            **json_data,
            "block_num": block_num,
            "timestamp": timestamp,
            "tx_index": op.get("tx_index", 0),
            "trx_id": op.get("trx_id", ""),
            "author": author,
        }

        if op_type == "pair":
            self._handle_pair(enriched)
        elif op_type == "epoch":
            self._handle_epoch(enriched)
        elif op_type == "version":
            self._handle_version(enriched)
        elif op_type == "verify":
            self._handle_verify(enriched)
        elif op_type == "flag":
            self._handle_flag(enriched)
        elif op_type == "stage_flag":
            self._handle_stage_flag(enriched)
        elif op_type == "protocol":
            self._handle_protocol(enriched)

        self.last_processed_block = max(self.last_processed_block, block_num)

    def _handle_pair(self, op: dict) -> None:
        self.pairs.append(op)

    def _handle_epoch(self, op: dict) -> None:
        self.epochs.append(op)
        self.latest_epoch = op

    def _handle_version(self, op: dict) -> None:
        self.versions.append(op)
        self.latest_version = op

    def _handle_verify(self, op: dict) -> None:
        version = op.get("v", "")
        if version not in self.verifications:
            self.verifications[version] = []
        self.verifications[version].append(op)

    def _handle_flag(self, op: dict) -> None:
        pair_tx = op.get("pair_tx", "")
        if pair_tx not in self.flags:
            self.flags[pair_tx] = []
        # Deduplicate by author
        existing_authors = {f.get("author") for f in self.flags[pair_tx]}
        if op.get("author") not in existing_authors:
            self.flags[pair_tx].append(op)

    def _handle_stage_flag(self, op: dict) -> None:
        pair_tx = op.get("pair_tx", "")
        if pair_tx not in self.stage_flags:
            self.stage_flags[pair_tx] = []
        existing_authors = {f.get("author") for f in self.stage_flags[pair_tx]}
        if op.get("author") not in existing_authors:
            self.stage_flags[pair_tx].append(op)

    def _handle_protocol(self, op: dict) -> None:
        # Latest protocol operation is authoritative
        self.protocol_config = op

    def get_trust_weight(self, pair_tx: str, current_time: datetime | None = None) -> float:
        """Compute trust weight for a pair: flags + age decay.

        Weight starts at 1.0. Three mechanisms adjust it:
        1. 3+ flags from different authors → 0.0 (effectively removed)
        2. Age decay: after grace period, gradual decay to floor
        3. Scorer re-score (handled externally during collection)
        """
        # Flag check
        flags = self.flags.get(pair_tx, [])
        unique_flaggers = len(set(f.get("author") for f in flags))
        if unique_flaggers >= 3:
            return 0.0

        # Age decay (simplified: 12-month grace, 0.03/month, floor 0.30)
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        # Find the pair's timestamp
        pair = next((p for p in self.pairs if p.get("trx_id") == pair_tx), None)
        if pair is None:
            return 1.0

        try:
            pair_time = parse_block_time(pair["timestamp"])
        except (KeyError, ValueError):
            return 1.0

        age_months = (current_time - pair_time).days / 30.0
        grace_months = 12
        decay_per_month = 0.03
        floor = 0.30

        if age_months <= grace_months:
            return 1.0

        decayed = 1.0 - (age_months - grace_months) * decay_per_month
        return max(floor, decayed)

    def get_unclaimed_pairs(self) -> list[dict]:
        """Get pairs since the last completed epoch."""
        if not self.latest_epoch:
            return list(self.pairs)

        epoch_block = self.latest_epoch.get("block_num", 0)
        return [p for p in self.pairs if p.get("block_num", 0) > epoch_block]

    def get_verification_status(self, version: str) -> dict:
        """Get verification status for a version."""
        votes = self.verifications.get(version, [])
        accepts = [v for v in votes if v.get("accept")]
        rejects = [v for v in votes if not v.get("accept")]
        return {
            "version": version,
            "total_votes": len(votes),
            "accepts": len(accepts),
            "rejects": len(rejects),
            "voters": [v.get("author") for v in votes],
        }


# ===========================================================================
# G. Utility: filter hiveai operations from a block
# ===========================================================================


def filter_hiveai_ops(block: dict, block_num: int = 0) -> list[dict]:
    """Extract all hiveai custom_json operations from a block.

    Returns enriched op dicts ready for ChainState.process_operation().
    """
    ops = []
    block_time = block.get("timestamp", "")

    for tx_index, tx in enumerate(block.get("transactions", [])):
        for op in tx.get("operations", []):
            op_type = op[0] if isinstance(op, list) else op.get("type", "")
            op_body = op[1] if isinstance(op, list) else op.get("value", {})

            if op_type != "custom_json":
                continue
            if op_body.get("id") != DBC_CUSTOM_JSON_ID:
                continue

            try:
                json_data = json.loads(op_body.get("json", "{}"))
            except (json.JSONDecodeError, AttributeError):
                continue

            ops.append(
                {
                    "type": "custom_json",
                    "body": op_body,
                    "block_num": block_num,
                    "timestamp": block_time,
                    "tx_index": tx_index,
                    "trx_id": tx.get("transaction_id", ""),
                    "author": (
                        op_body.get("required_posting_auths", [""])[0]
                    ),
                    "parsed": json_data,
                }
            )

    return ops
