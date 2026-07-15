# Bullet Bank Management Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Manage Bullet Bank" submenu to the interactive CLI that
shows staleness/last-run status for each of the 6 rebuild-pipeline stages
(plus the 2 needs-review/rewrite-queue maintenance scripts) and lets you
run any one of them individually, looping back into the same submenu
afterward.

**Architecture:** A new `scripts/bullet_bank_menu.py` module owns stage/
script definitions, status computation (file-mtime comparison for 5
stages, column-completeness for the one in-place-updating stage), and the
submenu's dispatch logic. `menu.py` gains one new entry point into it. A
new `cli_art.render_bullet_bank_status()` renders the status table using
existing `theme` tokens.

**Tech Stack:** Python 3.10+, stdlib `csv`/`os`/`datetime`/`subprocess`,
`questionary`, `rich` (via `cli_art`). Tests: stdlib `unittest`
(`python -m unittest discover -s tests`).

## Global Constraints

- No changes to any of the 8 underlying scripts (`audit_bullet_bank.py`,
  `cluster_bullet_bank.py`, `rewrite_bullets.py`, `audit_keepers.py`,
  `score_keeper_gems.py`, `embed_bullet_bank.py`, `triage_needs_review.py`,
  `retire_rewrite_queue.py`) — every one is invoked exactly as-is, via
  `subprocess.run([sys.executable, script_path])`, no imports of their
  internals.
- No new state-tracking file — status comes entirely from existing file
  mtimes, or (for `score_keeper_gems.py` specifically) column
  completeness in its existing output file.
- `detect_hidden_gems.py` is explicitly excluded from the menu (confirmed
  with the user).
- No exposure of per-script CLI flags through the menu — every menu
  action runs a script's plain default invocation.
- Run `python -m unittest discover -s tests` after every task and confirm
  the full suite passes.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/theme.py` (modified) | Gains one new icon token, `bullet_bank`, in both icon sets. |
| `scripts/bullet_bank_menu.py` (new) | `STAGES`/`MAINTENANCE` definitions, `_stage_status()`, `_maintenance_status()`, `_confirm()`, `_handle_choice()`, `run_bullet_bank_menu()`. |
| `scripts/cli_art.py` (modified) | New `render_bullet_bank_status()`. |
| `scripts/menu.py` (modified) | New `_CHOICES` entry, `_handle_bullet_bank()`, `_HANDLERS` registration. |
| `tests/test_theme.py` (modified) | Covers the new icon token. |
| `tests/test_bullet_bank_menu.py` (new) | Covers status computation and dispatch logic. |
| `tests/test_cli_art.py` (modified) | Covers `render_bullet_bank_status()`. |
| `tests/test_menu.py` (modified) | Covers the new `_CHOICES` entry and `_handle_bullet_bank()`. |
| `README.md` (modified) | New `## Bullet Bank Management` section. |

---

### Task 1: `theme.py` — add the `bullet_bank` icon token

**Files:**
- Modify: `scripts/theme.py:43-65` (`_NERD_ICONS`, `_UNICODE_ICONS`)
- Test: `tests/test_theme.py`

