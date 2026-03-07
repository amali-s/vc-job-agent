# Agent vs. ATS: Job-Candidate Fit Evaluation Comparison

A structured comparison of how this VC Job Agent evaluates job-candidate fit versus how a traditional Applicant Tracking System (ATS) resume scanner works.

---

## 1. Scoring Methodology

### This Agent
- **Approach**: Holistic LLM-based evaluation across 5 weighted dimensions
- **Score range**: 0-100% match percentage
- **How it works**: The full candidate profile (resume + portfolio + structured extraction) is evaluated against the full job posting by Claude, which produces a single match score with explanations
- **Threshold**: Configurable minimum (default 60%) — only strong matches surface

### Traditional ATS
- **Approach**: Keyword frequency and pattern matching algorithms
- **Score range**: Varies by system (often 0-100 or pass/fail)
- **How it works**: Resume text is parsed into fields (education, experience, skills), then compared against job requirement keywords using exact/fuzzy string matching
- **Threshold**: Typically set per-role by recruiters (often 70-80% keyword match)

---

## 2. Signals Each System Uses

### This Agent

| Signal | How It's Used |
|--------|---------------|
| Technical skills (from resume) | Matched against job qualifications via semantic understanding |
| Portfolio case studies | Problems solved, design methods, and outcomes are extracted and compared |
| Years of experience | Compared to job's stated experience requirements |
| Product types built | SaaS/consumer/mobile/enterprise alignment checked |
| Team collaboration history | Cross-functional, startup, enterprise team experience assessed |
| Industry background | B2B/consumer/health/fintech context matching |
| Visual & interaction skills | Design tool proficiency and visual skill alignment |
| Project outcomes | Results achieved compared to what the role seeks |
| Company context | Funding stage, mission, and culture signals extracted from posting |

### Traditional ATS

| Signal | How It's Used |
|--------|---------------|
| Keywords in resume | Exact/fuzzy match against job description keywords |
| Job titles held | Pattern match against required titles |
| Education credentials | Degree type and institution matched against requirements |
| Years at each role | Parsed to estimate total experience |
| Skills section | Keyword list compared to required skills list |
| Certifications | Exact match against listed certifications |
| File format & structure | Can reject based on unparseable formats (images, tables, columns) |

---

## 3. Keyword Matching vs. Semantic Matching

### Keyword Matching (ATS)
- **Exact match**: "Figma" in resume matches "Figma" in job posting
- **Fuzzy match**: "UI/UX" might match "UX/UI" depending on the system
- **Synonym gaps**: "user research" may NOT match "customer interviews" — same skill, different words
- **No context**: "5 years of React" and "used React once in a hackathon" score identically
- **Keyword stuffing**: Candidates can game the system by copying keywords from the job posting

### Semantic Matching (This Agent)
- **Contextual understanding**: "Led a redesign of the onboarding flow that increased activation by 30%" is understood as product design experience with measurable outcomes
- **Skill inference**: Portfolio showing complex data visualizations implies proficiency even if "D3.js" isn't explicitly listed
- **Equivalent terms**: "user research", "customer discovery", "usability testing", and "user interviews" are understood as related competencies
- **Experience quality**: Distinguishes between "used Figma" and "designed and maintained a design system in Figma for a team of 20"
- **Cannot be gamed**: Keyword stuffing doesn't help because the LLM evaluates actual evidence of competency

---

## 4. What Each System Misses

### What the ATS Misses

| Blind Spot | Why |
|-----------|-----|
| **Portfolio quality** | ATS cannot visit URLs, view designs, or assess visual work |
| **Career narrative** | Cannot understand growth trajectory or career pivots |
| **Soft skills in context** | "Led cross-functional team" is just keywords, not evidence |
| **Transferable skills** | A game designer moving to product design may be rejected despite relevant skills |
| **Project complexity** | Cannot distinguish simple CRUD app design from complex enterprise SaaS |
| **Non-standard formats** | Rejects creative resumes, multi-column layouts, PDF portfolios |
| **Cultural fit signals** | Company values alignment is invisible to keyword matching |
| **Outcome quality** | "Improved conversion" and "Improved conversion by 340%" are identical strings |

### What This Agent Misses

