# Phase 6 — Bullet-bank curation pipeline

Run 2026-08-05, Opus 5. Reviewed the 15 scripts listed under Phase 6 in
`PLAN.md`. No code changed.

**Unowned files claimed:** none. All 15 were already listed.

**Method note.** Findings 1 and the header mismatch behind it are
runtime-proven in a sandboxed copy of the real KB (scratchpad, real headers
+ real rows), not inferred from reading. Findings 3–7 are source-derived;
each names the exact line and the exact input that triggers it.

---

## Verdict on the phase question

> *Phase 3 asks "does the pipeline verifiably use `voice-anchors.md`?" —
> this phase asks whether that file is worth using.*

**`voice-anchors.md` is sound.** It regenerates byte-for-byte from
`build_voice_anchors.py` (4070 bytes in, 4070 out, identical). Phase 3's
findings about it stand on a reproducible artifact and do not need retesting.

**The bullet bank itself is not sound.** `bullet-bank-keepers.csv` has a live
path that writes rows into the wrong columns and destroys the `source`
provenance field (Finding 1), and `bullet-bank-keepers-audited.csv` — the file
the resume build and the embeddings both read — is rewritten in place, non
atomically, ~170 times during a normal scoring run with no backup (Finding 2).

Per `PLAN.md`'s closing note, Phase 9 should treat Finding 1 as grounds for
re-testing any Phase 3 finding that rests on keeper-bank *provenance* or
`source`. Findings about prompt wording are unaffected.

---

## Blocker

### 1. `triage_needs_review.py` appends keeper rows into the wrong columns and destroys provenance

`scripts/triage_needs_review.py:48-54` (`KEEP_FIELDS`) and `:160`
(`append_rows(KEEPERS_CSV, keep_rows, KEEP_FIELDS)`).

`KEEP_FIELDS` is 14 columns. The real on-disk header of
`bullet-bank-keepers.csv` is 16, and diverges from index 9 onward:

| position | file's real header | `KEEP_FIELDS` writes |
|---|---|---|
| 10 | `source` | `hidden_gem_score` |
| 11 | `rewrite_attempts` | `hidden_gem_flag` |
| 12 | `rewrite_reasoning` | `hidden_gem_reason` |
| 13 | `context_gaps` | `final_bullet` |
| 14 | `rewrite_date` | `rewrite_status` |
| 15–16 | `source_cluster_id`, `audit_status` | *(nothing — short row)* |

`append_rows` (`:73-80`) opens in `"a"` mode and writes the header **only if
the file does not exist**. Since it does exist, `csv.DictWriter` emits values
positionally in `KEEP_FIELDS` order under the file's real header. No
exception, no warning, and the result is still well-formed CSV.

**Reproduced.** Sandbox copy of the real header + 2 real rows, one
needs-review row carrying `source="REAL_RESUME_2019"`, `hidden_gem_score=77`.
After `main()`, parsing the file by its own header yields:

```
'source'            = '77'            <- was REAL_RESUME_2019
'rewrite_attempts'  = 'TRUE'
'rewrite_reasoning' = 'quantified'
'rewrite_date'      = 'KEEPER'
'source_cluster_id' = None
'audit_status'      = None
```

`source` is the provenance field — how the bank distinguishes a bullet lifted
from a real resume from one that was generated. It is overwritten with an
integer, and the true value is gone.

**Irreversible.** `:180` deletes `needs-review.csv` in the same run once every
row is routed, so the correct values are not recoverable from the input
either.

**Live, not theoretical.** `bullet_feedback.py:12-16` documents its purpose as
appending "the hidden_gem_* columns triage_needs_review.py's KEEP_FIELDS
already expects" — the whole feature was built on the premise that
`KEEP_FIELDS` matches the keepers file. It does not, and `hidden_gem_*` are
precisely the columns that land in the wrong place. Every accepted rewrite fed
back from a real JD run travels this path.

**Fix:** in `append_rows`, when the target exists, read its header and write
against that, raising if a required field is absent. Never let a hardcoded
`fieldnames` list address an existing file positionally. Same change applies
to the `REWRITE_QUEUE` / `RETIRED_PATH` appends at `:164`/`:168` (those two
happen to match today — they are one schema edit away from the same bug).

**Serves goal 2.** Corrupted provenance is upstream of Phase 3's fabrication
question: a bullet whose `source` says `77` can no longer be shown to have
come from a real resume.

