"""
scrapers/topjob.py — scrape jobs from TopJob.lk
Uses Playwright. Robust selector approach: tries multiple candidates and
falls back gracefully. Set DEBUG_HTML=true in env to dump page source.
"""

import re
import os
import hashlib
import logging
from playwright.async_api import async_playwright, Browser

log = logging.getLogger(__name__)

BASE_URL = "https://www.topjobs.lk"

# Try these in order for the search results page — job card links
LINK_SELECTORS = [
    "a[href*='ViewJobVacancy']",
    "a[href*='vacancy']",
    "a[href*='job']",
    ".job-listing a",
    "table a[href]",
]

# Try these for job title on detail page
TITLE_SELECTORS = [
    "h1", "h2",
    ".vacancy-title", ".job-title", ".position-title",
    "td.jobtitle", "font[size='4']",
]

# Try these for company name
COMPANY_SELECTORS = [
    ".company-name", ".employer-name", ".org-name",
    "td.companyname", "a[href*='employer']",
]

# Try these for job description block
DESC_SELECTORS = [
    ".job-description", ".vacancy-description", "#jobDesc",
    ".jd", "td.jobdetails", "div.jobdetails",
]


def _make_id(url: str) -> str:
    return "topjob_" + hashlib.md5(url.encode()).hexdigest()[:12]


def _extract_email(text: str) -> str | None:
    match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    return match.group(0) if match else None


async def _try_selectors(page, selectors: list[str]) -> str:
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if text:
                    return text
        except Exception:
            continue
    return ""


async def scrape_topjob(job_role: str, pages: int = 3) -> list[dict]:
    jobs = []
    debug = os.getenv("DEBUG_HTML", "false").lower() == "true"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/122.0.0.0 Safari/537.36"
        )

        keyword = job_role.replace(" ", "+")
        search_url = f"{BASE_URL}/applicant/vacancy/SearchVacancy.jsp?keyword={keyword}"

        for page_num in range(1, pages + 1):
            url = search_url + (f"&page={page_num}" if page_num > 1 else "")
            log.info(f"  TopJob page {page_num}: {url}")

            try:
                await page.goto(url, timeout=30_000)
                await page.wait_for_load_state("domcontentloaded", timeout=15_000)
            except Exception as e:
                log.warning(f"  Failed to load page {page_num}: {e}")
                break

            # Debug: dump HTML so you can inspect real selectors
            if debug:
                html = await page.content()
                debug_path = f"data/debug_topjob_page{page_num}.html"
                os.makedirs("data", exist_ok=True)
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(html)
                log.info(f"  HTML saved to {debug_path}")

            # Collect all job links on this page
            links = []
            for sel in LINK_SELECTORS:
                try:
                    found = await page.eval_on_selector_all(
                        sel, "els => els.map(e => e.href)"
                    )
                    # Filter out duplicates and non-detail links
                    found = [
                        l for l in found
                        if l.startswith("http") and l not in links
                    ]
                    links.extend(found)
                    if found:
                        log.debug(f"  Selector '{sel}' found {len(found)} links")
                        break
                except Exception:
                    continue

            # Deduplicate
            links = list(dict.fromkeys(links))
            log.info(f"  Found {len(links)} job links on page {page_num}")

            if not links:
                log.warning(
                    "  No links found. Try running with DEBUG_HTML=true to inspect the page:\n"
                    "    DEBUG_HTML=true python main.py"
                )
                break

            for link in links:
                try:
                    job = await _scrape_job_detail(browser, link, debug=debug)
                    if job and job["title"]:
                        jobs.append(job)
                        log.debug(f"  + {job['title']} @ {job['company']}")
                except Exception as e:
                    log.warning(f"  Detail error {link}: {e}")

        await browser.close()

    return jobs


async def _scrape_job_detail(browser: Browser, url: str, debug: bool = False) -> dict | None:
    page = await browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/122.0.0.0 Safari/537.36"
    )
    try:
        await page.goto(url, timeout=20_000)
        await page.wait_for_load_state("domcontentloaded")

        if debug:
            html = await page.content()
            slug = _make_id(url)
            debug_path = f"data/debug_topjob_detail_{slug}.html"
            os.makedirs("data", exist_ok=True)
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)

        title   = await _try_selectors(page, TITLE_SELECTORS)
        company = await _try_selectors(page, COMPANY_SELECTORS)

        # Description: try specific selectors first, then full body
        description = await _try_selectors(page, DESC_SELECTORS)
        if not description:
            description = (await page.inner_text("body"))[:4000]

        email = _extract_email(description) or _extract_email(
            await page.inner_text("body")
        )

        return {
            "id": _make_id(url),
            "source": "topjob",
            "url": url,
            "title": title,
            "company": company,
            "description": description.strip(),
            "contact_email": email,
        }
    except Exception as e:
        log.warning(f"  Detail page error {url}: {e}")
        return None
    finally:
        await page.close()
