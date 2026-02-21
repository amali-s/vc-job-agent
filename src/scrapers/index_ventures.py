"""Scraper for Index Ventures portfolio jobs."""

import logging
from datetime import datetime

from .base import BaseScraper
from ..models import Job

logger = logging.getLogger(__name__)


class IndexVenturesScraper(BaseScraper):
    """Scraper for Index Ventures portfolio jobs."""

    name = "Index Ventures"
    base_url = "https://www.indexventures.com"
    jobs_url = "https://www.indexventures.com/startup-jobs"

    def scrape(self) -> list[Job]:
        """Scrape product designer jobs from Index Ventures portfolio."""
        jobs = []

        soup = self.fetch_page(self.jobs_url)

        if not soup:
            logger.warning(f"[{self.name}] Could not fetch job listings")
            return jobs

        # Index Ventures uses a custom job board
        # Look for job listings in various formats
        job_elements = soup.select(
            ".job, .job-listing, .job-card, [class*='job-item'], "
            "[class*='JobCard'], article, .card"
        )

        if not job_elements:
            job_elements = soup.select("a[href*='/job'], a[href*='lever.co'], a[href*='greenhouse']")

        for elem in job_elements:
            try:
                title_elem = elem.select_one("h2, h3, h4, .title, [class*='title']")
                title = title_elem.get_text(strip=True) if title_elem else ""

                if not title:
                    title = elem.get_text(strip=True)[:100]

                if not self.is_design_job(title):
                    continue

                company_elem = elem.select_one(".company, [class*='company'], [class*='startup']")
                company = company_elem.get_text(strip=True) if company_elem else "Index Ventures Portfolio"

                location_elem = elem.select_one(".location, [class*='location']")
                location = self.extract_location(
                    location_elem.get_text(strip=True) if location_elem else ""
                )

                url = elem.get("href") if elem.name == "a" else None
                if not url:
                    link = elem.select_one("a")
                    url = link.get("href") if link else ""

                if url and not url.startswith("http"):
                    url = f"{self.base_url}{url}"

                jobs.append(
                    Job(
                        title=title,
                        company=company,
                        location=location,
                        url=url or self.jobs_url,
                        description="",
                        source=self.name,
                        scraped_at=datetime.utcnow(),
                    )
                )

            except Exception as e:
                logger.debug(f"[{self.name}] Error parsing job element: {e}")
                continue

        self.log_found(len(jobs))
        return jobs
