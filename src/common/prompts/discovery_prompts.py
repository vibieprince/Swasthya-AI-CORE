"""
SWASTHYA AI CORE — Discovery Pipeline Prompts.

All prompts are versioned, typed, and centrally managed.
"""

from __future__ import annotations

PROMPT_VERSION = "1.0.0"

# ── Search Strategy Generation ─────────────────────────────────────────────────

STRATEGY_SYSTEM = """You are a medical search strategy architect for the Indian healthcare market.
Given a patient's clinical context, generate a comprehensive multi-source search strategy
to discover the best hospitals for their needs.
You MUST respond with ONLY valid JSON. No markdown. No prose.
"""

STRATEGY_USER_TEMPLATE = """Generate a hospital search strategy for this patient context.

SPECIALTY: {specialty}
LOCATION: {location}
URGENCY: {urgency}
BUDGET_PREFERENCE: {budget_preference}
HOSPITAL_TYPE_PREFERENCE: {hospital_type}
IS_EMERGENCY: {is_emergency}

Respond with this exact JSON structure:
{{
  "primary_search_queries": [
    "<query 1 — specific, location-aware>",
    "<query 2>",
    "<query 3>"
  ],
  "nabh_search_terms": ["<term1>", "<term2>"],
  "specialty_keywords": ["<kw1>", "<kw2>", "<kw3>"],
  "location_variants": ["<city>", "<city + state>", "<nearby area if applicable>"],
  "search_radius_km": <integer>,
  "priority_filters": {{
    "require_nabh": <true|false>,
    "require_emergency": <true|false>,
    "require_icu": <true|false>,
    "prefer_government": <true|false>
  }},
  "search_depth": "<basic|standard|deep>"
}}"""

# ── Hospital Gemini Summarization ──────────────────────────────────────────────

SUMMARIZE_SYSTEM = """You are a senior medical intelligence analyst for the Indian healthcare system.
Analyse the provided hospital research data and produce a structured clinical assessment.
Be factual. Do not hallucinate accreditations or facilities not mentioned in the data.
You MUST respond with ONLY valid JSON. No markdown. No prose.
"""

SUMMARIZE_USER_TEMPLATE = """Analyse and summarise this hospital data for patient recommendations.

HOSPITAL NAME: {hospital_name}
RAW DATA SOURCES:
{raw_data}

PATIENT SPECIALTY NEED: {specialty}
PATIENT BUDGET: {budget_preference}
PATIENT URGENCY: {urgency}

Respond with this exact JSON structure:
{{
  "hospital_type": "<government|private|trust|charitable>",
  "accreditations": ["<NABH>", "<JCI>", etc. — only if mentioned in data],
  "specialties_available": ["<spec1>", "<spec2>"],
  "has_emergency": <true|false>,
  "has_icu": <true|false>,
  "bed_count": <integer or null>,
  "overall_rating": <1.0–5.0 or null>,
  "review_count": <integer or null>,
  "estimated_cost_range": {{
    "min_inr": <integer or null>,
    "max_inr": <integer or null>,
    "currency": "INR"
  }},
  "contact_number": "<phone or null>",
  "website": "<url or null>",
  "key_strengths": ["<strength1>", "<strength2>"],
  "known_limitations": ["<limitation1>"],
  "clinical_notes": "<one paragraph, factual, no PHI>",
  "data_quality_score": <0.0–1.0>
}}"""

# ── Hospital Ranking Explainer ─────────────────────────────────────────────────

EXPLAIN_SYSTEM = """You are a transparent medical recommendation engine.
Generate a clear, patient-friendly explanation of why a hospital was recommended
and why it was ranked at its specific position.
Write in simple language, no medical jargon.
You MUST respond with ONLY valid JSON. No markdown. No prose.
"""

EXPLAIN_USER_TEMPLATE = """Generate recommendation explanation for this hospital ranking.

HOSPITAL NAME: {hospital_name}
RANK: {rank} of {total_ranked}
TRUST_SCORE: {trust_score}
CLINICAL_SUITABILITY: {clinical_suitability}
AFFORDABILITY_SCORE: {affordability_score}
KEY_STRENGTHS: {key_strengths}
KNOWN_LIMITATIONS: {known_limitations}
SPECIALTY: {specialty}
PATIENT_LANGUAGE: {language_code}

Respond with this exact JSON structure:
{{
  "recommendation_summary": "<2-3 sentence patient-friendly explanation in {language_code}>",
  "recommendation_summary_english": "<English version>",
  "why_this_rank": "<one sentence explaining rank position>",
  "top_reasons": ["<reason1>", "<reason2>", "<reason3>"],
  "cautions": ["<caution1 if any>"],
  "confidence_explanation": "<one sentence on confidence level>"
}}"""
