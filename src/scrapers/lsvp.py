"""Scraper for LSVP (Lightspeed Venture Partners) portfolio jobs."""

from .getro_base import GetroScraper


class LSVPScraper(GetroScraper):
    """Scraper for LSVP portfolio jobs."""

    name = "LSVP"
    base_url = "https://jobs.lsvp.com"
    jobs_url = "https://jobs.lsvp.com/jobs"
