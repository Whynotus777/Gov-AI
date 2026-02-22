"""Matching engine that scores opportunities against a company profile or capability clusters."""
import logging
from datetime import datetime

from app.models.schemas import (
    Opportunity, CompanyProfile, CapabilityCluster, CertificationType,
    MatchScore, ScoredOpportunity,
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

# Maps each CertificationType to the set-aside keywords SAM.gov uses.
# Used when scoring cluster certifications against an opportunity's set_aside field.
CERT_SET_ASIDE_KEYWORDS: dict[CertificationType, list[str]] = {
    CertificationType.A8: ["8(a)", "8a", "eight-a"],
    CertificationType.HUBZONE: ["hubzone", "hub zone"],
    CertificationType.SDVOSB: ["service-disabled veteran", "sdvosb", "sdv"],
    CertificationType.VOSB: ["veteran-owned", "vosb"],
    CertificationType.WOSB: ["women-owned", "wosb"],
    CertificationType.EDWOSB: ["economically disadvantaged", "edwosb"],
    CertificationType.SDB: ["small disadvantaged", "sdb"],
    CertificationType.SB: ["small business"],
    CertificationType.MINORITY_OWNED: ["minority"],
    CertificationType.ABILITY_ONE: ["abilityone", "ability one"],
}


class MatchingEngine:
    """Scores government contract opportunities against a company profile or capability clusters."""

    def __init__(self):
        self.settings = get_settings()

    # ------------------------------------------------------------------
    # Profile-based matching (original, preserved for backward compat)
    # ------------------------------------------------------------------

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
        return self._match_naics_codes(opp.naics_code, profile.naics_codes)

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
        return self._match_agency(opp, profile.agency_preferences)

    def _score_geography(self, opp: Opportunity, profile: CompanyProfile) -> float:
        """Score geographic fit (0-10 points)."""
        return self._match_geography(opp, profile.geographic_preferences)

    # ------------------------------------------------------------------
    # Cluster-based matching (new in feat/clusters-and-tiers)
    # ------------------------------------------------------------------

    def score_opportunities_with_clusters(
        self,
        opportunities: list[Opportunity],
        clusters: list[CapabilityCluster],
        agency_preferences: list[str] | None = None,
        geographic_preferences: list[str] | None = None,
    ) -> list[ScoredOpportunity]:
        """
        Score opportunities against multiple capability clusters.

        For each opportunity, every cluster is evaluated and the highest-scoring
        cluster is selected. The result is tagged with the winning cluster's
        id and name so users can filter results by cluster.

        Args:
            opportunities: Opportunities to score.
            clusters: Capability clusters to score against.
            agency_preferences: Agency preferences shared across all clusters
                (typically from the parent CompanyProfile).
            geographic_preferences: Geographic preferences shared across all clusters.
        """
        agency_prefs = agency_preferences or []
        geo_prefs = geographic_preferences or []

        if not clusters:
            return [
                ScoredOpportunity(
                    opportunity=opp,
                    match_score=MatchScore(
                        overall_score=0, naics_score=0, set_aside_score=0,
                        agency_score=0, geo_score=0, semantic_score=0,
                        explanation="No capability clusters configured for matching",
                    ),
                    match_tier="unscored",
                )
                for opp in opportunities
            ]

        scored = []
        for opp in opportunities:
            best_score: MatchScore | None = None
            best_cluster: CapabilityCluster | None = None

            for cluster in clusters:
                score = self._compute_cluster_match(opp, cluster, agency_prefs, geo_prefs)
                if best_score is None or score.overall_score > best_score.overall_score:
                    best_score = score
                    best_cluster = cluster

            tier = self._get_tier(best_score.overall_score)
            scored.append(ScoredOpportunity(
                opportunity=opp,
                match_score=best_score,
                match_tier=tier,
                best_cluster_id=best_cluster.id if best_cluster else None,
                best_cluster_name=best_cluster.name if best_cluster else None,
            ))

        scored.sort(key=lambda x: x.match_score.overall_score, reverse=True)
        return scored

    def _compute_cluster_match(
        self,
        opp: Opportunity,
        cluster: CapabilityCluster,
        agency_preferences: list[str],
        geographic_preferences: list[str],
    ) -> MatchScore:
        """
        Compute match score for one opportunity against one capability cluster.

        NAICS and certification scoring use cluster-specific data.
        Agency and geography scoring use profile-level shared preferences.
        Semantic scoring is zero here — the analyzer enriches it separately.
        """
        naics = self._match_naics_codes(opp.naics_code, cluster.naics_codes)
        set_aside = self._score_cluster_certifications(opp, cluster)
        agency = self._match_agency(opp, agency_preferences)
        geo = self._match_geography(opp, geographic_preferences)

        overall = naics + set_aside + agency + geo

        explanations = []
        if naics > 0:
            explanations.append(f"NAICS match ({naics:.0f}/30)")
        if set_aside > 0:
            explanations.append(f"Certification eligible ({set_aside:.0f}/20)")
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
            semantic_score=0.0,
            explanation=". ".join(explanations),
        )

    def _score_cluster_certifications(
        self,
        opp: Opportunity,
        cluster: CapabilityCluster,
    ) -> float:
        """
        Score set-aside eligibility using the cluster's CertificationType list (0-20 points).

        Maps each CertificationType to the SAM.gov set-aside terminology via
        CERT_SET_ASIDE_KEYWORDS and performs a fuzzy keyword match.
        """
        if not opp.set_aside or not cluster.certifications:
            return 0.0

        opp_set_aside = opp.set_aside.lower()

        for cert in cluster.certifications:
            keywords = CERT_SET_ASIDE_KEYWORDS.get(cert, [])
            if any(kw in opp_set_aside for kw in keywords):
                return 20.0

        # Partial credit when opportunity is "Total Small Business" and cluster
        # holds any small business certification.
        if "small business" in opp_set_aside and cluster.certifications:
            return 15.0

        return 0.0

    # ------------------------------------------------------------------
    # Shared scoring primitives (used by both profile and cluster paths)
    # ------------------------------------------------------------------

    def _match_naics_codes(
        self,
        opp_naics: str | None,
        profile_codes: list[str],
    ) -> float:
        """Score NAICS code match (0-30 points). Shared by profile and cluster paths."""
        if not opp_naics or not profile_codes:
            return 0.0

        opp_naics = opp_naics.strip()

        # Exact match = 30 points
        if opp_naics in profile_codes:
            return 30.0

        # Related (same 4-digit prefix) = 20 points
        for code in profile_codes:
            if len(code) >= 4 and len(opp_naics) >= 4 and code[:4] == opp_naics[:4]:
                return 20.0

        # Same sector (2-digit) = 10 points
        for code in profile_codes:
            if len(code) >= 2 and len(opp_naics) >= 2 and code[:2] == opp_naics[:2]:
                return 10.0

        return 0.0

    def _match_agency(self, opp: Opportunity, agency_preferences: list[str]) -> float:
        """Score agency preference (0-10 points). Shared by profile and cluster paths."""
        if not agency_preferences or not opp.department:
            return 0.0

        opp_dept = opp.department.lower()
        for pref in agency_preferences:
            pref_lower = pref.lower()
            # Direct substring match in either direction
            if pref_lower in opp_dept or opp_dept in pref_lower:
                return 10.0
            # Keyword overlap: SAM.gov uses abbreviations like "DEPT OF DEFENSE"
            # vs profile value "Department of Defense". Match on significant words (>3 chars).
            key_words = [w for w in pref_lower.split() if len(w) > 3]
            if key_words and any(w in opp_dept for w in key_words):
                return 10.0

        return 0.0

    def _match_geography(self, opp: Opportunity, geographic_preferences: list[str]) -> float:
        """Score geographic fit (0-10 points). Shared by profile and cluster paths."""
        if not geographic_preferences or not opp.place_of_performance:
            return 0.0

        pop = opp.place_of_performance.lower()
        for geo in geographic_preferences:
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
