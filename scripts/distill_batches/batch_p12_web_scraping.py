"""
Batch P12 — Web Scraping & Data Extraction
Covers: Playwright/headless browser automation, structured data extraction,
anti-bot bypass techniques, large-scale crawl architecture, data pipeline
from web to knowledge graph.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    # --- 1. Playwright / Headless Browser Automation ---
    (
        "web-scraping/playwright-headless-browser-automation",
        r"""Explain how to use Playwright for headless browser automation in web scraping scenarios, covering page interaction patterns, network interception and request modification, stealth techniques to avoid detection, session and cookie management, and parallel scraping with browser contexts, including production-ready Python code examples.""",
        r"""# Playwright for Headless Browser Automation in Web Scraping

## Why Playwright Over Raw HTTP

When scraping modern web applications, a **common mistake** is reaching for `requests` or `httpx` as the first tool. Many sites today render content entirely via JavaScript -- single-page applications built with React, Vue, or Angular that return an empty `<div id="root"></div>` in the initial HTML. Because of this, you need a real browser engine to execute JavaScript and produce the final DOM. Playwright provides exactly that: a high-level API to control Chromium, Firefox, or WebKit from Python, Node.js, or .NET.

However, Playwright is not simply "Selenium but newer." It was designed from the ground up for **reliability and speed**. It auto-waits for elements to be actionable before clicking, supports network interception at the protocol level, and can run multiple isolated browser contexts in a single browser process -- therefore dramatically reducing memory overhead compared to launching separate browser instances.

The **trade-off** is resource consumption: even a single headless Chromium instance uses 100-300 MB of RAM. For high-volume scraping, you must therefore combine Playwright with careful concurrency management and fall back to raw HTTP requests whenever JavaScript rendering is not actually required.

## Installation and Basic Page Interaction

```python
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Page, BrowserContext, Browser

async def setup_browser(
    headless: bool = True,
    proxy: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> tuple[Browser, BrowserContext, Page]:
    # Launch a Chromium browser with configurable proxy and user agent
    pw = await async_playwright().start()

    launch_options: dict = {"headless": headless}
    if proxy:
        launch_options["proxy"] = {"server": proxy}

    browser = await pw.chromium.launch(**launch_options)

    context_options: dict = {}
    if user_agent:
        context_options["user_agent"] = user_agent
    context_options["viewport"] = {"width": 1920, "height": 1080}
    context_options["java_script_enabled"] = True

    context = await browser.new_context(**context_options)
    page = await context.new_page()
    return browser, context, page


async def scrape_product_page(page: Page, url: str) -> dict[str, str]:
    # Navigate and wait for the main content to be visible
    await page.goto(url, wait_until="networkidle")

    # Wait for a specific selector that indicates content is loaded
    await page.wait_for_selector("div.product-details", timeout=15000)

    title = await page.text_content("h1.product-title")
    price = await page.text_content("span.price-current")
    description = await page.text_content("div.product-description")

    return {
        "title": (title or "").strip(),
        "price": (price or "").strip(),
        "description": (description or "").strip(),
    }
```

The **best practice** for waiting is to use `wait_for_selector` with a meaningful DOM element rather than arbitrary `time.sleep()` calls. Playwright's auto-wait mechanism handles most timing issues, but explicit waits on content selectors ensure you do not proceed until the data you need is actually rendered.

## Network Interception and Request Modification

One of Playwright's most powerful features is the ability to intercept, modify, or block network requests at the protocol level. This is invaluable for scraping because you can block images, fonts, and tracking scripts to speed up page loads by 50-80%.

```python
from playwright.async_api import Route, Request
from typing import Callable

BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}
BLOCKED_DOMAINS = {"google-analytics.com", "facebook.net", "doubleclick.net"}


async def route_handler(route: Route, request: Request) -> None:
    # Block unnecessary resource types and tracking domains
    resource_type = route.request.resource_type
    url = route.request.url

    if resource_type in BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return

    for domain in BLOCKED_DOMAINS:
        if domain in url:
            await route.abort()
            return

    await route.continue_()


async def intercept_api_responses(
    page: Page,
    api_pattern: str,
    callback: Callable[[dict], None],
) -> None:
    # Capture JSON API responses that the page makes internally
    async def handle_response(response):
        if api_pattern in response.url and response.status == 200:
            try:
                data = await response.json()
                callback(data)
            except Exception:
                pass

    page.on("response", handle_response)


async def scrape_with_interception(url: str) -> list[dict]:
    # Demonstrate blocking resources and capturing API data
    captured_data: list[dict] = []

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    # Block unnecessary resources for faster loading
    await page.route("**/*", route_handler)

    # Capture internal API calls the page makes
    await intercept_api_responses(
        page, "/api/products", lambda d: captured_data.append(d)
    )

    await page.goto(url, wait_until="networkidle")
    await browser.close()

    return captured_data
```

This interception approach is significant **because** many modern SPAs fetch their data from internal JSON APIs. By capturing those responses directly, you bypass the need to parse the rendered DOM entirely -- the structured data is already in JSON format.

## Stealth Techniques to Avoid Detection

A major **pitfall** in browser-based scraping is detection by anti-bot systems. Headless browsers have telltale fingerprints that sites check for. The `playwright-stealth` plugin patches many of these signals.

```python
from playwright.async_api import async_playwright
from typing import Any

# Stealth configuration to mask headless browser fingerprints
STEALTH_SCRIPTS: list[str] = [
    # Override navigator.webdriver property
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});",
    # Fake plugins array
    "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});",
    # Fake languages
    "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});",
    # Override chrome runtime to appear as a real browser
    "window.chrome = { runtime: {} };",
]


async def create_stealth_context(
    browser,
    timezone: str = "America/New_York",
    locale: str = "en-US",
    color_scheme: str = "light",
) -> BrowserContext:
    # Create a browser context that mimics a real user
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale=locale,
        timezone_id=timezone,
        color_scheme=color_scheme,
        permissions=["geolocation"],
        geolocation={"latitude": 40.7128, "longitude": -74.0060},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )

    # Inject stealth scripts before any page navigation
    await context.add_init_script(script="\n".join(STEALTH_SCRIPTS))
    return context


async def save_and_restore_session(
    context: BrowserContext,
    storage_path: str = "session_state.json",
) -> None:
    # Persist cookies and local storage for session continuity
    storage = await context.storage_state()
    import json
    from pathlib import Path
    Path(storage_path).write_text(json.dumps(storage, indent=2))
```

## Parallel Scraping with Browser Contexts

For throughput, Playwright supports multiple **browser contexts** within a single browser process. Each context has its own cookies, cache, and session state -- therefore acting like separate browser profiles without the overhead of separate processes.

