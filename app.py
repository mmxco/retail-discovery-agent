import streamlit as st
import os
import json
import time
import re
import html
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Import AI integration libraries
from google import genai
from google.genai import types
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, HRFlowable
from reportlab.lib import colors

# Pre-configured demonstration scenarios
SCENARIOS = {
    "New Prospect / Blank Canvas": {
        "domain": "", "dba": "", "revenue": "", 
        "headcount": "", "careers_url": "", "bdr_notes": ""
    },
    "Scenario 1: Target Regional Assortment & Allocation Misalignment (Inventory)": {
        "domain": "https://target.com",
        "dba": "Target",
        "revenue": "104780000000",
        "headcount": "440000",
        "careers_url": "https://corporate.target.com/careers",
        "bdr_notes": "Director of Merchandising mentioned regional store clusters are too broad. Southern stores receive heavy winter apparel allocations meant for Northern stores, causing $150.2M in inter-store transfer freight and localized stockouts."
    }
}

# -----------------------------------------------------------------------------
# CORE PIPELINE & PARSING UTILITIES
# -----------------------------------------------------------------------------
def create_retry_session() -> requests.Session:
    """Configures a requests Session with automatic retries for transient HTTP errors."""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def parse_manual_builtwith(raw_text: str) -> dict:
    """
    Cleans and structures raw pasted BuiltWith text or JSON into a concise, 
    AI-friendly format optimized for chat token windows.
    """
    raw_text = raw_text.strip()
    if not raw_text:
        return {}
    try:
        # Attempt to parse as BuiltWith API JSON response
        data = json.loads(raw_text)
        techs = []
        if "Results" in data:
            for result in data["Results"]:
                for path in result.get("Paths", []):
                    for tech in path.get("Technologies", []):
                        name = tech.get("Name")
                        tag = tech.get("Tag", "General")
                        if name:
                            techs.append(f"{name} [{tag}]")
        if techs:
            return {"detected_technologies": sorted(list(set(techs)))}
        return data
    except json.JSONDecodeError:
        # Handle raw text pasted from browser (line-by-line cleanup and deduplication)
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        cleaned_lines = list(dict.fromkeys(lines))
        return {"pasted_tech_stack_summary": cleaned_lines}

