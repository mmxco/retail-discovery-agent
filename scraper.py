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
import asyncio
from typing import Dict, List, Optional, Any, Set, Tuple
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone

from bs4 import BeautifulSoup, Comment, Tag
from markdownify import markdownify as md
from playwright.async_api import (
    async_playwright,
    Page,
    BrowserContext,
    TimeoutError as PlaywrightTimeoutError,
)

from core.config import (
    get_logger,
    DEFAULT_USER_AGENT,
    VIEWPORT_CONFIG,
    DEFAULT_PAGE_TIMEOUT_MS,
    EVASION_INIT_SCRIPT,
    TECH_SIGNATURES,
    LINK_PATTERNS,
    NOISE_TAGS,
    BOILERPLATE_CLASS_ID_REGEX,
)
from core.models import PressReleaseItem, ScrapeResult

logger = get_logger("ApparelDiscoveryCrawler")

__all__ = [
    "DOMSanitizer",
    "ApparelDiscoveryCrawler",
    "ScrapeResult",
    "PressReleaseItem",
    "detect_tech_signals",
    "sanitize_dom",
    "convert_dom_to_markdown",
    "clean_html_dom",
    "html_to_clean_markdown",
    "check_playwright_availability",
    "restart_playwright",
    "scrape_retail_site",
    "run_async",
    "BeautifulSoup",
]


# ==============================================================================
# ASYNC EXECUTION RUNNER WITH THREAD POOL FALLBACK FOR SYNC CALLERS
# ==============================================================================

def run_async(coro):
    """
    Safely executes an async coroutine across synchronous and asynchronous contexts
    using a thread pool fallback if an event loop is already active.
    Zero sync_playwright usage.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


# ==============================================================================
# TECH FOOTPRINT DETECTION
# ==============================================================================

def detect_tech_signals(soup: BeautifulSoup, raw_html: str = "") -> List[str]:
    """
    Scans HTML script sources, stylesheet links, meta tags, and inline text
    for tell-tale enterprise retail platform signatures before DOM stripping.
    """
    detected: Set[str] = set()

    sources_to_check: List[str] = []

    # 1. Script sources and inline snippets
    for s in soup.find_all("script"):
        src = s.get("src")
        if src:
            sources_to_check.append(src)
        if s.string:
            sources_to_check.append(s.string[:2000])

    # 2. Link tags (stylesheets, preconnects, CDNs)
    for link in soup.find_all("link"):
        href = link.get("href")
        if href:
            sources_to_check.append(href)

    # 3. Meta tags (generator, powered-by, platform indicators)
    for meta in soup.find_all("meta"):
        content = meta.get("content")
        if content:
            sources_to_check.append(content)

    combined_text = "\n".join(sources_to_check)
    if raw_html:
        combined_text += "\n" + raw_html[:150000]

    for tech_name, patterns in TECH_SIGNATURES.items():
        for pat in patterns:
            if re.search(pat, combined_text, re.I):
                detected.add(tech_name)
                break

    return sorted(list(detected))


# ==============================================================================
# UNIFIED DOM SANITIZER PIPELINE
# ==============================================================================

class DOMSanitizer:
    """
    Consolidated DOM Sanitizer Pipeline.
    Unifies noise extraction, boilerplate/modal removal, semantic container targeting,
    metadata extraction, and Markdown transformation into a cohesive pipeline.
    """

    @classmethod
    def sanitize(cls, soup: BeautifulSoup, target_semantic_container: bool = True) -> Tag:
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

    @classmethod
    def to_markdown(cls, container: Tag) -> str:
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

    @classmethod
    def clean_html(cls, html: str) -> Tuple[BeautifulSoup, Dict[str, str], List[str]]:
        """
        Extracts metadata, detects tech indicators, and sanitizes non-content tags in-place.
        Returns (sanitized_soup, metadata_dict, tech_signals_list).
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
        cls.sanitize(soup, target_semantic_container=False)

        metadata = {
            "title": title,
            "meta_description": meta_desc,
            "meta_keywords": meta_keys,
        }
        return soup, metadata, tech_signals

    @classmethod
    def html_to_markdown(cls, soup: BeautifulSoup) -> str:
        """Converts cleaned soup to markdown."""
        return cls.to_markdown(soup)