**Interfaces:**
- Produces: `theme.ICONS["bullet_bank"]` (both icon sets gain this key).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_theme.py -- add to TestIconSwitch

    def test_bullet_bank_icon_exists_in_both_sets(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RESUME_BUILDER_ICONS", None)
            nerd = importlib.reload(theme)
        self.assertIn("bullet_bank", nerd.ICONS)
        with patch.dict(os.environ, {"RESUME_BUILDER_ICONS": "unicode"}):
            unicode_theme = importlib.reload(theme)
        self.assertIn("bullet_bank", unicode_theme.ICONS)
        importlib.reload(theme)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_theme -v`
Expected: FAIL — `AssertionError: 'bullet_bank' not found in {...}`

- [ ] **Step 3: Implement**

In `scripts/theme.py`, add one entry to each dict:

```python
_NERD_ICONS = {
    "success": "",     # nf-fa-check
    "error": "",       # nf-fa-times
    "warning": "",     # nf-fa-exclamation_triangle
    "hint": "",        # nf-fa-lightbulb_o
    "discovery": "",   # nf-fa-search
    "evaluate": "",    # nf-fa-bar_chart
    "build": "",       # nf-fa-wrench
    "utility": "",     # nf-fa-cog
    "bullet_bank": "", # nf-fa-database
}
```

```python
_UNICODE_ICONS = {
    "success": "✓",       # ✓
    "error": "✗",         # ✗
    "warning": "⚠",       # ⚠
    "hint": "\U0001F4A1",      # 💡
    "discovery": "\U0001F50D",  # 🔍
    "evaluate": "\U0001F4CA",   # 📊
    "build": "\U0001F6E0",      # 🛠
    "utility": "⚙",        # ⚙
    "bullet_bank": "\U0001F5C3", # 🗃
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_theme -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/theme.py tests/test_theme.py
git commit -m "$(cat <<'EOF'
Add bullet_bank icon token to theme.py

New category icon for the upcoming Bullet Bank Management menu entry.
EOF
)"
```

---

### Task 2: `bullet_bank_menu.py` — stage definitions + mtime-based status

**Files:**
- Create: `scripts/bullet_bank_menu.py`
- Test: `tests/test_bullet_bank_menu.py`

**Interfaces:**
- Produces: `bullet_bank_menu.STAGES: list[dict]`,
  `bullet_bank_menu.MAINTENANCE: list[dict]`,
  `bullet_bank_menu._stage_status(stage: dict) -> tuple[str, str]` (returns
  `(status_label, detail)` — `("Never run", "")`, `("Stale", "")`, or
  `("Up to date", "as of <timestamp>")`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bullet_bank_menu.py
import csv
import os
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bullet_bank_menu  # noqa: E402


class TestStageStatusMtime(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _touch(self, name, mtime_offset=0):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("x")
        stat = os.stat(path)
        os.utime(path, (stat.st_atime + mtime_offset, stat.st_mtime + mtime_offset))
        return path

    def test_missing_output_is_never_run(self):
        input_path = self._touch("input.csv")
        stage = {"inputs": [input_path], "output": os.path.join(self.tmp_dir, "missing.csv"), "status_mode": "mtime"}
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")

    def test_output_older_than_input_is_stale(self):
        output_path = self._touch("output.csv", mtime_offset=0)
        input_path = self._touch("input.csv", mtime_offset=10)
        stage = {"inputs": [input_path], "output": output_path, "status_mode": "mtime"}
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Stale")

    def test_output_newer_than_input_is_up_to_date(self):
        input_path = self._touch("input.csv", mtime_offset=0)
        output_path = self._touch("output.csv", mtime_offset=10)
        stage = {"inputs": [input_path], "output": output_path, "status_mode": "mtime"}
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Up to date")
        self.assertIn("as of", detail)

    def test_missing_input_does_not_crash(self):
        output_path = self._touch("output.csv")
        stage = {
            "inputs": [os.path.join(self.tmp_dir, "does_not_exist.csv")],
            "output": output_path, "status_mode": "mtime",
        }
        status, _ = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Up to date")


class TestStagesAndMaintenanceDefinitions(unittest.TestCase):

    def test_six_stages_in_pipeline_order(self):
        self.assertEqual([s["key"] for s in bullet_bank_menu.STAGES],
                          ["audit", "cluster", "rewrite", "audit_keepers", "score_gems", "embed"])
        self.assertEqual([s["number"] for s in bullet_bank_menu.STAGES], [1, 2, 3, 4, 5, 6])

    def test_all_stages_cost_api(self):
        self.assertTrue(all(s["api_cost"] for s in bullet_bank_menu.STAGES))

    def test_two_maintenance_scripts(self):
        self.assertEqual([m["key"] for m in bullet_bank_menu.MAINTENANCE], ["triage", "retire"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bullet_bank_menu -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bullet_bank_menu'`

- [ ] **Step 3: Implement**

```python
# scripts/bullet_bank_menu.py
"""bullet_bank_menu.py -- the "Manage Bullet Bank" submenu: shows
staleness/last-run status for the 6 rebuild-pipeline stages
(audit_bullet_bank.py -> cluster_bullet_bank.py -> rewrite_bullets.py ->
audit_keepers.py -> score_keeper_gems.py -> embed_bullet_bank.py) plus the
2 needs-review/rewrite-queue maintenance scripts, and runs any one of them
individually as a subprocess -- unmodified, exactly as
bootstrap_bullet_bank.py's own run_stage() does. See
docs/superpowers/specs/2026-07-15-bullet-bank-management-design.md.
"""

import csv
import datetime
import os
import subprocess
import sys

import questionary

import cli_art

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
KB_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

RAW_CSV = os.path.join(KB_DIR, "bullet-bank-clean.csv")
AUDITED_CSV = os.path.join(KB_DIR, "bullet-bank-audited.csv")
CLUSTER_MAP_CSV = os.path.join(KB_DIR, "bullet-bank-cluster-map.csv")
KEEPERS_CSV = os.path.join(KB_DIR, "bullet-bank-keepers.csv")
KEEPERS_AUDITED_CSV = os.path.join(KB_DIR, "bullet-bank-keepers-audited.csv")
NPY_PATH = os.path.join(KB_DIR, "bullet_vectors_ge2_d768.npy")
NEEDS_REVIEW_CSV = os.path.join(KB_DIR, "needs-review.csv")
REWRITE_QUEUE_CSV = os.path.join(KB_DIR, "rewrite-queue.csv")

# Verified directly against each script's own path constants -- see
# docs/superpowers/specs/2026-07-15-bullet-bank-management-design.md's
# Architecture section 1 table.
STAGES = [
    {
        "key": "audit", "number": 1, "label": "Audit Bullet Bank (Score Quality)",
        "script": "audit_bullet_bank.py", "inputs": [RAW_CSV], "output": AUDITED_CSV,
        "api_cost": True, "status_mode": "mtime",
    },
    {
        "key": "cluster", "number": 2, "label": "Cluster & Classify Bullets",
        "script": "cluster_bullet_bank.py", "inputs": [RAW_CSV, AUDITED_CSV], "output": CLUSTER_MAP_CSV,
        "api_cost": True, "status_mode": "mtime",
    },
    {
        "key": "rewrite", "number": 3, "label": "Rewrite Weak Bullets",
        "script": "rewrite_bullets.py", "inputs": [CLUSTER_MAP_CSV], "output": KEEPERS_CSV,
        "api_cost": True, "status_mode": "mtime",
    },
    {
        "key": "audit_keepers", "number": 4, "label": "Re-Audit Keepers",
        "script": "audit_keepers.py", "inputs": [KEEPERS_CSV], "output": KEEPERS_AUDITED_CSV,
        "api_cost": True, "status_mode": "mtime",
    },
    {
        "key": "score_gems", "number": 5, "label": "Score Hidden Gems",
        "script": "score_keeper_gems.py", "inputs": [KEEPERS_AUDITED_CSV], "output": KEEPERS_AUDITED_CSV,
        "api_cost": True, "status_mode": "columns",
        "status_columns": ["hidden_gem_score", "hidden_gem_flag"],
    },
    {
        "key": "embed", "number": 6, "label": "Embed Bullet Bank (Final Step)",
        "script": "embed_bullet_bank.py", "inputs": [KEEPERS_AUDITED_CSV], "output": NPY_PATH,
        "api_cost": True, "status_mode": "mtime",
    },
]

MAINTENANCE = [
    {
        "key": "triage", "label": "Triage Needs-Review Queue",
        "script": "triage_needs_review.py", "watched_file": NEEDS_REVIEW_CSV, "api_cost": False,
    },
    {
        "key": "retire", "label": "Retire Abandoned Rewrite-Queue Bullets",
        "script": "retire_rewrite_queue.py", "watched_file": REWRITE_QUEUE_CSV, "api_cost": False,
    },
]

_ALL_ENTRIES = {entry["key"]: entry for entry in STAGES + MAINTENANCE}


def _stage_status(stage: dict) -> tuple:
    """Returns (status_label, detail). status_mode='mtime' (5 of the 6
    stages, each with a distinct input/output file) compares mtimes.
    status_mode='columns' (score_keeper_gems.py, which updates its file
    in place -- see Task 3) is handled separately."""
    output = stage["output"]
    if not os.path.exists(output):
        return ("Never run", "")

    output_mtime = os.path.getmtime(output)
    for input_path in stage["inputs"]:
        if os.path.exists(input_path) and os.path.getmtime(input_path) > output_mtime:
            return ("Stale", "")

    timestamp = datetime.datetime.fromtimestamp(output_mtime).strftime("%Y-%m-%d %H:%M")
    return ("Up to date", f"as of {timestamp}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bullet_bank_menu -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/bullet_bank_menu.py tests/test_bullet_bank_menu.py
git commit -m "$(cat <<'EOF'
Add bullet_bank_menu.py: stage definitions + mtime-based status

STAGES/MAINTENANCE hold the verified script/input/output paths for the
6 rebuild-pipeline stages and 2 maintenance scripts. _stage_status()
covers the 5 stages with a distinct input/output file via mtime
comparison; the one in-place-updating stage is handled in the next task.
EOF
)"
```

---

### Task 3: Column-completeness status for `score_keeper_gems.py`

**Files:**
- Modify: `scripts/bullet_bank_menu.py` (extend `_stage_status`)
- Test: `tests/test_bullet_bank_menu.py`

**Interfaces:**
- Consumes: `STAGES[4]` (the `score_gems` entry, Task 2) — its
  `status_mode == "columns"` and `status_columns` keys.
- Produces: `bullet_bank_menu._stage_status()` now branches on
  `status_mode` (unchanged signature).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bullet_bank_menu.py -- add this class

class TestStageStatusColumns(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.tmp_dir, "keepers.csv")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write_csv(self, rows, fieldnames):
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_missing_file_is_never_run(self):
        stage = {"output": self.csv_path, "status_mode": "columns", "status_columns": ["hidden_gem_score"]}
        status, _ = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")

    def test_missing_column_entirely_is_stale(self):
        self._write_csv([{"Bullet Point": "x"}], ["Bullet Point"])
        stage = {"output": self.csv_path, "status_mode": "columns", "status_columns": ["hidden_gem_score"]}
        status, _ = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Stale")

    def test_blank_value_in_column_is_stale(self):
        self._write_csv(
            [{"Bullet Point": "a", "hidden_gem_score": "90"}, {"Bullet Point": "b", "hidden_gem_score": ""}],
            ["Bullet Point", "hidden_gem_score"],
        )
        stage = {"output": self.csv_path, "status_mode": "columns", "status_columns": ["hidden_gem_score"]}
        status, _ = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Stale")

    def test_fully_populated_column_is_up_to_date(self):
        self._write_csv(
            [{"Bullet Point": "a", "hidden_gem_score": "90"}, {"Bullet Point": "b", "hidden_gem_score": "10"}],
            ["Bullet Point", "hidden_gem_score"],
        )
        stage = {"output": self.csv_path, "status_mode": "columns", "status_columns": ["hidden_gem_score"]}
        status, _ = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Up to date")

    def test_empty_csv_is_never_run(self):
        self._write_csv([], ["Bullet Point", "hidden_gem_score"])
        stage = {"output": self.csv_path, "status_mode": "columns", "status_columns": ["hidden_gem_score"]}
        status, _ = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bullet_bank_menu.TestStageStatusColumns -v`
Expected: FAIL — all 5 fail (`_stage_status` doesn't branch on `status_mode` yet, so it tries `stage["inputs"]` and raises `KeyError`)

- [ ] **Step 3: Implement**

Replace `_stage_status` in `scripts/bullet_bank_menu.py` with:

```python
def _stage_status(stage: dict) -> tuple:
    """Returns (status_label, detail). status_mode='mtime' (5 of the 6
    stages, each with a distinct input/output file) compares mtimes.
    status_mode='columns' (score_keeper_gems.py, which updates its file
    in place -- same file in and out, so an mtime comparison against
    itself is meaningless) checks column completeness instead."""
    if stage.get("status_mode") == "columns":
        return _column_completeness_status(stage["output"], stage["status_columns"])

    output = stage["output"]
    if not os.path.exists(output):
        return ("Never run", "")

    output_mtime = os.path.getmtime(output)
    for input_path in stage["inputs"]:
        if os.path.exists(input_path) and os.path.getmtime(input_path) > output_mtime:
            return ("Stale", "")

    timestamp = datetime.datetime.fromtimestamp(output_mtime).strftime("%Y-%m-%d %H:%M")
    return ("Up to date", f"as of {timestamp}")


def _column_completeness_status(csv_path: str, columns: list) -> tuple:
    if not os.path.exists(csv_path):
        return ("Never run", "")
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return ("Never run", "")
    for col in columns:
        if any(not (row.get(col) or "").strip() for row in rows):
            return ("Stale", "")
    return ("Up to date", "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bullet_bank_menu -v`
Expected: all PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/bullet_bank_menu.py tests/test_bullet_bank_menu.py
git commit -m "$(cat <<'EOF'
Add column-completeness status mode for score_keeper_gems.py

Its input and output are the same file (in-place update), so mtime
comparison doesn't apply -- status instead checks whether
hidden_gem_score/hidden_gem_flag are present and non-blank on every row.
EOF
)"
```

---

### Task 4: Maintenance-script status (`triage`/`retire`)

**Files:**
- Modify: `scripts/bullet_bank_menu.py` (add `_maintenance_status`)
- Test: `tests/test_bullet_bank_menu.py`

**Interfaces:**
- Consumes: `MAINTENANCE` entries (Task 2) — `key` and `watched_file`.
- Produces: `bullet_bank_menu._maintenance_status(entry: dict) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bullet_bank_menu.py -- add this class

class TestMaintenanceStatus(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.tmp_dir, "watched.csv")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write_csv(self, rows, fieldnames):
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_triage_missing_file_is_empty(self):
        entry = {"key": "triage", "watched_file": self.csv_path}
        self.assertEqual(bullet_bank_menu._maintenance_status(entry), "empty -- nothing to triage")

    def test_triage_reports_row_count(self):
        self._write_csv([{"Bullet Point": "a"}, {"Bullet Point": "b"}], ["Bullet Point"])
        entry = {"key": "triage", "watched_file": self.csv_path}
        self.assertEqual(bullet_bank_menu._maintenance_status(entry), "2 row(s) waiting")

    def test_retire_missing_file_is_none_pending(self):
        entry = {"key": "retire", "watched_file": self.csv_path}
        self.assertEqual(bullet_bank_menu._maintenance_status(entry), "none pending")

    def test_retire_counts_only_non_representative_rows(self):
        self._write_csv(
            [{"is_representative": "True"}, {"is_representative": "False"}, {"is_representative": "False"}],
            ["is_representative"],
        )
        entry = {"key": "retire", "watched_file": self.csv_path}
        self.assertEqual(bullet_bank_menu._maintenance_status(entry), "2 bullet(s) pending retirement")

    def test_retire_none_pending_when_all_representative(self):
        self._write_csv([{"is_representative": "True"}], ["is_representative"])
        entry = {"key": "retire", "watched_file": self.csv_path}
        self.assertEqual(bullet_bank_menu._maintenance_status(entry), "none pending")


if __name__ == "__main__":
    unittest.main()
```

`csv` is already imported at module level (added in Task 2's Step 1) — no new import needed here.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bullet_bank_menu.TestMaintenanceStatus -v`
Expected: FAIL — `AttributeError: module 'bullet_bank_menu' has no attribute '_maintenance_status'`

- [ ] **Step 3: Implement**

Add to `scripts/bullet_bank_menu.py`:

```python
def _maintenance_status(entry: dict) -> str:
    path = entry["watched_file"]

    if entry["key"] == "triage":
        if not os.path.exists(path):
            return "empty -- nothing to triage"
        with open(path, newline="", encoding="utf-8") as f:
            count = sum(1 for _ in csv.DictReader(f))
        return "empty -- nothing to triage" if count == 0 else f"{count} row(s) waiting"

    if entry["key"] == "retire":
        if not os.path.exists(path):
            return "none pending"
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        pending = sum(1 for row in rows if (row.get("is_representative") or "").strip().lower() == "false")
        return "none pending" if pending == 0 else f"{pending} bullet(s) pending retirement"

    return ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bullet_bank_menu -v`
Expected: all PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/bullet_bank_menu.py tests/test_bullet_bank_menu.py
git commit -m "$(cat <<'EOF'
Add maintenance-script status for triage_needs_review/retire_rewrite_queue

Row count in needs-review.csv, and count of is_representative=False
rows still sitting in rewrite-queue.csv -- these two scripts aren't
part of the linear 6-stage chain, so they get a lighter status signal.
EOF
)"
```

---

### Task 5: `cli_art.render_bullet_bank_status()`

**Files:**
- Modify: `scripts/cli_art.py` (add after `render_fit_table`)
- Test: `tests/test_cli_art.py`

**Interfaces:**
- Consumes: `theme.SUCCESS`, `theme.WARNING`, `theme.BRAND` (existing).
- Produces: `cli_art.render_bullet_bank_status(stage_rows: list, maintenance_rows: list) -> None`.
  `stage_rows`: list of `(number, label, status, detail)` tuples.
  `maintenance_rows`: list of `(label, detail)` tuples.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_art.py -- add this class

class TestRenderBulletBankStatus(unittest.TestCase):

    def test_shows_stage_numbers_labels_status_and_maintenance_rows(self):
        stage_rows = [
            (1, "Audit Bullet Bank (Score Quality)", "Up to date", "as of 2026-07-15 10:00"),
            (2, "Cluster & Classify Bullets", "Stale", ""),
            (3, "Rewrite Weak Bullets", "Never run", ""),
        ]
        maintenance_rows = [("Triage Needs-Review Queue", "3 row(s) waiting")]

        console = Console(record=True, width=120)
        original = cli_art.console
        cli_art.console = console
        try:
            cli_art.render_bullet_bank_status(stage_rows, maintenance_rows)
        finally:
            cli_art.console = original
        output = console.export_text()
        self.assertIn("Audit Bullet Bank (Score Quality)", output)
        self.assertIn("Up to date", output)
        self.assertIn("Stale", output)
        self.assertIn("Never run", output)
        self.assertIn("Triage Needs-Review Queue", output)
        self.assertIn("3 row(s) waiting", output)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_cli_art.TestRenderBulletBankStatus -v`