```python
import asyncio
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ScrapeResult:
    url: str
    data: dict
    success: bool
    error: Optional[str] = None


@dataclass
class ParallelScraper:
    max_concurrency: int = 5
    results: list[ScrapeResult] = field(default_factory=list)
    semaphore: Optional[asyncio.Semaphore] = None

    def __post_init__(self) -> None:
        self.semaphore = asyncio.Semaphore(self.max_concurrency)

    async def scrape_url(
        self, browser: Browser, url: str
    ) -> ScrapeResult:
        # Each URL gets its own isolated browser context
        async with self.semaphore:
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                title = await page.title()
                content = await page.text_content("body")
                return ScrapeResult(
                    url=url,
                    data={"title": title, "text_length": len(content or "")},
                    success=True,
                )
            except Exception as e:
                return ScrapeResult(url=url, data={}, success=False, error=str(e))
            finally:
                await context.close()

    async def run(self, urls: list[str]) -> list[ScrapeResult]:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)

        tasks = [self.scrape_url(browser, url) for url in urls]
        self.results = await asyncio.gather(*tasks)

        await browser.close()
        return self.results
```

The semaphore-based approach is the **best practice** because launching too many concurrent contexts will exhaust system memory. Five to ten concurrent contexts is typically the sweet spot for a machine with 8-16 GB of RAM.

## Summary and Key Takeaways

- **Use Playwright when JavaScript rendering is required**; fall back to `httpx` for static pages because the resource overhead is significant.
- **Network interception** is your best tool for both performance (blocking unnecessary assets) and data capture (intercepting internal API calls).
- **Stealth techniques** should mask `navigator.webdriver`, fake plugin arrays, and set realistic viewport sizes, locales, and timezones. However, no stealth setup is undetectable -- pair it with proxy rotation and rate limiting.
- **Browser contexts** let you run parallel scrapes in isolated sessions within a single browser process, therefore saving memory compared to multiple browser instances.
- **Session persistence** via `storage_state()` allows you to save and restore cookies, enabling login-gated scraping across multiple runs.
- The **trade-off** with Playwright is always resource consumption versus fidelity: it gives you pixel-perfect rendering but at the cost of significantly more CPU and memory than raw HTTP scraping.
""",
    ),

    # --- 2. Structured Data Extraction ---
    (
        "web-scraping/structured-data-extraction-selectors-schema",
        r"""Describe advanced techniques for structured data extraction from web pages using CSS selectors, XPath expressions, and schema-based extraction approaches, including handling dynamically loaded content, incremental crawling strategies, data validation with Pydantic models, and production Python examples with BeautifulSoup and lxml.""",
        r"""# Structured Data Extraction: CSS Selectors, XPath, Schema-Based Parsing, and Incremental Crawling

## The Core Challenge of Web Data Extraction

Extracting structured data from HTML is fundamentally a **mapping problem**: you must transform an unstructured, presentation-oriented document into a typed, validated data record. A **common mistake** is writing fragile selectors that break whenever the site changes a CSS class name. Production-grade extraction requires layered strategies -- CSS selectors for speed, XPath for complex traversals, and schema-based validation to guarantee data quality.

The **best practice** is to treat extraction as a pipeline with three stages: (1) locate the data region on the page, (2) extract raw text or attribute values from specific elements, and (3) validate and transform the raw strings into typed fields. By separating these concerns, you build systems that are easier to debug and more resilient to HTML changes.

## CSS Selectors with BeautifulSoup

CSS selectors are the fastest and most readable way to locate elements in an HTML document. BeautifulSoup's `select` method supports a rich subset of CSS3 selectors.

```python
from bs4 import BeautifulSoup, Tag
from typing import Optional
from dataclasses import dataclass
import re

@dataclass
class ProductRecord:
    name: str
    price_cents: int
    currency: str
    rating: Optional[float]
    review_count: int
    in_stock: bool
    categories: list[str]


def parse_price(raw_price: str) -> tuple[int, str]:
    # Extract numeric price and currency from display strings like "$1,299.99"
    cleaned = raw_price.strip()
    currency = "USD"
    if cleaned.startswith("$"):
        currency = "USD"
    elif cleaned.startswith("\u20ac"):
        currency = "EUR"
    elif cleaned.startswith("\u00a3"):
        currency = "GBP"

    numeric = re.sub(r"[^\d.]", "", cleaned)
    price_cents = int(float(numeric) * 100)
    return price_cents, currency


def extract_product_css(soup: BeautifulSoup) -> Optional[ProductRecord]:
    # Use CSS selectors for a typical e-commerce product page
    title_el = soup.select_one("h1.product-title, h1[data-testid='product-name']")
    price_el = soup.select_one("span.price-current, [data-testid='current-price']")
    rating_el = soup.select_one("div.rating span.value, [itemprop='ratingValue']")
    review_el = soup.select_one("span.review-count, [itemprop='reviewCount']")
    stock_el = soup.select_one("div.stock-status, [data-testid='availability']")
    category_els = soup.select("nav.breadcrumb a, ol.breadcrumb li a")

    if not title_el or not price_el:
        return None

    price_cents, currency = parse_price(price_el.get_text())

    rating_text = rating_el.get_text().strip() if rating_el else None
    rating = float(rating_text) if rating_text else None

    review_text = review_el.get_text().strip() if review_el else "0"
    review_count = int(re.sub(r"[^\d]", "", review_text) or "0")

    stock_text = stock_el.get_text().strip().lower() if stock_el else ""
    in_stock = "in stock" in stock_text or "available" in stock_text

    categories = [a.get_text().strip() for a in category_els if a.get_text().strip()]

    return ProductRecord(
        name=title_el.get_text().strip(),
        price_cents=price_cents,
        currency=currency,
        rating=rating,
        review_count=review_count,
        in_stock=in_stock,
        categories=categories,
    )
```

Notice how each selector uses a fallback pattern with commas: `"h1.product-title, h1[data-testid='product-name']"`. This is a **best practice** because sites often A/B test different class names, and having multiple selector options makes your extractor more resilient.

## XPath for Complex Traversals with lxml

XPath surpasses CSS selectors when you need to traverse upward (to a parent), select based on text content, or apply positional logic. The `lxml` library provides the fastest XPath implementation available in Python.

```python
from lxml import html
from lxml.html import HtmlElement
from typing import Optional, Any

def extract_table_data_xpath(page_source: str) -> list[dict[str, Any]]:
    # Extract data from complex HTML tables using XPath axes
    tree: HtmlElement = html.fromstring(page_source)
    rows: list[dict[str, Any]] = []

    # Find table rows, skipping the header row
    data_rows = tree.xpath(
        "//table[contains(@class, 'data-table')]"
        "/tbody/tr[not(contains(@class, 'header'))]"
    )

    for row in data_rows:
        # Extract cells with text normalization
        cells = row.xpath("./td")
        if len(cells) < 4:
            continue

        # XPath text() gets direct text; .//text() gets all descendant text
        name = " ".join(cells[0].xpath(".//text()")).strip()
        value = " ".join(cells[1].xpath(".//text()")).strip()

        # Use ancestor axis to find the section this table belongs to
        section_header = row.xpath(
            "ancestor::div[contains(@class, 'section')]"
            "/preceding-sibling::h2[1]/text()"
        )
        section = section_header[0].strip() if section_header else "Unknown"

        # Use following-sibling to check if there is an expansion row
        detail_row = row.xpath(
            "following-sibling::tr[1][contains(@class, 'detail-row')]"
        )
        detail_text = ""
        if detail_row:
            detail_text = " ".join(detail_row[0].xpath(".//text()")).strip()

        rows.append({
            "section": section,
            "name": name,
            "value": value,
            "detail": detail_text,
        })

    return rows
```

