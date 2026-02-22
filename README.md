# VC Product Designer Job Agent

An AI-powered job agent that scrapes product designer positions from 14 VC portfolio job boards, intelligently matches them against your resume and portfolio, and sends daily email digests with the best-fit opportunities in New York and San Francisco.

## What It Does

This agent runs daily to find product designer roles that actually fit your background. Rather than just keyword matching, it uses an LLM to deeply parse your resume and portfolio — extracting your technical skills, strengths, years of experience, the types of products you've built, the teams you've worked with, and the problems you've solved — then evaluates each job posting against those dimensions.

The result is a daily email with your top matches, each showing the match percentage, a brief company bio, funding stage, salary (when listed), and the specific words from the job posting that aligned with your profile.

## How It Works

```
Resume + Portfolio
       │
       ▼
┌─────────────────┐     ┌──────────────────┐     ┌──────────────┐     ┌──────────────┐
│  Profile Parser  │────▶│   Job Scrapers   │────▶│   Matcher    │────▶│   Emailer    │
│  (LLM-powered)  │     │  (14 VC boards)  │     │ (Claude/GPT) │     │ (Gmail/SG)   │
└─────────────────┘     └──────────────────┘     └──────────────┘     └──────────────┘
                                │                        │
                         Filters applied:          Evaluates on:
                         • NYC / SF / Remote       • Skills & strengths
                         • Posted < 30 days        • Experience & products
                                                   • Team types
                                                   • Industry fit
                                                   • Results achieved
```

### Profile Parsing

The agent uses an LLM to extract structured data from your resume and portfolio:

**From your resume:** technical skills, strengths, soft skills, years of experience, types of products worked on, team types, and interface/experience types designed.

**From your portfolio:** years of experience, product types, problems solved in case studies, design process and methods, team collaborations, visual skillset, and goals/motivations from your about section.

This structured profile is then used for richer, more accurate matching.

### Job Scraping

Scrapes design roles from 14 VC portfolio job boards in parallel:

a16z, Sequoia, General Catalyst, Index Ventures, Greylock, Kleiner Perkins, Accel, Contrary, Pear VC, Battery Ventures, NEA, Antler, LSVP, and Bessemer.

Jobs are filtered to only include positions located in **New York**, **San Francisco / Bay Area**, or **Remote**, and posted within the **last 30 days**. Salary and posting date are extracted when available.

### Matching

Each job is evaluated against your profile on five dimensions:

1. **Skills & strengths** — Do your technical skills and design tools match what the role asks for?
2. **Experience & products** — Does your experience level and the types of products you've built align?
3. **Team fit** — Have you worked in the types of teams this role involves?
4. **Industry fit** — Does your company/industry background align with theirs?
5. **Results** — Do your project outcomes match what the role is looking for?

Jobs scoring 60% or higher are included in the digest, sorted best-first.

### Email Digest

Each job card in the daily email shows:

- Job title, company, and location
- Match percentage as colored text (green 80%+, blue 70%+, amber below)
- Company bio and funding series (when available)
- Posting date
- Salary range (when listed in the job description)
- Matched keywords — the specific words from the posting that aligned with your profile
- Direct apply link

## Setup

### 1. Install Dependencies

```bash
cd vc-job-agent
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

**Required:**

- One AI API key: `ANTHROPIC_API_KEY` (Claude) or `OPENAI_API_KEY` (GPT-4o)
- One email provider:
  - Gmail: `GMAIL_USER` + `GMAIL_APP_PASSWORD`
  - SendGrid: `SENDGRID_API_KEY` + `EMAIL_FROM`
- `EMAIL_TO` — your email address for receiving digests

**Optional:**

- `PORTFOLIO_URL` — your portfolio website URL (defaults to `https://www.amayamali.com/`)

### 3. Add Your Resume

Place your resume PDF at `data/resume.pdf`.

### 4. Run

```bash
python -m src.main
```

Dry run (skips sending email, prints results):

```bash
python -m src.main --dry-run
```

Verbose mode:

```bash
python -m src.main --dry-run -v
```

Custom match threshold:

```bash
python -m src.main --min-match 70
```

## GitHub Actions

The agent runs automatically via GitHub Actions at **5:00 PM CST daily**. You can also trigger it manually from the Actions tab.

### Required Secrets

Add these in your repository settings under Settings → Secrets → Actions:

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` | AI API key for profile parsing and job matching |
| `GMAIL_USER` + `GMAIL_APP_PASSWORD` | Gmail credentials (or use SendGrid below) |
| `SENDGRID_API_KEY` + `EMAIL_FROM` | SendGrid credentials (alternative to Gmail) |
| `EMAIL_TO` | Your email address |

## Project Structure

```
vc-job-agent/
├── src/
│   ├── main.py              # Orchestrator — scrape → filter → match → email
│   ├── models.py            # Data models (Job, MatchResult, CandidateProfile)
│   ├── resume_parser.py     # Resume PDF + portfolio extraction with LLM
│   ├── matcher.py           # AI matching engine (Claude or GPT-4o)
│   ├── emailer.py           # Email digest sender (Gmail or SendGrid)
│   └── scrapers/
│       ├── base.py          # Base scraper with location/date filters
│       ├── getro_base.py    # Getro platform scraper (most VC boards)
│       ├── a16z.py          # Individual VC scrapers...
│       └── ...
├── data/
│   └── resume.pdf           # Your resume
├── .github/workflows/
│   └── daily-job-scan.yml   # GitHub Actions automation
├── requirements.txt
└── .env.example
```

## Cost Estimate

- **Claude/OpenAI API**: ~$0.02–0.10 per run (profile parsing + job matching)
- **SendGrid**: Free tier covers 100 emails/day
- **GitHub Actions**: Free for public repos

## License

MIT
