"""
Production-Grade Asynchronous Retail Apparel Web Crawler & DOM Extractor
Author: Data Engineering & Automation Architecture Team

Utilizes playwright.async_api, beautifulsoup4, and markdownify to perform
headless extraction, anti-detection navigation, heuristic link discovery,
DOM sanitization, tech footprint profiling, and structured intelligence aggregation
across enterprise apparel retail domains.
"""

import os
import sys
import re
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any, Set, Tuple
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment, Tag
from markdownify import markdownify as md
from playwright.async_api import (
    async_playwright,
    Page,
    BrowserContext,
    TimeoutError as PlaywrightTimeoutError,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("ApparelDiscoveryCrawler")

# Stealth and Browser Defaults
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)

VIEWPORT_CONFIG = {"width": 1920, "height": 1080}
DEFAULT_PAGE_TIMEOUT_MS = 30000  # 30-second graceful timeout

# Anti-detection evasion script injected before any document script executes
EVASION_INIT_SCRIPT = """
(() => {
    // Overwrite navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });

    // Mock chrome runtime object
    window.chrome = {
        runtime: {},
        app: {},
        csi: () => {},
        loadTimes: () => {}
    };

    // Realistic language and plugins array
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
        configurable: true
    });

    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' }
        ],
        configurable: true
    });

    // Mock permissions query
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
})();
"""

# Technology Footprint & Platform Signatures
TECH_SIGNATURES: Dict[str, List[str]] = {
    # E-Commerce Engines
    "Shopify Plus": [r"cdn\.shopify\.com", r"Shopify\.", r"myshopify\.com", r"shopify-buy"],
    "Salesforce Commerce Cloud (Demandware)": [r"demandware\.net", r"demandware\.static", r"dw\.js", r"dwac_"],
    "Adobe Commerce / Magento": [r"mage\/", r"magento", r"static\/_requirejs", r"mage-translation-dictionary"],
    "SAP Commerce Cloud (Hybris)": [r"hybris", r"sap-commerce", r"occ\/v2", r"medias\/sys_master"],
    "Oracle Retail / NetSuite / ATG": [r"atg\.js", r"oracle\.com\/retail", r"netsuite\.com", r"elqCfg"],
    "BigCommerce": [r"cdn11\.bigcommerce\.com", r"bigcommerce\.com"],
    "commercetools": [r"commercetools", r"commercetools\.com"],

    # Analytics, CDP & Customer Engagement
    "Google Tag Manager": [r"googletagmanager\.com\/gtm\.js"],
    "Google Analytics 4": [r"google-analytics\.com\/g\/collect", r"gtag\("],
    "Segment CDP": [r"cdn\.segment\.com\/analytics\.js", r"analytics\.load\("],
    "Klaviyo": [r"static\.klaviyo\.com", r"klaviyo\.js"],
    "Braze": [r"js\.appboycdn\.com", r"braze\.min\.js"],
    "Dynamic Yield": [r"dynamicyield\.com", r"cdn\.dynamicyield\.com"],
    "Criteo": [r"static\.criteo\.net", r"criteo\.js"],
    "Adobe Experience Platform / Analytics": [r"adobedtm\.com", r"assets\.adobedtm\.com", r"omniture"],

    # Frontend Frameworks, Search & Discovery
    "Next.js": [r"/_next/", r"__NEXT_DATA__"],
    "React": [r"react\.production\.min\.js", r"react-dom"],
    "Vue.js": [r"vue\.min\.js", r"vue-router"],
    "Nuxt.js": [r"/_nuxt/", r"__NUXT__"],
    "Algolia Search": [r"algolia\.net", r"algoliasearch", r"instantsearch\.js"],
    "Constructor.io": [r"cnstrc\.com", r"constructorio"],
    "Bloomreach": [r"bloomreach\.com", r"brsrvr\.com"],
    "Yotpo Reviews": [r"staticw2\.yotpo\.com"],
    "Bazaarvoice": [r"bazaarvoice\.com", r"bvapi\.js"],
}

