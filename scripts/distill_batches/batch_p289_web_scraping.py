"""Web scraping — Playwright automation, anti-detection, rate limiting, data extraction, headless browsers."""

PAIRS = [
    (
        "web-scraping/playwright-automation",
        "Build a production-grade web scraping framework using Playwright with page object model, automatic retries, session management, and structured data extraction.",
        '''Production web scraping framework with Playwright:

```python
"""Playwright scraping framework — page objects, retries, extraction."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generic, TypeVar
from urllib.parse import urljoin, urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response,
    async_playwright,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ============================================================
# 1. Configuration and session management
# ============================================================

@dataclass
class ScraperConfig:
    """Scraper configuration with sensible defaults."""
    headless: bool = True
    browser_type: str = "chromium"  # chromium, firefox, webkit
    viewport_width: int = 1920
    viewport_height: int = 1080
    user_agent: str | None = None
    proxy: str | None = None
    timeout_ms: int = 30_000
    retry_count: int = 3
    retry_delay_ms: int = 2_000
    rate_limit_per_second: float = 2.0
    screenshot_on_error: bool = True
    screenshot_dir: Path = Path("./screenshots")
    cookies_file: Path | None = None
    block_resources: list[str] = field(
        default_factory=lambda: ["image", "media", "font"]
    )


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
]


class BrowserManager:
    """Manages browser lifecycle, contexts, and session persistence."""

    def __init__(self, config: ScraperConfig) -> None:
        self.config = config
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> "BrowserManager":
        self._playwright = await async_playwright().start()

        launch_kwargs: dict[str, Any] = {
            "headless": self.config.headless,
        }
        if self.config.proxy:
            launch_kwargs["proxy"] = {"server": self.config.proxy}

        browser_factory = getattr(self._playwright, self.config.browser_type)
        self._browser = await browser_factory.launch(**launch_kwargs)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_context(self) -> BrowserContext:
        """Create a new browser context with anti-detection settings."""
        assert self._browser is not None

        user_agent = self.config.user_agent or random.choice(USER_AGENTS)

        context = await self._browser.new_context(
            viewport={"width": self.config.viewport_width,
                       "height": self.config.viewport_height},
            user_agent=user_agent,
            locale="en-US",
            timezone_id="America/New_York",
            geolocation={"latitude": 40.7128, "longitude": -74.0060},
            permissions=["geolocation"],
            java_script_enabled=True,
        )

        # Block unnecessary resources
        if self.config.block_resources:
            await context.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in self.config.block_resources
                    else route.continue_()
                ),
            )

        # Load saved cookies
        if self.config.cookies_file and self.config.cookies_file.exists():
            cookies = json.loads(self.config.cookies_file.read_text())
            await context.add_cookies(cookies)

        return context

    async def save_cookies(self, context: BrowserContext) -> None:
        """Persist cookies for session reuse."""
        if self.config.cookies_file:
            cookies = await context.cookies()
            self.config.cookies_file.parent.mkdir(parents=True, exist_ok=True)
            self.config.cookies_file.write_text(json.dumps(cookies, indent=2))


# ============================================================
# 2. Rate limiter
# ============================================================

class RateLimiter:
    """Token bucket rate limiter for polite scraping."""

    def __init__(self, rate_per_second: float, burst: int = 1) -> None:
        self._rate = rate_per_second
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._rate
                # Add jitter to avoid thundering herd
                wait += random.uniform(0, 0.1)
                await asyncio.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


# ============================================================
# 3. Page Object Model
# ============================================================

class BasePage(ABC):
    """Base page object with common navigation and extraction helpers."""

    def __init__(self, page: Page, rate_limiter: RateLimiter) -> None:
        self.page = page
        self._rate_limiter = rate_limiter

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> Response | None:
        """Navigate with rate limiting and retry logic."""
        await self._rate_limiter.acquire()
        logger.info("Navigating to: %s", url)
        return await self.page.goto(url, wait_until=wait_until)

    async def wait_and_click(self, selector: str, timeout: int = 10_000) -> None:
        await self.page.wait_for_selector(selector, timeout=timeout)
        await self.page.click(selector)

    async def extract_text(self, selector: str, default: str = "") -> str:
        el = await self.page.query_selector(selector)
        if el:
            return (await el.inner_text()).strip()
        return default

    async def extract_texts(self, selector: str) -> list[str]:
        elements = await self.page.query_selector_all(selector)
        return [
            (await el.inner_text()).strip()
            for el in elements
        ]

    async def extract_attribute(self, selector: str, attr: str) -> str | None:
        el = await self.page.query_selector(selector)
        if el:
            return await el.get_attribute(attr)
        return None

    async def extract_all_attributes(self, selector: str, attr: str) -> list[str]:
        elements = await self.page.query_selector_all(selector)
        results = []
        for el in elements:
            value = await el.get_attribute(attr)
            if value:
                results.append(value)
        return results

    async def scroll_to_bottom(self, step: int = 500, delay: float = 0.5) -> None:
        """Scroll page incrementally to trigger lazy loading."""
        previous_height = 0
        while True:
            current_height = await self.page.evaluate("document.body.scrollHeight")
            if current_height == previous_height:
                break
            previous_height = current_height
            await self.page.evaluate(f"window.scrollBy(0, {step})")
            await asyncio.sleep(delay)

    async def screenshot(self, name: str, path: Path = Path("./screenshots")) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        filepath = path / f"{name}_{int(time.time())}.png"
        await self.page.screenshot(path=str(filepath), full_page=True)
        return filepath


# ============================================================
# 4. Concrete page objects for a job board scraper
# ============================================================

@dataclass
class JobListing:
    title: str
    company: str
    location: str
    salary: str | None
    url: str
    posted_date: str
    description: str = ""
    tags: list[str] = field(default_factory=list)


class SearchPage(BasePage):
    """Job search results page."""

    URL = "https://jobs.example.com/search"

    async def search(self, query: str, location: str = "") -> None:
        await self.navigate(self.URL)
        await self.page.fill("#search-input", query)
        if location:
            await self.page.fill("#location-input", location)
        await self.page.click("#search-button")
        await self.page.wait_for_selector(".job-card", timeout=15_000)

    async def get_listings(self) -> list[JobListing]:
        """Extract all job listings from current page."""
        cards = await self.page.query_selector_all(".job-card")
        listings = []

        for card in cards:
            title = await card.query_selector(".job-title")
            company = await card.query_selector(".company-name")
            location = await card.query_selector(".location")
            salary = await card.query_selector(".salary")
            link = await card.query_selector("a.job-link")
            date = await card.query_selector(".posted-date")
            tag_els = await card.query_selector_all(".tag")

            listings.append(JobListing(
                title=(await title.inner_text()).strip() if title else "",
                company=(await company.inner_text()).strip() if company else "",
                location=(await location.inner_text()).strip() if location else "",
                salary=(await salary.inner_text()).strip() if salary else None,
                url=await link.get_attribute("href") if link else "",
                posted_date=(await date.inner_text()).strip() if date else "",
                tags=[(await t.inner_text()).strip() for t in tag_els],
            ))

        return listings

    async def has_next_page(self) -> bool:
        btn = await self.page.query_selector(".pagination .next:not(.disabled)")
        return btn is not None

    async def go_next_page(self) -> None:
        await self._rate_limiter.acquire()
        await self.wait_and_click(".pagination .next")
        await self.page.wait_for_selector(".job-card", timeout=15_000)


class JobDetailPage(BasePage):
    """Individual job detail page."""

    async def load(self, url: str) -> None:
        await self.navigate(url)
        await self.page.wait_for_selector(".job-detail", timeout=15_000)

    async def get_full_description(self) -> str:
        return await self.extract_text(".job-description")

    async def get_requirements(self) -> list[str]:
        return await self.extract_texts(".requirements li")

    async def get_benefits(self) -> list[str]:
        return await self.extract_texts(".benefits li")


# ============================================================
# 5. Orchestrator with retry and error handling
# ============================================================

class JobScraper:
    """Orchestrates the scraping pipeline."""

    def __init__(self, config: ScraperConfig) -> None:
        self.config = config
        self._rate_limiter = RateLimiter(config.rate_limit_per_second)

    async def scrape_jobs(
        self,
        query: str,
        location: str = "",
        max_pages: int = 10,
    ) -> AsyncIterator[JobListing]:
        """Scrape job listings with pagination."""
        async with BrowserManager(self.config) as manager:
            context = await manager.new_context()
            page = await context.new_page()

            search = SearchPage(page, self._rate_limiter)
            detail = JobDetailPage(page, self._rate_limiter)

            await search.search(query, location)

            for page_num in range(max_pages):
                logger.info("Scraping page %d", page_num + 1)
                listings = await self._retry(search.get_listings)

                for listing in listings:
                    # Optionally fetch full description
                    try:
                        detail_page = await context.new_page()
                        detail_obj = JobDetailPage(detail_page, self._rate_limiter)
                        await detail_obj.load(listing.url)
                        listing.description = await detail_obj.get_full_description()
                        await detail_page.close()
                    except Exception as exc:
                        logger.warning("Failed to get detail for %s: %s", listing.url, exc)

                    yield listing

                if not await search.has_next_page():
                    break
                await search.go_next_page()

            await manager.save_cookies(context)

    async def _retry(self, fn, *args, **kwargs) -> Any:
        """Retry with exponential backoff."""
        last_exc = None
        for attempt in range(1, self.config.retry_count + 1):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                delay = (self.config.retry_delay_ms / 1000) * (2 ** (attempt - 1))
                logger.warning("Attempt %d failed: %s. Retrying in %.1fs",
                              attempt, exc, delay)
                await asyncio.sleep(delay)
        raise last_exc  # type: ignore


# Usage
async def main() -> None:
    config = ScraperConfig(
        headless=True,
        rate_limit_per_second=1.0,
        cookies_file=Path("./cookies.json"),
    )

    scraper = JobScraper(config)
    results = []

    async for job in scraper.scrape_jobs("python developer", "remote", max_pages=5):
        results.append(job)
        logger.info("Found: %s at %s", job.title, job.company)

    # Export results
    Path("jobs.json").write_text(
        json.dumps([vars(j) for j in results], indent=2, default=str)
    )

asyncio.run(main())
```

**Architecture patterns:**

| Pattern | Implementation | Benefit |
|---------|---------------|---------|
| Page Object Model | `BasePage` / `SearchPage` / `DetailPage` | Maintainable selectors |
| Rate limiting | Token bucket with jitter | Polite, avoid bans |
| Session persistence | Cookie save/restore | Resume sessions |
| Resource blocking | Route interception | Faster page loads |
| Retry with backoff | Exponential delay | Handle transient failures |
| Async generators | `AsyncIterator[T]` | Stream results, low memory |

**Best practices:**
- Always respect `robots.txt` and rate limit to 1-2 req/sec
- Use the Page Object Model to isolate CSS selectors from business logic
- Block images/fonts/media to reduce bandwidth and speed up scraping
- Save cookies between runs for authenticated sessions
- Take screenshots on error for debugging selector changes
- Use `wait_for_selector` instead of arbitrary `sleep()` calls'''
    ),
    (
        "web-scraping/anti-detection-stealth",
        "Show techniques for making Playwright scraping resistant to bot detection, including fingerprint randomization, browser profile emulation, and human-like interaction patterns.",
        '''Anti-detection techniques for Playwright scraping:

```python
"""Anti-detection — stealth mode, fingerprint randomization, human behavior."""

from __future__ import annotations

import asyncio
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright


# ============================================================
# 1. Stealth configuration — evade common detections
# ============================================================

STEALTH_SCRIPTS = [
    # Override navigator.webdriver
    """
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });
    """,

    # Override chrome runtime
    """
    window.chrome = {
        runtime: {
            connect: () => {},
            sendMessage: () => {},
        },
        loadTimes: () => {},
        csi: () => {},
    };
    """,

    # Realistic plugins
    """
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' },
        ],
    });
    """,

    # Override permissions
    """
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters);
    """,

    # Realistic language settings
    """
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en', 'es'],
    });
    """,

    # WebGL vendor and renderer
    """
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter.call(this, parameter);
    };
    """,

    # Realistic screen dimensions
    """
    Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
    Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
    """,
]


async def apply_stealth(context: BrowserContext) -> None:
    """Apply all stealth patches to a browser context."""
    for script in STEALTH_SCRIPTS:
        await context.add_init_script(script)


# ============================================================
# 2. Human-like mouse movement (Bezier curves)
# ============================================================

def bezier_curve(
    start: tuple[float, float],
    end: tuple[float, float],
    control1: tuple[float, float] | None = None,
    control2: tuple[float, float] | None = None,
    steps: int = 50,
) -> list[tuple[float, float]]:
    """Generate points along a cubic Bezier curve for natural mouse movement."""
    if control1 is None:
        # Random control points for natural-looking curves
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        control1 = (
            start[0] + dx * random.uniform(0.2, 0.4) + random.uniform(-50, 50),
            start[1] + dy * random.uniform(0.2, 0.4) + random.uniform(-50, 50),
        )
    if control2 is None:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        control2 = (
            start[0] + dx * random.uniform(0.6, 0.8) + random.uniform(-50, 50),
            start[1] + dy * random.uniform(0.6, 0.8) + random.uniform(-50, 50),
        )

    points = []
    for i in range(steps + 1):
        t = i / steps
        t2 = t * t
        t3 = t2 * t
        mt = 1 - t
        mt2 = mt * mt
        mt3 = mt2 * mt

        x = mt3 * start[0] + 3 * mt2 * t * control1[0] + 3 * mt * t2 * control2[0] + t3 * end[0]
        y = mt3 * start[1] + 3 * mt2 * t * control1[1] + 3 * mt * t2 * control2[1] + t3 * end[1]
        points.append((x, y))

    return points


async def human_move_to(page: Page, x: float, y: float) -> None:
    """Move mouse to target using Bezier curve path."""
    # Get current mouse position (approximate from last known)
    start_x = random.uniform(100, 500)
    start_y = random.uniform(100, 400)

    points = bezier_curve((start_x, start_y), (x, y), steps=random.randint(30, 60))

    for px, py in points:
        await page.mouse.move(px, py)
        # Variable delay between points (faster in middle, slower at edges)
        await asyncio.sleep(random.uniform(0.001, 0.008))


async def human_click(page: Page, selector: str) -> None:
    """Click element with human-like mouse movement and timing."""
    element = await page.wait_for_selector(selector)
    if not element:
        raise ValueError(f"Element not found: {selector}")

    box = await element.bounding_box()
    if not box:
        raise ValueError(f"Element has no bounding box: {selector}")

    # Click at random position within element (not dead center)
    target_x = box["x"] + box["width"] * random.uniform(0.2, 0.8)
    target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)

    await human_move_to(page, target_x, target_y)

    # Brief pause before clicking (human reaction time)
    await asyncio.sleep(random.uniform(0.05, 0.15))

    await page.mouse.click(target_x, target_y)

    # Brief pause after clicking
    await asyncio.sleep(random.uniform(0.1, 0.3))


async def human_type(page: Page, selector: str, text: str) -> None:
    """Type text with variable delays between keystrokes."""
    await human_click(page, selector)
    await asyncio.sleep(random.uniform(0.1, 0.3))

    for char in text:
        await page.keyboard.press(char)
        # Variable typing speed (40-120 WPM equivalent)
        base_delay = random.uniform(0.03, 0.12)
        # Occasional longer pauses (thinking/correcting)
        if random.random() < 0.05:
            base_delay += random.uniform(0.2, 0.8)
        await asyncio.sleep(base_delay)


# ============================================================
# 3. Browser fingerprint randomization
# ============================================================

@dataclass
class BrowserProfile:
    """Randomized browser profile for fingerprint diversity."""
    user_agent: str
    viewport_width: int
    viewport_height: int
    device_scale_factor: float
    timezone: str
    locale: str
    color_scheme: str
    platform: str
    hardware_concurrency: int
    device_memory: int

    @classmethod
    def random_desktop(cls) -> "BrowserProfile":
        """Generate a random realistic desktop profile."""
        profiles = [
            # Windows Chrome
            {
                "user_agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(128, 132)}.0.0.0 Safari/537.36",
                "platform": "Win32",
                "viewports": [(1920, 1080), (1366, 768), (1536, 864), (2560, 1440)],
            },
            # macOS Chrome
            {
                "user_agent": f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(128, 132)}.0.0.0 Safari/537.36",
                "platform": "MacIntel",
                "viewports": [(1440, 900), (1680, 1050), (2560, 1600), (1920, 1080)],
            },
            # Linux Chrome
            {
                "user_agent": f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(128, 132)}.0.0.0 Safari/537.36",
                "platform": "Linux x86_64",
                "viewports": [(1920, 1080), (2560, 1440), (1366, 768)],
            },
        ]

        profile = random.choice(profiles)
        vp = random.choice(profile["viewports"])
        tz = random.choice(["America/New_York", "America/Chicago", "America/Denver",
                            "America/Los_Angeles", "Europe/London", "Europe/Berlin"])

        return cls(
            user_agent=profile["user_agent"],
            viewport_width=vp[0],
            viewport_height=vp[1],
            device_scale_factor=random.choice([1, 1.25, 1.5, 2]),
            timezone=tz,
            locale=random.choice(["en-US", "en-GB", "en-CA"]),
            color_scheme=random.choice(["light", "dark"]),
            platform=profile["platform"],
            hardware_concurrency=random.choice([4, 8, 12, 16]),
            device_memory=random.choice([4, 8, 16]),
        )


async def create_stealth_context(
    browser,
    profile: BrowserProfile | None = None,
) -> BrowserContext:
    """Create browser context with full stealth configuration."""
    if profile is None:
        profile = BrowserProfile.random_desktop()

    context = await browser.new_context(
        viewport={"width": profile.viewport_width, "height": profile.viewport_height},
        user_agent=profile.user_agent,
        locale=profile.locale,
        timezone_id=profile.timezone,
        color_scheme=profile.color_scheme,
        device_scale_factor=profile.device_scale_factor,
    )

    # Apply stealth patches
    await apply_stealth(context)

    # Additional fingerprint overrides
    await context.add_init_script(f"""
        Object.defineProperty(navigator, 'platform', {{ get: () => '{profile.platform}' }});
        Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {profile.hardware_concurrency} }});
        Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {profile.device_memory} }});
    """)

    return context


# ============================================================
# 4. Session rotation and proxy management
# ============================================================

@dataclass
class ProxyConfig:
    server: str
    username: str | None = None
    password: str | None = None

    def to_playwright(self) -> dict[str, str]:
        proxy = {"server": self.server}
        if self.username:
            proxy["username"] = self.username
        if self.password:
            proxy["password"] = self.password
        return proxy


class SessionRotator:
    """Rotate browser sessions and proxies to avoid detection."""

    def __init__(
        self,
        proxies: list[ProxyConfig] | None = None,
        max_requests_per_session: int = 50,
        rotate_user_agent: bool = True,
    ) -> None:
        self._proxies = proxies or []
        self._proxy_index = 0
        self._max_requests = max_requests_per_session
        self._request_count = 0
        self._rotate_ua = rotate_user_agent
        self._current_context: BrowserContext | None = None
        self._current_page: Page | None = None

    def _next_proxy(self) -> ProxyConfig | None:
        if not self._proxies:
            return None
        proxy = self._proxies[self._proxy_index]
        self._proxy_index = (self._proxy_index + 1) % len(self._proxies)
        return proxy

    async def get_page(self, browser) -> Page:
        """Get a page, rotating session if threshold reached."""
        if self._request_count >= self._max_requests or self._current_page is None:
            await self._rotate_session(browser)

        self._request_count += 1
        assert self._current_page is not None
        return self._current_page

    async def _rotate_session(self, browser) -> None:
        """Close current session and create a new one."""
        if self._current_context:
            await self._current_context.close()

        profile = BrowserProfile.random_desktop() if self._rotate_ua else None
        self._current_context = await create_stealth_context(browser, profile)
        self._current_page = await self._current_context.new_page()
        self._request_count = 0


# ============================================================
# 5. Complete anti-detection scraper
# ============================================================

async def stealth_scrape(url: str) -> dict[str, Any]:
    """Full stealth scraping example."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        profile = BrowserProfile.random_desktop()
        context = await create_stealth_context(browser, profile)
        page = await context.new_page()

        # Navigate with human-like behavior
        await page.goto(url, wait_until="domcontentloaded")

        # Random scroll to simulate reading
        for _ in range(random.randint(2, 5)):
            await page.evaluate(
                f"window.scrollBy(0, {random.randint(200, 600)})"
            )
            await asyncio.sleep(random.uniform(0.5, 2.0))

        # Extract data
        title = await page.title()
        content = await page.content()

        # Check if we were blocked
        blocked_indicators = [
            "captcha", "access denied", "rate limit",
            "please verify", "are you a robot",
        ]
        is_blocked = any(ind in content.lower() for ind in blocked_indicators)

        await context.close()
        await browser.close()

        return {
            "url": url,
            "title": title,
            "blocked": is_blocked,
            "content_length": len(content),
        }
```

**Anti-detection checklist:**

| Technique | Detection Method | Evasion |
|-----------|-----------------|---------|
| `navigator.webdriver` | JS property check | Override to `undefined` |
| Chrome runtime | Missing chrome object | Inject fake chrome runtime |
| Plugin count | Zero plugins = headless | Inject realistic plugin list |
| Mouse movement | Straight lines / teleportation | Bezier curve paths |
| Typing speed | Instant text entry | Variable delays per keystroke |
| Viewport / screen | Unusual sizes | Randomize from common resolutions |
| WebGL fingerprint | Vendor/renderer strings | Override `getParameter` |
| TLS fingerprint | Unusual cipher suites | Use real browser (not requests) |

**Best practices:**
- Use real Chromium (Playwright/Puppeteer) over HTTP libraries for JS-heavy sites
- Rotate user agents AND viewport sizes together (they must be consistent)
- Add random scroll and reading pauses to simulate human behavior
- Rotate sessions every 30-50 requests to avoid behavioral fingerprinting
- Use residential proxies for high-value targets; datacenter IPs are easily blocked
- Always check response content for CAPTCHA/block indicators before parsing'''
    ),
    (
        "web-scraping/data-extraction-pipelines",
        "Build a structured data extraction pipeline with CSS selectors, XPath, JSON-LD parsing, automatic schema inference, and export to multiple formats.",
        '''Structured data extraction pipeline with multiple strategies:

```python
"""Data extraction pipeline — CSS, XPath, JSON-LD, schema inference."""

from __future__ import annotations

import csv
import json
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Generic, TypeVar
from urllib.parse import urljoin

from lxml import html as lxml_html
from selectolax.parser import HTMLParser

T = TypeVar("T")


# ============================================================
# 1. Extraction strategies
# ============================================================

class ExtractionStrategy(ABC):
    """Base class for different extraction approaches."""

    @abstractmethod
    def extract(self, source: str, selector: str, **kwargs: Any) -> list[str]:
        ...

    @abstractmethod
    def extract_one(self, source: str, selector: str, **kwargs: Any) -> str | None:
        ...


class CSSStrategy(ExtractionStrategy):
    """Fast CSS selector extraction using selectolax."""

    def extract(self, source: str, selector: str, attr: str | None = None, **kwargs: Any) -> list[str]:
        parser = HTMLParser(source)
        nodes = parser.css(selector)
        if attr:
            return [n.attributes.get(attr, "") for n in nodes if n.attributes.get(attr)]
        return [n.text(strip=True) for n in nodes if n.text(strip=True)]

    def extract_one(self, source: str, selector: str, attr: str | None = None, **kwargs: Any) -> str | None:
        results = self.extract(source, selector, attr=attr)
        return results[0] if results else None


class XPathStrategy(ExtractionStrategy):
    """XPath extraction using lxml for complex queries."""

    def extract(self, source: str, selector: str, **kwargs: Any) -> list[str]:
        tree = lxml_html.fromstring(source)
        results = tree.xpath(selector)
        return [
            r.text_content().strip() if hasattr(r, "text_content") else str(r).strip()
            for r in results
            if (r.text_content().strip() if hasattr(r, "text_content") else str(r).strip())
        ]

    def extract_one(self, source: str, selector: str, **kwargs: Any) -> str | None:
        results = self.extract(source, selector)
        return results[0] if results else None


class JsonLdStrategy(ExtractionStrategy):
    """Extract structured data from JSON-LD scripts."""

    def extract(self, source: str, selector: str = "", **kwargs: Any) -> list[str]:
        """Extract all JSON-LD blocks as JSON strings."""
        parser = HTMLParser(source)
        scripts = parser.css('script[type="application/ld+json"]')
        results = []
        for script in scripts:
            text = script.text(strip=True)
            if text:
                try:
                    data = json.loads(text)
                    results.append(json.dumps(data))
                except json.JSONDecodeError:
                    continue
        return results

    def extract_one(self, source: str, selector: str = "", **kwargs: Any) -> str | None:
        results = self.extract(source, selector)
        return results[0] if results else None

    def extract_structured(self, source: str) -> list[dict[str, Any]]:
        """Extract and parse all JSON-LD data."""
        raw = self.extract(source)
        parsed = []
        for item in raw:
            data = json.loads(item)
            if isinstance(data, list):
                parsed.extend(data)
            else:
                parsed.append(data)
        return parsed


# ============================================================
# 2. Field extractors with fallback chains
# ============================================================

@dataclass
class FieldSpec:
    """Specification for extracting a single field with fallbacks."""
    name: str
    selectors: list[tuple[str, str]]  # (strategy, selector) pairs
    attr: str | None = None
    transform: Any = None  # Callable[[str], Any]
    required: bool = False
    default: Any = None


class FieldExtractor:
    """Extract fields using fallback chains of selectors."""

    def __init__(self) -> None:
        self._strategies: dict[str, ExtractionStrategy] = {
            "css": CSSStrategy(),
            "xpath": XPathStrategy(),
            "jsonld": JsonLdStrategy(),
        }

    def extract_field(self, source: str, spec: FieldSpec) -> Any:
        """Try each selector in the fallback chain until one succeeds."""
        for strategy_name, selector in spec.selectors:
            strategy = self._strategies[strategy_name]
            result = strategy.extract_one(source, selector, attr=spec.attr)
            if result:
                if spec.transform:
                    try:
                        return spec.transform(result)
                    except Exception:
                        continue
                return result

        if spec.required:
            raise ExtractionError(f"Required field '{spec.name}' not found")
        return spec.default

    def extract_all(
        self, source: str, specs: list[FieldSpec]
    ) -> dict[str, Any]:
        """Extract all fields from source."""
        result = {}
        errors = []
        for spec in specs:
            try:
                result[spec.name] = self.extract_field(source, spec)
            except ExtractionError as exc:
                errors.append(str(exc))
        if errors:
            raise ExtractionError(f"Extraction errors: {'; '.join(errors)}")
        return result


class ExtractionError(Exception):
    pass


# ============================================================
# 3. Schema-driven extraction for product pages
# ============================================================

PRODUCT_SCHEMA = [
    FieldSpec(
        name="title",
        selectors=[
            ("css", "h1.product-title"),
            ("css", "h1[itemprop='name']"),
            ("xpath", "//h1[contains(@class, 'product')]"),
            ("css", "meta[property='og:title']"),
        ],
        attr=None,  # Use text content for first 3, would need 'content' attr for meta
        required=True,
    ),
    FieldSpec(
        name="price",
        selectors=[
            ("css", "[itemprop='price']"),
            ("css", ".price .current-price"),
            ("css", "span.price"),
            ("xpath", "//span[contains(@class, 'price')][1]"),
        ],
        transform=lambda s: float(re.sub(r"[^\\d.]", "", s)),
        required=True,
    ),
    FieldSpec(
        name="currency",
        selectors=[
            ("css", "[itemprop='priceCurrency']"),
            ("css", "meta[itemprop='priceCurrency']"),
        ],
        attr="content",
        default="USD",
    ),
    FieldSpec(
        name="description",
        selectors=[
            ("css", "[itemprop='description']"),
            ("css", ".product-description"),
            ("css", "meta[name='description']"),
        ],
        default="",
    ),
    FieldSpec(
        name="rating",
        selectors=[
            ("css", "[itemprop='ratingValue']"),
            ("css", ".rating-value"),
        ],
        transform=lambda s: float(s),
        default=None,
    ),
    FieldSpec(
        name="image_url",
        selectors=[
            ("css", "[itemprop='image']"),
            ("css", ".product-image img"),
            ("css", "meta[property='og:image']"),
        ],
        attr="src",
        default=None,
    ),
    FieldSpec(
        name="availability",
        selectors=[
            ("css", "[itemprop='availability']"),
            ("css", ".stock-status"),
        ],
        transform=lambda s: "in_stock" if "instock" in s.lower().replace(" ", "") else "out_of_stock",
        default="unknown",
    ),
]


# ============================================================
# 4. Data pipeline with validation and export
# ============================================================

@dataclass
class Product:
    title: str
    price: float
    currency: str = "USD"
    description: str = ""
    rating: float | None = None
    image_url: str | None = None
    availability: str = "unknown"
    source_url: str = ""
    scraped_at: str = ""


class DataPipeline(Generic[T]):
    """Pipeline for extraction, transformation, validation, and export."""

    def __init__(self) -> None:
        self._items: list[T] = []
        self._errors: list[dict[str, Any]] = []
        self._stats = Counter[str]()

    def add(self, item: T) -> None:
        self._items.append(item)
        self._stats["total"] += 1

    def add_error(self, url: str, error: str) -> None:
        self._errors.append({"url": url, "error": error})
        self._stats["errors"] += 1

    def deduplicate(self, key_fn) -> "DataPipeline[T]":
        """Remove duplicate items by key function."""
        seen = set()
        unique = []
        for item in self._items:
            key = key_fn(item)
            if key not in seen:
                seen.add(key)
                unique.append(item)
            else:
                self._stats["duplicates"] += 1
        self._items = unique
        return self

    def filter(self, predicate) -> "DataPipeline[T]":
        """Filter items by predicate."""
        original = len(self._items)
        self._items = [item for item in self._items if predicate(item)]
        self._stats["filtered"] += original - len(self._items)
        return self

    def transform(self, fn) -> "DataPipeline[T]":
        """Apply transformation to all items."""
        self._items = [fn(item) for item in self._items]
        return self

    def export_json(self, path: Path) -> None:
        data = [asdict(item) if hasattr(item, "__dataclass_fields__") else item
                for item in self._items]
        path.write_text(json.dumps(data, indent=2, default=str))
        self._stats["exported_json"] = len(data)

    def export_csv(self, path: Path) -> None:
        if not self._items:
            return
        first = self._items[0]
        if hasattr(first, "__dataclass_fields__"):
            fieldnames = [f.name for f in fields(first)]
        elif isinstance(first, dict):
            fieldnames = list(first.keys())
        else:
            raise ValueError("Cannot determine CSV columns")

        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for item in self._items:
                row = asdict(item) if hasattr(item, "__dataclass_fields__") else item
                writer.writerow(row)
        self._stats["exported_csv"] = len(self._items)

    def export_jsonl(self, path: Path) -> None:
        """Export as JSON Lines (one JSON object per line)."""
        with open(path, "w") as f:
            for item in self._items:
                row = asdict(item) if hasattr(item, "__dataclass_fields__") else item
                f.write(json.dumps(row, default=str) + "\\n")
        self._stats["exported_jsonl"] = len(self._items)

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    @property
    def items(self) -> list[T]:
        return self._items


# ============================================================
# 5. Usage: complete extraction pipeline
# ============================================================

def run_pipeline(pages: list[tuple[str, str]]) -> None:
    """Run full extraction pipeline on list of (url, html) pairs."""
    extractor = FieldExtractor()
    pipeline = DataPipeline[Product]()

    for url, html_content in pages:
        try:
            data = extractor.extract_all(html_content, PRODUCT_SCHEMA)
            product = Product(
                **data,
                source_url=url,
                scraped_at=datetime.now().isoformat(),
            )
            pipeline.add(product)
        except ExtractionError as exc:
            pipeline.add_error(url, str(exc))

    # Post-processing pipeline
    (
        pipeline
        .deduplicate(key_fn=lambda p: (p.title, p.price))
        .filter(lambda p: p.price > 0)
        .transform(lambda p: Product(
            **{**asdict(p), "title": p.title.strip().title()}
        ))
    )

    # Export to multiple formats
    pipeline.export_json(Path("products.json"))
    pipeline.export_csv(Path("products.csv"))
    pipeline.export_jsonl(Path("products.jsonl"))

    print(f"Pipeline stats: {pipeline.stats}")
```

**Extraction strategy comparison:**

| Strategy | Speed | Complex Queries | Structured Data | Best For |
|----------|-------|----------------|-----------------|----------|
| CSS (selectolax) | Fastest | Basic | No | Simple attribute/text extraction |
| XPath (lxml) | Fast | Advanced | No | Complex DOM navigation |
| JSON-LD | Fast | N/A | Yes | Structured schema.org data |
| Regex | Variable | N/A | No | Last resort for malformed HTML |

**Best practices:**
- Always use fallback chains: CSS first, XPath second, JSON-LD for structured data
- Validate extracted data against expected types and ranges
- Use JSON Lines (`.jsonl`) for large datasets (streamable, appendable)
- Deduplicate early in the pipeline to save processing time
- Track extraction error rates to detect selector breakage
- Use `selectolax` for speed-critical CSS extraction (5-10x faster than BeautifulSoup)'''
    ),
    (
        "web-scraping/rate-limiting-and-ethical-scraping",
        "Build a comprehensive rate limiting and ethical scraping system with robots.txt parsing, adaptive throttling, retry budgets, and request fingerprint rotation.",
        '''Ethical scraping framework with adaptive rate limiting:

```python
"""Ethical scraping — robots.txt, adaptive throttling, retry budgets."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import aiohttp

logger = logging.getLogger(__name__)


# ============================================================
# 1. Robots.txt parser and compliance checker
# ============================================================

class RobotsChecker:
    """Parse and respect robots.txt rules."""

    def __init__(self, user_agent: str = "*") -> None:
        self._user_agent = user_agent
        self._parsers: dict[str, RobotFileParser] = {}
        self._crawl_delays: dict[str, float] = {}
        self._sitemaps: dict[str, list[str]] = {}

    async def load(self, base_url: str, session: aiohttp.ClientSession) -> None:
        """Fetch and parse robots.txt for a domain."""
        parsed = urlparse(base_url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        if domain in self._parsers:
            return

        robots_url = f"{domain}/robots.txt"
        parser = RobotFileParser()

        try:
            async with session.get(robots_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    content = await resp.text()
                    parser.parse(content.splitlines())

                    # Extract crawl-delay
                    delay_match = re.search(
                        r"Crawl-delay:\s*(\d+(?:\.\d+)?)",
                        content, re.IGNORECASE,
                    )
                    if delay_match:
                        self._crawl_delays[domain] = float(delay_match.group(1))

                    # Extract sitemaps
                    sitemaps = re.findall(r"Sitemap:\s*(\S+)", content, re.IGNORECASE)
                    self._sitemaps[domain] = sitemaps
                else:
                    # No robots.txt = allow everything
                    parser.allow_all = True
        except Exception as exc:
            logger.warning("Failed to fetch robots.txt for %s: %s", domain, exc)
            parser.allow_all = True

        self._parsers[domain] = parser

    def can_fetch(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt."""
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._parsers.get(domain)
        if parser is None:
            return True  # Not loaded yet, assume allowed
        return parser.can_fetch(self._user_agent, url)

    def get_crawl_delay(self, url: str) -> float | None:
        """Get crawl-delay for a domain."""
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        return self._crawl_delays.get(domain)

    def get_sitemaps(self, url: str) -> list[str]:
        """Get sitemap URLs for a domain."""
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        return self._sitemaps.get(domain, [])


# ============================================================
# 2. Adaptive rate limiter
# ============================================================

@dataclass
class DomainStats:
    """Per-domain request statistics for adaptive throttling."""
    total_requests: int = 0
    successful: int = 0
    rate_limited: int = 0  # 429 responses
    server_errors: int = 0  # 5xx responses
    avg_response_time_ms: float = 0.0
    last_request_time: float = 0.0
    current_delay: float = 1.0  # seconds between requests
    min_delay: float = 0.5
    max_delay: float = 30.0


class AdaptiveRateLimiter:
    """Rate limiter that adjusts speed based on server responses."""

    def __init__(
        self,
        default_delay: float = 1.0,
        backoff_multiplier: float = 2.0,
        recovery_multiplier: float = 0.8,
    ) -> None:
        self._default_delay = default_delay
        self._backoff_mult = backoff_multiplier
        self._recovery_mult = recovery_multiplier
        self._domain_stats: dict[str, DomainStats] = defaultdict(DomainStats)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _get_domain(self, url: str) -> str:
        return urlparse(url).netloc

    async def acquire(self, url: str) -> None:
        """Wait for rate limit clearance for the given URL's domain."""
        domain = self._get_domain(url)
        stats = self._domain_stats[domain]

        async with self._locks[domain]:
            now = time.monotonic()
            elapsed = now - stats.last_request_time

            if elapsed < stats.current_delay:
                wait_time = stats.current_delay - elapsed
                # Add jitter (10-30% of delay)
                jitter = wait_time * random.uniform(0.1, 0.3)
                await asyncio.sleep(wait_time + jitter)

            stats.last_request_time = time.monotonic()
            stats.total_requests += 1

    def report_response(self, url: str, status_code: int, response_time_ms: float) -> None:
        """Update statistics and adjust rate based on response."""
        domain = self._get_domain(url)
        stats = self._domain_stats[domain]

        # Update average response time (exponential moving average)
        alpha = 0.3
        stats.avg_response_time_ms = (
            alpha * response_time_ms + (1 - alpha) * stats.avg_response_time_ms
        )

        if status_code == 429:
            # Rate limited — back off significantly
            stats.rate_limited += 1
            stats.current_delay = min(
                stats.current_delay * self._backoff_mult * 2,
                stats.max_delay,
            )
            logger.warning(
                "Rate limited by %s, delay increased to %.1fs",
                domain, stats.current_delay,
            )

        elif status_code >= 500:
            # Server error — back off moderately
            stats.server_errors += 1
            stats.current_delay = min(
                stats.current_delay * self._backoff_mult,
                stats.max_delay,
            )

        elif 200 <= status_code < 300:
            # Success — gradually recover speed
            stats.successful += 1
            if stats.rate_limited == 0:  # Only speed up if no recent 429s
                stats.current_delay = max(
                    stats.current_delay * self._recovery_mult,
                    stats.min_delay,
                )

    def set_crawl_delay(self, url: str, delay: float) -> None:
        """Set minimum delay from robots.txt crawl-delay."""
        domain = self._get_domain(url)
        stats = self._domain_stats[domain]
        stats.min_delay = max(stats.min_delay, delay)
        stats.current_delay = max(stats.current_delay, delay)

    def get_stats(self, url: str | None = None) -> dict[str, Any]:
        """Get statistics for a domain or all domains."""
        if url:
            domain = self._get_domain(url)
            stats = self._domain_stats.get(domain)
            if stats:
                return {
                    "domain": domain,
                    "total": stats.total_requests,
                    "successful": stats.successful,
                    "rate_limited": stats.rate_limited,
                    "current_delay_s": round(stats.current_delay, 2),
                    "avg_response_ms": round(stats.avg_response_time_ms, 1),
                }
        return {
            d: self.get_stats(f"https://{d}/")
            for d in self._domain_stats
        }


# ============================================================
# 3. Retry budget
# ============================================================

@dataclass
class RetryBudget:
    """Per-domain retry budget to prevent hammering failed services."""
    max_retries_per_url: int = 3
    max_total_retries: int = 100
    retry_ratio_threshold: float = 0.5  # Max 50% retries
    window_seconds: float = 60.0

    _retries_in_window: list[float] = field(default_factory=list)
    _total_requests_in_window: int = 0

    def can_retry(self) -> bool:
        """Check if we have budget for another retry."""
        now = time.monotonic()
        # Prune old entries
        self._retries_in_window = [
            t for t in self._retries_in_window
            if now - t < self.window_seconds
        ]

        if len(self._retries_in_window) >= self.max_total_retries:
            return False

        if self._total_requests_in_window > 0:
            ratio = len(self._retries_in_window) / self._total_requests_in_window
            if ratio > self.retry_ratio_threshold:
                return False

        return True

    def record_retry(self) -> None:
        self._retries_in_window.append(time.monotonic())

    def record_request(self) -> None:
        self._total_requests_in_window += 1


# ============================================================
# 4. Ethical scraper with all protections
# ============================================================

class EthicalScraper:
    """Scraper that combines all ethical protections."""

    def __init__(
        self,
        user_agent: str = "MyBot/1.0 (+https://example.com/bot-info)",
        default_delay: float = 1.0,
    ) -> None:
        self._user_agent = user_agent
        self._robots = RobotsChecker(user_agent)
        self._rate_limiter = AdaptiveRateLimiter(default_delay=default_delay)
        self._retry_budget = RetryBudget()
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "EthicalScraper":
        self._session = aiohttp.ClientSession(
            headers={
                "User-Agent": self._user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "DNT": "1",
                "Connection": "keep-alive",
            },
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._session:
            await self._session.close()

    async def fetch(self, url: str) -> tuple[int, str]:
        """Fetch URL with full ethical protections."""
        assert self._session is not None

        # 1. Check robots.txt
        await self._robots.load(url, self._session)
        if not self._robots.can_fetch(url):
            logger.info("Blocked by robots.txt: %s", url)
            raise BlockedByRobotsError(f"Blocked by robots.txt: {url}")

        # Apply robots.txt crawl-delay
        crawl_delay = self._robots.get_crawl_delay(url)
        if crawl_delay:
            self._rate_limiter.set_crawl_delay(url, crawl_delay)

        # 2. Rate limit
        await self._rate_limiter.acquire(url)

        # 3. Make request with retry
        last_exc = None
        for attempt in range(self._retry_budget.max_retries_per_url):
            self._retry_budget.record_request()
            start = time.monotonic()

            try:
                async with self._session.get(
                    url, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    self._rate_limiter.report_response(url, resp.status, elapsed_ms)

                    if resp.status == 200:
                        return resp.status, await resp.text()

                    if resp.status == 429:
                        # Rate limited — respect Retry-After header
                        retry_after = resp.headers.get("Retry-After", "60")
                        wait = int(retry_after) if retry_after.isdigit() else 60
                        logger.warning("429 from %s, waiting %ds", url, wait)
                        await asyncio.sleep(wait)

                    elif resp.status >= 500:
                        logger.warning("Server error %d from %s", resp.status, url)

                    else:
                        return resp.status, await resp.text()

            except Exception as exc:
                last_exc = exc
                elapsed_ms = (time.monotonic() - start) * 1000
                logger.warning("Request failed: %s (%s)", url, exc)

            # Check retry budget before retrying
            if not self._retry_budget.can_retry():
                logger.error("Retry budget exhausted for %s", url)
                break
            self._retry_budget.record_retry()

            # Exponential backoff between retries
            await asyncio.sleep(2 ** attempt + random.uniform(0, 1))

        raise ScrapingError(f"Failed to fetch {url} after retries: {last_exc}")

    def stats(self) -> dict[str, Any]:
        return self._rate_limiter.get_stats()


class BlockedByRobotsError(Exception):
    pass

class ScrapingError(Exception):
    pass


# Usage
async def main() -> None:
    async with EthicalScraper(
        user_agent="ResearchBot/1.0 (+https://university.edu/research)",
        default_delay=2.0,
    ) as scraper:
        urls = [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3",
        ]

        for url in urls:
            try:
                status, html = await scraper.fetch(url)
                if status == 200:
                    print(f"Success: {url} ({len(html)} bytes)")
            except BlockedByRobotsError:
                print(f"Skipped (robots.txt): {url}")
            except ScrapingError as exc:
                print(f"Failed: {url} - {exc}")

        print(f"Stats: {scraper.stats()}")

asyncio.run(main())
```

**Ethical scraping checklist:**

| Principle | Implementation | Why |
|-----------|---------------|-----|
| Respect robots.txt | Parse and obey Disallow rules | Legal compliance |
| Crawl-delay | Adaptive rate + robots.txt delay | Server health |
| Identify yourself | Descriptive User-Agent with contact URL | Transparency |
| Retry budget | Limit retries per domain and globally | Prevent hammering |
| Adaptive throttling | Slow down on 429/5xx, speed up on 200 | Server signals |
| Respect Retry-After | Wait the requested duration on 429 | HTTP standard |
| Cache responses | Store and reuse fetched pages | Reduce requests |

**Best practices:**
- Always set a descriptive User-Agent with a contact URL
- Respect `Crawl-delay` from robots.txt (many sites specify 5-10 seconds)
- Use adaptive throttling: speed up when server is healthy, back off on errors
- Implement a retry budget to prevent infinite retry loops
- Monitor your 429 rate; if > 5%, you are too aggressive
- Cache responses locally and check `If-Modified-Since` before re-fetching'''
    ),
]
