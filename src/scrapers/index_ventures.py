"""Scraper for Index Ventures portfolio jobs."""

import json
import logging
import re
import time
from datetime import datetime
from typing import Optional

from .base import BaseScraper
from ..models import Job

logger = logging.getLogger(__name__)


class IndexVenturesScraper(BaseScraper):
    """Scraper for Index Ventures portfolio jobs.

    Index Ventures has a custom job board at indexventures.com/startup-jobs
    which uses client-side rendering (SPA). We try multiple strategies:
    1. Search API endpoint discovery from page source
    2. Algolia/internal search API direct calls
    3. Paginated HTML with design keyword filtering
    4. Individual job page URLs discovered from sitemap or search results
    """

    name = "Index Ventures"
    base_url = "https://www.indexventures.com"
    jobs_url = "https://www.indexventures.com/startup-jobs"

    # Design-specific search URLs discovered from the site structure
    SEARCH_URLS = [
        "https://www.indexventures.com/startup-jobs/search?query=product+designer",
        "https://www.indexventures.com/startup-jobs/search?query=ux+designer",
        "https://www.indexventures.com/startup-jobs/search?query=ui+designer",
        "https://www.indexventures.com/startup-jobs/search?query=design",
        # Job function filtered pages
        "https://www.indexventures.com/startup-jobs/design-ui/",
        "https://www.indexventures.com/startup-jobs/design-ui/1",
    ]

    def scrape(self) -> list[Job]:
        """Scrape product designer jobs from Index Ventures portfolio."""
        jobs = []

        # Strategy 1: Try search/category pages
        logger.info(f"[{self.name}] Trying search and category pages...")
        for search_url in self.SEARCH_URLS:
            soup = self.fetch_page(search_url, delay=0.5)
            if soup:
                new_jobs = self._extract_from_page(soup)
                for j in new_jobs:
                    if j not in jobs:
                        jobs.append(j)
                if jobs:
                    break  # Found jobs, don't need more search URLs

        # Strategy 2: Try the main page and look for embedded data or API endpoints
        if not jobs:
            logger.info(f"[{self.name}] Trying main jobs page for embedded data...")
            soup = self.fetch_page(self.jobs_url)
            if soup:
                # Try to find API endpoint from page scripts
                api_jobs = self._try_discover_api(soup)
                if api_jobs:
                    jobs = api_jobs
                else:
                    # Try to find __NEXT_DATA__ or embedded JSON
                    next_data = soup.find("script", id="__NEXT_DATA__")
                    if next_data and next_data.string:
                        jobs = self._extract_from_next_data(next_data.string)

                    # Try embedded script data
                    if not jobs:
                        jobs = self._extract_from_scripts(soup)

                    # Fallback to HTML
                    if not jobs:
                        jobs = self._extract_from_page(soup)

        # Strategy 3: Try to find job URLs from the design-ui category
        if not jobs:
            logger.info(f"[{self.name}] Trying to find job links from category pages...")
            for page_num in range(1, 4):
                page_url = f"{self.base_url}/startup-jobs/design-ui/{page_num}"
                soup = self.fetch_page(page_url, delay=0.5)
                if soup:
                    page_jobs = self._extract_from_page(soup)
                    jobs.extend(page_jobs)
                else:
                    break

        if not jobs:
            logger.warning(
                f"[{self.name}] No design jobs found. Index Ventures uses a client-side "
                f"rendered SPA that may require JavaScript execution."
            )

        self.log_found(len(jobs))
        return jobs

    def _extract_from_page(self, soup) -> list[Job]:
        """Extract jobs from the HTML of an Index Ventures page."""
        jobs = []

        # Try various selectors for job listings
        selectors = [
            "a[href*='/startup-jobs/'][href*='/']",  # Job detail links
            "[class*='job' i]",
            "[class*='Job']",
            "[class*='listing' i]",
            "[class*='result' i]",
            "[class*='card' i]",
            "article",
            ".card",
            "li a[href*='/startup-jobs/']",
        ]

        job_elements = []
        for selector in selectors:
            elements = soup.select(selector)
            if elements and len(elements) > 1:
                job_elements = elements
                break

        for elem in job_elements:
            try:
                # Get title
                title_elem = elem.select_one(
                    "h2, h3, h4, [class*='title' i], [class*='name' i], [class*='role' i]"
                )
                title = title_elem.get_text(strip=True) if title_elem else ""

                if not title:
                    if elem.name == "a":
                        title = elem.get_text(strip=True)[:100]
                    else:
                        link = elem.select_one("a")
                        title = link.get_text(strip=True) if link else ""

                if not title or not self.is_design_job(title):
                    continue

                # Get company
                company_elem = elem.select_one(
                    "[class*='company' i], [class*='startup' i], [class*='org' i]"
                )
                company = company_elem.get_text(strip=True) if company_elem else "Index Ventures Portfolio"

                # Get location
                location_elem = elem.select_one("[class*='location' i], [class*='place' i]")
                location = self.extract_location(
                    location_elem.get_text(strip=True) if location_elem else ""
                )

                # Get URL
                url = elem.get("href") if elem.name == "a" else None
                if not url:
                    link = elem.select_one("a")
                    url = link.get("href") if link else ""
                if url and not url.startswith("http"):
                    url = f"{self.base_url}{url}"

                jobs.append(Job(
                    title=title,
                    company=company,
                    location=location,
                    url=url or self.jobs_url,
                    description="",
                    source=self.name,
                    scraped_at=datetime.utcnow(),
                ))

            except Exception as e:
                logger.debug(f"[{self.name}] Error parsing element: {e}")

        return jobs

    def _try_discover_api(self, soup) -> list[Job]:
        """Try to discover and call the API endpoint from page scripts."""
        jobs = []

        for script in soup.find_all("script", src=True):
            src = script.get("src", "")
            # Look for API keys or configuration in external scripts
            if "algolia" in src.lower() or "search" in src.lower():
                logger.debug(f"[{self.name}] Found search-related script: {src}")

        # Look for API configuration in inline scripts
        for script in soup.find_all("script"):
            text = script.string or ""
            if not text:
                continue

            # Look for Algolia config
            algolia_match = re.search(
                r'(?:algolia|algoliasearch)\s*\(\s*["\']([^"\']+)["\'].*?["\']([^"\']+)["\']',
                text, re.IGNORECASE
            )
            if algolia_match:
                app_id = algolia_match.group(1)
                api_key = algolia_match.group(2)
                logger.info(f"[{self.name}] Found Algolia config: app_id={app_id}")
                jobs = self._search_algolia(app_id, api_key)
                if jobs:
                    return jobs

            # Look for API base URL
            api_match = re.search(r'["\'](?:apiUrl|apiBase|baseUrl)["\']:\s*["\'](https?://[^"\']+)["\']', text)
            if api_match:
                api_base = api_match.group(1)
                logger.info(f"[{self.name}] Found API base: {api_base}")
                jobs = self._try_api_endpoint(api_base)
                if jobs:
                    return jobs

        return jobs

    def _search_algolia(self, app_id: str, api_key: str) -> list[Job]:
        """Search Algolia for design jobs."""
        jobs = []
        try:
            algolia_url = f"https://{app_id}-dsn.algolia.net/1/indexes/*/queries"
            headers = {
                "X-Algolia-Application-Id": app_id,
                "X-Algolia-API-Key": api_key,
                "Content-Type": "application/json",
            }

            for query in ["product designer", "ux designer", "design"]:
                payload = {
                    "requests": [{
                        "indexName": "jobs",
                        "params": f"query={query}&hitsPerPage=50"
                    }]
                }

                time.sleep(0.5)
                response = self.session.post(
                    algolia_url, json=payload,
                    headers=headers, timeout=15
                )
                if response.status_code == 200:
                    data = response.json()
                    for result in data.get("results", []):
                        for hit in result.get("hits", []):
                            title = hit.get("title", "")
                            if self.is_design_job(title):
                                company = hit.get("company", {})
                                company_name = company.get("name", "") if isinstance(company, dict) else str(company)
                                location = hit.get("location", "")
                                if isinstance(location, list):
                                    location = ", ".join(str(l) for l in location[:3])
                                elif isinstance(location, dict):
                                    location = location.get("name", "")

                                if not self.is_valid_location(str(location)):
                                    continue

                                url = hit.get("url", "") or hit.get("absolute_url", "")
                                if not url:
                                    slug = hit.get("slug", "") or hit.get("objectID", "")
                                    if slug:
                                        url = f"{self.base_url}/startup-jobs/{slug}"

                                jobs.append(Job(
                                    title=title,
                                    company=company_name or "Index Ventures Portfolio",
                                    location=self.extract_location(str(location)),
                                    url=url or self.jobs_url,
                                    description=self.clean_text(hit.get("description", ""))[:8000],
                                    source=self.name,
                                    scraped_at=datetime.utcnow(),
                                ))

        except Exception as e:
            logger.debug(f"[{self.name}] Algolia search failed: {e}")

        return jobs

    def _try_api_endpoint(self, api_base: str) -> list[Job]:
        """Try fetching jobs from a discovered API endpoint."""
        jobs = []
        try:
            for path in ["/jobs?q=design", "/search?q=design", "/jobs?function=design"]:
                time.sleep(0.5)
                response = self.session.get(f"{api_base}{path}", timeout=15)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type:
                        data = response.json()
                        items = data if isinstance(data, list) else data.get("jobs", data.get("results", []))
                        for item in items:
                            if isinstance(item, dict):
                                title = item.get("title", "")
                                if self.is_design_job(title):
                                    jobs.append(Job(
                                        title=title,
                                        company=item.get("company", {}).get("name", "Index Ventures Portfolio"),
                                        location=self.extract_location(str(item.get("location", ""))),
                                        url=item.get("url", self.jobs_url),
                                        description=self.clean_text(item.get("description", ""))[:8000],
                                        source=self.name,
                                        scraped_at=datetime.utcnow(),
                                    ))
                        if jobs:
                            return jobs
        except Exception as e:
            logger.debug(f"[{self.name}] API endpoint probe failed: {e}")
        return jobs

    def _extract_from_next_data(self, json_str: str) -> list[Job]:
        """Extract from __NEXT_DATA__ if present."""
        jobs = []
        try:
            data = json.loads(json_str)
            page_props = data.get("props", {}).get("pageProps", {})

            # Look for jobs array in various locations
            for key in ["jobs", "results", "listings", "data", "initialJobs"]:
                items = page_props.get(key, [])
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            title = item.get("title", "")
                            if self.is_design_job(title):
                                company = item.get("company", {})
                                company_name = company.get("name", "") if isinstance(company, dict) else str(company)
                                location = item.get("location", "")
                                if isinstance(location, (list, dict)):
                                    location = str(location)
                                jobs.append(Job(
                                    title=title,
                                    company=company_name or "Index Ventures Portfolio",
                                    location=self.extract_location(str(location)),
                                    url=item.get("url", self.jobs_url),
                                    description="",
                                    source=self.name,
                                    scraped_at=datetime.utcnow(),
                                ))
                    if jobs:
                        return jobs
        except Exception as e:
            logger.debug(f"[{self.name}] Error parsing __NEXT_DATA__: {e}")
        return jobs

    def _extract_from_scripts(self, soup) -> list[Job]:
        """Try to find job data in embedded scripts."""
        jobs = []
        for script in soup.find_all("script"):
            text = script.string or ""
            if not text or '"title"' not in text:
                continue

            # Look for JSON objects with job data
            for pattern in [r'"jobs"\s*:\s*(\[.*?\])', r'"results"\s*:\s*(\[.*?\])']:
                match = re.search(pattern, text, re.DOTALL)
                if match:
                    try:
                        items = json.loads(match.group(1))
                        for item in items:
                            if isinstance(item, dict):
                                title = item.get("title", "")
                                if self.is_design_job(title):
                                    jobs.append(Job(
                                        title=title,
                                        company=item.get("company", "Index Ventures Portfolio"),
                                        location=self.extract_location(str(item.get("location", ""))),
                                        url=item.get("url", self.jobs_url),
                                        description="",
                                        source=self.name,
                                        scraped_at=datetime.utcnow(),
                                    ))
                        if jobs:
                            return jobs
                    except (json.JSONDecodeError, TypeError):
                        continue
        return jobs