Expected: FAIL — `AttributeError: module 'cli_art' has no attribute 'render_bullet_bank_status'`

- [ ] **Step 3: Implement**

Add to `scripts/cli_art.py`, after `render_fit_table`:

```python
_STAGE_STATUS_COLORS = {"Up to date": theme.SUCCESS, "Stale": theme.WARNING}


def render_bullet_bank_status(stage_rows: list, maintenance_rows: list) -> None:
    """stage_rows: (number, label, status, detail) tuples, in pipeline
    order. maintenance_rows: (label, detail) tuples for the non-sequential
    triage/retire scripts."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Stage")
    table.add_column("Status")

    for number, label, status, detail in stage_rows:
        color = _STAGE_STATUS_COLORS.get(status)
        status_text = f"[{color}]{status}[/{color}]" if color else f"[dim]{status}[/dim]"
        if detail:
            status_text += f" ({detail})"
        table.add_row(str(number), label, status_text)

    for label, detail in maintenance_rows:
        table.add_row("-", label, detail)

    console.print(Panel(table, title="Bullet Bank Pipeline Status", border_style=theme.BRAND, box=box.ROUNDED))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_cli_art -v`
Expected: all PASS

Then: `python -m unittest discover -s tests`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/cli_art.py tests/test_cli_art.py
git commit -m "$(cat <<'EOF'
Add cli_art.render_bullet_bank_status()

