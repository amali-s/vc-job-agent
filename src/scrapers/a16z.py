"""Scraper for a16z portfolio jobs."""

from .consider_base import ConsiderScraper


class A16ZScraper(ConsiderScraper):
    """Scraper for a16z portfolio jobs (Consider-powered)."""

    name = "a16z"
    base_url = "https://portfoliojobs.a16z.com"
    jobs_url = "https://portfoliojobs.a16z.com/jobs"
    board_id = "andreessen-horowitz"
