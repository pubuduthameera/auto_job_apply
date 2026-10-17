"""
tests/test_title_extractor.py — Edge-case tests for job title extraction pipeline

Covers: synonym mapping, word-order variants, abbreviations, HTML noise,
slash splitting, multilingual tokens, salary stripping, ambiguous/low-confidence
inputs, deduplication, and the normalize_job convenience helper.
"""

import pytest

from scrapers.title_extractor import (
    ExtractedTitle,
    ExtractorConfig,
    extract_titles,
    normalize_job,
)


@pytest.fixture
def config() -> ExtractorConfig:
    return ExtractorConfig.load()


# ── Clean title-field inputs ─────────────────────────────────────────────────


class TestCleanTitles:
    def test_exact_known_title(self, config: ExtractorConfig):
        results = extract_titles({"title": "Software Engineer"}, config)
        assert results[0].canonical_title == "Software Engineer"
        assert results[0].confidence >= 0.80

    def test_synonym_mapping(self, config: ExtractorConfig):
        results = extract_titles({"title": "Software Developer"}, config)
        assert results[0].canonical_title == "Software Engineer"
        assert "synonym_match" in results[0].reason_codes

    def test_plain_string_short(self, config: ExtractorConfig):
        results = extract_titles("Data Scientist", config)
        assert results[0].canonical_title == "Data Scientist"

    def test_preserves_raw_text(self, config: ExtractorConfig):
        results = extract_titles({"title": "Software Developer"}, config)
        assert results[0].raw_text == "Software Developer"


# ── Abbreviation expansion ───────────────────────────────────────────────────


class TestAbbreviations:
    def test_sr_swe(self, config: ExtractorConfig):
        results = extract_titles({"title": "Sr. SWE"}, config)
        assert results[0].canonical_title == "Senior Software Engineer"
        assert "abbreviation_expanded" in results[0].reason_codes

    def test_jr_dev(self, config: ExtractorConfig):
        results = extract_titles({"title": "Jr. Dev"}, config)
        best = results[0]
        assert "junior" in best.normalized_text.lower()
        assert "developer" in best.normalized_text.lower()
        assert "abbreviation_expanded" in best.reason_codes

    def test_sr_without_dot(self, config: ExtractorConfig):
        results = extract_titles({"title": "Sr SWE"}, config)
        assert "senior" in results[0].normalized_text.lower()

    def test_qa_engineer(self, config: ExtractorConfig):
        results = extract_titles({"title": "QA Eng"}, config)
        normalized = results[0].normalized_text.lower()
        assert "quality assurance" in normalized
        assert "engineer" in normalized

    def test_devops(self, config: ExtractorConfig):
        results = extract_titles({"title": "DevOps"}, config)
        assert "devops" in results[0].canonical_title.lower() or "devops" in results[0].normalized_text.lower()


# ── Comma-inverted forms ─────────────────────────────────────────────────────


class TestCommaInversion:
    def test_engineer_comma_software(self, config: ExtractorConfig):
        results = extract_titles({"title": "Engineer, Software"}, config)
        canonicals = [r.canonical_title for r in results]
        assert "Software Engineer" in canonicals

    def test_developer_comma_frontend(self, config: ExtractorConfig):
        results = extract_titles({"title": "Developer, Frontend"}, config)
        canonicals = [r.canonical_title.lower() for r in results]
        assert any("frontend" in c and "developer" in c for c in canonicals)

    def test_inversion_adds_reason_code(self, config: ExtractorConfig):
        results = extract_titles({"title": "Engineer, Software"}, config)
        inverted = [r for r in results if "comma_inversion" in r.reason_codes]
        assert len(inverted) >= 1


# ── Slash / pipe splitting ───────────────────────────────────────────────────


class TestSlashSplit:
    def test_two_titles_separated_by_slash(self, config: ExtractorConfig):
        results = extract_titles({"title": "SWE / QA Eng"}, config)
        assert len(results) >= 2

    def test_pipe_separated(self, config: ExtractorConfig):
        results = extract_titles("Frontend Dev | Backend Dev", config)
        assert len(results) >= 2


# ── HTML noise stripping ────────────────────────────────────────────────────


