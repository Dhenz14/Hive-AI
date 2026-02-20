import logging
import hashlib
import requests
import re
import asyncio
from bs4 import BeautifulSoup
from readability import Document
from concurrent.futures import ThreadPoolExecutor, as_completed
from hiveai.config import MAX_CRAWL_PAGES, CRAWL_TIMEOUT, CORS_PROXIES, CRAWL_WORKERS, MAX_RAW_CONTENT_SIZE, CRAWL_CACHE_TTL_HOURS
from hiveai.models import SessionLocal, CrawledPage, Job

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    CRAWL4AI_AVAILABLE = True
    logger.info("crawl4ai loaded successfully")
except ImportError:
    CRAWL4AI_AVAILABLE = False
    logger.warning("crawl4ai not available, falling back to sync crawling")

try:
    from crawl4ai import DefaultMarkdownGenerator, PruningContentFilter
    MARKDOWN_GENERATOR_AVAILABLE = True
except ImportError:
    MARKDOWN_GENERATOR_AVAILABLE = False
    DefaultMarkdownGenerator = None
    PruningContentFilter = None


def fetch_page_sync(url, timeout=CRAWL_TIMEOUT):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning(f"Direct fetch failed for {url}: {e}")

    for proxy in CORS_PROXIES:
        try:
            proxy_url = proxy + url
            resp = requests.get(proxy_url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            continue

    return None


def extract_content_sync(html, url):
    try:
        doc = Document(html)
        title = doc.title()
        content_html = doc.summary()
        soup = BeautifulSoup(content_html, "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return title, text
    except Exception as e:
        logger.warning(f"Readability extraction failed for {url}: {e}")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        title = soup.title.string if soup.title else ""
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return title, text[:50000]


def crawl_url_sync(url):
    html = fetch_page_sync(url)
    if not html:
        return None

    title, content = extract_content_sync(html, url)
    if not content or len(content) < 100:
        return None

    content_hash = hashlib.sha256(content.encode()).hexdigest()

    return {
        "url": url,
        "title": title,
        "raw_html": html[:50000],
        "content": content,
        "content_hash": content_hash,
    }


async def crawl_url(url):
    if not CRAWL4AI_AVAILABLE:
        logger.debug(f"crawl4ai not available, using sync fallback for {url}")
        return crawl_url_sync(url)

    try:
        browser_config = BrowserConfig(headless=True, browser_type="chromium")
        
        if MARKDOWN_GENERATOR_AVAILABLE:
            markdown_generator = DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(
                    threshold=0.45,
                    threshold_type="dynamic",
                    min_word_threshold=5
                )
            )
            run_config = CrawlerRunConfig(
                word_count_threshold=10,
                markdown_generator=markdown_generator
            )
        else:
            run_config = CrawlerRunConfig(word_count_threshold=10)

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)

        if result.success and result.markdown:
            content = None
            if MARKDOWN_GENERATOR_AVAILABLE and hasattr(result.markdown, 'fit_markdown'):
                content = result.markdown.fit_markdown
                if not content:
                    content = result.markdown.raw_markdown
            else:
                content = result.markdown.raw_markdown
            
            if not content or len(content) < 100:
                logger.warning(f"crawl4ai content too short for {url}, falling back to sync")
                return crawl_url_sync(url)

            content_hash = hashlib.sha256(content.encode()).hexdigest()
            title = getattr(result, 'title', '') or ""
            logger.info(f"crawl4ai success for {url} ({len(content)} chars)")

            return {
                "url": url,
                "title": title,
                "raw_html": "",
                "content": content,
                "content_hash": content_hash,
            }
        else:
            logger.warning(f"crawl4ai failed for {url}, falling back to sync")
            return crawl_url_sync(url)

    except Exception as e:
        logger.warning(f"crawl4ai error for {url}: {e}, falling back to sync")
        return crawl_url_sync(url)


async def _mass_crawl_async(urls_to_crawl, seen_hashes):
    results = []
    failed_urls = []

    if not CRAWL4AI_AVAILABLE or not urls_to_crawl:
        return results, urls_to_crawl

    try:
        browser_config = BrowserConfig(headless=True, browser_type="chromium")
        
        if MARKDOWN_GENERATOR_AVAILABLE:
            markdown_generator = DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(
                    threshold=0.45,
                    threshold_type="dynamic",
                    min_word_threshold=5
                )
            )
            run_config = CrawlerRunConfig(
                word_count_threshold=10,
                markdown_generator=markdown_generator
            )
        else:
            run_config = CrawlerRunConfig(word_count_threshold=10)

        async with AsyncWebCrawler(config=browser_config) as crawler:
            crawl_results = await crawler.arun_many(urls=urls_to_crawl, config=run_config)

        for result in crawl_results:
            try:
                if result.success and result.markdown:
                    content = None
                    if MARKDOWN_GENERATOR_AVAILABLE and hasattr(result.markdown, 'fit_markdown'):
                        content = result.markdown.fit_markdown
                        if not content:
                            content = result.markdown.raw_markdown
                    else:
                        content = result.markdown.raw_markdown
                    
                    if not content or len(content) < 100:
                        failed_urls.append(result.url)
                        continue

                    content_hash = hashlib.sha256(content.encode()).hexdigest()
                    if content_hash in seen_hashes:
                        continue

                    seen_hashes.add(content_hash)
                    title = getattr(result, 'title', '') or ""
                    results.append({
                        "url": result.url,
                        "title": title,
                        "raw_html": "",
                        "content": content,
                        "content_hash": content_hash,
                    })
                    logger.info(f"crawl4ai batch success: {result.url} ({len(content)} chars)")
                else:
                    failed_urls.append(result.url)
                    logger.warning(f"crawl4ai batch failed for {result.url}")
            except Exception as e:
                failed_urls.append(result.url)
                logger.warning(f"crawl4ai batch result error for {result.url}: {e}")

    except Exception as e:
        logger.warning(f"crawl4ai batch crawl error: {e}, all URLs will use sync fallback")
        failed_urls = urls_to_crawl

    return results, failed_urls


