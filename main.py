"""
Auto Job Apply — main orchestrator
Run: python main.py
"""

import asyncio
import logging
from config.settings import Settings
from scrapers.topjob import scrape_topjob
from scrapers.linkedin import scrape_linkedin
from scrapers.title_extractor import normalize_job
from tracker.db import JobTracker
from ai.cover_letter import generate_cover_letter
from sender.email_sender import send_application

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


async def run():
    settings = Settings.load()
    tracker = JobTracker(settings.db_path)

    log.info("=== Starting job scan ===")

    # ── 1. Scrape jobs ────────────────────────────────────────────────────────
    jobs = []

    if settings.sources.topjob:
        log.info("Scraping TopJob.lk …")
        topjob_jobs = await scrape_topjob(settings.job_role, settings.topjob_pages)
        log.info(f"  Found {len(topjob_jobs)} jobs on TopJob.lk")
        jobs.extend(topjob_jobs)

    if settings.sources.linkedin:
        log.info("Scraping LinkedIn …")
        linkedin_jobs = await scrape_linkedin(
            settings.job_role,
            settings.linkedin_pages,
            location=settings.linkedin_location,
        )
        log.info(f"  Found {len(linkedin_jobs)} jobs on LinkedIn")
        jobs.extend(linkedin_jobs)

    # ── 1b. Normalize job titles ─────────────────────────────────────────────
    for job in jobs:
        normalize_job(job)
        if job.get("title_ambiguous"):
            log.debug(f"  Ambiguous title: {job['title']!r} → {job['canonical_title']!r}")

    # ── 2. Filter already-applied jobs ───────────────────────────────────────
    new_jobs = [j for j in jobs if not tracker.already_applied(j["id"])]
    log.info(f"{len(new_jobs)} new jobs (skipping {len(jobs) - len(new_jobs)} already seen)")

    if not new_jobs:
        log.info("Nothing new. Done.")
        return

    # ── 3. For each new job: generate cover letter → (review) → send ─────────
    for job in new_jobs:
        display_title = job.get("canonical_title", job["title"])
        log.info(f"\nProcessing: {display_title} @ {job['company']}")

        cover_letter = generate_cover_letter(
            job_title=display_title,
            company=job["company"],
            job_description=job["description"],
            cv_text=settings.cv_text,
            groq_api_key=settings.groq_api_key,
            model=settings.groq_model,
        )

        # Optional human review gate (set review_mode=True in settings)
        if settings.review_mode:
            print("\n" + "─" * 60)
            print(f"JOB:     {display_title} @ {job['company']}")
            print(f"URL:     {job.get('url', 'N/A')}")
            print(f"EMAIL:   {job.get('contact_email', 'N/A')}")
            print("\nCOVER LETTER PREVIEW:\n")
            print(cover_letter[:600] + " …" if len(cover_letter) > 600 else cover_letter)
            print("─" * 60)
            choice = input("Send this application? [y/N]: ").strip().lower()
            if choice != "y":
                log.info("Skipped by user.")
                tracker.mark(job["id"], status="skipped")
                continue

        # Send application email
        if job.get("contact_email"):
            success = send_application(
                to_email=job["contact_email"],
                job_title=display_title,
                company=job["company"],
                cover_letter=cover_letter,
                cv_path=settings.cv_path,
                sender_email=settings.sender_email,
                sender_password=settings.sender_password,
                sender_name=settings.sender_name,
            )
            status = "applied" if success else "error"
        else:
            log.warning(f"  No contact email found — marking as 'no_email'")
            status = "no_email"

        tracker.mark(job["id"], status=status, job=job)
        log.info(f"  Status: {status}")

    log.info("\n=== Done. ===")
    tracker.print_summary()


if __name__ == "__main__":
    asyncio.run(run())
