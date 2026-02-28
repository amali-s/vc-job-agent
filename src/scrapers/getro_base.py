"""Base scraper for Getro-powered job boards (used by many VCs)."""

import json
import logging
import re
from datetime import datetime
from typing import Optional

from .base import BaseScraper
from ..models import Job

logger = logging.getLogger(__name__)


class GetroScraper(BaseScraper):
    """Base scraper for Getro-powered VC job boards.

    Many VC portfolio job boards use Getro's platform with Next.js,
    which embeds job data in __NEXT_DATA__ script tags.
    """

    def scrape(self) -> list[Job]:
        """Scrape product designer jobs."""
        jobs = []

        # Try with design filter first for better results
        for search_query in ["product+designer", "ux+designer", "ui+designer", "design"]:
            filtered_url = f"{self.jobs_url}?q={search_query}"
            soup = self.fetch_page(filtered_url, delay=0.5)

            if soup:
                new_jobs = self._extract_jobs(soup)
                for job in new_jobs:
                    if job not in jobs:
                        jobs.append(job)

        # Also try base URL
        if not jobs:
            soup = self.fetch_page(self.jobs_url)
            if soup:
                jobs = self._extract_jobs(soup)

        if not jobs:
            logger.warning(f"[{self.name}] Could not find any jobs")

        self.log_found(len(jobs))
        return jobs

    def _extract_jobs(self, soup) -> list[Job]:
        """Extract jobs from page."""
        jobs = []

        # Try __NEXT_DATA__ first (Next.js apps)
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data and next_data.string:
            jobs = self._extract_from_next_data(next_data.string)
            if jobs:
                return jobs

        # Try other embedded JSON patterns
        jobs = self._extract_from_scripts(soup)
        if jobs:
            return jobs

        # Fallback to HTML parsing
        return self._parse_html(soup)

    def _extract_from_next_data(self, json_str: str) -> list[Job]:
        """Extract jobs from Next.js __NEXT_DATA__."""
        jobs = []
        try:
            data = json.loads(json_str)

            # Navigate through common Next.js structures
            props = data.get("props", {})
            page_props = props.get("pageProps", {})

            # Look for jobs in various locations
            jobs_data = None
            for key in ["jobs", "initialJobs", "listings", "results", "data"]:
                if key in page_props:
                    jobs_data = page_props[key]
                    break

            # Also check nested state
            if not jobs_data:
                initial_state = page_props.get("initialState", {})
                jobs_state = initial_state.get("jobs", {})
                jobs_data = jobs_state.get("found", [])

            # Also look in dehydratedState (React Query)
            if not jobs_data:
                dehydrated = page_props.get("dehydratedState", {})
                queries = dehydrated.get("queries", [])
                for query in queries:
                    state = query.get("state", {})
                    query_data = state.get("data", {})
                    if isinstance(query_data, dict):
                        jobs_data = query_data.get("jobs", []) or query_data.get("found", [])
                    elif isinstance(query_data, list):
                        jobs_data = query_data
                    if jobs_data:
                        break

            if jobs_data and isinstance(jobs_data, list):
                for job_data in jobs_data:
                    job = self._parse_job_json(job_data)
                    if job and self.is_design_job(job.title):
                        # Apply location and recency filters
                        if self.is_valid_location(job.location) and self.is_recent_posting(job.posted_date):
                            jobs.append(job)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"[{self.name}] Error parsing __NEXT_DATA__: {e}")

        return jobs

    def _extract_from_scripts(self, soup) -> list[Job]:
        """Extract jobs from other embedded JSON in script tags."""
        jobs = []

        for script in soup.find_all("script"):
            text = script.string or ""
            if not text or len(text) < 100:
                continue

            # Skip if no job-related content
            if '"title"' not in text:
                continue

            # Try multiple patterns for finding job arrays
            patterns = [
                (r'"found":\s*(\[.*?\])\s*,\s*"total"', 1),
                (r'"jobs":\s*(\[.*?\])', 1),
                (r'"openings":\s*(\[.*?\])', 1),
                (r'"results":\s*(\[.*?\])', 1),
            ]

            for pattern, group in patterns:
                try:
                    match = re.search(pattern, text, re.DOTALL)
                    if match:
                        jobs_json = match.group(group)
                        jobs_data = json.loads(jobs_json)

                        for job_data in jobs_data:
                            job = self._parse_job_json(job_data)
                            if job and self.is_design_job(job.title):
                                # Apply location and recency filters
                                if self.is_valid_location(job.location) and self.is_recent_posting(job.posted_date):
                                    jobs.append(job)

                        if jobs:
                            return jobs
                except (json.JSONDecodeError, TypeError):
                    continue

        return jobs

    def _parse_job_json(self, data: dict) -> Optional[Job]:
        """Parse a single job from JSON data."""
        try:
            title = data.get("title", "")
            if not title:
                return None

            # Get company name (various field names)
            company = ""
            org = data.get("organization") or data.get("company") or data.get("employer")
            if isinstance(org, dict):
                company = org.get("name", "")
            elif isinstance(org, str):
                company = org
            if not company:
                company = data.get("companyName", "") or data.get("organizationName", "")
            if not company:
                company = f"{self.name} Portfolio"

            # Get location
            location = ""
            loc_data = data.get("location") or data.get("locations") or data.get("locationName")
            if isinstance(loc_data, dict):
                location = loc_data.get("name", "") or loc_data.get("city", "")
            elif isinstance(loc_data, list) and loc_data:
                first_loc = loc_data[0]
                location = first_loc.get("name", "") if isinstance(first_loc, dict) else str(first_loc)
            elif isinstance(loc_data, str):
                location = loc_data

            # Check remote status
            work_mode = data.get("workMode", "") or data.get("remoteStatus", "") or data.get("locationType", "")
            is_remote = data.get("remote", False) or data.get("isRemote", False)
            if is_remote or (work_mode and "remote" in str(work_mode).lower()):
                location = f"{location} (Remote)".strip() if location else "Remote"

            # Get URL
            url = (
                data.get("url", "")
                or data.get("applyUrl", "")
                or data.get("sourceUrl", "")
                or data.get("jobUrl", "")
                or data.get("link", "")
            )
            if not url:
                # Try to construct from slug/id
                slug = data.get("slug", "") or data.get("id", "")
                if slug:
                    url = f"{self.base_url}/jobs/{slug}"
            if not url:
                url = self.jobs_url

            # Get description
            description = data.get("description", "") or data.get("content", "") or data.get("body", "")
            if isinstance(description, dict):
                description = description.get("text", "") or description.get("html", "")

            # Extract posted date
            posted_date = self.extract_posted_date(data)

            # Extract salary range
            salary_range = self.extract_salary(data)

            return Job(
                title=title,
                company=company,
                location=self.extract_location(location) if location else "Not specified",
                url=url,
                description=self.clean_text(str(description))[:8000],
                source=self.name,
                scraped_at=datetime.utcnow(),
                salary_range=salary_range,
                posted_date=posted_date,
            )
        except Exception as e:
            logger.debug(f"[{self.name}] Error parsing job JSON: {e}")
            return None

    def _parse_html(self, soup) -> list[Job]:
        """Fallback HTML parsing for job cards."""
        jobs = []

        # Common selectors for Getro job boards
        selectors = [
            "[class*='JobCard']",
            "[class*='job-card']",
            "[class*='jobCard']",
            "[class*='JobListItem']",
            ".job-listing",
            ".job",
            "article",
            "[data-job]",
            "a[href*='/jobs/']",
            "a[href*='/companies/']",
        ]

        job_elements = []
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                job_elements = elements
                break

        for elem in job_elements:
            try:
                # Get title
                title_elem = elem.select_one(
                    "[class*='title' i], [class*='Title'], h2, h3, h4"
                )
                title = title_elem.get_text(strip=True) if title_elem else ""

                if not title:
                    # Try getting text from link
                    link = elem.select_one("a")
                    title = link.get_text(strip=True) if link else elem.get_text(strip=True)[:100]

                if not self.is_design_job(title):
                    continue

                # Get company
                company_elem = elem.select_one(
                    "[class*='company' i], [class*='Company'], [class*='org' i]"
                )
                company = company_elem.get_text(strip=True) if company_elem else f"{self.name} Portfolio"

                # Get location
                location_elem = elem.select_one("[class*='location' i], [class*='Location']")
                location = self.extract_location(
                    location_elem.get_text(strip=True) if location_elem else ""
                )

                # Apply location filter
                if not self.is_valid_location(location):
                    continue

                # Get URL
                url = elem.get("href") if elem.name == "a" else None
                if not url:
                    link = elem.select_one("a")
                    url = link.get("href") if link else ""

                if url and not url.startswith("http"):
                    url = f"{self.base_url}{url}"

                jobs.append(
                    Job(
                        title=title,
                        company=company,
                        location=location,
                        url=url or self.jobs_url,
                        description="",
                        source=self.name,
                        scraped_at=datetime.utcnow(),
                    )
                )

            except Exception as e:
                logger.debug(f"[{self.name}] Error parsing HTML element: {e}")
                continue

        return jobs
