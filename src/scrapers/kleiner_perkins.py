"""Scraper for Kleiner Perkins portfolio jobs."""

from .consider_base import ConsiderScraper


class KleinerPerkinsScraper(ConsiderScraper):
    """Scraper for Kleiner Perkins portfolio jobs (Consider-powered)."""

    name = "Kleiner Perkins"
    base_url = "https://jobs.kleinerperkins.com"
    jobs_url = "https://jobs.kleinerperkins.com/jobs"
    board_id = "kleiner-perkins"
