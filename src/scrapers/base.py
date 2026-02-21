"""Base scraper class with common utilities."""

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Optional

import requests
from bs4 import BeautifulSoup

from ..models import Job

logger = logging.getLogger(__name__)


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