Renders the 6-stage + 2-maintenance-script status table for the new
Bullet Bank Management submenu, styled with the existing theme tokens.
EOF
)"
```

---

### Task 6: Dispatch logic — `_confirm`, `_handle_choice`, `run_bullet_bank_menu`

**Files:**
- Modify: `scripts/bullet_bank_menu.py` (add dispatch functions)
- Test: `tests/test_bullet_bank_menu.py`

**Interfaces:**
- Consumes: `cli_art.console.QUESTIONARY_STYLE`, `cli_art.display_error`,
  `cli_art.render_bullet_bank_status` (Task 5), `_ALL_ENTRIES`,
  `_stage_status`, `_maintenance_status` (Tasks 2-4).
- Produces: `bullet_bank_menu._confirm(label: str) -> bool`,
  `bullet_bank_menu._handle_choice(choice: str) -> None`,
  `bullet_bank_menu.run_bullet_bank_menu() -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bullet_bank_menu.py -- add these classes
from unittest.mock import patch


class TestHandleChoice(unittest.TestCase):

    @patch("bullet_bank_menu.subprocess.run")
    @patch("bullet_bank_menu._confirm", return_value=False)
    def test_declined_confirm_skips_subprocess(self, mock_confirm, mock_run):
        bullet_bank_menu._handle_choice("audit")
        mock_run.assert_not_called()

    @patch("bullet_bank_menu.cli_art.display_error")
    @patch("bullet_bank_menu.subprocess.run")
    @patch("bullet_bank_menu._confirm", return_value=True)
    def test_confirmed_api_stage_runs_subprocess(self, mock_confirm, mock_run, mock_error):
        mock_run.return_value.returncode = 0
        bullet_bank_menu._handle_choice("audit")
        mock_run.assert_called_once()
        mock_error.assert_not_called()

    @patch("bullet_bank_menu.cli_art.display_error")
    @patch("bullet_bank_menu.subprocess.run")
    @patch("bullet_bank_menu._confirm", return_value=True)
    def test_nonzero_exit_displays_error(self, mock_confirm, mock_run, mock_error):
        mock_run.return_value.returncode = 1
        bullet_bank_menu._handle_choice("audit")
        mock_error.assert_called_once()

    @patch("bullet_bank_menu.cli_art.display_error")
    @patch("bullet_bank_menu.subprocess.run")
    @patch("bullet_bank_menu._confirm")
    def test_maintenance_entry_skips_confirmation(self, mock_confirm, mock_run, mock_error):
        mock_run.return_value.returncode = 0
        bullet_bank_menu._handle_choice("triage")
        mock_confirm.assert_not_called()
        mock_run.assert_called_once()


