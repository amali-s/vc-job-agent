"""Scraper for Pear VC portfolio jobs."""

import logging
from datetime import datetime

from .base import BaseScraper
from ..models import Job

logger = logging.getLogger(__name__)


class PearScraper(BaseScraper):
    """Scraper for Pear VC portfolio jobs.

    Pear VC does not have a Getro-powered portfolio job board.
    Their pear.vc/talent page is a talent services info page, not a job listing.
    We scrape from Pear VC's portfolio page and check individual
    company career pages via Greenhouse API.
    """

    name = "Pear VC"
    base_url = "https://pear.vc"
    jobs_url = "https://pear.vc/portfolio"

    # Major Pear VC portfolio companies with Greenhouse job boards
    PORTFOLIO_BOARDS = [
        ("Vanta", "https://boards.greenhouse.io/vanta"),
        ("Affinity", "https://boards.greenhouse.io/affinity"),
        ("Branch", "https://boards.greenhouse.io/branch"),
        ("Webflow", "https://boards.greenhouse.io/webflow"),
        ("Ironclad", "https://boards.greenhouse.io/ironcladapp"),
    ]

    def scrape(self) -> list[Job]:
        """Scrape product designer jobs from Pear VC portfolio companies."""
        jobs = []

        # Strategy 1: Try the portfolio page for embedded job links
        logger.info(f"[{self.name}] Checking portfolio page for job links...")
        soup = self.fetch_page(self.jobs_url)
        if soup:
            links = soup.select(
                "a[href*='careers'], a[href*='jobs'], "
                "a[href*='greenhouse'], a[href*='lever.co']"
            )
            for link in links:
                href = link.get("href", "")
                text = link.get_text(strip=True)
                if href and self.is_design_job(text):
                    jobs.append(Job(
                        title=text,
                        company="Pear VC Portfolio",
                        location="Not specified",
                        url=href if href.startswith("http") else f"{self.base_url}{href}",
                        description="",
                        source=self.name,
                        scraped_at=datetime.utcnow(),
                    ))

        # Strategy 2: Check Greenhouse boards for known portfolio companies
        if not jobs:
            logger.info(f"[{self.name}] Checking {len(self.PORTFOLIO_BOARDS)} portfolio company boards...")
            for company_name, board_url in self.PORTFOLIO_BOARDS:
                try:
                    json_url = board_url.rstrip("/")
                    data = self.fetch_json(f"{json_url}/jobs?content=true", delay=0.5)
                    if data and isinstance(data, dict):
                        for jd in data.get("jobs", []):
                            title = jd.get("title", "")
                            if not self.is_design_job(title):
                                continue
                            loc = jd.get("location", {})
                            loc_name = loc.get("name", "") if isinstance(loc, dict) else ""
                            if not self.is_valid_location(loc_name):
                                continue
                            jobs.append(Job(
                                title=title,
                                company=company_name,
                                location=self.extract_location(loc_name),
                                url=jd.get("absolute_url", board_url),
                                description=self.clean_text(jd.get("content", ""))[:8000],
                                source=self.name,
                                scraped_at=datetime.utcnow(),
                            ))
                except Exception as e:
                    logger.debug(f"[{self.name}] Error checking {company_name}: {e}")

        if not jobs:
            logger.warning(
                f"[{self.name}] No design jobs found. Pear VC lacks a centralized "
                f"job board — results are sourced from individual portfolio companies."
            )

        self.log_found(len(jobs))
        return jobs
