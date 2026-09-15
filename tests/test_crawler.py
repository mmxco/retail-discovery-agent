"""
Unit tests for the crawler and DOM sanitization pipeline (scraper.py).
Tests DOMSanitizer, technology footprint detection, link heuristics, and async runner.
Zero live browser execution required.
"""

import pytest
import asyncio
from unittest.mock import patch
from bs4 import BeautifulSoup

from scraper import (
    DOMSanitizer,
    detect_tech_signals,
    ApparelDiscoveryCrawler,
    ScrapeResult,
    scrape_retail_site,
    check_playwright_availability,
    run_async,
)


def test_dom_sanitizer_noise_removal():
    raw_html = """
    <html>
    <head>
        <title>Luxe Apparel Group | Official Store</title>
        <script src="https://demandware.net/dw.js"></script>
        <script src="https://www.googletagmanager.com/gtm.js?id=GTM-TEST"></script>
        <script src="https://cdn.segment.com/analytics.js/v1/key/analytics.min.js"></script>
        <style>body { background: #fff; }</style>
    </head>
    <body>
        <nav><a href="/press-releases">Press</a><a href="/our-leadership">Leadership</a></nav>
        <header><p>Promo Banner</p></header>
        <div id="onetrust-consent-sdk" class="cookie-banner"><p>Cookie policy</p></div>
        <main>
            <h1>Luxe Apparel Spring Collection</h1>
            <p>Direct-to-consumer sustainable apparel engineered with high-twist cotton.</p>
        </main>
        <footer><p>Copyright 2026</p></footer>
    </body>
    </html>
    """

    soup = BeautifulSoup(raw_html, "html.parser")
    signals = detect_tech_signals(soup, raw_html)
    assert "Salesforce Commerce Cloud (Demandware)" in signals
    assert "Google Tag Manager" in signals
    assert "Segment CDP" in signals

    container = DOMSanitizer.sanitize(soup, target_semantic_container=True)
    md_text = DOMSanitizer.to_markdown(container)

    assert "# Luxe Apparel Spring Collection" in md_text
    assert "Promo Banner" not in md_text
    assert "Cookie policy" not in md_text
    assert "Copyright 2026" not in md_text


def test_dom_sanitizer_clean_html():
    raw_html = """
    <html>
    <head>
        <title>Retailer Portal</title>
        <meta name="description" content="Official luxury shopping experience." />
        <script src="https://cdn.shopify.com/shopify.js"></script>
    </head>
    <body>
        <main><p>Welcome to our storefront.</p></main>
    </body>
    </html>
    """
    clean_soup, metadata, signals = DOMSanitizer.clean_html(raw_html)
    assert metadata["title"] == "Retailer Portal"
    assert metadata["meta_description"] == "Official luxury shopping experience."
    assert "Shopify Plus" in signals


def test_link_heuristic_discovery():
    crawler = ApparelDiscoveryCrawler()
    raw_html = """
    <html>
    <body>
        <a href="/about-us">About Our Brand</a>
        <a href="/press-releases">Corporate Newsroom</a>
        <a href="/our-leadership">Executive Leadership</a>
        <a href="/careers">Tech Careers</a>
    </body>
    </html>
    """
    discovered = crawler.discover_target_links("https://luxeapparel.com", raw_html)
    assert "https://luxeapparel.com/about-us" in discovered["about"]
    assert "https://luxeapparel.com/press-releases" in discovered["press"]
    assert "https://luxeapparel.com/our-leadership" in discovered["leadership"]
    assert "https://luxeapparel.com/careers" in discovered["technology"]


def test_press_release_extraction():
    crawler = ApparelDiscoveryCrawler()
    press_html = """
    <html>
    <body>
        <main>
            <h1>Investor Relations & Press Newsroom</h1>
            <article class="press-release-card">
                <h2>Luxe Apparel Opens 50 New Omnichannel Store Hubs</h2>
                <a href="/news/store-expansion">Read More</a>
                <p>New regional hubs will enable same-day ship-from-store across key metropolitan markets.</p>
            </article>
            <article class="press-release-card">
                <h2>Q4 Fiscal 2025 Financial Results</h2>
                <a href="/news/q4-earnings">Read More</a>
                <p>Net sales increased 14% year-over-year driven by direct-to-consumer digital acceleration.</p>
            </article>
        </main>
    </body>
    </html>
    """
    items = crawler.extract_press_releases(press_html, "https://luxeapparel.com/press-releases")
    assert len(items) == 2
    assert "50 New Omnichannel Store Hubs" in items[0].title
    assert "same-day ship-from-store" in items[0].markdown_text


def test_run_async_sync_and_async():
    async def sample_coro():
        return "async_result"

    # 1. Direct synchronous execution
    res = run_async(sample_coro())
    assert res == "async_result"

    # 2. Execution from within an existing event loop
    async def caller():
        return run_async(sample_coro())

    nested_res = asyncio.run(caller())
    assert nested_res == "async_result"


def test_check_playwright_availability_mocked():
    async def mock_async_check():
        return True, "Playwright operational."

    with patch("scraper._async_check_playwright", side_effect=mock_async_check):
        ok, msg = check_playwright_availability()
        assert ok is True
        assert "Playwright operational." in msg