The **trade-off** between CSS and XPath is readability versus power. CSS selectors are easier to write and read for simple cases, however XPath is indispensable when you need ancestor traversal, text-based matching (`contains(text(), 'Price')`), or positional predicates (`[position() > 1]`).

## Schema-Based Extraction with Pydantic Validation

A **pitfall** in scraping is silently accepting malformed data. By defining Pydantic models for your expected output, you catch extraction errors at parse time rather than discovering corrupted data downstream.

```python
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime
import hashlib


class ExtractedArticle(BaseModel):
    # Strict schema with validation for scraped article data
    url: str
    title: str = Field(min_length=5, max_length=500)
    author: Optional[str] = None
    published_date: Optional[datetime] = None
    body_text: str = Field(min_length=100)
    word_count: int = Field(ge=0)
    categories: list[str] = Field(default_factory=list)
    content_hash: str = ""

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        # Remove common junk suffixes from page titles
        for suffix in [" | Site Name", " - Blog", " :: Archive"]:
            if v.endswith(suffix):
                v = v[: -len(suffix)]
        return v.strip()

    @field_validator("body_text")
    @classmethod
    def validate_body_not_boilerplate(cls, v: str) -> str:
        # Reject pages that returned error content instead of real articles
        boilerplate_markers = ["page not found", "403 forbidden", "access denied"]
        lower_v = v.lower()
        for marker in boilerplate_markers:
            if marker in lower_v and len(v) < 500:
                raise ValueError(f"Body appears to be an error page: contains '{marker}'")
        return v

    @model_validator(mode="after")
    def compute_content_hash(self) -> "ExtractedArticle":
        # Compute a hash for deduplication across crawl runs
        raw = f"{self.url}|{self.title}|{self.body_text[:500]}"
        self.content_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return self


class IncrementalCrawlState(BaseModel):
    # Track crawl state for incremental re-crawling
    last_crawl_timestamp: datetime
    known_urls: set[str] = Field(default_factory=set)
    content_hashes: dict[str, str] = Field(default_factory=dict)

    def should_recrawl(self, url: str, new_hash: str) -> bool:
        # Only re-extract if content has changed since last crawl
        if url not in self.content_hashes:
            return True
        return self.content_hashes[url] != new_hash

    def update(self, url: str, content_hash: str) -> None:
        self.known_urls.add(url)
        self.content_hashes[url] = content_hash
        self.last_crawl_timestamp = datetime.utcnow()
```

## Handling Dynamically Loaded Content

Many sites use infinite scroll or lazy-loading, which means the data you want is not in the initial HTML. The **best practice** is to detect whether content is loaded via XHR/fetch calls and, if so, intercept those API calls directly rather than simulating scroll events.

```python
import httpx
from typing import AsyncIterator


async def paginated_api_scrape(
    base_url: str,
    params: dict[str, str],
    page_key: str = "page",
    max_pages: int = 100,
) -> AsyncIterator[dict]:
    # Directly call the internal pagination API that the frontend uses
    async with httpx.AsyncClient(timeout=30.0) as client:
        for page_num in range(1, max_pages + 1):
            params[page_key] = str(page_num)
            response = await client.get(base_url, params=params)

            if response.status_code != 200:
                break

            data = response.json()
            items = data.get("results", data.get("items", []))

            if not items:
                break

            for item in items:
                yield item
```

## Summary and Key Takeaways

- **Layer your selectors**: use CSS for simple lookups and XPath for complex traversals involving ancestors, text content matching, or positional logic.
- **Always validate extracted data** with Pydantic or dataclasses. This catches extraction failures immediately rather than polluting your data store.
- **Incremental crawling** with content hashing prevents redundant work. Track URL-to-hash mappings and only re-extract pages whose content has actually changed.
- **Intercept API calls** for dynamically loaded content rather than simulating user interactions. This is faster, more reliable, and produces cleaner structured data.
- **Fallback selectors** (comma-separated CSS or `|`-joined XPath) provide resilience against site redesigns, therefore reducing maintenance burden.
- A **common mistake** is parsing the entire page when you only need a small region. Use a container selector first to narrow the DOM subtree, then apply detailed selectors within that subtree. This approach also improves extraction speed because the parser traverses fewer nodes.
- **Schema evolution** is inevitable when scraping long-running targets. Therefore, design your Pydantic models with optional fields and version identifiers so that older records remain valid when the site adds or removes data fields. Defensive extraction with graceful degradation is always preferable to hard failures that halt your entire pipeline.
""",
    ),

    # --- 3. Anti-Bot Bypass Techniques ---
    (
        "web-scraping/anti-bot-bypass-fingerprint-evasion-ethics",
        r"""Discuss anti-bot bypass techniques for web scraping including browser fingerprint evasion methods, proxy rotation strategies and pool management, rate limiting and request throttling best practices, CAPTCHA handling strategies, and the ethical considerations and legal boundaries of automated data collection with Python examples.""",
        r"""# Anti-Bot Bypass Techniques: Fingerprinting, Proxy Rotation, Rate Limiting, CAPTCHAs, and Ethics

## Understanding the Anti-Bot Landscape

Modern websites deploy sophisticated bot detection systems -- Cloudflare Bot Management, PerimeterX, DataDome, and Akamai Bot Manager are among the most common. These systems analyze dozens of signals: TLS fingerprints, JavaScript execution patterns, mouse movements, HTTP header ordering, and behavioral patterns across requests. A **common mistake** is thinking that simply rotating User-Agent strings is sufficient to evade detection. Modern systems look far deeper than that.

However, it is critical to emphasize upfront that **ethical scraping** means respecting the site's terms of service, honoring `robots.txt`, and collecting only data you have a legitimate right to access. The techniques below are presented for educational purposes and for use cases where you have explicit authorization (your own sites, contractual agreements, or publicly available data with no restrictive ToS).

## Browser Fingerprint Evasion

Anti-bot systems build a **fingerprint** from dozens of browser properties. The goal of evasion is to make your automated browser indistinguishable from a real user's browser. This is a constant arms race, and therefore no solution is permanent.

