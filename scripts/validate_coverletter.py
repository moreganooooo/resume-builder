"""
validate_coverletter.py — Deterministic Python checks for cover letter
output, run after every Gemini call in
ResumeEngine.build_tailored_coverletter().

Mirrors validate_resume.py's conventions (word-boundary forbidden-phrase
matching, a flat list of violation strings) but scoped to what actually
applies to a cover letter -- no bullet/skills/tagline checks exist here,
since a cover letter has none of those structures.

B14: _check_kb_traceability() is the one exception -- a factual-grounding
check with no resume-side analog, added because the cover letter is the
one document generated as free prose with no corpus constraint of its own
(see resume-engine/prompts/tailor_coverletter.md and orchestrator.py's
build_tailored_coverletter()). Proven live: a JD `description` field
carrying an injected "SYSTEM INSTRUCTION OVERRIDE" block got a fabricated
"10 years of professional Rust systems programming experience ... at
Stripe (2019-2024), cutting p99 latency 92%" woven into the letter's first
paragraph, and none of the three checks below caught it.
"""

import re

import profile_paths
import voice_metrics

# Numbers with a distinctive suffix (percentage, dollar amount, or K/M
# scale), an explicit "N years/yrs" experience claim, or a year range
# (e.g. a fabricated employment span) -- the same category of claim
# validate_resume.py's _extract_metric_signatures() already treats as
# checkable, restricted here to markers specific enough that a real KB
# corpus containing them by coincidence is unlikely. Deliberately not a
# bare `\d+` -- that would flag every ordinary number and drown any real
# violation in noise.
_METRIC_PATTERN = re.compile(r"\$?\d[\d,.]*\s?(?:%|percent\b|k\b|m\b)", re.IGNORECASE)
_YEARS_EXPERIENCE_PATTERN = re.compile(r"\b\d+\+?\s?(?:years?|yrs?)\b", re.IGNORECASE)
_YEAR_RANGE_PATTERN = re.compile(r"\b(?:19|20)\d{2}\s?[-–]\s?(?:19|20)\d{2}\b")


def _check_forbidden_phrases(cover_letter_data: dict, style_rules: dict) -> list[str]:
    violations = []
    phrases = [p.lower() for p in style_rules.get("forbidden_phrases", [])]
    haystacks = (
        [cover_letter_data.get("greeting", "")]
        + cover_letter_data.get("body_paragraphs", [])
        + [cover_letter_data.get("sign_off", "")]
    )
    for text in haystacks:
        lowered = text.lower()
        for phrase in phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", lowered):
                violations.append(f"Forbidden phrase '{phrase}' found in: {text!r}")
    return violations


def _check_paragraph_count(cover_letter_data: dict) -> list[str]:
    count = len(cover_letter_data.get("body_paragraphs", []))
    if count < 2 or count > 4:
        return [f"Expected 2-4 body paragraphs, got {count}"]
    return []


# Mirrors tailor_coverletter.md's own "250-350 words total" benchmark,
# with a practical 240-360 tolerance band to avoid spurious retries
# on high-quality letters that are within a few words of the boundaries.
_MIN_WORD_COUNT = 240
_MAX_WORD_COUNT = 360


def _check_word_count(cover_letter_data: dict) -> list[str]:
    total_words = sum(
        len(p.split()) for p in cover_letter_data.get("body_paragraphs", [])
    )
    if total_words < _MIN_WORD_COUNT or total_words > _MAX_WORD_COUNT:
        return [
            f"Expected {_MIN_WORD_COUNT}-{_MAX_WORD_COUNT} words across body paragraphs, got {total_words}"
        ]
    return []


def _third_person_terms() -> list[str]:
    """Terms that would indicate the letter slipped into third person about
    the candidate themself: their full name, first name, and -- only if
    the profile explicitly configures candidate.pronouns: -- their
    pronouns. Pronouns are never guessed or defaulted (see CLAUDE.md-level
    guidance against inferring pronouns from a name); a profile that
    hasn't set them just gets a name-only check rather than a wrong
    guess."""
    data = profile_paths.profile_yaml()
    candidate = data.get("candidate") or {}
    full_name = candidate.get("full_name", "")
    terms = [t for t in (full_name, full_name.split()[0] if full_name else "") if t]
    terms += candidate.get("pronouns") or []
    return terms


# A quoted span of 8+ characters, straight or curly quotes.
_QUOTED_SPAN = re.compile(r'"[^"\n]{8,}"|“[^”\n]{8,}”')


