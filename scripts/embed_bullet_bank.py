"""embed_bullet_bank.py — One-time offline embedder.

Run this script whenever bullet-bank-keepers-audited.csv is updated.
It embeds every bullet using gemini-embedding-2 and saves:

  profiles/<profile>/knowledge_base/bullet_vectors_ge2_d768.npy
      Shape: (N, 768) float32 array, one row per bullet.

  profiles/<profile>/knowledge_base/bullet_vectors_ge2_d768.meta
      JSON sidecar: model name, dimension, row count, CSV path.

The .npy file is loaded at runtime by mine_bullet_bank() in
orchestrator.py for cosine pre-filtering. Re-run this script if you
add or change bullets — the .npy will be regenerated from scratch.

Speed:
    Uses batchEmbedContents (up to 20 bullets per API call) instead of
    embedContent (1 bullet per call). At 15 RPM free-tier limit:
      Before: 1209 calls → ~80 minutes
      After:  ~61 calls  → ~20 minutes (EMBED_SLEEP = 20s between batches)

Resume from checkpoint:
    If interrupted, saves a checkpoint after every batch.
    Re-run the same command — it picks up where it left off.
    Checkpoint is deleted automatically on successful completion.

Usage:
    python scripts/embed_bullet_bank.py

Rate limiting:
    gemini-embedding-2 free tier: 15 RPM / 1500 RPD.
    This script sleeps 4s between batches → safely under 15 RPM.

Dependencies:
    pip install requests numpy pandas python-dotenv
"""

import json
import os
import sys
import time

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

# --- PATH SETUP ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
from typing import Any, cast

import cli_art
import profile_paths  # noqa: E402
import theme
from atomic_write import atomic_write  # noqa: E402
from bullet_bank_hash import bullets_sha  # noqa: E402

load_dotenv(profile_paths.env_path(), override=True)

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
AUTH_HEADERS = {"x-goog-api-key": API_KEY}

EMBED_MODEL = "gemini-embedding-2"
# Separate per-model quota, so it absorbs Embedding 2's rate limits -- but
# only against its own index (index_paths()); the two models' vectors are
# not comparable. Build it with: embed_bullet_bank.py --model gemini-embedding-001
BACKUP_EMBED_MODEL = "gemini-embedding-001"
MODEL_FAMILY = {EMBED_MODEL: "ge2", BACKUP_EMBED_MODEL: "ge1"}
EMBED_DIM = 768  # sweet spot for text-only
BATCH_SIZE = 20  # batchEmbedContents supports up to ~20 requests per call
EMBED_SLEEP = (
    0
    if (
        os.environ.get("CI") == "true"
        or os.environ.get("RESUME_BUILDER_TESTING") == "1"
    )
    else 20
)  # seconds between batch calls → ~15 RPM
MAX_RETRIES = 4

KB_DIR = profile_paths.kb_dir()
CSV_PATH = os.path.join(KB_DIR, "bullet-bank-keepers-audited.csv")
NPY_PATH = os.path.join(KB_DIR, f"bullet_vectors_ge2_d{EMBED_DIM}.npy")
META_PATH = os.path.join(KB_DIR, f"bullet_vectors_ge2_d{EMBED_DIM}.meta")
CHECKPOINT_PATH = os.path.join(
    KB_DIR, f"bullet_vectors_ge2_d{EMBED_DIM}.checkpoint.npz"
)


def index_paths(kb_dir: str, model: str | None = None) -> tuple:
    """(npy, meta, checkpoint) paths for `model`'s bullet-bank index.

    Vectors from different embedding models live in different spaces, so
    each model keeps its own index and a query must only ever be compared
    against the index built by the same model. The primary model keeps the
    historical ge2 file names."""
    family = MODEL_FAMILY[model or EMBED_MODEL]
    base = os.path.join(kb_dir, f"bullet_vectors_{family}_d{EMBED_DIM}")
    return f"{base}.npy", f"{base}.meta", f"{base}.checkpoint.npz"


