"""Scraper for Pear VC portfolio jobs."""

from .getro_base import GetroScraper


class PearScraper(GetroScraper):
    """Scraper for Pear VC portfolio jobs."""

    name = "Pear VC"
    base_url = "https://pear.vc"
    jobs_url = "https://pear.vc/talent"
