# Job Title Extraction & Normalization — Design Document

## 1. Problem Statement

Job listings scraped from TopJob.lk, LinkedIn, and other sources contain raw title
strings in varying formats: abbreviations ("Sr. SWE"), inverted forms
("Engineer, Software"), mixed-case noise, HTML artifacts, and non-English tokens.
We need a deterministic, configurable pipeline that extracts clean canonical titles
with confidence metadata so downstream logic (cover-letter generation, filtering,
deduplication) operates on reliable data.

---

## 2. Input Formats & Typical Noise

| Source    | Format            | Noise examples                                           |
|-----------|-------------------|----------------------------------------------------------|
| TopJob.lk | HTML (Playwright) | `<font size='4'>  Sr. Software Eng.  </font>`            |
| LinkedIn  | JSON via Node.js  | `"title": "Engineer, Software (Remote — Sri Lanka)"`     |
| Plain text| Pasted JD / email | `"""Looking for a Sr SWE / Full Stack Dev — $120k"""`    |

Common noise patterns:
- Leading/trailing whitespace and punctuation
- HTML tags and entities (`&amp;`, `<br>`, `\n`)
- Location / salary / remote tags appended to title
- Abbreviations: `Sr.`, `Jr.`, `Mgr.`, `Eng.`, `SWE`, `PM`, `QA`, `DevOps`
- Comma-inverted word order: `"Engineer, Software"` instead of `"Software Engineer"`
- Mixed languages: Sinhala/Tamil tokens alongside English titles on Sri Lankan boards
- Duplicate whitespace, em-dashes, slashes used as separators

---

## 3. Extraction Rules

### 3.1 Input Harmonization

```
raw input (str | dict | list)
  │
  ├─ HTML string  → strip tags via regex, decode entities
  ├─ dict         → pull "title" key (primary) + "description" key (fallback)
  └─ list of dict → process each dict individually
```

### 3.2 Text Normalization (applied to every candidate string)

1. Unicode NFC normalization.
2. Strip HTML tags: `<[^>]+>` → `""`.
3. Decode HTML entities: `&amp;` → `&`, `&lt;` → `<`, etc.
4. Collapse whitespace: `\s+` → single space, then strip.
5. Remove trailing parenthesized noise: `(Remote)`, `(Sri Lanka)`, `($120k)`, etc.
6. Remove trailing dash/pipe segments when they look like metadata:
   `"Software Engineer — Colombo"` → `"Software Engineer"`.
7. Expand abbreviations via configurable map (see §6).
8. Title-case the result for display consistency.

### 3.3 Candidate Generation

- **Primary candidate**: the `title` field after normalization.
- **Fallback candidates**: first `<h1>`/`<h2>` in HTML, or first line of plain text.
- **Comma inversion**: if the normalized string contains exactly one comma,
  try swapping segments: `"Engineer, Software"` → `"Software Engineer"`.
  Keep both the original and the swapped form as candidates.
- **Slash/pipe split**: `"SWE / Full Stack Dev"` → two candidates.

### 3.4 Canonical Mapping

Each candidate is matched against a three-tier lookup (first match wins):

1. **Exact map**: normalized string → canonical title.
2. **Synonym map**: token set → canonical title (order-insensitive).
3. **Regex map**: compiled patterns → canonical title.

All maps are loaded from `config/title_mappings.json` at startup.

### 3.5 Confidence Scoring

Each `ExtractedTitle` gets a float confidence in `[0.0, 1.0]`:

| Signal                        | Weight |
|-------------------------------|--------|
| Source is explicit title field | +0.40  |
| Exact canonical match found   | +0.30  |
| Synonym match found           | +0.20  |
| Regex match found             | +0.10  |
| Abbreviation expansion used   | -0.05  |
| Comma inversion applied       | -0.05  |
| Fallback (description/body)   | -0.20  |

Base confidence starts at `0.50`. Signals are additive.
Clamped to `[0.0, 1.0]`.

### 3.6 Ambiguity Handling

- If the top two candidates have confidence within `0.10` of each other,
  mark `ambiguous=True` and return both as `alternatives`.
- If no canonical mapping matches and confidence < `0.40`,
  set `canonical_title = "Unknown"` with reason `"no_mapping"`.

---

## 4. Post-Processing

1. **Deduplication**: group results by `canonical_title`; keep highest-confidence
   entry per group, merge `reason_codes`.
2. **Stable sort**: order by confidence descending, then alphabetical canonical title.
3. **Output schema** (per extracted title):

```json
{
  "raw_text":        "Sr. SWE (Remote)",
  "normalized_text": "Senior Software Engineer",
  "canonical_title": "Senior Software Engineer",
  "confidence":      0.85,
  "ambiguous":       false,
  "alternatives":    [],
  "reason_codes":    ["abbreviation_expanded", "exact_match"]
}
```