def backup_index_for(
    kb_dir: str, bullets_sha_value: str | None = None, n_rows: int | None = None
):
    """The backup model's bullet-bank matrix, or None when it is missing or
    was built from a different bank (content hash / row count). A query
    embedded with BACKUP_EMBED_MODEL may only ever be compared against this."""
    npy, meta_path, _ = index_paths(kb_dir, BACKUP_EMBED_MODEL)
    if not (os.path.exists(npy) and os.path.exists(meta_path)):
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        matrix = np.load(npy)
    except Exception:
        return None
    if bullets_sha_value is not None and meta.get("bullets_sha") != bullets_sha_value:
        return None
    if n_rows is not None and len(matrix) != n_rows:
        return None
    return matrix if matrix.ndim == 2 else None


def index_is_current(npy_path: str, meta_path: str, sha: str, n_rows: int) -> bool:
    """True when the index at these paths was built from exactly this bank
    (content hash and row count), so rebuilding it would spend API calls to
    reproduce the same vectors. Judged by content, never mtime: a column-only
    edit to the keepers CSV bumps its mtime without changing a bullet."""
    if not (os.path.exists(npy_path) and os.path.exists(meta_path)):
        return False
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        return False
    return cast("bool", meta.get("bullets_sha") == sha and meta.get("rows") == n_rows)


def embed_batch(
    texts: list, model: str | None = None, max_retries: int | None = None
) -> list:
    """Call batchEmbedContents for a list of strings. Returns list of float lists.

    `model` defaults to EMBED_MODEL; BACKUP_EMBED_MODEL has its own quota and
    its own index (see index_paths()). `max_retries` defaults to MAX_RETRIES
    -- callers that have a backup to fall back on pass a smaller number
    rather than waiting out the full ~150s ladder."""
    model = model or EMBED_MODEL
    retries = max_retries or MAX_RETRIES
    url = f"{BASE_URL}/{model}:batchEmbedContents"
    requests_payload = [
        {
            "model": f"models/{model}",
            "content": {"parts": [{"text": t}]},
            "outputDimensionality": EMBED_DIM,
            "taskType": "RETRIEVAL_DOCUMENT",
        }
        for t in texts
    ]
    body: dict[str, Any] = {"requests": requests_payload}

    # Same test-network chokepoint every gemini_client call goes through.
    # This module builds its own headers, so it slipped past that guard: a
    # test whose mock missed (test_job_compare, 2026-09-13) re-embedded the
    # operator's real 827-bullet bank with live, rate-limited API calls.
    import gemini_client

    if gemini_client._blocked_under_test():
        raise gemini_client.TestNetworkBlockedError(
            "A test tried to call the live embedding API. Mock requests.post for "
            f"this test, or set {gemini_client._TEST_NETWORK_ENV}=1 if it genuinely "
            "needs the network."
        )

    # The key is read per call, like every gemini_client request: the
    # module-level AUTH_HEADERS froze whatever key was in .env at import, so
    # a long-running job (a 374-role re-score, 2026-09-13) kept embedding on
    # a rate-limited old key for hours after the key had been switched.
    key_switches = 0
    for attempt in range(retries + len(gemini_client.api_keys())):
        if attempt - key_switches >= retries:
            break
        key = gemini_client._get_api_key(model) or API_KEY
        headers = {"x-goog-api-key": key or ""}
        resp = requests.post(url, json=body, headers=headers, timeout=120)
        if resp.status_code == 429:
            if gemini_client.mark_key_rate_limited(key, model):
                key_switches += 1
                cli_art.cli_warning("Rate limited -- switching to a backup API key.")
                continue
            wait = 10 * (2**attempt)
            cli_art.cli_warning(
                f"Rate limited. Waiting {wait}s (attempt {attempt+1}/{retries})..."
            )
            time.sleep(wait)
            continue
        resp.raise_for_status()
        embeddings = resp.json().get("embeddings", [])
        vecs = [e["values"] for e in embeddings]
        if len(vecs) != len(texts):
            # A response with a missing/short "embeddings" key would
            # otherwise silently contribute fewer rows than sent, shifting
            # every subsequent bullet's vector out of alignment with its
            # CSV row (B20, phase-9-backlog.md).
            raise RuntimeError(
                f"embed_batch: sent {len(texts)} texts but got {len(vecs)} embeddings back "
                "-- refusing to silently misalign the vector matrix."
            )
        return vecs

    raise RuntimeError(f"embed_batch failed after {retries} retries ({model}).")


