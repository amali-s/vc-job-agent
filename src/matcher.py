"""Job matching engine using Anthropic Claude API."""

import json
import logging
import os
from typing import Optional

from .models import CandidateProfile, DimensionScores, Job, MatchResult

logger = logging.getLogger(__name__)


class JobMatcher:
    """Matches jobs against candidate profiles using Anthropic Claude API."""

    # Weights for each dimension (must sum to 1.0)
    DIMENSION_WEIGHTS = {
        "experience": 0.20,
        "work_type": 0.20,
        "skills_methods": 0.25,
        "product_type": 0.20,
        "deliverables": 0.15,
    }

    MATCH_PROMPT = """Score how well this candidate matches the job posting across 5 specific dimensions.

CANDIDATE PROFILE:
{profile}

JOB POSTING:
Title: {title}
Company: {company}
Location: {location}
Company Description: {company_description}
Qualifications/Requirements: {qualifications}
Full Description: {description}

SCORING INSTRUCTIONS:
Score each dimension independently from 0 to 100. Use the FULL range — do NOT default to 50. Think carefully about each one:

1. EXPERIENCE (0-100): Years of experience fit.
   Compare the candidate's years of professional experience against what the job requires.
   - 90-100: Exact match or slightly above (e.g. job asks 5+ years, candidate has 5-7)
   - 70-89: Close match (e.g. job asks 5+ years, candidate has 3-4 or 8+)
   - 40-69: Some gap (e.g. job asks 7+ years, candidate has 3-4)
   - 0-39: Major gap (e.g. job asks 10+ years, candidate has 2)
   If the job doesn't specify years, score based on seniority level implied.

2. WORK TYPE (0-100): Type of work alignment.
   Does the work the candidate has done (shown in resume and portfolio) match the type of work this role involves?
   Consider: strategic vs. execution, research-heavy vs. visual-heavy, 0-to-1 vs. optimization, consumer vs. enterprise UX patterns.
   - 90-100: Near-identical work types
   - 70-89: Substantial overlap with minor differences
   - 40-69: Some overlap but different emphasis
   - 0-39: Fundamentally different type of work

3. SKILLS & METHODS (0-100): Skills, tools, and methods match.
   Does the candidate use the specific skills, tools, and design methods the job requires?
   Compare: design tools (Figma, Sketch, etc.), research methods (user interviews, usability testing, A/B testing), processes (design sprints, design thinking, agile), technical skills (prototyping, HTML/CSS, data analysis).
   - 90-100: Has nearly all required skills and methods
   - 70-89: Has most required skills, missing 1-2 minor ones
   - 40-69: Has some required skills but missing several important ones
   - 0-39: Missing most of the required skills

4. PRODUCT TYPE (0-100): Product type and platform fit.
   Does the candidate's experience with product types match what this company builds?
   Product types: B2B, B2C, SaaS, marketplace, automation, AI/ML, developer tools, fintech, healthtech, etc.
   Platform types: mobile apps (iOS/Android), desktop applications, web applications (desktop browser), mobile web, cross-platform.
   - 90-100: Same product type AND platform
   - 70-89: Same product type OR same platform with related product type
   - 40-69: Related but not matching product or platform type
   - 0-39: Very different product and platform types

5. DELIVERABLES (0-100): Deliverables and output fit.
   Does the candidate's portfolio show the types of deliverables this role requires?
   Deliverable types: design systems, component libraries, dashboards, admin panels, RBAC/permissions, data visualizations, onboarding flows, trial/freemium experiences, settings/configuration pages, checkout flows, landing pages, mobile interfaces, complex forms, notification systems.
   - 90-100: Portfolio shows nearly identical deliverable types
   - 70-89: Portfolio shows most of the relevant deliverable types
   - 40-69: Portfolio shows some related deliverables
   - 0-39: Portfolio deliverables are very different from what's needed

IMPORTANT RULES:
- Score each dimension INDEPENDENTLY. A candidate can score 90 on skills but 30 on product type.
- Use the full 0-100 range. Scores of exactly 50 should be rare — commit to higher or lower.
- If the job posting lacks info for a dimension (e.g., no years mentioned), score based on what you can reasonably infer from the role level and description.
- Prioritize the Qualifications/Requirements section for skills and experience evidence.
- Focus on product design, UX/UI design skills specifically.

Also extract:
- A 1-2 sentence company bio from the Company Description field (or infer from job description)
- The company's funding series if mentioned (e.g. "Series A", "Series B", "Public")
- Specific keywords from the job posting that matched the candidate's profile

Return this exact JSON structure:
{{
    "scores": {{
        "experience": <0-100>,
        "work_type": <0-100>,
        "skills_methods": <0-100>,
        "product_type": <0-100>,
        "deliverables": <0-100>
    }},
    "matching_skills": ["skill1", "skill2", ...],
    "missing_skills": ["skill1", "skill2", ...],
    "matched_keywords": ["keyword or phrase from job posting", ...],
    "company_bio": "<1-2 sentence company description>",
    "company_series": "<funding series or empty string>",
    "recommendation": "<2-3 sentence explanation citing which dimensions scored high/low and why>"
}}

Only return the JSON, no other text."""

    def __init__(self):
        """Initialize with Anthropic API key."""
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

        if not self.anthropic_key:
            raise ValueError("No API key found. Set ANTHROPIC_API_KEY")

        import anthropic
        self.client = anthropic.Anthropic(api_key=self.anthropic_key)
        logger.info("Using Anthropic Claude API for matching")

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

            response_text = self._call_anthropic(prompt)

            # Parse JSON response
            response_text = self._clean_json_response(response_text)
            result = json.loads(response_text)

            # Extract dimension scores
            scores_data = result.get("scores", {})
            dimension_scores = DimensionScores(
                experience=int(scores_data.get("experience", 0)),
                work_type=int(scores_data.get("work_type", 0)),
                skills_methods=int(scores_data.get("skills_methods", 0)),
                product_type=int(scores_data.get("product_type", 0)),
                deliverables=int(scores_data.get("deliverables", 0)),
            )

            # Calculate weighted average from dimension scores
            match_percentage = self._compute_weighted_score(dimension_scores)

            return MatchResult(
                job=job,
                match_percentage=match_percentage,
                dimension_scores=dimension_scores,
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

    def _compute_weighted_score(self, scores: DimensionScores) -> int:
        """Compute overall match percentage as weighted average of dimension scores."""
        total = (
            scores.experience * self.DIMENSION_WEIGHTS["experience"]
            + scores.work_type * self.DIMENSION_WEIGHTS["work_type"]
            + scores.skills_methods * self.DIMENSION_WEIGHTS["skills_methods"]
            + scores.product_type * self.DIMENSION_WEIGHTS["product_type"]
            + scores.deliverables * self.DIMENSION_WEIGHTS["deliverables"]
        )
        return round(total)

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
