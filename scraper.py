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
    # E-Commerce Engines & CMS
    "Shopify Plus": [r"cdn\.shopify\.com", r"Shopify\.", r"myshopify\.com", r"shopify-buy"],
    "Salesforce Commerce Cloud (Demandware)": [r"demandware\.net", r"demandware\.static", r"dw\.js", r"dwac_"],
    "Adobe Commerce / Magento": [r"(?<![a-zA-Z])mage\/", r"magento", r"static\/_requirejs", r"mage-translation-dictionary"],
    "Adobe Experience Manager (AEM)": [r"/etc\.clientlibs/", r"/etc/designs/", r"cq:template", r"aem-Grid", r"cmp-container"],
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
    "about": re.compile(
        r"(about-us|about-company|about-our-company|about-the-company|our-story|who-we-are|company-overview|heritage|our-history|about-brand|our-heritage|about|purpose)",
        re.I
    ),
    "press": re.compile(
        r"(press|newsroom|news-releases|press-releases|investor|investors|media-center|corporate-news|(?<![a-zA-Z])news(?![a-zA-Z]))",
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
    r"(cookie|consent|banner|popup|modal|overlay|onetrust|gdpr|newsletter|subscribe|toast|alertdialog|"
    r"experiencefragment--header|experiencefragment--footer|walmart-hub-header|site-header|site-footer|"
    r"global-header|global-footer|navbar|nav-wrapper|links-wrapper|hamburger|FooterWc|footer-container|header-container)",
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
    """Structured result returned by the scraping bridge."""
    url: str
    title: str = ""
    markdown: str = ""
    meta_description: str = ""
    meta_keywords: str = ""
    tech_signals: List[str] = field(default_factory=list)
    about_us_content: Dict[str, Any] = field(default_factory=dict)
    leadership_content: Dict[str, Any] = field(default_factory=dict)
    press_releases: List[Dict[str, str]] = field(default_factory=list)
    crawl_payload: Dict[str, Any] = field(default_factory=dict)
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
            "about_us_content": self.about_us_content,
            "leadership_content": self.leadership_content,
            "press_releases": self.press_releases,
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
    Decomposes noise, boilerplate, navigation, and modal elements while preserving primary semantic content.
    Returns the target semantic container or body tag.
    """
    # 1. Remove HTML comments
    for comment in list(soup.find_all(string=lambda text: isinstance(text, Comment))):
        try:
            comment.extract()
        except Exception:
            pass

    # 2. Decompose noise tags completely
    for tag in list(soup.find_all(NOISE_TAGS)):
        if getattr(tag, "decomposed", False):
            continue
        try:
            tag.decompose()
        except Exception:
            pass

    # 3. Decompose cookie/consent/modal banners and corporate header/footer wrappers
    for element in list(soup.find_all(["div", "section", "aside", "span", "nav", "header", "footer"])):
        if getattr(element, "decomposed", False) or getattr(element, "attrs", None) is None:
            continue
        class_val = element.attrs.get("class", [])
        class_str = " ".join(class_val) if isinstance(class_val, list) else str(class_val)
        elem_id = str(element.attrs.get("id", ""))
        role = str(element.attrs.get("role", ""))
        if (
            BOILERPLATE_CLASS_ID_REGEX.search(class_str)
            or BOILERPLATE_CLASS_ID_REGEX.search(elem_id)
            or role in ["banner", "alertdialog", "navigation", "contentinfo"]
        ):
            try:
                element.decompose()
            except Exception:
                pass

    # 4. Remove skip-to navigation links
    for a in list(soup.find_all("a")):
        if getattr(a, "decomposed", False) or getattr(a, "attrs", None) is None:
            continue
        href = str(a.attrs.get("href", ""))
        txt = a.get_text(strip=True).lower()
        if href.startswith(("#skip", "#main-content", "#content")) or "skip to" in txt:
            try:
                a.decompose()
            except Exception:
                pass

    # 5. Target semantic content container if requested
    if target_semantic_container:
        candidates = [
            soup.find("main"),
            soup.find("article"),
            soup.find(id=re.compile(r"^(content|main|news-content|article-body|press-body|leadership-content)$", re.I)),
            soup.find(class_=re.compile(r"^(main-content|article-content|news-body|press-releases|page-content|content-container)$", re.I)),
            soup.find("div", attrs={"role": "main"}),
        ]
        for candidate in candidates:
            if (
                candidate
                and getattr(candidate, "attrs", None) is not None
                and not getattr(candidate, "decomposed", False)
                and len(candidate.get_text(strip=True)) > 150
            ):
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
    if not title:
        og_title = (
            soup.find("meta", attrs={"property": re.compile(r"^og:title$", re.I)})
            or soup.find("meta", attrs={"name": re.compile(r"^twitter:title$", re.I)})
        )
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()

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
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

        # Inject stealth evasion script
        await context.add_init_script(EVASION_INIT_SCRIPT)
        return browser, context

    async def fetch_page(self, context: BrowserContext, url: str, custom_timeout_ms: Optional[int] = None) -> Tuple[str, str, int]:
        """
        Navigates to a URL using domcontentloaded and a brief hydration wait.
        Handles WAF bot-verification interstitials (e.g. Imperva istlWasHere)
        and scrolls to trigger lazy-loaded footers where corporate links reside.
        Returns (raw_html, final_url, status_code).
        """
        page: Page = await context.new_page()
        effective_timeout = custom_timeout_ms if custom_timeout_ms is not None else self.timeout_ms
        try:
            # Upgrade insecure HTTP links to HTTPS to avoid HTTP2 protocol errors
            if url.startswith("http://") and not url.startswith("http://127.0.0.1") and not url.startswith("http://localhost"):
                url = "https://" + url[7:]

            logger.info(f"Navigating to {url} (timeout: {effective_timeout}ms)...")
            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=effective_timeout
            )
            status_code = response.status if response else 0

            # 1. Handle WAF/Bot verification challenges (e.g., Imperva istlWasHere, Cloudflare, PerimeterX)
            for _ in range(6):
                html_check = await page.content()
                if "istlWasHere" not in html_check and len(html_check) > 300000:
                    break
                await page.wait_for_timeout(1000)

            # 2. Allow dynamic SPA client-side hydration (critical for React/Next.js mounting)
            await page.wait_for_timeout(2500)

            # 3. Scroll to trigger lazy-loaded footers where corporate & press links reside
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2500)
            except Exception:
                pass

            final_url = page.url
            html = await page.content()
            return html, final_url, status_code
        except PlaywrightTimeoutError:
            logger.warning(f"Timeout occurred loading {url} (after {effective_timeout}ms). Capturing partial DOM.")
            try:
                html = await page.content()
            except Exception:
                html = ""
            return html, page.url, 408
        except Exception as e:
            logger.error(f"Navigation failure on {url}: {e}")
            return "", url, 500
        finally:
            await page.close()

    def discover_target_links(self, base_url: str, html: str) -> Dict[str, List[str]]:
        """
        Discovers and resolves navigation, footer, and body links
        matching about, press, leadership, and technology heuristic patterns.
        Ranks candidates so parent landing pages are prioritized over sub-features.
        """
        soup = BeautifulSoup(html, "html.parser")
        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc.lower().replace("www.", "")

        def get_root_domain(dom: str) -> str:
            parts = dom.split(".")
            if len(parts) >= 2:
                return ".".join(parts[-2:])
            return dom

        base_root = get_root_domain(base_domain)

        discovered_candidates: Dict[str, List[Tuple[int, str]]] = {
            "about": [],
            "press": [],
            "leadership": [],
            "technology": [],
        }

        # Scan all anchors
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            resolved_url = urljoin(base_url, href)
            parsed_res = urlparse(resolved_url)
            resolved_domain = parsed_res.netloc.lower().replace("www.", "")
            resolved_root = get_root_domain(resolved_domain)

            # Exclude external domains, but allow same root domain (e.g. corporate.walmart.com and investors.walmart.com)
            if base_root != resolved_root and base_domain not in resolved_domain and resolved_domain not in base_domain:
                continue

            # Exclude asset files
            if re.search(r"\.(pdf|png|jpg|jpeg|gif|svg|zip|mp4|webp)$", parsed_res.path, re.I):
                continue

            # Check matching against patterns using both href and anchor text
            link_text = a.get_text(" ", strip=True)
            searchable_target = f"{resolved_url} {link_text}"
            norm_path = parsed_res.path.rstrip("/").lower()
            norm_path_clean = re.sub(r"\.html?$", "", norm_path)
            norm_text = link_text.lower()

            for category, pattern in LINK_PATTERNS.items():
                if pattern.search(searchable_target):
                    # Disambiguate: don't classify leadership links as generic about-us
                    if category == "about" and LINK_PATTERNS["leadership"].search(searchable_target):
                        continue

                    # Score candidate priority (higher score = better primary match)
                    score = 10
                    if category == "about":
                        # Ideal About Us root landing pages (like /browse/about, /about-us, /about, /our-story, /purpose)
                        if norm_path_clean in ["/about", "/about-us", "/our-story", "/browse/about", "/who-we-are", "/about/our-story", "/purpose"]:
                            score += 100
                        if norm_text in ["about us", "about", "our story", "who we are", "about nordstrom", "about our company", "about walmart"]:
                            score += 80
                        elif "about" in norm_text:
                            score += 40

                        # Penalize peripheral sub-features
                        if re.search(r"(podcast|restaurant|spa|app|media-network|credit|card|socialmedia|career|job|press|investor)", norm_path, re.I):
                            score -= 70
                        if re.search(r"(podcast|restaurant|spa|app|media network|card|rewards)", norm_text, re.I):
                            score -= 70

                    elif category == "leadership":
                        if norm_path_clean in ["/leadership", "/our-team", "/our-leadership", "/about-us/team", "/executives", "/board-of-directors", "/about/leadership", "/about/board-of-directors"]:
                            score += 100
                        elif norm_path_clean.endswith(("/leadership", "/executives", "/board-of-directors")):
                            score += 80
                        if norm_text in ["leadership", "our leaders", "executive team", "board of directors", "our team", "executives"]:
                            score += 80

                    elif category == "press":
                        # Ideal Newsroom / Press root landing pages
                        if norm_path_clean in ["/press", "/press-releases", "/newsroom", "/news-releases", "/investors/press-releases", "/news", "/corporate/news", "/media"]:
                            score += 100
                        elif norm_path_clean.endswith(("/newsroom", "/press-releases", "/news")):
                            score += 80
                        if norm_text in ["press releases", "newsroom", "press", "media center", "news", "view newsroom"]:
                            score += 80
                        elif "newsroom" in norm_text or "press release" in norm_text:
                            score += 40

                        # Penalize deep dated individual articles so root newsroom is selected
                        if re.search(r"/\d{4}/\d{2}/", norm_path):
                            score -= 50

                    discovered_candidates[category].append((score, resolved_url))

        # Sort each category by score descending, then deduplicate preserving highest score
        result: Dict[str, List[str]] = {}
        for cat, items in discovered_candidates.items():
            items.sort(key=lambda x: x[0], reverse=True)
            seen: Set[str] = set()
            ranked_urls: List[str] = []
            for score, u in items:
                if u not in seen:
                    seen.add(u)
                    ranked_urls.append(u)
            result[cat] = ranked_urls

        return result

    def extract_about_us(self, html: str, page_url: str) -> Dict[str, Any]:
        """
        Extracts narrative and key milestone/company facts from an About Us DOM.
        Returns a dict with source_url, markdown_text, and structured key_facts.
        """
        soup = BeautifulSoup(html, "html.parser")
        container = sanitize_dom(soup, target_semantic_container=True)
        text_md = convert_dom_to_markdown(container)[:6000]

        # Extract structured key facts, milestones, or core statistics
        key_facts: List[str] = []
        fact_patterns = re.compile(
            r"(founded|headquarter|stores|locations|employees|associates|heritage|mission|since\s+\d{4}|\b\d{4}\b|revenue|global|distribution|channels)",
            re.I
        )

        for elem in container.find_all(["li", "p"]):
            text = elem.get_text(" ", strip=True)
            sentences = re.split(r"(?<=[.!?])\s+", text) if len(text) > 400 else [text]
            for s in sentences:
                line = s.strip()
                if 25 <= len(line) <= 450 and fact_patterns.search(line):
                    cleaned_line = re.sub(r"\s+", " ", line).strip()
                    if cleaned_line not in key_facts:
                        key_facts.append(cleaned_line)
                    if len(key_facts) >= 8:
                        break
            if len(key_facts) >= 8:
                break

        return {
            "source_url": page_url,
            "markdown_text": text_md,
            "key_facts": key_facts[:8],
        }

    def extract_press_releases(self, html: str, page_url: str) -> List[PressReleaseItem]:
        """
        Parses press releases, corporate statements, and earnings articles from a newsroom DOM.
        """
        soup = BeautifulSoup(html, "html.parser")
        press_items: List[PressReleaseItem] = []

        # 1. First look for semantic <article> tags
        article_candidates = soup.find_all("article")

        # 2. If insufficient <article> tags, look for cards/items with news classes
        if len(article_candidates) < 2:
            class_candidates = soup.find_all(
                ["article", "li", "div"],
                class_=re.compile(r"(press-release|news-item|article-card|media-item|news-release|newsroom-card)", re.I)
            )
            if class_candidates:
                article_candidates = class_candidates

        seen_urls: Set[str] = set()
        seen_titles: Set[str] = set()

        for item in article_candidates:
            if getattr(item, "decomposed", False) or getattr(item, "attrs", None) is None:
                continue

            # Title: search headings first to avoid capturing empty thumbnail/icon anchors
            title = ""
            for heading_tag in item.find_all(["h1", "h2", "h3", "h4", "h5"]):
                t = heading_tag.get_text(" ", strip=True)
                if t and len(t) > 5 and "placeholder" not in t.lower():
                    title = t
                    break

            if not title:
                for a_tag in item.find_all("a", href=True):
                    t = a_tag.get_text(" ", strip=True)
                    if t and len(t) > 5 and "placeholder" not in t.lower():
                        title = t
                        break

            if not title or "placeholder" in title.lower():
                continue

            # Link: resolve target URL, preferring anchor with text
            item_url = page_url
            for a_tag in item.find_all("a", href=True):
                href = a_tag.get("href", "").strip()
                if href and not href.startswith("#") and not href.endswith(".html#"):
                    resolved = urljoin(page_url, href)
                    if a_tag.get_text(strip=True):
                        item_url = resolved
                        break
                    elif item_url == page_url:
                        item_url = resolved

            if item_url in seen_urls or title.lower() in seen_titles:
                continue

            # Body snippet
            clean_item_soup = BeautifulSoup(str(item), "html.parser")
            for tag in list(clean_item_soup.find_all(["script", "style", "svg", "button", "input", "form"])):
                if not getattr(tag, "decomposed", False):
                    try:
                        tag.decompose()
                    except Exception:
                        pass
            text_md = convert_dom_to_markdown(clean_item_soup).strip()

            if len(text_md) > 25:
                seen_urls.add(item_url)
                seen_titles.add(title.lower())
                press_items.append(PressReleaseItem(
                    title=title,
                    source_url=item_url,
                    markdown_text=text_md[:2000]
                ))

            if len(press_items) >= 5:
                break

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
        2. Crawls About Us / Company Overview page.
        3. Crawls Leadership/Executive page.
        4. Crawls Press/Newsroom page.
        5. Compiles structured JSON meeting all engineering specifications.
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

                # Extract tech signals, metadata, and clean markdown from homepage
                home_soup, home_metadata, tech_signals = clean_html_dom(home_html)
                home_markdown = html_to_clean_markdown(home_soup)

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

                # Discover candidate corporate sub-URLs from raw DOM before decomposition
                discovered_links = self.discover_target_links(final_home_url, home_html)
                logger.info(f"Discovered target link candidates for {clean_domain}: {discovered_links}")

                # -------------------------------------------------------------
                # STEP 2: Crawl About Us & Company Overview
                # -------------------------------------------------------------
                about_us_content: Dict[str, Any] = {
                    "source_url": "",
                    "markdown_text": "",
                    "key_facts": []
                }

                subpage_timeout = min(self.timeout_ms, 15000)

                if discovered_links.get("about"):
                    for target_about_url in discovered_links["about"][:2]:
                        logger.info(f"Navigating to About Us target: {target_about_url}")
                        about_html, about_final_url, _ = await self.fetch_page(context, target_about_url, custom_timeout_ms=subpage_timeout)
                        if about_html:
                            candidate_data = self.extract_about_us(about_html, about_final_url)
                            if candidate_data.get("markdown_text"):
                                about_us_content = candidate_data
                                break

                # -------------------------------------------------------------
                # STEP 3: Crawl Leadership / Executive Notes
                # -------------------------------------------------------------
                leadership_content: Dict[str, str] = {
                    "source_url": "",
                    "markdown_text": ""
                }

                if discovered_links.get("leadership"):
                    for target_lead_url in discovered_links["leadership"][:2]:
                        logger.info(f"Navigating to Leadership target: {target_lead_url}")
                        lead_html, lead_final_url, _ = await self.fetch_page(context, target_lead_url, custom_timeout_ms=subpage_timeout)
                        if lead_html:
                            lead_soup = BeautifulSoup(lead_html, "html.parser")
                            container = sanitize_dom(lead_soup, target_semantic_container=True)
                            md_text = convert_dom_to_markdown(container)[:6000]
                            if md_text:
                                leadership_content["source_url"] = lead_final_url
                                leadership_content["markdown_text"] = md_text
                                break

                # -------------------------------------------------------------
                # STEP 4: Crawl Press Releases & Investor Relations
                # -------------------------------------------------------------
                press_releases: List[Dict[str, str]] = []

                if discovered_links.get("press"):
                    for target_press_url in discovered_links["press"][:2]:
                        logger.info(f"Navigating to Press / Newsroom target: {target_press_url}")
                        press_html, press_final_url, _ = await self.fetch_page(context, target_press_url, custom_timeout_ms=subpage_timeout)
                        if press_html:
                            extracted_press = self.extract_press_releases(press_html, press_final_url)
                            if extracted_press:
                                press_releases = [item.to_dict() for item in extracted_press]
                                break

                # -------------------------------------------------------------
                # STEP 5: Secondary Scan on Careers/Tech page for Stack Footprint
                # -------------------------------------------------------------
                if discovered_links["technology"]:
                    tech_url = discovered_links["technology"][0]
                    logger.info(f"Scanning Technology/Careers page for stack indicators: {tech_url}")
                    tech_html, _, _ = await self.fetch_page(context, tech_url, custom_timeout_ms=subpage_timeout)
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
                    "page_title": home_metadata.get("title", ""),
                    "meta_description": home_metadata.get("meta_description", ""),
                    "tech_footprint": {
                        "ecommerce_platform": ecommerce_platform,
                        "analytics_tagging": sorted(list(set(analytics_tagging))),
                        "detected_frameworks": sorted(list(set(detected_frameworks))),
                    },
                    "homepage_content": {
                        "source_url": final_home_url,
                        "char_count": len(home_markdown),
                        "markdown_text": home_markdown[:6000],
                    },
                    "about_us_content": about_us_content,
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
# PLAYWRIGHT HEALTH & RESTART UTILITIES
# ==============================================================================

def check_playwright_availability() -> Tuple[bool, str]:
    """
    Verifies that Playwright is installed and Chromium Headless Browser can launch.
    Returns (True, message) if operational, or (False, error_reason) if unavailable.
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                ]
            )
            browser.close()
        return True, "Playwright Headless Browser is operational."
    except Exception as err:
        return False, f"Playwright Headless Browser unavailable: {err}"