```python
from dataclasses import dataclass, field
from typing import Optional
import random
import json

@dataclass
class BrowserFingerprint:
    # Model a realistic browser fingerprint for stealth scraping
    user_agent: str
    viewport_width: int
    viewport_height: int
    timezone: str
    locale: str
    platform: str
    webgl_vendor: str
    webgl_renderer: str
    hardware_concurrency: int
    device_memory: int
    color_depth: int = 24

    @classmethod
    def generate_realistic(cls) -> "BrowserFingerprint":
        # Generate a fingerprint that matches real-world browser distributions
        profiles = [
            {
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "platform": "Win32",
                "viewport_width": 1920,
                "viewport_height": 1080,
                "hardware_concurrency": 8,
                "device_memory": 8,
                "webgl_vendor": "Google Inc. (NVIDIA)",
                "webgl_renderer": "ANGLE (NVIDIA, GeForce GTX 1660 SUPER)",
            },
            {
                "user_agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "platform": "MacIntel",
                "viewport_width": 2560,
                "viewport_height": 1440,
                "hardware_concurrency": 10,
                "device_memory": 16,
                "webgl_vendor": "Apple",
                "webgl_renderer": "Apple M1 Pro",
            },
        ]

        profile = random.choice(profiles)
        timezones = ["America/New_York", "America/Chicago", "America/Los_Angeles",
                      "Europe/London", "Europe/Berlin"]

        return cls(
            user_agent=profile["user_agent"],
            viewport_width=profile["viewport_width"],
            viewport_height=profile["viewport_height"],
            timezone=random.choice(timezones),
            locale="en-US",
            platform=profile["platform"],
            webgl_vendor=profile["webgl_vendor"],
            webgl_renderer=profile["webgl_renderer"],
            hardware_concurrency=profile["hardware_concurrency"],
            device_memory=profile["device_memory"],
        )

    def to_playwright_context_options(self) -> dict:
        # Convert fingerprint into Playwright context configuration
        return {
            "user_agent": self.user_agent,
            "viewport": {"width": self.viewport_width, "height": self.viewport_height},
            "locale": self.locale,
            "timezone_id": self.timezone,
            "color_scheme": "light",
        }

    def to_stealth_script(self) -> str:
        # Generate JavaScript to inject that overrides detectable properties
        return f"""
        Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
        Object.defineProperty(navigator, 'platform', {{get: () => '{self.platform}'}});
        Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => {self.hardware_concurrency}}});
        Object.defineProperty(navigator, 'deviceMemory', {{get: () => {self.device_memory}}});
        """
```

The **best practice** is to maintain a pool of fingerprints drawn from real browser usage statistics (you can find these in public datasets). Each scraping session should use a consistent fingerprint -- mixing properties from different browsers is a **pitfall** that detection systems specifically look for.

## Proxy Rotation and Pool Management

Rotating IP addresses is essential for any scraping at scale. The **trade-off** is between cost and quality: datacenter proxies are cheap but easily detected, residential proxies are expensive but appear as real users, and mobile proxies are the most expensive but hardest to block.

```python
import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional
import random
import httpx

@dataclass
class ProxyInfo:
    url: str
    country: str
    proxy_type: str  # "datacenter", "residential", "mobile"
    last_used: float = 0.0
    fail_count: int = 0
    success_count: int = 0
    is_banned: bool = False

    @property
    def success_rate(self) -> float:
        total = self.fail_count + self.success_count
        return self.success_count / total if total > 0 else 1.0


class ProxyPool:
    # Manage a pool of proxies with health tracking and smart rotation

    def __init__(
        self,
        proxies: list[ProxyInfo],
        min_delay_seconds: float = 2.0,
        max_failures: int = 5,
        ban_duration_seconds: float = 300.0,
    ) -> None:
        self.proxies = proxies
        self.min_delay = min_delay_seconds
        self.max_failures = max_failures
        self.ban_duration = ban_duration_seconds
        self._lock = asyncio.Lock()

    async def get_proxy(self, target_country: Optional[str] = None) -> Optional[ProxyInfo]:
        # Select the best available proxy using weighted random selection
        async with self._lock:
            now = time.time()
            available = []

            for p in self.proxies:
                if p.is_banned and (now - p.last_used) > self.ban_duration:
                    p.is_banned = False
                    p.fail_count = 0

                if p.is_banned:
                    continue

                if target_country and p.country != target_country:
                    continue

                if (now - p.last_used) < self.min_delay:
                    continue

                available.append(p)

            if not available:
                return None

            # Weight selection by success rate -- prefer reliable proxies
            weights = [p.success_rate + 0.1 for p in available]
            selected = random.choices(available, weights=weights, k=1)[0]
            selected.last_used = now
            return selected

    async def report_result(self, proxy: ProxyInfo, success: bool) -> None:
        # Update proxy health metrics after each request
        async with self._lock:
            if success:
                proxy.success_count += 1
            else:
                proxy.fail_count += 1
                if proxy.fail_count >= self.max_failures:
                    proxy.is_banned = True

    def get_pool_stats(self) -> dict:
        active = sum(1 for p in self.proxies if not p.is_banned)
        banned = sum(1 for p in self.proxies if p.is_banned)
        avg_success = sum(p.success_rate for p in self.proxies) / len(self.proxies)
        return {"active": active, "banned": banned, "avg_success_rate": round(avg_success, 3)}
```

## Rate Limiting and Polite Request Throttling

Even with proxy rotation, sending requests too quickly is both ethically wrong and tactically counterproductive. Aggressive scraping degrades the target site's performance and triggers rate limits. The **best practice** is adaptive throttling.

```python
import asyncio
import time
from dataclasses import dataclass


@dataclass
class AdaptiveThrottler:
    # Adjust request rate based on server response signals
    base_delay: float = 1.0
    max_delay: float = 60.0
    current_delay: float = 1.0
    backoff_factor: float = 2.0
    recovery_factor: float = 0.9
    consecutive_successes: int = 0

    async def wait(self) -> None:
        # Apply the current delay before the next request
        jitter = random.uniform(0.5, 1.5)
        await asyncio.sleep(self.current_delay * jitter)

    def on_success(self) -> None:
        self.consecutive_successes += 1
        if self.consecutive_successes >= 10:
            # Gradually reduce delay after sustained success
            self.current_delay = max(
                self.base_delay,
                self.current_delay * self.recovery_factor
            )
            self.consecutive_successes = 0

    def on_rate_limited(self, retry_after: Optional[float] = None) -> None:
        # Back off exponentially on 429 or 503 responses
        self.consecutive_successes = 0
        if retry_after:
            self.current_delay = min(self.max_delay, retry_after)
        else:
            self.current_delay = min(
                self.max_delay,
                self.current_delay * self.backoff_factor
            )

    def on_captcha(self) -> None:
        # CAPTCHAs indicate aggressive detection -- slow down significantly
        self.consecutive_successes = 0
        self.current_delay = min(self.max_delay, self.current_delay * 4.0)
```

## CAPTCHA Handling Strategies

CAPTCHAs are the last line of defense in anti-bot systems. There are several approaches, each with different **trade-offs**:

1. **Avoidance** (preferred): Slow down, rotate fingerprints, and behave more like a real user so CAPTCHAs are not triggered.
2. **CAPTCHA-solving services**: Services like 2Captcha or Anti-Captcha employ human solvers. These cost $1-3 per 1000 solves and add 10-30 seconds of latency.
3. **Machine learning solvers**: For simple image CAPTCHAs, ML models can achieve 90%+ accuracy, however reCAPTCHA v3 and hCaptcha are designed to resist automated solving.

## Ethical Considerations and Legal Boundaries

This is perhaps the most important section. A **common mistake** among developers learning web scraping is ignoring the legal and ethical dimensions entirely.

