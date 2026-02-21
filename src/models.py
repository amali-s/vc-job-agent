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
        }


@dataclass
class MatchResult:
    """Result of matching a job against a candidate profile."""

    job: Job
    match_percentage: int  # 0-100
    matching_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    recommendation: str = ""

    @property
    def is_good_match(self) -> bool:
        """Returns True if match percentage is >= 60%."""
        return self.match_percentage >= 60

    def to_dict(self) -> dict:
        return {
            "job": self.job.to_dict(),
            "match_percentage": self.match_percentage,
            "matching_skills": self.matching_skills,
            "missing_skills": self.missing_skills,
            "recommendation": self.recommendation,
        }


@dataclass
class CandidateProfile:
    """Combined profile from resume and portfolio."""

    resume_text: str
    portfolio_content: str
    name: str = ""
    email: str = ""
    skills: list[str] = field(default_factory=list)

    @property
    def full_profile(self) -> str:
        """Returns combined profile text for matching."""
        return f"""
RESUME:
{self.resume_text}

PORTFOLIO:
{self.portfolio_content}
""".strip()
