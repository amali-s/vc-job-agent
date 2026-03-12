"""Scraper for Battery Ventures portfolio jobs."""

from .consider_base import ConsiderScraper


class BatteryScraper(ConsiderScraper):
    """Scraper for Battery Ventures portfolio jobs (Consider-powered)."""

    name = "Battery Ventures"
    base_url = "https://jobs.battery.com"
    jobs_url = "https://jobs.battery.com/jobs"
    board_id = "battery-ventures"
