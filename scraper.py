"""
Enterprise Retail Scraper Module
Playwright-powered scraper engineered to extract core DOM content from retail
e-commerce, corporate, and career sites, strip non-content elements, and convert
the DOM into clean, token-efficient Markdown using markdownify.
Includes automatic fallback to HTTP session for zero-failure resilience.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup, Comment
from markdownify import markdownify as md

# Configure module logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# User-Agent representing a modern enterprise desktop browser
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)

# Known retail tech footprints to scan in script/link tags prior to DOM stripping
TECH_SIGNATURES = {
    "Shopify / Shopify Plus": [r"cdn\.shopify\.com", r"Shopify\.", r"myshopify\.com"],
    "Salesforce Commerce Cloud (Demandware)": [r"demandware\.net", r"demandware\.static", r"dw\.js"],
    "Magento / Adobe Commerce": [r"mage\/", r"magento", r"static\/_requirejs"],
    "SAP Commerce Cloud (Hybris)": [r"hybris", r"sap-commerce", r"occ\/v2"],
    "Oracle Retail / ATG / NetSuite": [r"atg\.js", r"oracle\.com\/retail", r"netsuite\.com", r"elqCfg"],
    "BigCommerce": [r"cdn11\.bigcommerce\.com", r"bigcommerce\.com"],
    "commercetools": [r"commercetools", r"commercetools\.com"],
    "Manhattan Associates": [r"manh\.com", r"manhattan"],
    "Google Analytics 4 / GTM": [r"googletagmanager\.com\/gtm\.js", r"google-analytics\.com\/analytics\.js", r"gtag\("],
    "Segment CDP": [r"cdn\.segment\.com\/analytics\.js", r"analytics\.load\("],
    "Klaviyo": [r"static\.klaviyo\.com", r"klaviyo\.js"],
    "Braze": [r"js\.appboycdn\.com", r"braze\.min\.js"],
    "Algolia Search": [r"algolia\.net", r"algoliasearch"],
    "Constructor.io": [r"cnstrc\.com"],
    "Bloomreach": [r"bloomreach\.com", r"brsrvr\.com"],
    "Yotpo": [r"staticw2\.yotpo\.com"],
    "Bazaarvoice": [r"bazaarvoice\.com", r"bvapi\.js"],
}


@dataclass
class ScrapeResult:
    """Structured result returned by the scraper pipeline."""
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
        """Returns a summarized dictionary suitable for LLM analysis ingestion."""
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


def detect_tech_signals(soup: BeautifulSoup) -> List[str]:
    """
    Scans HTML script sources, stylesheet links, and meta tags for
    tell-tale enterprise retail platform signatures before DOM stripping.
    """
    detected: set[str] = set()

    # Inspect all script and link tags
    raw_indicators: List[str] = []
    for s in soup.find_all(["script", "link"]):
        src = s.get("src") or s.get("href") or ""
        if src:
            raw_indicators.append(src)
        if s.string:
            raw_indicators.append(s.string[:200])

    combined_text = " ".join(raw_indicators)

    for platform, patterns in TECH_SIGNATURES.items():
        for pat in patterns:
            if re.search(pat, combined_text, re.IGNORECASE):
                detected.add(platform)
                break

    return sorted(list(detected))


def clean_html_dom(html: str) -> tuple[BeautifulSoup, Dict[str, str], List[str]]:
    """
    Parses raw HTML, extracts metadata and tech indicators, decomposes
    non-content tags (<nav>, <footer>, <script>, etc.), and returns the cleaned DOM.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. Extract metadata before decomposing anything
    title = soup.title.get_text(strip=True) if soup.title else ""

    meta_desc = ""
    meta_desc_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)}) or \
                     soup.find("meta", attrs={"property": re.compile(r"^og:description$", re.I)})
    if meta_desc_tag and meta_desc_tag.get("content"):
        meta_desc = meta_desc_tag["content"].strip()

    meta_keys = ""
    meta_keys_tag = soup.find("meta", attrs={"name": re.compile(r"^keywords$", re.I)})
    if meta_keys_tag and meta_keys_tag.get("content"):
        meta_keys = meta_keys_tag["content"].strip()

    # 2. Extract technical signatures from scripts and links
    tech_signals = detect_tech_signals(soup)

    # 3. Strip HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # 4. Decompose non-content and layout tags completely (tag + children)
    non_content_tags = [
        "nav", "footer", "script", "style", "noscript", "svg", "aside",
        "iframe", "canvas", "video", "audio", "form", "button", "input",
        "select", "textarea", "dialog", "header"
    ]
    for tag in soup.find_all(non_content_tags):
        tag.decompose()

    # 5. Decompose common boilerplate/cookie/modal containers
    boilerplate_patterns = re.compile(
        r"(cookie|consent|banner|popup|modal|overlay|onetrust|gdpr|newsletter|subscribe|toast)",
        re.I
    )
    for element in soup.find_all(["div", "section", "aside", "span"]):
        class_str = " ".join(element.get("class", [])) if isinstance(element.get("class"), list) else ""
        elem_id = element.get("id", "")
        role = element.get("role", "")
        if boilerplate_patterns.search(class_str) or boilerplate_patterns.search(elem_id) or role in ["banner", "alertdialog"]:
            element.decompose()

    metadata = {
        "title": title,
        "meta_description": meta_desc,
        "meta_keywords": meta_keys,
    }
    return soup, metadata, tech_signals


