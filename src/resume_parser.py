"""Resume and portfolio parser."""

import logging
import os
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .models import CandidateProfile

logger = logging.getLogger(__name__)


class ResumeParser:
    """Parser for extracting profile information from resume PDF and portfolio website."""

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

        return CandidateProfile(
            resume_text=resume_text,
            portfolio_content=portfolio_content,
        )

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
        """Scrape portfolio website for additional profile information."""
        if not self.portfolio_url:
            return ""

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            response = requests.get(self.portfolio_url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Extract text content
            text = soup.get_text(separator="\n", strip=True)

            # Clean up whitespace
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            text = "\n".join(lines)

            # Also try to get project descriptions from common portfolio sections
            projects = []
            for section in soup.select(".project, .work, .case-study, [class*='project']"):
                project_text = section.get_text(separator=" ", strip=True)
                if project_text:
                    projects.append(project_text)

            if projects:
                text += "\n\nPROJECTS:\n" + "\n---\n".join(projects[:10])

            logger.info(f"Scraped {len(text)} characters from portfolio")
            return text[:20000]  # Limit portfolio content

        except requests.RequestException as e:
            logger.error(f"Error scraping portfolio: {e}")
            return ""
        except Exception as e:
            logger.error(f"Error parsing portfolio HTML: {e}")
            return ""


def get_profile() -> CandidateProfile:
    """Convenience function to get the candidate profile."""
    parser = ResumeParser()
    return parser.parse()
