"""
ai/cover_letter.py — generate a tailored cover letter using Groq API
Groq is free to sign up, has a generous free tier, and is very fast.
Get your key at: https://console.groq.com/keys
"""

import logging
from groq import Groq

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert career coach and professional cover letter writer.
Your task is to write a concise, compelling cover letter that:
- Is tailored specifically to the job description provided
- Highlights the most relevant skills and experience from the candidate's CV
- Sounds natural, confident, and human — not generic or AI-generated
- Is 3–4 short paragraphs (around 250–320 words)
- Does NOT use clichés like "I am writing to express my interest" or "I am a passionate..."
- Ends with a clear call to action

Return ONLY the cover letter text. No subject line, no metadata."""


def generate_cover_letter(
    job_title: str,
    company: str,
    job_description: str,
    cv_text: str,
    groq_api_key: str,
    model: str = "llama-3.3-70b-versatile",
) -> str:
    client = Groq(api_key=groq_api_key)

    user_prompt = f"""
Please write a cover letter for this job application.

JOB TITLE: {job_title}
COMPANY: {company}

JOB DESCRIPTION:
{job_description[:3000]}

MY CV / BACKGROUND:
{cv_text[:3000]}

Write the cover letter now:
""".strip()

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=1000,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
        )
        cover_letter = response.choices[0].message.content.strip()
        log.info(f"Cover letter generated ({len(cover_letter)} chars)")
        return cover_letter

    except Exception as e:
        log.error(f"Cover letter generation failed: {e}")
        return _fallback_cover_letter(job_title, company)


def _fallback_cover_letter(job_title: str, company: str) -> str:
    return (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to apply for the {job_title} position at {company}. "
        f"I believe my background and skills make me a strong candidate for this role.\n\n"
        f"I would welcome the opportunity to discuss my application further.\n\n"
        f"Kind regards"
    )
