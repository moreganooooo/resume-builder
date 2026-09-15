"""bullet_bank_state.py -- the bullet bank's memory of what was removed on
purpose, plus the near-duplicate check triage uses.

Why this exists: every pipeline stage only compares its own input with its
own output. Deleting a bullet from a downstream file therefore made an
upstream stage see it as unfinished work, and the next run brought it back
-- a retired "96% accuracy" bullet re-merged by Stage 4, a bullet removed
from bullet-bank-audited.csv re-queued by Stage 1. removed-bullets.csv is
the one record every stage consults instead:

- `final_texts` -- the removed bullet's own text. A row whose Bullet Point
  matches is never merged, triaged, or kept in the final bank again.
- `settled_raw` -- final texts plus the raw text each was rewritten FROM.
  Upstream stages (audit, cluster, rewrite) treat these as done, so a
  removed bullet is not re-audited or rewritten into a fresh variant.

The two are separate on purpose: several keepers are often rewritten from
the same raw bullet, and removing one of them must not remove its siblings.

Record removals through remove_bullets.py (or the Bullet Bank menu's
"Remove Bullets"), not by hand-editing the CSVs.
"""

import csv
import datetime
import difflib
import os
import re

REMOVED_FILENAME = "removed-bullets.csv"
FIELDS = [
    "Bullet Point",
    "original_bullet",
    "source_cluster_id",
    "Role / Company",
    "reason",
    "removed_date",
]

# Near-duplicate thresholds for triage, measured against the pairs that
# actually slipped through: same-company rewrites of one achievement ran
# 0.80-0.95 similar, and a shared metric ("$4,000", "3%") with >=0.50
# similarity was a different wording of the same fact every time.
NEAR_DUP_RATIO = 0.80
SHARED_METRIC_RATIO = 0.50


def normalize(text) -> str:
    """Lowercase, collapse whitespace, drop a leading list marker -- the
    audited/cluster files carry "- Built..." where keepers carry "Built..."."""
    text = str(text or "")
    if text.lower() == "nan":
        return ""
    return " ".join(text.strip().lstrip("-*• ").split()).lower()


def removed_path(kb_dir: str) -> str:
    return os.path.join(kb_dir, REMOVED_FILENAME)


class Removed:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.final_texts = {normalize(r.get("Bullet Point")) for r in self.rows} - {""}
        self.settled_raw = self.final_texts | (
            {normalize(r.get("original_bullet")) for r in self.rows} - {""}
        )

    def __len__(self):
        return len(self.rows)

    def blocks(self, text) -> bool:
        """True if a bullet with this text was removed and must stay out."""
        return normalize(text) in self.final_texts

    def settles(self, raw_text) -> bool:
        """True if upstream stages should treat this raw bullet as done."""
        return normalize(raw_text) in self.settled_raw


def load_removed(path: str) -> Removed:
    if not path or not os.path.exists(path):
        return Removed()
    with open(path, newline="", encoding="utf-8") as f:
        return Removed(csv.DictReader(f))


def record_removed(path: str, rows, reason: str) -> int:
    """Appends tombstones for `rows` (dicts with at least "Bullet Point"),
    skipping any already recorded. Returns how many were added."""
    existing = load_removed(path)
    today = str(datetime.date.today())
    new = []
    seen = set(existing.final_texts)
    for row in rows:
        key = normalize(row.get("Bullet Point"))
        if not key or key in seen:
            continue
        seen.add(key)
        new.append(
            {
                "Bullet Point": str(row.get("Bullet Point", "")).strip(),
                "original_bullet": _clean(row.get("original_bullet")),
                "source_cluster_id": _clean(row.get("source_cluster_id")),
                "Role / Company": _clean(row.get("Role / Company")),
                "reason": reason,
                "removed_date": today,
            }
        )
    if not new:
        return 0
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerows(new)
    return len(new)


def _clean(value) -> str:
    text = str(value if value is not None else "").strip()
    return "" if text.lower() == "nan" else text


_METRIC = re.compile(r"\$?\d[\d,]*(?:\.\d+)?(?:\s?%|[kKmMbB]\b|\+)?")


def metric_tokens(text) -> set:
    """Distinctive numbers in a bullet ("$4,000", "3%", "120+"). Bare one-digit
    counts ("2 patents") are too common to identify an achievement."""
    tokens = set()
    for match in _METRIC.findall(str(text or "")):
        token = match.replace(" ", "").rstrip(".,")
        digits = sum(c.isdigit() for c in token)
        if digits >= 2 or "$" in token or "%" in token:
            tokens.add(token.lower())
    return tokens


def near_duplicate_of(text, company, candidates):
    """Returns the first candidate bullet that restates `text` for the same
    company, or None. `candidates` is an iterable of (company, bullet)."""
    norm = normalize(text)
    if not norm:
        return None
    metrics = metric_tokens(text)
    company_key = normalize(company)
    for cand_company, cand_text in candidates:
        cand_key = normalize(cand_company)
        if company_key and cand_key and company_key != cand_key:
            continue
        cand_norm = normalize(cand_text)
        if not cand_norm:
            continue
        matcher = difflib.SequenceMatcher(None, norm, cand_norm)
        # quick_ratio() is an upper bound on ratio() and far cheaper; most
        # pairs in a large bank fail it outright.
        if matcher.quick_ratio() < SHARED_METRIC_RATIO:
            continue
        ratio = matcher.ratio()
        if ratio >= NEAR_DUP_RATIO:
            return cand_text
        if ratio >= SHARED_METRIC_RATIO and metrics & metric_tokens(cand_text):
            return cand_text
    return None
