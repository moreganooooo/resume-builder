"""embed_verified_skills.py — One-time offline embedder for the Skills Gap
Matrix's calibration reference.

Run this script whenever verified_tools.json changes. It embeds every
verified tool/skill NAME (short phrases, e.g. "Salesforce CRM") using
gemini-embedding-2 and saves:

  profiles/<profile>/knowledge_base/verified_skill_vectors_ge2_d768.npy
      Shape: (N, 768) float32 array, one row per unique tool/skill name.

  profiles/<profile>/knowledge_base/verified_skill_vectors_ge2_d768.meta
      JSON sidecar: model name, dimension, row count, name-list hash.

Why this exists: dashboard_actions._coverage_reference() ranks a JD skill's
best match against the bullet bank by percentile. Ranking a short skill
PHRASE ("Content Strategy") against a reference built from full BULLET
sentences systematically deflates real matches -- bullet-to-bullet
similarity runs high (same writing style/length), so a genuinely strong
0.71 cosine match for a skill phrase can rank at the very bottom of a
0.72-floor bullet-to-bullet distribution and read as 0% coverage. Ranking
against other short skill-phrase embeddings instead is an apples-to-apples
comparison. See dashboard_actions._coverage_reference()'s own docstring.

The .npy file is loaded at runtime by dashboard_actions._coverage_reference().
If it's missing, coverage falls back to the old bullet-to-bullet reference
rather than failing -- this script is an accuracy improvement, not a hard
dependency.

Usage:
    python scripts/embed_verified_skills.py

Dependencies:
    pip install requests numpy python-dotenv
"""

import hashlib
import json
import os
import sys
import time

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import cli_art  # noqa: E402
import profile_paths  # noqa: E402
import theme  # noqa: E402
from atomic_write import atomic_write  # noqa: E402
from embed_bullet_bank import embed_batch  # noqa: E402
from embed_bullet_bank import (  # noqa: E402
    BATCH_SIZE,
    EMBED_DIM,
    EMBED_MODEL,
    EMBED_SLEEP,
)

KB_DIR = profile_paths.kb_dir()
TOOLS_JSON_PATH = os.path.join(KB_DIR, "verified_tools.json")
NPY_PATH = os.path.join(KB_DIR, f"verified_skill_vectors_ge2_d{EMBED_DIM}.npy")
META_PATH = os.path.join(KB_DIR, f"verified_skill_vectors_ge2_d{EMBED_DIM}.meta")
CHECKPOINT_PATH = os.path.join(
    KB_DIR, f"verified_skill_vectors_ge2_d{EMBED_DIM}.checkpoint.npz"
)


_SELF_PROFILE_EMPLOYER = "self / profile"


def _names_sha(names: list) -> str:
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()


def load_verified_skill_names() -> list:
    """Every unique verified tool/skill name, case-insensitively deduped
    and sorted for a stable, reproducible embedding order."""
    with open(TOOLS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    tools = data.get("tools", []) if isinstance(data, dict) else data
    seen = set()
    names = []
    for t in tools or []:
        name = (t.get("name") or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return sorted(names)


def load_anchored_flags(names: list) -> list[bool]:
    """Parallel bool list to `names`: True when at least one entry for that
    tool name has a real employer (i.e. employer is not blank and not the
    scanner-absorbed "Self / Profile" sentinel).  Used to build an
    employer-grounded calibration reference in the skills-gap matrix."""
    with open(TOOLS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    tools = data.get("tools", []) if isinstance(data, dict) else data
    anchored: set[str] = set()
    for t in tools or []:
        name = (t.get("name") or "").strip()
        employer = (t.get("employer") or "").strip()
        if name and employer.lower() not in ("", _SELF_PROFILE_EMPLOYER):
            anchored.add(name.lower())
    return [n.lower() in anchored for n in names]


def load_checkpoint(expected_sha: str):
    if os.path.exists(CHECKPOINT_PATH):
        data = np.load(CHECKPOINT_PATH, allow_pickle=False)
        saved_sha = str(data["names_sha"]) if "names_sha" in data else None
        if saved_sha != expected_sha:
            cli_art.console.print(
                f"   {theme.colorize_icon('warning')}  Verified skills changed since this "
                "checkpoint was saved -- discarding stale progress and starting over.",
                soft_wrap=True,
            )
            os.remove(CHECKPOINT_PATH)
            return [], 0
        vectors = list(data["vectors"])
        start_index = int(data["next_index"])
        cli_art.console.print(
            f"   {theme.colorize_icon('resume')}  Resuming from checkpoint: "
            f"{start_index} skill names already embedded.",
            soft_wrap=True,
        )
        return vectors, start_index
    return [], 0


def save_checkpoint(vectors: list, next_index: int, names_sha_value: str):
    np.savez(
        CHECKPOINT_PATH,
        vectors=np.array(vectors, dtype=np.float32),
        next_index=np.array(next_index),
        names_sha=np.array(names_sha_value),
    )


def main():
    if not os.path.exists(TOOLS_JSON_PATH):
        raise FileNotFoundError(f"Verified tools file not found: {TOOLS_JSON_PATH}")

    names = load_verified_skill_names()
    anchored = load_anchored_flags(names)
    total = len(names)
    cli_art.console.print(
        f"{theme.colorize_icon('bullet_bank')} Loaded {total} unique verified skill/tool names",
        soft_wrap=True,
    )
    current_sha = _names_sha(names)

    vectors, start_index = load_checkpoint(current_sha)

    remaining = total - start_index
    n_batches = (remaining + BATCH_SIZE - 1) // BATCH_SIZE
    est_secs = n_batches * EMBED_SLEEP
    cli_art.console.print(
        f"{theme.colorize_icon('build')} Embedding with {EMBED_MODEL} @ {EMBED_DIM}d",
        soft_wrap=True,
    )
    cli_art.cli_info(
        f"Batch size: {BATCH_SIZE} names/call -> {n_batches} API calls remaining"
    )
    cli_art.cli_info(f"Estimated time: ~{est_secs // 60}m {est_secs % 60}s")

    batch_num = 0
    for batch_start in range(start_index, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch = names[batch_start:batch_end]
        batch_num += 1

        cli_art.cli_info(
            f"Batch {batch_num}/{n_batches}  [names {batch_start+1}-{batch_end}/{total}]  "
            f"{batch[0][:60]}"
        )

        vecs = embed_batch(batch)
        vectors.extend(vecs)
        save_checkpoint(vectors, batch_end, current_sha)

        if batch_end < total:
            time.sleep(EMBED_SLEEP)

    matrix = np.array(vectors, dtype=np.float32)
    np.save(NPY_PATH, matrix)
    cli_art.console.print(
        f"\n{theme.colorize_icon('success')} Saved {matrix.shape} vector matrix -> {NPY_PATH}",
        soft_wrap=True,
    )

    meta = {
        "model": EMBED_MODEL,
        "dim": EMBED_DIM,
        "rows": total,
        "source": TOOLS_JSON_PATH,
        "names_sha": current_sha,
        "anchored": anchored,
    }
    with atomic_write(META_PATH) as f:
        json.dump(meta, f, indent=2)
    cli_art.console.print(
        f"{theme.colorize_icon('save')} Saved metadata sidecar -> {META_PATH}",
        soft_wrap=True,
    )

    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)
        cli_art.cli_info("Checkpoint file removed.")

    cli_art.console.print(
        f"\n{theme.colorize_icon('complete')} Done. Run this script again whenever "
        "verified_tools.json changes.",
        soft_wrap=True,
    )


if __name__ == "__main__":
    main()
