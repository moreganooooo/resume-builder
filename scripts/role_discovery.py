"""
role_discovery.py -- modern job title normalization, O*NET SOC mapping,
and search query / title alias expansion.

Provides taxonomy lookups from data/modern_title_aliases.yml to support
role discovery, board scanning search query expansion, and skills/gap
evaluations.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_ALIASES_PATH = os.path.join(PROJECT_ROOT, "data", "modern_title_aliases.yml")

# Regex patterns for stripping seniority and noise from job titles
_SENIORITY_PATTERNS = [
    r"\b(senior|sr\.?|junior|jr\.?|lead|principal|staff|associate|entry[\s-]level|mid[\s-]level|intern)\b",
    r"\b(head\s+of|director\s+of|vp\s+of|vice\s+president\s+of|chief|executive)\b",
    r"\b(level\s+[iIvVxX\d]+|[iIvVxX]+)\b",
]

_TAGS_AND_NOISE_PATTERNS = [
    r"[\(\[\{][^\)\]\}]*(?:remote|hybrid|onsite|on-site|full[\s-]time|part[\s-]time|contract|temp|internship|us\s*only|usa)[^\)\]\}]*[\)\]\}]",
    r"\b(remote|hybrid|onsite|on-site|full[\s-]time|part[\s-]time|contract)\b",
    r"[-–—/\\|:]\s*(?:remote|hybrid|onsite|us\s*only|usa)\b",
    r"[-–—/\\|:]\s*$",
]


def normalize_job_title(title: str) -> str:
    """Cleans a raw job title by stripping seniority prefixes, remote/hybrid tags,
    employment type notes, and trailing punctuation.

    Example:
      'Senior Lifecycle Marketing Manager (Remote - US)' -> 'Lifecycle Marketing Manager'
      'Staff Software Engineer - Backend [Hybrid]' -> 'Software Engineer Backend'
    """
    if not title:
        return ""

    cleaned = title.strip()

    # Strip bracketed tags first
    for pattern in _TAGS_AND_NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

    # Clean punctuation noise
    cleaned = re.sub(r"[^\w\s&]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


@lru_cache(maxsize=4)
def _load_yaml_cached(file_path: str) -> dict:
    """Loads and caches the title aliases YAML file."""
    if not os.path.isfile(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_title_aliases(custom_path: Optional[str] = None) -> Dict[str, dict]:
    """Returns the role_families dictionary from the aliases YAML file."""
    path = custom_path or DEFAULT_ALIASES_PATH
    data = _load_yaml_cached(path)
    return data.get("role_families", {})


def _tokenize(text: str) -> set[str]:
    """Extracts lowercase alphabetic tokens from a string."""
    return set(re.findall(r"\b[a-z]{2,}\b", text.lower()))


def match_role_family(
    title: str, custom_path: Optional[str] = None
) -> Tuple[Optional[str], Optional[dict], float]:
    """Matches a job title against known role families and aliases.

    Returns:
      (family_id, family_dict, confidence_score)
      confidence_score ranges from 0.0 to 1.0 (1.0 = exact alias match).
    """
    if not title:
        return None, None, 0.0

    families = load_title_aliases(custom_path)
    if not families:
        return None, None, 0.0

    normalized = normalize_job_title(title).lower()
    raw_lower = title.strip().lower()
    title_tokens = _tokenize(normalized) or _tokenize(raw_lower)

    best_family_id: Optional[str] = None
    best_family_data: Optional[dict] = None
    best_score = 0.0

    for family_id, family in families.items():
        if not isinstance(family, dict):
            continue

        canonical = (family.get("canonical_title") or "").lower()
        aliases = [a.lower() for a in family.get("aliases") or []]

        # 1. Exact canonical or alias match
        if raw_lower == canonical or normalized == canonical:
            return family_id, family, 1.0

        for alias in aliases:
            if raw_lower == alias or normalized == alias:
                return family_id, family, 1.0

        # 2. Substring match
        for alias in aliases:
            if alias in raw_lower or alias in normalized:
                score = 0.9
                if score > best_score:
                    best_score = score
                    best_family_id = family_id
                    best_family_data = family

        # 3. Token overlap Jaccard-like score
        for alias in aliases + [canonical]:
            alias_tokens = _tokenize(alias)
            if not alias_tokens:
                continue
            common = title_tokens & alias_tokens
            if common:
                overlap = len(common) / max(len(title_tokens | alias_tokens), 1)
                # Boost if crucial key marketing/engineering/product terms match
                if common & {"marketing", "engineer", "designer", "product", "analyst"}:
                    overlap = min(1.0, overlap + 0.2)
                if overlap > best_score and overlap >= 0.35:
                    best_score = overlap
                    best_family_id = family_id
                    best_family_data = family

    if best_score > 0.0:
        return best_family_id, best_family_data, round(best_score, 2)

    return None, None, 0.0


def expand_title_aliases(title: str, custom_path: Optional[str] = None) -> List[str]:
    """Returns search query synonyms and title aliases for a given job title.

    If a matching role family is found, returns its search variations and aliases.
    Otherwise returns [title].
    """
    if not title:
        return []

    _, family, _ = match_role_family(title, custom_path)
    if not family:
        return [title]

    variations = list(family.get("search_query_variations") or [])
    aliases = list(family.get("aliases") or [])

    # Preserve order while deduping
    seen = set()
    expanded = []
    for item in variations + aliases:
        if item and item not in seen:
            seen.add(item)
            expanded.append(item)

    return expanded if expanded else [title]


def get_onet_classification(
    title: str, custom_path: Optional[str] = None
) -> Optional[dict]:
    """Returns the O*NET classification ({'onet_code': ..., 'onet_title': ...})
    for a given job title, or None if no match is found.
    """
    _, family, score = match_role_family(title, custom_path)
    if family and score >= 0.4:
        return {
            "onet_code": family.get("onet_code", ""),
            "onet_title": family.get("onet_title", ""),
            "canonical_title": family.get("canonical_title", ""),
        }
    return None


def get_core_competencies(
    title_or_family: str, custom_path: Optional[str] = None
) -> List[str]:
    """Returns core competencies for a given job title or role family identifier."""
    if not title_or_family:
        return []

    families = load_title_aliases(custom_path)
    # Check if direct family key
    if title_or_family in families:
        return families[title_or_family].get("core_competencies") or []

    # Match by title
    _, family, _ = match_role_family(title_or_family, custom_path)
    if family:
        return family.get("core_competencies") or []

    return []
