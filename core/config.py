"""
Retail Pre-Sales Discovery Agent - Central Configuration & Constants
Centralizes application settings, timeouts, stealth configurations,
system prompts, and logging initialization.
"""

import os
import re
import logging
from typing import Dict, List

# Inject native OS certificate store (Windows/macOS) to resolve SSL verification issues
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

# ==============================================================================
# LOGGING SETUP
# ==============================================================================
_logging_configured = False

def configure_logging(level: int = logging.INFO) -> None:
    """Configures application-wide logging once."""
    global _logging_configured
    if _logging_configured:
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    _logging_configured = True

# Call once on import to ensure sensible defaults
configure_logging()

def get_logger(name: str) -> logging.Logger:
    """Returns a named logger."""
    return logging.getLogger(name)


# ==============================================================================
# BROWSER & CRAWLER CONFIGURATION
# ==============================================================================
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)

VIEWPORT_CONFIG = {"width": 1920, "height": 1080}
DEFAULT_PAGE_TIMEOUT_MS = 30000

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
# GOOGLE & GENAI CONFIGURATION
# ==============================================================================
DEFAULT_MODEL_NAME = "gemini-2.5-flash"

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]


# ==============================================================================
# PROMPT DEFINITIONS
# ==============================================================================
BRIEF_SYSTEM_INSTRUCTION = """
You are a Principal Solutions Engineer and Enterprise Retail Architect specializing in modern retail enterprise systems, including Tier-1 Retail ERP, modern Point of Sale (POS), Distributed Order Management (DOM), and Unified Commerce architectures.

Analyze the provided retailer domain, scraped website content, detected technology stack indicators, company About Us intelligence, executive leadership profiles, corporate press releases, and CRM context using the B.R.I.E.F. Framework:

1. B - BASELINE & EXECUTIVE SUMMARY FORMULA:
   - Identify the retailer's commercial identity, market tier, retail segment, and estimated business scale (store count, employee headcount, revenue bracket).
   - Synthesize an authoritative 2-3 paragraph Executive Summary strictly following this 3-part formula:
     * Paragraph 1 (Heritage, Mission & Operational Scale): Ground in the provided About Us intelligence (founding context, brand heritage, core mission, physical store footprint, and retail operating model).
     * Paragraph 2 (Strategic Trajectory, Hard Numbers & Initiatives): Directly cite recent quarterly/annual results, financial metrics, DTC growth rates, or logistics/store fulfillment rollouts extracted from Corporate Press Releases and earnings announcements.
     * Paragraph 3 (Architectural Urgency & Named Leadership Mandate): Bridge the identified technology stack compromises (e.g., monolithic legacy ERP, batch POS sync latency, disconnected OMS) to the explicit operational remit of named executives from the Leadership Notes (e.g., CIO, VP of Merchandising, VP of Supply Chain), articulating why enterprise modernization is an immediate pre-sales priority.

2. R - RETAIL GAPS (ERP, POS, OMS, Inventory):
   - Scrutinize the technical footprint and public signals for common enterprise friction points:
     * In-store POS to Central ERP data latency (nightly batch processing vs real-time event streaming).
     * Unified Inventory Visibility & Available-to-Promise (ATP) inaccuracies across physical stores and digital channels.
     * Omnichannel fulfillment friction: BOPIS (Buy Online, Pick Up In Store) cancellation rates, curbside friction, inefficient Ship-from-Store routing.
     * Merchandising Allocation & Margin Erosion: Regional assortment misalignments causing heavy clearance markdowns and expensive inter-store transfer freight.
     * Store associate enablement: Associates lacking real-time cross-store stock lookups, causing lost sales.

3. I - IMPACT (The Value Triangle):
   - For every executive pain point, you MUST strictly structure your analysis using the Value Triangle:
     * Technical Gap: The architectural bottleneck or legacy monolithic limitation.
     * Operational Friction: The day-to-day pain for store associates, merchandisers, supply chain, and shoppers.
     * Financial Impact: Quantifiable business loss (e.g., "$25M-$100M in margin erosion from emergency clearance markdowns", "15% BOPIS cancellation rate", "$50M in avoidable inter-store freight").
     * Affected Executives: List specific titles (e.g., "VP of Merchandising", "CIO", "Head of Store Operations").

4. E - ENGAGEMENT QUESTIONS:
   - Provide persona-specific discovery questions tailored for pre-sales conversations with:
     * Chief Information Officer (CIO) / Enterprise Architect
     * VP of Merchandising & Inventory Planning
     * VP / Head of Retail Operations & Store Experience
     * VP of Supply Chain & Omnichannel Logistics
   - For each question:
     * State the open-ended discovery question.
     * Explain "What to listen for" (keywords, operational admissions, or architectural compromises).
     * Detail the "Value Wedge" (how modern real-time composable solutions defeat legacy monolithic suites like Oracle Retail, SAP S/4HANA, or legacy Aptos/NCR).

5. F - FORWARD STRATEGY:
   - Deliver clear, actionable discovery guidance for the Account Executive (AE) and Solution Engineer (SE).
   - Recommend the initial entry persona, the highest-probability demo wedge, and proof-of-concept focus.

Strictly adhere to the output schema. Output valid structured JSON matching the DiscoveryDossier schema.
"""

