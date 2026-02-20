import logging
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

SEED_URLS = {
    "hive blockchain": [
        "https://developers.hive.io/",
        "https://hive.io/eco/",
        "https://gitlab.syncad.com/hive/hive/-/blob/master/doc/devs/operations/README.md",
        "https://beem.readthedocs.io/en/latest/",
        "https://cdn.hive.io/DHF-Whitepaper.pdf",
        "https://peakd.com/@hiveio",
        "https://github.com/openhive-network",
        "https://developers.hive.io/apidefinitions/",
    ],
    "python": [
        "https://docs.python.org/3/",
        "https://wiki.python.org/moin/BeginnersGuide",
        "https://realpython.com/",
    ],
    "javascript": [
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript",
        "https://javascript.info/",
    ],
    "blockchain": [
        "https://en.wikipedia.org/wiki/Blockchain",
        "https://ethereum.org/en/developers/docs/",
    ],
    "machine learning": [
        "https://scikit-learn.org/stable/",
        "https://pytorch.org/docs/stable/",
        "https://en.wikipedia.org/wiki/Machine_learning",
    ],
    "artificial intelligence": [
        "https://en.wikipedia.org/wiki/Artificial_intelligence",
        "https://ai.google/discover/",
    ],
}

SOCIAL_MEDIA_DOMAINS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "linkedin.com", "tiktok.com",
}

MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".mp4", ".webm", ".svg", ".ico", ".bmp", ".pdf"}

NON_CONTENT_PATHS = {
    "login", "signin", "signup", "register", "about", "contact",
    "privacy", "terms", "tos", "cookie", "legal", "help", "support",
}

TOPIC_STOP_WORDS = {
    "a", "an", "the", "of", "in", "on", "for", "and", "or", "to", "is",
    "vs", "versus", "about", "with", "how", "what", "why", "knowledge",
}


def search_duckduckgo(query, max_results=15):
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed for '{query}': {e}")
        return []

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.select("a.result__a")
        urls = []
        for link in links:
            href = link.get("href", "")
            if not href:
                continue

            parsed = urlparse(href)
            if "duckduckgo.com" in (parsed.netloc or parsed.path):
                qs = parse_qs(parsed.query)
                uddg = qs.get("uddg", [None])[0]
                if uddg:
                    href = unquote(uddg)
                else:
                    continue

            if not href.startswith("http"):
                continue

            final_parsed = urlparse(href)
            if "duckduckgo.com" in final_parsed.netloc:
                continue
            if final_parsed.scheme not in ("http", "https"):
                continue

            urls.append(href)
            if len(urls) >= max_results:
                break

        logger.info(f"DuckDuckGo search for '{query}': found {len(urls)} URLs")
        return urls
    except Exception as e:
        logger.warning(f"DuckDuckGo result parsing failed: {e}")
        return []


def _searxng_filter_url(url):
    if not url or not url.startswith("http"):
        return False
    domain = urlparse(url).netloc.lower()
    if any(skip in domain for skip in ("duckduckgo.com", "google.com", "searx", "searxng", "bing.com")):
        return False
    return True


def _searxng_parse_html(html, max_results):
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for link in soup.select("h3 a, .result a, .result a.url_wrapper, a.result__url, article a, .result-default a"):
        href = link.get("href", "")
        if _searxng_filter_url(href):
            if href not in urls:
                urls.append(href)
                if len(urls) >= max_results:
                    break
    if not urls:
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if _searxng_filter_url(href) and href not in urls:
                parsed = urlparse(href)
                if parsed.path and parsed.path != "/":
                    urls.append(href)
                    if len(urls) >= max_results:
                        break
    return urls


_searxng_instance_cache = {"instances": [], "fetched": 0}

