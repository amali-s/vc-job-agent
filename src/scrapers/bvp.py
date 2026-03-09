"""Scraper for Bessemer Venture Partners (BVP) portfolio jobs."""

from .getro_base import GetroScraper


class BVPScraper(GetroScraper):
    """Scraper for Bessemer Venture Partners portfolio jobs.

    BVP's portfolio job board is at jobs.bvp.com (NOT www.bvp.com/jobs).
    """

    name = "Bessemer (BVP)"
    base_url = "https://jobs.bvp.com"
    jobs_url = "https://jobs.bvp.com/jobs"
