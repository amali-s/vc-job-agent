"""Scraper for NEA portfolio jobs."""

from .consider_base import ConsiderScraper


class NEAScraper(ConsiderScraper):
    """Scraper for NEA portfolio jobs (Consider-powered)."""

    name = "NEA"
    base_url = "https://careers.nea.com"
    jobs_url = "https://careers.nea.com/jobs"
    board_id = "nea"