---

### 2. `score_keeper_gems.py` can truncate the entire keeper bank on Ctrl-C

`scripts/score_keeper_gems.py:57` (`DEFAULT_OUTPUT` = the input, in place),
`:140-145` (`_write_scored_csv` opens `"w"`), `:246-247` (flush every
`GEM_FLUSH_EVERY = 5` bullets).

`bullet-bank-keepers-audited.csv` is 844 rows / 658 KB and is the source for
both the resume build and `embed_bullet_bank.py`. The script rewrites it whole,
in place, with a plain truncating `open(path, "w")` — no temp-file-plus-rename
— every 5 scored bullets. With `SLEEP_SECONDS = 4` and hundreds of bullets to
score, that is roughly 170 truncate-and-rewrite windows across a multi-hour
run. A Ctrl-C or crash inside one leaves the bank half-written.

There is no backup, and per commit `261047e2` the knowledge base is no longer
in git — so there is no `git checkout` to fall back on. Recovery is a
Syncthing peer, if one exists and has not already synced the damage.

**Fix:** write to `path + ".tmp"` then `os.replace()`. Atomic on POSIX, one
line changed, removes the entire window.

**Serves goals 1 and 2.**

---

## Major

### 3. Cluster representatives are order-dependent, though cluster IDs were deliberately made stable

`scripts/cluster_bullet_bank.py:293-303`.

`elect_representative` returns `group["accuracy_score"].idxmax()`, falling back
to `lengths.idxmax()`. `idxmax` returns the **first** occurrence of the maximum.
`accuracy_score` is a 0–100 integer and cluster members are near-duplicates by
construction, so ties are the common case, and "first" means first in
`bullet-bank-clean.csv` row order.

This is the same positional-instability bug the file already identifies and
fixes one layer up: `:233-237` and `:248-259` explain at length that positional
cluster numbering "silently reshuffles if `bullet-bank-clean.csv`'s row order
ever changes", and `stable_cluster_ids()` solves it with a content hash. That
fix was not carried into the representative election directly beneath it.

**Consequence:** appending or reordering a row in the raw bank changes which
bullet represents a cluster, which changes what `rewrite_bullets.py` rewrites
and which variant reaches the resume — with no diff anywhere to show it.
This is exactly the "reorder and re-score arbitrarily between runs"
non-determinism the phase brief asks about.

**Fix:** break ties deterministically on content, not position, e.g.
`sort_values(["accuracy_score", <normalized text>], ascending=[False, True])`
and take the first — matching `_cluster_content_hash`'s existing approach.

**Serves goal 2.**

### 4. Both embedding checkpoints resume without verifying the input is unchanged

`scripts/embed_bullet_bank.py:103-111`, `scripts/cluster_bullet_bank.py:141-148`.

`load_checkpoint()` returns `next_index` and the partial vector list with no
check that the CSV is the same file, same length, or same content. Edit the
bank while a checkpoint exists — which is exactly what a rate-limit interruption
invites, since the run stops for hours — and embedding resumes at the old index
against the new bullet list. Row *i* of the resulting matrix no longer
corresponds to bullet *i*, permanently and silently.

`cluster_bullet_bank.py` is one line from catching this: `save_checkpoint`
persists `total` (`:156`), and `load_checkpoint` never reads it back
(`:141-148`). The guard was written and then not wired up.

**Fix:** store a hash of the bullet list in the checkpoint and discard the
checkpoint on mismatch. `audit_bullet_bank.py:56-69` already does the robust
version of this — it resumes by *bullet text*, not by index, so it is immune.
Copy that pattern.

**Serves goal 2.**

### 5. `embed_batch` never checks that the API returned as many vectors as it sent

`scripts/embed_bullet_bank.py:97-98`, `scripts/cluster_bullet_bank.py:131-132`.

```python
embeddings = resp.json().get("embeddings", [])
return [e["values"] for e in embeddings]
```

A short or partial response returns fewer vectors than texts. The caller does
`vectors.extend(vecs)` then `save_checkpoint(vectors, batch_end)` — recording
the *requested* end index against a *shorter* vector list. Every subsequent row
is off by the shortfall, and the final matrix is misaligned end to end. The
`.get(..., [])` default means a response with no `embeddings` key at all
silently contributes zero rows.

