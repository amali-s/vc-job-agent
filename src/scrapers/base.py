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

    def log_found(self, count: int):
        """Log number of jobs found."""
        logger.info(f"[{self.name}] Found {count} design jobs")
