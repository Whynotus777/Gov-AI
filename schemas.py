"""Data models for GovContract AI."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class SetAsideType(str, Enum):
    TOTAL_SB = "Total Small Business"
    SBA_8A = "8(a)"
    HUBZONE = "HUBZone"
    SDVOSB = "Service-Disabled Veteran-Owned"
    WOSB = "Women-Owned Small Business"
    EDWOSB = "Economically Disadvantaged WOSB"
    SDB = "Small Disadvantaged Business"
    NONE = "None"


class OpportunityType(str, Enum):
    SOLICITATION = "Solicitation"
    PRESOLICITATION = "Presolicitation"
    COMBINED = "Combined Synopsis/Solicitation"
    AWARD = "Award Notice"
    SPECIAL_NOTICE = "Special Notice"
    SOURCES_SOUGHT = "Sources Sought"
    INTENT_TO_BUNDLE = "Intent to Bundle"


class CompanyProfile(BaseModel):
    """User's company profile for matching."""
    id: str = ""
    company_name: str
    cage_code: Optional[str] = None
    uei: Optional[str] = None
    naics_codes: list[str] = Field(default_factory=list, description="Primary + secondary NAICS codes")
    set_aside_types: list[SetAsideType] = Field(default_factory=list)
    capability_statement: str = Field(default="", description="Free-text capability description")
    past_performance_keywords: list[str] = Field(default_factory=list)
    geographic_preferences: list[str] = Field(default_factory=list, description="State abbreviations")
    agency_preferences: list[str] = Field(default_factory=list, description="Preferred agencies")
    revenue_range: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Opportunity(BaseModel):
    """A government contract opportunity from SAM.gov."""
    notice_id: str
    title: str
    solicitation_number: Optional[str] = None
    department: Optional[str] = None
    sub_tier: Optional[str] = None
    office: Optional[str] = None
    naics_code: Optional[str] = None
    naics_description: Optional[str] = None
    set_aside: Optional[str] = None
    opportunity_type: Optional[str] = None
    posted_date: Optional[str] = None
    response_deadline: Optional[str] = None
    description: Optional[str] = None
    place_of_performance: Optional[str] = None
    point_of_contact: Optional[dict] = None
    award_amount: Optional[float] = None
    link: Optional[str] = None
    active: bool = True


class MatchScore(BaseModel):
    """Breakdown of how well an opportunity matches a company profile."""
    overall_score: float = Field(ge=0, le=100)
    naics_score: float = Field(ge=0, le=30)
    set_aside_score: float = Field(ge=0, le=20)
    agency_score: float = Field(ge=0, le=10)
    geo_score: float = Field(ge=0, le=10)
    semantic_score: float = Field(ge=0, le=30)
    explanation: str = ""


class ScoredOpportunity(BaseModel):
    """An opportunity with its match score and AI analysis."""
    opportunity: Opportunity
    match_score: MatchScore
    ai_analysis: Optional[str] = None
    match_tier: str = "low"  # "high", "medium", "low"


class SearchFilters(BaseModel):
    """Filters for searching opportunities."""
    keywords: Optional[str] = None
    naics_codes: list[str] = Field(default_factory=list)
    set_aside: Optional[str] = None
    posted_from: Optional[str] = None
    posted_to: Optional[str] = None
    response_deadline_from: Optional[str] = None
    opportunity_types: list[str] = Field(default_factory=list)
    department: Optional[str] = None
    min_score: float = 0
    limit: int = 50
    offset: int = 0


class OpportunityDetail(BaseModel):
    """Extended detail for a single opportunity including AI analysis."""
    opportunity: Opportunity
    match_score: Optional[MatchScore] = None
    ai_analysis: str = ""
    competitive_intel: Optional[str] = None
    key_requirements: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    deadline_urgency: str = "normal"  # "urgent", "soon", "normal", "past"