**Fix:** `if len(vecs) != len(texts): raise`. Two lines, in both files.

**Serves goal 2.**

### 6. Nothing detects a stale `.npy` against a changed bank

`scripts/embed_bullet_bank.py` (whole file); the `.meta` sidecar at `:179-187`.

The sidecar records `model`, `dim`, `rows`, `csv`, `bullet_col` — enough to
detect staleness, but nothing verifies it. The only safeguard is the docstring
at `:13-14`: "Re-run this script if you add or change bullets." That is exactly
the tribal knowledge goal 3 is meant to eliminate, and the failure is silent —
a stale matrix returns confident, wrong cosine matches rather than an error.

Currently aligned (meta `rows: 844`, CSV 844 rows, `.npy` 2,592,896 bytes =
844×768×4 + header), so this is latent, not active.

`cluster_bullet_bank.py:167-173` does better — it compares `cached.shape`
against `(len(bullets), EMBED_DIM)` — but that is a **count** check only. Edit
a bullet's text without changing the row count and the stale cache is reused.

**Fix:** record a SHA of the bullet-text column in `.meta`, and have the
consumer refuse a mismatch rather than warn. See Handoffs — the consumer is
Phase 4's file.

**Serves goal 2.**

### 7. `retire_rewrite_queue.py` truncates the only copy of the active queue, and silently drops columns

`scripts/retire_rewrite_queue.py:79-83`, `:73`/`:80`.

`open(REWRITE_QUEUE, "w")` rewrites the live queue in place, non atomically. By
that point the retired rows have already been appended elsewhere (`:72-76`), so
the rows at risk are the **active** ones — and they exist nowhere else. A crash
inside this write loses in-flight rewrite work outright.

Separately, both `DictWriter`s use `extrasaction="ignore"` against a hardcoded
19-column `REWRITE_HEADER`. Any column `cluster_bullet_bank.py` adds to
`rewrite-queue.csv` is silently deleted from the live file the next time this
runs — a schema-drift data-loss path with no error.

**Fix:** temp-file-plus-rename, and derive fieldnames from the file's actual
header (union with `REWRITE_HEADER`) instead of hardcoding.

**Serves goal 1.**

### 8. `score_keeper_gems.py` loads a `.env` that does not exist

`scripts/score_keeper_gems.py:45`: `load_dotenv(PROJECT_ROOT / ".env")`.

There is no project-root `.env` (verified), and `CLAUDE.md` states keys live in
`profiles/<name>/.env`. This line is a no-op. It works today only because
`gemini_client.py:30` independently loads the correct path. Compare
`embed_bullet_bank.py:56` and `cluster_bullet_bank.py:77`, which both do
`load_dotenv(profile_paths.env_path(), override=True)` correctly.

Latent rather than active, but it is a second, wrong source of truth for
secrets in a file that makes API calls.

**Serves goal 3.**

---

## Minor

9. **Four of the 15 scripts are unreachable** from any menu, CLI, or other
   script: `detect_hidden_gems.py`, `build_voice_anchors.py`,
   `trim_detective_findings.py`, `detect_blank_scores.py` (only its own
   `scripts/archive/` copy references it, and the two differ).
   `build_voice_anchors.py` is the one that matters: `voice-anchors.md` is a
   Phase 3 input with **no automated regeneration path** — it is reproducible
   (verified) but only if someone knows to run the script by hand after
   editing `application-answers-index.csv`.

