"""Scraper for NEA portfolio jobs."""

from .getro_base import GetroScraper


class NEAScraper(GetroScraper):
    """Scraper for NEA portfolio jobs (Getro-powered)."""

    name = "NEA"
    base_url = "https://careers.nea.com"
    jobs_url = "https://careers.nea.com/jobs"