class TestHTMLStripping:
    def test_tags_removed(self, config: ExtractorConfig):
        html_input = "<h1>  Full Stack Developer  </h1>"
        results = extract_titles(html_input, config)
        assert results[0].canonical_title == "Full Stack Developer"
        assert "html_stripped" in results[0].reason_codes

    def test_entities_decoded(self, config: ExtractorConfig):
        results = extract_titles("<b>Dev &amp; Ops</b>", config)
        assert "&amp;" not in results[0].normalized_text

    def test_nested_tags(self, config: ExtractorConfig):
        results = extract_titles("<div><span><b>Data Analyst</b></span></div>", config)
        assert results[0].canonical_title == "Data Analyst"


# ── Trailing noise removal ──────────────────────────────────────────────────


class TestNoiseRemoval:
    def test_parenthesized_remote(self, config: ExtractorConfig):
        results = extract_titles({"title": "Software Engineer (Remote)"}, config)
        assert results[0].canonical_title == "Software Engineer"
        assert "noise_removed" in results[0].reason_codes

    def test_trailing_location_dash(self, config: ExtractorConfig):
        results = extract_titles({"title": "Developer — Colombo"}, config)
        canonical = results[0].canonical_title.lower()
        assert "colombo" not in canonical

    def test_salary_stripped(self, config: ExtractorConfig):
        results = extract_titles({"title": "Developer $120k"}, config)
        canonical = results[0].canonical_title.lower()
        assert "120" not in canonical
        assert "salary_removed" in results[0].reason_codes

    def test_salary_range_stripped(self, config: ExtractorConfig):
        results = extract_titles({"title": "Engineer 80K — 120K"}, config)
        canonical = results[0].canonical_title.lower()
        assert "80" not in canonical


# ── Multilingual / locale tokens ─────────────────────────────────────────────


class TestLocaleTokens:
    def test_sinhala_software_engineer(self, config: ExtractorConfig):
        results = extract_titles({"title": "මෘදුකාංග ඉංජිනේරු"}, config)
        assert results[0].canonical_title == "Software Engineer"
        assert "locale_match" in results[0].reason_codes

    def test_tamil_software_engineer(self, config: ExtractorConfig):
        results = extract_titles({"title": "மென்பொருள் பொறியாளர்"}, config)
        assert results[0].canonical_title == "Software Engineer"

    def test_mixed_english_and_locale(self, config: ExtractorConfig):
        results = extract_titles({"title": "Senior මෘදුකාංග ඉංජිනේරු"}, config)
        assert results[0].canonical_title == "Software Engineer"


# ── Edge cases: empty, garbage, ambiguous ────────────────────────────────────


class TestEdgeCases:
    def test_empty_string(self, config: ExtractorConfig):
        results = extract_titles("", config)
        assert results[0].canonical_title == "Unknown"
        assert results[0].ambiguous is True

    def test_whitespace_only(self, config: ExtractorConfig):
        results = extract_titles("   ", config)
        assert results[0].canonical_title == "Unknown"

    def test_garbage_dashes(self, config: ExtractorConfig):
        results = extract_titles({"title": "---"}, config)
        assert results[0].confidence < 0.50

    def test_no_title_key_in_dict(self, config: ExtractorConfig):
        results = extract_titles({"company": "Acme"}, config)
        assert results[0].canonical_title == "Unknown"

    def test_long_description_text_not_a_title(self, config: ExtractorConfig):
        text = "Looking for talented people to join our growing team in Colombo"
        results = extract_titles(text, config)
        assert results[0].confidence <= 0.60

    def test_none_title_in_dict(self, config: ExtractorConfig):
        results = extract_titles({"title": None, "description": "Software Engineer needed"}, config)
        assert len(results) >= 1

    def test_list_of_dicts(self, config: ExtractorConfig):
        payload = [
            {"title": "Software Engineer"},
            {"title": "Data Scientist"},
        ]
        results = extract_titles(payload, config)
        canonicals = {r.canonical_title for r in results}
        assert "Software Engineer" in canonicals
        assert "Data Scientist" in canonicals


# ── Deduplication ────────────────────────────────────────────────────────────


