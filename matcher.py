"""Matching engine that scores opportunities against a company profile."""
import logging
from datetime import datetime

from app.models.schemas import (
    Opportunity, CompanyProfile, MatchScore, ScoredOpportunity
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Related NAICS code groups (first 2-4 digits match = related industry)
# This gives partial credit for being in the same industry sector
NAICS_SECTOR_MAP = {
    "54": "Professional/Scientific/Technical Services",
    "51": "Information",
    "52": "Finance and Insurance",
    "56": "Administrative/Support Services",
    "33": "Manufacturing",
    "23": "Construction",
    "48": "Transportation",
    "62": "Health Care",
    "61": "Educational Services",
    "92": "Public Administration",
}


class MatchingEngine:
    """Scores government contract opportunities against a company profile."""
    
    def __init__(self):
        self.settings = get_settings()
    
    def score_opportunities(
        self,
        opportunities: list[Opportunity],
        profile: CompanyProfile,
    ) -> list[ScoredOpportunity]:
        """Score and rank a list of opportunities against a company profile."""
        scored = []
        for opp in opportunities:
            match_score = self._compute_match(opp, profile)
            tier = self._get_tier(match_score.overall_score)
            scored.append(ScoredOpportunity(
                opportunity=opp,
                match_score=match_score,
                match_tier=tier,
            ))
        
        # Sort by overall score descending
        scored.sort(key=lambda x: x.match_score.overall_score, reverse=True)
        return scored
    
    def _compute_match(self, opp: Opportunity, profile: CompanyProfile) -> MatchScore:
        """Compute the full match score breakdown."""
        naics = self._score_naics(opp, profile)
        set_aside = self._score_set_aside(opp, profile)
        agency = self._score_agency(opp, profile)
        geo = self._score_geography(opp, profile)
        
        # Semantic score placeholder — filled by analyzer.py when Claude is called
        semantic = 0.0
        
        overall = naics + set_aside + agency + geo + semantic
        
        explanations = []
        if naics > 0:
            explanations.append(f"NAICS match ({naics:.0f}/30)")
        if set_aside > 0:
            explanations.append(f"Set-aside eligible ({set_aside:.0f}/20)")
        if agency > 0:
            explanations.append(f"Preferred agency ({agency:.0f}/10)")
        if geo > 0:
            explanations.append(f"Geographic fit ({geo:.0f}/10)")
        if not explanations:
            explanations.append("No strong signals — review manually")
        
        return MatchScore(
            overall_score=min(overall, 100),
            naics_score=naics,
            set_aside_score=set_aside,
            agency_score=agency,
            geo_score=geo,
            semantic_score=semantic,
            explanation=". ".join(explanations),
        )
    
    def _score_naics(self, opp: Opportunity, profile: CompanyProfile) -> float:
        """Score NAICS code match (0-30 points)."""
        if not opp.naics_code or not profile.naics_codes:
            return 0.0
        
        opp_naics = opp.naics_code.strip()
        
        # Exact match = 30 points
        if opp_naics in profile.naics_codes:
            return 30.0
        
        # Related (same 4-digit prefix) = 20 points
        for code in profile.naics_codes:
            if len(code) >= 4 and len(opp_naics) >= 4 and code[:4] == opp_naics[:4]:
                return 20.0
        
        # Same sector (2-digit) = 10 points
        for code in profile.naics_codes:
            if len(code) >= 2 and len(opp_naics) >= 2 and code[:2] == opp_naics[:2]:
                return 10.0
        
        return 0.0
    
    def _score_set_aside(self, opp: Opportunity, profile: CompanyProfile) -> float:
        """Score set-aside eligibility (0-20 points)."""
        if not opp.set_aside or not profile.set_aside_types:
            return 0.0
        
        opp_set_aside = opp.set_aside.lower()
        
        # Check each of the user's set-aside types
        for sa in profile.set_aside_types:
            sa_lower = sa.value.lower() if hasattr(sa, 'value') else str(sa).lower()
            # Fuzzy match — SAM.gov uses inconsistent naming
            if any(keyword in opp_set_aside for keyword in sa_lower.split()):
                return 20.0
        
        # Partial credit for "Total Small Business" if user has any SB designation
        if "small business" in opp_set_aside and len(profile.set_aside_types) > 0:
            return 15.0
        
        return 0.0
    
    def _score_agency(self, opp: Opportunity, profile: CompanyProfile) -> float:
        """Score agency preference (0-10 points)."""
        if not profile.agency_preferences or not opp.department:
            return 0.0
        
        opp_dept = opp.department.lower()
        for pref in profile.agency_preferences:
            if pref.lower() in opp_dept:
                return 10.0
        
        return 0.0
    
    def _score_geography(self, opp: Opportunity, profile: CompanyProfile) -> float:
        """Score geographic fit (0-10 points)."""
        if not profile.geographic_preferences or not opp.place_of_performance:
            return 0.0
        
        pop = opp.place_of_performance.lower()
        for geo in profile.geographic_preferences:
            if geo.lower() in pop:
                return 10.0
        
        return 0.0
    
    def _get_tier(self, score: float) -> str:
        """Classify match into tier."""
        if score >= self.settings.high_match_threshold:
            return "high"
        elif score >= self.settings.medium_match_threshold:
            return "medium"
        return "low"
