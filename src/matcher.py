"""Job matching engine using Claude or OpenAI API."""

import json
import logging
import os
from typing import Optional

from .models import CandidateProfile, Job, MatchResult

logger = logging.getLogger(__name__)


class JobMatcher:
    """Matches jobs against candidate profiles using Claude or OpenAI API."""

    MATCH_PROMPT = """Analyze how well this candidate matches the job posting.

CANDIDATE PROFILE:
{profile}

JOB POSTING:
Title: {title}
Company: {company}
Location: {location}
Company Description: {company_description}
Qualifications/Requirements: {qualifications}
Full Description: {description}

MATCHING INSTRUCTIONS:
Prioritize the Qualifications/Requirements section above all else when evaluating fit.
This is the most reliable signal for what the role actually needs.
Use the Full Description for additional context on responsibilities and team.
Use the Company Description to assess industry and culture fit.

Evaluate the match based on these dimensions:
1. Skills & strengths required — Does the candidate have the technical skills, design tools, and strengths listed in the qualifications?
2. Years of experience & what they worked on — Does the candidate's experience level and the types of products they've built align with the stated requirements?
3. Who they worked with — Does the candidate have experience in the types of teams this role involves (cross-functional, engineering, data science, etc.)?
4. Who they worked for — Does the candidate's industry/company experience align (startups, enterprise, B2B, consumer, etc.)?
5. Results achieved — Do the candidate's project outcomes and problem-solving experience match what this role is looking for?

Also extract:
- A 1-2 sentence company bio: use the Company Description field if provided, otherwise infer from the job description (what the company does, its mission)
- The company's funding series if mentioned (e.g. "Series A", "Series B", "Series C", "Public")
- Specific words or short descriptions from the job posting that matched the candidate's profile

Return a JSON response with this exact structure:
{{
    "match_percentage": <0-100 integer>,
    "matching_skills": ["skill1", "skill2", ...],
    "missing_skills": ["skill1", "skill2", ...],
    "matched_keywords": ["keyword or phrase from job posting that matched", ...],
    "company_bio": "<1-2 sentence description of what the company does>",
    "company_series": "<funding series if mentioned, e.g. Series B, or empty string if not found>",
    "recommendation": "<2-3 sentence explanation of the match>"
}}

Be strict but fair. A 60%+ match should indicate a genuinely good fit.
Focus on product design, UX/UI design skills specifically.
Only return the JSON, no other text."""

    def __init__(self):
        """Initialize with available API key (OpenAI or Anthropic)."""
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

        if self.openai_key:
            self.provider = "openai"
            import openai
            self.client = openai.OpenAI(api_key=self.openai_key)
            logger.info("Using OpenAI API for matching")
        elif self.anthropic_key:
            self.provider = "anthropic"
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.anthropic_key)
            logger.info("Using Anthropic API for matching")
        else:
            raise ValueError("No API key found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY")

    def calculate_match(self, job: Job, profile: CandidateProfile) -> MatchResult:
        """Calculate match score between a job and candidate profile."""
        try:
            prompt = self.MATCH_PROMPT.format(
                profile=profile.full_profile[:10000],
                title=job.title,
                company=job.company,
                location=job.location,
                company_description=job.company_description[:2000] if job.company_description else "Not available",
                qualifications=job.qualifications[:4000] if job.qualifications else "Not available — refer to Full Description",
                description=job.description[:8000],
            )

            if self.provider == "openai":
                response_text = self._call_openai(prompt)
            else:
                response_text = self._call_anthropic(prompt)

            # Parse JSON response
            response_text = self._clean_json_response(response_text)
            result = json.loads(response_text)

            return MatchResult(
                job=job,
                match_percentage=int(result.get("match_percentage", 0)),
                matching_skills=result.get("matching_skills", []),
                missing_skills=result.get("missing_skills", []),
                recommendation=result.get("recommendation", ""),
                matched_keywords=result.get("matched_keywords", []),
                company_bio=result.get("company_bio", ""),
                company_series=result.get("company_series", ""),
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse API response as JSON: {e}")
            return MatchResult(
                job=job,
                match_percentage=0,
                recommendation="Error: Could not parse match result",
            )
        except Exception as e:
            logger.error(f"API error: {e}")
            return MatchResult(
                job=job,
                match_percentage=0,
                recommendation=f"Error: {e}",
            )

    def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API."""
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content.strip()

    def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic API."""
        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    def _clean_json_response(self, text: str) -> str:
        """Clean potential markdown code blocks from JSON response."""
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return text

    def match_jobs(
        self,
        jobs: list[Job],
        profile: CandidateProfile,
        min_match: int = 60,
    ) -> list[MatchResult]:
        """Match multiple jobs against a profile, filtering by minimum match percentage."""
        results = []

        for i, job in enumerate(jobs):
            logger.info(f"Matching job {i+1}/{len(jobs)}: {job.title} at {job.company}")

            result = self.calculate_match(job, profile)
            results.append(result)

            logger.info(f"  Match: {result.match_percentage}%")

        # Filter to good matches and sort by match percentage
        good_matches = [r for r in results if r.match_percentage >= min_match]
        good_matches.sort(key=lambda r: r.match_percentage, reverse=True)

        logger.info(f"Found {len(good_matches)} jobs matching >= {min_match}%")
        return good_matches
