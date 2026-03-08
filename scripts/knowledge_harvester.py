#!/usr/bin/env python3
"""
Knowledge Harvester — crawl documentation sites and generate training pairs.

Extracts structured code examples with explanations from official docs,
generates instruction/response pairs, scores quality, and exports to JSONL.

Supports checkpoint/resume for large crawls. Uses requests + BeautifulSoup
(swap in Scrapling later by replacing `_fetch_page`).

Usage:
    python scripts/knowledge_harvester.py --language rust --max-pages 50
    python scripts/knowledge_harvester.py --language all --dry-run
    python scripts/knowledge_harvester.py --language go --output /opt/hiveai/project/loras/training_data/harvested_go.jsonl
"""

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, Tag

# Import quality scoring from existing distiller
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hiveai.lora.distiller import _score_quality, _clean_response

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("harvester")

# ---------------------------------------------------------------------------
# Documentation source configs
# ---------------------------------------------------------------------------

DOC_SOURCES = {
    "rust": {
        "base_url": "https://doc.rust-lang.org/std/",
        "index_pattern": "all.html",
        "code_selector": "pre.rust",
        "link_selector": "a[href]",
        "lang_name": "Rust",
    },
    "go": {
        "base_url": "https://pkg.go.dev/std",
        "code_selector": "pre.Code",
        "link_selector": "a[href]",
        "lang_name": "Go",
    },
    "cpp": {
        "base_url": "https://en.cppreference.com/w/cpp/",
        "code_selector": "pre.source-cpp, div.source-cpp pre",
        "link_selector": "a[href]",
        "lang_name": "C++",
    },
    "hive": {
        "base_url": "https://developers.hive.io/apidefinitions/",
        "code_selector": "code, pre",
        "link_selector": "a[href]",
        "lang_name": "Hive",
    },
}

USER_AGENT = "HiveAI-KnowledgeHarvester/1.0 (training-data; polite-bot)"
MIN_CODE_LINES = 3


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CodeExample:
    """A single code block extracted from a doc page."""
    url: str
    heading: str
    code: str
    explanation: str
    language: str


@dataclass
class TrainingPair:
    """Instruction/response pair ready for JSONL export."""
    instruction: str
    input: str
    output: str
    category: str
    source_url: str
    quality_score: float


@dataclass
class Checkpoint:
    """Crawl progress for resume support with adaptive URL tracking."""
    visited: dict = field(default_factory=dict)  # url -> pair count
    timestamps: dict = field(default_factory=dict)  # url -> ISO timestamp of last scrape
    total_pairs: int = 0

    def save(self, path: str):
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: str) -> "Checkpoint":
        p = Path(path)
        if not p.exists():
            return cls()
        data = json.loads(p.read_text())
        return cls(
            visited=data.get("visited", {}),
            timestamps=data.get("timestamps", {}),
            total_pairs=data.get("total_pairs", 0),
        )

    def is_stale(self, url: str, refresh_days: int) -> bool:
        """Check if a URL needs re-scraping based on age."""
        from datetime import datetime, timedelta, timezone
        ts = self.timestamps.get(url)
        if not ts:
            return True
        try:
            scraped_at = datetime.fromisoformat(ts)
            return datetime.now(timezone.utc) - scraped_at > timedelta(days=refresh_days)
        except (ValueError, TypeError):
            return True

    def mark_visited(self, url: str, pair_count: int):
        """Record a URL visit with timestamp."""
        from datetime import datetime, timezone
        self.visited[url] = pair_count
        self.timestamps[url] = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Fetcher (swap this for Scrapling later)
# ---------------------------------------------------------------------------

_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": USER_AGENT})
    return _session


