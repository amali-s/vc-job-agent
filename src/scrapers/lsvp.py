"""Scraper for LSVP (Lightspeed Venture Partners) portfolio jobs."""

from .consider_base import ConsiderScraper


class LSVPScraper(ConsiderScraper):
    """Scraper for LSVP portfolio jobs (Consider-powered)."""

    name = "LSVP"
    base_url = "https://jobs.lsvp.com"
    jobs_url = "https://jobs.lsvp.com/jobs"
    board_id = "lightspeed"