**Legal frameworks to be aware of:**
- **CFAA (Computer Fraud and Abuse Act)**: In the US, accessing a computer system "without authorization" can be a federal crime. The hiQ v. LinkedIn case clarified that scraping publicly available data is generally permissible, however scraping behind a login wall without permission is risky.
- **GDPR**: In Europe, scraping personal data (names, emails, profiles) triggers GDPR obligations. You need a lawful basis for processing.
- **Terms of Service**: While ToS violations are typically civil (not criminal) matters, they can lead to lawsuits and injunctions.

**Best practices for ethical scraping:**
- Always check and respect `robots.txt`
- Identify yourself with a descriptive User-Agent string when possible
- Rate-limit requests to avoid degrading the target site
- Do not scrape personal data without a legitimate purpose
- Cache aggressively to minimize redundant requests
- Contact site owners if you plan large-scale collection

## Summary and Key Takeaways

- **Fingerprint evasion** requires consistency: every property in your browser profile must be internally coherent. Mixing Chrome user agents with Firefox WebGL renderers is an immediate red flag.
- **Proxy rotation** should use weighted selection based on success rates, with automatic banning and recovery for failed proxies.
- **Adaptive throttling** with exponential backoff on rate limits is both ethical and practical -- it keeps you under detection thresholds.
- **CAPTCHA avoidance** through behavioral mimicry is always preferable to solving. When solving is necessary, third-party human-solver services offer the best accuracy-to-cost ratio.
- **Ethics and legality** must guide every scraping project. The fact that you *can* scrape something does not mean you *should*. Therefore, always start by reading the ToS and `robots.txt`, and consider whether the data is truly public and whether your collection serves a legitimate purpose.
""",
    ),

    # --- 4. Large-Scale Crawl Architecture ---
    (
        "web-scraping/large-scale-crawl-architecture-scrapy",
        r"""Explain how to design and implement a large-scale web crawl architecture including URL frontier management with priority queues, politeness policies and domain-level throttling, distributed crawling with Scrapy and its extension points, content deduplication strategies using simhash and bloom filters, and robots.txt compliance handling in production systems.""",
        r"""# Large-Scale Crawl Architecture: URL Frontiers, Politeness, Distributed Scrapy, Deduplication, and Robots.txt

## The Complexity of Crawling at Scale

A **common mistake** when scaling a web scraper is treating it as simply "more of the same" -- running more instances of a single-URL scraper. In reality, large-scale crawling introduces fundamentally different challenges: URL frontier management (which URLs to crawl next and in what order), per-domain politeness (not overwhelming any single server), deduplication (avoiding redundant downloads), and distributed coordination (splitting work across machines without conflicts).

The architecture of a production crawler is therefore closer to a distributed systems problem than a simple scripting task. Google's original web crawler paper and the Mercator crawler design remain influential references, and frameworks like Scrapy, Heritrix, and StormCrawler implement many of these ideas.

## URL Frontier Management

The URL frontier is the core data structure of any crawler -- it is the prioritized queue of URLs waiting to be fetched. A well-designed frontier must balance three competing goals: **priority** (fetch important pages first), **politeness** (do not hit the same domain too frequently), and **freshness** (re-crawl pages that change often).

```python
import heapq
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse
from collections import defaultdict
import hashlib

@dataclass(order=True)
class CrawlRequest:
    priority: float
    url: str = field(compare=False)
    domain: str = field(compare=False)
    depth: int = field(compare=False, default=0)
    discovered_at: float = field(compare=False, default_factory=time.time)
    parent_url: Optional[str] = field(compare=False, default=None)


class URLFrontier:
    # Priority-based URL frontier with per-domain queues for politeness

    def __init__(
        self,
        max_size: int = 1_000_000,
        domain_delay: float = 2.0,
        max_depth: int = 10,
    ) -> None:
        self.max_size = max_size
        self.domain_delay = domain_delay
        self.max_depth = max_depth

        # Per-domain priority queues
        self._domain_queues: dict[str, list[CrawlRequest]] = defaultdict(list)
        # Track when each domain was last fetched
        self._domain_last_fetch: dict[str, float] = {}
        # Global set of seen URLs (use bloom filter at scale)
        self._seen_urls: set[str] = set()
        self._total_size: int = 0

    def _normalize_url(self, url: str) -> str:
        # Normalize URLs to avoid duplicate crawls of equivalent URLs
        parsed = urlparse(url)
        # Remove fragment, lowercase scheme and host
        normalized = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path}"
        if parsed.query:
            # Sort query parameters for canonical form
            params = sorted(parsed.query.split("&"))
            normalized += "?" + "&".join(params)
        return normalized

    def add_url(
        self, url: str, priority: float = 0.5, depth: int = 0, parent: Optional[str] = None
    ) -> bool:
        # Add a URL to the frontier if not already seen
        if self._total_size >= self.max_size:
            return False

        if depth > self.max_depth:
            return False

        normalized = self._normalize_url(url)
        if normalized in self._seen_urls:
            return False

        self._seen_urls.add(normalized)
        domain = urlparse(normalized).netloc
        request = CrawlRequest(
            priority=-priority,  # negative because heapq is a min-heap
            url=normalized,
            domain=domain,
            depth=depth,
            parent_url=parent,
        )
        heapq.heappush(self._domain_queues[domain], request)
        self._total_size += 1
        return True

    def get_next(self) -> Optional[CrawlRequest]:
        # Return the highest-priority URL from a domain that is not on cooldown
        now = time.time()
        best: Optional[CrawlRequest] = None
        best_domain: Optional[str] = None

        for domain, queue in self._domain_queues.items():
            if not queue:
                continue

            last_fetch = self._domain_last_fetch.get(domain, 0.0)
            if (now - last_fetch) < self.domain_delay:
                continue  # Domain is on cooldown -- respect politeness

            candidate = queue[0]
            if best is None or candidate.priority < best.priority:
                best = candidate
                best_domain = domain

        if best and best_domain:
            heapq.heappop(self._domain_queues[best_domain])
            self._domain_last_fetch[best_domain] = now
            self._total_size -= 1
            return best

        return None

    def stats(self) -> dict:
        return {
            "total_queued": self._total_size,
            "domains_active": sum(1 for q in self._domain_queues.values() if q),
            "urls_seen": len(self._seen_urls),
        }
```

The **best practice** for frontier management at true web scale (millions of URLs) is to replace the in-memory `set` with a **Bloom filter** for the seen-URL check and use a persistent queue (Redis sorted sets or RocksDB) for the domain queues. However, the architecture remains the same.

## Politeness Policies and Domain-Level Throttling

Politeness is not just an ethical obligation -- it is a practical necessity. Hammering a single server will get your IP banned, waste your proxy budget, and potentially cause legal issues. A well-designed politeness policy enforces per-domain rate limits derived from multiple signals.

