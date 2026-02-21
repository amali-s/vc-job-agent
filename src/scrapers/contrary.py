"""Scraper for Contrary portfolio jobs."""

from .getro_base import GetroScraper


class ContraryScraper(GetroScraper):
    """Scraper for Contrary portfolio jobs (Getro-powered)."""

    name = "Contrary"
    base_url = "https://jobs.contrary.com"
    jobs_url = "https://jobs.contrary.com/jobs"