# Module-level aliases for backward compatibility
sanitize_dom = DOMSanitizer.sanitize
convert_dom_to_markdown = DOMSanitizer.to_markdown
clean_html_dom = DOMSanitizer.clean_html
html_to_clean_markdown = DOMSanitizer.html_to_markdown


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
        Navigates to a URL using domcontentloaded and hydration wait.
        Returns (raw_html, final_url, status_code).
        """
        page: Page = await context.new_page()
        effective_timeout = custom_timeout_ms if custom_timeout_ms is not None else self.timeout_ms
        try:
            if url.startswith("http://") and not url.startswith("http://127.0.0.1") and not url.startswith("http://localhost"):
                url = "https://" + url[7:]

            logger.info(f"Navigating to {url} (timeout: {effective_timeout}ms)...")
            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=effective_timeout
            )
            status_code = response.status if response else 0

            # Handle WAF/Bot verification challenges
            for _ in range(6):
                html_check = await page.content()
                if "istlWasHere" not in html_check and len(html_check) > 300000:
                    break
                await page.wait_for_timeout(1000)

            # Dynamic SPA client-side hydration
            await page.wait_for_timeout(2500)

            # Scroll to trigger lazy-loaded footers
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

        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            resolved_url = urljoin(base_url, href)
            parsed_res = urlparse(resolved_url)
            resolved_domain = parsed_res.netloc.lower().replace("www.", "")
            resolved_root = get_root_domain(resolved_domain)

            if base_root != resolved_root and base_domain not in resolved_domain and resolved_domain not in base_domain:
                continue

            if re.search(r"\.(pdf|png|jpg|jpeg|gif|svg|zip|mp4|webp)$", parsed_res.path, re.I):
                continue

            link_text = a.get_text(" ", strip=True)
            searchable_target = f"{resolved_url} {link_text}"
            norm_path = parsed_res.path.rstrip("/").lower()
            norm_path_clean = re.sub(r"\.html?$", "", norm_path)
            norm_text = link_text.lower()

            for category, pattern in LINK_PATTERNS.items():
                if pattern.search(searchable_target):
                    if category == "about" and LINK_PATTERNS["leadership"].search(searchable_target):
                        continue

                    score = 10
                    if category == "about":
                        if norm_path_clean in ["/about", "/about-us", "/our-story", "/browse/about", "/who-we-are", "/about/our-story", "/purpose"]:
                            score += 100
                        if norm_text in ["about us", "about", "our story", "who we are", "about nordstrom", "about our company", "about walmart"]:
                            score += 80
                        elif "about" in norm_text:
                            score += 40

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
                        if norm_path_clean in ["/press", "/press-releases", "/newsroom", "/news-releases", "/investors/press-releases", "/news", "/corporate/news", "/media"]:
                            score += 100
                        elif norm_path_clean.endswith(("/newsroom", "/press-releases", "/news")):
                            score += 80
                        if norm_text in ["press releases", "newsroom", "press", "media center", "news", "view newsroom"]:
                            score += 80
                        elif "newsroom" in norm_text or "press release" in norm_text:
                            score += 40

                        if re.search(r"/\d{4}/\d{2}/", norm_path):
                            score -= 50

                    discovered_candidates[category].append((score, resolved_url))

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
        """Extracts narrative and key facts from an About Us DOM."""
        soup = BeautifulSoup(html, "html.parser")
        container = DOMSanitizer.sanitize(soup, target_semantic_container=True)
        text_md = DOMSanitizer.to_markdown(container)[:6000]

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
        """Parses press releases, corporate statements, and earnings articles from a newsroom DOM."""
        soup = BeautifulSoup(html, "html.parser")
        press_items: List[PressReleaseItem] = []

        article_candidates = soup.find_all("article")
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

            clean_item_soup = BeautifulSoup(str(item), "html.parser")
            for tag in list(clean_item_soup.find_all(["script", "style", "svg", "button", "input", "form"])):
                if not getattr(tag, "decomposed", False):
                    try:
                        tag.decompose()
                    except Exception:
                        pass
            text_md = DOMSanitizer.to_markdown(clean_item_soup).strip()

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

        if not press_items:
            container = DOMSanitizer.sanitize(soup, target_semantic_container=True)
            text_md = DOMSanitizer.to_markdown(container)
            if text_md:
                press_items.append(PressReleaseItem(
                    title=soup.title.get_text(strip=True) if soup.title else "Newsroom Digest",
                    source_url=page_url,
                    markdown_text=text_md[:4000]
                ))

        return press_items

    async def crawl_apparel_domain(self, domain_or_url: str) -> Dict[str, Any]:
        """
        Executes end-to-end extraction across the target apparel domain using async_playwright.
        """
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
                # STEP 1: Crawl Homepage & Extract Tech Signals
                home_html, final_home_url, status = await self.fetch_page(context, base_url)
                if not home_html:
                    logger.error(f"Could not retrieve homepage for {clean_domain}")
                    return {
                        "domain": clean_domain,
                        "crawl_timestamp": timestamp,
                        "error": f"Failed to connect to {base_url} (HTTP {status})",
                    }

                home_soup, home_metadata, tech_signals = DOMSanitizer.clean_html(home_html)
                home_markdown = DOMSanitizer.html_to_markdown(home_soup)

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

                discovered_links = self.discover_target_links(final_home_url, home_html)
                logger.info(f"Discovered target link candidates for {clean_domain}: {discovered_links}")

                # STEP 2: Crawl About Us & Company Overview
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

                # STEP 3: Crawl Leadership
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
                            container = DOMSanitizer.sanitize(lead_soup, target_semantic_container=True)
                            md_text = DOMSanitizer.to_markdown(container)[:6000]
                            if md_text:
                                leadership_content["source_url"] = lead_final_url
                                leadership_content["markdown_text"] = md_text
                                break

                # STEP 4: Crawl Press Releases
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

                # STEP 5: Secondary Scan on Careers/Tech page
                if discovered_links.get("technology"):
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

                # Assemble aggregated output
                return {
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

            finally:
                await context.close()
                await browser.close()


# ==============================================================================
# PLAYWRIGHT HEALTH & RESTART UTILITIES (ASYNC, ZERO SYNC_PLAYWRIGHT)
# ==============================================================================

async def _async_check_playwright() -> Tuple[bool, str]:
    """Asynchronously launches a Chromium browser to verify Playwright availability."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                ]
            )
            await browser.close()
        return True, "Playwright Headless Browser is operational."
    except Exception as err:
        return False, f"Playwright Headless Browser unavailable: {err}"


