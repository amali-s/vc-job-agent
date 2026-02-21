"""Scraper for Antler portfolio jobs."""

from .getro_base import GetroScraper


class AntlerScraper(GetroScraper):
    """Scraper for Antler portfolio jobs (Getro-powered)."""

    name = "Antler"
    base_url = "https://careers.antler.co"
    jobs_url = "https://careers.antler.co/jobs"