def restart_playwright() -> Tuple[bool, str]:
    """
    Attempts to reinstall/repair Playwright Chromium browser binaries.
    """
    import subprocess
    try:
        res = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if res.returncode == 0:
            return True, "Playwright Chromium browser binaries successfully reinstalled/restarted."
        else:
            return False, f"Playwright restart failed with code {res.returncode}: {res.stderr or res.stdout}"
    except Exception as err:
        return False, f"Playwright restart process failed: {err}"


# ==============================================================================
# SYNCHRONOUS ENTRY POINT FOR PIPELINE (STRICT PLAYWRIGHT HEADLESS)
# ==============================================================================

def scrape_retail_site(
    url: str,
    prefer_playwright: bool = True,
    timeout_ms: int = 30000,
    deep_crawl: bool = True,
) -> ScrapeResult:
    """
    Synchronous entry point compatible with app.py and pipeline calls.
    Strictly uses Playwright Headless Browser for multi-page apparel discovery or
    single-page extraction. Does not fall back to plain HTTP requests.
    """
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"

    # Verify Playwright availability
    pw_ok, pw_msg = check_playwright_availability()
    if not pw_ok:
        logger.error(f"Playwright Headless Browser unavailable for URL {url}: {pw_msg}")
        return ScrapeResult(
            url=url,
            success=False,
            engine_used="none",
            error_message=f"Playwright Headless Browser is unavailable: {pw_msg}",
        )

    # 1. Preferred Path: Full Multi-Page Deep Crawl via Playwright
    if deep_crawl:
        try:
            crawler = ApparelDiscoveryCrawler(timeout_ms=timeout_ms)
            try:
                asyncio.get_running_loop()
                in_loop = True
            except RuntimeError:
                in_loop = False

            if in_loop:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    crawl_data = pool.submit(
                        asyncio.run, crawler.crawl_apparel_domain(url)
                    ).result()
            else:
                crawl_data = asyncio.run(crawler.crawl_apparel_domain(url))

            if not crawl_data.get("error"):
                tech_fp = crawl_data.get("tech_footprint", {})
                detected_sigs = set(
                    tech_fp.get("analytics_tagging", [])
                    + tech_fp.get("detected_frameworks", [])
                )
                if tech_fp.get("ecommerce_platform") and tech_fp["ecommerce_platform"] != "Custom / In-House Headless":
                    detected_sigs.add(tech_fp["ecommerce_platform"])

                return ScrapeResult(
                    url=url,
                    title=crawl_data.get("page_title", ""),
                    markdown=crawl_data.get("homepage_content", {}).get("markdown_text", ""),
                    meta_description=crawl_data.get("meta_description", ""),
                    meta_keywords="",
                    tech_signals=sorted(list(detected_sigs)),
                    about_us_content=crawl_data.get("about_us_content", {}),
                    leadership_content=crawl_data.get("leadership_content", {}),
                    press_releases=crawl_data.get("press_releases", []),
                    crawl_payload=crawl_data,
                    engine_used="playwright_deep_crawler",
                    success=True,
                )
        except Exception as deep_err:
            logger.warning(f"Deep crawl execution note: {deep_err}. Attempting single-page Playwright...")

    # 2. Targeted Single-Page Playwright Scraper
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
            raw_html = ""
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=timeout)
                page.wait_for_timeout(1000)
                raw_html = page.content()
            except Exception as nav_err:
                logger.warning(
                    f"Playwright sync navigation timeout or error on {target_url} (timeout: {timeout}ms): {nav_err}. "
                    "Attempting partial content capture..."
                )
                try:
                    raw_html = page.content()
                except Exception:
                    raw_html = ""
            finally:
                context.close()
                browser.close()

        soup, meta, signals = clean_html_dom(raw_html)
        markdown_text = html_to_clean_markdown(soup)
        return markdown_text, meta, signals

    try:
        try:
            asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False

        if in_loop:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                markdown_content, metadata, tech_signals = pool.submit(
                    _run_playwright_sync, url, timeout_ms
                ).result()
        else:
            markdown_content, metadata, tech_signals = _run_playwright_sync(url, timeout_ms)

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
        logger.error(f"Playwright Headless Browser execution error: {e}")
        return ScrapeResult(
            url=url,
            success=False,
            engine_used="playwright",
            error_message=f"Playwright Headless Browser failed to render page: {e}",
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