def mass_crawl(urls, job_id, max_pages=MAX_CRAWL_PAGES):
    seen = set()
    deduped_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped_urls.append(url)

    deduped_urls = deduped_urls[:max_pages]
    logger.info(f"Mass crawl: {len(deduped_urls)} URLs to process for job {job_id}")

    results = []
    seen_hashes = set()
    urls_to_crawl = []

    db = SessionLocal()
    try:
        from datetime import datetime, timedelta
        cache_cutoff = datetime.utcnow() - timedelta(hours=CRAWL_CACHE_TTL_HOURS)
        cached_pages = db.query(CrawledPage).filter(
            CrawledPage.url.in_(deduped_urls),
            CrawledPage.cleaned_markdown.isnot(None),
            CrawledPage.crawled_at >= cache_cutoff,
        ).all()

        cached_by_url = {}
        for p in cached_pages:
            if p.url not in cached_by_url:
                cached_by_url[p.url] = p

        cached_count = 0
        for url in deduped_urls:
            if url in cached_by_url:
                p = cached_by_url[url]
                if p.content_hash and p.content_hash not in seen_hashes:
                    seen_hashes.add(p.content_hash)
                    results.append({
                        "url": p.url,
                        "title": p.title,
                        "raw_html": p.raw_content or "",
                        "content": p.cleaned_markdown,
                        "content_hash": p.content_hash,
                        "cached": True,
                    })
                    cached_count += 1
            else:
                urls_to_crawl.append(url)

        if cached_count > 0:
            logger.info(f"Crawl cache: reused {cached_count} pages, {len(urls_to_crawl)} to fetch")
    finally:
        db.close()

    if urls_to_crawl:
        if CRAWL4AI_AVAILABLE:
            logger.info(f"Using crawl4ai for {len(urls_to_crawl)} URLs")
            async_results, failed_urls = asyncio.run(_mass_crawl_async(urls_to_crawl, seen_hashes))
            results.extend(async_results)

            if failed_urls:
                logger.info(f"Falling back to sync crawling for {len(failed_urls)} URLs")
                with ThreadPoolExecutor(max_workers=CRAWL_WORKERS) as executor:
                    future_to_url = {executor.submit(crawl_url_sync, url): url for url in failed_urls}
                    for future in as_completed(future_to_url):
                        try:
                            result = future.result()
                            if result and result["content_hash"] not in seen_hashes:
                                seen_hashes.add(result["content_hash"])
                                results.append(result)
                        except Exception as e:
                            logger.warning(f"Sync crawl worker error: {e}")
        else:
            logger.info(f"crawl4ai not available, using sync crawling for {len(urls_to_crawl)} URLs")
            with ThreadPoolExecutor(max_workers=CRAWL_WORKERS) as executor:
                future_to_url = {executor.submit(crawl_url_sync, url): url for url in urls_to_crawl}
                for future in as_completed(future_to_url):
                    try:
                        result = future.result()
                        if result and result["content_hash"] not in seen_hashes:
                            seen_hashes.add(result["content_hash"])
                            results.append(result)
                    except Exception as e:
                        logger.warning(f"Crawl worker error: {e}")

    db = SessionLocal()
    try:
        for r in results:
            page = CrawledPage(
                job_id=job_id,
                url=r["url"],
                title=r["title"],
                raw_content=r.get("raw_html", "")[:MAX_RAW_CONTENT_SIZE] if r.get("raw_html") else None,
                cleaned_markdown=r["content"][:MAX_RAW_CONTENT_SIZE],
                content_hash=r["content_hash"],
                source_type="web",
                from_hive=False,
            )
            db.add(page)

        job = db.get(Job, job_id)
        if job:
            job.crawl_count = len(results)
            job.status = "crawled"
        db.commit()

        logger.info(f"Mass crawl complete: {len(results)} pages stored for job {job_id}")
    finally:
        db.close()

    return results
