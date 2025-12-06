"""
AI Classification Service using Azure OpenAI GPT-4o.

Handles both Stage 1 (quick classification by Event Name) and
Stage 2 (deep document analysis).

Features:
- Intelligent HTML parsing to extract just RFP table content
- Token limit management with chunking
- Comprehensive logging with metrics
"""

import json
import logging
import re
import time
from typing import Any
from datetime import datetime

from openai import AzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from shared.config import get_settings
from shared.models import ExtractedRFP, OpportunityCategory, DeepAnalysisResult

logger = logging.getLogger(__name__)


def normalize_category(raw_category: str, is_relevant: bool = False) -> OpportunityCategory:
    """
    Normalize AI-returned category strings to valid OpportunityCategory enum values.

    Handles various formats GPT might return like "AI", "Artificial Intelligence", "ai", etc.
    """
    if not raw_category:
        return OpportunityCategory.NOT_RELEVANT if not is_relevant else OpportunityCategory.OTHER

    # Convert to lowercase for matching
    cat_lower = raw_category.lower().strip()

    # Direct enum match
    try:
        return OpportunityCategory(cat_lower)
    except ValueError:
        pass

    # Mapping for common variations
    category_mappings = {
        # AI variations
        "artificial intelligence": OpportunityCategory.AI,
        "machine learning": OpportunityCategory.AI,
        "ml": OpportunityCategory.AI,
        "gen ai": OpportunityCategory.AI,
        "generative ai": OpportunityCategory.AI,
        "chatbot": OpportunityCategory.AI,
        "nlp": OpportunityCategory.AI,

        # Dynamics variations
        "microsoft dynamics": OpportunityCategory.DYNAMICS,
        "dynamics 365": OpportunityCategory.DYNAMICS,
        "d365": OpportunityCategory.DYNAMICS,
        "crm": OpportunityCategory.DYNAMICS,
        "power platform": OpportunityCategory.DYNAMICS,

        # ERP variations
        "enterprise resource planning": OpportunityCategory.ERP,
        "sap": OpportunityCategory.ERP,
        "oracle": OpportunityCategory.ERP,
        "financial system": OpportunityCategory.ERP,
        "data management": OpportunityCategory.ERP,

        # IoT variations
        "internet of things": OpportunityCategory.IOT,
        "smart city": OpportunityCategory.IOT,
        "smart building": OpportunityCategory.IOT,
        "sensors": OpportunityCategory.IOT,

        # Staff augmentation variations
        "it staffing": OpportunityCategory.STAFF_AUGMENTATION,
        "staffing": OpportunityCategory.STAFF_AUGMENTATION,
        "consulting": OpportunityCategory.STAFF_AUGMENTATION,
        "professional services": OpportunityCategory.STAFF_AUGMENTATION,

        # Cloud variations
        "cloud services": OpportunityCategory.CLOUD,
        "azure": OpportunityCategory.CLOUD,
        "aws": OpportunityCategory.CLOUD,
        "cloud infrastructure": OpportunityCategory.CLOUD,
        "saas": OpportunityCategory.CLOUD,
        "contact center": OpportunityCategory.CLOUD,

        # Cybersecurity variations
        "security": OpportunityCategory.CYBERSECURITY,
        "infosec": OpportunityCategory.CYBERSECURITY,
        "information security": OpportunityCategory.CYBERSECURITY,
        "risk management": OpportunityCategory.CYBERSECURITY,

        # Data analytics variations
        "business intelligence": OpportunityCategory.DATA_ANALYTICS,
        "bi": OpportunityCategory.DATA_ANALYTICS,
        "analytics": OpportunityCategory.DATA_ANALYTICS,
        "data warehouse": OpportunityCategory.DATA_ANALYTICS,
        "reporting": OpportunityCategory.DATA_ANALYTICS,

        # Not relevant
        "not relevant": OpportunityCategory.NOT_RELEVANT,
        "not_relevant": OpportunityCategory.NOT_RELEVANT,
    }

    # Check for partial matches
    for key, category in category_mappings.items():
        if key in cat_lower or cat_lower in key:
            return category

    # Default based on relevance
    return OpportunityCategory.OTHER if is_relevant else OpportunityCategory.NOT_RELEVANT


# Approximate tokens per character (for GPT-4)
CHARS_PER_TOKEN = 4
MAX_INPUT_TOKENS = 100000  # GPT-4o-128k input limit (leaving buffer for response)
MAX_CHUNK_TOKENS = 25000  # Process in chunks of ~25k tokens

