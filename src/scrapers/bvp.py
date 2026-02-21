"""Scraper for Bessemer Venture Partners (BVP) portfolio jobs."""

from .getro_base import GetroScraper


class BVPScraper(GetroScraper):
    """Scraper for Bessemer Venture Partners portfolio jobs (Getro-powered)."""

    name = "Bessemer (BVP)"
    base_url = "https://www.bvp.com"
    jobs_url = "https://www.bvp.com/jobs"
