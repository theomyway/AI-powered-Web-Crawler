"""
RFP Response Generator Service using Azure OpenAI GPT-4o.

Generates professional RFP response documents based on:
- Extracted RFP document content
- Company information
- GPT-4o's general knowledge

Features:
- Token limit management with smart chunking
- Two-pass approach: summarize RFP first, then generate response
- Professional document formatting
"""

import json
import logging
import time
from datetime import datetime
from typing import Any

from openai import AzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from shared.config import get_settings

logger = logging.getLogger(__name__)

# Token limits
CHARS_PER_TOKEN = 4
MAX_RFP_CONTENT_TOKENS = 60000  # Leave room for system prompt and response
MAX_SUMMARY_TOKENS = 20000  # For summarized RFP content


class RfpGeneratorService:
    """Service for generating RFP responses using Azure OpenAI."""

    def __init__(self):
        """Initialize the RFP generator service."""
        settings = get_settings()
        self.client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self.deployment = settings.azure_openai_deployment
        logger.info("RfpGeneratorService initialized")

    def _log_step(self, step_name: str, status: str,
                  duration: float = None, metrics: dict = None):
        """Log a processing step with standardized format."""
        timestamp = datetime.utcnow().isoformat()
        log_msg = f"[RfpGenerator] {step_name}: {status}"
        if duration is not None:
            log_msg += f" (duration: {duration:.2f}s)"
        if metrics:
            metrics_str = ", ".join(f"{k}={v}" for k, v in metrics.items())
            log_msg += f" | {metrics_str}"
        logger.info(f"{timestamp} - {log_msg}")

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return len(text) // CHARS_PER_TOKEN

    def _truncate_content(self, content: str, max_tokens: int) -> str:
        """Truncate content to fit within token limits."""
        max_chars = max_tokens * CHARS_PER_TOKEN
        if len(content) <= max_chars:
            return content
        
        truncated = content[:max_chars]
        # Find last complete sentence
        last_period = truncated.rfind('.')
        if last_period > max_chars * 0.8:  # Only truncate at sentence if >80% content preserved
            truncated = truncated[:last_period + 1]
        
        truncated += "\n\n[Document truncated due to length]"
        logger.info(f"Content truncated from {len(content)} to {len(truncated)} chars")
        return truncated

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True
    )
    def _summarize_rfp(self, rfp_content: str) -> str:
        """
        First pass: Summarize the RFP document to extract key information.

        This reduces token usage while preserving critical details.
        """
        logger.info("-" * 60)
        logger.info("[STEP 2.1] RFP SUMMARIZATION - Starting")
        logger.info("-" * 60)
        logger.info(f"  - Input RFP content length: {len(rfp_content)} chars")
        logger.info(f"  - Estimated input tokens: ~{len(rfp_content) // 4}")

        self._log_step("RFP Summarization", "started",
                       metrics={"content_chars": len(rfp_content)})

        # Log preview of input
        logger.info("-" * 40)
        logger.info("[STEP 2.1a] RFP CONTENT INPUT PREVIEW (first 1000 chars):")
        logger.info("-" * 40)
        preview = rfp_content[:1000].replace('\n', '\n  ')
        logger.info(f"  {preview}")
        if len(rfp_content) > 1000:
            logger.info(f"  ... [truncated, {len(rfp_content) - 1000} more chars]")
        logger.info("-" * 40)

        # Truncate if needed
        rfp_content = self._truncate_content(rfp_content, MAX_RFP_CONTENT_TOKENS)

        system_prompt = """You are an expert RFP analyst. Your task is to extract and summarize the key information from this RFP document that would be needed to write a comprehensive response.

Extract and organize the following information:
1. **Project Overview**: What is being requested? What problem needs to be solved?
2. **Scope of Work**: Specific deliverables, tasks, and responsibilities
3. **Technical Requirements**: Technologies, platforms, integrations, specifications
4. **Evaluation Criteria**: How proposals will be scored/evaluated
5. **Timeline Requirements**: Key dates, milestones, project duration
6. **Submission Requirements**: Format, sections required, page limits
7. **Qualification Requirements**: Required certifications, experience, references
8. **Budget/Pricing**: Any budget information or pricing format requirements
9. **Key Terms and Conditions**: Important contractual terms
10. **Contact Information**: Who to contact for questions

Be thorough but concise. Focus on information that would help write a winning proposal response."""

        logger.info("[STEP 2.1b] Calling Azure OpenAI for summarization...")
        start_time = time.time()
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"RFP Document:\n\n{rfp_content}"}
            ],
            temperature=0.3,
            max_tokens=8000,
        )

        summary = response.choices[0].message.content
        duration = time.time() - start_time

        logger.info(f"[STEP 2.1c] Summarization complete in {duration:.2f}s")
        logger.info(f"  - Summary length: {len(summary)} chars")
        logger.info("-" * 40)
        logger.info("[STEP 2.1d] RFP SUMMARY OUTPUT PREVIEW (first 2000 chars):")
        logger.info("-" * 40)
        summary_preview = summary[:2000].replace('\n', '\n  ')
        logger.info(f"  {summary_preview}")
        if len(summary) > 2000:
            logger.info(f"  ... [truncated, {len(summary) - 2000} more chars]")
        logger.info("-" * 40)

        self._log_step("RFP Summarization", "completed", duration=duration,
                       metrics={"summary_chars": len(summary)})

        return summary

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True
    )
    def generate_response(
        self,
        rfp_content: str,
        opportunity_title: str,
        company_info: dict[str, Any],
        opportunity_details: dict[str, Any] | None = None
    ) -> str:
        """
        Generate a professional RFP response document.

        Uses a two-pass approach:
        1. Summarize the RFP to extract key requirements
        2. Generate a comprehensive response based on company info and RFP summary

        Args:
            rfp_content: Extracted text from the RFP document
            opportunity_title: Title of the opportunity
            company_info: Company information dict with keys:
                - company_name, company_bio, relevant_experience, certifications
            opportunity_details: Optional additional opportunity metadata

        Returns:
            Markdown-formatted RFP response document
        """
        total_start = time.time()

        logger.info("[STEP 2] RfpGeneratorService.generate_response() called")
        logger.info(f"  - Opportunity: {opportunity_title}")
        logger.info(f"  - RFP content provided: {'YES' if rfp_content else 'NO'}")
        logger.info(f"  - RFP content length: {len(rfp_content) if rfp_content else 0} chars")

        self._log_step("RFP Response Generation", "started",
                       metrics={"opportunity": opportunity_title[:50]})

        # Step 1: Summarize the RFP if content is available
        rfp_summary = ""
        if rfp_content and len(rfp_content.strip()) > 100:
            logger.info("[STEP 2] RFP content available - proceeding with summarization...")
            try:
                rfp_summary = self._summarize_rfp(rfp_content)
                logger.info(f"[STEP 2] Summarization successful. Summary length: {len(rfp_summary)} chars")
            except Exception as e:
                logger.warning(f"[STEP 2] RFP summarization failed: {e}. Proceeding without summary.")
                rfp_summary = self._truncate_content(rfp_content, MAX_SUMMARY_TOKENS)
        else:
            logger.warning("[STEP 2] NO RFP CONTENT or content too short - skipping summarization")
            logger.warning(f"  - This means the response will be GENERIC without specific RFP details!")

        # Step 2: Generate the response
        logger.info("[STEP 2.2] Generating final response from summary...")
        response_content = self._generate_response_from_summary(
            rfp_summary=rfp_summary,
            opportunity_title=opportunity_title,
            company_info=company_info,
            opportunity_details=opportunity_details
        )

        total_duration = time.time() - total_start
        self._log_step("RFP Response Generation", "completed", duration=total_duration,
                       metrics={"response_chars": len(response_content)})

        return response_content

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True
    )
    def _generate_response_from_summary(
        self,
        rfp_summary: str,
        opportunity_title: str,
        company_info: dict[str, Any],
        opportunity_details: dict[str, Any] | None = None
    ) -> str:
        """Generate the RFP response using the summarized requirements."""

        logger.info("-" * 60)
        logger.info("[STEP 2.2] FINAL RESPONSE GENERATION - Starting")
        logger.info("-" * 60)
        logger.info(f"  - RFP summary provided: {'YES' if rfp_summary else 'NO'}")
        logger.info(f"  - RFP summary length: {len(rfp_summary) if rfp_summary else 0} chars")

        self._log_step("Response Generation", "started")

        # Build company context
        company_name = company_info.get("company_name", "Our Company")
        company_bio = company_info.get("company_bio", "")
        relevant_experience = company_info.get("relevant_experience", "")
        certifications = company_info.get("certifications", [])
        certs_text = ", ".join(certifications) if certifications else "None specified"

        logger.info("[STEP 2.2a] Company context:")
        logger.info(f"  - Company Name: {company_name}")
        logger.info(f"  - Company Bio length: {len(company_bio)} chars")
        logger.info(f"  - Relevant Experience length: {len(relevant_experience)} chars")
        logger.info(f"  - Certifications: {certs_text}")

        # Build opportunity context
        opp_context = ""
        if opportunity_details:
            if opportunity_details.get("deadline"):
                opp_context += f"\nSubmission Deadline: {opportunity_details['deadline']}"
            if opportunity_details.get("category"):
                opp_context += f"\nCategory: {opportunity_details['category']}"
            if opportunity_details.get("estimated_value"):
                opp_context += f"\nEstimated Value: ${opportunity_details['estimated_value']:,.2f}"

        system_prompt = f"""You are an expert proposal writer for {company_name}. Your task is to generate a professional, comprehensive, and compelling RFP response document.

COMPANY INFORMATION:
Company Name: {company_name}
Company Bio: {company_bio or "Not provided"}
Relevant Experience: {relevant_experience or "Not provided"}
Certifications: {certs_text}

INSTRUCTIONS:
1. Generate a COMPLETE, PROFESSIONAL RFP response document in Markdown format
2. The response should be comprehensive and client-ready
3. Use the company information provided but also leverage your general knowledge to enhance the response
4. Include realistic and professional content for each section
5. Match the response to the specific requirements mentioned in the RFP summary
6. Use professional business language appropriate for government/enterprise RFPs
7. Include specific, actionable content - not placeholders or generic statements

DOCUMENT STRUCTURE (Required Sections):
1. Executive Summary - Compelling overview of your proposal
2. Company Overview - Enhanced description of the company
3. Understanding of Requirements - Demonstrate understanding of the project
4. Technical Approach - Detailed methodology and solution approach
5. Project Management Approach - How you'll manage the project
6. Proposed Timeline & Milestones - Realistic project schedule
7. Team & Qualifications - Key personnel and their expertise
8. Relevant Experience & Past Performance - Similar projects completed
9. Quality Assurance - How you ensure deliverable quality
10. Risk Management - Identified risks and mitigation strategies
11. Conclusion - Strong closing statement

FORMAT REQUIREMENTS:
- Use proper Markdown formatting (headers, bullet points, tables where appropriate)
- Be thorough but concise
- Target approximately 2000-3000 words
- Make it specific to the RFP requirements, not generic"""

        user_content = f"""OPPORTUNITY: {opportunity_title}
{opp_context}

RFP REQUIREMENTS SUMMARY:
{rfp_summary if rfp_summary else "No RFP document content was provided. Generate a general professional proposal response for an IT services/technology project."}

Please generate a complete, professional RFP response document."""

        logger.info("[STEP 2.2b] Prompt details:")
        logger.info(f"  - System prompt length: {len(system_prompt)} chars")
        logger.info(f"  - User content length: {len(user_content)} chars")

        # Log the RFP summary that's being used
        if rfp_summary:
            logger.info("-" * 40)
            logger.info("[STEP 2.2c] RFP SUMMARY BEING USED (first 1500 chars):")
            logger.info("-" * 40)
            summary_preview = rfp_summary[:1500].replace('\n', '\n  ')
            logger.info(f"  {summary_preview}")
            if len(rfp_summary) > 1500:
                logger.info(f"  ... [truncated, {len(rfp_summary) - 1500} more chars]")
            logger.info("-" * 40)
        else:
            logger.warning("[STEP 2.2c] NO RFP SUMMARY - generating generic response!")

        logger.info("[STEP 2.2d] Calling Azure OpenAI for response generation...")
        start_time = time.time()
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.7,
            max_tokens=12000,
        )

        response_content = response.choices[0].message.content
        duration = time.time() - start_time

        logger.info(f"[STEP 2.2e] Response generation complete in {duration:.2f}s")
        logger.info(f"  - Response length: {len(response_content)} chars")
        logger.info("-" * 40)
        logger.info("[STEP 2.2f] GENERATED RESPONSE PREVIEW (first 2000 chars):")
        logger.info("-" * 40)
        response_preview = response_content[:2000].replace('\n', '\n  ')
        logger.info(f"  {response_preview}")
        if len(response_content) > 2000:
            logger.info(f"  ... [truncated, {len(response_content) - 2000} more chars]")
        logger.info("-" * 40)

        self._log_step("Response Generation", "completed", duration=duration,
                       metrics={"response_chars": len(response_content)})

        return response_content