# Heuristic URL Pattern Matchers for Target Discovery
LINK_PATTERNS = {
    "press": re.compile(
        r"(press|newsroom|news-releases|press-releases|investor|investors|media-center|corporate-news)",
        re.I
    ),
    "leadership": re.compile(
        r"(leadership|executive-team|executive-committee|board-of-directors|our-leaders|our-team|management-team|about-us/team|executives)",
        re.I
    ),
    "technology": re.compile(
        r"(careers|engineering|technology|tech-stack|work-with-us|tech-blog|engineering-blog|jobs)",
        re.I
    ),
}

NOISE_TAGS = [
    "script", "style", "noscript", "svg", "header", "footer", "nav",
    "aside", "iframe", "form", "button", "input", "select", "textarea",
    "dialog", "canvas", "video", "audio"
]

BOILERPLATE_CLASS_ID_REGEX = re.compile(
    r"(cookie|consent|banner|popup|modal|overlay|onetrust|gdpr|newsletter|subscribe|toast|alertdialog)",
    re.I
)


# ==============================================================================
# DATA STRUCTURES
# ==============================================================================

@dataclass
class PressReleaseItem:
    """Structured press release or corporate announcement entry."""
    title: str
    source_url: str
    markdown_text: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "source_url": self.source_url,
            "markdown_text": self.markdown_text,
        }


@dataclass
class ScrapeResult:
    """Structured result returned by the legacy synchronous scraping bridge."""
    url: str
    title: str = ""
    markdown: str = ""
    meta_description: str = ""
    meta_keywords: str = ""
    tech_signals: List[str] = field(default_factory=list)
    engine_used: str = "playwright"
    success: bool = True
    error_message: Optional[str] = None

    def to_summary_dict(self) -> Dict[str, object]:
        return {
            "url": self.url,
            "title": self.title,
            "meta_description": self.meta_description,
            "tech_signals": self.tech_signals,
            "markdown_char_count": len(self.markdown),
            "markdown_content": self.markdown,
            "engine_used": self.engine_used,
            "success": self.success,
        }


# ==============================================================================
# DOM SANITIZATION & MARKDOWN TRANSFORMATION UTILITIES
# ==============================================================================

def detect_tech_signals(soup: BeautifulSoup, raw_html: str = "") -> List[str]:
    """
    Scans HTML script sources, stylesheet links, meta tags, and inline text
    for tell-tale enterprise retail platform signatures before DOM stripping.
    """
    detected: Set[str] = set()

    # Collect indicators from DOM tags
    indicators: List[str] = []
    for s in soup.find_all(["script", "link"]):
        src = s.get("src") or s.get("href") or ""
        if src:
            indicators.append(src)
        if s.string:
            indicators.append(s.string[:250])

    combined_text = " ".join(indicators) + " " + raw_html[:30000]

    for platform, patterns in TECH_SIGNATURES.items():
        for pat in patterns:
            if re.search(pat, combined_text, re.IGNORECASE):
                detected.add(platform)
                break

    return sorted(list(detected))


def sanitize_dom(soup: BeautifulSoup, target_semantic_container: bool = True) -> Tag:
    """
    Decomposes noise and boilerplate elements while preserving primary semantic content.
    Returns the target semantic container or body tag.
    """
    # 1. Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # 2. Decompose noise tags completely
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()

    # 3. Decompose cookie/consent/modal banners
    for element in soup.find_all(["div", "section", "aside", "span"]):
        class_str = " ".join(element.get("class", [])) if isinstance(element.get("class"), list) else ""
        elem_id = element.get("id", "")
        role = element.get("role", "")
        if (
            BOILERPLATE_CLASS_ID_REGEX.search(class_str)
            or BOILERPLATE_CLASS_ID_REGEX.search(elem_id)
            or role in ["banner", "alertdialog"]
        ):
            element.decompose()

    # 4. Target semantic content container if requested
    if target_semantic_container:
        candidates = [
            soup.find("main"),
            soup.find("article"),
            soup.find(id=re.compile(r"^(content|main|news-content|article-body|press-body)$", re.I)),
            soup.find(class_=re.compile(r"^(main-content|article-content|news-body|press-releases|page-content)$", re.I)),
            soup.find("div", attrs={"role": "main"}),
        ]
        for candidate in candidates:
            if candidate and len(candidate.get_text(strip=True)) > 150:
                return candidate

    return soup.body or soup