```python
from dataclasses import dataclass
from typing import Optional
import time
from urllib.robotparser import RobotFileParser


@dataclass
class PolitenessPolicy:
    # Enforce per-domain rate limits using robots.txt and adaptive signals
    default_delay: float = 2.0
    max_delay: float = 30.0
    min_delay: float = 0.5

    def get_crawl_delay(
        self,
        domain: str,
        robots_parser: Optional[RobotFileParser] = None,
        avg_response_time: float = 0.5,
    ) -> float:
        # Determine the appropriate delay for a domain
        delay = self.default_delay

        # Respect Crawl-delay from robots.txt if present
        if robots_parser:
            robots_delay = robots_parser.crawl_delay("*")
            if robots_delay:
                delay = max(delay, float(robots_delay))

        # Adaptive: if the server is slow, back off further
        # because a slow response often indicates server strain
        if avg_response_time > 2.0:
            delay = max(delay, avg_response_time * 3)

        return min(max(delay, self.min_delay), self.max_delay)


class RobotsChecker:
    # Cache and check robots.txt for multiple domains

    def __init__(self, user_agent: str = "MyBot/1.0") -> None:
        self.user_agent = user_agent
        self._cache: dict[str, RobotFileParser] = {}

    def is_allowed(self, url: str) -> bool:
        # Check if the URL is allowed by the domain's robots.txt
        domain = urlparse(url).netloc
        if domain not in self._cache:
            parser = RobotFileParser()
            robots_url = f"https://{domain}/robots.txt"
            try:
                parser.set_url(robots_url)
                parser.read()
            except Exception:
                # If robots.txt is unavailable, assume allowed
                return True
            self._cache[domain] = parser

        return self._cache[domain].can_fetch(self.user_agent, url)
```

## Distributed Crawling with Scrapy

Scrapy is the most mature Python crawling framework, and its middleware and extension architecture makes it ideal for building distributed crawlers. The **trade-off** with Scrapy is that its Twisted-based async model has a learning curve, however the ecosystem of extensions (scrapy-redis, scrapy-splash, scrapy-playwright) compensates for this.

```python
import scrapy
from scrapy import signals
from scrapy.http import Request, Response
from scrapy.exceptions import IgnoreRequest
from typing import Any, Iterator
import hashlib
import json


class ProductSpider(scrapy.Spider):
    name = "product_spider"
    custom_settings = {
        "CONCURRENT_REQUESTS": 16,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "DOWNLOAD_DELAY": 1.5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 2.0,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 4.0,
        "ROBOTSTXT_OBEY": True,
        "HTTPCACHE_ENABLED": True,
        "HTTPCACHE_EXPIRATION_SECS": 86400,
    }

    def start_requests(self) -> Iterator[Request]:
        # Seed URLs loaded from a frontier or configuration
        seed_urls = [
            "https://example.com/products?page=1",
            "https://example.com/products?page=2",
        ]
        for url in seed_urls:
            yield scrapy.Request(url, callback=self.parse_listing, priority=10)

    def parse_listing(self, response: Response) -> Iterator[Any]:
        # Extract product links from listing pages
        for link in response.css("a.product-card::attr(href)").getall():
            yield response.follow(link, callback=self.parse_product, priority=5)

        # Follow pagination
        next_page = response.css("a.next-page::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse_listing, priority=8)

    def parse_product(self, response: Response) -> Iterator[dict]:
        yield {
            "url": response.url,
            "title": response.css("h1::text").get("").strip(),
            "price": response.css("span.price::text").get("").strip(),
            "description": " ".join(response.css("div.description ::text").getall()).strip(),
            "content_hash": hashlib.md5(response.body).hexdigest(),
        }
```

## Content Deduplication with SimHash

At scale, you will encounter duplicate and near-duplicate pages (pagination variants, URL parameters that do not change content, mirror sites). **Exact deduplication** with MD5/SHA256 catches identical pages, but **near-duplicate detection** requires locality-sensitive hashing. SimHash is the classic approach.

```python
from typing import Sequence
import hashlib
import re


def tokenize(text: str) -> list[str]:
    # Simple word-level tokenization with normalization
    return re.findall(r"\w+", text.lower())


def simhash(tokens: Sequence[str], hash_bits: int = 64) -> int:
    # Compute a SimHash fingerprint for near-duplicate detection
    v = [0] * hash_bits

    for token in tokens:
        token_hash = int(hashlib.md5(token.encode()).hexdigest(), 16)
        for i in range(hash_bits):
            if token_hash & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(hash_bits):
        if v[i] > 0:
            fingerprint |= (1 << i)

    return fingerprint


def hamming_distance(hash1: int, hash2: int) -> int:
    # Count differing bits between two SimHash fingerprints
    xor = hash1 ^ hash2
    return bin(xor).count("1")


class DuplicateDetector:
    # Detect exact and near-duplicate documents
    def __init__(self, near_dup_threshold: int = 3) -> None:
        self.threshold = near_dup_threshold
        self._exact_hashes: set[str] = set()
        self._simhashes: list[tuple[int, str]] = []

    def is_duplicate(self, url: str, content: str) -> bool:
        # Check for exact hash match first, then near-duplicate
        exact_hash = hashlib.sha256(content.encode()).hexdigest()
        if exact_hash in self._exact_hashes:
            return True
        self._exact_hashes.add(exact_hash)

        tokens = tokenize(content)
        if len(tokens) < 20:
            return False

        content_simhash = simhash(tokens)
        for existing_hash, existing_url in self._simhashes:
            if hamming_distance(content_simhash, existing_hash) <= self.threshold:
                return True

        self._simhashes.append((content_simhash, url))
        return False
```

## Summary and Key Takeaways

- **URL frontiers** must balance priority, politeness, and freshness. Use per-domain queues with cooldown timers to enforce rate limits at the domain level.
- **Politeness policies** should respect `robots.txt` Crawl-delay directives and adaptively increase delays when servers respond slowly, because this indicates strain.
- **Scrapy** is the **best practice** framework for Python-based crawling at scale. Its `AUTOTHROTTLE`, `ROBOTSTXT_OBEY`, and `HTTPCACHE` settings provide production-ready politeness and efficiency out of the box.
- **Deduplication** requires both exact matching (SHA256) and near-duplicate detection (SimHash with Hamming distance). A **pitfall** is relying solely on URL deduplication, which misses content served at different URLs.
- For truly distributed crawling, use **scrapy-redis** to share the URL frontier across multiple Scrapy instances, with Redis sorted sets providing both deduplication and priority ordering.
- The overall **trade-off** in crawl architecture is between throughput and politeness. Aggressive crawling maximizes data collection speed but risks bans, legal action, and harm to target sites. Therefore, always err on the side of being too polite rather than too aggressive.
""",
    ),

    # --- 5. Data Pipeline from Web to Knowledge Graph ---
    (
        "web-scraping/web-data-to-knowledge-graph-pipeline",
        r"""Explain how to build a complete data pipeline that transforms raw scraped web data into a knowledge graph, covering named entity extraction using spaCy and transformer models, relationship detection and triple extraction, schema mapping to ontologies like Schema.org, quality scoring and confidence metrics for extracted facts, and incremental update strategies for maintaining a living knowledge graph with Python examples.""",
        r"""# Data Pipeline from Web to Knowledge Graph: Entity Extraction, Relationship Detection, Schema Mapping, and Quality Scoring

## Why Build a Knowledge Graph from Web Data