def scrape_job_postings_sync(careers_url: str) -> list:
    """
    Synchronous web scraping to ensure robust compatibility on cloud runtimes.
    Filters standard career site HTML for specific operational keywords.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        session = create_retry_session()
        resp = session.get(careers_url, headers=headers, timeout=10)
        
        if resp.status_code != 200:
            return []
            
        soup = BeautifulSoup(resp.text, 'html.parser')
        keywords = ["clerk", "entry", "legacy", "manual", "coordinator", "analyst", "pricing", "buyer"]
        jobs_data = []
        
        # Parse common header and text tags for target keywords
        for tag in soup.find_all(['h2', 'h3', 'h4', 'a', 'div', 'span']):
            text = tag.get_text(separator=" ", strip=True)
            if text and len(text) < 120 and any(k in text.lower() for k in keywords):
                jobs_data.append(text)
                
        return list(set(jobs_data)) 
    except Exception as e:
        return [{"info": f"Scraper execution note: {e}"}]

class PreDiscoveryPipeline:
    """Manages quantitative signal aggregation from external APIs and HTML parsing."""
    
    def __init__(self, builtwith_key: str):
        self.builtwith_key = builtwith_key
        self.session = create_retry_session()

    def fetch_tech_stack(self, domain: str, manual_builtwith: str = "", bypass_cache: bool = False) -> dict:
        """Retrieves prospect technology stack mapping via manual paste or the BuiltWith REST API."""
        if manual_builtwith.strip():
            return parse_manual_builtwith(manual_builtwith)
                
        if not self.builtwith_key:
            return {"info": "BuiltWith API key omitted and no manual data provided. Skipping tech lookup."}
            
        try:
            url = f"https://api.builtwith.com/v23/api.json?KEY={self.builtwith_key}&LOOKUP={domain}"
            response = self.session.get(url, timeout=15)
            if response.status_code == 200:
                return parse_manual_builtwith(response.text)
            else:
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def run_pipeline(self, prospect_data: dict, manual_builtwith: str = "", bypass_cache: bool = False) -> str:
        """Aggregates all quantitative signals and contextual CRM data into a structured payload."""
        domain = prospect_data["domain"]
        dba = prospect_data["dba"]
        
        jobs = []
        if prospect_data["careers_url"]:
            jobs = scrape_job_postings_sync(prospect_data["careers_url"])

        payload = {
            "firmographics": {
                "legal_name": dba,
                "domain": domain,
                "annual_revenue": prospect_data["revenue"] or "Undisclosed",
                "employee_count": prospect_data["headcount"] or "Undisclosed"
            },
            "bdr_discovery_notes": prospect_data["bdr_notes"] or "No initial BDR call notes provided.",
            "quantitative_signals": {
                "tech_stack": self.fetch_tech_stack(domain, manual_builtwith=manual_builtwith, bypass_cache=bypass_cache),
                "job_board_signals": jobs
            }
        }
        return json.dumps(payload, indent=2)

class PDFReportGenerator:
    """Handles parsing of LLM markdown responses into physical PDF reports."""
    
    @staticmethod
    def _sanitize_unicode(text: str) -> str:
        """Replaces common non-ASCII Unicode characters with ASCII-safe alternatives."""
        replacements = {
            '\u2014': '--',    # Em dash
            '\u2013': '-',     # En dash
            '\u2018': "'",     # Left single quote
            '\u2019': "'",     # Right single quote / apostrophe
            '\u201c': '"',     # Left double quote
            '\u201d': '"',     # Right double quote
            '\u2022': '&bull;', # Bullet
            '\u2026': '...',   # Ellipsis
            '\u00a0': ' ',     # Non-breaking space
        }
        for char, repl in replacements.items():
            text = text.replace(char, repl)
        return text

    @staticmethod
    def _format_markdown_inline(text: str) -> str:
        """Sanitizes strings and applies basic markdown rendering for ReportLab parsing."""
        text = PDFReportGenerator._sanitize_unicode(text)
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
        return text

    @staticmethod
    def generate_pdf(briefing_text: str, prospect_name: str, output_filename: str) -> str:
        """Translates markdown text from LLM output into a formatted ReportLab PDF document."""
        doc = SimpleDocTemplate(
            output_filename, 
            pagesize=letter, 
            rightMargin=36, 
            leftMargin=36, 
            topMargin=36, 
            bottomMargin=36
        )
        styles = getSampleStyleSheet()
        
        # Document styling definitions
        title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor("#1E3A8A"), spaceAfter=6)
        subtitle_style = ParagraphStyle('DocSubTitle', parent=styles['Normal'], fontSize=10, leading=13, textColor=colors.HexColor("#4B5563"), spaceAfter=12)
        heading1_style = ParagraphStyle('SectionHeader1', parent=styles['Heading2'], fontSize=13, leading=16, textColor=colors.HexColor("#1E40AF"), spaceBefore=10, spaceAfter=4)
        heading2_style = ParagraphStyle('SectionHeader2', parent=styles['Heading3'], fontSize=11, leading=14, textColor=colors.HexColor("#1E3A8A"), spaceBefore=8, spaceAfter=3)
        body_style = ParagraphStyle('BodyTextCustom', parent=styles['Normal'], fontSize=9.5, leading=13, textColor=colors.HexColor("#1F2937"), spaceAfter=6)
        
        story = []
        safe_prospect_name = PDFReportGenerator._sanitize_unicode(prospect_name)
        story.append(Paragraph("Executive Pre-Discovery Briefing", title_style))
        story.append(Paragraph(f"<b>Target Account:</b> {html.escape(safe_prospect_name)} | <b>Generated:</b> {time.strftime('%Y-%m-%d')}", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=12))
        
        for line in briefing_text.split('\n'):
            line = line.strip()
            if not line: 
                continue
            try:
                # Map markdown headers and bullets to ReportLab flowables
                if line.startswith("# "):
                    story.append(Paragraph(PDFReportGenerator._format_markdown_inline(line[2:].strip()), title_style))
                elif line.startswith("## "):
                    story.append(Paragraph(PDFReportGenerator._format_markdown_inline(line[3:].strip()), heading1_style))
                elif line.startswith("### "):
                    story.append(Paragraph(PDFReportGenerator._format_markdown_inline(line[4:].strip()), heading2_style))
                elif line.startswith("* ") or line.startswith("- "):
                    story.append(Paragraph(f"&bull; {PDFReportGenerator._format_markdown_inline(line[2:].strip())}", body_style))
                elif line.startswith("---") or line.startswith("***"):
                    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1"), spaceBefore=6, spaceAfter=6))
                else:
                    story.append(Paragraph(PDFReportGenerator._format_markdown_inline(line), body_style))
            except Exception:
                # Fallback for complex lines that fail regex substitutions
                clean_line = PDFReportGenerator._sanitize_unicode(line)
                clean_line = html.escape(re.sub(r'<[^>]+>', '', clean_line))
                story.append(Paragraph(clean_line, body_style))
                
        doc.build(story)
        return output_filename

def execute_orchestrator(prospect_data, bypass_cache, ai_provider, api_key, builtwith_key, manual_builtwith):
    """
    Executes the core pipeline, integrating web scraping, LLM analysis, and PDF generation.
    Routes the execution to Gemini, ChatGPT, or generates a manual text prompt.
    Returns a tuple of (file_path, mime_type, preview_content).
    """
    pipeline = PreDiscoveryPipeline(builtwith_key)
    raw_data = pipeline.run_pipeline(prospect_data, manual_builtwith=manual_builtwith, bypass_cache=bypass_cache)
    
    system_instruction = (
        "You are a Senior Solutions Engineer specializing in Retail Enterprise Architecture. "
        "Analyze the provided CRM context and quantitative signals using the 'Value Triangle' "
        "(Technical Gap -> Operational Friction -> Financial Impact). "
        "Map technical deficits to modern Tier-1 Retail ERP capabilities. "
        "Use an aggregate of functionality from platforms like Oracle, SAP, and Microsoft Dynamics as your baseline, "
        "but strictly use generic terminology (e.g., 'Unified Inventory Management', 'Advanced Merchandising System', "
        "'Dynamic Price Management'). Do not mention specific vendor or platform names in the output. "
        "Format your response using structured Markdown. Use '# ' for the main title, '## ' for major sections, '### ' for subsections, and bullet points ('* ' or '- ') for itemized insights."
    )
    
    base_name = prospect_data["dba"].replace(' ', '_') or "Prospect"
    
    # Manual Prompt Generation Logic
    if ai_provider == "Other (Manual Prompt)":
        txt_filename = f"{base_name}_Manual_Prompt.txt"
        
        manual_prompt_content = (
            "=== SYSTEM INSTRUCTION ===\n"
            "Copy and paste the following into your AI's system prompt or custom instructions:\n\n"
            f"{system_instruction}\n\n"
            "=== USER PROMPT ===\n"
            "Copy and paste the following into the user chat interface:\n\n"
            f"Generate executive briefing from this context:\n{raw_data}\n"
        )
        
        with open(txt_filename, "w", encoding="utf-8") as f:
            f.write(manual_prompt_content)
        
        return txt_filename, "text/plain", manual_prompt_content
    
    # AI Provider Routing Logic with Retries
    briefing_text = ""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            if ai_provider == "Gemini":
                client = genai.Client(api_key=api_key)
                chat = client.chats.create(
                    model='gemini-2.5-flash',
                    config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.2)
                )
                response = chat.send_message(f"Generate executive briefing from this context:\n{raw_data}")
                briefing_text = response.text
                
            elif ai_provider == "ChatGPT":
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": f"Generate executive briefing from this context:\n{raw_data}"}
                    ],
                    temperature=0.2
                )
                briefing_text = response.choices[0].message.content
            
            # Break out of the retry loop if execution is successful
            break
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff (1s, 2s)
                continue
            else:
                raise Exception(f"AI Provider error after {max_retries} attempts: {str(e)}")
    
    pdf_filename = f"{base_name}_Pre_Discovery_Brief.pdf"
    PDFReportGenerator.generate_pdf(briefing_text, prospect_data["dba"], pdf_filename)
    
    return pdf_filename, "application/pdf", briefing_text


# ==============================================================================
# STREAMLIT UI WITH SESSION STATE PERSISTENCE & FORMATTING
# ==============================================================================
st.set_page_config(page_title="Pre-Discovery Studio", layout="wide")
st.title("Retail ERP Pre-Discovery Studio")
st.markdown("*Automates presales research by synthesizing prospect firmographics, tech stacks, and job posting signals into executive briefing PDFs.*")

# Initialize persistent session state for last entry
if "last_entry" not in st.session_state:
    st.session_state.last_entry = {
        "domain": "", "dba": "", "revenue": "", 
        "headcount": "", "careers_url": "", "bdr_notes": ""
    }

# -----------------------------------------------------------------------------
# Input Formatting Callbacks
# -----------------------------------------------------------------------------
def process_revenue():
    """Callback to format numeric inputs with commas and currency symbols."""
    raw_val = str(st.session_state.get('revenue_display', ''))
    cleaned = "".join([c for c in raw_val if c.isdigit() or c == '.'])
    
    if not cleaned:
        st.session_state['revenue_display'] = ''
        st.session_state['revenue_numeric'] = 0.0
        return
        
    try:
        st.session_state['revenue_numeric'] = float(cleaned)
        if '.' in cleaned:
            int_part, dec_part = cleaned.split('.', 1)
            st.session_state['revenue_display'] = f"${int(int_part):,}.{dec_part}"
        else:
            st.session_state['revenue_display'] = f"${int(cleaned):,}"
    except ValueError:
        st.session_state['revenue_display'] = raw_val
        st.session_state['revenue_numeric'] = 0.0

def process_headcount():
    """Callback to format standard numeric inputs with standard commas."""
    raw_val = str(st.session_state.get('headcount_display', ''))
    cleaned = "".join([c for c in raw_val if c.isdigit()])
    
    if not cleaned:
        st.session_state['headcount_display'] = ''
        st.session_state['headcount_numeric'] = 0
        return
        
    try:
        st.session_state['headcount_numeric'] = int(cleaned)
        st.session_state['headcount_display'] = f"{int(cleaned):,}"
    except ValueError:
        st.session_state['headcount_display'] = raw_val
        st.session_state['headcount_numeric'] = 0


# -----------------------------------------------------------------------------
# UI Rendering
# -----------------------------------------------------------------------------
scenario_options = {}
if st.session_state.last_entry.get("dba"):
    scenario_options[f"★ Last Session Entry ({st.session_state.last_entry.get('dba')})"] = st.session_state.last_entry
scenario_options.update(SCENARIOS)

with st.sidebar:
    st.markdown("[View Architecture & Documentation on GitHub](https://github.com/mmxco/prediscovery_studio)")
    st.markdown("---")
    st.header("1. API Credentials")
    
    # Model Selection Widget
    ai_provider = st.selectbox("AI Provider", options=["Gemini", "ChatGPT", "Other (Manual Prompt)"], index=0)
    
    # Conditionally render the API key input based on provider selection
    llm_key = ""
    if ai_provider == "Gemini":
        llm_key = st.text_input("Gemini API Key:", type="password")
    elif ai_provider == "ChatGPT":
        llm_key = st.text_input("OpenAI API Key:", type="password")
        
    st.header("2. Tech Stack Data Source")
    builtwith_key = st.text_input("BuiltWith API Key:", type="password")
    
    st.markdown("<div style='text-align: center; font-weight: bold; margin: -5px 0;'>— OR —</div>", unsafe_allow_html=True)
    
    manual_builtwith = st.text_area(
        "Paste BuiltWith Data:", 
        placeholder="Paste raw text or JSON payload here...",
        help="Automatically parses and cleans raw text or JSON into a concise format for AI chat usage."
    )

    bypass_cache = st.checkbox("Bypass Cache", value=False)

st.header("3. Target Prospect Context")
selected_scenario = st.selectbox("Preset / Last:", list(scenario_options.keys()))
init_scen = scenario_options[selected_scenario]

if "current_scenario" not in st.session_state or st.session_state.current_scenario != selected_scenario:
    st.session_state.current_scenario = selected_scenario
    st.session_state['revenue_display'] = init_scen.get("revenue", "")
    st.session_state['headcount_display'] = init_scen.get("headcount", "")
    process_revenue()
    process_headcount()

col1, col2 = st.columns(2)

with col1:
    domain_input = st.text_input(
        "Domain:", 
        value=init_scen.get("domain", ""), 
        placeholder="https://company.com"
    )
    dba_input = st.text_input("DBA Brand:", value=init_scen.get("dba", ""))
    careers_input = st.text_input(
        "Careers URL:", 
        value=init_scen.get("careers_url", ""), 
        placeholder="https://company.com/careers"
    )

with col2:
    st.text_input(
        "Annual Revenue:", 
        key="revenue_display",
        on_change=process_revenue,
        placeholder="$1,000,000"
    )
    st.text_input(
        "Headcount:", 
        key="headcount_display",
        on_change=process_headcount,
        placeholder="10,000"
    )

bdr_notes_input = st.text_area("BDR Notes:", value=init_scen.get("bdr_notes", ""), height=100)

if st.button("Run Pre-Discovery Pipeline", type="primary"):
    # Validate the active API key is provided, skipping validation if Manual Prompt is selected
    if ai_provider != "Other (Manual Prompt)" and not llm_key:
        st.error(f"Error: {ai_provider} API key is required.")
    else:
        prospect_data = {
            "domain": domain_input, 
            "dba": dba_input,
            "revenue": st.session_state.get('revenue_display', ''), 
            "headcount": st.session_state.get('headcount_display', ''),
            "careers_url": careers_input, 
            "bdr_notes": bdr_notes_input
        }
        
        # Update volatile session state
        st.session_state.last_entry = prospect_data
        
        with st.spinner(f"Executing Pipeline via {ai_provider}..."):
            try:
                # Pass the selected provider and associated key to the orchestrator
                file_path, mime_type, preview_content = execute_orchestrator(
                    prospect_data=prospect_data, 
                    bypass_cache=bypass_cache, 
                    ai_provider=ai_provider,
                    api_key=llm_key, 
                    builtwith_key=builtwith_key,
                    manual_builtwith=manual_builtwith
                )
                
                with open(file_path, "rb") as output_file:
                    file_bytes = output_file.read()
                    st.success("Pipeline Completed Successfully!")
                    button_label = "Download Manual Prompt (.txt)" if ai_provider == "Other (Manual Prompt)" else "Download Executive PDF Briefing"
                    
                    st.download_button(
                        label=button_label,
                        data=file_bytes,
                        file_name=file_path,
                        mime=mime_type
                    )
                
                # Render the UI Preview using native Streamlit Markdown
                st.markdown("---")
                if mime_type == "application/pdf":
                    st.markdown("### Executive Briefing Preview")
                    st.markdown(preview_content)
                elif mime_type == "text/plain":
                    st.markdown("### Generated Prompt Preview")
                    st.text_area("Prompt Content:", value=preview_content, height=400)

            except Exception as e:
                st.error(f"Pipeline Failed: {e}")