class TestRunBulletBankMenu(unittest.TestCase):

    @patch("bullet_bank_menu.cli_art.render_bullet_bank_status")
    @patch("bullet_bank_menu.questionary.select")
    def test_back_returns_without_handling_a_choice(self, mock_select, mock_render):
        mock_select.return_value.ask.return_value = "__back__"
        with patch("bullet_bank_menu._handle_choice") as mock_handle:
            bullet_bank_menu.run_bullet_bank_menu()
        mock_handle.assert_not_called()

    @patch("bullet_bank_menu.cli_art.render_bullet_bank_status")
    @patch("bullet_bank_menu.questionary.select")
    def test_cancelled_prompt_returns_without_handling_a_choice(self, mock_select, mock_render):
        mock_select.return_value.ask.return_value = None
        with patch("bullet_bank_menu._handle_choice") as mock_handle:
            bullet_bank_menu.run_bullet_bank_menu()
        mock_handle.assert_not_called()

    @patch("bullet_bank_menu.cli_art.render_bullet_bank_status")
    @patch("bullet_bank_menu.questionary.select")
    def test_choosing_a_stage_then_back_handles_it_once(self, mock_select, mock_render):
        mock_select.return_value.ask.side_effect = ["audit", "__back__"]
        with patch("bullet_bank_menu._handle_choice") as mock_handle:
            bullet_bank_menu.run_bullet_bank_menu()
        mock_handle.assert_called_once_with("audit")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bullet_bank_menu.TestHandleChoice tests.test_bullet_bank_menu.TestRunBulletBankMenu -v`
Expected: FAIL — `AttributeError: module 'bullet_bank_menu' has no attribute '_handle_choice'`

- [ ] **Step 3: Implement**

Add to `scripts/bullet_bank_menu.py`:

```python
def _confirm(label: str) -> bool:
    return bool(questionary.confirm(
        f'Ready to run "{label}"? This calls the Gemini API and may take a while.',
        default=True, style=cli_art.QUESTIONARY_STYLE,
    ).ask())