def _get_searxng_instances():
    import time
    cache = _searxng_instance_cache
    if cache["instances"] and (time.time() - cache["fetched"]) < 3600:
        return cache["instances"]

    hardcoded = [
        "https://priv.au",
        "https://paulgo.io",
        "https://opnxng.com",
        "https://etsi.me",
        "https://baresearch.org",
        "https://search.sapti.me",
        "https://searx.be",
    ]
    try:
        resp = requests.get("https://searx.space/data/instances.json", timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            live = []
            for url, info in data.get("instances", {}).items():
                if not isinstance(info, dict):
                    continue
                if info.get("http", {}).get("status_code") == 200:
                    clean = url.rstrip("/")
                    if clean.startswith("https://"):
                        live.append(clean)
            if live:
                import random
                random.shuffle(live)
                combined = []
                seen = set()
                for u in hardcoded + live:
                    if u not in seen:
                        seen.add(u)
                        combined.append(u)
                cache["instances"] = combined[:20]
                cache["fetched"] = time.time()
                logger.info(f"SearXNG: loaded {len(combined)} instances ({len(live)} live from searx.space)")
                return cache["instances"]
    except Exception:
        pass
    return hardcoded


def search_searxng(query, max_results=15):
    instances = _get_searxng_instances()
    max_attempts = min(len(instances), 8)
    for instance in instances[:max_attempts]:
        try:
            resp = requests.get(
                f"{instance}/search",
                params={"q": query, "format": "json", "categories": "general", "language": "en"},
                headers=HEADERS,
                timeout=6,
            )
            if resp.status_code == 429:
                resp = requests.get(
                    f"{instance}/search",
                    params={"q": query, "categories": "general", "language": "en"},
                    headers=HEADERS,
                    timeout=6,
                )
                ct = resp.headers.get("content-type", "")
                if resp.status_code == 200 and ("text/html" in ct or "text/plain" in ct or not ct):
                    urls = _searxng_parse_html(resp.text, max_results)
                    if urls:
                        logger.info(f"SearXNG HTML via {instance} for '{query}': found {len(urls)} URLs")
                        return urls
                continue
            resp.raise_for_status()
            data = resp.json()
            urls = []
            for result in data.get("results", []):
                url = result.get("url", "")
                if _searxng_filter_url(url):
                    urls.append(url)
                    if len(urls) >= max_results:
                        break
            logger.info(f"SearXNG search via {instance} for '{query}': found {len(urls)} URLs")
            return urls
        except Exception:
            continue
    logger.warning(f"SearXNG search failed for '{query}': all instances exhausted")
    return []


_brave_disabled = False

def search_brave(query, max_results=15):
    global _brave_disabled
    from hiveai.config import BRAVE_API_KEY
    if not BRAVE_API_KEY or _brave_disabled:
        return []
    try:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": BRAVE_API_KEY,
        }
        params = {"q": query, "count": min(max_results, 20)}
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
            timeout=10,
        )
        if resp.status_code in (401, 403):
            logger.warning(f"Brave Search auth failed (HTTP {resp.status_code}), disabling for this session")
            _brave_disabled = True
            return []
        resp.raise_for_status()
        data = resp.json()
        urls = [r["url"] for r in data.get("web", {}).get("results", []) if r.get("url")]
        logger.info(f"Brave search for '{query}': found {len(urls)} URLs")
        return urls[:max_results]
    except Exception as e:
        logger.warning(f"Brave search failed for '{query}': {e}")
        return []


def _check_url(url, timeout):
    try:
        original_parsed = urlparse(url)
        resp = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code == 405:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True, stream=True)
            resp.close()
        if not (200 <= resp.status_code < 400):
            return None

        final_url = resp.url
        final_parsed = urlparse(final_url)

        if original_parsed.path and original_parsed.path not in ("/", ""):
            if final_parsed.path in ("/", "") and final_parsed.netloc != original_parsed.netloc:
                return None

        return url
    except Exception:
        return None


def validate_urls(urls, timeout=10):
    if not urls:
        return []

    valid = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(_check_url, url, timeout): url for url in urls}
        for future in as_completed(future_to_url):
            result = future.result()
            if result:
                valid.append(result)

    filtered_count = len(urls) - len(valid)
    if filtered_count > 0:
        logger.info(f"URL validation: {len(valid)} valid, {filtered_count} filtered out")
    return valid


def _topic_keywords(topic):
    words = set()
    for w in topic.lower().replace("-", " ").replace("_", " ").split():
        w = w.strip(".,;:!?()[]{}\"'")
        if len(w) > 1 and w not in TOPIC_STOP_WORDS:
            words.add(w)
    return words


