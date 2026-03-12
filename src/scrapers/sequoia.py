"""Scraper for Sequoia Capital portfolio jobs."""

from .consider_base import ConsiderScraper


class SequoiaScraper(ConsiderScraper):
    """Scraper for Sequoia portfolio jobs (Consider-powered)."""

    name = "Sequoia"
    base_url = "https://jobs.sequoiacap.com"
    jobs_url = "https://jobs.sequoiacap.com/jobs"
    board_id = "sequoia-capital"
