"""Domain Probe Callback: Mid-training regression detection.

Novel approach — no published work implements online domain probe callbacks
during LoRA training. Runs lightweight domain probes every N steps during
training to detect catastrophic interference BEFORE the cycle completes.

If any domain drops >warn_threshold, reduces LR by 50%.
If any domain drops >stop_threshold, halts training early.

Uses 6 quick probes (1 per domain, the hardest from each) for speed (~90s per check).
Only activates for longer training runs (>50 steps).

Usage (integrated into train_v5.py):
    from domain_probe_callback import DomainProbeCallback

    callback = DomainProbeCallback(
        probe_interval=50,
        server_url="http://localhost:11435",
    )
    callback.set_baseline(baseline_scores)  # From pre-training eval
    trainer.add_callback(callback)
"""
import json
import logging
import time
from collections import defaultdict

import requests

try:
    from transformers import TrainerCallback
except ImportError:
    # Fallback: define a no-op base class so the file can be imported without transformers
    class TrainerCallback:
        pass

logger = logging.getLogger("domain_probe_callback")

# Import quick probes from probe library
try:
    from probe_library import QUICK_PROBES, Probe, score_response
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from probe_library import QUICK_PROBES, Probe


# Inline scoring function (mirrors regression_eval.py)
def _score_response(response: str, expected_keywords: list) -> float:
    """Score a response based on keyword coverage + structural quality."""
    import re
    if not response or not response.strip():
        return 0.0
    text = response.lower()

    found = sum(1 for kw in expected_keywords if kw.lower() in text)
    keyword_score = found / len(expected_keywords) if expected_keywords else 0.0

    structure_signals = []
    has_code = bool(re.search(r"```\w*\n", response))
    structure_signals.append(1.0 if has_code else 0.0)

    has_definitions = bool(re.search(
        r"\b(def |fn |func |function |class |struct |impl |interface )\b",
        response
    ))
    structure_signals.append(1.0 if has_definitions else 0.0)
    structure_signals.append(1.0 if len(response.strip()) > 200 else 0.3)

    prose_text = re.sub(r"```[\s\S]*?```", "", response).strip()
    structure_signals.append(1.0 if len(prose_text) > 50 else 0.2)

    structure_score = sum(structure_signals) / len(structure_signals)
    return keyword_score * 0.7 + structure_score * 0.3


SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant. Answer directly without chain-of-thought reasoning."


def run_quick_probes(server_url: str, timeout: int = 60) -> dict:
    """Run 6 quick probes (1 per domain), return {domain: score}."""
    domain_scores = {}

    for probe in QUICK_PROBES:
        try:
            resp = requests.post(
                f"{server_url}/v1/chat/completions",
                json={
                    "model": "hiveai",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": probe.prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024,  # Shorter for speed
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"].get("content", "")
                score = _score_response(content, probe.expected_keywords)
                domain_scores[probe.domain] = score
            else:
                domain_scores[probe.domain] = 0.0
        except Exception:
            domain_scores[probe.domain] = 0.0

    return domain_scores


class DomainProbeCallback(TrainerCallback):
    """TRL TrainerCallback that runs domain probes every N steps during training.

    Detects catastrophic interference mid-training by running 6 lightweight
    domain probes. Actions taken on regression:
    - >warn_threshold: reduce LR by 50%
    - >stop_threshold: halt training

    Only activates for training runs with >probe_interval steps.
    For micro-training (<20 steps), interference is negligible.
    """

    def __init__(self, probe_interval=50, lr_reduction=0.5,
                 warn_threshold=0.02, stop_threshold=0.04,
                 server_url="http://localhost:11435"):
        self.probe_interval = probe_interval
        self.lr_reduction = lr_reduction
        self.warn_threshold = warn_threshold
        self.stop_threshold = stop_threshold
        self.server_url = server_url
        self.baseline_scores = None
        self.lr_reductions = 0
        self.check_count = 0
        self.history = []  # [(step, scores_dict)]

    def set_baseline(self, scores: dict):
        """Set baseline domain scores (from pre-training eval or score ledger)."""
        self.baseline_scores = scores
        logger.info(f"Domain probe baseline set: {scores}")

    def on_step_end(self, args, state, control, **kwargs):
        """Called after each training step."""
        if self.baseline_scores is None:
            return

        if state.global_step == 0:
            return

        if state.global_step % self.probe_interval != 0:
            return

        self.check_count += 1
        logger.info(f"[PROBE CHECK #{self.check_count}] Running 6 domain probes at step {state.global_step}...")

        try:
            scores = run_quick_probes(self.server_url)
        except Exception as e:
            logger.warning(f"  Probe check failed: {e} — skipping")
            return

        self.history.append((state.global_step, scores))

        # Check for regression
        for domain, score in scores.items():
            baseline = self.baseline_scores.get(domain)
            if baseline is None:
                continue

            drop = baseline - score

            if drop > self.stop_threshold:
                logger.error(
                    f"  STOP: {domain} dropped {drop:.1%} "
                    f"({baseline:.3f} -> {score:.3f}) — halting training!"
                )
                control.should_training_stop = True
                return

            elif drop > self.warn_threshold:
                logger.warning(
                    f"  WARNING: {domain} dropping {drop:.1%} "
                    f"({baseline:.3f} -> {score:.3f}) — reducing LR 50%"
                )
                optimizer = kwargs.get('optimizer')
                if optimizer:
                    for param_group in optimizer.param_groups:
                        param_group['lr'] *= self.lr_reduction
                    self.lr_reductions += 1
                    logger.info(f"  LR reduced (total reductions: {self.lr_reductions})")

        # Log summary
        summary = " | ".join(f"{d}:{s:.3f}" for d, s in sorted(scores.items()))
        logger.info(f"  Probe scores: {summary}")

    def get_summary(self) -> dict:
        """Return summary of all probe checks for training metadata."""
        return {
            "checks": self.check_count,
            "lr_reductions": self.lr_reductions,
            "history": [
                {"step": step, "scores": scores}
                for step, scores in self.history
            ],
        }
