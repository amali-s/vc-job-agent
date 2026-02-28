"""Main orchestrator for the VC Job Agent."""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from .scrapers import ALL_SCRAPERS
from .scrapers.base import BaseScraper
from .resume_parser import get_profile
from .matcher import JobMatcher
from .emailer import send_digest
from .models import Job

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def scrape_all_jobs(max_workers: int = 5) -> list[Job]:
    """Scrape jobs from all VC job boards in parallel."""
    all_jobs: list[Job] = []
    scrapers = [scraper_class() for scraper_class in ALL_SCRAPERS]

    logger.info(f"Starting to scrape {len(scrapers)} job boards...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_scraper = {
            executor.submit(scraper.scrape): scraper for scraper in scrapers
        }

        for future in as_completed(future_to_scraper):
            scraper = future_to_scraper[future]
            try:
                jobs = future.result()
                all_jobs.extend(jobs)
                logger.info(f"[{scraper.name}] Completed: {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"[{scraper.name}] Failed: {e}")

    # Deduplicate jobs by URL
    seen_urls = set()
    unique_jobs = []
    for job in all_jobs:
        if job.url not in seen_urls:
            seen_urls.add(job.url)
            unique_jobs.append(job)

    logger.info(f"Total unique jobs found: {len(unique_jobs)}")
    return unique_jobs


def enhance_jobs_with_details(jobs: list[Job], max_workers: int = 5) -> list[Job]:
    """Fetch full descriptions from job detail pages in parallel.

    Enhances jobs that have short or missing descriptions by following
    their URLs to scrape the complete job posting content.
    """
    if not jobs:
        return jobs

    logger.info(f"Fetching detail pages for {len(jobs)} jobs...")

    # Use a BaseScraper instance for the fetch method
    scraper = BaseScraper.__subclasses__()[0]()
    enhanced_count = 0

    # Record original description lengths before enhancement
    original_lengths = {id(job): len(job.description) for job in jobs}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_job = {
            executor.submit(scraper.fetch_job_detail, job): job for job in jobs
        }

        results = []
        for future in as_completed(future_to_job):
            original = future_to_job[future]
            try:
                updated = future.result()
                if len(updated.description) > original_lengths.get(id(original), 0):
                    enhanced_count += 1
                results.append(updated)
            except Exception as e:
                logger.debug(f"Detail fetch failed for {original.title}: {e}")
                results.append(original)

    logger.info(f"Enhanced {enhanced_count}/{len(jobs)} jobs with full descriptions")
    return results


def filter_jobs(jobs: list[Job]) -> list[Job]:
    """Apply location and recency filters as a post-scrape safety net.

    Filters jobs to only include those in New York, San Francisco, or Remote,
    and posted within the last 30 days.
    """
    scraper = BaseScraper.__subclasses__()[0]()  # Use any scraper instance for filter methods

    filtered = []
    for job in jobs:
        if not scraper.is_valid_location(job.location):
            logger.debug(f"Filtered out (location): {job.title} at {job.company} — {job.location}")
            continue
        if not scraper.is_recent_posting(job.posted_date, max_days=30):
            logger.debug(f"Filtered out (old posting): {job.title} at {job.company} — {job.posted_date}")
            continue
        filtered.append(job)

    removed = len(jobs) - len(filtered)
    if removed > 0:
        logger.info(f"Post-scrape filter removed {removed} jobs (location/recency)")

    return filtered


def run(dry_run: bool = False, min_match: int = 60, skip_details: bool = False) -> int:
    """Run the complete job scanning pipeline.

    Args:
        dry_run: If True, skip sending email
        min_match: Minimum match percentage to include (default 60%)
        skip_details: If True, skip fetching full descriptions from detail pages

    Returns:
        Number of matching jobs found
    """
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("VC Product Designer Job Agent")
    logger.info(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Step 1: Parse resume and portfolio
    logger.info("\n📄 Parsing resume and portfolio...")
    try:
        profile = get_profile()
        if not profile.resume_text and not profile.portfolio_content:
            logger.warning("No profile content found. Add resume.pdf to data/ folder.")
        else:
            logger.info(f"Profile loaded: {len(profile.full_profile)} characters")
    except Exception as e:
        logger.error(f"Failed to parse profile: {e}")
        profile = None

    # Step 2: Scrape jobs from all sources
    logger.info("\n🔍 Scraping job boards...")
    jobs = scrape_all_jobs()

    if not jobs:
        logger.warning("No jobs found. Check scraper logs for errors.")
        return 0

    # Step 2.5: Apply post-scrape location and recency filters
    logger.info(f"\n📍 Filtering {len(jobs)} jobs by location (NYC/SF/Remote) and recency (<30 days)...")
    jobs = filter_jobs(jobs)

    if not jobs:
        logger.warning("No jobs remaining after location/recency filtering.")
        return 0

    logger.info(f"{len(jobs)} jobs passed filters")

    # Step 2.75: Enhance jobs with full descriptions from detail pages
    if not skip_details:
        logger.info(f"\n📝 Fetching full job descriptions from detail pages...")
        jobs = enhance_jobs_with_details(jobs)
    else:
        logger.info("Skipping detail page fetching (--skip-details)")

    # Step 3: Match jobs against profile
    logger.info(f"\n🎯 Matching {len(jobs)} jobs against profile...")

    if profile and (profile.resume_text or profile.portfolio_content):
        try:
            matcher = JobMatcher()
            matches = matcher.match_jobs(jobs, profile, min_match=min_match)
        except ValueError as e:
            logger.error(f"Matcher error: {e}")
            logger.info("Skipping matching - will send all jobs")
            # Create dummy matches for all jobs
            from .models import MatchResult
            matches = [
                MatchResult(job=job, match_percentage=50, recommendation="Not scored - no API key")
                for job in jobs
            ]
    else:
        logger.warning("No profile available - sending all jobs without matching")
        from .models import MatchResult
        matches = [
            MatchResult(job=job, match_percentage=50, recommendation="Not scored - no profile")
            for job in jobs
        ]

    if not matches:
        logger.info("No jobs matched the minimum threshold.")
        return 0

    # Step 4: Send email digest
    logger.info(f"\n📧 Sending digest with {len(matches)} jobs...")

    try:
        success = send_digest(matches, dry_run=dry_run)
        if success:
            logger.info("Email sent successfully!" if not dry_run else "Dry run completed.")
        else:
            logger.error("Failed to send email.")
    except ValueError as e:
        logger.error(f"Email configuration error: {e}")
        logger.info("Skipping email - printing results instead")
        print("\n" + "=" * 60)
        print("JOB MATCHES")
        print("=" * 60)
        for match in matches:
            print(f"\n{match.job.title} at {match.job.company}")
            print(f"  Match: {match.match_percentage}%")
            print(f"  Location: {match.job.location}")
            print(f"  Source: {match.job.source}")
            print(f"  URL: {match.job.url}")
            if match.company_bio:
                print(f"  About: {match.company_bio}")
            if match.job.salary_range:
                print(f"  Salary: {match.job.salary_range}")
            if match.matched_keywords:
                print(f"  Matched: {', '.join(match.matched_keywords)}")
            if match.recommendation:
                print(f"  Note: {match.recommendation}")

    # Summary
    elapsed = datetime.now() - start_time
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Jobs scraped: {len(jobs)}")
    logger.info(f"Jobs matched: {len(matches)}")
    logger.info(f"Time elapsed: {elapsed.total_seconds():.1f}s")
    logger.info("=" * 60)

    return len(matches)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="VC Product Designer Job Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without sending email",
    )
    parser.add_argument(
        "--min-match",
        type=int,
        default=60,
        help="Minimum match percentage (default: 60)",
    )
    parser.add_argument(
        "--skip-details",
        action="store_true",
        help="Skip fetching full descriptions from job detail pages",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        matches = run(dry_run=args.dry_run, min_match=args.min_match, skip_details=args.skip_details)
        sys.exit(0 if matches >= 0 else 1)
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
