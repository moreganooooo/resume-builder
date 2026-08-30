"""content_filters.py -- deterministic gates that read the posting's BODY.

Two filters live here, both opt-in and both exclusion-only:

  * language -- the posting is not written in a language the candidate
    reads, so nothing downstream can evaluate it honestly.
  * travel   -- the posting states a travel requirement above the
    candidate's ceiling.

WHY A NEW MODULE RATHER THAN prefilter.py

prefilter.evaluate_preflight_gate() is the obvious home and would have
been the wrong one: it is reached only from batch_sweeper.py, and
batch_sweeper is referenced by nothing but its own test. Adding a filter
there would have been a silent no-op -- the filter would exist, pass its
tests, and never run. These gates are instead wired into
scan_boards._passes_content_filters(), beside the location gate, which
scan_ats.py also routes through.

DESIGN, CARRIED FROM THE LOCATION WORK

Unknown is KEPT, never excluded. A posting too short to classify, or one
that names no travel figure, passes. Surfacing something to eyeball is
cheap; silently dropping a role the candidate wanted is not, because she
never sees it to correct the mistake.

Both filters are inert until their config block exists, so adopting one
is a deliberate act rather than a default that quietly reshapes the
corpus.
"""

from __future__ import annotations

import collections
import re

# --------------------------------------------------------------------------
# Language
# --------------------------------------------------------------------------

# Function-word sets, not vocabulary. Content words vary by industry;
# function words are the highest-frequency tokens in any prose and are
# what makes this work on a 400-token sample with no dependency and no
# model. Deliberately small -- this answers "is this English", not "which
# of the world's languages is this".
_STOPWORDS = {
    "en": {
        "the",
        "and",
        "of",
        "to",
        "in",
        "for",
        "with",
        "you",
        "is",
        "are",
        "will",
        "our",
        "a",
        "on",
        "as",
        "that",
        "we",
        "your",
        "or",
        "be",
        "this",
        "have",
        "from",
        "at",
        "an",
        "by",
    },
    "es": {
        "de",
        "la",
        "el",
        "y",
        "en",
        "los",
        "las",
        "para",
        "con",
        "que",
        "del",
        "una",
        "se",
        "al",
        "por",
        "un",
        "como",
        "su",
        "es",
        "o",
    },
    "fr": {
        "de",
        "la",
        "le",
        "et",
        "les",
        "des",
        "en",
        "pour",
        "du",
        "une",
        "dans",
        "est",
        "sur",
        "au",
        "avec",
        "par",
        "que",
        "vous",
        "ou",
    },
    "de": {
        "und",
        "der",
        "die",
        "das",
        "in",
        "für",
        "mit",
        "den",
        "von",
        "zu",
        "ist",
        "ein",
        "eine",
        "sie",
        "auf",
        "als",
        "im",
        "wir",
        "oder",
    },
    "pt": {
        "de",
        "e",
        "a",
        "o",
        "do",
        "da",
        "em",
        "para",
        "com",
        "os",
        "as",
        "um",
        "uma",
        "que",
        "no",
        "na",
        "se",
        "por",
        "ou",
    },
}

_WORD_RE = re.compile(r"[a-zà-ÿäöüßñáéíóúâêôçãõ']+")

# Below this many tokens the ratio is noise, so the posting is kept.
MIN_TOKENS_FOR_LANGUAGE = 40

# Tokens sampled. The opening of a posting is enough to identify a
# language and caps the cost on a 20,000-character Workday description.
LANGUAGE_SAMPLE_TOKENS = 400


def detect_language(text: str) -> str | None:
    """Best-effort language code, or None when the text is too short.

    None means "could not tell" and must be treated as a pass, never as a
    rejection -- same contract as geo_distance.resolve_location().
    """
    tokens = _WORD_RE.findall((text or "").lower())[:LANGUAGE_SAMPLE_TOKENS]
    if len(tokens) < MIN_TOKENS_FOR_LANGUAGE:
        return None
    counts = collections.Counter(tokens)
    total = len(tokens)
    scores = {
        code: sum(counts[word] for word in words) / total
        for code, words in _STOPWORDS.items()
    }
    best = max(scores, key=lambda code: scores[code])
    # A tie means the evidence does not separate the candidates -- most
    # often a very short or list-heavy posting. Refuse to guess.
    ranked = sorted(scores.values(), reverse=True)
    if len(ranked) > 1 and ranked[0] == ranked[1]:
        return None
    return best


def passes_language_filter(text: str, config: dict | None) -> tuple[bool, str]:
    """Returns (passes, reason). Inert unless `config` names languages.

    Measured on this profile's corpus (2,135 postings with a real
    description): exactly 3 are not English, and the separation is not
    close -- those 3 score an English function-word ratio of 0.003-0.007
    while the 1st PERCENTILE of the whole corpus is 0.138. A 20x gap is
    why this needs no tuned threshold: argmax over the sets above is
    enough, and the failure mode of a near-tie is handled by refusing to
    guess rather than by picking a winner.
    """
    languages = [str(code).lower().strip() for code in (config or []) if code]
    if not languages:
        return True, ""
    detected = detect_language(text)
    if detected is None:
        return True, "language undetermined; kept for review"
    if detected in languages:
        return True, detected
    return False, f"posting appears to be in {detected}"


# --------------------------------------------------------------------------
# Travel
# --------------------------------------------------------------------------

# A stated percentage is the only travel signal precise enough to gate
# on. "Ability to travel" appears on 6.1% of this corpus and quantifies
# nothing -- it covers both one conference a year and three weeks a
# month, so treating it as a rejection would hide roles on a phrase that
# carries no information.
_TRAVEL_PCT_RE = re.compile(
    r"(?:(\d{1,3})\s*%[^.\n]{0,40}?\btravel\b)"
    r"|(?:\btravel\b[^.\n]{0,40}?(\d{1,3})\s*%)",
    re.I,
)

