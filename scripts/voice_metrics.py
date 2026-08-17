"""
voice_metrics.py — Pure statistical stylometry and voice anchor validator.

Measures structural rhythm, sentence-length burstiness, lexical diversity,
and syntactic repetition in free prose (cover letters) to prevent
monotonous "AI-beige" synthetic generation and preserve authentic candidate voice.
"""

import math
import re
from typing import Any, Dict, List

_ABBREVIATIONS = (
    r"e\.g\.",
    r"i\.e\.",
    r"inc\.",
    r"corp\.",
    r"ltd\.",
    r"co\.",
    r"dr\.",
    r"mr\.",
    r"ms\.",
    r"mrs\.",
    r"vs\.",
    r"ph\.d\.",
    r"u\.s\.",
    r"st\.",
)

_ABBREV_REGEX = re.compile(r"\b(?:" + "|".join(_ABBREVIATIONS) + r")", re.IGNORECASE)
_DECIMAL_REGEX = re.compile(r"\b\d+\.\d+\b")

DEFAULT_THRESHOLDS = {
    "sentence_std_dev_min": 4.5,
    "sentence_span_min": 12,
    "sentence_length_max": 55,
    "sentence_length_min": 3,
    "type_token_ratio_min": 0.46,
    "max_consecutive_same_opener": 2,
}


def split_sentences(text: str) -> List[str]:
    """Splits text into sentences while protecting abbreviations and decimals."""
    if not text or not text.strip():
        return []

    # Mask decimals (e.g. 14.5% -> 14<DECIMAL>5%)
    masked = _DECIMAL_REGEX.sub(lambda m: m.group(0).replace(".", "<DECIMAL>"), text)

    # Mask abbreviations
    masked = _ABBREV_REGEX.sub(lambda m: m.group(0).replace(".", "<DOT>"), masked)

    # Split on sentence terminals followed by whitespace
    raw_splits = re.split(r"(?<=[.!?])\s+", masked)

    sentences = []
    for s in raw_splits:
        unmasked = s.replace("<DECIMAL>", ".").replace("<DOT>", ".").strip()
        if unmasked:
            sentences.append(unmasked)
    return sentences


def compute_sentence_length_stats(sentences: List[str]) -> Dict[str, Any]:
    """Computes word counts, mean, standard deviation, and span across sentences."""
    if not sentences:
        return {"counts": [], "mean": 0.0, "std_dev": 0.0, "span": 0, "min": 0, "max": 0}

    counts = [len(re.findall(r"\b\w+(?:[-']\w+)?\b", s)) for s in sentences]
    counts = [c for c in counts if c > 0]

    if not counts:
        return {"counts": [], "mean": 0.0, "std_dev": 0.0, "span": 0, "min": 0, "max": 0}

    n = len(counts)
    mean = sum(counts) / n
    if n > 1:
        variance = sum((x - mean) ** 2 for x in counts) / (n - 1)
        std_dev = math.sqrt(variance)
    else:
        std_dev = 0.0

    min_len = min(counts)
    max_len = max(counts)
    span = max_len - min_len

    return {
        "counts": counts,
        "mean": mean,
        "std_dev": std_dev,
        "span": span,
        "min": min_len,
        "max": max_len,
    }


def compute_type_token_ratio(text: str) -> Dict[str, float]:
    """Computes Standard and Root Type-Token Ratio for lexical diversity."""
    words = re.findall(r"\b[a-zA-Z]+(?:'[a-zA-Z]+)?\b", text.lower())
    if not words:
        return {"ttr": 1.0, "total_tokens": 0, "unique_tokens": 0}

    n = len(words)
    v = len(set(words))
    ttr = v / n
    return {"ttr": ttr, "total_tokens": n, "unique_tokens": v}


def detect_consecutive_opener_repetitions(sentences: List[str], max_consecutive: int = 2) -> List[str]:
    """Detects 3+ consecutive sentences starting with identical 1-2 word openers."""
    violations = []
    if len(sentences) < 3:
        return violations

    openers = []
    for s in sentences:
        tokens = re.findall(r"\b\w+\b", s.lower())
        if tokens:
            first_word = tokens[0]
            first_two = f"{tokens[0]} {tokens[1]}" if len(tokens) > 1 else first_word
            openers.append((first_word, first_two))
        else:
            openers.append(("", ""))

    consecutive_word_count = 1
    current_word = ""

    for word, _ in openers:
        if not word:
            consecutive_word_count = 1
            current_word = ""
            continue

        if word == current_word:
            consecutive_word_count += 1
            if consecutive_word_count > max_consecutive:
                violations.append(
                    f"{consecutive_word_count} consecutive sentences begin with '{word.capitalize()}...'"
                )
        else:
            current_word = word
            consecutive_word_count = 1

    return list(dict.fromkeys(violations))


def analyze_voice_metrics(cover_letter_data: dict, rules: dict | None = None) -> List[str]:
    """Evaluates cover letter paragraphs against voice anchor and stylometric rules."""
    paragraphs = cover_letter_data.get("body_paragraphs", [])
    if not paragraphs:
        return []

    thresholds = DEFAULT_THRESHOLDS.copy()
    if rules and isinstance(rules, dict):
        custom_t = rules.get("thresholds", {})
        thresholds.update(custom_t)

    full_text = " ".join(paragraphs)
    all_sentences = []
    for p in paragraphs:
        all_sentences.extend(split_sentences(p))

    violations = []

    # 1. Sentence length variance & rhythm
    if len(all_sentences) >= 4:
        stats = compute_sentence_length_stats(all_sentences)
        std_dev = stats["std_dev"]
        span = stats["span"]

        if std_dev < thresholds["sentence_std_dev_min"]:
            violations.append(
                f"Monotonous sentence rhythm: sentence length standard deviation is {std_dev:.1f} words "
                f"(minimum required is {thresholds['sentence_std_dev_min']:.1f}). "
                f"Vary sentence pacing with short punchy statements (4-8 words) alongside complex compound explanations (22-35 words)."
            )

        if span < thresholds["sentence_span_min"]:
            violations.append(
                f"Narrow sentence length span: shortest sentence is {stats['min']} words and longest is {stats['max']} words "
                f"(span {span} < required minimum {thresholds['sentence_span_min']} words)."
            )

        if stats["max"] > thresholds["sentence_length_max"]:
            violations.append(
                f"Sentence length exceeds readability threshold: longest sentence has {stats['max']} words "
                f"(maximum allowed is {thresholds['sentence_length_max']} words)."
            )

    # 2. Lexical diversity
    ttr_data = compute_type_token_ratio(full_text)
    if ttr_data["total_tokens"] >= 100:
        if ttr_data["ttr"] < thresholds["type_token_ratio_min"]:
            violations.append(
                f"Low lexical diversity (Type-Token Ratio {ttr_data['ttr']:.2f} < required {thresholds['type_token_ratio_min']:.2f}). "
                f"Reduce repetitive words and vary vocabulary choices."
            )

    # 3. Consecutive sentence opener repetition
    opener_issues = detect_consecutive_opener_repetitions(
        all_sentences,
        max_consecutive=thresholds["max_consecutive_same_opener"],
    )
    for issue in opener_issues:
        violations.append(f"Repetitive sentence starters: {issue}. Vary grammatical structure and sentence openings.")

    return violations
