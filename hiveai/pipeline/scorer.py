"""
hiveai/pipeline/scorer.py

Golden Book quality assessment — 8-dimensional scoring system.

Original 5 dimensions (surface-level):
  - Section coverage, word count, source diversity, fact density, structure

Enhanced with 3 new dimensions:
  - Code quality: AST-validated code blocks, complexity, error handling
  - Coherence: section-to-section flow, balanced depth
  - Topic coverage: key concept presence, completeness signals
"""
import re
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _score_section_coverage(content):
    if not content:
        return 0.0
    headings = re.findall(r'^#{1,3}\s+.+', content, re.MULTILINE)
    count = len(headings)
    if count >= 12:
        return 1.0
    elif count >= 8:
        return 0.8
    elif count >= 5:
        return 0.5
    elif count >= 3:
        return 0.3
    elif count >= 1:
        return 0.1
    return 0.0


def _score_word_count(word_count):
    if word_count is None:
        return 0.0
    if word_count >= 3000:
        return 1.0
    elif word_count >= 2000:
        return 0.8
    elif word_count >= 1000:
        return 0.6
    elif word_count >= 500:
        return 0.4
    elif word_count >= 300:
        return 0.2
    return 0.1


def _score_source_diversity(source_urls):
    if not source_urls:
        return 0.0
    domains = set()
    for url in source_urls:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            domain = re.sub(r'^www\.', '', domain)
            if domain:
                domains.add(domain)
        except Exception:
            continue
    count = len(domains)
    if count >= 8:
        return 1.0
    elif count >= 5:
        return 0.7
    elif count >= 3:
        return 0.5
    elif count >= 1:
        return 0.2
    return 0.0


def _score_fact_density(content):
    if not content:
        return 0.0
    sentences = re.split(r'[.!?]+', content)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if not sentences:
        return 0.0

    fact_count = 0
    for sentence in sentences:
        has_number = bool(re.search(r'\d+', sentence))
        words = sentence.split()
        has_proper_noun = any(
            w[0].isupper() and i > 0
            for i, w in enumerate(words)
            if len(w) > 1 and not w.startswith('#')
        )
        has_technical = any(
            ('-' in w or '_' in w) and len(w) > 3
            for w in words
        )
        if has_number or has_proper_noun or has_technical:
            fact_count += 1

    ratio = fact_count / len(sentences)
    if ratio >= 0.7:
        return 1.0
    elif ratio >= 0.5:
        return 0.7
    elif ratio >= 0.3:
        return 0.5
    elif ratio >= 0.2:
        return 0.3
    return 0.1


def _score_structure_quality(content):
    if not content:
        return 0.0
    score = 0.0

    if re.search(r'^#\s+.+', content, re.MULTILINE):
        score += 0.2

    h2_count = len(re.findall(r'^##\s+.+', content, re.MULTILINE))
    if h2_count >= 2:
        score += 0.3

    if re.search(r'^[\s]*[-*]\s+', content, re.MULTILINE) or re.search(r'^[\s]*\d+\.\s+', content, re.MULTILINE):
        score += 0.2

    conclusion_patterns = [
        r'^#{1,3}\s+(conclusion|summary|final\s+thoughts|key\s+takeaways|wrap.?up)',
    ]
    for pattern in conclusion_patterns:
        if re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
            score += 0.2
            break

    meta_starts = ["here is", "i'll write", "i will write", "below is", "this document", "in this article"]
    first_line = content.strip().split('\n')[0].lower().lstrip('#').strip() if content.strip() else ""
    if not any(first_line.startswith(m) for m in meta_starts):
        score += 0.1

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# NEW DIMENSIONS — code quality, coherence, topic coverage
# ---------------------------------------------------------------------------

def _score_code_quality(content):
    """
    Score the quality of code blocks in the book.
    0.0 = no code, 1.0 = multiple valid, complex code blocks.
    """
    if not content:
        return 0.0
    import ast as _ast

    code_pattern = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)
    blocks = code_pattern.findall(content)

    if not blocks:
        return 0.0

    score = 0.0
    valid_count = 0
    has_functions = False
    has_error_handling = False
    total_lines = 0

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = [ln for ln in block.split("\n") if ln.strip() and not ln.strip().startswith("#")]
        total_lines += len(lines)

        try:
            tree = _ast.parse(block)
            valid_count += 1
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                    has_functions = True
                if isinstance(node, (_ast.Try, _ast.ExceptHandler)):
                    has_error_handling = True
        except SyntaxError:
            pass

    # Block count
    if len(blocks) >= 4:
        score += 0.3
    elif len(blocks) >= 2:
        score += 0.2
    elif len(blocks) >= 1:
        score += 0.1

    # Valid syntax ratio
    if valid_count >= 3:
        score += 0.3
    elif valid_count >= 2:
        score += 0.2
    elif valid_count >= 1:
        score += 0.1

    # Sophistication
    if has_functions:
        score += 0.2
    if has_error_handling:
        score += 0.1

    # Code volume
    if total_lines >= 30:
        score += 0.1

    return min(score, 1.0)