def test_scrape_retail_site_mocked():
    mock_crawl_payload = {
        "page_title": "Mock Retail",
        "meta_description": "Mock description",
        "tech_footprint": {
            "ecommerce_platform": "Shopify Plus",
            "analytics_tagging": ["Google Tag Manager"],
            "detected_frameworks": ["React"],
        },
        "homepage_content": {
            "source_url": "https://mockretail.com",
            "markdown_text": "# Mock Retail Storefront",
        },
        "about_us_content": {"markdown_text": "About us text"},
        "leadership_content": {"markdown_text": "Leadership text"},
        "press_releases": [],
    }

    async def mock_async_crawl(self, url):
        return mock_crawl_payload

    with patch("scraper.check_playwright_availability", return_value=(True, "OK")), \
         patch.object(ApparelDiscoveryCrawler, "crawl_apparel_domain", new=mock_async_crawl):

        result = scrape_retail_site("https://mockretail.com", deep_crawl=True)
        assert isinstance(result, ScrapeResult)
        assert result.success is True
        assert result.title == "Mock Retail"
        assert "Shopify Plus" in result.tech_signals


def test_dom_sanitizer_nested_banners_and_nonetype_safety():
    nested_html = """
    <html>
    <body>
        <div class="cookie-banner">
            <div class="nested-child-1">
                <span class="nested-child-2">Nested cookie text</span>
            </div>
        </div>
        <div id="walmart-hub-header">
            <nav><a href="/about">About</a><a href="/news">News</a></nav>
        </div>
        <main>
            <h1>Main Apparel Title</h1>
            <p>Content body text goes here.</p>
        </main>
        <div class="cmp-experiencefragment--footer">
            <p>Footer content</p>
        </div>
    </body>
    </html>
    """
    nested_soup = BeautifulSoup(nested_html, "html.parser")
    clean_container = DOMSanitizer.sanitize(nested_soup, target_semantic_container=True)
    clean_md = DOMSanitizer.to_markdown(clean_container)
    assert "# Main Apparel Title" in clean_md
    assert "Nested cookie text" not in clean_md
    assert "Footer content" not in clean_md


def test_corporate_subdomain_and_news_ranking():
    crawler = ApparelDiscoveryCrawler()
    corp_html = """
    <html>
    <body>
        <a href="/about">About</a>
        <a href="/about/leadership">Leadership</a>
        <a href="/news">News</a>
        <a href="https://investors.walmart.com/events">Investors</a>
        <a href="/news/2026/09/individual-article">Dated Article</a>
    </body>
    </html>
    """
    discovered_corp = crawler.discover_target_links("https://corporate.walmart.com", corp_html)
    assert "https://corporate.walmart.com/about" in discovered_corp["about"]
    assert "https://corporate.walmart.com/about/leadership" in discovered_corp["leadership"]
    assert "https://corporate.walmart.com/news" in discovered_corp["press"]
    # Ensure root /news is ranked higher than deep dated article
    assert discovered_corp["press"][0] == "https://corporate.walmart.com/news"


def test_press_release_article_card_thumbnail_anchor():
    crawler = ApparelDiscoveryCrawler()
    card_html = """
    <html>
    <body>
        <article class="adp-newsroom-card">
            <a href="/news/article-one"><img src="thumb.jpg" alt="" /></a>
            <div class="header">
                <h3><a href="/news/article-one">Major Corporate Milestone Achieved</a></h3>
            </div>
            <p>Summary of the major corporate announcement.</p>
        </article>
    </body>
    </html>
    """
    card_items = crawler.extract_press_releases(card_html, "https://corporate.walmart.com/news")
    assert len(card_items) == 1
    assert card_items[0].title == "Major Corporate Milestone Achieved"
    assert card_items[0].source_url == "https://corporate.walmart.com/news/article-one"


def test_tech_signature_false_positive_guard():
    mime_html = '<link rel="icon" type="image/png" href="/favicon.png"><script src="/etc.clientlibs/aem.js"></script>'
    mime_soup = BeautifulSoup(mime_html, "html.parser")
    sig_result = detect_tech_signals(mime_soup, mime_html)
    assert "Adobe Commerce / Magento" not in sig_result
    assert "Adobe Experience Manager (AEM)" in sig_result


def test_run_async_nested_event_loops_and_exceptions():
    # 1. Deep nesting across event loops
    async def level3():
        return "level3_val"

    async def level2():
        return run_async(level3())

    async def level1():
        return run_async(level2())

    assert run_async(level1()) == "level3_val"

    # 2. Exception propagation through layers
    async def failing_level2():
        raise ValueError("deep error in async")

    async def failing_level1():
        return run_async(failing_level2())

    with pytest.raises(ValueError, match="deep error in async"):
        run_async(failing_level1())


def test_run_async_concurrent_threads():
    import concurrent.futures

    async def async_worker(n):
        await asyncio.sleep(0.01)
        return n * 3

    def thread_call(n):
        return run_async(async_worker(n))

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(thread_call, i) for i in range(5)]
        results = [f.result() for f in futures]

    assert results == [0, 3, 6, 9, 12]


def test_dom_sanitizer_exotic_structures():
    # Malformed table, unclosed tags, comments with HTML, and deeply nested elements
    exotic_html = (
        "<!-- <script>var malicious = 1;</script> -->"
        "<table><tr><td><table><tr><td>Nested Cell</td></tr>"
        + "<div>" * 25 + "<p>Deeply nested text</p>" + "</div>" * 25
        + "<svg><circle cx='50' cy='50' r='40'></circle></svg>"
        + "<div role='banner'>Banner to remove</div>"
    )
    soup, meta, sigs = DOMSanitizer.clean_html(exotic_html)
    md = DOMSanitizer.to_markdown(soup)
    assert "malicious" not in md
    assert "Nested Cell" in md
    assert "Deeply nested text" in md
    assert "Banner to remove" not in md

