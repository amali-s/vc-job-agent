"""Base scraper for Getro-powered job boards (used by many VCs).

Supports multiple extraction strategies:
1. __NEXT_DATA__ (classic Next.js pages router)
2. self.__next_f.push() (Next.js 13+ app router / RSC flight data)
3. Getro search API (direct API call to the Getro backend)
4. Embedded JSON in script tags
5. HTML fallback parsing

Includes a strategy cache that remembers which extraction method last
succeeded for each scraper, so subsequent runs try the fast path first.
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper
from ..models import Job

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# Strategy cache: remembers which extraction method last worked
# ────────────────────────────────────────────────────────────────

# Locate cache file next to this source file → src/scrapers/.strategy_cache.json
# Falls back to data/ directory, then current working directory.
_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_CACHE_PATH = _CACHE_DIR / ".strategy_cache.json"


def _load_strategy_cache() -> dict:
    """Load the strategy cache from disk."""
    try:
        if _CACHE_PATH.exists():
            with open(_CACHE_PATH, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"Could not load strategy cache: {e}")
    return {}


def _save_strategy_cache(cache: dict) -> None:
    """Persist the strategy cache to disk."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.debug(f"Could not save strategy cache: {e}")


class GetroScraper(BaseScraper):
    """Base scraper for Getro-powered VC job boards.

    Many VC portfolio job boards use Getro's platform with Next.js,
    which embeds job data in various formats depending on the Next.js version.
    """

    # Subclasses can override to provide a known Getro network ID or slug
    getro_network_id: Optional[str] = None

    # Strategy name constants (used as cache keys)
    _STRATEGY_PAGE = "page"
    _STRATEGY_API = "api"
    _STRATEGY_ALT = "alt_urls"

    def scrape(self) -> list[Job]:
        """Scrape product designer jobs using multiple strategies.

        On the first run every strategy is tried in order until one succeeds.
        The winning strategy name is cached to disk so subsequent runs try
        the fast path first, falling back to the full cascade only if the
        cached strategy stops working.
        """
        # Build the default strategy order
        all_strategies = [
            (self._STRATEGY_PAGE, self._scrape_from_page),
            (self._STRATEGY_API, self._scrape_from_getro_api),
            (self._STRATEGY_ALT, self._scrape_alternate_urls),
        ]

        # Check cache for a previously successful strategy
        cache = _load_strategy_cache()
        cached_strategy = cache.get(self.name)

        if cached_strategy:
            # Move the cached strategy to the front of the list
            reordered = [s for s in all_strategies if s[0] == cached_strategy]
            reordered += [s for s in all_strategies if s[0] != cached_strategy]
            all_strategies = reordered
            logger.info(f"[{self.name}] Using cached strategy '{cached_strategy}' first")

        # Try each strategy in order
        jobs = []
        winning_strategy = None
        for strategy_name, strategy_fn in all_strategies:
            if strategy_name == self._STRATEGY_PAGE:
                logger.info(f"[{self.name}] Trying strategy '{strategy_name}': {self.jobs_url}")
            else:
                logger.info(f"[{self.name}] Trying strategy '{strategy_name}'...")

            result = strategy_fn()
            if result:
                jobs.extend(result)
                winning_strategy = strategy_name
                break

        # Update cache
        if winning_strategy:
            if cache.get(self.name) != winning_strategy:
                cache[self.name] = winning_strategy
                _save_strategy_cache(cache)
                logger.debug(f"[{self.name}] Cached winning strategy: {winning_strategy}")

            # Deduplicate
            seen = set()
            unique = []
            for j in jobs:
                key = (j.title, j.company, j.url)
                if key not in seen:
                    seen.add(key)
                    unique.append(j)
            jobs = unique
        else:
            # All strategies failed — clear stale cache entry
            if self.name in cache:
                del cache[self.name]
                _save_strategy_cache(cache)
            logger.warning(
                f"[{self.name}] Could not find any jobs after all strategies. "
                f"URL: {self.jobs_url}"
            )

        self.log_found(len(jobs))
        return jobs

    def _scrape_from_page(self) -> list[Job]:
        """Try extracting jobs from the page HTML."""
        jobs = []

        # Try with design search filters first
        search_queries = ["product+designer", "ux+designer", "ui+designer", "design"]
        for search_query in search_queries:
            filtered_url = f"{self.jobs_url}?q={search_query}"
            soup = self.fetch_page(filtered_url, delay=0.5)

            if soup:
                new_jobs = self._extract_jobs(soup)
                for job in new_jobs:
                    if job not in jobs:
                        jobs.append(job)
                if jobs:
                    logger.info(f"[{self.name}] Found {len(jobs)} jobs via page scraping (query={search_query})")
                    return jobs

        # Also try base URL without search query
        if not jobs:
            soup = self.fetch_page(self.jobs_url)
            if soup:
                jobs = self._extract_jobs(soup)

        return jobs

    # Extraction sub-strategy constants (cached separately)
    _EXTRACT_NEXT_DATA = "next_data"
    _EXTRACT_FLIGHT = "flight"
    _EXTRACT_SCRIPTS = "scripts"
    _EXTRACT_HTML = "html"

    def _extract_jobs(self, soup) -> list[Job]:
        """Extract jobs from page using multiple sub-strategies in order.

        The winning extraction sub-strategy is cached so subsequent runs
        skip straight to it.
        """
        # Build default extraction order
        extractors = [
            (self._EXTRACT_NEXT_DATA, lambda: self._try_next_data(soup)),
            (self._EXTRACT_FLIGHT, lambda: self._extract_from_next_flight_data(soup)),
            (self._EXTRACT_SCRIPTS, lambda: self._extract_from_scripts(soup)),
            (self._EXTRACT_HTML, lambda: self._parse_html(soup)),
        ]

        # Reorder if we have a cached sub-strategy
        cache = _load_strategy_cache()
        cache_key = f"{self.name}__extract"
        cached_sub = cache.get(cache_key)
        if cached_sub:
            reordered = [e for e in extractors if e[0] == cached_sub]
            reordered += [e for e in extractors if e[0] != cached_sub]
            extractors = reordered

        for sub_name, extractor_fn in extractors:
            jobs = extractor_fn()
            if jobs:
                logger.info(f"[{self.name}] Extracted {len(jobs)} jobs via '{sub_name}'")
                # Cache the winning sub-strategy
                if cache.get(cache_key) != sub_name:
                    cache[cache_key] = sub_name
                    _save_strategy_cache(cache)
                return jobs

        # Log diagnostic info if nothing worked
        self._log_page_diagnostics(soup)
        return []

    def _try_next_data(self, soup) -> list[Job]:
        """Wrapper for __NEXT_DATA__ extraction with logging."""
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data and next_data.string:
            logger.debug(f"[{self.name}] Found __NEXT_DATA__, attempting extraction...")
            jobs = self._extract_from_next_data(next_data.string)
            if jobs:
                return jobs
            self._log_next_data_structure(next_data.string)
        return []

    def _log_next_data_structure(self, json_str: str):
        """Log the structure of __NEXT_DATA__ for debugging."""
        try:
            data = json.loads(json_str)
            props = data.get("props", {})
            page_props = props.get("pageProps", {})
            keys = list(page_props.keys())
            logger.warning(
                f"[{self.name}] __NEXT_DATA__ found but no jobs extracted. "
                f"pageProps keys: {keys}"
            )
            # Check buildId for versioning clues
            build_id = data.get("buildId", "unknown")
            page = data.get("page", "unknown")
            logger.debug(f"[{self.name}] buildId={build_id}, page={page}")
        except Exception:
            logger.debug(f"[{self.name}] Could not parse __NEXT_DATA__ for diagnostics")

    def _log_page_diagnostics(self, soup):
        """Log diagnostic information about the page structure."""
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else "N/A"

        # Check for SPA indicators
        has_next = bool(soup.find(id="__next"))
        has_root = bool(soup.find(id="root"))
        has_app = bool(soup.find(id="app"))

        # Check for Cloudflare challenge
        is_cf = "cf-browser-verification" in str(soup) or "challenge-platform" in str(soup)

        # Body text length (detect empty SPA shells)
        body = soup.find("body")
        body_text = body.get_text(strip=True) if body else ""
        body_len = len(body_text)

        # Count scripts
        scripts = soup.find_all("script")
        flight_scripts = [s for s in scripts if s.string and "self.__next_f.push" in s.string]

        logger.warning(
            f"[{self.name}] Page diagnostics: title='{title}', "
            f"body_text_len={body_len}, scripts={len(scripts)}, "
            f"flight_scripts={len(flight_scripts)}, "
            f"SPA_roots(next={has_next}, root={has_root}, app={has_app}), "
            f"cloudflare={is_cf}"
        )

    # ────────────────────────────────────────────────────────────────
    # Strategy A: __NEXT_DATA__ (Next.js pages router)
    # ────────────────────────────────────────────────────────────────

    def _extract_from_next_data(self, json_str: str) -> list[Job]:
        """Extract jobs from Next.js __NEXT_DATA__."""
        jobs = []
        try:
            data = json.loads(json_str)
            props = data.get("props", {})
            page_props = props.get("pageProps", {})

            # Find jobs data in various possible locations
            jobs_data = self._find_jobs_in_dict(page_props)

            if jobs_data and isinstance(jobs_data, list):
                for job_data in jobs_data:
                    job = self._parse_job_json(job_data)
                    if job and self.is_design_job(job.title):
                        if self.is_valid_location(job.location) and self.is_recent_posting(job.posted_date):
                            jobs.append(job)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"[{self.name}] Error parsing __NEXT_DATA__: {e}")

        return jobs

    def _find_jobs_in_dict(self, d: dict, depth: int = 0) -> Optional[list]:
        """Recursively search a dict for job list data.

        Looks for common Getro data keys at various nesting levels.
        """
        if depth > 5:
            return None

        if not isinstance(d, dict):
            return None

        # Direct keys that commonly hold job arrays
        job_keys = ["jobs", "initialJobs", "listings", "results", "found", "items", "data"]
        for key in job_keys:
            val = d.get(key)
            if isinstance(val, list) and len(val) > 0:
                # Verify it looks like job data (has 'title' field)
                if isinstance(val[0], dict) and ("title" in val[0] or "name" in val[0]):
                    return val

        # Check nested structures common in Getro / Next.js
        # dehydratedState → queries → state → data
        dehydrated = d.get("dehydratedState", {})
        if isinstance(dehydrated, dict):
            queries = dehydrated.get("queries", [])
            for query in queries if isinstance(queries, list) else []:
                state = query.get("state", {})
                query_data = state.get("data", {})
                if isinstance(query_data, dict):
                    result = self._find_jobs_in_dict(query_data, depth + 1)
                    if result:
                        return result
                elif isinstance(query_data, list) and len(query_data) > 0:
                    if isinstance(query_data[0], dict) and "title" in query_data[0]:
                        return query_data

        # initialState → jobs → found
        initial_state = d.get("initialState", {})
        if isinstance(initial_state, dict):
            result = self._find_jobs_in_dict(initial_state, depth + 1)
            if result:
                return result

        # Recurse into other dict values (limited depth)
        if depth < 3:
            for key, val in d.items():
                if isinstance(val, dict) and key not in ("_sentryTraceData", "_sentryBaggage", "buildManifest"):
                    result = self._find_jobs_in_dict(val, depth + 1)
                    if result:
                        return result

        return None

    # ────────────────────────────────────────────────────────────────
    # Strategy B: Next.js 13+ App Router flight data
    # ────────────────────────────────────────────────────────────────

    def _extract_from_next_flight_data(self, soup) -> list[Job]:
        """Extract jobs from Next.js 13+ self.__next_f.push() flight data.

        Next.js 13+ with App Router embeds data in script tags containing
        self.__next_f.push() calls instead of __NEXT_DATA__.
        The data is split across multiple script chunks that need reassembly.
        """
        jobs = []

        # Collect all flight data chunks
        flight_chunks = []
        for script in soup.find_all("script"):
            text = script.string or ""
            if "self.__next_f.push" not in text:
                continue

            # Extract the data from self.__next_f.push([...]) calls
            # Format: self.__next_f.push([1,"...data..."]) or self.__next_f.push([0])
            push_pattern = r'self\.__next_f\.push\(\s*\[(.*?)\]\s*\)'
            for match in re.finditer(push_pattern, text, re.DOTALL):
                content = match.group(1)
                flight_chunks.append(content)

        if not flight_chunks:
            return []

        logger.debug(f"[{self.name}] Found {len(flight_chunks)} Next.js flight data chunks")

        # Reassemble and search for JSON job data in the chunks
        all_text = "\n".join(flight_chunks)

        # Look for JSON arrays/objects that contain job data
        # Flight data format: type_id:content_type:json_data
        # We need to find JSON objects with job-related fields
        jobs = self._extract_jobs_from_flight_text(all_text)

        return jobs

    def _extract_jobs_from_flight_text(self, text: str) -> list[Job]:
        """Parse flight data text to find and extract job listings."""
        jobs = []

        # Strategy 1: Find JSON arrays that look like job listings
        # These appear as [...] containing objects with "title" fields
        json_array_pattern = r'\[(?:\s*\{[^[\]]*"title"[^[\]]*\}(?:\s*,\s*\{[^[\]]*\})*\s*)\]'
        for match in re.finditer(json_array_pattern, text, re.DOTALL):
            try:
                data = json.loads(match.group(0))
                if isinstance(data, list) and len(data) > 0:
                    for item in data:
                        if isinstance(item, dict):
                            job = self._parse_job_json(item)
                            if job and self.is_design_job(job.title):
                                if self.is_valid_location(job.location) and self.is_recent_posting(job.posted_date):
                                    jobs.append(job)
                    if jobs:
                        return jobs
            except (json.JSONDecodeError, TypeError):
                continue

        # Strategy 2: Find individual JSON objects with job data
        # Flight data often has escaped JSON strings
        # Unescape common escape sequences
        unescaped = text.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')

        # Look for "found":[...] or "jobs":[...] patterns
        for key in ["found", "jobs", "results", "items", "initialJobs"]:
            pattern = rf'"{key}"\s*:\s*(\[[^\]]*(?:\[[^\]]*\][^\]]*)*\])'
            for match in re.finditer(pattern, unescaped, re.DOTALL):
                try:
                    data = json.loads(match.group(1))
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                job = self._parse_job_json(item)
                                if job and self.is_design_job(job.title):
                                    if self.is_valid_location(job.location) and self.is_recent_posting(job.posted_date):
                                        jobs.append(job)
                        if jobs:
                            return jobs
                except (json.JSONDecodeError, TypeError):
                    continue

        # Strategy 3: Try to find any large JSON blob and parse recursively
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        large_jsons = []
        for match in re.finditer(json_pattern, unescaped, re.DOTALL):
            blob = match.group(0)
            if len(blob) > 200 and '"title"' in blob:
                large_jsons.append(blob)

        for blob in sorted(large_jsons, key=len, reverse=True)[:5]:
            try:
                data = json.loads(blob)
                if isinstance(data, dict):
                    jobs_data = self._find_jobs_in_dict(data)
                    if jobs_data:
                        for item in jobs_data:
                            job = self._parse_job_json(item)
                            if job and self.is_design_job(job.title):
                                if self.is_valid_location(job.location) and self.is_recent_posting(job.posted_date):
                                    jobs.append(job)
                        if jobs:
                            return jobs
            except (json.JSONDecodeError, TypeError):
                continue

        return jobs

    # ────────────────────────────────────────────────────────────────
    # Strategy C: Getro search API (direct HTTP)
    # ────────────────────────────────────────────────────────────────

    def _scrape_from_getro_api(self) -> list[Job]:
        """Try to hit Getro's internal search API directly.

        Getro job boards make XHR requests to fetch job data.
        Common patterns include:
        - /api/jobs?q=...
        - /api/search?q=...
        - The board's own domain with /api/ prefix
        """
        jobs = []
        parsed = urlparse(self.jobs_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        # Try common Getro API patterns
        api_patterns = [
            # Next.js API routes
            f"{base}/api/jobs?q=design",
            f"{base}/api/jobs?query=design",
            f"{base}/api/search?q=design",
            # Getro-specific patterns
            f"{base}/api/v1/jobs?q=design",
            f"{base}/api/v1/jobs?query=design",
            # JSON format of the main page
            f"{self.jobs_url}.json",
            f"{self.jobs_url}?format=json",
        ]

        for api_url in api_patterns:
            try:
                time.sleep(0.5)
                response = self.session.get(api_url, timeout=15)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type or "javascript" in content_type:
                        data = response.json()
                        logger.info(f"[{self.name}] Got JSON response from {api_url}")

                        jobs_data = None
                        if isinstance(data, list):
                            jobs_data = data
                        elif isinstance(data, dict):
                            jobs_data = self._find_jobs_in_dict(data)

                        if jobs_data:
                            for item in jobs_data:
                                if isinstance(item, dict):
                                    job = self._parse_job_json(item)
                                    if job and self.is_design_job(job.title):
                                        if self.is_valid_location(job.location) and self.is_recent_posting(job.posted_date):
                                            jobs.append(job)
                            if jobs:
                                return jobs
            except Exception as e:
                logger.debug(f"[{self.name}] API probe failed for {api_url}: {e}")
                continue

        return jobs

    # ────────────────────────────────────────────────────────────────
    # Strategy D: Alternate URL patterns
    # ────────────────────────────────────────────────────────────────

    def _scrape_alternate_urls(self) -> list[Job]:
        """Try alternate URL patterns that Getro boards sometimes use."""
        jobs = []
        parsed = urlparse(self.jobs_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        # Some Getro boards have /companies page that lists all portfolio companies
        # and individual company job pages
        alt_urls = [
            f"{base}/companies",
            f"{base}/talent",
            f"{base}/careers",
            f"{base}/opportunities",
        ]

        # Only try URLs that are different from what we already tried
        tried = {self.jobs_url}
        for alt_url in alt_urls:
            if alt_url in tried:
                continue
            tried.add(alt_url)

            soup = self.fetch_page(alt_url, delay=0.5)
            if soup:
                extracted = self._extract_jobs(soup)
                if extracted:
                    jobs.extend(extracted)
                    logger.info(f"[{self.name}] Found {len(extracted)} jobs at {alt_url}")
                    return jobs

        return jobs

    # ────────────────────────────────────────────────────────────────
    # Embedded script JSON extraction
    # ────────────────────────────────────────────────────────────────

    def _extract_from_scripts(self, soup) -> list[Job]:
        """Extract jobs from other embedded JSON in script tags."""
        jobs = []

        for script in soup.find_all("script"):
            text = script.string or ""
            if not text or len(text) < 100:
                continue

            # Skip flight data (handled separately)
            if "self.__next_f.push" in text:
                continue

            # Skip if no job-related content
            if '"title"' not in text:
                continue

            # Try multiple patterns for finding job arrays
            patterns = [
                r'"found":\s*(\[.*?\])\s*,\s*"total"',
                r'"jobs":\s*(\[.*?\])',
                r'"openings":\s*(\[.*?\])',
                r'"results":\s*(\[.*?\])',
                r'"items":\s*(\[.*?\])',
                r'"initialJobs":\s*(\[.*?\])',
            ]

            for pattern in patterns:
                try:
                    match = re.search(pattern, text, re.DOTALL)
                    if match:
                        jobs_json = match.group(1)
                        jobs_data = json.loads(jobs_json)

                        for job_data in jobs_data:
                            job = self._parse_job_json(job_data)
                            if job and self.is_design_job(job.title):
                                if self.is_valid_location(job.location) and self.is_recent_posting(job.posted_date):
                                    jobs.append(job)

                        if jobs:
                            return jobs
                except (json.JSONDecodeError, TypeError):
                    continue

        return jobs

    # ────────────────────────────────────────────────────────────────
    # Job JSON parsing
    # ────────────────────────────────────────────────────────────────

    def _parse_job_json(self, data: dict) -> Optional[Job]:
        """Parse a single job from JSON data."""
        try:
            if not isinstance(data, dict):
                return None

            title = data.get("title", "") or data.get("name", "")
            if not title:
                return None

            # Get company name (various field names used by Getro)
            company = ""
            org = data.get("organization") or data.get("company") or data.get("employer")
            if isinstance(org, dict):
                company = org.get("name", "") or org.get("title", "")
            elif isinstance(org, str):
                company = org
            if not company:
                company = (
                    data.get("companyName", "")
                    or data.get("organizationName", "")
                    or data.get("company_name", "")
                    or data.get("organization_name", "")
                )
            if not company:
                company = f"{self.name} Portfolio"

            # Get location (handle multiple field name conventions)
            location = ""
            loc_data = (
                data.get("location")
                or data.get("locations")
                or data.get("locationName")
                or data.get("location_name")
            )
            if isinstance(loc_data, dict):
                location = loc_data.get("name", "") or loc_data.get("city", "") or loc_data.get("text", "")
            elif isinstance(loc_data, list) and loc_data:
                parts = []
                for loc_item in loc_data[:3]:  # Take up to 3 locations
                    if isinstance(loc_item, dict):
                        parts.append(loc_item.get("name", "") or loc_item.get("city", ""))
                    elif isinstance(loc_item, str):
                        parts.append(loc_item)
                location = ", ".join(p for p in parts if p)
            elif isinstance(loc_data, str):
                location = loc_data

            # Check remote status
            work_mode = data.get("workMode", "") or data.get("remoteStatus", "") or data.get("locationType", "")
            is_remote = data.get("remote", False) or data.get("isRemote", False) or data.get("is_remote", False)
            if is_remote or (work_mode and "remote" in str(work_mode).lower()):
                location = f"{location} (Remote)".strip() if location else "Remote"

            # Get URL (try many possible field names)
            url = ""
            for url_key in ["url", "applyUrl", "apply_url", "sourceUrl", "source_url",
                            "jobUrl", "job_url", "link", "href", "externalUrl", "external_url",
                            "applicationUrl", "application_url"]:
                url = data.get(url_key, "")
                if url:
                    break
            if not url:
                slug = data.get("slug", "") or data.get("id", "")
                if slug:
                    url = f"{self.base_url}/jobs/{slug}"
            if not url:
                url = self.jobs_url

            # Get description
            description = data.get("description", "") or data.get("content", "") or data.get("body", "")
            if isinstance(description, dict):
                description = description.get("text", "") or description.get("html", "") or description.get("raw", "")

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

    # ────────────────────────────────────────────────────────────────
    # HTML fallback parsing
    # ────────────────────────────────────────────────────────────────

    def _parse_html(self, soup) -> list[Job]:
        """Fallback HTML parsing for job cards."""
        jobs = []

        # Expanded selectors for Getro job boards (including newer versions)
        selectors = [
            "[class*='JobCard']",
            "[class*='job-card']",
            "[class*='jobCard']",
            "[class*='JobListItem']",
            "[class*='JobItem']",
            "[class*='job-item']",
            "[class*='jobListing']",
            "[class*='JobListing']",
            "[data-testid*='job']",
            "[data-testid*='Job']",
            ".job-listing",
            ".job",
            "article",
            "[data-job]",
            "[role='listitem']",
            "li[class*='job']",
            "li[class*='Job']",
            "a[href*='/jobs/']",
            "a[href*='/companies/']",
        ]

        job_elements = []
        for selector in selectors:
            elements = soup.select(selector)
            if elements and len(elements) > 1:  # Need multiple to be a listing
                job_elements = elements
                logger.debug(f"[{self.name}] HTML fallback: matched {len(elements)} elements with '{selector}'")
                break

        for elem in job_elements:
            try:
                # Get title (expanded selectors)
                title_elem = elem.select_one(
                    "[class*='title' i], [class*='Title'], "
                    "[class*='name' i], [class*='Name'], "
                    "h2, h3, h4, [role='heading']"
                )
                title = title_elem.get_text(strip=True) if title_elem else ""

                if not title:
                    link = elem.select_one("a")
                    title = link.get_text(strip=True) if link else elem.get_text(strip=True)[:100]

                if not self.is_design_job(title):
                    continue

                # Get company
                company_elem = elem.select_one(
                    "[class*='company' i], [class*='Company'], "
                    "[class*='org' i], [class*='Org'], "
                    "[class*='employer' i]"
                )
                company = company_elem.get_text(strip=True) if company_elem else f"{self.name} Portfolio"

                # Get location
                location_elem = elem.select_one(
                    "[class*='location' i], [class*='Location'], "
                    "[class*='place' i]"
                )
                location = self.extract_location(
                    location_elem.get_text(strip=True) if location_elem else ""
                )

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