Raw scraped web data is a collection of unstructured text, HTML fragments, and metadata -- useful for search indexing but limited for reasoning, question answering, or data integration. A **knowledge graph** transforms this raw material into a structured network of entities and relationships that can be queried, reasoned over, and merged with other data sources.

The **trade-off** is significant: building a knowledge graph from noisy web data requires substantial NLP infrastructure and careful quality management. However, the resulting structured representation enables capabilities that are impossible with raw text -- semantic search, multi-hop question answering, entity disambiguation, and automated fact-checking.

A **common mistake** is treating knowledge graph construction as a one-shot batch process. In reality, the web changes constantly, and your graph must be maintained with incremental updates, conflict resolution, and confidence decay over time.

## Named Entity Extraction

The first pipeline stage identifies **entities** -- the nouns of your knowledge graph. People, organizations, locations, products, dates, and domain-specific concepts must be detected in raw text and normalized to canonical forms.

```python
import spacy
from spacy.tokens import Doc, Span
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import hashlib


class EntityType(str, Enum):
    PERSON = "PERSON"
    ORGANIZATION = "ORG"
    LOCATION = "GPE"
    PRODUCT = "PRODUCT"
    DATE = "DATE"
    TECHNOLOGY = "TECHNOLOGY"
    CONCEPT = "CONCEPT"


@dataclass
class ExtractedEntity:
    text: str
    canonical_name: str
    entity_type: EntityType
    confidence: float
    source_url: str
    context_sentence: str
    entity_id: str = ""

    def __post_init__(self) -> None:
        # Generate a stable ID from the canonical name and type
        raw = f"{self.entity_type.value}:{self.canonical_name.lower()}"
        self.entity_id = hashlib.sha256(raw.encode()).hexdigest()[:12]


class EntityExtractor:
    # Extract and normalize named entities from scraped text

    def __init__(self, model_name: str = "en_core_web_trf") -> None:
        self.nlp = spacy.load(model_name)
        # Custom entity normalization rules
        self._canonical_map: dict[str, str] = {
            "google llc": "Google",
            "alphabet inc": "Google",
            "microsoft corporation": "Microsoft",
            "microsoft corp": "Microsoft",
            "amazon.com inc": "Amazon",
            "meta platforms": "Meta",
            "facebook inc": "Meta",
        }

    def _normalize_entity(self, text: str, entity_type: str) -> str:
        # Map variant names to canonical forms
        lower = text.lower().strip()
        if lower in self._canonical_map:
            return self._canonical_map[lower]
        # Default: title-case for organizations and persons
        if entity_type in ("ORG", "PERSON"):
            return text.strip().title()
        return text.strip()

    def _spacy_to_entity_type(self, label: str) -> Optional[EntityType]:
        # Map spaCy labels to our entity type enum
        mapping = {
            "PERSON": EntityType.PERSON,
            "ORG": EntityType.ORGANIZATION,
            "GPE": EntityType.LOCATION,
            "LOC": EntityType.LOCATION,
            "PRODUCT": EntityType.PRODUCT,
            "DATE": EntityType.DATE,
        }
        return mapping.get(label)

    def extract(self, text: str, source_url: str) -> list[ExtractedEntity]:
        # Run NER on text and produce normalized entities
        doc: Doc = self.nlp(text)
        entities: list[ExtractedEntity] = []

        for ent in doc.ents:
            entity_type = self._spacy_to_entity_type(ent.label_)
            if entity_type is None:
                continue

            # Find the containing sentence for context
            sentence = ""
            for sent in doc.sents:
                if ent.start >= sent.start and ent.end <= sent.end:
                    sentence = sent.text.strip()
                    break

            canonical = self._normalize_entity(ent.text, ent.label_)

            entities.append(ExtractedEntity(
                text=ent.text,
                canonical_name=canonical,
                entity_type=entity_type,
                confidence=0.85,  # spaCy trf models typically achieve this accuracy
                source_url=source_url,
                context_sentence=sentence,
            ))

        return entities
```

The **best practice** is to use a transformer-based spaCy model (`en_core_web_trf`) for entity extraction because it achieves significantly higher accuracy than the statistical models. However, the trade-off is speed: the transformer model processes text roughly 10x slower than `en_core_web_sm`.

## Relationship Detection and Triple Extraction

Once entities are identified, the next stage extracts **relationships** between them -- the verbs and predicates of your knowledge graph. Each relationship is represented as a triple: (subject, predicate, object).

```python
from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class KnowledgeTriple:
    subject: ExtractedEntity
    predicate: str
    object_entity: ExtractedEntity
    confidence: float
    evidence_sentence: str
    source_url: str

    def to_dict(self) -> dict:
        return {
            "subject_id": self.subject.entity_id,
            "subject_name": self.subject.canonical_name,
            "predicate": self.predicate,
            "object_id": self.object_entity.entity_id,
            "object_name": self.object_entity.canonical_name,
            "confidence": self.confidence,
            "evidence": self.evidence_sentence,
            "source": self.source_url,
        }


class RelationExtractor:
    # Extract relationships between entities in the same sentence

    # Dependency-based patterns for common relationships
    RELATION_PATTERNS: list[dict] = [
        {"dep_path": ["nsubj", "ROOT", "dobj"], "predicate": "acts_on"},
        {"dep_path": ["nsubj", "ROOT", "attr"], "predicate": "is_a"},
        {"dep_path": ["nsubj", "ROOT", "prep", "pobj"], "predicate": "related_to"},
    ]

    VERB_TO_PREDICATE: dict[str, str] = {
        "acquire": "acquired",
        "acquires": "acquired",
        "acquired": "acquired",
        "found": "founded",
        "founded": "founded",
        "lead": "leads",
        "leads": "leads",
        "develop": "develops",
        "develops": "develops",
        "headquartered": "headquartered_in",
        "located": "located_in",
        "partner": "partners_with",
        "invest": "invested_in",
    }

    def __init__(self, nlp) -> None:
        self.nlp = nlp

    def extract_from_sentence(
        self,
        sentence: str,
        entities: list[ExtractedEntity],
        source_url: str,
    ) -> list[KnowledgeTriple]:
        # Find entity pairs in the same sentence and determine their relationship
        doc = self.nlp(sentence)
        triples: list[KnowledgeTriple] = []

        # Build entity span lookup
        entity_spans: list[tuple[ExtractedEntity, int, int]] = []
        for entity in entities:
            start_idx = sentence.lower().find(entity.text.lower())
            if start_idx >= 0:
                entity_spans.append((entity, start_idx, start_idx + len(entity.text)))

        # For each pair of entities, look for a connecting verb
        for i, (ent_a, start_a, end_a) in enumerate(entity_spans):
            for j, (ent_b, start_b, end_b) in enumerate(entity_spans):
                if i >= j:
                    continue

                # Find verb tokens between the two entities
                between_start = min(end_a, end_b)
                between_end = max(start_a, start_b)
                between_text = sentence[between_start:between_end].lower().strip()

                predicate = self._identify_predicate(between_text, doc)
                if predicate:
                    triples.append(KnowledgeTriple(
                        subject=ent_a,
                        predicate=predicate,
                        object_entity=ent_b,
                        confidence=0.7,
                        evidence_sentence=sentence,
                        source_url=source_url,
                    ))

        return triples

    def _identify_predicate(self, text: str, doc: Doc) -> Optional[str]:
        # Match verb text against known predicate patterns
        words = text.split()
        for word in words:
            lemma = word.strip(".,;:")
            if lemma in self.VERB_TO_PREDICATE:
                return self.VERB_TO_PREDICATE[lemma]
        return None
```

