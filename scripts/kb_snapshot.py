"""kb_snapshot.py -- a rotating pre-run snapshot of the knowledge base.

B13: atomic_write.py closes the truncate-at-open window a single KB write
opens, but that's not a backup -- a KB writer with a real bug, a bad
merge, or a mistaken hand-edit can still write valid-looking garbage over
good data, and there was previously no recovery path at all (no git
history -- profiles/<name>/ is gitignored on purpose per CLAUDE.md; no
.bak; Syncthing propagates corruption instead of guarding against it).

snapshot_kb() is meant to be called once, at the top of a real pipeline
run (orchestrator.run_pipeline()), before any JD is processed --
"pre-run," not "pre-write": snapshotting before every individual KB write
(score_keeper_gems.py alone rewrites its target ~170 times in one run)
would be its own source of slowdown and disk churn for no added safety
over a single copy taken before the run starts.
"""

import os
import shutil
import time

import profile_paths

KEEP = 5


def snapshot_kb(profile: str = None, keep: int = KEEP) -> str | None:
    """Copies every top-level file in profiles/<profile>/knowledge_base/
    into a new timestamped subdirectory of profile_paths.kb_snapshot_dir(),
    then deletes the oldest snapshots past `keep`. Returns the new
    snapshot's directory, or None if the KB directory doesn't exist yet
    (a profile that hasn't been bootstrapped has nothing to snapshot).

    Only top-level files are copied -- knowledge_base/archive/ and
    knowledge_base/bootstrap/ are subdirectories of process residue and
    in-progress bootstrap state, not the KB itself, mirroring
    KB_ALLOWLIST/check_kb_allowlist() treating the KB as a flat file
    listing rather than a tree."""
    kb_dir = profile_paths.kb_dir(profile)
    if not os.path.isdir(kb_dir):
        return None

    snapshot_root = profile_paths.kb_snapshot_dir(profile)
    dest = os.path.join(snapshot_root, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(dest, exist_ok=True)

    for name in os.listdir(kb_dir):
        src = os.path.join(kb_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dest, name))

    existing = sorted(
        d
        for d in os.listdir(snapshot_root)
        if os.path.isdir(os.path.join(snapshot_root, d))
    )
    for stale in existing[:-keep] if keep > 0 else existing:
        shutil.rmtree(os.path.join(snapshot_root, stale))

    return dest
