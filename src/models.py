"""Data models for the job agent."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Job:
    """Represents a job posting scraped from a VC job board."""

    title: str
    company: str
    location: str
    url: str
    description: str
    source: str  # Which VC job board
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    remote: bool = False
    salary_range: Optional[str] = None
    posted_date: Optional[datetime] = None
    qualifications: str = ""  # Extracted from Qualifications/Requirements section
    company_description: str = ""  # Company bio from top of job posting

    def __hash__(self):
        return hash((self.title, self.company, self.url))

    def __eq__(self, other):
        if not isinstance(other, Job):
            return False
        return self.title == other.title and self.company == other.company and self.url == other.url

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
            "description": self.description,
            "source": self.source,
            "scraped_at": self.scraped_at.isoformat(),
            "remote": self.remote,
            "salary_range": self.salary_range,
            "posted_date": self.posted_date.isoformat() if self.posted_date else None,
            "qualifications": self.qualifications,
            "company_description": self.company_description,
        }


@dataclass
class DimensionScores:
    """Individual dimension scores for job matching (0-100 each)."""

    experience: int = 0  # Years of experience fit
    work_type: int = 0  # Type of work alignment
    skills_methods: int = 0  # Skills and methods match
    product_type: int = 0  # Product type fit (B2B, SaaS, AI, mobile, etc.)
    deliverables: int = 0  # Deliverables fit (design systems, dashboards, etc.)

    def to_dict(self) -> dict:
        return {
            "experience": self.experience,
            "work_type": self.work_type,
            "skills_methods": self.skills_methods,
            "product_type": self.product_type,
            "deliverables": self.deliverables,
        }


@dataclass
class MatchResult:
    """Result of matching a job against a candidate profile."""

    job: Job
    match_percentage: int  # 0-100
    dimension_scores: DimensionScores = field(default_factory=DimensionScores)
    matching_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    recommendation: str = ""
    matched_keywords: list[str] = field(default_factory=list)
    company_bio: str = ""
    company_series: str = ""
    rank: int = 0  # Current rank position (1-indexed)
    rank_delta: Optional[int] = None  # Change from previous day (positive = moved up)
    match_delta: Optional[int] = None  # Change in match % from previous day

    @property
    def is_good_match(self) -> bool:
        """Returns True if match percentage is >= 60%."""
        return self.match_percentage >= 60

    def to_dict(self) -> dict:
        return {
            "job": self.job.to_dict(),
            "match_percentage": self.match_percentage,
            "dimension_scores": self.dimension_scores.to_dict(),
            "matching_skills": self.matching_skills,
            "missing_skills": self.missing_skills,
            "recommendation": self.recommendation,
            "matched_keywords": self.matched_keywords,
            "company_bio": self.company_bio,
            "company_series": self.company_series,
            "rank": self.rank,
            "rank_delta": self.rank_delta,
            "match_delta": self.match_delta,
        }


@dataclass
class ScrapeSummary:
    """Summary of scrape results for a single source."""

    source: str
    total: int = 0
    new: int = 0
    previously_seen: int = 0


@dataclass
class CandidateProfile:
    """Combined profile from resume and portfolio."""

    resume_text: str
    portfolio_content: str
    name: str = ""
    email: str = ""
    skills: list[str] = field(default_factory=list)

    # Structured fields parsed from resume
    technical_skills: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    soft_skills: list[str] = field(default_factory=list)
    years_of_experience: str = ""
    products_worked_on: list[str] = field(default_factory=list)
    team_types: list[str] = field(default_factory=list)
    interface_types: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)

    # Structured fields parsed from portfolio
    problems_solved: list[str] = field(default_factory=list)
    design_methods: list[str] = field(default_factory=list)
    visual_skillset: list[str] = field(default_factory=list)
    goals_motivations: str = ""

    @property
    def full_profile(self) -> str:
        """Returns combined profile text for matching."""
        sections = []

        sections.append("RESUME:\n" + self.resume_text)

        if self.portfolio_content:
            sections.append("PORTFOLIO:\n" + self.portfolio_content)

        # Append structured data if available
        structured = self._structured_summary()
        if structured:
            sections.append("STRUCTURED PROFILE:\n" + structured)

        return "\n\n".join(sections)

    def _structured_summary(self) -> str:
        """Generate a structured summary from parsed fields."""
        parts = []

        if self.technical_skills:
            parts.append(f"Technical Skills: {', '.join(self.technical_skills)}")
        if self.strengths:
            parts.append(f"Strengths: {', '.join(self.strengths)}")
        if self.soft_skills:
            parts.append(f"Soft Skills: {', '.join(self.soft_skills)}")
        if self.years_of_experience:
            parts.append(f"Years of Experience: {self.years_of_experience}")
        if self.products_worked_on:
            parts.append(f"Products Worked On: {', '.join(self.products_worked_on)}")
        if self.team_types:
            parts.append(f"Team Types: {', '.join(self.team_types)}")
        if self.interface_types:
            parts.append(f"Interface/Experience Types: {', '.join(self.interface_types)}")
        if self.deliverables:
            parts.append(f"Deliverables: {', '.join(self.deliverables)}")
        if self.problems_solved:
            parts.append(f"Problems Solved: {', '.join(self.problems_solved)}")
        if self.design_methods:
            parts.append(f"Design Process & Methods: {', '.join(self.design_methods)}")
        if self.visual_skillset:
            parts.append(f"Visual Skillset: {', '.join(self.visual_skillset)}")
        if self.goals_motivations:
            parts.append(f"Goals & Motivations: {self.goals_motivations}")

        return "\n".join(parts)