def convert_dom_to_markdown(container: Tag) -> str:
    """
    Converts a sanitized BeautifulSoup tag or tree into clean, token-efficient
    GitHub-flavored Markdown using markdownify with customized ATX headers.
    """
    raw_md = md(
        str(container),
        heading_style="ATX",
        strip=["img", "button", "input", "form", "svg"],
    )

    # Post-process Markdown to eliminate whitespace bloat
    cleaned = re.sub(r"\n{3,}", "\n\n", raw_md)
    cleaned = re.sub(r"[-*]{4,}", "---", cleaned)
    cleaned = "\n".join(line.rstrip() for line in cleaned.splitlines())
    cleaned = re.sub(r"\[\s*\]\(\s*\)", "", cleaned)
    return cleaned.strip()


def clean_html_dom(html: str) -> Tuple[BeautifulSoup, Dict[str, str], List[str]]:
    """
    Synchronous helper extracting metadata and tech indicators,
    and decomposing non-content tags.
    """
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""

    meta_desc = ""
    meta_desc_tag = (
        soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        or soup.find("meta", attrs={"property": re.compile(r"^og:description$", re.I)})
    )
    if meta_desc_tag and meta_desc_tag.get("content"):
        meta_desc = meta_desc_tag["content"].strip()

    meta_keys = ""
    meta_keys_tag = soup.find("meta", attrs={"name": re.compile(r"^keywords$", re.I)})
    if meta_keys_tag and meta_keys_tag.get("content"):
        meta_keys = meta_keys_tag["content"].strip()

    tech_signals = detect_tech_signals(soup, raw_html=html)

    # Sanitize in-place
    sanitized = sanitize_dom(soup, target_semantic_container=False)

    metadata = {
        "title": title,
        "meta_description": meta_desc,
        "meta_keywords": meta_keys,
    }
    return soup, metadata, tech_signals


def html_to_clean_markdown(soup: BeautifulSoup) -> str:
    """Synchronous helper converting cleaned soup to markdown."""
    return convert_dom_to_markdown(soup)


# ==============================================================================
# APPAREL DISCOVERY CRAWLER CLASS (ASYNC PLAYWRIGHT)
# ==============================================================================

