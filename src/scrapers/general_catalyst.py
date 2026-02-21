"""Scraper for General Catalyst portfolio jobs."""

from .getro_base import GetroScraper


class GeneralCatalystScraper(GetroScraper):
    """Scraper for General Catalyst portfolio jobs (Getro-powered)."""

    name = "General Catalyst"
    base_url = "https://jobs.generalcatalyst.com"
    jobs_url = "https://jobs.generalcatalyst.com/jobs"