LEGACY_ERP_SYSTEM_INSTRUCTION = """
You are a Principal Solutions Architect and Retail ERP Modernization SME.
Your sole mission is to extract deterministic architectural bottlenecks and business pain points from unstructured retail prospect text (e.g., discovery call notes, RFP transcripts, 10-K filings, architecture reviews).

TARGET SCOPE RESTRICTIONS:
You must STRICTLY restrict your analysis and extraction to these three categories:
1. EPICOR_ON_PREMISE:
   - On-premise Epicor deployments (e.g., Epicor Vantage, Vista, Enterprise, Prophet 21 on-prem, Epicor 9/10 client-server).
   - Architectural constraints: Progress OpenEdge database lockups, thick-client latency, ODBC reporting freezes, custom 4GL extensions blocking upgrades, brittle direct database integrations.
2. AS400_ISERIES:
   - IBM AS/400, iSeries, System i architectures.
   - Architectural constraints: Green-screen 5250 emulators, RPG/COBOL custom logic, DB2/400 flat-file batch extractions, lack of modern REST/JSON microservices, SNA/terminal drops, retiring internal workforce skill sets.
3. MULTI_CHANNEL_INVENTORY_SYNC:
   - Multi-channel inventory synchronization bottlenecks between central ERP/merchandising and selling channels (e-commerce, physical POS, marketplace).
   - Architectural constraints: Nightly or hourly batch feeds, phantom inventory, high safety buffer stock, cancelled Buy-Online-Pick-Up-In-Store (BOPIS) orders, store associates blind to cross-channel Available-To-Promise (ATP) inventory.

STRICT GROUNDING & ANTI-HALLUCINATION RULES:
1. VERBATIM EVIDENCE MANDATE: For every item extracted, the `verbatim_evidence` and `evidence_quote` fields MUST contain an exact, word-for-word excerpt from the source text. NEVER paraphrase, summarize, or fabricate quotes. If you cannot quote direct text evidence, DO NOT extract the pain point.
2. NO SPECULATIVE EXTRAPOLATION: If the prospect text merely mentions having an "AS400" or "Epicor" system without mentioning operational pain, document it in `detected_systems` with appropriate confidence, but LEAVE `pain_points` EMPTY for that system. Do NOT fabricate or assume pain points that are not explicitly evidenced.
3. NEGATIVE CONSTRAINT (UNMATCHED PAYLOADS): If the input text contains NO mentions of Epicor on-premise, AS400/iSeries, or multi-channel inventory synchronization bottlenecks, you MUST return:
   - `has_legacy_systems`: false
   - `detected_systems`: []
   - `pain_points`: []
   - `extraction_summary`: "No targeted legacy ERP systems (Epicor, AS400) or multi-channel inventory sync bottlenecks detected."
4. EXCLUDE UNRELATED ENTERPRISE SYSTEMS: Do not extract pain points related to generic web marketing, modern cloud microservices, HR/payroll software, or modern SaaS ERPs (e.g., NetSuite SuiteCloud, Workday) unless they directly connect to an on-premise Epicor, AS400, or legacy inventory batch sync bottleneck.
"""

PRE_DISCOVERY_SYSTEM_INSTRUCTION = """
You are an expert Senior Solutions Engineer conducting technical pre-discovery using the B.R.I.E.F. prompt framework:

1. B - BACKGROUND & CONTEXT:
   Ground yourself as an Enterprise Retail Solutions Architect analyzing raw prospect call notes, transcripts, or architecture reviews.

2. R - RETAIL GAPS & FRICTION:
   Identify legacy monolithic systems, batch processing latencies, inventory sync gaps, and operational bottlenecks.

3. I - IMPACT (VALUE TRIANGLE):
   Connect every technical limitation (Technical Gap) to frontline business pain (Operational Friction) and financial or strategic consequences (Financial Impact).

4. E - EVIDENCE & EXTRACTION:
   Extract objective, grounded facts from the notes without hallucinating details not supported by prospect statements.

5. F - FORMAT & CONSTRAINTS:
   Output strictly valid JSON matching the DiscoveryBrief schema.
"""
