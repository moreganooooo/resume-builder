# JD Batch Tracking & Mid-Pipeline Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `python scripts/orchestrator.py` (no arguments) process every not-yet-completed JD in `jds/`, tracking completion in a CSV, moving finished JDs to `jds/completed/`, auto-splitting batch exports into per-job files, and resuming each JD's pipeline from its last checkpoint instead of restarting from scratch if interrupted.

**Architecture:** A new standalone module, `scripts/jd_manager.py`, owns JD intake (splitting batch exports), identity (`compute_job_key`), completion tracking (`JDTracker` over a CSV), and per-job checkpointing (JSON files under `output/checkpoints/`). `scripts/orchestrator.py` imports it: `main()` gains a batch-mode default, and `build_tailored_resume()` / `audit_and_refine_bullets()` gain checkpoint-aware skip/resume logic at each of the 5 expensive steps.

**Tech Stack:** Python 3 stdlib only for `jd_manager.py` (`json`, `csv`, `hashlib`, `os`, `re`, `datetime`) — no new dependencies. Tests use `unittest` (stdlib) since the project has no existing test framework or `pytest` installed.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-01-jd-batch-tracking-design.md` — every requirement in it must map to a task below.
- No new pip dependencies. `jd_manager.py` must import only the Python standard library.
- `jds/jd_tracker_log.csv` must live at that exact path so it's covered by the existing `*_log.csv` gitignore rule (`.gitignore:20`) — job payloads can contain real names/LinkedIn URLs.
- `output/checkpoints/` must live under `output/` so it's covered by the existing `output/` gitignore rule (`.gitignore:22`).
- Existing single-file CLI usage (`python scripts/orchestrator.py jds/some_jd.txt`) must keep working.
- `jds/dummy_jd.txt` is not touched by this work (user is intentionally keeping it for manual testing).
- Tests for `scripts/orchestrator.py` require the project's real dependencies importable (`pandas`, `numpy`, `pyyaml`, `pydantic`, `requests`, `python-dotenv` — see `requirements.txt`). If `python3 -m unittest` fails with `ModuleNotFoundError` for one of these, run `pip3 install -r requirements.txt` in whichever Python environment `python3` resolves to, then retry.

---

### Task 1: `jd_manager.py` — job identity (`compute_job_key`, `extract_job_meta`)

**Files:**
- Create: `scripts/jd_manager.py`
- Create: `tests/test_jd_manager.py`

**Interfaces:**
- Produces: `compute_job_key(jd_path: str) -> str`, `extract_job_meta(jd_path: str) -> tuple[str, str]` (returns `(job_title, company_name)`, `("", "")` if not a JSON object or fields absent), `_meta_from_dict(job: dict) -> tuple[str, str]` (private helper both this task and Task 2 use).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_jd_manager.py`:

```python
import hashlib
import json
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import jd_manager  # noqa: E402


class TestComputeJobKey(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_jd_manager")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_uses_source_job_id_when_present(self):
        path = self._write("job.json", json.dumps({
            "source_job_id": "abc123",
            "job_title": "Engineer",
            "company_name": "Acme",
        }))
        self.assertEqual(jd_manager.compute_job_key(path), "abc123")

    def test_hashes_plain_text_content(self):
        path = self._write("job.txt", "We are hiring a Widget Engineer.")
        expected = hashlib.sha256(b"We are hiring a Widget Engineer.").hexdigest()
        self.assertEqual(jd_manager.compute_job_key(path), expected)

    def test_same_content_same_key(self):
        path_a = self._write("a.txt", "identical posting text")
        path_b = self._write("b.txt", "identical posting text")
        self.assertEqual(jd_manager.compute_job_key(path_a), jd_manager.compute_job_key(path_b))

    def test_different_content_different_key(self):
        path_a = self._write("a.txt", "posting one")
        path_b = self._write("b.txt", "posting two")
        self.assertNotEqual(jd_manager.compute_job_key(path_a), jd_manager.compute_job_key(path_b))

    def test_json_object_without_source_job_id_falls_back_to_hash(self):
        content = json.dumps({"job_title": "Engineer", "company_name": "Acme"})
        path = self._write("job.json", content)
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.assertEqual(jd_manager.compute_job_key(path), expected)


class TestExtractJobMeta(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_jd_manager_meta")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_reads_title_and_company_from_json(self):
        path = self._write("job.json", json.dumps({
            "job_title": "Content Strategist",
            "company_name": "Abnormal AI",
        }))
        self.assertEqual(jd_manager.extract_job_meta(path), ("Content Strategist", "Abnormal AI"))

    def test_plain_text_returns_empty_strings(self):
        path = self._write("job.txt", "Just a plain job description with no JSON.")
        self.assertEqual(jd_manager.extract_job_meta(path), ("", ""))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_jd_manager -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jd_manager'`

- [ ] **Step 3: Write the implementation**

Create `scripts/jd_manager.py`:

```python
"""
jd_manager.py — JD intake, identity, completion tracking, and per-job
checkpointing for the batch resume-building pipeline.

Used by orchestrator.py so it can process every not-yet-completed JD in
jds/ without a per-JD command-line invocation.
"""

import csv
import datetime
import hashlib
import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

JDS_DIR = os.path.join(PROJECT_ROOT, "jds")
COMPLETED_DIR = os.path.join(JDS_DIR, "completed")
CHECKPOINTS_DIR = os.path.join(PROJECT_ROOT, "output", "checkpoints")
TRACKER_CSV = os.path.join(JDS_DIR, "jd_tracker_log.csv")


def _meta_from_dict(job: dict) -> tuple:
    return job.get("job_title", ""), job.get("company_name", "")


def compute_job_key(jd_path: str) -> str:
    """
    Returns the tracking identity for a JD file: its source_job_id if the
    file is a JSON object carrying one, otherwise a SHA-256 hash of the
    file's raw bytes (covers plain-text drop-ins and any JSON without an id).
    """
    with open(jd_path, "rb") as f:
        raw_bytes = f.read()

    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        data = None

    if isinstance(data, dict) and data.get("source_job_id"):
        return str(data["source_job_id"])

    return hashlib.sha256(raw_bytes).hexdigest()


def extract_job_meta(jd_path: str) -> tuple:
    """Returns (job_title, company_name) for a JD file, or ("", "") if it's
    not a JSON object or the fields are absent."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return "", ""

    if isinstance(data, dict):
        return _meta_from_dict(data)
    return "", ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_jd_manager -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/jd_manager.py tests/test_jd_manager.py
git commit -m "Add jd_manager job identity helpers (compute_job_key, extract_job_meta)"
```

---

### Task 2: `jd_manager.py` — `split_batch_jds`

**Files:**
- Modify: `scripts/jd_manager.py` (add `split_batch_jds` and `_sanitize_for_filename`)
- Modify: `tests/test_jd_manager.py` (add `TestSplitBatchJds`)

**Interfaces:**
- Consumes: `_meta_from_dict(job: dict) -> tuple` (Task 1), `JDS_DIR` (Task 1).
- Produces: `split_batch_jds(jd_path: str) -> list[str]` — returns the list of resulting file paths. For a JSON array input, writes one file per element into `JDS_DIR` and deletes the original. For anything else (single JSON object, plain text, invalid JSON), returns `[jd_path]` unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_jd_manager.py` (above the `if __name__ == "__main__":` line):

```python
import datetime


