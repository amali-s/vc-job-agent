"""Scraper for Accel portfolio jobs."""

from .getro_base import GetroScraper


class AccelScraper(GetroScraper):
    """Scraper for Accel portfolio jobs (Getro-powered)."""

    name = "Accel"
    base_url = "https://jobs.accel.com"
    jobs_url = "https://jobs.accel.com/jobs"
