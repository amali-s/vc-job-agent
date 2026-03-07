# Job Posting Processing Workflow

How the VC Job Agent processes a single job posting, from discovery to match score.

---

## Step-by-Step Walkthrough

### Phase 1: Discovery (Scraping)

```
1. SCRAPER INITIALIZATION
   │
   │  One of 14 VC board scrapers (e.g. A16ZScraper) is launched in a
   │  ThreadPoolExecutor alongside the other 13 scrapers.
   │
   ▼
2. FETCH LISTING PAGE
   │
   │  URL visited: e.g. https://portfoliojobs.a16z.com/jobs
   │  Method: HTTP GET via requests.Session with browser User-Agent
   │  Rate limiting: 1-second delay before fetch
   │
   ▼
3. EXTRACT JOB DATA FROM LISTING
   │
   │  Strategy 1 (primary): Parse __NEXT_DATA__ script tag
   │    → Navigate JSON: props → pageProps → jobs/initialJobs/listings
   │    → Also checks: dehydratedState → queries (React Query cache)
   │
   │  Strategy 2 (fallback): Parse embedded JSON in other script tags
   │    → Regex patterns for window.__INITIAL_STATE__, etc.
   │
   │  Strategy 3 (last resort): HTML CSS selector parsing
   │    → .job-card, .posting, [class*='job'] selectors
   │
   │  Data extracted at this step:
   │    • title         (job title string)
   │    • company       (company name)
   │    • location      (city / remote status)
   │    • url           (link to full job posting)
   │    • description   (short description from listing, often truncated)
   │    • posted_date   (parsed from 12+ date formats)
   │    • salary_range  (if present in listing data)
   │    • remote        (boolean, inferred from location keywords)
   │    • source        (e.g. "a16z", "Sequoia")
   │
   ▼
4. FIRST-PASS FILTERS (at scrape time)
   │
   │  Filter 1: is_design_job(title, description)
   │    → Checks against 24 design keywords (product designer, ux, ui, etc.)
   │    → Must match at least one keyword in title or description
   │
   │  Filter 2: is_valid_location(location)
   │    → Accepts: NYC (7 keywords), SF/Bay Area (15 keywords), Remote (3 keywords)
   │    → Unknown/empty locations pass through (avoid false negatives)
   │
   │  Filter 3: is_recent_posting(posted_date, max_days=30)
   │    → Rejects postings older than 30 days
   │    → Unknown dates pass through
   │
   │  Jobs that fail any filter are discarded.
   │
   ▼
5. MEMORY CHECK (new in this version)
   │
   │  Each job URL is checked against data/scraped_jobs.json
   │    → If URL exists: marked as "previously seen", last_seen updated
   │    → If URL is new: added to memory with first_seen timestamp
   │    → Memory entries expire after 60 days of not being seen
   │
   │  Previously seen jobs still proceed to matching but skip
   │  the detail page fetch (optimization).
```

### Phase 2: Enrichment

```
6. DEDUPLICATION
   │
   │  All jobs from all 14 scrapers are merged.
   │  Duplicates removed by URL (first occurrence kept).
   │
   ▼
7. POST-SCRAPE FILTERS
   │
   │  Same location + recency filters applied again as safety net
   │  (catches edge cases where scraper-level filtering was incomplete).
   │
   ▼
8. FETCH JOB DETAIL PAGE (for new jobs only)
   │
   │  URL visited: The job's specific URL (e.g. https://portfoliojobs.a16z.com/jobs/12345)
   │  Method: HTTP GET with 0.3s delay
   │
   │  Content extraction (in order of specificity):
   │    1. Try CSS selectors: .job-description, [class*='description'], article, main
   │    2. Fallback: use <body> element
   │
   │  Data extracted at this step:
   │    • company_description  (first ~3 paragraphs before any section heading)
   │    • qualifications       (content under "Requirements"/"Qualifications" headings)
   │                            → DOM-based extraction: find heading, collect siblings
   │                            → Text-based fallback: line-by-line section detection
   │    • description          (full page text, replaces truncated listing description)
   │    • salary_range         (regex: $XXX,XXX - $XXX,XXX patterns)
```

### Phase 3: Matching

