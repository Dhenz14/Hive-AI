"""
hiveai/dbc/node.py

DBC Node Daemon — watches the Hive blockchain, verifies adapters,
manages updates, and submits training pairs.

Two operational modes:
  - GPU node: downloads adapters, runs eval, posts verification votes
  - Non-GPU node: waits for HP-weighted consensus, then downloads

Run modes:
  - Normal: full participation (read + write + verify)
  - Dry-run: read-only (watches chain, updates state, no broadcasts)
  - Mock: in-memory chain (for testing without real blockchain)
"""

import json
import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from hiveai.config import (
    DBC_ACCOUNT,
    DBC_CUSTOM_JSON_ID,
    DBC_MIN_ONCHAIN_QUALITY,
    DBC_POSTING_KEY,
    DBC_RC_FLOOR_PERCENT,
    DBC_RC_RESUME_PERCENT,
    LLAMA_SERVER_BASE_URL,
)
from hiveai.dbc.chain import (
    ChainState,
    ResilientChain,
    build_pair_op,
    build_verify_op,
    decode_pair,
    encode_pair,
    estimate_daily_capacity,
    evaluate_consensus,
    is_epoch_stalled,
    parse_block_time,
    pre_submission_check,
    scan_for_secrets,
    should_submit,
)
from hiveai.dbc.hivepoa import HivePoAClient

logger = logging.getLogger(__name__)


@dataclass
class NodeConfig:
    """Configuration for a DBC node."""

    account: str = ""
    posting_key: str | None = None
    gpu_available: bool = False
    adapter_dir: str = "adapters"
    eval_script: str | None = None  # Path to scripts/run_eval.py
    wot_accounts: set[str] = field(default_factory=set)
    dry_run: bool = False
    mock_chain: bool = False
    poll_interval: float = 3.0
    base_url: str = "http://localhost:11435"  # llama-server


class MockChain:
    """In-memory mock chain for testing. Mimics ResilientChain interface."""

    def __init__(self):
        self._operations: list[dict] = []
        self._block_num = 1

    def inject_operation(self, op_type: str, json_data: dict, author: str = "testuser"):
        """Inject a fake operation for testing."""
        self._block_num += 1
        self._operations.append({
            "type": "custom_json",
            "body": {
                "id": DBC_CUSTOM_JSON_ID,
                "json": json.dumps(json_data),
                "required_posting_auths": [author],
            },
            "block_num": self._block_num,
            "timestamp": "2026-01-01T00:00:00",
            "tx_index": 0,
            "trx_id": f"mock_{self._block_num}",
        })

    def stream_operations(self, start_block=None, op_types=None):
        """Yield injected operations."""
        for op in self._operations:
            yield op
        # After draining, block (simulating waiting for new blocks)
        while True:
            time.sleep(1)

    def broadcast_custom_json(self, json_id, json_data, posting_auths):
        logger.info(f"[MOCK] Would broadcast: {json_data.get('type', '?')}")
        self._block_num += 1
        return {"status": "mock", "block_num": self._block_num}

    def get_account(self, name):
        return {"name": name, "balance": "1000.000 HIVE"}

    def get_account_rc(self, name):
        return {"rc_manabar": {"current_mana": 90000000000, "max_mana": 100000000000}}

    def get_dynamic_global_properties(self):
        return {"head_block_number": self._block_num}


