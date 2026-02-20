import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DOMAIN_AUTHORITY_SCORES = {
    "wikipedia.org": 1.0,
    "simple.wikipedia.org": 1.0,
    "docs.python.org": 0.95,
    "doc.rust-lang.org": 0.95,
    "developer.mozilla.org": 0.95,
    "developer.android.com": 0.95,
    "developer.apple.com": 0.95,
    "docs.oracle.com": 0.95,
    "learn.microsoft.com": 0.95,
    "golang.org": 0.95,
    "nodejs.org": 0.95,
    "ruby-doc.org": 0.95,
    "docs.djangoproject.com": 0.95,
    "flask.palletsprojects.com": 0.95,
    "tools.ietf.org": 0.9,
    "www.w3.org": 0.9,
    "tc39.es": 0.9,
    "ecma-international.org": 0.9,
    "stackoverflow.com": 0.85,
    "github.com": 0.85,
    "arxiv.org": 0.85,
    "geeksforgeeks.org": 0.8,
    "tutorialspoint.com": 0.8,
    "w3schools.com": 0.8,
    "freecodecamp.org": 0.8,
    "realpython.com": 0.8,
    "medium.com": 0.7,
    "dev.to": 0.7,
    "news.ycombinator.com": 0.7,
    "hackernews.com": 0.7,
}


def get_domain_authority(url: str) -> float:
    """Extract domain from URL and return its authority score (0.0-1.0)."""
    if not url:
        return 0.5

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        domain = domain.replace("www.", "")

        if domain in DOMAIN_AUTHORITY_SCORES:
            return DOMAIN_AUTHORITY_SCORES[domain]

        for known_domain, score in DOMAIN_AUTHORITY_SCORES.items():
            if domain.endswith(known_domain) or known_domain.endswith(domain):
                return score

        return 0.5
    except Exception:
        return 0.5


def adjust_triple_confidence(confidence: float, source_url: str) -> float:
    """Adjust triple confidence using weighted blend of confidence and source authority."""
    if not source_url:
        return confidence

    authority = get_domain_authority(source_url)
    adjusted = 0.7 * confidence + 0.3 * authority
    return adjusted
