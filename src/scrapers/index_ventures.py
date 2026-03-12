"""Scraper for Index Ventures portfolio jobs.

Index Ventures uses a Wagtail CMS backend with Elasticsearch for search.
The Vue.js frontend queries ES directly; we replicate those queries here.
"""

import logging
import re
import time
from datetime import datetime
from typing import Optional

from .base import BaseScraper
from ..models import Job

logger = logging.getLogger(__name__)

# Elasticsearch configuration (public credentials embedded in the Vue.js app)
ES_URL = (
    "https://startup_jobs:CkS0aAwLYxY=TeNS@"
    "search-index-website-production-nwu2er7s3wt4fw45o5shvi6bky.eu-west-1.es.amazonaws.com"
)
ES_INDEX = "wagtail__startup_jobs_jobmodel"


class IndexVenturesScraper(BaseScraper):
    """Scraper for Index Ventures portfolio jobs.

    Queries the same Elasticsearch index that the Vue.js frontend uses.
    """

    name = "Index Ventures"
    base_url = "https://www.indexventures.com"
    jobs_url = "https://www.indexventures.com/startup-jobs"

    SEARCH_QUERIES = [
        "product designer",
        "ux designer",
        "ui designer",
        "design",
    ]

    # Fields to retrieve from Elasticsearch
    ES_SOURCE_FIELDS = [
        "title",
        "job_company_title",
        "job_application_url_filter",
        "url_filter",
        "job_geolocations_display_name",
        "cleaned_job_description",
        "last_published_at_filter",
        "live_filter",
        "job_company_stage_filter",
        "job_company_sector_filter",
    ]

    def scrape(self) -> list[Job]:
        """Scrape design jobs from Index Ventures via Elasticsearch."""
        jobs = []
        seen = set()

        for query in self.SEARCH_QUERIES:
            new_jobs = self._search_es(query)
            for job in new_jobs:
                key = (job.title, job.company, job.url)
                if key not in seen:
                    seen.add(key)
                    jobs.append(job)

            if jobs:
                logger.debug(f"[{self.name}] {len(jobs)} jobs after query '{query}'")

        if not jobs:
            logger.warning(
                f"[{self.name}] No design jobs found via Elasticsearch. "
                f"Credentials may have changed."
            )

        self.log_found(len(jobs))
        return jobs

    def _search_es(self, query: str) -> list[Job]:
        """Run an Elasticsearch query for design jobs."""
        search_url = f"{ES_URL}/{ES_INDEX}/_search"
        payload = {
            "size": 50,
            "query": {
                "bool": {
                    "must": [
                        {
                            "query_string": {
                                "query": query,
                                "fields": ["title^13", "get_synonyms^11", "job_category_name^2"],
                            }
                        },
                        {
                            "term": {
                                "_django_content_type": "startup_jobs.JobModel",
                            }
                        },
                    ],
                    "filter": [
                        {"term": {"live_filter": True}},
                    ],
                }
            },
            "_source": self.ES_SOURCE_FIELDS,
            "sort": [{"_score": "desc"}, {"last_published_at_filter": "desc"}],
        }

        try:
            time.sleep(0.5)
            response = self.session.post(
                search_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"[{self.name}] ES search error for '{query}': {e}")
            return []

        return self._parse_es_response(data)

    def _parse_es_response(self, data: dict) -> list[Job]:
        """Parse Elasticsearch response into Job objects."""
        jobs = []
        hits = data.get("hits", {}).get("hits", [])

        for hit in hits:
            src = hit.get("_source", {})
            job = self._parse_es_hit(src)
            if job:
                jobs.append(job)

        return jobs

    def _parse_es_hit(self, src: dict) -> Optional[Job]:
        """Parse a single ES hit into a Job."""
        try:
            title = src.get("title", "")
            if not title or not self.is_design_job(title):
                return None

            company = src.get("job_company_title", "Index Ventures Portfolio")

            # Location from display names
            locations = src.get("job_geolocations_display_name", [])
            if isinstance(locations, list) and locations:
                location = ", ".join(str(loc) for loc in locations[:3] if loc)
            else:
                location = "Not specified"

            if not self.is_valid_location(location):
                return None

            # URL: prefer the application URL, fall back to the IV site URL
            url = src.get("job_application_url_filter", "")
            if not url:
                url_path = src.get("url_filter", "")
                if url_path:
                    url = f"{self.base_url}{url_path}"
                else:
                    url = self.jobs_url

            # Posted date
            posted_date = None
            published = src.get("last_published_at_filter", "")
            if published:
                try:
                    clean = published.split("+")[0].split("Z")[0]
                    for fmt in ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"]:
                        try:
                            posted_date = datetime.strptime(clean, fmt)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

            if not self.is_recent_posting(posted_date):
                return None

            # Description: strip HTML tags
            description = src.get("cleaned_job_description") or ""
            if description:
                description = re.sub(r"<[^>]+>", " ", description)
                description = self.clean_text(description)[:8000]

            return Job(
                title=title,
                company=company,
                location=self.extract_location(location),
                url=url,
                description=description,
                source=self.name,
                scraped_at=datetime.utcnow(),
                posted_date=posted_date,
            )

        except Exception as e:
            logger.debug(f"[{self.name}] Error parsing ES hit: {e}")
            return None
