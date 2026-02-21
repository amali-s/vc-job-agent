"""Scraper for Sequoia Capital portfolio jobs."""

from .getro_base import GetroScraper


class SequoiaScraper(GetroScraper):
    """Scraper for Sequoia portfolio jobs (Getro-powered)."""

    name = "Sequoia"
    base_url = "https://jobs.sequoiacap.com"
    jobs_url = "https://jobs.sequoiacap.com/jobs"
