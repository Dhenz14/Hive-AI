#!/usr/bin/env python3
"""
DataClaw Session Miner — extract high-quality training pairs from
DataClaw-exported coding session JSONL files.

Reads multi-turn conversations, scores quality, and exports Alpaca JSONL.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from hiveai.lora.distiller import _score_quality, _clean_response, _persist_pair


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_INSTRUCTION_LEN = 20
MIN_RESPONSE_LEN = 100
DEDUP_SIMILARITY_THRESHOLD = 0.85

# Tool-use turn patterns worth synthesizing into training pairs
DEBUGGABLE_TOOLS = {"Read", "Bash", "Grep", "Edit", "Write"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_trivial(text: str) -> bool:
    """Return True if the text is a trivial confirmation or acknowledgment."""
    stripped = text.strip().lower()
    trivial_phrases = {
        "ok", "okay", "thanks", "thank you", "got it", "sure",
        "yes", "no", "done", "perfect", "great", "sounds good",
        "lgtm", "looks good", "nice", "cool", "understood",
    }
    return stripped in trivial_phrases or len(stripped) < 10


def _has_substantive_content(msg: dict) -> bool:
    """Check if an assistant message has substantive text beyond tool calls."""
    content = msg.get("content", "")
    if len(content.strip()) < MIN_RESPONSE_LEN:
        return False
    # Pure tool invocation with no explanation
    tool_uses = msg.get("tool_uses", [])
    if tool_uses and len(content.strip()) < 50:
        return False
    return True


def _near_duplicate(a: str, b: str) -> bool:
    """Quick near-duplicate check using SequenceMatcher on first 200 chars."""
    a_prefix = a[:200].lower().strip()
    b_prefix = b[:200].lower().strip()
    return SequenceMatcher(None, a_prefix, b_prefix).ratio() > DEDUP_SIMILARITY_THRESHOLD


def _format_thinking(thinking: Optional[str]) -> str:
    """Wrap thinking trace in <think> block."""
    if not thinking:
        return ""
    return f"<think>\n{thinking.strip()}\n</think>\n\n"


def _extract_tool_context(messages: list, idx: int) -> Optional[str]:
    """
    Given a tool-heavy assistant turn at `idx`, look at surrounding context
    to synthesize a 'how to debug/implement X' instruction.
    """
    if idx < 1:
        return None

    # Gather tool names used
    msg = messages[idx]
    tool_uses = msg.get("tool_uses", [])
    tools_used = [t.get("tool", "") for t in tool_uses if t.get("tool") in DEBUGGABLE_TOOLS]
    if not tools_used:
        return None

    # Look at the user message that triggered this
    user_msg = messages[idx - 1]
    user_text = user_msg.get("content", "").strip()
    if len(user_text) < MIN_INSTRUCTION_LEN:
        return None

    # Build a synthesized instruction from the user's request + tool context
    tool_list = ", ".join(sorted(set(tools_used)))
    instruction = (
        f"Using tools ({tool_list}), solve the following task step by step:\n\n"
        f"{user_text}"
    )
    return instruction


def _build_tool_response(msg: dict, include_thinking: bool) -> str:
    """Build a response string from a tool-heavy assistant turn."""
    parts = []
    if include_thinking and msg.get("thinking"):
        parts.append(_format_thinking(msg["thinking"]))

    content = msg.get("content", "").strip()
    tool_uses = msg.get("tool_uses", [])

    # Include tool interactions as structured steps
    for i, tool in enumerate(tool_uses, 1):
        tool_name = tool.get("tool", "Unknown")
        tool_input = tool.get("input", {})
        if isinstance(tool_input, dict):
            # Compact representation
            input_summary = json.dumps(tool_input, indent=None)
            if len(input_summary) > 500:
                input_summary = input_summary[:500] + "..."
        else:
            input_summary = str(tool_input)[:500]
        parts.append(f"**Step {i}: {tool_name}**\n```\n{input_summary}\n```\n")

    if content:
        parts.append(content)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def extract_pairs_from_session(
    session: dict,
    min_quality: float = 0.60,
    include_thinking: bool = False,
) -> list[dict]:
    """Extract training pairs from a single DataClaw session."""
    messages = session.get("messages", [])
    session_id = session.get("session_id", "unknown")
    project = session.get("project", "")
    pairs = []
    seen_instructions: list[str] = []  # for intra-session dedup

    i = 0
    while i < len(messages) - 1:
        user_msg = messages[i]
        asst_msg = messages[i + 1] if i + 1 < len(messages) else None

        # Only process user→assistant pairs
        if user_msg.get("role") != "user" or not asst_msg or asst_msg.get("role") != "assistant":
            i += 1
            continue

        instruction = user_msg.get("content", "").strip()
        response = asst_msg.get("content", "").strip()

        # --- Standard pair extraction ---
        if (
            len(instruction) >= MIN_INSTRUCTION_LEN
            and not _is_trivial(instruction)
            and _has_substantive_content(asst_msg)
        ):
            # Check intra-session dedup
            is_dup = any(_near_duplicate(instruction, seen) for seen in seen_instructions)
            if not is_dup:
                # Build response with optional thinking
                output = ""
                if include_thinking and asst_msg.get("thinking"):
                    output += _format_thinking(asst_msg["thinking"])
                output += _clean_response(response)

                quality = _score_quality(instruction, output)
                if quality >= min_quality:
                    pairs.append({
                        "instruction": instruction,
                        "input": "",
                        "output": output,
                        "metadata": {
                            "source": "dataclaw",
                            "session_id": session_id,
                            "project": project,
                            "has_thinking": bool(asst_msg.get("thinking")),
                            "quality": round(quality, 3),
                        },
                    })
                    seen_instructions.append(instruction)

        # --- Tool-use pair extraction ---
        tool_uses = asst_msg.get("tool_uses", [])
        if tool_uses and len(tool_uses) >= 2:
            synth_instruction = _extract_tool_context(messages, i + 1)
            if synth_instruction and not any(
                _near_duplicate(synth_instruction, seen) for seen in seen_instructions
            ):
                tool_response = _build_tool_response(asst_msg, include_thinking)
                if len(tool_response) >= MIN_RESPONSE_LEN:
                    quality = _score_quality(synth_instruction, tool_response)
                    if quality >= min_quality:
                        pairs.append({
                            "instruction": synth_instruction,
                            "input": "",
                            "output": tool_response,
                            "metadata": {
                                "source": "dataclaw",
                                "session_id": session_id,
                                "project": project,
                                "has_thinking": bool(asst_msg.get("thinking")),
                                "has_tool_use": True,
                                "quality": round(quality, 3),
                            },
                        })
                        seen_instructions.append(synth_instruction)

        i += 2  # skip past this pair

    return pairs


def process_file(
    filepath: Path,
    min_quality: float,
    include_thinking: bool,
) -> tuple[list[dict], dict]:
    """Process a single JSONL file. Returns (pairs, stats)."""
    stats = defaultdict(int)
    all_pairs = []

    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                session = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  WARN: {filepath}:{line_num} — invalid JSON: {e}", file=sys.stderr)
                stats["json_errors"] += 1
                continue

            stats["sessions"] += 1
            msg_count = len(session.get("messages", []))
            stats["messages"] += msg_count

            pairs = extract_pairs_from_session(session, min_quality, include_thinking)
            stats["pairs_extracted"] += len(pairs)
            all_pairs.extend(pairs)

    return all_pairs, dict(stats)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Mine training pairs from DataClaw session exports"
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to JSONL file or directory of JSONL files"
    )
    parser.add_argument(
        "--output", "-o",
        default="loras/training_data/dataclaw_pairs.jsonl",
        help="Output JSONL path (default: loras/training_data/dataclaw_pairs.jsonl)"
    )
    parser.add_argument(
        "--min-quality", type=float, default=0.60,
        help="Minimum quality score threshold (default: 0.60)"
    )
    parser.add_argument(
        "--include-thinking", action="store_true",
        help="Include <think> blocks in output for reasoning distillation"
    )
    parser.add_argument(
        "--persist", action="store_true",
        help="Also persist pairs to database via _persist_pair()"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Print extraction statistics"
    )
    args = parser.parse_args()

    # Resolve input files
    input_path = Path(args.input)
    if input_path.is_dir():
        files = sorted(input_path.glob("*.jsonl"))
        if not files:
            print(f"ERROR: No .jsonl files found in {input_path}", file=sys.stderr)
            sys.exit(1)
    elif input_path.is_file():
        files = [input_path]
    else:
        print(f"ERROR: {input_path} does not exist", file=sys.stderr)
        sys.exit(1)

    # Process all files
    all_pairs = []
    total_stats = defaultdict(int)

    for filepath in files:
        print(f"Processing {filepath.name}...")
        pairs, stats = process_file(filepath, args.min_quality, args.include_thinking)
        all_pairs.extend(pairs)
        for k, v in stats.items():
            total_stats[k] += v

    # Global dedup across files
    deduped = []
    seen_global: list[str] = []
    for pair in all_pairs:
        inst = pair["instruction"]
        if not any(_near_duplicate(inst, s) for s in seen_global):
            deduped.append(pair)
            seen_global.append(inst)

    total_stats["pairs_after_dedup"] = len(deduped)
    total_stats["pairs_removed_dedup"] = len(all_pairs) - len(deduped)

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for pair in deduped:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
    print(f"Wrote {len(deduped)} pairs to {output_path}")

    # Persist to DB if requested
    if args.persist and deduped:
        from hiveai.models import SessionLocal
        db = SessionLocal()
        try:
            persisted = 0
            for pair in deduped:
                meta = pair.get("metadata", {})
                db_pair = {
                    "source": "dataclaw",
                    "topic": meta.get("project", "dataclaw"),
                    "instruction": pair["instruction"],
                    "response": pair["output"],
                    "quality": meta.get("quality", 0.0),
                    "is_eligible": True,
                    "metadata": meta,
                }
                _persist_pair(db, db_pair)
                persisted += 1
            print(f"Persisted {persisted} pairs to database")
        finally:
            db.close()

    # Print stats
    if args.stats:
        print("\n--- Extraction Statistics ---")
        print(f"  Files processed:    {len(files)}")
        print(f"  Sessions parsed:    {total_stats.get('sessions', 0)}")
        print(f"  Messages seen:      {total_stats.get('messages', 0)}")
        print(f"  Pairs extracted:    {total_stats.get('pairs_extracted', 0)}")
        print(f"  After global dedup: {total_stats.get('pairs_after_dedup', 0)}")
        print(f"  Removed (dedup):    {total_stats.get('pairs_removed_dedup', 0)}")
        print(f"  JSON errors:        {total_stats.get('json_errors', 0)}")
        if deduped:
            qualities = [p["metadata"]["quality"] for p in deduped]
            print(f"  Quality — min: {min(qualities):.3f}  "
                  f"avg: {sum(qualities)/len(qualities):.3f}  "
                  f"max: {max(qualities):.3f}")


if __name__ == "__main__":
    main()