def html_to_clean_markdown(soup: BeautifulSoup) -> str:
    """
    Converts a cleaned BeautifulSoup DOM tree into normalized, readable Markdown
    using markdownify with custom ATX headers and noise reduction.
    """
    raw_markdown = md(
        str(soup),
        heading_style="ATX",
        strip=["img", "button", "input", "form", "svg"],
    )

    # Post-process Markdown to eliminate whitespace bloat
    # 1. Replace 3+ consecutive newlines with 2
    cleaned = re.sub(r"\n{3,}", "\n\n", raw_markdown)
    # 2. Collapse horizontal rules or dashes greater than 3
    cleaned = re.sub(r"[-*]{4,}", "---", cleaned)
    # 3. Clean up lines with only whitespace
    cleaned = "\n".join(line.rstrip() for line in cleaned.splitlines())
    # 4. Remove empty brackets like []() or [ ]
    cleaned = re.sub(r"\[\s*\]\(\s*\)", "", cleaned)
    # 5. Trim leading and trailing whitespace
    return cleaned.strip()


def scrape_with_playwright(url: str, timeout_ms: int = 30000) -> ScrapeResult:
    """
    Executes headless Playwright Chromium rendering to capture dynamic,
    JavaScript-hydrated retail storefront DOM.
    """
    from playwright.sync_api import sync_playwright

    logger.info(f"Launching Playwright Chromium for {url}")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
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
            # Navigate with domcontentloaded for fast reliable load
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            status_code = response.status if response else None
            
            # Short wait for any client-side JavaScript hydration (1.5 seconds)
            page.wait_for_timeout(1500)
            
            raw_html = page.content()
        finally:
            context.close()
            browser.close()

    cleaned_soup, metadata, tech_signals = clean_html_dom(raw_html)
    markdown_content = html_to_clean_markdown(cleaned_soup)

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


def scrape_with_requests(url: str, timeout: int = 15) -> ScrapeResult:
    """
    Resilient HTTP fallback using requests with exponential retry logic.
    Used when Playwright browser runtime is unavailable or encounters critical errors.
    """
    logger.info(f"Executing HTTP fallback scraper for {url}")
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

    resp = session.get(url, headers=headers, timeout=timeout)
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


def scrape_retail_site(
    url: str,
    prefer_playwright: bool = True,
    timeout_ms: int = 30000,
) -> ScrapeResult:
    """
    Main entry point for scraping retail prospect websites.
    Executes Playwright with clean DOM stripping and Markdown conversion,
    falling back seamlessly to HTTP requests on transient failure.
    """
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"

    if prefer_playwright:
        try:
            return scrape_with_playwright(url, timeout_ms=timeout_ms)
        except Exception as e:
            logger.warning(
                f"Playwright scrape failed for {url} ({e}). Falling back to HTTP requests scraper."
            )
            try:
                fallback_res = scrape_with_requests(url, timeout=int(timeout_ms / 1000))
                fallback_res.error_message = f"Playwright error: {str(e)}"
                return fallback_res
            except Exception as fe:
                logger.error(f"HTTP fallback scraper also failed for {url}: {fe}")
                return ScrapeResult(
                    url=url,
                    success=False,
                    engine_used="none",
                    error_message=f"Playwright error: {str(e)} | HTTP error: {str(fe)}",
                )
    else:
        try:
            return scrape_with_requests(url, timeout=int(timeout_ms / 1000))
        except Exception as e:
            return ScrapeResult(
                url=url,
                success=False,
                engine_used="requests",
                error_message=str(e),
            )
