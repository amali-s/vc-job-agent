"""Scraper for Pear VC portfolio jobs.

Pear VC has no centralized job board. We check known portfolio companies
via Greenhouse API and Ashby API.
"""

import logging
import time
from datetime import datetime

from .base import BaseScraper
from ..models import Job

logger = logging.getLogger(__name__)


class PearScraper(BaseScraper):
    """Scraper for Pear VC portfolio jobs.

    Checks individual portfolio company career pages via their ATS APIs.
    """

    name = "Pear VC"
    base_url = "https://pear.vc"
    jobs_url = "https://pear.vc/portfolio"

    # Portfolio companies with Greenhouse boards (boards-api.greenhouse.io)
    GREENHOUSE_BOARDS = [
        ("Affinity", "affinity"),
        ("Branch", "branch"),
        ("Webflow", "webflow"),
    ]

    # Portfolio companies with Ashby boards (api.ashbyhq.com)
    ASHBY_BOARDS = [
        ("Vanta", "vanta"),
        ("Ironclad", "ironcladhq"),
    ]

    def scrape(self) -> list[Job]:
        """Scrape product designer jobs from Pear VC portfolio companies."""
        jobs = []

        logger.info(
            f"[{self.name}] Checking {len(self.GREENHOUSE_BOARDS)} Greenhouse + "
            f"{len(self.ASHBY_BOARDS)} Ashby portfolio boards..."
        )

        # Check Greenhouse boards
        for company_name, slug in self.GREENHOUSE_BOARDS:
            new_jobs = self._scrape_greenhouse(company_name, slug)
            jobs.extend(new_jobs)

        # Check Ashby boards
        for company_name, slug in self.ASHBY_BOARDS:
            new_jobs = self._scrape_ashby(company_name, slug)
            jobs.extend(new_jobs)

        if not jobs:
            logger.warning(
                f"[{self.name}] No design jobs found across portfolio companies."
            )

        self.log_found(len(jobs))
        return jobs

    def _scrape_greenhouse(self, company_name: str, slug: str) -> list[Job]:
        """Fetch design jobs from a Greenhouse board."""
        jobs = []
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

        try:
            data = self.fetch_json(api_url, delay=0.5)
            if not data or not isinstance(data, dict):
                logger.debug(f"[{self.name}] No data from Greenhouse for {company_name}")
                return jobs

            for jd in data.get("jobs", []):
                title = jd.get("title", "")
                if not self.is_design_job(title):
                    continue

                loc = jd.get("location", {})
                loc_name = loc.get("name", "") if isinstance(loc, dict) else str(loc)
                if not self.is_valid_location(loc_name):
                    continue

                posted_date = self.extract_posted_date(jd)

                jobs.append(Job(
                    title=title,
                    company=company_name,
                    location=self.extract_location(loc_name),
                    url=jd.get("absolute_url", f"https://boards.greenhouse.io/{slug}"),
                    description=self.clean_text(jd.get("content") or "")[:8000],
                    source=self.name,
                    scraped_at=datetime.utcnow(),
                    posted_date=posted_date,
                ))
        except Exception as e:
            logger.debug(f"[{self.name}] Error checking Greenhouse for {company_name}: {e}")

        return jobs

    def _scrape_ashby(self, company_name: str, slug: str) -> list[Job]:
        """Fetch design jobs from an Ashby board."""
        jobs = []
        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"

        try:
            data = self.fetch_json(api_url, delay=0.5)
            if not data or not isinstance(data, dict):
                logger.debug(f"[{self.name}] No data from Ashby for {company_name}")
                return jobs

            for jd in data.get("jobs", []):
                title = jd.get("title", "")
                if not self.is_design_job(title):
                    continue

                loc = jd.get("location", "")
                if isinstance(loc, dict):
                    loc = loc.get("name", "")
                loc = str(loc)
                if not self.is_valid_location(loc):
                    continue

                url = jd.get("jobUrl", "") or jd.get("applyUrl", "")
                if not url:
                    job_id = jd.get("id", "")
                    url = f"https://jobs.ashbyhq.com/{slug}/{job_id}" if job_id else f"https://jobs.ashbyhq.com/{slug}"

                posted_date = self.extract_posted_date(jd)

                jobs.append(Job(
                    title=title,
                    company=company_name,
                    location=self.extract_location(loc),
                    url=url,
                    description=self.clean_text(jd.get("descriptionPlain") or "")[:8000],
                    source=self.name,
                    scraped_at=datetime.utcnow(),
                    posted_date=posted_date,
                ))
        except Exception as e:
            logger.debug(f"[{self.name}] Error checking Ashby for {company_name}: {e}")

        return jobs
