# VC Product Designer Job Agent

An AI-powered job agent that scrapes product designer positions from 15 VC portfolio job boards, matches them against your resume/portfolio using Claude API, and sends daily email digests.

## Features

- **15 VC Job Boards**: Scrapes job listings from a16z, Sequoia, General Catalyst, Index Ventures, Greylock, Kleiner Perkins, Accel, Contrary, Pear VC, Battery Ventures, NEA, Antler, LSVP, and Bessemer
- **AI Matching**: Uses Claude API to semantically match jobs to your profile
- **Daily Digests**: Automated email delivery via SendGrid at 5:00 PM CST
- **Portfolio Integration**: Parses both your resume PDF and portfolio website

## Setup

### 1. Clone and Install Dependencies

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

Required environment variables:
- `ANTHROPIC_API_KEY`: Your Claude API key
- `SENDGRID_API_KEY`: Your SendGrid API key
- `EMAIL_TO`: Your email address for receiving digests
- `EMAIL_FROM`: Verified SendGrid sender email

### 3. Add Your Resume

Place your resume PDF at `data/resume.pdf`

### 4. Run Locally

```bash
python -m src.main
```

For dry run (no email sent):
```bash
python -m src.main --dry-run
```

## GitHub Actions Setup

The agent runs automatically via GitHub Actions at 5:00 PM CST daily.

### Required Secrets

Add these secrets in your GitHub repository settings:

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key for matching |
| `SENDGRID_API_KEY` | SendGrid API key for emails |
| `EMAIL_TO` | Your email address |
| `EMAIL_FROM` | Verified SendGrid sender |

### Manual Trigger

You can also trigger the workflow manually from the Actions tab using `workflow_dispatch`.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub Actions (Daily 5PM CST)              │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Scrapers   │───▶│   Matcher    │───▶│   Emailer    │      │
│  │  (15 sites)  │    │ (Claude API) │    │  (SendGrid)  │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

## Cost Estimate

- **Claude API**: ~$0.01-0.05 per job match
- **SendGrid**: Free tier (100 emails/day)
- **GitHub Actions**: Free for public repos

## License

MIT