class ApparelDiscoveryCrawler:
    """
    Asynchronous crawler orchestrating anti-detection headless browsing,
    heuristic link resolution, and targeted content extraction for apparel retail domains.
    """

    def __init__(self, timeout_ms: int = DEFAULT_PAGE_TIMEOUT_MS):
        self.timeout_ms = timeout_ms

    async def init_stealth_context(self, p) -> Tuple[Any, BrowserContext]:
        """Launches a headless Chromium instance configured with evasion flags."""
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = await browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            viewport=VIEWPORT_CONFIG,
            locale="en-US",
            timezone_id="America/New_York",
            ignore_https_errors=True,
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Ch-Ua": '"Chromium";v="133", "Not(A:Brand";v="99"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Upgrade-Insecure-Requests": "1",
            }
        )

        # Inject stealth evasion script
        await context.add_init_script(EVASION_INIT_SCRIPT)
        return browser, context

    async def fetch_page(self, context: BrowserContext, url: str) -> Tuple[str, str, int]:
        """
        Navigates to a URL using domcontentloaded and a brief hydration wait.
        Returns (raw_html, final_url, status_code).
        """
        page: Page = await context.new_page()
        try:
            logger.info(f"Navigating to {url}...")
            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms
            )
            status_code = response.status if response else 0

            # Allow brief client-side hydration for dynamic SPAs
            await page.wait_for_timeout(1000)

            # Scroll to trigger lazy-loaded footers where corporate & press links reside
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)
            except Exception:
                pass

            final_url = page.url
            html = await page.content()
            return html, final_url, status_code
        except PlaywrightTimeoutError:
            logger.warning(f"Timeout occurred loading {url} (after {self.timeout_ms}ms). Capturing partial DOM.")
            html = await page.content()
            return html, page.url, 408
        except Exception as e:
            logger.error(f"Navigation failure on {url}: {e}")
            return "", url, 500
        finally:
            await page.close()

    def discover_target_links(self, base_url: str, html: str) -> Dict[str, List[str]]:
        """
        Discovers and resolves navigation, footer, and body links
        matching press, leadership, and technology heuristic patterns.
        """
        soup = BeautifulSoup(html, "html.parser")
        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc.lower().replace("www.", "")

        discovered: Dict[str, Set[str]] = {
            "press": set(),
            "leadership": set(),
            "technology": set(),
        }

        # Scan all anchors
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            resolved_url = urljoin(base_url, href)
            parsed_res = urlparse(resolved_url)
            resolved_domain = parsed_res.netloc.lower().replace("www.", "")

            # Exclude external domains except corporate/investor subdomains
            if base_domain not in resolved_domain:
                continue

            # Exclude asset files
            if re.search(r"\.(pdf|png|jpg|jpeg|gif|svg|zip|mp4|webp)$", parsed_res.path, re.I):
                continue

            # Check matching against patterns using both href and anchor text
            link_text = a.get_text(" ", strip=True)
            searchable_target = f"{resolved_url} {link_text}"

            for category, pattern in LINK_PATTERNS.items():
                if pattern.search(searchable_target):
                    discovered[category].add(resolved_url)

        return {k: sorted(list(v)) for k, v in discovered.items()}

    def extract_press_releases(self, html: str, page_url: str) -> List[PressReleaseItem]:
        """
        Parses press releases, corporate statements, and earnings articles from a newsroom DOM.
        """
        soup = BeautifulSoup(html, "html.parser")
        press_items: List[PressReleaseItem] = []

        # Look for article blocks or news list items
        article_candidates = soup.find_all(
            ["article", "li", "div"],
            class_=re.compile(r"(press-release|news-item|article-card|media-item|news-release)", re.I)
        )

        if not article_candidates:
            # Fallback to general article tags
            article_candidates = soup.find_all("article")

        for item in article_candidates[:5]:  # Capture top 5 items
            # Title
            title_tag = item.find(["h2", "h3", "h4", "a"])
            title = title_tag.get_text(strip=True) if title_tag else "Corporate Announcement"

            # Link
            link_tag = item.find("a", href=True)
            item_url = urljoin(page_url, link_tag["href"]) if link_tag else page_url

            # Body snippet
            container = sanitize_dom(BeautifulSoup(str(item), "html.parser"), target_semantic_container=False)
            text_md = convert_dom_to_markdown(container)

            if len(text_md) > 40:
                press_items.append(PressReleaseItem(
                    title=title,
                    source_url=item_url,
                    markdown_text=text_md[:2000]  # Store concise summary
                ))

        # Fallback if no individual cards were matched: extract main newsroom page
        if not press_items:
            container = sanitize_dom(soup, target_semantic_container=True)
            text_md = convert_dom_to_markdown(container)
            if text_md:
                press_items.append(PressReleaseItem(
                    title=soup.title.get_text(strip=True) if soup.title else "Newsroom Digest",
                    source_url=page_url,
                    markdown_text=text_md[:4000]
                ))

        return press_items

    async def crawl_apparel_domain(self, domain_or_url: str) -> Dict[str, Any]:
        """
        Executes end-to-end extraction across the target apparel domain:
        1. Crawls homepage, extracts tech signatures and discovers corporate links.
        2. Crawls Leadership/Executive page.
        3. Crawls Press/Newsroom page.
        4. Compiles structured JSON meeting all engineering specifications.
        """
        # Normalize URL
        if not domain_or_url.startswith(("http://", "https://", "file://", "data:")):
            base_url = f"https://{domain_or_url}"
        else:
            base_url = domain_or_url

        parsed_base = urlparse(base_url)
        clean_domain = parsed_base.netloc if parsed_base.netloc else ("local-test" if base_url.startswith("data:") else domain_or_url)

        timestamp = datetime.now(timezone.utc).isoformat()
        logger.info(f"Starting apparel discovery extraction for: {clean_domain} at {timestamp}")

        async with async_playwright() as p:
            browser, context = await self.init_stealth_context(p)

            try:
                # -------------------------------------------------------------
                # STEP 1: Crawl Homepage & Extract Tech Signals
                # -------------------------------------------------------------
                home_html, final_home_url, status = await self.fetch_page(context, base_url)
                if not home_html:
                    logger.error(f"Could not retrieve homepage for {clean_domain}")
                    return {
                        "domain": clean_domain,
                        "crawl_timestamp": timestamp,
                        "error": f"Failed to connect to {base_url} (HTTP {status})",
                    }

                home_soup = BeautifulSoup(home_html, "html.parser")
                tech_signals = detect_tech_signals(home_soup, raw_html=home_html)

                # Classify tech footprint
                ecommerce_platform = "Custom / In-House Headless"
                analytics_tagging: List[str] = []
                detected_frameworks: List[str] = []

                for signal in tech_signals:
                    if signal in ["Shopify Plus", "Salesforce Commerce Cloud (Demandware)", "Adobe Commerce / Magento", "SAP Commerce Cloud (Hybris)", "BigCommerce", "commercetools"]:
                        ecommerce_platform = signal
                    elif signal in ["Google Tag Manager", "Google Analytics 4", "Segment CDP", "Klaviyo", "Braze", "Dynamic Yield", "Criteo", "Adobe Experience Platform / Analytics"]:
                        analytics_tagging.append(signal)
                    else:
                        detected_frameworks.append(signal)

                # Discover candidate corporate sub-URLs
                discovered_links = self.discover_target_links(final_home_url, home_html)
                logger.info(f"Discovered target link candidates for {clean_domain}: {discovered_links}")

                # -------------------------------------------------------------
                # STEP 2: Crawl Leadership / Executive Notes
                # -------------------------------------------------------------
                leadership_content: Dict[str, str] = {
                    "source_url": "",
                    "markdown_text": ""
                }

                if discovered_links["leadership"]:
                    target_lead_url = discovered_links["leadership"][0]
                    logger.info(f"Navigating to Leadership target: {target_lead_url}")
                    lead_html, lead_final_url, _ = await self.fetch_page(context, target_lead_url)
                    if lead_html:
                        lead_soup = BeautifulSoup(lead_html, "html.parser")
                        container = sanitize_dom(lead_soup, target_semantic_container=True)
                        leadership_content["source_url"] = lead_final_url
                        leadership_content["markdown_text"] = convert_dom_to_markdown(container)[:6000]

                # -------------------------------------------------------------
                # STEP 3: Crawl Press Releases & Investor Relations
                # -------------------------------------------------------------
                press_releases: List[Dict[str, str]] = []

                if discovered_links["press"]:
                    target_press_url = discovered_links["press"][0]
                    logger.info(f"Navigating to Press / Newsroom target: {target_press_url}")
                    press_html, press_final_url, _ = await self.fetch_page(context, target_press_url)
                    if press_html:
                        extracted_press = self.extract_press_releases(press_html, press_final_url)
                        press_releases = [item.to_dict() for item in extracted_press]

                # -------------------------------------------------------------
                # STEP 4: Secondary Scan on Careers/Tech page for Stack Footprint
                # -------------------------------------------------------------
                if discovered_links["technology"]:
                    tech_url = discovered_links["technology"][0]
                    logger.info(f"Scanning Technology/Careers page for stack indicators: {tech_url}")
                    tech_html, _, _ = await self.fetch_page(context, tech_url)
                    if tech_html:
                        additional_signals = detect_tech_signals(BeautifulSoup(tech_html, "html.parser"), raw_html=tech_html)
                        for sig in additional_signals:
                            if sig in ["Shopify Plus", "Salesforce Commerce Cloud (Demandware)", "Adobe Commerce / Magento", "SAP Commerce Cloud (Hybris)"]:
                                ecommerce_platform = sig
                            elif sig not in analytics_tagging and sig not in detected_frameworks:
                                detected_frameworks.append(sig)

                # Assemble final aggregated JSON output
                aggregated_output = {
                    "domain": clean_domain,
                    "crawl_timestamp": timestamp,
                    "tech_footprint": {
                        "ecommerce_platform": ecommerce_platform,
                        "analytics_tagging": sorted(list(set(analytics_tagging))),
                        "detected_frameworks": sorted(list(set(detected_frameworks))),
                    },
                    "leadership_content": leadership_content,
                    "press_releases": press_releases,
                }

                return aggregated_output

            finally:
                await context.close()
                await browser.close()