def _handle_choice(choice: str) -> None:
    entry = _ALL_ENTRIES[choice]
    if entry.get("api_cost") and not _confirm(entry["label"]):
        return
    script_path = os.path.join(SCRIPT_DIR, entry["script"])
    result = subprocess.run([sys.executable, script_path])
    if result.returncode != 0:
        cli_art.display_error(f"{entry['script']} exited with an error -- check the output above.")


def _build_choices() -> list:
    choices = [
        questionary.Choice(title=f"{stage['number']}. {stage['label']}", value=stage["key"])
        for stage in STAGES
    ]
    choices.append(questionary.Separator())
    choices += [questionary.Choice(title=entry["label"], value=entry["key"]) for entry in MAINTENANCE]
    choices.append(questionary.Choice(title="Back to Main Menu", value="__back__"))
    return choices


def run_bullet_bank_menu() -> None:
    while True:
        stage_rows = [(s["number"], s["label"], *_stage_status(s)) for s in STAGES]
        maintenance_rows = [(m["label"], _maintenance_status(m)) for m in MAINTENANCE]
        cli_art.render_bullet_bank_status(stage_rows, maintenance_rows)

        choice = questionary.select(
            "Bullet Bank Management:", choices=_build_choices(), style=cli_art.QUESTIONARY_STYLE,
        ).ask()

        if not choice or choice == "__back__":
            return
        _handle_choice(choice)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bullet_bank_menu -v`
Expected: all PASS (24 tests)

Then: `python -m unittest discover -s tests`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/bullet_bank_menu.py tests/test_bullet_bank_menu.py
git commit -m "$(cat <<'EOF'
Add the Bullet Bank submenu's dispatch loop

_handle_choice() confirms before any API-costing stage, runs the script
as a subprocess, and reports a non-zero exit via cli_art.display_error
without advancing automatically. run_bullet_bank_menu() re-renders
status and re-prompts after every action until "Back to Main Menu".
EOF
)"
```