10. **Two scripts write `hidden-gems.csv`.** `detect_hidden_gems.py:45` and
    `score_keeper_gems.py:58`, with different schemas and different selection
    logic. Currently harmless only because the former is unreachable (#9).

11. **`ingest.py` is dead and points at a path that does not exist.** `:79`
    hardcodes `resume-engine/knowledge_base/cv.md`; the real file is
    `profiles/morgan/knowledge_base/cv.md` and the hardcoded path is absent, so
    running it prints an error and exits. It imports `profile_paths` (`:17`) but
    does not use it for this lookup. `:13-14` also write to project-root
    `output/txt` and `output/json` rather than `output/<profile>/`, which
    collides across profiles and falls outside `sync_roots()`. Raw `❌`/`✅`
    emoji remain at `:82` and `:93` — same class as the `liveness.py:211` and
    `bootstrap_bullet_bank.py:352` instances already noted in `PLAN.md`.

12. **`audit_bullet_bank.py:111` writes exception text into `weaknesses`.** A
    transient API error becomes durable row content in a column that
    `cluster_bullet_bank.decide_action()` reads as a quality signal. It lands in
    `NEEDS_AUDIT` today (because the score columns stay empty), so the blast
    radius is contained, but the error string persists in the bank.

13. **`tag_bullet_bank.py:156` restricts output to 3 columns.** Fine for its
    documented input (`bullet-bank-clean.csv` really is 3 columns), but pointing
    it at any richer bank CSV raises `ValueError` from `DictWriter` rather than
    reporting a usable message.

14. **`embed_bullet_bank.py` docstring drift.** `:20` and `:32` claim a 4s sleep
    and "~4 minutes"; `EMBED_SLEEP = 20` (`:65`) makes a full run ~20 minutes.
    The printed ETA (`:150`) is computed correctly, so only the docstring
    misleads.

---

## What is working — do not "fix" these

- `voice-anchors.md` regenerates byte-identically. Verified, not assumed.
- `stable_cluster_ids()` / `_cluster_content_hash()`
  (`cluster_bullet_bank.py:248-275`) is the correct solution to positional
  instability, with an unusually good comment explaining why. Finding 3 is that
  it was not applied one function further down — not that it is wrong.
- `audit_bullet_bank.py:56-69` resumes by bullet text rather than row index.
  This is the pattern Findings 4 and 5 should be fixed toward; it is already in
  the repo.
- Every LLM scoring call uses `temperature=0.0`
  (`audit_bullet_bank.py:97`, `score_keeper_gems.py:133`,
  `bootstrap_timeline.py:135`). LLM non-determinism is not a source of drift
  here; the drift found is all ordering and schema.

---

## Correction to the phase brief

`PLAN.md:354-356` asks to "round-trip a messy input" through
`ingest.py` / `normalize_resume.py` and read the result. **That task is not
executable as written, and the pairing is a mistake in the plan.**

- `ingest.py` is unreachable and its hardcoded input path does not exist
  (#11). Nothing imports it — the only match across `scripts/` is the word
  "ingest" inside a `bootstrap_extractors.py:236` comment.
- `normalize_resume.py` is **not** an ingestion component. It post-processes
  the *builder's output* mid-JD-run — injecting `fixed_content.CONTACT_INFO`,
  `CERTIFICATIONS`, `COMPANY_META`, section headings — before critique and
  before `validate_resume.py`. It never sees a user's resume file. Its real
  callers are `orchestrator.py`, `polish.py`, `render_html.py`.

The underlying question — *what does a stranger's real resume actually turn
into?* — is answered by `bootstrap_extractors.py` / `bootstrap_bullet_bank.py`,
which are **Phase 1's** files. Handed off below rather than absorbed.

---

## Handoffs

- **Phase 2** (`bullet_bank_menu.py`): `:184` declares `score_keeper_gems.py`'s
  output as identical to its input (in-place). Fixing Finding 2 to
  temp-file-plus-rename preserves that contract but changes the mtime-based
  status logic at `:225-228` — worth a glance during the fix pass.
- **Phase 4** (`orchestrator.py`): `mine_bullet_bank()` consumes
  `bullet_vectors_ge2_d768.npy`. Finding 6's staleness guard has to be enforced
  at that read, not only recorded in `.meta`. I did not read the file.
- **Phase 3**: `voice-anchors.md` derives *only* from
  `application-answers-index.csv` — a set copied once from `career-ops` — and
  has no connection to the bullet bank. If Phase 3 assumed voice anchors are
  mined from Morgan's bullets, that assumption is wrong.
- **Phase 1**: the real stranger's-resume ingestion path is
  `bootstrap_extractors.py` / `bootstrap_bullet_bank.py`, per the correction
  above.
- **Phase 8**: this phase found four non-atomic KB writes
  (`score_keeper_gems.py:142`, `retire_rewrite_queue.py:79`,
  `triage_needs_review.py:174`, `bullet_feedback.py:76`). That is Phase 8's
  Question 3 with the instances already enumerated — and the answer to "is there
  any backup or recovery path" is no, since commit `261047e2` removed the KB
  from git.
- **Phase 9**: `PLAN.md`'s ingest/normalize pairing needs correcting in the plan
  itself, not just here.
