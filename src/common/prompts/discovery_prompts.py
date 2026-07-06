"""
SWASTHYA AI CORE — Discovery Pipeline Prompts.

All prompts are versioned, typed, and centrally managed.
"""

from __future__ import annotations

PROMPT_VERSION = "1.0.0"

# ── Search Strategy Generation ─────────────────────────────────────────────────

STRATEGY_SYSTEM = """You are a medical search strategy architect.
Return ONLY valid JSON matching this exact schema:
{
  "primary_search_queries": ["query1"],
  "nabh_search_terms": ["term1"],
  "specialty_keywords": ["kw1"],
  "location_variants": ["loc1"],
  "search_radius_km": 10,
  "priority_filters": {"require_nabh": true, "require_emergency": false, "require_icu": false, "prefer_government": false},
  "search_depth": "basic|standard|deep"
}
No markdown. No prose."""

STRATEGY_USER_TEMPLATE = """Context:
Specialty: {specialty}
Location: {location}
Urgency: {urgency}
Budget: {budget_preference}
Type: {hospital_type}
Emergency: {is_emergency}"""

# ── Hospital Gemini Summarization ──────────────────────────────────────────────

SUMMARIZE_SYSTEM = """You are a medical intelligence analyst.
Summarize hospital data into a JSON dictionary mapping Candidate ID to this schema:
{
  "hospital_type": "government|private|trust|charitable",
  "accreditations": ["NABH"],
  "specialties_available": ["spec1"],
  "has_emergency": true,
  "has_icu": true,
  "bed_count": 100,
  "overall_rating": 4.5,
  "review_count": 150,
  "estimated_cost_range": {"min_inr": 1000, "max_inr": 5000, "currency": "INR"},
  "contact_number": "phone",
  "website": "url",
  "key_strengths": ["str1"],
  "known_limitations": ["str1"],
  "clinical_notes": "factual paragraph",
  "data_quality_score": 0.8
}
Return ONLY JSON. No markdown."""

SUMMARIZE_USER_TEMPLATE = """Specialty: {specialty}
Budget: {budget_preference}
Urgency: {urgency}

Data:
{batch_raw_data}"""

# ── Hospital Ranking Explainer ─────────────────────────────────────────────────

EXPLAIN_SYSTEM = """You are a transparent medical recommendation engine.
Generate a JSON dictionary mapping Hospital Name to this schema:
{
  "summary": "2-3 sentence patient-friendly explanation in patient's language",
  "pros": ["reason1", "reason2"],
  "cons": ["caution1"]
}
Return ONLY JSON. No markdown."""

EXPLAIN_USER_TEMPLATE = """Language: {language_code}
Specialty: {specialty}

Data:
{batch_ranking_data}"""
