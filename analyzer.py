"""Claude-powered opportunity analysis and semantic scoring."""
import logging
import json
from typing import Optional

import anthropic

from app.core.config import get_settings
from app.models.schemas import (
    Opportunity, CompanyProfile, ScoredOpportunity, OpportunityDetail
)

logger = logging.getLogger(__name__)


class OpportunityAnalyzer:
    """Uses Claude to analyze opportunities and generate semantic match scores."""
    
    def __init__(self):
        self.settings = get_settings()
        self.client = None
        if self.settings.anthropic_api_key:
            self.client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
    
    async def enrich_with_semantic_score(
        self,
        scored_opp: ScoredOpportunity,
        profile: CompanyProfile,
    ) -> ScoredOpportunity:
        """Add semantic relevance score by comparing capability statement to opportunity."""
        if not self.client or not profile.capability_statement:
            return scored_opp
        
        try:
            prompt = f"""Score how well this company matches this government contract opportunity.

COMPANY PROFILE:
- Capabilities: {profile.capability_statement[:1500]}
- Past Performance Keywords: {', '.join(profile.past_performance_keywords[:10])}
- NAICS Codes: {', '.join(profile.naics_codes[:5])}

OPPORTUNITY:
- Title: {scored_opp.opportunity.title}
- Description: {(scored_opp.opportunity.description or 'No description')[:2000]}
- NAICS: {scored_opp.opportunity.naics_code} - {scored_opp.opportunity.naics_description or ''}
- Department: {scored_opp.opportunity.department or 'Unknown'}
- Set-Aside: {scored_opp.opportunity.set_aside or 'None'}

Respond with ONLY a JSON object (no markdown, no explanation):
{{"score": <0-30>, "reason": "<one sentence explaining the semantic match>"}}

Score guide:
- 25-30: Strong alignment between capabilities and requirements
- 15-24: Moderate alignment, company could compete
- 5-14: Weak alignment, tangential fit
- 0-4: No meaningful connection"""

            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            
            result_text = response.content[0].text.strip()
            # Handle potential markdown wrapping
            if result_text.startswith("```"):
                result_text = result_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            
            result = json.loads(result_text)
            semantic_score = min(max(float(result.get("score", 0)), 0), 30)
            reason = result.get("reason", "")
            
            # Update the scored opportunity
            scored_opp.match_score.semantic_score = semantic_score
            scored_opp.match_score.overall_score = min(
                scored_opp.match_score.naics_score +
                scored_opp.match_score.set_aside_score +
                scored_opp.match_score.agency_score +
                scored_opp.match_score.geo_score +
                semantic_score,
                100
            )
            scored_opp.match_score.explanation += f". AI: {reason}" if reason else ""
            scored_opp.match_tier = self._get_tier(scored_opp.match_score.overall_score)
            
            return scored_opp
            
        except Exception as e:
            logger.warning(f"Semantic scoring failed for {scored_opp.opportunity.notice_id}: {e}")
            return scored_opp
    
    async def generate_detailed_analysis(
        self,
        opportunity: Opportunity,
        profile: CompanyProfile,
    ) -> OpportunityDetail:
        """Generate a full AI analysis of an opportunity."""
        if not self.client:
            return OpportunityDetail(
                opportunity=opportunity,
                ai_analysis="Claude API not configured. Set ANTHROPIC_API_KEY.",
                key_requirements=[], 
                suggested_actions=["Configure API key for AI analysis"],
            )
        
        try:
            prompt = f"""You are a government contracting advisor helping a small business evaluate an opportunity.

COMPANY:
- Name: {profile.company_name}
- Capabilities: {profile.capability_statement[:2000]}
- NAICS Codes: {', '.join(profile.naics_codes)}
- Set-Aside Status: {', '.join(str(s.value) if hasattr(s, 'value') else str(s) for s in profile.set_aside_types)}
- Past Performance: {', '.join(profile.past_performance_keywords[:10])}

OPPORTUNITY:
- Title: {opportunity.title}
- Solicitation #: {opportunity.solicitation_number or 'N/A'}
- Department: {opportunity.department or 'Unknown'}
- Office: {opportunity.office or 'Unknown'}
- NAICS: {opportunity.naics_code} - {opportunity.naics_description or ''}
- Set-Aside: {opportunity.set_aside or 'Full and Open'}
- Type: {opportunity.opportunity_type or 'Unknown'}
- Deadline: {opportunity.response_deadline or 'Not specified'}
- Place of Performance: {opportunity.place_of_performance or 'Not specified'}
- Description: {(opportunity.description or 'No description available')[:3000]}

Respond with ONLY a JSON object:
{{
    "analysis": "<2-3 paragraph analysis of fit, risks, and strategy>",
    "key_requirements": ["<req1>", "<req2>", ...],
    "suggested_actions": ["<action1>", "<action2>", ...],
    "competitive_intel": "<what you can infer about competition and positioning>",
    "deadline_urgency": "<urgent|soon|normal|past>"
}}"""

            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=self.settings.claude_max_tokens_per_analysis,
                messages=[{"role": "user", "content": prompt}],
            )
            
            result_text = response.content[0].text.strip()
            if result_text.startswith("```"):
                result_text = result_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            
            result = json.loads(result_text)
            
            return OpportunityDetail(
                opportunity=opportunity,
                ai_analysis=result.get("analysis", ""),
                competitive_intel=result.get("competitive_intel"),
                key_requirements=result.get("key_requirements", []),
                suggested_actions=result.get("suggested_actions", []),
                deadline_urgency=result.get("deadline_urgency", "normal"),
            )
            
        except Exception as e:
            logger.error(f"Detailed analysis failed: {e}")
            return OpportunityDetail(
                opportunity=opportunity,
                ai_analysis=f"Analysis generation failed: {str(e)}",
                key_requirements=[],
                suggested_actions=["Try again or review opportunity manually"],
            )
    
    def _get_tier(self, score: float) -> str:
        if score >= self.settings.high_match_threshold:
            return "high"
        elif score >= self.settings.medium_match_threshold:
            return "medium"
        return "low"
