"""Scraper for Greylock portfolio jobs."""

from .getro_base import GetroScraper


class GreylockScraper(GetroScraper):
    """Scraper for Greylock portfolio jobs (Getro-powered)."""

    name = "Greylock"
    base_url = "https://jobs.greylock.com"
    jobs_url = "https://jobs.greylock.com/jobs"