# ==============================================================================
# SYNCHRONOUS BACKWARD COMPATIBILITY BRIDGE (FOR app.py & PIPELINE)
# ==============================================================================

def scrape_retail_site(
    url: str,
    prefer_playwright: bool = True,
    timeout_ms: int = 30000,
) -> ScrapeResult:
    """
    Synchronous entry point compatible with app.py and existing pipeline calls.
    Invokes Playwright synchronously or falls back cleanly to HTTP session.
    """
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"

    def _run_playwright_sync(target_url: str, timeout: int) -> Tuple[str, Dict[str, str], List[str]]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                ignore_https_errors=True,
            )
            page = context.new_page()
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=timeout)
                page.wait_for_timeout(1000)
                raw_html = page.content()
            finally:
                context.close()
                browser.close()

        soup, meta, signals = clean_html_dom(raw_html)
        return raw_html, meta, signals

    if prefer_playwright:
        try:
            try:
                asyncio.get_running_loop()
                in_loop = True
            except RuntimeError:
                in_loop = False

            if in_loop:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    raw_html, metadata, tech_signals = pool.submit(
                        _run_playwright_sync, url, timeout_ms
                    ).result()
            else:
                raw_html, metadata, tech_signals = _run_playwright_sync(url, timeout_ms)

            markdown_content = html_to_clean_markdown(BeautifulSoup(raw_html, "html.parser"))
            return ScrapeResult(
                url=url,
                title=metadata.get("title", ""),
                markdown=markdown_content,
                meta_description=metadata.get("meta_description", ""),
                meta_keywords=metadata.get("meta_keywords", ""),
                tech_signals=tech_signals,
                engine_used="playwright",
                success=True,
            )
        except Exception as e:
            logger.warning(f"Playwright execution note: {e}. Falling back to HTTP requests scraper.")

    # Resilient HTTP fallback
    try:
        session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = session.get(url, headers=headers, timeout=int(timeout_ms / 1000))
        resp.raise_for_status()

        cleaned_soup, metadata, tech_signals = clean_html_dom(resp.text)
        markdown_content = html_to_clean_markdown(cleaned_soup)

        return ScrapeResult(
            url=url,
            title=metadata.get("title", ""),
            markdown=markdown_content,
            meta_description=metadata.get("meta_description", ""),
            meta_keywords=metadata.get("meta_keywords", ""),
            tech_signals=tech_signals,
            engine_used="requests_fallback",
            success=True,
        )
    except Exception as fe:
        return ScrapeResult(
            url=url,
            success=False,
            engine_used="none",
            error_message=str(fe),
        )


# ==============================================================================
# CLI ENTRY POINT & VERIFICATION TEST RUN
# ==============================================================================

async def main():
    """
    CLI execution entry point. Runs extraction against target domain passed
    in argv[1] or defaults to an illustrative apparel enterprise test case.
    """
    target = sys.argv[1] if len(sys.argv) > 1 else "https://target.com"
    logger.info(f"Initiating Apparel Discovery Extraction CLI for: {target}")

    crawler = ApparelDiscoveryCrawler(timeout_ms=30000)
    result = await crawler.crawl_apparel_domain(target)

    print("\n" + "=" * 80)
    print("STRUCTURED APPAREL DISCOVERY EXTRACTION RESULT (JSON)")
    print("=" * 80)
    print(json.dumps(result, indent=2))
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