def load_checkpoint(expected_sha: str):
    """Load saved vectors and resume index from checkpoint file if it
    exists and its bullet-text hash still matches the current bank --
    editing the bank during a rate-limit pause (a multi-hour stall
    invites exactly that) would otherwise resume with row i of the
    checkpointed matrix no longer corresponding to row i of the CSV,
    permanently and silently (B20, phase-9-backlog.md)."""
    if os.path.exists(CHECKPOINT_PATH):
        data = np.load(CHECKPOINT_PATH, allow_pickle=False)
        saved_sha = str(data["bullets_sha"]) if "bullets_sha" in data else None
        if saved_sha != expected_sha:
            cli_art.console.print(
                f"   {theme.colorize_icon('warning')}  Bullet bank changed since this checkpoint was saved "
                "-- discarding stale progress and starting over.",
                soft_wrap=True,
            )
            os.remove(CHECKPOINT_PATH)
            return [], 0
        vectors = list(data["vectors"])
        start_index = int(data["next_index"])
        cli_art.console.print(
            f"   {theme.colorize_icon('resume')}  Resuming from checkpoint: {start_index} bullets already embedded.",
            soft_wrap=True,
        )
        return vectors, start_index
    return [], 0


def save_checkpoint(vectors: list, next_index: int, bullets_sha_value: str):
    """Save current progress to checkpoint file."""
    np.savez(
        CHECKPOINT_PATH,
        vectors=np.array(vectors, dtype=np.float32),
        next_index=np.array(next_index),
        bullets_sha=np.array(bullets_sha_value),
    )