# Target categories for classification
TARGET_CATEGORIES = """
1. Microsoft Dynamics - Microsoft Dynamics 365, CRM, ERP, Power Platform, Business Central
2. Artificial Intelligence (AI) - AI, Machine Learning, ML, NLP, Computer Vision, Chatbots, Generative AI
3. Internet of Things (IoT) - IoT, Smart Devices, Sensors, Connected Systems, Smart City, Smart Building
4. Enterprise Resource Planning (ERP) - ERP, SAP, Oracle, NetSuite, Financial Systems, Supply Chain
5. Staff Augmentation - IT Staffing, Technical Consultants, Contract Developers, Professional Services
6. Cloud Services - Azure, AWS, Cloud Migration, Cloud Infrastructure, SaaS, PaaS
7. Cybersecurity - Security, Infosec, SOC, SIEM, Penetration Testing, Compliance
8. Data Analytics - BI, Business Intelligence, Data Warehouse, Reporting, Power BI, Tableau
"""

STAGE1_SYSTEM_PROMPT = """You are an expert RFP analyst for MazikUSA, a technology company. Your task is to extract RFP/RFQ/RFI opportunities and classify their relevance.

CORE BUSINESS FOCUS (mark as RELEVANT if opportunity relates to):
1. Microsoft Dynamics 365 - CRM, ERP, Power Platform, Business Central, D365 implementations → category: "dynamics"
2. Artificial Intelligence (AI) - Machine Learning, NLP, Chatbots, AI Agents, Generative AI, predictive analytics → category: "ai"
3. Internet of Things (IoT) - Smart devices, sensors, connected systems, smart city/building solutions → category: "iot"
4. Enterprise Resource Planning (ERP) - SAP, Oracle, financial systems, supply chain management → category: "erp"
5. Staff Augmentation - IT staffing, technical consultants, software developers, professional IT services → category: "staff_augmentation"

ALSO CONSIDER RELEVANT:
- Cloud services and infrastructure (Azure, AWS) → category: "cloud"
- Business intelligence and data analytics platforms → category: "data_analytics"
- Cybersecurity and IT security solutions → category: "cybersecurity"
- Software development and system integration projects → choose most appropriate category above, or "other"

MARK AS NOT RELEVANT (category: "not_relevant"):
- Construction, building maintenance, janitorial services
- Medical equipment, pharmaceuticals, healthcare staffing
- Vehicles, transportation, landscaping
- Food services, printing, office supplies
- Inspections (electrical, building) unless IT-related

VALID CATEGORY VALUES (use EXACT lowercase values):
"dynamics", "ai", "iot", "erp", "staff_augmentation", "cloud", "cybersecurity", "data_analytics", "other", "not_relevant"

CLASSIFICATION THRESHOLD:
- Use confidence >= 0.65 for borderline cases (balanced approach)
- Be inclusive for technology-adjacent opportunities
- When uncertain, lean towards RELEVANT if there's any IT/software component

Extract ALL opportunities from the page content. For each opportunity provide:
- document_id, event_name, document_url, event_start_date, response_due_date, last_updated
- is_relevant (true/false), predicted_category (MUST be one of the exact values above), classification_confidence (0.0-1.0), classification_reason

Respond with valid JSON:
{
  "opportunities": [...],
  "total_found": N,
  "relevant_count": N,
  "page_summary": "Brief summary"
}
"""