def _check_third_person_slip(cover_letter_data: dict) -> list[str]:
    # Blunt heuristic, not a perfect one: a first-person letter addressed
    # generically to "Hiring Team" shouldn't ever need to reference a third
    # party by name/pronoun, so this is a reasonable v1 check -- but it would
    # false-positive on a legitimate sentence naming someone else (e.g. "I
    # worked with the hiring manager and her team"). Not a concern for this
    # pass since letters don't name third parties without company research.
    terms = _third_person_terms()
    if not terms:
        return []
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.IGNORECASE
    )
    violations = []
    haystacks = (
        [("greeting", cover_letter_data.get("greeting", ""))]
        + [
            (f"body_paragraphs[{i}]", p)
            for i, p in enumerate(cover_letter_data.get("body_paragraphs", []))
        ]
        + [("sign_off", cover_letter_data.get("sign_off", ""))]
    )
    for field_name, text in haystacks:
        # A quoted recommendation ("Morgan got it done" -- Ed Roche) names the
        # candidate by design; that is a reference speaking, not the letter
        # slipping into third person. Only text outside quotation marks counts.
        text = _QUOTED_SPAN.sub(" ", text)
        if pattern.search(text):
            violations.append(
                f"Third-person self-reference found in {field_name}: {text!r}"
            )
    return violations


def _extract_grounding_claims(text: str) -> list[str]:
    """Pulls out the kind of specific, checkable claim a fabricated
    credential tends to carry. Not exhaustive -- a fabricated company name
    or skill with no attached number slips past this particular check --
    but it catches exactly the markers the proven B14 injection payload
    carried ("10 years", "92%", "(2019-2024)")."""
    claims: list[str] = []
    for pattern in (_METRIC_PATTERN, _YEARS_EXPERIENCE_PATTERN, _YEAR_RANGE_PATTERN):
        claims.extend(m.group(0) for m in pattern.finditer(text))
    return claims


def _check_kb_traceability(cover_letter_data: dict, kb_corpus: str) -> list[str]:
    """Every specific numeric/duration claim in the letter body must trace
    back to the knowledge base corpus the model was actually grounded in
    (ResumeEngine.build_audit_static_prefix()'s output -- the same text
    already in the system prompt telling the model not to invent facts
    outside it). A claim that appears nowhere in that corpus is exactly
    the shape of a fabrication the JD talked the model into asserting,
    since real facts about the candidate all come from the KB, not the JD.

    Skipped entirely when kb_corpus is empty -- callers outside the
    JD-injection threat model (e.g. polish.py, which edits an existing
    letter from a Morgan-typed instruction, never a JD) don't have a
    corpus to check against and shouldn't get spurious violations.

    Blunt heuristic, not a perfect one (see _extract_grounding_claims):
    a coincidental match (a real KB fact that happens to share a number
    with a fabricated one) is a false negative, and a legitimate restated
    JD number ("this role wants 5+ years...") with no numeric counterpart
    in the KB is a false positive. Reasonable v1 check, same trade-off
    this file already accepts in _check_third_person_slip."""
    if not kb_corpus:
        return []
    violations = []
    corpus_lower = kb_corpus.lower()
    for i, paragraph in enumerate(cover_letter_data.get("body_paragraphs", [])):
        for claim in _extract_grounding_claims(paragraph):
            if claim.lower() not in corpus_lower:
                violations.append(
                    f"Unverifiable claim {claim!r} in body_paragraphs[{i}] does not "
                    f"appear anywhere in the knowledge base: {paragraph!r}"
                )
    return violations


_CLICHED_OPENER_PATTERNS = [
    re.compile(r"\bi\s+am\s+writing\s+to\b", re.IGNORECASE),
    re.compile(r"\bi\s+was\s+excited\s+to\b", re.IGNORECASE),
    re.compile(r"\bi\s+am\s+thrilled\s+to\b", re.IGNORECASE),
    re.compile(r"\bmy\s+name\s+is\b", re.IGNORECASE),
    re.compile(r"\bplease\s+accept\s+this\b", re.IGNORECASE),
    re.compile(r"\bwith\s+great\s+enthusiasm\b", re.IGNORECASE),
]


def _check_filler_lines(cover_letter_data: dict) -> list[str]:
    """Sentences that could sit in anyone's letter (filler_phrases.py)."""
    import filler_phrases

    return [
        f"Generic filler line: {sentence!r} -- replace it with a specific fact "
        f"from the candidate's background tied to this role, or cut it."
        for paragraph in cover_letter_data.get("body_paragraphs", []) or []
        for sentence in filler_phrases.filler_sentences(paragraph)
    ]


def _check_role_title(cover_letter_data: dict, role_title: str) -> list[str]:
    """The role being applied for must be named in the first paragraph."""
    title = " ".join(str(role_title or "").lower().split())
    if not title:
        return []
    paragraphs = cover_letter_data.get("body_paragraphs") or []
    first = " ".join(str(paragraphs[0] if paragraphs else "").lower().split())
    if title in first:
        return []
    return [
        f"The first paragraph must name the role being applied for, word for word: "
        f"'{role_title}'. Work it into the first or second sentence."
    ]


def _check_cliched_openers(cover_letter_data: dict) -> list[str]:
    paragraphs = cover_letter_data.get("body_paragraphs", [])
    if not paragraphs:
        return []
    first_para = paragraphs[0].strip()
    prefix = first_para[:120].lower()
    violations = []
    for pattern in _CLICHED_OPENER_PATTERNS:
        if pattern.search(prefix):
            violations.append(
                f"Cover letter uses clichéd/passive opener pattern near the beginning of the first paragraph: {first_para!r}"
            )
    return violations