def main(model: str | None = None):
    # A backup-model build writes its own ge1 index (and checkpoint), never
    # the primary ge2 files -- see index_paths().
    global NPY_PATH, META_PATH, CHECKPOINT_PATH
    model = model or EMBED_MODEL
    if model != EMBED_MODEL:
        NPY_PATH, META_PATH, CHECKPOINT_PATH = index_paths(KB_DIR, model)

    if not API_KEY:
        raise EnvironmentError("GEMINI_API_KEY / GOOGLE_API_KEY not set in .env")

    cli_art.detail(
        "Using API key from environment (value redacted).", level=cli_art.VERBOSE
    )

    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Bullet bank not found: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)

    bullet_col = None
    for candidate in ("Bullet Point", "bullet", "achievement"):
        if candidate in df.columns:
            bullet_col = candidate
            break
    if bullet_col is None:
        raise ValueError(f"No known bullet column found. Columns: {list(df.columns)}")
    # fillna("") before astype(str), not after -- orchestrator.py's
    # mine_bullet_bank() hashes this same column via .fillna(""), and the
    # two sides must agree on NaN handling or a bank with no real content
    # change at all would still produce a hash mismatch ("nan" vs "").
    bullets = df[bullet_col].fillna("").astype(str).tolist()

    total = len(bullets)
    cli_art.console.print(
        f"{theme.colorize_icon('bullet_bank')} Loaded {total} bullets from {CSV_PATH}",
        soft_wrap=True,
    )
    current_sha = bullets_sha(bullets)

    if index_is_current(NPY_PATH, META_PATH, current_sha, total):
        cli_art.cli_info(f"{model} index already matches this bank -- skipping.")
        return

    vectors, start_index = load_checkpoint(current_sha)

    remaining = total - start_index
    n_batches = (remaining + BATCH_SIZE - 1) // BATCH_SIZE
    est_secs = n_batches * EMBED_SLEEP
    cli_art.console.print(
        f"{theme.colorize_icon('build')} Embedding with {model} @ {EMBED_DIM}d",
        soft_wrap=True,
    )
    cli_art.cli_info(
        f"Batch size: {BATCH_SIZE} bullets/call → {n_batches} API calls remaining"
    )
    cli_art.cli_info(f"Estimated time: ~{est_secs // 60}m {est_secs % 60}s")

    batch_num = 0
    for batch_start in range(start_index, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch = bullets[batch_start:batch_end]
        batch_num += 1

        cli_art.cli_info(
            f"Batch {batch_num}/{n_batches}  [bullets {batch_start+1}–{batch_end}/{total}]  "
            f"{batch[0][:60]}{'...' if len(batch[0]) > 60 else ''}"
        )

        vecs = embed_batch(batch, model=model)
        vectors.extend(vecs)

        # Checkpoint after every batch
        save_checkpoint(vectors, batch_end, current_sha)

        if batch_end < total:
            time.sleep(EMBED_SLEEP)

    # All done — write final outputs
    matrix = np.array(vectors, dtype=np.float32)  # shape: (N, EMBED_DIM)
    np.save(NPY_PATH, matrix)
    cli_art.console.print(
        f"\n{theme.colorize_icon('success')} Saved {matrix.shape} vector matrix → {NPY_PATH}",
        soft_wrap=True,
    )

    meta = {
        "model": model,
        "dim": EMBED_DIM,
        "rows": total,
        "csv": CSV_PATH,
        "bullet_col": bullet_col or "(stringified row)",
        "bullets_sha": current_sha,
    }
    with atomic_write(META_PATH) as f:
        json.dump(meta, f, indent=2)
    cli_art.console.print(
        f"{theme.colorize_icon('save')} Saved metadata sidecar → {META_PATH}",
        soft_wrap=True,
    )

    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)
        cli_art.cli_info("Checkpoint file removed.")

    cli_art.console.print(
        f"\n{theme.colorize_icon('complete')} Done. Run this script again whenever bullet-bank-keepers-audited.csv changes.",
        soft_wrap=True,
    )


def cli(argv: list | None = None) -> int:
    """Command-line entry point -- what the Bullet Bank menu's "Embed" stage
    and bootstrap_bullet_bank's pipeline both run. By default it builds the
    primary index and then the backup model's index, so the backup never
    silently goes stale after a bank edit (a stale backup is skipped at match
    time, which quietly removes the fallback). The backup is best-effort: if
    it fails -- say its own quota is spent -- this warns and still succeeds,
    since real builds need only the primary index. `--primary-only` skips
    it; `--model` builds exactly one index."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Embed the active profile's bullet bank."
    )
    parser.add_argument(
        "--model",
        choices=[EMBED_MODEL, BACKUP_EMBED_MODEL],
        help="Build only this model's index.",
    )
    parser.add_argument(
        "--primary-only",
        action="store_true",
        help="Skip the backup model's index.",
    )
    args = parser.parse_args(argv)

    if args.model:
        main(model=args.model)
        return 0

    main(model=EMBED_MODEL)
    if args.primary_only:
        return 0
    cli_art.console.print(
        f"\n{theme.colorize_icon('build')} Building the backup index ({BACKUP_EMBED_MODEL}) "
        "-- used automatically when the primary model is rate-limited.",
        soft_wrap=True,
    )
    try:
        main(model=BACKUP_EMBED_MODEL)
    except Exception as e:
        cli_art.cli_warning(
            f"Backup index not built ({e}). Resume builds still work; re-run this "
            f"step later, or `embed_bullet_bank.py --model {BACKUP_EMBED_MODEL}`, "
            "to restore the fallback."
        )
    return 0


if __name__ == "__main__":
    sys.exit(cli())