| Blind Spot | Why |
|-----------|-----|
| **Credential verification** | Cannot verify claimed degrees, certifications, or employment dates |
| **Reference quality** | Has no access to references or background checks |
| **Interview performance** | Cannot assess communication, whiteboarding, or presentation skills |
| **Real-time portfolio rendering** | Reads portfolio as text, cannot interact with prototypes or animations |
| **Salary negotiation signals** | Cannot infer salary expectations from current compensation |
| **Non-public information** | No access to internal hiring priorities, team dynamics, or budget constraints |
| **Recency bias** | May over-weight recent portfolio pieces vs. cumulative career experience |
| **LLM variability** | Same candidate-job pair may score slightly differently across runs |

---

## 5. Advantages and Disadvantages

### Where This Agent Has an Advantage

1. **Portfolio analysis**: This agent actually reads portfolio websites and case studies — ATS cannot. For design roles, this is arguably the most important signal.

2. **Semantic understanding**: "Built and shipped a design system used by 50+ engineers" is meaningfully different from "design system" as a keyword. The agent understands this.

3. **Multi-dimensional scoring**: Instead of a flat keyword count, the agent evaluates skills, experience, team fit, industry alignment, and outcomes as separate dimensions that inform a holistic score.

4. **Explanation transparency**: Each match includes a recommendation explaining *why* the score is what it is — recruiters see reasoning, not just a number.

5. **Qualifications prioritization**: The agent specifically extracts and prioritizes the Requirements/Qualifications section of job postings, which is the most reliable signal for what a role actually needs. ATS treats all text equally.

6. **Company context extraction**: Automatically pulls company bios, funding stage, and mission — giving candidates useful context that ATS doesn't surface.

7. **Cross-run intelligence**: Tracks rank changes and match deltas across days, showing trending jobs and score movements that a one-shot ATS scan cannot.

### Where This Agent Has a Disadvantage

1. **Scale**: ATS processes thousands of applicants per role instantly. This agent evaluates one candidate against many jobs — it's a candidate-side tool, not a recruiter-side tool.

2. **Structured data parsing**: ATS is better at extracting structured fields (dates, employers, degree names) from resumes into database records. The agent treats resume text as unstructured input.

3. **Compliance**: ATS systems are built for EEOC compliance, GDPR, and audit trails. This agent has no compliance framework.

4. **Integrations**: ATS connects to HRIS, calendaring, offer letter systems, and background check services. This agent only outputs email digests.

5. **Cost per evaluation**: Each job match requires an LLM API call (~$0.01-0.03). ATS keyword matching is essentially free per-candidate after initial setup.

6. **Determinism**: ATS produces identical scores for identical inputs. LLM-based matching may have slight variance between runs.

7. **Recruiter workflow**: ATS is designed for recruiters to manage pipelines, schedule interviews, and collaborate. This agent serves the candidate only.

---

## 6. Summary Matrix

| Dimension | This Agent | Traditional ATS |
|-----------|-----------|-----------------|
| **Matching method** | LLM semantic evaluation | Keyword frequency matching |
| **Portfolio analysis** | Yes (scrapes + analyzes) | No |
| **Scoring transparency** | Explains reasoning | Opaque score |
| **Skill synonyms** | Handles naturally | Requires manual synonym configuration |
| **Gaming resistance** | High (evaluates evidence) | Low (keyword stuffing works) |
| **Scale** | ~50-100 jobs/run | Thousands of applicants/role |
| **Cost per match** | ~$0.01-0.03 (API) | Near-zero (algorithmic) |
| **Compliance** | None | EEOC/GDPR built-in |
| **Best for** | Candidates finding matches | Recruiters filtering applicants |
| **Determinism** | Slight variance possible | Deterministic |
| **History tracking** | Rank changes across days | Application status tracking |

---

## Conclusion

This agent and traditional ATS systems solve fundamentally different problems from opposite sides of the hiring equation. The ATS helps recruiters efficiently filter high volumes of applicants using structured data. This agent helps a candidate find the best-fitting roles across many job boards using deep semantic understanding of their complete profile — resume, portfolio, and structured skills — evaluated against the full context of each job posting. They are complementary, not competitive: a candidate can use this agent to find roles where they're a strong fit, then optimize their application to also pass the ATS on the other side.