class TestSplitBatchJds(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_split_batch")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_jds_dir = jd_manager.JDS_DIR
        jd_manager.JDS_DIR = self.tmp_dir  # redirect writes into the temp dir for this test

    def tearDown(self):
        jd_manager.JDS_DIR = self._real_jds_dir
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_splits_array_into_one_file_per_job_and_deletes_original(self):
        batch_path = self._write("batch.json", json.dumps([
            {"job_title": "Content Strategist", "company_name": "Abnormal AI"},
            {"job_title": "Senior Manager, Lifecycle Marketing", "company_name": "Superhuman"},
        ]))

        result_paths = jd_manager.split_batch_jds(batch_path)

        self.assertEqual(len(result_paths), 2)
        self.assertFalse(os.path.exists(batch_path))
        today = datetime.date.today().isoformat()
        for path in result_paths:
            self.assertTrue(os.path.basename(path).startswith(today))
            self.assertTrue(os.path.exists(path))
        with open(result_paths[0], "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["company_name"], "Abnormal AI")
        with open(result_paths[1], "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["company_name"], "Superhuman")

    def test_single_json_object_passes_through_unchanged(self):
        path = self._write("single.json", json.dumps({"job_title": "Engineer", "company_name": "Acme"}))
        result_paths = jd_manager.split_batch_jds(path)
        self.assertEqual(result_paths, [path])
        self.assertTrue(os.path.exists(path))

    def test_plain_text_passes_through_unchanged(self):
        path = self._write("plain.txt", "Not JSON at all.")
        result_paths = jd_manager.split_batch_jds(path)
        self.assertEqual(result_paths, [path])
        self.assertTrue(os.path.exists(path))

    def test_filename_collision_gets_numeric_suffix(self):
        batch_path = self._write("batch2.json", json.dumps([
            {"job_title": "Engineer", "company_name": "Acme"},
            {"job_title": "Engineer", "company_name": "Acme"},
        ]))
        result_paths = jd_manager.split_batch_jds(batch_path)
        self.assertEqual(len(result_paths), 2)
        self.assertNotEqual(result_paths[0], result_paths[1])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_jd_manager -v`
Expected: FAIL with `AttributeError: module 'jd_manager' has no attribute 'split_batch_jds'`

- [ ] **Step 3: Write the implementation**

Add to `scripts/jd_manager.py` (after `extract_job_meta`):

```python
def _sanitize_for_filename(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", text or "")
    return cleaned or "Unknown"


def split_batch_jds(jd_path: str) -> list:
    """
    If jd_path contains a JSON array (a batch export), writes one file per
    array element into JDS_DIR named "YYYY-MM-DD_Company_JobTitle.json" and
    deletes the original. Returns the list of new file paths.

    If jd_path is anything else (single JSON object, plain text, invalid
    JSON), returns [jd_path] unchanged.
    """
    with open(jd_path, "r", encoding="utf-8") as f:
        raw = f.read()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [jd_path]

    if not isinstance(data, list):
        return [jd_path]

    os.makedirs(JDS_DIR, exist_ok=True)
    today = datetime.date.today().isoformat()
    new_paths = []

    for job in data:
        job_title, company_name = _meta_from_dict(job) if isinstance(job, dict) else ("", "")
        filename = f"{today}_{_sanitize_for_filename(company_name)}_{_sanitize_for_filename(job_title)}.json"
        dest = os.path.join(JDS_DIR, filename)

        counter = 1
        while os.path.exists(dest):
            dest = os.path.join(JDS_DIR, filename.replace(".json", f"_{counter}.json"))
            counter += 1

        with open(dest, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2, ensure_ascii=False)
        new_paths.append(dest)

    os.remove(jd_path)
    return new_paths
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_jd_manager -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/jd_manager.py tests/test_jd_manager.py
git commit -m "Add jd_manager.split_batch_jds for exploding batch JD exports"
```

---

### Task 3: `jd_manager.py` — `JDTracker` (CSV completion log)

**Files:**
- Modify: `scripts/jd_manager.py` (add `JDTracker`)
- Modify: `tests/test_jd_manager.py` (add `TestJDTracker`)

**Interfaces:**
- Produces: `JDTracker(csv_path: str = None)` with methods `is_completed(job_key: str) -> bool`, `mark_completed(job_key, job_title="", company_name="", source_file="", output_json="", output_pdf="") -> None`, `mark_failed(job_key, job_title="", company_name="", source_file="", error_message="") -> None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_jd_manager.py`:

```python
class TestJDTracker(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_tracker")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.csv_path = os.path.join(self.tmp_dir, "tracker.csv")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def test_unknown_job_key_is_not_completed(self):
        tracker = jd_manager.JDTracker(self.csv_path)
        self.assertFalse(tracker.is_completed("nope"))

    def test_mark_completed_then_is_completed(self):
        tracker = jd_manager.JDTracker(self.csv_path)
        tracker.mark_completed("abc123", job_title="Engineer", company_name="Acme",
                                source_file="abc.json", output_json="output/json/abc.json",
                                output_pdf="output/pdf/abc.pdf")
        self.assertTrue(tracker.is_completed("abc123"))

    def test_mark_failed_does_not_count_as_completed(self):
        tracker = jd_manager.JDTracker(self.csv_path)
        tracker.mark_failed("abc123", job_title="Engineer", company_name="Acme",
                             source_file="abc.json", error_message="builder returned empty")
        self.assertFalse(tracker.is_completed("abc123"))

    def test_failed_then_completed_counts_as_completed(self):
        tracker = jd_manager.JDTracker(self.csv_path)
        tracker.mark_failed("abc123", error_message="transient error")
        tracker.mark_completed("abc123", job_title="Engineer")
        self.assertTrue(tracker.is_completed("abc123"))

    def test_rows_persist_across_tracker_instances(self):
        jd_manager.JDTracker(self.csv_path).mark_completed("xyz")
        second_tracker = jd_manager.JDTracker(self.csv_path)
        self.assertTrue(second_tracker.is_completed("xyz"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_jd_manager -v`
Expected: FAIL with `AttributeError: module 'jd_manager' has no attribute 'JDTracker'`

- [ ] **Step 3: Write the implementation**

Add to `scripts/jd_manager.py`:

```python
TRACKER_FIELDNAMES = [
    "job_key", "job_title", "company_name", "source_file",
    "status", "date_processed", "output_json", "output_pdf", "error_message",
]


class JDTracker:
    """Thin CSV-backed completion log, keyed by job_key."""

    def __init__(self, csv_path: str = None):
        self.csv_path = csv_path or TRACKER_CSV

    def _read_rows(self) -> list:
        if not os.path.exists(self.csv_path):
            return []
        with open(self.csv_path, "r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _append_row(self, row: dict) -> None:
        parent = os.path.dirname(self.csv_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        file_exists = os.path.exists(self.csv_path)
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=TRACKER_FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def is_completed(self, job_key: str) -> bool:
        return any(row["job_key"] == job_key and row["status"] == "completed"
                   for row in self._read_rows())

    def mark_completed(self, job_key, job_title="", company_name="", source_file="",
                        output_json="", output_pdf="") -> None:
        self._append_row({
            "job_key": job_key,
            "job_title": job_title,
            "company_name": company_name,
            "source_file": source_file,
            "status": "completed",
            "date_processed": datetime.datetime.now().isoformat(timespec="seconds"),
            "output_json": output_json,
            "output_pdf": output_pdf,
            "error_message": "",
        })

    def mark_failed(self, job_key, job_title="", company_name="", source_file="",
                     error_message="") -> None:
        self._append_row({
            "job_key": job_key,
            "job_title": job_title,
            "company_name": company_name,
            "source_file": source_file,
            "status": "failed",
            "date_processed": datetime.datetime.now().isoformat(timespec="seconds"),
            "output_json": "",
            "output_pdf": "",
            "error_message": error_message,
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_jd_manager -v`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/jd_manager.py tests/test_jd_manager.py
git commit -m "Add jd_manager.JDTracker CSV completion log"
```

---

### Task 4: `jd_manager.py` — checkpoint helpers

**Files:**
- Modify: `scripts/jd_manager.py` (add `load_checkpoint`, `save_checkpoint`, `delete_checkpoint`)
- Modify: `tests/test_jd_manager.py` (add `TestCheckpoints`)

**Interfaces:**
- Produces: `load_checkpoint(job_key: str) -> dict` (returns `{}` if none exists or the file is unreadable), `save_checkpoint(job_key: str, data: dict) -> None`, `delete_checkpoint(job_key: str) -> None` (no-op if missing).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_jd_manager.py`:

```python
class TestCheckpoints(unittest.TestCase):

    def setUp(self):
        self._real_dir = jd_manager.CHECKPOINTS_DIR
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_checkpoints")
        jd_manager.CHECKPOINTS_DIR = self.tmp_dir

    def tearDown(self):
        jd_manager.CHECKPOINTS_DIR = self._real_dir
        if os.path.isdir(self.tmp_dir):
            for name in os.listdir(self.tmp_dir):
                os.remove(os.path.join(self.tmp_dir, name))
            os.rmdir(self.tmp_dir)

    def test_load_checkpoint_missing_returns_empty_dict(self):
        self.assertEqual(jd_manager.load_checkpoint("nope"), {})

    def test_save_then_load_roundtrip(self):
        jd_manager.save_checkpoint("job1", {"jd_keywords": {"skills": ["python"]}})
        self.assertEqual(jd_manager.load_checkpoint("job1"), {"jd_keywords": {"skills": ["python"]}})

    def test_save_overwrites_previous_checkpoint(self):
        jd_manager.save_checkpoint("job1", {"jd_keywords": {}})
        jd_manager.save_checkpoint("job1", {"jd_keywords": {}, "bullet_tuples": [["a", "b", "c"]]})
        self.assertIn("bullet_tuples", jd_manager.load_checkpoint("job1"))

    def test_delete_checkpoint_removes_file(self):
        jd_manager.save_checkpoint("job1", {"jd_keywords": {}})
        jd_manager.delete_checkpoint("job1")
        self.assertEqual(jd_manager.load_checkpoint("job1"), {})

    def test_delete_checkpoint_missing_is_a_no_op(self):
        jd_manager.delete_checkpoint("never-existed")  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_jd_manager -v`
Expected: FAIL with `AttributeError: module 'jd_manager' has no attribute 'load_checkpoint'`

- [ ] **Step 3: Write the implementation**

Add to `scripts/jd_manager.py`:

```python
def _checkpoint_path(job_key: str) -> str:
    return os.path.join(CHECKPOINTS_DIR, f"{job_key}.json")


def load_checkpoint(job_key: str) -> dict:
    path = _checkpoint_path(job_key)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_checkpoint(job_key: str, data: dict) -> None:
    os.makedirs(CHECKPOINTS_DIR, exist_ok=True)
    with open(_checkpoint_path(job_key), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def delete_checkpoint(job_key: str) -> None:
    path = _checkpoint_path(job_key)
    if os.path.exists(path):
        os.remove(path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_jd_manager -v`
Expected: PASS (20 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/jd_manager.py tests/test_jd_manager.py
git commit -m "Add jd_manager checkpoint load/save/delete helpers"
```

---

### Task 5: `jd_manager.py` — `get_pending_jds`

**Files:**
- Modify: `scripts/jd_manager.py` (add `get_pending_jds`)
- Modify: `tests/test_jd_manager.py` (add `TestGetPendingJds`)

**Interfaces:**
- Consumes: `split_batch_jds`, `compute_job_key`, `JDTracker`, `JDS_DIR`, `COMPLETED_DIR` (all from Tasks 1-3).
- Produces: `get_pending_jds() -> list[str]` — scans `JDS_DIR` at root (ignoring the `completed/` subfolder), splits any batch files first, and returns paths whose job key isn't already marked completed.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_jd_manager.py`:

```python
class TestGetPendingJds(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_pending")
        os.makedirs(self.tmp_dir, exist_ok=True)
        os.makedirs(os.path.join(self.tmp_dir, "completed"), exist_ok=True)
        self._real_jds_dir = jd_manager.JDS_DIR
        self._real_completed_dir = jd_manager.COMPLETED_DIR
        self._real_tracker_csv = jd_manager.TRACKER_CSV
        jd_manager.JDS_DIR = self.tmp_dir
        jd_manager.COMPLETED_DIR = os.path.join(self.tmp_dir, "completed")
        jd_manager.TRACKER_CSV = os.path.join(self.tmp_dir, "tracker.csv")

    def tearDown(self):
        jd_manager.JDS_DIR = self._real_jds_dir
        jd_manager.COMPLETED_DIR = self._real_completed_dir
        jd_manager.TRACKER_CSV = self._real_tracker_csv
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_returns_new_plain_text_jd(self):
        self._write("posting.txt", "A plain-text JD.")
        pending = jd_manager.get_pending_jds()
        self.assertEqual(len(pending), 1)

    def test_splits_batch_file_and_returns_both_jobs(self):
        self._write("batch.json", json.dumps([
            {"job_title": "A", "company_name": "X"},
            {"job_title": "B", "company_name": "Y"},
        ]))
        pending = jd_manager.get_pending_jds()
        self.assertEqual(len(pending), 2)

    def test_already_completed_job_is_excluded(self):
        path = self._write("posting.json", json.dumps({"source_job_id": "done-1", "job_title": "A"}))
        jd_manager.JDTracker().mark_completed("done-1")
        pending = jd_manager.get_pending_jds()
        self.assertEqual(pending, [])

    def test_files_in_completed_subfolder_are_ignored(self):
        completed_path = os.path.join(self.tmp_dir, "completed", "old.txt")
        with open(completed_path, "w", encoding="utf-8") as f:
            f.write("already done")
        pending = jd_manager.get_pending_jds()
        self.assertEqual(pending, [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_jd_manager -v`
Expected: FAIL with `AttributeError: module 'jd_manager' has no attribute 'get_pending_jds'`

- [ ] **Step 3: Write the implementation**

Add to `scripts/jd_manager.py`:

```python
def get_pending_jds() -> list:
    os.makedirs(JDS_DIR, exist_ok=True)
    os.makedirs(COMPLETED_DIR, exist_ok=True)
    tracker = JDTracker(TRACKER_CSV)

    root_files = sorted(
        os.path.join(JDS_DIR, name)
        for name in os.listdir(JDS_DIR)
        if os.path.isfile(os.path.join(JDS_DIR, name))
    )

    all_paths = []
    for path in root_files:
        all_paths.extend(split_batch_jds(path))

    return [p for p in all_paths if not tracker.is_completed(compute_job_key(p))]
```

Note: `JDTracker(TRACKER_CSV)` (not the default-arg form) so the test's monkey-patched `jd_manager.TRACKER_CSV` is honored even though `get_pending_jds` reads the module-level name at call time.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_jd_manager -v`
Expected: PASS (24 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/jd_manager.py tests/test_jd_manager.py
git commit -m "Add jd_manager.get_pending_jds to scan and split jds/ for new work"
```

---

### Task 6: `orchestrator.py` — resumable `audit_and_refine_bullets`

**Files:**
- Modify: `scripts/orchestrator.py` (function `audit_and_refine_bullets`, currently at `scripts/orchestrator.py:884-1098`)
- Create: `tests/test_orchestrator_audit_resume.py`

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: `audit_and_refine_bullets(self, bullet_tuples, static_prefix, resume_from=None, on_bullet_complete=None) -> list`. `resume_from`: bullets already refined in a prior run (the loop skips them). `on_bullet_complete`: optional callable invoked with the full `refined_bullets` list after every single bullet finishes (success or error), so a caller can checkpoint incrementally. Task 7 relies on both new parameters and calls `on_bullet_complete` to persist to `jd_manager.save_checkpoint`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_orchestrator_audit_resume.py`:

```python
import json
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


def _pass_critique_json():
    return json.dumps({
        "manager_test": "PASS",
        "believability_score": 95,
        "hidden_gem_score": 10,
        "hidden_gem_flag": False,
        "hidden_gem_reason": "",
        "weaknesses": "",
    })


class TestAuditResume(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.bullet_tuples = [
            ("Grew revenue 20% via new outbound program.", "CompanyA", "sales"),
            ("Led a team of 5 engineers to ship a new platform.", "CompanyB", "leadership"),
        ]
        self.static_prefix = "STATIC PREFIX FOR TEST"

    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    @patch("orchestrator.GeminiClient.generate")
    def test_resumes_from_partial_refined_bullets(self, mock_generate):
        mock_generate.return_value = (_pass_critique_json(), {})
        checkpoints = []

        result = self.engine.audit_and_refine_bullets(
            self.bullet_tuples,
            self.static_prefix,
            resume_from=[self.bullet_tuples[0][0]],
            on_bullet_complete=lambda partial: checkpoints.append(list(partial)),
        )

        # Only the second (not-yet-refined) bullet should trigger a Gemini call.
        self.assertEqual(mock_generate.call_count, 1)
        # The checkpoint callback fires exactly once, for the newly completed bullet.
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(result, [self.bullet_tuples[0][0], self.bullet_tuples[1][0]])

    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    @patch("orchestrator.GeminiClient.generate")
    def test_no_resume_processes_every_bullet(self, mock_generate):
        mock_generate.return_value = (_pass_critique_json(), {})
        checkpoints = []

        result = self.engine.audit_and_refine_bullets(
            self.bullet_tuples,
            self.static_prefix,
            on_bullet_complete=lambda partial: checkpoints.append(list(partial)),
        )

        self.assertEqual(mock_generate.call_count, 2)
        self.assertEqual(len(checkpoints), 2)
        self.assertEqual(len(result), 2)

    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    @patch("orchestrator.GeminiClient.generate")
    def test_fully_resumed_skips_loop_entirely(self, mock_generate):
        already_done = [b for b, _, _ in self.bullet_tuples]
        result = self.engine.audit_and_refine_bullets(
            self.bullet_tuples,
            self.static_prefix,
            resume_from=already_done,
        )
        mock_generate.assert_not_called()
        self.assertEqual(result, already_done)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_orchestrator_audit_resume -v`
Expected: FAIL with `TypeError: audit_and_refine_bullets() got an unexpected keyword argument 'resume_from'`

(If instead you see `ModuleNotFoundError` for `pandas`/`numpy`/`yaml`/`pydantic`/`dotenv`, run `pip3 install -r requirements.txt` per Global Constraints, then retry.)

- [ ] **Step 3: Modify the implementation**

In `scripts/orchestrator.py`, change the `audit_and_refine_bullets` signature and add the resume/checkpoint logic. Find:

```python
    def audit_and_refine_bullets(
        self,
        bullet_tuples: List[Tuple[str, str, str]],
        static_prefix: str,
    ) -> List[str]:
```

Replace with:

```python
    def audit_and_refine_bullets(
        self,
        bullet_tuples: List[Tuple[str, str, str]],
        static_prefix: str,
        resume_from: List[str] = None,
        on_bullet_complete=None,
    ) -> List[str]:
```

Find the empty-input guard and the line right after it:

```python
        if not isinstance(bullet_tuples, list) or len(bullet_tuples) == 0:
            print("  No bullets to audit -- empty or invalid input. Skipping audit loop.")
            return []

        critique_prompt     = self.load_prompt("critique_bullet.md")
```

Replace with:

```python
        if not isinstance(bullet_tuples, list) or len(bullet_tuples) == 0:
            print("  No bullets to audit -- empty or invalid input. Skipping audit loop.")
            return []

        refined_bullets = list(resume_from) if resume_from else []
        if len(refined_bullets) >= len(bullet_tuples):
            print(f"  Resuming: all {len(bullet_tuples)} bullets already refined in a prior run. "
                  f"Skipping audit loop.")
            return refined_bullets

        critique_prompt     = self.load_prompt("critique_bullet.md")
```

Find where the loop is set up (right before the `for` loop):

```python
        self.warm_segment_cache(bullet_tuples)

        refined_bullets = []
        for i, (bullet, company, tags) in enumerate(bullet_tuples):
            bullet_preview = bullet[:60]
            print(f"\n{'─'*60}")
            print(f"[{i+1}/{len(bullet_tuples)}] {bullet_preview}...")
            print(f"   Tags: {tags}  |  Company: {company}")

            if i > 0:
                time.sleep(CRITIQUE_SLEEP)
```

Replace with:

```python
        self.warm_segment_cache(bullet_tuples)

        start_index = len(refined_bullets)
        if start_index:
            print(f"  Resuming audit loop at bullet {start_index + 1}/{len(bullet_tuples)} "
                  f"(already refined: {start_index}).")

        def _record(refined_bullet: str) -> None:
            refined_bullets.append(refined_bullet)
            if on_bullet_complete:
                on_bullet_complete(list(refined_bullets))

        for i, (bullet, company, tags) in enumerate(bullet_tuples):
            if i < start_index:
                continue

            bullet_preview = bullet[:60]
            print(f"\n{'─'*60}")
            print(f"[{i+1}/{len(bullet_tuples)}] {bullet_preview}...")
            print(f"   Tags: {tags}  |  Company: {company}")

            if i > 0:
                time.sleep(CRITIQUE_SLEEP)
```

Now update the four `refined_bullets.append(...)` call sites inside the loop to use `_record(...)` instead. Find:

```python
                if not critique_text:
                    refined_bullets.append(bullet)
                    continue
```

Replace with:

```python
                if not critique_text:
                    _record(bullet)
                    continue
```

Find:

```python
                    refined_bullets.append(rewritten_bullet)
                else:
                    refined_bullets.append(bullet)

            except Exception as e:
                print(f"   ⚠️  Critique error on bullet {i+1}: {e}")
                refined_bullets.append(bullet)
```

Replace with:

```python
                    _record(rewritten_bullet)
                else:
                    _record(bullet)

            except Exception as e:
                print(f"   ⚠️  Critique error on bullet {i+1}: {e}")
                _record(bullet)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_orchestrator_audit_resume -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full test suite so far**

Run: `python3 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume -v`
Expected: PASS (27 tests total)

- [ ] **Step 6: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_audit_resume.py
git commit -m "Make audit_and_refine_bullets resumable with per-bullet checkpoint hook"
```

---

### Task 7: `orchestrator.py` — checkpoint-aware `build_tailored_resume`

**Files:**
- Modify: `scripts/orchestrator.py` (top-level imports; function `build_tailored_resume`, currently at `scripts/orchestrator.py:1186-1356`)
- Create: `tests/test_orchestrator_build_checkpoint.py`

**Interfaces:**
- Consumes: `jd_manager.compute_job_key`, `jd_manager.load_checkpoint`, `jd_manager.save_checkpoint`, `jd_manager.delete_checkpoint` (Tasks 1 & 4); `audit_and_refine_bullets(..., resume_from=, on_bullet_complete=)` (Task 6).
- Produces: `build_tailored_resume(self, jd_path, master_resume, output_filename=None, job_key=None) -> dict`. On full success (through PDF generation), returns the resume dict with a new `_output_paths` key: `{"json": ..., "html": ..., "pdf": ...}`. On any failure — including a PDF generation failure, which is now treated as a real failure instead of being silently swallowed — returns `{}` and leaves the checkpoint in place for the next run.

- [ ] **Step 1: Write the failing test**

Create `tests/test_orchestrator_build_checkpoint.py`:

```python
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import jd_manager  # noqa: E402


def _pass_critique_json():
    return json.dumps({
        "manager_test": "PASS",
        "believability_score": 95,
        "hidden_gem_score": 10,
        "hidden_gem_flag": False,
        "hidden_gem_reason": "",
        "weaknesses": "",
    })


class TestBuildCheckpointResume(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.jd_path = os.path.join(os.path.dirname(__file__), "_tmp_jd_for_build.txt")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            f.write("We are hiring a Widget Engineer.")
        self.job_key = "test-build-checkpoint-job"
        self.output_filename = "TESTONLY_build_checkpoint_resume.json"
        self.output_path = os.path.join(self.engine.output_json_dir, self.output_filename)

    def tearDown(self):
        if os.path.exists(self.jd_path):
            os.remove(self.jd_path)
        if os.path.exists(self.output_path):
            os.remove(self.output_path)
        jd_manager.delete_checkpoint(self.job_key)

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_skips_keyword_extraction_and_mining_when_checkpointed(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        # Pre-seed a checkpoint as if steps 1 and 2 already ran.
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (json.dumps({
                    "summary_alignment_score": 90,
                    "skills_relevance_score": 90,
                    "overall_fit_score": 90,
                    "flags": [],
                    "recommendations": [],
                }), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(self.engine, "mine_bullet_bank") as mock_mine:
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )
            mock_mine.assert_not_called()

        self.assertTrue(result)
        self.assertIn("_output_paths", result)
        # jd_keywords/bullet_tuples were cached, so GeminiClient.generate should
        # only have been called for: 1 bullet critique + 1 builder call + 1 resume critique.
        self.assertEqual(mock_generate.call_count, 3)
        # Full success deletes the checkpoint.
        self.assertEqual(jd_manager.load_checkpoint(self.job_key), {})

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_pdf_failure_leaves_checkpoint_and_returns_falsy(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (json.dumps({
                    "summary_alignment_score": 90, "skills_relevance_score": 90,
                    "overall_fit_score": 90, "flags": [], "recommendations": [],
                }), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=1, stdout="", stderr="node crashed")

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertEqual(result, {})
        # Checkpoint must survive so the next run doesn't redo the API calls.
        self.assertNotEqual(jd_manager.load_checkpoint(self.job_key), {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_orchestrator_build_checkpoint -v`
Expected: FAIL — `build_tailored_resume()` raises `TypeError: unexpected keyword argument 'job_key'`, or (once that's added naively) the mined-bullets assertion fails because Step 1/2 still always run.

- [ ] **Step 3: Modify the implementation**

In `scripts/orchestrator.py`, add the import near the other local imports at the top of the file. Find:

```python
from render_html import render_html
```

Replace with:

```python
from render_html import render_html
import jd_manager
```

Now find the start of `build_tailored_resume`:

```python
    def build_tailored_resume(
        self,
        jd_path: str,
        master_resume: dict,
        output_filename: str = None,
    ) -> dict:
```

Replace with:

```python
    def build_tailored_resume(
        self,
        jd_path: str,
        master_resume: dict,
        output_filename: str = None,
        job_key: str = None,
    ) -> dict:
```

Find the file-read block and the line right after it:

```python
        try:
            with open(jd_path, "r", encoding="utf-8") as f:
                jd_text = f.read()
        except FileNotFoundError:
            print(f"  ERROR: JD file not found: {jd_path}")
            return {}

        if output_filename is None:
```

Replace with:

```python
        try:
            with open(jd_path, "r", encoding="utf-8") as f:
                jd_text = f.read()
        except FileNotFoundError:
            print(f"  ERROR: JD file not found: {jd_path}")
            return {}

        if job_key is None:
            job_key = jd_manager.compute_job_key(jd_path)
        checkpoint = jd_manager.load_checkpoint(job_key)

        if output_filename is None:
```

Find Step 1:

```python
        # --- Step 1: Extract JD keywords ---
        print("\nStep 1: Extracting JD keywords...")
        extract_prompt = self.load_prompt("extract_keywords.md")
        keyword_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=extract_prompt,
            contents=f"=== JOB DESCRIPTION ===\n{jd_text}",
            response_schema=JDKeywordSchema,
            temperature=0.0,
        )
        jd_keywords: dict = GeminiClient.parse_json(keyword_text or "")
        if not jd_keywords:
            print("  WARNING: JD keyword extraction returned empty. Proceeding with empty keywords.")
        print(f"  Keywords extracted: {json.dumps(jd_keywords, indent=2)[:400]}")
```

Replace with:

```python
        # --- Step 1: Extract JD keywords ---
        print("\nStep 1: Extracting JD keywords...")
        jd_keywords = checkpoint.get("jd_keywords")
        if jd_keywords is not None:
            print("  Resuming: using JD keywords from checkpoint.")
        else:
            extract_prompt = self.load_prompt("extract_keywords.md")
            keyword_text, _ = GeminiClient.generate(
                model=BUILDER_MODEL,
                system_instruction=extract_prompt,
                contents=f"=== JOB DESCRIPTION ===\n{jd_text}",
                response_schema=JDKeywordSchema,
                temperature=0.0,
            )
            jd_keywords = GeminiClient.parse_json(keyword_text or "")
            if not jd_keywords:
                print("  WARNING: JD keyword extraction returned empty. Proceeding with empty keywords.")
            checkpoint["jd_keywords"] = jd_keywords
            jd_manager.save_checkpoint(job_key, checkpoint)
        print(f"  Keywords extracted: {json.dumps(jd_keywords, indent=2)[:400]}")
```

Find Step 2:

```python
        # --- Step 2: Mine bullet bank ---
        print("\nStep 2: Mining bullet bank...")
        bullet_tuples = self.mine_bullet_bank(jd_text, master_resume)
        print(f"  {len(bullet_tuples)} bullet tuples retrieved.")
```

Replace with:

```python
        # --- Step 2: Mine bullet bank ---
        print("\nStep 2: Mining bullet bank...")
        bullet_tuples = checkpoint.get("bullet_tuples")
        if bullet_tuples is not None:
            print(f"  Resuming: using {len(bullet_tuples)} bullet tuples from checkpoint.")
        else:
            bullet_tuples = self.mine_bullet_bank(jd_text, master_resume)
            checkpoint["bullet_tuples"] = bullet_tuples
            jd_manager.save_checkpoint(job_key, checkpoint)
        print(f"  {len(bullet_tuples)} bullet tuples retrieved.")
```

Find Step 3:

```python
        # --- Step 3: Audit and refine bullets ---
        print("\nStep 3: Auditing bullets...")
        static_prefix   = self.build_audit_static_prefix()
        refined_tuples  = self.audit_and_refine_bullets(bullet_tuples, static_prefix)
        refined_bullets = [b for b in refined_tuples if b]  # plain strings for builder
        print(f"  {len(refined_bullets)} bullets after audit.")
```

Replace with:

```python
        # --- Step 3: Audit and refine bullets ---
        print("\nStep 3: Auditing bullets...")
        static_prefix = self.build_audit_static_prefix()

        def _save_bullets_checkpoint(partial_bullets):
            checkpoint["refined_bullets"] = partial_bullets
            jd_manager.save_checkpoint(job_key, checkpoint)

        refined_tuples = self.audit_and_refine_bullets(
            bullet_tuples,
            static_prefix,
            resume_from=checkpoint.get("refined_bullets", []),
            on_bullet_complete=_save_bullets_checkpoint,
        )
        refined_bullets = [b for b in refined_tuples if b]  # plain strings for builder
        checkpoint["refined_bullets"] = refined_tuples
        jd_manager.save_checkpoint(job_key, checkpoint)
        print(f"  {len(refined_bullets)} bullets after audit.")
```

Find Step 4's builder call and its two failure returns:

```python
        build_prompt = self.load_prompt("tailor_resume.md")

        kb_context = self.load_knowledge_base()
```

Replace with:

```python
        resume_data = checkpoint.get("resume_data")
        if resume_data is not None:
            print("  Resuming: using resume JSON from checkpoint.")
        else:
            build_prompt = self.load_prompt("tailor_resume.md")

            kb_context = self.load_knowledge_base()
```

Find the rest of the (still-unindented) Step 4 body, from `builder_system` through the two early returns and the `resume_data = GeminiClient.parse_json(resume_text)` line:

```python
        builder_system = f"{build_prompt}\n\n{kb_context}"

        bullets_block = "\n".join(f"- {b}" for b in refined_bullets)
        combined_contents = (
            f"=== JD KEYWORDS ===\n{json.dumps(jd_keywords)}\n\n"
            f"=== JOB DESCRIPTION ===\n{jd_text}\n\n"
            f"=== MASTER RESUME ===\n{json.dumps(master_resume, indent=2)}\n\n"
            f"=== REFINED BULLETS ===\n{bullets_block}"
        )

        print(f"  builder_system size: {len(builder_system)} chars / ~{len(builder_system)//4} tokens")
        print(f"  combined_contents size: {len(combined_contents)} chars / ~{len(combined_contents)//4} tokens")

        resume_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=builder_system,
            contents=combined_contents,
            response_schema=TemplateSchema,
            temperature=0.0,
        )

        if not resume_text:
            print("  ERROR: Builder returned empty response.")
            return {}

        resume_data = GeminiClient.parse_json(resume_text)
        if not resume_data:
            print("  ERROR: Could not parse builder JSON.")
            print(f"  Raw response (first 500 chars):\n{resume_text[:500]}")
            return {}
```

Replace with (note the new 4-space indent, since this is now inside the `else:` block, and the added checkpoint save at the end):

```python
            builder_system = f"{build_prompt}\n\n{kb_context}"

            bullets_block = "\n".join(f"- {b}" for b in refined_bullets)
            combined_contents = (
                f"=== JD KEYWORDS ===\n{json.dumps(jd_keywords)}\n\n"
                f"=== JOB DESCRIPTION ===\n{jd_text}\n\n"
                f"=== MASTER RESUME ===\n{json.dumps(master_resume, indent=2)}\n\n"
                f"=== REFINED BULLETS ===\n{bullets_block}"
            )

            print(f"  builder_system size: {len(builder_system)} chars / ~{len(builder_system)//4} tokens")
            print(f"  combined_contents size: {len(combined_contents)} chars / ~{len(combined_contents)//4} tokens")

            resume_text, _ = GeminiClient.generate(
                model=BUILDER_MODEL,
                system_instruction=builder_system,
                contents=combined_contents,
                response_schema=TemplateSchema,
                temperature=0.0,
            )

            if not resume_text:
                print("  ERROR: Builder returned empty response.")
                return {}

            resume_data = GeminiClient.parse_json(resume_text)
            if not resume_data:
                print("  ERROR: Could not parse builder JSON.")
                print(f"  Raw response (first 500 chars):\n{resume_text[:500]}")
                return {}

            checkpoint["resume_data"] = resume_data
            jd_manager.save_checkpoint(job_key, checkpoint)
```

Find Step 5:

```python
        # --- Step 5: Post-build holistic critique ---
        print("\nStep 5: Running holistic resume critique...")
        critique_prompt = self.load_prompt("critique_resume.md")
        critique_contents = (
            f"=== JOB DESCRIPTION ===\n{jd_text}\n\n"
            f"=== RESUME JSON ===\n{json.dumps(resume_data, indent=2)}"
        )
        critique_text, _ = GeminiClient.generate(
            model=CRITIQUE_MODEL,
            system_instruction=critique_prompt,
            contents=critique_contents,
            response_schema=ResumeCritiqueSchema,
            temperature=0.0,
        )
        if critique_text:
            critique_data = GeminiClient.parse_json(critique_text)
            print(f"  Holistic critique scores:")
            print(f"    summary_alignment : {critique_data.get('summary_alignment_score', '?')}")
            print(f"    skills_relevance  : {critique_data.get('skills_relevance_score',  '?')}")
            print(f"    overall_fit       : {critique_data.get('overall_fit_score',        '?')}")
            flags = critique_data.get("flags", [])
            if flags:
                print("  Flags:")
                for flag in flags:
                    print(f"    - {flag}")
            recs = critique_data.get("recommendations", [])
            if recs:
                print("  Recommendations:")
                for rec in recs:
                    print(f"    - {rec}")
            resume_data["_critique"] = critique_data
        else:
            print("  WARNING: Holistic critique returned empty.")
```

Replace with:

```python
        # --- Step 5: Post-build holistic critique ---
        print("\nStep 5: Running holistic resume critique...")
        critique_data = checkpoint.get("critique_data")
        if critique_data is not None:
            print("  Resuming: using holistic critique from checkpoint.")
            resume_data["_critique"] = critique_data
        else:
            critique_prompt = self.load_prompt("critique_resume.md")
            critique_contents = (
                f"=== JOB DESCRIPTION ===\n{jd_text}\n\n"
                f"=== RESUME JSON ===\n{json.dumps(resume_data, indent=2)}"
            )
            critique_text, _ = GeminiClient.generate(
                model=CRITIQUE_MODEL,
                system_instruction=critique_prompt,
                contents=critique_contents,
                response_schema=ResumeCritiqueSchema,
                temperature=0.0,
            )
            if critique_text:
                critique_data = GeminiClient.parse_json(critique_text)
                print(f"  Holistic critique scores:")
                print(f"    summary_alignment : {critique_data.get('summary_alignment_score', '?')}")
                print(f"    skills_relevance  : {critique_data.get('skills_relevance_score',  '?')}")
                print(f"    overall_fit       : {critique_data.get('overall_fit_score',        '?')}")
                flags = critique_data.get("flags", [])
                if flags:
                    print("  Flags:")
                    for flag in flags:
                        print(f"    - {flag}")
                recs = critique_data.get("recommendations", [])
                if recs:
                    print("  Recommendations:")
                    for rec in recs:
                        print(f"    - {rec}")
                resume_data["_critique"] = critique_data
                checkpoint["critique_data"] = critique_data
                jd_manager.save_checkpoint(job_key, checkpoint)
            else:
                print("  WARNING: Holistic critique returned empty.")
```

Finally, find the end of the method:

```python
        pdf_result = subprocess.run(
            ["node", pdf_script, html_out, pdf_out, "--format=letter"],
            capture_output=True, text=True
        )
        if pdf_result.returncode == 0:
            print(pdf_result.stdout)
            print(f"  🎉 Pipeline complete! PDF → {pdf_out}")
        else:
            print(f"  ⚠️  PDF generation failed:\n{pdf_result.stderr}")

        return resume_data
```

Replace with:

```python
        pdf_result = subprocess.run(
            ["node", pdf_script, html_out, pdf_out, "--format=letter"],
            capture_output=True, text=True
        )
        if pdf_result.returncode != 0:
            print(f"  ⚠️  PDF generation failed:\n{pdf_result.stderr}")
            return {}

        print(pdf_result.stdout)
        print(f"  🎉 Pipeline complete! PDF → {pdf_out}")
        jd_manager.delete_checkpoint(job_key)
        resume_data["_output_paths"] = {"json": output_path, "html": html_out, "pdf": pdf_out}

        return resume_data
```

**Behavior change to note:** previously a PDF generation failure still returned `resume_data` (a "success" from the caller's point of view). It now returns `{}`, so the batch loop in Task 8 will correctly mark the JD as failed/pending-for-retry rather than as completed — this is required for the checkpoint-deletion and CSV-tracking contract to be coherent.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_orchestrator_build_checkpoint -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full test suite so far**

Run: `python3 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint -v`
Expected: PASS (29 tests total)

- [ ] **Step 6: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_build_checkpoint.py
git commit -m "Make build_tailored_resume checkpoint-aware and resumable per JD"
```

---

### Task 8: `orchestrator.py` — batch mode in `main()`

**Files:**
- Modify: `scripts/orchestrator.py` (function `main`, currently at `scripts/orchestrator.py:1363-1395`; add `import shutil` near the top)
- Create: `tests/test_orchestrator_main_batch.py`

**Interfaces:**
- Consumes: `jd_manager.get_pending_jds`, `jd_manager.compute_job_key`, `jd_manager.extract_job_meta`, `jd_manager.JDTracker`, `jd_manager.COMPLETED_DIR` (Task 5, Task 1, Task 3); `ResumeEngine.build_tailored_resume(..., job_key=...)` (Task 7).
- Produces: `main()` — no positional arg runs batch mode over `jd_manager.get_pending_jds()`; a path arg runs single-file mode. Both paths update the CSV tracker and move successfully completed JD files into `jd_manager.COMPLETED_DIR`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_orchestrator_main_batch.py`:

```python
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestMainBatchMode(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_main_batch")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.completed_dir = os.path.join(self.tmp_dir, "completed")
        os.makedirs(self.completed_dir, exist_ok=True)

        self.good_path = os.path.join(self.tmp_dir, "good.txt")
        self.bad_path = os.path.join(self.tmp_dir, "bad.txt")
        for path in (self.good_path, self.bad_path):
            with open(path, "w", encoding="utf-8") as f:
                f.write("a JD")

        self._real_completed_dir = orchestrator.jd_manager.COMPLETED_DIR
        orchestrator.jd_manager.COMPLETED_DIR = self.completed_dir

    def tearDown(self):
        orchestrator.jd_manager.COMPLETED_DIR = self._real_completed_dir
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.tmp_dir)

    @patch("orchestrator.jd_manager.JDTracker")
    @patch("orchestrator.jd_manager.get_pending_jds")
    @patch.object(orchestrator.ResumeEngine, "build_tailored_resume")
    def test_batch_mode_marks_completed_and_failed_and_moves_files(
        self, mock_build, mock_get_pending, mock_tracker_cls
    ):
        mock_get_pending.return_value = [self.good_path, self.bad_path]

        def build_side_effect(jd_path, master_resume, output_filename=None, job_key=None):
            if jd_path == self.good_path:
                return {"_output_paths": {"json": "j.json", "html": "h.html", "pdf": "p.pdf"}}
            return {}

        mock_build.side_effect = build_side_effect
        mock_tracker = mock_tracker_cls.return_value

        with patch.object(sys, "argv", ["orchestrator.py"]):
            orchestrator.main()

        mock_tracker.mark_completed.assert_called_once()
        mock_tracker.mark_failed.assert_called_once()
        self.assertTrue(os.path.exists(os.path.join(self.completed_dir, "good.txt")))
        self.assertFalse(os.path.exists(self.good_path))
        # A failed JD stays in place (pending) for the next run to retry.
        self.assertTrue(os.path.exists(self.bad_path))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_orchestrator_main_batch -v`
Expected: FAIL — `main()` currently requires a positional `jd` argument, so `sys.argv = ["orchestrator.py"]` raises `SystemExit` from argparse.

- [ ] **Step 3: Modify the implementation**

In `scripts/orchestrator.py`, add `import shutil` next to the other stdlib imports at the top of the file. Find:

```python
import subprocess
from pathlib import Path
```

Replace with:

```python
import subprocess
import shutil
from pathlib import Path
```

Now find `main()`:

```python
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Resume Builder Orchestrator")
    parser.add_argument("jd", help="Path to the job description .txt or .md file")
    parser.add_argument("--master", default=None, help="Path to master resume JSON (optional)")
    parser.add_argument("--output", default=None, help="Output JSON filename (optional)")
    args = parser.parse_args()

    master_resume = {}
    if args.master:
        try:
            with open(args.master, "r", encoding="utf-8") as f:
                master_resume = json.load(f)
            print(f"Loaded master resume from: {args.master}")
        except Exception as e:
            print(f"WARNING: Could not load master resume: {e}. Proceeding with empty dict.")

    engine = ResumeEngine()
    result = engine.build_tailored_resume(
        jd_path=args.jd,
        master_resume=master_resume,
        output_filename=args.output,
    )

    if result:
        print("\nDone! Resume built successfully.")
    else:
        print("\nERROR: Resume build failed. Check output above for details.")
        raise SystemExit(1)
```

Replace with:

```python
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Resume Builder Orchestrator")
    parser.add_argument(
        "jd", nargs="?", default=None,
        help="Path to a specific JD file. Omit to batch-process everything pending in jds/.",
    )
    parser.add_argument("--master", default=None, help="Path to master resume JSON (optional)")
    parser.add_argument("--output", default=None, help="Output JSON filename (single-JD mode only)")
    args = parser.parse_args()

    master_resume = {}
    if args.master:
        try:
            with open(args.master, "r", encoding="utf-8") as f:
                master_resume = json.load(f)
            print(f"Loaded master resume from: {args.master}")
        except Exception as e:
            print(f"WARNING: Could not load master resume: {e}. Proceeding with empty dict.")

    engine = ResumeEngine()
    tracker = jd_manager.JDTracker()

    if args.jd:
        jd_paths = [args.jd]
    else:
        jd_paths = jd_manager.get_pending_jds()
        if not jd_paths:
            print("\nNo pending JDs found in jds/. Nothing to do.")
            return

    completed_count = 0
    failed_count = 0

    for jd_path in jd_paths:
        try:
            job_key = jd_manager.compute_job_key(jd_path)
        except OSError as e:
            print(f"  ERROR: Could not read JD file {jd_path}: {e}")
            continue

        job_title, company_name = jd_manager.extract_job_meta(jd_path)

        try:
            result = engine.build_tailored_resume(
                jd_path=jd_path,
                master_resume=master_resume,
                output_filename=args.output if args.jd else None,
                job_key=job_key,
            )
        except Exception as e:
            result = None
            print(f"  ERROR: Unhandled exception building resume for {jd_path}: {e}")

        if result:
            output_paths = result.get("_output_paths", {})
            os.makedirs(jd_manager.COMPLETED_DIR, exist_ok=True)
            dest = os.path.join(jd_manager.COMPLETED_DIR, os.path.basename(jd_path))
            shutil.move(jd_path, dest)
            tracker.mark_completed(
                job_key=job_key,
                job_title=job_title,
                company_name=company_name,
                source_file=os.path.basename(jd_path),
                output_json=output_paths.get("json", ""),
                output_pdf=output_paths.get("pdf", ""),
            )
            completed_count += 1
            print(f"\nDone! Resume built successfully for {jd_path}.")
        else:
            tracker.mark_failed(
                job_key=job_key,
                job_title=job_title,
                company_name=company_name,
                source_file=os.path.basename(jd_path),
                error_message="Resume build failed. Check output above for details.",
            )
            failed_count += 1
            print(f"\nERROR: Resume build failed for {jd_path}. It stays pending and will be retried next run.")

    print(f"\nBatch summary: {completed_count} completed, {failed_count} failed.")

    if args.jd and failed_count and not completed_count:
        raise SystemExit(1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_orchestrator_main_batch -v`
Expected: PASS (1 test)

- [ ] **Step 5: Run the full automated test suite**

Run: `python3 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch -v`
Expected: PASS (30 tests total)

- [ ] **Step 6: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_main_batch.py
git commit -m "Add batch mode to orchestrator main(): process every pending JD in jds/"
```

---

### Task 9: Manual end-to-end verification

**Files:** none (verification only, no code changes)

This exercises the real pipeline (real Gemini calls) the way the automated tests intentionally don't, per the spec's Testing section.

- [ ] **Step 1: Set up two fake jobs in a batch file**

```bash
cat > jds/_manual_test_batch.json <<'EOF'
[
  {"job_title": "Manual Test Job One", "company_name": "TestCo", "description": "We need someone great at writing clear content."},
  {"job_title": "Manual Test Job Two", "company_name": "TestCo", "description": "We need someone great at managing projects."}
]
EOF
```

- [ ] **Step 2: Run batch mode and confirm the split + both jobs process**

```bash
python3 scripts/orchestrator.py
```

Expected: console shows the batch file getting split into 2 files, then each processed through all 7 steps, ending with `Batch summary: 2 completed, 0 failed.` Confirm both files moved into `jds/completed/`, and `jds/jd_tracker_log.csv` has 2 new rows with `status=completed`.

- [ ] **Step 2: Run again with nothing new pending**

```bash
python3 scripts/orchestrator.py
```

Expected: `No pending JDs found in jds/. Nothing to do.`

- [ ] **Step 3: Verify mid-pipeline resume**

Drop one more fake job into `jds/`, start a batch run, and interrupt it (Ctrl+C) partway through Step 3's bullet audit loop (watch the console for `[N/M]` progress lines and kill it after the first one or two bullets print). Rerun:

```bash
python3 scripts/orchestrator.py
```

Expected: console shows `Resuming: using JD keywords from checkpoint.` and `Resuming: using N bullet tuples from checkpoint.` for steps 1-2, and `Resuming audit loop at bullet K/M` for step 3, where `K` matches how many bullets had already printed before the interruption. The run then completes normally and the checkpoint file for that job is deleted from `output/checkpoints/`.

- [ ] **Step 4: Clean up test artifacts**

```bash
rm -f jds/completed/*ManualTestJob* jds/completed/*.json
# (remove only the manual test rows/files created above; leave jds/jd_tracker_log.csv history intact
#  unless you want to reset it, and leave dummy_jd.txt alone per the earlier decision to keep it)
```

## Plan Self-Review

**Spec coverage:**
- Auto-split batch exports → Task 2 (`split_batch_jds`).
- Track completion in a CSV → Task 3 (`JDTracker`).
- Move completed JDs to their own folder → Task 8 (`main()` moves to `jd_manager.COMPLETED_DIR`).
- Process only new JDs by default (no-arg batch mode) → Task 8.
- Single-file mode still works → Task 8 (`args.jd` branch).
- Content-hash identity for plain text, source_job_id for JSON → Task 1.
- `Date_Company_JobTitle.json` naming → Task 2.
- Failures stay pending for retry → Task 3 (`mark_failed` doesn't count as completed) + Task 8 (file not moved on failure).
- Mid-pipeline resume, checkpointed per bullet in the audit loop → Task 4 (checkpoint helpers) + Task 6 (resumable audit loop) + Task 7 (checkpoint wiring through all 5 steps).
- `dummy_jd.txt` left alone → called out explicitly in Global Constraints; no task touches it.

**Placeholder scan:** no TBD/TODO; every step has complete, runnable code and exact commands.

**Type consistency:** `compute_job_key`, `extract_job_meta`, `split_batch_jds`, `JDTracker`, `load_checkpoint`/`save_checkpoint`/`delete_checkpoint`, and `get_pending_jds` are defined once in Task 1-5 and referenced with the same names/signatures in Tasks 6-8. `audit_and_refine_bullets`'s new `resume_from`/`on_bullet_complete` params (Task 6) match exactly how Task 7 calls them. `build_tailored_resume`'s new `job_key` param and `_output_paths` return key (Task 7) match exactly how Task 8 consumes them.
