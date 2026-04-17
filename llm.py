"""
llm.py — Gemini wrapper for all AI tasks in the job pipeline.

All AI calls go through this module. To swap models, change GEMINI_MODEL in .env.
Requires: pip install google-genai python-dotenv
"""
import json
import os

from dotenv import load_dotenv
import google.genai as genai

load_dotenv()

MODEL       = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
SCORE_MODEL = os.environ.get("GEMINI_SCORE_MODEL", "gemini-2.5-flash")

def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set.\n"
            "Set it in the app's Settings tab or in the .env file.\n"
            "Get a free key at https://aistudio.google.com/app/apikey"
        )
    return key


def _call(prompt: str, model_name: str = MODEL) -> str:
    """Send a prompt and return the response text."""
    with genai.Client(api_key=_api_key()) as client:
        response = client.models.generate_content(model=model_name, contents=prompt)
    return response.text.strip()


def _parse_json(text: str) -> dict:
    """Extract JSON object from a response that may contain markdown fences."""
    if "```" in text:
        text = text.split("```")[1].lstrip("json").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    return json.loads(text[start:end])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_job(title: str, company: str, location: str,
              jd_text: str, cv_text: str) -> dict:
    """Score a job against the CV.

    Returns dict with keys:
      score        (int 1-10)
      reason       (str, max 15 words)
      role_profile (int 1-3)
    """
    prompt = f"""Score this job against the CV. Reply with JSON only - no explanation, no markdown.

CV (excerpt):
{cv_text[:2000]}

Job: {title} at {company} ({location})
Job Description:
{jd_text[:2000]}

JSON format:
{{"score": <integer 1-10>, "reason": "<max 15 words>", "role_profile": <1, 2, or 3>}}

role_profile key:
1 = Cybersecurity/GRC  (ISO 21434, UN R155, CSMS, GRC, ISMS, compliance, risk)
2 = Product Owner      (Product Owner, PO, roadmap, backlog, agile, Scrum, SAFe, MVP)
3 = Requirements/BA    (requirements, ASPICE, ALM, Codebeamer, systems engineering, BA)

Pick the profile whose keywords dominate the JD."""

    result = _parse_json(_call(prompt, model_name=SCORE_MODEL))
    return {
        "score": int(result["score"]),
        "reason": str(result.get("reason", ""))[:200],
        "role_profile": int(result.get("role_profile", 1)),
    }


def tailor_cv(title: str, company: str, jd_text: str,
              cv_text: str, certs: list[str],
              profile: dict, role_profile: int) -> str:
    """Tailor master_cv.md for a specific job."""
    cert_block = "\n".join(f"- {c}" for c in certs) if certs else "(no certs in database)"

    contact_parts = [
        profile.get("location", ""),
        profile.get("phone", ""),
        profile.get("email", ""),
        profile.get("linkedin_url", ""),
    ]
    contact_line = " | ".join(p for p in contact_parts if p)

    headlines = {
        1: "Automotive Cybersecurity & GRC Professional",
        2: "Product Owner | Agile Product Development",
        3: "Requirements Engineer | Business Analyst",
    }
    headline = headlines.get(role_profile, "")
    full_name = profile.get("full_name", "[Your Name]")

    prompt = f"""You are an expert CV writer. Tailor the CV below for the target job.
No hallucination - only rephrase what is already in the source CV.

CANDIDATE:
{full_name}
{contact_line}

SOURCE CV:
{cv_text}

RELEVANT CERTIFICATIONS (use exactly these, most relevant first):
{cert_block}

TARGET JOB: {title} at {company}
JOB DESCRIPTION:
{jd_text[:4000]}

OUTPUT RULES:
- Return ONLY the markdown CV - no preamble, no explanation
- Summary: rewrite completely (max 3 sentences), mirror key JD terms
- Experience: reorder bullets within each job to put most JD-relevant first
- Never add bullets or invent achievements
- Never drop any job entry - include ALL experience from the source CV
- Certifications section: use exactly the cert lines provided above
- Skills: reorder groups to match the job priority, keep all items within each group

OUTPUT FORMAT (generator.py depends on this structure):

{full_name}
{contact_line}
{headline}

## Professional Summary

[2-3 sentences, mirroring JD keywords]

## Professional Experience

[COMPANY] | [LOCATION]
[POSITION] | [START] - [END]
- [most JD-relevant bullet first]
- [bullet]
[repeat for ALL jobs]

## Education & Professional Development

[degree lines]

## Certifications

{cert_block}

## Technical Skills

[SKILL GROUP]: skill, skill, skill
[repeat for all groups]

## Languages

[language lines]

[City, Month Year]"""

    return _call(prompt)


def build_base_cv(profile_num: int, language: str,
                  cv_text: str, certs: list[str],
                  focus_instructions: str,
                  lang_instructions: str) -> str:
    """Generate a pre-built base CV for a given profile and language."""
    cert_block = "\n".join(f"- {c}" for c in certs) if certs else "(no certs in database)"

    prompt = f"""You are an expert CV writer. Produce a tailored CV in markdown format.

SOURCE CV (do not invent anything not present here):
{cv_text}

RELEVANT CERTIFICATIONS:
{cert_block}

LANGUAGE & FORMAT INSTRUCTIONS:
{lang_instructions}

ROLE FOCUS INSTRUCTIONS:
{focus_instructions}

GENERAL RULES:
- Include ALL job entries from the source CV - never drop any role
- Never invent skills, experience, or certifications not in the source
- No photo, no date of birth
- Contact line format: City - email - LinkedIn - website (single line after the name heading)
- Keep bullet points concise (one line each)
- Certifications section: list the relevant certs provided above

OUTPUT: Return the complete CV in markdown only. No preamble, no explanation."""

    return _call(prompt)