def check_playwright_availability() -> Tuple[bool, str]:
    """
    Verifies that Playwright is installed and Chromium Headless Browser can launch.
    Runs async execution cleanly without sync_playwright.
    """
    return run_async(_async_check_playwright())


def restart_playwright() -> Tuple[bool, str]:
    """Attempts to reinstall/repair Playwright Chromium browser binaries."""
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
# SINGLE-PAGE ASYNC SCRAPER HELPER
# ==============================================================================

async def _async_single_page_scrape(target_url: str, timeout: int) -> Tuple[str, Dict[str, str], List[str]]:
    """Single-page async scraper using async_playwright."""
    async with async_playwright() as p:
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
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            ignore_https_errors=True,
        )
        page = await context.new_page()
        raw_html = ""
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout)
            await page.wait_for_timeout(1000)
            raw_html = await page.content()
        except Exception as nav_err:
            logger.warning(
                f"Playwright navigation timeout or error on {target_url} (timeout: {timeout}ms): {nav_err}. "
                "Attempting partial content capture..."
            )
            try:
                raw_html = await page.content()
            except Exception:
                raw_html = ""
        finally:
            await context.close()
            await browser.close()

    soup, meta, signals = DOMSanitizer.clean_html(raw_html)
    markdown_text = DOMSanitizer.to_markdown(soup)
    return markdown_text, meta, signals


# ==============================================================================
# SYNCHRONOUS ENTRY POINT FOR PIPELINE (ZERO SYNC_PLAYWRIGHT)
# ==============================================================================

def scrape_retail_site(
    url: str,
    prefer_playwright: bool = True,
    timeout_ms: int = 30000,
    deep_crawl: bool = True,
) -> ScrapeResult:
    """
    Synchronous entry point compatible with app.py and pipeline calls.
    Runs entirely on async_playwright with thread pool fallback for sync callers.
    Zero sync_playwright invocations.
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

    # 1. Preferred Path: Full Multi-Page Deep Crawl via async crawler
    if deep_crawl:
        try:
            crawler = ApparelDiscoveryCrawler(timeout_ms=timeout_ms)
            crawl_data = run_async(crawler.crawl_apparel_domain(url))

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
    try:
        markdown_content, metadata, tech_signals = run_async(
            _async_single_page_scrape(url, timeout_ms)
        )

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


async def main():
    """CLI execution entry point."""
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