class DBCNode:
    """DBC node daemon. Watches chain, verifies adapters, manages updates.

    Usage:
        config = NodeConfig(
            account="myaccount",
            posting_key="5J...",
            gpu_available=True,
            eval_script="scripts/run_eval.py",
        )
        node = DBCNode(config)
        node.start()  # Runs in background thread
        # ... later ...
        node.stop()
    """

    def __init__(self, config: NodeConfig):
        self.config = config

        # Chain backend
        if config.mock_chain:
            self.chain = MockChain()
        else:
            self.chain = ResilientChain(
                posting_key=config.posting_key or DBC_POSTING_KEY
            )

        # Storage backend
        self.storage = HivePoAClient(adapter_dir=config.adapter_dir)

        # Derived state
        self.state = ChainState()

        # Runtime state
        self._running = threading.Event()
        self._thread: threading.Thread | None = None
        self._submission_paused = False
        self._local_queue: list[dict] = []
        self._current_adapter_version: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, start_block: int | None = None) -> None:
        """Start the daemon in a background thread."""
        if self._running.is_set():
            logger.warning("DBC node already running")
            return

        # Populate WoT accounts from HivePoA trust registry if available.
        # This replaces hardcoded wot_accounts with the live trusted set.
        # If HivePoA is unreachable or trust is disabled, falls back to
        # whatever was in config.wot_accounts (backward compatible).
        try:
            trusted = self.storage.get_trusted_accounts("dbc_trainer")
            if trusted:
                logger.info(f"Loaded {len(trusted)} trusted dbc_trainer accounts from HivePoA")
                self.config.wot_accounts = trusted
            elif self.config.wot_accounts:
                logger.info(f"Using {len(self.config.wot_accounts)} pre-configured WoT accounts")
            else:
                logger.info("No WoT accounts configured — fast-track disabled")
        except Exception as e:
            logger.warning(f"Failed to load trust registry, using config.wot_accounts: {e}")

        self._running.set()
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(start_block,),
            name="dbc-node",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"DBC node started: account={self.config.account}, "
            f"gpu={self.config.gpu_available}, "
            f"dry_run={self.config.dry_run}, "
            f"mock={self.config.mock_chain}"
        )

    def stop(self) -> None:
        """Graceful shutdown."""
        if not self._running.is_set():
            return
        logger.info("DBC node stopping...")
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("DBC node stopped")

    def _run_loop(self, start_block: int | None = None) -> None:
        """Main loop: stream operations → process → act."""
        logger.info(
            f"DBC node streaming from block {start_block or 'HEAD'}..."
        )

        try:
            for op in self.chain.stream_operations(
                start_block=start_block,
                op_types=["custom_json"],
            ):
                if not self._running.is_set():
                    break

                self._process_operation(op)

                # Periodically drain local queue if RC recovered
                if self._local_queue and not self._submission_paused:
                    self._drain_local_queue()

        except Exception as e:
            if self._running.is_set():
                logger.error(f"DBC node stream error: {e}")
                # Retry after backoff
                time.sleep(10)
                if self._running.is_set():
                    self._run_loop(self.state.last_processed_block + 1)

    # ------------------------------------------------------------------
    # Operation Processing
    # ------------------------------------------------------------------

    def _process_operation(self, op: dict) -> None:
        """Process a single blockchain operation."""
        body = op.get("body", {})

        # Filter to hiveai custom_json only
        if isinstance(body, dict):
            json_id = body.get("id", "")
            if json_id != DBC_CUSTOM_JSON_ID:
                return
            try:
                json_data = json.loads(body.get("json", "{}"))
            except (json.JSONDecodeError, TypeError):
                return
        else:
            return

        op_type = json_data.get("type", "")

        # Update chain state
        self.state.process_operation(op)

        # Dispatch to handlers
        if op_type == "pair":
            self._on_pair(json_data, op)
        elif op_type == "epoch":
            self._on_epoch(json_data, op)
        elif op_type == "version":
            self._on_version(json_data, op)
        elif op_type == "verify":
            self._on_verify(json_data, op)
        elif op_type == "flag":
            self._on_flag(json_data, op)
        elif op_type == "protocol":
            self._on_protocol(json_data, op)

    def _on_pair(self, data: dict, op: dict) -> None:
        """New pair on-chain. Log for awareness."""
        score = data.get("score", 0)
        topic = data.get("topic", "?")
        author = (op.get("body", {}).get("required_posting_auths") or ["?"])[0]
        logger.debug(
            f"New pair: score={score:.2f}, topic={topic}, by={author}"
        )

    def _on_epoch(self, data: dict, op: dict) -> None:
        """New epoch claim. Log and check for conflicts."""
        version = data.get("v", "?")
        author = (op.get("body", {}).get("required_posting_auths") or ["?"])[0]
        blocks = data.get("blocks", [])
        logger.info(
            f"Epoch claimed: v={version}, blocks={blocks}, by={author}"
        )

    def _on_version(self, data: dict, op: dict) -> None:
        """New version published. Verify (GPU) or wait for consensus."""
        version = data.get("v", "?")
        cid = data.get("cid", "")
        eval_score = data.get("eval", 0)
        author = (op.get("body", {}).get("required_posting_auths") or ["?"])[0]

        logger.info(
            f"New version: v={version}, eval={eval_score:.3f}, "
            f"cid={cid[:12]}..., by={author}"
        )

        if self.config.gpu_available and not self.config.dry_run:
            # GPU node: verify independently
            self._verify_and_update(data)
        elif not self.config.gpu_available:
            # Non-GPU: check if consensus already exists
            self._check_and_update(version, cid, data)

    def _on_verify(self, data: dict, op: dict) -> None:
        """New verification vote. Non-GPU nodes check if consensus reached."""
        version = data.get("v", "?")
        accept = data.get("accept", False)
        author = (op.get("body", {}).get("required_posting_auths") or ["?"])[0]

        logger.debug(
            f"Verify vote: v={version}, accept={accept}, by={author}"
        )

        # Non-GPU nodes: check if this vote tips consensus
        if not self.config.gpu_available and not self.config.dry_run:
            latest = self.state.latest_version
            if latest and latest.get("v") == version:
                self._check_and_update(
                    version, latest.get("cid", ""), latest
                )

    def _on_flag(self, data: dict, op: dict) -> None:
        """Pair flagged. State already updated by ChainState."""
        pair_tx = data.get("pair_tx", "?")
        reason = data.get("reason", "?")
        author = (op.get("body", {}).get("required_posting_auths") or ["?"])[0]
        logger.info(f"Pair flagged: tx={pair_tx[:12]}..., reason={reason}, by={author}")

    def _on_protocol(self, data: dict, op: dict) -> None:
        """Protocol config update."""
        logger.info(f"Protocol config updated: {data}")

    # ------------------------------------------------------------------
    # Verification (GPU nodes)
    # ------------------------------------------------------------------

    def _verify_and_update(self, version_data: dict) -> None:
        """GPU node: download adapter, run eval, compare, vote, update."""
        version = version_data.get("v", "")
        cid = version_data.get("cid", "")
        claimed_eval = version_data.get("eval", 0)

        try:
            # Download adapter
            adapter_path = self.storage.download_adapter(
                cid,
                output_dir=self.config.adapter_dir,
                github_tag=version_data.get("github"),
            )

            # Run eval
            my_eval = self._run_eval(adapter_path)
            if my_eval is None:
                logger.error(f"Eval failed for version {version}")
                return

            # Compare scores
            tolerance = self.state.protocol_config.get("eval_tolerance", 0.05)
            score_match = abs(my_eval - claimed_eval) <= tolerance
            improvement = my_eval > (
                self.state.latest_version or {}
            ).get("eval", 0)

            accept = score_match and improvement

            logger.info(
                f"Verification: v={version}, "
                f"claimed={claimed_eval:.3f}, mine={my_eval:.3f}, "
                f"match={score_match}, improvement={improvement}, "
                f"accept={accept}"
            )

            # Broadcast vote
            if not self.config.dry_run:
                verify_op = build_verify_op(version, my_eval, accept)
                self.chain.broadcast_custom_json(
                    DBC_CUSTOM_JSON_ID,
                    verify_op,
                    [self.config.account],
                )

            # Swap adapter if accepted
            if accept:
                self._swap_adapter(adapter_path, version)

        except Exception as e:
            logger.error(f"Verification failed for v={version}: {e}")

    def _run_eval(self, adapter_path: str) -> float | None:
        """Run the eval harness on an adapter. Returns overall score or None."""
        if not self.config.eval_script:
            logger.warning("No eval_script configured, skipping eval")
            return None

        eval_script = Path(self.config.eval_script)
        if not eval_script.exists():
            logger.error(f"Eval script not found: {eval_script}")
            return None

        try:
            result = subprocess.run(
                [
                    "python",
                    str(eval_script),
                    "--adapter", adapter_path,
                    "--base-url", self.config.base_url,
                    "--seed", "42",
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=7200,  # 2 hours max
            )

            if result.returncode != 0:
                logger.error(f"Eval failed: {result.stderr[:500]}")
                return None

            # Parse JSON output for overall score
            output = result.stdout.strip()
            for line in reversed(output.split("\n")):
                try:
                    data = json.loads(line)
                    if "overall_score" in data:
                        return float(data["overall_score"])
                except (json.JSONDecodeError, ValueError):
                    continue

            logger.error("Could not find overall_score in eval output")
            return None

        except subprocess.TimeoutExpired:
            logger.error("Eval timed out (2 hour limit)")
            return None
        except Exception as e:
            logger.error(f"Eval error: {e}")
            return None

    # ------------------------------------------------------------------
    # Consensus Check (Non-GPU nodes)
    # ------------------------------------------------------------------

    def _check_and_update(
        self, version: str, cid: str, version_data: dict
    ) -> None:
        """Non-GPU node: check HP-weighted consensus for a version."""
        votes = self.state.verifications.get(version, [])
        if not votes:
            return

        # For consensus evaluation, we need HP data for each voter.
        # In a full implementation, we'd query chain for each voter's HP.
        # For now, use the votes as-is (HP must be included by the voter
        # or looked up by a background process).
        enriched_votes = []
        for v in votes:
            vote = dict(v)
            # If HP not cached, try to look it up
            if "hp" not in vote and not self.config.mock_chain:
                try:
                    acc = self.chain.get_account(vote.get("author", ""))
                    hp = float(acc.get("balance", "0").split()[0])
                    vote["hp"] = hp
                except Exception:
                    vote["hp"] = 0
            enriched_votes.append(vote)

        if evaluate_consensus(enriched_votes, self.config.wot_accounts):
            logger.info(
                f"Consensus reached for v={version}, downloading adapter"
            )
            try:
                adapter_path = self.storage.download_adapter(
                    cid,
                    output_dir=self.config.adapter_dir,
                    github_tag=version_data.get("github"),
                )
                self._swap_adapter(adapter_path, version)
            except Exception as e:
                logger.error(f"Failed to download/swap adapter: {e}")

    # ------------------------------------------------------------------
    # Adapter Management
    # ------------------------------------------------------------------

    def _swap_adapter(self, adapter_path: str, version: str) -> bool:
        """Hot-swap adapter via llama-server API."""
        try:
            from hiveai.lora.adapter_manager import set_adapters

            success = set_adapters(
                [{"id": 0, "path": adapter_path, "scale": 1.0}]
            )
            if success:
                self._current_adapter_version = version
                logger.info(f"Adapter swapped to v={version}")
            return success
        except ImportError:
            logger.warning(
                "adapter_manager not available, cannot hot-swap"
            )
            return False
        except Exception as e:
            logger.error(f"Adapter swap failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Pair Submission
    # ------------------------------------------------------------------

    def submit_pair(
        self,
        instruction: str,
        response: str,
        score: float,
        lang: str,
        topic: str,
        scorer_version: str,
        metadata: dict | None = None,
    ) -> dict:
        """Submit a training pair through the 6-gate filter.

        Gates 1-5 are checked here. Gate 6 (secrets scanner) is inline.
        Returns a status dict with the result.
        """
        # Gate 1: Quality threshold
        if score < DBC_MIN_ONCHAIN_QUALITY:
            return {
                "status": "rejected",
                "gate": 1,
                "reason": f"Quality {score:.2f} < {DBC_MIN_ONCHAIN_QUALITY}",
            }

        # Gate 6: Secrets scanner (check early to fail fast)
        pair_data = {"instruction": instruction, "response": response}
        passed, findings = pre_submission_check(pair_data)
        if not passed:
            return {
                "status": "rejected",
                "gate": 6,
                "reason": "Secrets/PII detected",
                "findings": findings,
            }

        # Gates 2-5 are handled by the caller (distiller pipeline)
        # since they require DB access, embeddings, and chain state.
        # This function handles the final submission after all gates pass.

        # Build on-chain operation
        op = build_pair_op(
            instruction, response, score, lang, topic, scorer_version, metadata
        )
        if op is None:
            return {
                "status": "overflow",
                "reason": "Pair too large for on-chain. Needs data_cid overflow.",
            }

        # RC check
        if self._submission_paused:
            self._local_queue.append(op)
            return {
                "status": "queued",
                "reason": "RC throttled, pair queued locally",
                "queue_position": len(self._local_queue),
            }

        # Check RC before submission
        rc_pct = self._get_rc_percent()
        if not should_submit(rc_pct, self._submission_paused):
            self._submission_paused = True
            self._local_queue.append(op)
            logger.warning(
                f"RC low ({rc_pct:.1f}%), pausing submissions. "
                f"Pair queued ({len(self._local_queue)} in queue)."
            )
            return {
                "status": "queued",
                "reason": f"RC low ({rc_pct:.1f}%), pair queued",
                "queue_position": len(self._local_queue),
            }

        # Broadcast
        if self.config.dry_run:
            return {
                "status": "dry_run",
                "operation": op,
            }

        try:
            result = self.chain.broadcast_custom_json(
                DBC_CUSTOM_JSON_ID, op, [self.config.account]
            )
            return {
                "status": "submitted",
                "result": result,
            }
        except Exception as e:
            logger.error(f"Failed to submit pair: {e}")
            self._local_queue.append(op)
            return {
                "status": "error",
                "reason": str(e),
                "queued": True,
            }

    # ------------------------------------------------------------------
    # RC Management
    # ------------------------------------------------------------------

    def _get_rc_percent(self) -> float:
        """Query current RC percentage from chain."""
        try:
            rc_info = self.chain.get_account_rc(self.config.account)
            manabar = rc_info.get("rc_manabar", rc_info)
            current = int(manabar.get("current_mana", 0))
            maximum = int(manabar.get("max_mana", 1))
            if maximum == 0:
                return 100.0
            return (current / maximum) * 100.0
        except Exception as e:
            logger.warning(f"Could not get RC: {e}")
            return 100.0  # Assume OK if can't check

    def _drain_local_queue(self) -> None:
        """When RC recovers, submit queued pairs (highest quality first)."""
        rc_pct = self._get_rc_percent()
        if not should_submit(rc_pct, self._submission_paused):
            return

        self._submission_paused = False
        logger.info(
            f"RC recovered ({rc_pct:.1f}%), draining {len(self._local_queue)} queued pairs"
        )

        # Sort by quality (highest first)
        self._local_queue.sort(key=lambda p: p.get("score", 0), reverse=True)

        submitted = 0
        remaining = []
        for op in self._local_queue:
            # Re-check RC before each submission
            rc_pct = self._get_rc_percent()
            if not should_submit(rc_pct, False):
                self._submission_paused = True
                remaining.append(op)
                continue

            if self.config.dry_run:
                submitted += 1
                continue

            try:
                self.chain.broadcast_custom_json(
                    DBC_CUSTOM_JSON_ID, op, [self.config.account]
                )
                submitted += 1
                time.sleep(3)  # One per block
            except Exception as e:
                logger.warning(f"Queue drain failed: {e}")
                remaining.append(op)
                break

        self._local_queue = remaining
        if submitted:
            logger.info(
                f"Drained {submitted} pairs, {len(remaining)} remaining"
            )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Current node status for dashboard/monitoring."""
        return {
            "running": self._running.is_set(),
            "account": self.config.account,
            "gpu_available": self.config.gpu_available,
            "dry_run": self.config.dry_run,
            "mock_chain": self.config.mock_chain,
            "current_adapter": self._current_adapter_version,
            "latest_version": (
                self.state.latest_version.get("v")
                if self.state.latest_version
                else None
            ),
            "latest_epoch": (
                self.state.latest_epoch.get("v")
                if self.state.latest_epoch
                else None
            ),
            "pending_pairs": self.state.pending_pair_count,
            "total_pairs": len(self.state.pairs),
            "total_versions": len(self.state.versions),
            "total_epochs": len(self.state.epochs),
            "last_block": self.state.last_processed_block,
            "rc_percent": self._get_rc_percent() if not self.config.mock_chain else 100.0,
            "submission_paused": self._submission_paused,
            "queued_pairs": len(self._local_queue),
            "daily_capacity": (
                estimate_daily_capacity(0)
                if self.config.mock_chain
                else None
            ),
        }
