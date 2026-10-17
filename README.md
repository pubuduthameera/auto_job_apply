# Auto Job Apply

Automatically scan TopJob.lk and LinkedIn for jobs, generate tailored cover letters with Claude AI, and send applications by email.

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
playwright install chromium

# LinkedIn scraper (Node.js package — no login required)
npm install linkedin-jobs-scraper
```

### 2. Configure your environment
```bash
cp .env.example .env
# Edit .env and fill in all values
```

### 3. Add your CV
- Place your CV as `data/cv.pdf`
- Create `data/cv.txt` — a plain-text version of your CV (Claude uses this to write better cover letters)

### 4. Run
```bash
python main.py
```

---

## How it works

```
TopJob.lk ──┐
             ├─► Filter new jobs ─► Claude AI cover letter ─► Review? ─► Send email
LinkedIn ───┘                                                              + track in DB
```

1. **Scanner** — Playwright scrapes job listings from TopJob.lk and/or LinkedIn
2. **Deduplication** — SQLite DB tracks every job seen; won't apply twice
3. **Cover letter** — Claude API generates a tailored letter per job using your CV + JD
4. **Review gate** — With `REVIEW_MODE=true`, you approve each application before it sends
5. **Email** — Sends via Gmail SMTP with your CV attached as PDF

---

## LinkedIn note

LinkedIn scraping uses the [`linkedin-jobs-scraper`](https://www.npmjs.com/package/linkedin-jobs-scraper)
npm package — **no account, no login, no session management needed**.
It runs as a Node.js subprocess called from Python, returns results as JSON, and
handles pagination and rate-limiting internally.

Set `LINKEDIN_LOCATION` in `.env` to filter by region (default: `Sri Lanka`).

---

## File structure

```
auto_job_apply/
├── main.py                 # Orchestrator — run this
├── .env.example            # Copy to .env and fill in
├── requirements.txt
├── data/
│   ├── cv.pdf              # Your CV (add this)
│   ├── cv.txt              # Plain-text CV for AI context (add this)
│   ├── jobs.db             # SQLite tracker (auto-created)
│   └── linkedin_session.json  # Saved LinkedIn session (auto-created)
├── config/
│   └── settings.py         # Loads .env settings
├── scrapers/
│   ├── topjob.py           # TopJob.lk scraper
│   └── linkedin.py         # LinkedIn scraper
├── ai/
│   └── cover_letter.py     # Claude API cover letter generator
├── sender/
│   └── email_sender.py     # Gmail SMTP sender
└── tracker/
    └── db.py               # SQLite job tracker
```

---

## Scheduling (run daily automatically)

**macOS/Linux cron** — run every morning at 8am:
```
0 8 * * * cd /path/to/auto_job_apply && python main.py >> logs/run.log 2>&1
```

**GitHub Actions** — free cloud scheduling (see `.github/workflows/` if added).

---

## Gmail App Password setup

1. Go to https://myaccount.google.com/apppasswords
2. Create an app password for "Mail"
3. Use that 16-character password as `SENDER_PASSWORD` in `.env`

Regular Gmail password won't work — Google requires App Passwords for SMTP.
