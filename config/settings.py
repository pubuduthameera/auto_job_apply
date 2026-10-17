"""
config/settings.py — load all config from .env or environment variables
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Sources:
    topjob: bool = True
    linkedin: bool = True


@dataclass
class Settings:
    # Job search
    job_role: str = "Software Engineer"
    topjob_pages: int = 3
    linkedin_pages: int = 2

    # LinkedIn (no login needed)
    linkedin_location: str = "Sri Lanka"

    # Groq API (free tier — get key at https://console.groq.com/keys)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Your details
    sender_name: str = "Your Name"
    sender_email: str = ""
    sender_password: str = ""   # Gmail app password recommended
    cv_path: str = "data/cv.pdf"
    cv_text: str = ""           # Plain-text version of your CV for AI context

    # App behaviour
    db_path: str = "data/jobs.db"
    review_mode: bool = True    # True = ask before each send; False = fully auto

    sources: Sources = field(default_factory=Sources)

    @classmethod
    def load(cls) -> "Settings":
        s = cls()

        s.job_role           = os.getenv("JOB_ROLE", s.job_role)
        s.topjob_pages       = int(os.getenv("TOPJOB_PAGES", s.topjob_pages))
        s.linkedin_pages     = int(os.getenv("LINKEDIN_PAGES", s.linkedin_pages))

        s.linkedin_location  = os.getenv("LINKEDIN_LOCATION", "Sri Lanka")

        s.groq_api_key       = os.getenv("GROQ_API_KEY", "")
        s.groq_model         = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        s.sender_name        = os.getenv("SENDER_NAME", s.sender_name)
        s.sender_email       = os.getenv("SENDER_EMAIL", "")
        s.sender_password    = os.getenv("SENDER_PASSWORD", "")
        s.cv_path            = os.getenv("CV_PATH", s.cv_path)
        s.review_mode        = os.getenv("REVIEW_MODE", "true").lower() == "true"

        s.sources = Sources(
            topjob   = os.getenv("SOURCE_TOPJOB", "true").lower() == "true",
            linkedin = os.getenv("SOURCE_LINKEDIN", "true").lower() == "true",
        )

        # Load CV plain text if a .txt version exists alongside the PDF
        txt_path = s.cv_path.replace(".pdf", ".txt")
        if os.path.exists(txt_path):
            with open(txt_path, "r") as f:
                s.cv_text = f.read()
        else:
            s.cv_text = "[CV text not loaded — add data/cv.txt for better cover letters]"

        s._validate()
        return s

    def _validate(self):
        missing = []
        if not self.groq_api_key:
            missing.append("GROQ_API_KEY")
        if not self.sender_email:
            missing.append("SENDER_EMAIL")
        if not self.sender_password:
            missing.append("SENDER_PASSWORD")
        if missing:
            raise EnvironmentError(
                f"Missing required env vars: {', '.join(missing)}\n"
                "Copy .env.example to .env and fill in the values."
            )
