"""
diagnose.py — run this to debug scraper issues before running main.py

Usage:
    python diagnose.py
"""

import asyncio
import subprocess
import sys
import os

async def check_topjob():
    print("\n── TopJob.lk diagnosis ──────────────────────────────────")
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌  playwright not installed — run: pip install playwright && playwright install chromium")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        url = "https://www.topjobs.lk/applicant/vacancybyfunctionalarea.jsp?keyword=Software+Engineer"
        print(f"Fetching: {url}")
        try:
            await page.goto(url, timeout=30_000)
            await page.wait_for_load_state("domcontentloaded")
            title = await page.title()
            print(f"✅  Page loaded — title: {title!r}")

            # Count all links
            all_links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            job_links = [l for l in all_links if "vacancy" in l.lower() or "job" in l.lower()]
            print(f"   Total <a> tags: {len(all_links)}")
            print(f"   Links with 'vacancy' or 'job' in URL: {len(job_links)}")
            if job_links:
                print(f"   Sample links:")
                for l in job_links[:5]:
                    print(f"     {l}")

            # Save HTML for inspection
            os.makedirs("data", exist_ok=True)
            html = await page.content()
            with open("data/debug_topjob_search.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"   HTML saved to data/debug_topjob_search.html")
            print(f"   Open it in a browser and inspect the job card elements")

        except Exception as e:
            print(f"❌  Error: {e}")
        finally:
            await browser.close()


def check_linkedin_node():
    print("\n── LinkedIn / Node.js diagnosis ─────────────────────────")

    # Check node
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        print(f"✅  Node.js: {result.stdout.strip()}")
    except FileNotFoundError:
        print("❌  Node.js not found — install from https://nodejs.org")
        return

    # Check npm package
    nm_path = os.path.join(os.getcwd(), "node_modules", "linkedin-jobs-scraper")
    if os.path.isdir(nm_path):
        print(f"✅  linkedin-jobs-scraper installed at {nm_path}")
    else:
        print("❌  linkedin-jobs-scraper not found")
        print("    Run: npm install linkedin-jobs-scraper")
        return

    # Try running a minimal Node script to surface the real error
    test_script = """
const { LinkedinScraper, events } = require('linkedin-jobs-scraper');
console.log('linkedin-jobs-scraper loaded OK, version:', require('linkedin-jobs-scraper/package.json').version);
process.exit(0);
"""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write(test_script)
        script_path = f.name

    result = subprocess.run(["node", script_path], capture_output=True, text=True)
    os.unlink(script_path)

    if result.returncode == 0:
        print(f"✅  {result.stdout.strip()}")
    else:
        print(f"❌  Node error:\n{result.stderr.strip()}")
        print("\n    Common fixes:")
        print("    1. Delete node_modules and reinstall: rm -rf node_modules && npm install linkedin-jobs-scraper")
        print("    2. Make sure you're running Python from the same directory as node_modules/")

    # Try a real small scrape
    print("\n   Running a quick 3-job scrape test …")
    scrape_test = """
const { LinkedinScraper, events } = require('linkedin-jobs-scraper');
(async () => {
    const scraper = new LinkedinScraper({ headless: true, args: ['--no-sandbox'] });
    const jobs = [];
    scraper.on(events.scraper.data, d => jobs.push(d.title));
    scraper.on(events.scraper.error, e => process.stderr.write('ERR: ' + String(e) + '\\n'));
    await scraper.run([{ query: 'Software Engineer', options: { locations: ['Sri Lanka'], limit: 3 } }]);
    await scraper.close();
    console.log('Scraped titles:', JSON.stringify(jobs));
})();
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write(scrape_test)
        script_path = f.name

    result = subprocess.run(["node", script_path], capture_output=True, text=True, timeout=60)
    os.unlink(script_path)

    if result.stdout:
        print(f"✅  {result.stdout.strip()}")
    if result.stderr:
        print(f"⚠️  stderr:\n{result.stderr.strip()[:800]}")


async def main():
    print("=" * 55)
    print("  Auto Job Apply — Scraper Diagnostics")
    print("=" * 55)
    await check_topjob()
    check_linkedin_node()
    print("\n── Done ─────────────────────────────────────────────────\n")


if __name__ == "__main__":
    asyncio.run(main())
