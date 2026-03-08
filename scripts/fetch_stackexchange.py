#!/usr/bin/env python3
"""
scripts/fetch_stackexchange.py

Fetch coding questions from Stack Exchange API for use as miner seed prompts.
Uses the public API (no key needed, 300 requests/day quota).

Outputs JSONL with instruction (question title) and reference (accepted answer).

Usage:
    python scripts/fetch_stackexchange.py --tags "python;rust" --count 100 --output seeds_stackexchange.jsonl
    python scripts/fetch_stackexchange.py --tags "go;c++" --min-score 10 --count 50
"""

import argparse
import gzip
import html
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request

API_BASE = "https://api.stackexchange.com/2.3"
DEFAULT_TAGS = "python;rust;go;c++;javascript;hive-blockchain"
DEFAULT_OUTPUT = "seeds_stackexchange.jsonl"
DEFAULT_COUNT = 100
DEFAULT_MIN_SCORE = 5
PAGE_SIZE = 100  # max allowed by SE API


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<pre><code>(.*?)</code></pre>", r"```\n\1\n```", text, flags=re.DOTALL)
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return text.strip()


def fetch_questions(tag: str, min_score: int, page: int = 1) -> dict:
    """Fetch questions from Stack Exchange API for a single tag.

    Returns the raw JSON response dict.
    """
    params = (
        f"page={page}&pagesize={PAGE_SIZE}&order=desc&sort=votes"
        f"&tagged={urllib.request.quote(tag)}"
        f"&filter=withbody"  # include body in response
        f"&accepted=True"
        f"&closed=False"
        f"&min={min_score}"
        f"&site=stackoverflow"
    )
    url = f"{API_BASE}/questions?{params}"

    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            # SE API always returns gzip
            if resp.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            return json.loads(data)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"  Rate limited on tag '{tag}', waiting 60s...", file=sys.stderr)
            time.sleep(60)
            return fetch_questions(tag, min_score, page)
        print(f"  HTTP {e.code} for tag '{tag}': {e.reason}", file=sys.stderr)
        return {"items": [], "has_more": False, "quota_remaining": 0}
    except Exception as e:
        print(f"  Error fetching tag '{tag}': {e}", file=sys.stderr)
        return {"items": [], "has_more": False, "quota_remaining": 0}


def fetch_answer(answer_id: int) -> str | None:
    """Fetch a single answer body by ID."""
    url = f"{API_BASE}/answers/{answer_id}?filter=withbody&site=stackoverflow"
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            result = json.loads(data)
            items = result.get("items", [])
            if items:
                return items[0].get("body", "")
    except Exception as e:
        print(f"  Error fetching answer {answer_id}: {e}", file=sys.stderr)
    return None


def process_questions(tag: str, min_score: int, max_count: int) -> list[dict]:
    """Fetch and process questions for a single tag, up to max_count."""
    pairs = []
    page = 1
    seen_ids = set()

    while len(pairs) < max_count:
        print(f"  Fetching {tag} page {page}...", file=sys.stderr)
        result = fetch_questions(tag, min_score, page)

        quota = result.get("quota_remaining", 0)
        if quota < 10:
            print(f"  Quota low ({quota} remaining), stopping.", file=sys.stderr)
            break

        items = result.get("items", [])
        if not items:
            break

        for q in items:
            if len(pairs) >= max_count:
                break

            qid = q.get("question_id")
            if qid in seen_ids:
                continue
            seen_ids.add(qid)

            # Must have accepted answer
            accepted_id = q.get("accepted_answer_id")
            if not accepted_id:
                continue

            # Skip closed questions
            if q.get("closed_date") or q.get("closed_reason"):
                continue

            title = html.unescape(q.get("title", "")).strip()
            if not title:
                continue

            # Fetch accepted answer body
            answer_html = fetch_answer(accepted_id)
            if not answer_html:
                continue

            answer_text = strip_html(answer_html)
            if len(answer_text) < 50:
                continue  # too short to be useful

            # Rate limit: ~1 request per answer fetch
            time.sleep(0.5)

            pairs.append({
                "instruction": title,
                "input": "",
                "output": answer_text,
                "metadata": {
                    "source": "stackexchange",
                    "tag": tag,
                    "question_id": qid,
                    "score": q.get("score", 0),
                    "answer_id": accepted_id,
                    "url": q.get("link", ""),
                },
            })

        if not result.get("has_more", False):
            break
        page += 1
        time.sleep(1)  # be nice to the API

    return pairs


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Stack Exchange coding questions as seed prompts for miner"
    )
    parser.add_argument(
        "--tags", default=DEFAULT_TAGS,
        help=f"Semicolon-separated tags (default: {DEFAULT_TAGS})"
    )
    parser.add_argument(
        "--count", type=int, default=DEFAULT_COUNT,
        help=f"Max questions to fetch per tag (default: {DEFAULT_COUNT})"
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT,
        help=f"Output JSONL file (default: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--min-score", type=int, default=DEFAULT_MIN_SCORE,
        help=f"Minimum question score (default: {DEFAULT_MIN_SCORE})"
    )

    args = parser.parse_args()
    tags = [t.strip() for t in args.tags.split(";") if t.strip()]

    print(f"Fetching from Stack Exchange: tags={tags}, min_score={args.min_score}, "
          f"count={args.count}/tag", file=sys.stderr)

    all_pairs = []
    for tag in tags:
        print(f"\n--- Tag: {tag} ---", file=sys.stderr)
        pairs = process_questions(tag, args.min_score, args.count)
        print(f"  Got {len(pairs)} pairs for '{tag}'", file=sys.stderr)
        all_pairs.extend(pairs)

    # Deduplicate by question_id
    seen = set()
    unique = []
    for p in all_pairs:
        qid = p["metadata"]["question_id"]
        if qid not in seen:
            seen.add(qid)
            unique.append(p)

    # Write JSONL
    with open(args.output, "w", encoding="utf-8") as f:
        for pair in unique:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(unique)} seed prompts to {args.output}", file=sys.stderr)
    tag_counts = {t: sum(1 for p in unique if p["metadata"]["tag"] == t) for t in tags}
    breakdown = ", ".join(f"{t}={c}" for t, c in tag_counts.items())
    print(f"Tags breakdown: {breakdown}", file=sys.stderr)


if __name__ == "__main__":
    main()
