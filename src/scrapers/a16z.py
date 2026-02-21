"""Scraper for a16z portfolio jobs."""

from .getro_base import GetroScraper


class A16ZScraper(GetroScraper):
    """Scraper for a16z portfolio jobs (Getro-powered)."""

    name = "a16z"
    base_url = "https://portfoliojobs.a16z.com"
    jobs_url = "https://portfoliojobs.a16z.com/jobs"