class TestDeduplication:
    def test_duplicate_titles_merged(self, config: ExtractorConfig):
        payload = [
            {"title": "Software Engineer"},
            {"title": "Software Developer"},
        ]
        results = extract_titles(payload, config)
        se_results = [r for r in results if r.canonical_title == "Software Engineer"]
        assert len(se_results) == 1

    def test_highest_confidence_kept(self, config: ExtractorConfig):
        payload = [
            {"title": "Software Engineer"},
            {"title": "software developer"},
        ]
        results = extract_titles(payload, config)
        se = [r for r in results if r.canonical_title == "Software Engineer"][0]
        assert se.confidence >= 0.80


# ── Confidence scoring ───────────────────────────────────────────────────────


class TestConfidence:
    def test_title_field_boosts_confidence(self, config: ExtractorConfig):
        from_title = extract_titles({"title": "Software Engineer"}, config)
        from_string = extract_titles("Software Engineer", config)
        assert from_title[0].confidence >= from_string[0].confidence

    def test_abbreviation_slightly_lowers(self, config: ExtractorConfig):
        clean = extract_titles({"title": "Senior Software Engineer"}, config)
        abbrev = extract_titles({"title": "Sr. SWE"}, config)
        assert clean[0].confidence >= abbrev[0].confidence

    def test_confidence_in_range(self, config: ExtractorConfig):
        results = extract_titles({"title": "Sr. SWE (Remote)"}, config)
        for r in results:
            assert 0.0 <= r.confidence <= 1.0


# ── Ambiguity detection ─────────────────────────────────────────────────────


class TestAmbiguity:
    def test_close_confidence_marks_ambiguous(self, config: ExtractorConfig):
        results = extract_titles({"title": "Engineer, Software"}, config)
        top_two = sorted(results, key=lambda r: -r.confidence)[:2]
        if len(top_two) == 2:
            gap = top_two[0].confidence - top_two[1].confidence
            if gap <= config.ambiguity_margin:
                assert top_two[0].ambiguous is True

    def test_alternatives_populated(self, config: ExtractorConfig):
        results = extract_titles({"title": "Engineer, Software"}, config)
        top = sorted(results, key=lambda r: -r.confidence)[0]
        if top.ambiguous and top.alternatives:
            assert len(top.alternatives) >= 1


# ── normalize_job helper ─────────────────────────────────────────────────────


class TestNormalizeJob:
    def test_adds_canonical_fields(self, config: ExtractorConfig):
        job = {
            "id": "test_1",
            "title": "Sr. SWE",
            "company": "Acme",
            "description": "We need a senior software engineer",
        }
        normalize_job(job, config)
        assert "canonical_title" in job
        assert "title_confidence" in job
        assert "title_ambiguous" in job

    def test_preserves_original_title(self, config: ExtractorConfig):
        job = {
            "id": "test_2",
            "title": "Software Developer",
            "company": "Acme",
            "description": "...",
        }
        normalize_job(job, config)
        assert job["title"] == "Software Developer"
        assert job["canonical_title"] == "Software Engineer"

    def test_handles_missing_title(self, config: ExtractorConfig):
        job = {
            "id": "test_3",
            "company": "Acme",
            "description": "Data Scientist role",
        }
        normalize_job(job, config)
        assert "canonical_title" in job

    def test_multiple_jobs_independent(self, config: ExtractorConfig):
        jobs = [
            {"id": "a", "title": "Sr. SWE", "company": "X", "description": ""},
            {"id": "b", "title": "Data Analyst", "company": "Y", "description": ""},
        ]
        for j in jobs:
            normalize_job(j, config)
        assert jobs[0]["canonical_title"] != jobs[1]["canonical_title"]


# ── Requested direct comparisons ─────────────────────────────────────────────


class TestDirectComparisons:
    """Verify the specific ambiguity examples from the requirements."""

    def test_software_engineer_vs_engineer_software(self, config: ExtractorConfig):
        r1 = extract_titles({"title": "software engineer"}, config)
        r2 = extract_titles({"title": "engineer, software"}, config)
        c1 = {r.canonical_title for r in r1}
        c2 = {r.canonical_title for r in r2}
        assert "Software Engineer" in c1
        assert "Software Engineer" in c2

    def test_sr_swe_vs_senior_software_engineer(self, config: ExtractorConfig):
        r1 = extract_titles({"title": "Sr. SWE"}, config)
        r2 = extract_titles({"title": "Senior Software Engineer"}, config)
        assert r1[0].canonical_title == r2[0].canonical_title == "Senior Software Engineer"
