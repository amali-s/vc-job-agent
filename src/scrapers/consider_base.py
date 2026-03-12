"""Base scraper for Consider-powered job boards (used by many VCs).

Consider (formerly Getro) hosts portfolio job boards for VCs like a16z,
Sequoia, Greylock, etc. This scraper calls the Consider API directly
via POST /api-boards/search-jobs instead of scraping HTML.

Each subclass defines: name, base_url, jobs_url, board_id.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base import BaseScraper
from ..models import Job

logger = logging.getLogger(__name__)

# Strategy cache shared with getro_base.py
_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_CACHE_PATH = _CACHE_DIR / ".strategy_cache.json"


def _load_strategy_cache() -> dict:
    try:
        if _CACHE_PATH.exists():
            with open(_CACHE_PATH, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"Could not load strategy cache: {e}")
    return {}


def _save_strategy_cache(cache: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.debug(f"Could not save strategy cache: {e}")


class ConsiderScraper(BaseScraper):
    """Base scraper for Consider-powered VC job boards.

    Subclasses must set:
        name      - display name (e.g. "a16z")
        base_url  - the board's base URL (e.g. "https://portfoliojobs.a16z.com")
        jobs_url  - the board's jobs page URL
        board_id  - the Consider board slug (e.g. "andreessen-horowitz")
    """

    board_id: str = ""

    # Search queries to run (broader set catches more design roles)
    SEARCH_QUERIES = [
        "product designer",
        "ux designer",
        "ui designer",
        "design",
    ]

    # Number of results per API call
    PAGE_SIZE = 50

    def scrape(self) -> list[Job]:
        """Scrape design jobs via the Consider API."""
        jobs = []
        seen = set()  # (title, company, url) for dedup

        for query in self.SEARCH_QUERIES:
            new_jobs = self._search_jobs(query)
            for job in new_jobs:
                key = (job.title, job.company, job.url)
                if key not in seen:
                    seen.add(key)
                    jobs.append(job)

            if jobs:
                logger.debug(f"[{self.name}] {len(jobs)} jobs after query '{query}'")

        # Cache the strategy so other code knows Consider API works
        cache = _load_strategy_cache()
        if jobs:
            cache[self.name] = "consider_api"
            _save_strategy_cache(cache)
        elif self.name in cache:
            del cache[self.name]
            _save_strategy_cache(cache)
            logger.warning(f"[{self.name}] No jobs found via Consider API (board_id={self.board_id})")

        self.log_found(len(jobs))
        return jobs

    def _search_jobs(self, query: str) -> list[Job]:
        """Call the Consider search-jobs API for a single query."""
        api_url = f"{self.base_url}/api-boards/search-jobs"
        payload = {
            "meta": {"size": self.PAGE_SIZE},
            "board": {"id": self.board_id, "isParent": True},
            "query": {
                "titlePrefix": query,
                "promoteFeatured": True,
            },
            "grouped": True,
        }

        try:
            time.sleep(0.5)
            response = self.session.post(api_url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"[{self.name}] Consider API error for query '{query}': {e}")
            return []

        return self._parse_grouped_response(data)

    def _parse_grouped_response(self, data: dict) -> list[Job]:
        """Parse the grouped Consider API response.

        Response structure:
            { "jobs": [ { "company": {...}, "jobs": [...] }, ... ] }
        """
        jobs = []
        groups = data.get("jobs", [])

        for group in groups:
            if not isinstance(group, dict):
                continue

            company_info = group.get("company", {})
            company_name = company_info.get("name", f"{self.name} Portfolio")

            for job_data in group.get("jobs", []):
                job = self._parse_consider_job(job_data, company_name)
                if job:
                    jobs.append(job)

        return jobs

    def _parse_consider_job(self, data: dict, company_name: str) -> Optional[Job]:
        """Parse a single job from Consider API response."""
        try:
            title = data.get("title", "")
            if not title:
                return None

            if not self.is_design_job(title):
                return None

            # Location: Consider uses a locations list
            locations = data.get("locations", [])
            if isinstance(locations, list) and locations:
                location = ", ".join(str(loc) for loc in locations[:3])
            else:
                location = "Not specified"

            # Remote/hybrid status
            is_remote = data.get("remote", False)
            is_hybrid = data.get("hybrid", False)
            if is_remote and "remote" not in location.lower():
                location = f"{location} (Remote)".strip() if location and location != "Not specified" else "Remote"
            elif is_hybrid and "hybrid" not in location.lower():
                location = f"{location} (Hybrid)".strip() if location and location != "Not specified" else "Hybrid"

            if not self.is_valid_location(location):
                return None

            # URL: prefer applyUrl, fall back to url
            url = data.get("applyUrl", "") or data.get("url", "")
            if not url:
                job_id = data.get("jobId", "")
                if job_id:
                    url = f"{self.jobs_url}?jobId={job_id}"
                else:
                    url = self.jobs_url

            # Timestamp
            posted_date = None
            timestamp = data.get("timeStamp", "")
            if timestamp:
                try:
                    posted_date = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    posted_date = self.extract_posted_date(data)
            else:
                posted_date = self.extract_posted_date(data)

            if not self.is_recent_posting(posted_date):
                return None

            # Salary
            salary_range = None
            salary_data = data.get("salary", {})
            if isinstance(salary_data, dict):
                min_val = salary_data.get("minValue")
                max_val = salary_data.get("maxValue")
                currency_raw = salary_data.get("currency", "USD")
                period_raw = salary_data.get("period", "")
                # Currency/period can be dicts like {"label": "USD", "value": "USD"}
                currency = currency_raw.get("value", "USD") if isinstance(currency_raw, dict) else str(currency_raw or "USD")
                period = period_raw.get("value", "") if isinstance(period_raw, dict) else str(period_raw or "")
                if min_val and max_val:
                    salary_range = f"${min_val:,} - ${max_val:,} {currency}"
                    if period:
                        salary_range += f" ({period})"
                elif min_val:
                    salary_range = f"${min_val:,}+ {currency}"

            # Use company name from the job itself if available
            job_company = data.get("companyName", "") or company_name

            return Job(
                title=title,
                company=job_company,
                location=self.extract_location(location),
                url=url,
                description="",  # Consider API doesn't include full descriptions
                source=self.name,
                scraped_at=datetime.utcnow(),
                remote=is_remote,
                salary_range=salary_range,
                posted_date=posted_date,
            )

        except Exception as e:
            logger.debug(f"[{self.name}] Error parsing Consider job: {e}")
            return None
