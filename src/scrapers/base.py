"""Base scraper class with common utilities."""

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

from ..models import Job

logger = logging.getLogger(__name__)


# Location keywords for New York and San Francisco filtering
NY_KEYWORDS = [
    "new york", "nyc", "ny, ", "brooklyn", "manhattan",
    "new york city", "new york, ny",
]
SF_KEYWORDS = [
    "san francisco", "sf", "bay area", "south bay",
    "san jose", "palo alto", "mountain view", "menlo park",
    "sunnyvale", "cupertino", "oakland", "berkeley",
    "san mateo", "redwood city", "santa clara",
]
REMOTE_KEYWORDS = ["remote", "anywhere", "distributed"]


class BaseScraper(ABC):
    """Base class for all job board scrapers."""

    name: str = "Base"
    base_url: str = ""

    # Design-related keywords for filtering
    DESIGN_KEYWORDS = [
        "product design",
        "ux design",
        "ui design",
        "ux/ui",
        "ui/ux",
        "user experience",
        "user interface",
        "interaction design",
        "visual design",
        "design system",
        "product designer",
        "ux designer",
        "ui designer",
        "senior designer",
        "staff designer",
        "principal designer",
        "design lead",
        "head of design",
        "design manager",
        "ux researcher",
        "design director",
        "brand designer",
        "graphic designer",
    ]

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })

    @abstractmethod
    def scrape(self) -> list[Job]:
        """Scrape and return list of product designer jobs."""
        pass

    def is_design_job(self, title: str, description: str = "") -> bool:
        """Check if a job is design-related based on title and description."""
        text = f"{title} {description}".lower()
        return any(keyword in text for keyword in self.DESIGN_KEYWORDS)

    def is_valid_location(self, location: str) -> bool:
        """Check if job location is in New York, San Francisco, or Remote.

        Returns True if location matches target cities or is remote.
        Returns True if location is empty/unknown (to avoid filtering out jobs with missing data).
        """
        if not location or location == "Not specified":
            return True  # Don't filter out jobs with unknown location

        loc_lower = location.lower()

        # Check for NY
        if any(kw in loc_lower for kw in NY_KEYWORDS):
            return True

        # Check for SF / Bay Area
        if any(kw in loc_lower for kw in SF_KEYWORDS):
            return True

        # Check for remote
        if any(kw in loc_lower for kw in REMOTE_KEYWORDS):
            return True

        return False

    def is_recent_posting(self, posted_date: Optional[datetime], max_days: int = 30) -> bool:
        """Check if a job posting is less than max_days old.

        Returns True if the posting is recent or if no date is available.
        """
        if posted_date is None:
            return True  # Don't filter out jobs with unknown date

        cutoff = datetime.utcnow() - timedelta(days=max_days)
        return posted_date >= cutoff

    def extract_posted_date(self, data: dict) -> Optional[datetime]:
        """Extract posted date from common job data fields."""
        date_fields = [
            "createdAt", "created_at", "publishedAt", "published_at",
            "postedAt", "posted_at", "datePosted", "date_posted",
            "listDate", "list_date", "postDate", "post_date",
        ]

        for field in date_fields:
            value = data.get(field)
            if not value:
                continue

            if isinstance(value, (int, float)):
                # Unix timestamp (seconds or milliseconds)
                try:
                    if value > 1e12:
                        return datetime.utcfromtimestamp(value / 1000)
                    return datetime.utcfromtimestamp(value)
                except (ValueError, OSError):
                    continue

            if isinstance(value, str):
                # Try common date formats
                for fmt in [
                    "%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d",
                    "%m/%d/%Y",
                    "%B %d, %Y",
                ]:
                    try:
                        return datetime.strptime(value.strip(), fmt)
                    except ValueError:
                        continue

                # Try dateutil as fallback
                try:
                    from dateutil import parser as dateutil_parser
                    return dateutil_parser.parse(value)
                except Exception:
                    continue

        return None

    def extract_salary(self, data: dict) -> Optional[str]:
        """Extract salary range from job data if present."""
        salary_fields = [
            "salary", "salaryRange", "salary_range", "compensation",
            "pay", "payRange", "pay_range", "salaryMin", "salaryMax",
        ]

        for field in salary_fields:
            value = data.get(field)
            if not value:
                continue

            if isinstance(value, str) and value.strip():
                return value.strip()
            elif isinstance(value, dict):
                min_val = value.get("min") or value.get("minimum") or value.get("from")
                max_val = value.get("max") or value.get("maximum") or value.get("to")
                currency = value.get("currency", "USD")
                if min_val and max_val:
                    return f"${min_val:,} - ${max_val:,} {currency}"
                elif min_val:
                    return f"${min_val:,}+ {currency}"
                elif max_val:
                    return f"Up to ${max_val:,} {currency}"

        # Check for salary in min/max separate fields
        min_salary = data.get("salaryMin") or data.get("salary_min") or data.get("compensationMin")
        max_salary = data.get("salaryMax") or data.get("salary_max") or data.get("compensationMax")
        if min_salary and max_salary:
            return f"${min_salary:,} - ${max_salary:,}"
        elif min_salary:
            return f"${min_salary:,}+"

        return None

    def fetch_page(self, url: str, delay: float = 1.0) -> Optional[BeautifulSoup]:
        """Fetch a page and return BeautifulSoup object."""
        try:
            time.sleep(delay)  # Rate limiting
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.text, "lxml")
        except requests.RequestException as e:
            logger.error(f"[{self.name}] Failed to fetch {url}: {e}")
            return None

    def fetch_json(self, url: str, delay: float = 1.0) -> Optional[dict]:
        """Fetch JSON from a URL."""
        try:
            time.sleep(delay)
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"[{self.name}] Failed to fetch JSON from {url}: {e}")
            return None
        except ValueError as e:
            logger.error(f"[{self.name}] Invalid JSON from {url}: {e}")
            return None

    def extract_embedded_json(self, soup: BeautifulSoup) -> Optional[dict]:
        """Extract embedded JSON data from script tags (common in React apps)."""
        for script in soup.find_all("script"):
            text = script.string or ""

            # Look for common patterns
            patterns = [
                r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
                r'window\.__PRELOADED_STATE__\s*=\s*({.*?});',
                r'"initialState"\s*:\s*({.*?})\s*[,}]',
                r'window\.__DATA__\s*=\s*({.*?});',
                r'self\.__next_f\.push\(\[.*?"jobs":\s*(\[.*?\])',
            ]

            for pattern in patterns:
                match = re.search(pattern, text, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group(1))
                    except json.JSONDecodeError:
                        continue

            # Try to find any large JSON object with job data
            if '"jobs"' in text or '"openings"' in text or '"positions"' in text:
                # Find JSON-like structures
                json_matches = re.findall(r'\{[^{}]*"(?:jobs|openings|positions)"[^{}]*\}', text)
                for json_str in json_matches:
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        continue

        return None

    def clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        if not text:
            return ""
        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def extract_location(self, text: str) -> str:
        """Extract and clean location string."""
        if not text:
            return "Not specified"
        # Clean common patterns
        text = self.clean_text(text)
        # Check for remote
        if re.search(r"\bremote\b", text, re.IGNORECASE):
            if re.search(r"\bhybrid\b", text, re.IGNORECASE):
                return f"{text} (Hybrid)"
            return text
        return text

    # Section headings that indicate qualifications/requirements content
    QUALIFICATIONS_HEADINGS = [
        "qualifications", "requirements", "what you'll need", "what we're looking for",
        "who you are", "what you bring", "must have", "minimum qualifications",
        "preferred qualifications", "basic qualifications", "required skills",
        "skills & experience", "skills and experience", "you should have",
        "you have", "about you", "ideal candidate", "what we expect",
    ]

    # Section headings that indicate the end of a qualifications block
    SECTION_END_HEADINGS = [
        "responsibilities", "what you'll do", "the role", "about the role",
        "benefits", "perks", "compensation", "how to apply", "nice to have",
        "bonus", "about us", "about the team", "our stack", "tech stack",
        "equal opportunity", "eeo",
    ]

    def fetch_job_detail(self, job: 'Job') -> 'Job':
        """Fetch the full job description from the detail page.

        Follows the job URL to extract:
        - Full description text
        - Qualifications/Requirements section (prioritized for matching)
        - Company description from the top of the posting

        Returns the job with updated fields (or unchanged on failure).
        """
        # Skip if URL is just the listing page or missing
        if not job.url or job.url == getattr(self, 'jobs_url', ''):
            return job

        try:
            soup = self.fetch_page(job.url, delay=0.3)
            if not soup:
                return job

            # Remove non-content elements
            for tag in soup.find_all(["script", "style", "nav", "header", "footer", "noscript"]):
                tag.decompose()

            # Try job-specific selectors first (most specific → least specific)
            detail_selectors = [
                ".job-description",
                "[class*='description']",
                "[class*='Description']",
                "[class*='job-detail']",
                "[class*='JobDetail']",
                "[class*='job-content']",
                "[class*='posting-']",
                "[class*='content']",
                "article",
                "main",
                "[role='main']",
            ]

            content_elem = None
            for selector in detail_selectors:
                elem = soup.select_one(selector)
                if elem and len(elem.get_text(strip=True)) > 200:
                    content_elem = elem
                    break

            # Fallback: use body
            if not content_elem:
                content_elem = soup.find("body")

            if not content_elem:
                return job

            detail_text = content_elem.get_text(separator="\n", strip=True)
            if not detail_text:
                return job

            # --- Extract company description from top of posting ---
            company_desc = self._extract_company_description(content_elem)
            if company_desc:
                job.company_description = company_desc[:2000]

            # --- Extract qualifications/requirements section ---
            qualifications = self._extract_qualifications(content_elem, detail_text)
            if qualifications:
                job.qualifications = qualifications[:4000]

            # --- Update full description ---
            detail_text_clean = self.clean_text(detail_text)
            if len(detail_text_clean) > len(job.description):
                job.description = detail_text_clean[:8000]
                logger.debug(f"[{self.name}] Enhanced description for: {job.title} ({len(detail_text_clean)} chars)")

            # Try to extract salary from detail page if we don't have one
            if not job.salary_range:
                salary_match = re.search(
                    r'\$[\d,]+(?:\s*[-–—]\s*\$[\d,]+)?(?:\s*(?:per year|/yr|/year|annually))?',
                    detail_text_clean
                )
                if salary_match:
                    job.salary_range = salary_match.group(0)

        except Exception as e:
            logger.debug(f"[{self.name}] Failed to fetch detail for {job.title}: {e}")

        return job

    def _extract_company_description(self, content_elem) -> str:
        """Extract company description from the top of the job posting.

        Typically the first paragraph(s) before any section headings describe
        the company and its mission.
        """
        paragraphs = []
        all_headings = set(self.QUALIFICATIONS_HEADINGS + self.SECTION_END_HEADINGS)

        for child in content_elem.children:
            text = ""
            if hasattr(child, 'get_text'):
                text = child.get_text(strip=True)
            elif isinstance(child, str):
                text = child.strip()

            if not text:
                continue

            text_lower = text.lower()

            # Stop when we hit a known section heading
            if any(heading in text_lower for heading in all_headings):
                break

            # Also stop at heading tags that look like section breaks
            if hasattr(child, 'name') and child.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                # If it's a short heading (not the job title), treat as section start
                if len(text) < 100 and len(paragraphs) > 0:
                    break

            # Collect paragraph-length text (skip very short fragments)
            if len(text) > 40:
                paragraphs.append(text)

            # Cap at ~3 paragraphs for company description
            if len(paragraphs) >= 3:
                break

        return self.clean_text("\n".join(paragraphs))

    def _extract_qualifications(self, content_elem, full_text: str) -> str:
        """Extract the qualifications/requirements section from the job posting.

        Uses two strategies:
        1. DOM-based: Find heading elements that match qualification keywords,
           then collect all sibling content until the next section heading.
        2. Text-based: Split full text by lines and capture content between
           qualification headings and the next section heading.
        """
        # Strategy 1: DOM-based extraction using heading elements
        headings = content_elem.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b'])
        for heading in headings:
            heading_text = heading.get_text(strip=True).lower()
            if not any(q in heading_text for q in self.QUALIFICATIONS_HEADINGS):
                continue

            # Found a qualifications heading — collect following content
            sections = []
            sibling = heading.find_next_sibling()
            while sibling:
                sib_text = sibling.get_text(strip=True)
                sib_lower = sib_text.lower()

                # Stop at the next major section heading
                if sibling.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                    if any(end in sib_lower for end in self.SECTION_END_HEADINGS):
                        break
                    # Also stop at a new qualifications-type heading (e.g. "Preferred Qualifications")
                    # but only if we already have content
                    if sections and any(q in sib_lower for q in self.QUALIFICATIONS_HEADINGS):
                        # Include this sub-section too by continuing
                        pass
                    elif sections:
                        break

                if sib_text:
                    sections.append(sib_text)

                sibling = sibling.find_next_sibling()

            if sections:
                return self.clean_text("\n".join(sections))

        # Strategy 2: Text-based fallback using line splitting
        lines = full_text.split("\n")
        capture = False
        captured = []

        for line in lines:
            line_stripped = line.strip()
            line_lower = line_stripped.lower()

            if any(q in line_lower for q in self.QUALIFICATIONS_HEADINGS):
                capture = True
                continue

            if capture:
                # Stop at end-of-section headings
                if any(end in line_lower for end in self.SECTION_END_HEADINGS):
                    break
                if line_stripped:
                    captured.append(line_stripped)

        if captured:
            return self.clean_text("\n".join(captured))

        return ""

    def log_found(self, count: int):
        """Log number of jobs found."""
        logger.info(f"[{self.name}] Found {count} design jobs")
