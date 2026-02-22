"""
Proposal template generator using Claude Haiku.

Generates a structured proposal outline (cover letter, technical approach,
management approach, past performance placeholder, staffing plan, pricing
placeholder) for a specific opportunity + capability cluster pairing.

POST /api/v1/opportunities/{notice_id}/proposal?cluster_id=xxx
"""
import asyncio
import logging
from typing import Optional

from app.models.schemas import Opportunity, CapabilityCluster

logger = logging.getLogger(__name__)


class ProposalGenerator:
    """Generate proposal outlines using Claude Haiku."""

    _MODEL = "claude-haiku-4-5-20251001"
    _MAX_TOKENS = 2048

    async def generate(
        self,
        opportunity: Opportunity,
        cluster: CapabilityCluster,
    ) -> dict:
        """
        Generate a structured proposal template for an opportunity.

        Returns a dict with sections: cover_letter, technical_approach,
        management_approach, past_performance, staffing_plan, pricing_placeholder.
        """
        try:
            result = await asyncio.to_thread(
                self._call_claude, opportunity, cluster
            )
            return result
        except Exception as e:
            logger.error(f"ProposalGenerator error: {e}")
            return self._fallback_template(opportunity, cluster)

    def _call_claude(
        self,
        opportunity: Opportunity,
        cluster: CapabilityCluster,
    ) -> dict:
        import anthropic
        client = anthropic.Anthropic()

        team_str = ""
        if cluster.team_roster:
            team_str = "\n".join(
                f"- {m.name} ({m.role})" + (f", {m.clearance} clearance" if m.clearance else "")
                for m in cluster.team_roster
            )

        cert_str = ", ".join(c.value for c in cluster.certifications) if cluster.certifications else "None"
        naics_str = ", ".join(cluster.naics_codes) if cluster.naics_codes else "N/A"

        prompt = f"""You are a government proposal writer helping a small business respond to a federal/state contract opportunity. Generate a concise proposal template outline.

OPPORTUNITY:
Title: {opportunity.title}
Agency: {opportunity.department or "Unknown"}
NAICS: {opportunity.naics_code or "N/A"}
Set-Aside: {opportunity.set_aside or "None"}
Description: {(opportunity.description or "")[:800]}

COMPANY CLUSTER: {cluster.name}
Capabilities: {cluster.capability_description[:600]}
NAICS Codes: {naics_str}
Certifications: {cert_str}
Team:
{team_str or "(No team roster provided)"}

Generate a proposal template with exactly these 6 sections. Be specific to the opportunity and company. Keep each section to 2-4 paragraphs of actionable placeholder text that the user can customize.

Respond in this exact JSON format:
{{
  "cover_letter": "...",
  "technical_approach": "...",
  "management_approach": "...",
  "past_performance": "...",
  "staffing_plan": "...",
  "pricing_placeholder": "..."
}}"""

        response = client.messages.create(
            model=self._MODEL,
            max_tokens=self._MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()

        # Parse JSON from response
        import json
        # Find JSON block
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(text[start:end])
            return {
                "notice_id": opportunity.notice_id,
                "opportunity_title": opportunity.title,
                "cluster_name": cluster.name,
                "sections": parsed,
                "model": self._MODEL,
            }
        raise ValueError(f"Could not parse JSON from Claude response: {text[:200]}")

    def _fallback_template(
        self,
        opportunity: Opportunity,
        cluster: CapabilityCluster,
    ) -> dict:
        """Return a basic template when Claude is unavailable."""
        team_lines = "\n".join(
            f"- {m.name}, {m.role}" for m in cluster.team_roster
        ) if cluster.team_roster else "- [Add key personnel here]"

        return {
            "notice_id": opportunity.notice_id,
            "opportunity_title": opportunity.title,
            "cluster_name": cluster.name,
            "sections": {
                "cover_letter": (
                    f"[Company Name] is pleased to submit this proposal in response to "
                    f"{opportunity.title} (Solicitation: {opportunity.solicitation_number or 'N/A'}) "
                    f"issued by {opportunity.department or 'the contracting agency'}.\n\n"
                    f"Our {cluster.name} division brings direct experience in {', '.join(cluster.naics_codes[:3])} "
                    f"and is uniquely positioned to deliver the required capabilities on time and within budget."
                ),
                "technical_approach": (
                    f"[Describe your technical approach to the {opportunity.title} requirements here.]\n\n"
                    f"Our approach leverages: {cluster.capability_description[:300]}\n\n"
                    f"[Add specific technical solution, tools, methodologies, and compliance with SOW requirements.]"
                ),
                "management_approach": (
                    "[Describe your project management methodology — Agile/Waterfall/hybrid, "
                    "reporting cadence, risk management, quality assurance process.]\n\n"
                    "[Identify your Program Manager and key decision-making structure.]"
                ),
                "past_performance": (
                    "[List 3-5 relevant past performance references. For each include:\n"
                    "- Contract number and title\n"
                    "- Agency/customer name and POC\n"
                    "- Period of performance\n"
                    "- Contract value\n"
                    "- Relevance to this requirement]"
                ),
                "staffing_plan": (
                    f"Proposed Key Personnel:\n{team_lines}\n\n"
                    "[Add labor categories, hours per category, and qualifications "
                    "that meet the solicitation's staffing requirements.]"
                ),
                "pricing_placeholder": (
                    "[Include fully-loaded labor rates by category, ODC estimates, "
                    "fee/profit, and total proposed price in the format required by "
                    "Section B of the solicitation. Reference your GSA Schedule / "
                    "IDIQ rates if applicable.]"
                ),
            },
            "model": "fallback",
        }