---

### Task 7: `menu.py` integration

**Files:**
- Modify: `scripts/menu.py:33-49` (`_CHOICES`), add `_handle_bullet_bank`, `scripts/menu.py:190-201` (`_HANDLERS`)
- Test: `tests/test_menu.py`

**Interfaces:**
- Consumes: `bullet_bank_menu.run_bullet_bank_menu()` (Task 6).
- Produces: `menu._handle_bullet_bank() -> bool` (always returns `False`,
  same convention as `_handle_polish`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_menu.py -- add this class

class TestHandleBulletBank(unittest.TestCase):

    @patch("menu.bullet_bank_menu.run_bullet_bank_menu")
    def test_always_returns_false(self, mock_run):
        self.assertFalse(menu._handle_bullet_bank())
        mock_run.assert_called_once()
```

Also add a check to `TestChoicesAndHandlers`:

```python
    def test_bullet_bank_entry_is_registered(self):
        values = [c.value for c in menu._CHOICES]
        self.assertIn("bullet_bank", values)
        self.assertIn("bullet_bank", menu._HANDLERS)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_menu.TestHandleBulletBank tests.test_menu.TestChoicesAndHandlers -v`
Expected: FAIL — `AttributeError: module 'menu' has no attribute 'bullet_bank_menu'`

- [ ] **Step 3: Implement**

In `scripts/menu.py`, add the import (alongside the existing module
imports):

```python
import bullet_bank_menu
```

Add the new group to `_CHOICES` (after the `── Utility ──` group, before
the closing `]`):

```python
    questionary.Separator("── Bullet Bank ──"),
    questionary.Choice(title=f"{theme.ICONS['bullet_bank']}  Manage Bullet Bank", value="bullet_bank"),
