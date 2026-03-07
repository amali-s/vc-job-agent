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
from .models import Job, ScrapeSummary
from .history import (
    apply_rank_deltas,
    load_scraped_jobs,
    save_scraped_jobs,
    update_scraped_jobs_memory,
    compute_scrape_summaries,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _format_rank_delta(delta: int | None) -> str:
    """Format a rank delta for display."""
    if delta is None:
        return "NEW"
    if delta > 0:
        return f"↑{delta}"
    if delta < 0:
        return f"↓{abs(delta)}"
    return "—"


def _format_match_delta(delta: int | None) -> str:
    """Format a match % delta for display."""
    if delta is None:
        return ""
    if delta > 0:
        return f" (↑{delta}%)"
    if delta < 0:
        return f" (↓{abs(delta)}%)"
    return ""


def print_scrape_summary(summaries: list[ScrapeSummary]) -> None:
    """Print a per-source scrape summary table to the console."""
    if not summaries:
        return

    logger.info("\n" + "=" * 60)
    logger.info("SCRAPE SUMMARY BY SOURCE")
    logger.info("=" * 60)
    logger.info(f"{'Source':<25} {'Total':>6} {'New':>6} {'Seen':>6}")
    logger.info("-" * 49)

    total_all, new_all, seen_all = 0, 0, 0
    for s in summaries:
        logger.info(f"{s.source:<25} {s.total:>6} {s.new:>6} {s.previously_seen:>6}")
        total_all += s.total
        new_all += s.new
        seen_all += s.previously_seen

    logger.info("-" * 49)
    logger.info(f"{'TOTAL':<25} {total_all:>6} {new_all:>6} {seen_all:>6}")


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

            # --- Task 7: Resume analysis summary ---
            print_resume_summary(profile)
            # --- Task 6: Portfolio link analysis summary ---
            print_portfolio_summary(profile)
    except Exception as e:
        logger.error(f"Failed to parse profile: {e}")
        profile = None

    # Load scraped jobs memory (Task 3)
    scraped_memory = load_scraped_jobs()
    logger.info(f"Loaded memory of {len(scraped_memory)} previously scraped jobs")

    # Step 2: Scrape jobs from all sources
    logger.info("\n🔍 Scraping job boards...")
    jobs = scrape_all_jobs()

    if not jobs:
        logger.warning("No jobs found. Check scraper logs for errors.")
        return 0

    # Task 4: Compute per-source scrape summary (before memory update)
    scrape_summaries = compute_scrape_summaries(jobs, scraped_memory)
    print_scrape_summary(scrape_summaries)

    # Task 3: Update memory and identify new vs previously-seen jobs
    new_jobs, scraped_memory = update_scraped_jobs_memory(jobs, scraped_memory)
    save_scraped_jobs(scraped_memory)
    logger.info(f"New jobs this run: {len(new_jobs)} | Previously seen: {len(jobs) - len(new_jobs)}")

    # Drop previously seen jobs — only process net-new postings
    total_before = len(jobs)
    new_urls = {j.url for j in new_jobs}
    jobs = [j for j in jobs if j.url in new_urls]
    logger.info(f"Proceeding with {len(jobs)} new jobs (skipped {total_before - len(jobs)} previously seen)")

    if not jobs:
        logger.info("No new jobs to process this run.")
        return 0

    # Step 2.5: Apply post-scrape location and recency filters
    logger.info(f"\n📍 Filtering {len(jobs)} jobs by location (NYC/SF/Remote) and recency (<30 days)...")
    jobs = filter_jobs(jobs)

    if not jobs:
        logger.warning("No new jobs remaining after location/recency filtering.")
        return 0

    logger.info(f"{len(jobs)} new jobs passed filters")

    # Step 2.75: Fetch full descriptions from detail pages for new jobs
    if not skip_details:
        logger.info(f"\n📝 Fetching detail pages for {len(jobs)} new jobs...")
        jobs = enhance_jobs_with_details(jobs)
    else:
        logger.info("Skipping detail page fetching (--skip-details)")

    # Step 3: Match new jobs against profile
    logger.info(f"\n🎯 Matching {len(jobs)} new jobs against profile...")

    if profile and (profile.resume_text or profile.portfolio_content):
        try:
            matcher = JobMatcher()
            matches = matcher.match_jobs(jobs, profile, min_match=min_match)
        except ValueError as e:
            logger.error(f"Matcher error: {e}")
            logger.info("Skipping matching - will send all jobs")
            from .models import MatchResult
            matches = [
                MatchResult(job=job, match_percentage=50, recommendation="Not scored - no ANTHROPIC_API_KEY")
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

    # Task 2: Apply rank-change tracking
    matches = apply_rank_deltas(matches)

    # Step 4: Send email digest
    logger.info(f"\n📧 Sending digest with {len(matches)} jobs...")

    try:
        success = send_digest(matches, scrape_summaries=scrape_summaries, dry_run=dry_run)
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
            rank_str = f"Rank: #{match.rank} ({_format_rank_delta(match.rank_delta)})"
            match_str = f"Match: {match.match_percentage}%{_format_match_delta(match.match_delta)}"
            print(f"\n{match.job.title} at {match.job.company}")
            print(f"  {rank_str} | {match_str}")
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
    logger.info(f"New jobs: {len(new_jobs)}")
    logger.info(f"Previously seen: {len(scraped_memory) - len(new_jobs)}")
    logger.info(f"Time elapsed: {elapsed.total_seconds():.1f}s")
    logger.info("=" * 60)

    return len(matches)


def print_resume_summary(profile) -> None:
    """Task 7: Print structured resume analysis summary at start of run."""
    if not profile.resume_text:
        return

    logger.info("\n" + "=" * 60)
    logger.info("RESUME ANALYSIS SUMMARY")
    logger.info("=" * 60)

    if profile.technical_skills:
        logger.info(f"Technical Skills: {', '.join(profile.technical_skills)}")
    if profile.strengths:
        logger.info(f"Strengths: {', '.join(profile.strengths)}")
    if profile.soft_skills:
        logger.info(f"Soft Skills: {', '.join(profile.soft_skills)}")
    if profile.years_of_experience:
        logger.info(f"Experience Level: {profile.years_of_experience}")
    if profile.products_worked_on:
        logger.info(f"Product Types: {', '.join(profile.products_worked_on)}")
    if profile.team_types:
        logger.info(f"Team Types: {', '.join(profile.team_types)}")
    if profile.interface_types:
        logger.info(f"Interface Types: {', '.join(profile.interface_types)}")

    # Flag gaps
    gaps = []
    if not profile.technical_skills:
        gaps.append("technical skills (could not extract from resume)")
    if not profile.years_of_experience:
        gaps.append("years of experience (not clearly stated)")
    if not profile.products_worked_on:
        gaps.append("product types (no product context found)")
    if gaps:
        logger.info(f"Gaps/Ambiguities: {'; '.join(gaps)}")
    else:
        logger.info("Parsing: All key sections extracted successfully")

    logger.info("=" * 60)


def print_portfolio_summary(profile) -> None:
    """Task 6: Print portfolio link analysis summary."""
    if not profile.portfolio_content:
        return

    logger.info("\n" + "=" * 60)
    logger.info("PORTFOLIO ANALYSIS SUMMARY")
    logger.info("=" * 60)

    if profile.problems_solved:
        logger.info(f"Problems Solved: {', '.join(profile.problems_solved)}")
    if profile.design_methods:
        logger.info(f"Design Methods: {', '.join(profile.design_methods)}")
    if profile.visual_skillset:
        logger.info(f"Visual Skills: {', '.join(profile.visual_skillset)}")
    if profile.goals_motivations:
        logger.info(f"Goals & Motivations: {profile.goals_motivations}")

    # Skills inferred from portfolio
    all_skills = set()
    if profile.technical_skills:
        all_skills.update(profile.technical_skills)
    if profile.visual_skillset:
        all_skills.update(profile.visual_skillset)
    if all_skills:
        logger.info(f"Tools/Technologies Detected: {', '.join(sorted(all_skills))}")

    # Project types
    if profile.products_worked_on:
        logger.info(f"Project Types Identified: {', '.join(profile.products_worked_on)}")

    # Flag gaps
    gaps = []
    if not profile.problems_solved:
        gaps.append("no case study outcomes found")
    if not profile.design_methods:
        gaps.append("no design process/methods documented")
    if not profile.visual_skillset:
        gaps.append("visual skills not clearly showcased")
    if not profile.goals_motivations:
        gaps.append("no about/bio section found")
    if gaps:
        logger.info(f"Gaps/Ambiguities: {'; '.join(gaps)}")
    else:
        logger.info("Extraction: All portfolio sections parsed successfully")

    logger.info("=" * 60)


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
