"""SQLAlchemy ORM table definitions for GovContract AI.

These are the persistent representations. The Pydantic models in schemas.py
remain the canonical runtime models — these classes are for DB I/O only.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class OpportunityRow(Base):
    __tablename__ = "opportunities"

    notice_id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    solicitation_number = Column(String)
    department = Column(String)
    sub_tier = Column(String)
    office = Column(String)
    naics_code = Column(String)
    naics_description = Column(String)
    set_aside = Column(String)
    opportunity_type = Column(String)
    posted_date = Column(String)
    response_deadline = Column(String)
    description = Column(Text)
    place_of_performance = Column(String)
    point_of_contact = Column(JSONB)
    estimated_value = Column(Float)
    award_amount = Column(Float)
    link = Column(String)
    active = Column(Boolean, default=True)
    source = Column(String, default="sam.gov")
    complexity_tier = Column(String, default="STANDARD")
    estimated_competition = Column(String, default="OPEN")
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_updated_at = Column(DateTime, default=datetime.utcnow)


class ClusterRow(Base):
    __tablename__ = "clusters"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    naics_codes = Column(JSONB, default=list)
    certifications = Column(JSONB, default=list)
    capability_description = Column(Text, default="")
    team_roster = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ScoutRunRow(Base):
    __tablename__ = "scout_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_at = Column(DateTime, default=datetime.utcnow)
    opportunities_found = Column(Integer, default=0)
    new_above_threshold = Column(Integer, default=0)
    alerts_sent = Column(Integer, default=0)
    duration_seconds = Column(Float, default=0.0)


class PursuitRow(Base):
    __tablename__ = "pursuits"

    id = Column(String, primary_key=True)
    opportunity_id = Column(String)
    cluster_id = Column(String)
    # identified → qualifying → capture → proposal → submitted → won/lost
    status = Column(String, default="identified")
    notes = Column(Text)
    assigned_team = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
