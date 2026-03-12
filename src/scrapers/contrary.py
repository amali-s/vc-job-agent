"""Scraper for Contrary portfolio jobs."""

from .consider_base import ConsiderScraper


class ContraryScraper(ConsiderScraper):
    """Scraper for Contrary portfolio jobs (Consider-powered)."""

    name = "Contrary"
    base_url = "https://jobs.contrary.com"
    jobs_url = "https://jobs.contrary.com/jobs"
    board_id = "contrary"