# A percentage near the word "travel" is not always a travel figure.
# Found by reading all 67 distinct matches in this profile's corpus:
#
#   "Budget intra-office travel  Weekly coffee stipend  United States
#    100% medical, dental & vision insurance"
#
# -- a benefits list, which at any ceiling would have rejected the
# posting outright. That is the expensive direction of error, so a
# percentage immediately followed by benefits or work-arrangement
# vocabulary is discarded rather than trusted.
_NOT_A_TRAVEL_PCT = re.compile(
    r"^\s*(medical|dental|vision|health|coverage|covered|paid|match(?:ing)?|"
    r"remote|onsite|on-site|employer|401|premium|salary|equity|bonus|"
    # "of our/the ..." catches benefits language ("100% of our medical
    # premium"), but must NOT catch "60% of the time" -- which is the
    # single most common way a posting states travel in plain English.
    # Found by the settings round-trip test, not by reading.
    r"of\s+(?:our|the)\s+(?!time\b))",
    re.I,
)

# Qualitative phrases, used ONLY when no percentage is stated. Mapped to
# the conservative END of their plausible range: "occasional" is read as
# 10%, so a candidate whose ceiling is 10% keeps those postings and only
# a stricter ceiling drops them.
_TRAVEL_WORDS = (
    (re.compile(r"\bno\s+travel\b|\btravel\s*:\s*none\b|\b0\s*%\s*travel\b", re.I), 0),
    (
        re.compile(
            r"\b(frequent|extensive|significant|heavy|substantial)\s+travel\b", re.I
        ),
        50,
    ),
    (
        re.compile(
            r"\b(occasional|periodic|minimal|limited|infrequent)\s+travel\b", re.I
        ),
        10,
    ),
)


# How far either side of a travel mention to treat as "the same
# sentence". Bounded rather than unbounded because descriptions are often
# bullet lists with no terminating punctuation, where an unbounded window
# would run into an unrelated benefits line.
_SENTENCE_WINDOW = 160

_PCT_RE = re.compile(r"(\d{1,3})\s*%")


def _percentages_in_sentence(text: str, anchor: int) -> list[tuple[str, str]]:
    """Every "N%" in the sentence around `anchor`, each with its trailing text.

    The trailing text is returned so the caller can apply the benefits
    veto without re-deriving offsets.
    """
    start = max(0, anchor - _SENTENCE_WINDOW)
    end = min(len(text), anchor + _SENTENCE_WINDOW)
    window = text[start:end]
    # Trim to the nearest sentence break on each side, when there is one.
    left = max(
        window.rfind(". ", 0, anchor - start), window.rfind("\n", 0, anchor - start)
    )
    if left != -1:
        window = window[left + 1 :]
    right = min(
        (i for i in (window.find(". "), window.find("\n")) if i != -1),
        default=-1,
    )
    if right != -1:
        window = window[:right]
    return [(m.group(1), window[m.end() :]) for m in _PCT_RE.finditer(window)]


def stated_travel_percent(text: str) -> int | None:
    """The travel requirement a posting states, or None if it states none.

    When several figures appear ("10% domestic, 25% international") the
    LARGEST wins: the requirement is the total burden on the candidate,
    and taking the first or the smallest would under-report it.
    """
    text = text or ""
    found = []
    for match in _TRAVEL_PCT_RE.finditer(text):
        # Anchor on the travel-adjacent figure, then widen to the rest of
        # the SENTENCE. "Travel 10% domestic and 25% international" states
        # a 25% requirement, but the 25 sits too far from the word travel
        # for the anchor pattern to reach it -- and reporting 10% there
        # would under-state the burden on exactly the postings a ceiling
        # exists to catch.
        for value_text, tail in _percentages_in_sentence(text, match.start()):
            value = int(value_text)
            if not 0 <= value <= 100:
                continue
            if _NOT_A_TRAVEL_PCT.match(tail):
                continue
            found.append(value)
    if found:
        return max(found)
    for pattern, implied in _TRAVEL_WORDS:
        if pattern.search(text):
            return implied
    return None


def passes_travel_filter(text: str, config: dict | None) -> tuple[bool, str]:
    """Returns (passes, reason). Inert unless `max_travel_percent` is set.

    Measured: 20.7% of postings mention travel at all, 5.0% state a
    percentage, and those percentages spread widely (10, 25, 50, 30, 60
    are the five most common). So a ceiling is a real discriminator and
    not a rounding error -- but it can only act on the 5% that say a
    number, plus the ~2% that use a qualitative phrase. The silent
    majority is kept, by design.
    """
    config = config or {}
    ceiling = config.get("max_travel_percent")
    if ceiling is None:
        return True, ""
    stated = stated_travel_percent(text)
    if stated is None:
        return True, "no travel requirement stated; kept for review"
    if stated <= int(ceiling):
        return True, f"{stated}% travel"
    return False, f"{stated}% travel exceeds {ceiling}% ceiling"


def evaluate_content(text: str, filters: dict | None) -> tuple[bool, str]:
    """Both body gates, in one call. Returns (passes, reason).

    Language is checked first: a posting written in a language the
    candidate does not read should be reported as such rather than as a
    travel mismatch that happens to be detectable through the noise.
    """
    filters = filters or {}
    ok, reason = passes_language_filter(text, filters.get("languages"))
    if not ok:
        return False, reason
    return passes_travel_filter(text, filters)