def _score_coherence(content):
    """
    Score how well sections flow together and maintain balanced depth.
    0.0 = choppy/unbalanced, 1.0 = well-organized with even depth.
    """
    if not content:
        return 0.0

    # Split by section headers
    sections = re.split(r'^#{1,3}\s+', content, flags=re.MULTILINE)
    sections = [s.strip() for s in sections if len(s.strip()) > 50]

    if len(sections) < 2:
        return 0.3  # Only one section — can't assess inter-section coherence

    score = 0.0

    # Balance: section lengths shouldn't vary by more than 5x
    section_lengths = [len(s.split()) for s in sections]
    if section_lengths:
        min_len = max(min(section_lengths), 1)
        max_len = max(section_lengths)
        balance_ratio = min_len / max_len
        if balance_ratio >= 0.3:
            score += 0.3  # Reasonably balanced
        elif balance_ratio >= 0.1:
            score += 0.15
        # Very unbalanced: one 2000-word section and one 20-word section

    # Transition words between sections (indicates flow)
    transition_markers = [
        "building on", "related to", "in addition", "furthermore",
        "as mentioned", "similarly", "in contrast", "moving to",
        "next,", "finally,", "another", "additionally",
    ]
    content_lower = content.lower()
    transition_count = sum(1 for m in transition_markers if m in content_lower)
    if transition_count >= 4:
        score += 0.3
    elif transition_count >= 2:
        score += 0.2
    elif transition_count >= 1:
        score += 0.1

    # No orphan sections (very short sections suggest incomplete content)
    orphans = sum(1 for l in section_lengths if l < 30)
    if orphans == 0:
        score += 0.2
    elif orphans <= 1:
        score += 0.1

    # Multiple section depths (h1, h2, h3 = hierarchical organization)
    h1 = len(re.findall(r'^#\s+', content, re.MULTILINE))
    h2 = len(re.findall(r'^##\s+', content, re.MULTILINE))
    h3 = len(re.findall(r'^###\s+', content, re.MULTILINE))
    depth_levels = sum(1 for c in [h1, h2, h3] if c > 0)
    if depth_levels >= 3:
        score += 0.2
    elif depth_levels >= 2:
        score += 0.1

    return min(score, 1.0)


def _score_topic_coverage(content, title):
    """
    Score how well the book covers its stated topic.
    Checks for key concept mentions and completeness signals.
    """
    if not content or not title:
        return 0.0

    content_lower = content.lower()
    title_lower = title.lower()
    score = 0.0

    # Title keywords appear in content (topic relevance)
    title_words = [w for w in title_lower.split() if len(w) >= 4 and w.isalpha()]
    if title_words:
        mentioned = sum(1 for w in title_words if w in content_lower)
        mention_ratio = mentioned / len(title_words)
        if mention_ratio >= 0.8:
            score += 0.3
        elif mention_ratio >= 0.5:
            score += 0.2
        elif mention_ratio >= 0.3:
            score += 0.1

    # Completeness signals
    completeness_markers = [
        "example", "implementation", "use case", "advantage", "disadvantage",
        "limitation", "alternative", "comparison", "best practice",
        "common mistake", "performance", "trade-off",
    ]
    hits = sum(1 for m in completeness_markers if m in content_lower)
    if hits >= 6:
        score += 0.3
    elif hits >= 4:
        score += 0.2
    elif hits >= 2:
        score += 0.1

    # Has practical content (code examples + explanations together)
    has_code = bool(re.search(r"```", content))
    has_explanation = bool(re.search(r"because|therefore|this means|the reason", content_lower))
    if has_code and has_explanation:
        score += 0.2

    # Doesn't have filler markers
    filler_markers = ["lorem ipsum", "placeholder", "todo", "tbd", "to be determined"]
    if not any(f in content_lower for f in filler_markers):
        score += 0.2

    return min(score, 1.0)


def score_book(book):
    """
    8-dimensional book quality scoring.

    Original dimensions (surface-level):
      - section_coverage, word_count_density, source_diversity, fact_density, structure_quality

    Enhanced dimensions:
      - code_quality, coherence, topic_coverage
    """
    content = book.content or ""
    source_urls = book.source_urls or []
    word_count = book.word_count or len(content.split())

    # Original 5 dimensions
    section_coverage = _score_section_coverage(content)
    word_count_density = _score_word_count(word_count)
    source_diversity = _score_source_diversity(source_urls)
    fact_density = _score_fact_density(content)
    structure_quality = _score_structure_quality(content)

    # New 3 dimensions
    code_quality = _score_code_quality(content)
    coherence = _score_coherence(content)
    topic_coverage = _score_topic_coverage(content, book.title)

    details = {
        "section_coverage": round(section_coverage, 2),
        "word_count_density": round(word_count_density, 2),
        "source_diversity": round(source_diversity, 2),
        "fact_density": round(fact_density, 2),
        "structure_quality": round(structure_quality, 2),
        "code_quality": round(code_quality, 2),
        "coherence": round(coherence, 2),
        "topic_coverage": round(topic_coverage, 2),
    }

    # Weighted average — content quality matters more than surface metrics
    weights = {
        "section_coverage": 0.10,
        "word_count_density": 0.10,
        "source_diversity": 0.10,
        "fact_density": 0.15,
        "structure_quality": 0.10,
        "code_quality": 0.15,
        "coherence": 0.15,
        "topic_coverage": 0.15,
    }

    overall = sum(details[k] * weights[k] for k in details)

    result = {
        "score": round(overall, 2),
        "details": details,
    }

    logger.info(f"Book '{book.title}' scored {result['score']}: {details}")
    return result
