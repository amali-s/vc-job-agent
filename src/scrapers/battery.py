"""Scraper for Battery Ventures portfolio jobs."""

from .getro_base import GetroScraper


class BatteryScraper(GetroScraper):
    """Scraper for Battery Ventures portfolio jobs (Getro-powered)."""

    name = "Battery Ventures"
    base_url = "https://jobs.battery.com"
    jobs_url = "https://jobs.battery.com/jobs"