class AIClassifierService:
    """Service for AI-powered RFP classification using Azure OpenAI."""

    def __init__(self):
        settings = get_settings()
        self.client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self.deployment = settings.azure_openai_deployment

    def _log_step(self, step_num: int, step_name: str, status: str,
                  duration: float = None, metrics: dict = None):
        """Log a processing step with standardized format."""
        timestamp = datetime.utcnow().isoformat()
        log_msg = f"[Step {step_num}] {step_name}: {status}"
        if duration is not None:
            log_msg += f" (duration: {duration:.2f}s)"
        if metrics:
            metrics_str = ", ".join(f"{k}={v}" for k, v in metrics.items())
            log_msg += f" | {metrics_str}"
        logger.info(f"{timestamp} - {log_msg}")

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return len(text) // CHARS_PER_TOKEN

    def _extract_rfp_table_content(self, html_content: str) -> str:
        """
        Extract just the RFP table content from HTML, reducing token usage.

        This intelligently extracts the procurement opportunities table
        rather than sending the entire HTML page to GPT-4.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("BeautifulSoup not available, using raw HTML")
            return html_content

        step_start = time.time()
        self._log_step(7, "HTML Parsing", "started", metrics={"raw_html_chars": len(html_content)})

        soup = BeautifulSoup(html_content, 'html.parser')

        # Strategy 1: Find the main RFP table
        tables = soup.find_all('table')
        rfp_table = None

        for table in tables:
            # Check if table contains RFP-related headers
            headers = table.find_all(['th', 'td'])
            header_text = ' '.join(h.get_text(strip=True).lower() for h in headers[:10])
            if any(term in header_text for term in ['document id', 'event name', 'rfp', 'due date', 'response']):
                rfp_table = table
                break

        if rfp_table:
            # Extract table as clean text
            rows = rfp_table.find_all('tr')
            table_content = []

            for row in rows:
                cells = row.find_all(['th', 'td'])
                row_data = []
                for cell in cells:
                    # Get text and preserve links
                    links = cell.find_all('a', href=True)
                    cell_text = cell.get_text(strip=True)
                    if links:
                        for link in links:
                            href = link.get('href', '')
                            if href and not href.startswith('#'):
                                # Make relative URLs absolute
                                if href.startswith('/'):
                                    href = 'https://www.tn.gov' + href
                                cell_text += f" [URL: {href}]"
                    row_data.append(cell_text)
                table_content.append(' | '.join(row_data))

            extracted = '\n'.join(table_content)

            duration = time.time() - step_start
            self._log_step(7, "HTML Parsing", "completed", duration=duration,
                          metrics={"rows_found": len(rows), "extracted_chars": len(extracted)})

            # === ENHANCED LOGGING: EXTRACTED TABLE CONTENT ===
            logger.info("\n" + "-" * 50)
            logger.info("--- EXTRACTED RFP TABLE CONTENT ---")
            logger.info(f"Table rows found: {len(rows)}")
            logger.info(f"Extracted content size: {len(extracted):,} characters")
            logger.info(f"Estimated tokens: {self._estimate_tokens(extracted):,}")
            # Show preview of first 3 rows
            preview_rows = table_content[:4]  # Header + first 3 data rows
            logger.info("Content Preview (first 3 rows):")
            for i, row in enumerate(preview_rows):
                logger.info(f"  Row {i}: {row[:100]}...")
            logger.info("-" * 50 + "\n")

            return extracted

        # Strategy 2: Extract main content area
        main = soup.find('main') or soup.find('article') or soup.find('div', id='main-content')
        if main:
            # Remove scripts, styles, nav, footer
            for tag in main.find_all(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()

            extracted = main.get_text(separator='\n', strip=True)
            duration = time.time() - step_start
            self._log_step(7, "HTML Parsing", "completed (main content)", duration=duration,
                          metrics={"extracted_chars": len(extracted)})
            return extracted

        # Fallback: Return cleaned HTML
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()

        extracted = soup.get_text(separator='\n', strip=True)
        duration = time.time() - step_start
        self._log_step(7, "HTML Parsing", "completed (fallback)", duration=duration,
                      metrics={"extracted_chars": len(extracted)})
        return extracted

    def _chunk_content(self, content: str, max_tokens: int = MAX_CHUNK_TOKENS) -> list[str]:
        """Split content into chunks that fit within token limits."""
        max_chars = max_tokens * CHARS_PER_TOKEN

        if len(content) <= max_chars:
            return [content]

        # Split by lines to preserve row integrity
        lines = content.split('\n')
        chunks = []
        current_chunk = []
        current_size = 0

        for line in lines:
            line_size = len(line) + 1  # +1 for newline
            if current_size + line_size > max_chars and current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = [line]
                current_size = line_size
            else:
                current_chunk.append(line)
                current_size += line_size

        if current_chunk:
            chunks.append('\n'.join(current_chunk))

        logger.info(f"Content split into {len(chunks)} chunks for processing")
        return chunks

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True
    )
    def _classify_chunk(self, content: str, url: str, chunk_num: int = 1,
                        total_chunks: int = 1) -> list[dict]:
        """Classify a single chunk of content."""
        chunk_prompt = STAGE1_SYSTEM_PROMPT
        if total_chunks > 1:
            chunk_prompt += f"\n\nNOTE: This is chunk {chunk_num} of {total_chunks}. Extract all opportunities from this chunk."

        est_tokens = self._estimate_tokens(content)
        self._log_step(8, "Azure OpenAI API Call", "started",
                      metrics={"chunk": f"{chunk_num}/{total_chunks}", "est_tokens": est_tokens})

        api_start = time.time()
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": chunk_prompt},
                {"role": "user", "content": f"Source URL: {url}\n\nContent:\n{content}"}
            ],
            temperature=0.1,
            max_tokens=16000,  # Increased for larger responses with many opportunities
            response_format={"type": "json_object"}
        )
        api_duration = time.time() - api_start

        result = json.loads(response.choices[0].message.content)
        opps = result.get("opportunities", [])

        self._log_step(9, "Azure OpenAI Response", "received", duration=api_duration,
                      metrics={"opportunities_in_chunk": len(opps)})

        # === ENHANCED LOGGING: STAGE 1 AI CLASSIFICATION ===
        logger.info("\n" + "=" * 70)
        logger.info(f"=== STEP 2: STAGE 1 AI CLASSIFICATION (Chunk {chunk_num}/{total_chunks}) ===")
        logger.info("=" * 70)
        logger.info(f"Total opportunities found in chunk: {len(opps)}")

        relevant_opps = [o for o in opps if o.get("is_relevant", False)]
        not_relevant_opps = [o for o in opps if not o.get("is_relevant", False)]

        logger.info(f"Classified as RELEVANT: {len(relevant_opps)}")
        logger.info(f"Classified as NOT RELEVANT: {len(not_relevant_opps)}")

        # Show relevant opportunities
        if relevant_opps:
            logger.info("\n--- RELEVANT OPPORTUNITIES ---")
            for i, opp in enumerate(relevant_opps, 1):
                logger.info(f"  [{i}] {opp.get('document_id', 'N/A')}: {opp.get('event_name', 'N/A')}")
                logger.info(f"      Category: {opp.get('predicted_category', 'N/A')} | Confidence: {opp.get('classification_confidence', 0):.2f}")
                logger.info(f"      Reason: {opp.get('classification_reason', 'N/A')[:80]}...")
                logger.info(f"      Due Date: {opp.get('response_due_date', 'N/A')}")

        # Show not relevant opportunities (summarized)
        if not_relevant_opps:
            logger.info("\n--- NOT RELEVANT OPPORTUNITIES ---")
            for i, opp in enumerate(not_relevant_opps, 1):
                logger.info(f"  [{i}] {opp.get('document_id', 'N/A')}: {opp.get('event_name', 'N/A')[:50]}...")
                logger.info(f"      Reason: {opp.get('classification_reason', 'N/A')[:60]}...")

        logger.info("=" * 70 + "\n")

        return opps

    def extract_and_classify_page(self, html_content: str, url: str) -> list[ExtractedRFP]:
        """
        Stage 1: Extract RFPs from HTML and classify by Event Name.

        Features:
        - Intelligent HTML parsing to extract just RFP data
        - Token limit management with automatic chunking
        - Comprehensive logging at each step

        Args:
            html_content: Raw HTML from the procurement page
            url: Source URL for context

        Returns:
            List of ExtractedRFP with classification
        """
        total_start = time.time()
        self._log_step(6, "AI Classification", "started",
                      metrics={"url": url, "html_chars": len(html_content)})

        # Extract just the RFP content from HTML
        extracted_content = self._extract_rfp_table_content(html_content)

        est_tokens = self._estimate_tokens(extracted_content)
        self._log_step(7, "Content Extraction", "completed",
                      metrics={"extracted_chars": len(extracted_content), "est_tokens": est_tokens})

        # Chunk if needed
        chunks = self._chunk_content(extracted_content)

        all_opportunities = []
        try:
            for i, chunk in enumerate(chunks, 1):
                chunk_opps = self._classify_chunk(chunk, url, i, len(chunks))
                all_opportunities.extend(chunk_opps)

            # Deduplicate by document_id
            seen_ids = set()
            unique_opps = []
            for opp in all_opportunities:
                doc_id = opp.get("document_id", "")
                if doc_id and doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    unique_opps.append(opp)
                elif not doc_id:
                    unique_opps.append(opp)

            # Convert to ExtractedRFP objects
            opportunities = []
            for opp in unique_opps:
                is_relevant = opp.get("is_relevant", False)
                raw_category = opp.get("predicted_category", "not_relevant")

                # Use normalization function to handle various category formats
                category = normalize_category(raw_category, is_relevant)

                logger.debug(f"Category normalization: '{raw_category}' -> '{category.value}' (relevant={is_relevant})")

                extracted = ExtractedRFP(
                    document_id=opp.get("document_id", ""),
                    event_name=opp.get("event_name", ""),
                    document_url=opp.get("document_url"),
                    event_start_date=opp.get("event_start_date"),
                    response_due_date=opp.get("response_due_date"),
                    last_updated=opp.get("last_updated"),
                    is_relevant=is_relevant,
                    predicted_category=category,
                    classification_confidence=float(opp.get("classification_confidence", 0.0)),
                    classification_reason=opp.get("classification_reason", "")
                )
                opportunities.append(extracted)

            relevant_count = sum(1 for o in opportunities if o.is_relevant)
            total_duration = time.time() - total_start

            self._log_step(10, "Classification Results", "completed", duration=total_duration,
                          metrics={
                              "total_found": len(opportunities),
                              "relevant": relevant_count,
                              "not_relevant": len(opportunities) - relevant_count
                          })

            return opportunities

        except Exception as e:
            logger.error(f"Failed to analyze page: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True
    )
    def deep_analyze_document(self, document_text: str, rfp: ExtractedRFP) -> DeepAnalysisResult:
        """
        Stage 2: Deep analysis of downloaded RFP document.

        Args:
            document_text: Extracted text from PDF/DOCX
            rfp: The RFP metadata from Stage 1

        Returns:
            DeepAnalysisResult with full analysis
        """
        logger.info(f"Deep analyzing document: {rfp.document_id}")

        # Truncate if too large
        max_chars = 80000  # ~20k tokens
        if len(document_text) > max_chars:
            document_text = document_text[:max_chars] + "\n... [document truncated]"

        system_prompt = f"""You are an expert RFP analyst. Analyze this RFP document and extract key information.