```

Add the handler function (near `_handle_polish`, matching its style):

```python
def _handle_bullet_bank() -> bool:
    bullet_bank_menu.run_bullet_bank_menu()
    return False
```

Register it in `_HANDLERS`:

```python
    "bullet_bank": _handle_bullet_bank,
```

(No `_CHAIN` entry — same reasoning as `polish`: the submenu is its own
self-contained loop, not a pipeline step.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_menu -v`
Expected: all PASS

Then: `python -m unittest discover -s tests`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/menu.py tests/test_menu.py
git commit -m "$(cat <<'EOF'
Wire "Manage Bullet Bank" into the main menu

New Bullet Bank separator group with one entry, delegating to
bullet_bank_menu.run_bullet_bank_menu(). No _CHAIN entry -- same
convention as "polish", since the submenu is its own self-contained loop.
EOF
)"
```

- [ ] **Step 6: Live verification**

Run `resume` in a real terminal, select "Manage Bullet Bank," confirm the
status table renders with accurate never-run/stale/up-to-date states
against your real bullet-bank files, run one lightweight action (e.g.
"Triage Needs-Review Queue" if `needs-review.csv` is empty/absent) and
confirm the submenu re-renders afterward, then confirm "Back to Main
Menu" returns cleanly.

---

### Task 8: README documentation

**Files:**
- Modify: `README.md` (new section near "Bullet bank feedback loop")

**Interfaces:** None (documentation only).

- [ ] **Step 1: N/A — documentation task, no test**
- [ ] **Step 2: N/A**

- [ ] **Step 3: Add the new section**

In `README.md`, insert a new `## Bullet Bank Management` section
immediately before the existing `## Bullet bank feedback loop` section:

```markdown
## Bullet Bank Management

The menu's "Manage Bullet Bank" entry (separate from "New User? Start
Here!", which is the full first-time ingestion+profile+pipeline flow) is
for anyone already set up who just needs to run one stage of the
rebuild pipeline at a time. It shows a status table (never run / stale /
up to date, with a timestamp) computed from each stage's actual output
file — no separate tracking file to fall out of sync.

The 6 stages, in the only order that makes sense to run them:

1. **Audit Bullet Bank** (`audit_bullet_bank.py`) — scores every bullet
   (real Gemini calls) → `bullet-bank-audited.csv`
2. **Cluster & Classify** (`cluster_bullet_bank.py`) — embeds + clusters
   near-duplicates, joins audit scores, assigns `next_action` and elects
   `is_representative` per cluster → `bullet-bank-cluster-map.csv`
3. **Rewrite Weak Bullets** (`rewrite_bullets.py`) — rewrites every
   `is_representative=True` row whose `next_action` is `REWRITE` or
   `REVIEW` → `bullet-bank-keepers.csv`
4. **Re-Audit Keepers** (`audit_keepers.py`) — re-scores keepers, diffs
   against the cluster map, builds a triage queue → `bullet-bank-keepers-audited.csv`
5. **Score Hidden Gems** (`score_keeper_gems.py`) — flags standout
   bullets in place on the same file
6. **Embed Bullet Bank** (`embed_bullet_bank.py`) — final embeddings used
   by `orchestrator.py` at runtime to match bullets to a job description

Each stage already checkpoints/resumes internally (same as the full
bootstrap flow) — re-running a stage after an interruption picks up where
it left off.

Two more entries handle the ongoing (non-sequential) feedback loop:
**Triage Needs-Review Queue** (`triage_needs_review.py`) routes rows
`orchestrator.py` queued during a regular resume build into keepers,
the rewrite queue, or retirement; **Retire Abandoned Rewrite-Queue
Bullets** (`retire_rewrite_queue.py`) closes out non-representative rows
still sitting in `rewrite-queue.csv`.
```

- [ ] **Step 4: N/A — no tests for documentation**

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
Document the Bullet Bank Management menu section

Accurate 6-stage order (verified against each script's own path
constants) plus the 2 maintenance scripts, distinct from the full
"New User? Start Here!" bootstrap flow.
EOF
)"
```

## Final Verification

- [ ] Run the full suite one more time: `python -m unittest discover -s tests -v`
  Expected: all tests PASS.
- [ ] Run `resume` bare, open "Manage Bullet Bank," confirm the status
  table is accurate against your real bullet-bank state, run the "Triage
  Needs-Review Queue" action (safe/cheap — no API cost) end to end, and
  confirm the submenu shows updated status and "Back to Main Menu"
  returns to the main loop cleanly.
