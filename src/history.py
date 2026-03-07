"""Persistence layer for match history and scraped job memory."""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from .models import MatchResult, ScrapeSummary

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
MATCH_HISTORY_FILE = os.path.join(DATA_DIR, "match_history.json")
SCRAPED_JOBS_FILE = os.path.join(DATA_DIR, "scraped_jobs.json")


# ---------------------------------------------------------------------------
# Match history — stores daily ranked results for rank-change tracking
# ---------------------------------------------------------------------------

def load_previous_rankings() -> dict[str, dict]:
    """Load the most recent day's rankings from history.

    Returns a dict keyed by job URL with {'rank': int, 'match_percentage': int}.
    """
    if not os.path.exists(MATCH_HISTORY_FILE):
        return {}

    try:
        with open(MATCH_HISTORY_FILE, "r") as f:
            history = json.load(f)

        if not history:
            return {}

        # Get the most recent day's data
        latest_date = max(history.keys())
        entries = history[latest_date]
        return {entry["url"]: entry for entry in entries}

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Could not load match history: {e}")
        return {}


def save_rankings(matches: list[MatchResult]) -> None:
    """Save today's ranked results to history file."""
    os.makedirs(DATA_DIR, exist_ok=True)

    # Load existing history
    history = {}
    if os.path.exists(MATCH_HISTORY_FILE):
        try:
            with open(MATCH_HISTORY_FILE, "r") as f:
                history = json.load(f)
        except (json.JSONDecodeError, TypeError):
            history = {}

    today = datetime.utcnow().strftime("%Y-%m-%d")
    history[today] = [
        {
            "url": m.job.url,
            "title": m.job.title,
            "company": m.job.company,
            "rank": m.rank,
            "match_percentage": m.match_percentage,
        }
        for m in matches
    ]

    # Keep only last 30 days of history
    cutoff = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    history = {date: data for date, data in history.items() if date >= cutoff}

    with open(MATCH_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

    logger.info(f"Saved {len(matches)} rankings to history ({today})")


def apply_rank_deltas(matches: list[MatchResult]) -> list[MatchResult]:
    """Assign ranks and compute deltas from previous day's run.

    Modifies matches in-place and returns them.
    """
    previous = load_previous_rankings()

    for i, match in enumerate(matches):
        match.rank = i + 1

        prev = previous.get(match.job.url)
        if prev:
            match.rank_delta = prev["rank"] - match.rank  # positive = moved up
            match.match_delta = match.match_percentage - prev["match_percentage"]

    save_rankings(matches)
    return matches


# ---------------------------------------------------------------------------
# Scraped job memory — tracks previously seen job URLs to avoid re-scraping
# ---------------------------------------------------------------------------

def load_scraped_jobs() -> dict[str, dict]:
    """Load the memory of previously scraped job URLs.

    Returns dict keyed by URL with metadata: {first_seen, last_seen, source, title, company}.
    """
    if not os.path.exists(SCRAPED_JOBS_FILE):
        return {}

    try:
        with open(SCRAPED_JOBS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Could not load scraped jobs memory: {e}")
        return {}


def save_scraped_jobs(memory: dict[str, dict]) -> None:
    """Save scraped jobs memory to disk, pruning entries older than 60 days."""
    os.makedirs(DATA_DIR, exist_ok=True)

    cutoff = (datetime.utcnow() - timedelta(days=60)).isoformat()
    pruned = {
        url: meta for url, meta in memory.items()
        if meta.get("last_seen", "") >= cutoff
    }

    with open(SCRAPED_JOBS_FILE, "w") as f:
        json.dump(pruned, f, indent=2)

    pruned_count = len(memory) - len(pruned)
    if pruned_count > 0:
        logger.info(f"Pruned {pruned_count} stale entries from scraped jobs memory")


def update_scraped_jobs_memory(jobs: list, memory: dict[str, dict]) -> tuple[list, dict[str, dict]]:
    """Classify jobs as new or previously seen and update memory.

    Args:
        jobs: List of Job objects from current scrape.
        memory: Current scraped jobs memory dict.

    Returns:
        Tuple of (new_jobs_only, updated_memory).
    """
    now = datetime.utcnow().isoformat()
    new_jobs = []

    for job in jobs:
        if job.url in memory:
            # Previously seen — update last_seen timestamp
            memory[job.url]["last_seen"] = now
        else:
            # Net-new job
            memory[job.url] = {
                "first_seen": now,
                "last_seen": now,
                "source": job.source,
                "title": job.title,
                "company": job.company,
            }
            new_jobs.append(job)

    return new_jobs, memory


def compute_scrape_summaries(
    all_jobs: list, memory: dict[str, dict]
) -> list[ScrapeSummary]:
    """Compute per-source scrape summaries (total, new, previously seen).

    Args:
        all_jobs: All jobs from current scrape (before dedup/filtering).
        memory: Scraped jobs memory dict (before current run's update).

    Returns:
        List of ScrapeSummary objects sorted by source name.
    """
    by_source: dict[str, ScrapeSummary] = {}

    for job in all_jobs:
        source = job.source
        if source not in by_source:
            by_source[source] = ScrapeSummary(source=source)

        summary = by_source[source]
        summary.total += 1

        if job.url in memory:
            summary.previously_seen += 1
        else:
            summary.new += 1

    return sorted(by_source.values(), key=lambda s: s.source)
