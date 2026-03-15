"""Resume and portfolio parser with structured extraction."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .models import CandidateProfile

logger = logging.getLogger(__name__)

# Prompt for structured resume extraction
RESUME_EXTRACTION_PROMPT = """Analyze this resume and extract structured information. Return a JSON object with these fields:

{{
    "technical_skills": ["list of technical/design tools and hard skills, e.g. Figma, Sketch, Prototyping, HTML/CSS"],
    "strengths": ["list of professional strengths, e.g. Design Systems, User Research, Cross-functional Leadership"],
    "soft_skills": ["list of soft skills, e.g. Communication, Collaboration, Mentoring, Stakeholder Management"],
    "years_of_experience": "total years of professional design experience as a string, e.g. '5 years'",
    "products_worked_on": ["list of product types, e.g. SaaS B2B, Consumer Mobile App, E-commerce Platform, AI Tool, Automation Platform"],
    "team_types": ["list of team types worked in, e.g. Cross-functional product team, Design team of 5, Startup founding team"],
    "interface_types": ["list of interface/platform types designed, e.g. Web dashboard, Mobile app (iOS), Mobile app (Android), Desktop application, Desktop browser app, Mobile browser app"],
    "deliverables": ["list of specific deliverable types produced, e.g. Design system, Component library, Dashboard, Admin panel, RBAC/permissions, Data visualization, Onboarding flow, Trial/freemium experience, Settings page, Checkout flow, Landing page, Complex forms, Notification system"]
}}

Be thorough — extract everything relevant. Only return the JSON, no other text.

RESUME TEXT:
{text}"""

# Prompt for structured portfolio extraction
PORTFOLIO_EXTRACTION_PROMPT = """Analyze this portfolio website content and extract structured information. Return a JSON object with these fields:

{{
    "years_of_experience": "years of experience mentioned or inferred, e.g. '6 years'",
    "products_worked_on": ["list of product types shown in portfolio, e.g. SaaS Platform, Mobile App, AI Tool, Automation Platform, B2B Enterprise"],
    "problems_solved": ["list of problem types from case studies, e.g. Improved onboarding conversion, Reduced user churn, Simplified complex workflow"],
    "design_methods": ["list of design processes and methods, e.g. User interviews, A/B testing, Design sprints, Usability testing, Journey mapping"],
    "team_types": ["list of team types collaborated with, e.g. Engineering team, Product managers, Data science, Marketing"],
    "visual_skillset": ["list of visual design skills, e.g. Typography, Illustration, Motion design, Brand identity, Icon design"],
    "interface_types": ["list of interface/platform types shown, e.g. Web dashboard, Mobile app, Desktop application, Desktop browser app, Mobile browser app"],
    "deliverables": ["list of specific deliverable types shown in case studies, e.g. Design system, Dashboard, RBAC/permissions, Data visualization, Onboarding flow, Trial experience, Settings page, Gantt chart, DNS management interface"],
    "goals_motivations": "goals and motivations from about/bio section, as a short summary string"
}}

Be thorough — extract everything relevant from case studies and about sections. Only return the JSON, no other text.

