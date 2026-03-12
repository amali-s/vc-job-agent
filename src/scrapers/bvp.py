"""Scraper for Bessemer Venture Partners (BVP) portfolio jobs."""

from .consider_base import ConsiderScraper


class BVPScraper(ConsiderScraper):
    """Scraper for Bessemer Venture Partners portfolio jobs (Consider-powered).

    BVP's portfolio job board is at jobs.bvp.com (NOT www.bvp.com/jobs).
    """

    name = "Bessemer (BVP)"
    base_url = "https://jobs.bvp.com"
    jobs_url = "https://jobs.bvp.com/jobs"
    board_id = "bessemer-ventures"