def extract_links_from_content(html_or_markdown, source_url, topic):
    md_pattern = re.compile(r'\[([^\]]*)\]\((https?://[^)]+)\)')
    raw_pattern = re.compile(r'(?<!\()(https?://[^\s<>"\'\]]+)')

    found_urls = set()
    for _, url in md_pattern.findall(html_or_markdown):
        found_urls.add(url)
    for url in raw_pattern.findall(html_or_markdown):
        url = url.rstrip(".,;:!?)")
        found_urls.add(url)

    source_parsed = urlparse(source_url)
    keywords = _topic_keywords(topic)
    scored = []

    for url in found_urls:
        parsed = urlparse(url)

        if not parsed.scheme or parsed.scheme not in ("http", "https"):
            continue
        if parsed.fragment and not parsed.path:
            continue

        path_lower = parsed.path.lower()
        ext = ""
        if "." in path_lower.split("/")[-1]:
            ext = "." + path_lower.split("/")[-1].rsplit(".", 1)[-1]
        if ext in MEDIA_EXTENSIONS:
            continue

        domain = parsed.netloc.lower()
        if any(sm in domain for sm in SOCIAL_MEDIA_DOMAINS):
            continue
        if "reddit.com/r/" in url.lower():
            continue

        path_parts = path_lower.strip("/").split("/")
        if len(path_parts) == 1 and path_parts[0] in NON_CONTENT_PATHS:
            continue

        if domain == source_parsed.netloc and parsed.path == source_parsed.path:
            continue

        score = 0
        url_lower = url.lower()
        for kw in keywords:
            if kw in domain:
                score += 2
            if kw in path_lower:
                score += 1

        scored.append((url, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:10]


def get_seed_urls(topic):
    topic_lower = topic.lower()
    matched = []
    seen = set()

    for key, urls in SEED_URLS.items():
        if key in topic_lower:
            for url in urls:
                if url not in seen:
                    seen.add(url)
                    matched.append(url)

    logger.info(f"Seed URLs for '{topic}': {len(matched)} URLs from {sum(1 for k in SEED_URLS if k in topic_lower)} categories")
    return matched


def _domain_path_key(url):
    parsed = urlparse(url)
    return (parsed.netloc.lower(), parsed.path.rstrip("/").lower())


def discover_urls(topic, max_urls=25):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    seed_urls = get_seed_urls(topic)
    seed_count = len(seed_urls)

    search_results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(search_duckduckgo, topic): "ddg",
            executor.submit(search_searxng, topic): "searxng",
            executor.submit(search_brave, topic): "brave",
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                search_results[source] = future.result()
            except Exception as e:
                logger.warning(f"{source} search failed: {e}")
                search_results[source] = []

    ddg_urls = search_results.get("ddg", [])
    searxng_urls = search_results.get("searxng", [])
    brave_urls = search_results.get("brave", [])

    combined = []
    seen_keys = set()
    for url in seed_urls + searxng_urls + brave_urls + ddg_urls:
        key = _domain_path_key(url)
        if key not in seen_keys:
            seen_keys.add(key)
            combined.append(url)

    total_found = seed_count + len(ddg_urls) + len(searxng_urls) + len(brave_urls)
    dedup_count = total_found - len(combined)

    validated = validate_urls(combined)

    result = validated[:max_urls]
    logger.info(
        f"URL discovery for '{topic}': {seed_count} seed, {len(ddg_urls)} DDG, "
        f"{len(searxng_urls)} SearXNG, {len(brave_urls)} Brave, "
        f"{dedup_count} deduped, {len(validated)} validated, returning {len(result)}"
    )
    return result


def discover_gap_urls(topic, missing_facts, existing_urls, max_urls=10):
    gap_terms = " ".join([fact for fact in missing_facts if fact][:3])
    query = f"{topic} {gap_terms}".strip()

    from concurrent.futures import ThreadPoolExecutor, as_completed
    all_urls = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(search_duckduckgo, query, 10): "ddg",
            executor.submit(search_searxng, query, 10): "searxng",
            executor.submit(search_brave, query, 10): "brave",
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                all_urls.extend(future.result())
            except Exception as e:
                logger.warning(f"Gap {source} search failed: {e}")

    existing_set = set(existing_urls) if existing_urls else set()
    existing_keys = {_domain_path_key(u) for u in existing_set}

    new_urls = []
    seen_keys = set()
    for url in all_urls:
        key = _domain_path_key(url)
        if url not in existing_set and key not in existing_keys and key not in seen_keys:
            seen_keys.add(key)
            new_urls.append(url)

    validated = validate_urls(new_urls)
    result = validated[:max_urls]

    logger.info(
        f"Gap URL discovery for '{topic}': {len(all_urls)} total results, "
        f"{len(new_urls)} new unique, {len(validated)} validated, returning {len(result)}"
    )
    return result
