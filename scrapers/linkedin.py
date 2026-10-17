"""
scrapers/linkedin.py — scrape LinkedIn jobs using linkedin-jobs-scraper (Node.js)

No login required. Uses the `linkedin-jobs-scraper` npm package under the hood
via a Node.js subprocess.

Prerequisites (run once in your project root):
    npm install linkedin-jobs-scraper
"""

import re
import json
import hashlib
import logging
import asyncio
import os
import tempfile

log = logging.getLogger(__name__)

# Node.js script template injected with search params at runtime
NODE_SCRIPT = """
const {{ LinkedinScraper, events, Strategies }} = require('linkedin-jobs-scraper');

(async () => {{
    const scraper = new LinkedinScraper({{
        headless: true,
        slowMo: 200,
        args: ['--no-sandbox'],
    }});

    const jobs = [];

    scraper.on(events.scraper.data, (data) => {{
        jobs.push({{
            id:          'linkedin_' + Buffer.from(data.jobId || data.link || '').toString('base64').slice(0, 12),
            source:      'linkedin',
            url:         data.link        || '',
            title:       data.title       || '',
            company:     data.company     || '',
            location:    data.location    || '',
            description: (data.description || '').slice(0, 4000),
            contact_email: (data.description || '').match(/[a-zA-Z0-9._%+\\-]+@[a-zA-Z0-9.\\-]+\\.[a-zA-Z]{{2,}}/)?.[0] || null,
        }});
    }});

    scraper.on(events.scraper.error,   (err)  => process.stderr.write('ERR: ' + String(err) + '\\n'));
    scraper.on(events.scraper.invalid, (link) => process.stderr.write('INVALID: ' + link + '\\n'));

    await scraper.run([
        {{
            query:   '{role}',
            options: {{
                locations:  ['{location}'],
                limit:      {limit},
                filters: {{
                    relevance: 'R',
                    time:      'r604800',
                }},
            }},
        }},
    ]);

    await scraper.close();
    process.stdout.write(JSON.stringify(jobs));
}})();
"""


async def scrape_linkedin(
    job_role: str,
    pages: int = 2,
    email: str = "",          # unused — no login needed, kept for API compat
    password: str = "",       # unused — no login needed, kept for API compat
    location: str = "Sri Lanka",
) -> list[dict]:

    limit = pages * 25        # ~25 results per "page"

    script = NODE_SCRIPT.format(
        role=job_role.replace("'", "\\'"),
        location=location.replace("'", "\\'"),
        limit=limit,
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, prefix="lk_scraper_"
    ) as f:
        f.write(script)
        script_path = f.name

    try:
        log.info(f"Running linkedin-jobs-scraper (limit={limit}, location={location}) …")
        proc = await asyncio.create_subprocess_exec(
            "node", script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=_find_node_modules_root(),
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)

        if stderr:
            for line in stderr.decode().splitlines():
                if line.strip():
                    log.warning(f"[node] {line}")

        if proc.returncode != 0:
            log.error(f"Node process exited with code {proc.returncode}")
            return []

        raw = stdout.decode().strip()
        if not raw:
            log.warning("linkedin-jobs-scraper returned no output")
            return []

        jobs: list[dict] = json.loads(raw)
        log.info(f"  linkedin-jobs-scraper returned {len(jobs)} jobs")
        return jobs

    except asyncio.TimeoutError:
        log.error("linkedin-jobs-scraper timed out after 180s")
        return []
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse scraper output: {e}")
        return []
    except FileNotFoundError:
        log.error(
            "Node.js not found — install from https://nodejs.org\n"
            "Then run:  npm install linkedin-jobs-scraper"
        )
        return []
    finally:
        os.unlink(script_path)


def _find_node_modules_root() -> str:
    """Walk up from CWD looking for a node_modules folder."""
    current = os.getcwd()
    for _ in range(5):
        if os.path.isdir(os.path.join(current, "node_modules")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.getcwd()