PORTFOLIO CONTENT:
{text}"""


class ResumeParser:
    """Parser for extracting profile information from resume PDF and portfolio website."""

    # Portfolio subpages to scrape for design process and work experience
    PORTFOLIO_SUBPAGES = [
        "/about",
        "/trial",
        "/dns-feature",
        "/cloud-details",
        "/gantt-chart",
    ]

    def __init__(
        self,
        resume_path: Optional[str] = None,
        portfolio_url: Optional[str] = None,
    ):
        self.resume_path = resume_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "resume.pdf"
        )
        self.portfolio_url = portfolio_url or os.environ.get(
            "PORTFOLIO_URL", "https://www.amayamali.com/"
        )

    def parse(self) -> CandidateProfile:
        """Parse resume and portfolio to create a candidate profile."""
        resume_text = self._parse_resume()
        portfolio_content = self._scrape_portfolio()

        profile = CandidateProfile(
            resume_text=resume_text,
            portfolio_content=portfolio_content,
        )

        # Extract structured data using LLM
        self._extract_structured_resume(profile)
        self._extract_structured_portfolio(profile)

        return profile

    def _parse_resume(self) -> str:
        """Extract text from resume PDF."""
        if not os.path.exists(self.resume_path):
            logger.warning(f"Resume not found at {self.resume_path}")
            return ""

        try:
            import fitz  # PyMuPDF

            doc = fitz.open(self.resume_path)
            text_parts = []

            for page in doc:
                text_parts.append(page.get_text())

            doc.close()

            full_text = "\n".join(text_parts)
            logger.info(f"Extracted {len(full_text)} characters from resume")
            return full_text

        except ImportError:
            logger.error("PyMuPDF not installed. Cannot parse PDF.")
            return ""
        except Exception as e:
            logger.error(f"Error parsing resume: {e}")
            return ""

    def _scrape_portfolio(self) -> str:
        """Scrape portfolio website and case study subpages for profile information.

        Fetches the main portfolio URL plus all configured subpages (about, case studies)
        to build a complete picture of the candidate's design process and work experience.
        """
        if not self.portfolio_url:
            return ""

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        # Build full list of URLs: main page + subpages
        base_url = self.portfolio_url.rstrip("/")
        urls_to_scrape = [self.portfolio_url]
        for subpage in self.PORTFOLIO_SUBPAGES:
            urls_to_scrape.append(f"{base_url}{subpage}")

        all_sections = []

        for url in urls_to_scrape:
            try:
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "lxml")

                # Remove script and style elements
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()

                # Extract text content
                page_text = soup.get_text(separator="\n", strip=True)
                lines = [line.strip() for line in page_text.split("\n") if line.strip()]
                page_text = "\n".join(lines)

                if not page_text:
                    continue

                # Label each page's content by its source
                page_label = url.replace(base_url, "").strip("/") or "home"
                all_sections.append(f"[PAGE: {page_label}]\n{page_text}")

                # Also try to get project descriptions from common portfolio sections
                for section in soup.select(".project, .work, .case-study, [class*='project']"):
                    project_text = section.get_text(separator=" ", strip=True)
                    if project_text:
                        all_sections.append(f"[PROJECT from {page_label}]\n{project_text}")

                logger.info(f"Scraped {len(page_text)} characters from {page_label}")

            except requests.RequestException as e:
                logger.warning(f"Could not fetch portfolio page {url}: {e}")
                continue
            except Exception as e:
                logger.warning(f"Error parsing portfolio page {url}: {e}")
                continue

        combined = "\n\n---\n\n".join(all_sections)
        logger.info(f"Total portfolio content: {len(combined)} characters from {len(all_sections)} sections")
        return combined[:30000]  # Increased limit for multiple pages

    def _extract_structured_resume(self, profile: CandidateProfile) -> None:
        """Use LLM to extract structured data from resume text."""
        if not profile.resume_text:
            return

        try:
            result = self._call_llm(
                RESUME_EXTRACTION_PROMPT.format(text=profile.resume_text[:8000])
            )
            if not result:
                return

            data = json.loads(self._clean_json(result))
            profile.technical_skills = data.get("technical_skills", [])
            profile.strengths = data.get("strengths", [])
            profile.soft_skills = data.get("soft_skills", [])
            profile.years_of_experience = data.get("years_of_experience", "")
            profile.products_worked_on = data.get("products_worked_on", [])
            profile.team_types = data.get("team_types", [])
            profile.interface_types = data.get("interface_types", [])
            profile.deliverables = data.get("deliverables", [])
            logger.info("Extracted structured resume data successfully")

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Could not extract structured resume data: {e}")
        except Exception as e:
            logger.warning(f"LLM extraction failed for resume: {e}")

    def _extract_structured_portfolio(self, profile: CandidateProfile) -> None:
        """Use LLM to extract structured data from portfolio content."""
        if not profile.portfolio_content:
            return

        try:
            result = self._call_llm(
                PORTFOLIO_EXTRACTION_PROMPT.format(text=profile.portfolio_content[:15000])
            )
            if not result:
                return

            data = json.loads(self._clean_json(result))

            # Merge years of experience (prefer resume, fallback to portfolio)
            if not profile.years_of_experience:
                profile.years_of_experience = data.get("years_of_experience", "")

            # Extend product types (deduplicate)
            portfolio_products = data.get("products_worked_on", [])
            existing = set(p.lower() for p in profile.products_worked_on)
            for p in portfolio_products:
                if p.lower() not in existing:
                    profile.products_worked_on.append(p)
                    existing.add(p.lower())

            # Extend team types
            portfolio_teams = data.get("team_types", [])
            existing_teams = set(t.lower() for t in profile.team_types)
            for t in portfolio_teams:
                if t.lower() not in existing_teams:
                    profile.team_types.append(t)
                    existing_teams.add(t.lower())

            # Extend interface types from portfolio
            portfolio_interfaces = data.get("interface_types", [])
            existing_interfaces = set(t.lower() for t in profile.interface_types)
            for t in portfolio_interfaces:
                if t.lower() not in existing_interfaces:
                    profile.interface_types.append(t)
                    existing_interfaces.add(t.lower())

            # Extend deliverables from portfolio
            portfolio_deliverables = data.get("deliverables", [])
            existing_deliverables = set(d.lower() for d in profile.deliverables)
            for d in portfolio_deliverables:
                if d.lower() not in existing_deliverables:
                    profile.deliverables.append(d)
                    existing_deliverables.add(d.lower())

            profile.problems_solved = data.get("problems_solved", [])
            profile.design_methods = data.get("design_methods", [])
            profile.visual_skillset = data.get("visual_skillset", [])
            profile.goals_motivations = data.get("goals_motivations", "")
            logger.info("Extracted structured portfolio data successfully")

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Could not extract structured portfolio data: {e}")
        except Exception as e:
            logger.warning(f"LLM extraction failed for portfolio: {e}")

    def _call_llm(self, prompt: str) -> Optional[str]:
        """Call Anthropic Claude API for structured extraction."""
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

        if not anthropic_key:
            logger.warning("ANTHROPIC_API_KEY not set — skipping structured extraction")
            return None

        import anthropic
        client = anthropic.Anthropic(api_key=anthropic_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    def _clean_json(self, text: str) -> str:
        """Clean potential markdown code blocks from JSON response."""
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return text


def get_profile() -> CandidateProfile:
    """Convenience function to get the candidate profile."""
    parser = ResumeParser()
    return parser.parse()