def _fetch_page(url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
    """Fetch and parse a page. Returns None on failure."""
    try:
        resp = _get_session().get(url, timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        log.warning("Failed to fetch %s: %s", url, e)
        return None


def _check_robots(base_url: str) -> RobotFileParser:
    """Parse robots.txt for a domain."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        log.warning("Could not read robots.txt for %s, proceeding cautiously", base_url)
    return rp


# ---------------------------------------------------------------------------
# Link discovery
# ---------------------------------------------------------------------------

def _discover_links(soup: BeautifulSoup, base_url: str, source_cfg: dict,
                    max_pages: int) -> list[str]:
    """Extract internal documentation links from a page."""
    base_parsed = urlparse(base_url)
    links: list[str] = []
    seen = set()

    selector = source_cfg.get("link_selector", "a[href]")
    for a_tag in soup.select(selector):
        href = a_tag.get("href", "")
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        full = urljoin(base_url, href)
        full_parsed = urlparse(full)
        # Stay within same domain/path prefix
        if full_parsed.netloc != base_parsed.netloc:
            continue
        # Strip fragment
        clean = full_parsed._replace(fragment="").geturl()
        if clean not in seen:
            seen.add(clean)
            links.append(clean)
        if len(links) >= max_pages:
            break
    return links


# ---------------------------------------------------------------------------
# Code extraction
# ---------------------------------------------------------------------------

def _get_nearest_heading(element: Tag) -> str:
    """Walk backwards to find the nearest heading before this element."""
    for prev in element.find_all_previous(["h1", "h2", "h3", "h4"]):
        text = prev.get_text(strip=True)
        if text:
            return text
    return ""


def _get_surrounding_prose(element: Tag, max_chars: int = 800) -> str:
    """Extract explanatory text near the code block."""
    prose_parts: list[str] = []
    # Look at previous siblings for prose
    for sib in element.find_previous_siblings(limit=3):
        if isinstance(sib, Tag) and sib.name in ("p", "li", "div"):
            text = sib.get_text(strip=True)
            if text:
                prose_parts.insert(0, text)
    # Look at next siblings for prose
    for sib in element.find_next_siblings(limit=2):
        if isinstance(sib, Tag) and sib.name in ("p", "li", "div"):
            text = sib.get_text(strip=True)
            if text:
                prose_parts.append(text)
    combined = "\n".join(prose_parts)
    return combined[:max_chars]


def _is_nontrivial(code: str) -> bool:
    """Filter out trivial code snippets."""
    lines = [l for l in code.strip().splitlines() if l.strip()]
    if len(lines) < MIN_CODE_LINES:
        return False
    text = code.lower()
    # Must contain something structural
    markers = ["fn ", "func ", "def ", "class ", "struct ", "impl ", "type ",
               "pub ", "package ", "import ", "use ", "const ", "let ", "var ",
               "void ", "int ", "template", "namespace", "interface ", "enum ",
               "async ", "return ", "if ", "for ", "match ", "switch "]
    return any(m in text for m in markers)


def _extract_examples(soup: BeautifulSoup, url: str,
                      source_cfg: dict, lang: str) -> list[CodeExample]:
    """Extract code examples from a parsed doc page."""
    examples: list[CodeExample] = []
    selector = source_cfg.get("code_selector", "pre")

    for block in soup.select(selector):
        code = block.get_text()
        if not code or not _is_nontrivial(code):
            continue
        heading = _get_nearest_heading(block)
        explanation = _get_surrounding_prose(block)
        examples.append(CodeExample(
            url=url,
            heading=heading,
            code=code.strip(),
            explanation=explanation.strip(),
            language=lang,
        ))
    return examples


# ---------------------------------------------------------------------------
# Pair generation
# ---------------------------------------------------------------------------

_HOWTO_TEMPLATES = [
    "How do I {topic} in {lang}?",
    "Show me how to {topic} in {lang}.",
    "Write a {lang} example that demonstrates {topic}.",
    "What is the idiomatic way to {topic} in {lang}?",
]

_EXPLAIN_TEMPLATES = [
    "Explain how {topic} works in {lang} with a code example.",
    "What does the following {lang} code do and why is it written this way?",
]

_API_TEMPLATES = [
    "Show how to use `{topic}` in {lang} with an example.",
    "What are the parameters and return type of `{topic}` in {lang}?",
]


def _heading_to_topic(heading: str) -> str:
    """Normalize a heading into a topic phrase."""
    topic = heading.strip().rstrip(".")
    # Remove leading articles / section numbers
    topic = re.sub(r"^(\d+\.?\s*)+", "", topic)
    topic = re.sub(r"^(the|a|an)\s+", "", topic, flags=re.IGNORECASE)
    return topic.strip().lower() if topic else ""


def _looks_like_api(heading: str, code: str) -> bool:
    """Heuristic: is this an API/function reference?"""
    api_signals = ["fn ", "func ", "def ", "(", "::", "->", "=>"]
    h = heading.lower()
    return any(s in h for s in api_signals) or "::" in code[:200]


def _generate_pairs(examples: list[CodeExample], lang_name: str,
                    min_quality: float) -> list[TrainingPair]:
    """Generate scored training pairs from extracted code examples."""
    pairs: list[TrainingPair] = []

    for ex in examples:
        topic = _heading_to_topic(ex.heading)
        if not topic or len(topic) < 4:
            continue

        is_api = _looks_like_api(ex.heading, ex.code)

        # Pick instruction template
        if is_api:
            templates = _API_TEMPLATES
        else:
            templates = _HOWTO_TEMPLATES + _EXPLAIN_TEMPLATES

        # Use first template that makes sense (deterministic)
        template = templates[hash(topic) % len(templates)]
        instruction = template.format(topic=topic, lang=lang_name)

        # Build response
        response_parts: list[str] = []
        if ex.explanation:
            response_parts.append(ex.explanation)
        response_parts.append(f"\n```{ex.language}\n{ex.code}\n```")
        if ex.explanation and len(ex.explanation) > 50:
            response_parts.append(
                f"\nThis example demonstrates {topic} using {lang_name}'s "
                "standard library patterns."
            )
        response = "\n".join(response_parts)
        response = _clean_response(response)

        # Score quality
        try:
            score = _score_quality(instruction, response)
        except Exception:
            score = 0.0

        if score < min_quality:
            continue

        pairs.append(TrainingPair(
            instruction=instruction,
            input="",
            output=response,
            category=ex.language,
            source_url=ex.url,
            quality_score=round(score, 4),
        ))

    return pairs


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _export_jsonl(pairs: list[TrainingPair], output_path: str):
    """Append pairs to a JSONL file."""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        for pair in pairs:
            row = {
                "instruction": pair.instruction,
                "input": pair.input,
                "output": pair.output,
                "category": pair.category,
                "source_url": pair.source_url,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    log.info("Exported %d pairs to %s", len(pairs), output_path)


# ---------------------------------------------------------------------------
# Main crawl loop
# ---------------------------------------------------------------------------

def harvest_language(lang: str, source_cfg: dict, args) -> list[TrainingPair]:
    """Crawl docs for a single language and return training pairs."""
    base_url = source_cfg["base_url"]
    lang_name = source_cfg["lang_name"]
    log.info("=== Harvesting %s docs from %s ===", lang_name, base_url)

    # Respect robots.txt
    rp = _check_robots(base_url)
    if not rp.can_fetch(USER_AGENT, base_url):
        log.warning("robots.txt disallows crawling %s, skipping", base_url)
        return []

    checkpoint = Checkpoint.load(args.checkpoint)

    # Fetch index page
    index_url = base_url
    idx = source_cfg.get("index_pattern")
    if idx:
        index_url = urljoin(base_url, idx)

    soup = _fetch_page(index_url)
    if soup is None:
        log.error("Could not fetch index page %s", index_url)
        return []

    # Discover pages to crawl
    pages = _discover_links(soup, base_url, source_cfg, args.max_pages)
    # Also process the index page itself
    pages.insert(0, index_url)
    # Deduplicate while preserving order
    seen = set()
    unique_pages = []
    for p in pages:
        if p not in seen:
            seen.add(p)
            unique_pages.append(p)
    pages = unique_pages[:args.max_pages]

    log.info("Found %d pages to process for %s", len(pages), lang_name)
    all_pairs: list[TrainingPair] = []

    for i, page_url in enumerate(pages):
        refresh_days = getattr(args, "refresh_after", 0)
        if page_url in checkpoint.visited:
            if refresh_days and checkpoint.is_stale(page_url, refresh_days):
                log.info("Re-scraping stale URL (>%dd): %s", refresh_days, page_url)
            else:
                log.debug("Skipping already-visited %s", page_url)
                continue

        if not rp.can_fetch(USER_AGENT, page_url):
            log.debug("robots.txt blocks %s, skipping", page_url)
            checkpoint.mark_visited(page_url, 0)
            continue

        log.info("[%d/%d] %s", i + 1, len(pages), page_url)
        page_soup = _fetch_page(page_url)
        if page_soup is None:
            checkpoint.mark_visited(page_url, 0)
            continue

        examples = _extract_examples(page_soup, page_url, source_cfg, lang)
        pairs = _generate_pairs(examples, lang_name, args.min_quality)

        if args.dry_run:
            for p in pairs:
                log.info("  [DRY] %.3f | %s", p.quality_score, p.instruction[:80])
        else:
            all_pairs.extend(pairs)

        checkpoint.mark_visited(page_url, len(pairs))
        checkpoint.total_pairs += len(pairs)

        # Save checkpoint periodically
        if (i + 1) % 10 == 0 and not args.dry_run:
            checkpoint.save(args.checkpoint)

        # Rate limiting
        if args.delay > 0 and i < len(pages) - 1:
            time.sleep(args.delay)

    # Final checkpoint save
    if not args.dry_run:
        checkpoint.save(args.checkpoint)

    log.info("Extracted %d quality pairs for %s (visited %d pages)",
             len(all_pairs), lang_name, len(checkpoint.visited))
    return all_pairs


def _run_watch_mode():
    """Run harvester continuously, re-checking sources on interval."""
    parser = argparse.ArgumentParser(description="Watch mode — continuous harvesting")
    parser.add_argument("--language", default="all",
                        choices=["rust", "go", "cpp", "hive", "all"])
    parser.add_argument("--output", default=None)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--min-quality", type=float, default=0.60)
    parser.add_argument("--checkpoint", default="harvest_checkpoint.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--refresh-after", type=int, default=7,
                        help="Re-scrape URLs older than N days (default: 7)")
    parser.add_argument("--interval", type=int, default=3600,
                        help="Seconds between watch cycles (default: 3600)")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    languages = list(DOC_SOURCES.keys()) if args.language == "all" else [args.language]
    cycle = 0
    while True:
        cycle += 1
        log.info("=== Watch cycle %d ===", cycle)
        total = 0
        for lang in languages:
            if lang not in DOC_SOURCES:
                continue
            pairs = harvest_language(lang, DOC_SOURCES[lang], args)
            if pairs and not args.dry_run:
                out = args.output or f"loras/training_data/harvested_{lang}.jsonl"
                _export_jsonl(pairs, out)
                total += len(pairs)
        log.info("Cycle %d complete — %d new pairs. Sleeping %ds...", cycle, total, args.interval)
        time.sleep(args.interval)


def main():
    parser = argparse.ArgumentParser(
        description="Harvest code examples from documentation and generate training pairs"
    )
    parser.add_argument("--language", default="all",
                        choices=["rust", "go", "cpp", "hive", "all"],
                        help="Which documentation to scrape (default: all)")
    parser.add_argument("--output", default=None,
                        help="Output JSONL path (default: loras/training_data/harvested_{lang}.jsonl)")
    parser.add_argument("--max-pages", type=int, default=100,
                        help="Max pages to crawl per language (default: 100)")
    parser.add_argument("--min-quality", type=float, default=0.60,
                        help="Minimum quality score for a pair (default: 0.60)")
    parser.add_argument("--checkpoint", default="harvest_checkpoint.json",
                        help="Checkpoint file for resume support")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be extracted without saving")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds between requests (default: 1.0)")
    parser.add_argument("--refresh-after", type=int, default=0,
                        help="Re-scrape URLs older than N days (0=never, default: 0)")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    languages = list(DOC_SOURCES.keys()) if args.language == "all" else [args.language]

    total = 0
    for lang in languages:
        if lang not in DOC_SOURCES:
            log.error("Unknown language: %s", lang)
            continue

        pairs = harvest_language(lang, DOC_SOURCES[lang], args)

        if pairs and not args.dry_run:
            out = args.output or f"loras/training_data/harvested_{lang}.jsonl"
            _export_jsonl(pairs, out)
            total += len(pairs)

    if args.dry_run:
        log.info("Dry run complete — no files written")
    else:
        log.info("Done. Total pairs exported: %d", total)


if __name__ == "__main__":
    import sys as _sys
    if "--mcp" in _sys.argv:
        _sys.argv.remove("--mcp")
        from knowledge_harvester_mcp import start_mcp_server
        start_mcp_server()
    elif "--watch" in _sys.argv:
        _sys.argv.remove("--watch")
        _run_watch_mode()
    else:
        main()
