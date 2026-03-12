"""Scraper for Greylock portfolio jobs."""

from .consider_base import ConsiderScraper


class GreylockScraper(ConsiderScraper):
    """Scraper for Greylock portfolio jobs (Consider-powered)."""

    name = "Greylock"
    base_url = "https://jobs.greylock.com"
    jobs_url = "https://jobs.greylock.com/jobs"
    board_id = "greylock-partners"