# Similarity cutoffs are per embedding model: gemini-embedding-001 scores the
# same text pairs higher across the board. Measured 2026-09-13 on an
# 845-bullet bank, 0.60 on the primary model is the 1.2th percentile of
# bullet-pair similarity; the same percentile on the backup is 0.717.
GROUNDING_THRESHOLD = 0.60
GROUNDING_THRESHOLD_BACKUP = 0.72


def _check_semantic_grounding(
    cover_letter_data: dict,
    keeper_bullets: list[str],
    keeper_embs,
    keeper_embs_backup=None,
) -> list[str]:
    """
    Rigorously checks each sentence of the cover letter that makes a professional claim,
    computing its cosine similarity against the keeper bullets embeddings.
    If the maximum similarity score to any real candidate achievement is < 0.60,
    the sentence is flagged as an ungrounded hallucination.
    """
    if not keeper_bullets or keeper_embs is None:
        return []
    import numpy as np
    from gemini_client import GeminiClient

    violations = []

    # Conversational or transitional phrases that can safely be bypassed
    transitional_keywords = [
        "apply",
        "excited",
        "enthusiasm",
        "express my interest",
        "look forward",
        "thank you",
        "for your consideration",
        "resume",
        "please accept",
        "dear",
        "sincerely",
        "opportunity",
        "role",
        "position",
        "seeking",
        "qualified",
        "background",
    ]

    # Precise sentence splitter regex
    sentence_splitter = re.compile(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s")

    for p_idx, paragraph in enumerate(cover_letter_data.get("body_paragraphs", [])):
        sentences = [s.strip() for s in sentence_splitter.split(paragraph) if s.strip()]
        for s_idx, sentence in enumerate(sentences):
            # Only check substantive sentences capable of conveying professional claims
            if len(sentence) < 40:
                continue

            lowered = sentence.lower()
            if any(kw in lowered for kw in transitional_keywords):
                continue

            # Compute sentence embedding via sharing the main client
            emb = GeminiClient.embed(sentence)
            matrix, threshold = keeper_embs, GROUNDING_THRESHOLD
            if emb is None and keeper_embs_backup is not None:
                # Primary model unavailable: the backup model, against ITS OWN
                # index and at its own cutoff (the two are not comparable).
                try:
                    import embed_bullet_bank

                    emb = embed_bullet_bank.embed_batch(
                        [sentence],
                        model=embed_bullet_bank.BACKUP_EMBED_MODEL,
                        max_retries=2,
                    )[0]
                    matrix, threshold = keeper_embs_backup, GROUNDING_THRESHOLD_BACKUP
                except Exception:
                    emb = None
            if emb is None or len(emb) != matrix.shape[1]:
                continue

            s_vec = np.array(emb, dtype=np.float32)
            s_norm = np.linalg.norm(s_vec)
            if s_norm > 0:
                s_vec = s_vec / s_norm

            # Normalize keeper embeddings matrix
            embs_norm = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
            sims = embs_norm @ s_vec
            max_sim = float(np.max(sims))
            best_idx = int(np.argmax(sims))

            # 0.60 is the state-of-the-art threshold representing high similarity for d=768
            if max_sim < threshold:
                violations.append(
                    f"Ungrounded semantic claim in body_paragraphs[{p_idx}]: {sentence!r} "
                    f"(Highest similarity to keeper bank was only {max_sim:.2f}; "
                    f"best candidate: {keeper_bullets[best_idx]!r})"
                )
    return violations


def _check_voice_metrics(
    cover_letter_data: dict, voice_rules: dict | None = None
) -> list[str]:
    if not voice_rules:
        return []
    return voice_metrics.analyze_voice_metrics(cover_letter_data, rules=voice_rules)


def validate(
    cover_letter_data: dict,
    style_rules: dict,
    kb_corpus: str = "",
    keeper_bullets: list[str] = None,
    keeper_embs=None,
    voice_rules: dict | None = None,
    keeper_embs_backup=None,
    role_title: str = "",
) -> list[str]:
    violations = []
    violations.extend(_check_role_title(cover_letter_data, role_title))
    violations.extend(_check_filler_lines(cover_letter_data))
    violations.extend(_check_forbidden_phrases(cover_letter_data, style_rules))
    violations.extend(_check_paragraph_count(cover_letter_data))
    violations.extend(_check_word_count(cover_letter_data))
    violations.extend(_check_third_person_slip(cover_letter_data))
    violations.extend(_check_kb_traceability(cover_letter_data, kb_corpus))
    violations.extend(_check_cliched_openers(cover_letter_data))
    violations.extend(
        _check_semantic_grounding(
            cover_letter_data, keeper_bullets, keeper_embs, keeper_embs_backup
        )
    )
    violations.extend(_check_voice_metrics(cover_letter_data, voice_rules))
    return violations