TARGET CATEGORIES:
{TARGET_CATEGORIES}

RFP METADATA:
- Document ID: {rfp.document_id}
- Event Name: {rfp.event_name}
- Initial Category: {rfp.predicted_category.value}
- Response Due: {rfp.response_due_date}

Analyze the document and respond with a JSON object:
{{
  "confirmed_category": "dynamics|ai|iot|erp|staff_augmentation|cloud|cybersecurity|data_analytics|other|not_relevant",
  "category_confidence": 0.95,
  "summary": "2-3 sentence summary",
  "scope_of_work": "Detailed scope description",
  "estimated_value": 500000.00 or null,
  "requires_prequalification": true/false,
  "prequalification_details": [{{"requirement": "...", "mandatory": true/false}}],
  "eligibility_requirements": "Who can apply",
  "certifications_required": ["ISO 27001", "SOC 2"],
  "is_discretionary": true/false,
  "discretionary_reason": "Below $50k threshold" or null,
  "contact_info": {{"name": "...", "email": "...", "phone": "..."}},
  "submission_deadline": "2026-02-20T17:00:00" or null,
  "prequalification_deadline": "2026-01-15T17:00:00" or null,
  "key_requirements": ["Requirement 1", "Requirement 2"],
  "technology_stack": ["Azure", "Power Platform"]
}}
"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"RFP Document Content:\n\n{document_text}"}
                ],
                temperature=0.1,
                max_tokens=4000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)

            # Parse and normalize category
            raw_category = result.get("confirmed_category", "not_relevant")
            category = normalize_category(raw_category, is_relevant=True)
            logger.info(f"Stage 2 category normalization: '{raw_category}' -> '{category.value}'")

            return DeepAnalysisResult(
                confirmed_category=category,
                category_confidence=float(result.get("category_confidence", 0.0)),
                summary=result.get("summary", ""),
                scope_of_work=result.get("scope_of_work"),
                estimated_value=result.get("estimated_value"),
                requires_prequalification=result.get("requires_prequalification", False),
                prequalification_details=result.get("prequalification_details", []),
                eligibility_requirements=result.get("eligibility_requirements"),
                certifications_required=result.get("certifications_required", []),
                is_discretionary=result.get("is_discretionary", False),
                discretionary_reason=result.get("discretionary_reason"),
                contact_info=result.get("contact_info"),
                raw_analysis=result
            )

        except Exception as e:
            logger.error(f"Failed to analyze document: {e}")
            raise