---

## 5. Example Inputs vs Expected Outputs

### Example 1 — Clean title field
**Input**: `{"title": "Software Engineer", "description": "..."}`
**Output**:
```json
{"canonical_title": "Software Engineer", "confidence": 0.90, "ambiguous": false}
```

### Example 2 — Inverted form
**Input**: `{"title": "Engineer, Software", "description": "..."}`
**Output**:
```json
{"canonical_title": "Software Engineer", "confidence": 0.85, "ambiguous": false,
 "reason_codes": ["comma_inversion"]}
```

### Example 3 — Abbreviation
**Input**: `{"title": "Sr. SWE", "description": "..."}`
**Output**:
```json
{"canonical_title": "Senior Software Engineer", "confidence": 0.85,
 "reason_codes": ["abbreviation_expanded"]}
```

### Example 4 — Noisy HTML
**Input**: `"<h1>  Full Stack Dev — Colombo (Remote)</h1>"`
**Output**:
```json
{"canonical_title": "Full Stack Developer", "confidence": 0.75,
 "reason_codes": ["html_stripped", "noise_removed", "synonym_match"]}
```

### Example 5 — Ambiguous / low confidence
**Input**: `"Looking for talented people to join our team"`
**Output**:
```json
{"canonical_title": "Unknown", "confidence": 0.30, "ambiguous": true,
 "reason_codes": ["no_mapping", "low_confidence"]}
```

---

## 6. Configuration (`config/title_mappings.json`)

```json
{
  "abbreviations": {
    "sr": "senior", "jr": "junior", "mgr": "manager",
    "eng": "engineer", "swe": "software engineer",
    "dev": "developer", "devops": "devops engineer",
    "qa": "quality assurance", "pm": "project manager",
    "vp": "vice president", "cto": "chief technology officer",
    "ceo": "chief executive officer"
  },
  "synonyms": {
    "software developer":       "Software Engineer",
    "software dev":             "Software Engineer",
    "full stack developer":     "Full Stack Developer",
    "full stack dev":           "Full Stack Developer",
    "frontend developer":       "Frontend Developer",
    "front end developer":      "Frontend Developer",
    "backend developer":        "Backend Developer",
    "back end developer":       "Backend Developer",
    "devops engineer":          "DevOps Engineer",
    "site reliability engineer":"SRE",
    "quality assurance engineer":"QA Engineer",
    "project manager":          "Project Manager",
    "product manager":          "Product Manager",
    "data scientist":           "Data Scientist",
    "data analyst":             "Data Analyst",
    "machine learning engineer":"ML Engineer",
    "ui ux designer":           "UI/UX Designer"
  },
  "locale_tokens": {
    "en": {},
    "si": {"මෘදුකාංග ඉංජිනේරු": "Software Engineer"},
    "ta": {"மென்பொருள் பொறியாளர்": "Software Engineer"}
  },
  "confidence_thresholds": {
    "ambiguity_margin": 0.10,
    "unknown_cutoff":   0.40
  }
}
```

Users can edit this file to add domain-specific titles, new abbreviations, or
locale-specific mappings without touching Python code.

---

## 7. Testing Plan

| Category              | Example input                          | Expected canonical        |
|-----------------------|----------------------------------------|---------------------------|
| Clean title           | `"Software Engineer"`                  | `Software Engineer`       |
| Comma inversion       | `"Engineer, Software"`                 | `Software Engineer`       |
| Abbreviation          | `"Sr. SWE"`                            | `Senior Software Engineer`|
| HTML noise            | `"<b>Dev</b> (Remote)"`               | `Developer`               |
| Slash split           | `"SWE / QA Engineer"`                  | Two results               |
| Non-English fallback  | Sinhala token for "Software Engineer"  | `Software Engineer`       |
| Salary noise          | `"Developer — $120k — NYC"`           | `Developer`               |
| Empty / garbage       | `"---"` or `""`                        | `Unknown`                 |
| Ambiguous             | `"People person with team skills"`     | `Unknown` (ambiguous)     |
| Multi-word seniority  | `"Junior Full Stack Developer"`        | `Junior Full Stack Developer` |

Edge-case tests live in `tests/test_title_extractor.py` and are runnable via
`pytest tests/`.

---

## 8. Architecture Fit

```
TopJob scraper ──┐                        ┌─► cover letter gen
                 ├─► normalize_job() ─────┤
LinkedIn scraper ┘   (title_extractor)    └─► dedup / DB tracker
```

The `normalize_job(job_dict)` helper is called in `main.py` after scraping and
before the dedup/application loop. It mutates the job dict in-place, adding
`canonical_title`, `title_confidence`, and `title_ambiguous` fields while
preserving the original `title`.
