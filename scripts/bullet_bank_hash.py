"""
bullet_bank_hash.py -- one shared hash function for the bullet bank's text
column, used on both the write side (embed_bullet_bank.py,
cluster_bullet_bank.py) and the read side (orchestrator.py's
mine_bullet_bank()). A staleness check only means something if both sides
compute the hash the same way -- duplicating this in three places would
risk exactly the kind of silent drift this check exists to catch
(B20, phase-9-backlog.md).
"""

import hashlib


def bullets_sha(texts) -> str:
    """SHA256 of the bullet-text column, in row order. Changes if any
    bullet's text changes, or if rows are added/removed/reordered -- so a
    cached embedding matrix computed against a since-edited bank is
    detected instead of row i silently pairing with the wrong bullet."""
    return hashlib.sha256("\n".join(str(t) for t in texts).encode("utf-8")).hexdigest()
