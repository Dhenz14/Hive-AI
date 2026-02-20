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


def score_book(book):
    content = book.content or ""
    source_urls = book.source_urls or []
    word_count = book.word_count or len(content.split())

    section_coverage = _score_section_coverage(content)
    word_count_density = _score_word_count(word_count)
    source_diversity = _score_source_diversity(source_urls)
    fact_density = _score_fact_density(content)
    structure_quality = _score_structure_quality(content)

    details = {
        "section_coverage": round(section_coverage, 2),
        "word_count_density": round(word_count_density, 2),
        "source_diversity": round(source_diversity, 2),
        "fact_density": round(fact_density, 2),
        "structure_quality": round(structure_quality, 2),
    }

    overall = sum(details.values()) / len(details)

    result = {
        "score": round(overall, 2),
        "details": details,
    }

    logger.info(f"Book '{book.title}' scored {result['score']}: {details}")
    return result