```
9. BUILD MATCHING PROMPT
   │
   │  Candidate profile assembled from:
   │    • Resume text (first 10,000 chars from PDF)
   │    • Portfolio content (first 15,000 chars from website + subpages)
   │    • Structured summary:
   │        - technical_skills, strengths, soft_skills
   │        - years_of_experience, products_worked_on
   │        - team_types, interface_types
   │        - problems_solved, design_methods, visual_skillset
   │        - goals_motivations
   │
   │  Job context assembled from:
   │    • title, company, location
   │    • company_description (first 2,000 chars)
   │    • qualifications      (first 4,000 chars) ← PRIORITIZED
   │    • description         (first 8,000 chars)
   │
   ▼
10. LLM EVALUATION (Anthropic Claude API)
    │
    │  Model: claude-sonnet-4-20250514
    │  Max tokens: 1024
    │
    │  Evaluation dimensions:
    │    1. Skills & strengths — technical skills + design tools match
    │    2. Experience level — years + product types alignment
    │    3. Team fit — cross-functional, startup, enterprise experience
    │    4. Industry fit — B2B/consumer/SaaS background match
    │    5. Results — project outcomes + problem-solving evidence
    │
    │  Output (JSON):
    │    • match_percentage   (0-100 integer)
    │    • matching_skills    (list of matched skills)
    │    • missing_skills     (list of gaps)
    │    • matched_keywords   (phrases from posting that matched)
    │    • company_bio        (1-2 sentence company description)
    │    • company_series     (funding stage if mentioned)
    │    • recommendation     (2-3 sentence explanation)
    │
    ▼
11. THRESHOLD FILTER
    │
    │  Only jobs with match_percentage >= 60% (configurable) are kept.
    │  Results sorted by match percentage descending.
    │
    ▼
12. RANK-CHANGE TRACKING
    │
    │  Current run's rankings compared against data/match_history.json:
    │    • rank        = position in today's sorted results (1-indexed)
    │    • rank_delta  = previous_rank - current_rank (positive = moved up)
    │    • match_delta = current_match% - previous_match%
    │
    │  Today's rankings saved for tomorrow's comparison.
```

### Phase 4: Delivery

```
13. EMAIL GENERATION
    │
    │  HTML email built with:
    │    • Job cards (title, company, match%, rank delta, keywords, apply link)
    │    • Per-source scrape summary table (total/new/seen per VC board)
    │
    ▼
14. EMAIL DELIVERY
    │
    │  Sent via Gmail SMTP or SendGrid API
    │  Subject: "🎯 N Product Designer Jobs - Mar 07, 2026"
```

---

## Visual Flowchart

```
┌──────────────────┐     ┌──────────────────┐
│  Resume PDF      │     │  Portfolio URL    │
│  (data/resume)   │     │  (+ 5 subpages)  │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         └──────────┬─────────────┘
                    ▼
         ┌──────────────────┐
         │  Claude API      │
         │  Extract profile │
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ CandidateProfile │
         │ (structured)     │
         └────────┬─────────┘
                  │
    ┌─────────────┼─────────────────────────────────┐
    │             │                                  │
    ▼             ▼              ...                 ▼
┌────────┐  ┌────────┐                        ┌────────┐
│ a16z   │  │Sequoia │   (14 scrapers         │  BVP   │
│scraper │  │scraper │    in parallel)         │scraper │
└───┬────┘  └───┬────┘                        └───┬────┘
    │           │                                  │
    └─────────┬─┴──────────────────────────────────┘
              │
              ▼
    ┌──────────────────┐
    │ Deduplicate      │
    │ by URL           │
    └────────┬─────────┘
              │
              ▼
    ┌──────────────────┐       ┌──────────────────┐
    │ Memory check     │◄─────│ scraped_jobs.json │
    │ (new vs seen)    │─────►│ (updated)         │
    └────────┬─────────┘       └──────────────────┘
              │
              ▼
    ┌──────────────────┐
    │ Filter           │
    │ location/recency │
    └────────┬─────────┘
              │
              ▼
    ┌──────────────────┐
    │ Fetch detail     │
    │ pages (new only) │
    └────────┬─────────┘
              │
              ▼
    ┌──────────────────┐
    │ Claude API       │
    │ Match each job   │
    │ (5 dimensions)   │
    └────────┬─────────┘
              │
              ▼
    ┌──────────────────┐       ┌──────────────────────┐
    │ Rank + deltas    │◄─────│ match_history.json    │
    │ (vs yesterday)   │─────►│ (updated)             │
    └────────┬─────────┘       └──────────────────────┘
              │
              ▼
    ┌──────────────────┐
    │ Email digest     │
    │ (Gmail/SendGrid) │
    └──────────────────┘
```

---

## Data Sizes & Limits

| Field | Max Size | Source |
|-------|----------|--------|
| Resume text for profile | 10,000 chars | PDF via PyMuPDF |
| Portfolio content | 15,000 chars | Website scrape (6 pages) |
| Company description | 2,000 chars | Detail page top paragraphs |
| Qualifications section | 4,000 chars | Detail page heading extraction |
| Full job description | 8,000 chars | Detail page full text |
| LLM response (matching) | 1,024 tokens | Claude API |
| LLM response (extraction) | 2,048 tokens | Claude API |