A **pitfall** in relationship extraction is over-extraction: generating triples for every pair of co-occurring entities regardless of whether a meaningful relationship exists. The confidence score is therefore critical for downstream filtering.

## Schema Mapping to Ontologies

Raw triples use ad-hoc predicate names. To make your knowledge graph interoperable and queryable, you must map entities and predicates to a formal ontology like **Schema.org**, **Wikidata properties**, or a domain-specific schema.

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OntologyMapping:
    # Map extracted predicates and entity types to Schema.org vocabulary
    predicate_map: dict[str, str] = field(default_factory=lambda: {
        "acquired": "schema:acquiredFrom",
        "founded": "schema:foundingDate",
        "headquartered_in": "schema:location",
        "located_in": "schema:containedInPlace",
        "leads": "schema:employee",
        "develops": "schema:creator",
        "partners_with": "schema:sponsor",
        "invested_in": "schema:funder",
        "is_a": "rdf:type",
    })

    entity_type_map: dict[str, str] = field(default_factory=lambda: {
        "PERSON": "schema:Person",
        "ORG": "schema:Organization",
        "GPE": "schema:Place",
        "PRODUCT": "schema:Product",
        "TECHNOLOGY": "schema:SoftwareApplication",
    })

    def map_triple(self, triple: KnowledgeTriple) -> dict:
        # Convert a raw triple into Schema.org-compatible JSON-LD
        predicate = self.predicate_map.get(triple.predicate, f"custom:{triple.predicate}")
        subj_type = self.entity_type_map.get(
            triple.subject.entity_type.value, "schema:Thing"
        )
        obj_type = self.entity_type_map.get(
            triple.object_entity.entity_type.value, "schema:Thing"
        )

        return {
            "@context": "https://schema.org",
            "@type": "Statement",
            "subject": {
                "@type": subj_type,
                "@id": f"entity:{triple.subject.entity_id}",
                "name": triple.subject.canonical_name,
            },
            "predicate": predicate,
            "object": {
                "@type": obj_type,
                "@id": f"entity:{triple.object_entity.entity_id}",
                "name": triple.object_entity.canonical_name,
            },
            "confidence": triple.confidence,
            "evidence": triple.evidence_sentence,
            "source": triple.source_url,
        }
```

## Quality Scoring and Confidence Metrics

Not all extracted facts are equally reliable. A **best practice** is to assign multi-dimensional quality scores that account for source reliability, extraction confidence, corroboration across sources, and recency.

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
import math


@dataclass
class QualityScore:
    # Multi-factor quality score for knowledge graph facts
    extraction_confidence: float  # NLP model confidence
    source_authority: float       # Domain authority of the source
    corroboration_count: int      # Number of independent sources confirming the fact
    freshness_days: int           # Days since the fact was last confirmed

    @property
    def composite_score(self) -> float:
        # Weighted composite of all quality dimensions
        corroboration_factor = min(1.0, math.log2(self.corroboration_count + 1) / 3)
        freshness_decay = math.exp(-self.freshness_days / 365.0)

        score = (
            0.30 * self.extraction_confidence
            + 0.25 * self.source_authority
            + 0.25 * corroboration_factor
            + 0.20 * freshness_decay
        )
        return round(min(1.0, max(0.0, score)), 4)

    @property
    def is_reliable(self) -> bool:
        # A fact is considered reliable if its composite score exceeds a threshold
        return self.composite_score >= 0.6


class IncrementalGraphUpdater:
    # Maintain a living knowledge graph with conflict resolution

    def __init__(self) -> None:
        # In production, this would be a graph database (Neo4j, Amazon Neptune)
        self._triples: dict[str, dict] = {}  # keyed by (subj_id, pred, obj_id)
        self._entity_registry: dict[str, dict] = {}

    def _triple_key(self, triple: KnowledgeTriple) -> str:
        return f"{triple.subject.entity_id}|{triple.predicate}|{triple.object_entity.entity_id}"

    def upsert_triple(
        self, triple: KnowledgeTriple, quality: QualityScore
    ) -> str:
        # Insert or update a triple, keeping the highest-quality version
        key = self._triple_key(triple)

        if key in self._triples:
            existing = self._triples[key]
            existing_score = existing["quality"].composite_score

            if quality.composite_score > existing_score:
                # New evidence is higher quality -- update
                self._triples[key] = {
                    "triple": triple.to_dict(),
                    "quality": quality,
                    "updated_at": datetime.utcnow().isoformat(),
                    "version": existing.get("version", 1) + 1,
                }
                return "updated"
            else:
                # Increment corroboration even if not replacing
                existing["quality"].corroboration_count += 1
                return "corroborated"
        else:
            self._triples[key] = {
                "triple": triple.to_dict(),
                "quality": quality,
                "updated_at": datetime.utcnow().isoformat(),
                "version": 1,
            }
            return "inserted"

    def decay_stale_facts(self, max_age_days: int = 180) -> int:
        # Remove or flag facts that have not been re-confirmed recently
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        removed = 0
        keys_to_remove = []

        for key, record in self._triples.items():
            updated = datetime.fromisoformat(record["updated_at"])
            if updated < cutoff and record["quality"].composite_score < 0.4:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._triples[key]
            removed += 1

        return removed

    def get_stats(self) -> dict:
        total = len(self._triples)
        reliable = sum(
            1 for r in self._triples.values() if r["quality"].is_reliable
        )
        return {
            "total_triples": total,
            "reliable_triples": reliable,
            "entities": len(self._entity_registry),
            "reliability_ratio": round(reliable / total, 3) if total else 0,
        }
```

## Summary and Key Takeaways

- **Entity extraction** is the foundation of your knowledge graph. Use transformer-based NER models for accuracy and maintain a canonical name registry to merge variant mentions of the same entity.
- **Relationship extraction** should be conservative. It is better to miss a true relationship than to assert a false one, therefore set confidence thresholds aggressively and corroborate across multiple sources.
- **Schema mapping** to standard ontologies (Schema.org, Wikidata) makes your graph interoperable. A **common mistake** is inventing ad-hoc predicates that no downstream consumer can interpret.
- **Quality scoring** must be multi-dimensional: combine extraction confidence, source authority, cross-source corroboration, and temporal freshness into a composite score. Facts below the reliability threshold should be quarantined, not deleted.
- **Incremental updates** with conflict resolution and freshness decay keep your graph alive. The **best practice** is to treat the graph as an append-mostly data structure where new evidence either corroborates or supersedes existing facts.
- The overall **pitfall** to avoid is building a knowledge graph without a clear query use case. Start with the questions you want to answer, then design the schema and extraction pipeline to support those queries. A graph with perfect entity extraction but irrelevant predicates is useless.
""",
    ),
]
