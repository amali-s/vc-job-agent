"""Scraper for Kleiner Perkins portfolio jobs."""

from .getro_base import GetroScraper


class KleinerPerkinsScraper(GetroScraper):
    """Scraper for Kleiner Perkins portfolio jobs (Getro-powered)."""

    name = "Kleiner Perkins"
    base_url = "https://jobs.kleinerperkins.com"
    jobs_url = "https://jobs.kleinerperkins.com/jobs"
