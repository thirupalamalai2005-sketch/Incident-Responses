"""
ai_analyzer.py
Incident analysis using the official Google Gemini SDK (google-genai).
Prompts Gemini for strict JSON output:
    {
        "summary": str,
        "category": str,
        "priority": str,
        "steps": [str, ...]
    }

Normalizes category and priority to standard values.
Falls back automatically to the rule-based analyzer on any exception,
invalid key, network failure, or malformed JSON, marking source='fallback'.
"""

import json
import os
import re
from typing import Any, Dict, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

try:
    from google import genai
except ImportError:
    genai = None

from fallback_analyzer import (
    ALLOWED_CATEGORIES,
    ALLOWED_PRIORITIES,
    analyze_with_rules,
)

# Standard category mapping
CATEGORY_SYNONYMS = {
    "network": "network",
    "wifi": "network",
    "internet": "network",
    "hardware": "hardware",
    "laptop": "hardware",
    "device": "hardware",
    "software": "software",
    "application": "software",
    "app": "software",
    "access": "access",
    "account": "access",
    "permission": "access",
    "security": "access",
    "database": "database",
    "db": "database",
    "sql": "database",
    "other": "other",
    "inquiry": "other",
}

PRIORITY_SYNONYMS = {
    "critical": "Critical",
    "p1": "Critical",
    "high": "High",
    "p2": "High",
    "medium": "Medium",
    "p3": "Medium",
    "moderate": "Medium",
    "low": "Low",
    "p4": "Low",
}


def clean_markdown_json(text: str) -> str:
    """
    Remove markdown code fences (```json ... ``` or ``` ... ```)
    and surrounding whitespace.
    """
    if not text:
        return ""
    cleaned = text.strip()
    # Match ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    return cleaned


def normalize_category(cat: str) -> str:
    """Normalize category to one of ALLOWED_CATEGORIES."""
    val = (cat or "").strip().lower()
    return CATEGORY_SYNONYMS.get(val, "other")


def normalize_priority(prio: str) -> str:
    """Normalize priority to one of Critical, High, Medium, Low."""
    val = (prio or "").strip().lower()
    return PRIORITY_SYNONYMS.get(val, "Medium")


def analyze_incident(issue_text: str) -> Tuple[Dict[str, Any], str]:
    """
    Analyze an IT incident text using Gemini API with automatic fallback.

    Returns:
        (result_dict, source) where source is 'gemini' or 'fallback'.
        result_dict contains:
            {
                "summary": str,
                "category": str,
                "priority": str,
                "steps": [str, ...]
            }
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

    if not api_key or genai is None:
        # Fallback immediately
        return analyze_with_rules(issue_text), "fallback"

    prompt = f"""You are an enterprise IT Service Desk Copilot.
Analyze this employee's IT incident report:

\"\"\"{issue_text}\"\"\"

Classify the incident and provide practical troubleshooting steps.
Return ONLY a valid JSON object with EXACTLY this structure:
{{
    "summary": "Short professional summary of the problem (max 120 chars)",
    "category": "hardware|software|network|database|access|other",
    "priority": "Critical|High|Medium|Low",
    "steps": [
        "First troubleshooting step...",
        "Second troubleshooting step...",
        "Third troubleshooting step..."
    ]
}}

Guidelines:
- category MUST be one of: hardware, software, network, database, access, other.
- priority MUST be one of: Critical, High, Medium, Low.
- steps MUST be a list of 3-5 concise, actionable, numbered troubleshooting instructions.
- Never request user passwords, OTPs, or private keys.
- Return raw JSON only, no explanatory text outside the JSON.
"""

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )

        raw_text = response.text or ""
        cleaned_json = clean_markdown_json(raw_text)

        parsed = json.loads(cleaned_json)

        # Validate required fields
        if not isinstance(parsed, dict):
            raise ValueError("Gemini output is not a JSON object")

        summary = str(parsed.get("summary", "")).strip()
        if not summary:
            summary = issue_text[:120].strip()

        raw_category = str(parsed.get("category", "")).strip()
        raw_priority = str(parsed.get("priority", "")).strip()
        raw_steps = parsed.get("steps", [])

        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("Steps must be a non-empty list of instructions")

        clean_steps = [str(s).strip() for s in raw_steps if str(s).strip()]
        if not clean_steps:
            raise ValueError("No valid steps parsed")

        normalized_result = {
            "summary": summary,
            "category": normalize_category(raw_category),
            "priority": normalize_priority(raw_priority),
            "steps": clean_steps,
        }

        return normalized_result, "gemini"

    except Exception:
        # On quota, invalid key, bad JSON, network error, etc.
        fallback_res = analyze_with_rules(issue_text)
        return fallback_res, "fallback"
